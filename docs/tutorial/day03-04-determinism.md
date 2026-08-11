# Day 3-4 — 确定性攻坚（TDD 红 → 绿）

> 上接 [day02-pytest-infra.md](day02-pytest-infra.md)
> 本课产出：**三个缺陷的红灯测试 + 修复 + 绿灯**，以及一条能写进简历的完整叙事
> 预计耗时：2 天（Day 3 = Step 0-4，Day 4 = Step 5-8）

---

> ## 📌 执行状态（2026-08-03 更新）
>
> **Step 0-4 已完成**，实测结果与本文写作时的若干预设不符，已在对应章节标注。
>
> | 项 | 计划 | 实际 |
> |---|---|---|
> | 用例 | — | 90 → **110 passed**（+10 xfail） |
> | `randomization.py` 覆盖率 | 目标 50% | **69%** ✅ |
> | `mink_solver.py` | 目标 40% | **46%** ✅（外溢，未直接测） |
> | TOTAL | 目标 45% | **59%** ✅ |
> | commit | — | `8cfbc38` 缺陷 J、`cd09b80` seed 贯穿 |
>
> **三条被推翻的预设**（详见 [checkpoint-day03.md](../checkpoint/checkpoint-day03.md) 第七节）：
> 1. MJCF 不是静态文件，是 `make_env` 运行时拼的 → 见 [day03-step1-walkthrough.md](day03-step1-walkthrough.md) 坑 A
> 2. 缺陷 J 实际是 **12 物体 9 受影响**，非 checkpoint 写的 13/11
> 3. `templates/randomization.yaml` **从未被任何任务 extends**，兼容双键名的理由要重写
>
> **Step 5-8（Day 4）尚未开始。**
>
> 逐步实录见 [devil-log-day03.md](../log/devil-log-day03.md)，知识拆解见 [devil-note-day03.md](../note/devil-note-day03.md)。

---

## 先破除一个错误认知

> ❌ 「确定性就是加一行 `np.random.seed(42)`。」

如果真这么简单，这个项目就不会有 62.5%-75% 的 flake 率了。真正的难点在三层：

| 层 | 问题 | 本课对应 Step |
|---|---|---|
| **配置层** | `seed: null` 声明了 6 处，**没有任何代码读它** | Step 2-4 |
| **传播层** | seed 读到了，怎么送到 25 处裸 `np.random.*`？ | Step 4 |
| **验证层** | 怎么证明「真的确定了」而不是「碰巧两次一样」？ | Step 1、Step 3 |

**第三层最容易被跳过，却最重要。** 一个不会红的确定性测试，和没有测试是一回事 —— 这是 Day 2 方法论第 1 条。

---

## 本课八步法

| Step | 做什么 | 验收标准 | 状态 |
|---|---|---|---|
| 0 | 环境 + 基线确认 | `90 passed, 4 skipped, 9 xfailed` | ✅ |
| 1 | 建 `tests/simulation/`，写**会红的**确定性测试 | ❌ 红灯，且红的原因你能说清 | ✅ 含两次自检 |
| 2 | 顺藤摸瓜定位 seed 断在哪一层 | 能画出断链图 | ✅ 6 声明 / 0 读取 |
| 3 | 先修**缺陷 J**（一行修复，最高性价比） | 红 → 绿 | ✅ `8cfbc38` |
| 4 | 修 seed 贯穿（`np.random.Generator` 注入） | Step 1 的测试转绿 | ✅ `cd09b80` |
| — | —— Day 3 结束 —— | | |
| 5 | 修**缺陷 O**（`dt` 被硬编码遮蔽） | 红 → 绿 | ⬜ |
| 6 | 查 **IK 状态泄漏**（先证明，再决定修不修） | 有结论（可能是"不存在"） | ⬜ |
| 7 | 查缺陷 H 的 iiwa14 根因 | 能解释差 6 从哪来 | ⬜ |
| 8 | 覆盖率复测 + 分两次提交 | `randomization.py` 9% → 目标 50%+ | ⬜ 覆盖率已达 69% |

---

## Step 0｜环境与基线（5 分钟，不要跳）

### 你要做的

```bash
cd /home/ubuntu22/workspaces/airbot-play/DISCOVERSE
source scripts/dev/env.sh
$PY -m pytest tests/ -q | tail -3
```

**预期**：`90 passed, 4 skipped, 9 xfailed`

### 为什么这么做

**在改任何代码前，先确认基线是绿的。** 否则等你改完代码跑出 3 个失败，你分不清是「我改坏的」还是「本来就坏的」。

这不是形式主义。Day 2 的坑 4 就是这个问题的变体：5 个测试同时失败，你要有**独立第二信源**才能判断是代码错还是测试错。基线快照就是这个第二信源。

