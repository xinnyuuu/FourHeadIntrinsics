from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def save_processed_image(path: str | Path, image: np.ndarray, lines: list[str], status: str) -> None:
    color = (0, 180, 0) if status == "accepted" else (0, 0, 255)
    output = image.copy()
    y = 32
    for line in lines:
        cv2.putText(output, line, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2, cv2.LINE_AA)
        y += 34
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), output)
