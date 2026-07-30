# Day 0 — 环境就绪与仓库准备

> **协作方式**：所有命令由你亲手敲，我负责解释每一步「为什么」。
> 每步都有 **验证命令**，看到预期输出再进下一步。

---

## 本日目标

| # | 事项 | 产出 |
|---|---|---|
| 1 | 建工作分支 | `feat/test-infra` |
| 2 | 装 pytest 全家桶 | `pytest --version` 有输出 |
| 3 | 解决无头渲染 | `MUJOCO_GL=osmesa` 能渲染 |
| 4 | 建魔鬼日志 | `docs/devil-log.md` |
| 5 | 复跑基线数据 | 你亲手测出的成功率数字 |

预计 1.5–2 小时。

---

## 计划已做的两处调整

### 调整一：不提上游 PR，只在自己仓库做

**利弊你要心里有数**（面试可能被问「为什么不提上游」）：

- ✅ 去掉不可控因素 —— PR 合不合、maintainer 何时看，都不由你决定
- ✅ 省下 2 天，不用适配上游规范、等 review、处理冲突
- ⚠️ 说服力略降 —— merged PR 是第三方背书，个人仓库是自证

**补偿方案**：用**缺陷分析报告**代替 PR。工业界真实的测试开发产出本来就是缺陷报告，不是 PR。一份写着「复现步骤 / 根因分析 / 修复方案 / 回归验证」的专业报告，恰恰更贴近 SDET 日常工作。

> 💡 被问到时诚实答：「三周内我优先保证产出可控和深度，PR 合并周期不由我掌握。缺陷我全部定位、修复并回归验证了，报告在这里。」—— 这是有判断力的回答，不是短板。

### 调整二：加入源码攻坚（你提的，很关键）

你说得对 —— 我原计划的 13 个缺陷是**静态读码 + 少量运行**发现的，属于表层。**不懂被测系统的模块边界、数据流、接口契约，就只能写浅测试**，面试被问「讲讲这个项目架构」会哑火。

新增编排：
- **Day 1 上午**：全局架构鸟瞰（半天），产出 `docs/architecture-notes.md`
- **四条核心链路溶进对应测试日**：

| 链路 | 溶进哪天 | 为什么测试必须懂 |
|---|---|---|
| 仿真内核：步进与控制 | Day 3-4 确定性攻坚 | 不懂 decimation 与控制频率关系，分不清"不确定"是物理引擎问题还是控制时序问题 |
| 场景拼装：MJCF 合并 | Day 1-2 配置层单测 | 45 组合中某些会挂，根因常在 XML 合并。不懂就只能报"任务失败"，说不出根因 |
| 运动学：IK 内部 | Day 3-4 + Day 15-17 | 直接对接你的工业机器人背景。要能答"为什么不收敛""容差怎么定" |
| 数据流：采集与编码 | Day 18-19 | 具身智能"数据即产品"。要能说清时间戳如何对齐、丢帧在哪产生 |

**强制约束**：读不懂就写不出那天的测试。这不是可选项。

---

## Step 1｜建工作分支

```bash
cd /home/ubuntu22/workspaces/airbot-play/DISCOVERSE
git checkout -b feat/test-infra
```

**讲解**：为什么不直接在 `main` 上干活？

1. **可回滚** —— 搞砸了 `git checkout main` 就回去了，`main` 永远干净
2. **可对比** —— `git diff main --stat` 一眼看清「这三周我到底加了什么」，这是写简历时统计工作量的依据
3. **本身就是面试考点** —— 分支策略是 SDET 基本功

**验证**：
```bash
git branch
```
预期 `* feat/test-infra` 前有星号。

### 顺手处理未跟踪文件

```bash
git status --short
```

你会看到一堆 `??`，其中包括简历 PDF。**简历不应进代码仓库**（个人隐私 + 与项目无关）。面试官很可能会 clone 你的仓库，里面躺着简历 PDF 显得不专业。

在 `.gitignore` 末尾加一行：
```
source-notes/*.pdf
```

---

## Step 2｜安装 pytest 全家桶

### 2.1 先确认 Python 环境

```bash
conda activate discoverse
which python
```

**必须输出** `/home/ubuntu22/miniconda3/envs/discoverse/bin/python`。

> ⚠️ 我实测过：系统的 `/usr/bin/python3` 里**没有 mujoco**。环境没激活就装包，会装到错误的地方，后面全是坑。这是新手最高频翻车点。

### 2.2 安装

```bash
pip install pytest pytest-cov pytest-xdist pytest-timeout pytest-repeat
```

**逐个讲解**（面试常问「你用过哪些 pytest 插件」，这就是标准答案）：

| 包 | 作用 | 我们为什么需要 |
|---|---|---|
| `pytest` | 框架本体 | 基础 |
| `pytest-cov` | 覆盖率测量 | 简历要写「覆盖率 5%→X%」，需要它出数据 |
| `pytest-xdist` | 多进程并行 `-n 8` | 你有 28 核，45 个仿真任务串行太慢 |
| `pytest-timeout` | 单用例超时 | **仿真测试特有刚需**：IK 不收敛会死循环，没超时 CI 会挂死几小时 |
| `pytest-repeat` | 重复执行 `--count=10` | **Flake 分析核心工具**，用来量化那个 62.5% |

