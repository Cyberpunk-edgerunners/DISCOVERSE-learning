# Checkpoint · Day 6-7（2026-08-11）

> 分支：`feat/test-infra` ｜ 状态：**Day 6-7 完成（缺陷报告已产出），文档已提交**
> 代码 commit：`eef1c4d` 文档+flake 采样器+缺陷 L ｜ 历史见 [checkpoint-day05.md](checkpoint-day05.md)
> 用途：下次开工只读这一份即可接上。

**本文每条推断都标注「已核实 / 待核实」。** Day 6-7 又有 **3 条既有文档记录被实测推翻**（见第四节），累计 16 条。

---

## 一、下次开工第一件事

```bash
cd /home/ubuntu22/workspaces/airbot-play/DISCOVERSE
source scripts/dev/env.sh
$PY -m pytest tests/ -q       # 预期：113 passed, 4 skipped, 45 deselected, 10 xfailed
git status --short            # 预期：干净（Day 6-7 已全部提交）
```

⚠️ **工作区当前是干净的**，与 Day 5 结束时不同 —— 不需要先处理未提交文件。

---

## 二、Day 6-7 成果【已核实，实跑】

### 2.1 主产出

| 文件 | 内容 |
|---|---|
| [../defect-report.md](../defect-report.md) | **1910 行缺陷分析报告，20 条缺陷全部完整格式** |
| `pyproject.toml` | 补 `mink>=1.2.0`、`quadprog>=0.1.13`（缺陷 L 修复） |
| `.gitignore` | 为 `docs/log/` 加例外（见第五节的坑） |

**报告格式**：每条缺陷统一按 影响模块 → 复现步骤 → 预期 vs 实际 → 根因分析 → 修复方案 → 回归验证 → 影响范围 展开。**不再区分详写/简写** —— 面试时自行按场合摘取。

**报告内嵌 8 处「面试可用点」**：`default_rng` vs `np.random.seed()` 的并行污染、变异测试、"不是每个修复都该配测试"、命令式 `pytest.xfail()` 的缺陷、配置继承下 grep 不足以判可达性等。

### 2.2 缺陷 L 已修【已核实】

`pyproject.toml` 的 `dependencies` 增加两行。**修复理由**：`universal_manipulation/__init__.py` 会主动加载 `mink_solver`，而 `mink_solver.py:8` 是模块级 `import mink` —— 缺失则**整个包 import 即失败**，不只是脚本报错。干净环境下 `pip install -e .` 后 `import discoverse.universal_manipulation` 直接 `ModuleNotFoundError`。

回归：`113 passed, 4 skipped, 45 deselected, 10 xfailed`，无回退。

⚠️ **未加守护测试**：理想做法是 CI 里加一个干净环境 job 跑 `pip install -e . && python -c "import discoverse.universal_manipulation"`。**当前无此保护，依赖缺失只能靠人工发现。** 留给 Day 10-11 的 CI 工作。

### 2.3 缺陷编号体系变更 ⚠️【重要，影响后续所有引用】

**报告用了新编号，与 [defect-inventory-day02.md](../defect-inventory-day02.md) 的旧编号对不上。**

| 报告编号 | 旧编号 | 内容 |
|---|---|---|
| **#1** | seed | 域随机化 seed 零消费 |
| **#2** | （问题 1） | 退出码恒为 0 |
| **#3** | W | pytest 超时未生效 |
| J/L/N/V/B/I/U/S/K/M/O/H/Q/P/R/T/X | 同名 | 保持不变 |

**总数 20 条**（此前记为 16 或 19 —— 我自己数错过两次，最终按报告总表逐行核对为 20）。

> **待办**：inventory 尚未同步新编号，也仍未收录 V/W/X。两份文档目前不一致。

---

## 三、缺陷状态总表【已核实】

