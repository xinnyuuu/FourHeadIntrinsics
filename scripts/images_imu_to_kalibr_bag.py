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
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTS)


def read_imu_records(path: Path) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if {"timestamp_monotonic_ns", "accel_mps2", "gyro_radps"} <= record.keys():
            records.append(record)
    records.sort(key=lambda item: int(item["timestamp_monotonic_ns"]))
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a ROS1 Kalibr bag with selected camera image folders and one IMU JSONL.")
    parser.add_argument("--config", default="configs/four_head_rig.yaml")
    parser.add_argument("--images-root", default="data/images")
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--camera", action="append", dest="cameras", help="Camera key to include. Repeat for multiple cameras.")
    parser.add_argument("--imu-jsonl", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--fps", type=float, default=None, help="Image FPS. Defaults to capture.fps from config.")
    parser.add_argument("--imu-topic", default="/imu0")
    parser.add_argument("--topic-suffix", default="/image_raw")
    parser.add_argument("--truncate", action="store_true", help="Use shortest image sequence if camera counts differ.")
    args = parser.parse_args()

    import cv2
    import rosbag
    import rospy
    from sensor_msgs.msg import Image, Imu

    rig = load_rig_config(args.config)
    selected = args.cameras or [camera.key for camera in rig.cameras]
    cameras_by_key = {camera.key: camera for camera in rig.cameras}
    missing = [key for key in selected if key not in cameras_by_key]
    if missing:
        raise SystemExit(f"error: unknown camera keys: {missing}")

    fps = float(args.fps if args.fps is not None else rig.fps)
    if fps <= 0:
        raise SystemExit("error: --fps must be positive or capture.fps must be set in config")

    image_sets: list[tuple[str, str, list[Path]]] = []
    for key in selected:
        folder = Path(args.images_root) / key / args.experiment
        images = list_images(folder)
        if not images:
            raise SystemExit(f"error: no images found for {key}: {folder}")
        image_sets.append((key, f"/{key}{args.topic_suffix}", images))

    counts = [len(images) for _, _, images in image_sets]
    if len(set(counts)) != 1 and not args.truncate:
        raise SystemExit(f"error: image counts differ {counts}; pass --truncate to use the shortest sequence")
    frame_count = min(counts)
    imu_records = read_imu_records(Path(args.imu_jsonl))
    if not imu_records:
        raise SystemExit(f"error: no IMU records found in {args.imu_jsonl}")

    image_dt = 1.0 / fps
    imu_t0 = int(imu_records[0]["timestamp_monotonic_ns"])
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with rosbag.Bag(str(out), "w") as bag:
        for index in range(frame_count):
            stamp = rospy.Time.from_sec(index * image_dt)
            for camera_key, topic, images in image_sets:
                img = cv2.imread(str(images[index]), cv2.IMREAD_COLOR)
                if img is None:
                    raise SystemExit(f"error: failed to read image: {images[index]}")
                msg = Image()
                msg.header.stamp = stamp
                msg.header.frame_id = camera_key
                msg.height, msg.width = img.shape[:2]
                msg.encoding = "bgr8"
                msg.is_bigendian = False
                msg.step = int(img.strides[0])
                msg.data = img.tobytes()
                bag.write(topic, msg, stamp)
        for record in imu_records:
            stamp = rospy.Time.from_sec((int(record["timestamp_monotonic_ns"]) - imu_t0) * 1e-9)
            msg = Imu()
            msg.header.stamp = stamp
            msg.header.frame_id = "imu0"
            msg.linear_acceleration.x = float(record["accel_mps2"][0])
            msg.linear_acceleration.y = float(record["accel_mps2"][1])
            msg.linear_acceleration.z = float(record["accel_mps2"][2])
            msg.angular_velocity.x = float(record["gyro_radps"][0])
            msg.angular_velocity.y = float(record["gyro_radps"][1])
            msg.angular_velocity.z = float(record["gyro_radps"][2])
            bag.write(args.imu_topic, msg, stamp)

    print(f"wrote {out}")
    print(f"image_frames_per_camera: {frame_count}")
    print(f"imu_samples: {len(imu_records)}")
    print(f"imu_topic: {args.imu_topic}")
    for camera_key, topic, images in image_sets:
        print(f"{camera_key}: topic={topic} images={len(images)}")


if __name__ == "__main__":
    main()
