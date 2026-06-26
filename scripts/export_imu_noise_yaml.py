#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vimas_calibration.imu import estimate_noise, read_imu_jsonl
from vimas_calibration.io import write_yaml


def main() -> None:
    parser = argparse.ArgumentParser(description="Export first-pass IMU noise and bias YAML from static JSONL data.")
    parser.add_argument("--head-imu", help="Static head_imu JSONL.")
    parser.add_argument("--wrist-imu", help="Static wrist_imu JSONL.")
    parser.add_argument("--output", default="imu_calibration/imu_noise.yaml")
    args = parser.parse_args()

    if not args.head_imu and not args.wrist_imu:
        raise SystemExit("error: provide --head-imu and/or --wrist-imu")

    imus = {}
    if args.head_imu:
        imus["head_imu"] = estimate_noise(read_imu_jsonl(args.head_imu))
    if args.wrist_imu:
        imus["wrist_imu"] = estimate_noise(read_imu_jsonl(args.wrist_imu))

    data = {
        "imus": imus,
        "source": {
            "head_imu": args.head_imu,
            "wrist_imu": args.wrist_imu,
            "method": "static first-pass standard deviation estimate",
        },
    }
    write_yaml(args.output, data)
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
