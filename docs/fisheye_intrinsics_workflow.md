# 单个鱼眼相机内参流程

## 1. 固定采集档位

先选定最终会使用的相机输出模式，例如：

```text
MJPG 1600x1200 @ 25fps
```

只要切换分辨率、裁剪比例、ISP 路径、dewarp/LDC/EIS/digital zoom，就必须重新标定。
标定时尽量关闭自动畸变校正、电子防抖、动态裁剪和数字变焦。

## 2. 先用 A4 AprilGrid 跑通链路

A4 AprilGrid 只用于确认打印、采集、检测和标定命令能跑通，不作为最终鱼眼内参。

先生成 Kalibr target YAML。这里的 `tagSpacing` 是比例：

```text
tagSpacing = 相邻 tag 之间的白色空隙 / tag 黑色边长
```

```bash
python scripts/generate_kalibr_aprilgrid.py \
  --tag-cols 6 \
  --tag-rows 6 \
  --tag-size-m 0.025 \
  --tag-spacing 0.3 \
  --output data/targets/aprilgrid_6x6_025_a4.yaml
```

优先用 Kalibr 官方工具生成 PDF，避免 OpenCV 生成图案和 Kalibr detector 不兼容。
在 Kalibr 容器里执行：

```bash
source devel/setup.bash
rosrun kalibr kalibr_create_target_pdf \
  --type apriltag \
  --nx 6 \
  --ny 6 \
  --tsize 0.025 \
  --tspace 0.3 \
  --tfam t36h11 \
  /data/data/targets/kalibr_aprilgrid_6x6_025_a4.pdf
```

如果只是想快速预览或没有进入 Kalibr 容器，也可以用仓库脚本生成 SVG/PNG：

```bash
python scripts/generate_kalibr_aprilgrid_artwork.py \
  --target-yaml data/targets/aprilgrid_6x6_025_a4.yaml \
  --margin-m 0.005 \
  --output-svg data/targets/aprilgrid_6x6_025_a4.svg \
  --output-png data/targets/aprilgrid_6x6_025_a4.png
```

打印 PDF/SVG 时选择 100% / actual size / 不缩放。打印后必须测量实体板，并把
实测值回填 target YAML。

要测两项：

```text
tag-size-mm: 单个黑色 tag 的边长
gap-mm: 相邻两个 tag 黑色边之间的白色空隙
```

例如实测 tag 边长是 `24.0 mm`，白色空隙是 `7.5 mm`：

```bash
python scripts/update_aprilgrid_measurement.py \
  --target-yaml data/targets/aprilgrid_6x6_025_a4.yaml \
  --tag-size-mm 24.0 \
  --gap-mm 7.5
```

这会写入：

```yaml
tagSize: 0.024
tagSpacing: 0.2916666666666667
```

不要把 `tagSpacing` 写成 `0.007` 或 `0.7`；它不是米，也不是毫米，是 `gap / tagSize`。

## 3. 正式标定换标准大板

220-240 度鱼眼需要大板覆盖画面中心、上下左右边缘和圆周边缘。建议 A1/A0
级硬板，哑光纸贴硬质平板。

```bash
python scripts/generate_kalibr_aprilgrid.py \
  --tag-cols 6 \
  --tag-rows 6 \
  --tag-size-m 0.088 \
  --tag-spacing 0.3 \
  --output data/targets/aprilgrid_6x6_088.yaml
```

在 Kalibr 容器里生成官方 PDF：

```bash
source devel/setup.bash
rosrun kalibr kalibr_create_target_pdf \
  --type apriltag \
  --nx 6 \
  --ny 6 \
  --tsize 0.088 \
  --tspace 0.3 \
  --tfam t36h11 \
  /data/data/targets/kalibr_aprilgrid_6x6_088.pdf
```

可选生成 SVG/PNG 预览：

```bash
python scripts/generate_kalibr_aprilgrid_artwork.py \
  --target-yaml data/targets/aprilgrid_6x6_088.yaml \
  --output-svg data/targets/aprilgrid_6x6_088.svg \
  --output-png data/targets/aprilgrid_6x6_088.png
```

打印后同样用 `update_aprilgrid_measurement.py` 按实测 tag 边长和白色空隙回填
`data/targets/aprilgrid_6x6_088.yaml`。

## 4. 采集单路数据

先确认相机设备：

```bash
python scripts/list_cameras.py --max-index 12 --require-frame
```

采集单路图像，用稳定的 `/dev/video*` 或 `/dev/v4l/by-path/*`：

