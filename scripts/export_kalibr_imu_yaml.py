#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vimas_calibration.io import write_yaml


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a Kalibr imu.yaml from VimasCalibration IMU noise YAML.")
    parser.add_argument("--imu-noise", required=True, help="YAML containing imus.<sensor-id> noise parameters.")
    parser.add_argument("--sensor-id", default="head_imu")
    parser.add_argument("--output", default="imu_calibration/kalibr_head_imu.yaml")
    parser.add_argument("--topic", default="/imu0")
    parser.add_argument("--rate", type=float, default=None, help="Defaults to sample_rate_hz from the input if present.")
    args = parser.parse_args()

    data = yaml.safe_load(Path(args.imu_noise).read_text(encoding="utf-8")) or {}
    imu = (data.get("imus") or {}).get(args.sensor_id)
    if not imu:
        raise SystemExit(f"error: no imus.{args.sensor_id} entry in {args.imu_noise}")
    rate = float(args.rate if args.rate is not None else imu.get("sample_rate_hz", 100.0))
    out = {
        "imu0": {
            "rostopic": args.topic,
            "update_rate": rate,
            "accelerometer_noise_density": float(imu["accelerometer_noise_density"]),
            "accelerometer_random_walk": float(imu["accelerometer_random_walk"]),
            "gyroscope_noise_density": float(imu["gyroscope_noise_density"]),
            "gyroscope_random_walk": float(imu["gyroscope_random_walk"]),
            "model": "kalibr",
        }
    }
    write_yaml(args.output, out)
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
