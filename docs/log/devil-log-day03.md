# Devil Log · Day 3 — 过程实录

> 2026-08-03 ｜分支 `feat/test-infra`
> 这份是**踩坑实录**，按时间顺序。知识拆解见 [devil-note-day03.md](../note/devil-note-day03.md)。

---

## 时间线概览

| 阶段 | 事件 | 结果 |
|---|---|---|
| Step 0 | 基线确认 | 90 passed / 4 skipped / 9 xfailed |
| Step 1 | 写确定性红灯测试 | **1 failed, 2 passed** —— 目标红灯 |
| 自检 1 | seed 42 → 999 | 仍红 ✅ |
| 自检 2 | 注入 `np.random.seed(42)` | **红绿对调**，意外收获 |
| Step 2 | grep 供需两端 | **6 处声明 / 0 个读取者** |
| Step 3 | 修缺陷 J（键名不匹配） | 16 新用例，`8cfbc38` |
| Step 4.1-4.2 | 加 seed 参数 + 25 处替换 | **sed 误伤自己刚写的代码** |
| Step 4.3 | task_base 接线 | 我的验证脚本先写错了一次 |
| Step 4.4 | 贴图随机源 | **发现新缺陷 S** |
| 收尾 | 变异测试 + 提交 | `cd09b80`，110 passed |

**最终产出**：110 passed / 4 skipped / 10 xfailed，覆盖率 30% → **59%**，2 个缺陷修复 + 1 个新发现

---

## 卡点 0｜MJCF 找不到（Step 1 开场）

### 现象

按教程要「加载 place_block 的 MJCF」，但：

```bash
grep -n "mjcf\|xml\|scene" discoverse/configs/tasks/place_block.yaml
# 什么都没有
```

### 真相

场景不是静态文件，是**运行时拼出来的**：

```python
# universal_task_runtime.py:405
def generate_robot_task_model(robot_name, task_name):
    xml_path = os.path.join(DISCOVERSE_ASSETS_DIR, "mjcf/tmp", f"{robot_name}_{task_name}.xml")
    make_env(robot_name, task_name, xml_path)   # 机器人 XML + 任务场景 XML 在这里合并
    return xml_path
```

9 机器人 × 5 任务 = 45 个组合，不可能预存 45 个文件。

### 教训

**测试的输入应尽可能沿用生产代码的构造路径。** 手写一个 XML 也能让测试跑起来，但那测的是自造场景 —— `make_env` 的拼接逻辑有 bug 永远发现不了。

---

## 卡点 1｜「打印的 traceback」不是「抛出的异常」

每次跑测试都会看到：

```
Traceback (most recent call last):
  File ".../discoverse/envs/simulator.py", line 22, in <module>
    from gaussian_renderer.gs_renderer_mujoco import GSRendererMuJoCo
ModuleNotFoundError: No module named 'gaussian_renderer'
```

第一反应是环境坏了。**实际上程序继续往下跑了** —— 异常被 try/except 捕获，3DGS 渲染器缺失时降级。

### 判据

**程序继续执行了吗？** 执行了就说明异常被 catch 了。

### 但这本身是个可用性缺陷

`ModuleNotFoundError` 打在 **stderr**，配套的 `Warning: gaussian_splatting renderer not found` 打在 **stdout** —— 同一件事拆到两个流，而且打的是完整 traceback。

**真错误和假错误在输出里长得一模一样。** 将来 CI 日志混进一条真的 `ModuleNotFoundError`，没人会注意到。

→ 记入 defect-inventory（低严重度）：库代码用 `print` + 打印 traceback 代替 `logging`，无法按级别过滤。

---

## 卡点 2｜⚠️ 最重要的一个 —— 测试差点绿在错误的入口

### 现象

写确定性测试时，最自然的写法是：

```python
np.random.seed(42)
第一次随机化()
np.random.seed(42)
第二次随机化()
assert 两次相同    # ← 会【绿】！
```

### 实测三种设 seed 的方式

| 做法 | 两次结果相同？ |
|---|---|
| 测试里 `np.random.seed(42)` | ✅ **相同（测试绿）** |
| 不设 seed | ❌ 不同 |
| **config 里 `settings.seed = 42`** | ❌ **不同 ← 这才是缺陷** |

### 为什么第一种会绿

`randomization.py` 消费的是 numpy **全局**随机流。在测试里 seed 全局，它当然确定。

**但真实用户是通过 YAML 配 seed 的，而那条路是断的。**

### 教训

**测试必须走用户走的入口。** 要测的契约是「我在配置文件里写 seed: 42，两次运行应该一样」，不是「numpy 的 PRNG 工作正常」（那是 numpy 自己的测试该干的事）。

**从错误的入口进去，测的是别人家的代码。**

---

## 卡点 3｜自检 2 的意外收获 —— 三条测试缺一不可

### 做了什么

按计划做变异自检：临时在 `_randomize_once` 首行加 `np.random.seed(42)`，预期第 1 条测试变绿。

### 实际结果（比预期多）

| 测试 | 结果 |
|---|---|
| 第 1 条（同 seed 应相同） | **PASSED** ← 预期内 |
| 第 2 条（异 seed 应不同） | **FAILED** ← 没预告 |

### 为什么第 2 条会红

seed 被硬编码在函数首行，config 里传的 42 和 1234 **被完全无视**。两次结果一模一样，而第 2 条期待的是「不一样」。

### 这说明了什么

假设 Step 4 修得不彻底 —— 比如 seed 写死了，忘了从配置读。那么：