> 💡 注意 `pytest-timeout` 这条 —— 传统 Web 测试很少需要，但仿真测试**必须**有。面试主动提这点，能体现你理解「具身智能测试的特殊性」。

**验证**：
```bash
pytest --version
python -c "import pytest_cov, pytest_repeat, xdist, pytest_timeout; print('全部插件 OK')"
```

---

## Step 3｜解决无头渲染（本日最关键）

### 3.1 先理解问题

我实测了你机器上三种 MuJoCo 渲染后端：

```
MUJOCO_GL=glfw   ✅ 能用（因为你有 DISPLAY=:1，即有图形界面）
MUJOCO_GL=egl    ❌ 报错 EGLError
MUJOCO_GL=osmesa ❌ 库未安装
```

**为什么这是大问题**：

CI runner（GitHub Actions、Docker 容器）**没有显示器**，`DISPLAY` 是空的，`glfw` 必挂。

而 DISCOVERSE 的 `--headless` 参数**名不副实**。我读了源码：它只是不开 viewer 窗口（`universal_task_runtime.py:436`），但仍会执行 `mujoco.Renderer(mj_model)`（第 44 行）创建离屏渲染器，照样要 GL。

三种后端怎么选？

| 后端 | 原理 | 优劣 |
|---|---|---|
| `glfw` | 依赖真实窗口系统 | 需要 DISPLAY，CI 不可用 |
| `egl` | GPU 直接离屏渲染 | 快，但依赖驱动配置，你机器上目前是坏的 |
| `osmesa` | **纯 CPU 软件渲染** | 慢，但**零依赖、必然能跑** |

**决策：CI 用 osmesa，本地开发用 glfw**。理由是**可靠性优先于速度** —— CI 里渲染只为让流程跑通、验证不崩溃，不需要高帧率。

> 💡 这段推理就是面试题「你的 CI 里 osmesa 和 EGL 为什么选前者？」的答案。
> **记住这个思路：CI 环境优先选确定性高的方案，性能是次要的。**

### 3.2 安装

```bash
sudo apt update
sudo apt install -y libosmesa6-dev xvfb
```

- `libosmesa6-dev` — 软件渲染库，让 `MUJOCO_GL=osmesa` 可用
- `xvfb` — 「虚拟显示器」，凭空造一个假 `DISPLAY`。作为备选方案（某些库硬依赖 X11 时用 `xvfb-run` 包一层）

### 3.3 验证 osmesa 真能渲染

```bash
cd /tmp && MUJOCO_GL=osmesa python -c "
import mujoco
m = mujoco.MjModel.from_xml_string('<mujoco><worldbody><light pos=\"0 0 3\"/><body><geom type=\"box\" size=\".1 .1 .1\"/></body></worldbody></mujoco>')
d = mujoco.MjData(m); mujoco.mj_forward(m, d)
r = mujoco.Renderer(m, 64, 64); r.update_scene(d)
img = r.render()
print('osmesa OK', img.shape, 'mean pixel =', img.mean().round(2))
"
```

**预期**：`osmesa OK (64, 64, 3) mean pixel = 33.83` 左右。

> ⚠️ **`mean pixel` 不能是 0.0**。若是 0，说明渲染出了纯黑图 —— 等于没渲染成功。
>
> 这个检查点很重要：很多人以为「不报错就是成功」，但渲染可能**静默输出黑图**。
> **测试思维的核心就是：不要只验证没报错，要验证结果正确。**

### 3.4 终极验证：模拟无显示器环境跑真实任务

```bash
cd /home/ubuntu22/workspaces/airbot-play/DISCOVERSE
env -u DISPLAY MUJOCO_GL=osmesa python examples/universal_tasks/universal_task_runtime.py \
  -r airbot_play -t place_block -1 --headless 2>&1 | tail -20
```

**讲解**：`env -u DISPLAY` 临时**删除** DISPLAY 变量，精确模拟 CI runner 环境。这比「相信它能跑」可靠得多。

**判断标准**：只要没有 GL / OpenGL / EGL 相关报错就算过。

> ⚠️ **任务失败也算通过本步验证**。这步验证的是「渲染管线能跑」，不是「任务能成功」。实测该任务成功率仅 62.5%，失败很正常 —— 那是 Day 5 要攻的问题。

---

## Step 4｜建立魔鬼日志

```bash
mkdir -p docs
```

创建 `docs/devil-log.md`。

**为什么不能省**：

三周后面试官问「讲一个你定位复杂问题的经历」，你需要的不是结论，而是**过程细节** —— 你当时怎么想、试了什么、为什么排除某个方向。这些细节两周后必然遗忘，而**恰恰是它们能证明你真做过**。

