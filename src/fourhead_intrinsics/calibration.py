from __future__ import annotations

import math
import shutil
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .io import list_images, write_yaml
from .metrics import fov_degrees, per_view_reprojection_errors, summarize_errors
from .quality import image_quality, quality_label_lines, quality_rejection_reason
from .visualization import save_processed_image


@dataclass(frozen=True)
class QualityFilter:
    min_sharpness: float = 20.0
    min_contrast: float = 15.0
    min_coverage: float = 0.02
    min_brightness: float = 10.0
    max_brightness: float = 245.0


@dataclass(frozen=True)
class CalibrationOptions:
    images: Path
    output: Path
    processed_dir: Path
    debug_dir: Path
    square_size: float
    max_error: float = 5.0
    camera_model: str = "fisheye"
    auto_filter: bool = True
    quality_filter: QualityFilter = QualityFilter()


def build_chessboard_object_points(cols: int, rows: int, square_size: float) -> np.ndarray:
    objp = np.zeros((rows * cols, 3), np.float32)
    objp[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2)
    objp *= square_size
    return objp


def _quality_reason(metrics: dict[str, float], quality_filter: QualityFilter) -> str | None:
    return quality_rejection_reason(
        metrics,
        quality_filter.min_sharpness,
        quality_filter.min_contrast,
        quality_filter.min_coverage,
        quality_filter.min_brightness,
        quality_filter.max_brightness,
    )


def _quality_filter_data(quality_filter: QualityFilter) -> dict[str, float]:
    return {
        "min_sharpness": quality_filter.min_sharpness,
        "min_contrast": quality_filter.min_contrast,
        "min_coverage": quality_filter.min_coverage,
        "min_brightness": quality_filter.min_brightness,
        "max_brightness": quality_filter.max_brightness,
    }


def _prepare_dirs(options: CalibrationOptions) -> None:
    options.debug_dir.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(options.processed_dir / "accepted", ignore_errors=True)
    shutil.rmtree(options.processed_dir / "rejected", ignore_errors=True)


def _model_metadata(camera_model: str) -> dict[str, str]:
    if camera_model == "fisheye":
        return {
            "camera_model": "fisheye",
            "distortion_model": "opencv_fisheye",
            "dist_coeffs_order": "k1,k2,k3,k4",
        }
    if camera_model == "pinhole":
        return {
            "camera_model": "pinhole",
            "distortion_model": "plumb_bob",
            "dist_coeffs_order": "k1,k2,p1,p2,k3",
        }
    raise ValueError(f"Unsupported camera model: {camera_model}")


def _fisheye_object_points(points: list[np.ndarray]) -> list[np.ndarray]:
    return [np.asarray(obj, dtype=np.float64).reshape(-1, 1, 3) for obj in points]


def _fisheye_image_points(points: list[np.ndarray]) -> list[np.ndarray]:
    return [np.asarray(img, dtype=np.float64).reshape(-1, 1, 2) for img in points]


def _calibrate_model(
    object_points: list[np.ndarray],
    image_points: list[np.ndarray],
    image_size: tuple[int, int],
    camera_model: str,
) -> tuple[float, np.ndarray, np.ndarray, list[np.ndarray], list[np.ndarray]]:
    if camera_model == "fisheye":
        camera_matrix = np.zeros((3, 3), dtype=np.float64)
        dist_coeffs = np.zeros((4, 1), dtype=np.float64)
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 200, 1e-6)
        flags = cv2.fisheye.CALIB_RECOMPUTE_EXTRINSIC + cv2.fisheye.CALIB_FIX_SKEW
        rms, camera_matrix, dist_coeffs, rvecs, tvecs = cv2.fisheye.calibrate(
            _fisheye_object_points(object_points),
            _fisheye_image_points(image_points),
            image_size,
            camera_matrix,
            dist_coeffs,
            None,
            None,
            flags,
            criteria,
        )
        return float(rms), camera_matrix, dist_coeffs, list(rvecs), list(tvecs)

    if camera_model == "pinhole":
        rms, camera_matrix, dist_coeffs, rvecs, tvecs = cv2.calibrateCamera(
            object_points,
            image_points,
            image_size,
            None,
            None,
        )
        return float(rms), camera_matrix, dist_coeffs, list(rvecs), list(tvecs)

    raise ValueError(f"Unsupported camera model: {camera_model}")


