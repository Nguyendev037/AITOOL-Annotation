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
from typing import Any

import numpy as np
import torch
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from PIL import Image

from enhancement import enhance_image

app = FastAPI(title="CVAT Smart Model Service", version="3.0.0")


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
    }


# ---------------------------------------------------------------------------
# Semantic Segmentation endpoint
# ---------------------------------------------------------------------------

@app.post("/segment-semantic")
async def segment_semantic(image: UploadFile = File(...)) -> dict[str, Any]:
    """Run semantic segmentation with optional SAM2 boundary refinement.

    Returns masks in internal format (mask_png_base64) for flexibility.
    The Nuclio adapter converts to CVAT-native polygon or mask format.
    """
    try:
        from handlers.segment import run_semantic_segmentation
        raw = await image.read()
        pil_image, rgb = _decode_image(raw)
        return run_semantic_segmentation(pil_image, rgb)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Semantic segmentation failed: {exc}") from exc


@app.post("/segment-drivable")
async def segment_drivable(image: UploadFile = File(...)) -> dict[str, Any]:
    """Drivable-area segmentation (Polygon) via EoMT COCO-panoptic.

    Approximates `area/drivable` from COCO `road` and `area/alternative`
    from COCO `pavement-merged`. Lane marking is returned as an explicit
    limitation (COCO has no lane classes).
    """
    try:
        from handlers.segment import run_drivable_segmentation
        raw = await image.read()
        pil_image, rgb = _decode_image(raw)
        return run_drivable_segmentation(rgb)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Drivable segmentation failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Automatic Mask Generation (SAM2 standalone)
# ---------------------------------------------------------------------------

@app.post("/segment-auto")
async def segment_auto(
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
        raw = await image.read()
        pil_image, rgb = _decode_image(raw)
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
async def detect(
    image: UploadFile = File(...),
    conf: float = Form(0.25),
    iou: float = Form(0.45),
) -> dict[str, Any]:
    """Run YOLO26 object detection and return guideline-mapped bounding boxes."""
    from handlers.detect import run_detection

    try:
        raw = await image.read()
        pil_image = Image.open(io.BytesIO(raw)).convert("RGB")
        conf = float(os.getenv("YOLO26_CONF", str(conf)))
        iou = float(os.getenv("YOLO26_IOU", str(iou)))
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
