# 3D Motion 四鱼眼 / 全向相机标定计划

这份流程把超广角/全向相机标定方法和 3D Motion 当前采集档位对齐。核心判断：这个 1.4mm、220-240 度对角 FOV 模组不要按普通 pinhole 相机标定。标定分两层：

```text
第一层：每颗相机的内参 + 超广角/全向投影模型
第二层：多相机之间的外参；做 VIO 时再标相机-IMU 外参和时间偏移
```

内参必须对应真实录制的 `sensor mode + ISP path + format + width + height`，不能跨分辨率、跨裁剪比例复用。

## 1. 当前档位决策

3D Motion 当前离线主线使用：

```text
MJPG 1600x1200 @ 25fps
```

理由：

- 四路当前相机的共同 4:3 高质量档位。
- 比 16:9 更保留上下视野，适合手部、桌面和胸前操作区。
- 数据量比 5MP/4K 可控，方便 AprilTag、OpenVINS 和 rosbag2 反复离线处理。

需要额外标定的对照档位：

| 档位 | 用途 | 是否优先 |
| --- | --- | --- |
| `MJPG 1600x1200 @ 25fps` | 四路统一离线主线、AprilTag、OpenVINS 调试 | 必须先做 |
| `MJPG 800x600 @ 60fps` | 四路同步/USB 带宽压测、低负载追踪 | 主线完成后做 |
| `MJPG 1280x960 @ 60fps` | imx415 单路/双路高动态 A/B | 按需要做 |
| `MJPG 1920x1080 @ 60fps` | VLM/通用视频，不是追踪主线 | 按需要做 |

当前阶段 3D Motion 的 USB 相机主线是 `1600x1200`。目标头环的 1:1 鱼眼硬件到位后，要重新按最终输出模式标定，例如：

```text
2580x2580 原始鱼眼
2Kx2K 原始鱼眼
ISP dewarp 后图像
裁剪/缩放后的图像
```

固定最终模式时同时固定：

```text
分辨率 / sensor mode / 帧率 / 曝光 / 增益 / 焦距或对焦 / ISP 路径
```

除非最终算法就吃 ISP 校正后的图，否则标定时关闭：

```text
LDC / dewarp / EIS / digital zoom / 动态裁剪 / 自动畸变校正
```

## 2. 标定模型优先级

当前四路都是 1.4mm、约 220-240 度对角线 FOV 鱼眼，不再使用普通 pinhole/plumb_bob 作为主线模型。

首选路线：

```text
工具：Kalibr
标定板：AprilGrid
模型优先级：
1. ds-none
2. eucm-none
3. omni-radtan
```

OpenCV fisheye 路线只作为 fallback：

```text
只用中心区域 / 裁到约 180 度以内：
    可以试 OpenCV fisheye 或 Kalibr pinhole-equi

想用完整 220-240 度原始鱼眼图：
    优先 Kalibr ds-none / eucm-none / omni-radtan
    或后续接入 OpenCV omnidir / Mei unified model
```

FourHeadIntrinsics 内置的 OpenCV fallback 默认：

```text
camera_model: fisheye
distortion_model: opencv_fisheye
dist_coeffs: k1,k2,k3,k4
```

导出到 3D Motion / OpenVINS 时映射为：

```text
camera_model: fisheye
distortion_model: equidistant
```

注意：当前 3D Motion 的 AprilTag PnP 和 OpenVINS 生成器可以直接消费 `pinhole/radtan` 与 `fisheye/equidistant`。Kalibr 的 `ds/eucm/omni` 结果会被导入并保留元数据，但不会被当前下游静默当 pinhole 使用；下游会明确提示需要模型适配。

RMS 初筛阈值：

```text
RMS < 5 px       优先候选
5-10 px          可诊断/可初筛
RMS > 10 px      先检查采集、角点、板尺寸、边缘覆盖
```

## 3. 准备 AprilGrid

优先使用 AprilGrid，不要把普通棋盘格当主线。建议做 A1/A0 级硬板：

```text
tagSize: 0.06-0.10 m 起步
tagCols/tagRows: 6x6、7x6、8x6 都可以
材质：哑光纸 + 硬质平板
```

生成 Kalibr target YAML：

```bash
cd ~/lxy/FourHeadIntrinsics
source .venv/bin/activate

python scripts/generate_kalibr_aprilgrid.py \
  --tag-cols 6 \
  --tag-rows 6 \
  --tag-size-m 0.088 \
  --tag-spacing 0.3 \
  --output data/targets/aprilgrid_6x6_088.yaml
```

打印后必须重新测量实际 `tagSize` 和 spacing，不能相信打印设置。

## 4. 采集标定数据

每一路相机单独采图或录 bag，四路都要在同一档位下采集。OpenCV fallback 可直接用图片；Kalibr 主线建议录 ROS bag 或把图片序列转成 bag。

以 `left_side` 图片采集为例：

