# FourHeadIntrinsics

四目头环鱼眼/全向相机标定辅助仓库。这个仓库只负责生成标定板、采集标定数据、
求单路/多路相机内参和外参，并把结果保存为本仓库自己的 YAML。下游工程如何消费
这些参数，不放在 FourHeadIntrinsics 里维护。

当前物理顺序：

```text
left_side -> left_front -> right_front -> right_side
```

只要切换分辨率、裁剪比例、ISP 路径、dewarp/LDC/EIS/digital zoom，就必须重新标定。

## 环境

```bash
cd ~/lxy/FourHeadIntrinsics
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

单个鱼眼相机内参、A4 测试板、正式大板、Kalibr Docker、OpenCV fallback 和质量检查
都统一维护在：

[docs/fisheye_intrinsics_workflow.md](docs/fisheye_intrinsics_workflow.md)

Kalibr 输出、重投影误差和 AprilGrid 诊断 CSV 的字段解释见：

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