> 📌 **知识点：基线（baseline）**
> 测试工程里「基线」= 已知良好状态的快照。所有的「变好/变坏」判断都相对基线而言。没有基线的 CI 只能告诉你「现在有 3 个失败」，有基线的 CI 能告诉你「**你这次提交新增了 3 个失败**」—— 后者才可行动。

---

## Step 1｜写会红的确定性测试（40 分钟）⭐ 本课最重要

### 1.1 先想清楚：我们要断言什么？

在动手前，请你先回答（写在纸上或 devil-note 里）：

> **「同一个 seed 跑两次，什么东西应该完全相同？」**

候选答案：
- A. 最终任务成功/失败
- B. 每一帧的 `qpos` 数组
- C. 随机化之后、仿真开始之前的物体初始位置

**建议选 C。** 理由：

| 选项 | 问题 |
|---|---|
| A | 粒度太粗。成功率相同不代表轨迹相同；而且要跑完整任务，单次几十秒 |
| B | 粒度对，但**引入了物理引擎的不确定性**。测试红了你分不清是 seed 问题还是 MuJoCo 浮点问题 |
| C | ✅ 粒度刚好。纯 Python 随机数问题，**不涉及物理步进**，毫秒级，红了原因唯一 |

> 📌 **知识点：测试的「隔离性」**
> 好测试只有**一个**失败原因。选 B 会让测试同时承担「seed 是否生效」和「物理引擎是否确定」两个职责 —— 一旦红了，你要先花半小时判断是哪一个。这在测试设计里叫**职责混淆**。
>
> 后面 Day 5 做 flake 分析时你会再遇到这个概念：**能分桶的失败才有价值**。

### 1.2 你要做的

先建目录（注意 `__init__.py`，Day 2 已经解释过为什么需要）：

```bash
mkdir -p tests/simulation
touch tests/simulation/__init__.py
```

然后创建 `tests/simulation/test_determinism.py`。**先自己写**，写不出来再看下面的骨架：

```python
"""确定性专项测试：同 seed → 同结果。"""
import numpy as np
import pytest

pytestmark = pytest.mark.determinism   # 整个文件打 determinism marker


def test_same_seed_produces_same_object_positions(...):
    """同一 seed 随机化两次，物体初始位置应逐位相同。"""
    # 1. 加载 place_block 任务配置
    # 2. 设 settings.seed = 42
    # 3. 建 SceneRandomizer，跑 exec_randomization，记录物体 qpos
    # 4. 重置模型，用同样的 seed 再跑一次，记录
    # 5. np.testing.assert_allclose(第一次, 第二次, rtol=0, atol=0)
```

**关键提示**：
- `SceneRandomizer` 的构造签名目前是 `(mj_model, mj_data)` —— **没有 seed 参数**，这正是我们要发现的事
- 「设 seed」这一步现在**无处可设**。这个「写不下去」的体验本身就是发现
- 读物体位置：`randomizer._object_pose(body_name)` 返回 7 维 `[x,y,z,qw,qx,qy,qz]`
- 用哪个 MJCF：`grep -n "mjcf\|scene" discoverse/configs/tasks/place_block.yaml` 自己找

**遇到卡壳时先问自己**：「我卡住是因为不会写 Python，还是因为**代码根本没提供这个能力**？」后者就是缺陷本身。

### 1.3 `rtol=0, atol=0` 是什么意思

计划文档里原话写的是 `rtol=1e-5`。**我建议你改成严格相等**，理由：

伪随机数生成器（PRNG）是**确定性算法** —— 同 seed 同状态必然产出**逐比特相同**的 float64。这里没有浮点累积误差的余地。允许 1e-5 容差等于说「差一点点也算对」，而在这个场景里，**差一点点只可能是 seed 没生效**。

> 📌 **知识点：容差该给多少**
> 判据不是「差多少算能接受」，而是「**理论上应该差多少**」：
> - 纯 PRNG 复现 → 理论差 0 → `atol=0`
> - 浮点物理累积 1000 步 → 理论有误差 → 给 `rtol=1e-9` 量级
> - 神经网络在不同 GPU 上 → 理论差更大 → `rtol=1e-3`
>
> **给宽容差是在掩盖你不理解误差来源。** 这是数值测试最常见的偷懒。

### 1.4 验收

```bash
$PY -m pytest tests/simulation/ -v
```

**必须是红的。** 而且你要能一句话说清红的原因。如果它绿了，**停下来** —— 大概率是你的测试根本没在测你以为的东西（比如两次都用了同一个 `mj_data` 对象，第二次的"随机化"落在了同样的位置上，或者根本没跑到断言）。

**自检手段**：把 seed 从 42 改成 43，测试的行为应该**不变**（因为现在 seed 根本不起作用）。如果改 seed 会让结果变，说明 seed 意外生效了 —— 那你要重新理解代码。