def _project_points(
    object_points: np.ndarray,
    rvec: np.ndarray,
    tvec: np.ndarray,
    camera_matrix: np.ndarray,
    dist_coeffs: np.ndarray,
    camera_model: str,
) -> np.ndarray:
    if camera_model == "fisheye":
        projected, _ = cv2.fisheye.projectPoints(
            np.asarray(object_points, dtype=np.float64).reshape(-1, 1, 3),
            rvec,
            tvec,
            camera_matrix,
            dist_coeffs,
        )
        return projected
    projected, _ = cv2.projectPoints(object_points, rvec, tvec, camera_matrix, dist_coeffs)
    return projected


def _per_view_errors(
    object_points: list[np.ndarray],
    image_points: list[np.ndarray],
    rvecs: list[np.ndarray],
    tvecs: list[np.ndarray],
    camera_matrix: np.ndarray,
    dist_coeffs: np.ndarray,
    camera_model: str,
) -> list[float]:
    if camera_model == "pinhole":
        return per_view_reprojection_errors(object_points, image_points, rvecs, tvecs, camera_matrix, dist_coeffs)

    errors = []
    for obj, img, rvec, tvec in zip(object_points, image_points, rvecs, tvecs):
        projected = _project_points(obj, rvec, tvec, camera_matrix, dist_coeffs, camera_model)
        corners = np.asarray(img, dtype=np.float64).reshape(-1, 1, 2)
        errors.append(float(cv2.norm(corners, projected, cv2.NORM_L2) / math.sqrt(len(projected))))
    return errors


