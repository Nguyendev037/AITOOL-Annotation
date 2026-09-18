"""Nuclio thin adapter: CVAT serverless function -> model-service sidecar.

One source file, three deployments. The ``TASK`` environment variable selects
which model-service endpoint is called and which CVAT geometry is produced:

    TASK=bbox       POST /detect             -> type "rectangle"
    TASK=semantic   POST /segment-semantic   -> type "polygon" (mask -> contours)
    TASK=drivable   POST /segment-drivable   -> type "polygon" (polygons ready)

All heavy models (YOLO26, EoMT, SAM2) live in the ``cvat-smart-model`` sidecar
container which owns the GPU. This function is a CPU-only proxy plus a geometry
converter, which keeps the nuclio build small and fast.

CVAT calls ``handler`` once per frame with a JSON body::

    {"image": "<base64>", "threshold": 0.5, "job": ..., "frame": ...}

and expects a JSON list of annotations back, one object per shape::

    {"confidence": "0.93", "label": "car", "points": [x1, y1, x2, y2],
     "type": "rectangle"}

Label names must match the CVAT task labels exactly; the label list this
function advertises lives in ``metadata.annotations.spec`` of its function.yaml.
"""
from __future__ import annotations

import base64
import io
import json
import os

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TASK = os.environ.get("TASK", "bbox").strip().lower()
MODEL_SERVER_URL = os.environ.get("MODEL_SERVER_URL", "http://host.docker.internal:8001").rstrip("/")
MODEL_SERVER_TIMEOUT = float(os.environ.get("MODEL_SERVER_TIMEOUT", "180"))
MIN_ANNOTATION_AREA = float(os.environ.get("MIN_ANNOTATION_AREA", "64"))
POLYGON_EPSILON = float(os.environ.get("POLYGON_EPSILON", "0.01"))

TASK_ENDPOINTS = {
    "bbox": "/detect",
    "semantic": "/segment-semantic",
    "drivable": "/segment-drivable",
}

# Task-specific label taxonomy, injected by `tools/deploy_nuclio.py` straight
# from `taxonomy.yaml`. Nothing label-related is hardcoded in this file: change
# `taxonomy.yaml`, run `python tools/sync_taxonomy.py --write`, then redeploy.
TAXONOMY_JSON = os.environ.get("TAXONOMY_JSON", "").strip()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_label(label: str) -> str:
    """Normalise a model class name so both sides of a map compare equal.

    EoMT's id2label carries names such as ``traffic light`` while taxonomy.yaml
    writes ``traffic light`` too, but COCO's own detector names use spaces as
    well; normalising removes the ambiguity entirely.
    """
    return label.strip().lower().replace(" ", "_")


