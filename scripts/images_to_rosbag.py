#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


def list_images(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert an image folder to a ROS1 bag for Kalibr.")
    parser.add_argument("--images", required=True, help="Input image folder.")
    parser.add_argument("--output", required=True, help="Output ROS1 bag path.")
    parser.add_argument("--topic", default="/cam0/image_raw")
    parser.add_argument("--fps", type=float, default=25.0)
    parser.add_argument("--frame-id", default="cam0")
    args = parser.parse_args()

    import cv2
    import rosbag
    import rospy
    from sensor_msgs.msg import Image

    image_dir = Path(args.images)
    images = list_images(image_dir)
    if not images:
        raise SystemExit(f"error: no images found in {image_dir}")
    if args.fps <= 0:
        raise SystemExit("error: --fps must be positive")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    dt = 1.0 / args.fps

    with rosbag.Bag(str(out), "w") as bag:
        for index, path in enumerate(images):
            img = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if img is None:
                raise SystemExit(f"error: failed to read image: {path}")
            stamp = rospy.Time.from_sec(index * dt)
            msg = Image()
            msg.header.stamp = stamp
            msg.header.frame_id = args.frame_id
            msg.height, msg.width = img.shape[:2]
            msg.encoding = "bgr8"
            msg.is_bigendian = False
            msg.step = int(img.strides[0])
            msg.data = img.tobytes()
            bag.write(args.topic, msg, stamp)

    print(f"wrote {out}")
    print(f"images: {len(images)}")
    print(f"topic: {args.topic}")
    print(f"fps: {args.fps}")


if __name__ == "__main__":
    main()
