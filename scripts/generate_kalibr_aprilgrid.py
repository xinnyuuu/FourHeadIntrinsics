#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fourhead_intrinsics.io import write_yaml


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a Kalibr AprilGrid target YAML.")
    parser.add_argument("--tag-cols", type=int, default=6)
    parser.add_argument("--tag-rows", type=int, default=6)
    parser.add_argument("--tag-size-m", type=float, default=0.088)
    parser.add_argument("--tag-spacing", type=float, default=0.3, help="Spacing ratio: gap / tag size.")
    parser.add_argument("--output", default="data/targets/aprilgrid_6x6_088.yaml")
    args = parser.parse_args()

    data = {
        "target_type": "aprilgrid",
        "tagCols": args.tag_cols,
        "tagRows": args.tag_rows,
        "tagSize": args.tag_size_m,
        "tagSpacing": args.tag_spacing,
    }
    write_yaml(args.output, data)
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
