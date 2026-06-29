#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vimas_calibration.io import IMAGE_EXTS
from vimas_calibration.rig import load_rig_config


def list_images(folder: Path) -> list[Path]:
    return sorted(path for path in folder.iterdir() if path.suffix.lower() in IMAGE_EXTS)


def load_selection(path: Path) -> dict[int, dict[str, bool]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    frames = data.get("frames") or []
    selection: dict[int, dict[str, bool]] = {}
    for frame in frames:
        selection[int(frame["index"])] = {str(key): bool(value) for key, value in (frame.get("include") or {}).items()}
    return selection


def parse_experiment_arg(value: str) -> tuple[str, Path | None]:
    if ":" not in value:
        return value, None
    experiment, selection = value.split(":", 1)
    return experiment, Path(selection)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge multiple synchronized image experiments into one sparse multi-camera ROS1 bag for Kalibr."
    )
    parser.add_argument("--config", default="configs/four_head_rig.yaml")
    parser.add_argument("--images-root", default="data/images")
    parser.add_argument(
        "--experiment",
        action="append",
        required=True,
        metavar="NAME[:selection.json]",
        help="Experiment to append. Can be repeated. Selection JSON omits weak per-camera observations.",
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--fps", type=float, default=None)
    parser.add_argument("--topic-suffix", default="/image_raw")
    parser.add_argument("--gap-s", type=float, default=1.0, help="Timestamp gap between experiments.")
    args = parser.parse_args()

    import cv2
    import rosbag
    import rospy
    from sensor_msgs.msg import Image

    rig = load_rig_config(args.config)
    fps = float(args.fps if args.fps is not None else rig.fps)
    if fps <= 0:
        raise SystemExit("error: --fps must be positive or capture.fps must be set in config")
    dt = 1.0 / fps

    experiments = [parse_experiment_arg(item) for item in args.experiment]
    images_root = Path(args.images_root)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    written_counts = {camera.key: 0 for camera in rig.cameras}
    written_pair_counts = {f"{rig.cameras[i].key}+{rig.cameras[i + 1].key}": 0 for i in range(len(rig.cameras) - 1)}

    stamp_index = 0
    with rosbag.Bag(str(out), "w") as bag:
        for experiment, selection_path in experiments:
            camera_images = {}
            for camera in rig.cameras:
                folder = images_root / camera.key / experiment
                images = list_images(folder)
                if not images:
                    raise SystemExit(f"error: no images for {camera.key} in {folder}")
                camera_images[camera.key] = images
            counts = {key: len(images) for key, images in camera_images.items()}
            if len(set(counts.values())) != 1:
                raise SystemExit(f"error: image counts differ for {experiment}: {counts}")
            selection = load_selection(selection_path) if selection_path else {}
            frame_count = next(iter(counts.values()))

            for index in range(frame_count):
                include = {camera.key: True for camera in rig.cameras}
                if selection:
                    include = selection.get(index, {})
                if not any(include.values()):
                    continue

                stamp = rospy.Time.from_sec(stamp_index * dt)
                present = []
                for camera in rig.cameras:
                    if not include.get(camera.key, False):
                        continue
                    path = camera_images[camera.key][index]
                    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
                    if image is None:
                        raise SystemExit(f"error: failed to read image: {path}")
                    msg = Image()
                    msg.header.stamp = stamp
                    msg.header.frame_id = camera.key
                    msg.height, msg.width = image.shape[:2]
                    msg.encoding = "bgr8"
                    msg.is_bigendian = False
                    msg.step = int(image.strides[0])
                    msg.data = image.tobytes()
                    bag.write(f"/{camera.key}{args.topic_suffix}", msg, stamp)
                    written_counts[camera.key] += 1
                    present.append(camera.key)

                present_set = set(present)
                for left, right in zip(rig.cameras, rig.cameras[1:]):
                    if left.key in present_set and right.key in present_set:
                        written_pair_counts[f"{left.key}+{right.key}"] += 1
                stamp_index += 1

            stamp_index += int(round(max(0.0, args.gap_s) * fps))

    print(f"wrote {out}")
    print(f"fps: {fps}")
    print("written camera messages:")
    for key, count in written_counts.items():
        print(f"  {key}: {count}")
    print("written adjacent-pair shared timestamps:")
    for key, count in written_pair_counts.items():
        print(f"  {key}: {count}")


if __name__ == "__main__":
    main()
