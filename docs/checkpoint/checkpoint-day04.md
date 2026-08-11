# Checkpoint · Day 4（2026-08-05）

> 分支：`feat/test-infra` ｜ 状态：**Day 3-4 全部完成（Step 0-8）**
> 已提交：`8cfbc38` 缺陷 J ｜ `cd09b80` seed 贯穿 ｜ `c722ca8` 缺陷 O + U + H 根因
> 用途：下次开工只读这一份即可接上。历史见 [checkpoint-day03.md](checkpoint-day03.md)、[checkpoint-day02.md](checkpoint-day02.md)。

**本文每条推断都标注「已核实 / 待核实」。** Day 4 又有四条推断被推翻，其中一条是当天自己写的（见第七节）。

---

## 一、下次开工第一件事

```bash
cd /home/ubuntu22/workspaces/airbot-play/DISCOVERSE
source scripts/dev/env.sh          # 必须，否则 pytest 被 ROS 污染直接崩
$PY -m pytest tests/ -q            # 预期：113 passed, 4 skipped, 10 xfailed
```

对 Claude 说：**「读 docs/checkpoint/checkpoint-day04.md，开始 Day 5 flake 定量分析」**

⚠️ **开工前必做**：提交文档（见第八节）。当前有大量未提交文件，含 `docs/note/` 的重命名 —— **必须与删除同 commit**，否则 git 的重命名检测失效。

---

## 二、Day 3-4 最终成果【已核实，实跑】

| 项 | Day 2 结束 | Day 3 结束 | **Day 4 结束** |
|---|---|---|---|
| 用例 | 90 passed | 110 passed | **113 passed** |
| xfail | 9 | 10 | 10 |
| 覆盖率 TOTAL | 30% | 59% | **62%** |
| 全量耗时 | 1.46s | 2.86s | 2.97s |
| commit | 1 | 2 | **3** |

### 覆盖率明细【已核实】

| 模块 | Day 2 | Day 3 | **Day 4** | 目标 | 达成 |
|---|---|---|---|---|---|
| `mink_solver.py` | 19% | 46% | **90%** | 40% | ✅ |
| `randomization.py` | 9% | 69% | 69% | 50% | ✅ |
| `config_utils.py` | 98% | 98% | 98% | — | |
| `robot_config.py` | 86% | 87% | 87% | — | |
| `gripper_controller.py` | 39% | 78% | 78% | — | |
| `task_config.py` | 57% | 63% | 63% | — | |
| `robot_interface.py` | 16% | 56% | 56% | — | |
| `task_base.py` | 16% | 28% | 28% | — | |
| `recorder.py` | 19% | 19% | 19% | — | **未动** |
| **TOTAL** | **30%** | **59%** | **62%** | 45% | ✅ |

**三个目标全部超额达成。**

`mink_solver.py` 剩 8 行未覆盖（`42, 80, 107, 111, 207, 213, 217, 232`）—— 异常分支 + `__str__`/`__repr__`，**不值得为它们写测试**。

⚠️ `recorder.py` 19% 是 Day 2 以来**完全没动过**的模块，是当前最大盲区。

### 测试文件清单【已核实】

| 文件 | 用例 | 内容 |
|---|---|---|
| `tests/conftest.py` | — | 5 个 fixture |
| `tests/unit/test_smoke.py` | 2 | 框架自检 + ROS 污染防护 |
| `tests/unit/test_conftest_fixtures.py` | 5 | fixture 自检 |
| `tests/unit/test_robot_config.py` | 66 | 9 机械臂参数化（4 xfail = 缺陷 H） |
| `tests/unit/test_task_config.py` | 30 | 5 任务（5 xfail = 缺陷 B/I） |
| `tests/unit/test_randomization_config.py` | 16 | 缺陷 J 回归 |
| `tests/unit/test_mink_solver.py` | 3 | 缺陷 U 回归 + 状态隔离契约 |
| `tests/simulation/test_determinism.py` | 4 + 1 xfail | 确定性四条 + 缺陷 S |

