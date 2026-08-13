# DISCOVERSE 缺陷分析报告

> 分支：`feat/test-infra` ｜ 基线 commit：`c722ca8` ｜ 报告日期：2026-08-11
> 覆盖范围：`discoverse/universal_manipulation/`、`examples/universal_tasks/`、`discoverse/configs/`
> 排除范围：`policies/`（237 个策略学习文件，属上游第三方代码，不在本次测试范围）

---

## 〇、阅读指南

本报告记录 **20 条缺陷，每条均按统一完整格式展开**：

> 影响模块 → 复现步骤 → 预期 vs 实际 → 根因分析 → 修复方案 → 回归验证 → 影响范围

**每条结论都标注核实方式**：

| 标记 | 含义 |
|---|---|
| **【实测】** | 亲自跑过，附命令与实际输出 |
| **【静态核实】** | 逐行读代码 + grep 全库确认，未实跑 |
| **【推断】** | 有依据但未验证，明确标出 |

### 一个必须先说明的事

本报告有 **3 条结论推翻了此前自己写下的记录**（§二专门列出）。这不是文档质量问题，而是这类工作的固有特征——**排查的过程就是不断提出假设并杀死它们**。凡被推翻的，正文一律采用实测版本，并保留原记录供对照。

---

## 一、摘要

### 1.1 缺陷总表

| 章节 | 编号 | 缺陷 | 严重度 | 状态 | 核实 |
|---|---|---|---|---|---|
| §三 | **#1** | 域随机化 seed 配置零消费，仿真不可复现 | 🔴 Critical | ✅ 已修 `cd09b80` | 实测 |
| §四 | **#2** | 任务失败时退出码仍为 0，CI 永远绿灯 | 🔴 Critical | ⏸ 未修 | 实测 |
| §五 | **#3** | pytest 超时保险丝未生效 | 🟠 High | ⏸ 未修 | 实测 |
| §六 | J | `collision_radius` 键名不匹配，9/12 物体避让半径失效 | 🟠 High | ✅ 已修 `8cfbc38` | 实测 |
| §七 | L | `mink`/`quadprog` 未声明依赖，包无法 import | 🟠 High | ✅ 已修（本次） | 实测 |
| §八 | N | 配置错误 → 静默删数据 → 无限重试 | 🟠 High | ⏸ 未修 | 静态核实 |
| §九 | V | `cover_cup` 声明不存在的相机，8/9 机器人崩溃 | 🟠 High | ⏸ 未修 | 实测 |
| §十 | B | 4/5 任务 `camera_configs` 为空，采集零图像 | 🟠 High | ⏸ 4 xfail | 实测 |
| §十一 | I | `_validate_config` 未把 `observation` 列必填 | 🟡 Medium | ⏸ 1 xfail | 实测 |
| §十二 | U | IK `posture_task` 目标跨调用泄漏 | 🟡 Medium | ✅ 已修 `c722ca8` | 实测 |
| §十三 | S | 贴图随机源不受 seed 管控 | 🟡 Medium | ⏸ 1 xfail | 实测 |
| §十四 | K | 夹爪工厂假多态 | 🟡 Medium | ⏸ 未修 | 静态核实 |
| §十五 | M | `step()` 返回值语义重载（2 值承载 5 种含义） | 🟡 Medium | ⏸ 未修 | 静态核实 |
| §十六 | O | IK `dt` 被硬编码遮蔽（休眠缺陷） | 🟢 Low | ✅ 已修 `c722ca8` | 实测 |
| §十七 | H | 4/9 机器人 `qpos_dim` ≠ MJCF `nq` | 🟢 Low ⬇ | ⏸ 4 xfail | 实测 |
| §十八 | Q | 空 `conditions` → 恒判定成功（当前不可达） | 🟢 Low | ⏸ 未修 | 静态核实 |
| §十九 | P | `panda.yaml` 重复键 + 乱码残留 | 🟢 Low | ⏸ 未修 | 实测 |
| §二十 | R | `randomize_scene` 返回类型与注解不符 | 🟢 Low | ⏸ 未修 | 静态核实 |
| §廿一 | T | 库代码 96 处 `print` 代替 `logging` | 🟢 Low | ⏸ 未修 | 实测 |
| §廿二 | X | MuJoCo viewer 退出时段错误 | 🟢 Low | ⏸ 未修 | 静态核实 |
| §廿三 | **L′** | 另外 4 个包未声明依赖 —— **缺陷 L 只修了一半** | 🟠 High | ⏸ 未修 | 实测 |
| §廿四 | **Y** | `recoder_single_arm` 部分写入留下 0 字节坏文件 | 🟡 Medium | ⏸ 3 xfail | 实测 |
| §廿五 | **Z** | `PyavImageEncoder` 未 close 则整段录像静默丢失 | 🟡 Medium | ⏸ 1 xfail | 实测 |
| §廿六 | **G** | `cv2` 依赖的系统库 `libglib2.0-0` 未记录 | 🟢 Low | ✅ 已修（`Dockerfile.test`） | 实测 |

**已修 6 条，未修 18 条**，其中 14 条由 `xfail(strict=True)` 测试守护。

> **§廿三 ~ §廿六 是 Day 8-9 新增。** 四条都由**同一件事**暴露：把测试放进一个干净的 Docker 容器里跑。
>
> 其中 **L′ 与 G 是同一个问题的两层**：L′ 是 pip 管的 Python 包缺失，G 是 pip **管不到**的系统库缺失。
> 而 L′ 尤其值得注意 —— 它证明**缺陷 L 当时只修了症状**（见 §廿三）。

### 1.2 关于"未修"的说明

未修不等于未定位。**15 条未修缺陷全部完成根因定位**，10 条被 `xfail(strict=True)` 钉在代码里——一旦有人修好，测试自动转 XPASS 报警提醒撤标记，**缺陷不会因为无人记得而消失**。

有意识停在这里的理由：本项目目标是建立测试能力与缺陷分析方法，**而非把上游代码修完**。修复 T（96 处 print）和 M（重构返回值契约）会产生大量 diff 噪音，淹没真正的技术产出。取舍记录在此，供评审判断。

### 1.3 贯穿性模式：声明了但没人消费

20 条缺陷中，**8 条同属一个模式**：

| 缺陷 | 声明了什么 | 谁该消费 | 实际 |
|---|---|---|---|
| #1 | `seed: 42` | `SceneRandomizer` | 无人读取 |
| #3 | `timeout = 60` | pytest-timeout | 未生效 |
| J | `collision_radius` | 避让检测 | 键名不匹配 → 返回默认值 |
| K | `gripper.type` | 夹爪工厂 | 工厂函数从不读 |
| K′ | `grasp_threshold`、`sensor_index` | 抓取检测 | 检测功能不存在 |
| H | `qpos_dim` | （无） | 终点是没人读的数组 |
| B | `camera_configs` | 数据采集 | 空列表 → 零张图像 |
| V | `eye_arm` 相机 | 渲染器 | MJCF 里不存在 |

**Python 语义根源**：`dict.get(key, default)` 键不存在时返回默认值而非报错；`for x in []` 直接跳过循环体；`all([])` 返回 `True`。三者都让"配置缺失"表现为"一切正常"。

### 1.3.1 Day 8-9 的补充：该模式不限于配置，也不限于本项目

容器化过程中同一模式又出现 **5 次**，其中三次根本不在 YAML 里：

| 场景 | 声明了什么 | 实际 |
|---|---|---|
| `MUJOCO_GL=glfw`（现有 `Dockerfile:58`） | 用 glfw 渲染 | 无头环境下不可用 |
| `pyproject.toml` 核心依赖 | 依赖齐全 | **少 4 个包**（§廿三） |
| `HTTP_PROXY=127.0.0.1:7897` | 走代理 | **代理软件两个月前就停了** |
| compose 的 `:ro` 挂载 | 保护源码不被容器改 | **顺带杀死一个合法测试** |
| `recoder_single_arm` | 产出 obs-action JSON | **0 字节坏文件**（§廿四） |

**三点补充结论**：

**其一，该模式不是配置文件特有的。** git 的 `.gitignore`（Day 6-7 吞掉 `docs/log/`）、Docker 的 `.dockerignore`（挡掉 MJCF 使测试静默 skip）、systemd 的环境变量，全都表现出同一行为。**它是"声明式配置 + 缺失即默认"这一组合的固有属性。**

**其二，"声明"不一定错，副作用同样静默。** 上表第四行 `:ro` 挂载是**完全正确的配置** —— 它就是要防止容器写宿主机源码。但它顺带让一个需要写临时 YAML 的测试失败。**任何声明都可能有未预期的下游影响，而配置系统不会告诉你。**

**其三，环境会随时间漂移。** 那个代理配置写下时是对的，代理停掉之后就不对了，**而没有任何机制会通知你**。

> 本机环境是**累积**的，容器环境是**声明**的。
> **这是容器化最根本的价值 —— 不是"隔离"，是"没有历史包袱"。**

> **本报告最值得带走的结论**：配置驱动系统里，**最危险的不是配置写错，而是配置写了没人读**。写错通常会报错，没人读则永远沉默。
>
> **防御手段**：对每个配置项写一条"它确实被消费了"的测试，而不只是"它能被解析"。

### 1.4 三条缺陷之间的依赖关系

```
#1 seed 不可复现
    ↓ 提供"必然失败"的确定输入
#2 退出码恒为 0   ←── 回归测试依赖 #1，顺序不可颠倒
    ↓ 修复后退出码才有意义
X  段错误使退出码变 139  ←── 必须与 #2 一并处理，否则契约被破坏
```

同时 **#3（超时未生效）是 #2 的前提保障**：任务挂死而无超时，退出码根本不会产生。

> **CI 可靠性不是单点修复能达成的**，它要求可复现性、退出码契约、超时保护三者同时成立。

---

## 二、被实测推翻的记录（方法论）

本节前置，因为它决定了如何阅读后文每一条结论。

### 2.1 缺陷 #1 的根因位置写错了

| | 内容 |
|---|---|
| **原记录** | "`task_config.py:88` 读取了 `randomization.settings.seed`，但只存在 `self.randomization` 字典里" |
| **实测** | `task_config.py:88` 是 `states` 字段的**校验代码**，与 seed 无关；整个文件 grep `seed` **零命中** |
| **影响** | 描述从"读了但没传下去"（链路中段断裂）变为"整条链路无人提及"（**根本没有链路**） |

**这个更正让缺陷更严重，而非更轻。** 若照原记录写进报告，评审翻开代码会当场对不上。

### 2.2 缺陷 #3 的机制完全反了

| | 内容 |
|---|---|
| **原记录** | "pytest 全局 `timeout=60` 覆盖了用例内 `TIMEOUT_S=120`，导致 BUCKET3 归桶不准" |
| **实测** | 方向相反——`timeout=60` **压根没生效**（纯 sleep 75s 照样 passed）。`TIMEOUT_S=120` 从未被覆盖，它是**唯一**在生效的超时 |
| **影响** | 按原记录去修，会去调整两个超时值的大小关系——**修一个不存在的问题**，而真实问题（没有任何 pytest 层超时保护）继续存在 |

**补充**：中途一次自动化排查曾报告"`pytest-timeout` 未安装"，实测为**该排查使用了错误的 Python 解释器**（系统 python 而非项目 conda 环境）。项目环境中该插件为 `2.4.0`，安装完好。**这条错误结论未被采信，因为它与"命令行 `--timeout=10` 能杀掉测试"的实测直接矛盾。**

> 面试可用点：**别人（包括自动化工具）给的结论也要验。** 判据是它与已有实测证据是否自洽。

### 2.3 缺陷 H 的严重度虚高

| | 内容 |
|---|---|
| **原记录** | 严重度"高"，"IK 按 YAML 维度切 qpos 数组，维度错了会静默取错关节"（该说法出现在 **5 份文档**中） |
| **实测** | 全库**不存在任何 `qpos[:qpos_dim]` 切片**；`qpos_dim` 仅 4 处引用，终点是无人读取的 `target_qpos` |
| **影响** | 严重度降为低；**"待决策"卡点自动解除**——原本担心改动破坏行为，实测确认无消费者可破坏 |

### 2.4 共同教训

前期还有一次更典型的失误：Day 5 排查 BUCKET2 根因时，**用两个样本的对比就宣布找到根因**（"轴向深度"），随后被 `seed=14` 反例推翻——而该结论写在"两个样本不足以下结论"这句话之后。

> 📌 **成对对比是最容易产生假根因的方法。** 任何两次运行之间都有几十个数值不同，总能挑出一个"完美解释"——过拟合到样本，解释力 100%、泛化能力 0。
>
> **唯一解药是主动扩大样本找反例。**

三周累计 **13 条写进文档的推断被实测推翻，其中 3 条是当天自己写的**。因此本报告每条结论标注核实方式，并且 **§5.5 明确承认缺陷 #3 的失效机制尚未定位到根因**——不把未验证的猜测写成结论。

---

## 三、缺陷 #1｜域随机化 seed 配置零消费，仿真不可复现

**严重级别**：🔴 Critical ｜ **状态**：✅ 已修复（`cd09b80`）｜【实测】