---

## Step 2｜定位 seed 断在哪一层（30 分钟）

### 2.1 你要做的

自己执行这三条命令，**在 devil-note 里画出断链图**：

```bash
# 谁声明了 seed？
grep -rn "seed" discoverse/configs/tasks/*.yaml discoverse/configs/tasks/templates/*.yaml

# 谁读了 seed？
grep -rn "seed" --include=*.py discoverse/ examples/universal_tasks/ | grep -v __pycache__

# 有多少处裸随机？
grep -cn "np\.random\." discoverse/universal_manipulation/randomization.py
grep -rn "random\." --include=*.py discoverse/utils/__init__.py
```

### 2.2 你应该看到的结论

我已经实测过（你要自己复现一遍确认）：

```
配置层：  6 处声明 seed: null
          ↓
          ✂️ 断在这里 —— 零个 Python 文件读取它
          ↓
代码层：  randomization.py 25 处裸 np.random.*
          utils/__init__.py:86 另有 stdlib random.choice（贴图路径，独立随机源）
```

> 📌 **知识点：「未消费的配置」是一类独立缺陷模式**
> 它比「配置写错」更隐蔽：配置写错通常会炸或行为异常；配置**没人读**则表现为**改配置完全没反应**。使用者会以为「我设了 seed 但还是不复现，一定是仿真本身不确定」—— **缺陷成功伪装成了固有属性**。
>
> Day 2 的缺陷 J（`collision_radius`）、缺陷 O（`dt`）是同一模式的不同变体。defect-inventory 第七节把这个模式总结为「**静默的空集合与未消费的配置**」，值得重读。

### 2.3 关键判断：`utils/__init__.py:86` 那条要不要管？

**要。** 而且这是本 Step 最有价值的发现。

贴图随机化走的是 stdlib `random` 模块，**不是** numpy。这意味着即使你把 `randomization.py` 里 25 处全改成 `self.rng.*`，贴图仍然不确定。

> 📌 **知识点：多随机源问题**
> 一个进程里可以有多个互不相干的随机源：`random`（stdlib）、`np.random`（全局单例）、`np.random.Generator`（实例）、`torch.manual_seed`、CUDA 的 cuDNN 非确定算子…… **seed 一个不等于 seed 全部。**
>
> 这是 ML 复现性的经典坑。PyTorch 官方复现指南要求同时设 4 处 seed，即便如此仍不保证跨 GPU 一致。
>
> **测试开发的启示**：验证确定性时，不要只测你改过的那条路径。要问「**还有哪些随机源我没看见**」。

---

## Step 3｜先修缺陷 J（40 分钟）—— 为什么插队

### 3.1 为什么先做这个

按 checkpoint 的排序，seed 是最高优先。但我建议**先修缺陷 J**：

| 维度 | 缺陷 J | seed 贯穿 |
|---|---|---|
| 修复成本 | **一行** | 改 25 处 + 改构造签名 + 改调用方 |
| 影响面 | **12 物体中 9 个**避让半径失效 | 不可复现 |
| 与本课关系 | **它会污染 Step 4 的验证** | — |

> ⚠️ **实测修正**：checkpoint-day02 记的是「13 物体 11 受影响」，**实测是 12/9**（另 3 个声明值恰好就是 0.05）。用实测数字，不要用 checkpoint 的。

最后一行是关键。缺陷 J 让碰撞检测半径全部塌到 0.05，`_randomize_objects` 的重试次数因此变少。你在 Step 4 修完 seed 后跑测试，看到的行为是「seed 已修 + J 未修」的**叠加结果**。

> 📌 **知识点：修复顺序应该按「相互干扰」排，不只按严重度**
> 两个缺陷同时在场时，一个的修复效果会被另一个掩盖。工程上叫**变量隔离** —— 每次只改一个变量，才能归因。
>
> 这也是为什么本课要求**分两次 commit**（Step 8）：`git bisect` 只有在一个 commit 做一件事时才有用。

### 3.2 你要做的

**先写测试，再改代码。** 顺序不能反。

在 `tests/unit/test_task_config.py` 或新建 `tests/unit/test_randomization_config.py` 里，写一个测试断言：

> 对每个任务的每个物体，**碰撞检测实际用到的半径 == YAML 里声明的半径**

关键难点：怎么拿到「实际用到的半径」？`randomization.py:184` 那行是函数内部的局部变量，测试拿不到。

**给你三条路，自己选一条并说明理由**：

| 方案 | 做法 | 代价 |
|---|---|---|
| A | 测「配置字典里 `min_distance` 键存在」 | 弱 —— 测的是实现细节不是行为 |
| B | monkeypatch `_check_collision_2d`，捕获传入的 radius | 中 —— 能测真实调用链 |
| C | 把「取半径」抽成一个可测的小函数 `_get_collision_radius(obj_config)` | 需要改生产代码，但**最可测** |