```bash
python scripts/capture_camera.py \
  --source /dev/video0 \
  --camera left_side \
  --experiment main_1600x1200_exp01 \
  --width 1600 \
  --height 1200 \
  --fps 25 \
  --fourcc MJPG \
  --max-images 80 \
  --interval 0
```

四路建议实验名保持一致：

```text
main_1600x1200_exp01
```

采集要求：

- 每路保留 80-150 张有效图；最低不要少于 40 张。
- 标定板覆盖整个有效成像圆，不要只拍正前方。
- 中心、左边缘、右边缘、上边缘、下边缘、四角/圆周边缘都要覆盖。
- 每个区域建议 10-20 张，并包含近/中/远距离。
- 姿态要有 pitch、yaw、roll 变化。
- 标定板保持平整，避免反光、运动模糊和过曝。
- 同一实验内不要切换分辨率、格式、焦距、ISP 路径或标定板尺寸。

## 5. Kalibr 单相机模型比较

单颗相机先跑 `ds-none`：

```bash
kalibr_calibrate_cameras \
  --bag data/kalibr/main_1600x1200_exp01/cam0.bag \
  --topics /cam0/image_raw \
  --models ds-none \
  --target data/targets/aprilgrid_6x6_088.yaml \
  --bag-freq 4.0 \
  --show-extraction
```

再分别跑：

```bash
--models eucm-none
--models omni-radtan
```

比较时不要只看总 RMS，还要看：

```text
残差是否均匀
边缘误差是否系统性爆炸
左右/上下残差是否对称
重复标定结果是否稳定
未参与标定的验证图重投影是否贴合
```

推荐筛图方式：

```text
第一轮：阈值宽一点，先跑通
第二轮：删掉误差特别大的图
第三轮：重新标定
第四轮：比较 ds/eucm/omni
第五轮：再收紧阈值
```

对于 2580x2580 或 2Kx2K 超广角原图，最终参考：

```text
1-2 px：很好
2-4 px：很多鱼眼场景可接受
> 5 px：检查模型、覆盖、角点检测或图像模式
```

## 6. OpenCV fallback 单路标定

如果当前先用 1600x1200 USB 原型链路跑通 3D Motion，或只用约 180 度以内有效区域，可以用 FourHeadIntrinsics 的 OpenCV fisheye fallback。优先 ChArUco，棋盘格只做交叉验证：

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

生成去畸变预览和多次实验表：

```bash
python scripts/analyze_experiments.py \
  --camera left_side \
  --method charuco \
  --experiments main_1600x1200_exp01 \
  --undistort
```

检查：

- `valid_image_count >= 20`，越多越稳。
- `rms_reprojection_error_px < 5` 优先；`5-10` 需要人工看预览和 rejected 原因。
- `cx/cy` 接近当前图像中心 `(800, 600)`。
- `processed/rejected/` 中高误差图是否能解释。
- `undistort/` 预览不要出现明显反常拉伸或中心漂移。

## 7. 多相机外参标定

内参稳定后，再做四相机外参。Kalibr 多相机示例：

```bash
kalibr_calibrate_cameras \
  --bag data/kalibr/main_1600x1200_exp01/multicam.bag \
  --topics /cam0/image_raw /cam1/image_raw /cam2/image_raw /cam3/image_raw \
  --models ds-none ds-none ds-none ds-none \
  --target data/targets/aprilgrid_6x6_088.yaml \
  --bag-freq 4.0 \
  --show-extraction
```

要求：

- 四路时间戳尽量同步。
- rig 必须刚性固定，采集过程中不要碰相机模组。
- 相邻相机要同时看到 AprilGrid，让观测关系形成连通图。
- 板子围绕头环移动，覆盖每颗相机中心、边缘和相邻重叠区域。

导入 Kalibr camchain 到 3D Motion：

```bash
python scripts/import_kalibr_camchain_to_3dmotion.py \
  --camchain data/kalibr/main_1600x1200_exp01/camchain.yaml \
  --output ../3DMotion/configs/cameras.yaml \
  --existing ../3DMotion/configs/cameras.yaml \
  --profile-name kalibr_main_1600x1200_25fps \
  --format MJPG \
  --fps 25
```

如果 camchain 是 `ds/eucm/omni`，3D Motion 会保存这些参数，但当前 AprilTag/OpenVINS 模块不会直接运行，需要后续接入对应投影模型。若要立即跑当前 3D Motion 原型，使用下一节 OpenCV fisheye fallback 导出的 `fisheye/equidistant` 配置。

## 8. OpenCV fallback 导出四路内参

四路都标定完成后，直接按实验名导出 rig YAML：

```bash
python scripts/export_rig_yaml.py \
  --config configs/four_head_rig.yaml \
  --results-root data/results \
  --experiment main_1600x1200_exp01 \
  --method charuco \
  --output data/results/four_camera_intrinsics.yaml \
  --max-rms-px 5.0 \
  --max-per-view-px 10.0
```

如果某一路 `quality_ledger` 是 `review`，先不要导入 3D Motion；按原因补拍或放宽阈值做诊断。

