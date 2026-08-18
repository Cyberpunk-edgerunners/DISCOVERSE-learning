# Day 13-14 — 结果契约：给整个测试体系定义「一次运行的结论长什么样」

> 上接 [day12-jenkins.md](day12-jenkins.md)
> 本课产出：`discoverse/testing/` 结果契约包 + 19 个回归测试（122 → 141）
> 服务对象：Day 15-17（MMK2 专项）、**Day 18-19（数据质量验证）**
> ⭐ **逐行代码解析见** [day13-14-supplement-line-by-line.md](day13-14-supplement-line-by-line.md)（991 行，查阅型）
> 预计耗时：约 8 小时（两天）

---

## 今天到底在干嘛（先建立直觉）

前 12 天你已经有了一套完整的测试闭环：

```
pytest tests/  →  141 passed  →  5 个 CI job 全绿  →  红了能定位
nightly -m flake  →  45 个组合采样  →  出成功率数据
```

**这套闭环是好的。今天不动它。**

今天要补的是它**没有**的一样东西：

> **一个统一的答案格式 —— 「一次运行的结论」到底长什么样。**

### 先看问题长什么样

你的体系里，「一次运行的结论」目前有**三种**互不相同的表达：

| 出处 | 结论怎么表达 | 谁定义的 |
|---|---|---|
| `pytest` 用例 | `assert` 过 / 不过 | pytest |
| Day 5 `test_task_matrix.py` | 四个桶（`SUCCESS`/`BUCKET1`…） | 你，从 stdout 正则捞 |
| Day 18-19 计划里的数据校验 | `ValidationResult`（`passed` + `metric` + `threshold`） | 计划文档，**还没写** |

三种格式，三套语义，**没有一个能被另外两个消费**。

📌 **今天的任务：定义一份契约，让「结论」在整个项目里只有一种形状。**

### ⭐ 为什么现在做，而不是等到 Day 18-19

因为计划文档 §7.1 已经给 Day 18-19 写好了一个 `ValidationResult` —— **而它带着一个你已经修过的毛病**：

```python
# 计划文档 §7.1 原文（两处 threshold）
threshold=f'{self.min_brightness}-{self.max_brightness}',   # ← str
threshold=self.min_sharpness,                                # ← float
```

同一个字段，一处塞字符串一处塞浮点，**没有任何校验拦得住**。

如果等到 Day 18-19 才想这件事，你会**又造一个半成品**，然后项目里有两套结果类型。

> **今天先把契约立起来，Day 18-19 就是复用它，而不是另起炉灶。**

### 今天的一句话总结（先记住，最后再回来看）

> **把「这次跑得怎么样」，从一段给人看的文字，
> 变成一份给机器读的、不能自相矛盾的、自带排查方向的数据。**

---

## ⚠️ 关于 `examples/` 里那个脚本

`examples/universal_tasks/cicd_testing.py` 是**上游开源代码**（`git log` 显示它来自 `7bacbc9 rearrange`，不是你写的）。

它有个很典型的毛病 —— 靠匹配 stdout 里的 emoji 判断成败：

```python
if "✅ 任务成功检查通过" in output or "🎉" in output and "任务成功完成" in output:
```

**今天不重写它，也不把它当成主线。** 它在今天只扮演一个角色：

> **契约的第一个消费者** —— 用来证明这份契约能装进**别人写的代码**里。

📌 **这个定位很重要。** 真实工作中你面对的代码库，大部分都是别人写的。**「能在不重写别人代码的前提下，给它补一层可测的边界」是比「我从零搭一套」更值钱的能力。**

⚠️ **它没有接进任何流水线**，自己验证：

```bash
grep -rn "cicd_testing\|universal_task_runtime" .github/ Jenkinsfile
# （没有任何引用）
```

所以别把今天说成「修好了 CI」——**你的 CI 一直是好的**，跑的是 `pytest tests/`，该红就红。

---

## ⚠️ 开课前必读：今天会踩的 8 个坑

| # | 坑 | 后果 | 在哪讲 |
|---|---|---|---|
| 1 | **ROS 污染 `PYTHONPATH`** | pytest 报 `No module named 'lark'` | Step 0.2 |
| 2 | **系统 python 没有依赖** | `No module named 'mink'` | Step 0.1 |
| 3 | ⭐ **`FailureMode` 写成 `Enum`** | `json.dump` 抛 `TypeError` | Step 2.2 |
| 4 | **想复用 pytest 的 `LogXML`** | 与 pytest 内部对象强耦合 | Step 5.1 |
| 5 | **先写防御性代码再读接口** | 写出「类型不符时静默返回 None」—— 新的静默失败 | Step 3.3 |
| 6 | ⭐ **把 flake 当成分类器 bug** | 差点去改没坏的代码 | Step 6.2 |
| 7 | ⭐ **容器挂载路径错配**（自造） | 调试了一个 CI 里根本不会发生的问题 | Step 7.2 |
| 8 | **`tests/` 的 lint 是严格模式** | `check=True` 会把今天的成果原地毁掉 | Step 7.3 |

### ⚠️ 计划文档有 3 条要改

