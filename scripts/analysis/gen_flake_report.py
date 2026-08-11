#!/usr/bin/env python
"""从 flake 采样 CSV 生成热力图。

用法:
    $PY scripts/analysis/gen_flake_report.py \
        docs/experiments/flake-2026-08-07.csv \
        docs/report/assets

产出两张图:
    flake-heatmap.png        成功率热力图（标注主导失败模式）
    flake-failure-modes.png  各机器人的 B1/B2 失败模式构成

⚠️ BUCKET4（配置崩溃）在热力图中标为 "CFG" 而非计入成功率 ——
   它 100% 复现、无随机性，混进 flake 统计会让那一格永远是黑的，
   误导人去调 IK 容差，而真正的问题是一行配置。
"""
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")            # 无显示器环境必须，且必须在 pyplot 之前
import matplotlib.pyplot as plt
import numpy as np

ROBOTS = ["airbot_play", "arx_l5", "arx_x5", "iiwa14", "panda",
          "piper", "rm65", "ur5e", "xarm7"]
TASKS = ["cover_cup", "place_block", "place_coffeecup",
         "place_kiwi_fruit", "stack_block"]

B4 = "BUCKET4_配置崩溃"
SHORT = {
    "BUCKET1_早期IK失败": "IK",
    "BUCKET2_判据失败": "GRASP",
    "BUCKET3_超时/未记录": "TIMEOUT",
    B4: "CFG",
}


def load(csv_path):
    cells = defaultdict(list)
    with open(csv_path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            cells[(r["robot"], r["task"])].append(r["bucket"])
    return cells


def heatmap(cells, out_path):
    """成功率热力图。BUCKET4 单元格用灰色标出，不参与成功率计算。"""
    rate = np.full((len(TASKS), len(ROBOTS)), np.nan)
    label = {}

    for i, task in enumerate(TASKS):
        for j, robot in enumerate(ROBOTS):
            buckets = cells.get((robot, task), [])
            if not buckets:
                continue
            valid = [b for b in buckets if b != B4]          # 剔除配置崩溃
            n_cfg = len(buckets) - len(valid)

            if not valid:                                     # 整格都是配置崩溃
                label[(i, j)] = "CFG\n100%"
                continue

            rate[i, j] = sum(b == "SUCCESS" for b in valid) / len(valid) * 100
            fails = [b for b in valid if b != "SUCCESS"]
            txt = f"{rate[i, j]:.0f}%"
            if fails:
                top = Counter(fails).most_common(1)[0][0]
                txt += f"\n{SHORT.get(top, top)}"
            if n_cfg:
                txt += f"\n(cfg {n_cfg})"
            label[(i, j)] = txt

    fig, ax = plt.subplots(figsize=(12, 5.2))
    # NaN（整格都是配置崩溃）单独染成灰色，而不是留白 ——
    # 留白会被误读为「没测」，而实际是「测了，但每次都崩」。
    cmap = plt.get_cmap("RdYlGn").copy()
    cmap.set_bad("#9e9e9e")
    im = ax.imshow(np.ma.masked_invalid(rate), cmap=cmap,
                   vmin=0, vmax=100, aspect="auto")

    ax.set_xticks(range(len(ROBOTS)))
    ax.set_xticklabels(ROBOTS, rotation=30, ha="right")
    ax.set_yticks(range(len(TASKS)))
    ax.set_yticklabels(TASKS)

    for i in range(len(TASKS)):
        for j in range(len(ROBOTS)):
            txt = label.get((i, j), "-")
            # 深色背景用白字，浅色背景用黑字
            v = rate[i, j]
            color = "white" if (np.isnan(v) or v < 25 or v > 88) else "black"
            ax.text(j, i, txt, ha="center", va="center", fontsize=7.5, color=color)

    ax.set_title(
        "Task success rate  (N=50 per cell, BUCKET4=config crash excluded)\n"
        "cell label: success% / dominant failure mode",
        fontsize=11,
    )
    fig.colorbar(im, label="success %")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    print(f"已保存 {out_path}")


def failure_modes(cells, out_path):
    """各机器人的失败模式构成（堆叠条形图）。

    回答的问题：这个机器人的失败是【够不着】还是【抓不住】？
    两者的修复方向完全不同。
    """
    b1 = np.zeros(len(ROBOTS))
    b2 = np.zeros(len(ROBOTS))
    for j, robot in enumerate(ROBOTS):
        buckets = [b for t in TASKS for b in cells.get((robot, t), []) if b != B4]
        c = Counter(buckets)
        b1[j] = c.get("BUCKET1_早期IK失败", 0)
        b2[j] = c.get("BUCKET2_判据失败", 0)

    fig, ax = plt.subplots(figsize=(10, 4.5))
    x = np.arange(len(ROBOTS))
    ax.bar(x, b1, label="BUCKET1  early IK failure (unreachable)", color="#4C72B0")
    ax.bar(x, b2, bottom=b1, label="BUCKET2  grasp failure (reached but slipped)",
           color="#DD8452")
    ax.set_xticks(x)
    ax.set_xticklabels(ROBOTS, rotation=30, ha="right")
    ax.set_ylabel("failure count (of 200-250 runs)")
    ax.set_title("Failure mode composition per robot  (BUCKET4 excluded)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    print(f"已保存 {out_path}")


def main():
    csv_path = Path(sys.argv[1] if len(sys.argv) > 1
                    else "docs/experiments/flake-2026-08-07.csv")
    out_dir = Path(sys.argv[2] if len(sys.argv) > 2 else "docs/report/assets")
    out_dir.mkdir(parents=True, exist_ok=True)

    cells = load(csv_path)
    heatmap(cells, out_dir / "flake-heatmap.png")
    failure_modes(cells, out_dir / "flake-failure-modes.png")


if __name__ == "__main__":
    main()
