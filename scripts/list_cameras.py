#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vimas_calibration.video import list_available_cameras


def main() -> None:
    parser = argparse.ArgumentParser(description="List local OpenCV/V4L2 camera devices.")
    parser.add_argument("--max-index", type=int, default=12)
    parser.add_argument(
        "--require-frame",
        action="store_true",
        help="Only show devices that can return a frame. Useful for hiding UVC metadata nodes.",
    )
    parser.add_argument("--include-missing", action="store_true", help="Also show devices that fail to open/read.")
    args = parser.parse_args()

    cameras = list_available_cameras(args.max_index, args.require_frame, args.include_missing)
    if not cameras:
        print("No cameras opened. Try unplug/replug, check permissions, or lower --max-index.")
        return
    for camera in cameras:
        if camera.get("opened"):
            print(
                f"index={camera['index']} source={camera['source']} "
                f"opened={camera['opened']} read_ok={camera['read_ok']} "
                f"size={camera['width']:.0f}x{camera['height']:.0f} "
                f"fps={camera['fps']:.2f} fourcc={camera['fourcc']}"
            )
        else:
            print(f"index={camera['index']} source={camera['source']} opened=false read_ok=false")


if __name__ == "__main__":
    main()