### 3.1 影响模块

- `discoverse/universal_manipulation/randomization.py`（24 处随机调用）
- `discoverse/universal_manipulation/task_base.py:53`（构造断链点）
- `discoverse/configs/tasks/*.yaml`（6 处声明）

### 3.2 复现步骤

```bash
sed -i "s/    seed: .*/    seed: 42/" discoverse/configs/tasks/place_block.yaml
python examples/universal_tasks/universal_task_runtime.py \
    -r airbot_play -t place_block -1 --headless      # 连续运行两次
```

### 3.3 预期 vs 实际

| | 行为 |
|---|---|
| **预期** | 相同 seed → 相同物体初始位置 → 相同轨迹 → 相同成败 |
| **实际** | 每次物体位置都不同，成败随机。**`seed` 写与不写没有任何区别** |

### 3.4 根因分析

**配置侧声明 6 处，其中 2 处还配了解释性注释**——写配置的人确信它生效：

```
discoverse/configs/tasks/place_block.yaml:85              seed: null
discoverse/configs/tasks/cover_cup.yaml:115               seed: null
discoverse/configs/tasks/place_coffeecup.yaml:92          seed: null
discoverse/configs/tasks/place_kiwi_fruit.yaml:92         seed: null
discoverse/configs/tasks/stack_block.yaml:103             seed: null   # 随机种子（null表示使用系统时间）
discoverse/configs/tasks/templates/randomization.yaml:63  seed: null   # 随机种子（null表示使用系统时间）
```

**代码侧读取者：0 个。**

```bash
$ git grep -n "seed" cd09b80^ | grep -E "^cd09b80\^:(discoverse|examples|scripts)/.*\.py:"
（无输出）
```

三个目录下所有 `.py` 中 `seed` 命中行数为 **0**。全库其余命中全在 `policies/`（无关训练代码，自带独立 seed 机制）。

**断链点**——修复前 `task_base.py:53`：

```python
self.randomizer = SceneRandomizer(self.mj_model, self.mj_data)   # 没有 seed 参数
```

`SceneRandomizer.__init__` 签名为 `(self, mj_model, mj_data)`，**根本不接受 seed**。内部 24 处随机调用全部裸调全局流：

```python
local_x = np.random.uniform(x_range[0], x_range[1])       # :230
u1, u2, u3 = np.random.random(3)                          # :368
self.mj_model.light_active[np.random.randint(...)] = 1    # :412
```

> **这不是"链路中间断了"，而是从 YAML 到代码整条链路上没有任何一处提到过 seed。** 配置项是纯粹的装饰。
>
> 打个比方：**车上装了个音量旋钮，但旋钮背后没接线。** 不是接错了，是压根没接。

### 3.5 为什么是 Critical

表面是"一个配置项没生效"，实际**把整个项目的可测试性废掉了**：

- **测试写不了** —— 相同输入产生不同结果，断言无从下手
- **缺陷报不了** —— "有时候会失败"无法让他人复现
- **修复验证不了** —— 修完跑一次成功，是真修好了还是碰巧？

而且**它是静默的**。写 `seed: 42` 不报错、不警告，使用者一直以为自己在做可复现实验。

### 3.6 修复方案

```python
class SceneRandomizer:
    def __init__(self, mj_model, mj_data, seed: Optional[int] = None):
        # 用 Generator 实例而非 np.random.seed()：
        #   全局随机流是进程级共享的，第三方库调一次就会推进它，
        #   且 pytest-xdist 并行下会互相污染。实例是隔离的。
        # seed=None -> 从操作系统熵源取种，保持"不指定就随机"的原有行为。
        self.rng = np.random.default_rng(seed)
```

24 处 `np.random.*` 改为 `self.rng.*`，并在 `task_base.py` 打通 YAML → 构造函数传递。

**为什么用 `default_rng` 而非 `np.random.seed()`**：后者设置**进程级全局状态**，任何第三方库调一次就会推进它，`pytest-xdist` 并行下多个测试还会互相污染。Generator 实例是隔离的，这是可复现性的必要条件。

> 面试可用点：这不是"随便选个 API"，而是**并行测试环境下的必然选择**。

### 3.7 回归验证

测试文件：`tests/simulation/test_determinism.py`
验证方法：把 `randomization.py` 回退到修复前（`cd09b80^`）实跑对比。

| 测试用例 | 修复前 | 修复后 |
|---|---|---|
| `test_config_seed_makes_randomization_reproducible` | ❌ FAILED | ✅ |
| `test_different_seeds_produce_different_scenes` | ❌ FAILED | ✅ |
| `test_randomization_actually_moves_objects` | ❌ FAILED | ✅ |
| `test_task_base_wires_yaml_seed_to_randomizer` | ❌ FAILED | ✅ |
| **汇总** | `4 failed, 1 passed, 1 xfailed` | `5 passed, 1 xfailed` |

修复前的红灯报错**直接坐实断链点**：

```
TypeError: SceneRandomizer.__init__() got an unexpected keyword argument 'seed'
```

**端到端验证**（不只单元测试）：

```
seed=42 → 8 次运行，最终距离全部 0.0024m（稳定成功）
seed=13 → 5 次运行，最终距离全部 0.2378m（稳定失败）
```

单元测试只证明"随机化可复现"，端到端才证明**整条管道可复现**——含 IK、物理步进、状态机、成功判定。

> **缺陷从"偶尔犯病、抓不着"变成"输入 13 就必现"。** 这是后续一切定量分析的前提。

### 3.8 修复的已知边界（诚实声明）

**贴图随机化仍不受管控**（见 §十三 缺陷 S，挂 xfail）。`get_random_texture()` 是模块级函数拿不到 `self.rng`。

**准确说法：物体位置、光照、姿态已可复现，贴图尚未。**

### 3.9 影响范围

此修复是 Day 5 flake 定量分析（2250 次运行、9×5 热力图）的**前置条件**。没有可复现性，"成功率 41.1%"这个数字本身没有意义——无法区分代码问题还是运气问题。

⚠️ **需澄清**：修复后端到端成功率并未提升（Day 0 为 75%，Day 5 实测 76.7%）。**这不是白干**——本缺陷修的是**可复现性**而非成功率，二者是不同维度。

---

## 四、缺陷 #2｜任务失败时退出码仍为 0，CI 永远绿灯

**严重级别**：🔴 Critical ｜ **状态**：⏸ 未修复 ｜【实测】

### 4.1 影响模块

- `examples/universal_tasks/universal_task_runtime.py:508`
- `examples/universal_tasks/cicd_testing.py:121`（连带）

### 4.2 复现步骤

利用缺陷 #1 修复后获得的可复现能力，构造**必然失败**的运行：

```bash
sed -i "s/    seed: .*/    seed: 13/" discoverse/configs/tasks/place_block.yaml
python examples/universal_tasks/universal_task_runtime.py \
    -r airbot_play -t place_block -1 --headless
echo "退出码 = $?"
```

### 4.3 预期 vs 实际

失败用例实际输出：

```
   📋 检查 1 个简单条件...
       🔍 block_green在bowl_pink的5cm范围内: 实际距离=0.2378m, 阈值=0.05m
     1. block_green在bowl_pink的5cm范围内: ❌ 失败
   完成状态: 10/10
   任务成功: ❌ 否
   ❌ 任务未成功，已删除保存目录: .../data/airbot_play_place_block
⚠️ 第 1 轮任务未完全成功
退出码 = 0          ← 这里
```

对照实验（`seed=42`，已知成功）：

```
   任务成功: ✅ 是
🎉 第 1 轮任务成功完成!
退出码 = 0          ← 完全相同
```

| | 退出码 |
|---|---|
| **预期** | 成功 → 0，失败 → 非 0 |
| **实际** | 成功 → 0，失败 → **0**。两者对外完全无法区分 |

### 4.4 根因分析

`universal_task_runtime.py:508`：

```python
if __name__ == "__main__":
    ...
    main(args.robot, args.task, sync=args.sync, once=args.once, headless=args.headless)
    #  ↑ 没有 sys.exit()，返回值直接丢弃
```

函数内部逐层算出的成败——`executor.run()` 返回 `self.success`（:348）、`check_success()` 逐条判定——**走到进程边界就全部蒸发**。

Python 的 `main()` 正常返回时，解释器默认以状态码 0 退出。**要让失败传出去，必须显式 `sys.exit(1)`。**

### 4.5 为什么是 Critical

**所有 CI 系统判断步骤成败，唯一依据就是退出码。** GitHub Actions、Jenkins、GitLab CI 概莫能外。退出码恒为 0 意味着：

- 流水线**永远绿灯**，任务全失败也报成功
- 自动化测试意义归零——**它无法失败，因此无法发现任何问题**
- 更糟的是**制造虚假信心**：团队看到一片绿色，以为一切正常

> 一个永远不会红的测试，比没有测试更危险。没有测试时人们知道自己没有保障；假绿灯让人以为有。

### 4.6 连带发现：CI 层的补偿性 hack

`cicd_testing.py:121` 为绕开此问题，改用**匹配输出里的 emoji** 判定成功：

```python
if "✅ 任务成功检查通过" in output or "🎉" in output and "任务成功完成" in output:
    result.success = True
```

在错误地基上打补丁，引入三重脆弱性：

1. **任何人修改打印文案，整套判定崩溃**——且崩得静默
2. 运算符优先级隐患：`A or B and C` 实为 `A or (B and C)`，与阅读直觉不符
3. emoji 在不同终端编码/日志采集管道下可能丢失

### 4.7 修复方案

**主修复**：

```python
if __name__ == "__main__":
    success = main(args.robot, args.task, sync=args.sync,
                   once=args.once, headless=args.headless)
    sys.exit(0 if success else 1)
```

需配套让 `main()` 显式 `return` 成败（当前无返回值）。

**连带修复**：`cicd_testing.py` 改用 `proc.returncode`，删除 emoji 匹配。

**建议的退出码契约**：

| 码 | 含义 |
|---|---|
| 0 | 任务成功 |
| 1 | 任务失败（判据未满足） |
| 2 | 配置/环境错误（区别于任务失败，见 §八 缺陷 N） |

⚠️ 修复时**必须同时处理 §廿二 缺陷 X**（段错误使退出码变 139），否则新契约立即被破坏。

### 4.8 回归验证方案（未实施）

```python
@pytest.mark.parametrize("seed,expected_rc", [(42, 0), (13, 1)])
def test_exit_code_reflects_task_outcome(seed, expected_rc):
    """退出码必须反映任务成败 —— CI 的唯一判定依据。"""
    proc = subprocess.run([...], timeout=TIMEOUT_S)
    assert proc.returncode == expected_rc
```

**此测试之所以能写，完全依赖缺陷 #1 的修复**——没有可复现的 seed，就没有"必然失败"的输入，也就无法断言失败时的退出码。

### 4.9 影响范围

整个 CI/CD 体系失效。当前 45 组合的自动化测试**无法通过退出码报告任何失败**，只能依赖脆弱的字符串匹配。

---

## 五、缺陷 #3｜pytest 超时保险丝未生效

**严重级别**：🟠 High ｜ **状态**：⏸ 未修复 ｜【实测】

### 5.1 影响模块

- `pyproject.toml:274`
- `tests/integration/test_task_matrix.py:31,79-83`

### 5.2 背景：为什么需要超时

`pyproject.toml` 原有注释已说明设计意图：

```toml
# MuJoCo 仿真最常见的失败模式是死循环而非抛异常。
# 无超时则 CI 会挂到平台上限才被杀；有超时则变成一条明确的失败。
timeout = 60
```

**意图完全正确**：物理仿真挂死时不抛异常，只是永远不返回。没有超时，CI 会一直跑到平台上限（GitHub Actions 为 6 小时）才被杀，既浪费配额又得不到有效诊断。

### 5.3 复现步骤

```python
# test_sleep_kinds.py
import time
def test_pure_sleep():
    time.sleep(75)          # 远超 pyproject 的 timeout = 60
```

```bash
python -m pytest test_sleep_kinds.py -q -p no:randomly
```

### 5.4 预期 vs 实际

| 实验 | 命令 | 结果 |
|---|---|---|
| 依赖 pyproject 的 `timeout = 60` | `pytest test_sleep_kinds.py` | ✅ **1 passed in 75.08s** —— **没杀掉** |
| 命令行显式传参 | `pytest --timeout=10` | ❌ `Failed: Timeout (>10.0s)` —— 杀掉了 |
| 走 ini 通道显式覆盖 | `pytest -o timeout=10` | ❌ `Failed: Timeout (>10.0s)` —— 杀掉了 |

**插件工作正常，命令行传值有效，唯独 `pyproject.toml` 里那行不生效。**

### 5.5 根因分析：排除了六项，仍未定位