def calibrate_chessboard(cols: int, rows: int, options: CalibrationOptions) -> dict[str, object]:
    _prepare_dirs(options)
    objp = build_chessboard_object_points(cols, rows, options.square_size)
    object_points: list[np.ndarray] = []
    image_points: list[np.ndarray] = []
    used_images: list[str] = []
    debug_images: list[np.ndarray] = []
    rejected_images: list[str] = []
    rejected_by_quality_images: list[str] = []
    quality_metrics_by_image: dict[str, dict[str, float]] = {}
    image_size: tuple[int, int] | None = None

    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.001)
    flags = cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE + cv2.CALIB_CB_FAST_CHECK

    for path in list_images(options.images):
        img = cv2.imread(str(path))
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        current_size = (gray.shape[1], gray.shape[0])
        if image_size is None:
            image_size = current_size
        elif current_size != image_size:
            rejected_images.append(str(path))
            save_processed_image(
                options.processed_dir / "rejected" / path.name,
                img,
                ["REJECTED", f"reason: size mismatch {current_size} != {image_size}"],
                "rejected",
            )
            continue

        found, corners = cv2.findChessboardCorners(gray, (cols, rows), flags)
        if not found:
            rejected_images.append(str(path))
            save_processed_image(
                options.processed_dir / "rejected" / path.name,
                img,
                ["REJECTED", "reason: no chessboard corners"],
                "rejected",
            )
            continue

        corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
        metrics = image_quality(gray, corners)
        quality_metrics_by_image[str(path)] = metrics
        reason = _quality_reason(metrics, options.quality_filter)
        if reason is not None:
            rejected_by_quality_images.append(str(path))
            dbg = img.copy()
            cv2.drawChessboardCorners(dbg, (cols, rows), corners, found)
            save_processed_image(
                options.processed_dir / "rejected" / path.name,
                dbg,
                ["REJECTED", f"reason: {reason}", *quality_label_lines(metrics)],
                "rejected",
            )
            continue

        object_points.append(objp.copy())
        image_points.append(corners)
        used_images.append(str(path))
        dbg = img.copy()
        cv2.drawChessboardCorners(dbg, (cols, rows), corners, found)
        debug_images.append(dbg)
        cv2.imwrite(str(options.debug_dir / path.name), dbg)

    if image_size is None or len(object_points) < 8:
        raise RuntimeError(f"Need at least 8 valid chessboard images, got {len(object_points)}.")

    rejected_by_error_images: list[str] = []
    while True:
        rms, camera_matrix, dist_coeffs, rvecs, tvecs = _calibrate_model(
            object_points,
            image_points,
            image_size,
            options.camera_model,
        )
        errors = _per_view_errors(
            object_points,
            image_points,
            rvecs,
            tvecs,
            camera_matrix,
            dist_coeffs,
            options.camera_model,
        )
        high_error_indexes = [idx for idx, err in enumerate(errors) if err > options.max_error]
        for idx in high_error_indexes:
            if used_images[idx] not in rejected_by_error_images:
                rejected_by_error_images.append(used_images[idx])
            image_path = Path(used_images[idx])
            save_processed_image(
                options.processed_dir / "rejected" / image_path.name,
                debug_images[idx],
                ["REJECTED", f"reason: error {errors[idx]:.4f} > {options.max_error:.4f} px"],
                "rejected",
            )
        if not options.auto_filter or not high_error_indexes:
            break
        accepted_indexes = [idx for idx, err in enumerate(errors) if err <= options.max_error]
        if len(accepted_indexes) < 8:
            raise RuntimeError(
                f"Only {len(accepted_indexes)} images remain after filtering by --max-error {options.max_error}. "
                "Need at least 8. Increase --max-error or collect more images."
            )
        object_points = [object_points[idx] for idx in accepted_indexes]
        image_points = [image_points[idx] for idx in accepted_indexes]
        used_images = [used_images[idx] for idx in accepted_indexes]
        debug_images = [debug_images[idx] for idx in accepted_indexes]

    for path, dbg, err in zip(used_images, debug_images, errors):
        if err > options.max_error:
            continue
        image_path = Path(path)
        save_processed_image(
            options.processed_dir / "accepted" / image_path.name,
            dbg,
            ["ACCEPTED", f"error: {err:.4f} px", *quality_label_lines(quality_metrics_by_image.get(path, {}))],
            "accepted",
        )

    summary = summarize_errors(errors)
    data = {
        "method": "chessboard",
        **_model_metadata(options.camera_model),
        "image_size": list(image_size),
        "pattern": {"inner_cols": cols, "inner_rows": rows, "square_size": options.square_size},
        "valid_image_count": len(used_images),
        "auto_filter": bool(options.auto_filter),
        "max_error_px": options.max_error,
        "quality_filter": _quality_filter_data(options.quality_filter),
        "initial_rejected_images": rejected_images,
        "rejected_by_quality_images": rejected_by_quality_images,
        "rejected_by_error_images": rejected_by_error_images,
        "processed_images_dir": str(options.processed_dir),
        "quality_metrics_by_image": quality_metrics_by_image,
        "rms_reprojection_error_px": float(rms),
        "per_view_error_summary": summary,
        "fov_degrees": fov_degrees(camera_matrix, image_size),
        "camera_matrix": camera_matrix,
        "dist_coeffs": dist_coeffs.reshape(-1),
        "used_images": used_images,
        "per_view_errors_px": dict(zip(used_images, errors)),
    }
    write_yaml(options.output, data)
    return data


def make_charuco_board(cols: int, rows: int, square_size: float, marker_ratio: float):
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_1000)
    board = cv2.aruco.CharucoBoard((cols, rows), square_size, square_size * marker_ratio, dictionary)
    return board, dictionary


