# Checkpoint · Day 3（2026-08-03）

> 分支：`feat/test-infra` ｜ 状态：**Day 3 完成（Step 0-4），Day 4 未开始（Step 5-8）**
> 已提交：`8cfbc38` 缺陷 J + `cd09b80` seed 贯穿
> 用途：下次开工只读这一份即可接上。历史见 [checkpoint-day02.md](checkpoint-day02.md)。

**本文每条推断都标注「已核实 / 待核实」** —— Day 2 的教训，Day 3 又犯了一次（见第七节）。

---

## 一、下次开工第一件事

```bash
cd /home/ubuntu22/workspaces/airbot-play/DISCOVERSE
source scripts/dev/env.sh          # 必须，否则 pytest 被 ROS 污染直接崩
$PY -m pytest tests/ -q            # 预期：110 passed, 4 skipped, 10 xfailed
```

对 Claude 说：**「读 docs/checkpoint/checkpoint-day03.md，开始 Day 4 的 Step 5-8」**

---

## 二、Day 3 最终成果【已核实】

| 项 | Day 2 结束 | Day 3 结束 |
|---|---|---|
| 用例 | 90 passed | **110 passed** |
| xfail | 9 | **10**（+缺陷 S） |
| 覆盖率 TOTAL | 30% | **59%** |
| 全量耗时 | 1.46s | 2.86s |

### 覆盖率明细【已核实，实跑 `--cov`】

| 模块 | Day 2 | Day 3 | Day 3-4 目标 | 达成 |
|---|---|---|---|---|
| `randomization.py` | 9% | **69%** | 50% | ✅ |
| `mink_solver.py` | 19% | **46%** | 40% | ✅ |
| `task_base.py` | 16% | 28% | — | |
| `robot_interface.py` | 16% | 56% | — | |
| `task_config.py` | 57% | 63% | — | |
| `robot_config.py` | 86% | 87% | — | |
| `config_utils.py` | 98% | 98% | — | |
| `recorder.py` | 19% | 19% | — | 未动 |
| `gripper_controller.py` | 39% | 78% | — | |
| **TOTAL** | **30%** | **59%** | 45% | ✅ |

**三个覆盖率目标全部在 Day 3 达成。**

⚠️ `mink_solver.py` 的 46% 是**外溢**得来的 —— 接线测试构造 `UniversalTaskBase` 时顺带跑到，**我们一行都没直接测它**。代码被执行过 ≠ 行为被验证过。Step 6 查 IK 时要真正测它。

### 新增测试文件【已核实】

| 文件 | 用例数 | 内容 |
|---|---|---|
| `tests/unit/test_randomization_config.py` | 16 | 缺陷 J 回归：4 条单值行为 + 12 条真实配置契约（参数化） |
| `tests/simulation/test_determinism.py` | 4 + 1 xfail | 确定性四条 + 缺陷 S 的 xfail |

---

## 三、Day 3 修复的缺陷【已核实】

### 缺陷 J｜`collision_radius` 键名不匹配 → `8cfbc38`

代码读 `min_distance`，12 个任务物体的 YAML 全写 `collision_radius` → `.get()` 永远落到默认值 0.05。

**⚠️ 实测修正**：checkpoint-day02 写的是「13 物体 11 受影响」，**实测是 12 物体 9 受影响**（另 3 个声明值恰好就是 0.05）。

| 任务 | 物体 | 声明 | 修复前实际 |
|---|---|---|---|
| place_block | bowl_pink | 0.12 | 0.05（缩小 2.4×） |
| place_coffeecup | plate_white | 0.12 | 0.05（缩小 2.4×） |
| place_coffeecup | coffeecup_white | 0.10 | 0.05 |
| cover_cup | plate_white | 0.10 | 0.05 |
| place_kiwi_fruit | flower_bowl | 0.09 | 0.05 |
| place_kiwi_fruit | kiwi | 0.07 | 0.05 |
| stack_block | block_green/red/blue | 0.06 | 0.05（3 个） |

**修复**：抽出 `_get_collision_radius()` 兼容两个键名 + 更新模板统一为 `collision_radius`。

**⚠️ 又一条实测修正**：checkpoint-day02 的修复建议说「模板与任务两边都是真实存在的用户」。**实测：`templates/randomization.yaml` 从未被任何任务 extends** —— 唯一引用是它自己第 137 行的注释示例。兼容两个键名仍然正确，但理由变了：不是「保护现有用户」，是「保护未来照模板抄的人」。

### 缺陷「seed 未被消费」｜→ `cd09b80`

**断链实测**【已核实】：

```
配置层：6 处声明 seed: null（5 任务 YAML + 1 模板）
            ↓  ✂️  0 个 Python 读取者
代码层：randomization.py 25 处裸 np.random.*
```

**修复**：`SceneRandomizer(mj_model, mj_data, seed=None)` → `np.random.default_rng(seed)` 实例，25 处改 `self.rng.*`，`task_base.py` 从 `randomization.settings.seed` 取值传入。

**行为兼容**：默认 `None`，`default_rng(None)` 从系统熵源取种，等价于原行为。

**变异测试验证**【已核实，实跑】：注入三种真实修复失误，后两种**各自只有一条测试**能抓到 → 四条测试缺一不可。

| 注入 | 谁抓到 |
|---|---|
| `default_rng(None)`（忘了用 seed） | 2 条红 |
| task_base 不传 seed（忘了接线） | **只有接线测试红** |
| `default_rng(42)`（seed 写死） | **只有异 seed 测试红** |

---

## 四、Day 3 新发现的缺陷

### 缺陷 S｜`get_random_texture()` 的随机源不受管控【已核实】

**位置**：`discoverse/utils/__init__.py:86-97`

