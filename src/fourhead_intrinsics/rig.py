from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .io import load_calibration, read_yaml, write_yaml


DEFAULT_CAMERA_NAMES = [
    "cam_left_side",
    "cam_left_front",
    "cam_right_front",
    "cam_right_side",
]


@dataclass(frozen=True)
class RigCamera:
    key: str
    label: str
    source: str
    role: str


@dataclass(frozen=True)
class RigConfig:
    image_size: tuple[int, int]
    width: int
    height: int
    fps: float
    fourcc: str
    cameras: list[RigCamera]


def load_rig_config(path: str | Path) -> RigConfig:
    raw = read_yaml(path)
    capture = raw.get("capture", {})
    width = int(capture.get("width", raw.get("image_size", [0, 0])[0]))
    height = int(capture.get("height", raw.get("image_size", [0, 0])[1]))
    fps = float(capture.get("fps", 0.0))
    fourcc = str(capture.get("fourcc", "MJPG"))
    cameras = [
        RigCamera(
            key=str(item["key"]),
            label=str(item.get("label", item["key"])),
            source=str(item.get("source", "")),
            role=str(item.get("role", item.get("label", item["key"]))),
        )
        for item in raw.get("cameras", [])
    ]
    return RigConfig(
        image_size=(width, height),
        width=width,
        height=height,
        fps=fps,
        fourcc=fourcc,
        cameras=cameras,
    )


def camera_output_key(index: int, camera: RigCamera) -> str:
    return f"camera_{index}_{camera.key}"


def quality_status(
    result: dict[str, Any],
    principal_tolerance_px: float,
    max_rms_px: float,
    max_per_view_px: float,
) -> dict[str, Any]:
    width, height = result["image_size"]
    camera_matrix = result["camera_matrix"]
    fx = float(camera_matrix[0][0])
    fy = float(camera_matrix[1][1])
    cx = float(camera_matrix[0][2])
    cy = float(camera_matrix[1][2])
    rms = float(result["rms_reprojection_error_px"])
    max_view = float(result["per_view_error_summary"]["max_px"])
    center_x = float(width) / 2.0
    center_y = float(height) / 2.0
    checks = {
        "rms_ok": rms <= max_rms_px,
        "max_per_view_ok": max_view <= max_per_view_px,
        "principal_x_ok": abs(cx - center_x) <= principal_tolerance_px,
        "principal_y_ok": abs(cy - center_y) <= principal_tolerance_px,
    }
    return {
        "status": "pass" if all(checks.values()) else "review",
        "checks": checks,
        "fx": fx,
        "fy": fy,
        "cx": cx,
        "cy": cy,
        "center_expected": [center_x, center_y],
        "principal_offset_px": [cx - center_x, cy - center_y],
        "rms_reprojection_error_px": rms,
        "max_per_view_error_px": max_view,
    }


def export_four_camera_yaml(
    rig: RigConfig,
    calibration_paths: list[Path],
    output: str | Path,
    method_preference: str = "best_available",
    principal_tolerance_px: float = 20.0,
    max_rms_px: float = 5.0,
    max_per_view_px: float = 10.0,
) -> dict[str, Any]:
    cameras: dict[str, Any] = {}
    ledger: dict[str, Any] = {}
    image_size: list[int] | None = None
    distortion_models: set[str] = set()
    camera_models: set[str] = set()

    for idx, (camera, path) in enumerate(zip(rig.cameras, calibration_paths)):
        result = load_calibration(path)
        result["camera_matrix"] = result["camera_matrix"].tolist()
        result["dist_coeffs"] = result["dist_coeffs"].reshape(-1).tolist()
        image_size = result["image_size"]
        camera_model = str(result.get("camera_model", "pinhole"))
        distortion_model = str(result.get("distortion_model", "plumb_bob"))
        camera_models.add(camera_model)
        distortion_models.add(distortion_model)
        key = camera_output_key(idx, camera)
        cameras[key] = {
            "label": camera.label,
            "role": camera.role,
            "source": camera.source,
            "method": result["method"],
            "camera_model": camera_model,
            "distortion_model": distortion_model,
            "camera_matrix": result["camera_matrix"],
            "dist_coeffs": result["dist_coeffs"],
        }
        ledger[key] = {
            "calibration_file": str(path),
            "valid_image_count": result["valid_image_count"],
            "method": result["method"],
            "camera_model": camera_model,
            "distortion_model": distortion_model,
            **quality_status(result, principal_tolerance_px, max_rms_px, max_per_view_px),
        }

    data = {
        "setting": {
            "image_size": image_size or list(rig.image_size),
            "camera_model": next(iter(camera_models)) if len(camera_models) == 1 else "mixed",
            "distortion_model": next(iter(distortion_models)) if len(distortion_models) == 1 else "mixed",
            "method_preference": method_preference,
        },
        **cameras,
        "quality_ledger": ledger,
    }
    write_yaml(output, data)
    return data
