# Kalibr 输出和诊断报告说明

这份文档解释 FourHeadIntrinsics 流程里常见的输出文件和数字含义。

## 1. 常见输出文件

Kalibr 单目相机标定通常会生成：

```text
*-camchain.yaml
*-results-cam.txt
*-report-cam.pdf
```

含义：

```text
camchain.yaml       机器可读的相机模型、内参和外参结果
results-cam.txt    终端结果的文本版，适合快速看参数和误差
report-cam.pdf     图形报告，适合看重投影误差分布和角点覆盖
```

FourHeadIntrinsics 的 AprilGrid 诊断脚本会生成：

```text
aprilgrid_detection_report.csv
debug overlay images
```

它用于判断图片里是否能检测到 AprilTag，以及缺哪些 tag。

## 2. Double Sphere 模型

如果命令使用：

```bash
--models ds-none
```

Kalibr 输出里会看到：

```text
type: <class 'aslam_cv.libaslam_cv_python.DoubleSphereCameraGeometry'>
distortion: [] +- []
projection: [xi alpha fx fy cx cy] +- [std_xi std_alpha std_fx std_fy std_cx std_cy]
reprojection error: [mean_x, mean_y] +- [std_x, std_y]
```

`ds-none` 没有单独 distortion 参数，所以：

```text
distortion: [] +- []
```

`projection` 的 6 个参数是：

```text
xi, alpha    Double Sphere 投影形状参数
fx, fy       焦距，单位是像素
cx, cy       主点坐标，单位是像素
```

例如：

```text
projection: [ -0.08232586 0.58845726 434.52447003 432.50501323 795.85931371 592.18854838]
```

表示：

```text
xi    = -0.08232586
alpha =  0.58845726
fx    = 434.52447003 px
fy    = 432.50501323 px
cx    = 795.85931371 px
cy    = 592.18854838 px
```

如果图像是 `1600x1200`，图像中心是 `(800, 600)`。主点 `(795.86, 592.19)`
接近中心，通常是合理信号。

`+- [...]` 是参数不确定度，近似理解为标准差。越小通常说明这批数据对该参数约束越稳定。

## 3. Reprojection Error

例如：

```text
reprojection error: [-0.000022, 0.000002] +- [0.869667, 0.885830]
```

含义：

```text
mean_x = -0.000022 px
mean_y =  0.000002 px
std_x  =  0.869667 px
std_y  =  0.885830 px
```

平均误差接近 0 是正常的，因为优化会让整体残差居中。更有参考价值的是标准差：

```text
0.8-1.0 px    smoke test 通常可以接受
< 1 px        对清晰、大板、覆盖好的正式数据是不错信号
> 2-3 px      需要检查图像覆盖、板子尺寸、模型或角点质量
```

Kalibr 这里给的是 x/y 两个方向的误差标准差。为了得到一个更直观的二维像素误差，
可以计算：

```text
rms_2d = sqrt(std_x^2 + std_y^2)
```

例如：

```text
std_x = 0.869667 px
std_y = 0.885830 px
rms_2d = sqrt(0.869667^2 + 0.885830^2) = 1.241376 px
```

仓库提供了脚本直接从 Kalibr `*-results-cam.txt` 里计算：

```bash
python scripts/kalibr_reprojection_rms.py \
  data/kalibr/main_1600x1200_exp01/left_side-results-cam.txt
```

输出示例：

```text
mean_x_px: -0.000022
mean_y_px:  0.000002
std_x_px:   0.869667
std_y_px:   0.885830
rms_2d_px:  1.241376
```

对 `ds-none` 的经验参考：

```text
A4 smoke test:
  rms_2d < 2 px       链路测试通常可以接受

正式大板:
  rms_2d < 1.5 px     较好
  1.5-2.0 px          可诊断，需要结合覆盖和残差图判断
  > 2.0 px            建议检查采集、板尺寸、模型选择和角点质量
```

不要只看一个总误差。正式结果还要看：

```text
角点是否覆盖中心和边缘
边缘残差是否明显偏大
主点是否稳定
多次采集标定结果是否接近
```

## 4. 常见模型参数顺序

FourHeadIntrinsics 推荐先比较：

```text
ds-none -> eucm-none -> omni-radtan
```

常见参数顺序：

```text
ds-none:
  projection = [xi, alpha, fx, fy, cx, cy]
  distortion = []

eucm-none:
  projection = [alpha, beta, fx, fy, cx, cy]
  distortion = []

omni-radtan:
  projection = [xi, fx, fy, cx, cy]
  distortion = [k1, k2, r1, r2]
```

不同 Kalibr 版本的打印格式可能略有差异，最终以 `camchain.yaml` 里的字段为准。

## 5. AprilGrid 诊断 CSV

运行：

```bash
python scripts/diagnose_aprilgrid_images.py \
  --images data/images/left_front/main_1600x1200_exp01 \
  --target-yaml data/targets/aprilgrid_6x6_025_a4.yaml \
  --output-dir data/results/left_front/main_1600x1200_exp01/aprilgrid_debug
```

会生成：

```text
aprilgrid_detection_report.csv
```

字段含义：

```text
image                图片名
expected_seen        成功识别出的目标 tag 数
expected_total       target YAML 期望的 tag 总数
unexpected_count     识别出了但不在 target 范围内的 tag 数
rejected_candidates  看起来像 tag、但未能成功解码的候选框数量
seen_ids             成功识别出的目标 tag id
missing_ids          期望存在但没识别出的 tag id
unexpected_ids       不在 target 范围内的 tag id
```

例如：

```text
expected_seen=31/36
rejected_candidates=44
missing_ids=0 6 12 24 30
```

表示这张图成功识别了 36 个期望 tag 中的 31 个，另有 44 个疑似 tag 的候选轮廓
没有解码成功，并且缺了 `0, 6, 12, 24, 30` 这些 tag。

`rejected_candidates` 不是“图片被拒绝”，而是“疑似 tag 候选框没解码成功”。
它很多时，常见原因是：

```text
板子太近，鱼眼畸变太强
图像边缘拉伸严重
运动模糊、过曝、反光
打印边缘不够锐
tag 在图中太小
背景里有类似黑白块的干扰
```

这个诊断脚本使用 OpenCV AprilTag 检测器，不等同于 Kalibr 的检测器。OpenCV 能看到
`36/36` 只说明图里有 tag，不保证 Kalibr 一定能形成 valid grid observation。

## 6. 结果是否可用

A4 板、少量图片、只拍中心区域得到的结果只能说明链路跑通。正式鱼眼内参建议：

```text
标准大板
80-150 张有效图
覆盖中心、上下左右边缘、四角/圆周边缘
多距离、多角度
重复采集结果稳定
```

如果正式数据下 `reprojection std` 仍接近 1 px，主点合理，参数重复稳定，才更适合
作为下游工程使用的内参。
