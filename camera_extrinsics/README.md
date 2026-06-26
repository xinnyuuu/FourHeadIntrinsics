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

## 6. Kalibr Multi-Camera Workflow

Use this path when adjacent headset cameras can see the same AprilGrid at the same time.

### Capture

Use the same capture mode as intrinsics, for example `1600x1200 MJPG 25fps`. Capture synchronized
image sequences into:

```text
data/images/left_side/<experiment>/
data/images/left_front/<experiment>/
data/images/right_front/<experiment>/
data/images/right_side/<experiment>/
```

Move the AprilGrid through the overlapping regions:

```text
left_side + left_front
left_front + right_front
right_front + right_side
```

Keep many frames where each neighboring pair sees the board together. Kalibr needs these shared
observations to estimate camera-to-camera transforms.

### Build a Multi-Camera ROS Bag

Inside the Kalibr container:

```bash
python3 /data/scripts/images_to_multicam_rosbag.py \
  --config /data/configs/four_head_rig.yaml \
  --images-root /data/data/images \
  --experiment extrinsics_1600x1200_exp01 \
  --output /data/data/kalibr/extrinsics_1600x1200_exp01/four_head.bag
```

This writes four topics:

```text
/left_side/image_raw
/left_front/image_raw
/right_front/image_raw
/right_side/image_raw
```

The topic order must match `configs/four_head_rig.yaml`. Kalibr names cameras by topic order:

```text
cam0 = left_side
cam1 = left_front
cam2 = right_front
cam3 = right_side
```

### Run Kalibr

Use the model that won your intrinsics comparison. Example with `omni-radtan`:

```bash
rosrun kalibr kalibr_calibrate_cameras \
  --bag /data/data/kalibr/extrinsics_1600x1200_exp01/four_head.bag \
  --topics /left_side/image_raw /left_front/image_raw /right_front/image_raw /right_side/image_raw \
  --models omni-radtan omni-radtan omni-radtan omni-radtan \
  --target /data/data/targets/aprilgrid_6x6_088.yaml \
  --show-extraction \
  2>&1 | tee /data/data/kalibr/extrinsics_1600x1200_exp01/four_head-kalibr.log
```

Kalibr should output a `*-camchain.yaml`. For multi-camera results, `cam1`, `cam2`, etc. should
contain `T_cn_cnm1`.

### Export `T_head_camera`

If you only need relative camera extrinsics first, use cam0 as the temporary Head frame:

```bash
python scripts/export_kalibr_extrinsics.py \
  --config configs/four_head_rig.yaml \
  --camchain data/kalibr/extrinsics_1600x1200_exp01/four_head-camchain.yaml \
  --output camera_extrinsics/four_head_camera_extrinsics.yaml
```

This assumes:

```text
T_head_camera0 = identity
```

If you have measured the real Head frame relative to `cam0`, create a YAML:

```yaml
T_head_camera:
  rotation_matrix:
    - [1.0, 0.0, 0.0]
    - [0.0, 1.0, 0.0]
    - [0.0, 0.0, 1.0]
  translation_m: [0.0, 0.0, 0.0]
```

Then export:

```bash
python scripts/export_kalibr_extrinsics.py \
  --config configs/four_head_rig.yaml \
  --camchain data/kalibr/extrinsics_1600x1200_exp01/four_head-camchain.yaml \
  --t-head-cam0 camera_extrinsics/T_head_cam0.yaml \
  --output camera_extrinsics/four_head_camera_extrinsics.yaml
```

The exporter uses Kalibr's convention:

```text
camN.T_cn_cnm1 maps points from cam(N-1) frame into camN frame.
```

So the chain is inverted internally before writing `T_head_camera`.

### Downstream handoff

After reviewing the result, copy each camera's `T_head_camera` into the downstream project using its
local naming convention. For 3DMotion, this value is `T_H_C` in `configs/cameras.yaml`.

Do not copy blindly:

```text
cam0 = first Kalibr topic
cam1 = second Kalibr topic
...
```

The Kalibr topic order must match the camera order documented in `configs/four_head_rig.yaml`.