我倾向 **C**。理由：缺陷 J 的根因是「取值逻辑藏在循环体内部，无法独立验证」。把它提取成命名函数，既修了缺陷，又让它**从此可测**。

> 📌 **知识点：为可测性重构（Design for Testability）**
> 当你发现「这段逻辑没法测」时，往往不是测试技术不够，而是**代码结构本身有问题** —— 一段有独立业务含义的逻辑（「决定用哪个半径」）被埋在了循环里。
>
> 提取它不是为了测试而牺牲设计，**恰恰是测试暴露了设计缺陷**。这是 TDD 最被低估的收益：测试驱动出的代码结构通常更好。
>
> 反面教材：为了测试把 private 方法改成 public、或大量使用 mock 去戳内部状态 —— 那是在**迁就**坏结构。

### 3.3 修复

一行修复是：

```python
radius = obj_config.get('collision_radius', obj_config.get('min_distance', 0.05))
```

**但请你先想 30 秒**：为什么是「兼容两个键名」而不是「把代码改成读 `collision_radius`」或「把 YAML 全改成 `min_distance`」？

<details>
<summary>想完再展开</summary>

⚠️ **这一段我最初给的理由是错的，实测推翻了它 —— 保留原文以展示"先证明再下结论"的过程。**

**我原来的说法**：「模板里 6 处 `min_distance`，任务 YAML 里 13 处 `collision_radius`，两边都是真实存在的用户，只改一边会破坏另一边。」

**实测**：

```bash
grep -rn "randomization.yaml" --include=*.py --include=*.yaml discoverse/ examples/
# 唯一结果：randomization.yaml:137:# extends: "templates/randomization.yaml"  ← 它自己的注释
```

**`templates/randomization.yaml` 从未被任何任务 extends。** 它是一份纯文档性质的模板，从未被加载过。

| | 声明数 | 实际被加载 |
|---|---|---|
| `collision_radius`（任务 YAML） | 12 处 | ✅ 全部 |
| `min_distance`（模板） | 6 处 | ❌ 零 |

**兼容两个键名仍然是对的做法，但理由变了** —— 不是「保护现有用户」，是「**保护未来照模板抄的人**」。模板是给人抄的，只认新键名的话，照抄的人会掉进同一个坑。

**同时要更新模板本身**，把那 6 处改成 `collision_radius`。修缺陷分两层：**修表现，和修「缺陷的来源」。** 只做第一层，同样的 bug 会再长出来。

**顺带**：因此**不需要**加 `DeprecationWarning` —— 发警告的对象根本不存在，加了只是噪音。

</details>

### 3.4 验收

```bash
$PY -m pytest tests/unit/ -q       # 新测试转绿，其余 90 个不许变红
```

**「其余不许变红」比「新测试变绿」更重要。** 前者叫回归验证。

---

## Step 4｜seed 贯穿（90 分钟）⭐ 本课核心

### 4.1 设计决策：`np.random.seed()` 还是 `Generator`？

**先自己选，再看解析。**

```python
# 方案 A：全局种子
np.random.seed(seed)
# ... 代码里继续用 np.random.uniform(...)

# 方案 B：Generator 实例
self.rng = np.random.default_rng(seed)
# ... 代码里改用 self.rng.uniform(...)
```

<details>
<summary>解析</summary>

**选 B。** 三个理由：

1. **全局状态是共享的**。`np.random.seed()` 修改的是进程级全局单例。你的 randomizer seed 完后，任何第三方库（mujoco 的某个工具、matplotlib、mink）调一次 `np.random.*` 都会推进这个状态，导致你的下一次调用结果改变。**你无法控制谁在消费全局随机流。**

2. **测试并行会互相污染**。你已经装了 `pytest-xdist`（Day 2 记录）。多个测试同时跑，全局 seed 会被互相覆盖 —— 典型的「单跑绿、`-n 8` 跑红」。这和 Day 2 学的 fixture 作用域是**同一个道理**：可变的共享状态必须隔离。

3. **NumPy 官方已弃用 `np.random.seed()` 的推荐地位**。NEP 19 明确建议新代码用 `Generator`。`RandomState`（旧 API）保留只为向后兼容。

**代价**：25 处调用都要改，且 API 有细微差异 —— `np.random.random(3)` → `self.rng.random(3)`，`np.random.rand(n)` → `self.rng.random(n)`（`rand` 在 Generator 上**不存在**）。

</details>

