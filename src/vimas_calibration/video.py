from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

import cv2


@dataclass(frozen=True)
class CaptureSpec:
    source: str
    width: int = 0
    height: int = 0
    fps: float = 0.0
    fourcc: str = ""


def normalize_source(source: str) -> int | str:
    if source.startswith("/dev/video"):
        return source
    if source.isdigit():
        return int(source)
    return source


def open_capture(spec: CaptureSpec) -> cv2.VideoCapture:
    source = normalize_source(spec.source)
    if isinstance(source, str) and source.startswith("/dev/video"):
        cap = cv2.VideoCapture(source, cv2.CAP_V4L2)
    elif isinstance(source, int):
        cap = cv2.VideoCapture(source, cv2.CAP_V4L2)
    else:
        cap = cv2.VideoCapture(source)
    if spec.fourcc:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*spec.fourcc))
    if spec.width:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, spec.width)
    if spec.height:
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, spec.height)
    if spec.fps:
        cap.set(cv2.CAP_PROP_FPS, spec.fps)
    return cap


def camera_summary(cap: cv2.VideoCapture) -> dict[str, float | str]:
    fourcc_int = int(cap.get(cv2.CAP_PROP_FOURCC))
    fourcc = "".join(chr((fourcc_int >> 8 * idx) & 0xFF) for idx in range(4)).strip()
    return {
        "width": cap.get(cv2.CAP_PROP_FRAME_WIDTH),
        "height": cap.get(cv2.CAP_PROP_FRAME_HEIGHT),
        "fps": cap.get(cv2.CAP_PROP_FPS),
        "fourcc": fourcc,
    }


def indexed_video_devices(max_index: int) -> list[tuple[int, str]]:
    devices = []
    for idx in range(max_index + 1):
        devices.append((idx, f"/dev/video{idx}"))
    return devices


def existing_video_devices(max_index: int) -> list[tuple[int, str]]:
    devices = []
    for path in sorted(Path("/dev").glob("video*"), key=lambda item: item.name):
        suffix = path.name.removeprefix("video")
        if suffix.isdigit() and int(suffix) <= max_index:
            devices.append((int(suffix), str(path)))
    return devices


def list_available_cameras(
    max_index: int = 12,
    require_frame: bool = False,
    include_missing: bool = False,
) -> list[dict[str, object]]:
    cameras: list[dict[str, object]] = []
    devices = existing_video_devices(max_index)
    if not devices:
        devices = indexed_video_devices(max_index)

    for idx, source in devices:
        cap = cv2.VideoCapture(source, cv2.CAP_V4L2)
        opened = cap.isOpened()
        read_ok = False
        if opened:
            ok, _ = cap.read()
            read_ok = bool(ok)
        if opened and (read_ok or not require_frame):
            cameras.append({"index": idx, "source": source, "opened": opened, "read_ok": read_ok, **camera_summary(cap)})
        elif include_missing:
            cameras.append({"index": idx, "source": source, "opened": opened, "read_ok": read_ok})
        cap.release()
    return cameras


def source_label(source: str) -> str:
    if source.startswith("/dev/"):
        return Path(source).name
    return source.replace("/", "_").replace(":", "_")
