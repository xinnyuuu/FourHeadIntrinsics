#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vimas_calibration.io import write_yaml


def parse_vec3(value: str, name: str) -> list[float]:
    parts = [float(item.strip()) for item in value.split(",") if item.strip()]
    if len(parts) != 3:
        raise SystemExit(f"error: {name} must contain three comma-separated values")
    return parts


def main() -> None:
    parser = argparse.ArgumentParser(description="Export IMU extrinsics template for VIMAS head and wrist frames.")
    parser.add_argument("--output", default="imu_calibration/imu_extrinsics.yaml")
    parser.add_argument("--head-translation", default="0,0,0", help="T_H_IH translation in meters.")
    parser.add_argument("--wrist-translation", default="0,0,0", help="T_B_IB translation in meters.")
    args = parser.parse_args()

    identity = np.eye(3, dtype=float).tolist()
    data = {
        "frames": {
            "head": {
                "T_H_IH": {
                    "rotation_matrix": identity,
                    "translation_m": parse_vec3(args.head_translation, "--head-translation"),
                    "note": "P3a may temporarily use identity by setting H := I_H.",
                }
            },
            "wrist": {
                "T_B_IB": {
                    "rotation_matrix": identity,
                    "translation_m": parse_vec3(args.wrist_translation, "--wrist-translation"),
                    "note": "Replace rotation with visual/gyro fit and translation with CAD or physical measurement.",
                }
            },
        }
    }
    write_yaml(args.output, data)
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
