"""CVAT Smart Model Service — Multi-task inference server.

Provides endpoints for semantic segmentation, object detection, keypoint
estimation and more. Each endpoint applies image enhancement automatically
and returns annotations in CVAT-compatible format.

Architecture: FastAPI + handlers pattern.  Each task lives in handlers/.
Nuclio thin adapters call these endpoints via HTTP.
"""
from __future__ import annotations

import base64
import io
import os
import threading
from typing import Any

import numpy as np
import torch
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from PIL import Image

from enhancement import enhance_image

app = FastAPI(title="CVAT Smart Model Service", version="3.0.0")


# ---------------------------------------------------------------------------
# Concurrency model — read this before turning any endpoint back into `async def`
# ---------------------------------------------------------------------------
# Every inference handler below is SYNCHRONOUS and blocking (torch,
# transformers, ultralytics, OpenCV).  A plain `def` endpoint is executed by
# FastAPI in Starlette's threadpool, so the asyncio event loop stays free and a
# slow request delays only itself.  Declaring the same endpoint `async def`
# instead runs it *on* the event loop, where one blocking call freezes every
# other request in the process — including /health and endpoints that share no
# state with it.  That is what turned a one-off 42 MB weight download into a
# total service outage.  Keep these endpoints synchronous; if one ever genuinely
# needs to be async, push the blocking part out with `await run_in_threadpool`.
#
# The locks serialise a *cold* model load.  handlers/* cache their models with
# `lru_cache`, which does not lock on a cache miss: two concurrent cold requests
# would each build their own copy, and a second EoMT or SAM2 instance does not
# fit beside the first on an 8 GB card.  They also serialise inference, which is
# the correct behaviour for a single GPU and matches the previous (fully
# serialised) behaviour — minus the event-loop stall.
_SEMANTIC_LOCK = threading.Lock()  # /segment-semantic + /segment-drivable (share EoMT)
_SAM2_LOCK = threading.Lock()      # /segment-auto
_YOLO_LOCK = threading.Lock()      # /detect


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

def _device() -> str:
    requested = os.getenv("SAM2_DEVICE", "cuda")
    if requested == "cuda" and not torch.cuda.is_available():
        return "cpu"
    return requested


def _checkpoint_details() -> dict[str, Any]:
    checkpoint = os.getenv("SAM2_CHECKPOINT", "/models/sam2.1_hiera_large.pt")
    exists = os.path.exists(checkpoint)
    size = os.path.getsize(checkpoint) if exists else 0
    return {"path": checkpoint, "exists": exists, "size_bytes": size}


def _mask_png(mask: np.ndarray) -> str:
    """Encode a boolean mask as a base64 PNG string."""
    image = Image.fromarray((mask.astype(np.uint8) * 255), mode="L")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _decode_image(raw: bytes) -> tuple[Image.Image, np.ndarray]:
    """Decode raw bytes into PIL image and numpy RGB array."""
    pil_image = Image.open(io.BytesIO(raw)).convert("RGB")
    if os.getenv("ENHANCE_ENABLED", "true").lower() in {"1", "true", "yes"}:
        pil_image = enhance_image(pil_image)
    rgb = np.asarray(pil_image)
    return pil_image, rgb


# ---------------------------------------------------------------------------
# Health & Root
# ---------------------------------------------------------------------------

@app.get("/")
def root() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "CVAT Smart Model Service",
        "version": "3.0.0",
        "endpoints": {
            "health": "/health",
            "segment_semantic": "/segment-semantic",
            "segment_drivable": "/segment-drivable",
            "segment_auto": "/segment-auto",
            "segment_lane": "/segment-lane",
            "detect": "/detect",
            "keypoint": "/keypoint (coming soon)",
        },
    }


@app.get("/health")
def health() -> dict[str, Any]:
    checkpoint_info = _checkpoint_details()
    return {
        "status": "ok",
        "service": "CVAT Smart Model Service",
        "version": "3.0.0",
        "device": _device(),
        "cuda_available": torch.cuda.is_available(),
        "cuda_device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "checkpoint_path": checkpoint_info["path"],
        "checkpoint_exists": checkpoint_info["exists"],
        "checkpoint_size_bytes": checkpoint_info["size_bytes"],
        "semantic_backend": os.getenv("SEMANTIC_BACKEND", "segformer"),
        "semantic_model_id": os.getenv("SEMANTIC_MODEL_ID", ""),
        "semantic_refine": os.getenv("SEMANTIC_REFINE", "true").lower() in {"1", "true", "yes"},
        "semantic_split_instances": os.getenv("SEMANTIC_SPLIT_INSTANCES", "true").lower() in {"1", "true", "yes"},
        "semantic_min_component_area": int(os.getenv("SEMANTIC_MIN_COMPONENT_AREA", "100")),
        "enhance_dark_regions": os.getenv("ENHANCE_DARK_REGIONS", "true").lower() in {"1", "true", "yes"},
        "enhance_motion_blur": os.getenv("ENHANCE_MOTION_BLUR", "false").lower() in {"1", "true", "yes"},
        "lane_device": "cpu",
        "lane_max_depth_m": os.getenv("LANE_MAX_DEPTH_M", "12.0"),
        "lane_bird_ppm": os.getenv("LANE_BIRD_PPM", "40.0"),
        "lane_curb_enabled": os.getenv("LANE_CURB_ENABLED", "false").lower() in {"1", "true", "yes"},
    }


