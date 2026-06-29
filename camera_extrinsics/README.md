# Camera Extrinsics

This folder is for camera-to-head extrinsics:

```text
T_head_camera_i
```

`T_head_camera_i` means a 3D point expressed in camera frame `C_i` is transformed into the
headset Head frame `H`:

```text
p_H = R_H_Ci * p_Ci + t_H_Ci
```

## 1. Define the Head Frame

Defining a Head frame means choosing an origin and axes that are fixed to the rigid headset.
It is a convention, not something the physical world gives automatically.

Recommended convention:

```text
origin: geometric center of the four-camera rigid cluster, or the midpoint between left_front and right_front
+X: forward
+Y: left
+Z: up
```

You can define this from CAD, a mechanical drawing, or careful physical measurement. The important
rule is consistency: every camera translation and rotation must be expressed relative to the same
Head frame.

Current measured Head frame origin for this prototype:

```text
H origin: user-measured headset center point
+X: forward toward the headset front
+Y: user's left
+Z: up

Measured headset width, left-right outer edge to outer edge: 0.176 m
H origin is the left-right midpoint: 0.088 m from either side edge

Measured distance from H origin to the frontmost outer edge: 0.107 m
With +X forward, the frontmost outer edge is at x = +0.107 m relative to H

Measured headset vertical thickness: 0.034 m
H origin is the vertical midpoint: 0.017 m from top and bottom outer edges
With +Z up, the top outer edge is at z = +0.017 m and the bottom outer edge is at z = -0.017 m
```

## 2. If You Measure Camera Pose Directly in Head Frame

If CAD or measurement gives camera axes and camera optical center directly in Head frame, write them
as `T_head_camera`.

Example:

```yaml
left_front:
  T_head_camera:
    rotation_matrix:
      - [0.0, 0.0, 1.0]
      - [-1.0, 0.0, 0.0]
      - [0.0, -1.0, 0.0]
    translation_m: [0.035, 0.045, 0.012]
```

`translation_m` is the camera origin position in Head frame, in meters.

## 3. If You Have the Opposite Transform

Sometimes tools output `T_camera_head`, meaning:

```text
p_C = R_C_H * p_H + t_C_H
```

Invert it before saving:

```text
R_H_C = R_C_H^T
t_H_C = -R_C_H^T * t_C_H
```

## 4. If You Have Camera-to-Camera Extrinsics

Choose one reference camera, define its transform to Head frame, then chain the rest.

If Kalibr gives:

```text
T_C0_C1
```

and you know:

```text
T_H_C0
```

then:

```text
T_H_C1 = T_H_C0 * T_C0_C1
```

Be careful with Kalibr field names. Some camera chains store transforms from the previous camera to
the current camera, and some documentation describes the inverse. Always verify by projecting a
known point or drawing the camera frustums.

## 5. Validation Checklist

- A point in front of each camera should land in front of the Head frame in the expected direction.
- Left cameras should have positive `Y` if `+Y` is left.
- Right cameras should have negative `Y` if `+Y` is left.
- Front cameras should usually have larger positive `X` than side cameras if `+X` is forward.
- Units must be meters.

Template:

- `templates/four_head_camera_extrinsics.yaml`

## 6. Three-Segment Four-Camera Workflow

Use this as the main four-camera extrinsics path. The goal is one connected Kalibr chain:

```text
left_side -- left_front -- right_front -- right_side
```

Kalibr names cameras by topic order, so the order in `configs/four_head_rig.yaml` is part of the
calibration result:

```text
cam0 = left_side
cam1 = left_front
cam2 = right_front
cam3 = right_side
```

Before capture, verify that the config matches the current physical `/dev/video*` mapping:

```bash
python scripts/list_cameras.py --max-index 8 --require-frame
cat configs/four_head_rig.yaml
```

Current config:

```text
left_side   -> /dev/video2
left_front  -> /dev/video0
right_front -> /dev/video6
right_side  -> /dev/video4
```

