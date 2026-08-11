# Checkpoint · Day 2（2026-07-30）

> 分支：`feat/test-infra` ｜ 状态：**Day 2 全部完成（Step 1-8）**
> 已提交：`ce88e8d` 骨架 + `cc3fc02` 配置层单测
> 用途：下次开工只读这一份 + [checkpoint-day01.md](checkpoint-day01.md) 即可接上。

---

## 一、下次开工第一件事

```bash
cd /home/ubuntu22/workspaces/airbot-play/DISCOVERSE
source scripts/dev/env.sh          # 必须，否则 pytest 被 ROS 污染直接崩
$PY -m pytest tests/ -q            # 预期：90 passed, 4 skipped, 9 xfailed
```

对 Claude 说：**「读 docs/checkpoint/checkpoint-day02.md，开始 Day 3-4 确定性攻坚」**

---

## 二、Day 2 最终成果

| 项 | 值 |
|---|---|
| 测试用例 | **90 passed, 4 skipped, 9 xfailed** |
| 覆盖率 | **5% → 30%**（961 语句，674 未覆盖） |
| 代码量 | 549 行测试 + 141 行基础设施 |
| 全量耗时 | 1.46s |
| commit | `ce88e8d`（骨架）、`cc3fc02`（单测） |

**Step 1-8 全部完成**：目录骨架 → pytest 配置 → 反向验证 → conftest fixture → 9 机器人参数化 → 5 任务配置 → 覆盖率基线 → 清理提交。

### 测试文件清单

| 文件 | 用例数 | 内容 |
|---|---|---|
| `tests/conftest.py` | — | 5 个 fixture（repo_root / 两个 config_dir / mj_model_factory / mj_data_factory） |
| `tests/unit/test_smoke.py` | 2 | 框架自检 + ROS 污染回归防护 |
| `tests/unit/test_conftest_fixtures.py` | 5 | fixture 自检（含 session/function 作用域隔离验证） |
| `tests/unit/test_robot_config.py` | 66 | 9 机械臂参数化 + MJCF 对账 + MMK2 烟雾测试 |
| `tests/unit/test_task_config.py` | 30 | 5 任务 + extends 验证 + 缺陷 B/C/I |

---

## 三、Day 2 发现的缺陷（4 条新增）

