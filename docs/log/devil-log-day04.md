# Devil Log · Day 4 — 过程实录

> 2026-08-05 ｜分支 `feat/test-infra`
> 这份是**踩坑实录**，按时间顺序。知识拆解见 [devil-note-day04.md](../note/devil-note-day04.md)。

---

## 时间线概览

| 阶段 | 事件 | 结果 |
|---|---|---|
| 开工前 | 四项调查全跑一遍 | **计划文档三条推断，两条错了** |
| Step 5 | 缺陷 O：`dt` 遮蔽 | 实测**修复前后逐位相同** → 严重度降级 |
| Step 5 | 「能不能不修」的争论 | 采纳「不写测试」，但仍修 |
| Step 6.1 | 两个泄漏假设的判定实验 | 假设 1 证伪，**假设 2 成立** |
| Step 6.6 | 修复 + 撤 xfail | XPASS(strict) → FAILED → 撤标记 |
| **Step 6.8** | **变异验证** | **⚠️ 没红 —— 全绿** |
| Step 6.8 | 排查为什么没红 | **不是测试错，是契约不完整** |
| Step 6.9 | 补第三条测试 | 再次变异，只有新测试红 ✅ |
| Step 7 | iiwa14 根因 | **零个 FREE 关节**，是夹爪 8 连杆 |
| Step 8 | 覆盖率 + 提交 | 113 passed，`mink_solver.py` **90%** |

**最终产出**：113 passed / 4 skipped / 10 xfailed，TOTAL 覆盖率 **62%**，2 个缺陷修复 + 1 条根因查明 + 2 条新缺陷记录

---

## 卡点 0｜开工前的四项调查推翻了计划文档

Day 3 学到「先证明再动手」，Day 4 开工第一件事就是把 Step 5-7 的前提全查一遍。**结果三条推断错了两条。**

| Step | 计划文档说 | 实测 |
|---|---|---|
| 5 | 修 `dt` 会改变 IK 收敛行为 | ❌ **逐位相同** |
| 6 | `self.configuration` 泄漏，需 `try/finally` | ❌ **不泄漏** |
| 6 | — | ✅ **`posture_task` 才是真泄漏**（新发现） |
| 7 | iiwa14「可能有 FREE 关节占 7 个 qpos」 | ❌ **零个 FREE** |

**如果直接照着文档改，会花时间给 `configuration` 加一个多余的 `try/finally`，同时漏掉真正的泄漏。**

---

## 卡点 1｜`dt` 修复前后为什么一模一样

### 现象

实测四个末端偏移量，`dt=1e-3` 和 `dt=2e-3` 的解**逐位相同**（`atol=1e-9`）：

```
偏移 0.02: iters=1 err=0.000589 | iters=1 err=0.000589 | 相同
偏移 0.05: iters=1 err=0.003180 | iters=1 err=0.003180 | 相同
偏移 0.10: iters=2 err=0.000742 | iters=2 err=0.000742 | 相同
偏移 0.15: iters=2 err=0.003363 | iters=2 err=0.003363 | 相同
```

### 原因

```python
velocity = mink.solve_ik(configuration, tasks, dt, ...)   # 内部把误差【除以 dt】得速度
configuration.integrate_inplace(velocity, dt)             # 又【乘以 dt】积分回去
```

**一除一乘，dt 约掉。** 它只在配了 `mink.VelocityLimit` 时才影响单步位移上限。

### 一个中途的假警报

第一次测的时候我随手编了个目标坐标 `[0.35, -0.1, 0.9]`，结果 `converged=False`，跑满 50 次迭代。

差点以为 IK 本身有问题。**改成「从当前末端位姿偏移 2cm」后立刻 `converged=True, iters=1`** —— 之前那个坐标只是不可达。

**教训**：测某个特性时，要让被测系统处在**正常工作状态**。否则你观察到的失败和你想测的东西无关。

---

## 卡点 2｜「不影响行为为什么还要修」的争论

我原计划让 Step 5 走完整 TDD（写红灯 → 修 → 转绿）。**实测发现没有可观测差异之后，这条路走不通** —— 写不出会红的测试。

### 我提出的方案

不写测试，但改代码。

### 反问（有道理的）

> 为什么不可以忽略，不影响到并且用户角度也走不到？

### 分歧点

「用户角度走不到」要拆成两种：

| 类型 | 例子 | 处置 |
|---|---|---|
| **结构性不可达** | 被 `if False` 挡死、函数无人调用 | 可以忽略 |
| **条件性不可达** | 需某配置/功能开启才显现 | **记录，因为条件会变** |

