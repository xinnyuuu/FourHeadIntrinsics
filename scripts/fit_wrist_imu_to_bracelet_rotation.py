#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vimas_calibration.imu import fit_rotation_from_angular_velocity, read_imu_jsonl, read_visual_pose_jsonl
from vimas_calibration.io import write_yaml


def parse_vec3(value: str) -> list[float]:
    parts = [float(item.strip()) for item in value.split(",") if item.strip()]
    if len(parts) != 3:
        raise SystemExit("error: --translation must contain three comma-separated values")
    return parts


def main() -> None:
    parser = argparse.ArgumentParser(description="Fit wrist IMU-to-wristband rotation from gyro and visual T_H_B poses.")
    parser.add_argument("--wrist-imu", required=True, help="wrist_imu.jsonl.")
    parser.add_argument("--wrist-visual", required=True, help="wrist_visual_pose.jsonl containing T_H_B.")
    parser.add_argument("--transform-key", default="T_H_B")
    parser.add_argument("--translation", default="0,0,0", help="T_B_IB translation from CAD/measurement, meters.")
    parser.add_argument("--min-gyro-norm-radps", type=float, default=0.05)
    parser.add_argument("--output", default="imu_calibration/wrist_imu_extrinsics.yaml")
    args = parser.parse_args()

    imu = read_imu_jsonl(args.wrist_imu)
    visual_times, visual_rotations = read_visual_pose_jsonl(args.wrist_visual, args.transform_key)
    fit = fit_rotation_from_angular_velocity(
        imu.timestamps_ns,
        imu.gyro_radps,
        visual_times,
        visual_rotations,
        min_gyro_norm_radps=args.min_gyro_norm_radps,
    )
    data = {
        "frames": {
            "wrist": {
                "T_B_IB": {
                    "rotation_matrix": fit["rotation_matrix"],
                    "translation_m": parse_vec3(args.translation),
                }
            }
        },
        "fit": {
            "used_samples": fit["used_samples"],
            "residual_rms_radps": fit["residual_rms_radps"],
            "min_gyro_norm_radps": fit["min_gyro_norm_radps"],
            "source": {
                "wrist_imu": args.wrist_imu,
                "wrist_visual": args.wrist_visual,
                "transform_key": args.transform_key,
            },
        },
    }
    write_yaml(args.output, data)
    print(f"wrote {args.output}")
    print(f"used_samples: {fit['used_samples']}")
    print(f"residual_rms_radps: {fit['residual_rms_radps']:.6f}")


if __name__ == "__main__":
    main()
