# IMU Calibration

This folder covers the two IMU calibrations needed by 3DMotion/VIMAS:

```text
T_H_IH  head IMU frame I_H -> headset Head frame H
T_B_IB  wrist IMU frame I_B -> wristband frame B
```

The transform convention is:

```text
T_A_B maps points from frame B into frame A.
p_A = T_A_B * p_B
```

## Head IMU

Prototype P3a may temporarily use:

```text
H := I_H
T_W_H := T_W_IH
```

For the final calibration, run camera-IMU calibration with Kalibr or an equivalent tool using one
head camera and `head_imu`. If Kalibr gives `T_C0_IH` and camera extrinsics provide `T_H_C0`, then:

```text
T_H_IH = T_H_C0 * T_C0_IH
```

If OpenVINS needs `T_imu_cam`:

```text
T_IH_C0 = inverse(T_H_IH) * T_H_C0
```

### Head Camera-IMU Kalibr Workflow

Use this when the head IMU is rigidly fixed to the headset camera rig.

1. Capture one or more head cameras and `head_imu` while moving the rigid headset in front of an
   AprilGrid. Keep the first 2-3 seconds still, then include rotation and translation excitation.
2. Build a Kalibr ROS1 bag:

```bash
python3 /data/scripts/images_imu_to_kalibr_bag.py \
  --config /data/configs/four_head_rig.yaml \
  --images-root /data/data/images \
  --experiment head_imucam_1600x1200_exp01 \
  --camera left_front \
  --imu-jsonl /data/data/imu/head_imu_exp01/head_imu.jsonl \
  --output /data/data/kalibr/head_imucam_1600x1200_exp01/head_imucam.bag
```

3. Export Kalibr IMU noise YAML from the static estimate:

```bash
python scripts/export_kalibr_imu_yaml.py \
  --imu-noise imu_calibration/static/head_imu_exp01/head_imu_noise.yaml \
  --sensor-id head_imu \
  --rate 200 \
  --output imu_calibration/kalibr_head_imu.yaml
```

Use `--rate` for the intended IMU output rate. WT BLE host receive timestamps can arrive in bursts,
so the raw median timestamp rate in a static JSONL may be higher than the physical sensor rate.

4. Run Kalibr camera-IMU calibration inside the Kalibr container. Example for one camera:

```bash
rosrun kalibr kalibr_calibrate_imu_camera \
  --bag /data/data/kalibr/head_imucam_1600x1200_exp01/head_imucam.bag \
  --cam /data/data/kalibr/head_imucam_1600x1200_exp01/camchain.yaml \
  --imu /data/imu_calibration/kalibr_head_imu.yaml \
  --target /data/data/targets/aprilgrid_6x6_088.yaml \
  2>&1 | tee /data/data/kalibr/head_imucam_1600x1200_exp01/head_imucam-kalibr.log
```

5. Convert Kalibr's camera-IMU result into `T_H_IH` using your already reviewed camera extrinsic:

```text
T_H_IH = T_H_C0 * T_C0_IH
```

If Kalibr provides `T_IH_C0`, invert it first.

## Wrist IMU

The wrist IMU is fixed to the wristband, not to the head cameras. Calibrate:

```text
T_B_IB
```

Current wristband frame `B` convention:

```text
origin: wristband geometric center
+X: along the back-of-hand plane toward the fingers
+Y: toward the left side of the hand
+Z: outward normal from the back of the hand; points upward when the back of the hand faces up
```

This is a right-handed frame:

```text
+X cross +Y = +Z
```

Recommended split:

- Translation `t_B_IB`: CAD, PCB layout, or physical measurement from IMU chip origin to wristband center.
- Rotation `R_B_IB`: start from datasheet/PCB axes, then refine with visual/gyro dynamic fitting.

Current measured wrist IMU translation:

```text
t_B_IB = [0.0, 0.0, -0.034] m
```

This means the wrist IMU origin is 34 mm along `B -Z` from the wristband center.

Current measured wrist IMU axis mapping:

```text
IMU +X = B -X
IMU +Y = B -Y
IMU +Z = B +Z
```

So:

```text
R_B_IB =
[[-1,  0, 0],
 [ 0, -1, 0],
 [ 0,  0, 1]]
```

Dynamic fitting uses:

```text
wrist_imu.jsonl
wrist_visual_pose.jsonl  # visual T_H_B from AprilTags
```

The script estimates:

```text
omega_B_visual ~= R_B_IB * omega_IB
```

## Static IMU Intrinsics Workflow

This workflow estimates prototype-stage IMU noise and bias from a static capture. It does not estimate
full scale/misalignment.

### 1. Install BLE Support

From the VimasCalibration repository root:

```bash
python -m pip install -e ".[ble]"
```

### 2. Prepare the IMU

Place the IMU on a stable surface and keep it completely still for the whole capture. Avoid touching
the table, cable, headset, or wristband during recording.

Use at least 60 seconds for a quick prototype estimate. Use several minutes if you want a more stable
first-pass number.

