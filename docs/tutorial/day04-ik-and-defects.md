# Day 4 — IK 攻坚与缺陷收尾（Step 5-8）

> 上接 [day03-04-determinism.md](day03-04-determinism.md) Step 0-4（已完成）
> 本课产出：缺陷 O 修复、IK 状态泄漏定性与修复、缺陷 H 根因、Day 3-4 收尾提交
> 预计耗时：约 3 小时

---

## 0｜开工前：本课的四项调查已全部完成

⚠️ **重要**：Day 3-4 计划文档里对 Step 5-7 的描述，**有三处被实测推翻**。本文用的是实测结论。

| Step | 计划文档的说法 | **实测结论** |
|---|---|---|
| 5 | `dt` 遮蔽 → 修复会改变 IK 收敛行为 | **不会改变，逐位相同**（dt 在一除一乘中约掉） |
| 6 | `self.configuration` 状态泄漏，需 try/finally | **不泄漏**（每次入口被 `update()` 覆盖） |
| 6 | — | **`posture_task` target 才是真泄漏**（实测确认） |
| 7 | iiwa14 nq 差 6「最可疑，可能有 FREE 关节」 | **没有 FREE 关节，是夹爪 8 连杆** |

**这四条是本课最重要的教学内容**：checkpoint 里三条推断，两条错了。**先证明，再动手。**

### 基线确认

```bash
cd /home/ubuntu22/workspaces/airbot-play/DISCOVERSE
source scripts/dev/env.sh
$PY -m pytest tests/ -q | tail -3
```

**预期**：`110 passed, 4 skipped, 10 xfailed`

---

## 本课四步

| Step | 做什么 | 时间 | 性质 |
|---|---|---|---|
| 5 | 缺陷 O：`dt` 遮蔽 | 15 min | 代码卫生，**不写测试** |
| 6 | IK 状态泄漏：`posture_task` target | 60 min | **真缺陷，TDD 红→绿** |
| 7 | 缺陷 H：iiwa14 根因 | 30 min | 调查 + 撤销 xfail |
| 8 | 收尾：defect-inventory、覆盖率、提交 | 45 min | — |

---

# Step 5｜缺陷 O：`dt` 被硬编码遮蔽（15 分钟）

## 5.1 现象

