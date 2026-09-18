"""Semantic segmentation handler.

Refactored from sam-service/app.py. Provides two inference modes:
1. Semantic segmentation (SegFormer/EoMT/Mask2Former + SAM2 refine)
2. Automatic mask generation (SAM2 standalone)
"""
from __future__ import annotations

import base64
import io
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image
from scipy.ndimage import label as cc_label


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# The label taxonomy is generated from `taxonomy.yaml` by
# `tools/sync_taxonomy.py` and baked into the image by the Dockerfile
# (`COPY . /opt/service/`). Never hardcode label names here: regenerate with
#     python tools/sync_taxonomy.py --write
# and rebuild. A missing artifact is a hard error on purpose, so the service can
# never start with a stale label map.
TAXONOMY_PATH = Path(__file__).resolve().parent.parent / "taxonomy.json"
if not TAXONOMY_PATH.is_file():
    raise RuntimeError(
        f"taxonomy artifact missing at {TAXONOMY_PATH}; "
        "run `python tools/sync_taxonomy.py --write` and rebuild the image"
    )
TAXONOMY = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
DRIVABLE_TASK = TAXONOMY["tasks"]["drivable"]
LANE_GROUP = TAXONOMY["unsupported"]["lane"]


def _normalize_label(label: str) -> str:
    """Normalise a model class name for taxonomy lookups.

    EoMT's id2label carries names such as "traffic light" and
    "pavement-merged", so both sides of every map are normalised identically.
    """
    return label.strip().lower().replace(" ", "_")


# Declared 19-class Cityscapes taxonomy, used only when the loaded model exposes
# no id2label of its own (see `_semantic_labels`).
CITYSCAPES_LABELS = list(TAXONOMY["tasks"]["semantic"]["declared"])

