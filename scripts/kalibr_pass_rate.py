#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


PROCESSED_RE = re.compile(r"Processed\s+(?P<total>\d+)\s+images\s+with\s+(?P<used>\d+)\s+images\s+used")


def parse_pass_rates(text: str) -> list[tuple[int, int]]:
    return [(int(m.group("total")), int(m.group("used"))) for m in PROCESSED_RE.finditer(text)]


def print_rate(label: str, total: int, used: int) -> None:
    rejected = total - used
    rate = 100.0 * used / total if total else 0.0
    print(label)
    print(f"  total_images: {total}")
    print(f"  used_images:  {used}")
    print(f"  rejected:     {rejected}")
    print(f"  pass_rate:    {rate:.2f}%")


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse Kalibr image pass rate from calibration terminal logs.")
    parser.add_argument("logs", nargs="*", help="Kalibr log file(s). If omitted, read stdin.")
    args = parser.parse_args()

    if not args.logs:
        entries = parse_pass_rates(sys.stdin.read())
        if not entries:
            raise SystemExit("error: no 'Processed X images with Y images used' lines found on stdin")
        total, used = entries[-1]
        print_rate("stdin", total, used)
        return

    had_result = False
    for log in args.logs:
        path = Path(log)
        entries = parse_pass_rates(path.read_text(encoding="utf-8", errors="replace"))
        if not entries:
            print(f"{path}: no pass-rate lines found")
            continue
        had_result = True
        total, used = entries[-1]
        print_rate(str(path), total, used)
    if not had_result:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