### 6.1 Capture Three Segments

Set one experiment id and capture the three neighboring overlaps. Press `SPACE` to save one
synchronized four-camera set.

```bash
EXP=exp03

python scripts/capture_multicam_extrinsics.py \
  --config configs/four_head_rig.yaml \
  --experiment extrinsics_ls_lf_${EXP} \
  --max-sets 80

python scripts/capture_multicam_extrinsics.py \
  --config configs/four_head_rig.yaml \
  --experiment extrinsics_lf_rf_${EXP} \
  --max-sets 80

python scripts/capture_multicam_extrinsics.py \
  --config configs/four_head_rig.yaml \
  --experiment extrinsics_rf_rs_${EXP} \
  --max-sets 80
```

For each segment, keep the AprilGrid visible in the intended pair:

```text
extrinsics_ls_lf_*: left_side + left_front
extrinsics_lf_rf_*: left_front + right_front
extrinsics_rf_rs_*: right_front + right_side
```

After capture, check the folders and image counts:

```bash
python scripts/check_multicam_capture.py \
  --config configs/four_head_rig.yaml \
  --experiment extrinsics_ls_lf_${EXP} \
  --require-equal-counts

python scripts/check_multicam_capture.py \
  --config configs/four_head_rig.yaml \
  --experiment extrinsics_lf_rf_${EXP} \
  --require-equal-counts

python scripts/check_multicam_capture.py \
  --config configs/four_head_rig.yaml \
  --experiment extrinsics_rf_rs_${EXP} \
  --require-equal-counts
```

### 6.2 Build Pair-Only Selection Files

These JSON files only choose which camera topics are present in each segment of the sparse bag.
They are not the final AprilGrid detection result; Kalibr still extracts the target from the real
images.

```bash
OUT=data/kalibr/extrinsics_three_segment_${EXP}
mkdir -p ${OUT}

python scripts/select_multicam_aprilgrid_observations.py \
  --config configs/four_head_rig.yaml \
  --experiment extrinsics_ls_lf_${EXP} \
  --output ${OUT}/ls_lf_selection.json \
  --allowed-cameras left_side left_front \
  --force-include-cameras left_side left_front \
  --required-pairs left_side+left_front \
  --min-tags 999

python scripts/select_multicam_aprilgrid_observations.py \
  --config configs/four_head_rig.yaml \
  --experiment extrinsics_lf_rf_${EXP} \
  --output ${OUT}/lf_rf_selection.json \
  --allowed-cameras left_front right_front \
  --force-include-cameras left_front right_front \
  --required-pairs left_front+right_front \
  --min-tags 999

python scripts/select_multicam_aprilgrid_observations.py \
  --config configs/four_head_rig.yaml \
  --experiment extrinsics_rf_rs_${EXP} \
  --output ${OUT}/rf_rs_selection.json \
  --allowed-cameras right_front right_side \
  --force-include-cameras right_front right_side \
  --required-pairs right_front+right_side \
  --min-tags 999
```

For example, with `EXP=exp03`, the three output files are:

```text
data/kalibr/extrinsics_three_segment_exp03/ls_lf_selection.json
data/kalibr/extrinsics_three_segment_exp03/lf_rf_selection.json
data/kalibr/extrinsics_three_segment_exp03/rf_rs_selection.json
```

### 6.3 Merge The Sparse Bag

Start the Kalibr container:

```bash
chmod +x scripts/kalibr_docker.sh
scripts/kalibr_docker.sh build
scripts/kalibr_docker.sh shell
```

Inside the container:

```bash
EXP=exp03
OUT=/data/data/kalibr/extrinsics_three_segment_${EXP}
mkdir -p ${OUT}

python3 /data/scripts/merge_multicam_experiments_to_rosbag.py \
  --config /data/configs/four_head_rig.yaml \
  --images-root /data/data/images \
  --experiment extrinsics_ls_lf_${EXP}:${OUT}/ls_lf_selection.json \
  --experiment extrinsics_lf_rf_${EXP}:${OUT}/lf_rf_selection.json \
  --experiment extrinsics_rf_rs_${EXP}:${OUT}/rf_rs_selection.json \
  --output ${OUT}/four_head_sparse.bag
```

