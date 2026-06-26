# VimasCalibration

VIMAS 头环/手环 camera + IMU 标定工具包。这个仓库分成三块：

- `camera_intrinsics/`：相机内参、畸变、Kalibr/OpenCV 流程说明。
- `camera_extrinsics/`：相机相对头环 Head frame 的外参定义、模板和测量流程说明。
- `imu_calibration/`：Head IMU、Wrist IMU 外参和 noise/bias 初步统计流程。

VimasCalibration 是独立标定仓库：它负责采集、估计和导出标定结果；下游工程
例如 3DMotion 只消费自己仓库内的配置文件。跨仓库交接时应人工审阅坐标系、单位和
transform 方向，不在本仓库维护“一键写入 3DMotion”的脚本。

当前物理顺序：

```text
left_side -> left_front -> right_front -> right_side
```

只要切换分辨率、裁剪比例、ISP 路径、dewarp/LDC/EIS/digital zoom，就必须重新标定。

## 环境

```bash
cd ~/lxy/VimasCalibration
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

## 推荐路线

对 1.4mm、220-240 度对角 FOV 模组，推荐优先使用：

```text
Kalibr + AprilGrid
模型比较顺序：ds-none -> eucm-none -> omni-radtan
```

OpenCV `fisheye` + ChArUco 是 fallback，用于先跑通采集/检测/结果检查，
或只使用约 180 度以内有效区域时做对照。

## 工作流程

相机内参流程：

[docs/fisheye_intrinsics_workflow.md](docs/fisheye_intrinsics_workflow.md)

相机到 Head frame 的外参流程：

[camera_extrinsics/README.md](camera_extrinsics/README.md)

Head/Wrist IMU 标定流程：

[imu_calibration/README.md](imu_calibration/README.md)

## 输出成果物

标定完成后，重点保留这些 YAML：

```text
data/results/four_camera_intrinsics.yaml             # 四目内参汇总
camera_extrinsics/four_head_camera_extrinsics.yaml  # T_head_camera / T_H_C 候选
imu_calibration/imu_extrinsics.yaml                  # T_H_IH / T_B_IB
imu_calibration/static/*/*_noise.yaml                # head_imu / wrist_imu noise and bias
imu_calibration/kalibr_head_imu.yaml                 # Kalibr camera-IMU 标定用 imu.yaml
```

交给 3DMotion 前，人工确认：

```text
transform direction: T_A_B maps B-frame points into A-frame
translation unit: meters
camera order: left_side -> left_front -> right_front -> right_side
IMU units: m/s^2 and rad/s
```

没有大幅面打印机时，用 A4 分块打印再拼贴 AprilGrid 的方案见：

[docs/a4_tiled_aprilgrid_plan.md](docs/a4_tiled_aprilgrid_plan.md)

Kalibr 输出、真实图像通过率和重投影误差的字段解释见：

[docs/kalibr_report_guide.md](docs/kalibr_report_guide.md)

## 常用入口

确认相机：

```bash
python scripts/list_cameras.py --max-index 12 --require-frame
```

采集单路图像：

```bash
python scripts/capture_camera.py \
  --source /dev/video0 \
  --camera left_front \
  --experiment main_1600x1200_exp01 \
  --max-images 120
```

OpenCV fallback 标定：

```bash
python scripts/calibrate_camera.py \
  --method charuco \
  --camera-model fisheye \
  --camera left_front \
  --experiment main_1600x1200_exp01 \
  --cols 8 \
  --rows 11 \
  --square-size 22.0 \
  --marker-ratio 0.72 \
  --max-error 5.0 \
  --auto-filter
```

四路结果汇总：

```bash
python scripts/export_rig_yaml.py \
  --config configs/four_head_rig.yaml \
  --results-root data/results \
  --experiment main_1600x1200_exp01 \
  --method charuco \
  --output data/results/four_camera_intrinsics.yaml
```

## 维护检查

```bash
python -m py_compile $(rg --files scripts src -g '*.py')
for f in scripts/*.py; do python "$f" --help >/tmp/help.out || exit 1; done
```
