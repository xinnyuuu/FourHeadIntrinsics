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


def detect_tag_count(path: Path, detector) -> int:
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise SystemExit(f"error: failed to read image: {path}")
    _, ids, _ = detector.detectMarkers(image)
    return 0 if ids is None else int(len(ids))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Select usable per-camera AprilGrid observations for sparse Kalibr multi-camera bag export."
    )
    parser.add_argument("--config", default="configs/four_head_rig.yaml")
    parser.add_argument("--images-root", default="data/images")
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--min-tags", type=int, default=2)
    parser.add_argument("--min-pair-observations", type=int, default=15)
    parser.add_argument(
        "--allowed-cameras",
        nargs="+",
        default=None,
        help="Only these cameras may be included. Useful for pair-focused experiments.",
    )
    parser.add_argument(
        "--force-include-cameras",
        nargs="+",
        default=[],
        help="Always include these cameras even if OpenCV AprilTag detection is weak. Useful for side fisheye cameras.",
    )
    parser.add_argument(
        "--required-pairs",
        nargs="+",
        default=None,
        metavar="left+right",
        help="Only require these adjacent pairs to meet --min-pair-observations.",
    )
    args = parser.parse_args()

    rig = load_rig_config(args.config)
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())

    camera_images: dict[str, list[Path]] = {}
    for camera in rig.cameras:
        folder = Path(args.images_root) / camera.key / args.experiment
        images = list_images(folder)
        if not images:
            raise SystemExit(f"error: no images found for {camera.key}: {folder}")
        camera_images[camera.key] = images

    counts = {key: len(images) for key, images in camera_images.items()}
    if len(set(counts.values())) != 1:
        raise SystemExit(f"error: image counts differ: {counts}")

    camera_keys = [camera.key for camera in rig.cameras]
    allowed = set(args.allowed_cameras or camera_keys)
    forced = set(args.force_include_cameras or [])
    unknown = sorted((allowed | forced) - set(camera_keys))
    if unknown:
        raise SystemExit(f"error: unknown camera keys: {', '.join(unknown)}")

    adjacent_pairs = [(rig.cameras[i].key, rig.cameras[i + 1].key) for i in range(len(rig.cameras) - 1)]
    per_camera_messages = {camera.key: 0 for camera in rig.cameras}
    per_pair_observations = {f"{left}+{right}": 0 for left, right in adjacent_pairs}
    frames: list[dict[str, Any]] = []
    frame_count = next(iter(counts.values()))

    for index in range(frame_count):
        tag_counts = {key: detect_tag_count(images[index], detector) for key, images in camera_images.items()}
        include = {
            key: key in allowed and (key in forced or count >= args.min_tags)
            for key, count in tag_counts.items()
        }
        good_pairs = []
        for left, right in adjacent_pairs:
            if include[left] and include[right]:
                pair_key = f"{left}+{right}"
                per_pair_observations[pair_key] += 1
                good_pairs.append(pair_key)
        for key, should_include in include.items():
            if should_include:
                per_camera_messages[key] += 1
        frames.append(
            {
                "index": index,
                "tag_counts": tag_counts,
                "include": include,
                "good_pairs": good_pairs,
            }
        )

    required_pairs = set(args.required_pairs or per_pair_observations.keys())
    unknown_pairs = sorted(required_pairs - set(per_pair_observations.keys()))
    if unknown_pairs:
        raise SystemExit(f"error: unknown/non-adjacent required pairs: {', '.join(unknown_pairs)}")

    warnings = [
        f"{pair} has only {count} shared observations; recommended >= {args.min_pair_observations}"
        for pair, count in per_pair_observations.items()
        if pair in required_pairs and count < args.min_pair_observations
    ]
    data = {
        "experiment": args.experiment,
        "images_root": args.images_root,
        "min_tags": args.min_tags,
        "allowed_cameras": sorted(allowed),
        "force_include_cameras": sorted(forced),
        "required_pairs": sorted(required_pairs),
        "frame_count": frame_count,
        "per_camera_messages": per_camera_messages,
        "per_adjacent_pair_observations": per_pair_observations,
        "warnings": warnings,
        "frames": frames,
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: data[k] for k in data if k != "frames"}, indent=2, ensure_ascii=False))
    print(f"wrote {out}")
    if warnings:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