| 计划文档 | 实测 | 改成 |
|---|---|---|
| 用 `_pytest.junitxml.LogXML` | 与 pytest 内部 `Item`/`TestReport` 强耦合 | 手写 `ElementTree` |
| 结果文件用 `/tmp/..._{pid}.json` | `subprocess.run` 返回时子进程已结束，拿 pid 的时机不对 | 显式传路径 |
| §7.1 `ValidationResult` 的 `threshold` | 一处 str 一处 float | **今天的契约要防住这类问题** |

---

## Step 0｜环境（20 分钟）

### 0.1 用 conda 环境的 python

```bash
PY=~/miniconda3/envs/discoverse/bin/python
```

系统 python 会报 `ModuleNotFoundError: No module named 'mink'`。

### 0.2 ⚠️ ROS 污染 PYTHONPATH

```bash
echo $PYTHONPATH
# /opt/ros/humble/lib/python3.10/site-packages:...
```

`PYTHONPATH` 优先于环境自己的 site-packages，pytest 收集时会爬进 ROS 目录，报 `No module named 'lark'`。

**今天所有 pytest 命令都带这个前缀**：

```bash
env -u PYTHONPATH $PY -m pytest tests/ -q
```

### 0.3 基线

```bash
env -u PYTHONPATH MUJOCO_GL=osmesa $PY -m pytest tests/ -q | tail -2
# 122 passed, ...        ← 开工前
# 141 passed, ...        ← 收工后（+19）
```

---

## Step 1｜⭐ 先想清楚：一份「结论」需要携带什么（40 分钟）

**别急着写代码。先回答一个问题：**

> 一个人看到红灯之后，需要知道什么才能开始排查？

### 1.1 从三个真实场景倒推

**场景 A**：仿真任务失败了。你需要知道 —— 走到第几步？是没走完，还是走完了没做对？种子是多少（能复现吗）？

**场景 B**（Day 15-17，MMK2）：FK→IK→FK 往返误差超标。你需要知道 —— 误差多大？阈值多少？哪个关节？

**场景 C**（Day 18-19，数据质量）：一张图像不合格。你需要知道 —— 哪个指标？实测值？阈值？

📌 **三个场景，同一个骨架**：

```
成功了吗    → success: bool
为什么失败  → failure_mode: 分类，不是自由文本
走到哪了    → 进度信息
怎么复现    → seed / 环境快照
给人看的细节 → error_message
```

### 1.2 ⭐ 两条设计原则（今天所有决定都从这来）

**原则一：任何需要用正则从自由文本里捞出来的信息，都说明设计出了问题。**

反例就是你 Day 5 写的采样器：

```python
m_state = re.search(r"完成状态: (\d+)/(\d+)", stdout)
```

⚠️ **这在 Day 5 是合理的** —— 采样器不需要断言，能捞到就够了。但如果**要断言**，就不能靠正则：打印文案一改，断言就失效，而且是**静默**失效。

**原则二：分类比布尔值有用。**

`success=False` 只说「红了」。但红灯有很多种：

| 失败模式 | 该查什么 |
|---|---|
| `ik_early` | 运动学、目标位姿是否可达 |
| `final_check` | 任务判据、物理参数 |
| `timeout` | 性能、死循环 |
| `config` | **根本不是被测代码的问题** |
| `crash` | 段错误、内存 |

> **一个好的红灯，应该自带排查方向。**

---

## Step 2｜写契约（60 分钟）

```bash
mkdir -p discoverse/testing
```

### 2.1 退出码：刻意区分 1 和 2

```python
class ExitCode(IntEnum):
    SUCCESS = 0        # 成功
    FAILED = 1         # 失败，判据未满足（这是一个有效的测试结论）
    CONFIG_ERROR = 2   # 配置/环境错误，根本没跑起来
```

| 码 | 性质 |
|---|---|
| 1 | **有效结论** —— 系统正常工作，给出了「不通过」这个正确答案 |
| 2 | **无效结论** —— 系统自己坏了，没有给出答案 |

> **「被测对象坏了」和「测试环境坏了」是两类事件，不能共用一个信号。**

⚠️ **Day 18-19 会直接用到这个区分**：图像亮度不达标 = 1（数据真有问题）；图像文件读不出来 = 2（采集环节坏了）。**混为一谈会让你去调相机参数，而实际是磁盘满了。**

### 📖 补充知识：退出码速查表

| 码 | 含义 |
|---|---|
| 0 | 成功 |
| 1 | 一般性失败 |
| 2 | 命令用法错误（**argparse 默认用它**） |
| 127 | 命令不存在 |
| 128+N | 被信号 N 杀死 |
| **139** | **段错误**（128+11） |

⚠️ 139 是本项目的现实威胁（缺陷 X）：MuJoCo viewer 清理时段错误，能让**一次成功的运行**返回 139。契约必须能识别「非契约退出码」。

### 2.2 ⚠️ 第一个坑：`FailureMode` 不能用 Enum

我一开始两个都写成 `Enum`。落盘时：

```
TypeError: Object of type FailureMode is not JSON serializable
```

改成普通字符串常量类：

```python
class FailureMode:
    NONE = None
    IK_EARLY = "ik_early"
    FINAL_CHECK = "final_check"
    TIMEOUT = "timeout"
    CONFIG = "config"
    CRASH = "crash"

    ALL = (IK_EARLY, FINAL_CHECK, TIMEOUT, CONFIG, CRASH)
```

