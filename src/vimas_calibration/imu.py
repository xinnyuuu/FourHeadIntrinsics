from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

GRAVITY_MPS2 = 9.80665


@dataclass(frozen=True)
class ImuSeries:
    sensor_id: str
    timestamps_ns: np.ndarray
    accel_mps2: np.ndarray
    gyro_radps: np.ndarray


def read_imu_jsonl(path: str | Path) -> ImuSeries:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        record = json.loads(line)
        if not {"timestamp_monotonic_ns", "accel_mps2", "gyro_radps"} <= record.keys():
            raise ValueError(f"{path}:{line_number}: expected timestamp_monotonic_ns, accel_mps2, and gyro_radps")
        records.append(record)
    if not records:
        raise ValueError(f"no IMU samples found in {path}")

    sensor_id = str(records[0].get("sensor_id") or "imu")
    timestamps = np.asarray([int(item["timestamp_monotonic_ns"]) for item in records], dtype=np.int64)
    accel = np.asarray([item["accel_mps2"] for item in records], dtype=np.float64)
    gyro = np.asarray([item["gyro_radps"] for item in records], dtype=np.float64)
    if accel.ndim != 2 or accel.shape[1] != 3:
        raise ValueError("accel_mps2 must contain 3 values per sample")
    if gyro.ndim != 2 or gyro.shape[1] != 3:
        raise ValueError("gyro_radps must contain 3 values per sample")
    return ImuSeries(sensor_id=sensor_id, timestamps_ns=timestamps, accel_mps2=accel, gyro_radps=gyro)


def analyze_imu(series: ImuSeries) -> dict[str, Any]:
    timestamps = series.timestamps_ns
    dt_s = np.diff(timestamps.astype(np.float64)) * 1e-9
    positive_dt = dt_s[dt_s > 0.0]
    accel_norm = np.linalg.norm(series.accel_mps2, axis=1)
    gyro_norm = np.linalg.norm(series.gyro_radps, axis=1)
    duration_s = float((timestamps[-1] - timestamps[0]) * 1e-9) if len(timestamps) > 1 else 0.0
    rate_hz = float(1.0 / np.median(positive_dt)) if positive_dt.size else 0.0
    accel_mean = series.accel_mps2.mean(axis=0)
    gyro_mean = series.gyro_radps.mean(axis=0)
    return {
        "sensor_id": series.sensor_id,
        "sample_count": int(len(timestamps)),
        "duration_s": duration_s,
        "timestamp_monotonic": bool(np.all(np.diff(timestamps) > 0)),
        "dt_s": {
            "median": float(np.median(positive_dt)) if positive_dt.size else None,
            "min": float(np.min(positive_dt)) if positive_dt.size else None,
            "max": float(np.max(positive_dt)) if positive_dt.size else None,
        },
        "sample_rate_hz": rate_hz,
        "accel_mps2": _vector_stats(series.accel_mps2),
        "gyro_radps": _vector_stats(series.gyro_radps),
        "accel_norm_mps2": _scalar_stats(accel_norm),
        "gyro_norm_radps": _scalar_stats(gyro_norm),
        "static_bias_estimate": {
            "accel_mean_mps2": accel_mean,
            "gyro_bias_radps": gyro_mean,
            "gravity_magnitude_error_mps2": float(np.linalg.norm(accel_mean) - GRAVITY_MPS2),
        },
    }


def estimate_noise(series: ImuSeries) -> dict[str, Any]:
    timestamps = series.timestamps_ns.astype(np.float64)
    dt_s = np.diff(timestamps) * 1e-9
    positive_dt = dt_s[dt_s > 0.0]
    sample_rate_hz = float(1.0 / np.median(positive_dt)) if positive_dt.size else 0.0
    accel_std = series.accel_mps2.std(axis=0, ddof=1) if len(series.timestamps_ns) > 1 else np.zeros(3)
    gyro_std = series.gyro_radps.std(axis=0, ddof=1) if len(series.timestamps_ns) > 1 else np.zeros(3)
    # White-noise density approximation for a static segment.
    accel_noise_density = float(np.mean(accel_std) / np.sqrt(sample_rate_hz)) if sample_rate_hz > 0.0 else 0.0
    gyro_noise_density = float(np.mean(gyro_std) / np.sqrt(sample_rate_hz)) if sample_rate_hz > 0.0 else 0.0
    return {
        "accelerometer_noise_density": accel_noise_density,
        "accelerometer_random_walk": accel_noise_density / 10.0,
        "gyroscope_noise_density": gyro_noise_density,
        "gyroscope_random_walk": gyro_noise_density / 10.0,
        "accel_bias_mps2": series.accel_mps2.mean(axis=0),
        "gyro_bias_radps": series.gyro_radps.mean(axis=0),
        "sample_rate_hz": sample_rate_hz,
        "sample_count": int(len(series.timestamps_ns)),
        "note": "First-pass static estimate; replace with Allan variance for production calibration.",
    }


