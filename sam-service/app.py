from __future__ import annotations

import base64
import io
import os
from functools import lru_cache
from typing import Any

import numpy as np
import torch
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from PIL import Image
from scipy.ndimage import label as cc_label

app = FastAPI(title="SAM 2.1 Hiera Large service", version="1.0.0")

CITYSCAPES_LABELS = [
    "road", "sidewalk", "building", "wall", "fence", "pole", "traffic_light",
    "traffic_sign", "vegetation", "terrain", "sky", "person", "rider", "car",
    "truck", "bus", "train", "motorcycle", "bicycle",
]
REFINABLE_THING_LABELS = {
    "person", "rider", "car", "truck", "bus", "train", "motorcycle", "bicycle",
    "traffic_light", "traffic_sign",
}


def _checkpoint_details() -> dict[str, Any]:
    checkpoint = os.getenv("SAM2_CHECKPOINT", "/models/sam2.1_hiera_large.pt")
    exists = os.path.exists(checkpoint)
    size = os.path.getsize(checkpoint) if exists else 0
    return {"path": checkpoint, "exists": exists, "size_bytes": size}


def _device() -> str:
    requested = os.getenv("SAM2_DEVICE", "cuda")
    if requested == "cuda" and not torch.cuda.is_available():
        return "cpu"
    return requested


@lru_cache(maxsize=1)
def _generator(points_per_side: int, pred_iou_thresh: float, stability_score_thresh: float, min_mask_region_area: int):
    try:
        from sam2.automatic_mask_generator import SAM2AutomaticMaskGenerator
        from sam2.build_sam import build_sam2
    except ImportError as exc:
        raise RuntimeError("SAM2 is not installed in the service image") from exc

    config = os.getenv("SAM2_CONFIG", "configs/sam2.1/sam2.1_hiera_l.yaml")
    checkpoint = os.getenv("SAM2_CHECKPOINT", "/models/sam2.1_hiera_large.pt")
    checkpoint_info = _checkpoint_details()

    if not checkpoint_info["exists"]:
        raise RuntimeError(f"SAM2 checkpoint not found: {checkpoint}")

    if checkpoint_info["size_bytes"] < 1024 * 1024:
        raise RuntimeError(
            "SAM2 checkpoint looks corrupt or incomplete: "
            f"{checkpoint} size={checkpoint_info['size_bytes']} bytes. "
            "Download a valid SAM 2.1 Hiera Large checkpoint to /models/sam2.1_hiera_large.pt."
        )

    try:
        model = build_sam2(config, checkpoint, device=_device(), apply_postprocessing=False)
    except KeyError as exc:
        raise RuntimeError(
            "Invalid or corrupted SAM2 checkpoint: the file is not a valid SAM 2.1 Hiera Large checkpoint. "
            f"File: {checkpoint}. Detected size: {checkpoint_info['size_bytes']} bytes. "
            "Please replace it with the official checkpoint from the SAM 2 repository."
        ) from exc
    except Exception as exc:
        raise RuntimeError(f"Failed to load SAM2 model from {checkpoint}. config={config}. error={exc}") from exc

    return SAM2AutomaticMaskGenerator(
        model,
        points_per_side=points_per_side,
        pred_iou_thresh=pred_iou_thresh,
        stability_score_thresh=stability_score_thresh,
        min_mask_region_area=min_mask_region_area,
        output_mode="binary_mask",
    )


def _mask_png(mask: np.ndarray) -> str:
    image = Image.fromarray((mask.astype(np.uint8) * 255), mode="L")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


@lru_cache(maxsize=1)
def _semantic_model():
    try:
        from transformers import AutoImageProcessor, AutoModelForSemanticSegmentation, AutoModelForUniversalSegmentation
    except ImportError as exc:
        raise RuntimeError("transformers is not installed in the service image") from exc

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
    return [_normalize_label(str(id2label[key])) for key in sorted(id2label, key=lambda value: int(value))] if id2label else CITYSCAPES_LABELS


def _normalize_label(label: str) -> str:
    return label.strip().lower().replace(" ", "_")


def _eomt_semantic_map(processor: Any, outputs: Any, target_size: tuple[int, int], class_count: int) -> np.ndarray:
    result = processor.post_process_panoptic_segmentation(outputs, target_sizes=[target_size])[0]
    segmentation = result["segmentation"].cpu().numpy()
    semantic = np.full(target_size, -1, dtype=np.int32)
    for segment in result["segments_info"]:
        class_id = int(segment["label_id"])
        if 0 <= class_id < class_count:
            semantic[segmentation == int(segment["id"])] = class_id
    return semantic


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


