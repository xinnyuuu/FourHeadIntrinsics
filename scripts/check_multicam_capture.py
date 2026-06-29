#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import cv2

from vimas_calibration.io import IMAGE_EXTS
from vimas_calibration.rig import load_rig_config


def list_images(folder: Path) -> list[Path]:
    return sorted(path for path in folder.iterdir() if path.suffix.lower() in IMAGE_EXTS)


def image_shape(path: Path) -> list[int]:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise SystemExit(f"error: failed to read image: {path}")
    height, width = image.shape[:2]
    return [int(width), int(height)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Check synchronized multi-camera image folders before Kalibr bag export.")
    parser.add_argument("--config", default="configs/four_head_rig.yaml")
    parser.add_argument("--images-root", default="data/images")
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--min-frames", type=int, default=80)
    parser.add_argument("--require-equal-counts", action="store_true")
    args = parser.parse_args()

    rig = load_rig_config(args.config)
    report: dict[str, Any] = {
        "experiment": args.experiment,
        "images_root": args.images_root,
        "cameras": {},
        "ok": True,
        "warnings": [],
    }
    counts: list[int] = []
    shapes: list[tuple[int, int]] = []

    for camera in rig.cameras:
        folder = Path(args.images_root) / camera.key / args.experiment
        if not folder.exists():
            report["ok"] = False
            report["warnings"].append(f"missing folder for {camera.key}: {folder}")
            continue
        images = list_images(folder)
        counts.append(len(images))
        entry: dict[str, Any] = {
            "folder": str(folder),
            "count": len(images),
            "first": images[0].name if images else None,
            "last": images[-1].name if images else None,
            "source": camera.source,
        }
        if images:
            first_shape = image_shape(images[0])
            last_shape = image_shape(images[-1])
            entry["first_shape_wh"] = first_shape
            entry["last_shape_wh"] = last_shape
            shapes.append(tuple(first_shape))
            if first_shape != last_shape:
                report["ok"] = False
                report["warnings"].append(f"{camera.key} first/last image resolution differs")
        else:
            report["ok"] = False
            report["warnings"].append(f"no images for {camera.key}: {folder}")
        if len(images) < args.min_frames:
            report["warnings"].append(f"{camera.key} has {len(images)} frames; recommended >= {args.min_frames}")
        report["cameras"][camera.key] = entry

    if counts and len(set(counts)) != 1:
        message = f"image counts differ: {counts}"
        report["warnings"].append(message)
        if args.require_equal_counts:
            report["ok"] = False
    if shapes and len(set(shapes)) != 1:
        report["ok"] = False
        report["warnings"].append(f"image resolutions differ: {sorted(set(shapes))}")

    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
