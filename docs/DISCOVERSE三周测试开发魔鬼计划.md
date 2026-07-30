# DISCOVERSE 三周测试开发魔鬼计划

> **目标受众**：工业机器人测试工程师 → 具身智能测试开发（SDET）  
> **时间投入**：21 天，10-12 小时/天（约 220 小时）  
> **产出物**：4 个可展示 artifact + 重写简历

> 🧭 **迷路了？直接跳到 [4.0 主线图](#40-主线图迷路时只看这一节)。**
> 本文档颗粒度很细，是给**执行**用的；4.0 节是给**定位**用的。
> 每日具体接续点见 `docs/checkpoint/checkpoint-day0X.md`。

---

## 一、计划背景与目标

### 1.1 背景诊断

**现状**：
- 3 年工业机器人（钱江机器人）系统级测试经验
- 简历已写"精通 Python/Pytest 数据驱动测试"、"Docker + Jenkins CI/CD 平台从 0 到 1"
- **实际情况**：自述"CICD、pytest、docker 啥的也不懂"

**核心问题**：简历与实际能力存在落差。

**解决方案**：三周内**把简历上的每一句话变成可当场被拷问、有 GitHub 链接佐证的真实产出**。

### 1.2 为什么选 DISCOVERSE

- ✅ IROS 2025 论文项目，MIT 协议，真实活跃
- ✅ **测试基建几乎为零**（无 tests/、无 .github/、覆盖率 ~5%）—— 测试开发的天然舞台
- ✅ 实测确认的技术缺口（13+ 个已定位缺陷）

### 1.3 已确认的技术缺口（实测证据）

| 缺口类型 | 实测证据 |
|---------|---------|
| 无测试基建 | 目录不存在：`tests/`、`.github/`、`conftest.py`；conda 环境 `discoverse` 里 pytest 都没装 |
| CI 无法感知失败 | 注入异常后 `main()` 吞掉异常正常返回，进程退出码恒为 0 |
| **Flake 率 62.5%-75%** | `place_block` 任务 8 次跑 5-6 成功，两种失败模式：`1/10`（IK 早期）、`10/10`（判据不通过） |
| 仿真完全不可复现 | `place_block.yaml` 里 `settings.seed: null` 是死配置，`randomization.py` 里 20+ 处裸 `np.random.*` 从未被 seed |
| headless 模式仍依赖 GL | 本机 EGL 报错、osmesa 未装、xvfb 未装，只有 glfw+`DISPLAY=:1` 能渲染 → 真无头 CI 必挂 |

### 1.4 预期产出

**4 个可展示 artifact**：
1. **GitHub 仓库**：`feat/test-infra` 分支，包含完整测试框架（pytest + Docker + CI）
2. **架构分析笔记**：`docs/architecture-notes.md`，含自绘架构图与调用链
3. **缺陷分析报告**：`docs/defect-report.md`，13 个缺陷的完整闭环（复现→根因→修复→回归）
4. **技术总结**：一页 A4，面试带纸质版

**加分项**：
- 重写的简历（可验证的具体成果代替模糊描述）
- Devil-log（记录每日验证假设、踩坑排查过程，面试 STAR 故事素材）

---

## 二、环境现状（已实测）

### 2.1 软硬件环境

```bash
# Python 环境
conda env: discoverse (Python 3.10.20)
  已安装: mujoco 3.10.0, mink, numpy 2.2.6, scipy, cv2 4.13, torch 2.13(cpu), mediapy
  未安装: pytest, taichi, gaussian_renderer (3DGS 不可用)

# 硬件
GPU: RTX 4060 Laptop 8G
CPU: 28 核
RAM: 14G
磁盘: 92G 可用

# 渲染后端测试
MUJOCO_GL=glfw + DISPLAY=:1  ✅ 可用
MUJOCO_GL=egl                ❌ EGLError
MUJOCO_GL=osmesa             ❌ 未安装
xvfb                         ❌ 未安装

# 容器
Docker 29.1.5 + Compose v5.0.2
已运行: jenkins_server:8080, portainer

# Git
remote: git@github.com:Cyberpunk-edgerunners/DISCOVERSE-learning.git
```

### 2.2 首日必须解决

```bash
# 1. 安装 pytest 全家桶
pip install pytest pytest-cov pytest-xdist pytest-timeout pytest-repeat hypothesis

# 2. 安装无头渲染依赖（CI 刚需）
sudo apt update
sudo apt install -y libosmesa6-dev xvfb
```

---

## 三、已定位缺陷清单（13 个）

> **这就是 PR 素材**，按提交优先级排序

| ID | 严重级别 | 位置 | 问题描述 | 测试价值 |
|----|---------|------|---------|---------|
| 1 | 🔴 Critical | `universal_task_runtime.py:483-494` | `main()` 捕获所有异常后正常返回，进程退出码恒为 0，CI 无法区分"任务失败"和"程序崩溃" | 修复：返回布尔并 `sys.exit(0 if ok else 1)` |
| 2 | 🔴 Critical | `randomization.py` 全文 | 无任何 seed 消费，`place_block.yaml` 的 `settings.seed` 是死配置 | **最有价值的 PR**：引入 `np.random.Generator` 实例，从 config 读 seed 并贯穿 |
| 3 | 🟡 High | `cicd_testing.py:366-381` | `--timeout` 参数被 argparse 解析后从未使用，CLI flag 是死的 | `run_batch_tests()` 签名里没有 timeout，内部调 `run_single_test(robot, task)` 恒用默认 60s |
| 4 | 🟡 High | `cicd_testing.py:121` | 成功判据 `A in out or B in out and C in out` 实为 `A or (B and C)`，且第一分支字符串在真实输出中根本不出现 | 死分支，`process.returncode` 被完全忽略 |
| 5 | 🟡 High | `mink_solver.py:126` | 局部 `dt = 1e-3` 覆盖了 `self.dt`（config 里的 0.002），YAML 的 `ik_solver.dt` 是死配置 | 参数化测试可覆盖 |
| 6 | 🟠 Medium | `mink_solver.py:181-195` | `_validate_solution()` 名为"验证解有效性"，实际只查 NaN/Inf，不查关节限位 | 补充关节限位检查 |
| 7 | 🟠 Medium | `mink_solver.py:99,142` | `self.configuration` 被就地 mutate，即使不收敛也保留污染状态 → 跨调用状态泄漏 | 同一输入两次调用结果不同 |
| 8 | 🟢 Low | `task_base.py:78-81` | `randomize_scene()` 标注 `-> bool` 但所有路径都返回 `None` | 类型注解不一致 |
| 9 | 🟢 Low | `universal_task_runtime.py:327` | f-string 里 `\\n` 是字面反斜杠 n，实测输出为 `\n📊 AIRBOT_PLAY...` | 格式化输出问题 |
| 10 | 🟠 Medium | `universal_task_runtime.py:385` | `save_dir` 每 episode 相同，多轮采集互相覆盖，无 episode 索引 | 数据采集丢数据 |
| 11 | 🟢 Low | `recorder.py:58` | 用 `assert` 保证时间戳单调，`python -O` 下会被剥离 | 用显式 if 检查 + raise |
| 12 | 🟢 Low | `cicd_testing.py:249,260` | 统计只遍历 `self.supported_robots`，用户 `-r` 传入表外机器人会被静默丢弃 | 用户输入验证缺失 |
| 13 | 🟡 High | `universal_task_runtime.py:436` | `--headless` 仍构造 `mujoco.Renderer`，真无头环境必挂 | 本机 EGL 已报错验证 |

---

## 四、三周排期总览

### 4.0 主线图（迷路时只看这一节）⭐

> **本节存在的理由**：下面 4.1 起的排期和第六章的详细计划颗粒度很细，执行时容易被细节淹没、失去方向感。
> **任何时候觉得"乱七八糟被牵着走"，回到这一节。**

#### 三句话概括三周

```
第 1 周：搞清楚这个项目怎么工作，并建立能自动验证它的基础设施
第 2 周：用这套基础设施覆盖核心功能，挖出真实缺陷
第 3 周：让这一切自动运行（CI + Docker），并整理成能对外讲的东西
```

**每周一个主题，每天服务于当周主题。** 判断某天工作是否跑偏，就看它是否服务于当周主题。

#### 定位表

| 周 | 主题 | Day | 做什么 | 完成标志（可验证） |
|---|---|---|---|---|
| **1** | **理解 + 打地基** | 1 | 读架构、追调用链 | 能画出模块分层图，对着讲 10 分钟 |
| | | **2** | **搭 pytest 骨架 + 配置层单测** | **`pytest` 能跑且有测试通过** |
| | | 3-4 | 确定性攻坚 | 同种子 → 同结果，能证明 |
| | | 5 | Flake 定量分析 | 热力图 + 失败模式分类 |
| | | 6-7 | 缺陷分析报告 | 8-13 条带根因的缺陷闭环 |
| **2** | **自动化基建** | 8-9 | Docker 测试镜像 | 无 ROS、无显示器也能跑测试 |
| | | 10-11 | GitHub Actions | push 自动跑测试 + 绿色徽章 |
| | | 12 | Jenkins 辅线 | GPU 夜间回归 |
| | | 13-14 | 重构 cicd_testing.py | 结构化 JSON 结果契约 |
| **3** | **专项 + 交付** | 15-17 | MMK2 双臂轮式专项 | `tests/mobile_manipulation/` 4 个模块 |
| | | 18-19 | 数据质量验证器 | 图像/轨迹/时序/一致性四类检查 |
| | | 20-21 | 求职材料 | 能对着 GitHub 讲 30 分钟 |

#### 三周后的实际产出

| 产出 | 具体内容 |
|---|---|
| 一套测试代码 | `tests/`，约 150-250 个用例，覆盖 9 机械臂 × 5 任务 + MMK2 |
| 一份缺陷报告 | 8-13 条真实缺陷，每条带复现步骤、根因、影响分析 |
| 一条 CI 流水线 | GitHub Actions，push 自动跑测试出报告 |
| 一个 Docker 镜像 | 无 ROS、无显示器的干净测试环境 |
| 一份技术文档 | tutorial / note / log 三件套 + 架构笔记 |

**能力层面**（面试能讲的）：

| 能力 | 证据来源 |
|---|---|
| 能读懂陌生的大型代码库 | Day 1 调用链追踪 |
| 能搭测试基础设施 | Day 2 pytest 骨架 |
| **能发现别人发现不了的 bug** | Day 2 起持续（如 `qpos_dim` 4/9 与 MJCF 不符） |
| 能判断「代码错」vs「测试错」 | Day 2 起持续训练 |
| 能把测试跑进 CI | Day 10-11 |

**最值钱的是第三条** —— 这是测试开发与手工测试的分水岭。

#### 为什么执行时会觉得"乱"（预先说明）

**真实的测试开发是「侦查 → 假设 → 验证」的循环，不是线性推进。** 典型的一天长这样：

```
写测试 → 发现字段名不对 → 侦查 YAML → 提出 ctrl_dim 公式假设
  → 横向验证 9 个样本 → 成立 → 再和 MJCF 对账 → 发现 4/9 不符
  → 记为缺陷、xfail 标记 → 继续写测试
```

**这个"绕"不是浪费，是主要工作。** 但要区分两类命令：

| 类型 | 例子 | 留下产出？ |
|---|---|---|
| **建设** | 写 `conftest.py`、改 `pyproject.toml` | ✅ 永久 |
| **侦查** | `$PY - <<'PYEOF'` 一次性探查脚本 | ❌ 跑完即弃 |

侦查脚本本身不是产出，**它的结论才是产出** —— 结论要么变成断言，要么变成缺陷记录。

#### 为什么 Day 2 测 9 种机械臂而不是先测 MMK2

这是执行中最常见的疑问，答案不是"双臂不重要"（MMK2 是 Day 15-17 的重点专项），而是**顺序**：

| 理由 | 说明 |
|---|---|
| **样本量就是判断力** | 9 个样本中 5 个符合公式、4 个不符 → 能确定是那 4 个配置错了。只有 2 个样本时，1 对 1 错**无法判断谁错** |
| **先建立可信基线** | 框架在 9 个简单样本上验证通过后才可信；再用可信的框架测 MMK2，红了就是 MMK2 真有问题 |
| **复杂度阶梯** | 机械臂 6-7 DOF、配置扁平；MMK2 19 DOF、六个子系统、五处切片边界。同类错误的排查难度高数倍 |
| **确定性难度递增** | 机械臂是固定基座；MMK2 有轮子会打滑、差速驱动误差累积，直接冲击"同种子→同结果"。必须先在简单场景把方法搞对 |

**但 MMK2 更值钱** —— 会的人少、难度高、正是具身智能主流形态，且本项目文档标注为"⭐ 重点"。**若三周时间紧张，优先砍策略学习相关测试，保住 Day 15-17。**

---

**设计原则**：每周一个可独立展示的 artifact；周一周二产出，周三周四加固，周五写文档+改简历。

### 第 0 天（启动）✅ 已完成

- [x] 建 `feat/test-infra` 分支
- [x] 装依赖：pytest 全家桶 + `libosmesa6-dev` + `xvfb`
- [x] 建 `docs/devil-note.md`
- [x] 复跑基线：测出 place_block 成功率（实测 75%）

### 第 1 周：Pytest 框架 + 确定性攻坚（最硬的技术资产）

| 天数 | 任务 | 产出 | 关键点 |
|-----|------|------|--------|
| **Day 1 上午** ✅ | 全局架构鸟瞰 | `docs/architecture-notes.md` | 双路线架构、调用链、三层配置体系 |
| **Day 1 下午-2** 🔄 | pytest 骨架 + 配置层单测 | `tests/` 目录、`conftest.py`、9×5=45 组合参数化 | fixture 作用域选择（面试必问） |
| **Day 3-4** | 确定性攻坚 | TDD 红→绿：seed 贯穿、IK 状态泄漏修复 | 本周核心，最有含金量 |
| **Day 5** | Flake 定量分析 | `docs/flakiness-analysis.md`、热力图 | 差异化亮点，绝大多数候选人不会做 |
| **Day 6-7** | 缺陷分析报告 | `docs/defect-report.md`（13 个缺陷闭环） | 代替原 PR 计划，重点打磨 3 个高价值缺陷 |

**周产出**：架构笔记、45+ 测试用例、确定性测试从红到绿、flake 分析、缺陷报告

### 第 2 周：CI/CD 双线 + Docker（把简历第一条坐实）

| 天数 | 任务 | 产出 | 关键点 |
|-----|------|------|--------|
| **Day 8-9** | Docker 测试镜像 | `Dockerfile.test`、瘦身记录（X GB → Y GB） | 解决真无头渲染，固化 `MUJOCO_GL=osmesa` |
| **Day 10-11** | GitHub Actions 主线 | `.github/workflows/ci.yml`（5-job 流水线）+ 绿色徽章 | lint/unit/integration/nightly + 覆盖率上传 |
| **Day 12** | Jenkins 辅线 | `Jenkinsfile` GPU 夜间回归 | 真实理由：GA 免费 runner 无 GPU |
| **Day 13-14** | 重构 cicd_testing.py | 结构化 JSON 结果契约 + JUnit XML | 替换 emoji 字符串匹配，修问题 4、12 |

**周产出**：测试镜像、GA 流水线+徽章、Jenkinsfile、结构化结果契约

### 第 3 周：MMK2 专项 + 数据质量 + 求职材料

| 天数 | 任务 | 产出 | 关键点 |
|-----|------|------|--------|
| **Day 15-17** | MMK2 双臂轮式专项 | `tests/mobile_manipulation/`（4 个测试模块） | FK→IK→FK 往返一致性，工业机器人经验迁移 |
| **Day 18-19** | 数据质量验证器 | `discoverse/data_validation/` 模块 | 图像清晰度、轨迹平滑度、时间戳同步、丢帧检测 |
| **Day 20-21** | 求职材料 | 重写简历、`README-testing.md`、技术总结（一页 A4）、模拟面试自测 | 不要压到最后一天 |

**周产出**：MMK2 测试、数据验证器、新简历、技术总结

---

## 五、源码攻坚编排（贯穿全程）

> **为什么必须有**：13 个缺陷是静态读码 + 少量运行发现的，属于表层。不懂被测系统的模块边界、数据流、接口契约，只能写浅测试，面试被问"讲讲这个项目架构"会哑火。

### 5.1 Day 1 上午｜全局鸟瞰（半天）

**产出**：`docs/architecture-notes.md`

**三个发现任务**：
1. **双路线架构**：
   ```
   路线 A（旧）: SimulatorBase (envs/simulator.py, 658行)
                ← robots_env/*_base.py (airbot_play_base, mmk2_base...)
                ← examples/tasks_mmk2/*.py, examples/tasks_airbot_play/*.py
   
   路线 B（新）: UniversalTaskBase (universal_manipulation/task_base.py, 305行)
                ← examples/universal_tasks/universal_task_runtime.py
   ```
   **关键发现**：`universal_manipulation/` 目录下无任何一处 import `SimulatorBase` —— 两条路线完全独立

2. **调用链追踪**：用三种互补方法
   - Monkey-patch 追踪（运行时调用栈）
   - 静态依赖扫描（`grep` imports）
   - 入口点普查（`examples/` 目录结构）

3. **三层配置体系**：robot YAML / task YAML / MJCF XML 各管什么、在哪里汇合

**验收方式**：架构图必须是**你自己画的**（Mermaid），且能对着它讲 10 分钟不看稿。

### 5.2 四条核心链路溶进对应测试日

| 链路 | 溶进哪天 | 读什么 | 为什么测试必须懂 |
|------|---------|--------|-----------------|
| **仿真内核：步进与控制** | Day 3-4 确定性攻坚 | `simulator.py:639 step()`、`universal_task_runtime.py:213 step(decimation=5)`、`opt.timestep`/`decimation` 关系 | 不懂 decimation 与控制频率的关系，就分不清"仿真不确定"是物理引擎问题还是控制时序问题 |
| **场景拼装：MJCF 合并** | Day 1-2 配置层单测 | `make_env.py:143 _merge_robot_and_pure_task()`、`_convert_paths_to_absolute()`（425行） | 9×5=45 组合中某些会挂，根因常在 XML 合并（site/body 命名冲突、路径解析）。不懂就只能报"任务失败"，说不出根因 |
| **运动学：IK 内部** | Day 3-4 + Day 15-17 MMK2 | `mink_solver.py` 全文、mink 的 `FrameTask`/`PostureTask` 代价函数、`solve_ik` 迭代收敛判据 | 直接对接你的工业机器人运动学背景。要能回答"为什么不收敛""容差怎么定" |
| **数据流：采集与编码** | Day 18-19 数据质量 | `universal_task_runtime.py:107 get_observation()` → `recorder.py` H.264 编码 → `obs_action.json` | 具身智能"数据即产品"。要能说清时间戳如何对齐、多相机如何同步、丢帧在哪产生 |

**强制约束**：读不懂就写不出那天的测试。这不是可选项。

### 5.3 已验证的依赖分层

```
第0层  discoverse/__init__.py    路径常量（不算功能依赖）
第1层  utils                     真正的最底层
第2层  robots  /  envs           都只依赖 utils，互不依赖
第3层  robots_env                依赖 envs
       universal_manipulation    只依赖 utils —— 刻意绕开 envs ⚠️
第4层  task_base                 依赖 robots + robots_env
```

---

## 六、详细执行计划

### Day 0（启动）✅ 已完成

**任务清单**：
- [x] 建 `feat/test-infra` 分支
- [x] 装 pytest 全家桶：`pytest pytest-cov pytest-xdist pytest-timeout pytest-repeat hypothesis`
- [x] 装无头渲染：`libosmesa6-dev xvfb`
- [x] 建 `docs/devil-note.md`
- [x] 复跑基线数据：8 次跑 place_block，记录成功率和失败时的 `完成状态: X/10`

**验收标准**：
- `pytest --version` 正常
- `MUJOCO_GL=osmesa` 渲染测试通过，**且 mean pixel ≠ 0**（关键检查点）
- `env -u DISPLAY` 下真实任务能跑完（无 GL 报错即可）
- 拿到自己的基线成功率数字（实测 75%）

**教程文档**：`docs/tutorial/day00-setup.md`

---

### Day 1 上午｜全局架构鸟瞰

**目标**：理解 DISCOVERSE 的整体架构，产出自己的架构图。

**步骤 1｜用三种方法发现调用链**

1. **入口点普查**（5 分钟）
   ```bash
   cd /home/ubuntu22/workspaces/airbot-play/DISCOVERSE
   find examples/ -name "*.py" -type f | head -20
   ```
   观察：`examples/universal_tasks/` vs `examples/tasks_airbot_play/` vs `examples/tasks_mmk2/`

2. **静态依赖扫描**（10 分钟）
   ```bash
   # 扫描 universal_manipulation 的依赖
   grep -rhoE "from discoverse\.[a-z_]+" discoverse/universal_manipulation/ | sort -u
   
   # 关键验证：是否 import SimulatorBase？
   grep -r "SimulatorBase" discoverse/universal_manipulation/
   # 预期输出：无结果 → 说明路线 B 绕开了路线 A
   ```

3. **运行时追踪**（15 分钟）
   用 monkey-patch 打印调用链，观察 `universal_task_runtime.py` 启动后的模块加载顺序

**步骤 2｜画出架构图**

用 Mermaid 语法画出：
- 双路线架构（Route A vs Route B）
- 模块依赖关系（5 层）
- 三层配置体系汇合点

**步骤 3｜回答三个架构问题**

1. **为什么 `universal_manipulation` 不依赖 `envs`？**
   - 提示：Route B 是新框架，试图摆脱 SimulatorBase 的 658 行历史包袱
2. **MMK2 测试能不能复用 universal_tasks 的 fixture？**
   - 答：不能，MMK2 走 Route A（mmk2_base.py），universal_tasks 走 Route B
3. **9×5=45 组合中哪些会挂？根因在哪？**
   - 提示：MJCF 合并时 site/body 命名冲突

**产出**：`docs/architecture-notes.md`，包含架构图和三个问题的答案。

---

### Day 1 下午-2｜pytest 骨架 + 配置层单测

**目标**：建立测试框架骨架，把"精通 Pytest"坐实。

**步骤 1｜目录结构**

```bash
mkdir -p tests/{unit,kinematics,simulation,mobile_manipulation,data}
touch tests/__init__.py
```

创建：
```
tests/
├── conftest.py              # 根 fixture
├── pytest.ini               # markers/超时/覆盖率
├── unit/
│   ├── test_robot_config.py     # 9 个 YAML × 必填字段校验
│   ├── test_task_config.py      # 模板继承 extends 解析
│   ├── test_gripper_controller.py
│   └── test_success_conditions.py  # 5 种 condition 类型
├── kinematics/
│   └── test_ik_solver.py
└── data/
    └── test_recorder.py
```

**步骤 2｜编写 conftest.py**

关键 fixture（**面试必被问，务必能讲清作用域选择理由**）：

```python
import pytest
import mujoco
import numpy as np

@pytest.fixture(scope="session")
def mj_model_factory():
    """MjModel 加载慢（XML 解析 + mesh 加载），跨用例复用"""
    def _make(xml_path):
        return mujoco.MjModel.from_xml_path(xml_path)
    return _make

@pytest.fixture(scope="function")
def mj_data(mj_model_factory):
    """MjData 含可变仿真状态，必须每用例新建，否则测试间污染"""
    model = mj_model_factory("path/to/test.xml")
    return mujoco.MjData(model)
```

**步骤 3｜参数化测试示例**

```python
# tests/unit/test_robot_config.py
import pytest
from discoverse.universal_manipulation.robot_config import RobotConfigLoader

ROBOTS = ["airbot_play", "panda", "ur5e", "arx_x5", "arx_l5", "piper", "rm65", "xarm7", "iiwa14"]

@pytest.mark.parametrize("robot_name", ROBOTS)
def test_robot_config_required_fields(robot_name):
    """测试 9 个机器人配置的必填字段"""
    config_path = f"discoverse/configs/robots/{robot_name}.yaml"
    loader = RobotConfigLoader(config_path)
    
    # 必填字段校验
    assert loader.robot_name == robot_name
    assert len(loader.arm_joints) > 0
    assert loader.end_effector_site is not None
```

这直接对应简历上"Pytest 数据驱动框架"——9 机器人 × 5 任务 = 45 组合参数化。

**步骤 4｜编写 pytest.ini**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
markers =
    unit: 单元测试
    integration: 集成测试
    slow: 慢速测试
timeout = 60
addopts = --strict-markers --tb=short
```

**验收标准**：
```bash
pytest tests/unit -v  # 全绿
pytest tests/ --collect-only  # 能收集到至少 20 个测试
```

---

### Day 3-4｜确定性攻坚（本周核心，最有含金量）

**目标**：通过 TDD（测试驱动开发）修复仿真不可复现问题。

**标准 TDD 流程：红灯 → 实现 → 绿灯**

**步骤 1｜写"红灯"测试（证明问题存在）**

```python
# tests/simulation/test_determinism.py
import pytest
import numpy as np

def test_same_seed_produces_same_trajectory():
    """同一 seed 两次运行，qpos 轨迹应逐帧相同"""
    seed = 42
    trajectory1 = run_task_with_seed("airbot_play", "place_block", seed)
    trajectory2 = run_task_with_seed("airbot_play", "place_block", seed)
    
    # 当前必然失败（seed 未被消费）
    np.testing.assert_allclose(trajectory1, trajectory2, rtol=1e-5)
```

运行：`pytest tests/simulation/test_determinism.py -v`  
**预期**：❌ 红灯（AssertionError）

**步骤 2｜实现 seed 贯穿（问题 2 修复）**

修改 `discoverse/universal_manipulation/randomization.py`：

```python
class SceneRandomizer:
    def __init__(self, mj_model, mj_data, seed=None):
        self.mj_model = mj_model
        self.mj_data = mj_data
        self.rng = np.random.default_rng(seed)  # 使用 Generator 实例
    
    def randomize_position(self, body_name, x_range, y_range, z_range):
        # 替换所有 np.random.uniform 为 self.rng.uniform
        x = self.rng.uniform(*x_range)
        y = self.rng.uniform(*y_range)
        z = self.rng.uniform(*z_range)
        ...
```

**步骤 3｜修复 IK 状态泄漏（问题 7）**

```python
# discoverse/universal_manipulation/mink_solver.py
def solve_ik(self, target_pos, target_rmat, current_qpos):
    """IK 求解，不污染 self.configuration"""
    # 保存原始状态
    original_config = self.configuration.copy()
    
    try:
        # ... IK 求解逻辑 ...
        if converged:
            return solution, True, solve_info
        else:
            return None, False, solve_info
    finally:
        # 恢复原始状态（无论成功失败）
        self.configuration = original_config
```

**步骤 4｜再跑测试 → 绿灯**

```bash
pytest tests/simulation/test_determinism.py -v
```
**预期**：✅ 绿灯（测试通过）

**面试叙事**：
> "我发现 place_block 任务成功率只有 62.5%-75%，且完全不可复现。通过静态分析发现 `randomization.py` 里 20+ 处裸 `np.random.*` 调用，配置文件的 seed 字段从未被消费。我先写了一个确定性测试（同 seed 两次运行应得到相同轨迹），验证问题存在（红灯），然后引入 `np.random.Generator` 实例并贯穿整个随机化流程，测试变绿。同时修复了 IK 求解器的状态泄漏问题。最终将任务成功率提升到 X%，且完全可复现。"

**产出**：
- `tests/simulation/test_determinism.py`（红→绿的完整历史 commit）
- 修复后的 `randomization.py` 和 `mink_solver.py`

---

### Day 5｜Flake 定量分析（差异化亮点）

**目标**：产出 flake 热力图和根因分桶报告。

**步骤 1｜批量重复测试**

```bash
# 使用 pytest-repeat 跑 45 组合 × 50 次
pytest tests/integration/test_task_matrix.py \
  --count=50 \
  -n 8 \
  --tb=no \
  --json-report \
  --json-report-file=flake_report.json
```

**步骤 2｜失败分桶**

按 `完成状态: X/10` 分类：
- **Bucket 1: `1/10`** — IK 早期不收敛（第一步就挂）
- **Bucket 2: `10/10`** — 最终判据失败（抓取滑脱、物体位置不可达）
- **Bucket 3: 超时** — 死循环或物理引擎卡住

**步骤 3｜生成热力图**

用 matplotlib/seaborn 生成：
- X 轴：9 种机器人
- Y 轴：5 种任务
- 颜色：成功率（0%-100%）
- 标注：失败模式（Bucket 1/2/3）

**产出**：`docs/flakiness-analysis.md`

**面试叙事**：
> "我把 45 个任务组合各跑 50 次，收集了 2250 次运行数据。发现 flake 不是均匀分布的：airbot_play + place_block 成功率 75%，但 panda + cover_cup 只有 40%。我把失败按根因分桶，发现低成功率主要是 IK 早期不收敛（Bucket 1），而非最终判据问题。这指导了后续的 IK 容差调优方向。"

---

### Day 6-7｜缺陷分析报告（代替原 PR 计划）

**目标**：产出工业级缺陷分析报告，代替上游 PR。

**格式规范**（每个缺陷一个章节）：

```markdown
## 缺陷 #2：域随机化 seed 配置未被消费

**严重级别**：🔴 Critical

**影响模块**：`discoverse/universal_manipulation/randomization.py`

**复现步骤**：
1. 编辑 `discoverse/configs/tasks/place_block.yaml`，设置 `settings.seed: 42`
2. 运行两次：`python examples/universal_tasks/universal_task_runtime.py -r airbot_play -t place_block -1 --headless`
3. 观察：物体位置完全不同（应相同）

**预期行为 vs 实际行为**：
- 预期：相同 seed → 相同物体初始位置 → 轨迹可复现
- 实际：seed 配置被声明但从未被任何代码读取，`np.random.*` 裸调用使用全局随机状态

**根因分析**：
- `randomization.py:45-70`：所有随机化函数直接调用 `np.random.uniform()`、`np.random.choice()`
- `task_config.py:88`：读取了 `randomization.settings.seed`，但只存在 `self.randomization` 字典里
- `SceneRandomizer.__init__()`：构造函数未接受 seed 参数
- **系统性缺失**：配置 → 代码的整条链路未打通

**修复方案**：
```python
# randomization.py
class SceneRandomizer:
    def __init__(self, mj_model, mj_data, seed=None):
        self.rng = np.random.default_rng(seed)  # 使用 Generator 实例
        ...
```

**回归验证**：
- 测试用例：`tests/simulation/test_determinism.py::test_same_seed_produces_same_trajectory`
- 修复前：❌ 失败
- 修复后：✅ 通过
```

**重点打磨 3 个高价值缺陷**：

1. **问题 2（seed 死配置）** — 系统性缺失，讲清"配置项声明了但整条链路没实现"的定位过程
2. **问题 1（退出码恒为 0）** — CI 视角，讲清"为什么这让自动化失效"
3. **问题 7（IK 状态泄漏）** — 需要运动学理解，体现你的差异化背景

**其余 10 个缺陷**：简写（缺陷描述 + 修复方案 + 影响范围）

**产出**：`docs/defect-report.md`（预计 15-20 页）

**面试用法**：纸质打印带去，问到"你怎么做缺陷分析"时直接翻开。比口头描述强十倍。

---

### 第 1 周小结

**已产出**：
- ✅ `docs/architecture-notes.md`（架构图 + 双路线分析）
- ✅ `tests/` 目录（45+ 用例，pytest 骨架完整）
- ✅ 确定性测试从红到绿（TDD 完整历史）
- ✅ `docs/flakiness-analysis.md`（flake 热力图 + 根因分桶）
- ✅ `docs/defect-report.md`（13 个缺陷完整闭环）

**验收标准**：
```bash
pytest tests/unit -v                                   # 全绿
pytest tests/simulation/test_determinism.py -v         # 修复后绿灯
pytest tests/ --count=10 -p no:randomly                # flake 统计可复现
pytest tests/ --cov=discoverse --cov-report=html       # 覆盖率可测量
```

---

### Day 8-9｜Docker 测试镜像

**目标**：构建真无头测试镜像，解决 CI 渲染问题。

**步骤 1｜分析现有 Dockerfile**

```bash
cat discoverse/docker/Dockerfile | grep -E "FROM|RUN apt|RUN pip" | head -20
```

识别：
- 基础镜像（可能是 nvidia/cuda:11.8）
- 已有依赖（libosmesa6-dev 可能已装）
- 冗余依赖（3DGS 训练相关、CUDA 库）

**步骤 2｜编写瘦身 Dockerfile.test**

```dockerfile
# discoverse/docker/Dockerfile.test
FROM nvidia/cuda:11.8.0-base-ubuntu22.04

# 系统依赖（无头渲染刚需）
RUN apt-get update && apt-get install -y \
    python3.10 python3-pip git \
    libosmesa6-dev xvfb libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖（剥离 3DGS）
COPY requirements-test.txt /tmp/
RUN pip3 install -r /tmp/requirements-test.txt

# 固化渲染后端
ENV MUJOCO_GL=osmesa

WORKDIR /workspace
COPY . /workspace/

# 验证渲染可用
RUN python3 -c "import mujoco; print('MuJoCo OK')"

CMD ["pytest", "tests/", "-v"]
```

**步骤 3｜多阶段构建优化**

```dockerfile
# 第一阶段：构建依赖
FROM python:3.10-slim as builder
RUN pip install --user pytest pytest-cov ...

# 第二阶段：运行时
FROM python:3.10-slim
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH
```

**步骤 4｜docker-compose.test.yml**

```yaml
version: '3.8'
services:
  test:
    build:
      context: .
      dockerfile: discoverse/docker/Dockerfile.test
    environment:
      - MUJOCO_GL=osmesa
    volumes:
      - ./tests:/workspace/tests:ro
      - ./discoverse:/workspace/discoverse:ro
    command: pytest tests/unit -v
```

**步骤 5｜记录瘦身效果**

```bash
docker images | grep discoverse
# 记录：原镜像 X GB → 测试镜像 Y GB（可量化，面试爱听）
```

**验收标准**：
```bash
docker build -f discoverse/docker/Dockerfile.test -t discoverse:test .
docker run --rm discoverse:test pytest tests/unit -v   # 容器内无 DISPLAY 必须能跑通
```

**产出**：`Dockerfile.test`、`docker-compose.test.yml`、瘦身记录（写入 devil-note）

---

### Day 10-11｜GitHub Actions 主线

**目标**：建立分层 CI 流水线，获得绿色徽章。

**步骤 1｜创建 .github/workflows/ci.yml**

```yaml
name: CI

on:
  push:
    branches: [feat/test-infra]
  pull_request:

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - run: pip install ruff black
      - run: ruff check discoverse/ tests/
      - run: black --check discoverse/ tests/

  unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Install dependencies
        run: |
          sudo apt-get update
          sudo apt-get install -y libosmesa6-dev xvfb
          pip install -e .
          pip install pytest pytest-cov pytest-xdist
      - name: Run unit tests
        env:
          MUJOCO_GL: osmesa
        run: pytest tests/unit -v --cov=discoverse --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v3

  integration:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Build test image
        run: docker build -f discoverse/docker/Dockerfile.test -t discoverse:test .
      - name: Run integration tests
        run: docker run --rm discoverse:test pytest tests/kinematics tests/simulation -v
```

**步骤 2｜添加 nightly job（flake 监控）**

```yaml
  nightly:
    runs-on: ubuntu-latest
    if: github.event_name == 'schedule'
    steps:
      - uses: actions/checkout@v3
      - name: Run flake detection
        run: |
          docker build -f discoverse/docker/Dockerfile.test -t discoverse:test .
          docker run --rm discoverse:test pytest tests/integration/test_task_matrix.py --count=50 -n 8 --json-report
      - name: Upload flake report
        uses: actions/upload-artifact@v3
        with:
          name: flake-report
          path: flake_report.json

on:
  schedule:
    - cron: '0 2 * * *'  # 每天凌晨 2 点（避开 :00 和 :30）
```

**步骤 3｜README 徽章**

```markdown
# DISCOVERSE

[![CI](https://github.com/Cyberpunk-edgerunners/DISCOVERSE-learning/actions/workflows/ci.yml/badge.svg)](https://github.com/Cyberpunk-edgerunners/DISCOVERSE-learning/actions)
[![codecov](https://codecov.io/gh/Cyberpunk-edgerunners/DISCOVERSE-learning/branch/feat/test-infra/graph/badge.svg)](https://codecov.io/gh/Cyberpunk-edgerunners/DISCOVERSE-learning)
```

**验收标准**：
- Push 后 GitHub Actions 全绿
- README 徽章显示 ✅ passing
- 覆盖率报告可访问

**产出**：`.github/workflows/ci.yml`（5-job 流水线）

---

### Day 12｜Jenkins 辅线（GPU 夜间回归）

**目标**：利用本地 jenkins_server:8080，建立 GPU 回归任务。

**为什么需要 Jenkins**（面试必问）：
- GitHub Actions 免费 runner 无 GPU
- 本地有 RTX 4060，可跑需要 GPU 的测试（如 3DGS 渲染，虽然我们暂不做）
- **真实理由**：差异化 CI 策略，轻量级测试走云端，重型测试走本地

**步骤 1｜编写 Jenkinsfile**

```groovy
pipeline {
    agent any
    
    environment {
        MUJOCO_GL = 'glfw'  // 本地有 DISPLAY，用 glfw
        CUDA_VISIBLE_DEVICES = '0'
    }
    
    stages {
        stage('Checkout') {
            steps {
                git branch: 'feat/test-infra',
                    url: 'git@github.com:Cyberpunk-edgerunners/DISCOVERSE-learning.git'
            }
        }
        
        stage('Install Dependencies') {
            steps {
                sh '''
                    conda activate discoverse
                    pip install -e .
                '''
            }
        }
        
        stage('GPU Tests') {
            steps {
                sh '''
                    conda activate discoverse
                    pytest tests/simulation -v --tb=short
                '''
            }
        }
    }
    
    post {
        always {
            junit 'test-results/*.xml'
            archiveArtifacts artifacts: 'test-results/*', allowEmptyArchive: true
        }
    }
}
```

**步骤 2｜Jenkins 配置**

1. 访问 http://localhost:8080
2. 新建 Pipeline 任务："DISCOVERSE-GPU-Regression"
3. 配置：
   - Pipeline script from SCM
   - Git: `git@github.com:Cyberpunk-edgerunners/DISCOVERSE-learning.git`
   - Branch: `feat/test-infra`
   - Script Path: `Jenkinsfile`
4. 触发器：Build periodically `0 3 * * *`（每天凌晨 3 点）

**步骤 3｜Docker-in-Docker 配置（对应简历原文）**

```groovy
agent {
    docker {
        image 'discoverse:test'
        args '-v /var/run/docker.sock:/var/run/docker.sock --gpus all'
    }
}
```

这正好对应简历那句"Docker-in-Docker"——这次是真做过了。

**验收标准**：
- Jenkins job 手动触发能成功
- 控制台输出显示 GPU 可用（`nvidia-smi` 有输出）

**产出**：`Jenkinsfile`、Jenkins job 配置截图

---

### 第 2 周小结

**已产出**：
- ✅ `Dockerfile.test`（瘦身记录：X GB → Y GB）
- ✅ `.github/workflows/ci.yml`（5-job 流水线 + 绿色徽章）
- ✅ `Jenkinsfile`（GPU 夜间回归）
- ✅ 结构化结果契约（见 Day 13-14）

---

### Day 13-14｜重构 cicd_testing.py 为结构化结果契约

**目标**：替换 emoji 字符串匹配，建立机器可读的结果契约。

**步骤 1｜定义结果 Schema**

```python
# discoverse/testing/result_schema.py
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class TaskResult:
    robot: str
    task: str
    success: bool
    completed_states: int
    total_states: int
    sim_time: float
    wall_time: float
    exit_code: int
    error_message: Optional[str] = None
    failure_mode: Optional[str] = None  # "ik_early" | "final_check" | "timeout"
```

**步骤 2｜修改 universal_task_runtime.py 输出**

```python
# universal_task_runtime.py
def main(...):
    result = {
        "robot": robot_name,
        "task": task_name,
        "success": success,
        "completed_states": executor.stm.state_idx,
        "total_states": executor.total_states,
        "sim_time": executor.mj_data.time,
        "wall_time": elapsed_time,
        "exit_code": 0 if success else 1
    }
    
    # 写入 JSON 文件
    import json
    with open(f"/tmp/discoverse_result_{os.getpid()}.json", "w") as f:
        json.dump(result, f)
    
    sys.exit(0 if success else 1)  # 修复问题 1
```

**步骤 3｜重构 cicd_testing.py**

```python
# cicd_testing.py
def run_single_test(robot, task, timeout=60):
    """读取结构化结果文件，而非 parse stdout"""
    result_file = f"/tmp/discoverse_result_{process.pid}.json"
    
    try:
        process = subprocess.run(
            ["python", "examples/universal_tasks/universal_task_runtime.py",
             "-r", robot, "-t", task, "-1", "--headless"],
            timeout=timeout,
            capture_output=True
        )
        
        # 读取结果文件
        with open(result_file) as f:
            result = json.load(f)
        
        # 不再依赖字符串匹配和 emoji
        return TaskResult(**result)
        
    except subprocess.TimeoutExpired:
        return TaskResult(robot=robot, task=task, success=False, 
                         exit_code=-1, failure_mode="timeout", ...)
```

**步骤 4｜生成 JUnit XML**

```python
import pytest
from _pytest.junitxml import LogXML

def generate_junit_xml(results: List[TaskResult], output_path: str):
    """让 GitHub Actions / Jenkins 原生渲染"""
    # 使用 pytest 的 JUnit XML 生成器
    ...
```

**验收标准**：
- `cicd_testing.py` 不再有字符串匹配（`"✅ 任务成功检查通过" in output`）
- 使用 `process.returncode` 判断失败（修复问题 4）
- 用户 `-r` 传入表外机器人会报错而非静默丢弃（修复问题 12）
- 生成的 JUnit XML 能被 GitHub Actions Test Reporter 正确解析

**产出**：重构后的 `cicd_testing.py`、`result_schema.py`

---

### Day 15-17｜MMK2 双臂轮式专项测试（差异化核心）

**目标**：利用工业机器人运动学背景，做具身智能移动操作测试。

**已验证**：`MMK2Base` headless 可实例化（nu=19, nq=28）

**步骤 1｜MMK2 运动学测试**

```python
# tests/mobile_manipulation/test_mmk2_kinematics.py
import pytest
from discoverse.robots.mmk2.mmk2_fk import get_armjoint_pose_wrt_footprint
from discoverse.robots.mmk2.mmk2_fik import solve_mmk2_ik

def test_fk_ik_fk_consistency():
    """FK→IK→FK 往返一致性（工业机器人经典测试）"""
    # 给定关节角
    joint_angles = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
    
    # FK：关节角 → 末端位姿
    pose1 = get_armjoint_pose_wrt_footprint(joint_angles, arm='left')
    
    # IK：末端位姿 → 关节角
    joint_solution = solve_mmk2_ik(pose1, arm='left')
    
    # FK：求解的关节角 → 末端位姿
    pose2 = get_armjoint_pose_wrt_footprint(joint_solution, arm='left')
    
    # 往返误差应 < 1mm
    np.testing.assert_allclose(pose1[:3], pose2[:3], atol=1e-3)
```

**这是你的主场**：工业机器人的重复定位精度、运动学标定思维，直接迁移到仿真验证。

**步骤 2｜差速驱动测试**

```python
# tests/mobile_manipulation/test_differential_drive.py
def test_straight_line_motion():
    """直线运动测试：左右轮相同速度 → 直线度误差 < 5%"""
    action = np.zeros(19)
    action[0] = 0.5  # 左轮速度
    action[1] = 0.5  # 右轮速度
    
    initial_pos = mj_data.qpos[:2].copy()
    
    # 运行 100 步
    for _ in range(100):
        mj_data.ctrl[:] = action
        mujoco.mj_step(mj_model, mj_data)
    
    final_pos = mj_data.qpos[:2].copy()
    displacement = final_pos - initial_pos
    
    # 验证直线度：横向偏移 / 纵向位移 < 5%
    straightness = abs(displacement[0]) / abs(displacement[1])
    assert straightness < 0.05

def test_turning_radius():
    """转弯测试：左右轮差速 → 实际转弯半径 vs 理论值"""
    ...
```

**步骤 3｜升降测试**

```python
# tests/mobile_manipulation/test_slide_lift.py
def test_lift_range():
    """升降行程测试：0-0.87m，精度 ±5mm"""
    target_heights = [0.0, 0.2, 0.5, 0.87]
    
    for h in target_heights:
        action[2] = h  # 升降控制
        # ... 运行仿真 ...
        actual_h = mj_data.qpos[2]
        assert abs(actual_h - h) < 0.005  # 5mm 容差
```

**步骤 4｜双臂协同测试**

```python
# tests/mobile_manipulation/test_dual_arm_coordination.py
def test_self_collision_detection():
    """双臂协同：自碰撞检测"""
    # 让左右臂移动到可能碰撞的位置
    left_arm_pose = [...]
    right_arm_pose = [...]
    
    # 检查 MuJoCo 碰撞对
    for i in range(mj_data.ncon):
        contact = mj_data.contact[i]
        geom1 = mj_model.geom(contact.geom1).name
        geom2 = mj_model.geom(contact.geom2).name
        
        # 检测左臂与右臂的碰撞
        if "left_arm" in geom1 and "right_arm" in geom2:
            pytest.fail(f"Self-collision detected: {geom1} <-> {geom2}")

def test_workspace_overlap():
    """工作空间重叠区域验证"""
    # 计算左臂可达空间
    left_workspace = compute_reachable_workspace('left')
    # 计算右臂可达空间
    right_workspace = compute_reachable_workspace('right')
    
    # 重叠区域应 > 30% 总空间（协作任务需求）
    overlap = left_workspace.intersection(right_workspace)
    assert overlap.volume / left_workspace.volume > 0.3
```

**面试叙事**：
> "我在工业机器人测试中积累了运动学标定和重复定位精度验证经验。在 MMK2 双臂移动机器人测试中，我把这套思维迁移过来：FK→IK→FK 往返一致性测试验证运动学求解精度，差速驱动直线度测试验证底盘控制，双臂自碰撞检测验证协同安全性。这是我相对纯软件测试候选人的差异化优势。"

**产出**：`tests/mobile_manipulation/` 目录，4 个测试模块

---

### Day 18-19｜数据质量验证器（具身智能特有）

**目标**：对应"策略学习的数据是产品"这个具身智能核心命题。

**步骤 1｜创建数据验证模块**

```python
# discoverse/data_validation/image_quality.py
import cv2
import numpy as np

def check_image_clarity(image: np.ndarray, threshold: float = 100.0) -> dict:
    """检查图像清晰度（Laplacian 方差）"""
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    
    return {
        "laplacian_variance": laplacian_var,
        "is_clear": laplacian_var > threshold,
        "quality": "high" if laplacian_var > 200 else "medium" if laplacian_var > 100 else "low"
    }

def detect_motion_blur(image: np.ndarray) -> dict:
    """检测运动模糊"""
    ...
```

**步骤 2｜轨迹平滑度检查**

```python
# discoverse/data_validation/trajectory_quality.py
def check_trajectory_smoothness(joint_positions: np.ndarray, dt: float = 0.02) -> dict:
    """检查关节轨迹平滑度（jerk 阈值）"""
    # 速度（一阶导数）
    velocity = np.diff(joint_positions, axis=0) / dt
    # 加速度（二阶导数）
    acceleration = np.diff(velocity, axis=0) / dt
    # jerk（三阶导数）
    jerk = np.diff(acceleration, axis=0) / dt
    
    max_jerk = np.max(np.abs(jerk), axis=0)
    
    return {
        "max_jerk_per_joint": max_jerk.tolist(),
        "is_smooth": np.all(max_jerk < 50.0),  # 阈值需调优
        "problematic_joints": np.where(max_jerk > 50.0)[0].tolist()
    }
```

**步骤 3｜时间戳同步性检查**

```python
# discoverse/data_validation/temporal_quality.py
def check_timestamp_consistency(obs_data: list) -> dict:
    """检查时间戳单调性和丢帧"""
    timestamps = [obs["time"] for obs in obs_data]
    
    # 检查单调性
    is_monotonic = all(timestamps[i] < timestamps[i+1] for i in range(len(timestamps)-1))
    
    # 检查丢帧
    expected_dt = 1.0 / 30.0  # 假设 30 FPS
    actual_dts = np.diff(timestamps)
    dropped_frames = np.sum(actual_dts > expected_dt * 1.5)
    
    return {
        "is_monotonic": is_monotonic,
        "dropped_frames": int(dropped_frames),
        "avg_fps": len(timestamps) / (timestamps[-1] - timestamps[0]),
        "timestamp_gaps": np.where(actual_dts > expected_dt * 1.5)[0].tolist()
    }
```

**步骤 4｜obs-action 一致性检查**

```python
# discoverse/data_validation/consistency.py
def check_obs_action_consistency(dataset_path: str) -> dict:
    """检查 obs 和 action 维度/长度一致性"""
    with open(os.path.join(dataset_path, "obs_action.json")) as f:
        data = json.load(f)
    
    obs_lengths = [len(ep["observations"]) for ep in data]
    action_lengths = [len(ep["actions"]) for ep in data]
    
    return {
        "episodes": len(data),
        "obs_action_length_match": obs_lengths == action_lengths,
        "dimension_consistent": check_all_same_dim(data),
        "problematic_episodes": find_mismatched_episodes(data)
    }
```

**步骤 5｜CLI 工具**

```python
# discoverse/data_validation/cli.py
import argparse

def main():
    parser = argparse.ArgumentParser(description="DISCOVERSE 数据质量验证器")
    parser.add_argument("--dataset", type=str, required=True, help="数据集路径")
    parser.add_argument("--checks", nargs="+", 
                       choices=["image", "trajectory", "timestamp", "consistency", "all"],
                       default=["all"])
    parser.add_argument("--report", type=str, default="validation_report.json")
    
    args = parser.parse_args()
    
    results = {}
    if "image" in args.checks or "all" in args.checks:
        results["image_quality"] = validate_images(args.dataset)
    # ... 其他检查 ...
    
    with open(args.report, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"✅ 验证完成，报告已保存到 {args.report}")

if __name__ == "__main__":
    main()
```

**验收标准**：
```bash
python -m discoverse.data_validation.cli --dataset data/airbot_play_place_block --checks all
```

**顺带修复**：
- 问题 10（save_dir episode 覆盖）：在 save_dir 后加 episode 索引
- 问题 11（assert 剥离）：用显式 if + raise 替换 `assert`

**产出**：`discoverse/data_validation/` 模块，CLI 工具

---

### Day 20-21｜求职材料（不要压到最后一天）

**目标**：将三周产出转化为可展示的求职材料。

**步骤 1｜重写简历**

**原简历问题**：
- "精通 Pytest 数据驱动测试" — 模糊，无法验证
- "Docker + Jenkins CI/CD 平台从 0 到 1" — 无 GitHub 链接

**改写为可验证的具体成果**：

```markdown
## 项目经历

### DISCOVERSE 具身智能仿真平台测试基建实践
**时间**：2026.07（3 周全职）  
**项目链接**：https://github.com/Cyberpunk-edgerunners/DISCOVERSE-learning

**背景**：
- IROS 2025 开源项目，支持 9 种机械臂 + 2 种双臂移动机器人，测试覆盖率 ~5%，无 CI
- place_block 任务成功率仅 62.5%-75%，且完全不可复现

**工作内容**：
1. **测试框架建设**：从 0 建立 pytest 分层测试体系（unit/integration/simulation），45+ 测试用例，核心模块覆盖率提升至 X%
2. **确定性攻坚**：定位仿真不可复现根因（域随机化 seed 配置未被消费），通过 TDD 方式修复（红灯→绿灯），将任务成功率提升至 X%
3. **Flake 定量分析**：批量重复测试（45 组合 × 50 次），产出热力图和根因分桶报告，指导 IK 容差调优
4. **CI/CD 双线**：搭建 GitHub Actions 5-job 流水线（lint/unit/integration/nightly）+ Jenkins GPU 回归
5. **MMK2 专项测试**：FK→IK→FK 往返一致性、差速驱动直线度、双臂自碰撞检测（工业机器人经验迁移）
6. **缺陷分析**：系统性定位并修复 13 项缺陷，产出完整缺陷报告（复现→根因→修复→回归）

**技术栈**：Pytest, Docker, GitHub Actions, Jenkins, MuJoCo, Python

**成果**：
- 测试覆盖率：5% → X%
- 任务成功率：62.5%-75% → X%（可复现）
- 缺陷修复：13 个（含系统性缺失）
- CI 徽章：✅ passing
```

**步骤 2｜README-testing.md（项目门面）**

```markdown
# DISCOVERSE 测试开发实践

[![CI](https://github.com/Cyberpunk-edgerunners/DISCOVERSE-learning/actions/workflows/ci.yml/badge.svg)](...)
[![codecov](https://codecov.io/gh/.../badge.svg)](...)

本项目是对 DISCOVERSE 具身智能仿真平台的测试基建实践。

## 快速开始

\```bash
# 安装依赖
pip install -e .
pip install pytest pytest-cov pytest-xdist pytest-timeout

# 运行测试
pytest tests/unit -v                    # 单元测试
pytest tests/simulation -v              # 确定性测试
pytest tests/ --cov=discoverse          # 覆盖率测量

# Docker 测试
docker build -f discoverse/docker/Dockerfile.test -t discoverse:test .
docker run --rm discoverse:test pytest tests/ -v
\```

## 测试架构

\```
tests/
├── unit/               # 配置层、IK 求解器单元测试
├── kinematics/         # 运动学测试（FK-IK 往返一致性）
├── simulation/         # 确定性测试、flake 分析
├── mobile_manipulation/ # MMK2 双臂轮式专项
└── data/               # 数据质量验证
\```

## 核心成果

- 📈 覆盖率：5% → X%
- 🎯 成功率：62.5%-75% → X%（可复现）
- 🐛 缺陷修复：13 个
- 🚀 CI/CD：GitHub Actions + Jenkins 双线

## 技术亮点

详见 [docs/defect-report.md](docs/defect-report.md) 和 [docs/flakiness-analysis.md](docs/flakiness-analysis.md)
```

**步骤 3｜一页 A4 技术总结（面试带纸质版）**

```markdown
# DISCOVERSE 测试开发技术总结

## 核心成果（可量化）
- 测试用例：0 → 45+（9 机器人 × 5 任务参数化）
- 覆盖率：5% → X%（核心模块 universal_manipulation）
- 成功率：62.5%-75% → X%（place_block 任务，可复现）
- CI/CD：从无到有（GitHub Actions 5-job + Jenkins GPU）
- 缺陷修复：13 个（含 3 个 Critical）

## 三大技术突破

### 1. 确定性攻坚（TDD 实践）
**问题**：仿真完全不可复现（相同输入 → 不同输出）
**定位**：静态分析发现 randomization.py 里 20+ 处裸 np.random.* 调用，配置文件的 seed 从未被消费
**方案**：引入 np.random.Generator 实例 + 修复 IK 求解器状态泄漏
**验证**：TDD 红灯→绿灯（tests/simulation/test_determinism.py）

### 2. Flake 定量分析（差异化）
**数据**：45 组合 × 50 次 = 2250 次运行
**发现**：成功率不均匀分布，airbot_play+place_block 75% vs panda+cover_cup 40%
**分桶**：IK 早期不收敛（1/10）vs 最终判据失败（10/10）vs 超时
**价值**：指导 IK 容差调优方向

### 3. 工业机器人经验迁移（差异化）
**MMK2 双臂移动机器人专项测试**：
- FK→IK→FK 往返一致性（运动学标定思维）
- 差速驱动直线度（±5% 容差）
- 双臂自碰撞检测（协同安全性）

## 面试准备的 5 个深度问题

1. **为什么 mj_model 用 session scope 而 mj_data 用 function scope？**
   答：MjModel 不可变且加载慢（XML+mesh），跨用例复用；MjData 含可变仿真状态，必须每用例新建避免污染

2. **仿真测试的 flaky 和 Web 测试的 flaky 本质区别？**
   答：Web 主要是异步时序（sleep/wait），仿真还有物理引擎数值稳定性（接触求解器、IK 收敛）

3. **没有真机怎么保证 Sim2Real 有效性？**
   答：(1) 物理参数标定（惯量、摩擦系数）(2) 域随机化覆盖真实分布 (3) 真机回环验证

4. **CI 里 osmesa 和 EGL 为什么选前者？**
   答：CI 环境优先选确定性高的方案，性能是次要的。osmesa 纯 CPU 软渲染，零依赖必然能跑；EGL 依赖驱动配置

5. **具身智能测试和传统软件测试最大的不同？**
   答：(1) 数据即产品（数据质量 = 策略质量）(2) 物理仿真的不确定性（确定性是奢侈品，不是默认）(3) 多模态（视觉+关节+力）
```

**步骤 4｜模拟面试自测（务必做）**

**准备方式**：
1. 把 devil-note 里的每日记录整理成 STAR 故事（Situation, Task, Action, Result）
2. 对着镜子讲一遍，计时 3-5 分钟
3. 录音回听，识别口头禅和不必要的停顿

**必练 10 题**：

**基础题（3 个）**：
1. 介绍一下你在 DISCOVERSE 上做了什么？（3 分钟电梯演讲）
2. 你用过哪些 pytest 插件？为什么选择它们？
3. Docker 镜像从 X GB 瘦身到 Y GB，你怎么做的？

**深度题（5 个）**：
4. 讲讲你定位 seed 配置未被消费这个问题的过程（问题 2）
5. 为什么说"仿真不可复现"是 Critical 级别的缺陷？
6. Flake 分析你跑了 2250 次，为什么不是 100 次或 5000 次？
7. MMK2 的 FK→IK→FK 测试，容差怎么定的？1mm 还是 1cm？
8. 数据质量验证器里，Laplacian 方差阈值 100.0 怎么来的？

**挑战题（2 个）**：
9. 如果让你从头设计一个具身智能项目的测试体系，你会怎么做？
10. 你的测试发现了 13 个缺陷，maintainer 说"我们不认为这是 bug"，你怎么办？

**答题要点**：
- 用数字说话（62.5% → X%，45 组合，2250 次运行）
- 讲清"为什么"（不是"我做了 X"，而是"因为 Y 问题，我做了 X，达到了 Z 效果"）
- 诚实（不知道就说不知道，但要说"我会怎么去查"）

**产出**：
- 重写的简历（PDF）
- README-testing.md
- 技术总结（一页 A4，纸质打印）
- 模拟面试录音（自我复盘用）

---

### 第 3 周小结

**已产出**：
- ✅ MMK2 专项测试（4 个模块）
- ✅ 数据质量验证器（CLI 工具 + 4 种检查）
- ✅ 重写简历（可验证的具体成果）
- ✅ README-testing.md（项目门面）
- ✅ 技术总结（一页 A4）
- ✅ 模拟面试准备（10 题）

---

## 七、验收标准

### 7.1 总验收清单

**第 1 周**：
- [ ] `docs/architecture-notes.md` 含自绘架构图（Mermaid），能脱稿讲 10 分钟
- [ ] `tests/` 目录完整，`pytest tests/ --collect-only` 收集到 45+ 用例
- [ ] `pytest tests/unit -v` 全绿
- [ ] `pytest tests/simulation/test_determinism.py -v` 修复后绿灯（修复前有红灯的 commit 记录）
- [ ] `docs/flakiness-analysis.md` 含热力图和根因分桶
- [ ] `docs/defect-report.md` 完成 13 个缺陷闭环

**第 2 周**：
- [ ] `docker build -f discoverse/docker/Dockerfile.test -t discoverse:test .` 成功
- [ ] `docker run --rm discoverse:test pytest tests/unit -v` 容器内无 DISPLAY 能跑通
- [ ] GitHub Actions 全绿，README 徽章显示 ✅ passing
- [ ] Jenkins job 手动触发成功，控制台有 GPU 信息
- [ ] `cicd_testing.py` 不再有 emoji 字符串匹配，使用结构化 JSON

**第 3 周**：
- [ ] `pytest tests/mobile_manipulation -v` 全绿
- [ ] `python -m discoverse.data_validation.cli --dataset data/xxx --checks all` 成功
- [ ] 重写的简历 PDF 含 GitHub 链接和可量化成果
- [ ] `README-testing.md` 完成，项目门面清晰
- [ ] 技术总结打印为纸质版

**整体**：
- [ ] 覆盖率从 ~5% 提升到可量化数字（**诚实报告实际值**）
- [ ] `place_block` 成功率从 62.5%-75% 提升到可量化数字，且可复现
- [ ] 13 个缺陷全部完成「复现→根因→修复→回归验证」闭环
- [ ] 容器内无 DISPLAY 跑通全套测试

### 7.2 每日验收命令

```bash
# Day 0
pytest --version
python -c "import pytest_cov, pytest_repeat, xdist, pytest_timeout; print('OK')"
MUJOCO_GL=osmesa python -c "import mujoco; m=mujoco.MjModel.from_xml_string('<mujoco><worldbody><geom type=\"box\" size=\".1 .1 .1\"/></worldbody></mujoco>'); d=mujoco.MjData(m); r=mujoco.Renderer(m,64,64); r.update_scene(d); print('mean=',r.render().mean())"

# Day 1-2
pytest tests/unit -v
pytest tests/ --collect-only | grep "test session starts"

# Day 3-4
git log --oneline --grep="test_determinism" | head -5  # 应看到红→绿的 commit
pytest tests/simulation/test_determinism.py -v

# Day 5
ls docs/flakiness-analysis.md

# Day 6-7
ls docs/defect-report.md
wc -l docs/defect-report.md  # 应 > 500 行

# Day 8-9
docker images | grep discoverse
docker run --rm discoverse:test pytest tests/unit -v

# Day 10-11
curl -s https://api.github.com/repos/Cyberpunk-edgerunners/DISCOVERSE-learning/actions/runs | jq '.workflow_runs[0].conclusion'  # 应返回 "success"

# Day 12
curl -s http://localhost:8080/job/DISCOVERSE-GPU-Regression/lastBuild/api/json | jq '.result'

# Day 15-17
pytest tests/mobile_manipulation -v

# Day 18-19
python -m discoverse.data_validation.cli --help

# Day 20-21
ls README-testing.md docs/DISCOVERSE三周测试开发技术总结.pdf
```

---

## 八、风险与应对

| 风险 | 应对 |
|------|------|
| **面试官问"为什么不提上游 PR"** | 诚实答：三周内优先保证产出可控和深度，PR 合并周期不由我掌握；缺陷已全部定位、修复并回归验证，报告在此。**这是有判断力的回答，不是短板** |
| **源码只停留在表层，被问架构答不上** | Day 1 上午强制产出架构笔记；四条链路溶进对应测试日，**读不懂就写不出那天的测试**，形成强制约束 |
| **RTX 4060 仅 8G，3DGS 跑不动** | 已实测 `gaussian_renderer` 未安装。**主动放弃 3DGS**，聚焦 MuJoCo 物理层测试——面试时诚实说明取舍反而显得有判断力 |
| **覆盖率达不到 75%** | 3 周单人不可能。**改用"关键路径覆盖"叙事**：`universal_manipulation` 核心模块覆盖率 + 缺陷发现数，比虚高的总覆盖率更有说服力 |
| **面试提前到来** | Day 5 起 `devil-note.md` 就已有可讲内容；求职材料放第 3 周而非最后一天，正是为此 |
| **简历与实际能力落差被拷问** | 这三周就是为消除落差。**未做到的部分（如 EtherCAT 相关）不要在具身智能岗位上强行包装** |
| **Day 3-4 确定性测试修不好** | seed 贯穿是代码层面可控的（不依赖外部因素）。若 IK 状态泄漏难修，可先跳过，专注 seed。**不要在一个问题上卡超过 4 小时**，记录到 devil-note，继续下一个 |
| **Docker 镜像构建失败** | 降级方案：只写 Dockerfile 不实际构建，用本地 conda 环境跑测试。面试时诚实说"时间有限，Dockerfile 已完成但未充分验证" |
| **GitHub Actions 配额不够** | 免费账户每月 2000 分钟。**优化策略**：unit 测试每次跑，integration 只在 PR 跑，nightly 改为手动触发 |

---

## 九、诚实提醒

### 9.1 关于简历

1. **不要把简历上没做过的事继续写成做过**。这三周做完，你有足够真实素材，不需要再靠包装。

2. **旧简历里"精通 Pytest"如果面试被拷问 fixture 作用域答不上来，比写"熟悉"伤害大得多**。

3. **数字要经得起追问**：
   - ❌ "覆盖率提升到 75%" — 3 周单人做不到，一问就穿帮
   - ✅ "核心模块 universal_manipulation 覆盖率提升到 X%"（X 是你实测的真实值）

4. **未做到的部分诚实说明**：
   - EtherCAT 通信（工业机器人特有）在具身智能岗位用不上，不要强行包装
   - 如果 3DGS 没跑起来，就说"时间有限，聚焦 MuJoCo 物理层"

### 9.2 关于缺陷分析

**13 个缺陷里最有价值的是 seed 那个**（问题 2）。它不是低级 bug，而是"配置项声明了但整条链路没实现"的系统性缺失，直接导致整个项目的仿真不可复现。

**能讲清这个根因定位过程，胜过 50 个单元测试。**

### 9.3 关于基线数据

**62.5%-75% 这个数字是实测跑出来的，不是估算**。写进简历前请自己再复跑一遍确认——数字要经得起追问：

- 面试官："这个 75% 怎么来的？"
- 你："我跑了 8 次，6 次成功。这是 Day 0 建立的基线。"

**如果你的最终成功率是 85%，就写 75%→85%；如果是 78%，就写 75%→78%。诚实的小幅提升比虚构的大幅提升更可信。**

### 9.4 关于时间分配

**每天 10-12 小时不是口号**：
- 10-12 小时 = 实际编码/调试/写文档的时间
- **不包括**：吃饭、休息、刷手机

**如果某天只投入 6 小时，不要自欺欺人说"我今天完成了"——往后顺延一天，保证每个阶段的质量。**

面试官能看出来你是真做了 220 小时，还是只做了 100 小时然后赶工凑出来的。

### 9.5 关于 devil-note

**这是三周后最有价值的资产**。面试官问"讲一个你定位复杂问题的经历"，你需要的不是结论，而是**过程细节**：

- ❌ "我发现了一个 seed 配置未被消费的问题，然后修复了它"
- ✅ "我发现任务完全不可复现，先怀疑是 MuJoCo 物理引擎的数值误差，跑了对比测试排除了；然后怀疑是 IK 求解器有随机性，trace 代码发现它用的是确定性算法；最后 grep 了所有 `np.random` 调用，发现 randomization.py 里 20 多处裸调用，配置文件的 seed 字段在代码里完全找不到消费点。这是个系统性缺失——配置到代码的整条链路没打通。"

**后者才是面试官想听的。而这些细节，两周后你必然遗忘——必须每天记录。**

---

## 十、协作方式

**明确约定**：
- **所有命令由你亲手敲**，我负责解释每一步"为什么"
- 每步都有验证命令，看到预期输出再进下一步
- 遇到问题时贴**完整报错**，不要只说"报错了"
- **我不会替你写代码**，只会给出示例和思路，你来实现

**教学目标**：
> 要抱着把你真的教会的目的，还有真的入手一个新项目成熟的开发思维应该怎么样的

**不是**：给你一堆代码让你复制粘贴  
**而是**：教你面对新项目时的思维方式——怎么从海量输出里抓重点、怎么验证假设、怎么交叉验证避免被工具骗、怎么在不懂的地方快速建立认知地图。

---

## 十一、开始执行

**现在你应该**：
1. 再读一遍 Day 0 教程：`docs/tutorial/day00-setup.md`
2. 确认 Day 0 已全部完成（验收清单全勾选）
3. 准备开始 Day 1 上午：全局架构鸟瞰

**Day 1 上午教程**：即将编写（等你确认 Day 0 完成）

**记住**：
- **质量 > 速度**。宁可慢一天保证质量，不要赶进度糊弄过去
- **真实 > 完美**。75%→78% 的真实提升，比编造的 75%→90% 更有价值
- **过程 > 结果**。面试看的是你的思维方式，不是最终数字

**祝你三周后，简历上的每一句话都能当场被拷问、有 GitHub 链接佐证。**

---

**文档版本**：v1.0  
**最后更新**：2026-07-28  
**适用人群**：工业机器人测试工程师 → 具身智能测试开发（SDET）