---

## 三、缺陷状态总表【已核实】

| 编号 | 内容 | 严重度 | 状态 |
|---|---|---|---|
| **J** | `collision_radius` 键名不匹配，9/12 物体避让半径失效 | 高 | ✅ 已修 `8cfbc38` |
| **seed** | 6 处声明零个读取者，25 处裸 `np.random` | 高 | ✅ 已修 `cd09b80` |
| **O** | `dt` 被硬编码遮蔽 | ~~中~~ **低** | ✅ 已修 `c722ca8` |
| **U** | `posture_task` 目标跨调用泄漏 | 中 | ✅ 已修 `c722ca8` |
| **H** | 4/9 机器人 `qpos_dim` ≠ MJCF `nq` | 高 | 🔍 **根因已明，待决策** |
| **S** | `get_random_texture()` 随机源不受管控 | 中 | ⏸ xfail 守着 |
| **T** | 库代码用 `print` 代替 `logging` | 低 | ⏸ 未修 |
| **B/I** | `camera_configs` 空 / `observation` 非必填 | 高/中 | ⏸ Day 2 遗留，5 xfail |
| K/L/M/N/P/Q/R | 见 [defect-inventory-day02.md](../defect-inventory-day02.md) | — | ⏸ 未处理 |

完整记录见 [defect-inventory-day02.md 第九节](../defect-inventory-day02.md)。

---

## 四、Day 4 关键实测结论

### 4.1 缺陷 O：修复不改变任何行为【已核实】

9/9 机器人 YAML 都配 `dt: 0.002`，全部无效（实际跑 `0.001`）。但**修复前后 IK 解逐位相同**（`atol=1e-9`，测了 2/5/10/15cm 四个偏移）。