- 第 1 条会**绿**（确定了）
- 第 3 条会**绿**
- **只有第 2 条会红**

**任何单独一条都会给出「修好了」的错觉。**

### 后来的系统性验证（Step 4 收尾）

注入三种真实的修复失误：

| 注入的错误 | 谁抓到了 |
|---|---|
| `default_rng(seed)` → `default_rng(None)` | 2 条红 |
| **task_base 不传 seed**（接线断开） | **只有接线测试红**，其他 3 条全绿 |
| **`default_rng(42)` 硬编码**（假修复） | **只有异 seed 测试红**，其他 3 条全绿 |

**实测证明四条测试每一条都不可省。**

---

## 卡点 4｜我给的 sed 命令误伤了自己刚写的代码

### 现象

批量替换 25 处 `np.random.*` 之后：

```bash
grep -c "np\.random\." randomization.py    # 返回 1，不是 0
$PY -m pytest tests/ -q                    # 3 failed（从 1 failed 涨上来）
```

红的是第 2、3 条（`different_seeds` 和 `actually_moves`）—— 正是「随机化到底跑了没有」那两条。

### 根因

sed 命令是：

```bash
sed -i 's/np\.random\.random(/self.rng.random(/g; ...'
```

但**五分钟前刚加的构造函数那行也在替换范围内**：

```python
self.rng = np.random.default_rng(seed)
        ↓ 被 sed 改成
self.rng = self.rng.default_rng(seed)    # ← self.rng 此时还不存在 → AttributeError
```

`__init__` 一炸，后面全崩。

### 有意思的一点

第 1 条测试**仍然是红的**，但**病因换了** —— 从「seed 未生效」变成「构造函数崩溃」。

如果 4.1-4.3 一口气改完再跑，这个变化根本不会被注意到。

### 教训

1. **批量替换会作用于「我刚写的新代码」**，改动顺序影响结果
2. **`sed -i` 敢用的唯一理由是代码已 commit**（`8cfbc38` 垫底，改坏了 `git checkout` 就能回来）
3. **批量操作后先看 `git diff`**，别直接跑测试

---

## 卡点 5｜Claude 的验证脚本先写错了一次

### 现象

验证 task_base 接线时，第一版脚本写的是：

```python
t = UniversalTaskBase(...)                       # 构造
t.task_config.config[...]["seed"] = 42           # 改内存里的配置
t2 = UniversalTaskBase(...)                      # 重建
# 结果：两次不同 → 看起来接线没通
```

### 真相

`UniversalTaskBase.__init__` 是**从文件路径加载配置**的。改 `t` 对象内存里的 dict，`t2` 重新读了一遍文件 —— 改动根本没传过去。

改成**修改真实 YAML 文件**（真用户就是这么做的），结果立刻 `True`。

### 判断依据（为什么怀疑测试而不是代码）

**分布不合理**：seed 在 `SceneRandomizer` 层已经验证能工作，`task_base` 只是多传一个参数，不太可能这么简单还错。

→ Day 2 坑 4 的同一课：**测试红了先分三步 —— 找独立第二信源 → 看分布 → 看语义是否自洽。**

---

## 卡点 6｜Step 4 尾声发现新缺陷 S

### 起因

Step 2 grep 时注意到 `utils/__init__.py:90` 有一处 stdlib `random.choice`，当时以为「只有这一处，而且当前不可达」。

### 实测发现（比预想严重）

```python
def get_random_texture():
    if 贴图目录存在:
        random.choice(...)                      # stdlib（当前不可达）
    else:
        np.random.randint(0, 255, (768,768,3))  # numpy 全局流（当前就在跑！）
```

**两个分支，两种未受管控的随机源。** 而且 else 分支现在就是活跃路径 —— 实测连续两次调用返回的噪声图**不同**。

### 关键认知

**随机性是从 import 边界溜走的。**

Step 4 的修复范围是 `randomization.py`，但 `randomization.py:553` 调用了 `utils.get_random_texture()` —— 那个函数在另一个文件里，完全不知道 `rng` 的存在。

**确定性的边界不是「我改过的文件」，而是整条调用链。**

### 处置

写成 `xfail(strict=True)`，不修。理由：
- 当前 else 分支虽可达，但只影响贴图不影响物体位姿
- `get_random_texture` 是模块级函数，没有 `self.rng` 可用，修它要改公共签名 + 牵连全部 4 个调用方
- 超出 Step 4 范围，但**「没注意到」不可接受**

---

## Day 3 最终数字

| 项 | Day 2 结束 | Day 3 结束 |
|---|---|---|
| 用例 | 90 passed | **110 passed** |
| xfail | 9 | 10（+缺陷 S） |
| 覆盖率 TOTAL | 30% | **59%** |
| `randomization.py` | 9% | **69%** |
| `mink_solver.py` | 19% | 46%（外溢，未直接测） |
| commit | `cc3fc02` | `8cfbc38`、`cd09b80` |

**Day 3-4 计划的三个覆盖率目标（randomization 50%、mink_solver 40%、TOTAL 45%）全部在 Day 3 达成。**

---

## 未完成（Day 4）

- [ ] Step 5 缺陷 O（`mink_solver.py:126` 的 `dt` 硬编码遮蔽 `self.dt`）
- [ ] Step 6 IK 状态泄漏 —— **先证明再修**，读代码认为计划文档那条不成立（`solve_ik` 每次入口 `configuration.update()`），但 `posture_task` target 那处是真泄漏
- [ ] Step 7 缺陷 H 的 iiwa14 根因（nq 差 6）
- [ ] 缺陷 S 写进 defect-inventory