def calibrate_charuco(cols: int, rows: int, marker_ratio: float, options: CalibrationOptions) -> dict[str, object]:
    if not hasattr(cv2, "aruco"):
        raise RuntimeError("cv2.aruco not found. Install opencv-contrib-python.")

    _prepare_dirs(options)
    board, dictionary = make_charuco_board(cols, rows, options.square_size, marker_ratio)
    detector_params = cv2.aruco.DetectorParameters()
    detector_params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    detector_params.cornerRefinementWinSize = 5
    detector_params.cornerRefinementMaxIterations = 30
    detector_params.cornerRefinementMinAccuracy = 0.01
    detector = cv2.aruco.ArucoDetector(dictionary, detector_params)
    if hasattr(cv2.aruco, "CharucoDetector"):
        charuco_params = cv2.aruco.CharucoParameters()
        charuco_detector = cv2.aruco.CharucoDetector(board, charuco_params, detector_params)
    else:
        charuco_detector = None
    chess_corners = board.getChessboardCorners()

    all_object_points: list[np.ndarray] = []
    all_corners: list[np.ndarray] = []
    all_ids: list[np.ndarray] = []
    used_images: list[str] = []
    debug_images: list[np.ndarray] = []
    rejected_images: list[str] = []
    rejected_by_quality_images: list[str] = []
    quality_metrics_by_image: dict[str, dict[str, float]] = {}
    image_size: tuple[int, int] | None = None

    for path in list_images(options.images):
        img = cv2.imread(str(path))
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        current_size = (gray.shape[1], gray.shape[0])
        if image_size is None:
            image_size = current_size
        elif current_size != image_size:
            rejected_images.append(str(path))
            save_processed_image(
                options.processed_dir / "rejected" / path.name,
                img,
                ["REJECTED", f"reason: size mismatch {current_size} != {image_size}"],
                "rejected",
            )
            continue

        if charuco_detector is not None:
            charuco_corners, charuco_ids, marker_corners, marker_ids = charuco_detector.detectBoard(gray)
        else:
            marker_corners, marker_ids, _ = detector.detectMarkers(gray)
            if marker_ids is not None and len(marker_ids) >= 4 and hasattr(cv2.aruco, "interpolateCornersCharuco"):
                _, charuco_corners, charuco_ids = cv2.aruco.interpolateCornersCharuco(
                    marker_corners, marker_ids, gray, board
                )
            else:
                charuco_corners, charuco_ids = None, None

        if marker_ids is None or len(marker_ids) < 4:
            rejected_images.append(str(path))
            save_processed_image(
                options.processed_dir / "rejected" / path.name,
                img,
                ["REJECTED", "reason: too few markers"],
                "rejected",
            )
            continue

        if charuco_corners is None or charuco_ids is None or len(charuco_ids) < 8:
            rejected_images.append(str(path))
            dbg = img.copy()
            cv2.aruco.drawDetectedMarkers(dbg, marker_corners, marker_ids)
            save_processed_image(
                options.processed_dir / "rejected" / path.name,
                dbg,
                ["REJECTED", "reason: too few charuco corners"],
                "rejected",
            )
            continue

        object_points = chess_corners[charuco_ids.flatten()].reshape(-1, 1, 3)
        metrics = image_quality(gray, charuco_corners)
        quality_metrics_by_image[str(path)] = metrics
        reason = _quality_reason(metrics, options.quality_filter)
        if reason is not None:
            rejected_by_quality_images.append(str(path))
            dbg = img.copy()
            cv2.aruco.drawDetectedMarkers(dbg, marker_corners, marker_ids)
            cv2.aruco.drawDetectedCornersCharuco(dbg, charuco_corners, charuco_ids)
            save_processed_image(
                options.processed_dir / "rejected" / path.name,
                dbg,
                ["REJECTED", f"reason: {reason}", *quality_label_lines(metrics)],
                "rejected",
            )
            continue

        all_object_points.append(object_points)
        all_corners.append(charuco_corners)
        all_ids.append(charuco_ids)
        used_images.append(str(path))
        dbg = img.copy()
        cv2.aruco.drawDetectedMarkers(dbg, marker_corners, marker_ids)
        cv2.aruco.drawDetectedCornersCharuco(dbg, charuco_corners, charuco_ids)
        debug_images.append(dbg)
        cv2.imwrite(str(options.debug_dir / path.name), dbg)

    if image_size is None or len(all_corners) < 8:
        raise RuntimeError(f"Need at least 8 valid ChArUco images, got {len(all_corners)}.")

    rejected_by_error_images: list[str] = []
    while True:
        rms, camera_matrix, dist_coeffs, rvecs, tvecs = _calibrate_model(
            all_object_points,
            all_corners,
            image_size,
            options.camera_model,
        )
        errors = _per_view_errors(
            all_object_points,
            all_corners,
            rvecs,
            tvecs,
            camera_matrix,
            dist_coeffs,
            options.camera_model,
        )
        high_error_indexes = [idx for idx, err in enumerate(errors) if err > options.max_error]
        for idx in high_error_indexes:
            if used_images[idx] not in rejected_by_error_images:
                rejected_by_error_images.append(used_images[idx])
            image_path = Path(used_images[idx])
            save_processed_image(
                options.processed_dir / "rejected" / image_path.name,
                debug_images[idx],
                ["REJECTED", f"reason: error {errors[idx]:.4f} > {options.max_error:.4f} px"],
                "rejected",
            )
        if not options.auto_filter or not high_error_indexes:
            break
        accepted_indexes = [idx for idx, err in enumerate(errors) if err <= options.max_error]
        if len(accepted_indexes) < 8:
            raise RuntimeError(
                f"Only {len(accepted_indexes)} images remain after filtering by --max-error {options.max_error}. "
                "Need at least 8. Increase --max-error or collect more images."
            )
        all_object_points = [all_object_points[idx] for idx in accepted_indexes]
        all_corners = [all_corners[idx] for idx in accepted_indexes]
        all_ids = [all_ids[idx] for idx in accepted_indexes]
        used_images = [used_images[idx] for idx in accepted_indexes]
        debug_images = [debug_images[idx] for idx in accepted_indexes]

    for path, dbg, err in zip(used_images, debug_images, errors):
        if err > options.max_error:
            continue
        image_path = Path(path)
        save_processed_image(
            options.processed_dir / "accepted" / image_path.name,
            dbg,
            ["ACCEPTED", f"error: {err:.4f} px", *quality_label_lines(quality_metrics_by_image.get(path, {}))],
            "accepted",
        )

    summary = summarize_errors(errors)
    data = {
        "method": "charuco",
        **_model_metadata(options.camera_model),
        "image_size": list(image_size),
        "pattern": {
            "squares_cols": cols,
            "squares_rows": rows,
            "square_size": options.square_size,
            "marker_ratio": marker_ratio,
        },
        "valid_image_count": len(used_images),
        "auto_filter": bool(options.auto_filter),
        "max_error_px": options.max_error,
        "quality_filter": _quality_filter_data(options.quality_filter),
        "initial_rejected_images": rejected_images,
        "rejected_by_quality_images": rejected_by_quality_images,
        "rejected_by_error_images": rejected_by_error_images,
        "processed_images_dir": str(options.processed_dir),
        "quality_metrics_by_image": quality_metrics_by_image,
        "rms_reprojection_error_px": float(rms),
        "per_view_error_summary": summary,
        "fov_degrees": fov_degrees(camera_matrix, image_size),
        "camera_matrix": camera_matrix,
        "dist_coeffs": dist_coeffs.reshape(-1),
        "used_images": used_images,
        "per_view_errors_px": dict(zip(used_images, errors)),
    }
    write_yaml(options.output, data)
    return data