| 编号 | 内容 | 严重度 | 状态 |
|---|---|---|---|
| **#1** | seed 零消费 | 🔴 Critical | ✅ 已修 `cd09b80` |
| **#2** | 退出码恒为 0 | 🔴 Critical | ⏸ 未修（**素材已补齐**） |
| **#3** | pytest 超时未生效 | 🟠 High | ⏸ 未修，**根因未定位** |
| J | `collision_radius` 键名不匹配 | 🟠 High | ✅ 已修 `8cfbc38` |
| **L** | mink/quadprog 未声明依赖 | 🟠 High | ✅ **已修 `eef1c4d`（本次）** |
| N | 配置错误→静默删数据→死循环 | 🟠 High | ⏸ 未修 |
| V | `cover_cup` 相机 `eye_arm` 不存在 | 🟠 High | ⏸ 未修（**用户明确说先不管**） |
| B | 4/5 任务 `camera_configs` 为空 | 🟠 High | ⏸ 4 xfail |
| I | `observation` 未列必填 | 🟡 Medium | ⏸ 1 xfail |
| U | `posture_task` 跨调用泄漏 | 🟡 Medium | ✅ 已修 `c722ca8` |
| S | 贴图随机源不受管控 | 🟡 Medium | ⏸ 1 xfail |
| K | 夹爪工厂假多态 | 🟡 Medium | ⏸ 未修 |
| M | `step()` 返回值重载 | 🟡 Medium | ⏸ 未修 |
| O | `dt` 硬编码遮蔽 | 🟢 Low | ✅ 已修 `c722ca8` |
| **H** | `qpos_dim` ≠ `nq` | 🟢 **Low（由高降级）** | ⏸ 4 xfail，**卡点已解除** |
| Q | 空 conditions 恒成功 | 🟢 Low | ⏸ 未修（不可达） |
| P | `panda.yaml` 重复键 | 🟢 Low | ⏸ 未修 |
| R | `randomize_scene` 返回类型 | 🟢 Low | ⏸ 未修 |
| T | 96 处 print | 🟢 Low | ⏸ 未修 |
| X | viewer 段错误 | 🟢 Low | ⏸ 未修 |

**已修 5，未修 15**（其中 10 条由 xfail 守着）。

---

## 四、Day 6-7 被推翻的三条记录【已核实，实跑】

**这三条是本次最重要的产出，也是报告 §二 的内容。照旧记录写会出错。**

### 4.1 缺陷 #1 的根因位置写错了

| | 内容 |
|---|---|
| **原记录** | "`task_config.py:88` 读取了 seed，但只存在字典里" |
| **实测** | 该行是 `states` 字段的**校验代码**，与 seed 无关；整个文件 grep `seed` **零命中** |

**更正让缺陷更严重**：不是"读了没传下去"，而是**整条链路无人提及**。

⚠️ **这句错误说法可能还散落在其他文档里，引用前先核实。**

### 4.2 缺陷 W（=报告 #3）的机制完全反了

| | 内容 |
|---|---|
| **原记录** | "pytest `timeout=60` 覆盖了用例内 `TIMEOUT_S=120`" |
| **实测** | 方向相反 —— `timeout=60` **压根没生效**（纯 `time.sleep(75)` 照样 passed），`TIMEOUT_S=120` 从未被覆盖，是**唯一**生效的超时 |

**实验三组对照**：

```
pytest test_sleep.py              → 1 passed in 75.08s   ← 没杀掉
pytest test_sleep.py --timeout=10 → Failed: Timeout      ← 杀掉了
pytest test_sleep.py -o timeout=10→ Failed: Timeout      ← 杀掉了
```

**已排除六项假设**（插件未装/未注册/pyproject 未读/键放错 table/同 table 其他键失效/subprocess 的锅）—— `pytest-timeout 2.4.0` 装着，`configfile: pyproject.toml` 被识别，同段 `addopts` 正常工作。