@app.post("/segment-semantic")
async def segment_semantic(image: UploadFile = File(...)) -> dict[str, Any]:
    try:
        raw = await image.read()
        pil_image = Image.open(io.BytesIO(raw)).convert("RGB")
        rgb = np.asarray(pil_image)
        backend, processor, model = _semantic_model()
        labels = _semantic_labels(model)
        inputs = processor(images=pil_image, return_tensors="pt")
        inputs = {key: value.to(_device()) for key, value in inputs.items()}
        with torch.inference_mode():
            outputs = model(**inputs)
        if backend in {"mask2former", "eomt"}:
            if backend == "eomt":
                semantic = _eomt_semantic_map(processor, outputs, rgb.shape[:2], len(labels))
            else:
                semantic = processor.post_process_semantic_segmentation(outputs, target_sizes=[rgb.shape[:2]])[0].cpu().numpy()
        else:
            logits = torch.nn.functional.interpolate(outputs.logits, size=rgb.shape[:2], mode="bilinear", align_corners=False)
            semantic = logits.argmax(dim=1)[0].cpu().numpy()
        semantic = _refine_with_sam(rgb, semantic, labels)
        split_instances = os.getenv("SEMANTIC_SPLIT_INSTANCES", "true").lower() in {"1", "true", "yes"}
        min_component_area = int(os.getenv("SEMANTIC_MIN_COMPONENT_AREA", "100"))
        masks = []
        for class_id, label in enumerate(labels):
            class_mask = semantic == class_id
            if not class_mask.any():
                continue
            if split_instances:
                # Split spatially disconnected regions of the same class into separate masks.
                # This prevents the model from merging multiple objects (e.g. two cars) into one mask.
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
                        "bbox": [float(xs.min()), float(ys.min()), float(xs.max() - xs.min() + 1), float(ys.max() - ys.min() + 1)],
                        "mask_png_base64": _mask_png(component_mask),
                    })
            else:
                ys, xs = np.where(class_mask)
                masks.append({
                    "mask_id": len(masks),
                    "label": label,
                    "area": int(class_mask.sum()),
                    "bbox": [float(xs.min()), float(ys.min()), float(xs.max() - xs.min() + 1), float(ys.max() - ys.min() + 1)],
                    "mask_png_base64": _mask_png(class_mask),
                })
        return {"width": int(rgb.shape[1]), "height": int(rgb.shape[0]), "backend": backend, "masks": masks}
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Semantic segmentation failed: {exc}") from exc


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "SAM 2.1 Hiera Large",
        "health": "/health",
        "segment": "/segment-auto",
        "segment_semantic": "/segment-semantic",
    }


@app.get("/health")
def health() -> dict[str, Any]:
    checkpoint_info = _checkpoint_details()
    return {
        "status": "ok",
        "model": "SAM 2.1 Hiera Large",
        "device": _device(),
        "cuda_available": torch.cuda.is_available(),
        "cuda_device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "checkpoint_path": checkpoint_info["path"],
        "checkpoint_exists": checkpoint_info["exists"],
        "checkpoint_size_bytes": checkpoint_info["size_bytes"],
        "semantic_backend": os.getenv("SEMANTIC_BACKEND", "segformer"),
        "semantic_model_id": os.getenv("SEMANTIC_MODEL_ID", ""),
        "semantic_refine": os.getenv("SEMANTIC_REFINE", "true").lower() in {"1", "true", "yes"},
        "semantic_refine_min_area": int(os.getenv("SEMANTIC_REFINE_MIN_AREA", "500")),
        "semantic_split_instances": os.getenv("SEMANTIC_SPLIT_INSTANCES", "true").lower() in {"1", "true", "yes"},
        "semantic_min_component_area": int(os.getenv("SEMANTIC_MIN_COMPONENT_AREA", "100")),
    }


@app.post("/segment-auto")
async def segment_auto(
    image: UploadFile = File(...),
    points_per_side: int = Form(16),
    pred_iou_thresh: float = Form(0.86),
    stability_score_thresh: float = Form(0.92),
    min_mask_region_area: int = Form(150),
    max_masks: int = Form(40),
) -> dict[str, Any]:
    try:
        raw = await image.read()
        rgb = np.asarray(Image.open(io.BytesIO(raw)).convert("RGB"))
        with torch.inference_mode():
            generated = _generator(points_per_side, pred_iou_thresh, stability_score_thresh, min_mask_region_area).generate(rgb)
        generated = sorted(generated, key=lambda item: int(item.get("area", 0)), reverse=True)[:max_masks]
        masks = []
        for mask_id, item in enumerate(generated):
            mask = np.asarray(item["segmentation"], dtype=bool)
            masks.append({
                "mask_id": mask_id,
                "area": int(item["area"]),
                "bbox": [float(value) for value in item["bbox"]],
                "predicted_iou": float(item["predicted_iou"]) if item.get("predicted_iou") is not None else None,
                "stability_score": float(item["stability_score"]) if item.get("stability_score") is not None else None,
                "mask_png_base64": _mask_png(mask),
            })
        return {"width": int(rgb.shape[1]), "height": int(rgb.shape[0]), "masks": masks}
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=(
                "SAM2 segmentation failed: "
                f"{exc}. "
                f"checkpoint={os.getenv('SAM2_CHECKPOINT', '/models/sam2.1_hiera_large.pt')}, "
                f"config={os.getenv('SAM2_CONFIG', 'configs/sam2.1/sam2.1_hiera_l.yaml')}"
            ),
        ) from exc
        