def _load_taxonomy() -> tuple[dict[str, str], list[str]]:
    """Decode the taxonomy injected by ``tools/deploy_nuclio.py``.

    Returns ``(coco_map, declared)`` where ``coco_map`` maps a normalised COCO
    class name to a guideline label and ``declared`` is the full label list the
    CVAT Models page advertises.

    Deploying this file by hand without ``TAXONOMY_JSON`` is a hard error on
    purpose: a function that silently falls back to a built-in map is exactly how
    labels drifted away from the guideline before.
    """
    if not TAXONOMY_JSON:
        raise ValueError(
            "TAXONOMY_JSON is not set; deploy with `python tools/deploy_nuclio.py` "
            "so the taxonomy from taxonomy.yaml is injected into the function"
        )
    try:
        parsed = json.loads(TAXONOMY_JSON)
    except json.JSONDecodeError as exc:
        raise ValueError(f"TAXONOMY_JSON is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict) or "coco_map" not in parsed:
        raise ValueError("TAXONOMY_JSON must be an object with a 'coco_map' key")

    coco_map = {
        _normalize_label(str(key)): str(value)
        for key, value in (parsed.get("coco_map") or {}).items()
    }
    declared = [str(name) for name in (parsed.get("declared") or [])]
    return coco_map, declared


def _load_label_map() -> dict[str, str]:
    """Optional JSON object renaming emitted labels to match the CVAT task.

    The guideline taxonomy writes ``traffic light`` (space) while some CVAT
    tasks use ``traffic_light`` (underscore). Set ``LABEL_MAP`` to bridge that
    without touching code, e.g.::

        LABEL_MAP={"pedestrian": "person", "traffic light": "traffic_light"}
    """
    raw = os.environ.get("LABEL_MAP", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LABEL_MAP is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("LABEL_MAP must be a JSON object")
    return {str(key): str(value) for key, value in parsed.items()}


def _json_response(context, status_code: int, payload):
    return context.Response(
        body=json.dumps(payload),
        headers={},
        content_type="application/json",
        status_code=status_code,
    )


def _parse_body(event) -> dict:
    body = event.body
    if isinstance(body, (bytes, bytearray)):
        body = json.loads(body.decode("utf-8"))
    if not isinstance(body, dict):
        raise ValueError("request body must be a JSON object")
    if "image" not in body:
        raise ValueError("request body must contain an 'image' field")
    return body


def _call_model_service(session: requests.Session, endpoint: str, image_bytes: bytes, body: dict) -> dict:
    """POST the frame to the model-service sidecar and return its JSON."""
    form = {}
    # Pass CVAT's confidence threshold through where the endpoint supports it.
    if endpoint == "/detect" and body.get("threshold") is not None:
        form["conf"] = str(float(body["threshold"]))
    response = session.post(
        f"{MODEL_SERVER_URL}{endpoint}",
        files={"image": ("frame.png", image_bytes, "image/png")},
        data=form or None,
        timeout=MODEL_SERVER_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def _mask_to_polygons(mask_png_base64: str, width: int, height: int) -> list[list[float]]:
    """Decode a base64 PNG mask and trace its external contours as polygons."""
    import cv2
    import numpy as np
    from PIL import Image

    raw = base64.b64decode(mask_png_base64)
    mask = np.asarray(Image.open(io.BytesIO(raw)).convert("L")) > 127
    if not mask.any():
        return []

    binary = mask.astype(np.uint8) * 255
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    polygons: list[list[float]] = []
    for contour in contours:
        if cv2.contourArea(contour) < MIN_ANNOTATION_AREA:
            continue
        approx = cv2.approxPolyDP(contour, POLYGON_EPSILON * cv2.arcLength(contour, True), True)
        points = approx.reshape(-1, 2)
        if len(points) < 3:
            continue
        flat: list[float] = []
        for x, y in points:
            # Guideline: shapes must stay inside the frame.
            flat.append(float(min(max(float(x), 0.0), float(width))))
            flat.append(float(min(max(float(y), 0.0), float(height))))
        polygons.append(flat)
    return polygons


# ---------------------------------------------------------------------------
# Geometry builders, one per task
# ---------------------------------------------------------------------------

def _bbox_annotations(payload: dict, context, threshold: float | None) -> list[dict]:
    width = float(payload.get("width") or 0)
    height = float(payload.get("height") or 0)
    annotations: list[dict] = []
    for detection in payload.get("detections", []):
        confidence = float(detection.get("confidence", 0.0))
        if threshold is not None and confidence < threshold:
            continue
        x1, y1, x2, y2 = (float(v) for v in detection["bbox"])
        # model-service returns xyxy in original pixel coordinates.
        if width and height:
            x1 = min(max(x1, 0.0), width)
            x2 = min(max(x2, 0.0), width)
            y1 = min(max(y1, 0.0), height)
            y2 = min(max(y2, 0.0), height)
        if x2 - x1 < 1.0 or y2 - y1 < 1.0:
            continue
        annotations.append({
            "confidence": f"{confidence:.4f}",
            "label": detection["label"],
            "points": [round(x1, 2), round(y1, 2), round(x2, 2), round(y2, 2)],
            "type": "rectangle",
        })
    return annotations


def _semantic_annotations(payload: dict, context, threshold: float | None) -> list[dict]:
    width = int(payload.get("width") or 0)
    height = int(payload.get("height") or 0)
    annotations: list[dict] = []
    unmapped: set[str] = set()
    for mask_info in payload.get("masks", []):
        if float(mask_info.get("area", 0)) < MIN_ANNOTATION_AREA:
            continue
        coco_label = _normalize_label(str(mask_info.get("label", "")))
        label = context.user_data.coco_map.get(coco_label)
        if label is None:
            unmapped.add(coco_label)
            continue
        for points in _mask_to_polygons(mask_info["mask_png_base64"], width, height):
            annotations.append({
                "confidence": "1.0",
                "label": label,
                "points": points,
                "type": "polygon",
            })
    if unmapped:
        context.logger.debug(
            "semantic: dropped %d COCO class(es) with no guideline mapping: %s",
            len(unmapped), ", ".join(sorted(unmapped)),
        )
    return annotations


def _drivable_annotations(payload: dict, context, threshold: float | None) -> list[dict]:
    annotations: list[dict] = []
    for area in payload.get("drivable", []):
        confidence = float(area.get("confidence", 0.0))
        if float(area.get("area_px", 0)) < MIN_ANNOTATION_AREA:
            continue
        for points in area.get("polygons", []):
            if len(points) < 6:
                continue
            annotations.append({
                "confidence": f"{confidence:.4f}",
                "label": area["label"],
                "points": [round(float(v), 2) for v in points],
                "type": "polygon",
            })
    # Lane marking is intentionally absent: see the function description and
    # the limitation reported by /segment-drivable.
    return annotations


_BUILDERS = {
    "bbox": _bbox_annotations,
    "semantic": _semantic_annotations,
    "drivable": _drivable_annotations,
}


# ---------------------------------------------------------------------------
# Nuclio entry points
# ---------------------------------------------------------------------------

def init_context(context):
    endpoint = TASK_ENDPOINTS.get(TASK)
    if endpoint is None:
        raise ValueError(f"unknown TASK {TASK!r}; expected one of {sorted(TASK_ENDPOINTS)}")
    context.logger.info("smart-annotator init: task=%s endpoint=%s target=%s", TASK, endpoint, MODEL_SERVER_URL)
    session = requests.Session()
    context.user_data.session = session
    context.user_data.endpoint = endpoint
    coco_map, declared = _load_taxonomy()
    context.user_data.coco_map = coco_map
    context.user_data.declared = declared
    context.logger.info(
        "smart-annotator taxonomy: %d declared label(s), %d COCO mapping(s)",
        len(declared), len(coco_map),
    )
    context.user_data.label_map = _load_label_map()
    if context.user_data.label_map:
        context.logger.info("smart-annotator label map: %s", context.user_data.label_map)
    context.logger.info("smart-annotator ready: task=%s", TASK)


def handler(context, event):
    try:
        body = _parse_body(event)
    except ValueError as exc:
        return _json_response(context, 400, {"error": str(exc)})

    try:
        image_bytes = base64.b64decode(body["image"])
    except Exception as exc:
        return _json_response(context, 400, {"error": f"image is not valid base64: {exc}"})

    try:
        threshold = body.get("threshold")
        threshold = float(threshold) if threshold is not None else None
        payload = _call_model_service(
            context.user_data.session, context.user_data.endpoint, image_bytes, body
        )
        annotations = _BUILDERS[TASK](payload, context, threshold)
        label_map = context.user_data.label_map
        if label_map:
            for annotation in annotations:
                annotation["label"] = label_map.get(annotation["label"], annotation["label"])
    except requests.HTTPError as exc:
        detail = exc.response.text[:500] if exc.response is not None else str(exc)
        context.logger.error("model-service returned an error: %s", detail)
        return _json_response(context, 502, {"error": f"model-service error: {detail}"})
    except Exception as exc:
        context.logger.error("inference failed: %s", exc)
        return _json_response(context, 500, {"error": f"{type(exc).__name__}: {exc}"})

    context.logger.info("task=%s produced %d annotation(s)", TASK, len(annotations))
    return _json_response(context, 200, annotations)