The bag should contain four topics:

```text
/left_side/image_raw
/left_front/image_raw
/right_front/image_raw
/right_side/image_raw
```

### 6.4 Run Kalibr

Use the model that won the intrinsics comparison. Example with `omni-radtan`:

```bash
cd ${OUT}

rosrun kalibr kalibr_calibrate_cameras \
  --bag four_head_sparse.bag \
  --topics /left_side/image_raw /left_front/image_raw /right_front/image_raw /right_side/image_raw \
  --models omni-radtan omni-radtan omni-radtan omni-radtan \
  --target /data/data/targets/aprilgrid_6x6_025_a4.yaml \
  --show-extraction \
  2>&1 | tee four_head_sparse-kalibr.log
```

If `omni-radtan` fails during automatic intrinsic initialization, use the single-camera Kalibr
camchains as initial values and keep the same model:

```bash
python3 /data/scripts/kalibr_calibrate_cameras_with_init.py \
  --init-camchain /left_side/image_raw=/data/data/kalibr/main_1600x1200_exp03/left_side-camchain.yaml \
  --init-camchain /left_front/image_raw=/data/data/kalibr/leftfront_exp03/left_front-camchain.yaml \
  --init-camchain /right_front/image_raw=/data/data/kalibr/rightfront_exp03/right_front-camchain.yaml \
  --init-camchain /right_side/image_raw=/data/data/kalibr/rightside_exp03/right_side-camchain.yaml \
  --bag four_head_sparse.bag \
  --topics /left_side/image_raw /left_front/image_raw /right_front/image_raw /right_side/image_raw \
  --models omni-radtan omni-radtan omni-radtan omni-radtan \
  --target /data/data/targets/aprilgrid_6x6_025_a4.yaml \
  --dont-show-report \
  2>&1 | tee four_head_sparse_omni_init-camchain-kalibr.log
```

Kalibr should output a `*-camchain.yaml`. For multi-camera results, `cam1`, `cam2`, and `cam3`
should contain `T_cn_cnm1`.

### 6.5 Align To Head Frame

Back on the host, align Kalibr's relative rig into the measured Head frame using:

```text
camera_extrinsics/manual_camera_centers.yaml
```

Current reference camera centers:

```text
left_side:   [0.042,  0.142, -0.010] m
left_front:  [0.140,  0.072, -0.026] m
right_front: [0.138, -0.072, -0.026] m
right_side:  [0.042, -0.142, -0.010] m
```

```bash
EXP=exp03

python scripts/align_kalibr_rig_to_head.py \
  --config configs/four_head_rig.yaml \
  --camchain data/kalibr/extrinsics_three_segment_${EXP}/four_head_sparse-camchain.yaml \
  --manual-centers camera_extrinsics/manual_camera_centers.yaml \
  --output camera_extrinsics/four_head_camera_extrinsics.yaml
```

Review:

```text
alignment.rms_residual_m
alignment.max_residual_m
cameras.*.T_head_camera
```

Large residuals usually mean camera order, `/dev/video*` mapping, or one of the hand-measured
camera-center signs is wrong.

### 6.6 Export For 3DMotion

Generate a paste-in snippet without modifying the downstream repository:

```bash
python scripts/export_3dmotion_camera_extrinsics.py \
  --extrinsics camera_extrinsics/four_head_camera_extrinsics.yaml \
  --output camera_extrinsics/3dmotion_T_H_C_snippet.yaml
```

Then copy each `T_H_C` into `3DMotion/configs/cameras.yaml` after checking the camera ids:

```text
left_side   -> C0
left_front  -> C1
right_front -> C2
right_side  -> C3
```