```python
def get_random_texture():
    if 贴图目录存在:
        random.choice(...)                       # stdlib random（当前不可达）
    else:
        np.random.randint(0, 255, (768,768,3))   # numpy 全局流（当前可达！）
```

**两个分支，两种未受管控的随机源。** 实测：连续两次调用返回的噪声图**不同**。

**严重度**：中（影响视觉域随机化的可复现性，不影响物体位姿）

**为什么没在 Day 3 修**：`get_random_texture` 是模块级函数，没有 `self.rng` 可用；修它要改公共函数签名，牵连全部 4 个调用方（`task_base/airbot_task_base.py:110`、`randomization.py:553`、`examples/tasks_airbot_play/place_coffeecup.py`、`utils/__init__.py:140` 导出）。

**状态**：由 `test_texture_randomization_respects_seed` 的 `xfail(strict=True)` 守着。修好后 XPASS 会报 FAILED，强制有人回来撤标记。

**关键认知**：**随机性是从 import 边界溜走的。** 修复范围是 `randomization.py`，但它调用的 `utils` 函数不知道 rng 的存在。**确定性的边界不是「我改过的文件」，而是整条调用链。**

### 缺陷 T｜库代码用 print 代替 logging【已核实，低严重度】

`ModuleNotFoundError` 打 stderr，配套 `Warning:` 打 stdout，同一件事拆两个流，且打完整 traceback。**真错误和假错误在输出里长得一模一样。**

`exec_randomization` 还会往 stdout 刷 emoji 日志且无法关闭。

**尚未写进 defect-inventory** —— 待办。

---

## 五、Day 4 待办清单

- [ ] **Step 5｜缺陷 O**：`mink_solver.py:126` 的局部 `dt = 1e-3` 遮蔽了 `:50` 的 `self.dt`，YAML 配置无效
  - ⚠️ 修复会**改变现有 IK 收敛行为**（默认从 1e-3 变成配置值/2e-3）。先查 `grep -A2 -rn "ik_solver" discoverse/configs/robots/*.yaml | grep dt`，记录为行为变更而非纯 bugfix
- [ ] **Step 6｜IK 状态泄漏**：**先证明，再决定修不修**
  - 【待核实】读代码认为计划文档那条**不成立**：`solve_ik:99` 每次入口 `self.configuration.update(current_qpos)`，上次残留影响不了这次
  - 【待核实】但 `mink_solver.py:120-123` 的 `posture_task` target **只在 `reference_qpos is not None` 时更新，否则沿用上次** → 这才是真泄漏，且无入口重置保护
  - 判据：**调用 N 次后的输出，是否只由第 N 次的输入决定？**
  - 时间盒 60 分钟，到点没结论就写 xfail + 记录卡在哪
- [ ] **Step 7｜缺陷 H 的 iiwa14 根因**：nq 差 6（命令见 checkpoint-day02 第三节）
  - ⚠️ 该命令里的 `TYPE` 字典映射**待核实**，先跑 `$PY -c "import mujoco; print({e.name: e.value for e in mujoco.mjtJoint})"` 核对
- [ ] **Step 8｜收尾**：覆盖率复测、缺陷 S/T 写进 defect-inventory、更新 checkpoint

---

## 六、环境速查（与 Day 2 相同）

```bash
source scripts/dev/env.sh

$PY -m pytest tests/ -q                                   # 全部
$PY -m pytest tests/ -m determinism -v                    # 仅确定性专项
$PY -m pytest tests/ -m unit -q                           # 仅纯逻辑
$PY -m pytest tests/ --cov --cov-report=term-missing -q   # 覆盖率
$PY -m pytest tests/ --collect-only -q                    # 看收集数量
```

**输出很吵时**（`exec_randomization` 会刷 emoji 日志）：

```bash
$PY -m pytest tests/simulation/ -v 2>&1 | grep -E "PASSED|FAILED|XFAIL|passed|failed"
```

---

## 七、Day 3 被推翻的假设（方法论）

| 来源 | 假设 | 实测 |
|---|---|---|
| 计划文档 | MJCF 是静态文件，grep 配置能找到 | ❌ 是 `make_env` 运行时拼的（45 组合不可能预存） |
| checkpoint-day02 | 缺陷 J「13 物体 11 受影响」 | ❌ **12 物体 9 受影响** |
| Claude | 「模板 `min_distance` 是真实存在的用户」 | ❌ 模板**从未被 extends** |
| 观察 | 「四元数恒为 1,0,0,0 → 姿态随机化路径断了」 | ❌ **配置里就没要求随机化物体姿态**，不是缺陷 |

**四条里三条是「文档/推断」错，一条是「观察者过度解读」。**

最后一条值得单独记：观察到可疑现象后**先去查了配置**，查完发现是正常的 —— 这次没有把正常行为误报成 bug。**观察到「可疑」不等于发现缺陷。**

---

## 八、未提交的文件

```
 M docs/checkpoint/checkpoint-day02.md
 D docs/devil-*.md            ← 移动到 docs/note/ 和 docs/log/，git 尚未记录这次重命名
?? docs/note/  docs/log/devil-log-day03.md  docs/note/devil-note-day03.md
?? docs/checkpoint/checkpoint-day03.md
?? docs/defect-inventory-day02.md
?? docs/tutorial/day03-*.md
?? source-notes/DISCOVERSE小白入门讲解.md
```

⚠️ **那批 `D`（deleted）不是文件丢了**，是笔记移进了子目录。git 不存储「重命名」这个动作，它是提交时**事后推断**的（内容相似度 >50%）。

**必须在同一个 commit 里 add 两边**，否则重命名信息永久丢失，`git log --follow` 追不到历史。

```bash
git add docs/ source-notes/
git status --short        # 确认看到 R（renamed），而非 D + ??
```
