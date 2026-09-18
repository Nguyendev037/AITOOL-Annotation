"""Nuclio thin adapter for CVAT auto-annotation.

This handler receives image requests from CVAT, forwards them to the
model-service sidecar, and converts responses into CVAT-compatible
annotation format (polygons or masks).
"""
import base64
import io
import json

from PIL import Image
from model_handler import ModelHandler


def init_context(context):
    context.logger.info("Init context... 0%")
    context.user_data.model = ModelHandler()
    context.logger.info("Init context... 100%")


def handler(context, event):
    data = event.body
    if not isinstance(data, dict) or "image" not in data:
        return context.Response(
            body=json.dumps({"error": "missing image"}),
            content_type="application/json",
            status_code=400,
        )

    image = Image.open(io.BytesIO(base64.b64decode(data["image"]))).convert("RGB")
    threshold = float(data.get("threshold", 0.5))
    results = context.user_data.model.infer(image=image, threshold=threshold, request=data)
    if not isinstance(results, list):
        raise TypeError("ModelHandler.infer() must return a list of CVAT annotations")
    return context.Response(
        body=json.dumps(results),
        headers={},
        content_type="application/json",
        status_code=200,
    )
