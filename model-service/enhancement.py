"""Image enhancement pipeline for improving model inference quality.

Applied automatically before inference when enabled. All operations preserve
original image dimensions and coordinate space.
"""
from __future__ import annotations

import io
import os

import cv2
import numpy as np
from PIL import Image, ImageFilter


def enhance_image(pil_image: Image.Image) -> Image.Image:
    """Apply all enabled enhancement steps and return the improved image."""
    result = pil_image.copy()
    if os.getenv("ENHANCE_DARK_REGIONS", "true").lower() in {"1", "true", "yes"}:
        result = _brighten_dark_regions(result)
    if os.getenv("ENHANCE_MOTION_BLUR", "false").lower() in {"1", "true", "yes"}:
        result = _reduce_motion_blur(result)
    return result


def _brighten_dark_regions(image: Image.Image) -> Image.Image:
    """Selectively brighten dark shadow/night regions without affecting bright areas."""
    width, height = image.size
    luminance = image.convert("L")
    radius = max(8, min(width, height) // 24)
    local_luminance = np.asarray(
        luminance.filter(ImageFilter.GaussianBlur(radius)), dtype=np.float32
    )
    threshold = float(os.getenv("ENHANCE_DARK_THRESHOLD", "85"))
    dark_fraction = float(np.mean(local_luminance < threshold))
    min_dark_fraction = float(os.getenv("ENHANCE_DARK_MIN_FRACTION", "0.05"))
    if dark_fraction < min_dark_fraction:
        return image

    pixels = np.asarray(image, dtype=np.uint8)
    strength = np.clip((threshold - local_luminance) / 55.0, 0.0, 1.0)[..., None]
    gamma = np.power(np.arange(256, dtype=np.float32) / 255.0, 0.55) * 255.0
    boosted = np.minimum(gamma[pixels], pixels.astype(np.float32) * 2.5)
    adjusted = np.clip(pixels + strength * (boosted - pixels), 0, 255).astype(np.uint8)
    return Image.fromarray(adjusted)


def _reduce_motion_blur(image: Image.Image) -> Image.Image:
    """Reduce motion blur using Wiener-like sharpening for highway/fast scenes."""
    rgb = np.asarray(image, dtype=np.uint8)
    blur_score = cv2.Laplacian(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), cv2.CV_64F).var()
    blur_threshold = float(os.getenv("ENHANCE_BLUR_THRESHOLD", "100"))
    if blur_score >= blur_threshold:
        return image

    # Apply unsharp mask for mild deblurring
    gaussian = cv2.GaussianBlur(rgb, (0, 0), 3)
    sharpened = cv2.addWeighted(rgb, 1.5, gaussian, -0.5, 0)
    return Image.fromarray(sharpened)
