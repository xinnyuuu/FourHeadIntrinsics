#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
import yaml


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


def list_images(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTS)


def load_ds_intrinsics(camchain: Path, camera: str) -> tuple[float, float, float, float, float, float]:
    data = yaml.safe_load(camchain.read_text(encoding="utf-8")) or {}
    if camera not in data:
        raise SystemExit(f"error: camera {camera!r} not found in {camchain}")
    cam = data[camera]
    if cam.get("camera_model") != "ds":
        raise SystemExit(f"error: camera_model must be 'ds', got {cam.get('camera_model')!r}")
    intrinsics = cam.get("intrinsics")
    if not isinstance(intrinsics, list) or len(intrinsics) != 6:
        raise SystemExit("error: ds intrinsics must be [xi, alpha, fx, fy, cx, cy]")
    return tuple(float(x) for x in intrinsics)  # type: ignore[return-value]


def ds_project(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    xi: float,
    alpha: float,
    fx: float,
    fy: float,
    cx: float,
    cy: float,
) -> tuple[np.ndarray, np.ndarray]:
    d1 = np.sqrt(x * x + y * y + z * z)
    z_xi = xi * d1 + z
    d2 = np.sqrt(x * x + y * y + z_xi * z_xi)
    denom = alpha * d2 + (1.0 - alpha) * z_xi
    map_x = fx * x / denom + cx
    map_y = fy * y / denom + cy
    return map_x.astype(np.float32), map_y.astype(np.float32)


def make_rectified_map(
    width: int,
    height: int,
    intrinsics: tuple[float, float, float, float, float, float],
    rectified_focal_px: float,
) -> tuple[np.ndarray, np.ndarray]:
    xi, alpha, fx, fy, cx, cy = intrinsics
    u, v = np.meshgrid(np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32))
    cx_new = (width - 1.0) / 2.0
    cy_new = (height - 1.0) / 2.0
    x = (u - cx_new) / rectified_focal_px
    y = (v - cy_new) / rectified_focal_px
    z = np.ones_like(x)
    return ds_project(x, y, z, xi, alpha, fx, fy, cx, cy)


def write_side_by_side(path: Path, left: np.ndarray, right: np.ndarray) -> None:
    canvas = np.hstack([left, right])
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), canvas)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate rectilinear undistortion previews from a Kalibr ds camchain.")
    parser.add_argument("--camchain", required=True)
    parser.add_argument("--camera", default="cam0")
    parser.add_argument("--images", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--rectified-focal-px", type=float, default=None)
    args = parser.parse_args()

    intrinsics = load_ds_intrinsics(Path(args.camchain), args.camera)
    images = list_images(Path(args.images))
    if not images:
        raise SystemExit(f"error: no images found in {args.images}")
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    map_cache: dict[tuple[int, int], tuple[np.ndarray, np.ndarray]] = {}
    written = 0
    for image_path in images:
        if written >= args.limit:
            break
        img = cv2.imread(str(image_path))
        if img is None:
            continue
        height, width = img.shape[:2]
        focal = args.rectified_focal_px or min(width, height) * 0.45
        key = (width, height)
        if key not in map_cache:
            map_cache[key] = make_rectified_map(width, height, intrinsics, focal)
        map_x, map_y = map_cache[key]
        undistorted = cv2.remap(img, map_x, map_y, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        write_side_by_side(out_dir / f"undistort_{image_path.name}", img, undistorted)
        written += 1

    print(f"wrote {written} previews to {out_dir}")
    print(f"rectified_focal_px: {args.rectified_focal_px or 'auto'}")


if __name__ == "__main__":
    main()