**原因**：`mink.solve_ik` 内部把误差**除以 dt**，`integrate_inplace` 又**乘以 dt` —— 一除一乘约掉。dt 仅在配了 `mink.VelocityLimit` 时才影响单步位移上限。

**因此是休眠缺陷**：当前零影响，但一旦引入速度限制，配置写 0.002 实际按 0.001 算，**限幅严一倍**而配置看起来完全正确。

**仍然修**（一行、零风险），但**未写测试**（无可观测差异，写了也是永远为真的断言）。

### 4.2 缺陷 U：真泄漏在 `posture_task`，不在 `configuration`【已核实】

**计划文档记载的「`self.configuration` 泄漏，需 try/finally」不成立** —— [solve_ik:99](../../discoverse/universal_manipulation/mink_solver.py#L99) 每次入口 `configuration.update(current_qpos)` 已隔离它，两次同参调用解逐位相同。

**真泄漏**（三次调用实测）：

```
第1次(无ref):  [3.84020671e-06, -7.16114078e-01, 1.00542549e+00]
第2次(有ref):  [4.42028460e-06, -7.16113819e-01, 1.00542520e+00]
第3次(无ref):  [4.42028460e-06, -7.16113819e-01, 1.00542520e+00]  ← 跟着第2次
```

第 1 次与第 3 次**输入完全相同**，输出却不同。

**修复对应两个独立契约**：

| 改动 | 作用 |
|---|---|
| 把 `set_target_from_configuration` 挪出 if 块 | **消除泄漏** |
| 补 else 分支恢复 `_default_posture_qpos` | **保持默认姿态是 home** |

⚠️ **第二点不是修泄漏** —— 挪出 `set_target` 后有没有 else 都不泄漏。else 决定「默认姿态取谁」：无 else 时 `temp_config` 保持 `mink.Configuration` 默认值 **qpos0**（airbot_play 全 0），与 home（`[0,-1,1.2,1.5708,-1.2,-1.5708]`）差得很远。

### 4.3 缺陷 H 根因【已核实】

遍历 `jnt_type`：**4 个模型零个 FREE 关节**，推翻 checkpoint-day02 的猜测。

| 机器人 | 臂 | 夹爪 | nq | YAML | 差 |
|---|---|---|---|---|---|
| arx_x5 / piper | 6 HINGE | 2 SLIDE | 8 | 7 | 1 |
| rm65 | 6 HINGE | 6 HINGE + 2 SLIDE | 14 | 12 | 2 |
| **iiwa14** | **7 HINGE** | **8 HINGE** | **15** | **9** | **6** |

**iiwa14 夹爪**：Robotiq 式平行连杆，`left/right` 各 4 个 `driver`/`coupler`/`spring_link`/`follower`，约束耦合成 1 个物理自由度但各占 1 个 qpos。YAML 按「2 根手指」计数。

**⚠️ 待决策，故未改数字**：`qpos_dim` 语义未定义 —— 指模型 `nq`（15）还是可控自由度（7 臂 + 1 夹爪 = 8）？连杆是被约束的从动关节，算 1 个还是 8 个取决于定义。**在有共识前改数字只是把一个错误换成另一个错误。**

xfail reason 已从「原因不明」升级为「根因已知 + 待决策点明确」。

---

## 五、Day 5+ 待办

### 优先级 1：文档提交（开工第一件事）

见第八节，含 `docs/note/` 重命名的处理。

### 优先级 2：Day 5 flake 定量分析（原计划）

见 [计划文档](../DISCOVERSE三周测试开发魔鬼计划.md) Day 5 章节：45 组合 × 50 次，失败分桶，热力图。

⚠️ **Day 3-4 修了 J 和 seed 之后，flake 率大概率已经变化。** 建议先跑一个小规模基线（比如 airbot_play × place_block × 20 次）对比 Day 1 记录的 62.5%-75%，**用数据证明修复的价值** —— 这是面试叙事里最硬的一段。

### 优先级 3：遗留缺陷

- [ ] **缺陷 H 决策**：先定义 `qpos_dim` 语义（查 `grep -rn "qpos_dim" --include=*.py` 看谁在用）
- [ ] **缺陷 B/I**（Day 2 遗留，5 xfail）：`camera_configs` 为空 → 数据采集产出零张图像，**严重度高于 S/T**
- [ ] **缺陷 S**（贴图随机源）：需改 `get_random_texture` 公共签名，牵连 4 个调用方
- [ ] **缺陷 T**（print vs logging）

### 优先级 4：覆盖率盲区

- [ ] `recorder.py` **19%**，Day 2 至今未动 —— 数据采集的核心模块，当前最大盲区
- [ ] `task_base.py` 28%

---

## 六、环境速查

```bash
source scripts/dev/env.sh