但 `ExitCode` 用 `IntEnum` 是**对的**，因为它要当 int 用：

```python
sys.exit(ExitCode.FAILED)              # IntEnum 成员就是 int
proc.returncode == ExitCode.SUCCESS    # 直接比较
```

> 📌 **选类型的依据是「它要跨越什么边界」**：
> 跨进程序列化 → 字符串；要当 int 用 → IntEnum。

### 2.3 ⭐⭐ 让非法状态无法表示

**这是今天最该带走的一节。**

```python
def __post_init__(self):
    if self.failure_mode is not None and self.failure_mode not in FailureMode.ALL:
        raise ValueError(f"未知的 failure_mode: {self.failure_mode!r}，允许值: {FailureMode.ALL}")
    if self.success and self.failure_mode is not None:
        raise ValueError(f"矛盾的结果：success=True 但 failure_mode={self.failure_mode!r}")
    if not self.success and self.failure_mode is None:
        raise ValueError("矛盾的结果：success=False 但未指定 failure_mode")
```

**与其在下游到处写 `if` 防御脏数据，不如让脏数据构造不出来。**

| 校验 | 防的是 |
|---|---|
| 第 1 条 | `"tiemout"` 这种拼写错误**悄悄变成一个新的失败类别**，在统计里单独占一行，而你永远不会发现自己少统计了一类超时 |
| 第 2 条 | 自相矛盾的结果流进下游，让报告和统计全部失去意义 |
| 第 3 条 | ⭐ **随手 `return success=False` 了事** |

📌 **第三条最值钱**：它把「说明失败原因」从**可选的好习惯**变成了**强制契约**。

### ⚠️ 回头看计划文档 §7.1 的 `ValidationResult`

```python
@dataclass
class ValidationResult:
    passed: bool
    metric_name: str
    value: float
    threshold: float      # ← 声明是 float
    message: str
```

实际用的时候：

```python
threshold=f'{self.min_brightness}-{self.max_brightness}',   # str！
threshold=self.min_sharpness,                                # float
threshold=f'{limits[0]:.2f} ~ {limits[1]:.2f}',              # str！
```

**没有 `__post_init__`，三处不一致没人拦。**

后果：想按阈值排序、想画阈值趋势图的时候，一半数据是字符串。**而这时候数据已经采完了。**

> 📌 **这就是今天先立契约的理由。** Day 18-19 到时候只需要回答「`ValidationResult` 和 `TaskResult` 是什么关系」，而不是从头设计一遍。

---

## Step 3｜让被测对象产出结果（60 分钟）

契约有了，得有人填。改 `examples/universal_tasks/universal_task_runtime.py`。

⚠️ **这是上游代码，改动原则：只加不改** —— 不动它的业务逻辑，只在关键节点埋点。

### 3.1 在状态机里打上失败模式

三处埋点，对应三种机制：

```python
# ① IK 求解失败 —— 状态机中途卡住
if not self.set_target_from_primitive(state_config):
    self.failure_mode = FailureMode.IK_EARLY
    self.running = False
    return False

# ② 状态全部走完，成败取决于最终判据
else:
    self.success = self.check_task_success()
    if not self.success:
        self.failure_mode = FailureMode.FINAL_CHECK
    self.running = False
    return True

# ③ 仿真时间超预算
elif self.mj_data.time > self.max_time:
    self.failure_mode = FailureMode.TIMEOUT
    self.running = False
    return False
```

📌 **① 和 ② 的区别**：都是失败，但一个是「走不到」，一个是「走到了没做对」。

### 3.2 `build_result()`

```python
def build_result(self) -> TaskResult:
    wall_time = time.time() - self.start_time
    success = bool(self.success)
    return TaskResult(
        robot=self.robot_name,
        task=self.task.task_config.task_name,
        success=success,
        completed_states=self.stm.state_idx,
        total_states=self.total_states,
        sim_time=float(self.mj_data.time),
        wall_time=wall_time,
        exit_code=ExitCode.SUCCESS if success else ExitCode.FAILED,
        failure_mode=None if success else (self.failure_mode or FailureMode.FINAL_CHECK),
        error_message=self.error_message,
        seed=self._current_seed(),
        timestamp=datetime.now().isoformat(),
    )
```

💡 `sim_time` 和 `wall_time` **分开记录**：前者反映任务本身长度，后者反映机器性能。换台机器 `wall_time` 会变，`sim_time` 不该变。

### 3.3 ⚠️ 一次返工：先读接口，再写代码

取 seed 时，我第一版写了一长串防御：

```python
# ❌ 我的第一版
seed=(self.task.task_config.randomization.get("settings", {}) or {}).get("seed")
     if isinstance(getattr(self.task.task_config, "randomization", None), dict) else None,
```

写完才去查 [task_config.py:180](../../discoverse/universal_manipulation/task_config.py) —— `randomization` 本来就是返回 `dict | None` 的 `@property`。

那串代码不但多余，而且**类型不符时会静默返回 None** —— 我在修静默失败的路上，又写了一个静默失败。

改成与 [task_base.py:58](../../discoverse/universal_manipulation/task_base.py) 一致的读法：

