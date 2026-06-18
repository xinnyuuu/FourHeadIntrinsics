#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fourhead_intrinsics.rig import export_four_camera_yaml, load_rig_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Export four_camera_intrinsics.yaml from existing per-camera results.")
    parser.add_argument("--config", default="configs/four_head_rig.yaml")
    parser.add_argument("--results-root", default="data/results")
    parser.add_argument("--method", default="charuco")
    parser.add_argument("--experiment", help="Experiment name under each camera directory, e.g. main_1600x1200_exp01.")
    parser.add_argument("--output", default="data/results/four_camera_intrinsics.yaml")
    parser.add_argument("--principal-tolerance-px", type=float, default=20.0)
    parser.add_argument("--max-rms-px", type=float, default=5.0)
    parser.add_argument("--max-per-view-px", type=float, default=10.0)
    args = parser.parse_args()

    rig = load_rig_config(args.config)
    if args.experiment:
        paths = [Path(args.results_root) / camera.key / args.experiment / args.method / "calibration.yaml" for camera in rig.cameras]
    else:
        paths = [Path(args.results_root) / camera.key / args.method / "calibration.yaml" for camera in rig.cameras]
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing calibration files: {missing}")

    export_four_camera_yaml(
        rig,
        paths,
        args.output,
        method_preference=args.method,
        principal_tolerance_px=args.principal_tolerance_px,
        max_rms_px=args.max_rms_px,
        max_per_view_px=args.max_per_view_px,
    )
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
