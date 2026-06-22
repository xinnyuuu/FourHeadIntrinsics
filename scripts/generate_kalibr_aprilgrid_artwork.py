#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
from pathlib import Path
from xml.sax.saxutils import escape

import cv2
import numpy as np
import yaml

A4_WIDTH_M = 0.210
A4_HEIGHT_M = 0.297


def _load_target(path: str | None) -> dict[str, object]:
    if path is None:
        return {}
    with Path(path).open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if data.get("target_type") != "aprilgrid":
        raise ValueError(f"{path} is not a Kalibr aprilgrid target YAML.")
    return data


def _marker(dictionary: cv2.aruco.Dictionary, tag_id: int, size_px: int) -> np.ndarray:
    return cv2.aruco.generateImageMarker(dictionary, tag_id, size_px)


def _png_data_uri(image: np.ndarray) -> str:
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError("Failed to encode AprilTag marker as PNG.")
    payload = base64.b64encode(encoded.tobytes()).decode("ascii")
    return f"data:image/png;base64,{payload}"


def _render_png(
    cols: int,
    rows: int,
    tag_px: int,
    gap_px: int,
    margin_px: int,
    output: Path,
) -> None:
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    width = cols * tag_px + (cols - 1) * gap_px + 2 * margin_px
    height = rows * tag_px + (rows - 1) * gap_px + 2 * margin_px
    canvas = np.full((height, width), 255, dtype=np.uint8)
    for row in range(rows):
        for col in range(cols):
            tag_id = row * cols + col
            marker = _marker(dictionary, tag_id, tag_px)
            x0 = margin_px + col * (tag_px + gap_px)
            y0 = margin_px + row * (tag_px + gap_px)
            canvas[y0 : y0 + tag_px, x0 : x0 + tag_px] = marker

    output.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output), canvas)


def _render_svg(
    cols: int,
    rows: int,
    tag_size_m: float,
    tag_spacing: float,
    margin_m: float,
    marker_px: int,
    output: Path,
) -> None:
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    tag_mm = tag_size_m * 1000.0
    gap_mm = tag_mm * tag_spacing
    margin_mm = margin_m * 1000.0
    width_mm = cols * tag_mm + (cols - 1) * gap_mm + 2 * margin_mm
    height_mm = rows * tag_mm + (rows - 1) * gap_mm + 2 * margin_mm

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{width_mm:.6f}mm" height="{height_mm:.6f}mm" '
            f'viewBox="0 0 {width_mm:.6f} {height_mm:.6f}">'
        ),
        '<rect x="0" y="0" width="100%" height="100%" fill="white"/>',
    ]
    for row in range(rows):
        for col in range(cols):
            tag_id = row * cols + col
            marker = _marker(dictionary, tag_id, marker_px)
            href = escape(_png_data_uri(marker))
            x = margin_mm + col * (tag_mm + gap_mm)
            y = margin_mm + row * (tag_mm + gap_mm)
            parts.append(
                f'<image x="{x:.6f}" y="{y:.6f}" width="{tag_mm:.6f}" height="{tag_mm:.6f}" '
                f'href="{href}" image-rendering="pixelated"/>'
            )
    parts.append("</svg>")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(parts) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate printable artwork for a Kalibr AprilGrid target.")
    parser.add_argument("--target-yaml", help="Read tagCols/tagRows/tagSize/tagSpacing from a Kalibr target YAML.")
    parser.add_argument("--tag-cols", type=int, default=6)
    parser.add_argument("--tag-rows", type=int, default=6)
    parser.add_argument("--tag-size-m", type=float, default=0.088)
    parser.add_argument("--tag-spacing", type=float, default=0.3, help="Spacing ratio: gap / tag size.")
    parser.add_argument("--margin-m", type=float, default=0.02)
    parser.add_argument("--tag-px", type=int, default=880, help="PNG pixels per tag side.")
    parser.add_argument("--marker-px", type=int, default=880, help="Embedded marker pixels per SVG tag.")
    parser.add_argument("--output-svg", default="data/targets/aprilgrid_6x6_088.svg")
    parser.add_argument("--output-png", default="data/targets/aprilgrid_6x6_088.png")
    args = parser.parse_args()

    target = _load_target(args.target_yaml)
    cols = int(target.get("tagCols", args.tag_cols))
    rows = int(target.get("tagRows", args.tag_rows))
    tag_size_m = float(target.get("tagSize", args.tag_size_m))
    tag_spacing = float(target.get("tagSpacing", args.tag_spacing))

    if cols <= 0 or rows <= 0:
        raise ValueError("tag rows/cols must be positive.")
    if tag_size_m <= 0 or tag_spacing < 0 or args.margin_m < 0:
        raise ValueError("tag size must be positive, spacing and margin must be non-negative.")
    if args.tag_px <= 0 or args.marker_px <= 0:
        raise ValueError("pixel sizes must be positive.")

    gap_px = int(round(args.tag_px * tag_spacing))
    margin_px = int(round(args.tag_px * args.margin_m / tag_size_m))
    svg_out = Path(args.output_svg)
    png_out = Path(args.output_png)

    _render_svg(cols, rows, tag_size_m, tag_spacing, args.margin_m, args.marker_px, svg_out)
    _render_png(cols, rows, args.tag_px, gap_px, margin_px, png_out)

    width_m = cols * tag_size_m + (cols - 1) * tag_size_m * tag_spacing + 2 * args.margin_m
    height_m = rows * tag_size_m + (rows - 1) * tag_size_m * tag_spacing + 2 * args.margin_m
    fits_a4_portrait = width_m <= A4_WIDTH_M and height_m <= A4_HEIGHT_M
    fits_a4_landscape = width_m <= A4_HEIGHT_M and height_m <= A4_WIDTH_M
    print(f"wrote {svg_out}")
    print(f"wrote {png_out}")
    print(f"physical board size: {width_m * 1000.0:.1f} mm x {height_m * 1000.0:.1f} mm")
    if fits_a4_portrait or fits_a4_landscape:
        orientation = "portrait" if fits_a4_portrait else "landscape"
        print(f"A4 check: fits A4 {orientation}. Good for pipeline smoke tests.")
    else:
        print("A4 check: does not fit A4. Use A0/A1 or reduce tag size for a smoke test.")
    print("A4-sized AprilGrid is for early testing only; use a larger rigid board for final fisheye calibration.")
    print("print the SVG at 100% / actual size / no scaling, then measure the real tag size and spacing.")


if __name__ == "__main__":
    main()
