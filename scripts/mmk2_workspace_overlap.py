#!/usr/bin/env python3
"""MMK2 双臂可达空间与重叠区度量。

⚠️ 这是【度量脚本】，不是测试 —— 刻意如此。

计划文档 §Day 15-17 步骤 4 要求写成断言：
    assert overlap.volume / left_workspace.volume > 0.3

不这么做的理由（实测支撑，见 docs/tutorial/day15-17-*.md §5.5）：

  1. ⭐ 分母口径未定义时，阈值可以被"选"成任何结论。实测：
         重叠 / 单臂可达  = 44.9% ~ 48.4%   → 远超 30%，阈值形同虚设
         重叠 / 并集      = 29.0% ~ 31.8%   → 正好骑在 30% 线上
  2. ⭐ 在"重叠/并集"口径下，结论对采样分辨率敏感：
         --step 0.15 → 29.0%（断言失败）
         --step 0.06 → 31.8%（断言通过）
     即红绿取决于本脚本的参数，而非机器人有没有问题 —— 是 flaky 断言。
  3. 阈值没有出处。"> 30%" 是计划文档拍的。
  4. 它不测行为，测的是几何 —— 几何由 MJCF 决定，MJCF 没变它就不会变红。
  5. 成本高：网格采样每点一次 IK（0.06 步长 5292 点需数分钟）。

⚠️ 注意"比值"与"绝对体积"的稳定性不同：
   绝对体积随步长抖动约 10%（0.2143 ~ 0.2350 m³），
   但比值的分子分母同步失真，误差大部分抵消 ——
   0.10 与 0.06 两档的"重叠/单臂"实测完全相同（48.1%）。
   所以"网格越粗比值越失真"这个直觉是错的，别拿它当理由。

度量脚本输出三个口径的数字供人看；等有了明确需求（比如"某任务要求
双臂在指定区域协作"）再决定要不要变成断言。

用法：
    MUJOCO_GL=osmesa python scripts/mmk2_workspace_overlap.py
    MUJOCO_GL=osmesa python scripts/mmk2_workspace_overlap.py --step 0.05 --slide 0.3
"""

import argparse
import itertools
import sys

import numpy as np


def build_grid(x_range, y_range, z_range, step):
    """生成规则采样网格，返回 (N, 3) 的点阵。"""
    axes = [
        np.arange(lo, hi + step / 2, step) for lo, hi in (x_range, y_range, z_range)
    ]
    return np.array(list(itertools.product(*axes))), axes


def reachable_mask(solver, points, arm, slide, rotation):
    """逐点试解 IK，返回布尔可达掩码。

    MMK2IK 在不可达时抛 ValueError（已由 test_mmk2_kinematics 钉住），
    所以这里用异常做判据是可靠的。
    """
    mask = np.zeros(len(points), dtype=bool)
    for i, point in enumerate(points):
        try:
            solver.armIK_wrt_footprint(point, rotation, arm, slide)
        except ValueError:
            continue
        except Exception as exc:  # noqa: BLE001 - 度量脚本，任何异常都记为不可达但要可见
            print(f"  [warn] 点 {point} 抛出非预期异常 {type(exc).__name__}: {exc}")
            continue
        mask[i] = True
    return mask


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step", type=float, default=0.08, help="网格步长（m）")
    parser.add_argument("--slide", type=float, default=0.0, help="升降位置（m）")
    args = parser.parse_args(argv)

    from discoverse.robots.mmk2.mmk2_ik import MMK2IK

    solver = MMK2IK()
    rotation = np.eye(3)

    # 覆盖躯干前方的操作区（footprint 系）。
    points, axes = build_grid(
        x_range=(0.0, 0.8),
        y_range=(-0.6, 0.6),
        z_range=(0.6, 1.6),
        step=args.step,
    )
    cell_volume = args.step**3

    print(f"网格 {[len(a) for a in axes]} = {len(points)} 点，步长 {args.step} m")
    print(f"升降 slide = {args.slide} m，姿态 = 单位阵\n")

    masks = {}
    for arm, label in (("l", "左臂"), ("r", "右臂")):
        masks[arm] = reachable_mask(solver, points, arm, args.slide, rotation)
        count = int(masks[arm].sum())
        print(f"{label}可达点数 {count:6d}  体积 ≈ {count * cell_volume:.4f} m³")

    overlap = masks["l"] & masks["r"]
    union = masks["l"] | masks["r"]
    n_overlap = int(overlap.sum())

    print(f"\n双臂重叠点数 {n_overlap:6d}  体积 ≈ {n_overlap * cell_volume:.4f} m³")

    for arm, label in (("l", "左臂"), ("r", "右臂")):
        denom = int(masks[arm].sum())
        ratio = n_overlap / denom if denom else float("nan")
        print(f"  重叠 / {label}可达 = {ratio:.1%}")

    n_union = int(union.sum())
    if n_union:
        print(f"  重叠 / 并集     = {n_overlap / n_union:.1%}")

    # ⚠️ 不做断言，只报数。见模块 docstring。
    print("\n注：本脚本不设阈值判定 —— 结论取决于选哪个分母。")
    print("    比值对 --step 较稳健（0.10 与 0.06 两档实测一致），")
    print("    但绝对体积随步长抖动约 10%，且过粗的网格会抹平左右臂的真实不对称。")
    print("    宜用于横向比较（如改动 MJCF 前后同参数对比），不作绝对结论。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
