from __future__ import annotations

import math

import cv2
import numpy as np


def per_view_reprojection_errors(
    object_points: list[np.ndarray],
    image_points: list[np.ndarray],
    rvecs: list[np.ndarray],
    tvecs: list[np.ndarray],
    camera_matrix: np.ndarray,
    dist_coeffs: np.ndarray,
) -> list[float]:
    errors = []
    for obj, img, rvec, tvec in zip(object_points, image_points, rvecs, tvecs):
        projected, _ = cv2.projectPoints(obj, rvec, tvec, camera_matrix, dist_coeffs)
        errors.append(float(cv2.norm(img, projected, cv2.NORM_L2) / math.sqrt(len(projected))))
    return errors


def summarize_errors(errors: list[float]) -> dict[str, float]:
    arr = np.array(errors, dtype=np.float64)
    return {
        "mean_px": float(arr.mean()) if len(arr) else float("nan"),
        "median_px": float(np.median(arr)) if len(arr) else float("nan"),
        "max_px": float(arr.max()) if len(arr) else float("nan"),
        "min_px": float(arr.min()) if len(arr) else float("nan"),
    }


def fov_degrees(camera_matrix: np.ndarray, image_size: tuple[int, int]) -> dict[str, float]:
    width, height = image_size
    fx = float(camera_matrix[0, 0])
    fy = float(camera_matrix[1, 1])
    return {
        "horizontal": math.degrees(2.0 * math.atan(width / (2.0 * fx))),
        "vertical": math.degrees(2.0 * math.atan(height / (2.0 * fy))),
        "diagonal": math.degrees(
            2.0 * math.atan(math.sqrt(width * width + height * height) / (2.0 * math.sqrt(fx * fy)))
        ),
    }