```python
def _current_seed(self):
    rand_cfg = self.task.task_config.randomization or {}
    return (rand_cfg.get("settings") or {}).get("seed")
```

> 📌 **防御性代码不是免费的。** 在不了解接口的地方写防御，写出来的往往是新的静默失败。**先花 30 秒读接口。**

### 3.4 三层兜底 + 关键的一行

```python
# 兜底：连 executor 都没构造出来
if result is None:
    result = TaskResult(..., exit_code=ExitCode.CONFIG_ERROR, failure_mode=FailureMode.CONFIG,
                        error_message="任务未产生任何结果（执行器未成功初始化）")

if result_json:
    result.to_json(result_json)
```

```python
if __name__ == "__main__":
    _result = main(...)
    # 把成败送出进程边界。没有这一行，main() 正常返回 -> 解释器默认退出 0
    sys.exit(int(_result.exit_code))
```

📌 **「没有结果」本身也必须是一种结果。** 否则调用方只能靠猜 —— 而猜的方式就是 parse stdout。

### 📖 补充知识：进程边界会吞信息

```
check_success()   逐条判定             ✅ 算对了
    ↓ return
executor.run()    return self.success  ✅ 传上来了
    ↓ return
main()            拿到 success          ✅ 收到了
    ↓ ???
进程退出                                ❌ 没了
```

**Python 的 `main()` 正常返回时，解释器默认以 0 退出。返回值不会自动变成退出码。**

---

## Step 4｜验证：构造「必然失败」和「必然成功」（50 分钟）

### 4.1 ⭐ 这一步依赖 Day 3-4 的成果

要验证「失败时退出码是 1」，得先有一个**必然失败**的输入。

而仿真是随机的 —— 除非**随机化可复现**。

```bash
grep -n "seed" discoverse/configs/tasks/place_block.yaml
# 85:    seed: null      ← 每次随机
```

> 💡 这完全依赖 Day 3-4 修的缺陷 #1（seed 贯穿，commit `cd09b80`）。
> **修之前 seed 写了也不生效。没有可复现性，就构造不出「必然失败的输入」。**

**先备份**：

```bash
cp discoverse/configs/tasks/place_block.yaml /tmp/pb.bak
md5sum discoverse/configs/tasks/place_block.yaml
# 7d225acd3537ae3aef210152119e779d      ← 收工时要核对
```

### 4.2 实测

```bash
# 必然失败
sed -i "s/^    seed: null/    seed: 13/" discoverse/configs/tasks/place_block.yaml
MUJOCO_GL=osmesa $PY examples/universal_tasks/universal_task_runtime.py \
    -r airbot_play -t place_block -1 --headless --result-json /tmp/r13.json
echo "rc=$?"

cp /tmp/pb.bak discoverse/configs/tasks/place_block.yaml

# 必然成功
sed -i "s/^    seed: null/    seed: 42/" discoverse/configs/tasks/place_block.yaml
MUJOCO_GL=osmesa $PY examples/universal_tasks/universal_task_runtime.py \
    -r airbot_play -t place_block -1 --headless --result-json /tmp/r42.json
echo "rc=$?"

cp /tmp/pb.bak discoverse/configs/tasks/place_block.yaml
```

实测：

```
seed=13 → rc=1   {'success': False, 'exit_code': 1, 'failure_mode': 'final_check',
                  'completed_states': 10, 'total_states': 10, 'seed': 13}
seed=42 → rc=0   {'success': True,  'exit_code': 0, 'failure_mode': None, 'seed': 42}
```

✅ **同一份契约，两个方向都对。**

### 4.3 ⭐ 顺带证明「靠 stdout 判定」为什么不能用来断言

把 emoji 匹配那行逻辑抠出来，喂四种输入：

```bash
$PY - <<'EOF'
def judge(output):
    return "✅ 任务成功检查通过" in output or "🎉" in output and "任务成功完成" in output

cases = {
    "A. 真实成功":                  "✅ 任务成功检查通过\n🎉 第 1 轮任务成功完成!",
    "B. 文案改成「任务完成」":        "🎉 第 1 轮任务完成!",
    "C. 日志管道剥离了 emoji":       " 任务成功检查通过\n 第 1 轮任务成功完成!",
    "D. 失败运行，但日志里出现过字样": "⚠️ 未成功\n（历史日志）🎉 第 0 轮任务成功完成!",
}
for name, out in cases.items():
    print(f"{judge(out)!s:>6}  <- {name}")
EOF
```

```
  True  <- A. 真实成功
 False  <- B. 文案改成「任务完成」
 False  <- C. 日志管道剥离了 emoji
  True  <- D. 失败运行，但日志里出现过字样
```

- **B、C = 假阴性**（成功被判失败）
- **D = 假阳性**（失败被判成功）← ⚠️ 致命

顺带，运算符优先级也是错的：

```bash
$PY -c "print((False or True and False) == (False or (True and False)))"
# True    → A or B and C 实际是 A or (B and C)
```

📌 **这不是「上游代码写得差」，而是「用自由文本传结论」这条路本身走不通。**

---

## Step 5｜JUnit XML：让结论能被 CI 消费（40 分钟）

契约是给机器读的，但**人要在 CI 界面上看**。JUnit XML 是 CI 世界的事实标准。

### 5.1 ⚠️ 为什么不复用 pytest 的 `LogXML`

