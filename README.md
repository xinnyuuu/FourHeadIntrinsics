# FourHeadIntrinsics

四目头环独立 USB/UVC 摄像头内参标定工具。当前四路物理顺序：

```text
左侧 -> 左前 -> 右前 -> 右侧
```

对应 camera key：

```text
left_side
left_front
right_front
right_side
```

推荐采集格式：

```text
640x480 YUYV @ 30fps
```

如果相机实际返回 `60 fps`，也可以继续做内参采图；关键是同一次实验内保持同一分辨率、格式和标定板参数。

## 1. 环境

```bash
cd ~/lxy/FourHeadIntrinsics
source .venv/bin/activate
```

首次安装：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

## 2. 确认相机节点

```bash
python scripts/list_cameras.py --max-index 12 --require-frame
```

只使用 `read_ok=True` 的 `source=/dev/videoX`。如果 `/dev/videoX` 重启后会变化，可以改用：

```bash
ls -l /dev/v4l/by-path/
```

并把稳定路径填入 [configs/four_head_rig.yaml](configs/four_head_rig.yaml)。

## 3. 多次实验目录结构

现在支持用 `--experiment` 手动指定第几次实验。目录会自动变成：

```text
data/images/<camera>/<experiment>/
data/results/<camera>/<experiment>/<method>/
```

例如左侧第 1 次实验：

```text
data/images/left_side/exp01/
data/results/left_side/exp01/chessboard/
```

左侧第 2 次实验：

```text
data/images/left_side/exp02/
data/results/left_side/exp02/chessboard/
```

这样每次实验都不会覆盖前一次结果。

## 4. 采集某次实验

左侧第 2 次实验示例：

```bash
python scripts/capture_camera.py \
  --source /dev/video2 \
  --camera left_side \
  --experiment exp02 \
  --width 640 \
  --height 480 \
  --fps 30 \
  --fourcc YUYV \
  --max-images 60 \
  --interval 0
```

窗口按键：

```text
空格 / s / Enter  保存一张
a                  开关自动保存
q / ESC            退出
```

旧用法仍然可用。如果你显式传 `--output`，脚本会使用这个目录，而不是自动生成实验目录。

## 5. 标定某次实验

棋盘格，左侧第 2 次实验：

```bash
python scripts/calibrate_camera.py \
  --method chessboard \
  --camera left_side \
  --experiment exp02 \
  --cols 9 \
  --rows 6 \
  --square-size 25.0 \
  --max-error 1.0 \
  --auto-filter
```

这会自动读取：

```text
data/images/left_side/exp02/
```

并写入：

```text
data/results/left_side/exp02/chessboard/calibration.yaml
data/results/left_side/exp02/chessboard/processed/
data/results/left_side/exp02/chessboard/debug/
```

ChArUco 交叉验证：

```bash
python scripts/calibrate_camera.py \
  --method charuco \
  --camera left_side \
  --experiment exp02 \
  --cols 8 \
  --rows 11 \
  --square-size 25.0 \
  --max-error 1.0 \
  --auto-filter
```

旧用法仍然可用。如果你显式传 `--images`、`--output`、`--processed-dir`、`--debug-dir`，脚本会使用这些路径。

## 6. 质量判断

对 `640x480` 图像，主点参考：

```text
cx ≈ 320
cy ≈ 240
```

经验值：

- `RMS < 0.5 px`：较好
- `0.5 <= RMS <= 1.0 px`：可用，但建议看 rejected 图
- `RMS > 1.0 px`：偏高，建议补拍或筛图
- 单张误差 `> 1.0 px`：优先检查该图片

如果 `--auto-filter --max-error 1.0` 后剩余图片少于 8 张，说明这次实验中高质量图片不足。建议重新拍一组，或先用较宽阈值诊断：

```bash
python scripts/calibrate_camera.py \
  --method chessboard \
  --camera left_side \
  --experiment exp02 \
  --cols 9 \
  --rows 6 \
  --square-size 22.0\
  --max-error 2.5 \
  --auto-filter
```

## 7. 内参和畸变参数怎么算出来

运行 `calibrate_camera.py` 时，脚本会先在每张图里检测标定板角点：

- 棋盘格：检测 9 x 6 个内部角点。
- ChArUco：先检测 ArUco marker，再插值得到 ChArUco 角点。

这些角点有两套坐标：

- `object_points`：标定板真实平面坐标。比如棋盘格第一个角点是 `(0, 0, 0)`，下一个是 `(square_size, 0, 0)`。
- `image_points`：相机图像里检测到的像素坐标，比如 `(u, v)`。

OpenCV 会用这些对应关系同时优化：

- `camera_matrix`：相机内参矩阵
- `dist_coeffs`：畸变系数
- 每张图中标定板相对于相机的姿态，也就是 `rvecs/tvecs`

棋盘格调用的是：

```python
cv2.calibrateCamera(object_points, image_points, image_size, None, None)
```

ChArUco 调用的是：

```python
cv2.aruco.calibrateCameraCharuco(...)
```

所以 `dist_coeffs` 不是你手动逐项计算出来的，而是 OpenCV 通过最小化重投影误差估计出来的。

### 7.1 camera_matrix

输出里的 `camera_matrix` 通常长这样：

```yaml
camera_matrix:
  - [fx, 0.0, cx]
  - [0.0, fy, cy]
  - [0.0, 0.0, 1.0]
```

含义：

