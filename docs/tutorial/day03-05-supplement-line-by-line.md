# Day 3-5 补充 — 逐行解析：确定性、IK 状态泄漏、Flake 定量分析

> 配套 [day03-04-determinism.md](day03-04-determinism.md)、[day04-ik-and-defects.md](day04-ik-and-defects.md)、[day05-flake-analysis.md](day05-flake-analysis.md)
> 用途：**查阅型文档**，不用从头读。看不懂哪一行就跳到哪一节。
> 覆盖：`test_determinism.py` 292 行 + `test_mink_solver.py` 177 行 + `test_randomization_config.py` 134 行 + `test_task_matrix.py` 123 行 + `gen_flake_report.py` 149 行 + 全部命令行
> 面向：**没做过可复现性工程、没做过统计实验的读者**。每个概念从零讲起。

---

## 目录

- [第一部分：预备概念（8 个，不懂这些后面全是天书）](#第一部分预备概念8-个)
- [第二部分：`test_randomization_config.py` 逐行（134 行）](#第二部分test_randomization_configpy-逐行134-行)
- [第三部分：`test_determinism.py` 逐行（292 行）](#第三部分test_determinismpy-逐行292-行)
- [第四部分：`test_mink_solver.py` 逐行（177 行）](#第四部分test_mink_solverpy-逐行177-行)
- [第五部分：`test_task_matrix.py` 逐行（123 行）](#第五部分test_task_matrixpy-逐行123-行)
- [第六部分：`gen_flake_report.py` 逐行（149 行）](#第六部分gen_flake_reportpy-逐行149-行)
- [第七部分：命令行逐字解析](#第七部分命令行逐字解析)
- [第八部分：面试问答速查](#第八部分面试问答速查)
- [第九部分：企业开发扩展](#第九部分企业开发扩展)

---

# 第一部分：预备概念（8 个）

## 1.1 什么叫「确定性」，为什么它是测试的地基

**确定性（determinism）**：相同输入 → 相同输出。

听起来是废话，但在仿真里它**默认不成立**：

```python
randomizer.exec_randomization(config)   # 第一次：方块在 (0.31, 0.12)
randomizer.exec_randomization(config)   # 第二次：方块在 (0.28, -0.05)
```

物体位置是随机生成的，两次当然不同。**这本身没问题** —— 域随机化
（domain randomization）就是要让场景每次都不一样，这样训出来的策略才不会
只会在一个固定场景里работать。

问题在于：**你必须能在需要的时候把它关掉。**

### 为什么必须能关掉

| 场景 | 需要确定性吗 | 为什么 |
|---|---|---|
| 训练策略 | ❌ 不需要 | 场景越多样越好 |
| **复现一个 bug** | ✅ **必须** | 「第 37 次跑挂了」，你得能再跑出那第 37 次 |
| **回归测试** | ✅ **必须** | 测试今天绿明天红，你不知道是代码坏了还是运气差 |
| **对比两个算法** | ✅ **必须** | 不同场景下比成功率，比的是运气不是算法 |

📌 **所以 seed（随机种子）不是可选功能，是调试能力的地基。**
seed 断了 → 任何失败都无法复现 → 整个测试体系失去意义。

### 本项目实际的情况（Day 3 实测）

```
settings.seed 声明于 6 处 YAML   ←  用户以为写了就生效
真正读它的代码：0 处            ←  完全没人读
randomization.py 里的裸 np.random.*：25 处
```

**用户写 `seed: 42`，什么都不会发生。** 这就是 Day 3 要修的东西。

---

## 1.2 `np.random.seed()` vs `np.random.default_rng()` ⭐ 本课最重要的设计决策

修 seed 有两种写法，**选错了会留下一个更隐蔽的坑**。

### 方案 A：全局种子（❌ 我没选）

```python
np.random.seed(42)              # 设置全局状态
x = np.random.uniform(0, 1)     # 从全局流取数
```

`np.random` 是一个**进程级的全局单例**。想象成整个 Python 进程共用一个骰子。

### 方案 B：Generator 实例（✅ 我选的）

```python
self.rng = np.random.default_rng(42)   # 自己的骰子
x = self.rng.uniform(0, 1)              # 从自己的流取数
```

每个 `SceneRandomizer` 拿一个**属于自己的**随机数生成器。

### 为什么方案 A 是错的：三个具体的坑

**坑 1：并行测试会互相污染**

```python
# pytest -n 4 时，4 个进程... 不，是同一进程里的多个线程/用例交错执行
测试 A: np.random.seed(42);  取 3 个数 → [0.37, 0.95, 0.73]
测试 B: np.random.seed(42);  取 2 个数 → [0.37, 0.95]
测试 A: 继续取第 4 个数     → 拿到的是 B 推进后的位置！
```

全局状态 = 谁都能改 = 顺序一变结果就变。**Day 5 的 `-n 8` 并行采样会直接翻车。**

**坑 2：污染整个进程，影响无关代码**

你在随机化模块里 `np.random.seed(42)`，结果**整个进程**的 numpy 随机都被固定了 ——
包括策略网络的权重初始化、数据增强、任何第三方库。这叫**副作用外溢**。

**坑 3：无法同时有两条独立随机流**

```python
r1 = SceneRandomizer(model, data, seed=42)    # 场景随机化
r2 = SceneRandomizer(model, data, seed=7)     # 另一个独立场景
```
方案 A 做不到 —— 只有一个全局骰子，后设的种子覆盖先设的。
方案 B 天然支持，两个实例各有各的 `self.rng`。

### 📖 企业扩展：这是「全局可变状态」反模式的一个实例

| 领域 | 全局状态的表现 | 正确做法 |
|---|---|---|
| 随机数 | `np.random.seed()` | `default_rng()` 实例 |
| 数据库 | 全局 `connection` | 连接池 + 依赖注入 |
| 配置 | 全局 `CONFIG` 字典 | 配置对象传参 |
| 时间 | 直接调 `time.now()` | 注入 `clock` 对象（可 mock） |
| 日志 | 全局 logger 改 level | 每模块独立 logger |

**共同症状**：单元测试单跑绿、全跑红；顺序一变就复现不了。
**共同解法**：把隐式的全局依赖变成显式的构造参数。这叫**依赖注入**。

面试可以这样讲：「我修 seed 时选了 Generator 实例而不是全局 seed，
因为全局随机流本质上是全局可变状态 —— 它会让并行测试互相污染，
而我 Day 5 要跑 `-n 8` 的并行采样，用全局种子那份数据是不可信的。」

---

## 1.3 什么是「平凡解」——为什么一条绿灯测试可能什么都没测

这是 Day 3 最反直觉的一个点。

假设我们要测「seed 生效」，写了这条：

```python
def test_seed_reproducible():
    a = randomize(seed=42)
    b = randomize(seed=42)
    assert a == b          # 两次结果应该一样
```

**这条测试有一个平凡解（trivial solution）**：

> 如果随机化**根本没执行**（config 是空的、物体名写错了、函数提前 return），
> 两次结果**自然完全相同** —— 测试变绿，但它什么都没验证。

绿灯的原因不是「seed 生效了」，而是「什么都没发生」。

### 解法：加反向哨兵

```python
def test_different_seeds_differ():
    a = randomize(seed=42)
    b = randomize(seed=1234)
    assert a != b          # 不同 seed 必须不同
```

**两条一起才是完整判据**：
- 第 1 条保证「**确定**」（同 seed 同结果）
- 第 2 条保证「**真的在随机**」（异 seed 异结果）

只有第 1 条 → 可能是死的；只有第 2 条 → 可能没被 seed 管控。

📌 **通用方法论：每写一条断言，问自己「有没有一种什么都没做的情况能让它通过」。**
有的话，就得再补一条把那种情况排除掉。

---

## 1.4 什么是「变异测试」（mutation testing）—— 怎么验证测试真的有用

**测试通过了，怎么知道测试本身是对的？**

答案：**故意把代码改坏，看测试红不红。**

```
① 测试全绿 ✅
② 把修复代码注释掉（人为制造缺陷）
③ 重跑测试
   → 红了 ✅ 说明测试真的守住了这个行为
   → 还是绿 ❌ 说明测试是摆设，它守的不是你以为的那个东西
```

这叫**变异测试**（mutation testing）/ **变异验证**。

### Day 4 的真实经历：变异验证「失败」了

我修好 IK 状态泄漏后，注释掉修复代码，**测试仍然全绿**。

这说明：我以为测试守住的契约，其实它没守住。
排查后发现契约有两层，我只测了一层（详见 [4.4](#44-test_default_posture_target_is_home_not_qpos0142-177-行)）。

📌 **这一步的价值：它是唯一能证明「测试有效」的手段。**
没做变异验证的测试，你只知道它「现在是绿的」，不知道它「坏了会不会红」。

### 📖 企业扩展：工业界的变异测试工具

| 语言 | 工具 | 做法 |
|---|---|---|
| Python | `mutmut`、`cosmic-ray` | 自动改 `>` 为 `>=`、删语句、改常量 |
| Java | **PIT (pitest)** | 业界最成熟，能出「变异得分」报告 |
| JS | `Stryker` | |

**变异得分** = 被测试杀死的变异体 / 总变异体。
比行覆盖率诚实得多 —— 覆盖率只说「这行跑过」，变异得分说「这行改坏了会被发现」。

⚠️ 但工具化变异测试**很慢**（每个变异体要跑一遍全套测试）。
实践中常见做法：**关键模块手工做变异验证**（像我 Day 4 这样），
全量自动变异只在 nightly 跑。

---

## 1.5 `xfail(strict=True)` —— 把「已知缺陷」变成可执行的文档

```python
@pytest.mark.xfail(strict=True, reason="缺陷 U：...")
def test_something():
    assert ...
```

| 标记 | 含义 | 测试红了 | 测试绿了 |
|---|---|---|---|
| 无标记 | 应该通过 | ❌ FAILED | ✅ PASSED |
| `skip` | **不跑** | — | — |
| `xfail` | 预期失败 | ✅ XFAIL（正常） | ⚠️ XPASS |
| **`xfail(strict=True)`** | **预期失败** | ✅ XFAIL | ❌ **FAILED** |

### 为什么必须加 `strict=True`

不加 strict，缺陷被修好后测试会变成 XPASS —— **一个没人看的黄色标记**。
加了 strict，XPASS 直接报 **FAILED**，强制有人回来把 xfail 标记撤掉。

📌 **效果：「缺陷被修复」这件事也不会静默发生。**

### 为什么 xfail 比注释掉测试好

```python
# ❌ 注释掉 —— 死的，三个月后没人知道它还成不成立
# def test_texture_seed():
#     assert ...

# ✅ xfail —— 活的，每次 CI 都跑，状态一变就有人知道
@pytest.mark.xfail(strict=True, reason="...")
def test_texture_seed():
    assert ...
```

**xfail 是可执行的缺陷报告。** 它同时是：
- 缺陷记录（`reason` 写清楚根因）
- 回归防护（修好了会通知你）
- 交接文档（新人看测试就知道有哪些坑）

---

## 1.6 什么是 flake（不稳定测试）

**flake / flaky test**：同样的代码、同样的输入，**有时绿有时红**。

```
第 1 次跑：PASSED
第 2 次跑：FAILED     ← 代码一行没改
第 3 次跑：PASSED
```

### 为什么 flake 是 CI 的头号杀手

flake 会摧毁团队对测试的信任：

```
测试红了 → 「哦又 flake 了，重跑一下」→ 重跑变绿 → 合并
                                            ↑
                            真实的 bug 就是这样被放过去的
```

一旦养成「红了就重跑」的习惯，**测试就失去了全部价值**。

### 具身智能里 flake 的第二重身份 ⭐

在普通 Web 后端，flake 通常是**测试写得不好**（依赖时序、共享状态、网络抖动）。

但在机器人仿真里，flake 还可能是**产品本身的属性**：

```
场景是随机的 → 有些场景物体离得远 → IK 够不着 → 任务失败
```

这**不是测试的 bug，是机器人能力的边界**。

📌 **所以「成功率 76%」这个数字本身没有意义。** 必须回答：
- 那 24% 是**同一个原因**还是**多个原因**？
- 是**随机的**（真 flake）还是**确定的**（配置缺陷伪装成 flake）？
- 不同机器人的失败模式一样吗？

这就是 Day 5 要做的**失败归因（failure attribution）**。

---

## 1.7 分桶（bucketing）—— 把「失败」拆成可行动的类别

**一个失败率数字是不可行动的。** 分桶后才知道该修什么。

Day 5 实测得出四个桶：

| 桶 | 含义 | 判据 | 说明什么 |
|---|---|---|---|
| `SUCCESS` | 成功 | 输出含 `任务成功: ✅` | — |
| `BUCKET1` | **早期 IK 失败** | 完成状态 `5/17` < 总数 | **够不着** —— 目标超出工作空间 |
| `BUCKET2` | **判据失败** | 完成状态 `17/17` 但没成功 | **抓不住** —— 走到位了但物体滑了 |
| `BUCKET3` | 超时 | 进程被杀 / 输出含 TIMEOUT | 死循环或太慢 |
| `BUCKET4` | **配置崩溃** | 连完成状态都没打印 | ⚠️ **不是 flake，是确定性缺陷** |

### ⭐ BUCKET1 vs BUCKET2 的区分为什么值钱

两者的**修复方向完全相反**：

```
BUCKET1 多  → 够不着     → 改机器人摆位 / 缩小随机化范围 / 换机械臂
BUCKET2 多  → 抓不住     → 调夹爪力度 / 摩擦系数 / 抓取姿态
```

**只看「成功率 60%」，你不知道往哪个方向修。**
分桶后看到「airbot_play 全是 BUCKET2、iiwa14 全是 BUCKET1」，
修复方向立刻清晰。

---

## 1.8 ⭐ BUCKET4：为什么必须把确定性缺陷从 flake 统计里剔除

**这是 Day 5 最值钱的一个判断，面试必讲。**

实测数据：

```
总运行           2250 次
BUCKET4（配置崩溃） 355 次     ← cover_cup 对非 airbot_play 机器人
                                声明了不存在的相机 eye_arm
```

这 355 次**100% 复现、零随机性** —— 每次都崩，不是「有时候崩」。

### 如果不剔除会怎样

```
表观成功率 = 924 / 2250 = 41.1%      ← 把确定性缺陷算进了 flake
真实成功率 = 924 / 1895 = 48.8%      ← 剔除后
                                        差了 7.7 个百分点
```

**更严重的是误导修复方向**：

热力图上 `cover_cup` 那一整行永远是黑的 → 有人会去调 IK 容差、
改抓取策略、怀疑物理引擎 —— 而**真正的问题是一行配置里写错了相机名**。

📌 **结论：`355/2250 = 15.8%` 的「随机失败」实际是确定性缺陷。**

### 这个判断的通用价值

> **在做统计之前，先把确定性的部分剥离出去。**
> 把 100% 复现的 bug 混进随机性分析，会同时污染两件事：
> 分母（低估真实成功率）和归因（掩盖真正的随机性信号）。

面试可以这样讲：「我做 flake 分析时发现 15.8% 的失败是 100% 复现的配置缺陷。
如果直接算成功率，会得到 41.1% 这个被污染的数字，而且热力图会误导人去调 IK。
我把它单独成桶剔除后，真实 flake 率是 48.8%。**这个区分本身比那个数字更重要** ——
它说明「不稳定」和「一直坏」是两类问题，混在一起就都修不好。」

---

# 第二部分：`test_randomization_config.py` 逐行（134 行）

> 缺陷 J：碰撞避让半径的键名不匹配 —— 9/12 物体的半径静默失效。

## 2.1 文件头 docstring（1-14 行）

```python
"""缺陷 J：碰撞避让半径的键名不匹配。

实测（2026-07-31）：
    randomization.py:184 读的是 min_distance
    12 个任务物体的 YAML 写的全是 collision_radius
    -> .get() 取不到 -> 9/12 物体的半径静默塌到默认值 0.05
"""
```

### 这个缺陷是什么

```python
# 代码里（randomization.py:184）
radius = obj_config.get("min_distance", 0.05)

# YAML 里（12 个物体，全部）
- name: bowl_pink
  collision_radius: 0.12        ← 键名不一样！
```

`.get()` 取不到 `min_distance` → **静默**返回默认值 `0.05`。

### ⚠️ 为什么「静默」是关键词

如果写成 `obj_config["min_distance"]`，取不到会抛 `KeyError`，**当场炸**。
但 `.get(key, default)` **不会报错** —— 它安静地用了默认值。

后果：
```
bowl_pink 声明避让半径 0.12m，实际生效 0.05m  → 缩小 2.4 倍
物体之间会摆得太近 → 生成的场景物理上重叠/干涉 → 数据集质量下降
```

**而且没有任何日志、任何报错。** 你只会觉得「这个仿真怎么老是抓失败」。

📌 **`.get()` 的默认值是双刃剑**：它让代码健壮，也让配置错误隐形。
**企业实践**：配置加载应该有 schema 校验（见 [第九部分](#92-配置即代码用-schema-校验替代-get-默认值)）。

### 为什么兼容两个键名，而不是只改一边（8-13 行）

```python
为什么兼容两个键名而不是只改一边：
    templates/randomization.yaml 用 min_distance（6 处），
    但实测【没有任何任务继承它】——
    唯一引用是该文件第 137 行的注释示例。
    它是给人照抄的文档模板，所以新键名要认，旧键名也要认。
```

**这是一个「读者是谁」的判断**：

| 选项 | 后果 |
|---|---|
| 只认 `collision_radius`（改代码） | 照着模板抄的人掉进同一个坑 |
| 只认 `min_distance`（改 12 处 YAML） | 改动面大，且模板才是「文档」 |
| **两个都认，新的优先** ✅ | 现有配置立刻生效，照抄模板的人也不会踩坑 |

📌 **修 bug 时要问：谁会受影响？** 不只是「现在的代码」，
还有「照着文档写新代码的人」。

---

## 2.2 `radius_of` fixture（23-37 行）⭐ 用 `__new__` 绕过 `__init__`

```python
@pytest.fixture
def radius_of():
    instance = SceneRandomizer.__new__(SceneRandomizer)
    return instance._get_collision_radius
```

### `__new__` 和 `__init__` 的区别（从零讲）

Python 创建对象分两步：

```python
obj = SceneRandomizer(model, data)
# 等价于：
obj = SceneRandomizer.__new__(SceneRandomizer)   # ① 分配内存，造一个空壳
obj.__init__(model, data)                         # ② 填充属性
```

`SceneRandomizer.__new__(SceneRandomizer)` = **只做第 ①  步**，
得到一个**没有任何属性**的空对象。

### 为什么要这么干

`__init__` 需要真实的 `MjModel` / `MjData`（要遍历 body、camera、light 存初始状态）。
但 `_get_collision_radius` **只是个字典查找**，跟模型毫无关系：

```python
def _get_collision_radius(self, obj_config):
    return obj_config.get("collision_radius", obj_config.get("min_distance", 0.05))
    #      ↑ 完全没用到 self 的任何属性
```

| 做法 | 耗时 | 失败可能性 |
|---|---|---|
| 正常构造 | ~200ms（加载 MJCF、编译 mesh） | 模型文件缺失、mesh 加载失败…… |
| **`__new__` 空壳** | **~0.001ms** | 只有被测逻辑本身 |

📌 **关键理由（33-34 行的注释）**：

> 那些失败会**伪装成**「半径逻辑坏了」。

模型加载失败 → 测试红 → 你以为半径逻辑有问题 → 排查半天发现是 mesh 路径变了。
**测试应该只在被测行为坏掉时红。** 引入无关依赖 = 引入假警报。

### ⚠️ 什么时候不该用这招

`__new__` 空壳只在被测方法**不依赖任何实例属性**时安全。
如果方法里用了 `self.mj_model`，空壳会 `AttributeError`。

**更通用的替代方案**（企业实践）：把纯函数**提取出类**：

```python
# 更好的设计：它本来就不该是方法
def get_collision_radius(obj_config: dict) -> float:
    ...
```
测试直接调函数，无需任何技巧。
📌 **需要用 `__new__` 绕过构造，往往是在提示你：这个方法不该是方法。**

---

## 2.3 四条单值行为测试（43-68 行）

```python
def test_reads_collision_radius(radius_of):
    assert radius_of({"collision_radius": 0.12}) == 0.12       # 新键名

def test_reads_min_distance_as_fallback(radius_of):
    assert radius_of({"min_distance": 0.03}) == 0.03           # 旧键名

def test_collision_radius_wins_over_min_distance(radius_of):
    assert radius_of({"collision_radius": 0.12,
                      "min_distance": 0.03}) == 0.12           # 优先级

def test_falls_back_to_default_when_absent(radius_of):
    assert radius_of({}) == 0.05                                # 默认值
```

**这四条覆盖了一个「兼容两个键名」逻辑的全部分支**：

```
     有 collision_radius?
      ├─ 是 ──────────────→ 用它            （测试 1、3）
      └─ 否 ─→ 有 min_distance?
                ├─ 是 ────→ 用它            （测试 2）
                └─ 否 ────→ 用默认 0.05     （测试 4）
```

📌 **这叫「分支覆盖」**：不是「这行代码跑过了」（行覆盖），
而是「每个 if/else 的每条岔路都走过了」。

### 为什么第 3 条（优先级）单独写

```python
"""为什么是 collision_radius 优先：
  它是【实际被加载的】那个（12 处 vs 0 处）。
  优先级要给真正生效的一方，否则修复等于没修。
"""
```

如果优先级搞反（`min_distance` 优先），当两个键都存在时会取旧的 →
**修了等于没修**。这条测试把这个决策钉死。

---

## 2.4 `DECLARED_RADII` 契约表（76-89 行）⭐ 写成脆断言

```python
# 实测值（2026-07-31），非文档抄录。
# 写成脆断言：任何一个数字变了都要有人来看一眼，
# 而不是让测试悄悄跟着配置漂移。
DECLARED_RADII = [
    ("cover_cup", "coffeecup_white", 0.05),
    ("cover_cup", "plate_white",     0.10),
    ...
    ("place_block", "bowl_pink",     0.12),
]
```

### 什么叫「脆断言」（brittle assertion）

```python
# ❌ 自适应断言 —— 永远不会红，也永远不会告诉你任何事
assert radius_of(obj) == obj.get("collision_radius", 0.05)
#      ↑ 左右两边是同一个逻辑，这在测「1 == 1」

# ✅ 脆断言 —— 数字写死
assert radius_of(place_block_bowl) == 0.12
```

**「脆」在这里是褒义词**：配置一改，测试就红，有人来看一眼。

📌 **常见错误：用被测代码去算期望值。**
那样测试永远绿，因为它在自己验证自己。期望值必须是**独立来源** ——
手工实测、需求文档、或者人工计算。

### ⚠️ 但脆断言有代价

配置正常演进时（比如真的要把 bowl 改成 0.15），测试会红，
需要人手动更新这个表。**这是有意的成本**：

> 让「配置变更」这件事必须经过一次人工确认，而不是静默发生。

**企业实践中的权衡**：
- 核心业务规则（价格、权限、安全阈值）→ **用脆断言**，变更必须被感知
- 频繁调整的调优参数 → 用范围断言 `assert 0.05 <= r <= 0.2`

---

## 2.5 `loaded_objects` fixture（92-113 行）—— 静态读 ≠ 运行时加载

```python
@pytest.fixture(scope="session")
def loaded_objects(task_config_dir):
    """{(任务名, 物体名): 物体配置} —— 经加载器解析 extends 后的最终配置。

    Day 2 方法论第 7 条：静态读 YAML != 运行时加载。
    """
    out = {}
    for path in sorted(task_config_dir.glob("*.yaml")):
        cfg = TaskConfigLoader.from_dict(
            replace_variables(load_and_resolve_config(str(path)))
        )
        for obj in (cfg.randomization or {}).get("objects") or []:
            out[(path.stem, obj["name"])] = obj
    return out
```

### ⭐ 为什么不能直接 `yaml.safe_load(path)`

因为配置有**继承**：

```yaml
# place_block.yaml
extends: "templates/place_object.yaml"    ← 继承模板
randomization:
  objects:
    - name: bowl_pink
      collision_radius: 0.12
```

直接读文件 → 只看到 `place_block.yaml` 自己写的那部分。
**模板里的字段完全看不到。**

必须走**和生产代码相同的加载路径**：

```
load_and_resolve_config()  →  解析 extends，合并模板
replace_variables()        →  替换 ${变量}
TaskConfigLoader.from_dict →  转成结构化对象
```

📌 **通用原则：测试要走用户真实走的那条路。**
从错误的入口进去，测的是另一个东西。

### 逐段拆解

| 代码 | 作用 |
|---|---|
| `sorted(task_config_dir.glob("*.yaml"))` | 找出所有任务配置。`sorted` 保证顺序稳定（glob 顺序依赖文件系统） |
| `(cfg.randomization or {})` | `randomization` 可能是 `None`，`or {}` 兜底避免 `AttributeError` |
| `.get("objects") or []` | 同上，两层保护 |
| `out[(path.stem, obj["name"])]` | `path.stem` = 文件名去掉后缀（`place_block.yaml` → `place_block`） |
| `scope="session"` | 解析全部 YAML 不便宜，且结果只读 → 全局复用 |

---

## 2.6 参数化契约测试（116-134 行）⭐ 核心

```python
@pytest.mark.parametrize("task,obj,declared", DECLARED_RADII)
def test_effective_radius_equals_declared(
    radius_of, loaded_objects, task, obj, declared
):
    """修复前：9/12 会红（全部塌到 0.05）
       修复后：12/12 绿"""
    obj_config = loaded_objects.get((task, obj))
    assert obj_config is not None, f"{task}/{obj} 不在加载后的配置里，测试前提不成立"

    effective = radius_of(obj_config)
    assert effective == pytest.approx(declared), (
        f"{task}/{obj} 声明半径 {declared}，实际生效 {effective} "
        f"（缩小 {declared / effective:.1f}×）—— 避让距离静默失效"
    )
```

### `parametrize` 三元组解包

```python
@pytest.mark.parametrize("task,obj,declared", DECLARED_RADII)
#                         ↑ 三个参数名，逗号分隔
#                                            ↑ 列表里每项是 3 元组
```
`("cover_cup", "coffeecup_white", 0.05)` → `task="cover_cup"`, `obj="coffeecup_white"`, `declared=0.05`

**生成 12 个独立用例**，测试名长这样：
```
test_effective_radius_equals_declared[cover_cup-coffeecup_white-0.05]
```

### 为什么用参数化而不是 for 循环

```python
# ❌ 循环：第一个失败就 raise，剩下 11 个根本没跑
for task, obj, declared in DECLARED_RADII:
    assert radius_of(...) == declared

# ✅ 参数化：12 个独立用例，一眼看出红了哪 9 个
```

📌 **Day 3 靠这个才看出「9/12 红」这个分布** ——
如果是循环，只会看到「第 1 条就挂了」，无法判断影响面。

### `pytest.approx` 是什么

浮点数比较不能用 `==`：

```python
>>> 0.1 + 0.2 == 0.3
False                      # 浮点精度！实际是 0.30000000000000004
>>> 0.1 + 0.2 == pytest.approx(0.3)
True                       # 允许极小误差（默认相对误差 1e-6）
```

📌 **本例其实是从 YAML 直接读出来的值，不涉及运算，用 `==` 也行。**
但用 `approx` 是**防御性习惯** —— 万一以后加了单位换算就不会莫名其妙红。

### 前提断言（127-128 行）

```python
assert obj_config is not None, f"{task}/{obj} 不在加载后的配置里，测试前提不成立"
```

**这条不是在测被测行为，是在测「测试自己的假设」。**

如果物体名写错了，`loaded_objects.get()` 返回 `None`，
下一行 `radius_of(None)` 会抛 `AttributeError` —— 一个**看不懂的错误**。

有了这条断言 → 直接告诉你「测试前提不成立」，而不是让你去猜。

📌 **通用技巧：把「我以为成立的前提」写成可执行的检查。**

### 失败消息里的 `缩小 {declared / effective:.1f}×`

```python
f"（缩小 {declared / effective:.1f}×）"
# 0.12 / 0.05 = 2.4  →  "（缩小 2.4×）"
```

**好的失败消息回答三个问题**：期望什么、实际什么、**影响多大**。
第三个最容易被忽略 —— 「2.4 倍」立刻让人意识到严重性。

---

# 第三部分：`test_determinism.py` 逐行（292 行）

## 3.1 文件头：⚠️ 最重要的一条警告（1-12 行）

```python
"""确定性专项测试：配置里的 seed 是否真的生效。

⚠️ 关键设计（详见 docs/tutorial/day03-step1-walkthrough.md 坑 C）：
   绝不能在测试里调 np.random.seed(42)。
   那样测试会【绿】—— 因为 randomization.py 消费的是全局 np.random，
   在外面 seed 全局当然确定。但真实用户走的是配置文件那条路，
   而那条路是断的。从错误的入口进去，测的是 numpy 不是本项目。
"""
```

### ⭐ 这是全篇最值钱的一段，慢慢读

**错误写法**：

```python
def test_seed_works():
    np.random.seed(42)              # ← 在测试里设全局种子
    a = randomize(config)
    np.random.seed(42)
    b = randomize(config)
    assert a == b                   # ✅ 绿灯！
```

**这条测试会通过 —— 但它是假的。**

原因：`randomization.py` 用的是全局 `np.random`。你在外面把全局流固定了，
它当然确定。**但你测的是「numpy 的 seed 功能好不好用」，而不是
「本项目的配置里写 seed 有没有用」。**

真实用户的路径是：

```
用户编辑 place_block.yaml：settings.seed = 42
    ↓
UniversalTaskBase 读配置
    ↓
传给 SceneRandomizer
    ↓
randomization.py 用它
```

**这条链在 Day 3 之前是断的（第 2 步之后没人读 seed）。**
而 `np.random.seed(42)` 的写法完全绕过了这条链。

📌 **通用方法论：测试的入口必须是用户的入口。**

| 反例 | 为什么错 |
|---|---|
| 测 API 时直接调 service 层 | 绕过了路由、鉴权、参数校验 |
| 测配置时直接构造对象 | 绕过了配置文件加载、类型转换 |
| 测 seed 时设全局 seed | 绕过了整条 seed 传递链 |

**面试可以这样讲**：「Day 3 我差点写出一条假绿灯测试 ——
在测试里调 `np.random.seed(42)`。它会通过，但它测的是 numpy，
不是我的项目。真实用户是在 YAML 里写 seed，而那条链当时是断的。
**测试的入口必须是用户的入口**，否则绿灯毫无意义。」

---

## 3.2 模块级配置（27-32 行）

```python
pytestmark = [pytest.mark.determinism, pytest.mark.integration]

ROBOT = "airbot_play"
TASK = "place_block"
# place_block 场景里仅有的两个自由体（实测 free_body_qpos_ids 确认）
FREE_BODIES = ["block_green", "bowl_pink"]
```

### `pytestmark` 是什么

给**本文件所有测试**统一打标签，等价于在每个函数上加 `@pytest.mark.xxx`。

```bash
$PY -m pytest -m determinism      # 只跑确定性专项
$PY -m pytest -m "not integration"  # 跳过所有需要加载 MJCF 的
```

### 什么是「自由体」（free body）

MuJoCo 里的物体分两类：

| 类型 | 含义 | 例子 |
|---|---|---|
| **固定体** | 焊死在世界上，不会动 | 桌子、地面、墙 |
| **自由体**（free body） | 有 free joint，能自由飞 | 方块、碗、杯子 |

**只有自由体的位姿会被随机化** —— 桌子随机化了就穿模了。

📌 注释里的「实测 `free_body_qpos_ids` 确认」很关键：**不是照文档抄的，
是跑代码数出来的。** Day 1-2 的方法论：不要凭文档猜。

---

## 3.3 `task_xml` fixture（38-56 行）—— 场景是现场拼出来的

```python
@pytest.fixture(scope="session")
def task_xml(repo_root):
    """生成 robot x task 的 MJCF，返回路径。

    §0 坑 A：场景不是静态文件，是 make_env 现场拼出来的
    （9 机器人 x 5 任务 = 45 组合，不可能预存）。
    测试走和生产代码相同的构造路径，否则测的是自造场景。
    """
    from discoverse import DISCOVERSE_ASSETS_DIR
    from discoverse.envs.make_env import make_env

    xml_path = os.path.join(DISCOVERSE_ASSETS_DIR, "mjcf", "tmp", f"{ROBOT}_{TASK}.xml")
    make_env(ROBOT, TASK, xml_path)
    if not os.path.exists(xml_path):
        pytest.skip(f"make_env 未产出 MJCF: {xml_path}")
    return xml_path
```

### ⭐ 坑 A：场景文件不存在于磁盘上

新手最容易犯的错：以为 `place_block.xml` 是个静态文件，直接去加载。

**实际上**：9 机器人 × 5 任务 = 45 种组合，**不可能每种都预存一个 XML**。
`make_env(robot, task, out_path)` 会：

```
读机器人 MJCF（robot_airbot_play.xml）
    +
读任务场景 MJCF（place_block 的桌子、方块、碗）
    ↓
XML 树合并
    ↓
写出 tmp/airbot_play_place_block.xml
```

📌 **测试必须走这条路**，否则你测的是一个自己拼的场景，
和生产环境跑的不是同一个东西。

### 为什么是 `scope="session"`

```
make_env 要读多个 XML 并做树合并  →  不便宜
产出是磁盘上的文件               →  只读，复用安全
```

⚠️ 注意区别：**产出的是「文件路径」（字符串），不是 MjModel 对象。**
每个用例拿到路径后自己 `from_xml_path` 编译 —— 所以状态仍然隔离。

### 延迟 import（49-50 行）

```python
def task_xml(repo_root):
    from discoverse import DISCOVERSE_ASSETS_DIR      # ← 在函数内 import
    from discoverse.envs.make_env import make_env
```

**为什么不写在文件顶部**：
- `make_env` 会拉起一长串 import 链（MuJoCo、渲染后端……）
- 写在顶部 → **收集阶段**就执行 → 即使你只想跑 `-m unit` 也要付这个代价
- 写在 fixture 里 → 只有真正需要时才执行

📌 **企业实践：重依赖延迟 import，是让「快测试快速失败」的常用手段。**

### `pytest.skip` vs `assert`（54-55 行）

```python
if not os.path.exists(xml_path):
    pytest.skip(f"make_env 未产出 MJCF: {xml_path}")
```

| | 语义 | 什么时候用 |
|---|---|---|
| `assert` | **被测代码错了** | 断言业务行为 |
| `pytest.skip` | **前提条件不满足，测不了** | 缺依赖、缺文件、缺 GPU |

这里用 skip 是因为：`make_env` 没产出文件 → 可能是环境问题（资源目录缺失），
不一定是 seed 逻辑坏了。**用 skip 避免假警报。**

⚠️ **但 skip 有滥用风险**：CI 上一堆 skip = 一堆没跑的测试。
**企业实践**：CI 里加 `-ra` 汇总所有 skip 原因，并设一个「skip 数量上限」告警。

---

## 3.4 `base_randomization_config` fixture（59-72 行）

```python
@pytest.fixture(scope="session")
def base_randomization_config(task_config_dir):
    cfg_path = str(task_config_dir / f"{TASK}.yaml")
    resolved = replace_variables(load_and_resolve_config(cfg_path))
    randomization = TaskConfigLoader.from_dict(resolved).randomization
    assert randomization is not None, f"{TASK} 没有 randomization 段，测试前提不成立"
    return randomization
```

三步加载链，和 [2.5](#25-loaded_objects-fixture92-113-行) 完全一样 ——
**必须用加载器而非直接读 YAML**（extends 会改变最终内容）。

### ⚠️ 一个 session 级 fixture 的陷阱（66 行注释）

```python
⚠️ session 级 + 返回可变 dict：使用者必须 deepcopy（见 §4）。
```

**这是 pytest 里非常容易踩的坑**：

```python
def test_a(base_randomization_config):
    base_randomization_config["objects"][0]["x_range"] = [0, 0]   # 改了！
    ...

def test_b(base_randomization_config):
    # 拿到的是【被 test_a 改过的】同一个 dict 对象！
```

session 级 fixture **只执行一次**，返回的是**同一个对象引用**。
任何测试改了它，后面所有测试都受影响。

📌 **三种解法**：

```python
# ① 使用者自己 deepcopy（本项目的选择，配注释提醒）
cfg = copy.deepcopy(base_randomization_config)

# ② fixture 返回时就 deepcopy（改成 function 级）
@pytest.fixture
def config(base_randomization_config):
    return copy.deepcopy(base_randomization_config)

# ③ 返回不可变结构（frozen dataclass / MappingProxyType）
from types import MappingProxyType
return MappingProxyType(randomization)      # 改它会 TypeError
```

**企业实践推荐 ③** —— 让错误在**写代码时**就暴露，而不是靠注释提醒。

---

## 3.5 `_randomize_once` helper（78-105 行）⭐ 核心逻辑

```python
def _randomize_once(xml_path, config, seed=None):
    model = mujoco.MjModel.from_xml_path(xml_path)
    data = mujoco.MjData(model)
    mujoco.mj_resetData(model, data)
    mujoco.mj_forward(model, data)

    randomizer = SceneRandomizer(model, data, seed=seed)
    randomizer.exec_randomization(config)

    return np.concatenate(
        [np.asarray(randomizer._object_pose(name)).copy() for name in FREE_BODIES]
    )
```

### 逐行拆解

**① `MjModel.from_xml_path` + `MjData(model)`（93-94 行）**

每次调用都**新建**模型和数据。

```python
§3：每次调用都新建 MjData 和 SceneRandomizer。
复用会导致状态泄漏 —— randomization.py 的 z 坐标沿用 mj_data
当前值，第二次跑就不是从同一起点出发了。
```

⚠️ **这个细节很微妙**：随机化只改 x/y，**z 坐标沿用当前值**。
如果复用 `MjData`：

```
第 1 次随机化：z 从 0.75 开始 → 结束时 z = 0.78
第 2 次随机化：z 从 0.78 开始 ← 起点变了！
```
即使 seed 相同，结果也会不同 —— **测试会红，但根因是测试自己写错了。**

**② `mj_resetData`（95 行）**

把 `MjData` 恢复到模型定义的初始状态（`qpos0`）。
新建的 `MjData` 其实已经是初始态，这行是**防御性的**，明确表达意图。

**③ `mj_forward`（96-98 行）** ⭐ 容易漏

```python
# 必须 forward：_randomize_objects 要读 armbase site 的世界坐标，
# 而 site 位置只有在前向运动学算过之后才有效。
mujoco.mj_forward(model, data)
```

**什么是前向运动学（forward kinematics）**：

```
qpos（各关节角度）  →  mj_forward()  →  每个 body/site 的世界坐标
   [0, -1, 1.2, ...]                      armbase 在 (0.3, 0, 0.75)
```

**刚建好的 `MjData` 里，`site_xpos` 全是 0** —— 还没算过。
不调 `mj_forward` 就读 → 拿到全 0 → 随机化以原点为基准 → 物体全跑到地上。

📌 **MuJoCo 新手 top 3 错误之一。** 记住：
**读任何「世界坐标」之前，必须先 `mj_forward` 或 `mj_step`。**

**④ seed 走构造参数（86-89 行）** ⭐ 重要设计决策

```python
seed 走【构造参数】而非 config 字典：随机数生成器是有状态的，
一个 randomizer 对应一条随机流。若在 exec_randomization 里重设 seed，
连续调用两次会得到完全相同的场景 —— 那几乎肯定不是使用者想要的。
```

**对比两种设计**：

```python
# 设计 A：seed 在构造时（✅ 本项目）
r = SceneRandomizer(model, data, seed=42)
r.exec_randomization(cfg)    # 场景 1
r.exec_randomization(cfg)    # 场景 2（不同！随机流继续推进）

# 设计 B：seed 在每次调用时（❌）
r.exec_randomization(cfg, seed=42)   # 场景 1
r.exec_randomization(cfg, seed=42)   # 场景 1（完全一样！）
```

设计 B 下，采集 100 条数据会得到 **100 个完全相同的场景** ——
域随机化彻底失效，而且**没有任何报错**。

📌 **「一个 randomizer 对应一条随机流」** 是正确的心智模型：
seed 决定的是「这条流从哪开始」，不是「每次取数用什么种子」。

**⑤ `.copy()`（104 行）** ⚠️ 又一个容易漏的坑

```python
[np.asarray(randomizer._object_pose(name)).copy() for name in FREE_BODIES]
#                                          ↑ 必须
```

`_object_pose` 很可能返回的是 **`data.qpos` 的一个视图（view）**，
而不是独立数组。

```python
a = data.qpos[7:14]        # 视图！和 qpos 共享内存
mujoco.mj_step(model, data)
print(a)                   # 变了！因为底层内存被改了
```

不 `.copy()` → 第二次随机化会**同时改掉第一次的结果** → 两个数组永远相等
→ **测试永远绿，什么都没测**（又一个平凡解）。

📌 **NumPy 切片默认是视图，不是拷贝。** 这是 numpy 头号陷阱。

---

## 3.6 `_assert_identical` helper（108-117 行）—— 好的失败消息

```python
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
```

### 对比：裸断言 vs 诊断式失败

```python
# ❌ 裸断言
assert np.array_equal(first, second)
# 失败输出：
#   assert False
#    +  where False = array_equal(array([...]), array([...]))
#   （数组被截断，看不出差多少）

# ✅ 本项目
# 失败输出：
#   同一个 seed=42，两次随机化结果却不同 —— 随机流未被 seed 隔离
#     最大偏差: 0.034821756（期望 0，PRNG 是确定性算法）
#     第一次:   [0.312481 0.120043 0.750000 ...]
#     第二次:   [0.277659 0.089221 0.750000 ...]
```

### ⭐ 「最大偏差」为什么重要

它直接区分了两类完全不同的问题：

| 偏差量级 | 说明什么 |
|---|---|
| `1e-16` ~ `1e-9` | **浮点误差** —— 可能是并行归约顺序不同，不是 seed 问题 |
| `0.03` | **完全不同的随机数** —— seed 真的没生效 |

📌 **好的失败消息不只说「不相等」，还要帮人判断「为什么不相等」。**

### `pytest.fail` vs `assert`

`pytest.fail(msg)` = 无条件失败并打印 msg。
适合**需要构造复杂诊断信息**的场景 —— 先算 diff、格式化，再失败。

### 为什么期望是**精确相等**（`rtol=0, atol=0` 的思想）

```
PRNG（伪随机数生成器）是确定性算法：
    同样的 seed → 同样的比特序列 → 完全相同的浮点数
```

**不是「差不多」，是「一个 bit 都不差」。**
所以这里用 `np.array_equal`（精确）而非 `np.allclose`（容差）。

📌 如果这里用了容差，一个真实的 seed 泄漏可能被 `atol=1e-6` 吞掉。

---

## 3.7 核心测试（123-139 行）

```python
def test_config_seed_makes_randomization_reproducible(
    task_xml, base_randomization_config
):
    """【核心】同一个 seed 两次随机化，结果应完全相同。

    Day 3 写下时是红灯：randomization.py 有 25 处裸 np.random.*，
    消费进程级全局随机流；settings.seed 声明于 6 处 YAML，零个读取者。

    Step 4 修复：SceneRandomizer 接受 seed 参数，
    建 np.random.default_rng(seed) 实例，25 处改用 self.rng.*。
    """
    first = _randomize_once(task_xml, base_randomization_config, seed=42)
    second = _randomize_once(task_xml, base_randomization_config, seed=42)

    _assert_identical(
        first, second, "同一个 seed=42，两次随机化结果却不同 —— 随机流未被 seed 隔离"
    )
```

**这就是 TDD 的「红」**：写下这条时它是失败的，因为 seed 根本没人读。
修复后变绿。

📌 **docstring 记录了「写下时是什么状态」和「怎么修的」** ——
三个月后看代码的人能立刻理解这条测试的来历。

---

## 3.8 反向哨兵（142-164 行）⭐ 排除平凡解

```python
def test_different_seeds_produce_different_scenes(task_xml, base_randomization_config):
    """【反向哨兵】不同 seed 应得到不同场景。

    为什么需要这条：上一条测试有个平凡解 —— 如果随机化
    根本没执行（config 为 None、物体名写错、randomize 被跳过），
    两次结果自然完全相同，测试会【绿】但什么都没验证。

    Day 3 自检 2 实测证明了它不可省：注入 np.random.seed(42)
    这个"部分正确的假修复"时，本文件其他测试全绿，只有这条会红。
    """
    a = _randomize_once(task_xml, base_randomization_config, seed=42)
    b = _randomize_once(task_xml, base_randomization_config, seed=1234)

    assert not np.array_equal(a, b), (
        "seed=42 与 seed=1234 得到了完全相同的场景 —— "
        "随机化很可能根本没有执行，上一条测试的绿灯是平凡解"
    )
```

### ⭐ 155-156 行是本节精华

> Day 3 自检 2 实测证明了它不可省：注入 `np.random.seed(42)`
> 这个"部分正确的假修复"时，本文件其他测试全绿，**只有这条会红**。

**这是一次真实的变异验证**：

```
假修复：在 exec_randomization 开头加 np.random.seed(42)
    ↓
test_config_seed_makes_reproducible       → 绿 ✅（确实可复现了）
test_randomization_actually_moves_objects → 绿 ✅（物体确实动了）
test_different_seeds_produce_different    → 红 ❌  ← 只有它抓住了
```

因为假修复**写死了 42**，传 seed=1234 也会被覆盖成 42 →
两个 seed 得到相同场景 → 这条红。

📌 **这证明了「反向哨兵」不是理论洁癖，是真的能抓到 bug 的。**

### 注意 152-153 行的诚实记录

```python
注意：修复前这条会【偶然通过】（因为全局随机流本就每次不同），
修复后它才真正在验证 seed 的区分能力。
```

**这条测试在修复前是绿的** —— 但绿得没有意义（因为全局流本来就每次不同）。
修复后它才真正开始工作。

**面试价值**：能说清「一条测试在不同阶段的语义变化」，
说明你理解测试而不只是在写测试。

---

## 3.9 前提校验（167-191 行）

```python
def test_randomization_actually_moves_objects(task_xml, base_randomization_config):
    """【前提校验】随机化确实改变了物体位置。

    比上一条更基础：确认 exec_randomization 不是空操作。
    如果这条红了，前两条测试的结论全部无意义 —— 先修这个。

    这叫【测试的前提断言】：把「我以为成立的前提」写成可执行的检查。
    """
    ...
    before = np.concatenate([... for n in FREE_BODIES])
    randomizer.exec_randomization(base_randomization_config)
    after  = np.concatenate([... for n in FREE_BODIES])

    assert not np.array_equal(before, after), \
        "exec_randomization 执行前后物体位姿完全没变 —— 随机化是空操作"
```

### 三条测试构成的判据金字塔

```
        ┌─────────────────────────────────────┐
  第3层  │ 随机化真的在做事吗？（前提）          │  ← 最基础
        ├─────────────────────────────────────┤
  第2层  │ 不同 seed 给不同结果吗？（有区分度）  │
        ├─────────────────────────────────────┤
  第1层  │ 同 seed 给同结果吗？（确定性）        │  ← 最终目标
        └─────────────────────────────────────┘

  第3层红 → 第1、2层的结论全部无意义
```

📌 **失败诊断顺序**：从下往上看。底层前提不成立时，
上层的绿灯或红灯都不可信。

---

## 3.10 ⭐ 接线测试（194-254 行）—— 全文件最重要的一条

```python
def test_task_base_wires_yaml_seed_to_randomizer(task_xml, task_config_dir):
    """【接线测试】YAML 里的 seed 必须经 UniversalTaskBase 传到 SceneRandomizer。

    为什么单独写这条：
      本文件其他测试都直接构造 SceneRandomizer，绕过了 task_base。
      组件正确 != 调用方接对了线。
    """
```

### ⭐ 「组件正确 ≠ 接线正确」

前面 3 条测试都是这样写的：

```python
randomizer = SceneRandomizer(model, data, seed=42)     # ← 直接构造，手动传 seed
```

**它们证明了 `SceneRandomizer` 这个零件是好的。**

但真实用户不会手动构造 randomizer，他们的路径是：

```
编辑 YAML（seed: 42）
    ↓
UniversalTaskBase.__init__(robot_cfg, task_cfg, ...)     ← 这一段没被测到！
    ↓
SceneRandomizer(model, data, seed=???)
```

**中间这段「接线」如果断了，零件再好也没用。**

### 项目里所有的「接线缺陷」

```python
缺陷 J（键名不匹配）、seed 断链、
Day 2 缺陷 B（模板缺 observation 段）——
全都是"接线"缺陷：每个零件单看都对，装到一起不工作。
```

| 缺陷 | 零件本身 | 接线 |
|---|---|---|
| 缺陷 J | `_get_collision_radius` 逻辑正确 | YAML 写 `collision_radius`，代码读 `min_distance` |
| seed 断链 | `SceneRandomizer` 支持 seed | `task_base` 没把 YAML 的 seed 传下去 |
| 缺陷 B | 模板结构正确 | 缺 `observation` 段，继承者拿不到 |

📌 **这解释了为什么「单元测试 94% 覆盖率」仍然会有 bug**：
单测覆盖的是零件，**接线是零件之间的缝隙**。
必须有集成测试去走完整链路。

**企业术语**：这类测试叫**契约测试（contract test）**或**接线测试（wiring test）**。
Spring 里的 `@SpringBootTest`、Django 的 `Client()` 测试都是干这个的。

### 为什么改真实文件而不是内存 dict（204-207 行）

```python
为什么改真实文件而不是改内存 dict：
  UniversalTaskBase.__init__ 从【文件路径】加载配置。
  改一个已构造对象的 task_config.config 不会影响下次构造 ——
  这正是真实用户的操作路径（编辑 YAML 再运行）。
```

```python
# ❌ 改内存 —— 绕过了配置加载，测不到 extends 解析、类型转换
task.task_config.config["randomization"]["settings"]["seed"] = 42

# ✅ 改文件 —— 走完整加载链，就是用户的操作
tmp_cfg.write_text(text.replace("seed: null", "seed: 42"))
```

### 为什么临时文件放在 `tasks/` 目录内（208-210 行）

```python
为什么临时文件放在 tasks/ 目录内：
  place_block.yaml 头部有 extends: "templates/place_object.yaml"，
  是相对路径。放到 tmp_path 会解析失败。
```

⚠️ **pytest 有个内置 fixture `tmp_path`**（自动创建临时目录、自动清理），
本来应该用它。但**相对路径的 `extends` 会失效** —— 模板找不到。

📌 **这是一个「理想做法被现实约束否决」的例子。**
面试讲这种取舍比讲「我用了最佳实践」更有说服力。

### `try/finally` 保证清理（222-247 行）

```python
shutil.copy(src, tmp_cfg)
try:
    text = tmp_cfg.read_text(encoding="utf-8")
    assert "seed: null" in text, "前提不成立：源配置里没有 seed: null"
    tmp_cfg.write_text(text.replace("seed: null", "seed: 42"), encoding="utf-8")
    ...
    first = _run_via_task_base()
    second = _run_via_task_base()
finally:
    # 必须删掉 —— 测试绝不能给仓库留下文件。
    # 用 try/finally 保证断言失败时也会清理。
    tmp_cfg.unlink(missing_ok=True)
```

### ⚠️ 为什么必须 `try/finally`

```python
# ❌ 没有 finally
tmp_cfg.write_text(...)
assert something    # ← 如果这里失败，抛异常
tmp_cfg.unlink()    # ← 这行永远不会执行！垃圾文件留在仓库里
```

后果：`git status` 里多出一个 `_tmp_seed_wiring_test.yaml`，
而且**下次跑测试时它会被 `glob("*.yaml")` 扫到**，污染其他测试。

📌 **测试的第一守则：不留痕迹（leave no trace）。**

`missing_ok=True` = 文件不存在也不报错（Python 3.8+）。

### 前提断言（225 行）

```python
assert "seed: null" in text, "前提不成立：源配置里没有 seed: null"
```

如果哪天有人把 `place_block.yaml` 里的 `seed: null` 删了，
`.replace()` 会**什么都不替换**（静默！），测试仍然跑，
但测的是「没有 seed 的配置」—— **假绿灯**。

这条断言把它变成明确的失败。

### 企业扩展：更好的做法

```python
# ① 用 pytest 的 monkeypatch 自动恢复
def test_x(monkeypatch, tmp_path):
    ...

# ② 用自定义 fixture 封装 setup/teardown
@pytest.fixture
def seeded_config(task_config_dir):
    tmp = task_config_dir / "_tmp.yaml"
    shutil.copy(...)
    yield tmp                    # ← yield 之前是 setup
    tmp.unlink(missing_ok=True)  # ← yield 之后是 teardown，异常时也会执行
```

**方案 ② 是 pytest 惯用法**：`yield` 型 fixture 的清理逻辑
比 `try/finally` 更清晰，且可复用。

---

## 3.11 xfail 记录未修复缺陷（257-292 行）⭐

```python
@pytest.mark.xfail(
    strict=True,
    reason="已知缺陷：utils/get_random_texture() 的两个分支都用未受管控的"
    "随机源 —— if 分支用 stdlib random.choice（当前 TEXTURE_1K_PATH "
    "未配置故不可达），else 分支用 np.random 全局流（当前可达）。"
    "二者都不受 SceneRandomizer.rng 管控，贴图选择因此不可复现。"
    "未在 Step 4 修复：get_random_texture 是模块级函数，没有 rng 可用，"
    "修它要改公共函数签名并牵连全部 4 个调用方。",
)
def test_texture_randomization_respects_seed():
```

### ⭐ 「确定性的边界不是我改过的文件，而是整条调用链」（278-279 行）

```
Step 4 把 randomization.py 的 25 处改成了 self.rng.*
    ↓
但 randomization.py:553 调的是 utils.get_random_texture()
    ↓
那个函数完全不知道 rng 的存在  ← 随机性从 import 边界溜走了
```

**这是可复现性工程的核心难点**：

```
你的模块        ✅ 用了 rng
   ↓ import
第三方/工具模块  ❌ 用全局 random
   ↓ import
更深的依赖      ❌ 有自己的随机源
```

**只要链上有一处没被管控，整条链就不确定。**

📌 **企业实践：怎么找出所有的随机源**

```bash
# 找裸随机调用
grep -rn 'np\.random\.\|random\.\|torch\.rand\|\.shuffle(' --include='*.py' discoverse/

# Python 里常见的隐藏随机源
np.random.*          # numpy 全局
random.*             # stdlib 全局
torch.rand / cuda    # PyTorch（还需 torch.use_deterministic_algorithms(True)）
hash()               # ⚠️ 字符串 hash 有随机盐！需 PYTHONHASHSEED=0
set / dict 迭代顺序   # Python 3.7+ dict 有序，但 set 无序
os.listdir / glob    # 文件系统顺序，需显式 sorted()
多线程/并行归约        # 浮点加法不满足结合律
```

**最后两条是最阴的** —— 我在 [2.5](#25-loaded_objects-fixture92-113-行) 里用
`sorted(glob(...))` 就是为了防这个。

### 为什么「未修复」是一个合理的决策（263-264 行）

```python
未在 Step 4 修复：get_random_texture 是模块级函数，没有 rng 可用，
修它要改公共函数签名并牵连全部 4 个调用方。
```

**修复成本 vs 收益的判断**：

| | 影响 |
|---|---|
| 收益 | 贴图选择可复现 —— 但贴图不影响物理，只影响视觉 |
| 成本 | 改公共 API 签名，牵连 4 个调用方，可能破坏下游用户代码 |

**决策：钉住，不修。** 用 `xfail(strict=True)` 让它保持可见。

📌 **面试价值：这展示了「知道什么该修、什么不该修」的判断力。**
初级工程师看到 bug 就想修；高级工程师会评估影响面和成本。

---

# 第四部分：`test_mink_solver.py` 逐行（177 行）

## 4.1 什么是 IK，什么是「状态泄漏」

### IK（逆运动学，Inverse Kinematics）一句话解释

```
正运动学 FK：关节角度  →  末端在哪         （简单，一个公式）
逆运动学 IK：末端要去哪  →  关节角度该是多少  （难，通常要迭代求解）
```

机械臂控制的核心问题：「我想让夹爪到 (0.4, 0.1, 0.8)，六个关节各转多少度？」

**IK 通常没有解析解**，靠迭代逼近：

```
猜一个关节角 → 算末端在哪 → 差多远 → 往减小误差的方向调一点 → 重复
```

### 什么是「状态泄漏」（state leakage）

```python
solver.solve_ik(target_A)     # 第 1 次
solver.solve_ik(target_B)     # 第 2 次
solver.solve_ik(target_A)     # 第 3 次：输入和第 1 次完全一样
                              # 输出应该也一样 —— 但如果不一样，就是泄漏
```

**判定标准（文件头 docstring）**：

> 调用 N 次后的输出，是否**只由第 N 次的输入决定**？

如果第 2 次调用「留下了什么」影响到第 3 次 → **状态泄漏**。

### 为什么这是严重缺陷

```
数据采集时：同样的目标位姿，第 1 条和第 100 条数据算出不同的关节轨迹
    ↓
训练出的策略学到的是「噪声」而不是「规律」
    ↓
而且 —— 无法复现。你永远不知道那条奇怪的数据是怎么来的
```

📌 **状态泄漏 = 确定性被破坏的另一种形式。**
Day 3 的 seed 是「外部随机源」，Day 4 的泄漏是「内部残留状态」。

---

## 4.2 文件头：先实测再动手（1-9 行）

```python
"""MinkIKSolver 的状态隔离契约。

判定标准（见 devil-note-day04.md）：
    调用 N 次后的输出，是否只由第 N 次的输入决定？

实测（2026-08-04）：
    self.configuration      -> 不泄漏（solve_ik:99 每次入口被 update 覆盖）
    self.posture_task target -> 【泄漏】（:120 只在给 reference 时更新，否则沿用）
"""
```

### ⭐ 这段体现了一个关键工作方式：先证明，再修

**计划文档要求**：给 `solve_ik` 加 `try/finally` 恢复 `self.configuration`。

**实测结论**：`self.configuration` **根本不泄漏** —— 那个修复是多余的。

```python
def solve_ik(self, target_pos, target_ori, current_qpos, reference_qpos=None):
    ...
    self.configuration.update(current_qpos)      # ← 第 101 行，每次入口都覆盖
```

**它每次入口就被完全覆盖了**，上次的残留没有任何影响。

📌 **如果照着计划文档做，会加一段永远不会生效的防御代码** ——
增加复杂度、误导后来的读者「这里有过泄漏问题」。

**面试可以这样讲**：「计划要求给 IK 求解器加状态恢复。我先写了个判定实验，
发现两个候选状态里只有一个真的泄漏 —— 另一个每次入口就被覆盖了。
我只修了真实存在的那个，另一个写了测试钉住现状，防止有人日后把那行覆盖删掉。
**先证明缺陷存在，再动手修**，否则加的是没用的复杂度。」

---

## 4.3 fixture 设计（23-78 行）

### `solver_env`：module 级（23-65 行）

```python
@pytest.fixture(scope="module")
def solver_env(task_config_dir):
    """module 级：make_env + 模型编译不便宜，而本文件的用例
    都只【读】这些对象，真正可变的 solver 在每个用例里新建。
    """
```

**作用域的判断依据始终是「可变性」**：

| 对象 | 可变吗 | 作用域 |
|---|---|---|
| `model`（MjModel） | ❌ 只读 | module ✅ |
| `robot_config` | ❌ 只读 | module ✅ |
| `home_qpos`（已 `.copy()`） | ❌ | module ✅ |
| **`solver`（MinkIKSolver）** | ✅ **持有可变状态** | **function** ⚠️ |

⚠️ **注意 `data` 也在 `solver_env` 里，是可变的** ——
但它只用于**构造时**读取末端位姿，之后各个 solver 用自己的。这是可接受的折中。

### 关键：`home_qpos` 与 `.copy()`（46-48 行）

```python
home_qpos = model.key(0).qpos.copy()      # ← .copy() 必须
data.qpos[:] = home_qpos
mujoco.mj_forward(model, data)
```

**什么是 keyframe**：MJCF 里预定义的姿态，通常 `key(0)` 是「home」（初始姿态）。

```xml
<keyframe>
  <key name="home" qpos="0 -1 1.2 1.5708 -1.2 -1.5708 ..."/>
</keyframe>
```

`.copy()` 的理由同 [3.5⑤](#35-_randomize_once-helper78-105-行) —— `model.key(0).qpos` 是视图。

### `data.qpos[:] = home_qpos` 里 `[:]` 的意义

```python
data.qpos = home_qpos       # ❌ 替换 Python 引用，MuJoCo 底层 C 数组没变！
data.qpos[:] = home_qpos    # ✅ 原地写入，底层内存被更新
```

📌 **MuJoCo 的 `data.qpos` 是 C 数组的 numpy 视图。**
直接赋值只是让 Python 变量指向新对象，**物理引擎读的还是旧内存**。
必须用 `[:]` 做原地赋值。**这是 MuJoCo 新手 top 1 错误。**

### `pytest.skip` 守卫（43-44 行）

```python
if model.nkey == 0:
    pytest.skip("模型无 keyframe，MinkIKSolver 构造会失败")
```

`nkey` = keyframe 数量。没有 keyframe → `MinkIKSolver.__init__` 会
`raise ValueError`（见源码 79-80 行）。**前提不满足 → skip 而非 fail。**

### ⭐ 为什么用「当前末端位姿」做基准（60-64 行）

```python
# 取当前末端位姿做基准 —— 保证目标可达。
# 随手编一个坐标很可能不可达，届时 converged=False，
# 测试红了却和状态泄漏无关。
"ee_pos": data.site_xpos[site_id].copy(),
"ee_mat": data.site_xmat[site_id].reshape(3, 3).copy(),
```

**这是测试设计的关键考量**：

```python
# ❌ 随手编坐标
target = np.array([0.5, 0.5, 1.5])     # 可能超出工作空间！
# → IK 不收敛 → 测试红 → 但根因是「够不着」，不是「状态泄漏」

# ✅ 从当前位置出发，只挪一点
target = solver_env["ee_pos"] + np.array([0.08, 0.0, 0.0])   # 沿 x 挪 8cm
# → 一定可达 → 测试红了就一定是泄漏
```

📌 **通用原则：测试要隔离变量。**
让**唯一可能导致失败的原因**是你要测的那个东西。

### `site_xmat.reshape(3, 3)`

MuJoCo 把 3×3 旋转矩阵**扁平存成 9 个数**，读出来要 reshape。

### `make_solver` fixture（68-78 行）

```python
@pytest.fixture
def make_solver(solver_env):
    """每个用例新建 solver —— 它持有可变状态，绝不能跨用例复用。"""
    def _make():
        return MinkIKSolver(...)
    return _make
```

**「工厂即 fixture」模式**（同 `mj_model_factory`）：
返回一个**函数**而不是对象，让用例决定什么时候造、造几个。

**本例的必要性**：`test_posture_target_does_not_leak` 需要在**同一个 solver**
上连续调用 3 次（泄漏必须在同一实例内才能观察到）。

---

## 4.4 三条测试逐条解析

### ① `test_repeated_solve_is_deterministic`（81-98 行）—— 守护「不泄漏」的部分

```python
def test_repeated_solve_is_deterministic(solver_env, make_solver):
    """【已核实不泄漏】同参数连续调用两次，解应相同。

    这条守的是 self.configuration —— solve_ik:99 每次入口
    self.configuration.update(current_qpos) 已经隔离了它。
    计划文档要求加 try/finally 恢复 configuration，实测【不需要】。

    这条测试的价值是【防止有人日后把那行 update 删掉】。
    """
    solver = make_solver()
    target = solver_env["ee_pos"] + np.array([0.08, 0.0, 0.0])

    first,  _, _ = solver.solve_ik(target, solver_env["ee_mat"], solver_env["home_qpos"])
    second, _, _ = solver.solve_ik(target, solver_env["ee_mat"], solver_env["home_qpos"])

    np.testing.assert_allclose(first, second, atol=0, rtol=0)
```

**⭐ 这条测试测的是一个「已经正确」的行为。**

初看像是浪费 —— 为什么测一个没坏的东西？

📌 **因为测试的作用不只是「发现 bug」，还有「锁住正确行为」。**

```
今天：solve_ik:101 有 self.configuration.update(current_qpos)  → 不泄漏
明天：有人重构，觉得这行冗余，删掉                              → 泄漏
       ↓
   这条测试立刻红                                             ← 它的价值在这
```

**这叫「回归测试」**（regression test）：防止已修好/本来就对的东西再坏掉。

### `atol=0, rtol=0` 是什么意思

```python
np.testing.assert_allclose(first, second, atol=0, rtol=0)
#                                          ↑          ↑
#                                     绝对容差    相对容差
```

| 参数 | 含义 | 默认值 |
|---|---|---|
| `atol` | 绝对容差：`|a-b| <= atol` | `0` |
| `rtol` | 相对容差：`|a-b| <= rtol * |b|` | `1e-7` |

**两个都设 0 = 要求比特级完全相同。**

**为什么可以这么严**：IK 求解是**确定性数值算法** ——
同样的输入走同样的迭代路径，得到同样的浮点数。**不是「差不多」，是「一模一样」。**

⚠️ 如果用默认的 `rtol=1e-7`，一个真实的微小泄漏可能被吞掉。

---

### ② `test_posture_target_does_not_leak_across_calls`（109-139 行）⭐ 核心

```python
def test_posture_target_does_not_leak_across_calls(solver_env, make_solver):
    """【回归】reference_qpos 不应污染后续不传 reference 的调用。

    判定：调用 N 次后的输出，是否只由第 N 次的输入决定？
    第 1 次和第 3 次输入完全相同（同 target、同 qpos、都不给 reference），
    所以输出必须相同。
    """
    solver = make_solver()
    target = solver_env["ee_pos"] + np.array([0.08, 0.0, 0.0])
    ori  = solver_env["ee_mat"]
    home = solver_env["home_qpos"]

    reference = home.copy()
    reference[:6] += 0.3        # 一个明显不同的参考构型

    first, _, _ = solver.solve_ik(target, ori, home)                          # ①
    solver.solve_ik(target, ori, home, reference_qpos=reference)              # ② 污染源
    third, _, _ = solver.solve_ik(target, ori, home)                          # ③

    np.testing.assert_allclose(third, first, atol=0, rtol=0, err_msg="...")
```

### ⭐ 「1-2-3 夹心」测试模式

```
① 干净调用      → 记录基准输出
② 污染调用      → 传入会留下状态的参数
③ 重复①的调用   → 输入和①完全相同
                  ↓
        断言 ③ == ①，任何差异都来自②的残留
```

📌 **这是测状态泄漏的标准模式**，适用于任何有状态对象：
数据库连接、HTTP session、缓存、ORM 会话……

### 缺陷 U 的具体机制

**修复前的代码**（源码 123-126 行，现已注释掉）：

```python
if reference_qpos is not None:
    temp_config = mink.Configuration(self.mj_model)
    temp_config.update(reference_qpos)
    self.posture_task.set_target_from_configuration(temp_config)
# ← 没有 else 分支！不传 reference 时，posture_task 保持上次设的目标
```

`self.posture_task` 是**实例属性**，它的 target 一旦被设置就一直保留：

```
调用①：不传 reference → 不进 if → posture target = 构造时的 home
调用②：传 reference   → 进 if   → posture target = reference  ← 被改了
调用③：不传 reference → 不进 if → posture target 仍是 reference ← 泄漏！
```

**什么是 posture task**：IK 有无穷多解（冗余自由度），
`posture_task` 是个「软约束」，告诉求解器「在所有可行解里，
优先选**接近这个参考姿态**的那个」。

**所以 target 被污染 → 求解器的偏好变了 → 同样的末端目标得到不同的关节角。**

### 修复（源码 128-137 行）

```python
# ————————修复补充上缺少的调用
# 姿态任务目标：每次调用都显式设定，不沿用上一次。
temp_config = mink.Configuration(self.mj_model)
if reference_qpos is not None:
    temp_config.update(reference_qpos)
else:
    temp_config.update(self._default_posture_qpos)     # ← 补上的 else
self.posture_task.set_target_from_configuration(temp_config)
```

**关键改动**：把 `set_target_from_configuration` **挪出 if 块** ——
现在**每次调用都会设定**，不存在「沿用上次」的路径。

📌 **修复模式：「有条件地设置」→「无条件地设置，条件只决定设成什么」。**
这是消除状态泄漏的通用手法。

---

### ③ `test_default_posture_target_is_home_not_qpos0`（142-177 行）⭐ 来自失败的变异验证

```python
def test_default_posture_target_is_home_not_qpos0(solver_env, make_solver):
    """不传 reference 时，posture 目标应是构造时的 home，而非模型 qpos0。

    【这条测试来自一次失败的变异验证】（Day 4）：
    注释掉 solve_ik 里的 else 分支后，test_posture_target_does_not_leak
    仍然全绿 —— 说明它没能守住完整契约。
    """
```

### ⭐⭐ 这是全项目最值钱的一段经历，面试必讲

**变异验证的过程**：

```
① 修复完成，两条测试全绿 ✅
② 变异：把 else 分支注释掉
      else:
          temp_config.update(self._default_posture_qpos)
③ 重跑 → test_posture_target_does_not_leak 仍然绿 ❌❌❌
```

**测试没有抓住这个变异 → 说明测试守的不是完整契约。**

### 排查：为什么删了 else 还是不泄漏

```python
temp_config = mink.Configuration(self.mj_model)    # ← 每次新建
if reference_qpos is not None:
    temp_config.update(reference_qpos)
# else 被删掉了
self.posture_task.set_target_from_configuration(temp_config)   # ← 仍然每次都设
```

**真正消除泄漏的是「把 `set_target_from_configuration` 挪出 if 块」**，
不是 else 分支本身！

删掉 else 后，不传 reference 时 `temp_config` 保持**新建状态**，
而 `mink.Configuration(model)` 的默认值是 **`qpos0`**：

| | 值（airbot_play） | 来源 |
|---|---|---|
| `qpos0` | `[0, 0, 0, 0, 0, 0]` | MJCF 模型定义的零位 |
| `key(0).qpos`（home） | `[0, -1, 1.2, 1.5708, -1.2, -1.5708]` | keyframe 定义的初始姿态 |

**两者都不泄漏，但默认姿态取谁是另一个契约。**

### ⭐ 结论（154-156 行）

```python
else 分支的作用因此不是「修泄漏」，而是「保持原有默认行为」：
构造时 _setup_ik_tasks 用的就是 key(0).qpos。
```

**一个改动同时做了两件事，我原本只理解了其中一件。**
变异验证把这个盲区暴露出来了。

### 补上的测试

```python
import mink

solver = make_solver()
home = solver_env["home_qpos"]

solver.solve_ik(solver_env["ee_pos"], solver_env["ee_mat"], home)   # 不传 reference

expected = mink.Configuration(solver_env["model"])
expected.update(home)                    # 期望值：home
n = len(solver.posture_task.target_q)

np.testing.assert_allclose(
    solver.posture_task.target_q,
    expected.q[:n],
    atol=0, rtol=0,
    err_msg="不传 reference 时 posture 目标不是 home —— "
            "可能退化成了 qpos0（else 分支缺失或失效）",
)
```

**这条测试直接检查内部状态**（`solver.posture_task.target_q`），
而不是通过输出间接推断。

⚠️ **这违反了「只测公开行为」的常规建议** —— 但这里是有意的：
「默认姿态取 home 而非 qpos0」这个契约，**从输出上很难区分**
（两者可能给出相近的解）。直接断言内部状态更可靠。

📌 **企业实践的权衡**：
- 优先测公开行为（重构时不会误伤）
- 但当某个内部契约**从外部无法可靠观察**时，直接测它 —— 并在 docstring 里
  写清楚为什么（像本例这样）

### 面试叙事（完整版）

「Day 4 我修了一个 IK 求解器的状态泄漏。修完两条测试都绿了，
但我做了变异验证 —— 把修复代码注释掉，测试**居然还是绿的**。

排查后发现：我的修复其实同时做了两件事。真正消除泄漏的是把
`set_target` 挪出 if 块，而 else 分支的作用是**保持默认姿态是 home 而非 qpos0**。
我原本只理解了第一件，所以测试只覆盖了一半契约。

我补了第三条测试专门锁住默认姿态。**这次变异验证的价值不是发现代码 bug，
是发现我对自己修复的理解不完整** —— 如果没做这一步，
三个月后有人把 else 删掉，测试全绿，默认姿态静默变成 qpos0。」

---

# 第五部分：`test_task_matrix.py` 逐行（123 行）

## 5.1 ⚠️ 这不是测试，是数据采集实验（1-15 行）

```python
"""9 机器人 × 5 任务的 flake 矩阵采样。

⚠️ 这不是常规回归测试 —— 它是【数据采集实验】：
   常规测试问「代码对不对」，本文件问「这个组合的成功率是多少」。
   因此默认 skip，只在显式指定 -m flake 时运行。
"""
```

### 常规测试 vs 采样实验

| | 常规测试 | 本文件 |
|---|---|---|
| 问题 | 代码对不对？ | 成功率是多少？ |
| 断言 | 有明确的对错 | **故意不断言成功** |
| 运行频率 | 每次提交 | 手动 / nightly |
| 耗时 | 秒级 | **数分钟到小时** |
| 失败含义 | 有 bug | （没有「失败」，只有数据） |

📌 **把它放在 `tests/` 目录里，是为了复用 pytest 的基础设施**：
参数化、并行（`-n`）、重复（`--count`）、报告（`--json-report`）。

**但必须防止它被常规 CI 跑到** —— 见 [5.2](#52-pytestmark-与默认排除24-行)。

### 为什么用 subprocess 而非进程内调用（11-14 行）

```python
为什么用 subprocess 而非进程内调用 main()：
    universal_task_runtime 会加载 MuJoCo 模型、创建编码器、写文件。
    进程内重复调用会累积全局状态（Day 2-4 反复遇到的主题）。
    子进程保证每次运行完全隔离 —— 代价是 ~0.3s 的启动开销，值得。
```

**这是 Day 2-4 主题的延续**：全局状态污染。

```python
# ❌ 进程内
for i in range(50):
    universal_task_runtime.main(robot, task)   # 第 50 次和第 1 次环境不同了
    # MuJoCo 全局上下文、渲染器、matplotlib figure、打开的文件句柄……

# ✅ 子进程
subprocess.run([sys.executable, RUNTIME, ...])  # 每次全新解释器
```

**代价与收益**：

| | 进程内 | 子进程 |
|---|---|---|
| 单次开销 | ~0 | **+0.3s**（解释器启动 + import） |
| 2250 次总开销 | 0 | **+11 分钟** |
| 隔离性 | ❌ 累积污染 | ✅ 完全隔离 |

📌 **2250 次采样，多花 11 分钟换「数据可信」，绝对值得。**
如果数据被污染，跑再多次也是废的。

---

## 5.2 `pytestmark` 与默认排除（24 行）

```python
pytestmark = pytest.mark.flake
```

配合 `pyproject.toml`：

```toml
addopts = "--strict-markers --tb=short -ra -m 'not flake'"
#                                          ↑ 默认排除 flake
markers = [
    "flake: flake 率采样实验，非常规回归；需显式 -m flake 运行，单次数分钟起",
]
```

**效果**：

```bash
$PY -m pytest                    # 45 个用例被 deselect，不跑
$PY -m pytest -m flake           # ← 必须显式指定才跑
```

📌 **「默认安全」的设计**：危险/昂贵的东西默认关闭，需要显式开启。
同理：`--dry-run` 默认开、生产部署默认需要确认、删除操作默认需要 `--force`。

⚠️ 注意 `-m flake` 会**覆盖** addopts 里的 `-m 'not flake'`（后者被后指定的覆盖）。

---

## 5.3 `_classify` 分桶函数（49-87 行）⭐ 核心

```python
def _classify(stdout: str, returncode: int) -> dict:
    if returncode == -9 or "TIMEOUT" in stdout:
        return {"bucket": "BUCKET3_超时", "state": None, "dist": None}

    m_state = re.search(r"完成状态: (\d+)/(\d+)", stdout)
    m_dist  = re.search(r"实际距离=([\d.]+)", stdout)
    dist = float(m_dist.group(1)) if m_dist else None

    if "任务成功: ✅" in stdout:
        return {"bucket": "SUCCESS", "state": m_state.group(0) if m_state else None, "dist": dist}

    if m_state is None:
        return {"bucket": "BUCKET4_配置崩溃", "state": None, "dist": None}   # 没跑到统计阶段

    done, total = int(m_state.group(1)), int(m_state.group(2))
    if done < total:
        return {"bucket": "BUCKET1_早期IK失败", "state": f"{done}/{total}", "dist": dist}
    return {"bucket": "BUCKET2_判据失败", "state": f"{done}/{total}", "dist": dist}
```

### 判定顺序很重要

```
① returncode == -9 或 输出含 TIMEOUT   →  BUCKET3（超时）
② 输出含「任务成功: ✅」                →  SUCCESS
③ 连「完成状态」都没打印                →  BUCKET4（崩溃）  ⭐
④ 完成状态 done < total                →  BUCKET1（够不着）
⑤ 完成状态 done == total 但没成功       →  BUCKET2（抓不住）
```

📌 **顺序不能乱**：③ 必须在 ④⑤ 之前 —— 崩溃时 `m_state` 是 `None`，
`int(m_state.group(1))` 会 `AttributeError`。

### `returncode == -9` 是什么

**负的 returncode = 进程被信号杀死**，`-9` 对应 `SIGKILL`（信号 9）。

```
subprocess.run(..., timeout=120) 超时
    ↓
Python 发 SIGKILL 杀掉子进程
    ↓
returncode = -9
```

📌 **Unix 约定**：`returncode = -N` 表示被信号 N 杀死。
常见：`-9` SIGKILL、`-15` SIGTERM、`-11` SIGSEGV（段错误）。

### 正则表达式拆解

```python
re.search(r"完成状态: (\d+)/(\d+)", stdout)
#                    ↑ 捕获组1  ↑ 捕获组2
```

| 部分 | 含义 |
|---|---|
| `r"..."` | 原始字符串，反斜杠不转义（正则必用） |
| `\d` | 一个数字字符 |
| `+` | 前面的东西出现 1 次或多次 |
| `(...)` | **捕获组**，可以用 `.group(n)` 取出 |

```python
m = re.search(r"完成状态: (\d+)/(\d+)", "完成状态: 5/17")
m.group(0)   # "完成状态: 5/17"   ← 整个匹配
m.group(1)   # "5"                ← 第一个括号
m.group(2)   # "17"               ← 第二个括号
```

`([\d.]+)` = 一个或多个「数字或点」→ 匹配浮点数 `0.0342`。

### ⚠️ 用正则解析 stdout 是技术债

**这是 Day 13-14 要解决的问题** ——「结构化结果契约替代 stdout 字符串判定」。

**为什么 stdout 解析很脆**：

| 问题 | 后果 |
|---|---|
| 有人改了输出文案（`任务成功` → `Task Success`） | 分桶全错，**静默** |
| 有人加了颜色代码（ANSI 转义） | 正则匹配不上 |
| 输出被缓冲截断 | 匹配不到 |
| emoji `✅` 在不同终端编码不同 | 匹配失败 |

**更严重的是：出错时不会报错，只会「分桶不准」。**

📌 **Day 13-14 的改进方向**（见 [第九部分](#93-用结构化契约替代-stdout-解析)）：
让 runtime 输出 JSON，测试读 JSON 而非 grep 文本。

**面试价值**：能说清「我当时为什么这么做，以及它的问题在哪，后来怎么改的」——
展示的是**演进能力**而不是一次做对。

---

## 5.4 双层参数化（90-92 行）

```python
@pytest.mark.parametrize("robot", ROBOTS)     # 9 个
@pytest.mark.parametrize("task", TASKS)       # 5 个
def test_task_combination(robot, task, repo_root, record_property):
```

**两个 `parametrize` 叠加 = 笛卡尔积** = 9 × 5 = **45 个用例**。

```
test_task_combination[cover_cup-airbot_play]
test_task_combination[cover_cup-arx_l5]
...
test_task_combination[stack_block-xarm7]
```

配合 `--count=50` → 45 × 50 = **2250 次运行**。

📌 **一行装饰器生成 45 个用例** —— 这就是为什么要把实验放进 pytest：
参数化、并行、报告全部免费。

---

## 5.5 ⭐ 故意不断言成功（94-101 行）

```python
"""跑一次 robot × task，把分桶结果记进报告。

⚠️ 本用例【故意不断言成功】—— 它是采样器，不是质量门。
断言成功率会让 45 个组合里一大半永远红，测试失去意义。
真正的判定留给 Step 5 的分析报告。

唯一的断言：进程不能是配置崩溃（BUCKET4）——
那是确定性缺陷，应该被修，不该被当成 flake 容忍。
"""
```

### ⭐ 这是本文件最重要的设计判断

**如果断言成功会怎样**：

```python
assert result["bucket"] == "SUCCESS"     # ❌
```

→ 45 个组合里 **一大半永远红**（真实成功率只有 48.8%）
→ 红色变成常态
→ **没人再看这个测试的结果**
→ 测试失去全部价值

📌 **「测试红了」必须意味着「有东西坏了」。**
如果红是常态，红就不再是信号，而是噪声。

### 但有一条断言（120-123 行）

```python
if result["bucket"] == "BUCKET4_配置崩溃":
    pytest.fail(
        f"{robot} × {task} 配置缺陷（非 flake）：{proc.stdout.strip().splitlines()[-1]}"
    )
```

**为什么只对 BUCKET4 断言**：

| 桶 | 性质 | 该断言吗 |
|---|---|---|
| BUCKET1/2（IK失败/抓失败） | **随机的**，是机器人能力边界 | ❌ 不该 —— 那是产品属性 |
| BUCKET3（超时） | 可能随机 | ❌ 不该 |
| **BUCKET4（配置崩溃）** | **100% 确定性缺陷** | ✅ **该** —— 那是 bug |

📌 **判断依据：这件事是「该修的 bug」还是「产品的当前能力」？**
只对前者断言。

`proc.stdout.strip().splitlines()[-1]` = 取输出最后一行（通常是异常消息），
让失败消息直接告诉你崩在哪。

---

## 5.6 `subprocess.run` 逐参数解析（102-110 行）

```python
proc = subprocess.run(
    [sys.executable, RUNTIME, "-r", robot, "-t", task, "-1", "--headless"],
    cwd=str(repo_root),
    capture_output=True,
    text=True,
    timeout=TIMEOUT_S,
    env={**os.environ, "MUJOCO_GL": "osmesa"},
    check=False,
)
```

| 参数 | 作用 | ⚠️ 注意 |
|---|---|---|
| `[sys.executable, ...]` | **列表形式**传参 | ✅ 不经过 shell，无注入风险、无需转义 |
| `sys.executable` | **当前** Python 解释器的绝对路径 | ✅ 保证子进程和父进程同一个环境（不是 PATH 上的 `python`） |
| `cwd=repo_root` | 工作目录 | 脚本里的相对路径才能解析对 |
| `capture_output=True` | 捕获 stdout/stderr | 等价于 `stdout=PIPE, stderr=PIPE` |
| `text=True` | 输出是 `str` 而非 `bytes` | 不加的话 `"任务成功" in stdout` 会 TypeError |
| `timeout=120` | 超时杀进程 | 超时抛 `TimeoutExpired`（⚠️ 见下） |
| `env={**os.environ, ...}` | **继承**环境 + 覆盖 `MUJOCO_GL` | ⚠️ 不能只传 `{"MUJOCO_GL": ...}`，那样 PATH 都没了 |
| `check=False` | 非零退出码**不抛异常** | 本例靠 returncode 分类，非零是预期输入 |

### `check=False` 的重要性（109 行注释）

```python
check=False,  # 本用例靠 returncode 分类，非零是预期输入而非异常
```

```python
check=True  → 子进程退出码非 0 时抛 CalledProcessError
check=False → 不抛，自己检查 proc.returncode
```

**本例任务失败是「正常数据」，不是异常** —— 必须 `check=False`。

### `env={**os.environ, "MUJOCO_GL": "osmesa"}` 的字典展开

```python
{**os.environ, "MUJOCO_GL": "osmesa"}
# 等价于：复制所有现有环境变量，然后覆盖 MUJOCO_GL
```

⚠️ **常见错误**：

```python
env={"MUJOCO_GL": "osmesa"}     # ❌ 子进程没有 PATH、没有 HOME、没有 CONDA_PREFIX
                                #    → 大概率直接找不到 python 或库
```

### ⚠️ 一个真实的 bug：两个 timeout 打架

**实验元数据里如实记录了这个问题**：

```yaml
caveats:
  - BUCKET3 的 12 例里至少 1 例是撞上 pytest 全局 timeout=60s
    而非任务真超时 —— pyproject.toml 的 timeout 先于用例内的
    TIMEOUT_S=120 生效，导致归桶不准。
```

```
pyproject.toml:  timeout = 60         ← pytest-timeout，管整个用例
test_task_matrix: TIMEOUT_S = 120     ← subprocess，管子进程

用例跑到 60s → pytest 先杀掉整个用例 → subprocess 的 120s 永远等不到
```

📌 **教训：多层超时必须有明确的层级关系**（外层 > 内层）。
本例是外层 60 < 内层 120，内层配置形同虚设。

**正确做法**：给这个用例单独放宽 —— `@pytest.mark.timeout(180)`。

**面试价值**：主动讲出自己数据里的测量误差，可信度远高于「一切完美」。

---

## 5.7 `record_property`（113-118 行）

```python
record_property("robot", robot)
record_property("task", task)
record_property("bucket", result["bucket"])
record_property("state", result["state"])
record_property("dist", result["dist"])
```

`record_property` 是 **pytest 内置 fixture**，把键值对写进测试报告。

```bash
pytest --junitxml=report.xml       # → <property name="bucket" value="BUCKET2..."/>
pytest --json-report               # → JSON 里的 metadata
```

### 为什么用它而不是 `print`

| | print | record_property |
|---|---|---|
| 输出位置 | stdout，混在日志里 | **结构化字段** |
| 并行时 (`-n 8`) | 交错混乱 | ✅ 归属到正确的用例 |
| 后续处理 | 要写正则解析 | ✅ 直接读 XML/JSON |

📌 **这是「结构化输出 > 文本输出」原则的一次正确应用** ——
讽刺的是，同一个文件里的 `_classify` 还在解析别人的 stdout。
Day 13-14 就是把这个原则推广到整条链路。

---

# 第六部分：`gen_flake_report.py` 逐行（149 行）

## 6.1 matplotlib 的无头设置（22-24 行）⚠️ 顺序不能错

```python
import matplotlib
matplotlib.use("Agg")            # 无显示器环境必须，且必须在 pyplot 之前
import matplotlib.pyplot as plt
```

### 什么是 backend

matplotlib 的 **backend** 决定图往哪画：

| backend | 输出 | 需要显示器 |
|---|---|---|
| `TkAgg` / `Qt5Agg` | **弹窗** | ✅ 需要 |
| **`Agg`** | **只写文件** | ❌ 不需要 |

**服务器 / CI / Docker 里没有显示器** → 用默认 backend 会报：

```
RuntimeError: Invalid DISPLAY variable
```

### ⚠️ 为什么必须在 `import pyplot` 之前

```python
# ❌ 顺序错了，无效
import matplotlib.pyplot as plt
matplotlib.use("Agg")            # 太晚了！pyplot 导入时已经选定 backend

# ✅ 正确
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
```

📌 **这违反了 PEP 8「import 都放最上面」** —— 所以要写注释说明，
否则会被 lint 工具或好心的同事「修正」掉。

**企业实践替代方案**：设环境变量，无需改代码：
```bash
export MPLBACKEND=Agg
```

---

## 6.2 ⚠️ 文件头声明 BUCKET4 的处理（13-15 行）

```python
⚠️ BUCKET4（配置崩溃）在热力图中标为 "CFG" 而非计入成功率 ——
   它 100% 复现、无随机性，混进 flake 统计会让那一格永远是黑的，
   误导人去调 IK 容差，而真正的问题是一行配置。
```

**把关键决策写在文件头**，而不是埋在代码里 —— 读脚本的人第一眼就看到。

---

## 6.3 `load` 函数（41-46 行）

```python
def load(csv_path):
    cells = defaultdict(list)
    with open(csv_path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            cells[(r["robot"], r["task"])].append(r["bucket"])
    return cells
```

### `csv.DictReader` 是什么

把 CSV 每行读成**字典**，用表头做键：

```csv
task,robot,rep,bucket,state,dist,outcome,duration_s
cover_cup,airbot_play,1,BUCKET3_超时/未记录,,,failed,60.12
```
```python
r = {"task": "cover_cup", "robot": "airbot_play", "rep": "1", "bucket": "BUCKET3_超时/未记录", ...}
```

✅ 比 `csv.reader` + `row[3]` 好 —— **列顺序变了不会静默取错值**。

### `defaultdict(list)` 是什么

```python
# 普通 dict
d = {}
d[key].append(x)              # ❌ KeyError！key 还不存在

d = {}
if key not in d: d[key] = []  # 要手动初始化
d[key].append(x)

# defaultdict
d = defaultdict(list)
d[key].append(x)              # ✅ key 不存在时自动创建 []
```

**结果结构**：
```python
cells[("airbot_play", "cover_cup")] = ["BUCKET3...", "BUCKET2...", "SUCCESS", ...]   # 50 个
```

⚠️ `encoding="utf-8"` 必须显式写 —— bucket 名含中文，
Windows 上默认编码是 GBK 会乱码/报错。

---

## 6.4 `heatmap` 函数：BUCKET4 的剔除逻辑（49-105 行）⭐

```python
rate = np.full((len(TASKS), len(ROBOTS)), np.nan)     # 5×9 矩阵，初始全 NaN
label = {}

for i, task in enumerate(TASKS):
    for j, robot in enumerate(ROBOTS):
        buckets = cells.get((robot, task), [])
        if not buckets:
            continue

        valid = [b for b in buckets if b != B4]        # ⭐ 剔除配置崩溃
        n_cfg = len(buckets) - len(valid)

        if not valid:                                   # 整格都是配置崩溃
            label[(i, j)] = "CFG\n100%"
            continue

        rate[i, j] = sum(b == "SUCCESS" for b in valid) / len(valid) * 100
```

### ⭐ 三种情况的区分

| 情况 | `rate` 值 | 显示 | 含义 |
|---|---|---|---|
| 有有效数据 | 0-100 | `62%\nGRASP` | 正常统计 |
| **整格都是 BUCKET4** | **NaN** | **灰色 `CFG 100%`** | **测了，但每次都崩** |
| 完全没数据 | NaN | `-` | 没测 |

### `np.nan` 与「留白 vs 灰色」（77-80 行）

```python
# NaN（整格都是配置崩溃）单独染成灰色，而不是留白 ——
# 留白会被误读为「没测」，而实际是「测了，但每次都崩」。
cmap = plt.get_cmap("RdYlGn").copy()
cmap.set_bad("#9e9e9e")                    # 「坏值」（NaN）的颜色
im = ax.imshow(np.ma.masked_invalid(rate), cmap=cmap, vmin=0, vmax=100, aspect="auto")
```

📌 **「没测」和「测了但全崩」是完全不同的信息，视觉上必须能区分。**
这是数据可视化的诚实性问题 —— 图不能误导读者。

| 函数 | 作用 |
|---|---|
| `plt.get_cmap("RdYlGn")` | 红-黄-绿 色阶（低=红，高=绿） |
| `.copy()` | ⚠️ 必须 —— 直接改全局 cmap 会影响其他图 |
| `cmap.set_bad(color)` | 设定 NaN/masked 值的颜色 |
| `np.ma.masked_invalid(rate)` | 把 NaN 标记成「masked」，让 `set_bad` 生效 |
| `vmin=0, vmax=100` | **固定色阶范围** ⭐ |

### ⭐ `vmin` / `vmax` 为什么重要

不指定 → matplotlib 按**数据的实际范围**自动缩放：

```
数据范围 40%-60%  →  40% 被染成纯红，60% 被染成纯绿
                     视觉上像是「有的极差有的极好」，实际都在中间
```

📌 **固定 0-100 保证颜色的含义在不同图之间一致**，
可以横向对比不同时间跑的实验。**这是数据可视化的基本诚实性。**

### 单元格文字与自适应颜色（89-95 行）

```python
for i in range(len(TASKS)):
    for j in range(len(ROBOTS)):
        txt = label.get((i, j), "-")
        v = rate[i, j]
        color = "white" if (np.isnan(v) or v < 25 or v > 88) else "black"
        ax.text(j, i, txt, ha="center", va="center", fontsize=7.5, color=color)
```

**深色背景（很红 <25 或很绿 >88）用白字，中间的浅色用黑字。**

📌 **无障碍设计（accessibility）的基本功**：
保证文字与背景有足够对比度。**WCAG 标准要求对比度 ≥ 4.5:1。**

### 标注主导失败模式（68-74 行）⭐

```python
txt = f"{rate[i, j]:.0f}%"
if fails:
    top = Counter(fails).most_common(1)[0][0]
    txt += f"\n{SHORT.get(top, top)}"
if n_cfg:
    txt += f"\n(cfg {n_cfg})"
```

**每格显示两行信息**：

```
  62%        ← 成功率
 GRASP       ← 主导失败模式（抓不住）
```

`Counter(fails).most_common(1)[0][0]`：

```python
Counter(["BUCKET1", "BUCKET2", "BUCKET2"])
# Counter({'BUCKET2': 2, 'BUCKET1': 1})
.most_common(1)      # [('BUCKET2', 2)]     ← 出现最多的 1 个
[0]                  # ('BUCKET2', 2)
[0]                  # 'BUCKET2'
```

📌 **「成功率 + 主导失败模式」两个数字一起，才是可行动的。**
只有成功率 → 不知道往哪修。

`SHORT.get(top, top)` = 用短名（`GRASP`），查不到就用原名 —— **防御性写法**。

---

## 6.5 `failure_modes` 堆叠条形图（108-134 行）

```python
def failure_modes(cells, out_path):
    """回答的问题：这个机器人的失败是【够不着】还是【抓不住】？
    两者的修复方向完全不同。
    """
    b1 = np.zeros(len(ROBOTS))
    b2 = np.zeros(len(ROBOTS))
    for j, robot in enumerate(ROBOTS):
        buckets = [b for t in TASKS for b in cells.get((robot, t), []) if b != B4]
        c = Counter(buckets)
        b1[j] = c.get("BUCKET1_早期IK失败", 0)
        b2[j] = c.get("BUCKET2_判据失败", 0)

    ax.bar(x, b1, label="BUCKET1  early IK failure (unreachable)", color="#4C72B0")
    ax.bar(x, b2, bottom=b1, label="BUCKET2  grasp failure (reached but slipped)", color="#DD8452")
    #             ↑ 堆叠的关键：第二组从第一组的顶部开始画
```

### 嵌套列表推导式

```python
[b for t in TASKS for b in cells.get((robot, t), []) if b != B4]
#    ↑外层循环          ↑内层循环                      ↑过滤
```
等价于：
```python
result = []
for t in TASKS:
    for b in cells.get((robot, t), []):
        if b != B4:
            result.append(b)
```
**把一个机器人在全部 5 个任务上的结果拍平成一个列表**（250 次运行，剔除 BUCKET4 后更少）。

### `bottom=b1` —— 堆叠条形图的原理

```
      ┌──────┐  ← BUCKET2 从 b1 的高度开始画
      │ B2   │
      ├──────┤  ← b1 的顶部
      │ B1   │
      └──────┘  ← 0
```

📌 **这张图回答的问题比热力图更聚焦**：
不是「哪个组合差」，而是「**这个机器人差在哪个环节**」。

```
airbot_play：B2 占绝大多数  →  够得着但抓不住  →  调夹爪/摩擦
iiwa14：    B1 占绝大多数  →  根本够不着      →  调摆位/工作空间
```

**这就是「失败率是『机器人 × 任务』的匹配属性」这个结论的证据。**

---

## 6.6 `main` 与命令行参数（137-149 行）

```python
def main():
    csv_path = Path(sys.argv[1] if len(sys.argv) > 1
                    else "docs/experiments/flake-2026-08-07.csv")
    out_dir = Path(sys.argv[2] if len(sys.argv) > 2 else "docs/report/assets")
    out_dir.mkdir(parents=True, exist_ok=True)

    cells = load(csv_path)
    heatmap(cells, out_dir / "flake-heatmap.png")
    failure_modes(cells, out_dir / "flake-failure-modes.png")

if __name__ == "__main__":
    main()
```

| 写法 | 作用 |
|---|---|
| `sys.argv[1] if len(sys.argv) > 1 else 默认值` | 位置参数 + 默认值 |
| `mkdir(parents=True, exist_ok=True)` | 创建多级目录；已存在不报错 |
| `out_dir / "x.png"` | `pathlib` 的路径拼接（跨平台，优于字符串 `+`） |
| `if __name__ == "__main__"` | 只在直接运行时执行，被 import 时不执行 |

📌 **企业实践**：参数多起来应该换 `argparse`（像 `trace_chain.py` 那样），
能自动生成 `--help`、校验类型、支持可选参数。
本脚本只有 2 个位置参数，`sys.argv` 够用 —— **不要过度工程化**。

---

# 第七部分：命令行逐字解析

## 7.1 环境准备

```bash
cd /home/ubuntu22/workspaces/airbot-play/DISCOVERSE
source scripts/dev/env.sh
```

⚠️ **`source` 不跨命令持久** —— 每个 `Bash` 调用是独立进程：

```bash
# ❌ 错的 —— 两条命令是两个进程，第二条里 $PY 是空的
source scripts/dev/env.sh
$PY -m pytest

# ✅ 对的 —— 用 && 串在同一条命令里
source scripts/dev/env.sh && $PY -m pytest tests/ -v
```

---

## 7.2 Day 3：确定性验证

```bash
# 只跑确定性专项
source scripts/dev/env.sh && $PY -m pytest -m determinism -v

# 跑单个文件
$PY -m pytest tests/simulation/test_determinism.py -v

# 只跑核心那条
$PY -m pytest tests/simulation/test_determinism.py::test_config_seed_makes_randomization_reproducible -v
#                                                ↑↑ 两个冒号分隔文件和用例名
```

### 侦查命令：seed 到底断在哪一层

```bash
# ① 谁声明了 seed？
grep -rn 'seed' discoverse/configs/tasks/ discoverse/configs/robots/
# → 6 处 YAML 写了 settings.seed

# ② 谁读了 seed？
grep -rn "get('seed'\|\[.seed.\]\|seed=" discoverse/universal_manipulation/
# → 修复前：0 处

# ③ 有多少处裸随机？
grep -c 'np\.random\.' discoverse/universal_manipulation/randomization.py
# → 25

# ④ 修复后自查：只剩「刻意保留」的那些
grep -n 'np\.random\.' discoverse/universal_manipulation/randomization.py
# → 实测剩 2 处，都不是裸随机调用：
#     :31  注释里提到 np.random.seed()（在解释为什么不用它）
#     :35  self.rng = np.random.default_rng(seed)   ← 建生成器实例，这正是修复本身
#
# ⚠️ 别用 grep -c 数个数然后期望是 0 —— default_rng 也匹配 'np.random.'，
#    永远不会归零。要看的是「还有没有 np.random.uniform/random/integers
#    这类【取数】调用」，而不是这个字符串出现几次：
grep -nE 'np\.random\.(uniform|random|randint|integers|normal|choice|rand)\b' \
    discoverse/universal_manipulation/randomization.py
# → 应该输出空（修复前是 25 处）
```

📌 **①②③ 这三个命令构成了一条完整的「断链诊断」**：
声明处 6 → 读取处 0 → 裸随机 25。**三个数字讲完了整个缺陷。**

### 验证并行安全（Day 3 的回报）

```bash
# 装依赖
$PY -m pip install pytest-repeat pytest-xdist

# 同一条测试重复跑 3 次
$PY -m pytest tests/simulation/ --count=3 -v
# 实测：12 passed, 3 xfailed  （4 条测试 × 3 次 = 12）

# 并行跑
$PY -m pytest tests/ -n 4
```

| 参数 | 来自 | 作用 |
|---|---|---|
| `--count=N` | `pytest-repeat` | 每条测试**重复** N 次（测 flake） |
| `-n N` | `pytest-xdist` | 用 N 个**进程并行**（测隔离性 + 提速） |
| `-n auto` | `pytest-xdist` | 进程数 = CPU 核数 |

⚠️ **两者的区别**：`--count` 测「重复跑稳不稳」，`-n` 测「并行跑会不会互相污染」。
**Day 3 用 Generator 而非全局 seed，就是为了让 `-n 8` 的数据可信。**

---

## 7.3 Day 4：IK 与变异验证

```bash
# 跑 IK 测试
$PY -m pytest tests/unit/test_mink_solver.py -v

# 撤销 xfail 后确认变绿（预期看到 XPASS(strict) -> FAILED 再改回来）
$PY -m pytest tests/unit/test_mink_solver.py -v -ra
```

### ⭐ 变异验证的完整操作

```bash
# ① 确认全绿
$PY -m pytest tests/unit/test_mink_solver.py -v

# ② 手动注释掉修复代码（mink_solver.py 的 else 分支）
#    else:
#        temp_config.update(self._default_posture_qpos)

# ③ 重跑 —— 必须有测试变红
$PY -m pytest tests/unit/test_mink_solver.py -v
#    全绿 = 测试是摆设，需要补测试
#    红了 = 测试有效 ✅

# ④ 恢复代码
git checkout discoverse/universal_manipulation/mink_solver.py
```

⚠️ **第 ④ 步别忘了** —— 我见过有人变异验证完直接提交了被注释掉的修复。

---

## 7.4 Day 5：Flake 采样

### 小规模验证管道（先做这个！）

```bash
source scripts/dev/env.sh && $PY -m pytest tests/integration/test_task_matrix.py \
    -m flake -k "airbot_play and place_block" --count=3 -v
```

| 参数 | 作用 |
|---|---|
| `-m flake` | **必须** —— 否则被 addopts 的 `-m 'not flake'` 排除 |
| `-k "表达式"` | 按**名字**筛选，支持 `and` / `or` / `not` |
| `--count=3` | 先跑 3 次验证管道通不通 |

📌 **永远先小规模验证。** 2250 次要跑 10 分钟，
管道有 bug 的话白等 —— 而且 CPU 满载 10 分钟你什么也干不了。

### 全量采样

```bash
source scripts/dev/env.sh && $PY -m pytest tests/integration/test_task_matrix.py \
    -m flake --count=50 -n 8 \
    --json-report --json-report-file=docs/experiments/flake-raw.json
```

**这条命令的规模**：

```
45 个组合 × 50 次重复 = 2250 次运行
÷ 8 个并行进程
≈ 10 分钟墙钟时间
```

⚠️ **`-n 8` 的选择**：不要设成 CPU 核数。每个子进程还会 fork 一个
MuJoCo 进程，实际负载是 2 倍。**8 个进程在 16 核机器上刚好。**

### 生成图表

```bash
$PY scripts/analysis/gen_flake_report.py \
    docs/experiments/flake-2026-08-07.csv \
    docs/report/assets
# 产出：flake-heatmap.png、flake-failure-modes.png
```

### 快速统计（不画图）

```bash
# 各桶计数
tail -n +2 docs/experiments/flake-2026-08-07.csv | cut -d, -f4 | sort | uniq -c | sort -rn

# 输出：
#  924 SUCCESS
#  660 BUCKET2_判据失败
#  355 BUCKET4_配置崩溃
#  299 BUCKET1_早期IK失败
#   12 BUCKET3_超时/未记录
```

| 部分 | 作用 |
|---|---|
| `tail -n +2` | **从第 2 行开始**（跳过 CSV 表头） |
| `cut -d, -f4` | 按逗号分隔，取第 4 列（bucket） |
| `sort \| uniq -c` | **必须先 sort** —— `uniq` 只合并**相邻**的重复行 |
| `sort -rn` | 按数字逆序（`-n` 数字，`-r` 倒序） |

### 算真实 flake 率

```bash
# 总行数（减表头）
tail -n +2 docs/experiments/flake-2026-08-07.csv | wc -l          # 2250

# 剔除 BUCKET4 后的分母
tail -n +2 docs/experiments/flake-2026-08-07.csv | grep -vc 'BUCKET4'   # 1895

# 成功数
tail -n +2 docs/experiments/flake-2026-08-07.csv | grep -c 'SUCCESS'    # 924

# 924 / 1895 = 48.8%   ← 真实成功率
# 924 / 2250 = 41.1%   ← 被污染的表观成功率
```

📌 **这三条命令就是简历上「48.8% vs 41.1%」那个结论的完整复现路径。**
面试时能当场敲出来，可信度完全不同。

---

# 第八部分：面试问答速查

## Q1「你怎么保证仿真实验可复现？」

> 分三层答：
>
> **① 找出所有随机源。** 我 grep 出 `randomization.py` 里有 25 处裸的
> `np.random.*`，而配置里 6 处声明的 `seed` **零个读取者** —— 用户写 seed 完全没用。
>
> **② 选对隔离方式。** 我用 `np.random.default_rng(seed)` 实例，
> 而不是 `np.random.seed()`。因为全局种子是**全局可变状态**：
> 并行测试会互相污染，而我后面要跑 `-n 8` 的并行采样，
> 用全局 seed 那份数据不可信。
>
> **③ 确定性的边界是整条调用链，不是单个文件。**
> 我改完 25 处后发现 `randomization.py:553` 调了 `utils.get_random_texture()`，
> 那个函数完全不知道 rng 的存在 —— 随机性从 import 边界溜走了。
> 这个我评估后没修（要改公共 API 签名、牵连 4 个调用方），
> 用 `xfail(strict=True)` 钉住，让它保持可见。

---

## Q2「一条测试通过了，你怎么知道它真的有用？」⭐

> **做变异验证：把修复代码注释掉，看测试红不红。**
>
> Day 4 我修了 IK 求解器的状态泄漏，两条测试都绿。
> 但我把修复注释掉之后，**测试居然还是绿的**。
>
> 排查发现我的修复其实同时做了两件事：真正消除泄漏的是把
> `set_target_from_configuration` 挪出 if 块，而我以为关键的那个 else 分支，
> 作用其实是**保持默认姿态是 home 而非模型的 qpos0**。
> 我只理解了第一件，所以测试只覆盖了一半契约。
>
> 我补了第三条测试专门锁住默认姿态。**这次变异验证的价值不是发现代码 bug，
> 是发现我对自己修复的理解不完整。**
>
> 工业界有 `mutmut`、PIT 这类自动变异工具，但很慢。
> 我的做法是关键修复手工做一次变异验证，成本几分钟，收益是「知道测试是活的」。

---

## Q3「你说的 48.8% 和 41.1% 是怎么回事？」⭐⭐

> 这是我 Day 5 做 flake 定量分析时最重要的一个发现。
>
> 我设计了 **9 机器人 × 5 任务 × 50 次重复 = 2250 次**的正交实验，
> 并行 10 分钟跑完。原始成功率是 924/2250 = **41.1%**。
>
> 但我做失败归因时把失败分成四桶，发现其中一桶（355 次，15.8%）是
> **100% 确定性复现**的 —— `cover_cup` 任务对非 airbot_play 机器人
> 声明了一个不存在的相机 `eye_arm`，每次必崩，没有任何随机性。
>
> **把它剔除后，真实 flake 率是 924/1895 = 48.8%。**
>
> 这个区分比数字本身更重要，因为它影响修复方向：
> 不剔除的话，热力图上 `cover_cup` 那一整行永远是黑的，
> 会有人去调 IK 容差、怀疑物理引擎 —— 而**真正的问题是一行配置里写错了相机名**。
>
> 一句话：**做统计之前，先把确定性的部分剥离出去。**
> 把 100% 复现的 bug 混进随机性分析，会同时污染分母和归因。

---

## Q4「失败率高，你怎么定位问题？」

> 光看「成功率 48.8%」是不可行动的。我按**失败模式**分桶：
>
> - **BUCKET1 早期 IK 失败**（完成状态 5/17）→ **够不着**，目标超出工作空间
> - **BUCKET2 判据失败**（完成状态 17/17 但没成功）→ **抓不住**，走到位了物体滑了
>
> **这两类的修复方向完全相反**：前者要改机器人摆位或缩小随机化范围，
> 后者要调夹爪力度或摩擦系数。
>
> 我画了每个机器人的失败模式构成图，看到 airbot_play 几乎全是 BUCKET2，
> 而 iiwa14 几乎全是 BUCKET1。这直接说明：
> **失败率不是「机器人的属性」也不是「任务的属性」，是「机器人 × 任务」的匹配属性。**
>
> 我还标了置信区间：N=50 时 95% CI 约 ±12%，
> 所以 50% 和 56% 之间的差异在噪声范围内，**不能用这份数据下那种结论**。

---

## Q5「你的测试有没有写错过？」⭐

> 有，而且我觉得这是最值得讲的部分。
>
> **① 差点写出一条假绿灯。** 测 seed 时最自然的写法是在测试里
> `np.random.seed(42)`，然后跑两次比较。**这条测试会通过 ——
> 但它测的是 numpy，不是我的项目。** 因为项目代码用的就是全局 `np.random`，
> 我在外面固定它当然确定。而真实用户是在 YAML 里写 seed，**那条链当时是断的**。
> 教训：**测试的入口必须是用户的入口。**
>
> **② 差点漏掉平凡解。** 「同 seed 两次结果相同」这条断言有个平凡解：
> 如果随机化根本没执行，两次结果自然相同，测试变绿但什么都没验证。
> 我补了反向哨兵「不同 seed 必须给不同结果」。
> 后来实测证明它不可省 —— 我注入一个「写死 seed=42」的假修复时，
> **只有这条测试会红**。
>
> **③ 数据里有测量误差，我如实记了。** flake 实验里 BUCKET3 的 12 例，
> 至少 1 例是撞上 `pyproject.toml` 的全局 `timeout=60` 而非用例内的
> `TIMEOUT_S=120` —— **两个超时配置打架**，导致归桶不准。
> 我把它写进了实验元数据的 `caveats`。

---

## Q6「xfail 和直接注释掉测试有什么区别？」

> 注释掉的测试是**死的** —— 它不会执行，三个月后没人知道那个缺陷还成不成立。
>
> `xfail(strict=True)` 是**活的**：
> - 每次 CI 都跑
> - 缺陷还在 → XFAIL（正常，不打扰人）
> - **缺陷被修好了 → XPASS，而 strict 模式下 XPASS 直接报 FAILED**，
>   强制有人回来撤掉这个标记
>
> **效果是让「缺陷被修复」这件事也不会静默发生。**
>
> 我用它钉了两类东西：一类是**评估后决定不修的**（比如贴图随机化，
> 修它要改公共 API 签名牵连 4 个调用方），一类是**语义未定义的**
> （`qpos_dim` 到底指模型 nq 还是可控自由度，不搞清楚就改数字
> 只是把一个已知错误换成一个未知错误）。
>
> **xfail 是可执行的缺陷报告** —— 同时是缺陷记录、回归防护和交接文档。

---

## Q7「为什么 fixture 要分作用域？」

> 判断依据只有一个：**这个对象可变吗？**
>
> - `MjModel`（编译产物，只读）→ `session`，编译一次要几百 ms 到几秒
> - `MjData`（持有 qpos/qvel/时间，可变）→ **必须 `function`**
>
> 如果 `MjData` 跨用例复用，用例 A 步进 1000 步后的状态会泄漏给用例 B，
> 造成典型的「**单跑绿、全跑红**」—— 而且顺序一变就复现不了。
>
> 还有个反直觉的坑：**session 级 fixture 返回可变 dict 时，
> 任何用例改了它，后面所有用例都受影响。** 我在配置 fixture 上写了注释提醒
> 使用者 deepcopy，但更好的做法是返回不可变结构（`MappingProxyType` 或
> frozen dataclass），让错误在写代码时就暴露，而不是靠注释。

---

# 第九部分：企业开发扩展

## 9.1 可复现性工程（Reproducibility Engineering）

**本项目做的 seed 贯穿，在工业界是一个专门的工程领域。**

### 完整的可复现性清单（ML/仿真项目通用）

```python
# ① 所有随机源
np.random.default_rng(seed)          # numpy
random.Random(seed)                  # stdlib（不要用全局 random.seed）
torch.manual_seed(seed)              # PyTorch CPU
torch.cuda.manual_seed_all(seed)     # PyTorch GPU
torch.use_deterministic_algorithms(True)   # 强制确定性算子

# ② 环境变量
PYTHONHASHSEED=0                     # ⚠️ 字符串 hash 有随机盐！
CUBLAS_WORKSPACE_CONFIG=:4096:8      # cuBLAS 确定性

# ③ 隐藏的顺序依赖
sorted(glob(...))                    # 文件系统顺序不保证
sorted(set(...))                     # set 迭代顺序不保证
num_workers=0 或固定 worker seed      # DataLoader 多进程

# ④ 记录环境
git commit hash / 依赖版本锁定 / Docker 镜像 digest
```

### 📌 本项目做到了哪些

| 项 | 状态 | 位置 |
|---|---|---|
| numpy 随机流隔离 | ✅ | `SceneRandomizer.rng` |
| 记录 git commit | ✅ | `flake-*.meta.yaml` |
| 记录完整命令 | ✅ | 同上 |
| 依赖锁定 | ✅ | Docker 镜像（Day 8-9） |
| 贴图随机源 | ❌ | xfail 钉住 |
| `PYTHONHASHSEED` | ❌ | 本项目不涉及 hash 敏感逻辑 |

---

## 9.2 配置即代码：用 schema 校验替代 `.get()` 默认值

**缺陷 J（键名不匹配）的根本解法不是「兼容两个键名」，而是「让配置错误无法通过校验」。**

### 现状的问题

```python
radius = obj_config.get("min_distance", 0.05)     # 拼错键名 → 静默降级
```

### 企业实践：Pydantic / dataclass + 校验

```python
from pydantic import BaseModel, Field, ValidationError

class ObjectConfig(BaseModel):
    name: str
    collision_radius: float = Field(default=0.05, gt=0, le=1.0)

    model_config = {"extra": "forbid"}     # ⭐ 关键：多余的键直接报错

# 用户写 min_distance → ValidationError: extra fields not permitted
```

| 特性 | 收益 |
|---|---|
| `extra="forbid"` | **拼错的键名当场报错**，而不是静默忽略 |
| `gt=0, le=1.0` | 值域校验，负半径/超大半径当场拒绝 |
| 类型注解 | IDE 补全、静态检查 |
| `.model_json_schema()` | **自动生成 JSON Schema**，可给 YAML 编辑器做补全 |

📌 **面试可以这样讲**：「我修缺陷 J 时用了兼容两个键名的方案，
因为改动面最小、对照文档抄的人也不会踩坑。但**根本解法是加 schema 校验** ——
用 Pydantic 的 `extra='forbid'` 让拼错的键当场报错，
而不是让 `.get()` 的默认值把错误吞掉。
这个项目里我没做，因为要改的是上游的配置加载层，超出了我的改动范围。」

---

## 9.3 用结构化契约替代 stdout 解析

**这正是本项目 Day 13-14 做的事**，[5.3](#53-_classify-分桶函数49-87-行) 里的
`_classify` 是它要解决的技术债。

### 演进路径

```
阶段 1（Day 5）：  grep stdout 文本
                   ❌ 改文案就全错、❌ 静默失败、❌ 编码问题

阶段 2（Day 13-14）：被测程序输出结构化结果
                   { "status": "success", "steps_done": 17, "steps_total": 17,
                     "failure_reason": null, "metrics": {...} }
                   ✅ 契约明确、✅ 可加 schema 校验、✅ 版本化
```

### 企业实践中的通用形式

| 场景 | 结构化契约 |
|---|---|
| 测试结果 | **JUnit XML** / TAP / JSON report |
| CLI 工具 | `--output json` 选项（`kubectl -o json`、`gh --json`） |
| 服务间 | Protobuf / OpenAPI schema |
| 日志 | **结构化日志**（JSON lines）而非 printf |

📌 **判断标准：如果一个程序的输出会被另一个程序消费，
那它就需要一个契约 —— 而不是让消费方去 grep。**

---

## 9.4 实验数据的管理

**本项目把 155KB 的 CSV 提交进了 git，并写下了退出条件**：

```yaml
retention:
  rationale: >
    155KB 换「结论可复算」。数据含随机性，重跑 2250 次也得不到同一份 ——
    它是一次性观测记录，不是可再生的中间产物。
  exit_condition: >
    累积约 10 份实验数据（~1.5MB）时迁移到 Git LFS 或 CI artifact。
    在那之前不做优化。
```

### ⭐ 这段值得单独讲

**判断依据：可再生 vs 一次性观测。**

| 数据 | 可再生吗 | 该进 git 吗 |
|---|---|---|
| 编译产物 | ✅ 重跑就有 | ❌ |
| 采集的视频/轨迹（`data/`） | ✅ 重跑就有 | ❌（上游已 gitignore） |
| **flake 实验 CSV** | ❌ **含随机性，重跑得不到同一份** | ✅ |

**而且写了退出条件** —— 这是「临时决定」和「技术债」的区别：

```
临时决定 + 退出条件  =  有意识的权衡  ✅
临时决定 无退出条件  =  技术债        ❌
```

### 企业实践的阶梯

| 数据量 | 方案 |
|---|---|
| < 1MB | 直接进 git |
| 1MB - 100MB | **Git LFS** |
| > 100MB | 对象存储（S3/OSS）+ git 里存 URL 和 checksum |
| 需要版本+血缘 | **DVC**、MLflow、W&B |

📌 **面试价值**：「我把实验数据提交进了 git，
但在元数据里写了 rationale 和 exit_condition ——
155KB 换结论可复算是划算的，累积到 10 份（约 1.5MB）时迁 LFS。
**临时决定加上退出条件才不是技术债。**」

---

## 9.5 统计实验设计的基本功

### 本项目做对的三件事

**① 正交实验设计**

```
9 机器人 × 5 任务 × 50 重复 = 2250
```
不是「随便跑跑看」，而是**全因子设计**（full factorial）——
每个组合都有相同的样本量，可以做行列对比。

**② 标注置信区间**

```yaml
- N=50 时 95% 置信区间约 ±12%（p≈0.5）。不要用它区分接近的数值，
  例如 50% 和 56% 之间的差异在噪声范围内。
```

**二项分布的标准误**：

```
SE = sqrt(p(1-p)/n) = sqrt(0.5 × 0.5 / 50) = 0.0707
95% CI = ±1.96 × SE ≈ ±13.9%   （文档里写 ±12%，同一量级）
```

📌 **不标 CI 的百分比是耍流氓。** N=50 的 62% 和 56%，
你**没有证据**说前者更好。

**想把 CI 缩到 ±5% 需要多少样本？**
```
n = (1.96/0.05)² × 0.25 ≈ 384    ← 每格要跑 384 次，总共 17280 次
```
**这就是为什么要先算 CI 再决定样本量** —— 而不是跑完才发现区分不出来。

**③ 记录可复现信息**

```yaml
command: pytest tests/integration/test_task_matrix.py -m flake --count=50 -n 8
git_commit: c722ca8ae0d9bb2d8c4b16df20c6d879f315b161
```

**命令 + commit hash = 别人能复算你的结论。**

### 📖 企业扩展：A/B 测试的同一套逻辑

| 本项目 | A/B 测试 |
|---|---|
| 9 机器人 × 5 任务 | 实验组 vs 对照组 |
| 50 次重复 | 样本量（用 power analysis 算） |
| 剔除 BUCKET4 | 剔除 bot 流量、异常用户 |
| ±12% CI | p 值 / 置信区间 |
| 失败分桶 | 漏斗分析、分群 |

📌 **「先剔除确定性污染再做统计」在 A/B 测试里对应
「先清洗 bot 流量再算转化率」** —— 完全一样的思路。

---

## 9.6 测试分层与运行策略

**本项目的 marker 体系**（`pyproject.toml`）：

```toml
markers = [
    "unit: 纯函数/配置层单测，无 MuJoCo 依赖，秒级",
    "integration: 需要加载 MJCF 或跑仿真步进",
    "slow: 单用例 >10s，CI 主线跳过",
    "determinism: 确定性/可复现性专项",
    "flake: flake 率采样实验，非常规回归；需显式 -m flake 运行",
]
```

### 对应的运行策略（测试金字塔的落地）

| 时机 | 命令 | 耗时 | 目的 |
|---|---|---|---|
| 本地开发 | `pytest -m unit` | 秒级 | 快速反馈 |
| **pre-commit** | `pytest -m "unit and not slow"` | < 30s | 挡住低级错误 |
| **PR CI** | `pytest -m "not flake"` | 分钟级 | 完整回归 |
| **nightly** | `pytest -m flake --count=50 -n 8` | 小时级 | 趋势监控 |
| 发版前 | 全部 + 变异验证 | — | 最终确认 |

📌 **`addopts` 里的 `-m 'not flake'` 是关键**：
让**默认行为是安全的**，昂贵的东西必须显式开启。

### 企业实践补充

```bash
# 只跑受本次改动影响的测试（需 pytest-testmon）
pytest --testmon

# 失败时自动重跑（⚠️ 慎用，会掩盖 flake）
pytest --reruns 2 --reruns-delay 1

# 显示最慢的 10 个用例，找优化目标
pytest --durations=10
```

⚠️ **`--reruns` 是双刃剑**：它让 CI 变绿，也让你**看不见 flake**。
正确用法是：**允许重跑，但把重跑次数上报到监控** —— 
重跑率上升就是质量在退化的信号。

---

## 相关文档

- [day03-04-determinism.md](day03-04-determinism.md) — Day 3-4 确定性攻坚
- [day04-ik-and-defects.md](day04-ik-and-defects.md) — Day 4 IK 与缺陷收尾
- [day05-flake-analysis.md](day05-flake-analysis.md) — Day 5 Flake 定量分析
- [day00-02-supplement-line-by-line.md](day00-02-supplement-line-by-line.md) — 环境、pytest 骨架、配置层逐行
- [day08-11-supplement-line-by-line.md](day08-11-supplement-line-by-line.md) — Docker 与 CI 逐行
- [../defect-report.md](../defect-report.md) — 完整缺陷清单
- [../experiments/flake-2026-08-07.meta.yaml](../experiments/flake-2026-08-07.meta.yaml) — 实验元数据