计划文档建议 `from _pytest.junitxml import LogXML`。

实测：它与 pytest 的 `Item` / `TestReport` 对象**强耦合**，得构造一堆假的 pytest 内部对象。**JUnit 的 schema 很小，手写更可控。**

### 5.2 ⭐ `failure` vs `error`：语义不能混

```python
tag = "error" if r.failure_mode == FailureMode.CONFIG else "failure"
```

| 标签 | 语义 | 退出码 |
|---|---|---|
| `<failure>` | 断言失败 —— 跑完了，没通过 | 1 |
| `<error>` | 测试自身出错 —— 没跑起来 | 2 |

CI 面板会**分开计数**，一眼看出「产品坏了」还是「测试环境坏了」。

### 5.3 ⭐ 让报告结构承载诊断信息

```python
case = ET.SubElement(testsuite, "testcase", {
    "classname": f"{suite_name}.{r.robot}",   # ← 机器人
    "name": r.task,                            # ← 任务
})
```

CI 按 `classname` 自动分组，于是：

- **某机器人整栏全红** → 这个机器人的配置/模型有问题
- **某任务在所有机器人下都红** → 这个任务的判据有问题

> **让报告的结构去承载诊断信息**，比在错误文本里写一百字有用。

### 5.4 失败详情必须带复现信息

```python
if r.seed is not None:
    lines.append(f"seed           = {r.seed}   # 复现用")
```

📌 **看到红灯的人第一件事是想复现。seed 不在报告里，红灯就只是个坏消息。**

---

## Step 6｜第一个消费者：把契约装进上游脚本（50 分钟）

⚠️ **重申定位**：这一步的目的**不是**「修好上游脚本」，而是**证明契约能装进别人的代码**。

### 6.1 判定依据换成两条硬信息

```python
result = self._load_result_file(result_file, robot, task)
if result is None:
    result = self._result_from_returncode(proc.returncode, robot, task, proc.stderr)
```

**优先级：结果文件 > 退出码。** stdout 从此**只**用于人工排查：

```python
result.stdout_tail = stdout_tail    # 仅供人看，不参与任何判定
```

### 6.2 ⭐ 交叉校验：两个信息源打架时

```python
# 退出码不在契约内（如 139 段错误）
if proc.returncode not in (ExitCode.SUCCESS, ExitCode.FAILED, ExitCode.CONFIG_ERROR):
    result = TaskResult(..., failure_mode=FailureMode.CRASH,
        error_message=f"子进程异常退出码 {proc.returncode}（139 通常是段错误）")

# 结果文件说成功，退出码说不是
elif result.success and proc.returncode != ExitCode.SUCCESS:
    result.success = False
    result.failure_mode = FailureMode.CRASH
```

📌 **有两个独立信息源时，不一致本身就是信息。**

⚠️ **诚实标注**：今天只加了**检测**，没**修复**缺陷 X。它只在 `MUJOCO_GL=glfw` 出现，CI 全程 headless —— 属「恰好绕开」而非「安全」。

### 6.3 ⚠️ 差点误判：把 flake 当成分类器 bug

批量里 `airbot_play/cover_cup` 报 `ik_early` `0/17`，单跑却是 `final_check` `17/17`。

**第一反应：分类器写错了。** 差点去改 Step 3.1 那三处埋点。

**先采样，再下结论**（6 次）：

```
第1次: ik_early    0/17      第4次: final_check 17/17
第2次: ik_early    9/17      第5次: ik_early    0/17
第3次: final_check 17/17     第6次: final_check 17/17
```

分类器没错 —— `cover_cup.yaml:115` 的 `seed: null`，**任务本身 flaky**，两种机制各占一半。

> ⚠️ **在 flaky 的被测对象上，单次运行不构成证据。**

📌 **意外收获**：`failure_mode` 把 flake 的**结构**照出来了。`cover_cup` 不只是「有时失败」，而是「**以两种不同机制失败**」—— 有时物体随机到 IK 够不着的位置，有时够得着但没放准。

> 这正是「分类比布尔值有用」最好的例证：**它把「flake」这个模糊概念变成了可分解的现象。**

---

## Step 7｜验证方法论（60 分钟）

今天有三个坑都属于「验证方式本身有问题」。

### 7.1 ⭐ 别用自己的解析器验证自己的输出

我写 XML，我用 `ElementTree` 解析，我说它对 —— **这构不成证据。万一我对 JUnit 格式的理解本身就是错的？**

```bash
env -u PYTHONPATH $PY -m pip install junitparser -q
env -u PYTHONPATH $PY - <<'EOF'
from junitparser import JUnitXml
xml = JUnitXml.fromfile("/tmp/junit.xml")
print(f"tests={xml.tests} failures={xml.failures} errors={xml.errors}")
EOF
# tests=4 failures=1 errors=1        ← 与自己解析的结论一致
```

✅ **两个独立实现结论一致，才算验证。**

### 7.2 ⭐⭐ 我自己造出来的坑

宿主机 141 passed。挂载进容器：

```bash
docker run --rm -v "$PWD":/work -w /work discoverse:test pytest tests/integration/... -q
# ModuleNotFoundError: No module named 'discoverse.testing'
```

**但容器里手动 import 是成功的。**