> ⚠️ **根因仍未定位。** 候选（均为**待核实**）：pytest 9.1.1 与 pytest-timeout 2.4.0 版本兼容；插件读 ini 的时机；某 conftest 覆盖。**下一步用二分法：升降插件版本、或改用独立 pytest.ini。**

**另一条**：一次自动化排查曾报"pytest-timeout 未安装" —— 实为**该排查用了系统 python 而非项目 conda 环境**。未采信，因为它与"命令行 `--timeout=10` 能杀掉测试"直接矛盾。

### 4.3 缺陷 H 严重度虚高，卡点解除

| | 内容 |
|---|---|
| **原记录** | 严重度"高"，"IK 按 YAML 维度切 qpos，会静默取错关节"（**该说法出现在 5 份文档中**） |
| **实测** | 全库**不存在任何 `qpos[:qpos_dim]` 切片**；`qpos_dim` 仅 4 处引用，终点是 `robot_interface.py:50` 的 `target_qpos`，**全库无人读取** |

所有 `qpos[:...]` 用的是 `nu`/`nj`/`njq`/字面量，来自 `robots_env/`、`task_base/` 这个**从不 import `RobotConfigLoader`** 的独立子系统。真实 IK 按**关节名** `mj_name2id` 解析，不按维度。

**结论**：严重度高→低；**"待决策"卡点自动解除** —— 原本担心改动破坏行为，实测确认无消费者可破坏。可直接定义 `qpos_dim ≡ nq` 并修正 4 个 YAML。

**附带发现**：`test_robot_config.py:149` 用**命令式** `pytest.xfail()`，它**立即中断测试** —— 那 4 个 MJCF 从未被加载，比对值取自 :20-25 的**硬编码表**。**若 MJCF 上游修好，该测试仍会 xfail 而不报警。** 相邻的 `test_ctrl_dim_matches_mjcf_nu` 无此问题，可作修复参照。

---

## 五、一个 `.gitignore` 事故（值得记住）

提交时发现 `docs/log/` 下 5 份实录笔记**既不显示为未跟踪，也不报错，`git add -A` 直接跳过**。

```bash
$ git check-ignore -v docs/log/devil-log-day01.md
.gitignore:10:*log	docs/log/devil-log-day01.md
```

`.gitignore` 第 10 行的 `*log`（本意挡运行日志）**吞掉了整个 `docs/log/` 目录**。已加例外：

```
!docs/log/
!docs/log/*.md
```

> 📌 **这是报告 §1.3「声明了但行为不符，且失败时静默」模式的现实版本** —— 只不过这次是 git 而非 YAML。差点让 5 份笔记漏提交、2 份历史断链。
>
> **可作为报告附录素材**：证明该模式不是本项目特有，是配置驱动系统的通病。（用户尚未决定是否补进报告。）

---

## 六、环境速查

```bash
source scripts/dev/env.sh

# 日常回归（3 秒）
$PY -m pytest tests/ -q

# flake 采样实验（需显式 -m flake）
$PY -m pytest tests/integration/test_task_matrix.py -m flake \
    --count=50 -n 8 --json-report --json-report-file=/tmp/flake.json --tb=no -q

# 复现缺陷 #2（退出码）
sed -i "s/    seed: .*/    seed: 13/" discoverse/configs/tasks/place_block.yaml
$PY examples/universal_tasks/universal_task_runtime.py -r airbot_play -t place_block -1 --headless
echo "退出码 = $?"        # 实测 0，应为非 0
sed -i "s/    seed: .*/    seed: null/" discoverse/configs/tasks/place_block.yaml   # 务必还原
grep -n "seed:" discoverse/configs/tasks/place_block.yaml   # 确认回到 null

# 复现缺陷 #3（超时未生效）
printf 'import time\ndef test_s():\n    time.sleep(75)\n' > /tmp/t.py
$PY -m pytest /tmp/t.py -q                 # passed（应被杀掉）
$PY -m pytest /tmp/t.py -q --timeout=10    # Timeout（证明插件正常）
```

