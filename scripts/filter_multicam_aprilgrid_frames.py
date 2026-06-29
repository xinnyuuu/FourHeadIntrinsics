#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
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
    corners, ids, _ = detector.detectMarkers(image)
    return 0 if ids is None else int(len(ids))


def link_or_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Filter synchronized multi-camera AprilGrid frames before Kalibr calibration."
    )
    parser.add_argument("--config", default="configs/four_head_rig.yaml")
    parser.add_argument("--images-root", default="data/images")
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--output-experiment", required=True)
    parser.add_argument("--min-tags", type=int, default=2, help="A camera observation is usable if it sees at least this many full tags.")
    parser.add_argument("--min-kept-sets", type=int, default=40)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    rig = load_rig_config(args.config)
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    parameters = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(dictionary, parameters)

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

    output_dirs = {camera.key: Path(args.images_root) / camera.key / args.output_experiment for camera in rig.cameras}
    for key, folder in output_dirs.items():
        if folder.exists() and list(folder.iterdir()) and not args.overwrite:
            raise SystemExit(f"error: output folder exists for {key}: {folder}; pass --overwrite")
        folder.mkdir(parents=True, exist_ok=True)

    adjacent_pairs = [(rig.cameras[i].key, rig.cameras[i + 1].key) for i in range(len(rig.cameras) - 1)]
    frame_count = next(iter(counts.values()))
    kept = []
    rejected: list[dict[str, Any]] = []
    per_camera_good = {camera.key: 0 for camera in rig.cameras}
    per_pair_good = {f"{left}+{right}": 0 for left, right in adjacent_pairs}

    for index in range(frame_count):
        tag_counts = {key: detect_tag_count(images[index], detector) for key, images in camera_images.items()}
        good = {key: count >= args.min_tags for key, count in tag_counts.items()}
        weak = {key: count for key, count in tag_counts.items() if 0 < count < args.min_tags}
        good_pairs = [(left, right) for left, right in adjacent_pairs if good[left] and good[right]]
        if weak or not good_pairs:
            rejected.append({"index": index, "tag_counts": tag_counts, "weak": weak, "good_pairs": good_pairs})
            continue
        kept.append((index, tag_counts, good_pairs))
        for key, is_good in good.items():
            if is_good:
                per_camera_good[key] += 1
        for left, right in good_pairs:
            per_pair_good[f"{left}+{right}"] += 1

    for new_index, (old_index, _, _) in enumerate(kept):
        for camera in rig.cameras:
            src = camera_images[camera.key][old_index]
            dst = output_dirs[camera.key] / f"frame_{new_index:06d}{src.suffix.lower()}"
            if dst.exists():
                dst.unlink()
            link_or_copy(src, dst)

    report = {
        "source_experiment": args.experiment,
        "output_experiment": args.output_experiment,
        "min_tags": args.min_tags,
        "input_sets": frame_count,
        "kept_sets": len(kept),
        "rejected_sets": len(rejected),
        "per_camera_good_sets": per_camera_good,
        "per_adjacent_pair_good_sets": per_pair_good,
        "first_rejected": rejected[:20],
    }
    report_path = Path(args.images_root) / f"{args.output_experiment}_aprilgrid_filter_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"wrote {report_path}")
    if len(kept) < args.min_kept_sets:
        raise SystemExit(f"error: kept only {len(kept)} frame sets; recommended >= {args.min_kept_sets}")


if __name__ == "__main__":
    main()