#### 我走的弯路

我去翻 editable install 的 finder，发现 `NAMESPACES` 里有一份**构建时冻结的子包清单**，不含 `discoverse.testing`。

📌 **看起来完全说得通。** 我差点把这个结论写进教程。

#### 真正的原因

```python
MAPPING = {'discoverse': '/workspace/discoverse'}
```

镜像里代码烤在 `/workspace`，我挂到了 `/work`。**我制造了「两份代码」。**

#### 而且 CI 根本不挂载

```bash
grep -n "docker run" .github/workflows/ci.yml
# run: docker run --rm discoverse:test pytest tests/ -q     ← 没有 -v
```

CI 是**重建镜像**（`COPY . /workspace/`）。按 CI 的方式重来：

```bash
docker build -q -f discoverse/docker/Dockerfile.test -t discoverse:test-day13 .
docker run --rm discoverse:test-day13 pytest tests/ -q | tail -2
# 141 passed
```

> ⚠️ **两条教训**：
> 1. **别停在第一个「看起来合理」的解释上。** finder 冻结清单确实存在、确实说得通 —— 但**不是原因**。
> 2. **验证环境必须与 CI 一致。** 我花时间调试了一个 **CI 里根本不会发生的问题**。

### 7.3 ⚠️ lint 严格模式：`check=False` 必须写

```bash
env -u PYTHONPATH $PY -m ruff check tests/
# PLW1510 subprocess-run-without-check  ×2
```

⚠️ **必须是 `check=False`**：

```python
# check=False：非零退出码正是本文件要断言的对象，不能让它抛异常
return subprocess.run(cmd, ..., check=False, ...)
```

📌 **顺手写成 `check=True`，今天的成果会被 lint 规则原地毁掉** —— 非零退出码变成异常，就永远测不到退出码本身。

---

## Step 8｜写回归测试（70 分钟）

**没有回归测试的契约，只是一份君子协定。**

### 8.1 契约单测（8 个）

```python
def test_failure_requires_a_mode(self):
    """失败必须说明失败模式，否则红灯不带任何排查方向。"""
    with pytest.raises(ValueError, match="未指定 failure_mode"):
        TaskResult(robot="a", task="b", success=False)

def test_unknown_failure_mode_rejected(self):
    """拼错的失败模式必须当场报错，而不是混进统计里变成新类别。"""
    with pytest.raises(ValueError, match="未知的 failure_mode"):
        TaskResult(robot="a", task="b", success=False, failure_mode="tiemout")

def test_roundtrip_through_json(self, tmp_path):
    """跨进程边界后信息不能丢 —— 这正是契约存在的理由。"""
    assert TaskResult.from_json(str(path)).to_dict() == original.to_dict()
```

### 8.2 JUnit 单测（6 个）

```python
def test_config_error_renders_as_error_not_failure(tmp_path, mixed_results):
    assert [c.tag for c in panda] == ["error"]
    assert [c.tag for c in airbot] == ["failure"]

def test_empty_results_still_valid_xml(tmp_path):
    """空结果不能产出损坏的 XML —— 否则 CI 报告步骤会以解析错误告终。"""
```

### 8.3 ⭐ 集成测试（5 个）：fixture 必须逐字节还原

测试要改配置文件，**绝不能污染工作区**：

```python
@pytest.fixture
def task_seed(request):
    with open(TASK_YAML, encoding="utf-8") as f:
        original = f.read()              # ← 存原始文本
    ...
    try:
        yield seed
    finally:
        with open(TASK_YAML, "w", encoding="utf-8") as f:
            f.write(original)            # ← 逐字节还原，不是再 dump 一次
```

📌 **`finally` 里写的是 `original` 原文**。`yaml.safe_dump` 会重排格式、丢注释 —— 那样 `git diff` 会花掉。

```python
@pytest.mark.parametrize("task_seed,expected_rc",
                         [(SEED_PASS, 0), (SEED_FAIL, 1)], indirect=["task_seed"])
def test_exit_code_reflects_task_outcome(task_seed, expected_rc):
    proc = run_task()
    assert proc.returncode == expected_rc, (
        f"seed={task_seed} 期望 {expected_rc}，实际 {proc.returncode}\n"
        f"stdout 尾部:\n" + "\n".join(proc.stdout.splitlines()[-15:])
    )
```

💡 **断言消息里带 stdout 尾部** —— 这测试跑在 CI 上，红了的时候你看不到现场。

### 8.4 ⭐⭐ 缺陷之间有依赖顺序

```
缺陷 #1 修复（seed 贯穿，cd09b80）
    ↓ 使仿真可复现
可以构造「必然失败的 seed=13」和「必然成功的 seed=42」
    ↓ 使断言成为可能
可以写 test_exit_code_reflects_task_outcome
```

> 📌 **修 bug 的顺序不是随意的。有些缺陷是另一些缺陷的前置条件。**
> **「可复现性」尤其常常是其他一切验证工作的地基。**

---

## Step 9｜收工验收（20 分钟）