$PY -m pytest tests/ -q                                   # 全部
$PY -m pytest tests/ -m determinism -v                    # 确定性专项
$PY -m pytest tests/ -m unit -q                           # 纯逻辑（毫秒级）
$PY -m pytest tests/ -m integration -q                    # 需加载 MJCF
$PY -m pytest tests/ --cov --cov-report=term-missing -q   # 覆盖率
$PY -m pytest tests/ --lf                                 # 只跑上次失败的
```

**输出很吵时**（`exec_randomization` 刷 emoji 日志，即缺陷 T）：

```bash
$PY -m pytest tests/ -v 2>&1 | grep -E "PASSED|FAILED|XFAIL|XPASS|passed|failed"
```

**只看覆盖率表**：

```bash
$PY -m pytest tests/ --cov --cov-report=term -q 2>&1 | grep -E "^discoverse|^TOTAL|^Name|^---"
```

---

## 七、Day 4 被推翻的假设（方法论）

| 来源 | 假设 | 实测 |
|---|---|---|
| 计划文档 | 修 `dt` 会改变 IK 收敛行为 | ❌ 逐位相同 |
| 计划文档 | `self.configuration` 泄漏，需 `try/finally` | ❌ 不泄漏 |
| checkpoint-day02 | iiwa14「可能有 FREE 关节」 | ❌ 零个 FREE |
| **day04 教程 §6.6（当天自己写的）** | **else 分支是修泄漏的关键** | ❌ **关键是 `set_target` 的位置** |

**前三条是「别人写的文档错了」，第四条是「我自己五分钟前写的解释错了」。**

而且第四条**不是靠读代码发现的 —— 是变异验证抓出来的**。

> 📌 **对自己修复的理解，也需要外部检验机制。** 读一遍代码觉得「应该是这样」是不够的。

### 变异验证「没红」时的三种可能

Day 4 遇到了变异验证**全绿**的情况。第一反应容易是「测试写错了」，实际有三种：

| 可能 | 如何区分 |
|---|---|
| A. 测试写错 | 注入一个**必然**破坏契约的变异，看它红不红 |
| B. 修复不是你以为的那样 | **先看 `git diff`** |
| C. **契约不完整** | 测试守的契约确实没被破坏，但还有别的契约无人守 |

**本课是 C。** 补上第三条测试后再次变异，**只有新测试红** —— 这个「只红一条」的分布本身证明两个契约被精确区分了。

---

## 八、未提交文件（开工第一件事处理）

```
 M docs/checkpoint/checkpoint-day02.md
 M docs/defect-inventory-day02.md          ← Day 4 新增第九节
 D docs/devil-log-day01.md   ┐
 D docs/devil-log-day02.md   │
 D docs/devil-note-day00.md  ├─ 移动到 docs/log/ 和 docs/note/
 D docs/devil-note-day01.md  │
 D docs/devil-note-day02.md  ┘
?? docs/log/  docs/note/                   ← 新位置
?? docs/checkpoint/checkpoint-day03.md
?? docs/checkpoint/checkpoint-day04.md
?? docs/tutorial/day03-04-determinism.md
?? docs/tutorial/day03-step1-walkthrough.md
?? docs/tutorial/day04-ik-and-defects.md
?? source-notes/DISCOVERSE小白入门讲解.md
```

⚠️ **那批 `D`（deleted）不是文件丢了**，是笔记移进了子目录。

**git 不存储「重命名」这个动作** —— 它存内容快照，重命名是**提交时事后推断的**（内容相似度 >50%）。

**必须在同一个 commit 里 add 两边**，否则重命名信息永久丢失，`git log --follow` 追不到历史。

```bash
git add docs/ source-notes/
git status --short        # 确认看到 R（renamed），而非 D + ??
```

`git status --short` 的两列含义：**第 1 列 = 暂存区（会被提交）**，第 2 列 = 工作区（不会）。

建议 commit message：

```
docs: Day 3-4 确定性攻坚与 IK 修复的教程、实录与缺陷更新

新增：
  tutorial/day03-04-determinism.md      Day 3-4 八步法
  tutorial/day03-step1-walkthrough.md   确定性红灯测试逐行精讲
  tutorial/day04-ik-and-defects.md      Day 4 IK 攻坚
  log/devil-log-day03.md  note/devil-note-day03.md  checkpoint-day03.md
  log/devil-log-day04.md  note/devil-note-day04.md  checkpoint-day04.md

更新 defect-inventory-day02.md 第九节：
  新增缺陷 S/T/U，修正 J（12 物体 9 受影响，非 13/11）、
  O（严重度中->低）、H（根因是夹爪连杆，非 FREE 关节）

整理：devil-* 笔记移入 log/ 与 note/ 子目录
```

---

## 九、Day 3-4 全周期一句话总结

**修了 4 个缺陷，新发现 3 个，查清 1 个根因，用例 90 → 113，覆盖率 30% → 62%。**

**但最有价值的产出不是这些数字，是这条**：

> Day 3-4 一共有 **8 条被写进文档的推断被实测推翻**（Day 3 四条，Day 4 四条），其中一条是当天自己写的。
>
> **所以现在每份 checkpoint 的每条结论都标注「已核实 / 待核实」，而核实的方式是跑一遍。**