| 假设 | 验证 | 结论 |
|---|---|---|
| `pytest-timeout` 没装 | `pip list` → `pytest-timeout 2.4.0` | ❌ 排除 |
| 插件未注册该选项 | `pytest --help` 中存在 `--timeout=TIMEOUT` | ❌ 排除 |
| pyproject 未被读取 | pytest 报告 `configfile: pyproject.toml` | ❌ 排除 |
| 键放错了 table | 位于 `[tool.pytest.ini_options]`（:253）内 | ❌ 排除 |
| 同 table 其他键也失效 | 同段 `addopts` 正常工作（`-m 'not flake'` 生效，45 deselected） | ❌ 排除 |
| 是 subprocess 的锅 | 纯 `time.sleep(75)` 同样不被杀 | ❌ 排除 |

**配置被读取、插件已加载、同 table 相邻键生效，唯独 `timeout` 值未被应用。**

> ⚠️ **诚实声明：具体失效机制尚未定位到根因。**
>
> 候选方向（**均为【推断】，未验证**）：`pytest 9.1.1` 与 `pytest-timeout 2.4.0` 的版本兼容问题；插件读取 ini 值的时机早于 pyproject 解析；某个 conftest 或插件覆盖了该设置。
>
> **不把未验证的猜测写成结论**——这正是 §二 三条更正的教训来源。

> 面试可用点：**"我不知道"是合法结论。** 已排除六项、给出候选方向、说明下一步二分策略，比编一个听起来合理的根因强。

### 5.6 连带缺陷：真正的超时不会进入 BUCKET3【静态核实】

`subprocess.run(timeout=120)` 超时时抛 `subprocess.TimeoutExpired` **异常**，而非返回非零码。而分桶逻辑（`test_task_matrix.py:47-49`）是：

```python
if returncode == -9 or "TIMEOUT" in stdout:
    return {"bucket": "BUCKET3_超时", ...}
```

该异常**未被捕获**，直接冲出 `test_task_combination`，而 `record_property` 位于 :85-89——**在 subprocess 之后**。

**后果**：真实超时既不进 BUCKET3，也不产生任何分桶记录，而是变成一条无标签的 pytest ERROR。**Day 5 报告中 BUCKET3 仅占 0.5%，这个数字因此偏低且不可信。**

### 5.7 修复方案

**第一步（诊断）**：升/降 `pytest-timeout` 版本，或改用独立 `pytest.ini`，二分定位失效原因。

**第二步（补防线）**：

```python
try:
    proc = subprocess.run(..., timeout=TIMEOUT_S)
except subprocess.TimeoutExpired:
    record_property("bucket", "BUCKET3_超时")
    pytest.fail(f"任务超时 >{TIMEOUT_S}s")
```

**第三步（防回归）**：把 §5.3 的复现实验固化为守护测试，断言超时配置**确实生效**。

### 5.8 回归验证方案（未实施）

```python
def test_timeout_config_actually_takes_effect(testdir):
    """守护 pyproject 的 timeout 真的生效 —— 它曾经是死配置。"""
    testdir.makepyfile("import time\ndef test_s(): time.sleep(75)")
    result = testdir.runpytest()
    result.assert_outcomes(failed=1)     # 必须被超时杀掉，而非 passed
```

### 5.9 影响范围

**当前整个测试套件没有任何 pytest 层超时保护。** 45 组合 × 50 次采样若有组合挂死，CI 会跑到平台上限。

注释描述的保护是**不存在的**，而阅读者会认为它存在——**这比没写更危险**。

唯一仍生效的是测试内 stdlib 的 `subprocess.run(timeout=120)`，它与 pytest 无关，**目前实为唯一防线**。

> **这条缺陷本身就是"配置写了没人读"模式的又一实例**（§1.3）。区别在于：前几条是代码不读配置，这条是**配置读了但没起作用**——更隐蔽，因为连 grep 都查不出来。

---

## 六、缺陷 J｜`collision_radius` 键名不匹配，9/12 物体避让半径失效

**严重级别**：🟠 High ｜ **状态**：✅ 已修复（`8cfbc38`）｜【实测】

### 6.1 影响模块

- `discoverse/universal_manipulation/randomization.py:184`
- `discoverse/configs/tasks/*.yaml`（物体避让配置）

### 6.2 复现步骤

```bash
# 在 place_block.yaml 中把碗的 collision_radius 从 0.12 改为 0.5（极大值）
# 运行随机化，观察物体间距是否受影响
python examples/universal_tasks/universal_task_runtime.py -r airbot_play -t place_block -1 --headless
```

### 6.3 预期 vs 实际

| | 行为 |
|---|---|
| **预期** | 碗声明 `collision_radius: 0.12` → 避让半径按 0.12 计算 |
| **实际** | 无论声明什么值，一律按默认 **0.05** 计算。改大改小**毫无效果** |

### 6.4 根因分析

修复前 `randomization.py:184`：

```python
radius = obj_config.get('min_distance', 0.05)     # 代码读 min_distance
```

而 YAML 侧声明的键名是 `collision_radius`：

```yaml
# place_block.yaml
:26      collision_radius: 0.05   # 方块碰撞检测半径5cm
:32      collision_radius: 0.12   # 碗的直径较大，需要更大的避让距离
```

**键名不匹配 → `.get()` 静默返回默认值 0.05。** 12 个物体中 **9 个的自定义避让半径完全失效**——碗声明 0.12（注释明确写了"需要更大的避让距离"），实际按 0.05 算。

> 这是 §1.3 模式的典型：**`.get(key, default)` 把"配置项写错名字"伪装成"用户没配，走默认值"。** 若用 `obj_config['min_distance']` 则会立即 `KeyError`。

### 6.5 修复方案

抽出兼容函数，优先新键名、回退旧键名：

```python
radius = self._get_collision_radius(obj_config)   # 兼容 collision_radius / min_distance
```

**为什么兼容而非直接改**：YAML 与代码分属不同修改方，直接改任一侧都会破坏另一侧的既有用法。兼容层是向后安全的过渡。

### 6.6 回归验证

修复 commit `8cfbc38` 配套测试，验证声明值确实被消费（而非仅能解析）。

### 6.7 影响范围

**数据质量。** 避让半径失效导致物体可能重叠生成，产生物理上不合法的初始状态。这些数据会污染模仿学习数据集，**且全程不报错**。

---

## 七、缺陷 L｜`mink`/`quadprog` 未声明依赖，包无法 import

**严重级别**：🟠 High ｜ **状态**：✅ 已修复 ｜【实测】

> ⚠️ **本条修复不完整。** Day 8-9 在干净容器中发现**同一文件、同一机制**下还有 4 个包未声明（`pyyaml`/`av`/`PyOpenGL`/`pillow`）——见 **§廿三（缺陷 L′）**。
>
> 修本条时看见 `mink` 缺就补 `mink`，**没有系统性走完整条 eager import 链**。这是一次典型的**修症状而非修根因**：修复动作正确，但排查范围不完整。

### 7.1 影响模块

- `pyproject.toml`（`dependencies` 段）
- `discoverse/universal_manipulation/__init__.py`
- `discoverse/universal_manipulation/mink_solver.py:8,45`

### 7.2 复现步骤

```bash
# 干净环境（不含 mink）
pip install -e .
python -c "import discoverse.universal_manipulation"
```

### 7.3 预期 vs 实际

| | 行为 |
|---|---|
| **预期** | `pip install` 后包可正常导入 |
| **实际** | `ModuleNotFoundError: No module named 'mink'` —— **整个包不可导入** |

### 7.4 根因分析

```bash
$ grep -n "mink\|quadprog" pyproject.toml
（修复前无输出）
```

而实际导入点：

```
discoverse/universal_manipulation/mink_solver.py:8    import mink        ← 模块级
examples/mocap_ik/mink_arm_ik.py:1                    import mink
examples/robots/ur5e_pick_fruit.py:5                  import mink
```

**关键放大因素**：`universal_manipulation/__init__.py` 会**主动加载** `mink_solver`。因此失败点不是"运行某个脚本时"，而是**`import discoverse.universal_manipulation` 这一句本身**——影响范围比"脚本跑不了"大得多，所有测试、所有下游代码全部受阻。

`quadprog` 同理，它是 `solver_type` 的默认后端（`mink_solver.py:45`）。

### 7.5 修复方案

```toml
dependencies = [
    ...
    # IK 求解链路的硬依赖，非可选：
    #   universal_manipulation/__init__.py 会主动加载 mink_solver，
    #   而 mink_solver.py:8 是模块级 `import mink` —— 缺失则整个包 import 即失败，
    #   不只是运行脚本报错。quadprog 是 solver_type 的默认后端（mink_solver.py:45）。
    "mink>=1.2.0",
    "quadprog>=0.1.13",
]
```

版本下限取当前实测可用版本（`mink 1.2.0` / `quadprog 0.1.13`）。

### 7.6 回归验证

```bash
$ python -m pytest tests/ -q
113 passed, 4 skipped, 45 deselected, 10 xfailed in 3.10s     # 无回退
```

依赖声明已确认写入并可被解析。

**理想的守护测试**（未实施）：CI 中加一个干净环境 job，执行 `pip install -e . && python -c "import discoverse.universal_manipulation"`。**当前无此保护——依赖缺失只能靠人工发现。**

### 7.7 影响范围

**全新安装 100% 失败。** 对作品集/开源项目是硬伤——**他人 clone 后第一步就死**。

这是本次唯一动手修复的未修缺陷，理由即在此：它挡在所有人的第一步。

---

## 八、缺陷 N｜配置错误 → 静默删数据 → 无限重试

**严重级别**：🟠 High ｜ **状态**：⏸ 未修复 ｜【静态核实】

### 8.1 影响模块

- `discoverse/universal_manipulation/task_base.py:172-174`
- `examples/universal_tasks/universal_task_runtime.py:340-341,385,457`

### 8.2 复现步骤（推断路径，未实跑）

```yaml
# 在 place_block.yaml 的成功条件里把物体名写错
conditions:
  - object_a: block_gren      # 少了一个 e
```

```bash
python examples/universal_tasks/universal_task_runtime.py -r airbot_play -t place_block --headless
# 不加 -1，进入循环模式
```

### 8.3 预期 vs 实际

| | 行为 |
|---|---|
| **预期** | 配置错误 → 明确报错退出，提示物体名不存在 |
| **实际** | 打印一行中文警告 → 判为"任务失败" → **删除保存目录** → 重新随机化 → **无限重复** |

### 8.4 根因分析：四个独立问题叠加

**问题一：裸 `except` 吞掉配置错误**（`task_base.py:172-174`）

```python
except Exception as e:
    print(f"条件检查失败 ({condition.get('description', '未知条件')}): {e}")
    return False
```

物体名写错 → `self.mj_data.body(obj1)` 抛 `KeyError` → 被吞 → **表现为"任务判定失败"**，与真实的任务失败无法区分。

**问题二：失败即删除**（`universal_task_runtime.py:340-341`）

```python
if not self.success:
    shutil.rmtree(self.save_dir, ignore_errors=True)
```

`ignore_errors=True` 意味着**删除本身出错也不报**。

**问题三：目录名不含 episode 索引**（:385）

```python
self.save_dir = os.path.join(DISCOVERSE_ROOT_DIR, "data",
                             f"{self.robot_name}_{self.task.task_config.task_name}")
```

**第 2 轮的失败会删掉第 1 轮成功保存的数据。**

**问题四：无限循环**（:457）

```python
while True:
```

唯一出口是 `if once: break`（:474）和 `viewer_closed`（:478）。**headless + 循环模式下两者都不触发。**

### 8.5 失效链路

```
配置 typo → KeyError → 裸 except 吞掉 → 判为任务失败
    → rmtree 删除目录（含上一轮成功数据）→ reset 重新随机化
    → 再次 KeyError → 再次删除 → ……无限
```

### 8.6 修复方案（按性价比排序）

| 顺序 | 改动 | 效果 |
|---|---|---|
| 1 | `save_dir` 加 episode 索引 | **单独此项即可阻止数据丢失** |
| 2 | 收窄 `except`，让 `KeyError`/`AttributeError` 向上抛 | 区分"配置错误"与"任务失败"，配合 §4.7 退出码 2 |
| 3 | `while True` 加连续失败上限 | 防止无限空转 |

### 8.7 回归验证方案（未实施）

```python
def test_config_typo_raises_not_silently_deletes(tmp_path):
    """物体名写错必须报错，而非判为任务失败并删数据。"""
    # 构造含 typo 的配置，断言抛出 KeyError 而非 return False
```

### 8.8 影响范围

**一个配置 typo 会静默删除已采集数据，并无限重试且每轮都删。** 在长时间无人值守的数据采集场景下，可能损失全部成果且无任何报错信息。

---

## 九、缺陷 V｜`cover_cup` 声明不存在的相机，8/9 机器人崩溃

**严重级别**：🟠 High ｜ **状态**：⏸ 未修复 ｜【实测】

### 9.1 影响模块

- `discoverse/configs/tasks/cover_cup.yaml:14`
- `models/mjcf/manipulator/*/`（各机器人 MJCF）

### 9.2 复现步骤

```bash
python examples/universal_tasks/universal_task_runtime.py -r panda -t cover_cup -1 --headless
```

### 9.3 预期 vs 实际

| | 行为 |
|---|---|
| **预期** | 任务正常运行，或给出可理解的配置错误提示 |
| **实际** | 崩溃：`Camera 'eye_arm' not found in the MJCF model.` |

