#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vimas_calibration.imu import analyze_imu, read_imu_jsonl
from vimas_calibration.io import write_yaml


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze a 3DMotion IMU JSONL file.")
    parser.add_argument("imu_jsonl", help="Input JSONL with timestamp_monotonic_ns, accel_mps2, gyro_radps.")
    parser.add_argument("--output", help="Optional YAML output path.")
    args = parser.parse_args()

    series = read_imu_jsonl(args.imu_jsonl)
    summary = analyze_imu(series)
    if args.output:
        write_yaml(args.output, summary)
        print(f"wrote {args.output}")
    else:
        import yaml

        print(yaml.safe_dump(summary, sort_keys=False, allow_unicode=True))


if __name__ == "__main__":
    main()
