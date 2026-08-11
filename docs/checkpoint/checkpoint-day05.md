# Checkpoint · Day 5（2026-08-07）

> 分支：`feat/test-infra` ｜ 状态：**Day 5 完成（Step 0-5），文档待提交**
> 代码 commit：`8cfbc38` 缺陷 J ｜ `cd09b80` seed 贯穿 ｜ `c722ca8` 缺陷 O + U + H 根因
> 用途：下次开工只读这一份即可接上。历史见 [checkpoint-day04.md](checkpoint-day04.md)。

**本文每条推断都标注「已核实 / 待核实」。** Day 3-5 共 13 条文档推断被实测推翻，其中 3 条是当天自己写的（见第七节）。

---

## 一、下次开工第一件事

```bash
cd /home/ubuntu22/workspaces/airbot-play/DISCOVERSE
source scripts/dev/env.sh
$PY -m pytest tests/ -q       # 预期：113 passed, 4 skipped, 45 deselected, 10 xfailed
```

⚠️ **`45 deselected` 是正常的** —— 那是 flake 采样实验，被 `-m 'not flake'` 默认排除。要跑它见第六节。

⚠️ **开工前必做**：提交文档（见第八节）。当前有大量未提交文件，含 `docs/note/` 的重命名 —— **必须与删除同 commit**。

---

## 二、Day 5 成果【已核实，实跑】

### 2.1 主产出

| 文件 | 内容 |
|---|---|
| [report/flakiness-analysis.md](../report/flakiness-analysis.md) | 313 行分析报告（八节） |
| [report/assets/flake-heatmap.png](../report/assets/flake-heatmap.png) | 9×5 成功率热力图 |
| [report/assets/flake-failure-modes.png](../report/assets/flake-failure-modes.png) | 失败模式构成图 |
| [experiments/flake-2026-08-07.csv](../experiments/flake-2026-08-07.csv) | 2250 行原始数据（155KB） |
| [experiments/flake-2026-08-07.meta.yaml](../experiments/flake-2026-08-07.meta.yaml) | 实验条件 + caveats + 保留策略 |
| `scripts/analysis/gen_flake_report.py` | 图表生成脚本（可复用） |
| `tests/integration/test_task_matrix.py` | 45 组合采样器 |

### 2.2 实验数字

| 指标 | 值 |
|---|---|
| 总运行 | **2250**（9 机器人 × 5 任务 × 50 次） |
| 耗时 | 约 10 分钟（`-n 8`） |
| 单次运行 | 2.17s |
| **表观成功率** | 41.1%（924/2250） |
| **真实成功率**（剔除配置崩溃） | **48.8%**（924/1895） |

### 2.3 全局分桶

| 桶 | 数量 | 占比 |
|---|---|---|
| SUCCESS | 924 | 41.1% |
| BUCKET2 判据失败 | 660 | 29.3% |
| **BUCKET4 配置崩溃**（非 flake） | **355** | **15.8%** |
| BUCKET1 早期 IK 失败 | 299 | 13.3% |
| BUCKET3 超时 | 12 | 0.5% |

### 2.4 单元测试不受影响

`113 passed, 4 skipped, 45 deselected, 10 xfailed in 3.04s` —— **marker 隔离生效**，日常回归仍是 3 秒。

---

## 三、Day 5 的三个核心发现【已核实】

### 3.1 ⭐ 失败模式呈现清晰的机器人分组

**这是最可行动的发现。**

| 主导 BUCKET1（够不着） | 主导 BUCKET2（抓不住） |
|---|---|
| ur5e (B1=89, B2=5) | arx_l5 (B1=2, B2=151) |
| panda (B1=74, B2=5) | iiwa14 (B1=16, B2=141) |
| rm65 (B1=73, B2=43) | airbot_play (B1=35, B2=123) |
| | xarm7 (B1=5, B2=101) |
| | arx_x5 (B1=1, B2=50) |
| | piper (B1=4, B2=41) |

**panda 是 15:1，arx_l5 是 1:75 —— 不是程度差异，是两种机理。**

**修复方向完全不同**：panda/ur5e/rm65 查工作空间与 IK 配置；arx_l5/iiwa14/xarm7 查夹爪与接触参数。

**在这张图之前，两者都只表现为「成功率低」。**

### 3.2 15.8% 的「失败」根本不是 flake

`cover_cup` 对 8/9 机器人 100% 崩溃：

```
Camera 'eye_arm' not found in the MJCF model.
```

**剔除前后差 7.7 个百分点**（41.1% → 48.8%）。混进统计会让热力图那一行永远是黑的，误导人去调 IK 容差。

