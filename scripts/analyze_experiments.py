#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import cv2
import numpy as np

from fourhead_intrinsics.io import list_images, load_calibration, write_side_by_side


FLOAT_COLUMNS = {
    "rms_px",
    "mean_view_px",
    "median_view_px",
    "max_view_px",
    "fx",
    "fy",
    "cx",
    "cy",
    "d1",
    "d2",
    "d3",
    "d4",
    "d5",
}


def calibration_path(results_root: Path, camera: str, experiment: str, method: str) -> Path:
    return results_root / camera / experiment / method / "calibration.yaml"


def image_dir(images_root: Path, camera: str, experiment: str) -> Path:
    return images_root / camera / experiment


def discover_experiments(results_root: Path, camera: str, method: str) -> list[str]:
    camera_root = results_root / camera
    if not camera_root.exists():
        return []
    experiments = []
    for item in sorted(camera_root.iterdir()):
        if item.is_dir() and (item / method / "calibration.yaml").exists():
            experiments.append(item.name)
    return experiments


def row_from_calibration(path: Path, experiment: str) -> dict[str, object]:
    calib = load_calibration(path)
    matrix = calib["camera_matrix"]
    dist = calib["dist_coeffs"].reshape(-1)
    padded = np.full(5, np.nan, dtype=np.float64)
    padded[: min(5, len(dist))] = dist[:5]
    summary = calib.get("per_view_error_summary", {})
    return {
        "experiment": experiment,
        "method": calib.get("method", "?"),
        "camera_model": calib.get("camera_model", "pinhole"),
        "distortion_model": calib.get("distortion_model", "plumb_bob"),
        "valid_images": calib.get("valid_image_count", ""),
        "rms_px": calib.get("rms_reprojection_error_px", np.nan),
        "mean_view_px": summary.get("mean_px", np.nan),
        "median_view_px": summary.get("median_px", np.nan),
        "max_view_px": summary.get("max_px", np.nan),
        "fx": float(matrix[0, 0]),
        "fy": float(matrix[1, 1]),
        "cx": float(matrix[0, 2]),
        "cy": float(matrix[1, 2]),
        "d1": float(padded[0]),
        "d2": float(padded[1]),
        "d3": float(padded[2]),
        "d4": float(padded[3]),
        "d5": float(padded[4]),
        "calibration": str(path),
    }


def print_rows(rows: list[dict[str, object]]) -> None:
    headers = [
        "experiment",
        "method",
        "camera_model",
        "distortion_model",
        "valid_images",
        "rms_px",
        "mean_view_px",
        "median_view_px",
        "max_view_px",
        "fx",
        "fy",
        "cx",
        "cy",
        "d1",
        "d2",
        "d3",
        "d4",
        "d5",
        "calibration",
    ]
    writer = csv.DictWriter(sys.stdout, fieldnames=headers)
    writer.writeheader()
    for row in rows:
        writer.writerow(format_row(row))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(format_row(row) for row in rows)


def format_value(key: str, value: object) -> object:
    if key not in FLOAT_COLUMNS:
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    if np.isnan(number):
        return ""
    return f"{number:.6f}"


def format_row(row: dict[str, object]) -> dict[str, object]:
    return {key: format_value(key, value) for key, value in row.items()}


def undistort_previews(
    calibration: Path,
    images: Path,
    output_dir: Path,
    limit: int,
    alpha: float,
) -> None:
    calib = load_calibration(calibration)
    camera_matrix = calib["camera_matrix"]
    dist_coeffs = calib["dist_coeffs"]
    camera_model = calib.get("camera_model", "pinhole")
    output_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    for path in list_images(images):
        if written >= limit:
            break
        img = cv2.imread(str(path))
        if img is None:
            continue
        height, width = img.shape[:2]
        if camera_model == "fisheye":
            balance = max(0.0, min(1.0, alpha))
            new_matrix = cv2.fisheye.estimateNewCameraMatrixForUndistortRectify(
                camera_matrix,
                dist_coeffs.reshape(-1, 1),
                (width, height),
                np.eye(3),
                balance=balance,
            )
            map1, map2 = cv2.fisheye.initUndistortRectifyMap(
                camera_matrix,
                dist_coeffs.reshape(-1, 1),
                np.eye(3),
                new_matrix,
                (width, height),
                cv2.CV_16SC2,
            )
            undistorted = cv2.remap(img, map1, map2, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        else:
            new_matrix, roi = cv2.getOptimalNewCameraMatrix(
                camera_matrix, dist_coeffs, (width, height), alpha, (width, height)
            )
            undistorted = cv2.undistort(img, camera_matrix, dist_coeffs, None, new_matrix)
            x, y, roi_w, roi_h = roi
            if roi_w > 0 and roi_h > 0:
                cv2.rectangle(undistorted, (x, y), (x + roi_w, y + roi_h), (0, 255, 0), 1)
        write_side_by_side(output_dir / f"undistort_{path.name}", img, undistorted)
        written += 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize calibration experiments and optionally generate undistortion previews.")
    parser.add_argument("--camera", required=True, help="Camera key, e.g. left_side.")
    parser.add_argument("--method", default="chessboard", choices=["chessboard", "charuco"])
    parser.add_argument("--experiments", nargs="*", help="Experiment names. If omitted, discover all experiments with this method.")
    parser.add_argument("--results-root", default="data/results")
    parser.add_argument("--images-root", default="data/images")
    parser.add_argument("--csv", help="Optional CSV output path.")
    parser.add_argument("--undistort", action="store_true", help="Write side-by-side original/undistorted previews.")
    parser.add_argument("--undistort-limit", type=int, default=6)
    parser.add_argument("--undistort-alpha", type=float, default=1.0, help="OpenCV alpha: 0 crops more, 1 keeps more pixels.")
    parser.add_argument("--output-dir", default="data/analysis")
    args = parser.parse_args()

    results_root = Path(args.results_root)
    images_root = Path(args.images_root)
    experiments = args.experiments or discover_experiments(results_root, args.camera, args.method)
    if not experiments:
        raise SystemExit(f"No experiments found for camera={args.camera} method={args.method} under {results_root}.")

    rows = []
    for experiment in experiments:
        calib_path = calibration_path(results_root, args.camera, experiment, args.method)
        if not calib_path.exists():
            print(f"skip missing calibration: {calib_path}", file=sys.stderr)
            continue
        rows.append(row_from_calibration(calib_path, experiment))
        if args.undistort:
            previews_dir = Path(args.output_dir) / args.camera / experiment / args.method / "undistort"
            undistort_previews(
                calib_path,
                image_dir(images_root, args.camera, experiment),
                previews_dir,
                args.undistort_limit,
                args.undistort_alpha,
            )

    if not rows:
        raise SystemExit("No calibration rows to report.")

    print_rows(rows)
    if args.csv:
        write_csv(Path(args.csv), rows)
        print(f"wrote CSV: {args.csv}", file=sys.stderr)
    if args.undistort:
        print(f"wrote undistortion previews under: {args.output_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
