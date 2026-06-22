# A4 纸拼贴 AprilGrid 方案

这份方案用于没有大幅面打印机时，把一张完整 AprilGrid 标定板拆成多张 A4 打印后拼贴。核心原则是：先生成一张连续的大板图案，再用 A4 分块打印、裁切、对齐并贴到同一块刚性平板上；Kalibr target YAML 仍然只描述这一整块板，不按 A4 页拆分。

## 1. 推荐版面

A4 单页 AprilGrid 只适合 smoke test。鱼眼相机正式内参建议尽量做大，拼贴后贴到亚克力板、铝塑板、玻璃或厚泡沫板上，表面尽量哑光、平整、不反光。

推荐两档：

```text
中等拼贴测试板：6 x 6 tags，tagSize 50 mm，tagSpacing 0.3，margin 10 mm
成品尺寸：395 mm x 395 mm，通常需要 2x2 到 3x3 张 A4

正式大板：6 x 6 tags，tagSize 88 mm，tagSpacing 0.3，margin 20 mm
成品尺寸：700 mm x 700 mm，通常需要 3x3 到 4x4 张 A4
```

如果只是验证链路，继续使用仓库里的 A4 单页 `25 mm` 版本即可；如果要给 220-240 度鱼眼做可靠内参，优先用 `88 mm` 或更大的刚性大板。

## 2. 生成 Kalibr Target YAML

先生成目标板的逻辑尺寸。`tagSpacing` 是白色间隙除以黑色 tag 边长的比例，不是米，也不是毫米。

中等拼贴测试板：

```bash
python scripts/generate_kalibr_aprilgrid.py \
  --tag-cols 6 \
  --tag-rows 6 \
  --tag-size-m 0.050 \
  --tag-spacing 0.3 \
  --output data/targets/aprilgrid_6x6_050_tiled_a4.yaml
```

正式大板：

```bash
python scripts/generate_kalibr_aprilgrid.py \
  --tag-cols 6 \
  --tag-rows 6 \
  --tag-size-m 0.088 \
  --tag-spacing 0.3 \
  --output data/targets/aprilgrid_6x6_088_tiled_a4.yaml
```

## 3. 生成 PNG / SVG 图案

仓库脚本会从 target YAML 读取 `tagCols`、`tagRows`、`tagSize`、`tagSpacing`，生成同一张完整图案的 SVG 和 PNG。SVG 带物理毫米尺寸，适合打印；PNG 适合预览、归档或导入排版软件时使用。

中等拼贴测试板：

```bash
python scripts/generate_kalibr_aprilgrid_artwork.py \
  --target-yaml data/targets/aprilgrid_6x6_050_tiled_a4.yaml \
  --margin-m 0.010 \
  --tag-px 1000 \
  --marker-px 1000 \
  --output-svg data/targets/aprilgrid_6x6_050_tiled_a4.svg \
  --output-png data/targets/aprilgrid_6x6_050_tiled_a4.png
```

正式大板：

```bash
python scripts/generate_kalibr_aprilgrid_artwork.py \
  --target-yaml data/targets/aprilgrid_6x6_088_tiled_a4.yaml \
  --margin-m 0.020 \
  --tag-px 880 \
  --marker-px 880 \
  --output-svg data/targets/aprilgrid_6x6_088_tiled_a4.svg \
  --output-png data/targets/aprilgrid_6x6_088_tiled_a4.png
```

PNG 像素尺寸由脚本按下面公式计算：

```text
gap_px = round(tag_px * tagSpacing)
margin_px = round(tag_px * margin_m / tagSize)
width_px = tagCols * tag_px + (tagCols - 1) * gap_px + 2 * margin_px
height_px = tagRows * tag_px + (tagRows - 1) * gap_px + 2 * margin_px
```

以 `50 mm` 方案为例，`tag_px=1000` 时，`gap_px=300`、`margin_px=200`，输出 PNG 是 `7900 x 7900 px`。这相当于 `20 px/mm`，约 `508 DPI`。注意 PNG 文件本身不可靠保存实际打印物理尺寸，所以打印时要明确指定成品宽高或缩放比例。

## 4. A4 分块打印和拼贴

优先打印 SVG 或由 SVG 转出的 PDF，因为它们带毫米尺寸。打印时必须选择：

```text
100% / actual size / no scaling / 不适应页面 / 不缩放
```

如果使用海报/Poster/Tile 打印模式，建议设置：

```text
纸张：A4
方向：自动或横向
缩放：100%
重叠：10-15 mm
裁切标记：开启
```

拼贴步骤：

1. 先在刚性底板上画水平和垂直基准线。
2. 从中心页开始贴，逐页向外扩展，避免误差一路累积。
3. 页与页之间尽量让黑色 tag 连续；如果接缝穿过 tag，必须保证两侧图案无错位、无台阶、无白缝。
4. 用刮板或软布压平，避免纸张起泡、翘边和局部拉伸。
5. 拼完后不要立刻标定，等胶水或喷胶稳定后再复测尺寸。

不要把多张 A4 各自生成成独立 AprilGrid 后拼在一起。那样 tag id 和坐标系会重复，Kalibr 会把它当成错误 target。

## 5. 实测和 YAML 回填

打印和拼贴完成后，必须用游标卡尺或钢尺测量实体板，再把实测尺寸回填到 target YAML。Kalibr 使用的是实体尺寸，不是设计尺寸。

需要测两类值：

```text
tag-size-mm：单个黑色 tag 的实际边长
gap-mm：相邻两个黑色 tag 边缘之间的白色间隙
```

建议至少测：

```text
横向 tag 边长：上/中/下各 2 个
纵向 tag 边长：左/中/右各 2 个
横向 gap：上/中/下各 2 个
纵向 gap：左/中/右各 2 个
```

取平均值回填。如果横向和纵向差异超过约 `0.5%`，或者不同区域差异超过约 `1%`，说明打印缩放或拼贴拉伸明显，建议重新打印或重新拼贴。

假设拼贴后平均黑色 tag 边长是 `49.62 mm`，平均白色间隙是 `14.91 mm`：

```bash
python scripts/update_aprilgrid_measurement.py \
  --target-yaml data/targets/aprilgrid_6x6_050_tiled_a4.yaml \
  --tag-size-mm 49.62 \
  --gap-mm 14.91
```

脚本会按下面公式更新 YAML：

```text
tagSize = tag-size-mm / 1000
tagSpacing = gap-mm / tag-size-mm
```

对应写入：

```yaml
target_type: aprilgrid
tagCols: 6
tagRows: 6
tagSize: 0.04962
tagSpacing: 0.300483676
```

回填后，后续 Kalibr 命令必须使用这个更新后的 YAML。不要把 `tagSpacing` 写成 `0.01491`，也不要写成 `14.91`；它只能是 `gap / tagSize` 的无量纲比例。

## 6. 检查清单

正式采集前确认：

```text
图案是一张完整 AprilGrid 分块打印，不是多张独立小板
打印缩放是 100%，没有 fit to page
拼贴在刚性平板上，接缝无错位、无明显白缝
实测 tagSize 和 tagSpacing 已回填 YAML
采集命令里的 --target 指向回填后的 YAML
```

如果只是 PNG 预览正常，但 Kalibr 检测失败，优先检查：打印缩放、tagSpacing 是否按比例回填、tag id 是否被拼错、接缝是否破坏了 tag、相机是否看到足够多完整 tag。
