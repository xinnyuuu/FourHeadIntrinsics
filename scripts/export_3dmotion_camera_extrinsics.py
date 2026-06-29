#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vimas_calibration.io import read_yaml, write_yaml


DEFAULT_CAMERA_ID_BY_KEY = {
    "left_side": "C0",
    "left_front": "C1",
    "right_front": "C2",
    "right_side": "C3",
}


def parse_mapping(items: list[str]) -> dict[str, str]:
    mapping = dict(DEFAULT_CAMERA_ID_BY_KEY)
    for item in items:
        if "=" not in item:
            raise SystemExit(f"error: invalid mapping {item!r}; expected camera_key=Cx")
        key, camera_id = item.split("=", 1)
        mapping[key.strip()] = camera_id.strip()
    return mapping


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a 3DMotion configs/cameras.yaml T_H_C snippet from VimasCalibration extrinsics."
    )
    parser.add_argument("--extrinsics", default="camera_extrinsics/four_head_camera_extrinsics.yaml")
    parser.add_argument("--output", default=None, help="Optional output YAML. If omitted, print to stdout.")
    parser.add_argument(
        "--map",
        action="append",
        default=[],
        metavar="camera_key=Cx",
        help="Override camera key to 3DMotion camera id mapping. Can be repeated.",
    )
    args = parser.parse_args()

    mapping = parse_mapping(args.map)
    if not Path(args.extrinsics).exists():
        raise SystemExit(
            f"error: extrinsics file not found: {args.extrinsics}\n"
            "Run align_kalibr_rig_to_head.py first, after Kalibr has generated a multi-camera camchain.yaml."
        )
    raw = read_yaml(args.extrinsics)
    cameras = raw.get("cameras") or {}
    if not cameras:
        raise SystemExit(f"error: no cameras found in {args.extrinsics}")

    snippet: dict[str, Any] = {"cameras": {}}
    missing = []
    for key, camera_id in mapping.items():
        node = cameras.get(key)
        if not node:
            missing.append(key)
            continue
        transform = node.get("T_head_camera") or {}
        matrix = transform.get("matrix4x4")
        if matrix is None:
            missing.append(key)
            continue
        snippet["cameras"][camera_id] = {
            "role": key,
            "T_H_C": matrix,
        }

    if missing:
        raise SystemExit(f"error: missing T_head_camera matrix for: {', '.join(missing)}")

    if args.output:
        write_yaml(args.output, snippet)
        print(f"wrote {args.output}")
    else:
        import yaml

        print(yaml.safe_dump(snippet, sort_keys=False, allow_unicode=True))


if __name__ == "__main__":
    main()
