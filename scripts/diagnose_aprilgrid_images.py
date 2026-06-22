#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import cv2
import yaml


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


def list_images(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTS)


def load_target(path: Path) -> tuple[int, int]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if data.get("target_type") != "aprilgrid":
        raise SystemExit(f"error: not an aprilgrid target: {path}")
    return int(data["tagCols"]), int(data["tagRows"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Create AprilGrid detection debug images for an image folder.")
    parser.add_argument("--images", required=True)
    parser.add_argument("--target-yaml", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    image_dir = Path(args.images)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cols, rows = load_target(Path(args.target_yaml))
    expected_ids = set(range(cols * rows))
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())

    rows_out: list[dict[str, object]] = []
    for path in list_images(image_dir):
        img = cv2.imread(str(path))
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        corners, ids, rejected = detector.detectMarkers(gray)
        seen_ids = set(ids.flatten().tolist()) if ids is not None else set()
        expected_seen = sorted(seen_ids & expected_ids)
        missing = sorted(expected_ids - seen_ids)
        unexpected = sorted(seen_ids - expected_ids)

        dbg = img.copy()
        if ids is not None:
            cv2.aruco.drawDetectedMarkers(dbg, corners, ids)
        label = (
            f"expected_seen={len(expected_seen)}/{len(expected_ids)} "
            f"unexpected={len(unexpected)} rejected={len(rejected)}"
        )
        cv2.rectangle(dbg, (0, 0), (dbg.shape[1], 38), (255, 255, 255), -1)
        cv2.putText(dbg, label, (12, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)
        cv2.imwrite(str(out_dir / path.name), dbg)

        rows_out.append(
            {
                "image": path.name,
                "expected_seen": len(expected_seen),
                "expected_total": len(expected_ids),
                "unexpected_count": len(unexpected),
                "rejected_candidates": len(rejected),
                "seen_ids": " ".join(map(str, expected_seen)),
                "missing_ids": " ".join(map(str, missing)),
                "unexpected_ids": " ".join(map(str, unexpected)),
            }
        )

    report = out_dir / "aprilgrid_detection_report.csv"
    with report.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "image",
                "expected_seen",
                "expected_total",
                "unexpected_count",
                "rejected_candidates",
                "seen_ids",
                "missing_ids",
                "unexpected_ids",
            ],
        )
        writer.writeheader()
        writer.writerows(rows_out)

    print(f"wrote debug images: {out_dir}")
    print(f"wrote report: {report}")
    if rows_out:
        counts = [int(row["expected_seen"]) for row in rows_out]
        print(f"images: {len(rows_out)}")
        print(f"expected tags per image: min={min(counts)} max={max(counts)}")


if __name__ == "__main__":
    main()
