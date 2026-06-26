#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vimas_calibration.rig import load_rig_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Create one image folder per rig camera.")
    parser.add_argument("--config", default="configs/four_head_rig.yaml")
    parser.add_argument("--images-root", default="data/images")
    args = parser.parse_args()

    rig = load_rig_config(args.config)
    root = Path(args.images_root)
    for camera in rig.cameras:
        folder = root / camera.key
        folder.mkdir(parents=True, exist_ok=True)
        print(folder)


if __name__ == "__main__":
    main()
