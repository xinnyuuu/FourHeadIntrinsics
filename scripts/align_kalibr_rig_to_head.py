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


def transform_to_yaml(transform: np.ndarray) -> dict[str, Any]:
    return {
        "rotation_matrix": transform[:3, :3],
        "translation_m": transform[:3, 3],
        "matrix4x4": transform,
    }


def load_kalibr_cam0_transforms(camchain_path: str | Path) -> dict[int, np.ndarray]:
    path = Path(camchain_path)
    if not path.exists():
        raise SystemExit(
            f"error: camchain not found: {path}\n"
            "Run Kalibr multi-camera calibration first. Expected flow:\n"
            "  1. python3 /data/scripts/images_to_multicam_rosbag.py ...\n"
            "  2. rosrun kalibr kalibr_calibrate_cameras ...\n"
            "  3. copy/use the generated *-camchain.yaml with this script."
        )
    camchain = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    kalibr_keys = sorted((key for key in camchain if CAMERA_RE.match(key)), key=camera_index)
    if not kalibr_keys:
        raise SystemExit(f"error: no camN entries found in {camchain_path}")

    transforms: dict[int, np.ndarray] = {0: np.eye(4, dtype=np.float64)}
    for index in range(1, len(kalibr_keys)):
        key = f"cam{index}"
        if key not in camchain:
            raise SystemExit(f"error: expected contiguous camera key {key}")
        if "T_cn_cnm1" not in camchain[key]:
            raise SystemExit(f"error: {key} has no T_cn_cnm1")
        t_cam_current_cam_previous = as_transform(camchain[key]["T_cn_cnm1"], f"{key}.T_cn_cnm1")
        t_cam_previous_cam_current = invert_transform(t_cam_current_cam_previous)
        transforms[index] = transforms[index - 1] @ t_cam_previous_cam_current
    return transforms


def load_measured_centers(path: str | Path) -> dict[str, np.ndarray]:
    raw = read_yaml(path)
    centers = raw.get("camera_centers_H", {})
    if not centers:
        raise SystemExit(f"error: no camera_centers_H entries in {path}")
    result: dict[str, np.ndarray] = {}
    for key, item in centers.items():
        value = np.asarray(item["translation_m"], dtype=np.float64)
        if value.shape != (3,):
            raise SystemExit(f"error: {key}.translation_m must have 3 values")
        result[str(key)] = value
    return result