def fit_rotation_from_angular_velocity(
    imu_times_ns: np.ndarray,
    imu_gyro_radps: np.ndarray,
    visual_times_ns: np.ndarray,
    visual_rotations: np.ndarray,
    *,
    min_gyro_norm_radps: float = 0.05,
) -> dict[str, Any]:
    visual_omega = _visual_angular_velocity(visual_times_ns, visual_rotations)
    if visual_omega.shape[0] < 2:
        raise ValueError("need at least three visual pose samples to estimate angular velocity")

    mid_times = visual_times_ns[1:-1].astype(np.float64)
    imu_interp = np.column_stack(
        [np.interp(mid_times, imu_times_ns.astype(np.float64), imu_gyro_radps[:, axis]) for axis in range(3)]
    )
    norms = np.linalg.norm(imu_interp, axis=1)
    mask = norms >= min_gyro_norm_radps
    if int(mask.sum()) < 3:
        raise ValueError("not enough moving samples after gyro threshold")

    rotation = _wahba(imu_interp[mask], visual_omega[mask])
    residuals = visual_omega[mask] - (rotation @ imu_interp[mask].T).T
    return {
        "rotation_matrix": rotation,
        "used_samples": int(mask.sum()),
        "residual_rms_radps": float(np.sqrt(np.mean(np.sum(residuals * residuals, axis=1)))),
        "min_gyro_norm_radps": float(min_gyro_norm_radps),
    }


def read_visual_pose_jsonl(path: str | Path, transform_key: str = "T_H_B") -> tuple[np.ndarray, np.ndarray]:
    times: list[int] = []
    rotations: list[np.ndarray] = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        record = json.loads(line)
        if "timestamp_monotonic_ns" not in record:
            raise ValueError(f"{path}:{line_number}: missing timestamp_monotonic_ns")
        transform = record.get(transform_key)
        if transform is None:
            transform = record.get("matrix4x4") or record.get("transform")
        if transform is None:
            raise ValueError(f"{path}:{line_number}: missing {transform_key}")
        matrix = np.asarray(transform, dtype=np.float64)
        if matrix.shape != (4, 4):
            raise ValueError(f"{path}:{line_number}: {transform_key} must be 4x4")
        times.append(int(record["timestamp_monotonic_ns"]))
        rotations.append(matrix[:3, :3])
    if len(times) < 3:
        raise ValueError("need at least three visual poses")
    return np.asarray(times, dtype=np.int64), np.asarray(rotations, dtype=np.float64)


def _vector_stats(values: np.ndarray) -> dict[str, Any]:
    return {
        "mean": values.mean(axis=0),
        "std": values.std(axis=0, ddof=1) if len(values) > 1 else np.zeros(3),
        "min": values.min(axis=0),
        "max": values.max(axis=0),
    }


def _scalar_stats(values: np.ndarray) -> dict[str, Any]:
    return {
        "mean": float(values.mean()),
        "std": float(values.std(ddof=1)) if len(values) > 1 else 0.0,
        "min": float(values.min()),
        "max": float(values.max()),
    }


def _visual_angular_velocity(times_ns: np.ndarray, rotations: np.ndarray) -> np.ndarray:
    omegas: list[np.ndarray] = []
    for index in range(1, len(rotations) - 1):
        dt = float((times_ns[index + 1] - times_ns[index - 1]) * 1e-9)
        if dt <= 0.0:
            omegas.append(np.zeros(3, dtype=np.float64))
            continue
        delta = rotations[index - 1].T @ rotations[index + 1]
        omega_body = _log_so3(delta) / dt
        omegas.append(omega_body)
    return np.asarray(omegas, dtype=np.float64)


def _log_so3(rotation: np.ndarray) -> np.ndarray:
    cos_theta = float(np.clip((np.trace(rotation) - 1.0) * 0.5, -1.0, 1.0))
    theta = float(np.arccos(cos_theta))
    if theta < 1e-9:
        return np.array(
            [
                0.5 * (rotation[2, 1] - rotation[1, 2]),
                0.5 * (rotation[0, 2] - rotation[2, 0]),
                0.5 * (rotation[1, 0] - rotation[0, 1]),
            ],
            dtype=np.float64,
        )
    scale = theta / (2.0 * np.sin(theta))
    return scale * np.array(
        [rotation[2, 1] - rotation[1, 2], rotation[0, 2] - rotation[2, 0], rotation[1, 0] - rotation[0, 1]],
        dtype=np.float64,
    )


def _wahba(source_vectors: np.ndarray, target_vectors: np.ndarray) -> np.ndarray:
    covariance = target_vectors.T @ source_vectors
    u, _, vt = np.linalg.svd(covariance)
    sign = np.linalg.det(u @ vt)
    correction = np.diag([1.0, 1.0, sign])
    return u @ correction @ vt