REFINABLE_THING_LABELS = {
    "person", "rider", "car", "truck", "bus", "train", "motorcycle", "bicycle",
    "traffic_light", "traffic_sign",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _device() -> str:
    requested = os.getenv("SAM2_DEVICE", "cuda")
    if requested == "cuda" and not torch.cuda.is_available():
        return "cpu"
    return requested


def _mask_png(mask: np.ndarray) -> str:
    image = Image.fromarray((mask.astype(np.uint8) * 255), mode="L")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _to_device(inputs, device: str):
    """Move a BatchFeature/dict of model inputs to `device`.

    Some processors return lists (e.g. EoMT's `patch_offsets`) alongside
    tensors; calling `.to()` on a plain list raises
    `'list' object has no attribute 'to'`. Only torch tensors are moved.
    """
    return {key: value.to(device) if torch.is_tensor(value) else value
            for key, value in inputs.items()}


# COCO panoptic class name -> guideline drivable-area label, from taxonomy.yaml.
# EoMT-DINOv3 (COCO panoptic) has no `area/drivable` / `area/alternative` nor any
# `lane/*` class; the two area labels are documented approximations.
DRIVABLE_COCO_MAP = {
    _normalize_label(coco): label
    for coco, label in DRIVABLE_TASK["coco_map"].items()
}


# ---------------------------------------------------------------------------
# Model loaders (cached — loaded once)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _semantic_model():
    from transformers import (
        AutoImageProcessor,
        AutoModelForSemanticSegmentation,
        AutoModelForUniversalSegmentation,
    )

    backend = os.getenv("SEMANTIC_BACKEND", "segformer").lower()
    model_id = os.getenv(
        "SEMANTIC_MODEL_ID",
        "nvidia/segformer-b5-finetuned-cityscapes-1024-1024"
        if backend == "segformer"
        else (
            "tue-mps/eomt-dinov3-coco-panoptic-large-640"
            if backend == "eomt"
            else "facebook/mask2former-swin-large-cityscapes-semantic"
        ),
    )
    processor = AutoImageProcessor.from_pretrained(model_id)
    if backend in {"mask2former", "eomt"}:
        model = AutoModelForUniversalSegmentation.from_pretrained(model_id)
    elif backend == "segformer":
        model = AutoModelForSemanticSegmentation.from_pretrained(model_id)
    else:
        raise RuntimeError(f"Unsupported SEMANTIC_BACKEND: {backend}; use segformer, mask2former, or eomt")
    model.to(_device()).eval()
    return backend, processor, model


def _semantic_labels(model: Any) -> list[str]:
    configured = os.getenv("SEMANTIC_LABELS")
    if configured:
        labels = [label.strip() for label in configured.split(",") if label.strip()]
        if labels:
            return labels
    id2label = getattr(model.config, "id2label", {})
    if id2label:
        return [_normalize_label(str(id2label[key])) for key in sorted(id2label, key=lambda v: int(v))]
    return CITYSCAPES_LABELS


@lru_cache(maxsize=1)
def _sam2_generator(points_per_side: int, pred_iou_thresh: float,
                     stability_score_thresh: float, min_mask_region_area: int):
    from sam2.automatic_mask_generator import SAM2AutomaticMaskGenerator
    from sam2.build_sam import build_sam2

    config = os.getenv("SAM2_CONFIG", "configs/sam2.1/sam2.1_hiera_l.yaml")
    checkpoint = os.getenv("SAM2_CHECKPOINT", "/models/sam2.1_hiera_large.pt")
    if not os.path.exists(checkpoint):
        raise RuntimeError(f"SAM2 checkpoint not found: {checkpoint}")
    if os.path.getsize(checkpoint) < 1024 * 1024:
        raise RuntimeError(f"SAM2 checkpoint looks corrupt: {checkpoint}")

    model = build_sam2(config, checkpoint, device=_device(), apply_postprocessing=False)
    return SAM2AutomaticMaskGenerator(
        model,
        points_per_side=points_per_side,
        pred_iou_thresh=pred_iou_thresh,
        stability_score_thresh=stability_score_thresh,
        min_mask_region_area=min_mask_region_area,
        output_mode="binary_mask",
    )


# ---------------------------------------------------------------------------
# Semantic segmentation pipeline
# ---------------------------------------------------------------------------

def _eomt_semantic_map(processor, outputs, target_size: tuple[int, int], class_count: int) -> np.ndarray:
    result = processor.post_process_panoptic_segmentation(outputs, target_sizes=[target_size])[0]
    segmentation = result["segmentation"].cpu().numpy()
    semantic = np.full(target_size, -1, dtype=np.int32)
    for segment in result["segments_info"]:
        class_id = int(segment["label_id"])
        if 0 <= class_id < class_count:
            semantic[segmentation == int(segment["id"])] = class_id
    return semantic


def _panoptic_result(processor, model, rgb: np.ndarray):
    """Run panoptic inference and return (segmentation, segments_info).

    `segmentation` is an HxW integer map of instance ids; `segments_info`
    is the list of {id, label_id, score} segments produced by EoMT/Mask2Former.
    """
    inputs = processor(images=Image.fromarray(rgb), return_tensors="pt")
    inputs = _to_device(inputs, _device())
    with torch.inference_mode():
        outputs = model(**inputs)
    result = processor.post_process_panoptic_segmentation(outputs, target_sizes=[rgb.shape[:2]])[0]
    segmentation = result["segmentation"].cpu().numpy()
    segments_info = result["segments_info"]
    return segmentation, segments_info


def _refine_with_sam(rgb: np.ndarray, semantic: np.ndarray, labels: list[str]) -> np.ndarray:
    if os.getenv("SEMANTIC_REFINE", "true").lower() not in {"1", "true", "yes"}:
        return semantic
    try:
        from sam2.sam2_image_predictor import SAM2ImagePredictor
        from sam2.build_sam import build_sam2
        config = os.getenv("SAM2_CONFIG", "configs/sam2.1/sam2.1_hiera_l.yaml")
        checkpoint = os.getenv("SAM2_CHECKPOINT", "/models/sam2.1_hiera_large.pt")
        predictor = SAM2ImagePredictor(build_sam2(config, checkpoint, device=_device(), apply_postprocessing=False))
        predictor.set_image(rgb)
    except Exception:
        return semantic

    refined = semantic.copy()
    for class_id in np.unique(semantic):
        if class_id < 0:
            continue
        label = labels[int(class_id)] if int(class_id) < len(labels) else ""
        if label not in REFINABLE_THING_LABELS:
            continue
        class_mask = semantic == class_id
        ys, xs = np.where(class_mask)
        if len(xs) < int(os.getenv("SEMANTIC_REFINE_MIN_AREA", "500")):
            continue
        box = np.array([xs.min(), ys.min(), xs.max() + 1, ys.max() + 1], dtype=np.float32)
        try:
            masks, _, _ = predictor.predict(box=box, multimask_output=False)
            candidate = np.asarray(masks[0], dtype=bool)
            overlap = np.logical_and(class_mask, candidate).sum()
            coverage = overlap / max(1, class_mask.sum())
            candidate_iou = overlap / max(1, np.logical_or(class_mask, candidate).sum())
            min_coverage = float(os.getenv("SEMANTIC_REFINE_MIN_COVERAGE", "0.85"))
            min_iou = float(os.getenv("SEMANTIC_REFINE_MIN_IOU", "0.6"))
            if coverage >= min_coverage and candidate_iou >= min_iou:
                refined[class_mask] = candidate[class_mask]
        except Exception:
            continue
    return refined


def _split_into_instances(semantic: np.ndarray, labels: list[str]) -> list[dict]:
    """Split semantic map into individual instances using connected components."""
    split_instances = os.getenv("SEMANTIC_SPLIT_INSTANCES", "true").lower() in {"1", "true", "yes"}
    min_component_area = int(os.getenv("SEMANTIC_MIN_COMPONENT_AREA", "100"))
    masks = []
    for class_id, label in enumerate(labels):
        class_mask = semantic == class_id
        if not class_mask.any():
            continue
        if split_instances:
            labeled, num_components = cc_label(class_mask)
            for component_idx in range(1, num_components + 1):
                component_mask = labeled == component_idx
                area = int(component_mask.sum())
                if area < min_component_area:
                    continue
                ys, xs = np.where(component_mask)
                masks.append({
                    "mask_id": len(masks),
                    "label": label,
                    "area": area,
                    "bbox": [float(xs.min()), float(ys.min()),
                             float(xs.max() - xs.min() + 1), float(ys.max() - ys.min() + 1)],
                    "mask_png_base64": _mask_png(component_mask),
                })
        else:
            ys, xs = np.where(class_mask)
            masks.append({
                "mask_id": len(masks),
                "label": label,
                "area": int(class_mask.sum()),
                "bbox": [float(xs.min()), float(ys.min()),
                         float(xs.max() - xs.min() + 1), float(ys.max() - ys.min() + 1)],
                "mask_png_base64": _mask_png(class_mask),
            })
    return masks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_semantic_segmentation(pil_image: Image.Image, rgb: np.ndarray) -> dict[str, Any]:
    """Full semantic segmentation pipeline: classify → refine → split → return."""
    backend, processor, model = _semantic_model()
    labels = _semantic_labels(model)
    inputs = processor(images=pil_image, return_tensors="pt")
    inputs = _to_device(inputs, _device())

    with torch.inference_mode():
        outputs = model(**inputs)

    if backend in {"mask2former", "eomt"}:
        if backend == "eomt":
            semantic = _eomt_semantic_map(processor, outputs, rgb.shape[:2], len(labels))
        else:
            semantic = processor.post_process_semantic_segmentation(
                outputs, target_sizes=[rgb.shape[:2]]
            )[0].cpu().numpy()
    else:
        logits = torch.nn.functional.interpolate(
            outputs.logits, size=rgb.shape[:2], mode="bilinear", align_corners=False
        )
        semantic = logits.argmax(dim=1)[0].cpu().numpy()

    semantic = _refine_with_sam(rgb, semantic, labels)
    masks = _split_into_instances(semantic, labels)

    return {
        "width": int(rgb.shape[1]),
        "height": int(rgb.shape[0]),
        "backend": backend,
        "masks": masks,
    }


def _mask_to_polygons(mask: np.ndarray, epsilon_ratio: float = 0.002) -> list[list[float]]:
    """Convert a boolean mask to a list of polygon contours (pixel coords).

    Uses OpenCV contours; returns a flat [x1,y1,x2,y2,...] list per contour.
    """
    import cv2

    binary = (mask.astype(np.uint8)) * 255
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    polygons = []
    for contour in contours:
        if len(contour) < 3:
            continue
        poly = cv2.approxPolyDP(contour, epsilon_ratio * cv2.arcLength(contour, True), True)
        flat = [round(float(v), 1) for point in poly.reshape(-1, 2) for v in point]
        if len(flat) >= 6:
            polygons.append(flat)
    return polygons


def run_drivable_segmentation(rgb: np.ndarray) -> dict[str, Any]:
    """Drivable-area segmentation via EoMT COCO-panoptic.

    COCO has no `area/drivable` / `area/alternative` classes; we approximate
    them from `road` -> `area/drivable` and `pavement-merged` ->
    `area/alternative`. Lane marking (`lane/*`) is NOT available in any COCO
    panoptic model and is returned as an explicit, documented limitation.
    """
    backend, processor, model = _semantic_model()
    if backend not in {"eomt", "mask2former"}:
        raise RuntimeError(
            f"/segment-drivable requires a panoptic backend (eomt/mask2former), got {backend}"
        )
    labels = _semantic_labels(model)

    device = _device()
    if device == "cuda":
        torch.cuda.reset_peak_memory_stats()
    segmentation, segments_info = _panoptic_result(processor, model, rgb)
    if device == "cuda":
        allocated = int(torch.cuda.memory_allocated(0))
        max_allocated = int(torch.cuda.max_memory_allocated(0))
        reserved = int(torch.cuda.memory_reserved(0))
    else:
        allocated = max_allocated = reserved = 0

    drivable = []
    raw_segments = 0
    for segment in segments_info:
        raw_segments += 1
        class_id = int(segment["label_id"])
        coco_name = labels[class_id] if 0 <= class_id < len(labels) else ""
        guideline_label = DRIVABLE_COCO_MAP.get(coco_name)
        if guideline_label is None:
            continue
        instance_mask = segmentation == int(segment["id"])
        if not instance_mask.any():
            continue
        polygons = _mask_to_polygons(instance_mask)
        if not polygons:
            continue
        drivable.append({
            "label": guideline_label,
            "coco_source": coco_name,
            "confidence": round(float(segment.get("score", 0.0)), 4),
            "area_px": int(instance_mask.sum()),
            "polygons": polygons,
        })

    return {
        "width": int(rgb.shape[1]),
        "height": int(rgb.shape[0]),
        "backend": backend,
        "raw_segment_count": raw_segments,
        "drivable": drivable,
        "lane_marking": {
            # Declared by the guideline but not producible by any deployed
            # model; the taxonomy carries the reason so it cannot drift.
            "supported": False,
            "labels": LANE_GROUP["labels"],
            "reason": LANE_GROUP["reason"],
        },
        "memory": {
            "allocated_bytes": allocated,
            "max_allocated_bytes": max_allocated,
            "reserved_bytes": reserved,
            "allocated_mib": round(allocated / 1048576, 2),
            "max_allocated_mib": round(max_allocated / 1048576, 2),
            "reserved_mib": round(reserved / 1048576, 2),
        },
    }


def run_auto_segmentation(
    rgb: np.ndarray,
    points_per_side: int,
    pred_iou_thresh: float,
    stability_score_thresh: float,
    min_mask_region_area: int,
    max_masks: int,
) -> dict[str, Any]:
    """SAM2 automatic mask generation."""
    with torch.inference_mode():
        generated = _sam2_generator(
            points_per_side, pred_iou_thresh,
            stability_score_thresh, min_mask_region_area,
        ).generate(rgb)

    generated = sorted(generated, key=lambda item: int(item.get("area", 0)), reverse=True)[:max_masks]
    masks = []
    for mask_id, item in enumerate(generated):
        mask = np.asarray(item["segmentation"], dtype=bool)
        masks.append({
            "mask_id": mask_id,
            "area": int(item["area"]),
            "bbox": [float(v) for v in item["bbox"]],
            "predicted_iou": float(item["predicted_iou"]) if item.get("predicted_iou") is not None else None,
            "stability_score": float(item["stability_score"]) if item.get("stability_score") is not None else None,
            "mask_png_base64": _mask_png(mask),
        })

    return {"width": int(rgb.shape[1]), "height": int(rgb.shape[0]), "masks": masks}