| 编号 | 位置 | 内容 | 严重度 | 根因 |
|---|---|---|---|---|
| **B** | `templates/place_object.yaml` | 4/5 任务 `camera_configs` 返回空列表 → **数据采集静默产出零张图像** | **高** | ✅ 模板缺 `observation` 段（3 个继承者受害）+ `stack_block` 自己漏写 → **修 2 个文件而非 4 个** |
| **C** | [task_config.py:167](../../discoverse/universal_manipulation/task_config.py#L167) | `record_fps` 双层静默默认值；`observation: null` 触发 `AttributeError` | 中 | ✅ `.get(k, default)` 只在键不存在时兜底；键存在值为 `None` 时返回 `None`，随后 `None.get()` 炸 |
| **H** | `discoverse/configs/robots/*.yaml` | 4/9 机器人 `qpos_dim` 与 MJCF `nq` 不符 | **高** | ⏸ **iiwa14 差 6 待查**（其余差 1-2 可由夹爪建模解释） |
| **I** | `task_config.py:_validate_config` | `required_fields` 只有 `['task_name','description']`，未含 `observation` | 中 | ✅ 这是缺陷 B 能存在于 4/5 任务的直接原因 |

### 缺陷 H 的详细数据（Day 6-7 查根因用）

| robot | YAML `qpos_dim` | MJCF `nq` | 差 |
|---|---|---|---|
| arx_x5 | 7 | 8 | 1 |
| piper | 7 | 8 | 1 |
| rm65 | 12 | 14 | 2 |
| **iiwa14** | **9** | **15** | **6** ← 最可疑 |

**注意 `ctrl_dim` vs `nu` 是 9/9 全对。** 这个分布本身是线索：
- 写错 `ctrl_dim` → `data.ctrl[:] = 长度不符数组` → **立刻 ValueError**，开发马上修
- 写错 `qpos_dim` → `qpos[:9]` 在 `nq=15` 上**完全合法**，静默丢掉后 6 个关节

**会炸的字段维护得好，不会炸的字段积累错误。**

**下次查 iiwa14 的命令**（找有没有 `FREE` 类型关节，占 7 个 qpos）：

```bash
$PY - <<'PYEOF'
import mujoco
m = mujoco.MjModel.from_xml_path("models/mjcf/manipulator/robot_iiwa14.xml")
print(f"nq={m.nq} nu={m.nu} njnt={m.njnt}")
TYPE = {0: "FREE(7)", 1: "BALL(4)", 2: "SLIDE(1)", 3: "HINGE(1)"}
for j in range(m.njnt):
    nm = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, j) or "(无名)"
    print(f"{j:3d} {nm:22s} {TYPE.get(int(m.jnt_type[j]),'?'):10s} qposadr={m.jnt_qposadr[j]}")
PYEOF
```

---

## 四、Day 3-4 的入口（覆盖率报告直接给出的工作清单）

```
模块                        语句   未覆盖  覆盖率
randomization.py             300    274     9%   ← 确定性攻坚核心
task_base.py                 160    134    16%   ← 成功判定逻辑（原线索已证伪，见下）
robot_interface.py            88     74    16%
mink_solver.py                79     64    19%   ← IK，Day 3-4 也要碰
recorder.py                   63     51    19%
gripper_controller.py         36     22    39%
task_config.py                99     43    57%   ← 今天测的
robot_config.py               77     11    86%   ← 今天测的
config_utils.py               48      1    98%   ← 只差第 83 行
TOTAL                        961    674    30%
```

### ⚠️ 实测修正：原「最高优先线索」的假设已被证伪（2026-07-30）

原记录写着「若 `except` 吞异常后返回 `True`，则任何条件检查出错都判定成功，可能是整个项目最严重的缺陷」。

**实测：返回的是 `False`，不是 `True`。** [task_base.py:165-167](../../discoverse/universal_manipulation/task_base.py#L165) 与未知条件类型分支（:164）都返回 `False` —— fail-closed，是安全的。

**Day 1「完成状态 10/10 但距离 0.2908m」的真正解释**：`step()` 返回值语义重载（[universal_task_runtime.py:213-262](../../examples/universal_tasks/universal_task_runtime.py#L213)）。`False` 有三个出处（原语失败 :223 / 超时 :234 / 抛异常 :262），而 `run()` 只写 `if not self.step(): break`，无法区分。超时退出时 `self.success` 保持初值 `False`，但 `state_idx` 已推进到 10 → 打印「完成状态 10/10」+「任务成功：否」。**是「进度指标与成功判定脱钩」，不是「伪造成功」。**

**完整分析见 [defect-inventory-day02.md](../defect-inventory-day02.md) 第二节与缺陷 M。**

> **教训**：这条假设从 Day 1 带到 Day 2，被当作两天的最高优先线索，而它只需要一条 `sed -n '165,167p'` 就能证伪。**checkpoint 里的每条推断都该标注「已核实 / 待核实」。**

### Day 3-4 真正的最高优先项

`randomization.py` 的 seed 问题（见下方「确定性攻坚目标」）。另外 [defect-inventory-day02.md](../defect-inventory-day02.md) 里新增的**缺陷 J（`collision_radius` 键名不匹配，11/13 物体避让半径静默失效）严重度高于原线索**，且可能解释部分 flake 率 —— 建议优先处理。

### 确定性攻坚目标

`randomization.py` 300 语句只覆盖 9%，计划文档称有 20+ 处裸 `np.random.*` 从未被 seed，且 `place_block.yaml` 的 `settings.seed: null` 是死配置。

**验证顺序建议**：
1. 先写一条"同种子跑两次应得相同结果"的测试 → 预期红
2. 再定位 seed 在哪一层断掉
3. 修复后测试转绿（TDD 红→绿，本周最有含金量的部分）

### config_utils.py 第 83 行（低优先）

```python
if i < len(result):
    result[i] = override_state      # 覆盖已有状态
else:
    result.append(override_state)   # 第 83 行，未覆盖
```

是 `states` 列表合并的分支：子配置 states 比模板多时才走到。今天测的 3 个继承任务都不超过模板长度。**纯列表操作，风险低，Day 8-9 再补。**

---

## 五、Day 2 踩坑与修复（都已固化）

### 坑 1｜ROS Humble 的 PYTHONPATH 污染 pytest（耗时最久，约 40 分钟）

**现象**：`ModuleNotFoundError: No module named 'lark'`，pytest 启动阶段直接崩。

**根因链**：

```
~/.bashrc: source /opt/ros/humble/setup.bash
  -> export PYTHONPATH=/opt/ros/humble/lib/python3.10/site-packages
  -> PYTHONPATH 优先级高于 conda 环境隔离，强行注入 sys.path
  -> pytest 启动时 load_setuptools_entrypoints("pytest11") 扫描所有插件
  -> 发现 ROS 的 launch_testing -> import launch -> import lark（conda 没装）
  -> 崩
```

**同根因的第二种表现**（反向验证时撞出）：

```
PluginValidationError: unknown hook 'pytest_launch_collect_makemodule'
in plugin launch_testing_ros_pytest_entrypoint  ->  INTERNALERROR
```

**修复**：`unset PYTHONPATH`，固化在 [scripts/dev/env.sh](../../scripts/dev/env.sh) + 回归测试 `test_no_ros_pollution_in_syspath`。

**为什么不用 `-p no:launch_testing`**：`-p no:` 要求插件**先被成功导入**才能禁用。ROS 那堆插件只要有一个在导入期或 hook 校验期就炸，`-p no:` 根本来不及。**环境隔离必须在更外层做。**

### 坑 2｜pyproject.toml 与 pytest.ini 双配置

**现象**：`WARNING: ignoring pytest config in pyproject.toml!`

**决策**：删掉自建的 `pytest.ini`，**改写上游已有的 `[tool.pytest.ini_options]`**（缺陷 G：上游声明了 `testpaths=["tests"]` 但目录不存在，配置从未生效）。

**TOML vs INI 语法差异**：字符串必须加引号；多值必须是真数组 `["a","b"]` 而非换行缩进。

### 坑 3｜heredoc 静默截断

`checkpoint-day02.md` 第一版写入时**预期 200 行实际只写了 15 行，零报错**。

**验证习惯（必须执行）**：

```bash
wc -l <file> && tail -3 <file>
```

**「命令没报错」≠「命令做对了」。**

### 坑 4｜5 个测试同时失败 —— 判断出是「测试错」不是「代码错」

**现象**：`test_task_config.py` 中 5 个测试全部 `ValueError: Missing required field: description`。

**判断依据**：

| 线索 | 指向 |
|---|---|
| 5 个失败**全在同一处**（`from_dict` 构造阶段） | 系统性问题，非分散 bug |
| 报的是 `Missing required field` | **这是设计好的校验正在正常工作** |
| 真实的 5 个 YAML 都有 `description` | 我的测试数据不真实 |

**结论**：`_validate_config` 是对的，我给的假配置不完整。改测试，不改代码。

**修法**：加 `_minimal_config()` 辅助函数，构造能通过校验的最小配置。

**副产品**：查清必填字段清单时发现 `observation` **不在其中** → 缺陷 I。

### 坑 5｜误粘贴终端输出

把上一轮的终端输出（含提示符）整块贴回终端，bash 逐行执行产生大量 `command not found`。**本次无损**（那些行凑不出可执行命令），但同样操作在别的场景可能执行到危险命令。

**习惯**：从终端复制时只选命令，不带提示符；长命令写进脚本再执行。

### 坑 6｜我自己加了重复的 .gitignore 规则

追加 `.pytest_cache/` 等规则前没先 `grep`，而上游 `# CI/CD 产物` 段落早已有这三条。**加配置前必须先看已有什么** —— 这正是今天反复强调却自己没做的事。

---

## 六、方法论沉淀（Day 2 全天）

1. **新写的断言必须亲手让它红一次。** 永远为真的断言等于没写。
2. **collection 错误 ≠ 测试失败。** 一个 marker 拼错让整个文件用例集体消失，CI 摘要只显示 "1 error"。**`collected N items` 的 N 比 pass/fail 更早暴露问题。**
3. **`INTERNALERROR` 是独立失败类别。** 退出码 3（非 1），且**不生成任何报告文件**。→ **Day 10-11：CI 判定必须基于退出码，不能基于报告内容。**
4. **刻意写"脆"的断言**（如 `assert len(yamls) == 9`）。宁可要吵闹的正确，不要安静的错误。
5. **同一根因可有多种表现。** `lark` 和 `PluginValidationError` 长得完全不同。**错误信息也会骗人。**
6. **fixture 作用域**：贵且不可变 → session；可变 → 必须 function。**代价不对称**：选窄只是慢，选宽是测试间污染（单跑绿、全跑红、换顺序不复现）。
7. **静态读文件 ≠ 运行时加载。** `extends` 继承机制让「直接读 YAML 看到缺失」和「加载器合并后是否缺失」是两个问题。**这是「静态分析会骗人」的第三次现身。**
8. **xfail ≠ skip。** xfail = 「断言应成立但因已知缺陷不成立」；skip = 「前提不满足，无法判断」。**混用会把缺陷伪装成环境问题。**
9. **`@pytest.mark.xfail(strict=True)`**：缺陷修复后 XPASS 报为失败，**强制有人回来撤销标记**。让「缺陷已修复」也不会静默发生。
10. **覆盖率是下限指标。** 低覆盖一定有问题；高覆盖不保证质量。`record_fps` 只有 1 行代码，但写了 4 个测试（正常/无键/空dict/null崩溃）。**看 Missing 那列找盲区，不要盯总百分比。**
11. **「有验证」≠「验证够」。** `_validate_config` 存在且正常工作，但漏了 `observation` 这个影响数据产出的字段。
12. **默认值的判断标准**：影响**产出正确性**的配置，缺失必须报错；只影响**行为偏好**的配置，才可以有默认值。`camera_configs` 返回 `[]` 是最坏的一种——空集合在 Python 里不是错误，`for` 循环安静跳过。
13. **测试红了先分三步判断**：找独立第二信源 → 看分布（1/9 vs 7/9）→ 看语义是否自洽。**分不清「代码错」还是「测试错」时，测试就失去了价值。**
14. **样本量就是判断力。** 9 个样本中 5 对 4 错 → 能定位缺陷。2 个样本 1 对 1 错 → 无法判断。这是 Day 2 测 9 机械臂而非先测 MMK2 的核心理由。

---

## 七、环境速查

```bash
cd /home/ubuntu22/workspaces/airbot-play/DISCOVERSE
source scripts/dev/env.sh

$PY -m pytest tests/ -q                      # 全部
$PY -m pytest tests/ -m unit -q              # 仅纯逻辑（毫秒级）
$PY -m pytest tests/ -m integration -q       # 需加载 MJCF（百毫秒级）
$PY -m pytest tests/ --cov --cov-report=term-missing -q   # 覆盖率（作用域已配好）
$PY -m pytest tests/ --collect-only -q       # 看收集数量
$PY -m pytest tests/ --lf                    # 只跑上次失败的
```

**覆盖率作用域已写进 `pyproject.toml` 的 `[tool.coverage.run]`** —— 不要手写 `--cov=discoverse`，会被 `policies/` 237 个文件稀释到 2-3%。

**为什么用 `$PY -m pytest` 而非 `pytest`**：保证解释器与装包环境一致，且 `-m` 会把 cwd 加进 sys.path。

**已装插件**：timeout-2.4.0 / repeat-0.9.4 / cov-7.1.0 / xdist-3.8.0

---

## 八、未提交的文件（有意保留）

```
?? .claude/  .claudeignore  CLAUDE.md        工具配置，待单独 commit
?? docs/                                     学习笔记，Day 5 整理后统一提交
?? scripts/dev/trace_chain.py                Day 1 产物，应与 Day 1 文档一起提交
?? source-notes/*.md                         同上
```

**一个 commit 只做一件事。** 把笔记、工具配置、测试代码混在一起提交，`git log` 就废了。

---

## 九、Day 3-4 待办清单

- [x] ~~查 `task_base.py:149-167` 的 `except` 吞异常后返回值~~ —— **已证伪，返回 `False`，见第四节修正**
- [ ] **修缺陷 J**（`collision_radius` 键名不匹配，11/13 物体避让半径失效）—— 影响最大且一行可修，见 [defect-inventory-day02.md](../defect-inventory-day02.md)
- [ ] 写"同种子两次运行结果一致"测试 → 预期红
- [ ] 定位 seed 在哪一层断掉（**实测精确数字**：`randomization.py` **25 处**裸 `np.random`，该文件 `seed` 零命中；`settings.seed: null` 声明于 **6 处**但无任何代码读取；`utils/__init__.py:86` 另有 stdlib `random.choice`）
- [ ] TDD 修复：seed 贯穿到所有随机源（含 texture 那条独立路径）
- [ ] 查缺陷 H 的 iiwa14 根因（命令见第三节）
- [ ] `mink_solver.py` IK 状态泄漏（计划文档提到）；顺带修缺陷 O（`dt` 被 `:126` 硬编码遮蔽）
