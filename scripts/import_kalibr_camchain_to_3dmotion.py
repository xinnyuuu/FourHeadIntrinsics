#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fourhead_intrinsics.io import read_yaml, write_yaml


DEFAULT_CAMERA_MAP = "cam0:C0:left_ear,cam1:C1:front_left,cam2:C2:front_right,cam3:C3:right_ear"


def parse_camera_map(value: str) -> dict[str, tuple[str, str]]:
    mapping: dict[str, tuple[str, str]] = {}
    for item in value.split(","):
        parts = [part.strip() for part in item.split(":")]
        if len(parts) != 3 or not all(parts):
            raise argparse.ArgumentTypeError("Camera map entries must be kalibr_cam:3dmotion_id:role.")
        mapping[parts[0]] = (parts[1], parts[2])
    return mapping


def import_camchain(
    camchain_path: Path,
    output_path: Path,
    camera_map: dict[str, tuple[str, str]],
    existing_path: Path | None,
    profile_name: str,
    capture_format: str,
    capture_fps: float,
) -> dict[str, Any]:
    camchain = _read_kalibr_yaml(camchain_path)
    existing = read_yaml(existing_path) if existing_path and existing_path.exists() else {}
    existing_cameras = existing.get("cameras", {})
    cameras: dict[str, Any] = {}
    profile_image_size: list[int] | None = None

    for kalibr_key, (camera_id, role) in camera_map.items():
        if kalibr_key not in camchain:
            raise RuntimeError(f"Missing {kalibr_key!r} in {camchain_path}.")
        raw = camchain[kalibr_key]
        resolution = [int(v) for v in raw.get("resolution", [])]
        if len(resolution) != 2:
            raise RuntimeError(f"Missing/invalid resolution for {kalibr_key}.")
        profile_image_size = profile_image_size or resolution
        model = str(raw.get("camera_model", "unknown"))
        distortion_model = str(raw.get("distortion_model", "none"))
        intrinsics = [float(v) for v in raw.get("intrinsics", [])]
        distortion = [float(v) for v in raw.get("distortion_coeffs", [])]
        existing_camera = existing_cameras.get(camera_id, {})
        cameras[camera_id] = {
            "role": role,
            "source_calibration": kalibr_key,
            "image_size": resolution,
            "camera_model": _runtime_camera_model(model, distortion_model),
            "distortion_model": _runtime_distortion_model(model, distortion_model),
            "projection_model": model,
            "projection_parameters": intrinsics,
            "intrinsics": _camera_matrix_from_kalibr(model, intrinsics),
            "distortion": distortion,
            "kalibr": {
                "camera_model": model,
                "distortion_model": distortion_model,
                "intrinsics": intrinsics,
                "distortion_coeffs": distortion,
                "rostopic": raw.get("rostopic"),
                "T_cn_cnm1": raw.get("T_cn_cnm1"),
            },
            "T_H_C": existing_camera.get("T_H_C"),
        }

    data = {
        "profile": {
            "name": profile_name,
            "format": capture_format,
            "fps": capture_fps,
            "image_size": profile_image_size,
            "source": str(camchain_path),
            "note": "Kalibr DS/EUCM/omni models are preserved here. Current 3D Motion AprilTag/OpenVINS code directly consumes only pinhole/radtan and fisheye/equidistant.",
        },
        "camera_defaults": {
            "image_size": profile_image_size,
        },
        "cameras": dict(sorted(cameras.items())),
    }
    write_yaml(output_path, data)
    return data


def _read_kalibr_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if text.startswith("%YAML:"):
        text = "\n".join(text.splitlines()[1:])
    return yaml.safe_load(text) or {}


def _camera_matrix_from_kalibr(model: str, intrinsics: list[float]) -> list[list[float]]:
    fx, fy, cx, cy = _fx_fy_cx_cy(model, intrinsics)
    return [[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]]


def _fx_fy_cx_cy(model: str, intrinsics: list[float]) -> tuple[float, float, float, float]:
    if model in {"ds", "eucm"} and len(intrinsics) >= 6:
        return intrinsics[-4], intrinsics[-3], intrinsics[-2], intrinsics[-1]
    if model == "omni" and len(intrinsics) >= 5:
        return intrinsics[-4], intrinsics[-3], intrinsics[-2], intrinsics[-1]
    if model == "pinhole" and len(intrinsics) >= 4:
        return intrinsics[0], intrinsics[1], intrinsics[2], intrinsics[3]
    raise RuntimeError(f"Cannot derive fx/fy/cx/cy from camera_model={model!r} intrinsics={intrinsics!r}.")


def _runtime_camera_model(model: str, distortion_model: str) -> str:
    if model == "pinhole" and distortion_model == "equidistant":
        return "fisheye"
    if model == "pinhole":
        return "pinhole"
    return "kalibr"


def _runtime_distortion_model(model: str, distortion_model: str) -> str:
    if model == "pinhole" and distortion_model == "equidistant":
        return "equidistant"
    if model == "pinhole" and distortion_model == "radtan":
        return "radtan"
    return distortion_model


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a Kalibr camchain YAML into 3D Motion cameras.yaml.")
    parser.add_argument("--camchain", required=True)
    parser.add_argument("--output", default="../3DMotion/configs/cameras.yaml")
    parser.add_argument("--existing", default="../3DMotion/configs/cameras.yaml", help="Existing 3D Motion cameras YAML used to preserve T_H_C.")
    parser.add_argument("--camera-map", type=parse_camera_map, default=parse_camera_map(DEFAULT_CAMERA_MAP))
    parser.add_argument("--profile-name", default="kalibr_main_1600x1200_25fps")
    parser.add_argument("--format", dest="capture_format", default="MJPG")
    parser.add_argument("--fps", type=float, default=25.0)
    args = parser.parse_args()

    data = import_camchain(
        camchain_path=Path(args.camchain),
        output_path=Path(args.output),
        camera_map=args.camera_map,
        existing_path=Path(args.existing) if args.existing else None,
        profile_name=args.profile_name,
        capture_format=args.capture_format,
        capture_fps=args.fps,
    )
    print(f"wrote {args.output} for cameras: {', '.join(data['cameras'])}")


if __name__ == "__main__":
    main()
