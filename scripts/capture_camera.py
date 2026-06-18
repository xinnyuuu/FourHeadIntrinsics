#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import cv2
import numpy as np

from fourhead_intrinsics.video import CaptureSpec, camera_summary, open_capture


def frame_motion_score(previous_gray: np.ndarray | None, frame: np.ndarray, width: int) -> tuple[float, np.ndarray]:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    if width > 0 and w > width:
        scale = width / float(w)
        gray = cv2.resize(gray, (width, max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    if previous_gray is None or previous_gray.shape != gray.shape:
        return 0.0, gray
    return float(cv2.absdiff(previous_gray, gray).mean()), gray


def beep(enabled: bool) -> None:
    if not enabled:
        return
    paplay = shutil.which("paplay")
    sound = Path("/usr/share/sounds/freedesktop/stereo/complete.oga")
    if paplay and sound.exists():
        subprocess.Popen([paplay, str(sound)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    print("\a", end="", flush=True)


def open_source_or_none(args: argparse.Namespace):
    cap = open_capture(CaptureSpec(args.source, args.width, args.height, args.fps, args.fourcc))
    if not cap.isOpened():
        cap.release()
        return None
    return cap


def resolve_output_dir(args: argparse.Namespace, parser: argparse.ArgumentParser) -> Path:
    if args.output:
        return Path(args.output)
    if not args.camera or not args.experiment:
        parser.error("Either pass --output, or pass both --camera and --experiment.")
    return Path(args.images_root) / args.camera / args.experiment


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture still calibration images from one USB camera.")
    parser.add_argument("--source", required=True, help="Camera index, /dev/videoX, URL, or video file.")
    parser.add_argument("--output", help="Output image folder for this camera. Overrides --camera/--experiment.")
    parser.add_argument("--camera", help="Camera key such as left_side, left_front, right_front, right_side.")
    parser.add_argument("--experiment", help="Experiment/run name such as exp01 or 20260618_left_side_v2.")
    parser.add_argument("--images-root", default="data/images")
    parser.add_argument("--prefix", help="Saved image filename prefix. Defaults to --camera, then 'calib'.")
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=1200)
    parser.add_argument("--fps", type=float, default=25.0)
    parser.add_argument("--fourcc", default="MJPG", help="MJPG or YUYV. Empty string keeps default.")
    parser.add_argument("--interval", type=float, default=0.0, help="Auto-save interval. 0 disables auto-save.")
    parser.add_argument("--start-delay", type=float, default=3.0)
    parser.add_argument("--max-images", type=int, default=100)
    parser.add_argument("--require-still", action="store_true")
    parser.add_argument("--motion-threshold", type=float, default=2.0)
    parser.add_argument("--stable-seconds", type=float, default=0.8)
    parser.add_argument("--motion-width", type=int, default=320)
    parser.add_argument("--no-preview", action="store_true")
    parser.add_argument("--no-beep", action="store_true")
    args = parser.parse_args()

    out_dir = resolve_output_dir(args, parser)
    prefix = args.prefix or args.camera or "calib"
    out_dir.mkdir(parents=True, exist_ok=True)

    cap = open_source_or_none(args)
    if cap is None:
        raise RuntimeError(f"Cannot open video source: {args.source}")
    print(f"opened {args.source}: {camera_summary(cap)}")
    print("Press SPACE/S/ENTER to save, A to toggle auto interval, Q/ESC to quit.")

    print(f"writing images to {out_dir}")
    saved = len(list(out_dir.glob(f"{prefix}_*.png")))
    auto = args.interval > 0
    start_time = time.time()
    last_save = 0.0
    previous_motion_gray: np.ndarray | None = None
    stable_since: float | None = None
    motion_score = 0.0

    while saved < args.max_images:
        ok, frame = cap.read()
        if not ok:
            raise RuntimeError(f"Read failed from {args.source}")

        now = time.time()
        motion_score, previous_motion_gray = frame_motion_score(previous_motion_gray, frame, args.motion_width)
        if args.require_still:
            if motion_score <= args.motion_threshold:
                stable_since = stable_since or now
            else:
                stable_since = None
            is_still = stable_since is not None and now - stable_since >= args.stable_seconds
        else:
            is_still = True

        ready = now - start_time >= args.start_delay
        should_save = auto and ready and is_still and now - last_save >= args.interval

        if not args.no_preview:
            display = frame.copy()
            status = (
                f"saved={saved} auto={'on' if auto else 'off'} "
                f"motion={motion_score:.2f} {'still' if is_still else 'moving'}"
            )
            if not ready:
                status = f"starting in {args.start_delay - (now - start_time):.1f}s"
            cv2.putText(display, status, (20, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2, cv2.LINE_AA)
            cv2.imshow(f"capture {args.source}", display)
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q")):
                break
            if key == ord("a"):
                auto = not auto
            if key in (32, 10, 13, ord("s"), ord("S")):
                should_save = True

        if should_save:
            path = out_dir / f"{prefix}_{saved:03d}.png"
            cv2.imwrite(str(path), frame)
            print(f"saved {path} motion={motion_score:.3f}")
            beep(not args.no_beep)
            saved += 1
            last_save = now
            stable_since = None

    cap.release()
    if not args.no_preview:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
