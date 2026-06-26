#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vimas_calibration.imu import analyze_imu, estimate_noise, read_imu_jsonl
from vimas_calibration.io import write_yaml
from vimas_calibration.wt901 import WT901BleClient, scan_ble_devices, scan_wt_devices, write_jsonl_sample


def main() -> None:
    parser = argparse.ArgumentParser(
        description="One-command static IMU calibration: scan/connect WT BLE IMU, record JSONL, export noise and bias YAML."
    )
    parser.add_argument("--sensor-id", default="head_imu", help="Sensor ID written into JSONL, e.g. head_imu or wrist_imu.")
    parser.add_argument("--address", help="BLE address. If omitted, scan and use the first WT/FFE device.")
    parser.add_argument("--scan-timeout-s", type=float, default=8.0)
    parser.add_argument("--duration-s", type=float, default=60.0, help="Static capture duration.")
    parser.add_argument("--output-dir", default="imu_calibration/static")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--scan", action="store_true", help="Scan WT/FFE-looking IMUs and exit.")
    parser.add_argument("--scan-all", action="store_true", help="Scan all BLE devices and exit.")
    args = parser.parse_args()

    if args.scan_all:
        _print_all_devices(args.scan_timeout_s)
        return
    if args.scan:
        _print_wt_devices(args.scan_timeout_s)
        return

    if args.duration_s <= 0:
        raise SystemExit("error: --duration-s must be positive")

    output_dir = Path(args.output_dir)
    jsonl_path = output_dir / f"{args.sensor_id}.jsonl"
    analysis_path = output_dir / f"{args.sensor_id}_analysis.yaml"
    noise_path = output_dir / f"{args.sensor_id}_noise.yaml"
    if jsonl_path.exists() and not args.overwrite:
        raise SystemExit(f"error: {jsonl_path} exists; pass --overwrite or choose another --output-dir")
    if jsonl_path.exists():
        jsonl_path.unlink()

    address = args.address or _scan_first_address(args.scan_timeout_s)
    print(f"sensor_id: {args.sensor_id}")
    print(f"address: {address}")
    print(f"duration_s: {args.duration_s}")
    print("keep the IMU completely still until capture finishes")

    sample_count = 0

    def on_sample(sample) -> None:
        nonlocal sample_count
        sample_count += 1
        write_jsonl_sample(jsonl_path, sample)
        if sample_count % 100 == 0:
            print(f"samples: {sample_count}", flush=True)

    client = WT901BleClient(address, args.sensor_id, on_sample, on_connected=lambda: print("connected"))
    asyncio.run(client.run(duration_s=args.duration_s))
    if sample_count < 10:
        raise SystemExit(f"error: captured only {sample_count} samples")

    series = read_imu_jsonl(jsonl_path)
    analysis = analyze_imu(series)
    noise = {
        "imus": {
            args.sensor_id: estimate_noise(series),
        },
        "source": {
            "jsonl": str(jsonl_path),
            "method": "static first-pass standard deviation estimate",
        },
    }
    write_yaml(analysis_path, analysis)
    write_yaml(noise_path, noise)
    print(f"wrote {jsonl_path}")
    print(f"wrote {analysis_path}")
    print(f"wrote {noise_path}")


def _scan_first_address(timeout_s: float) -> str:
    devices = asyncio.run(scan_wt_devices(timeout_s))
    if not devices:
        all_devices = asyncio.run(scan_ble_devices(timeout_s))
        if all_devices:
            print("no WT/FFE-looking IMU found; all scanned BLE devices:")
            for device in all_devices:
                services = ",".join(device.get("service_uuids", []))
                print(f"  {device['name']}\t{device['address']}\trssi={device.get('rssi')}\tservices={services}")
        raise SystemExit("error: no WT/FFE BLE IMU found; pass --address or increase --scan-timeout-s")
    print("found devices:")
    for index, (name, address) in enumerate(devices):
        print(f"  [{index}] {name}\t{address}")
    if len(devices) > 1:
        print("using the first device; pass --address to choose explicitly")
    return devices[0][1]


def _print_wt_devices(timeout_s: float) -> None:
    devices = asyncio.run(scan_wt_devices(timeout_s))
    for name, address in devices:
        print(f"{name}\t{address}")


def _print_all_devices(timeout_s: float) -> None:
    devices = asyncio.run(scan_ble_devices(timeout_s))
    for device in devices:
        services = ",".join(device.get("service_uuids", []))
        print(f"{device['name']}\t{device['address']}\trssi={device.get('rssi')}\tservices={services}")


if __name__ == "__main__":
    main()
