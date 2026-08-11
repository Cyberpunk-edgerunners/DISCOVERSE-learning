# Day 3 · Step 1 逐行精讲 — 写出会红的确定性测试

> 配套 [day03-04-determinism.md](day03-04-determinism.md) Step 1
> 本文给完整源码 + 每一段的「为什么这么写」
> **读法建议**：先看 §1-§4 想清楚设计，再抄 §6 的代码。直接抄代码你会错过本课 80% 的价值。

---

## 0｜我替你踩过的坑（先看这个，能省你 40 分钟）

我在写这份讲解前，先把整条链路跑通了一遍。有三件事**和计划文档写的不一样**，你必须先知道：

### 坑 A｜MJCF 不是静态文件，是运行时生成的

计划文档让你「加载 place_block 的 MJCF」，但你 `grep` 遍 `place_block.yaml` **找不到任何 xml 路径**。

真相在 [universal_task_runtime.py:405-408](../../examples/universal_tasks/universal_task_runtime.py#L405)：

```python
def generate_robot_task_model(robot_name, task_name):
    xml_path = os.path.join(DISCOVERSE_ASSETS_DIR, "mjcf/tmp", f"{robot_name}_{task_name}.xml")
    make_env(robot_name, task_name, xml_path)   # ← 机器人 XML + 任务场景 XML 在这里被拼起来
    return xml_path
```

**场景是「机器人 × 任务」笛卡尔积拼出来的**，9 机器人 × 5 任务 = 45 个组合不可能预先存 45 个文件。所以 `make_env` 在 `models/mjcf/tmp/` 下现场生成。

> 📌 **知识点：测试要面对「真实的构造路径」**
> 你可以偷懒直接 `from_xml_path("某个手写的xml")`，测试也能跑。但那测的是**你自己造的场景**，不是产品实际用的场景。一旦 `make_env` 的拼接逻辑有 bug，你的测试永远发现不了。
>
> **原则：测试的输入应该尽可能沿用生产代码的构造路径。** 这也是为什么下面的 fixture 要调 `make_env` 而不是硬编码 XML。

### 坑 B｜导入时会打印一条 `ModuleNotFoundError`，但这是正常的

```
ModuleNotFoundError: No module named 'gaussian_renderer'
Warning: gaussian_splatting renderer not found.
```

[simulator.py:22](../../discoverse/envs/simulator.py#L22) 用 try/except 包了 3DGS 渲染器的导入，没装就降级。**这不是错误**，traceback 是被打印出来的不是被抛出的。

> 📌 **知识点：区分「打印的 traceback」和「抛出的异常」**
> 新手最容易被这个吓到，以为环境坏了。判据很简单：**程序继续往下跑了吗？** 跑了就说明异常被 catch 了。
>
> 顺带一提：这种「打印完整 traceback 然后继续」的写法本身是个**可用性缺陷** —— 它让真错误和假错误长得一模一样。可以记进 defect-inventory（低严重度）。

### 坑 C｜⚠️ 最重要 —— `np.random.seed(42)` 在外面设，测试会**绿**

我实测的结果：

| 做法 | 两次结果是否相同 |
|---|---|
| 测试里 `np.random.seed(42)` 后各跑一次 | ✅ **相同**（测试会绿！） |
| 不设 seed 跑两次 | ❌ 不同 |
| **在 config 里设 `settings.seed = 42`** 跑两次 | ❌ **不同** ← 这才是缺陷 |

**这个发现直接决定了测试怎么写。**

如果你按第一种写法（在测试里调 `np.random.seed`），测试会绿 —— 因为 `randomization.py` 用的是全局 `np.random`，你在外面 seed 全局，它当然确定。**但这没有测到任何东西**，因为真实用户是通过 YAML 配 seed 的，而那条路是断的。

> 📌 **知识点：测试必须走用户走的入口**
> 这是 Step 1 最核心的教学点，也是我在 [day03-04-determinism.md](day03-04-determinism.md) 里说「如果它绿了，停下来」的真正原因。
>
> 你要测的**契约**是：「**我在配置文件里写 `seed: 42`，两次运行应该一样**」。
> 不是「numpy 的 PRNG 工作正常」（那是 numpy 的测试该干的事）。
>
> 从错误的入口进去，你测的是别人家的代码。

---

## 1｜先把契约写成一句话

动手写代码前，把要断言的东西写成一句**不含代码的中文**：

> 「对 place_block 任务，**把 `randomization.settings.seed` 设为 42**，
> 执行两次场景随机化，
> 两次结束后 `block_green` 和 `bowl_pink` 的位姿应**逐位完全相同**。」

这句话里每个词都有讲究：

| 词 | 为什么是它 |
|---|---|
| **把 settings.seed 设为 42** | 走用户入口（坑 C） |
| **场景随机化**，不是完整任务 | 不引入物理引擎不确定性（一个测试一个失败原因） |
| **block_green 和 bowl_pink** | 这是 place_block 仅有的 2 个自由体（实测 `free_body_qpos_ids` 确认） |
| **位姿**（7 维）不只是位置 | 姿态也可能被随机化，全测比只测 xyz 强 |
| **逐位完全相同** | PRNG 是确定性算法，理论误差为 0 |

**写不出这句话就不要写代码。** 写得出来，代码只是翻译。

---

## 2｜怎么「设 seed」？—— 这一步会让你卡住，那是设计的

你想设 seed，但：

```python
SceneRandomizer.__init__(self, mj_model, mj_data)   # 没有 seed 参数
```

那 seed 应该从哪进去？看 `exec_randomization` 的第一行（[randomization.py:83](../../discoverse/universal_manipulation/randomization.py#L83)）：

```python
self._current_settings = randomization_config.get('settings', {})
```

**settings 是被读进来的！** 只是 `seed` 这个键没人碰。

所以我们的测试这样设 seed：**改传给 `exec_randomization` 的那个 config 字典**。

```python
config["settings"]["seed"] = 42
```

这是**用户在 YAML 里写 `seed: 42` 之后，加载器加载完的等价效果**。走的是真实入口，但不用改 YAML 文件。

> 📌 **知识点：在「配置对象」层面注入，而不是改配置文件**
> 两种做法的对比：
>
> | | 改 YAML 文件 | 改加载后的 dict |
> |---|---|---|
> | 真实性 | 更真实 | 等价（加载器输出就是 dict） |
> | 副作用 | **污染仓库文件** | 无 |
> | 能否参数化多个 seed | 难 | 容易 |
>
> 选后者。测试**永远不应该修改仓库里的文件** —— 那会让「跑过测试的工作区」和「干净工作区」行为不同，是测试污染的一种。

---

## 3｜怎么保证「两次运行」真的是两次独立运行？

这是最容易写错的地方。**错误写法**：

```python
r = SceneRandomizer(m, d)
r.exec_randomization(cfg)
a = 读位置()
r.exec_randomization(cfg)      # ❌ 在已被随机化过的 d 上继续随机化
b = 读位置()
```

为什么错？看 [randomization.py:238](../../discoverse/universal_manipulation/randomization.py#L238)：

```python
current_z = self.mj_data.qpos[joint_adr + 2]
world_pos[2] = current_z          # z 沿用当前值，不随机
```

第二次跑的时候 `current_z` 已经是第一次的结果了。**状态在两次运行之间泄漏。**

**正确写法**：每次运行都从零开始 —— 新的 `MjData`、新的 `SceneRandomizer`。

```python
def _run_once(seed):
    model = mujoco.MjModel.from_xml_path(xml)   # 或复用 model（只读）
    data  = mujoco.MjData(model)                # 必须新建
    mujoco.mj_resetData(model, data)
    mujoco.mj_forward(model, data)              # 让 site/body 位置生效
    r = SceneRandomizer(model, data)            # 必须新建
    ...
```

> 📌 **知识点：这就是 Day 2 学的 fixture 作用域，换了个场合**
> Day 2 你学过：`MjModel` 可以 session 级（只读、编译贵），`MjData` 必须 function 级（可变状态）。
>
> **今天是同一条原则在函数内部的应用**：一个测试内部的两次「运行」，彼此也必须隔离。
>
> 判断标准永远是那一条：**这个对象是否持有可变状态？** 持有就必须新建。
> - `MjModel` → 只读编译产物 → 可复用
> - `MjData` → qpos/qvel/time → **必须新建**
> - `SceneRandomizer` → 持有 `mj_data` 引用 + `initial_camera_poses` → **必须新建**
>
> ⚠️ 注意 `mj_forward` 那一行不能少：`SceneRandomizer._randomize_objects` 要调 `get_site_tmat(self.mj_data, "armbase")`，而 site 的世界坐标只有在 `mj_forward` 之后才被计算出来。

---

## 4｜为什么要 `deepcopy` 配置？

```python
cfg = copy.deepcopy(base_config)
cfg["settings"]["seed"] = 42
```

因为 `load_task` 这类 fixture 通常是 **session 级缓存的**（看 [test_task_config.py:56](../../tests/unit/test_task_config.py#L56)，它就是）。你直接改它，**后面所有用到这个配置的测试都会看到你改过的版本**。

而且 `exec_randomization` 内部还会往 config 里翻 `settings`，`cameras_config` 那里甚至做了个 `{k: v for ...}` 过滤 —— 你无法保证它不改原字典。

> 📌 **知识点：session 级 fixture 返回可变对象是个陷阱**
> Day 2 你学的是「可变的用 function 级」。但这里 fixture **本身**是 session 级的（缓存加载结果，因为加载要读 YAML + 解析 extends，不便宜）。
>
> 解法有两种：
> 1. fixture 保持 session 级，**用的人负责 deepcopy**（本文选这个）
> 2. 套一层 function 级 fixture，每次返回 deepcopy
>
> 方案 2 更安全（不依赖使用者自觉），方案 1 更省。**Step 4 之后你可以把它重构成方案 2** —— 那是个很好的练习。

---

## 5｜断言怎么写

```python
np.testing.assert_array_equal(first, second)
```

**不用 `assert_allclose`，不给容差。** 理由在主教程 §1.3 讲过：PRNG 是确定性算法，理论误差为 0。

但 `assert_array_equal` 的报错信息不够好用。更好的写法是**先给人看得懂的诊断，再断言**：

```python
if not np.array_equal(first, second):
    diff = np.abs(first - second)
    pytest.fail(
        f"同 seed 两次随机化结果不同，最大偏差 {diff.max():.6f}\n"
        f"  第一次: {first}\n  第二次: {second}"
    )
```

> 📌 **知识点：失败信息的质量决定测试的价值**
> `assert a == b` 失败时你只知道「不相等」。半年后 CI 半夜红了，值班的人看到的就是这条信息。
>
> 好的失败信息回答：**差多少？差在哪一维？期望是什么？**
>
> pytest 的断言重写（assertion rewriting）对简单表达式已经很好了，但对 numpy 数组它只会打印两个大数组。手工构造消息是值得的。

---

## 6｜完整源码

创建 `tests/simulation/__init__.py`（空文件）和下面这个文件。

**每一段我都标了对应上面哪一节**，请对照着看，不要只抄。

```python
"""确定性专项测试：配置里的 seed 是否真的生效。

本文件测的是【契约】而非【实现】：
    用户在 task YAML 里写 randomization.settings.seed: 42
    -> 两次运行应得到完全相同的场景

⚠️ 关键设计（详见 docs/tutorial/day03-step1-walkthrough.md 坑 C）：
   绝不能在测试里调 np.random.seed(42)。
   那样测试会【绿】—— 因为 randomization.py 消费的是全局 np.random，
   在外面 seed 全局当然确定。但真实用户走的是配置文件那条路，
   而那条路是断的。从错误的入口进去，测的是 numpy 不是本项目。
"""
import copy
import os

import mujoco
import numpy as np
import pytest

from discoverse.universal_manipulation.randomization import SceneRandomizer
from discoverse.universal_manipulation.task_config import TaskConfigLoader
from discoverse.universal_manipulation.config_utils import (
    load_and_resolve_config,
    replace_variables,
)

pytestmark = [pytest.mark.determinism, pytest.mark.integration]

ROBOT = "airbot_play"
TASK = "place_block"
# place_block 场景里仅有的两个自由体（实测 free_body_qpos_ids 确认）
FREE_BODIES = ["block_green", "bowl_pink"]


# ---------------------------------------------------------------- fixtures

@pytest.fixture(scope="session")
def task_xml(repo_root):
    """生成 robot x task 的 MJCF，返回路径。

    §0 坑 A：场景不是静态文件，是 make_env 现场拼出来的
    （9 机器人 x 5 任务 = 45 组合，不可能预存）。
    测试走和生产代码相同的构造路径，否则测的是自造场景。

    session 级：make_env 要读多个 XML 并做树合并，不便宜；
    产出是磁盘上的文件，只读复用安全。
    """
    from discoverse.envs.make_env import make_env
    from discoverse import DISCOVERSE_ASSETS_DIR

    xml_path = os.path.join(
        DISCOVERSE_ASSETS_DIR, "mjcf", "tmp", f"{ROBOT}_{TASK}.xml"
    )
    make_env(ROBOT, TASK, xml_path)
    if not os.path.exists(xml_path):
        pytest.skip(f"make_env 未产出 MJCF: {xml_path}")
    return xml_path


@pytest.fixture(scope="session")
def base_randomization_config(task_config_dir):
    """加载 place_block 的随机化配置（已解析 extends）。

    必须用加载器而非直接读 YAML —— Day 2 方法论第 7 条：
    静态读文件 != 运行时加载，extends 会改变最终内容。

    ⚠️ session 级 + 返回可变 dict：使用者必须 deepcopy（见 §4）。
    """
    cfg_path = str(task_config_dir / f"{TASK}.yaml")
    resolved = replace_variables(load_and_resolve_config(cfg_path))
    randomization = TaskConfigLoader.from_dict(resolved).randomization
    assert randomization is not None, f"{TASK} 没有 randomization 段，测试前提不成立"
    return randomization


# ---------------------------------------------------------------- helpers

def _randomize_once(xml_path, config):
    """跑一次完整的场景随机化，返回所有自由体的位姿拼接结果。

    §3：每次调用都新建 MjData 和 SceneRandomizer。
    复用会导致状态泄漏 —— randomization.py:238 的 z 坐标
    沿用 mj_data 当前值，第二次跑就不是从同一起点出发了。

    返回: shape (14,) 的 float64 数组 = 2 个物体 x [x,y,z,qw,qx,qy,qz]
    """
    model = mujoco.MjModel.from_xml_path(xml_path)
    data = mujoco.MjData(model)
    mujoco.mj_resetData(model, data)
    # 必须 forward：_randomize_objects 要读 armbase site 的世界坐标，
    # 而 site 位置只有在前向运动学算过之后才有效。
    mujoco.mj_forward(model, data)

    randomizer = SceneRandomizer(model, data)
    randomizer.exec_randomization(config)

    return np.concatenate([
        np.asarray(randomizer._object_pose(name)).copy() for name in FREE_BODIES
    ])


def _config_with_seed(base_config, seed):
    """返回设好 seed 的配置副本。

    §2：走用户入口 —— 等价于在 YAML 里写 settings.seed: <seed>。
    §4：deepcopy，因为 base_config 是 session 级共享的。
    """
    cfg = copy.deepcopy(base_config)
    cfg.setdefault("settings", {})["seed"] = seed
    return cfg


def _assert_identical(first, second, context):
    """§5：先给人看得懂的诊断，再失败。"""
    if not np.array_equal(first, second):
        diff = np.abs(first - second)
        pytest.fail(
            f"{context}\n"
            f"  最大偏差: {diff.max():.9f}（期望 0，PRNG 是确定性算法）\n"
            f"  第一次:   {np.array2string(first, precision=6)}\n"
            f"  第二次:   {np.array2string(second, precision=6)}"
        )


# ---------------------------------------------------------------- 测试

def test_config_seed_makes_randomization_reproducible(
    task_xml, base_randomization_config
):
    """【核心红灯】配置里的 seed 应让两次随机化结果完全相同。

    当前必然失败：randomization.py 有 25 处裸 np.random.*，
    消费的是进程级全局随机流；settings.seed 声明于 6 处 YAML，
    但整个代码库零个读取者。

    修复方向（Step 4）：SceneRandomizer 接受 seed 参数，
    建 np.random.default_rng(seed) 实例，25 处改用 self.rng.*。
    """
    cfg = _config_with_seed(base_randomization_config, 42)

    first = _randomize_once(task_xml, cfg)
    second = _randomize_once(task_xml, cfg)

    _assert_identical(
        first, second,
        "配置 settings.seed=42，两次随机化结果却不同 —— seed 未被消费"
    )


def test_different_seeds_produce_different_scenes(
    task_xml, base_randomization_config
):
    """【反向哨兵】不同 seed 应得到不同场景。

    为什么需要这条：上一条测试有个平凡解 —— 如果随机化
    根本没执行（config 为 None、物体名写错、randomize 被跳过），
    两次结果自然完全相同，测试会【绿】但什么都没验证。

    这条测试保证「随机化确实在发生」。
    两条一起才构成完整的判据：既确定，又真的随机。

    注意：修复前这条会【偶然通过】（因为全局随机流本就每次不同），
    修复后它才真正在验证 seed 的区分能力。
    """
    a = _randomize_once(task_xml, _config_with_seed(base_randomization_config, 42))
    b = _randomize_once(task_xml, _config_with_seed(base_randomization_config, 1234))

    assert not np.array_equal(a, b), (
        "seed=42 与 seed=1234 得到了完全相同的场景 —— "
        "随机化很可能根本没有执行，上一条测试的绿灯是平凡解"
    )


def test_randomization_actually_moves_objects(task_xml, base_randomization_config):
    """【前提校验】随机化确实改变了物体位置。

    比上一条更基础：确认 exec_randomization 不是空操作。
    如果这条红了，前两条测试的结论全部无意义 —— 先修这个。

    这叫【测试的前提断言】：把「我以为成立的前提」写成可执行的检查。
    """
    cfg = _config_with_seed(base_randomization_config, 42)

    model = mujoco.MjModel.from_xml_path(task_xml)
    data = mujoco.MjData(model)
    mujoco.mj_resetData(model, data)
    mujoco.mj_forward(model, data)
    randomizer = SceneRandomizer(model, data)

    before = np.concatenate([
        np.asarray(randomizer._object_pose(n)).copy() for n in FREE_BODIES
    ])
    randomizer.exec_randomization(cfg)
    after = np.concatenate([
        np.asarray(randomizer._object_pose(n)).copy() for n in FREE_BODIES
    ])

    assert not np.array_equal(before, after), (
        "exec_randomization 执行前后物体位姿完全没变 —— 随机化是空操作"
    )
```

---

## 7｜跑起来

```bash
source scripts/dev/env.sh
$PY -m pytest tests/simulation/ -v
```

### 预期结果

```
test_config_seed_makes_randomization_reproducible   FAILED   ← 目标红灯 ✅
test_different_seeds_produce_different_scenes       PASSED
test_randomization_actually_moves_objects           PASSED
```

**这个组合才是正确的**：
- 第 1 条红 → 缺陷确实存在
- 第 2、3 条绿 → 证明第 1 条的红**不是因为随机化没跑**

> 📌 **知识点：一个红灯需要绿灯来解释**
> 「测试红了」本身信息量不足 —— 可能是被测代码有 bug，也可能是测试前提就不成立（模型没加载、物体名写错、函数根本没被调用）。
>
> 配一组「前提校验」测试，就能把红灯的含义**收窄到唯一解释**。
>
> 这是 Day 2「找独立第二信源」方法论的具体实现。

### 输出很吵？

`exec_randomization` 会打印一堆 emoji 日志，还有 `TEXTURE_1K_PATH not found` 警告。加 `-q` 或者：

```bash
$PY -m pytest tests/simulation/ -v --tb=short 2>&1 | grep -v "⚠️\|✅\|🎯\|📦\|🪑\|🎨\|Warning: TEXTURE"
```

> 📌 **顺带记一条缺陷**：库代码往 stdout 打 emoji 日志、且无法关闭，本身是可用性问题（应该用 `logging` 模块，让调用方决定级别）。记进 defect-inventory，低严重度。

---

## 8｜⚠️ 自检：确认你的红灯是真红

跑完之后**必须做这一步**，否则你不知道自己测对了没有。

### 自检 1｜改 seed 值，第 1 条测试的行为不该变

```python
cfg = _config_with_seed(base_randomization_config, 999)   # 42 -> 999
```

**仍然应该红**。因为 seed 现在根本不起作用，换成什么值都一样。

如果改了 seed 之后测试**变绿了**，说明有东西意外生效了 —— 停下来重新理解代码。

### 自检 2｜临时在测试里加 `np.random.seed(42)`，应该变绿

在 `_randomize_once` 的第一行临时加：

```python
def _randomize_once(xml_path, config):
    np.random.seed(42)      # 临时！自检用！验证完必须删掉！
    ...
```

**第 1 条测试应该变绿。**

这证明了两件事：
1. 你的测试基础设施是对的（能检测到确定性）
2. **缺陷确实在「配置 → 代码」这条链路上**，而不是在别处

⚠️ **验证完立刻删掉这行。** 留着它测试永远是绿的，而且是假绿。

> 📌 **知识点：这就是手工「变异测试」**
> 主教程 §4.3 提过这个概念，这里是它的第一次实战：
>
> **注入一个已知的修复 → 测试应该变绿；撤销 → 应该变红。**
>
> 能对「已知的修复」正确反应的测试，才有资格去验证「未知的修复」。
>
> 很多人写完测试看到红灯就直接去改代码了 —— 但如果测试本身写错了，你会**改一个不存在的问题**，或者改对了却看不到绿灯，然后在正确的修复上反复怀疑自己。

---

## 9｜写进 devil-note 的问题

1. 坑 C 那个表格（三种设 seed 方式，三种结果）说明了什么？用你自己的话写。
2. `_randomize_once` 里为什么必须新建 `MjData` 而不能复用？（提示：randomization.py:238）
3. 第 2、3 条测试如果去掉，第 1 条的红灯会损失什么信息？
4. 自检 2 里临时加 `np.random.seed(42)` 让测试变绿 —— 这说明缺陷在哪一层？

---

## 10｜下一步

红灯确认无误后，回到 [day03-04-determinism.md](day03-04-determinism.md) **Step 2**（画 seed 断链图）。

**先别急着修。** Step 2、Step 3 各有各的教学目的，尤其 Step 3 的缺陷 J 必须在 seed 修复**之前**做完 —— 理由是变量隔离（主教程 §3.1）。