背下来的结论一问就穿帮，真实的排查过程问不倒。

**记录模板**（每天 10 分钟）：

```markdown
## Day N — YYYY-MM-DD

### 今天验证了什么假设
- 假设：...
- 结论：证实 / 证伪，证据是 ...

### 踩了什么坑
- 现象：...
- 排查路径：先怀疑 A（排除，因为...），再查 B（命中）
- 根因：...
- 修复：...

### 面试可讲的点
- （一句话，能展开讲 3 分钟的那种）
```

**Day 0 应记的内容**（我实测过，但**你要自己复跑确认后再写**）：

1. **渲染后端选型** —— 三种后端实测结果 + 为什么 CI 选 osmesa
2. **`--headless` 名不副实** —— 只关了 viewer（`:436`），没关 Renderer（`:44`），真无头仍会挂
3. **基线数据** —— 见 Step 5

---

## Step 5｜复跑基线数据（重要，别跳过）

**简历上要写的数字，必须是你亲手跑出来的。**

我实测 8 次里 5 成功 3 失败（62.5%），但仿真有随机性，你的结果可能不同。写进简历的数字必须经得起追问：「这个 62.5% 怎么来的？」——「我跑了 8 次，5 次成功。」

```bash
cd /home/ubuntu22/workspaces/airbot-play/DISCOVERSE
S=0; F=0
for i in $(seq 1 8); do
  OUT=$(timeout 180 python examples/universal_tasks/universal_task_runtime.py \
        -r airbot_play -t place_block -1 --headless 2>&1)
  if echo "$OUT" | grep -q "任务成功: ✅ 是"; then
    S=$((S+1)); echo "run $i: PASS"
  else
    F=$((F+1)); echo "run $i: FAIL  <- $(echo "$OUT" | grep -o '完成状态: [0-9]*/[0-9]*' | tail -1)"
  fi
done
echo "成功 $S / 失败 $F  → 成功率 $(( S * 100 / 8 ))%"
```

**讲解：为什么跑 8 次而不是 3 次？**

**统计意义**。3 次样本太小 —— 一个真实成功率 60% 的任务，连续 3 次全成功的概率有 21%，你会误判成「稳定」。8 次是「快速」与「有意义」之间的折中。正式的 flake 分析（Day 5）会跑更多次。

> 💡 「样本量」意识是测试开发和普通开发的分水岭。面试时能主动说「3 次不够，我跑了 N 次」，加分。

**务必记下失败时的 `完成状态: X/10`** —— 这个数字揭示失败发生在第几步，是 Day 5 根因分类的关键线索。我实测见过两种：

- `1/10` —— 第一步就挂（IK 早期不收敛）
- `10/10` —— 十步全走完但最终判据不通过（抓取滑脱 / 物体位置不合理）

**两种失败模式根因完全不同**，混在一起统计就没法定位问题。这是 Day 5 的核心工作。

---

## 今日验收清单

全部打勾才算 Day 0 完成：

- [ ] `git branch` 显示当前在 `feat/test-infra`
- [ ] `.gitignore` 已忽略简历 PDF
- [ ] `pytest --version` 正常，5 个插件都能 import
- [ ] `MUJOCO_GL=osmesa` 渲染测试通过，**且 mean pixel ≠ 0**
- [ ] `env -u DISPLAY` 下真实任务能跑完（无 GL 报错即可）
- [ ] `docs/devil-log.md` 已写 Day 0 记录
- [ ] 拿到**你自己的**基线成功率数字，并记下失败时的 `完成状态`

---

## 遇到问题时

把**完整报错**贴给我，不要只说「报错了」。同时附上环境信息：

```bash
conda info --envs && which python && echo "DISPLAY=$DISPLAY MUJOCO_GL=$MUJOCO_GL"
```

---

## 明日预告：Day 1 上午 — 全局架构鸟瞰

先剧透一个我已经验证过的发现，让你有心理准备：

**DISCOVERSE 内部存在两条并行的、互不相通的技术路线**：

```
路线 A（旧）: SimulatorBase (envs/simulator.py, 658行)
             ← robots_env/*_base.py (airbot_play_base, mmk2_base...)
             ← examples/tasks_mmk2/*.py, examples/tasks_airbot_play/*.py

路线 B（新）: UniversalTaskBase (universal_manipulation/task_base.py, 305行)
             ← examples/universal_tasks/universal_task_runtime.py
```

我已用 grep 验证：`universal_manipulation/` 目录下**没有任何一处** import `SimulatorBase` —— 两条路线完全独立，各自实现了一套仿真循环、数据记录、状态机。

**这对测试意味着什么**（明天会展开讲）：
- 你的测试策略必须覆盖两条路线，不能只测一条
- MMK2 走路线 A，通用机械臂走路线 B —— 所以 Day 15-17 的 MMK2 测试和 Day 1-2 的通用测试，fixture 无法复用
- 这种「架构分裂」本身就是值得写进架构笔记的发现，面试讲出来很有分量

明天上午我们会把这两条路线的完整调用链画出来。
