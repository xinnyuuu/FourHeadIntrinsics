#!/usr/bin/env python3
from __future__ import annotations

import argparse
import runpy
import sys
from pathlib import Path

import numpy as np
import yaml


def parse_init_arg(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("expected /topic=camchain.yaml")
    topic, path = value.split("=", 1)
    return topic.strip(), Path(path)


def load_init_params(items: list[tuple[str, Path]]) -> dict[str, tuple[list[float], list[float]]]:
    params: dict[str, tuple[list[float], list[float]]] = {}
    for topic, path in items:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        cam = data.get("cam0")
        if not cam:
            raise SystemExit(f"error: {path} has no cam0")
        if cam.get("camera_model") != "omni" or cam.get("distortion_model") != "radtan":
            raise SystemExit(f"error: {path} is not omni-radtan")
        params[topic] = (list(map(float, cam["intrinsics"])), list(map(float, cam["distortion_coeffs"])))
    return params


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Kalibr camera calibration with omni-radtan intrinsics initialized from existing camchain files.",
        add_help=True,
    )
    parser.add_argument("--init-camchain", action="append", default=[], type=parse_init_arg)
    known, remaining = parser.parse_known_args()
    init_params = load_init_params(known.init_camchain)

    import aslam_cv_backend as acvb
    import kalibr_camera_calibration as kcc

    original_init = kcc.CameraGeometry.initGeometryFromObservations

    def init_from_camchain(self, observations):
        if self.dataset.topic not in init_params:
            return original_init(self, observations)

        intrinsics, distortion = init_params[self.dataset.topic]
        values = np.array(intrinsics + distortion, dtype=np.float64).reshape((-1, 1))
        self.geometry.setParameters(values, True, True, False)

        success = True
        if self.model == acvb.DistortedOmni:
            success = kcc.calibrateIntrinsics(self, observations, distortionActive=False)
        if success:
            success = kcc.calibrateIntrinsics(self, observations)
        self.isGeometryInitialized = success
        return success

    kcc.CameraGeometry.initGeometryFromObservations = init_from_camchain

    sys.argv = ["kalibr_calibrate_cameras"] + remaining
    runpy.run_path(
        "/catkin_ws/src/kalibr/aslam_offline_calibration/kalibr/python/kalibr_calibrate_cameras",
        run_name="__main__",
    )


if __name__ == "__main__":
    main()
