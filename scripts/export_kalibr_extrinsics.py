#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vimas_calibration.io import read_yaml, write_yaml
from vimas_calibration.rig import load_rig_config


CAMERA_RE = re.compile(r"^cam(?P<index>\d+)$")


def camera_index(key: str) -> int:
    match = CAMERA_RE.match(key)
    if not match:
        raise ValueError(f"invalid Kalibr camera key: {key}")
    return int(match.group("index"))


def as_transform(value: Any, name: str) -> np.ndarray:
    matrix = np.asarray(value, dtype=np.float64)
    if matrix.shape != (4, 4):
        raise SystemExit(f"error: {name} must be a 4x4 matrix")
    return matrix


def invert_transform(transform: np.ndarray) -> np.ndarray:
    rotation = transform[:3, :3]
    translation = transform[:3, 3]
    inverse = np.eye(4, dtype=np.float64)
    inverse[:3, :3] = rotation.T
    inverse[:3, 3] = -rotation.T @ translation
    return inverse


def load_t_head_cam0(path: str | None) -> np.ndarray:
    if path is None:
        return np.eye(4, dtype=np.float64)
    data = read_yaml(path)
    node = data.get("T_head_camera", data)
    rotation = np.asarray(node["rotation_matrix"], dtype=np.float64)
    translation = np.asarray(node["translation_m"], dtype=np.float64)
    if rotation.shape != (3, 3):
        raise SystemExit("error: rotation_matrix in --t-head-cam0 must be 3x3")
    if translation.shape != (3,):
        raise SystemExit("error: translation_m in --t-head-cam0 must have 3 values")
    transform = np.eye(4, dtype=np.float64)
    transform[:3, :3] = rotation
    transform[:3, 3] = translation
    return transform


def transform_to_yaml(transform: np.ndarray) -> dict[str, Any]:
    return {
        "rotation_matrix": transform[:3, :3],
        "translation_m": transform[:3, 3],
        "matrix4x4": transform,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export T_head_camera from a Kalibr multi-camera camchain.yaml.")
    parser.add_argument("--camchain", required=True, help="Kalibr multi-camera camchain.yaml.")
    parser.add_argument("--config", default="configs/four_head_rig.yaml", help="Maps cam0..camN to rig camera keys.")
    parser.add_argument("--output", default="camera_extrinsics/four_head_camera_extrinsics.yaml")
    parser.add_argument(
        "--t-head-cam0",
        default=None,
        help="Optional YAML containing T_head_camera for Kalibr cam0. Defaults to identity, so Head frame equals cam0.",
    )
    args = parser.parse_args()

    camchain = yaml.safe_load(Path(args.camchain).read_text(encoding="utf-8")) or {}
    rig = load_rig_config(args.config)
    kalibr_keys = sorted((key for key in camchain if CAMERA_RE.match(key)), key=camera_index)
    if not kalibr_keys:
        raise SystemExit(f"error: no camN entries found in {args.camchain}")
    if len(kalibr_keys) > len(rig.cameras):
        raise SystemExit(f"error: camchain has {len(kalibr_keys)} cameras but config has {len(rig.cameras)}")

    t_head_cam0 = load_t_head_cam0(args.t_head_cam0)
    t_cam0_cam: dict[int, np.ndarray] = {0: np.eye(4, dtype=np.float64)}

    for index in range(1, len(kalibr_keys)):
        key = f"cam{index}"
        previous_key = f"cam{index - 1}"
        if key not in camchain:
            raise SystemExit(f"error: expected contiguous camera key {key}")
        if "T_cn_cnm1" not in camchain[key]:
            raise SystemExit(f"error: {key} has no T_cn_cnm1; run Kalibr with overlapping multi-camera observations")
        t_cam_current_cam_previous = as_transform(camchain[key]["T_cn_cnm1"], f"{key}.T_cn_cnm1")
        t_cam_previous_cam_current = invert_transform(t_cam_current_cam_previous)
        t_cam0_cam[index] = t_cam0_cam[index - 1] @ t_cam_previous_cam_current
        if previous_key not in camchain:
            raise SystemExit(f"error: expected contiguous camera key {previous_key}")

    cameras: dict[str, Any] = {}
    for index, key in enumerate(kalibr_keys):
        rig_camera = rig.cameras[index]
        t_head_camera = t_head_cam0 @ t_cam0_cam[index]
        cameras[rig_camera.key] = {
            "role": rig_camera.role,
            "kalibr_camera": key,
            "T_head_camera": transform_to_yaml(t_head_camera),
        }

    data = {
        "source": {
            "camchain": str(args.camchain),
            "config": str(args.config),
            "kalibr_convention": "T_cn_cnm1 maps points from cam(n-1) frame into cam(n) frame.",
            "head_frame": "T_head_cam0 from --t-head-cam0, or identity if omitted.",
        },
        "head_frame": {
            "name": "head",
            "units": "meters",
        },
        "cameras": cameras,
    }
    write_yaml(args.output, data)
    print(f"wrote {args.output}")
    print(f"cameras: {', '.join(cameras)}")


if __name__ == "__main__":
    main()