`dt` 是第二种：一旦有人加 `VelocityLimit`（真机限幅是很自然的需求），配置写 0.002 实际按 0.001 算，**限幅严一倍**而配置文件看起来完全正确 —— **缺陷 J 的剧本重演**。

### 结论（部分采纳）

| 动作 | 决定 |
|---|---|
| 写行为测试 | ❌ **不写**（采纳质疑意见） |
| 改代码 | ✅ 修（一行，实测零风险） |
| 记录严重度降级 | ✅ 中 → 低 |

**判断公式**：比的是「修的成本 + 风险」和「不修的期望损失」，不是「现在有没有影响」。
若修复要改 20 行且有回归风险，正确答案就变成「记录，不修」。

---

## 卡点 3｜Step 6.1 的三次调用实验

### 假设 1：`self.configuration` 泄漏吗

```python
s = MinkIKSolver(...)
a = s.solve_ik(tgt, mat, q)   # 第一次
b = s.solve_ik(tgt, mat, q)   # 第二次，参数完全一样
```

**实测 `a == b`** → 不泄漏。

原因：[solve_ik:99](../../discoverse/universal_manipulation/mink_solver.py#L99) 每次入口 `self.configuration.update(current_qpos)`，上次残留进门就被冲掉。计划文档要加的 `try/finally` 是多余的。

### 假设 2：`posture_task` 泄漏吗（三次调用）

```python
x = s.solve_ik(tgt, mat, q)                      # 第1次：不传 reference
y = s.solve_ik(tgt, mat, q, reference_qpos=ref)  # 第2次：传   ← 污染源
z = s.solve_ik(tgt, mat, q)                      # 第3次：不传
```

**关键：第 1 次和第 3 次输入完全相同，输出必须相同。**

```
第1次: [3.84020671e-06, -7.16114078e-01, 1.00542549e+00]
第2次: [4.42028460e-06, -7.16113819e-01, 1.00542520e+00]
第3次: [4.42028460e-06, -7.16113819e-01, 1.00542520e+00]   ← 跟着第2次
```

**第 3 次没回到第 1 次。泄漏确认。**

### 为什么必须三次

只跑两次（第 1 次不传、第 2 次传）会看到结果不同 —— 但**那是应该的**，输入本来就不同。

**必须有第 3 次，才能构造出「输入相同、中间发生过事」的对照。**

---

## 卡点 4｜XPASS(strict) 报 FAILED —— 修好了却红了

修完代码后跑测试：

```
[XPASS(strict)] 缺陷 U：mink_solver.py:120 的 posture_task target 只在...
FAILED tests/unit/test_mink_solver.py::test_posture_target_does_not_leak_across_calls
1 failed, 1 passed
```

**这是好消息。** 我给测试打了 `xfail(strict=True)`，意思是「预期它会红」。结果它绿了 —— pytest 报错说「你的预期过时了，回来撤标记」。

| | 缺陷还在 | **缺陷修好了** |
|---|---|---|
| `strict=False` | XFAIL | XPASS —— 静默放过 |
| **`strict=True`** | XFAIL | **XPASS → FAILED** |

**这正是 `strict=True` 的设计目的：让「缺陷已修复」也不会静默发生。**

撤掉装饰器、把 docstring 改成「回归测试」之后 → `112 passed`。

---

## 卡点 5｜⚠️ 本课最有价值的一步：变异验证「失败」了

### 现象

按 §6.8 做变异验证 —— **临时**把修复里的 else 分支注释掉：

```python
if reference_qpos is not None:
    temp_config.update(reference_qpos)
# else:
#     temp_config.update(self._default_posture_qpos)
self.posture_task.set_target_from_configuration(temp_config)
```

**预期**：泄漏回归测试转红。
**实际**：`112 passed` —— **和没注释一模一样，全绿。**

### 第一反应（部分错的）

「要么测试写错了，要么 else 不是真正的修复。」

### 查 `git diff` 后的真相

修复实际做了**两件事**：

1. 把 `set_target_from_configuration` **挪出 if 块**
2. 加 else 分支

**注释掉 else 只撤销了第 2 件。泄漏依然被第 1 件修着** —— 原代码里那行在 if 内部，不传 reference 时根本不设目标；挪出来之后每次调用都会显式设定，泄漏即消除，**有没有 else 都一样**。

### 那 else 管什么

实测 `mink.Configuration(model)` 新建时 q = **`qpos0`**，不是 `key(0).qpos`：

```
mink.Configuration(model) 新建  -> [0, 0, 0, 0, 0, 0, ...]        = qpos0
model.key(0).qpos（home）       -> [0, -1, 1.2, 1.5708, -1.2, -1.5708, ...]
两者不同
```

| 写法 | 不传 reference 时 posture 目标 | 泄漏 |
|---|---|---|
| 原代码 | 完全不设 → 沿用上次 | ✅ |
| 挪出 `set_target`，**无** else | **qpos0** | ❌ |
| 挪出 `set_target`，**有** else | **home** | ❌ |

**两种都不泄漏，但默认姿态取值不同**，会影响冗余自由度下选哪个解。

### 结论：测试没写错，是契约不完整

那条测试守的「不泄漏」契约**确实没被破坏**，所以它绿是对的。

问题是「**默认姿态是 home**」这个契约**根本没人守**。

### 补测后再验证

加了 `test_default_posture_target_is_home_not_qpos0`，再次注释 else：

```
FAILED tests/unit/test_mink_solver.py::test_default_posture_target_is_home_not_qpos0
1 failed, 2 passed
```

**只有新测试红，另外两条仍绿** —— 精确说明「注释 else 不会让泄漏回来，只会改变默认姿态取值」。契约现在完整了。

### 这一步暴露的第二件事

**我在教程 §6.6 把 else 分支说成「修复的关键」—— 那句话是错的。**

跳过变异验证的话，会带着这个错误认知继续，直到某天有人删掉 else，泄漏没回来但默认姿态悄悄从 home 变成 qpos0，而完全想不通哪里出了问题。

> **变异验证的价值不止「验证测试有效」，它还能暴露你对自己修复的理解是错的。**

---

## 卡点 6｜iiwa14 差 6 的真相

原猜测「可能有 FREE 关节占 7 个 qpos」。遍历 `jnt_type` 之后：**4 个模型零个 FREE，全是 HINGE + SLIDE。**

```
=== iiwa14  nq=15 ===
   0-6   joint1~7                  HINGE   ← 7 轴臂
   7-10  right_{driver,coupler,spring_link,follower}_joint   HINGE
  11-14  left_{driver,coupler,spring_link,follower}_joint    HINGE
```

**夹爪是 Robotiq 式平行连杆机构**：left/right 各 4 根杆，由约束耦合成 **1 个物理自由度**，但每根杆各占 1 个 qpos。

YAML 写 `qpos_dim: 9` = 7 臂 + **2**（按「两根手指」算）。实际是 7 + **8**。**差 6 就是这么来的。**

| 机器人 | 臂 | 夹爪 | nq | YAML | 差 |
|---|---|---|---|---|---|
| arx_x5 / piper | 6 | 2 SLIDE | 8 | 7 | 1 |
| rm65 | 6 | 6 HINGE + 2 SLIDE | 14 | 12 | 2 |
| iiwa14 | 7 | **8 HINGE** | 15 | 9 | **6** |

### 处置：不改数字

`qpos_dim` 的语义**本身没定义** —— 指模型 `nq`（15）还是可控自由度（7 臂 + 1 夹爪 = 8）？那 8 根连杆是被约束的从动关节，算 1 个还是 8 个取决于定义。

**在有共识之前改数字只是把一个错误换成另一个错误。**

只把 xfail 的 reason 从「原因不明」升级为「根因已知 + 待决策点明确」。下一个人可以直接开始决策，而不用重新调查。

---

## Day 4 最终数字

| 项 | Day 3 结束 | Day 4 结束 |
|---|---|---|
| 用例 | 110 passed | **113 passed** |
| xfail | 10 | 10 |
| **`mink_solver.py`** | 46% | **90%** |
| `randomization.py` | 69% | 69% |
| **TOTAL** | 59% | **62%** |
| commit | `cd09b80` | `c722ca8` |

`mink_solver.py` 剩下 8 行未覆盖（异常分支 + `__str__`/`__repr__`）—— **不值得为它们写测试**。

---

## Day 3-4 全周期总结

| | Day 2 结束 | **Day 4 结束** |
|---|---|---|
| 用例 | 90 | **113** |
| 覆盖率 | 30% | **62%** |
| commit | 1 | **3**（J / seed / IK） |
| 缺陷修复 | 0 | **4**（J、seed、O、U） |
| 新发现缺陷 | — | **3**（S、T、U） |
| 根因查明 | — | **1**（H） |

**Day 3-4 计划的三个覆盖率目标全部达成且超额。**

---

## 未完成（Day 5+）

- [ ] 缺陷 S（贴图随机源）—— 需改 `get_random_texture` 公共签名，牵连 4 个调用方
- [ ] 缺陷 T（print vs logging）
- [ ] 缺陷 H —— **待决策**：先定义 `qpos_dim` 语义
- [ ] 文档提交（含 `docs/note/` 的重命名，必须与删除同 commit）
- [ ] Day 5：flake 定量分析
