# Camera Intrinsics

This folder is the entry point for camera intrinsics work:

- camera matrix / projection parameters
- distortion coefficients
- image resolution and capture mode
- Kalibr and OpenCV fallback workflows

The current implementation keeps executable scripts in `../scripts` and reusable Python code in
`../src/vimas_calibration`. The old `fourhead_intrinsics` package remains as a compatibility shim.

Main references:

- `../docs/fisheye_intrinsics_workflow.md`
- `../docs/kalibr_report_guide.md`
- `../configs/four_head_rig.yaml`

Typical output:

```text
data/results/four_camera_intrinsics.yaml
```

Intrinsic parameters do not define where a camera sits on the headset. Use
`../camera_extrinsics` for `T_head_camera` values.