### 9.4 根因分析

`cover_cup.yaml:14` 为**所有机器人**声明相机：

```yaml
  cameras:
    - name: "eye_arm"    # 机械臂末端相机
```

而该相机仅存在于 airbot_play 系列 MJCF：

```bash
$ grep -rl "eye_arm" models/mjcf/
models/mjcf/manipulator/airbot_play/airbot_play.xml
models/mjcf/manipulator/airbot_play_force/airbot_play_peg.xml
models/mjcf/manipulator/new_airbot_play/mjx_airbot_play.xml
```

**任务级配置假设了机器人级的硬件特性。** 9 个机器人中 8 个没有这个相机。

### 9.5 修复方案

三选一：

1. **相机配置下沉到机器人级** —— 任务只声明"需要末端相机"，具体名字由机器人配置提供（推荐，符合项目"配置驱动"原则）
2. 任务配置中做相机存在性校验，缺失时降级而非崩溃
3. 为其余 8 个 MJCF 补充 `eye_arm` 相机

### 9.6 回归验证方案（未实施）

```python
@pytest.mark.parametrize("robot", ALL_ROBOTS)
@pytest.mark.parametrize("task", ALL_TASKS)
def test_declared_cameras_exist_in_mjcf(robot, task):
    """任务声明的每个相机都必须在该机器人的 MJCF 中存在。"""
```

**这条测试价值极高**：45 个组合一次性覆盖，能防住整类"配置引用不存在的模型实体"缺陷。

### 9.7 影响范围

**Day 5 flake 实验中 15.8% 的运行（355/2250）。**

关键危害不在崩溃本身，而在**污染统计**：这些是配置崩溃而非 flake，混入成功率统计会让 `cover_cup` 整行热力图恒黑，**误导他人去调 IK 容差**——而真正原因是一行配置。

剔除前后真实成功率差 **7.7 个百分点**（41.1% → 48.8%）。

> 面试可用点：**分析 flake 数据前必须先剔除非 flake 失败。** 否则统计量本身是错的，后续所有推论都不成立。

---

## 十、缺陷 B｜4/5 任务 `camera_configs` 为空，采集零图像

**严重级别**：🟠 High ｜ **状态**：⏸ 4 xfail 守着 ｜【实测】

### 10.1 影响模块

- `discoverse/configs/tasks/place_block.yaml` 等 4 个任务配置
- `discoverse/universal_manipulation/recorder.py`

### 10.2 复现步骤

```bash
python -m pytest tests/unit/test_task_config.py::test_camera_configs_nonempty -v
```

### 10.3 预期 vs 实际

| | 行为 |
|---|---|
| **预期** | 数据采集产出图像序列 |
| **实际** | `camera_configs` 为空 → **静默产出零张图像**，采集流程全程无警告 |

xfail 记录：

```
缺陷 B：place_block 的 camera_configs 为空 —— 数据采集会静默产出零张图像
```

受影响任务：`place_block`、`place_coffeecup`、`place_kiwi_fruit`、`stack_block`（4/5）。

### 10.4 根因分析

配置中 `camera_configs` 为空列表，而遍历逻辑对空列表**直接跳过循环体**——`for cam in []` 不执行任何操作，也不报错。

这是 §1.3 模式的第三种表现形式：**空集合的静默**。

根因在 §十一 缺陷 I：校验器不把 `observation` 列为必填，空配置能通过校验。

### 10.5 修复方案

1. 为 4 个任务补齐 `camera_configs`
2. 配合 §十一 修复，使空配置无法通过校验
3. `recorder` 在零相机时主动告警

### 10.6 回归验证

已有 4 条 `xfail(strict=True)` 测试守护（`test_camera_configs_nonempty[<task>]`）。修复后自动转 XPASS 提醒撤标记。

### 10.7 影响范围

**模仿学习数据集无图像即完全无用**，而采集过程全程无警告——可能跑完上百个 episode 才发现。

⚠️ `recorder.py` 覆盖率仅 **19%**，是当前最大测试盲区。

---

## 十一、缺陷 I｜`_validate_config` 未把 `observation` 列必填

**严重级别**：🟡 Medium ｜ **状态**：⏸ 1 xfail 守着 ｜【实测】

### 11.1 影响模块

`discoverse/universal_manipulation/task_config.py:76-81`

### 11.2 复现步骤

```bash
python -m pytest tests/unit/test_task_config.py::test_validate_config_should_require_observation -v
```

### 11.3 预期 vs 实际

| | 行为 |
|---|---|
| **预期** | 缺少 `observation` 的任务配置校验失败 |
| **实际** | 校验通过。**4/5 任务缺相机配置却全部合法** |

### 11.4 根因分析

```python
required_fields = [
    'task_name',
    'description'
]
```

**必填字段只有两个**，且都是元数据。真正影响功能的 `observation`（含 `camera_configs`）不在其中。

> **校验器只检查了"文档性字段"，没检查"功能性字段"。** 这类校验给人以安全感，实则不设防。

### 11.5 修复方案

```python
required_fields = ['task_name', 'description', 'observation']
```

并对 `observation.camera_configs` 做非空校验。

**注意**：此改动会让现有 4 个任务配置立即校验失败——**这是正确行为**，但需与 §十 缺陷 B 的修复同批进行，否则会阻断现有流程。

### 11.6 回归验证

已有 `xfail(strict=True)` 守护。

### 11.7 影响范围

**它是缺陷 B 的根因**。校验层放行 → 空配置进入运行时 → 静默产出零图像。修 I 才能防住 B 的再次发生。

---

## 十二、缺陷 U｜IK `posture_task` 目标跨调用泄漏

**严重级别**：🟡 Medium ｜ **状态**：✅ 已修复（`c722ca8`）｜【实测】

### 12.1 影响模块

`discoverse/universal_manipulation/mink_solver.py:120`

### 12.2 复现步骤

同一 target/qpos 连续三次调用 `solve_ik`：

```
第 1 次：不传 reference_qpos
第 2 次：传 reference_qpos
第 3 次：不传 reference_qpos      ← 期望回到第 1 次的结果
```

### 12.3 预期 vs 实际

| | 行为 |
|---|---|
| **预期** | 第 3 次与第 1 次结果相同（相同输入 → 相同输出） |
| **实际** | 第 3 次与**第 2 次逐位相同** —— 上一次的 reference 残留了 |

### 12.4 根因分析

修复前：

```python
if reference_qpos is not None:
    temp_config = mink.Configuration(self.mj_model)
    temp_config.update(reference_qpos)
    self.posture_task.set_target_from_configuration(temp_config)
    #  ↑ set_target 也在 if 块内
```

**不传 reference 时根本不设目标**，于是 `posture_task` 沿用上一次调用设定的值。

> **这是典型的对象状态泄漏**：求解器是有状态对象，但接口表现得像纯函数。调用方无从得知"这次结果取决于上次传了什么"。

### 12.5 修复方案

```python
temp_config = mink.Configuration(self.mj_model)
if reference_qpos is not None:
    temp_config.update(reference_qpos)
else:
    temp_config.update(self._default_posture_qpos)
self.posture_task.set_target_from_configuration(temp_config)   # 移出 if 块
```

⚠️ **修复对应两个独立契约**：

1. **把 `set_target` 移出 `if` 块** → 消除泄漏
2. **补 `else` 分支恢复默认姿态** → 决定"默认姿态取谁"

第 2 点**不是修泄漏**——移出后有没有 `else` 都不泄漏。`else` 决定默认值取 `home`（`[0,-1,1.2,1.5708,-1.2,-1.5708]`）还是 mink 默认的 `qpos0`（airbot_play 全 0），二者差距很大，会影响冗余自由度下的解选择。**那是行为变更，不是缺陷修复。**

### 12.6 回归验证

3 条测试（`tests/unit/test_mink_solver.py`）：

- `test_repeated_solve_is_deterministic` —— 守 `configuration`，防有人删掉 :99 的 update
- `test_posture_target_does_not_leak_across_calls` —— 泄漏回归
- `test_default_posture_target_is_home_not_qpos0` —— 默认姿态回归

覆盖率：`mink_solver.py` **46% → 90%**，TOTAL 59% → 62%。

> **第三条测试来自一次失败的变异验证**：注释掉 `else` 后前两条测试**仍全绿**，暴露出"默认姿态是 home"这个契约无人守护。补上第三条后再次变异，只有它转红——**精确区分了两个契约**。
>
> 面试可用点：**变异测试是检验"测试是否真的在测东西"的手段。** 全绿不代表覆盖充分，故意改坏代码看测试是否报警才算数。

### 12.7 一条被推翻的记录

⚠️ 计划文档记载"`self.configuration` 泄漏，需 try/finally"——**实测不成立**。`solve_ik:99` 每次入口都执行 `configuration.update(current_qpos)`，已隔离该状态；两次同参调用解逐位相同。

### 12.8 影响范围

IK 可复现性。在冗余自由度机器人上会影响解的选择，导致相同任务产生不同轨迹。属于 §三 缺陷 #1 之外的**第二个不可复现来源**。

---

## 十三、缺陷 S｜贴图随机源不受 seed 管控

**严重级别**：🟡 Medium ｜ **状态**：⏸ 1 xfail 守着 ｜【实测】

### 13.1 影响模块

`discoverse/utils/__init__.py:86-97`

### 13.2 复现步骤

```bash
python -m pytest tests/simulation/test_determinism.py::test_texture_randomization_respects_seed -v
```

### 13.3 预期 vs 实际

| | 行为 |
|---|---|
| **预期** | 相同 seed → 相同贴图选择 |
| **实际** | 贴图选择不可复现，两个分支都绕过 `SceneRandomizer.rng` |

### 13.4 根因分析

```python
def get_random_texture():
    TEXTURE_1K_PATH = os.getenv("TEXTURE_1K_PATH", ...)
    if not TEXTURE_1K_PATH is None and os.path.exists(TEXTURE_1K_PATH):
        for _ in range(5):
            img_path = os.path.join(TEXTURE_1K_PATH,
                                    random.choice(os.listdir(TEXTURE_1K_PATH)))   # stdlib random
            ...
    else:
        return Image.fromarray(np.random.randint(0, 255, (768,768,3), dtype=np.uint8))  # np 全局流
```

**两个分支用了两个不同的失控随机源**：

| 分支 | 随机源 | 当前可达性 |
|---|---|---|
| `if`（有贴图目录） | stdlib `random.choice` | 不可达（`TEXTURE_1K_PATH` 未配置） |
| `else`（无贴图目录） | `np.random` 全局流 | **可达** |

**它是模块级函数，没有 `self.rng` 可用**——这是修复困难的根本原因。

### 13.5 修复方案

```python
def get_random_texture(rng: np.random.Generator | None = None):
    rng = rng if rng is not None else np.random.default_rng()
    ...
```

由调用方注入 `SceneRandomizer.rng`。**牵连全部 4 个调用方**，故本次未做。

### 13.6 回归验证

`xfail(strict=True)` 守护，reason 中完整记录了两个分支的失控原因与未修理由。

### 13.7 影响范围

**这是缺陷 #1 修复的已知边界**——位置/光照/姿态已可复现，贴图尚未。

对视觉策略训练而言，数据多样性不可控意味着**无法复现某次训练用到的确切数据分布**。

---

## 十四、缺陷 K｜夹爪工厂假多态

**严重级别**：🟡 Medium ｜ **状态**：⏸ 未修复 ｜【静态核实】

### 14.1 影响模块

`discoverse/universal_manipulation/gripper_controller.py:1-10,26-42,70-71`

### 14.2 复现步骤

```python
cfg = {"type": "tendon", "ctrl_index": 6, "ctrl_range": [0, 0.04]}
g = create_gripper_controller(cfg, model, data)
print(type(g))     # 无论 type 写什么，永远是 TwoFingerGripper
```

### 14.3 预期 vs 实际

| | 行为 |
|---|---|
| **预期** | 按 `type` 返回三种夹爪实现之一 |
| **实际** | 永远返回 `TwoFingerGripper`，`type` 从不被读取 |

### 14.4 根因分析

**文件头 docstring 的承诺**（:1-10）：

```python
"""
夹爪控制器 - 统一不同夹爪实现方式的接口

支持三种夹爪实现模式：
1. tendon控制 (如airbot_play)
2. equality约束 (如panda)
3. 单关节控制 (如ur5e)

支持从传感器数据获取夹爪状态
"""
```

**工厂函数的实现**（:70-71）：

```python
def create_gripper_controller(gripper_config, mj_model, mj_data) -> GripperController:
    return TwoFingerGripper(gripper_config, mj_model, mj_data)
```

**整个函数体一行，`gripper_config["type"]` 从未被读取。** 全文件只有 `GripperController(ABC)` 和 `TwoFingerGripper` 两个类——**三种模式中的两种不存在**。

**附带问题一：注释与代码矛盾**（:26-31）