# ---------------------------------------------------------------------------
# Semantic Segmentation endpoint
# ---------------------------------------------------------------------------

@app.post("/segment-semantic")
def segment_semantic(image: UploadFile = File(...)) -> dict[str, Any]:
    """Run semantic segmentation with optional SAM2 boundary refinement.

    Returns masks in internal format (mask_png_base64) for flexibility.
    The Nuclio adapter converts to CVAT-native polygon or mask format.
    """
    try:
        from handlers.segment import run_semantic_segmentation
        raw = image.file.read()
        pil_image, rgb = _decode_image(raw)
        with _SEMANTIC_LOCK:
            return run_semantic_segmentation(pil_image, rgb)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Semantic segmentation failed: {exc}") from exc


@app.post("/segment-drivable")
def segment_drivable(image: UploadFile = File(...)) -> dict[str, Any]:
    """Drivable-area segmentation (Polygon) via EoMT COCO-panoptic.

    Approximates `area/drivable` from COCO `road` and `area/alternative`
    from COCO `pavement-merged`. Lane marking is returned as an explicit
    limitation (COCO has no lane classes).
    """
    try:
        from handlers.segment import run_drivable_segmentation
        raw = image.file.read()
        pil_image, rgb = _decode_image(raw)
        with _SEMANTIC_LOCK:
            return run_drivable_segmentation(rgb)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Drivable segmentation failed: {exc}") from exc


@app.post("/segment-lane")
def segment_lane(image: UploadFile = File(...)) -> dict[str, Any]:
    """Lane marking detection (Polyline) via classical CV.

    Runs entirely on the CPU on purpose. The detector needs no training data
    and no VRAM, so it costs nothing next to the GPU-resident YOLO26 / EoMT /
    SAM2 models, which is what makes it affordable on an 8 GB card. It also
    holds no cached model, so it takes no lock and stays parallel to the
    GPU-backed endpoints.
    """
    try:
        from handlers.lane import run_lane_detection
        raw = image.file.read()
        pil_image, rgb = _decode_image(raw)
        return run_lane_detection(rgb)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Lane detection failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Automatic Mask Generation (SAM2 standalone)
# ---------------------------------------------------------------------------

@app.post("/segment-auto")
def segment_auto(
    image: UploadFile = File(...),
    points_per_side: int = Form(16),
    pred_iou_thresh: float = Form(0.86),
    stability_score_thresh: float = Form(0.92),
    min_mask_region_area: int = Form(150),
    max_masks: int = Form(40),
) -> dict[str, Any]:
    """Generate masks using SAM2 automatic mask generator."""
    try:
        from handlers.segment import run_auto_segmentation
        raw = image.file.read()
        pil_image, rgb = _decode_image(raw)
        with _SAM2_LOCK:
            return run_auto_segmentation(
                rgb, points_per_side, pred_iou_thresh,
                stability_score_thresh, min_mask_region_area, max_masks,
            )
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"SAM2 segmentation failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Object Detection (YOLO26)
# ---------------------------------------------------------------------------

@app.post("/detect")
def detect(
    image: UploadFile = File(...),
    conf: float = Form(0.25),
    iou: float = Form(0.45),
) -> dict[str, Any]:
    """Run YOLO26 object detection and return guideline-mapped bounding boxes."""
    from handlers.detect import run_detection

    try:
        raw = image.file.read()
        pil_image = Image.open(io.BytesIO(raw)).convert("RGB")
        conf = float(os.getenv("YOLO26_CONF", str(conf)))
        iou = float(os.getenv("YOLO26_IOU", str(iou)))
        with _YOLO_LOCK:
            return run_detection(pil_image, conf_threshold=conf, iou_threshold=iou)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Object detection failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Keypoint Estimation (Phase 3 — placeholder)
# ---------------------------------------------------------------------------

@app.post("/keypoint")
async def keypoint(image: UploadFile = File(...)) -> dict[str, Any]:
    """Keypoint estimation endpoint (coming in Phase 3)."""
    raise HTTPException(status_code=501, detail="Keypoint estimation not yet implemented. Coming in Phase 3.")
