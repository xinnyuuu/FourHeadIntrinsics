#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import cv2

from vimas_calibration.io import write_yaml
from vimas_calibration.rig import load_rig_config
from vimas_calibration.video import CaptureSpec, camera_summary, open_capture


def open_cameras(config_path: str, width: int | None, height: int | None, fps: float | None, fourcc: str | None):
    rig = load_rig_config(config_path)
    if not rig.cameras:
        raise SystemExit(f"error: no cameras in {config_path}")

    capture_width = int(width if width is not None else rig.width)
    capture_height = int(height if height is not None else rig.height)
    capture_fps = float(fps if fps is not None else rig.fps)
    capture_fourcc = str(fourcc if fourcc is not None else rig.fourcc)

    cameras = []
    for camera in rig.cameras:
        cap = open_capture(CaptureSpec(camera.source, capture_width, capture_height, capture_fps, capture_fourcc))
        if not cap.isOpened():
            cap.release()
            raise SystemExit(f"error: cannot open {camera.key} source={camera.source}")
        cameras.append((camera, cap))
        print(f"opened {camera.key} source={camera.source}: {camera_summary(cap)}")
    return rig, cameras, capture_width, capture_height, capture_fps, capture_fourcc


def grab_frame_set(cameras, flush_frames: int) -> dict[str, object]:
    for _ in range(max(0, flush_frames)):
        for _, cap in cameras:
            cap.grab()

    for camera, cap in cameras:
        if not cap.grab():
            raise RuntimeError(f"grab failed for {camera.key}")

    frames = {}
    for camera, cap in cameras:
        ok, frame = cap.retrieve()
        if not ok:
            raise RuntimeError(f"retrieve failed for {camera.key}")
        frames[camera.key] = frame
    return frames


def draw_preview(frames: dict[str, object], preview_width: int) -> object:
    tiles = []
    for key, frame in frames.items():
        tile = frame.copy()
        height, width = tile.shape[:2]
        if width > preview_width:
            scale = preview_width / float(width)
            tile = cv2.resize(tile, (preview_width, max(1, int(height * scale))), interpolation=cv2.INTER_AREA)
        cv2.putText(tile, key, (16, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2, cv2.LINE_AA)
        tiles.append(tile)
    if len(tiles) == 1:
        return tiles[0]
    if len(tiles) == 2:
        return cv2.hconcat(tiles)
    top = cv2.hconcat(tiles[:2])
    bottom = cv2.hconcat(tiles[2:4])
    return cv2.vconcat([top, bottom])


def save_frame_set(frames: dict[str, object], output_dirs: dict[str, Path], index: int, extension: str) -> None:
    for key, frame in frames.items():
        path = output_dirs[key] / f"frame_{index:06d}.{extension}"
        if not cv2.imwrite(str(path), frame):
            raise RuntimeError(f"failed to write {path}")
    print(f"saved synchronized frame set {index:06d}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Capture synchronized four-camera image sets for Kalibr multi-camera extrinsics."
    )
    parser.add_argument("--config", default="configs/four_head_rig.yaml")
    parser.add_argument("--images-root", default="data/images")
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--width", type=int, default=None)
    parser.add_argument("--height", type=int, default=None)
    parser.add_argument("--fps", type=float, default=None)
    parser.add_argument("--fourcc", default=None)
    parser.add_argument("--max-sets", type=int, default=250)
    parser.add_argument("--interval", type=float, default=0.0, help="Auto-save interval in seconds. 0 means manual only.")
    parser.add_argument("--start-delay", type=float, default=2.0)
    parser.add_argument("--flush-frames", type=int, default=2, help="Drop this many buffered frames before each saved set.")
    parser.add_argument("--extension", default="png", choices=["png", "jpg", "jpeg"])
    parser.add_argument("--preview-width", type=int, default=480)
    parser.add_argument("--no-preview", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    rig, cameras, width, height, fps, fourcc = open_cameras(args.config, args.width, args.height, args.fps, args.fourcc)
    output_dirs = {camera.key: Path(args.images_root) / camera.key / args.experiment for camera, _ in cameras}
    for key, folder in output_dirs.items():
        existing = sorted(folder.glob(f"frame_*.{args.extension}")) if folder.exists() else []
        if existing and not args.overwrite:
            raise SystemExit(f"error: {key} output folder already has {len(existing)} frames: {folder}; pass --overwrite")
        folder.mkdir(parents=True, exist_ok=True)

    metadata_path = Path(args.images_root) / f"{args.experiment}_multicam_capture.yaml"
    metadata = {
        "experiment": args.experiment,
        "config": args.config,
        "capture": {"width": width, "height": height, "fps": fps, "fourcc": fourcc},
        "cameras": [
            {"key": camera.key, "label": camera.label, "role": camera.role, "source": camera.source}
            for camera, _ in cameras
        ],
        "output_dirs": {key: str(folder) for key, folder in output_dirs.items()},
        "usage": "Move AprilGrid through left_side+left_front, left_front+right_front, right_front+right_side overlaps.",
    }

    print("Controls: SPACE/S/ENTER save all cameras, A toggle auto, Q/ESC quit.")
    print("Move the AprilGrid through neighboring overlap regions while all four cameras stream.")
    start_time = time.time()
    last_save = 0.0
    saved = 0
    auto = args.interval > 0.0

    try:
        while saved < args.max_sets:
            frames = grab_frame_set(cameras, flush_frames=0)
            now = time.time()
            ready = now - start_time >= args.start_delay
            should_save = auto and ready and now - last_save >= args.interval

            if not args.no_preview:
                preview = draw_preview(frames, args.preview_width)
                status = f"saved={saved}/{args.max_sets} auto={'on' if auto else 'off'}"
                if not ready:
                    status = f"starting in {args.start_delay - (now - start_time):.1f}s"
                cv2.putText(preview, status, (16, preview.shape[0] - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2, cv2.LINE_AA)
                cv2.imshow("multicam extrinsics capture", preview)
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")):
                    break
                if key == ord("a"):
                    auto = not auto
                if key in (32, 10, 13, ord("s"), ord("S")) and ready:
                    should_save = True

            if should_save:
                frames = grab_frame_set(cameras, args.flush_frames)
                save_frame_set(frames, output_dirs, saved, args.extension)
                saved += 1
                last_save = time.time()
    finally:
        for _, cap in cameras:
            cap.release()
        if not args.no_preview:
            cv2.destroyAllWindows()

    metadata["saved_sets"] = saved
    write_yaml(metadata_path, metadata)
    print(f"wrote {metadata_path}")
    print(f"saved synchronized sets: {saved}")


if __name__ == "__main__":
    main()
