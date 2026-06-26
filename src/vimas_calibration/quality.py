from __future__ import annotations

import cv2
import numpy as np


def image_quality(gray: np.ndarray, corners: np.ndarray) -> dict[str, float]:
    pts = corners.reshape(-1, 2)
    x0, y0 = pts.min(axis=0)
    x1, y1 = pts.max(axis=0)
    h, w = gray.shape[:2]
    bbox_area = max(0.0, float(x1 - x0)) * max(0.0, float(y1 - y0))
    return {
        "sharpness": float(cv2.Laplacian(gray, cv2.CV_64F).var()),
        "brightness": float(gray.mean()),
        "contrast": float(gray.std()),
        "coverage": float(bbox_area / float(w * h)) if w and h else 0.0,
    }


def quality_rejection_reason(
    metrics: dict[str, float],
    min_sharpness: float,
    min_contrast: float,
    min_coverage: float,
    min_brightness: float,
    max_brightness: float,
) -> str | None:
    if metrics["sharpness"] < min_sharpness:
        return f"blur sharpness {metrics['sharpness']:.1f} < {min_sharpness:.1f}"
    if metrics["contrast"] < min_contrast:
        return f"low contrast {metrics['contrast']:.1f} < {min_contrast:.1f}"
    if metrics["coverage"] < min_coverage:
        return f"board too small coverage {metrics['coverage']:.3f} < {min_coverage:.3f}"
    if metrics["brightness"] < min_brightness:
        return f"too dark brightness {metrics['brightness']:.1f} < {min_brightness:.1f}"
    if metrics["brightness"] > max_brightness:
        return f"too bright brightness {metrics['brightness']:.1f} > {max_brightness:.1f}"
    return None


def quality_label_lines(metrics: dict[str, float]) -> list[str]:
    if not metrics:
        return []
    return [
        f"sharpness: {metrics['sharpness']:.1f}",
        f"brightness/contrast: {metrics['brightness']:.1f}/{metrics['contrast']:.1f}",
        f"coverage: {metrics['coverage']:.3f}",
    ]