```python
# 从配置文件获取控制范围，但优先使用从MJCF文件中读取的实际关节范围
self.config_ctrl_range = gripper_config["ctrl_range"]
# 如果配置中指定了关节名称，尝试从MJCF获取真实范围
# 使用配置中指定的控制范围
self.ctrl_range = self.config_ctrl_range      # 根本没读 MJCF
```

**附带问题二：抓取检测不存在**

`sensor_index` 在 :35-42 赋值后**全库无人读取**；`grasp_threshold` 在 YAML 中声明（如 `panda.yaml:41`）但无消费者。**"支持从传感器数据获取夹爪状态"这句承诺完全落空。**

### 14.5 为什么当前没出事

现有 9 个机器人**恰好都是"双指 + 单控制量"**，`TwoFingerGripper` 巧合正确。这是典型的**巧合正确（coincidental correctness）**——测试全绿不代表实现正确，只代表当前输入没触发差异。

### 14.6 修复方案

**低成本诚实版本**（约 20 分钟，推荐）：

1. 删除 docstring 中的虚假承诺，改为"当前仅支持双指单控制量夹爪"
2. 修正 :26-31 说谎的注释
3. 工厂对未知 `type` **抛异常**而非静默返回默认实现

**完整版本**（1 天以上）：实现三种夹爪类，属设计决策。

> **推荐低成本版本的理由**：假多态的真正危害不是"少了两个类"，而是**文档承诺让人以为可以直接接入腱驱动夹爪**。让它失败得响亮，比让它静默用错模型好。

### 14.7 回归验证方案（未实施）

```python
def test_factory_rejects_unsupported_gripper_type():
    """未知夹爪类型必须抛异常，而非静默返回双指实现。"""
    with pytest.raises(ValueError):
        create_gripper_controller({"type": "tendon", ...}, model, data)
```

### 14.8 影响范围

当前零影响（巧合正确）。新增腱驱动或 equality 约束夹爪时，会**静默使用错误的控制模型**——夹爪行为异常但不报错，排查成本极高。

---

## 十五、缺陷 M｜`step()` 返回值语义重载

**严重级别**：🟡 Medium ｜ **状态**：⏸ 未修复 ｜【静态核实】

### 15.1 影响模块

`examples/universal_tasks/universal_task_runtime.py:213-262,280-282,331`

### 15.2 复现步骤

观察 Day 1 遇到的现象：

```
完成状态: 10/10
任务成功: ❌ 否
```

"10/10 完成"却"未成功"——阅读者无法从输出判断到底发生了什么。

### 15.3 预期 vs 实际

| | 行为 |
|---|---|
| **预期** | 调用方能区分"正常结束"与各类异常终止 |
| **实际** | 2 个布尔值承载 5 种语义，三种失败原因坍缩为同一个 `break` |

### 15.4 根因分析

`step()` 的 5 个返回点：

| 行号 | 返回值 | 真实含义 |
|---|---|---|
| :230 | `True` | **全部状态完成**，任务正常结束 |
| :257 | `True` | 单步执行正常，**继续循环** |
| :223 | `False` | primitive 设置失败（IK 不可达） |
| :234 | `False` | **超时**（`mj_data.time > max_time`） |
| :262 | `False` | 异常（裸 `except`） |

**`True` 同时表示"结束了"和"没结束"；`False` 同时表示三种完全不同的失败。**

调用方（:280-282）：

```python
while self.running:
    if not self.step():
        break               # 三种 False 原因坍缩为一个 break
```

**误导性打印**（:331）：

```python
print(f"   完成状态: {self.stm.state_idx}/{self.total_states}")
```

`state_idx` 是**状态机推进进度**，与任务成功与否无关。状态全部走完但物体没放到位，就会出现"10/10 但失败"。**这正是 Day 1 那次困惑的来源。**

### 15.5 修复方案

**完整版**（1 天以上）：引入枚举

```python
class StepResult(Enum):
    CONTINUE = auto()       # 继续循环
    COMPLETED = auto()      # 全部状态完成
    IK_FAILED = auto()
    TIMEOUT = auto()
    ERROR = auto()
```

涉及所有调用方，成本高。

**低成本缓解**（一行，强烈推荐先做）：

```python
print(f"   状态机进度: {self.stm.state_idx}/{self.total_states}")
```

把"完成状态"改为"状态机进度"，**消除最主要的误读来源**。

> 面试可用点：**一行改动消除 80% 危害，剩下 20% 需要 1 天重构** —— 这类判断比"全都要修"更能体现工程取舍。

### 15.6 回归验证方案（未实施）

枚举化后，每个返回点对应一条断言其语义的测试。

### 15.7 影响范围

**可诊断性。** 失败时无法从返回值和日志判断根因，排查只能靠加 print。这直接拖慢了 Day 5 的 BUCKET 分桶工作——分桶逻辑不得不去**匹配 stdout 字符串**，而非读取结构化状态。

---

## 十六、缺陷 O｜IK `dt` 被硬编码遮蔽（休眠缺陷）

**严重级别**：🟢 Low（由中降低）｜ **状态**：✅ 已修复（`c722ca8`）｜【实测】

### 16.1 影响模块

`discoverse/universal_manipulation/mink_solver.py:50,126`

### 16.2 复现步骤

```yaml
# 任一机器人 YAML
ik_solver:
  dt: 0.002        # 声明值
```

观察实际积分步长。

### 16.3 预期 vs 实际

| | 行为 |
|---|---|
| **预期** | 使用配置声明的 `dt: 0.002` |
| **实际** | 使用硬编码的 `1e-3`。**9/9 机器人的 `dt` 声明全部无效** |

### 16.4 根因分析

```python
self.dt = ik_solver_config.get('dt', ...)     # :50  从配置读
...
def solve_ik(...):
    dt = 1e-3                                  # :126 局部变量遮蔽了 self.dt
    ...
    self.configuration.integrate_inplace(velocity, dt)
```

**局部变量 `dt` 遮蔽（shadow）了 `self.dt`。** 配置读了、存了，但求解时用的是另一个值。

### 16.5 关键实测：当前行为影响为零

修复前后 IK 解**逐位相同**（`atol=1e-9`，测了 2/5/10/15cm 四个偏移）。

**原因**：`mink.solve_ik` 内部把任务误差**除以** dt 得期望速度，`integrate_inplace` 又**乘以** dt 积分回去——**一除一乘，dt 约掉了**。

它仅在配置了 `mink.VelocityLimit` 时才影响单步位移上限。

### 16.6 为什么仍然修复

定性为**休眠缺陷（dormant defect）**：

> 当前零行为影响，但一旦引入速度限制，**配置写 0.002 实际按 0.001 算，限幅严一倍，而配置看起来完全正确**——届时排查成本极高。

严重度由中降为低，仍修复——**成本一行且实测零风险**。

### 16.7 回归验证

**未写行为测试，且这是有意为之。**

修复前后无可观测差异，写出来的断言**永远为真**——它不验证任何东西，只会给人虚假的覆盖率。

> 面试可用点：**不是每个修复都该配测试。** 判据是"这条测试失败时能告诉我什么"。若答案是"什么都不能"，那它就是噪音。这比机械地追求"每个 commit 都带测试"更重要。

### 16.8 影响范围

当前为零。属**技术债预埋**——为未来引入速度限制时的正确行为铺路。

---

## 十七、缺陷 H｜4/9 机器人 `qpos_dim` ≠ MJCF `nq`

**严重级别**：🟢 Low（**由高降级**，见 §2.3）｜ **状态**：⏸ 4 xfail 守着 ｜【实测】

### 17.1 影响模块

- `discoverse/configs/robots/{arx_x5,iiwa14,piper,rm65}.yaml:9`
- `discoverse/universal_manipulation/robot_config.py:117-119`
- `discoverse/universal_manipulation/robot_interface.py:46,50`

### 17.2 复现步骤

```bash
python -m pytest tests/unit/test_robot_config.py::test_qpos_dim_matches_mjcf_nq -v
```

### 17.3 预期 vs 实际

| 机器人 | YAML `qpos_dim` | MJCF `nq` |
|---|---|---|
| arx_x5 | 7 | 8 |
| iiwa14 | 9 | **15** |
| piper | 7 | 8 |
| rm65 | 12 | 14 |

### 17.4 根因分析

逐个遍历 MJCF 的 `jnt_type` 确认：**4 个模型零个 FREE 关节**——推翻了 checkpoint 中"iiwa14 可能有 FREE 关节占 7 个 qpos"的猜测。

**真因是夹爪建模复杂度超出配置假设**：

| 机器人 | MJCF 实际构成 | YAML 假设 |
|---|---|---|
| iiwa14 | 7 臂 + 夹爪 8 HINGE（Robotiq 式平行连杆：left/right 各 driver/coupler/spring_link/follower）= **15** | 按 2 手指计 = 9 |
| rm65 | 6 臂 + 夹爪 6 HINGE + 2 SLIDE = **14** | 12 |
| arx_x5 / piper | 6 臂 + 2 SLIDE 手指 = **8** | 7 |

### 17.5 严重度降级依据【实测】

全库检索 `qpos_dim` **仅 4 处引用**，构成一条死路：

```
robot_config.py:117-119   property 定义
robot_interface.py:46     self.qpos_dim = robot_config.qpos_dim
robot_interface.py:50     self.target_qpos = np.zeros(self.qpos_dim)   ← 终点
```

```bash
$ grep -rn "target_qpos" --include=*.py . | grep -v /policies/
discoverse/universal_manipulation/robot_interface.py:50
```

**`target_qpos` 被赋值一次，全库无任何读取者。**

且**不存在任何 `qpos[:qpos_dim]` 切片**——所有 `qpos[:...]` 用的是 `nu`/`nj`/`njq`/字面量，来自 `robots_env/`、`task_base/` 这个**从不 import `RobotConfigLoader`** 的独立子系统。

真实 IK 路径按**关节名**解析（`robot_interface.py:55-63` 的 `mj_name2id`），**不按维度**。

> **原记录中"IK 按 YAML 维度切 qpos 数组，会静默取错关节"这个失败模式，在代码中不存在。** 该说法曾出现在 5 份文档中。

### 17.6 修复方案

定义 **`qpos_dim ≡ MJCF nq`**，修正 4 个 YAML 数值。

**依据**：`ctrl_dim` 已覆盖"可控自由度"语义且 9/9 正确，故 `qpos_dim` 取 `nq` 才不冗余；且唯一断言它的测试正是拿它与 `nq` 比。

**"待决策"卡点已解除**——原本担心改动破坏行为，实测确认**无消费者可破坏**。

### 17.7 回归验证与一个测试自身的缺陷

4 条 `xfail(strict=True)` 守护。

⚠️ **但该测试自身有缺陷**：`test_robot_config.py:149` 使用**命令式** `pytest.xfail(...)`，它**立即中断测试**——那 4 个机器人的 MJCF **从未被加载**，`model.nq` 从未被比较。比对值取自 :20-25 的**硬编码表**（2026-07-30 测得）：

```python
QPOS_DIM_MISMATCH = {
    "arx_x5": (7, 8), "iiwa14": (9, 15),
    "piper":  (7, 8), "rm65":   (12, 14),
}
```

**后果：若 MJCF 上游被修好，该测试仍会继续 xfail，不会报警。**

相邻的 `test_ctrl_dim_matches_mjcf_nu`（:121-134）无此问题——它总是加载并断言，可作修复参照。

> 面试可用点：**测试本身也会有缺陷。** 命令式 `pytest.xfail()` 与装饰器 `@pytest.mark.xfail(strict=True)` 的区别在于前者跳过执行、后者仍执行并检查结果——**只有后者能在缺陷被修复时报警**。

### 17.8 影响范围

**当前运行时影响为零**，仅分配一个长度错误但无人读取的零数组。

属**潜在风险**：`qpos_dim` 是公开 property（经 `__init__.py` 导出），**第一个写下 `data.qpos[:cfg.qpos_dim]` 的人会在 4/9 机器人上踩到静默错误**。

---

## 十八、缺陷 Q｜空 `conditions` → 恒判定成功

**严重级别**：🟢 Low（当前不可达）｜ **状态**：⏸ 未修复 ｜【静态核实】

### 18.1 影响模块

`discoverse/universal_manipulation/task_base.py:96-97,106-117,121-135`

### 18.2 复现步骤（构造性，当前配置不可达）

```yaml
success_check:
  type: simple
  conditions: []      # 空列表
```

### 18.3 预期 vs 实际

| | 行为 |
|---|---|
| **预期** | 无成功条件 → 报错（配置无意义） |
| **实际** | **恒判定成功**，成功率 100% |

### 18.4 根因分析

```python
def _check_simple_conditions(self, success_config) -> bool:
    conditions = success_config.get('conditions', [])
    print(f"   📋 检查 {len(conditions)} 个简单条件...")
    for i, condition in enumerate(conditions):
        ...
        if not result:
            return False
    return True          # ← 空列表直接到这里
```

空列表跳过循环体，**无条件 `return True`**。组合路径同理：`all([])` 在 Python 中返回 `True`（空真，vacuous truth）。

**附带风险**（:96-97）：`success_config.get(...)` 在 `success_check` 为 `None` 时抛 `AttributeError`，且该行**不在任何 try/except 内**。

