#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import re
from pathlib import Path


REPROJECTION_RE = re.compile(
    r"reprojection error:\s*"
    r"\[\s*(?P<mean_x>[-+0-9.eE]+)\s*,\s*(?P<mean_y>[-+0-9.eE]+)\s*\]\s*"
    r"\+-\s*"
    r"\[\s*(?P<std_x>[-+0-9.eE]+)\s*,\s*(?P<std_y>[-+0-9.eE]+)\s*\]"
)


def parse_reprojection_errors(text: str) -> list[dict[str, float]]:
    results: list[dict[str, float]] = []
    for match in REPROJECTION_RE.finditer(text):
        values = {key: float(value) for key, value in match.groupdict().items()}
        values["rms_2d"] = math.hypot(values["std_x"], values["std_y"])
        results.append(values)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute 2D reprojection RMS from Kalibr results text.")
    parser.add_argument("results", nargs="+", help="Kalibr *-results-cam.txt file(s).")
    args = parser.parse_args()

    had_result = False
    for item in args.results:
        path = Path(item)
        entries = parse_reprojection_errors(path.read_text(encoding="utf-8"))
        if not entries:
            print(f"{path}: no reprojection error lines found")
            continue
        had_result = True
        for index, entry in enumerate(entries):
            suffix = f" cam{index}" if len(entries) > 1 else ""
            print(f"{path}{suffix}")
            print(f"  mean_x_px: {entry['mean_x']:.6f}")
            print(f"  mean_y_px: {entry['mean_y']:.6f}")
            print(f"  std_x_px:  {entry['std_x']:.6f}")
            print(f"  std_y_px:  {entry['std_y']:.6f}")
            print(f"  rms_2d_px: {entry['rms_2d']:.6f}")
    if not had_result:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