**与 Day 2 缺陷 B 同族** —— `camera_configs` 与实际 MJCF 不匹配。

### 3.3 端到端确定性成立（Day 3-4 的最终验收）

```
seed=42 → 8 次运行，最终距离全部 0.0024m
seed=13 → 5 次运行，最终距离全部 0.2378m（稳定失败）
```

**Day 3 的单元测试只证明了「随机化可复现」，这一步证明整条管道可复现** —— 含 IK、物理步进、状态机、成功判定。

⚠️ **成功率没变**（Day 0 是 75%，Day 5 实测 76.7%）。**这不是白干** —— Day 3-4 修的是可复现性不是成功率。

---

## 四、缺陷状态总表

| 编号 | 内容 | 严重度 | 状态 |
|---|---|---|---|
| J | `collision_radius` 键名不匹配 | 高 | ✅ 已修 `8cfbc38` |
| seed | 6 处声明零读取者 | 高 | ✅ 已修 `cd09b80` |
| O | `dt` 硬编码遮蔽 | 低 | ✅ 已修 `c722ca8` |
| U | `posture_task` 跨调用泄漏 | 中 | ✅ 已修 `c722ca8` |
| H | 4/9 机器人 `qpos_dim` ≠ `nq` | 高 | 🔍 根因已明，**待决策** |
| S | `get_random_texture` 随机源不受管控 | 中 | ⏸ xfail 守着 |
| T | 库代码用 `print` 代替 `logging` | 低 | ⏸ 未修 |
| B/I | `camera_configs` 空 / `observation` 非必填 | 高/中 | ⏸ 5 xfail |
| **V**（新） | **`cover_cup` 对非 airbot_play 声明不存在的相机 `eye_arm`** | **高** | ⏸ **预计一行可修，影响 15.8% 运行** |
| **W**（新） | pytest 全局 `timeout=60` 覆盖用例内 `TIMEOUT_S=120` | 低 | ⏸ 导致 BUCKET3 归桶不准 |
| **X**（新） | MuJoCo viewer 退出时 `Segmentation fault` | 低 | ⏸ 不影响结果 |

⚠️ **V/W/X 尚未写进 [defect-inventory-day02.md](../defect-inventory-day02.md)** —— 待办。

---

## 五、BUCKET2 根因排查：分层结论【重要】

BUCKET2 占全部失败的 68%，是最值得追的。以下针对 `airbot_play × place_block`：

| 层级 | 内容 | 依据 |
|---|---|---|
| **已排除** | IK 求解 | 末端偏离 IK 目标 0.5mm，**优于成功组的 1.5mm** |
| **已排除** | 手臂到位 | 末端离物体 8.3mm，**优于成功组的 8.9mm** |
| **已确认** | 夹爪闭合时与物体**零接触** | MuJoCo 接触数据：全程仅 `['table']` |
| **已证伪** | 轴向深度假设 | **seed=14 反例**（轴向 8.1mm 与失败样本相同却成功） |
| **已证伪** | 桌面高度假设 | 按 z 排序成功/失败交错，无阈值 |
| **弱相关** | 离基座 >0.315m | 0/11 vs 10/19，但远处也有 47% 成功 —— **风险因子非充分原因** |
| **未确定** | 根因 | — |

**剩余候选**：夹爪闭合速度与手臂移动的时序竞争、接触摩擦/刚度参数、**物体的随机化朝向（本次未查）**、多因素耦合。

> ⚠️ **不要把「轴向深度是根因」这个已被推翻的结论讲出去。** 详见第七节。

---

## 六、环境速查

```bash
source scripts/dev/env.sh

# 日常回归（3 秒，自动排除 flake 实验）
$PY -m pytest tests/ -q

# flake 采样实验（需显式 -m flake）
$PY -m pytest tests/integration/test_task_matrix.py -m flake \
    --count=50 -n 8 --json-report --json-report-file=/tmp/flake.json --tb=no -q

# 生成图表
$PY scripts/analysis/gen_flake_report.py \
    docs/experiments/flake-2026-08-07.csv docs/report/assets

# 看画面（调试用）
export MUJOCO_GL=glfw        # env.sh 默认是 osmesa
$PY examples/universal_tasks/universal_task_runtime.py -r airbot_play -t place_block -1 -s
#                                                     不加 --headless，加 -s 实时同步
```

⚠️ **临时改 seed 调试的标准流程**（务必还原）：

```bash
cp discoverse/configs/tasks/place_block.yaml /tmp/pb.bak
sed -i "s/    seed: .*/    seed: 13/" discoverse/configs/tasks/place_block.yaml
# ... 实验 ...
cp /tmp/pb.bak discoverse/configs/tasks/place_block.yaml
grep -n "seed:" discoverse/configs/tasks/place_block.yaml   # 必须确认回到 null
```