> 📌 **知识点：全局可变状态是测试的头号敌人**
> 这条会在你整个职业生涯里反复出现：全局单例、模块级缓存、环境变量、单例数据库连接。它们的共同特征是**测试之间会互相看见对方的修改**，而修改顺序取决于测试执行顺序 —— 于是你得到「换个顺序就不复现」的 bug。
>
> Day 2 你已经踩过一次（fixture 作用域），今天是第二次（全局 PRNG），Day 10-11 写 CI 时还会遇到第三次（并行 job 共用临时目录）。

### 4.2 你要做的

分四小步，**每步跑一次测试**：

**4.2.1** 改 `SceneRandomizer.__init__` 签名，加 `seed: Optional[int] = None`，建 `self.rng = np.random.default_rng(seed)`

> 思考题：为什么默认值是 `None` 而不是 `0` 或 `42`？
> <details><summary>答案</summary>`default_rng(None)` 表示从操作系统熵源取种 —— 即保持「不指定就随机」的原有行为。给个固定默认值会让**所有不传 seed 的用户突然变成同一个固定序列**，这是行为破坏。<br><br>**通用原则：新增可选参数的默认值，必须等价于旧行为。**</details>

**4.2.2** 把 25 处 `np.random.*` 改成 `self.rng.*`

```bash
# 改完后自查，应该输出 0
grep -c "np\.random\." discoverse/universal_manipulation/randomization.py
```

⚠️ 注意 `np.random.rand(n)` → `self.rng.random(n)`，`np.random.randint` → `self.rng.integers`（**注意 `integers` 的 high 是开区间，`randint` 也是开区间，这里一致；但 `Generator.integers` 有 `endpoint` 参数**）。逐个改完跑一次 `$PY -c "import discoverse.universal_manipulation.randomization"` 确认没有 AttributeError。

**4.2.3** 打通配置 → 构造的链路。`task_base.py:53` 现在写的是：

```python
self.randomizer = SceneRandomizer(self.mj_model, self.mj_data)
```

seed 在 `self.task_config.randomization['settings']['seed']` 里。你要把它取出来传进去。

> 思考题：`randomization` 可能是 `None`，`settings` 可能不存在，`seed` 可能是 `null`。这三层怎么安全取？
> 提示：Day 2 缺陷 C 教过 `.get(k, default)` 的陷阱 —— **键存在但值为 `None` 时它返回 `None`，不是 default**。

**4.2.4** 处理 `utils/__init__.py:86` 的 stdlib `random`（贴图随机源）

这条独立路径你有两个选择：修，或者**明确记录为已知限制并写一个 xfail 测试**。两者都可接受 —— 但「没注意到」不可接受。

> 📌 **知识点：`xfail` 是一种诚实**
> Day 2 方法论第 8 条已经讲过 xfail vs skip。这里补一条：**当你决定暂不修某个缺陷时，写一个 `xfail(strict=True)` 测试是最负责任的做法** —— 它把「我知道但没修」变成了代码库里的**可执行文档**，而且一旦别人修好了，XPASS 会强制有人回来清理标记。
>
> 对比「写在 TODO 注释里」：注释不会被执行，三个月后没人知道它还成不成立。

### 4.3 验收

```bash
$PY -m pytest tests/simulation/ -v      # Step 1 的红灯 → 绿灯 ✅
$PY -m pytest tests/ -q                 # 91+ passed，原有 90 个不许红
```

**然后做一件事**：把测试里的 seed 从 42 改成 43，确认结果**变了**。

> 为什么要做这一步？因为「两次结果相同」有一个平凡解：**随机化根本没跑**。如果 `randomization_config` 是 `None`，`randomize_scene` 直接 `return`，两次自然完全相同 —— 你的测试会绿，但什么都没验证。
>
> 📌 **知识点：变异测试（Mutation Testing）的思想**
> 「改一个应该影响结果的输入，测试行为必须改变」—— 这是验证测试有效性的通用手段。手工版就是：**故意破坏一处，看测试红不红**。红不了的测试是摆设。
>
> Day 2 方法论第 1 条「新写的断言必须亲手让它红一次」是同一件事的入门版。

---

## —— Day 3 结束，写 devil-note ——

Day 3 收尾请回答（写进 `docs/note/devil-note-day03.md`）：

1. seed 断链图（配置 6 处 → 0 个读取者 → 25 处裸随机 + 1 处 stdlib）
2. 为什么选 `Generator` 而不是 `np.random.seed()`（三个理由默写）
3. 缺陷 J 插队修复的理由（变量隔离）
4. 今天哪个「我以为对的假设」被实测推翻了？

---

## Step 5｜缺陷 O：`dt` 被硬编码遮蔽（30 分钟）

### 5.1 现象

