# Checkpoint · Day 13-14（2026-08-18）

> 上一站：[checkpoint-day12.md](checkpoint-day12.md)
> 本站产出：`discoverse/testing/`、重构的 `cicd_testing.py`、19 个回归测试
> 下一站：Day 15-17 MMK2 双臂轮式专项

---

## 一、下次开工第一件事

```bash
# 0) 环境（每个新终端都要）
PY=~/miniconda3/envs/discoverse/bin/python
#    ⚠️ 若 shell source 过 ROS，所有 pytest 命令前加 env -u PYTHONPATH

# 1) 基线核实
env -u PYTHONPATH MUJOCO_GL=osmesa $PY -m pytest tests/ -q | tail -2
#    预期：141 passed, 4 skipped, 45 deselected, 15 xfailed

# 2) 工作区干净
git diff --stat discoverse/configs/
#    预期：空（测试 fixture 会改 place_block.yaml，必须逐字节还原）

# 3) 未跟踪文档
git status --short
#    预期：Day 10-11 / Day 12 / Day 13-14 共 9 个文档未跟踪
```

---

## 二、Day 13-14 成果【已核实】

| 产出 | 位置 | 验证方式 |
|---|---|---|
| 结果契约 | `discoverse/testing/result_schema.py` | 8 个单测 |
| JUnit 渲染 | `discoverse/testing/junit_report.py` | 6 个单测 + junitparser 独立复核 |
| 退出码修复 | `universal_task_runtime.py` | seed 13→rc=1，seed 42→rc=0 |
| 批量重构 | `cicd_testing.py` | 真实批量跑，退出码 1 |
| 回归测试 | `tests/unit/test_result_schema.py`、`test_junit_report.py`、`tests/integration/test_exit_code_contract.py` | 19 passed |

**测试数：122 → 141（+19）** = 8 契约 + 6 JUnit + 5 退出码集成

### 修复的缺陷

| 编号 | 状态 |
|---|---|
| **#2** 退出码恒 0 | ✅ 已修复 + 回归测试钉死 |
| **连带** emoji 匹配 | ✅ 已删除，改用退出码 + 结果文件 |
| **#12** 表外机器人 | ✅ 已修复（fail fast，退出码 2） |

---

## 三、⭐ 契约速查（下次要用）

```python
from discoverse.testing import TaskResult, FailureMode, ExitCode
```

### 退出码

| 码 | 含义 | 性质 |
|---|---|---|
| 0 | 任务成功 | 有效结论 |
| 1 | 任务失败，判据未满足 | 有效结论 |
| 2 | 配置/环境错误 | **无效结论**（测试没跑起来） |
| 139 | 段错误（缺陷 X） | 契约被破坏 → 判 `crash` |

### 失败模式

| 值 | 含义 | 排查方向 |
|---|---|---|
| `ik_early` | 状态机中途 IK 不收敛 | 运动学、目标位姿可达性 |
| `final_check` | 状态走完，判据未满足 | 任务判据、物理参数 |
| `timeout` | 超时 | 性能、死循环 |
| `config` | 配置/环境错误 | **不是被测代码的问题** |
| `crash` | 异常退出 | 段错误、内存 |

### 契约不变式（`__post_init__` 强制）

1. `failure_mode` 必须在 `FailureMode.ALL` 内（拼错当场炸）
2. `success=True` → `failure_mode` 必须为 `None`
3. `success=False` → `failure_mode` **必须**指定

### 常用命令

```bash
# 单次运行 + 结构化结果
MUJOCO_GL=osmesa $PY examples/universal_tasks/universal_task_runtime.py \
    -r airbot_play -t place_block -1 --headless --result-json /tmp/r.json

# 批量 + JUnit XML
MUJOCO_GL=osmesa $PY examples/universal_tasks/cicd_testing.py \
    -r airbot_play panda -t place_block cover_cup \
    --serial --timeout 200 --junit-xml /tmp/junit.xml
```

---

## 四、⭐ 方法论收获（面试可直接用）

1. **「结果」是数据不是文字** —— 退出码恒 0 会连锁催生 parse stdout → 匹配 emoji 的补偿性 hack。
   修法不是把匹配写聪明，而是换信息通道。
2. **进程边界会吞信息** —— 函数返回值不会自动变成退出码，必须显式 `sys.exit()`。
3. **让非法状态无法表示** —— `__post_init__` 三条校验，胜过下游一百个 `if`。
4. **分类比布尔值有用** —— `success=False` 只说「红了」；`failure_mode` 说「往哪查」。
5. **关键词捞错误必然失效** —— 只要有一个良性 Traceback（本项目的 `gaussian_renderer`），
   捞到的就是噪声里最响的那条。且**成功的运行里也有它**。
