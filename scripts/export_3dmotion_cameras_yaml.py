#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fourhead_intrinsics.io import read_yaml, write_yaml


DEFAULT_CAMERA_MAP = "left_side:C0:left_ear,left_front:C1:front_left,right_front:C2:front_right,right_side:C3:right_ear"


def parse_camera_map(value: str) -> dict[str, tuple[str, str]]:
    mapping: dict[str, tuple[str, str]] = {}
    for item in value.split(","):
        parts = [part.strip() for part in item.split(":")]
        if len(parts) != 3 or not all(parts):
            raise argparse.ArgumentTypeError(
                "Camera map entries must be fourhead_key:3dmotion_id:role, "
                f"got {item!r}."
            )
        fourhead_key, camera_id, role = parts
        mapping[fourhead_key] = (camera_id, role)
    return mapping


def export_3dmotion_cameras(
    intrinsics_path: Path,
    output_path: Path,
    camera_map: dict[str, tuple[str, str]],
    existing_path: Path | None,
    profile_name: str,
    capture_format: str,
    capture_fps: float,
) -> dict[str, Any]:
    intrinsics = read_yaml(intrinsics_path)
    existing = read_yaml(existing_path) if existing_path and existing_path.exists() else {}
    existing_cameras = existing.get("cameras", {})
    setting = intrinsics.get("setting", {})
    image_size = setting.get("image_size")
    if image_size is None:
        raise RuntimeError(f"Missing setting.image_size in {intrinsics_path}.")

    cameras: dict[str, Any] = {}
    for fourhead_key, (camera_id, role) in camera_map.items():
        source_key, source = _find_camera_entry(intrinsics, fourhead_key)
        existing_camera = existing_cameras.get(camera_id, {})
        camera_model = _to_3dmotion_camera_model(str(source.get("camera_model", setting.get("camera_model", "pinhole"))))
        distortion_model = _to_3dmotion_distortion_model(
            str(source.get("distortion_model", setting.get("distortion_model", "plumb_bob")))
        )
        cameras[camera_id] = {
            "role": role,
            "source_calibration": source_key,
            "image_size": source.get("image_size", image_size),
            "camera_model": camera_model,
            "distortion_model": distortion_model,
            "intrinsics": source["camera_matrix"],
            "distortion": source["dist_coeffs"],
            "T_H_C": existing_camera.get("T_H_C"),
        }

    data = {
        "profile": {
            "name": profile_name,
            "format": capture_format,
            "fps": capture_fps,
            "image_size": image_size,
            "source": str(intrinsics_path),
            "note": "Intrinsics must be recalibrated whenever capture resolution or crop/aspect ratio changes.",
        },
        "camera_defaults": {
            "image_size": image_size,
            "camera_model": _to_3dmotion_camera_model(str(setting.get("camera_model", "fisheye"))),
            "distortion_model": _to_3dmotion_distortion_model(str(setting.get("distortion_model", "opencv_fisheye"))),
        },
        "cameras": dict(sorted(cameras.items())),
    }
    write_yaml(output_path, data)
    return data


def _find_camera_entry(intrinsics: dict[str, Any], fourhead_key: str) -> tuple[str, dict[str, Any]]:
    for key, value in intrinsics.items():
        if not key.startswith("camera_") or not isinstance(value, dict):
            continue
        if key.endswith(f"_{fourhead_key}"):
            return key, value
    raise RuntimeError(f"Could not find camera entry for {fourhead_key!r}.")


def _to_3dmotion_camera_model(value: str) -> str:
    if value in {"fisheye", "omnidirectional"}:
        return "fisheye"
    return "pinhole"


def _to_3dmotion_distortion_model(value: str) -> str:
    if value in {"opencv_fisheye", "equidistant", "fisheye"}:
        return "equidistant"
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Export FourHeadIntrinsics results to 3DMotion configs/cameras.yaml.")
    parser.add_argument("--intrinsics", default="data/results/four_camera_intrinsics.yaml")
    parser.add_argument("--output", default="../3DMotion/configs/cameras.yaml")
    parser.add_argument("--existing", default="../3DMotion/configs/cameras.yaml", help="Existing 3DMotion cameras YAML used to preserve T_H_C.")
    parser.add_argument("--camera-map", type=parse_camera_map, default=parse_camera_map(DEFAULT_CAMERA_MAP))
    parser.add_argument("--profile-name", default="offline_main_1600x1200_25fps")
    parser.add_argument("--format", dest="capture_format", default="MJPG")
    parser.add_argument("--fps", type=float, default=25.0)
    args = parser.parse_args()

    data = export_3dmotion_cameras(
        intrinsics_path=Path(args.intrinsics),
        output_path=Path(args.output),
        camera_map=args.camera_map,
        existing_path=Path(args.existing) if args.existing else None,
        profile_name=args.profile_name,
        capture_format=args.capture_format,
        capture_fps=args.fps,
    )
    camera_ids = ", ".join(data["cameras"].keys())
    print(f"wrote {args.output} for cameras: {camera_ids}")


if __name__ == "__main__":
    main()