### 3. Capture and Estimate Head IMU Intrinsics

Optional scan:

```bash
python scripts/calibrate_imu_static.py --scan
```

If that does not show the device, list every BLE device:

```bash
python scripts/calibrate_imu_static.py --scan-all --scan-timeout-s 12
```

If only one WT/FFE IMU is powered nearby, this one command scans, connects, records, analyzes, and
exports the first-pass intrinsic estimate:

```bash
python scripts/calibrate_imu_static.py \
  --sensor-id head_imu \
  --duration-s 60 \
  --output-dir imu_calibration/static/head_imu_exp01
```

Expected outputs:

```text
imu_calibration/static/head_imu_exp01/head_imu.jsonl
imu_calibration/static/head_imu_exp01/head_imu_analysis.yaml
imu_calibration/static/head_imu_exp01/head_imu_noise.yaml
```

### 4. Capture and Estimate Wrist IMU Intrinsics

For the wrist IMU, use a separate output folder:

```bash
python scripts/calibrate_imu_static.py \
  --sensor-id wrist_imu \
  --duration-s 60 \
  --output-dir imu_calibration/static/wrist_imu_exp01
```

Expected outputs:

```text
imu_calibration/static/wrist_imu_exp01/wrist_imu.jsonl
imu_calibration/static/wrist_imu_exp01/wrist_imu_analysis.yaml
imu_calibration/static/wrist_imu_exp01/wrist_imu_noise.yaml
```

### 5. Choose a Specific BLE Device

If both head and wrist IMUs are powered on, the auto-scan may pick the first discovered device. In
that case, pass the BLE address explicitly:

```bash
python scripts/calibrate_imu_static.py \
  --sensor-id head_imu \
  --address C4:65:91:2C:E2:20 \
  --duration-s 60 \
  --output-dir imu_calibration/static/head_imu_exp01 \
  --overwrite
```

Use `--overwrite` only when you intentionally want to replace an existing capture in that folder.

### 6. Check the Result

Open the analysis file and check:

```text
timestamp_monotonic: true
accel_norm_mps2.mean: close to 9.80665
gyro_norm_radps.mean: close to 0 while static
sample_count: non-trivial, usually thousands of samples for WT BLE streams
```

Example:

```bash
sed -n '1,120p' imu_calibration/static/head_imu_exp01/head_imu_analysis.yaml
```

The noise YAML contains the values to use as prototype OpenVINS/ESKF parameters:

```bash
sed -n '1,120p' imu_calibration/static/head_imu_exp01/head_imu_noise.yaml
```

### 7. Combine Existing Static JSONL Files

Analyze one IMU JSONL:

```bash
python scripts/analyze_imu_jsonl.py \
  ../3DMotion/data/raw/session_YYYYMMDD_HHMMSS/imus/head_imu.jsonl
```

Export first-pass noise/bias YAML:

```bash
python scripts/export_imu_noise_yaml.py \
  --head-imu ../3DMotion/data/raw/session_YYYYMMDD_HHMMSS/imus/head_imu.jsonl \
  --wrist-imu ../3DMotion/data/raw/session_YYYYMMDD_HHMMSS/imus/wrist_imu.jsonl \
  --output imu_calibration/imu_noise.yaml
```

This is a quick static estimate, not a replacement for Allan variance.

## Extrinsics Templates

Generate identity templates:

```bash
python scripts/export_imu_extrinsics_template.py \
  --output imu_calibration/imu_extrinsics.yaml
```

Generate with measured translations:

```bash
python scripts/export_imu_extrinsics_template.py \
  --head-translation 0.0,0.0,0.0 \
  --wrist-translation 0.0,0.0,-0.034 \
  --output imu_calibration/imu_extrinsics.yaml
```

Fit wrist rotation from visual pose and gyro:

```bash
python scripts/fit_wrist_imu_to_bracelet_rotation.py \
  --wrist-imu ../3DMotion/data/raw/session_YYYYMMDD_HHMMSS/imus/wrist_imu.jsonl \
  --wrist-visual ../3DMotion/data/processed/session_YYYYMMDD_HHMMSS/wrist_visual/wrist_visual_pose.jsonl \
  --translation 0.0,0.0,-0.034 \
  --output imu_calibration/wrist_imu_extrinsics.yaml
```

## Downstream Handoff

VimasCalibration does not write into downstream repositories. After reviewing units, frame
conventions, and transform directions, copy final values into the downstream project's local config
files.

For 3DMotion, the expected destinations are:

```text
configs/frames.yaml            # T_H_IH, T_B_IB, frame conventions
configs/imu_calibration.yaml    # head_imu and wrist_imu noise/bias estimates
configs/cameras.yaml            # T_H_C for each camera, from camera extrinsics
```

3DMotion should then be checked from its own repo:

```bash
python scripts/check_calibration_readiness.py
```

For wrist fusion, `T_B_IB` should be consumed by the future wrist ESKF so IMU propagation and
AprilTag visual correction share the same wristband frame `B`.
