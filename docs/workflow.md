# 四目头环内参测定流程

1. 用 `scripts/list_cameras.py` 锁定四路 `/dev/video*`。
2. 按物理顺序更新 `configs/four_head_rig.yaml`。
3. 打印棋盘格或 ChArUco，量真实方格边长。
4. 对每一路独立采图，确保标定板覆盖全画面和四角。
5. 用 `--experiment exp01`、`--experiment exp02` 等参数把不同实验存入不同目录。
6. 先跑棋盘格标定，再视情况跑 ChArUco 交叉验证。
7. 查看 `processed/rejected` 中被拒图片，必要时删除模糊、反光、误检图片后重跑。
8. 在 `README.md` 的“内参和畸变参数怎么算出来”章节中对比 `camera_matrix`、`dist_coeffs` 和重投影误差。
9. 用 `scripts/analyze_experiments.py` 输出多次实验的 `[k1, k2, p1, p2, k3]`，必要时生成去畸变对比图。
10. 用 `scripts/calibrate_rig.py` 导出 `data/results/four_camera_intrinsics.yaml`。
11. 若 `quality_ledger` 中某路为 `review`，按原因补拍或放宽阈值后重新评估。

单路多次实验示例：

```bash
python scripts/capture_camera.py \
  --source /dev/video2 \
  --camera left_side \
  --experiment exp02 \
  --interval 0

python scripts/calibrate_camera.py \
  --method chessboard \
  --camera left_side \
  --experiment exp02 \
  --cols 9 \
  --rows 6 \
  --square-size 25.0 \
  --max-error 1.0 \
  --auto-filter

python scripts/analyze_experiments.py \
  --camera left_side \
  --method chessboard \
  --experiments exp02 \
  --undistort
```

这个库只做每个独立相机的内参和畸变，不估计四路外参。外参应在固定头环刚体安装后，用多目共同可见标定板或 AprilTag/Charuco 板另行测定。