[mink_solver.py:50](../../discoverse/universal_manipulation/mink_solver.py#L50) 读了配置：

```python
self.dt = self.solver_config.get('dt', 2e-3)
```

[mink_solver.py:126](../../discoverse/universal_manipulation/mink_solver.py#L126) 在 `solve_ik` 里又定义了一个局部变量：

```python
dt = 1e-3
```

第 136、142 行用的都是**局部的 `dt`**，`self.dt` 从未被使用。

**9/9 机器人的 YAML 都配了 `dt: 0.002`**（实测），全部无效，实际跑的是 `0.001`。

## 5.2 ⚠️ 实测：修复不改变任何行为

我先测了一遍再决定怎么教。**同一目标，两种 dt，解逐位相同**（`atol=1e-9`）：

| 末端偏移 | dt=1e-3（现状） | dt=2e-3（配置值） | 解相同 |
|---|---|---|---|
| 2cm | 1 迭代，err=0.000589 | 1 迭代，err=0.000589 | ✅ |
| 5cm | 1 迭代，err=0.003180 | 1 迭代，err=0.003180 | ✅ |
| 10cm | 2 迭代，err=0.000742 | 2 迭代，err=0.000742 | ✅ |
| 15cm | 2 迭代，err=0.003363 | 2 迭代，err=0.003363 | ✅ |

### 为什么 dt 会约掉

```python
velocity = mink.solve_ik(configuration, tasks, dt, ...)   # 内部把任务误差【除以 dt】得期望速度
configuration.integrate_inplace(velocity, dt)             # 又【乘以 dt】积分回去
```

**一除一乘，dt 消失。**

它唯一的作用是给速度限制（`mink.VelocityLimit`）提供量纲 —— 而当前配置**没有速度限制**，所以 dt 完全不起作用。

> 📌 **知识点：「配置无效」和「配置无效且有害」是两回事**
>
> 判断未消费配置的严重度，要问：**如果它生效了，行为会变吗？**
>
> | 缺陷 | 生效后 | 严重度 |
> |---|---|---|
> | J（碰撞半径） | 0.05 → 0.12，**行为大变** | 高 |
> | **O（dt）** | **逐位相同** | **低** |
>
> 两者都是「配置没人读」，危害差一个数量级。**不要因为模式相同就假设严重度相同。**

## 5.3 决策：修，但不写测试

| 动作 | 做不做 | 理由 |
|---|---|---|
| 写行为测试 | ❌ **不写** | 没有可观测差异，测不出来；写了也是永远为真的断言 |
| 改代码 | ✅ **做** | 一行，实测零风险 |
| 记进 defect-inventory | ✅ **做** | 严重度降为「低」，注明休眠条件 |

**为什么「现在没影响」不足以支撑不修**：

修复成本 = 一行 + 实测零风险。
不修的期望损失 = 将来有人加速度限制时，`dt` 立刻生效，配置写 0.002 实际按 0.001 算，**限幅严一倍**，IK 变慢或不收敛，而配置文件看起来完全正确 —— **缺陷 J 的剧本重演**。

> 📌 **知识点：休眠缺陷（latent defect）**
>
> 「当前不可达」有两种：
>
> | 类型 | 例子 | 处置 |
> |---|---|---|
> | **结构性不可达** | 被 `if False` 挡死、函数无人调用 | 可删可忽略 |
> | **条件性不可达** | 需某配置/功能开启才显现 | **记录，因为条件会变** |
>
> `dt` 是第二种 —— 不是「不会发生」，是「**还没发生**」。缺陷 S（贴图随机源）同类。
>
> **判断公式：比的是「修的成本+风险」和「不修的期望损失」，不是「现在有没有影响」。**
> 若修复要改 20 行且有回归风险，正确答案就变成「记录，不修」。

## 5.4 操作

**改 [mink_solver.py:126](../../discoverse/universal_manipulation/mink_solver.py#L126)**，删掉这行：

```python
        dt = 1e-3
```

**改 [:136](../../discoverse/universal_manipulation/mink_solver.py#L136) 和 [:142](../../discoverse/universal_manipulation/mink_solver.py#L142)**，两处 `dt` → `self.dt`：

```python
            velocity = mink.solve_ik(
                self.configuration,
                self.tasks,
                self.dt,          # ← 改这里
                self.solver_type,
                self.damping
            )

            # 积分更新配置
            self.configuration.integrate_inplace(velocity, self.dt)   # ← 和这里
```

**自查**（`solve_ik` 内应无裸 `dt`）：

```bash
sed -n '124,145p' discoverse/universal_manipulation/mink_solver.py | grep -n "dt"
```

## 5.5 验收

```bash
$PY -m pytest tests/ -q | tail -3
```

**预期：`110 passed` 不变**（实测已证明行为逐位相同）。

---

# Step 6｜IK 状态泄漏（60 分钟）⭐ 本课核心

## 6.1 先证明，再修 —— 计划文档那条是错的

计划文档要求给 `self.configuration` 加 `try/finally` 恢复。**实测：不需要。**

### 我跑的判定实验（你要自己复现）

```bash
source scripts/dev/env.sh
$PY - <<'PYEOF' 2>&1 | grep -v "Warning:\|Traceback\|File \|Module\|    from\|Gripper\|body airbot"
import os, numpy as np, mujoco
from discoverse.envs.make_env import make_env
from discoverse import DISCOVERSE_ASSETS_DIR, DISCOVERSE_ROOT_DIR
from discoverse.universal_manipulation.robot_config import RobotConfigLoader
from discoverse.universal_manipulation.mink_solver import MinkIKSolver
xml=os.path.join(DISCOVERSE_ASSETS_DIR,"mjcf","tmp","airbot_play_place_block.xml")
make_env("airbot_play","place_block",xml)
m=mujoco.MjModel.from_xml_path(xml); d=mujoco.MjData(m)
rc=RobotConfigLoader(os.path.join(DISCOVERSE_ROOT_DIR,"discoverse","configs","robots","airbot_play.yaml"))
mujoco.mj_forward(m,d); q=m.key(0).qpos.copy()
sid=mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_SITE,rc.end_effector_site)
d.qpos[:]=q; mujoco.mj_forward(m,d)
base=d.site_xpos[sid].copy(); mat=d.site_xmat[sid].reshape(3,3).copy()
tgt=base+np.array([0.08,0,0])

print("--- 假设1: self.configuration 泄漏? ---")
s=MinkIKSolver(rc,m,d)
a,_,_=s.solve_ik(tgt,mat,q); b,_,_=s.solve_ik(tgt,mat,q)
print("  两次同参调用解相同?", np.allclose(a,b,atol=1e-12))

print("--- 假设2: posture_task target 泄漏? ---")
s2=MinkIKSolver(rc,m,d)
ref=q.copy(); ref[:6]+=0.3
x,_,_=s2.solve_ik(tgt,mat,q)                      # 无 reference
y,_,_=s2.solve_ik(tgt,mat,q,reference_qpos=ref)   # 设 reference
z,_,_=s2.solve_ik(tgt,mat,q)                      # 又不给 reference
print("  第1次(无ref) vs 第3次(无ref) 相同?", np.allclose(x,z,atol=1e-12))
print(f"  第1次: {x[:3]}")
print(f"  第2次: {y[:3]}")
print(f"  第3次: {z[:3]}")
PYEOF
```

### 实测结果

```
--- 假设1: self.configuration 泄漏? ---
  两次同参调用解相同? True          ← 不泄漏

--- 假设2: posture_task target 泄漏? ---
  第1次(无ref) vs 第3次(无ref) 相同? False    ← 泄漏！
  第1次: [3.84020671e-06 -7.16114078e-01 1.00542549e+00]
  第2次: [4.42028460e-06 -7.16113819e-01 1.00542520e+00]
  第3次: [4.42028460e-06 -7.16113819e-01 1.00542520e+00]
```

**关键观察：第 3 次和第 2 次逐位相同，而不是回到第 1 次。**

第 3 次的输入和第 1 次**完全一样**（同 target、同 qpos、都不给 reference），输出却跟着第 2 次走 —— **第 2 次设的 posture 目标残留了下来**。

## 6.2 为什么假设 1 不成立

看 [mink_solver.py:99](../../discoverse/universal_manipulation/mink_solver.py#L99)：

```python
def solve_ik(self, target_pos, target_ori, current_qpos, reference_qpos=None):
    self.configuration.update(current_qpos)     # ← 每次入口都被覆盖
```

上一次的残留**在下一次入口就被 `current_qpos` 冲掉了**。加 `try/finally` 是多余的。

## 6.3 为什么假设 2 成立

[mink_solver.py:120-123](../../discoverse/universal_manipulation/mink_solver.py#L120)：

```python
if reference_qpos is not None:
    temp_config = mink.Configuration(self.mj_model)
    temp_config.update(reference_qpos)
    self.posture_task.set_target_from_configuration(temp_config)
# ← else 分支不存在：不给 reference 时，沿用上一次设的目标
```

**和 `configuration` 不同，它没有「每次入口重置」的保护。**

> 📌 **知识点：状态泄漏的判定标准**
>
> 判据不是「对象有可变字段」，而是：
>
> **「调用 N 次后的输出，是否只由第 N 次的输入决定？」**
>
> 用这个判据重新审视：
>
> | 字段 | 每次入口重置 | 泄漏 |
> |---|---|---|
> | `self.configuration` | ✅ 被 `current_qpos` 覆盖 | ❌ 不泄漏 |
> | `self.posture_task` target | ❌ 只在给 reference 时更新 | ✅ **泄漏** |
>
> 这是**纯函数（pure function）思想的实用版本**：相同输入必得相同输出。
> 测试开发对纯函数最友好，对有隐藏状态的对象最头疼。

## 6.4 这个缺陷的真实危害

`posture_task` 是「姿态保持」任务 —— 它把解往某个参考构型上拉，用来在冗余自由度里选一个「自然」的解。

泄漏意味着：**同样的目标点，IK 给出的解取决于「上一次调用有没有传 reference」**。

在任务序列里（抓 → 抬 → 移 → 放），某一步传了 reference，后续所有步骤都会沿用它 —— **而调用方完全不知道**。

**这是可复现性问题的另一个来源**，与 Day 3 的 seed 属同一类：**隐藏状态让「相同输入」得到「不同输出」**。

## 6.5 先写测试（红）

新建 `tests/unit/test_mink_solver.py`：

```python
"""MinkIKSolver 的状态隔离契约。

判定标准（见 devil-note-day04.md）：
    调用 N 次后的输出，是否只由第 N 次的输入决定？

实测（2026-08-04）：
    self.configuration      -> 不泄漏（solve_ik:99 每次入口被 update 覆盖）
    self.posture_task target -> 【泄漏】（:120 只在给 reference 时更新，否则沿用）
"""
import os

import mujoco
import numpy as np
import pytest

pytestmark = [pytest.mark.integration]

ROBOT = "airbot_play"
TASK = "place_block"


@pytest.fixture(scope="module")
def solver_env(task_config_dir):
    """构造 IK 求解器所需的模型 / 配置 / 参考位姿。

    module 级：make_env + 模型编译不便宜，而本文件的用例
    都只【读】这些对象，真正可变的 solver 在每个用例里新建。
    """
    from discoverse.envs.make_env import make_env
    from discoverse import DISCOVERSE_ASSETS_DIR
    from discoverse.universal_manipulation.robot_config import RobotConfigLoader

    xml = os.path.join(DISCOVERSE_ASSETS_DIR, "mjcf", "tmp", f"{ROBOT}_{TASK}.xml")
    make_env(ROBOT, TASK, xml)

    model = mujoco.MjModel.from_xml_path(xml)
    data = mujoco.MjData(model)
    robot_config = RobotConfigLoader(
        str(task_config_dir.parent / "robots" / f"{ROBOT}.yaml")
    )

    if model.nkey == 0:
        pytest.skip("模型无 keyframe，MinkIKSolver 构造会失败")

    home_qpos = model.key(0).qpos.copy()
    data.qpos[:] = home_qpos
    mujoco.mj_forward(model, data)

    site_id = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_SITE, robot_config.end_effector_site
    )
    assert site_id >= 0, f"找不到末端 site: {robot_config.end_effector_site}"

    return {
        "model": model,
        "data": data,
        "robot_config": robot_config,
        "home_qpos": home_qpos,
        # 取当前末端位姿做基准 —— 保证目标可达。
        # 随手编一个坐标很可能不可达，届时 converged=False，
        # 测试红了却和状态泄漏无关。
        "ee_pos": data.site_xpos[site_id].copy(),
        "ee_mat": data.site_xmat[site_id].reshape(3, 3).copy(),
    }


@pytest.fixture
def make_solver(solver_env):
    """每个用例新建 solver —— 它持有可变状态，绝不能跨用例复用。"""
    from discoverse.universal_manipulation.mink_solver import MinkIKSolver

    def _make():
        return MinkIKSolver(
            solver_env["robot_config"], solver_env["model"], solver_env["data"]
        )

    return _make


def test_repeated_solve_is_deterministic(solver_env, make_solver):
    """【已核实不泄漏】同参数连续调用两次，解应相同。

    这条守的是 self.configuration —— solve_ik:99 每次入口
    self.configuration.update(current_qpos) 已经隔离了它。
    计划文档要求加 try/finally 恢复 configuration，实测【不需要】。

    这条测试的价值是【防止有人日后把那行 update 删掉】。
    """
    solver = make_solver()
    target = solver_env["ee_pos"] + np.array([0.08, 0.0, 0.0])

    first, _, _ = solver.solve_ik(target, solver_env["ee_mat"], solver_env["home_qpos"])
    second, _, _ = solver.solve_ik(target, solver_env["ee_mat"], solver_env["home_qpos"])

    np.testing.assert_allclose(first, second, atol=0, rtol=0)


@pytest.mark.xfail(
    strict=True,
    reason="缺陷 U：mink_solver.py:120 的 posture_task target 只在 "
           "reference_qpos is not None 时更新，没有 else 分支恢复默认。"
           "先传一次 reference 之后，后续【不传 reference】的调用会沿用它 —— "
           "同样的输入得到不同的输出。与 self.configuration 不同，"
           "它没有『每次入口重置』的保护。",
)
def test_posture_target_does_not_leak_across_calls(solver_env, make_solver):
    """【核心红灯】reference_qpos 不应污染后续不传 reference 的调用。

    判定：调用 N 次后的输出，是否只由第 N 次的输入决定？

    第 1 次和第 3 次的输入【完全相同】（同 target、同 qpos、都不给 reference），
    所以输出必须相同。实测第 3 次跟着第 2 次走 —— 泄漏。
    """
    solver = make_solver()
    target = solver_env["ee_pos"] + np.array([0.08, 0.0, 0.0])
    ori = solver_env["ee_mat"]
    home = solver_env["home_qpos"]

    reference = home.copy()
    reference[:6] += 0.3          # 一个明显不同的参考构型

    first, _, _ = solver.solve_ik(target, ori, home)
    solver.solve_ik(target, ori, home, reference_qpos=reference)   # 污染源
    third, _, _ = solver.solve_ik(target, ori, home)

    np.testing.assert_allclose(
        third, first, atol=0, rtol=0,
        err_msg="第 3 次调用与第 1 次输入完全相同，解却不同 —— "
                "posture_task target 被第 2 次调用污染",
    )
```

**跑，确认第二条红（表现为 xfail）：**

```bash
$PY -m pytest tests/unit/test_mink_solver.py -v 2>&1 | grep -E "PASSED|XFAIL|FAILED"
```

**预期**：`test_repeated_solve_is_deterministic PASSED` + `test_posture_target_does_not_leak XFAIL`

> ⚠️ 这里用 `xfail` 而不是让它 FAILED，是为了**保持主线全绿**。修完之后 `strict=True` 会让它 XPASS 报错，强制你回来撤标记 —— 这正是我们想要的。

## 6.6 修复

**在 [mink_solver.py:_setup_ik_tasks](../../discoverse/universal_manipulation/mink_solver.py#L72) 里记住默认姿态目标**。找到这段：

```python
        if self.mj_model.nkey > 0:
            home_qpos = self.mj_model.key(0).qpos.copy()
            self.configuration.update(home_qpos)
            self.posture_task.set_target_from_configuration(self.configuration)
        else:
            raise ValueError("MuJoCo model does not contain keyframes. Cannot set home posture.")
```

**在末尾加一行**，把默认参考构型存下来：

```python
        if self.mj_model.nkey > 0:
            home_qpos = self.mj_model.key(0).qpos.copy()
            self.configuration.update(home_qpos)
            self.posture_task.set_target_from_configuration(self.configuration)
            # 记住默认姿态目标：solve_ik 不传 reference_qpos 时要恢复到它，
            # 否则上一次调用传入的 reference 会残留下来污染后续求解。
            self._default_posture_qpos = home_qpos
        else:
            raise ValueError("MuJoCo model does not contain keyframes. Cannot set home posture.")
```

**然后给 [:120](../../discoverse/universal_manipulation/mink_solver.py#L120) 补上 else 分支**：

```python
        # 姿态任务目标：每次调用都显式设定，不沿用上一次。
        # 缺陷 U：原代码只有 if 分支，导致传过一次 reference_qpos 之后，
        # 后续【不传】的调用会继续用它 —— 相同输入得到不同输出。
        temp_config = mink.Configuration(self.mj_model)
        if reference_qpos is not None:
            temp_config.update(reference_qpos)
        else:
            temp_config.update(self._default_posture_qpos)
        self.posture_task.set_target_from_configuration(temp_config)
```

> 📌 **为什么恢复到 home 而不是 `current_qpos`**
>
> 两种语义都说得通，但 **home 保持了原有的默认行为** —— 构造时 `_setup_ik_tasks` 就是用 `key(0).qpos` 设的 posture 目标。
>
> 用 `current_qpos` 会让「不传 reference」的行为**从「拉向 home」变成「保持当前」**，那是行为变更，不是 bug 修复。
>
> **Day 3 学的原则再用一次：修复应当恢复「本来该有的行为」，而不是顺手改成「我觉得更好的行为」。**

### ⚠️ 实测修正：else 分支不是「修泄漏」的关键

**本节初稿把 else 分支说成修复的核心 —— 那是错的**，是 §6.8 的变异验证暴露出来的（见 §6.8 实录）。

真正消除泄漏的是**把 `set_target_from_configuration` 挪出 if 块**。原代码里那行在 if 内部，不传 reference 时**根本不设目标**，于是沿用上次；挪出来之后，每次调用都会显式设定，泄漏即被消除 —— **有没有 else 都一样**。

那 else 分支管什么？**管「默认姿态取谁」：**

| 写法 | 不传 reference 时的 posture 目标 | 泄漏 |
|---|---|---|
| 原代码 | 完全不设 → 沿用上次 | ✅ 泄漏 |
| 挪出 `set_target`，**无** else | `mink.Configuration(model)` 的默认值 = **`qpos0`** | ❌ 不泄漏 |
| 挪出 `set_target`，**有** else | `key(0).qpos` = **home** | ❌ 不泄漏 |

**实测**（airbot_play）：

```
mink.Configuration(model) 新建     -> q = qpos0  = [0, 0, 0, 0, 0, 0, ...]
model.key(0).qpos（home）          -> [0, -1, 1.2, 1.5708, -1.2, -1.5708, ...]
两者不同
```

**差得很远**，会影响冗余自由度下选哪个解。所以 else 仍然要加 —— 但理由是**保持原有默认行为**，不是修泄漏。

> 📌 **知识点：一个缺陷的修复里可能藏着两个独立契约**
>
> 这里是「**不泄漏**」和「**默认值是 home**」。它们碰巧被同一段代码实现，但**可以独立地被破坏**。
>
> 只写一条测试守住其中一个，另一个就是裸奔的 —— 这正是 §6.8 变异验证发现的问题。

## 6.7 撤销 xfail，确认变绿

修完之后 `strict=True` 会让测试 **XPASS → FAILED**，强制你回来：

```bash
$PY -m pytest tests/unit/test_mink_solver.py -v 2>&1 | tail -5
# 预期看到 [XPASS(strict)] -> FAILED
```

**这时把 `@pytest.mark.xfail(...)` 整个装饰器删掉**，并在 docstring 里记录修复：

```python
def test_posture_target_does_not_leak_across_calls(solver_env, make_solver):
    """【回归】reference_qpos 不应污染后续不传 reference 的调用。

    缺陷 U，Day 4 修复：给 mink_solver.py:120 补上 else 分支，
    不传 reference 时恢复到构造时记住的 _default_posture_qpos。
    """
```

**再跑：**

```bash
$PY -m pytest tests/ -q | tail -3
```

**预期**：`112 passed, 4 skipped, 10 xfailed`（110 + 本文件 2 条）

## 6.8 ⚠️ 变异验证（不要跳过）—— 本课最有价值的一步

Day 3 学的：**改一个应该影响结果的东西，测试必须有反应。**

**临时**把修复里的 else 分支注释掉：

```python
        if reference_qpos is not None:
            temp_config.update(reference_qpos)
        # else:
        #     temp_config.update(self._default_posture_qpos)
```

跑测试。

### 实录：第一次变异验证「失败」了

**预期**：`test_posture_target_does_not_leak` 转红。
**实际**：`112 passed` —— **全绿，和没注释一模一样。**

注释掉修复，测试毫无反应。按验收标准，这是**测试失效**的信号。

### 排查：不是测试写错，是契约不完整

查 `git diff` 后发现，修复实际做了**两件事**：

1. 把 `set_target_from_configuration` 从 if 块里**挪了出来** ← 这个消除了泄漏
2. 加了 else 分支 ← 这个决定默认姿态取谁

注释掉 else 只撤销了第 2 件。**泄漏依然被第 1 件修着**，所以泄漏测试当然还是绿的。

**测试没写错 —— 它守的「不泄漏」契约确实没被破坏。问题是「默认姿态是 home」这个契约根本没人守。**

### 补上缺失的那条测试

见 §6.9 `test_default_posture_target_is_home_not_qpos0`。

补完再做一次变异验证：

```
FAILED tests/unit/test_mink_solver.py::test_default_posture_target_is_home_not_qpos0
1 failed, 2 passed
```

**只有新测试红，另外两条仍绿** —— 精确说明「注释 else 不会让泄漏回来，只会改变默认姿态取值」。契约现在完整了。

**验完立刻恢复 else。**

> 📌 **变异验证的价值不止「验证测试有效」**
>
> 它还能暴露 **你对自己修复的理解是错的**。
>
> 本课初稿把 else 分支说成「修复的关键」—— 错的。跳过这一步，你会带着这个错误认知继续，直到某天有人删掉 else，泄漏没回来但默认姿态悄悄从 home 变成 qpos0，而你完全想不通哪里出了问题。
>
> **绿灯从来不是证据。能对已知的破坏做出反应，才是证据。**

---

## 6.9 补测：锁住「默认姿态是 home」

```python
def test_default_posture_target_is_home_not_qpos0(solver_env, make_solver):
    """不传 reference 时，posture 目标应是构造时的 home，而非模型 qpos0。

    【这条测试来自一次失败的变异验证】（Day 4）：
    注释掉 else 分支后 test_posture_target_does_not_leak 仍全绿 ——
    说明它没能守住完整契约。

    真正消除泄漏的是把 set_target_from_configuration 挪出 if 块。
    挪出后不传 reference 时 temp_config 保持新建状态，
    而 mink.Configuration(model) 的默认值是【qpos0】（airbot_play 全 0），
    不是 key(0).qpos（home，[0,-1,1.2,1.5708,-1.2,-1.5708]）。
    两者都不泄漏，但默认姿态取谁是另一个契约。

    ⚠️ target_q 是 mink 的内部属性（不在 dir(PostureTask) 的公开列表里，
    只在实例 vars() 中）。这是唯一能观测 posture 目标的途径 ——
    属于为锁住契约而接受的耦合。mink 升级换掉它，本测试要重写。
    """
    import mink

    solver = make_solver()
    home = solver_env["home_qpos"]

    solver.solve_ik(solver_env["ee_pos"], solver_env["ee_mat"], home)   # 不传 reference

    expected = mink.Configuration(solver_env["model"])
    expected.update(home)
    n = len(solver.posture_task.target_q)

    np.testing.assert_allclose(
        solver.posture_task.target_q, expected.q[:n], atol=0, rtol=0,
        err_msg="不传 reference 时 posture 目标不是 home —— "
                "可能退化成了 qpos0（else 分支缺失或失效）",
    )
```

**验收**：`$PY -m pytest tests/ -q` → `113 passed`

---

# Step 7｜缺陷 H：iiwa14 的 nq 差 6（30 分钟）

## 7.1 先核对枚举值（checkpoint 让你自己核对的那步）

```bash
$PY -c "
import mujoco
print({n: getattr(mujoco.mjtJoint, n).value for n in dir(mujoco.mjtJoint) if n.startswith('mjJNT')})"
```

**实测输出**：`{'mjJNT_BALL': 1, 'mjJNT_FREE': 0, 'mjJNT_HINGE': 3, 'mjJNT_SLIDE': 2}`

**checkpoint-day02 里的 TYPE 映射是对的**（FREE=0, BALL=1, SLIDE=2, HINGE=3）。这次核对没查出问题 —— 但核对本身是必要的。

## 7.2 跑调查脚本

```bash
$PY - <<'PYEOF' 2>&1 | grep -v "Warning\|Traceback\|File \|Module\|    from"
import mujoco, glob, os
TYPE={0:"FREE(7)",1:"BALL(4)",2:"SLIDE(1)",3:"HINGE(1)"}
for name in ["iiwa14","arx_x5","piper","rm65"]:
    p=f"models/mjcf/manipulator/robot_{name}.xml"
    m=mujoco.MjModel.from_xml_path(p)
    print(f"\n=== {name}  nq={m.nq} nu={m.nu} njnt={m.njnt} ===")
    for j in range(m.njnt):
        nm=mujoco.mj_id2name(m,mujoco.mjtObj.mjOBJ_JOINT,j) or "(无名)"
        print(f"  {j:2d} {nm:24s} {TYPE.get(int(m.jnt_type[j]),'?'):9s}")
PYEOF
```

## 7.3 实测结论：**没有 FREE 关节，是夹爪建模差异**

checkpoint 猜测「iiwa14 差 6 最可疑，可能有 FREE 关节占 7 个 qpos」。**猜错了。**

| 机器人 | nq | 臂关节 | 夹爪关节 | YAML `qpos_dim` | 差 |
|---|---|---|---|---|---|
| arx_x5 | 8 | 6 HINGE | **2 SLIDE**（finger_joint1/2） | 7 | 1 |
| piper | 8 | 6 HINGE | **2 SLIDE** | 7 | 1 |
| rm65 | 14 | 6 HINGE | **6 HINGE + 2 SLIDE** = 8 | 12 | 2 |
| **iiwa14** | **15** | **7 HINGE** | **8 HINGE**（每侧 4 连杆） | **9** | **6** |

**iiwa14 的夹爪**（实测关节名）：

```
right_driver_joint / right_coupler_joint / right_spring_link_joint / right_follower_joint
left_driver_joint  / left_coupler_joint  / left_spring_link_joint  / left_follower_joint
```

这是一个 **8 连杆的平行夹爪机构**（Robotiq 风格）—— 每侧 4 个关节由**等式约束/腱**耦合，实际只有 1 个自由度，但 MuJoCo 里每个连杆都是一个 joint，各占 1 个 qpos。

**YAML 写的 `qpos_dim: 9` = 7 臂 + 2 夹爪**，把 8 连杆当成了 2 个手指。

## 7.4 为什么这类错误能长期存在

checkpoint-day02 有一段精彩分析，实测印证了它：

| 字段 | 写错的后果 |
|---|---|
| `ctrl_dim` | `data.ctrl[:] = 长度不符数组` → **立刻 ValueError** → 9/9 全对 |
| `qpos_dim` | `qpos[:9]` 在 `nq=15` 上**完全合法** → 静默丢掉后 6 个 → 4/9 出错 |

> 📌 **可以推广成一条测试开发的世界观：**
>
> **「哪里没有反馈，哪里就有缺陷。」**
>
> 会炸的字段维护得好，不会炸的字段积累错误。
>
> **测试的本质工作，就是给那些原本不会炸的地方装上会炸的机制。**
>
> 这句话可以直接用在面试回答里。

## 7.5 处置决策

**不改 YAML 的 `qpos_dim`。** 理由：

1. `qpos_dim` 的**语义本身是模糊的** —— 它指「整个模型的 nq」还是「机械臂可控自由度」？rm65/iiwa14 的连杆是**被约束的从动关节**，算不算「自由度」取决于你问谁。
2. 改它可能破坏依赖该值的代码（需先查 `grep -rn "qpos_dim"`）。
3. **本课的产出是「根因清楚了」，不是「数字改对了」。**

**要做的是把 xfail 的 reason 从「原因不明」升级为「已知根因」**：

打开 `tests/unit/test_robot_config.py`，找到 `test_qpos_dim_matches_mjcf_nq` 的 xfail 标记，把 reason 改成实测结论。例如 iiwa14 那条：

```
缺陷 H：iiwa14 声明 qpos_dim=9（7 臂 + 2 夹爪），MJCF nq=15。
根因（Day 4 实测）：夹爪是 8 连杆平行机构（left/right 各 4 个
driver/coupler/spring_link/follower 关节），由约束耦合成 1 自由度，
但每个连杆各占 1 个 qpos。YAML 按「2 个手指」计数。
同类：rm65 差 2（夹爪 6 HINGE + 2 SLIDE），arx_x5/piper 差 1（2 SLIDE 手指）。
待决：qpos_dim 语义未定义（模型 nq？可控 DOF？），改动前需先定义。
```

> 📌 **知识点：调查的产出可以是「定义问题」而不是「修复问题」**
>
> 有些缺陷的正确处置是**先把语义定清楚**。在 `qpos_dim` 到底指什么没有共识之前，改数字只是把一个错误换成另一个错误。
>
> **把「原因不明」升级为「根因已知 + 待决策点明确」，本身就是有价值的产出。**

---

# Step 8｜收尾（45 分钟）

## 8.1 覆盖率复测

```bash
$PY -m pytest tests/ --cov --cov-report=term-missing -q 2>&1 | grep -E "^discoverse|^TOTAL|^Name|^---"
```

对比基线：

| 模块 | Day 2 | Day 3 | Day 4 目标 |
|---|---|---|---|
| `randomization.py` | 9% | 69% | — |
| `mink_solver.py` | 19% | 46% | **60%+**（本课直接测了它） |
| TOTAL | 30% | 59% | 60%+ |

⚠️ **不要为刷数字写无意义的测试。** 看 Missing 那列找盲区。

## 8.2 更新 defect-inventory

追加三条（缺陷 S 是 Day 3 的欠账）：

| 编号 | 位置 | 内容 | 严重度 | 状态 |
|---|---|---|---|---|
| **S** | `utils/__init__.py:86-97` | `get_random_texture()` 两分支各用一种未受管控的随机源（stdlib `random.choice` / `np.random` 全局流），贴图选择不可复现 | 中 | 未修，xfail 守着 |
| **T** | 多处 | 库代码用 `print` + 打印 traceback 代替 `logging`，真错误与假错误输出无法区分 | 低 | 未修 |
| **U** | `mink_solver.py:120` | `posture_task` target 缺 else 分支，传过一次 `reference_qpos` 后污染所有后续调用 —— 相同输入不同输出 | 中 | **Day 4 已修** |

同时更新缺陷 O 和 H：

- **O**：严重度 **中 → 低**，注明「实测修复前后 IK 解逐位相同；dt 在 `solve_ik` 的一除一乘中约掉，仅在配置了 `VelocityLimit` 时才生效 —— 休眠缺陷」，状态改「已修 + commit」
- **H**：补根因（8 连杆夹爪），标注「待决：`qpos_dim` 语义未定义」

## 8.3 提交（分两个 commit）

**变量隔离原则**：Step 5 和 Step 6 是两件独立的事。

```bash
git add discoverse/universal_manipulation/mink_solver.py
git commit -m "fix(ik): dt 使用配置值而非硬编码，消除变量遮蔽（缺陷 O）

solve_ik:126 的局部 dt = 1e-3 遮蔽了 :50 从配置读取的 self.dt，
9/9 机器人 YAML 声明的 ik_solver.dt: 0.002 全部无效。

实测：修复前后 IK 解【逐位相同】（atol=1e-9，测了 2/5/10/15cm 四个偏移）。
原因是 mink.solve_ik 内部将任务误差除以 dt 得期望速度，
integrate_inplace 又乘以 dt 积分回去 —— 一除一乘，dt 约掉。
dt 仅在配置了 mink.VelocityLimit 时才影响单步位移上限。

因此这是【休眠缺陷】：当前无行为影响，但一旦引入速度限制，
配置写 0.002 实际按 0.001 算，限幅严一倍，而配置文件看起来完全正确。
严重度由中降为低，但仍修复 —— 成本一行且零风险。

未写行为测试：无可观测差异，测了也是永远为真的断言。

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

```bash
git add discoverse/universal_manipulation/mink_solver.py tests/unit/test_mink_solver.py
git commit -m "fix(ik): posture_task 目标不再跨调用泄漏（缺陷 U）

solve_ik:120 只在 reference_qpos is not None 时更新 posture_task
目标，没有 else 分支。传过一次 reference 之后，后续【不传 reference】
的调用会继续沿用它 —— 相同输入得到不同输出。

实测：同一 target/qpos 连续调用三次，第 2 次传 reference，
第 3 次不传，结果第 3 次与第 2 次逐位相同而非回到第 1 次。

修复分两部分，对应两个【独立】契约：
1. 把 set_target_from_configuration 挪出 if 块 —— 消除泄漏。
   原代码那行在 if 内部，不传 reference 时根本不设目标，于是沿用上次。
2. 补 else 分支，恢复到构造时记住的 _default_posture_qpos（key(0).qpos）
   —— 保持原有默认姿态。

⚠️ 第 2 点不是修泄漏：挪出 set_target 之后有没有 else 都不泄漏。
else 决定的是「默认姿态取谁」——
无 else 时 temp_config 保持 mink.Configuration 的默认值 qpos0
（airbot_play 全 0），与 key(0).qpos（home，[0,-1,1.2,1.5708,...]）
差得很远，会影响冗余自由度下的解选择。那是行为变更，不是修复。

⚠️ 计划文档记载的『self.configuration 状态泄漏，需 try/finally』
【实测不成立】—— solve_ik:99 每次入口 configuration.update(current_qpos)
已经隔离了它。两次同参调用解逐位相同。
真正的泄漏在 posture_task，且它没有入口重置保护。

测试：tests/unit/test_mink_solver.py
  - test_repeated_solve_is_deterministic（守 configuration，防有人删掉 :99）
  - test_posture_target_does_not_leak_across_calls（泄漏回归）
  - test_default_posture_target_is_home_not_qpos0（默认姿态回归）

第三条测试来自一次【失败的变异验证】：注释掉 else 后前两条仍全绿，
暴露出「默认姿态是 home」这个契约无人守护。补上后再次变异，
只有第三条转红 —— 精确区分了两个契约。

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

## 8.4 文档收尾

- `docs/log/devil-log-day04.md` —— 过程实录
- `docs/note/devil-note-day04.md` —— 知识拆解
- `docs/checkpoint/checkpoint-day04.md` —— **每条推断标注「已核实 / 待核实」**
- `docs/defect-inventory-day02.md` —— 按 8.2 更新（文件名已不准确，可考虑改为 `defect-inventory.md`）

---

## 本课方法论沉淀

1. **「配置无效」和「配置无效且有害」是两回事。** 判据：如果它生效了，行为会变吗？
2. **休眠缺陷值得记录。** 「条件性不可达」的条件会变；「结构性不可达」才可以忽略。
3. **修 or 不修，比的是「修的成本+风险」和「不修的期望损失」**，不是「现在有没有影响」。
4. **状态泄漏的判据**：调用 N 次后的输出，是否只由第 N 次的输入决定？
5. **修复应当恢复「本来该有的行为」**，而不是顺手改成「我觉得更好的行为」。
6. **「哪里没有反馈，哪里就有缺陷。」** 测试的本质工作是给不会炸的地方装上会炸的机制。
7. **调查的产出可以是「定义问题」而不是「修复问题」。** 语义没共识时，改数字只是换个错误。
8. **先证明，再动手** —— 本课四项调查，计划文档三条推断错了两条。
9. **测试没有可观测差异就不要写。** 永远为真的断言是负债不是资产。
10. **修完必做变异验证**：注释掉修复，测试必须红。
11. **一个缺陷的修复里可能藏着两个独立契约。** 本课是「不泄漏」和「默认值是 home」—— 碰巧由同一段代码实现，但可以被独立破坏。只守一个，另一个就在裸奔。
12. **变异验证「没红」时，先别急着改测试。** 三种可能：测试写错、修复不是你以为的那样、**契约不完整**。本课是第三种 —— 测试是对的，只是漏了一个契约。
13. **绿灯从来不是证据；能对已知的破坏做出反应，才是证据。**

---

## 面试叙事（Day 4 部分）

> 「修完 seed 之后我继续排查 IK 求解器。计划里记着两个问题：`dt` 配置被硬编码遮蔽，以及 `self.configuration` 存在状态泄漏需要 try/finally。
>
> 我没有直接照着改 —— 先各写了一个判定实验。结果两条都和记录的不一样。
>
> `dt` 确实被遮蔽了，9 个机器人的配置全部无效。但我实测发现修复前后 IK 解**逐位相同** —— 因为 mink 内部把误差除以 dt 得速度，积分时又乘回去，dt 约掉了。它只在配置了速度限制时才起作用。所以这是个休眠缺陷：当前零影响，但一旦有人加速度限幅，配置写 0.002 实际按 0.001 算，限幅严一倍而配置看起来完全正确。我仍然修了 —— 一行且零风险 —— 但没有为它写测试，因为没有可观测差异，写了也是永远为真的断言。
>
> `configuration` 泄漏那条则**不成立**：`solve_ik` 每次入口都用 `current_qpos` 覆盖它。但同一次排查发现了真正的泄漏 —— `posture_task` 的目标只在传了 `reference_qpos` 时更新，没有 else 分支。传过一次之后，后续不传的调用会一直沿用它。我用的判据是『调用 N 次后的输出，是否只由第 N 次的输入决定』，实测第三次调用的解跟着第二次走，而不是回到第一次。修完做了变异验证：把 else 分支注释掉，回归测试立刻转红。
>
> 顺带查清了另一个遗留缺陷的根因：4 个机器人的 `qpos_dim` 和 MJCF 的 nq 对不上，iiwa14 差 6。原记录猜是有 FREE 关节，实测是夹爪 8 连杆平行机构，每个连杆占一个 qpos，而 YAML 按两个手指计数。这条我**没有改数字** —— 因为 `qpos_dim` 到底指模型 nq 还是可控自由度，本身没有定义，改之前得先定义。我把 xfail 的 reason 从『原因不明』升级成『根因已知 + 待决策点明确』。
>
> 这一天最大的收获不是修了几个 bug，是**三条被写进交接文档的推断里有两条是错的**。所以我现在的 checkpoint 每条结论都标注『已核实 / 待核实』。」

**面试官在听的是**：你会不会照着文档执行，还是会先验证文档。以及你能不能说清「为什么这个修了那个没修」。