## 9. OpenCV fallback 导出到 3D Motion

把 FourHeadIntrinsics 的四路结果转成 3D Motion 的 `configs/cameras.yaml`：

```bash
python scripts/export_3dmotion_cameras_yaml.py \
  --intrinsics data/results/four_camera_intrinsics.yaml \
  --output ../3DMotion/configs/cameras.yaml \
  --existing ../3DMotion/configs/cameras.yaml \
  --profile-name offline_main_1600x1200_25fps \
  --format MJPG \
  --fps 25
```

默认映射：

```text
left_side   -> C0 left_ear
left_front  -> C1 front_left
right_front -> C2 front_right
right_side  -> C3 right_ear
```

如果实际 C0-C3 顺序不同，用 `--camera-map` 覆盖：

```bash
--camera-map left_side:C0:left_ear,left_front:C1:front_left,right_front:C2:front_right,right_side:C3:right_ear
```

导出脚本会保留已有 `T_H_C` 外参字段；如果还没测外参，会保持为 `null`。

## 10. Camera-IMU 标定

内参和多相机外参稳定后，再做 camera-IMU 标定：

```bash
kalibr_calibrate_imu_camera \
  --bag data/kalibr/main_1600x1200_exp01/cam_imu.bag \
  --cam data/kalibr/main_1600x1200_exp01/camchain.yaml \
  --imu data/kalibr/imu.yaml \
  --target data/targets/aprilgrid_6x6_088.yaml
```

`imu.yaml` 里的噪声参数不要随便填，优先来自 IMU 数据手册或 Allan variance 测试。采集时需要足够 6DoF 运动：

```text
前后左右平移
上下平移
绕 X/Y/Z 轴旋转
慢速和中速都有
不要剧烈甩动
不要让图像严重模糊
```

## 11. 3D Motion 验证

进入 3D Motion：

```bash
cd ~/lxy/3DMotion
source .venv/bin/activate
```

采集前检查主线档位：

```bash
python scripts/check_camera_capture.py \
  --source C0:/dev/video0 \
  --format MJPG \
  --width 1600 \
  --height 1200 \
  --fps 25 \
  --output-dir data/raw/camera_preflight
```

录 20-30 秒真实 session 后跑：

```bash
python project_tests/session_quality/check_session_quality.py \
  --session-dir data/raw/session_YYYYMMDD_HHMMSS
```

再跑 AprilTag：

```bash
python scripts/process_apriltag_session.py \
  --session-dir data/raw/session_YYYYMMDD_HHMMSS/cameras \
  --cameras configs/cameras.yaml \
  --bracelet configs/bracelet.yaml \
  --max-reprojection-error-px 10 \
  --output-dir data/processed/session_YYYYMMDD_HHMMSS/wrist_visual
```

验收：

- `frames.jsonl` 中宽高应为 `1600x1200`。
- `configs/cameras.yaml` 中 `profile.image_size` 也应为 `[1600, 1200]`。
- AprilTag detection rate 不应因为畸变模型错误而大面积为空。
- wrist visual 的 reprojection error 应和鱼眼初筛阈值一致，先用 `10 px` 做诊断，再收紧。

OpenVINS 配置生成：

```bash
python scripts/generate_openvins_config.py \
  --cameras configs/cameras.yaml \
  --camera-id C0 \
  --output-dir configs/openvins/generated_head_vio
```

生成的 `kalibr_imucam_chain.yaml` 对鱼眼应包含：

```text
distortion_model: equidistant
distortion_coeffs: [k1, k2, k3, k4]
```

## 12. 最终验证方法

标定完成后，用没有参与标定的图验证：

```text
1. AprilGrid 重投影点是否贴合检测点
2. 残差是否均匀，而不是边缘一圈全偏
3. 主点 cx/cy 是否接近图像中心
4. fx/fy 是否相近
5. 同一批数据分成两半标定，结果是否接近
6. 透视展开后的门框/墙砖直线是否合理
7. VIO 跑短序列时，特征跟踪和尺度是否稳定
```

不要试图把 220-240 度全部展开成一个普通 pinhole 画面。工程上更常见的是：

```text
VIO：直接用原始鱼眼/全向模型投影和反投影
检测/显示：生成多个虚拟 pinhole 视角
全景显示：equirectangular / cubemap / dewarp mesh
```

## 13. 不通过时的排查顺序

1. 真实 session 的宽高是否和 `configs/cameras.yaml` 完全一致。
2. 是否误用了旧的 1920x1080 或 640x480 内参。
3. `camera_model/distortion_model` 是否为 `fisheye/equidistant`。
4. 单路去畸变预览是否正常。
5. 标定板尺寸 `--square-size` 是否填真实值。
6. 边缘和四角覆盖是否足够。
7. 3D Motion 的 C0-C3 映射是否和物理镜头顺序一致。
8. `T_H_C` 外参是否仍为 `null`；内参通过后再做外参，不要混在一起 debug。