### 18.5 可达性核实【实测】

加载全部 5 个 shipped 配置（经模板继承解析）：

| 任务 | 条件数 |
|---|---|
| cover_cup | 3 |
| place_block | 1 |
| place_coffeecup | 2 |
| place_kiwi_fruit | 2 |
| stack_block | 3 |

**均非空，当前不可达。**

⚠️ **一个易错点**：`place_block.yaml` 裸 grep **查不到** `success_check`——它经 `extends` 从 `templates/place_object.yaml:27-34` 继承。**仅凭 grep 会误判此缺陷可达。** 必须走真实的配置加载器验证。

> 面试可用点：**配置继承体系下，静态 grep 不足以判断可达性。** 必须用运行时加载器解析。

### 18.6 修复方案

```python
if not conditions:
    raise ValueError(f"任务 {task_name} 的 success_check.conditions 为空 —— "
                     f"无条件的成功判定恒为真，这几乎总是配置错误")
```

并对 `success_check is None` 做前置检查。

### 18.7 回归验证方案（未实施）

```python
def test_empty_conditions_raises_not_vacuous_success():
    with pytest.raises(ValueError, match="conditions 为空"):
        ...
```

### 18.8 影响范围

**当前为零，但失败模式最恶劣**——静默的 100% 成功率。若有人新增任务时漏写条件，会得到"完美通过"的假象。属**廉价保险**（约 30 分钟）。

---

## 十九、缺陷 P｜`panda.yaml` 重复键 + 乱码残留

**严重级别**：🟢 Low ｜ **状态**：⏸ 未修复 ｜【实测】

### 19.1 影响模块

`discoverse/configs/robots/panda.yaml:5-29`

### 19.2 复现步骤

```bash
python -c "import yaml; d=yaml.safe_load(open('discoverse/configs/robots/panda.yaml')); print(d['kinematics'].keys())"
```

### 19.3 预期 vs 实际

| | 行为 |
|---|---|
| **预期** | YAML 中每个键唯一 |
| **实际** | 两个顶层 `kinematics:`（:6、:16）。第二块**静默覆盖**第一块 |

`safe_load` 后实际生效的键：`['base_link','end_effector_site','qpos_dim','ctrl_dim','arm_joints','arm_joint_names']`——**第一块独有的 `posture_cost` 和 `dt` 消失了**。

### 19.4 根因分析

**重复键**：YAML 规范下重复键不报错，后者静默覆盖前者。9 个机器人 YAML 中**仅 panda 存在此问题**。

**乱码**（:13）：

```yaml
dt: 0.002    # 积分时间步长 (参考示例)ika Panda 7-DOF协作机械臂"
```

`ika Panda 7-DOF协作机械臂"` 是第 3 行 `description` 的碎片，**含未闭合的双引号**。因位于 `#` 注释内，YAML 未报错。

### 19.5 为什么当前无行为影响【实测】

两块 `kinematics` 的 **6 个重叠键字节完全相同**，故覆盖无差异；第一块独有的 `posture_cost`/`dt` 虽被丢弃，但这两项在 `ik_solver` 段有正确定义——**而代码实际是从 `ik_solver` 读的**。

**纯属巧合。** 若两块数值有差异，就会变成一个极难排查的缺陷。

### 19.6 修复方案

1. 删除第一块（:5-14），含乱码行
2. **配套加一条跨 9 个 YAML 的重复键检测测试**

```python
class DuplicateKeyLoader(yaml.SafeLoader):
    """重复键直接报错，而非静默覆盖。"""
    def construct_mapping(self, node, deep=False):
        keys = set()
        for k, _ in node.value:
            key = self.construct_object(k, deep=deep)
            if key in keys:
                raise ValueError(f"重复键: {key}")
            keys.add(key)
        return super().construct_mapping(node, deep)
```

### 19.7 回归验证方案（未实施）

上述 loader 对全部 9 个机器人 + 5 个任务 YAML 跑一遍。

### 19.8 影响范围

当前零行为影响。乱码中的未闭合引号是**潜在解析隐患**（若有人取消注释或重排该行）。

> **这是"配置文件也会有 bug"的优质案例。** 团队通常对 `.py` 做 lint，却很少对 `.yaml` 做重复键检查——而配置错误的排查成本往往更高。

---

## 二十、缺陷 R｜`randomize_scene` 返回类型与注解不符

**严重级别**：🟢 Low ｜ **状态**：⏸ 未修复 ｜【静态核实】

### 20.1 影响模块

`discoverse/universal_manipulation/task_base.py:85-88`

### 20.2 复现步骤

```python
result = task.randomize_scene()
print(result)      # 永远是 None，尽管注解写着 -> bool
```

### 20.3 预期 vs 实际

| | 行为 |
|---|---|
| **预期** | 返回 `bool` 表示随机化是否成功 |
| **实际** | 两条路径**都返回 `None`** |

### 20.4 根因分析

```python
def randomize_scene(self, max_attempts: int = 100) -> bool:
    if not self.randomization_config:
        return                                                   # ← 裸 return，None
    self.randomizer.exec_randomization(self.randomization_config, max_attempts)
    # ← 未 return，隐式 None
```

被丢弃的返回值是真实存在的：`randomization.py:77` 的 `exec_randomization` 注解 `-> bool` 且末尾 `return True`。

### 20.5 修复方案

```python
def randomize_scene(self, max_attempts: int = 100) -> bool:
    if not self.randomization_config:
        return False
    return self.randomizer.exec_randomization(self.randomization_config, max_attempts)
```

约 5 分钟。

### 20.6 回归验证方案（未实施）

断言返回值类型为 `bool`，且无随机化配置时为 `False`。

### 20.7 影响范围

当前无调用方读取返回值（`universal_task_runtime.py:361`、`test_determinism.py:232` 均忽略），故为**潜在缺陷**。

真实危害：**随机化失败（如 100 次尝试仍无法无碰撞放置物体）无法被上层感知**——场景可能处于非法状态而流程继续。

---

## 廿一、缺陷 T｜库代码 96 处 `print` 代替 `logging`

**严重级别**：🟢 Low ｜ **状态**：⏸ 未修复 ｜【实测】

### 21.1 影响模块

| 目录 | `print(` 数量 | 主要文件 |
|---|---|---|
| `discoverse/universal_manipulation/` | **47** | randomization.py 24、task_base.py 11、robot_interface.py 7 |
| `discoverse/envs/` | **49** | simulator.py 34、make_env.py 11 |
| **合计** | **96** | **两个目录零 `import logging`** |

### 21.2 复现步骤

```bash
grep -rc "print(" discoverse/universal_manipulation/ discoverse/envs/
grep -rn "import logging" discoverse/universal_manipulation/ discoverse/envs/   # 无输出
```

### 21.3 预期 vs 实际

| | 行为 |
|---|---|
| **预期** | 库代码用 logger，由使用者决定级别与去向 |
| **实际** | 全部硬编码 `print` 到 stdout，**使用者无法抑制或过滤** |

### 21.4 根因分析

**连一个 logger 都没有**——不是"用错了"，是从未建立日志设施。

作为**库**（而非脚本），这违反了基本约定：库不应擅自占用调用方的 stdout。

### 21.5 连带影响：它加剧了缺陷 #2 和 M

因为没有结构化日志，CI 层（`cicd_testing.py:121`）只能**匹配 stdout 里的 emoji** 来判断成败，Day 5 的分桶逻辑也只能**正则解析 stdout**。

> **这三条缺陷是耦合的**：无结构化输出（T）→ 无法从返回值判断状态（M）→ CI 只能字符串匹配（#2 的 hack）。

### 21.6 修复方案

**完整版**（2-3 小时）：引入模块级 logger，96 处逐一转换。

**推荐的部分版本**：仅转换约 10 处 **error/warning 级**输出，保留 emoji 进度打印。

> **理由**：全量转换产生 96 行 diff 噪音，**在评审时会淹没真正重要的修复**。而 error/warning 才是使用者真正需要过滤和采集的部分。

### 21.7 回归验证方案（未实施）

```python
def test_library_does_not_print_errors_to_stdout(capsys):
    """错误必须走 logger，以便调用方采集。"""
```

### 21.8 影响范围

- 无法按级别过滤
- CI 日志无法结构化采集
- 库使用者无法抑制输出
- **间接导致 CI 判定依赖脆弱的字符串匹配**

列为最低优先级的原因是**修复成本与 diff 噪音**，而非危害小。

---

## 廿二、缺陷 X｜MuJoCo viewer 退出时段错误

**严重级别**：🟢 Low ｜ **状态**：⏸ 未修复 ｜【静态核实】

### 22.1 影响模块

- `examples/universal_tasks/universal_task_runtime.py:488-494`
- `discoverse/envs/simulator.py:181-189`

### 22.2 复现步骤

```bash
export MUJOCO_GL=glfw     # 非无头模式
python examples/universal_tasks/universal_task_runtime.py -r airbot_play -t place_block -1 -s
# 退出时观察
```

### 22.3 预期 vs 实际

| | 行为 |
|---|---|
| **预期** | 正常退出，退出码 0 |
| **实际** | `Segmentation fault (core dumped)`，发生在 `🎬 查看器已关闭` 打印**之后** |

### 22.4 根因分析【推断】

疑为 viewer 与 GL 上下文的**清理顺序冲突**：

```python
# simulator.py:181-189
import atexit
atexit.register(self._cleanup_before_exit)
...
glfw.terminate()
```

`atexit` 处理器与 GLFW/GL 上下文销毁交互，是典型的 double-free / 顺序问题来源。

**⚠️ 此为推断，未做深入定位。**

**清理路径本身也有问题**（`universal_task_runtime.py:488-494`）：

```python
finally:
    if viewer is not None:
        try:
            viewer.close()
            print("🎬 查看器已关闭")
        except:
            pass          # ← SIGSEGV 无法被 except 捕获，这个兜底是无效的
```

### 22.5 为什么"不影响结果"——以及这个结论为何脆弱

**代码顺序确认**：结果打印与数据落盘（:325-345）**早于** viewer 清理（:488-494 的 `finally`）。段错误发生时，stdout 已刷新、文件已写入。

**但有两个重要前提**：

1. **flake 实验全程 `--headless`**（`viewer is None`），根本不走这条路径——**它只在交互式运行时出现**
2. **段错误会把进程退出码变成 139**

> ⚠️ **"不影响结果"目前成立，但成立的原因是无头模式恰好绕开了它，而非代码本身安全。**

### 22.6 与缺陷 #2 的冲突

**这是本条最重要的结论**：

§四 缺陷 #2 的修复要建立"退出码反映任务成败"的契约（0=成功，1=失败，2=配置错误）。而段错误会让**一次完全成功的运行返回 139**。

> **修 #2 时必须一并处理 X，否则新契约立即被破坏。**

### 22.7 修复方案

显式管理 GL 上下文销毁顺序，避免依赖 `atexit`；或在进程退出前显式 `os._exit(code)` 绕过有问题的清理链。

### 22.8 影响范围

当前：交互式调试体验受损，结果与数据不受影响。

修复 #2 之后：**直接破坏退出码契约**，使 CI 把成功运行判为失败。

---

## 廿三、缺陷 L′｜另外 4 个包未声明依赖 —— 缺陷 L 只修了一半

**严重级别**：🟠 High ｜ **状态**：⏸ 未修（`requirements-test.txt` 已绕过，`pyproject.toml` 未改）｜【实测】

### 23.1 影响模块

- `pyproject.toml`（核心 `dependencies` 缺 4 项）
- `discoverse/universal_manipulation/__init__.py`（eager import 全部子模块）
- 所有通过 `pip install -e .` 安装本项目的用户

### 23.2 复现步骤

**必须在干净环境复现** —— 这正是它能存活至今的原因。

```bash
docker run --rm -v "$PWD":/src python:3.10-slim bash -c '
  cd /src && pip install -q -e . 2>/dev/null
  python -c "import discoverse.universal_manipulation"'
```

或直接构建 `Dockerfile.test`（其末尾的自检 `RUN` 就是这条守护）。

### 23.3 预期 vs 实际

| | 行为 |
|---|---|
| **预期** | `pip install -e .` 后包可正常 import |
| **实际** | `ModuleNotFoundError: No module named 'yaml'`，**整个包 import 即失败** |

修完 `yaml` 会依次撞上 `av`、`OpenGL`、`PIL` —— 共 4 个。

### 23.4 根因分析

**`__init__.py` 是 eager import**，无条件加载全部子模块：

```python
from .config_utils import (...)              # → yaml
from .robot_config import RobotConfigLoader  # → yaml
from .task_config import TaskConfigLoader    # → yaml
from .mink_solver import MinkIKSolver        # → mink, quadprog（缺陷 L 已修）
from .randomization import SceneRandomizer   # → OpenGL, PIL
from .recorder import PyavImageEncoder, ...  # → av
```

四个包的实际 import 点：

| 包 | 位置 | 在 `pyproject.toml` 的哪个组 |
|---|---|---|
| `pyyaml` | `config_utils.py:2`、`robot_config.py:8`、`task_config.py:8` | `[act]` |
| `av` | `recorder.py:6-7` | `[data-collection]` |
| `PyOpenGL` | `randomization.py:10` | `[xml-editor]` |
| `pillow` | `randomization.py:11` | `[data-collection]` |