```bash
env -u PYTHONPATH MUJOCO_GL=osmesa $PY -m pytest tests/ -q | tail -2
# 141 passed, 4 skipped, 45 deselected, 15 xfailed

git diff --stat discoverse/configs/          # （空）
md5sum discoverse/configs/tasks/place_block.yaml
# 7d225acd3537ae3aef210152119e779d           ← 与 Step 4.1 一致

env -u PYTHONPATH $PY -m ruff check tests/   # All checks passed!

docker build -q -f discoverse/docker/Dockerfile.test -t discoverse:test-day13 .
docker run --rm discoverse:test-day13 pytest tests/ -q | tail -2   # 141 passed
```

**122 → 141（+19）** = 8（契约）+ 6（JUnit）+ 5（退出码集成）

---

## ⭐ Step 10｜这份契约给后面留了什么（30 分钟，别跳过）

**今天的价值不在今天。** 契约是给后面两周用的。

### 10.1 Day 15-17（MMK2 双臂轮式）

MMK2 专项要验的东西 —— FK→IK→FK 往返一致性、差速底盘里程计、19 自由度控制接口 —— **每一项都要回答「这次跑得怎么样」**。

复用方式：

```python
TaskResult(
    robot="mmk2", task="fk_ik_roundtrip",
    success=err < tol,
    failure_mode=None if err < tol else FailureMode.FINAL_CHECK,
    error_message=f"往返误差 {err:.4f} rad 超过阈值 {tol}",
    seed=seed,
)
```

⚠️ **可能要扩充 `FailureMode`** —— 比如加一个 `numerical`（求解器不收敛 vs 收敛到错误解）。**扩充时记得同步 `ALL`**，否则 `__post_init__` 会当场拦下（这正是它该做的）。

### 10.2 ⭐ Day 18-19（数据质量验证）

计划文档 §7.1 打算新造一个 `ValidationResult`。**今天之后，该问的问题变成：它和 `TaskResult` 是什么关系？**

两者的骨架高度重合：

| `TaskResult` | `ValidationResult` | 是否同一概念 |
|---|---|---|
| `success` | `passed` | ✅ 同一个 |
| `failure_mode` | （无） | ⚠️ **计划文档缺这个** |
| `error_message` | `message` | ✅ 同一个 |
| （无） | `metric_name` / `value` / `threshold` | 数据校验特有 |

**建议的做法**（Day 18-19 再定，今天只留结论）：

```python
# ValidationResult 保留自己的度量字段，但复用契约的三条不变式
@dataclass
class ValidationResult:
    passed: bool
    metric_name: str
    value: float
    threshold: float          # ⚠️ 必须是数值，不能塞 "30-220" 这种字符串
    message: str

    def __post_init__(self):
        if not isinstance(self.threshold, (int, float)):
            raise TypeError(f"threshold 必须是数值，收到 {type(self.threshold).__name__}")
```

📌 **区间阈值该拆成两个字段**（`threshold_min` / `threshold_max`），而不是塞成 `"30-220"` 字符串。
理由和今天第一条校验一样：**塞成字符串的那一刻，下游就再也没法对它做数值运算了** —— 排序、画趋势图、算超标幅度，全废。

⚠️ **而且这个错误发现得会很晚**：数据采完了、报告出了，等你想画「亮度阈值随版本的变化」时才发现一半是字符串。

### 10.3 一句话交接

> **今天立的不是一个类，是一个约定：
> 这个项目里，凡是「一次检查的结论」，都必须能被机器读、不能自相矛盾、且自带排查方向。**

---

## 今天的验收标准

- [ ] 能说清**为什么需要统一的结果格式**（三种表达并存的问题）
- [ ] `discoverse/testing/` 建好，`__post_init__` 三条校验各有对应单测
- [ ] 能解释 `ExitCode` 用 IntEnum 而 `FailureMode` 用字符串的**理由**
- [ ] seed 13→rc=1、seed 42→rc=0 实测通过
- [ ] 能动手证明「靠 stdout 判定」的两个错误方向
- [ ] JUnit XML 用 **junitparser 独立复核**过
- [ ] 141 passed，`git diff discoverse/configs/` 为空，md5 一致
- [ ] `ruff check tests/` 全绿，且 `subprocess.run` 是 `check=False`
- [ ] 容器内**重建镜像**（不挂载）跑出同样的 141
- [ ] ⭐ **能说清这份契约将怎么服务 Day 15-17 和 Day 18-19**
- [ ] ⭐ **能说清今天没做什么**：没修缺陷 X、没治 `cover_cup` 的 flake、没重写上游脚本

---

## 今天真正学到的

### 1. ⭐「结论」需要一个格式，而不是一段文字

**判断标准**：任何需要用正则从自由文本里捞出来的信息，都说明设计出了问题。

⚠️ 但要分场景：Day 5 的采样器用正则是**合理的**（它不断言，只采样）。**一旦要断言，就不能靠正则。**

### 2. ⭐ 让非法状态无法表示

`__post_init__` 三条校验，胜过下游一百个 `if`。

其中「失败必须指定 `failure_mode`」把**可选的好习惯**变成了**强制契约**。

### 3. 分类比布尔值有用

`success=False` 只说「红了」；`failure_mode` 说「往哪查」。

**副产品**：它把 flake 的**结构**照了出来。

### 4. 选类型看它要跨越什么边界

跨进程序列化 → 字符串；要当 int 用 → IntEnum。

### 5. 进程边界会吞信息

函数返回值不会自动变成退出码。**必须显式 `sys.exit()`。**