[mink_solver.py:50](../../discoverse/universal_manipulation/mink_solver.py#L50) 读了配置：

```python
self.dt = self.solver_config.get('dt', 2e-3)
```

[mink_solver.py:126](../../discoverse/universal_manipulation/mink_solver.py#L126) 在 `solve_ik` 里又定义了一个局部变量：

```python
dt = 1e-3
```

后面第 136、142 行用的都是**局部的 `dt`**，`self.dt` 从未被使用。

### 5.2 你要做的

写一个测试证明它。**思考：怎么在不跑 IK 的情况下证明 `self.dt` 无效？**

<details>
<summary>提示</summary>

最直接的方式是**静态断言 + 行为断言**两条：
- 静态：`assert solver.dt == config里的值` —— 这条会**绿**（`self.dt` 确实被正确赋值了）
- 行为：改配置里的 `dt`，IK 迭代结果应该变 —— 这条会**红**

这个对比本身就是本 Step 的教学点。

</details>

> 📌 **知识点：变量遮蔽（shadowing）**
> `dt = 1e-3` 在函数作用域内创建了一个新名字，与 `self.dt` 毫无关系。Python 不会警告 —— 这是合法代码。
>
> 更隐蔽的是：`self.dt` **仍然被正确赋值了**，任何检查 `solver.dt` 的测试都会通过。**属性存在且值正确 ≠ 属性被使用。**
>
> 这解释了为什么静态检查工具（linter）抓不到它：`self.dt` 有写无读，但类属性的「无人读取」几乎不可能静态判定（可能被子类或外部代码读）。
>
> **测试开发的启示**：断言「配置被正确加载」是不够的，要断言「**配置改变导致行为改变**」。前者测的是 getter，后者测的是契约。

### 5.3 修复

删掉 `dt = 1e-3`，把 136、142 行改成 `self.dt`。

⚠️ **但这会改变现有行为**：默认从 1e-3 变成配置里的值（或 2e-3）。请你先查一下各机器人 YAML 里的 `ik_solver.dt` 实际写了什么：

```bash
grep -A2 -rn "ik_solver" discoverse/configs/robots/*.yaml | grep dt
```

如果配置值与 1e-3 差很多，修完 IK 收敛行为会变 —— 你需要在 devil-note 里记录这个**行为变更**，而不是当作纯 bugfix 悄悄合并。

> 📌 **知识点：bugfix 也可能是 breaking change**
> 「修复」意味着行为改变。如果有人（无意中）依赖了错误行为 —— 比如某个机器人的 IK 参数是在 `dt=1e-3` 下调优的 —— 那么"修复"会让它变差。
>
> 正确做法不是不修，而是**修 + 明确记录 + 验证受影响范围**。这是缺陷报告里「影响分析」章节存在的意义。

---

## Step 6｜IK 状态泄漏：先证明，再决定修不修（60 分钟）

### 6.1 这一步的真正教学目的

计划文档断言 `mink_solver` 有「状态泄漏」，需要 `try/finally` 恢复 `self.configuration`。

**但 Day 2 已经教过一次教训**：checkpoint 里带了两天的「最高优先线索」，一条 `sed -n '165,167p'` 就证伪了。

所以本 Step 的第一要务不是修，是**验证这个断言是否成立**。

### 6.2 你要做的

先读 [mink_solver.py:96-161](../../discoverse/universal_manipulation/mink_solver.py#L96)，回答：

1. `solve_ik` 每次入口第 99 行做了什么？（`self.configuration.update(current_qpos)`）
2. 既然每次入口都用 `current_qpos` 重置，上一次的残留还能影响这一次吗？
3. 那么「状态泄漏」这个说法，成立还是不成立？

**然后写一个测试来判定**，不要靠读代码下结论：

> 用同样的 `target_pos / target_ori / current_qpos` 连续调用 `solve_ik` 两次，两次的 `solution` 应完全相同。

如果绿 → 断言不成立（`update()` 已经隔离了状态）
如果红 → 断言成立，去修

### 6.3 无论结果如何，你要注意的第二个泄漏点

看 [mink_solver.py:120-123](../../discoverse/universal_manipulation/mink_solver.py#L120)：

```python
if reference_qpos is not None:
    temp_config = mink.Configuration(self.mj_model)
    temp_config.update(reference_qpos)
    self.posture_task.set_target_from_configuration(temp_config)
```

**`posture_task` 的目标被修改了，而且没有被恢复。** 下一次调用如果 `reference_qpos=None`，会沿用上一次设的目标。

**这才是真正的状态泄漏。** 而且和 `self.configuration` 不同，它没有「每次入口重置」的保护。

> 📌 **知识点：状态泄漏的判定标准**
> 判据不是「对象有可变字段」，而是：
> **「调用 N 次后的输出，是否只由第 N 次的输入决定？」**
>
> 如果否，就是泄漏。用这个判据重新审视：
> - `self.configuration` → 每次入口被 `current_qpos` 覆盖 → **不泄漏**
> - `self.posture_task` 的 target → 只在 `reference_qpos is not None` 时更新，否则沿用 → **泄漏**
>
> **这是纯函数（pure function）思想的实用版本**：给定相同输入，必得相同输出。测试开发对纯函数最友好，而对有隐藏状态的对象最头疼。

### 6.4 时间盒

计划文档写着「**不要在一个问题上卡超过 4 小时**」。这一步给 60 分钟。到点了没结论就：
1. 在 devil-note 记录你查到哪一步、卡在什么地方
2. 写一个 `xfail` 测试标记未解决
3. 继续 Step 7

> 📌 **知识点：时间盒（timeboxing）**
> 调试的边际收益随时间递减，但沉没成本会让你越陷越深（「都查两小时了，肯定快出结果了」）。时间盒是对抗沉没成本谬误的机械手段。
>
> 更重要的是：**卡住的记录本身有价值**。「我花了 60 分钟没能确定 X，卡在 Y」是一条真实信息，比「跳过没提」强得多。

---

## Step 7｜缺陷 H：iiwa14 的 nq 差 6（30 分钟）

### 7.1 你要做的

checkpoint 第三节给了现成命令，自己跑：

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

### 7.2 怎么读结果

你要找的是：**多出来的 6 个 qpos 是从哪些关节来的**。

三种可能的解释：
- 有一个 `FREE` 关节（占 7 个 qpos）→ 场景里有自由物体被算进模型
- 有 6 个额外的 `HINGE`/`SLIDE` → 夹爪建模比 YAML 假设的复杂
- 别的

⚠️ **注意**：checkpoint 里 `TYPE` 字典把 `mjJNT_FREE=0, BALL=1, SLIDE=2, HINGE=3` —— 请你**自己核对 MuJoCo 的枚举值**再信这个映射。

```bash
$PY -c "import mujoco; print({e.name: e.value for e in mujoco.mjtJoint})"
```

> 📌 **知识点：为什么这条缺陷值得追**
> checkpoint 第三节有一段极精彩的分析，请重读：
>
> > `ctrl_dim` vs `nu` 是 9/9 全对，`qpos_dim` vs `nq` 是 4/9 错。
> > 写错 `ctrl_dim` → 立刻 `ValueError`；写错 `qpos_dim` → `qpos[:9]` 在 `nq=15` 上**完全合法**，静默丢掉后 6 个关节。
> > **会炸的字段维护得好，不会炸的字段积累错误。**
>
> 这个观察可以推广成一条测试开发的世界观：
> **「哪里没有反馈，哪里就有缺陷。」**
>
> 测试的本质工作就是**给那些原本不会炸的地方装上会炸的机制**。这句话可以直接用在面试回答里。

---

## Step 8｜覆盖率复测与提交（40 分钟）

### 8.1 复测

```bash
$PY -m pytest tests/ --cov --cov-report=term-missing -q | tail -20
```

对比 Day 2 基线：

| 模块 | Day 2 | Day 3-4 目标 |
|---|---|---|
| `randomization.py` | 9% | 50%+ |
| `mink_solver.py` | 19% | 40%+ |
| TOTAL | 30% | 45%+ |

**目标没达到不要慌**，也**不要为了刷数字写无意义的测试**。Day 2 方法论第 10 条：覆盖率是下限指标，看 Missing 那列找盲区，不要盯总百分比。

### 8.2 提交

**分两个 commit**（这是 Step 3.1 讲的变量隔离在版本控制上的体现）：

```
fix(randomization): 兼容 collision_radius 键名，修复 11/13 物体避让半径失效（缺陷 J）
fix(randomization): seed 贯穿随机化流程，改用 np.random.Generator 实例
```

第二个 commit 的 message body 里写清楚：
- 为什么用 `Generator` 而非全局 seed
- `utils/__init__.py:86` 的 stdlib random 是否已处理
- 行为变更：默认行为不变（`default_rng(None)`）

> 📌 **知识点：commit message 是给未来的你写的**
> 半年后 `git blame` 到这一行，你只会看到 commit message。「fix bug」等于没写。
>
> 好的 body 回答三个问题：**为什么改**（不是改了什么，diff 已经说了）、**考虑过什么替代方案**、**有什么行为变更**。

### 8.3 更新文档

- `docs/note/devil-note-day03.md` / `devil-note-day04.md`
- `docs/checkpoint/checkpoint-day04.md` —— **每条推断标注「已核实 / 待核实」**（Day 2 教训）
- `docs/defect-inventory-day02.md` 里 J / O 的状态改成「已修复 + commit hash」

---

## 本课方法论沉淀（预填，你自己补充）

1. **测试只能有一个失败原因。** 选「随机化后的初始位置」而非「完整轨迹」，是为了不让物理引擎的不确定性混进来。
2. **容差的判据是「理论上应该差多少」**，不是「差多少我能接受」。PRNG 复现该给 `atol=0`。
3. **未消费的配置是独立缺陷模式**，比配置写错更隐蔽 —— 它把缺陷伪装成系统固有属性。
4. **seed 一个不等于 seed 全部。** 多随机源问题在 ML 项目里普遍存在。
5. **修复顺序按「相互干扰」排，不只按严重度。** 两个缺陷同时在场时无法归因。
6. **新增可选参数的默认值必须等价于旧行为。**
7. **改一个应该影响结果的输入，测试行为必须改变**（手工变异测试）。绿灯有平凡解。
8. **属性存在且值正确 ≠ 属性被使用。** 要断言「配置改变导致行为改变」。
9. **状态泄漏的判据**：调用 N 次后的输出，是否只由第 N 次输入决定。
10. **「哪里没有反馈，哪里就有缺陷」** —— 会炸的字段维护得好，不会炸的字段积累错误。
11. **先证明，再修。** Day 2 那条带了两天的假设，一条命令就证伪了。

**Day 3 实测后补充的（完整 19 条见 [devil-note-day03.md](../note/devil-note-day03.md)）：**

12. **测试必须走用户走的入口。** 在测试里 `np.random.seed(42)` 会让测试变绿，但那测的是 numpy 不是本项目 —— 真实用户走的是 YAML 那条路。
13. **一个红灯需要绿灯来解释。** 单看「同 seed 结果不同」的红，分不清是「seed 没生效」还是「随机化压根没跑」。配前提校验测试才能收窄到唯一解释。
14. **测试金字塔最容易漏的是「接线」。** 变异测试实测：注入「task_base 不传 seed」时，**只有接线测试红**，其他三条全绿。
15. **随机性会从 import 边界溜走。** 确定性的边界不是「我改过的文件」，而是整条调用链。
16. **批量替换会作用于「我刚写的新代码」。** `sed -i` 误伤了五分钟前加的 `self.rng = np.random.default_rng(seed)`。敢用它的唯一理由是代码已 commit。
17. **覆盖率会外溢，但外溢的质量低。** `mink_solver.py` 涨到 46% 而我们一行都没测它 —— 代码被执行过 ≠ 行为被验证过。

---

## 面试叙事（Day 4 结束后你应该能这样讲）

> 「place_block 任务成功率 62.5%-75% 且不可复现。我先做了链路排查：配置文件里 6 处声明了 `seed`，但整个代码库**零个读取者**，同时 `randomization.py` 有 25 处裸 `np.random.*` 调用直接消费全局随机流，另有一条走 stdlib `random` 的贴图路径。
>
> 我先写了一条确定性红灯测试 —— 刻意选「随机化后的物体初始位置」而不是完整轨迹作为断言对象，因为后者会把物理引擎的浮点不确定性混进来，测试红了无法归因。容差给的是 `atol=0`，因为 PRNG 是确定性算法，理论误差就是 0。
>
> 修复时我选了 `np.random.Generator` 实例注入而非 `np.random.seed()` 全局种子，理由是全局状态在 pytest-xdist 并行下会互相污染，而且我无法控制第三方库是否消费全局随机流。
>
> 过程中还发现了一个会干扰验证的缺陷：碰撞避让半径的键名不匹配（代码读 `min_distance`，配置写 `collision_radius`），导致 12 个物体里 9 个的避让半径静默塌到默认值 0.05 —— 碗和盘子这类容器受影响最重（0.12 塌到 0.05，缩小 2.4 倍），方块可能直接生成在碗里，任务开局即失败。我把它排在 seed 修复之前做，因为两个缺陷同时在场时无法归因。
>
> 最终 `randomization.py` 覆盖率从 9% 提到 69%，整体 30% 到 59%，确定性测试稳定通过。
>
> 我还做了变异测试验证测试本身有效：注入三种真实的修复失误 —— 忘了用 seed、忘了在调用方接线、seed 被写死 —— 结果后两种**各自只有一条测试能抓到**。这证明了那四条测试缺一不可，而不是我写多了。
>
> 收尾时发现了一个新缺陷：贴图随机化走的是另一个模块的函数，两个分支分别用 stdlib `random` 和 numpy 全局流，都逃出了我的 rng 管控 —— **随机性是从 import 边界溜走的**。它超出了本次修复范围，我用 `xfail(strict=True)` 标记，这样一旦有人修好，XPASS 会报为失败，强制有人回来清理，不会静默遗留。」

**注意这段叙事的结构**：现象 → 排查方法 → **测试设计的取舍理由** → 修复方案的**技术选型理由** → 意外发现 → **顺序决策的理由** → 结果 + 有效性验证。

面试官真正在听的是**中间那些「为什么这样选」**，不是结果数字。
