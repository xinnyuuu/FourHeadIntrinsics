#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vimas_calibration.io import IMAGE_EXTS
from vimas_calibration.rig import load_rig_config


def list_images(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert synchronized multi-camera image folders to one ROS1 bag for Kalibr.")
    parser.add_argument("--config", default="configs/four_head_rig.yaml")
    parser.add_argument("--images-root", default="data/images", help="Contains one subfolder per camera key.")
    parser.add_argument("--experiment", required=True, help="Experiment folder under each camera directory.")
    parser.add_argument("--output", required=True, help="Output ROS1 bag path.")
    parser.add_argument("--fps", type=float, default=None, help="Defaults to capture.fps from config.")
    parser.add_argument("--topic-suffix", default="/image_raw", help="Topic suffix appended to /<camera_key>.")
    parser.add_argument("--truncate", action="store_true", help="Use the shortest camera sequence if counts differ.")
    parser.add_argument("--max-frames", type=int, default=None)
    args = parser.parse_args()

    import cv2
    import rosbag
    import rospy
    from sensor_msgs.msg import Image

    rig = load_rig_config(args.config)
    fps = float(args.fps if args.fps is not None else rig.fps)
    if fps <= 0:
        raise SystemExit("error: --fps must be positive or capture.fps must be set in config")

    images_root = Path(args.images_root)
    camera_images: list[tuple[str, str, list[Path]]] = []
    for camera in rig.cameras:
        folder = images_root / camera.key / args.experiment
        images = list_images(folder)
        if not images:
            raise SystemExit(f"error: no images found for {camera.key}: {folder}")
        topic = f"/{camera.key}{args.topic_suffix}"
        camera_images.append((camera.key, topic, images))

    counts = [len(images) for _, _, images in camera_images]
    if len(set(counts)) != 1 and not args.truncate:
        raise SystemExit(f"error: image counts differ {counts}; pass --truncate to use the shortest sequence")

    frame_count = min(counts)
    if args.max_frames is not None:
        frame_count = min(frame_count, args.max_frames)
    if frame_count <= 0:
        raise SystemExit("error: no frames to write")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    dt = 1.0 / fps

    with rosbag.Bag(str(out), "w") as bag:
        for index in range(frame_count):
            stamp = rospy.Time.from_sec(index * dt)
            for camera_key, topic, images in camera_images:
                path = images[index]
                img = cv2.imread(str(path), cv2.IMREAD_COLOR)
                if img is None:
                    raise SystemExit(f"error: failed to read image: {path}")
                msg = Image()
                msg.header.stamp = stamp
                msg.header.frame_id = camera_key
                msg.height, msg.width = img.shape[:2]
                msg.encoding = "bgr8"
                msg.is_bigendian = False
                msg.step = int(img.strides[0])
                msg.data = img.tobytes()
                bag.write(topic, msg, stamp)

    print(f"wrote {out}")
    print(f"frames_per_camera: {frame_count}")
    print(f"fps: {fps}")
    for camera_key, topic, images in camera_images:
        print(f"{camera_key}: topic={topic} images={len(images)}")


if __name__ == "__main__":
    main()
