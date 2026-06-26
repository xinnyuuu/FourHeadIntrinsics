#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vimas_calibration.calibration import (
    CalibrationOptions,
    QualityFilter,
    calibrate_charuco,
    calibrate_chessboard,
)
from vimas_calibration.rig import export_four_camera_yaml, load_rig_config


def make_options(
    args: argparse.Namespace,
    camera_key: str,
    images: Path,
    method: str,
    results_root: Path,
) -> CalibrationOptions:
    base = results_root / camera_key / args.experiment / method if args.experiment else results_root / camera_key / method
    return CalibrationOptions(
        images=images,
        output=base / "calibration.yaml",
        processed_dir=base / "processed",
        debug_dir=base / "debug",
        square_size=args.square_size,
        max_error=args.max_error,
        camera_model=args.camera_model,
        auto_filter=args.auto_filter,
        quality_filter=QualityFilter(
            min_sharpness=args.min_sharpness,
            min_contrast=args.min_contrast,
            min_coverage=args.min_coverage,
            min_brightness=args.min_brightness,
            max_brightness=args.max_brightness,
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch-calibrate four independent cameras and export a rig YAML.")
    parser.add_argument("--config", default="configs/four_head_rig.yaml")
    parser.add_argument("--images-root", default="data/images", help="Contains one subfolder per camera key.")
    parser.add_argument("--results-root", default="data/results")
    parser.add_argument("--experiment", help="Experiment name under each camera directory, e.g. main_1600x1200_exp01.")
    parser.add_argument("--method", choices=["chessboard", "charuco"], default="charuco")
    parser.add_argument("--output", default="data/results/four_camera_intrinsics.yaml")
    parser.add_argument("--square-size", type=float, required=True)
    parser.add_argument("--max-error", type=float, default=5.0)
    parser.add_argument(
        "--camera-model",
        choices=["fisheye", "pinhole"],
        default="fisheye",
        help="Intrinsic/distortion model. Use fisheye for 1.4mm 220-240 degree lenses.",
    )
    parser.add_argument("--auto-filter", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--min-sharpness", type=float, default=20.0)
    parser.add_argument("--min-contrast", type=float, default=15.0)
    parser.add_argument("--min-coverage", type=float, default=0.02)
    parser.add_argument("--min-brightness", type=float, default=10.0)
    parser.add_argument("--max-brightness", type=float, default=245.0)
    parser.add_argument("--cols", type=int, default=9, help="Chessboard inner cols or ChArUco square cols.")
    parser.add_argument("--rows", type=int, default=6, help="Chessboard inner rows or ChArUco square rows.")
    parser.add_argument("--marker-ratio", type=float, default=0.72)
    parser.add_argument("--principal-tolerance-px", type=float, default=20.0)
    parser.add_argument("--max-rms-px", type=float, default=5.0)
    parser.add_argument("--max-per-view-px", type=float, default=10.0)
    args = parser.parse_args()

    rig = load_rig_config(args.config)
    images_root = Path(args.images_root)
    results_root = Path(args.results_root)
    calibration_paths: list[Path] = []

    for camera in rig.cameras:
        images = images_root / camera.key / args.experiment if args.experiment else images_root / camera.key
        options = make_options(args, camera.key, images, args.method, results_root)
        print(f"[{camera.key}] calibrating {args.method} from {images}")
        if args.method == "chessboard":
            result = calibrate_chessboard(args.cols, args.rows, options)
        else:
            result = calibrate_charuco(args.cols, args.rows, args.marker_ratio, options)
        calibration_paths.append(options.output)
        cm = result["camera_matrix"]
        print(
            f"[{camera.key}] rms={result['rms_reprojection_error_px']:.4f}px "
            f"fx={cm[0][0]:.2f} fy={cm[1][1]:.2f} cx={cm[0][2]:.2f} cy={cm[1][2]:.2f} "
            f"valid={result['valid_image_count']}"
        )

    export = export_four_camera_yaml(
        rig,
        calibration_paths,
        args.output,
        method_preference=f"{args.camera_model}/{args.method}",
        principal_tolerance_px=args.principal_tolerance_px,
        max_rms_px=args.max_rms_px,
        max_per_view_px=args.max_per_view_px,
    )
    print(f"wrote {args.output}")
    for key, status in export["quality_ledger"].items():
        print(
            f"{key}: {status['status']} rms={status['rms_reprojection_error_px']:.4f}px "
            f"principal_offset={status['principal_offset_px']}"
        )


if __name__ == "__main__":
    main()
