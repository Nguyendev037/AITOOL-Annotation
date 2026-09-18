"""Object detection handler (YOLO26 via Ultralytics).

Isolated from the semantic/SAM2 pipeline. Loads the YOLO26 model once and
reuses it across requests. Returns real detector bounding boxes mapped to the
local BBox annotation guideline taxonomy.
"""
from __future__ import annotations

import json
import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image

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
BBOX_TASK = TAXONOMY["tasks"]["bbox"]

# COCO class name -> guideline label. Only the guideline's allowed classes are
# kept; everything else is filtered out by run_detection().
GUIDELINE_TAXONOMY = BBOX_TASK["coco_map"]

# Guideline labels the detector may emit directly (e.g. a model fine-tuned on
# the 10-class guideline taxonomy). These pass through without COCO mapping.
GUIDELINE_LABELS = set(BBOX_TASK["declared"])


def _device() -> str:
    import torch
    return "cuda" if torch.cuda.is_available() else "cpu"


@lru_cache(maxsize=1)
def _model():
    """Load YOLO26 once. Ultralytics caches the checkpoint on disk and the
    returned object is reused for every request."""
    from ultralytics import YOLO

    weights = os.getenv("YOLO26_MODEL", "yolo26m.pt")
    device = _device()
    model = YOLO(weights)
    # Move to device and enable FP16 only on CUDA (FP16 is safe there).
    model.to(device)
    if device == "cuda":
        try:
            model.model.half()
        except Exception:
            pass
    return model, device, weights


def run_detection(
    pil_image: Image.Image,
    conf_threshold: float,
    iou_threshold: float,
) -> dict[str, Any]:
    """Run YOLO26 object detection on a PIL image.

    Returns detections mapped to the guideline taxonomy, in original image
    pixel coordinates.
    """
    import torch

    model, device, weights = _model()
    t_pre_start = time.perf_counter()
    rgb = pil_image.convert("RGB")
    t_pre_end = time.perf_counter()

    # Reset CUDA memory stats so the figures below reflect this request only.
    if device == "cuda":
        torch.cuda.reset_peak_memory_stats()

    t_infer_start = time.perf_counter()
    results = model.predict(
        source=rgb,
        conf=conf_threshold,
        iou=iou_threshold,
        verbose=False,
    )
    t_infer_end = time.perf_counter()

    # Capture VRAM before post-processing so the numbers reflect the model
    # forward pass (torch.cuda.memory_allocated/max_memory_allocated/memory_reserved).
    if device == "cuda":
        allocated = int(torch.cuda.memory_allocated(0))
        max_allocated = int(torch.cuda.max_memory_allocated(0))
        reserved = int(torch.cuda.memory_reserved(0))
    else:
        allocated = max_allocated = reserved = 0

    names = model.names  # int id -> COCO name

    detections: list[dict[str, Any]] = []
    raw_count = 0
    result = results[0]
    if result.boxes is not None:
        boxes = result.boxes
        raw_count = int(boxes.shape[0])
        for i in range(raw_count):
            cls_id = int(boxes.cls[i])
            raw_name = names.get(cls_id, names.get(int(cls_id), ""))
            if raw_name in GUIDELINE_LABELS:
                label = raw_name  # already a guideline label (fine-tuned model)
            else:
                label = GUIDELINE_TAXONOMY.get(raw_name)
            if label is None:
                continue  # filter out-of-guideline classes
            xyxy = boxes.xyxy[i].tolist()
            x1, y1, x2, y2 = (round(float(v), 1) for v in xyxy)
            # Keep boxes inside the image boundary (guideline: no out-of-frame boxes).
            x1 = max(0.0, min(x1, float(rgb.width)))
            y1 = max(0.0, min(y1, float(rgb.height)))
            x2 = max(0.0, min(x2, float(rgb.width)))
            y2 = max(0.0, min(y2, float(rgb.height)))
            detections.append({
                "label": label,
                "confidence": round(float(boxes.conf[i]), 4),
                "bbox": [x1, y1, x2, y2],
                "raw_class": raw_name,
            })

    t_post_end = time.perf_counter()

    return {
        "width": rgb.width,
        "height": rgb.height,
        "model": weights,
        "device": device,
        "raw_count": raw_count,
        "detections": detections,
        "timing_ms": {
            "preprocess": round((t_pre_end - t_pre_start) * 1000, 2),
            "inference": round((t_infer_end - t_infer_start) * 1000, 2),
            "postprocess": round((t_post_end - t_infer_end) * 1000, 2),
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