---

## 七、Day 5 被推翻的假设

| 来源 | 假设 | 实测 |
|---|---|---|
| 计划文档 | `test_task_matrix.py` 已存在 | ❌ 不存在 |
| 计划文档 | 失败分三个桶 | ❌ **有第四类（配置崩溃）** |
| 计划文档 | 需要 seaborn | ❌ matplotlib 就够 |
| **我（Day 5 早期）** | 桌面高度是根因 | ❌ 按 z 排序无阈值 |
| **我（Day 5 中期）** | **轴向深度是根因，「彻底查清了」** | ❌ **seed=14 反例** |

**最后一条是本日最重要的教训**：我用**两个样本**的对比就宣布找到根因，而且在**刚写完「两个样本不足以下结论」之后**。

> 📌 **成对对比是最容易产生假根因的方法。** 任何两次运行间有几十个数值不同，总能挑出一个「完美解释」—— 过拟合到样本，解释力 100%、泛化能力 0。
>
> **唯一解药是主动扩大样本找反例。**

**三天累计 13 条假设被推翻，3 条是自己当天写的。** 这不是能力问题，是这类工作的固有特征 —— **排查就是不断提出假设并杀死它们**。

---

## 八、未提交文件（开工第一件事）

```
 M docs/checkpoint/checkpoint-day02.md
 M docs/defect-inventory-day02.md
 M pyproject.toml                          ← flake marker + 默认排除
 D docs/devil-*.md（5 个）                  ← 移动到 log/ 和 note/
?? docs/checkpoint/checkpoint-day0{3,4,5}.md
?? docs/log/  docs/note/                    ← 新位置
?? docs/tutorial/day0{3,4,5}-*.md
?? docs/report/  docs/experiments/          ← Day 5 产出
?? scripts/analysis/
?? tests/integration/
?? source-notes/DISCOVERSE小白入门讲解.md
```

⚠️ **那批 `D`（deleted）不是文件丢了**，是笔记移进了子目录。**git 不存储「重命名」这个动作** —— 它是提交时按内容相似度事后推断的。**必须在同一个 commit 里 add 两边**，否则 `git log --follow` 永久追不到历史。

```bash
git add docs/ scripts/ tests/integration/ pyproject.toml source-notes/
git status --short        # 确认看到 R（renamed），而非 D + ??
```

**建议分两个 commit**：

1. `test(flake): 45 组合采样器 + marker 隔离`（代码：`tests/integration/`、`pyproject.toml`、`scripts/analysis/`）
2. `docs: Day 3-5 教程、实录与 flake 分析报告`（文档 + 数据）

---

## 九、Day 6+ 待办

### 优先级 1：文档提交（见第八节）

### 优先级 2：修缺陷 V（`cover_cup` 相机）

**影响 15.8% 的运行，预计一行可修。** 修完后 `cover_cup` 这一整行热力图才有意义。

### 优先级 3：Day 6-7 缺陷分析报告（原计划）

大部分素材已就绪 —— [defect-inventory-day02.md](../defect-inventory-day02.md) 有 J-R + S/T/U，本 checkpoint 有 V/W/X。**需要做的是把 V/W/X 写进清单，并按统一格式整理。**

### 优先级 4：遗留

- [ ] BUCKET2 根因（剩余候选见第五节，**优先查物体朝向** —— 唯一没查过的）
- [ ] 缺陷 H 决策：先定义 `qpos_dim` 语义
- [ ] 缺陷 B/I（Day 2 遗留，5 xfail）：`camera_configs` 为空 → 数据采集产出零图像
- [ ] 加 L2 失败元数据记录（报告 §6.4）
- [ ] `recorder.py` 覆盖率 **19%**，Day 2 至今未动 —— 当前最大盲区

---

## 十、Day 3-5 全周期总结

| | Day 2 结束 | **Day 5 结束** |
|---|---|---|
| 用例 | 90 | **113** |
| 覆盖率 | 30% | **62%** |
| commit | 1 | 3 |
| 缺陷修复 | 0 | **4**（J、seed、O、U） |
| 新发现缺陷 | — | **6**（S、T、U、V、W、X） |
| 根因查明 | — | 1（H） |
| 实验数据 | — | **2250 次运行** |

**但最有价值的产出不是这些数字，是这条：**

> 三天共 **13 条被写进文档的推断被实测推翻**，其中 3 条是当天自己写的。
>
> **所以现在每份 checkpoint 的每条结论都标注「已核实 / 待核实」，而核实的方式是跑一遍。**