```bash
python scripts/capture_camera.py \
  --source /dev/video0 \
  --camera left_front \
  --experiment main_1600x1200_exp01 \
  --width 1600 \
  --height 1200 \
  --fps 25 \
  --fourcc MJPG \
  --max-images 120 \
  --interval 0
```

采集要求：

- 保留 80-150 张有效图，最低不要少于 40 张。
- 标定板覆盖中心、上下左右边缘、四角/圆周边缘。
- 包含近/中/远距离，姿态有 pitch、yaw、roll 变化。
- 避免反光、运动模糊、过曝和板子弯曲。

## 5. Kalibr 主线

Ubuntu 22.04 上建议通过 Docker 使用 Kalibr：

```bash
scripts/kalibr_docker.sh build
scripts/kalibr_docker.sh shell
source devel/setup.bash
```

在容器里，仓库被挂载到 `/data`。如果你是用 `capture_camera.py` 采的图片，
需要先在容器里把图片序列转成 ROS1 bag：

```bash
python3 /data/scripts/images_to_rosbag.py \
  --images /data/data/images/left_front/main_1600x1200_exp01 \
  --output /data/data/kalibr/main_1600x1200_exp01/left_front.bag \
  --topic /left_front/image_raw \
  --fps 25 \
  --frame-id left_front
```

A4 测试阶段可先跑：

```bash
rosrun kalibr kalibr_calibrate_cameras \
  --bag /data/data/kalibr/main_1600x1200_exp01/left_front.bag \
  --topics /left_front/image_raw \
  --models ds-none \
  --target /data/data/targets/aprilgrid_6x6_025_a4.yaml \
  --show-extraction \
  2>&1 | tee /data/data/kalibr/main_1600x1200_exp01/left_front-kalibr.log
```

回到宿主机后，用 Kalibr 日志计算真实图像通过率：

```bash
python scripts/kalibr_pass_rate.py \
  data/kalibr/main_1600x1200_exp01/left_front-kalibr.log
```

输出里的 `used_images / total_images` 是 Kalibr 自己实际接受的 observation 比例。

正式阶段用标准大板重新采 bag，并把 `--target` 换成标准大板 YAML。模型比较顺序：

```text
ds-none -> eucm-none -> omni-radtan
```

## 6. OpenCV Fallback

如果暂时没有 Kalibr，可以用 ChArUco + OpenCV fisheye 跑单目 fallback。

生成 ChArUco 板：

```bash
python scripts/generate_charuco.py \
  --cols 8 \
  --rows 11 \
  --square-px 140 \
  --marker-ratio 0.72 \
  --output data/patterns/charuco_8x11.png
```

打印后测量真实棋盘格边长，假设为 `22.0 mm`：

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

结果默认写到：

```text
data/results/left_front/main_1600x1200_exp01/charuco/calibration.yaml
```

生成去畸变预览：

```bash
python scripts/analyze_experiments.py \
  --camera left_front \
  --method charuco \
  --experiments main_1600x1200_exp01 \
  --undistort
```

如果使用 Kalibr `ds-none` 结果，可以用 Double Sphere 去畸变预览脚本：

```bash
python scripts/undistort_kalibr_ds.py \
  --camchain data/kalibr/main_1600x1200_exp01/left_side-camchain.yaml \
  --camera cam0 \
  --images data/images/left_side/main_1600x1200_exp01 \
  --output-dir data/analysis/left_side/main_1600x1200_exp01/ds_undistort \
  --limit 8
```

输出是原图和 rectilinear 预览的 side-by-side 图片。`--rectified-focal-px` 可以调节
预览视场：数值越小视场越大、黑边和拉伸越明显；数值越大视场越窄。

## 7. 质量检查

Kalibr 输出数字、真实图像通过率和 RMS 的详细解释见：

[kalibr_report_guide.md](kalibr_report_guide.md)

OpenCV fisheye fallback 第一轮不要用普通相机的 `<1 px` 门槛：

```text
RMS < 5 px       优先候选
5-10 px          可诊断/可初筛
RMS > 10 px      回查模型、覆盖、角点和图像模式
```

还要看：

- 残差是否集中在画面边缘。
- 主点是否离图像中心过远。
- 多次采集/标定结果是否稳定。
- `used_images` 是否覆盖完整有效成像圆。

单目内参稳定后，再按同样流程采集其他相机；需要多相机外参时，再使用四路/多路
标定流程。