---

## 七、Day 8+ 待办

### 优先级 1：Day 8-9 计划任务 —— Docker 测试镜像

⚠️ **开工前必读的环境实测结论**（已核实，避免按计划文档白走弯路）：

| 项 | 实测 | 影响 |
|---|---|---|
| docker | ✅ 29.1.5，daemon 可用 | 可构建 |
| GPU | ✅ RTX 4060 8GB | 有 |
| **nvidia-container-toolkit** | ❌ **未安装** | **`FROM nvidia/cuda` 镜像拿不到 GPU** |
| 现有 `Dockerfile` | `FROM nvidia/cuda:11.8.0-devel`，**已装 `libosmesa6-dev`**（:17） | 无需重装 |
| 现有 `ENV MUJOCO_GL` | **`glfw`**（:58） | 测试镜像需改 `osmesa` |
| `requirements-test.txt` | ❌ **不存在**，依赖只在 `pyproject.toml` | 计划文档的 `COPY requirements-test.txt` **不可照抄** |
| 磁盘 | 87G 可用（已用 82%） | 够，但别囤镜像 |

> **两条最关键**：① 计划里的 `requirements-test.txt` 根本不存在，要么新建、要么改用 `pip install -e .`；② 无 nvidia-container-toolkit，**测试镜像应走 CPU + osmesa 路线**（本来无头测试也不需要 GPU），别在 CUDA 基础镜像上浪费体积 —— 这正好也是"瘦身"叙事的天然理由。

### 优先级 2：报告与 inventory 的一致性（欠账）

- [ ] `defect-inventory-day02.md` 未收录 V/W/X
- [ ] inventory 用旧编号，与报告新编号（#1/#2/#3）**对不上**
- [ ] 4.1/4.2/4.3 三条更正**尚未回写**到 inventory 与 tutorial 等文档 —— 旧的错误说法仍在

### 优先级 3：报告里 6 条"回归验证方案（未实施）"

缺陷 #2、#3、N、V、K、Q 各有一段已写好的测试代码，**尚未落地为真实测试**。其中价值最高的是 V 的那条：

```python
@pytest.mark.parametrize("robot", ALL_ROBOTS)
@pytest.mark.parametrize("task", ALL_TASKS)
def test_declared_cameras_exist_in_mjcf(robot, task):
```

45 组合一次覆盖，能防住整类"配置引用不存在的模型实体"缺陷。

### 优先级 4：Day 5 遗留

- [ ] BUCKET2 根因（**优先查物体朝向** —— 唯一没查过的）
- [ ] 缺陷 V（用户说先不管，但它影响 15.8% 运行，修完 `cover_cup` 那行热力图才有意义）
- [ ] `recorder.py` 覆盖率 **19%**，Day 2 至今未动 —— 当前最大盲区

---

## 八、Day 0-7 累计

| | Day 5 结束 | **Day 7 结束** |
|---|---|---|
| 用例 | 113 | 113 |
| 覆盖率 | 62% | 62% |
| commit | 3 | **4** |
| 缺陷修复 | 4 | **5**（+L） |
| 定位缺陷总数 | 16 | **20** |
| 严重度基于实测下调 | 1（O） | **2**（+H） |
| 被推翻的文档推断 | 13 | **16** |

**Day 6-7 没有增加用例和覆盖率** —— 这两天的产出是**报告**（1910 行）与**三条更正**，不是代码。

> **累计 16 条写进文档的推断被实测推翻。** 这不是能力问题，是这类工作的固有特征 —— **排查就是不断提出假设并杀死它们**。
>
> 所以每份 checkpoint 的每条结论都标注「已核实 / 待核实」，而核实的方式是跑一遍。
>
> 本文第 4.2 节明确写着"根因仍未定位" —— **"我不知道"是合法结论，"我猜是 X"写成"根因是 X"不是。**
