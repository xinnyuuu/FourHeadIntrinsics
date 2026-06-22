#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import yaml


def main() -> None:
    parser = argparse.ArgumentParser(description="Update a Kalibr AprilGrid target YAML from printed measurements.")
    parser.add_argument("--target-yaml", required=True)
    parser.add_argument("--tag-size-mm", type=float, required=True, help="Measured black tag edge length in millimeters.")
    parser.add_argument("--gap-mm", type=float, required=True, help="Measured white gap between adjacent tags in millimeters.")
    args = parser.parse_args()

    if args.tag_size_mm <= 0:
        raise SystemExit("error: --tag-size-mm must be positive")
    if args.gap_mm < 0:
        raise SystemExit("error: --gap-mm must be non-negative")

    path = Path(args.target_yaml)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if data.get("target_type") != "aprilgrid":
        raise SystemExit(f"error: not an aprilgrid target: {path}")

    data["tagSize"] = args.tag_size_mm / 1000.0
    data["tagSpacing"] = args.gap_mm / args.tag_size_mm
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")

    print(f"updated {path}")
    print(f"tagSize: {data['tagSize']:.9g} m")
    print(f"tagSpacing: {data['tagSpacing']:.9g}  # gap / tag_size")


if __name__ == "__main__":
    main()