**四个全部只声明在 `[project.optional-dependencies]`，而 `pip install -e .` 只装核心 `dependencies`。**

### 23.5 ⚠️ 排查陷阱：grep 会给出相反的结论

```bash
$ grep -n "\"av\"\|PyOpenGL\|pillow\|pyyaml" pyproject.toml
72:    "PyOpenGL>=3.1.0",
81:    "pyyaml",
129:    "pillow>=10.2.0",
131:    "av"
```

**四个全部命中，看起来毫无问题。** 但命中的全在可选组里。

正确做法是按**结构**查：

```python
core = open('pyproject.toml').read().split('dependencies = [')[1].split(']')[0]
for p in ['pyyaml','av','PyOpenGL','pillow']:
    print(f"{p:10} {'在核心' if p.lower() in core.lower() else '不在核心 ← 缺'}")
# 四个全部输出「不在核心」
```

> 📌 **`grep` 回答的是「这些字符出现过吗」，不是「它在语义上生效吗」。**
>
> 这是本报告第二次记录同类陷阱 —— §2.3 的缺陷 H 也是"grep 不足以判可达性"。

### 23.6 为什么本机从未发现

这 4 个包在开发机上**全都装着**：

```bash
$ python -c "import av, OpenGL, PIL, yaml; print('全都在')"
全都在
```

它们是被 optional 组或早期手工 pip 顺带装上的。

> **开发环境是「脏」的，这份脏掩盖了依赖声明的缺失。**
> **任何在现有环境里的验证都发现不了它 —— 只有干净容器能。**

### 23.7 与缺陷 L 的关系：只修了症状

| | 缺陷 L（§七，已修） | **L′（本条）** |
|---|---|---|
| 缺失的包 | `mink`、`quadprog` | `pyyaml`、`av`、`PyOpenGL`、`pillow` |
| 机制 | `__init__.py` eager import | **完全相同** |
| 文件 | 同一个 | **同一个** |

**修缺陷 L 时看见 `mink` 缺就补 `mink`，没有系统性走完整条 eager import 链。**

这是一次**修症状而非修根因**的典型：修复动作正确，但排查范围不完整。

### 23.8 修复方案

三个层次，代价与受益不同：

| 方案 | 改哪 | 谁受益 | 代价 |
|---|---|---|---|
| **A** | `requirements-test.txt` | **只有测试镜像** | 5 分钟；`pip install -e .` 的用户照样崩 |
| **B** | `pyproject.toml` 核心 `dependencies` | 所有安装者 | 核心依赖变重（`av` 拖 ffmpeg 约 30-40 MB） |
| **C** | `__init__.py` 改惰性导入 | 所有人 + **镜像省 106 MB** | 改动大，可能破坏现有 import 路径 |

**当前状态：只做了 A。** 容器绿了，但**真 bug 仍在** —— `Dockerfile.test` 用了 `--no-deps`，容器完全绕过 `pyproject.toml`。

> ⚠️ **「容器绿了」和「bug 修好了」是两件事。**

**建议做 B**（与缺陷 L 修法一致，改同一处），**C 作为根治方案**：

```python
# 方案 C 示意：重依赖改为按需加载
def __getattr__(name):
    if name in ("PyavImageEncoder", "recoder_single_arm"):
        from .recorder import PyavImageEncoder, recoder_single_arm
        return {"PyavImageEncoder": PyavImageEncoder,
                "recoder_single_arm": recoder_single_arm}[name]
    raise AttributeError(name)
```

⚠️ **动 C 之前必须跑全量回归** —— `__all__` 导出的名字改成惰性后，现有 `from discoverse.universal_manipulation import X` 的行为会变。

### 23.9 方案 C 的量化价值【Day 9 实测】

镜像内按包体积排序：

| 包 | 体积 | 测试需要吗 |
|---|---|---|
| `av` + `av.libs` | **106 MB** | ❌ **只有 recorder 用，测试不录视频** |
| `OpenGL` | 30 MB | ✅ `randomization.py` |

**`av` 单独占 106 MB，却因 eager import 成为硬依赖。**

> 📌 昨天只能说方案 C「治本」，今天能说「**省 106 MB**」。
> **能把架构改进换算成数字，说服力完全不同。**

### 23.10 回归验证

**守护已经存在** —— `Dockerfile.test` 末尾：

```dockerfile
RUN python -c "import mujoco; print('MuJoCo', mujoco.__version__)" \
 && python -c "import discoverse.universal_manipulation; print('discoverse OK')"
```

这正是 [checkpoint-day06-07.md](checkpoint/checkpoint-day06-07.md) §2.2 当时说"留给 Day 10-11"的那道守护：

> 理想做法是 CI 里加一个干净环境 job 跑 `pip install -e . && python -c "import discoverse.universal_manipulation"`

**Day 8 以镜像构建自检的形式实现了它。** Day 10-11 的 CI 只要 build 这个镜像即可。

⚠️ **但当前守护有个盲区**：`--no-deps` 使它验证的是 `requirements-test.txt` 而非 `pyproject.toml`。**修复 B 之后应加一个不带 `--no-deps` 的干净安装 job。**

### 23.11 影响范围

- **所有新安装者**：`pip install -e .` 后包不可用
- **CI**：任何从零安装的流水线都会失败
- **文档**：README 的安装说明因此是错的

---

## 廿四、缺陷 Y｜`recoder_single_arm` 部分写入留下 0 字节坏文件

**严重级别**：🟡 Medium ｜ **状态**：⏸ 未修（3 个 xfail 守护）｜【实测】

### 24.1 影响模块

- `discoverse/universal_manipulation/recorder.py:76-91`
- `examples/universal_tasks/universal_task_runtime.py:345`（唯一调用方）
- 所有消费 `obs_action.json` 的下游（数据集加载、策略训练）

### 24.2 复现步骤

```python
import os, tempfile
from discoverse.universal_manipulation.recorder import recoder_single_arm

d = tempfile.mkdtemp()
obs_lst = [{"time": 0.0, "jq": [1, 2, 3]}]      # 故意漏 'action'
try:
    recoder_single_arm(d, obs_lst)
except Exception as e:
    print(f"抛异常: {type(e).__name__}: {e}")
f = os.path.join(d, "obs_action.json")
print("json 存在:", os.path.exists(f), "| 大小:", os.path.getsize(f))
```

实测输出：

```
抛异常: KeyError: 'action'
json 存在: True | 大小: 0
```

### 24.3 预期 vs 实际

| | 行为 |
|---|---|
| **预期** | 异常时不产出文件，或产出一个完整可解析的文件 |
| **实际** | 抛出异常，**同时在磁盘留下一个 0 字节的 `obs_action.json`** |

### 24.4 根因分析

`recorder.py:79-91`：

```python
with open(os.path.join(save_path, "obs_action.json"), "w") as fp:   # ← "w" 立即创建并截断
    save_dict = {"time": [], "obs": {"jq": []}, "act": []}
    for obs in obs_lst:                    # ← 循环里才可能抛异常
        save_dict["time"].append(obs['time'])
        save_dict["obs"]["jq"].append(obs['jq'])
        save_dict["act"].append(obs['action'])
    json.dump(save_dict, fp)               # ← 抛异常就永远走不到
```

**文件在数据准备好之前就被创建了。** `open(..., "w")` 的语义是"打开并截断"，此时文件已存在且为空；循环中途抛异常 → `with` 退出 → 留下空文件。

### 24.5 为什么危险：下游会误判为成功

```python
if os.path.exists(save_dir / "obs_action.json"):
    # 判定"这条数据采集成功了" → 误判
```

**文件存在 ≠ 数据完整。** 真去 `json.load()` 才会炸 `JSONDecodeError`，而那时可能已经是训练流水线跑到一半。

> 📌 又一次 §1.3 的模式：**声明了产物，实际是坏的，且失败时留下看似正常的痕迹。**

### 24.6 连带发现：ndarray 序列化（健壮性隐患，非可达缺陷）

```python
obs_lst = [{"time": 0.0, "jq": np.zeros(7), "action": np.ones(7)}]
recoder_single_arm(d, obs_lst)
# TypeError: Object of type ndarray is not JSON serializable
# 文件大小 31 字节（写了一半）
```

**但唯一调用方已做 `.tolist()`**（`universal_task_runtime.py:111-112`）：

```python
"jq"     : self.mj_data.sensordata[...].tolist(),
"action" : self.action[:self.mujoco_ctrl_dim].tolist(),
```

| | 缺键 | ndarray |
|---|---|---|
| 当前可达 | ✅ | ❌ **不可达** |
| 定级 | **真缺陷** | **健壮性隐患** |

> 📌 **可达性分析决定定级** —— 与 §2.3 缺陷 H 从"高"降"低"是同一种分析。
>
> 但也不能一笔勾销：隐患的本质是**契约没写下来**。函数从未声明"只接受 list"，新增调用方漏掉 `.tolist()` 即会炸，**且同样留下半截文件**。

### 24.7 修复方案

| 方案 | 评价 |
|---|---|
| 循环内加 `try/except` | 治标，坏文件仍然留下 |
| **先在内存 build 完 dict，再 `open()`** | ✅ 异常时文件根本不会被创建 |
| **写临时文件 + `os.replace()`** | ✅✅ **原子写**，最稳 |

推荐第三种：

```python
def recoder_single_arm(save_path, obs_lst):
    os.makedirs(save_path, exist_ok=True)

    # 先在内存里构建完整结构 —— 任何 KeyError 都在碰文件系统之前抛出
    save_dict = {"time": [], "obs": {"jq": []}, "act": []}
    for obs in obs_lst:
        save_dict["time"].append(obs['time'])
        save_dict["obs"]["jq"].append(obs['jq'])
        save_dict["act"].append(obs['action'])

    # 原子写：os.replace 在同一文件系统上是原子操作，
    # 要么完全替换，要么完全没发生，不存在"半截文件"的中间状态。
    final = os.path.join(save_path, "obs_action.json")
    tmp = final + ".tmp"
    with open(tmp, "w") as fp:
        json.dump(save_dict, fp)
    os.replace(tmp, final)
```

> **atomic write** 是工业界处理"要么完整、要么不存在"的标准做法。

### 24.8 回归验证

已实施，`tests/unit/test_recorder.py`：

```python
@pytest.mark.xfail(reason="缺陷 Y：...", strict=True)
@pytest.mark.parametrize("missing", ["time", "jq", "action"])
def test_partial_write_leaves_no_corrupt_file(tmp_path, missing):
```

**3 个 xfail(strict)** —— 缺陷修复后自动转 XPASS 报警。

⚠️ 用**装饰器** `@pytest.mark.xfail` 而非命令式 `pytest.xfail()` —— 后者会立即中断测试，下面的断言根本不执行（见 [checkpoint-day06-07.md](checkpoint/checkpoint-day06-07.md) §4.3）。

### 24.9 影响范围

`recorder.py` 覆盖率从 **19% → 94%**，本条缺陷及其守护是该提升的一部分。

实际触发条件：obs 字典缺键。当前 obs 由 `universal_task_runtime.py:108-115` 单点拼装，**短期内不易触发**；但该字典无 schema 校验，新增字段或改名即可能触发。

---

## 廿五、缺陷 Z｜`PyavImageEncoder` 未 close 则整段录像静默丢失

**严重级别**：🟡 Medium ｜ **状态**：⏸ 未修（1 个 xfail 守护）｜【实测】

### 25.1 影响模块

- `discoverse/universal_manipulation/recorder.py:9-74`
- `examples/universal_tasks/universal_task_runtime.py`（无 try/finally 保护）

### 25.2 复现步骤

```python
import os, tempfile, numpy as np
from discoverse.universal_manipulation.recorder import PyavImageEncoder

d = tempfile.mkdtemp()
enc = PyavImageEncoder(64, 48, d, 9)
for i in range(3):
    enc.encode(np.zeros((48, 64, 3), np.uint8), i * 0.1)
print("close 前文件存在:", os.path.exists(enc.av_file_path))   # False
enc.close()
print("close 后大小:", os.path.getsize(enc.av_file_path))       # 1636
```

### 25.3 预期 vs 实际

| | 行为 |
|---|---|
| **预期** | 已编码的帧至少部分落盘，进程崩溃时能抢救一部分 |
| **实际** | **文件完全不存在** —— PyAV 从未把缓冲刷到磁盘 |

### 25.4 根因分析

PyAV 的 `container.mux(packet)` 写入的是内存缓冲。MP4 容器格式要求在文件末尾写 `moov` box（索引），因此 **`container.close()` 之前不会产生可用文件**。

`close()` 做了两件必需的事（`recorder.py:64-69`）：

```python
def close(self):
    if self.container is not None:
        for packet in self.stream.encode():   # flush 编码器内部缓冲
            self.container.mux(packet)
        self.container.close()                # 写 moov box 并落盘
    self.container = None
```

