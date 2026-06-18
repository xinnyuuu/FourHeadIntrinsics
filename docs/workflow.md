# 四目头环标定简版流程

详细计划见 [3dmotion_calibration_workflow.md](3dmotion_calibration_workflow.md)。这里保留最短操作入口，避免和详细文档重复。

## 1. 固定采集档位

当前 3D Motion 原型主线：

```text
MJPG 1600x1200 @ 25fps
```

切换分辨率、裁剪比例或 ISP/dewarp 路径后必须重新标定。

## 2. 首选 Kalibr 全向标定

生成 AprilGrid target：

```bash
python scripts/generate_kalibr_aprilgrid.py \
  --tag-cols 6 \
  --tag-rows 6 \
  --tag-size-m 0.088 \
  --tag-spacing 0.3 \
  --output data/targets/aprilgrid_6x6_088.yaml
```

采集 bag 后比较：

```text
ds-none
eucm-none
omni-radtan
```

把 Kalibr camchain 导入 3D Motion：

```bash
python scripts/import_kalibr_camchain_to_3dmotion.py \
  --camchain data/kalibr/main_1600x1200_exp01/camchain.yaml \
  --output ../3DMotion/configs/cameras.yaml \
  --existing ../3DMotion/configs/cameras.yaml
```

## 3. OpenCV Fallback

采集单路图像：

```bash
python scripts/capture_camera.py \
  --source /dev/video0 \
  --camera left_side \
  --experiment main_1600x1200_exp01 \
  --max-images 100
```

ChArUco fallback 标定：

```bash
python scripts/calibrate_camera.py \
  --method charuco \
  --camera-model fisheye \
  --camera left_side \
  --experiment main_1600x1200_exp01 \
  --cols 8 \
  --rows 11 \
  --square-size 22.0 \
  --marker-ratio 0.72 \
  --max-error 5.0 \
  --auto-filter
```

四路导出：

```bash
python scripts/export_rig_yaml.py \
  --experiment main_1600x1200_exp01 \
  --method charuco \
  --output data/results/four_camera_intrinsics.yaml
```

导出给 3D Motion：

```bash
python scripts/export_3dmotion_cameras_yaml.py \
  --intrinsics data/results/four_camera_intrinsics.yaml \
  --output ../3DMotion/configs/cameras.yaml \
  --existing ../3DMotion/configs/cameras.yaml
```

## 4. 验收重点

- 每路有效图建议 80-150 张，覆盖完整有效成像圆。
- 初筛 `RMS < 5 px` 优先，`5-10 px` 可诊断，`>10 px` 回查模型、覆盖、角点和图像模式。
- 不只看 RMS，还要看残差分布、边缘误差、主点、重复标定稳定性。
- 内参通过后再做多相机外参和 camera-IMU 标定。
