from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yaml


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


def list_images(folder: str | Path) -> list[Path]:
    path = Path(folder)
    return sorted(p for p in path.glob("*") if p.suffix.lower() in IMAGE_EXTS)


def to_serializable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, dict):
        return {key: to_serializable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_serializable(item) for item in value]
    return value


def read_yaml(path: str | Path) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def write_yaml(path: str | Path, data: dict[str, Any]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(to_serializable(data), sort_keys=False, allow_unicode=True), encoding="utf-8")


def load_calibration(path: str | Path) -> dict[str, Any]:
    data = read_yaml(path)
    if "camera_matrix" in data:
        data["camera_matrix"] = np.array(data["camera_matrix"], dtype=np.float64)
    if "dist_coeffs" in data:
        data["dist_coeffs"] = np.array(data["dist_coeffs"], dtype=np.float64)
    return data


def write_side_by_side(path: str | Path, left: np.ndarray, right: np.ndarray) -> None:
    if left.shape[:2] != right.shape[:2]:
        right = cv2.resize(right, (left.shape[1], left.shape[0]))
    canvas = np.hstack([left, right])
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), canvas)