- `fx/fy`：像素单位下的焦距。
- `cx/cy`：主点，理想情况下接近图像中心。
- 640x480 图像下，主点参考值是 `(320, 240)`。

### 7.2 dist_coeffs

本库默认使用 OpenCV 的 5 参数 plumb_bob 畸变模型：

```yaml
dist_coeffs:
  - k1
  - k2
  - p1
  - p2
  - k3
```

含义：

- `k1, k2, k3`：径向畸变，主要描述镜头从中心到边缘的桶形或枕形弯曲。
- `p1, p2`：切向畸变，主要来自镜头和成像平面不完全平行等装配误差。

简化理解：

```text
k 系数管“边缘弯不弯”
p 系数管“画面有没有轻微斜/偏”
```

OpenCV 内部会把理想归一化坐标 `(x, y)` 按下面的模型变成畸变后的坐标：

```text
r2 = x*x + y*y
x_distorted = x * (1 + k1*r2 + k2*r2*r2 + k3*r2*r2*r2) + 2*p1*x*y + p2*(r2 + 2*x*x)
y_distorted = y * (1 + k1*r2 + k2*r2*r2 + k3*r2*r2*r2) + p1*(r2 + 2*y*y) + 2*p2*x*y
```

标定的目标是：用 `camera_matrix + dist_coeffs + 每张图的姿态` 把标定板真实角点投影回图像，让投影点尽量贴近实际检测到的角点。

### 7.3 重投影误差

重投影误差就是：

```text
检测到的角点位置 - 用当前参数重新投影出来的角点位置
```

脚本会输出：

- `rms_reprojection_error_px`：整体 RMS。
- `per_view_errors_px`：每张图的误差。
- `per_view_error_summary`：单张误差的 mean/median/max/min。

一般判断：

- `< 0.5 px`：很好。
- `0.5 ~ 1.0 px`：可用。
- `> 1.0 px`：建议检查图片质量、棋盘格尺寸、角点分布。

### 7.4 多次实验怎么比较

对同一个相机、同一分辨率、同一标定板，比较多次实验时看这些字段：

```yaml
rms_reprojection_error_px
per_view_error_summary
valid_image_count
camera_matrix
dist_coeffs
```

推荐判断顺序：

1. `valid_image_count` 至少 20 张以上更稳，最低不要少于 8 张。
2. RMS 越低越好，但不能只看 RMS。
3. `cx/cy` 要接近 `(320, 240)`，明显偏离说明采集分布可能不均匀。
4. 同型号四路相机的 `fx/fy` 应该大体接近。
5. `dist_coeffs` 的趋势应相对稳定。比如同一相机多次实验中 `k1/k2/k3` 不应剧烈跳变。
6. 如果 ChArUco RMS 很低但 `cy` 明显偏离中心，也不能直接采用，应检查上下边缘覆盖。

最终推荐采用：RMS 低、主点合理、有效图充足、边缘和四角覆盖充分、畸变参数在多次实验中稳定的一组。

## 8. 标定板

棋盘格生成：

```bash
python scripts/generate_chessboard.py \
  --cols 10 \
  --rows 7 \
  --square-px 160 \
  --output data/patterns/chessboard_9x6_inner.png
```

这对应标定参数：

```text
--cols 9
--rows 6
```

打印后必须用尺量真实方格边长，`--square-size` 填真实值，例如 `21.5` 或 `25.0`。

## 9. 对比多次实验

每次实验结果都在独立目录里，例如：

```text
data/results/left_side/exp01/chessboard/calibration.yaml
data/results/left_side/exp02/chessboard/calibration.yaml
```

对比时重点看：

- `rms_reprojection_error_px`
- `per_view_error_summary`
- `valid_image_count`
- `camera_matrix` 里的 `fx/fy/cx/cy`
- `dist_coeffs`

最终优先选 RMS 低、主点接近 `(320, 240)`、有效图数量充足、rejected 图原因可解释的一次实验。

可以用脚本直接汇总某个相机的多次实验：

```bash
python scripts/analyze_experiments.py \
  --camera left_side \
  --method chessboard
```

输出是 CSV 风格表格，其中这些列就是畸变参数：

```text
k1,k2,p1,p2,k3
```

所有浮点参数会统一保留小数点后 6 位，终端输出和 `--csv` 文件一致。

也可以指定实验并保存 CSV：

```bash
python scripts/analyze_experiments.py \
  --camera left_side \
  --method chessboard \
  --experiments exp01 exp02 exp03 \
  --csv data/analysis/left_side_chessboard_summary.csv
```

## 10. 去畸变分析

生成原图 / 去畸变图并排对比：

```bash
python scripts/analyze_experiments.py \
  --camera left_side \
  --method chessboard \
  --experiments exp02 \
  --undistort \
  --undistort-limit 8
```

输出目录：

```text
data/analysis/left_side/exp02/chessboard/undistort/
```

每张图左边是原图，右边是 `camera_matrix + dist_coeffs` 去畸变后的结果。右图绿色框是 OpenCV 估计的有效 ROI。

去畸变图主要用来检查：

- 画面边缘直线是否变直。
- 去畸变后是否出现异常拉伸。
- `dist_coeffs` 是否过度补偿。
- 棋盘格边缘区域是否比原图更符合直线几何。

如果去畸变后画面明显扭曲得更奇怪，通常说明这次实验的畸变参数不可靠，需要回头检查采集覆盖、棋盘格平整度和 RMS。
