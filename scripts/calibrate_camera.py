#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fourhead_intrinsics.calibration import (
    CalibrationOptions,
    QualityFilter,
    calibrate_charuco,
    calibrate_chessboard,
)


def make_options(args: argparse.Namespace) -> CalibrationOptions:
    paths = resolve_paths(args)
    return CalibrationOptions(
        images=paths["images"],
        output=paths["output"],
        processed_dir=paths["processed_dir"],
        debug_dir=paths["debug_dir"],
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


def resolve_paths(args: argparse.Namespace) -> dict[str, Path]:
    if args.camera and args.experiment:
        image_dir = Path(args.images) if args.images else Path(args.images_root) / args.camera / args.experiment
        result_base = Path(args.results_root) / args.camera / args.experiment / args.method
        return {
            "images": image_dir,
            "output": Path(args.output) if args.output else result_base / "calibration.yaml",
            "processed_dir": Path(args.processed_dir) if args.processed_dir else result_base / "processed",
            "debug_dir": Path(args.debug_dir) if args.debug_dir else result_base / "debug",
        }

    required = {
        "--images": args.images,
        "--output": args.output,
        "--processed-dir": args.processed_dir,
        "--debug-dir": args.debug_dir,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise SystemExit(
            "Missing required path arguments: "
            + ", ".join(missing)
            + ". Pass them explicitly, or pass both --camera and --experiment."
        )
    return {
        "images": Path(args.images),
        "output": Path(args.output),
        "processed_dir": Path(args.processed_dir),
        "debug_dir": Path(args.debug_dir),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate one camera from saved images.")
    parser.add_argument("--method", choices=["chessboard", "charuco"], required=True)
    parser.add_argument("--images", help="Input image folder. Overrides --camera/--experiment derived image path.")
    parser.add_argument("--output", help="Output calibration YAML. Overrides derived result path.")
    parser.add_argument("--processed-dir", help="Processed accepted/rejected image directory. Overrides derived path.")
    parser.add_argument("--debug-dir", help="Debug image directory. Overrides derived path.")
    parser.add_argument("--camera", help="Camera key such as left_side, left_front, right_front, right_side.")
    parser.add_argument("--experiment", help="Experiment/run name such as exp01 or 20260618_left_side_v2.")
    parser.add_argument("--images-root", default="data/images")
    parser.add_argument("--results-root", default="data/results")
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
    args = parser.parse_args()

    options = make_options(args)
    try:
        if args.method == "chessboard":
            result = calibrate_chessboard(args.cols, args.rows, options)
        else:
            result = calibrate_charuco(args.cols, args.rows, args.marker_ratio, options)
    except (FileNotFoundError, RuntimeError) as exc:
        raise SystemExit(f"error: {exc}") from exc

    cm = result["camera_matrix"]
    summary = result["per_view_error_summary"]
    print(f"valid images: {result['valid_image_count']}")
    print(f"RMS reprojection error: {result['rms_reprojection_error_px']:.4f} px")
    print(f"mean/median/max per-view error: {summary['mean_px']:.4f}/{summary['median_px']:.4f}/{summary['max_px']:.4f} px")
    print(f"fx={cm[0][0]:.3f}, fy={cm[1][1]:.3f}, cx={cm[0][2]:.3f}, cy={cm[1][2]:.3f}")
    print(f"wrote {options.output}")


if __name__ == "__main__":
    main()