def fit_rigid_transform(source_points: np.ndarray, target_points: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if source_points.shape != target_points.shape or source_points.shape[1] != 3:
        raise SystemExit("error: source and target point arrays must both be Nx3")
    if source_points.shape[0] < 3:
        raise SystemExit("error: at least three measured camera centers are required")
    if np.linalg.matrix_rank(source_points - source_points.mean(axis=0), tol=1e-9) < 2:
        raise SystemExit("error: Kalibr camera centers are degenerate; need at least three non-collinear centers")
    if np.linalg.matrix_rank(target_points - target_points.mean(axis=0), tol=1e-9) < 2:
        raise SystemExit("error: measured camera centers are degenerate; need at least three non-collinear centers")

    source_centroid = source_points.mean(axis=0)
    target_centroid = target_points.mean(axis=0)
    source_centered = source_points - source_centroid
    target_centered = target_points - target_centroid
    covariance = source_centered.T @ target_centered
    u, _, vt = np.linalg.svd(covariance)
    rotation = vt.T @ u.T
    if np.linalg.det(rotation) < 0.0:
        vt[-1, :] *= -1.0
        rotation = vt.T @ u.T
    translation = target_centroid - rotation @ source_centroid
    residuals = (rotation @ source_points.T).T + translation - target_points
    return rotation, translation, residuals


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Align a Kalibr multi-camera rig to the user-defined Head frame using measured camera centers."
    )
    parser.add_argument("--camchain", required=True, help="Kalibr multi-camera camchain.yaml.")
    parser.add_argument("--manual-centers", default="camera_extrinsics/manual_camera_centers.yaml")
    parser.add_argument("--config", default="configs/four_head_rig.yaml", help="Maps cam0..camN to rig camera keys.")
    parser.add_argument("--output", default="camera_extrinsics/four_head_camera_extrinsics.yaml")
    parser.add_argument("--warn-rms-residual-m", type=float, default=0.010)
    parser.add_argument("--fail-rms-residual-m", type=float, default=None)
    args = parser.parse_args()

    rig = load_rig_config(args.config)
    t_cam0_camera = load_kalibr_cam0_transforms(args.camchain)
    measured_centers = load_measured_centers(args.manual_centers)

    source_points: list[np.ndarray] = []
    target_points: list[np.ndarray] = []
    used: list[tuple[int, str]] = []
    for index, camera in enumerate(rig.cameras):
        if index not in t_cam0_camera or camera.key not in measured_centers:
            continue
        source_points.append(t_cam0_camera[index][:3, 3])
        target_points.append(measured_centers[camera.key])
        used.append((index, camera.key))

    if len(used) < 3:
        available = ", ".join(measured_centers)
        raise SystemExit(f"error: need at least 3 matched camera centers; matched {len(used)}; available: {available}")

    rotation, translation, residuals = fit_rigid_transform(np.vstack(source_points), np.vstack(target_points))
    t_head_cam0 = np.eye(4, dtype=np.float64)
    t_head_cam0[:3, :3] = rotation
    t_head_cam0[:3, 3] = translation

    cameras: dict[str, Any] = {}
    residual_report: dict[str, Any] = {}
    for residual, (index, key) in zip(residuals, used):
        residual_report[key] = {
            "residual_m": residual,
            "residual_norm_m": float(np.linalg.norm(residual)),
            "kalibr_camera": f"cam{index}",
        }

    for index, camera in enumerate(rig.cameras):
        if index not in t_cam0_camera:
            continue
        t_head_camera = t_head_cam0 @ t_cam0_camera[index]
        cameras[camera.key] = {
            "role": camera.role,
            "source": camera.source,
            "kalibr_camera": f"cam{index}",
            "T_head_camera": transform_to_yaml(t_head_camera),
        }

    rms_residual = float(np.sqrt(np.mean(np.sum(residuals * residuals, axis=1))))
    max_residual = float(np.max(np.linalg.norm(residuals, axis=1)))
    data = {
        "source": {
            "camchain": str(args.camchain),
            "manual_centers": str(args.manual_centers),
            "config": str(args.config),
            "method": "least_squares_rigid_alignment_from_kalibr_camera_centers_to_measured_head_centers",
            "kalibr_convention": "T_cn_cnm1 maps points from cam(n-1) frame into cam(n) frame.",
        },
        "head_frame": {
            "name": "head",
            "units": "meters",
            "T_head_cam0": transform_to_yaml(t_head_cam0),
        },
        "alignment": {
            "matched_camera_count": len(used),
            "matched_cameras": [key for _, key in used],
            "rms_residual_m": rms_residual,
            "max_residual_m": max_residual,
            "residuals": residual_report,
        },
        "cameras": cameras,
    }
    write_yaml(args.output, data)
    print(f"wrote {args.output}")
    print(f"matched cameras: {', '.join(key for _, key in used)}")
    print(f"rms residual: {rms_residual:.6f} m")
    print(f"max residual: {max_residual:.6f} m")
    if args.warn_rms_residual_m is not None and rms_residual > args.warn_rms_residual_m:
        print(f"warning: RMS residual exceeds {args.warn_rms_residual_m:.3f} m; re-check camera order and hand measurements")
    if args.fail_rms_residual_m is not None and rms_residual > args.fail_rms_residual_m:
        raise SystemExit(f"error: RMS residual exceeds {args.fail_rms_residual_m:.3f} m")


if __name__ == "__main__":
    main()