**调用方没有保护**：`universal_task_runtime.py` 中 `encoder.close()` 是普通语句，不在 `finally` 块里。仿真中途抛异常或进程被 kill → **close 永远不执行 → 整段录像消失**。

### 25.5 ⭐ 与缺陷 Y 的对比：两种失败模式

**同一个文件里的两个缺陷，失败方式恰好互补：**

| | 缺陷 Y | 缺陷 Z |
|---|---|---|
| 触发 | obs 缺键 | 未调 `close()` |
| 结果 | 留下 **0 字节**文件 | **文件完全不存在** |
| 下游 `os.path.exists()` | **True → 误判成功** | False → 知道没产出 |
| 危险程度 | ⚠️ **更危险** | 相对安全 |

> 📌 **"什么都没有"比"半截坏东西"安全** —— 前者无法被误认为成功。
>
> 这个对比说明：**失败模式的设计和功能的设计同样重要**。同样是"数据丢了"，一种会污染下游判断，另一种不会。

### 25.6 修复方案

| 方案 | 评价 |
|---|---|
| 调用方加 `try/finally` | 有效，但每个调用点都要记得写 |
| **实现 `__enter__`/`__exit__`** | ✅ 让它能用 `with`，语言层面保证清理 |

推荐后者：

```python
class PyavImageEncoder:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()          # 无论是否异常都执行
        return False          # 不吞异常
```

调用方改为：

```python
with PyavImageEncoder(w, h, save_dir, cam_id) as enc:
    for frame, ts in frames:
        enc.encode(frame, ts)
# 离开 with 块自动 close，异常路径同样保证
```

⚠️ **`__exit__` 返回 `False`** 很重要 —— 返回 `True` 会吞掉异常，把一个崩溃变成静默失败，那就制造了新的同类缺陷。

### 25.7 回归验证

已实施：

```python
@pytest.mark.xfail(reason="缺陷 Z：...", strict=True)
def test_frames_survive_without_explicit_close(tmp_path):
```

同时补齐了 5 条正向测试（编码往返、文件名约定、时间戳单调性、close 幂等、remove_av_file）。

**其中往返验证值得单独说明**：

```python
with av.open(str(out)) as container:
    frames = list(container.decode(video=0))
assert len(frames) == 3
assert (frames[0].width, frames[0].height) == (64, 48)
```

> **一个损坏的 MP4 同样非空。** 只断言"文件存在且大小 > 0"等于没验证。
> 必须**解码回来**才证明编码链路真的走通。

**未 mock `av`** 的理由：其 PyPI wheel 自带完整 ffmpeg（`av.libs` 约 72 MB），实测本机与容器内 `h264`/`libx264` 均可用。mock 掉就只是在测自己写的假对象，编码链路一行没走到。

### 25.8 影响范围

- **数据采集**：仿真崩溃/中断时该 episode 的视频全部丢失
- **难以察觉**：不留任何痕迹，只有事后清点文件数才会发现
- 当前 `universal_task_runtime.py` 是唯一调用方，修 `__exit__` 后需同步改调用点

---

## 廿六、缺陷 G｜`cv2` 依赖的系统库 `libglib2.0-0` 未记录

**严重级别**：🟢 Low ｜ **状态**：✅ 已修（`Dockerfile.test` 已补）｜【实测】

### 26.1 影响模块

- `discoverse/envs/simulator.py:7`（`import cv2`）
- 任何最小化 Linux 环境（slim 容器、CI runner、裸机新装）

### 26.2 复现步骤

在不含 glib 的干净镜像中：

```bash
docker run --rm python:3.10-slim bash -c '
  pip install -q opencv-python && python -c "import cv2"'
# ImportError: libgthread-2.0.so.0: cannot open shared object file
```

### 26.3 预期 vs 实际

| | 行为 |
|---|---|
| **预期** | `pip install opencv-python` 后 `import cv2` 可用 |
| **实际** | `ImportError: libgthread-2.0.so.0` —— **缺系统库，非 Python 包** |

### 26.4 根因分析：依赖有三层，pip 只管中间那层

```
第 3 层  项目代码            ← git 管
第 2 层  Python 包           ← pip 管
第 1 层  系统库（.so）       ← apt 管   ← ⚠️ pip 管不到
第 0 层  内核                ← 宿主机提供
```

```
pip install opencv-python
  └─ 装了 cv2 的 Python 封装 + 一个 .so
        └─ 那个 .so 又动态链接系统的 libgthread-2.0.so.0（glib）
              └─ pip 不管这层，它假设系统上有
```

wheel 会带一部分依赖库（`opencv_python.libs` 占 115 MB），但不会带全 —— glib 这类"任何 Linux 桌面都有"的库被假设存在。**在 slim 镜像里该假设不成立。**

### 26.5 排查要点：失败方式与错误伪装

**其一，它不是启动即崩，而是 7 个用例 ERROR：**

```
106 passed, 4 skipped, 45 deselected, 10 xfailed, 7 errors
```

因为 `cv2` 不在测试文件顶部 import，而是在 fixture 里才被拉进来：

```
test_determinism.py:47 → discoverse/envs/__init__.py:1 → simulator.py:7 → import cv2
```

只影响用到 `discoverse.envs` 的 7 个用例。

> 📌 **这就是"容器内数字必须与本机完全一致"作为验收标准的意义。**
> 只看"跑起来了没报错"，`106 passed` 看着挺正常。**106 + 7 = 113 才是信号。**

**其二，同一次排查中出现过一个伪装成根因的下游症状：**

```
E: Unable to locate package libosmesa6-dev
```

看着像 Debian/Ubuntu 包名差异，实际是上游 `apt-get update` 因代理失败、索引没拉到。绕开代理验证，**三个包名全都存在**。

> 📌 **构建日志要从上往下读。** 那三行 `Failed to fetch` 才是真因。

### 26.6 快速定位手段

```bash
ldd /usr/local/lib/python3.10/site-packages/cv2/cv2*.so | grep "not found"
```

`ldd` 列出一个 `.so` 的全部动态依赖，`not found` 即缺失项。

| 报错长相 | 是什么 | 去哪修 |
|---|---|---|
| `No module named 'X'` | Python 包 | `requirements.txt` / `pyproject.toml` |
| `libXXX.so.N: cannot open shared object file` | **系统库** | `Dockerfile` 的 `apt-get install` |

### 26.7 修复方案

`Dockerfile.test` 已补：

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
        libosmesa6-dev \
        libgl1 \
        libglx-mesa0 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
```

⚠️ **`libosmesa6-dev` 是另一个陷阱**：名字带 `-dev` 看着像编译期依赖，**但 osmesa 软件渲染在运行期就要它**，不能因"瘦身"砍掉。

**尚未做的**：README / 安装文档未记录系统级依赖。裸机新装的用户仍会撞上。

### 26.8 与缺陷 L′ 的关系

**两者是同一个问题的两层**：

| | L′ | **G** |
|---|---|---|
| 缺什么 | Python 包 | **系统库** |
| 谁该声明 | `pyproject.toml` | **Dockerfile / 安装文档** |
| pip 能管吗 | ✅ 能 | ❌ **管不到** |
| 本机为何不炸 | 被 optional 组顺带装了 | Ubuntu 桌面自带 glib |

**共同点：本机环境的"脏"掩盖了声明的缺失，只有干净容器能暴露。**

---

## 廿七、验证与复现

### 27.1 环境

**方式一：本机**

```bash
cd /path/to/DISCOVERSE
source scripts/dev/env.sh      # 设置 MUJOCO_GL=osmesa、PYTHONPATH
```

**方式二：容器（推荐 —— 干净环境，且是 §廿三/§廿六 的复现载体）**

```bash
docker build -f discoverse/docker/Dockerfile.test -t discoverse:test .
docker run --rm discoverse:test pytest tests/ -q
```

⚠️ 两种方式必须跑出**完全相同**的数字。不一致即说明容器与本机环境不等价 —— §廿六 正是这样被发现的（容器 `106 passed`，本机 `113 passed`）。

### 27.2 回归测试

```bash
$PY -m pytest tests/ -q
# 预期：122 passed, 4 skipped, 45 deselected, 15 xfailed
```

`45 deselected` 是 flake 采样实验，由 `-m 'not flake'` 默认排除。**那 15 个 xfail 即本报告中未修复的缺陷**——修好后自动转 XPASS 报警。

### 27.3 复现关键实验

```bash
# 缺陷 #1：确定性（修复后）
$PY -m pytest tests/simulation/test_determinism.py -v

# 缺陷 #2：退出码
sed -i "s/    seed: .*/    seed: 13/" discoverse/configs/tasks/place_block.yaml
$PY examples/universal_tasks/universal_task_runtime.py -r airbot_play -t place_block -1 --headless
echo "退出码 = $?"        # 实测为 0，应为非 0
sed -i "s/    seed: .*/    seed: null/" discoverse/configs/tasks/place_block.yaml   # 务必还原

# 缺陷 #3：超时未生效
printf 'import time\ndef test_s():\n    time.sleep(75)\n' > /tmp/t.py
$PY -m pytest /tmp/t.py -q                    # 实测 passed（应被 60s 杀掉）
$PY -m pytest /tmp/t.py -q --timeout=10       # 实测 Timeout（证明插件正常）

# 缺陷 V：相机不存在
$PY examples/universal_tasks/universal_task_runtime.py -r panda -t cover_cup -1 --headless

# 缺陷 H：qpos_dim 无消费者
grep -rn "qpos_dim" --include=*.py discoverse/ examples/ | grep -v /policies/
grep -rn "target_qpos" --include=*.py . | grep -v /policies/
```

⚠️ 涉及临时修改 `place_block.yaml` 的实验**务必还原**，并 `grep -n "seed:"` 确认回到 `null`。

### 27.4 flake 数据

- `docs/experiments/flake-2026-08-07.csv`（2250 行原始数据）
- `docs/experiments/flake-2026-08-07.meta.yaml`（实验条件 + caveats）
- `docs/report/flakiness-analysis.md`（分析报告）

---

## 廿八、结论

### 28.1 数字

| 指标 | 值 |
|---|---|
| 定位缺陷 | **24** |
| 已修复并回归验证 | **6** |
| 由 xfail 守护的未修缺陷 | **14**（共 18 条未修） |
| 严重度调整（基于实测） | **2**（O 中→低，H 高→低） |
| 被实测推翻的既有记录 | **9**（Day 6-7 三条 + Day 8-9 六条） |
| 测试用例 | 122 passed + 15 xfail |
| 核心模块覆盖率 | 67%（`recorder.py` 94%、`mink_solver.py` 90%） |

> **Day 8-9 新增 4 条（§廿三~§廿六）全部由同一件事暴露**：把测试放进一个干净的 Docker 容器里跑。
> 其中 §廿三 证明 Day 6-7 修的缺陷 L **只修了症状** —— 同一文件、同一机制，还剩 4 个包没查。

### 28.2 最值得带走的三条

**其一，配置驱动系统的头号风险不是配置写错，而是配置写了没人读。**

20 条缺陷中 8 条属此模式（§1.3）。写错通常会报错，没人读则永远沉默。`dict.get(key, default)`、`for x in []`、`all([])` 这三个 Python 语义把"配置缺失"一致地伪装成"一切正常"。

**防御手段**：对每个配置项写一条"它确实被消费了"的测试，而不只是"它能被解析"。

**其二，可复现性是一切定量分析的前提。**

缺陷 #1 修复前，"成功率 75%"这个数字无法解释——不知道是代码问题还是运气。修复后才能做 2250 次运行的分桶分析，才能构造"必然失败"的输入去验证退出码（#2）。

**三条 CI 相关缺陷存在严格依赖**（§1.4）：可复现性 → 退出码契约 → 超时保护，缺一不可。

**其三，排查的本质是提出假设并杀死它们。**

13 条文档推断被实测推翻，3 条是当天自己写的。这不是能力问题，而是这类工作的固有特征。

**因此本报告每条结论都标注核实方式，而核实的方式是跑一遍。** §5.5 明确承认一条尚未定位到根因的问题——**"我不知道"是合法结论，"我猜是 X"写成"根因是 X"不是。**

### 28.3 若继续投入，建议顺序

| 顺序 | 缺陷 | 成本 | 理由 |
|---|---|---|---|
| 1 | V | 1 行 | 解锁 15.8% 的运行，让 flake 数据可信 |
| 2 | #2 + X | 半天 | 建立退出码契约（必须同批，否则契约被破坏） |
| 3 | N(1) | 30 分钟 | `save_dir` 加索引，单独此项即可阻止数据丢失 |
| 4 | M 的一行改名 | 1 行 | "完成状态"→"状态机进度"，消除主要误读 |
| 5 | #3 | 半天 | 恢复超时保护 |
| 6 | B + I | 半天 | 同批修，恢复数据采集 |

**T 与 M 的枚举化不建议做**——成本高、diff 噪音大，收益不成比例。

---

**报告结束** ｜ 基线 `c722ca8` ｜ 相关文档：[flakiness-analysis.md](report/flakiness-analysis.md) · [defect-inventory-day02.md](defect-inventory-day02.md) · [architecture-notes.md](architecture-notes.md)
