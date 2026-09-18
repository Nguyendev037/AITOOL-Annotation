"""Sidecar adapter: forwards requests to the model-service and converts
responses into CVAT polygon/mask annotation format.
"""
from __future__ import annotations

import base64
import io
import os

import numpy as np
import requests
from PIL import Image


class ModelHandler:
    def __init__(self):
        self.url = os.environ.get(
            "MODEL_SERVER_URL", "http://host.docker.internal:8001"
        )
        self.timeout = float(os.environ.get("MODEL_SERVER_TIMEOUT", "120"))
        self.output_format = os.environ.get("ANNOTATION_FORMAT", "polygon")
        self.min_area = int(os.environ.get("MIN_ANNOTATION_AREA", "50"))

    def infer(self, image: Image.Image, threshold: float, request: dict) -> list[dict]:
        # Send image to model-service
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        buf.seek(0)
        response = requests.post(
            f"{self.url}/segment-semantic",
            files={"image": ("frame.png", buf, "image/png")},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()

        # Convert model-service response to CVAT annotations
        annotations = []
        for mask_info in data.get("masks", []):
            if mask_info["area"] < self.min_area:
                continue
            if self.output_format == "polygon":
                polygons = self._mask_to_polygons(mask_info)
                annotations.extend(polygons)
            else:
                cvat_mask = self._to_cvat_mask(mask_info, data["width"], data["height"])
                if cvat_mask:
                    annotations.append(cvat_mask)

        return annotations

    def _mask_to_polygons(self, mask_info: dict) -> list[dict]:
        """Convert a mask PNG to CVAT polygon annotations."""
        import cv2
        mask_bytes = base64.b64decode(mask_info["mask_png_base64"])
        mask = np.asarray(Image.open(io.BytesIO(mask_bytes)).convert("L")) > 127
        mask_uint8 = mask.astype(np.uint8) * 255
        contours, _ = cv2.findContours(mask_uint8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        polygons = []
        for contour in contours:
            if cv2.contourArea(contour) < self.min_area:
                continue
            epsilon = 0.01 * cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, epsilon, True)
            if len(approx) < 3:
                continue
            points = []
            for point in approx:
                points.extend([float(point[0][0]), float(point[0][1])])
            polygons.append({
                "confidence": "1.0",
                "label": mask_info["label"],
                "type": "polygon",
                "points": points,
            })
        return polygons

    def _to_cvat_mask(self, mask_info: dict, width: int, height: int) -> dict | None:
        """Convert a mask PNG to CVAT mask annotation format."""
        mask_bytes = base64.b64decode(mask_info["mask_png_base64"])
        mask = np.asarray(Image.open(io.BytesIO(mask_bytes)).convert("L")) > 127
        ys, xs = np.where(mask)
        if len(xs) == 0:
            return None
        xtl, ytl = int(xs.min()), int(ys.min())
        xbr, ybr = int(xs.max()), int(ys.max())
        cropped = mask[ytl:ybr + 1, xtl:xbr + 1].flatten().astype(int).tolist()
        cropped.extend([xtl, ytl, xbr, ybr])
        return {
            "confidence": "1.0",
            "label": mask_info["label"],
            "type": "mask",
            "mask": cropped,
        }