### 6. 区分「产品坏了」与「测试环境坏了」

退出码 1 vs 2；JUnit `<failure>` vs `<error>`。**Day 18-19 会原样用到这个区分。**

### 7. ⭐ 验证方法论（今天踩了三次）

| 教训 | 我踩的坑 |
|---|---|
| 别用自己的解析器验证自己的输出 | 用 junitparser 独立复核才算数 |
| 看到不一致，先采样再改代码 | 差点把 flake 当成分类器 bug |
| 别停在第一个「看起来合理」的解释上 | finder 冻结清单「完全说得通」，但不是原因 |
| 验证环境必须与 CI 一致 | 调试了一个 CI 里不存在的问题 |

📌 **后两条是我自己造出来的。** 一天里相当一部分时间花在**排查一个并不存在于真实系统中的故障**上。

### 8. ⭐ 缺陷有依赖顺序

没有 Day 3-4 的 seed 修复，就写不出今天的退出码回归测试。

> **「可复现性」是其他一切验证工作的地基。**

### 9. 防御性代码不是免费的

在不了解接口的地方写防御，写出来的往往是**新的静默失败**。

---

> **面试可用点**：被问「你在这个项目里做的测试工作，最能体现设计能力的是哪一块」时 ——
>
> 答：*「我给整个测试体系定义了一份结果契约。」*
>
> *「起因是我发现同一个项目里，『一次运行的结论』有三种互不相同的表达：pytest 的 assert、我自己写的 flake 采样器的四个分桶（从 stdout 正则捞的）、还有计划里要做的数据质量校验的 ValidationResult。三种格式，没有一个能被另外两个消费。」*
>
> *「所以我先定契约再写实现：`TaskResult` 是个 dataclass，`__post_init__` 里有三条不变式 —— 未知失败模式当场炸、成功不能带失败模式、**失败必须指定失败模式**。第三条最值钱，它把『说明失败原因』从可选的好习惯变成了强制约束，堵死了随手 return False 了事的写法。」*
>
> *「类型选择上有个细节：`ExitCode` 用 IntEnum 因为要 `sys.exit()` 和跟 returncode 比较，而 `FailureMode` 必须用字符串常量 —— 我一开始写成 Enum，`json.dump` 直接抛 TypeError。**选类型的依据是它要跨越什么边界。**」*
>
> *「验证契约的时候我需要一个『必然失败』的输入，这依赖我前几天修的另一个缺陷 —— 随机种子没贯穿。**修 bug 是有依赖顺序的，可复现性是其他一切验证工作的地基。**」*
>
> *「第一个消费者是项目里一个上游的批量测试脚本。**我没有重写它** —— 那是开源代码，不是我的职责范围。我只是在它的进程边界上补了一层契约：退出码加一份 JSON 结果文件。这样它第一次能被程序化消费了，而它的业务逻辑我一行没动。」*
>
> *「契约的真正价值在后面：接下来的双臂机器人运动学验证和数据质量校验都会复用它。我还发现原计划里的 `ValidationResult` 有个坑 —— threshold 字段声明是 float，但实际有三处塞的是 `'30-220'` 这种字符串。**没有校验拦得住，而等你想按阈值画趋势图的时候，数据已经采完了。**」*
>
> 📌 **这段的重心**：讲的是「我发现了什么结构性问题、怎么定的约定、约定怎么服务后面」，不是「我写了什么类」。

---

## 下一步

- **Day 15-17**：MMK2 双臂轮式专项 —— FK→IK→FK 往返一致性、差速底盘里程计、19 自由度控制接口。**产出的结论用今天的契约表达**（可能要扩 `FailureMode`）。

- **Day 18-19**：数据质量验证 —— ⚠️ **动手前先回到 Step 10.2**，决定 `ValidationResult` 与 `TaskResult` 的关系，别又造一个半成品。

- **今天新增的欠账**：
  - [ ] **缺陷 X（段错误 → 139）未修**，只加了**检测**。只在 `MUJOCO_GL=glfw` 出现，CI 全程 headless —— 属「恰好绕开」非「安全」
  - [ ] **`cover_cup` flake 未修**（已量化：6 次采样，两种模式各半；根因之一是 `cover_cup.yaml:115` 的 `seed: null`）
  - [ ] **`panda/cover_cup` 缺相机** —— 实测 `ValueError: The camera "eye_arm" does not exist.`，归类 `config`。**新线索**
  - [ ] ⚠️ **判据本身的两个疑点**（今天发现，未核实）：
        `_check_distance_2d_condition` **忽略 Z 轴** —— 物体掉在目标外的桌面上，水平距离够近也算成功；
        `_evaluate_condition` 的 `except` 把判据异常**吞成 False** —— 配置错误伪装成任务失败

- **老欠账**（未动）：
  - [ ] `task_base.py` 28% —— 仍是最大覆盖率盲区
  - [ ] 测试往 `models/mjcf/tmp/` 写文件，导致 `:ro` 挂载不可用

⚠️ **收工必须是 `141 passed`**，且 `git diff discoverse/configs/` 为空。
📌 **如果 configs 有 diff，第一嫌疑是 Step 4 手动改 seed 之后忘了 `cp /tmp/pb.bak` 还原。**
