# FourHeadIntrinsics

四目头环独立 USB/UVC 摄像头标定辅助工具。当前物理顺序：

```text
left_side -> left_front -> right_front -> right_side
```

当前 3D Motion 原型主线档位：

```text
MJPG 1600x1200 @ 25fps
```

`800x600 @ 60fps` 或 `640x480 @ 60fps` 只用于压测和排障。只要切换分辨率、裁剪比例、ISP 路径、dewarp/LDC/EIS/digital zoom，就必须重新标定。

## 推荐路线

对 1.4mm、220-240 度对角 FOV 模组，不要把普通 pinhole/chessboard 当最终主线。推荐：

```text
Kalibr + AprilGrid
模型比较顺序：ds-none -> eucm-none -> omni-radtan
```

仓库内置的 OpenCV `fisheye` 标定是 fallback，用于先跑通当前 3D Motion 原型链路，或只使用约 180 度以内有效区域时做对照。完整计划和验收标准见 [docs/3dmotion_calibration_workflow.md](docs/3dmotion_calibration_workflow.md)。

## 环境

```bash
cd ~/lxy/FourHeadIntrinsics
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

## 确认相机

```bash
python scripts/list_cameras.py --max-index 12 --require-frame
```

把稳定的 `/dev/video*` 或 `/dev/v4l/by-path/*` 写入 [configs/four_head_rig.yaml](configs/four_head_rig.yaml)。

## Kalibr 主线准备

生成 AprilGrid target YAML：

```bash
python scripts/generate_kalibr_aprilgrid.py \
  --tag-cols 6 \
  --tag-rows 6 \
  --tag-size-m 0.088 \
  --tag-spacing 0.3 \
  --output data/targets/aprilgrid_6x6_088.yaml
```

打印后必须重新测量真实 `tagSize` 和 spacing。采集 Kalibr bag 后，先分别比较：

```bash
kalibr_calibrate_cameras --bag cam0.bag --topics /cam0/image_raw --models ds-none --target data/targets/aprilgrid_6x6_088.yaml --bag-freq 4.0 --show-extraction
kalibr_calibrate_cameras --bag cam0.bag --topics /cam0/image_raw --models eucm-none --target data/targets/aprilgrid_6x6_088.yaml --bag-freq 4.0 --show-extraction
kalibr_calibrate_cameras --bag cam0.bag --topics /cam0/image_raw --models omni-radtan --target data/targets/aprilgrid_6x6_088.yaml --bag-freq 4.0 --show-extraction
```

Kalibr `camchain.yaml` 可导入 3D Motion：

```bash
python scripts/import_kalibr_camchain_to_3dmotion.py \
  --camchain data/kalibr/main_1600x1200_exp01/camchain.yaml \
  --output ../3DMotion/configs/cameras.yaml \
  --existing ../3DMotion/configs/cameras.yaml \
  --profile-name kalibr_main_1600x1200_25fps \
  --format MJPG \
  --fps 25
```

注意：当前 3D Motion AprilTag/OpenVINS 代码不能直接消费 `ds/eucm/omni`，导入脚本会保留参数元数据；下游会明确报错，避免误当 pinhole 使用。

## OpenCV Fallback

采集单路标定图：

```bash
python scripts/capture_camera.py \
  --source /dev/video0 \
  --camera left_side \
  --experiment main_1600x1200_exp01 \
  --max-images 100
```

默认采集参数已经是 `1600x1200 / 25fps / MJPG`。鱼眼需要覆盖完整有效成像圆，每路建议保留 80-150 张有效图。

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

生成去畸变预览：

```bash
python scripts/analyze_experiments.py \
  --camera left_side \
  --method charuco \
  --experiments main_1600x1200_exp01 \
  --undistort
```

四路 fallback 批量标定：

```bash
python scripts/calibrate_rig.py \
  --config configs/four_head_rig.yaml \
  --images-root data/images \
  --results-root data/results \
  --experiment main_1600x1200_exp01 \
  --method charuco \
  --square-size 22.0 \
  --cols 8 \
  --rows 11 \
  --marker-ratio 0.72 \
  --max-error 5.0 \
  --output data/results/four_camera_intrinsics.yaml
```

或从已有单路结果导出四路 YAML：

```bash
python scripts/export_rig_yaml.py \
  --config configs/four_head_rig.yaml \
  --results-root data/results \
  --experiment main_1600x1200_exp01 \
  --method charuco \
  --output data/results/four_camera_intrinsics.yaml
```

导出给 3D Motion：

```bash
python scripts/export_3dmotion_cameras_yaml.py \
  --intrinsics data/results/four_camera_intrinsics.yaml \
  --output ../3DMotion/configs/cameras.yaml \
  --existing ../3DMotion/configs/cameras.yaml \
  --profile-name offline_main_1600x1200_25fps \
  --format MJPG \
  --fps 25
```

## Fallback 质量门槛

OpenCV fisheye fallback 第一轮不要用普通相机的 `<1 px` 门槛：

```text
RMS < 5 px       优先候选
5-10 px          可诊断/可初筛
RMS > 10 px      检查模型、角点、板尺寸、边缘覆盖和图像模式
```

还要看残差分布、边缘误差、主点是否接近 `(width/2, height/2)`、多次实验结果是否稳定。不要只看总 RMS。

## 维护检查

不依赖硬件的基本检查：

```bash
python -m py_compile $(rg --files scripts src -g '*.py')
for f in scripts/*.py; do python "$f" --help >/tmp/help.out || exit 1; done
```