6. **区分「产品坏了」与「测试环境坏了」** —— 退出码 1 vs 2；JUnit `<failure>` vs `<error>`。
7. **别用自己的解析器验证自己的输出** —— 用 junitparser 独立复核才算验证。
8. **看到不一致先采样** —— flaky 被测对象上单次运行不构成证据（cover_cup 采样 6 次）。
9. **别停在第一个合理解释上** —— editable finder 冻结清单「看起来完全说得通」，但不是原因。
10. **缺陷有依赖顺序** —— 没有 Day 3-4 的 seed 修复，就写不出 Day 13-14 的退出码回归测试。

---

## 五、⚠️ 环境坑（会再撞上）

### 5.1 ROS 污染 PYTHONPATH

```bash
echo $PYTHONPATH     # 若含 /opt/ros/humble → pytest 会报 No module named 'lark'
```

解法：`env -u PYTHONPATH $PY -m pytest ...`

### 5.2 系统 python 无依赖

```bash
PY=~/miniconda3/envs/discoverse/bin/python    # 必须用 conda 环境
```

### 5.3 ⭐ Docker 挂载路径错配

```bash
# ❌ 制造「两份代码」，import 解析到镜像里的旧代码
docker run --rm -v "$PWD":/work -w /work discoverse:test pytest tests/ -q

# ✅ CI 的真实方式：重建镜像，不挂载
docker build -q -f discoverse/docker/Dockerfile.test -t discoverse:test .
docker run --rm discoverse:test pytest tests/ -q      # → 141 passed

# 若确实要挂载调试，挂到镜像内的同一路径
docker run --rm -v "$PWD":/workspace -w /workspace discoverse:test pytest tests/ -q
```

镜像里代码烤在 `/workspace`（`Dockerfile.test:67,78`）。

### 5.4 lint 严格模式

`tests/` 目录 CI 不带 `|| true`，必须全绿：

```bash
env -u PYTHONPATH $PY -m ruff check tests/     # All checks passed!
```

`subprocess.run` 在退出码测试里**必须显式 `check=False`** + 注释说明。

---

## 六、遗留问题（按优先级）

| # | 问题 | 说明 |
|---|---|---|
| 1 | **缺陷 X（段错误→139）未修** | 今天只加了**检测**（交叉校验判 `crash`）。仅在 `MUJOCO_GL=glfw` 交互模式出现，CI 全程 headless —— 属「恰好绕开」非「安全」 |
| 2 | **`cover_cup` flake 未修** | 已量化：6 次采样，`ik_early` 3 次 / `final_check` 3 次。根因之一是 `cover_cup.yaml` 的 `seed: null` |
| 3 | **`panda/cover_cup` 缺相机** | 实测 `ValueError: The camera "eye_arm" does not exist.`，归类 `config`。是新线索，未进缺陷报告 |
| 4 | **批量 JUnit XML 未接进 CI** | `Jenkinsfile:166` 已有 `junit` 步骤消费 pytest 的 XML，但批量测试的 XML 还没有专门 job |
| 5 | **打印文案仍是自由文本** | `universal_task_runtime.py` 的 stdout 仍是给人看的；若将来有别的消费者，应考虑结构化日志 |

---

## 七、与计划文档的差异【已核实】

| 计划文档 | 实际 | 原因 |
|---|---|---|
| 用 `_pytest.junitxml.LogXML` | 手写 ElementTree | `LogXML` 与 pytest 内部对象强耦合，需伪造 `Item`/`TestReport` |
| 结果文件 `/tmp/discoverse_result_{pid}.json` | `--result-json` 显式传路径 | `subprocess.run` 返回时子进程已结束，父进程拿 pid 的时机不对；显式传参也更好测 |
| 问题 12 =「静默丢弃」 | 实测是**误报** | 机器人照常执行，失败被记成普通任务失败 + 无关错误信息。修法因此不同（fail fast + 退出码 2） |
| `failure_mode` 类型未定 | 字符串常量非 Enum | 要跨进程 JSON 序列化，Enum 会抛 `TypeError` |

---

## 八、文档产出

| 类型 | 文件 |
|---|---|
| 教程 | `docs/tutorial/day13-14-result-contract.md`（1000 行） |
| 教程·逐行 | `docs/tutorial/day13-14-supplement-line-by-line.md`（991 行） |
| 实录 | `docs/log/devil-log-day13-14.md` |
| 笔记 | `docs/note/devil-note-day13-14.md` |
| 本文 | `docs/checkpoint/checkpoint-day13-14.md` |

---

## 九、下一站：Day 15-17 MMK2 双臂轮式专项

三周计划里**差异化程度最高**的一段，也最能对接工业机器人运动学背景：

- FK→IK→FK 往返一致性
- 差速底盘里程计
- 19 自由度控制接口（2轮 + 1升降 + 2头部 + 12臂 + 4夹爪）

今天的结果契约会继续用：移动操作的失败模式更多
（底盘没到位？升降不够？双臂干涉？），`failure_mode` 的分类价值会更明显 ——
可能需要给 `FailureMode` 增补移动操作专属的类别。
