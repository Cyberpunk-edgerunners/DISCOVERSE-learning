# Day 13-14 补充 — 逐行解析：结果契约的每一行代码

> 配套 [day13-14-result-contract.md](day13-14-result-contract.md)
> 用途：**查阅型文档**，不用从头读。看不懂哪一行就跳到哪一节。
> 覆盖：`discoverse/testing/` 全部 245 行 + runtime 的 5 处埋点 + 19 个测试

---

## 目录

- [第一部分：Python 语法基础（6 个概念）](#第一部分python-语法基础6-个概念)
- [第二部分：`result_schema.py` 逐行](#第二部分result_schemapy-逐行136-行)
- [第三部分：`junit_report.py` 逐行](#第三部分junit_reportpy-逐行96-行)
- [第四部分：`__init__.py` 逐行](#第四部分__init__py-逐行13-行)
- [第五部分：runtime 的 5 处埋点逐行](#第五部分runtime-的-5-处埋点逐行)
- [第六部分：19 个测试逐个](#第六部分19-个测试逐个)
- [第七部分：ruff 报的 12 个问题](#第七部分ruff-报的-12-个问题)

---

# 第一部分：Python 语法基础（6 个概念）

看契约代码前先建立六个概念，否则每行都像天书。

## 1.1 `@dataclass` 是什么

```python
@dataclass
class TaskResult:
    robot: str
    task: str
```

这一个装饰器，等价于你手写下面这一堆：

```python
class TaskResult:
    def __init__(self, robot, task):      # ← 自动生成
        self.robot = robot
        self.task = task
    def __repr__(self):                    # ← 自动生成
        return f"TaskResult(robot={self.robot!r}, task={self.task!r})"
    def __eq__(self, other):               # ← 自动生成
        return (self.robot, self.task) == (other.robot, other.task)
```

📌 **`dataclass` 的本质**：你只声明「有哪些字段」，它把样板代码补全。

⚠️ **有默认值的字段必须排在没默认值的后面** —— 和函数参数规则一样：

```python
robot: str              # ✅ 无默认值，排前面
completed_states: int = 0   # ✅ 有默认值，排后面
# 反过来写会 TypeError
```

## 1.2 ⭐ `__post_init__` 什么时候被调用

**这是今天最关键的语法点。**

```python
@dataclass
class TaskResult:
    robot: str
    def __post_init__(self):
        print("我被调用了")
```

调用时序：

```
TaskResult(robot="panda")
    ↓
dataclass 生成的 __init__ 执行     ← 把 robot 赋值给 self.robot
    ↓
__post_init__() 自动执行          ← 在这里做校验
    ↓
对象构造完成，返回给调用方
```

📌 **关键**：`__post_init__` 里 `raise`，对象就**根本构造不出来**。

```python
TaskResult(robot="a", task="b", success=False)
# ValueError: 矛盾的结果：success=False 但未指定 failure_mode
#             ↑ 不是「构造了一个坏对象」，是「压根没构造出来」
```

⚠️ **对比一下没有校验会怎样**：

```python
r = TaskResult(robot="a", task="b", success=False)   # 假设没校验
# 对象存在了，failure_mode=None
# → 下游 JUnit 渲染：tag = "error" if r.failure_mode == CONFIG else "failure"
# → None != CONFIG，渲染成 <failure>，type="None"
# → CI 面板上出现一个 type 是字符串 "None" 的失败
# → 没人知道这次为什么失败
```

**这就是「让非法状态无法表示」要防的东西。**

## 1.3 `IntEnum` vs `Enum` vs 普通类

```python
from enum import Enum, IntEnum

class A(Enum):    X = 0
class B(IntEnum): X = 0
class C:          X = 0        # 普通类
```

| 操作 | `Enum` | `IntEnum` | 普通类 |
|---|---|---|---|
| `A.X == 0` | ❌ False | ✅ True | ✅ True |
| `sys.exit(A.X)` | ❌ 报错 | ✅ 可以 | ✅ 可以 |
| `json.dump(A.X)` | ❌ TypeError | ✅ 可以 | ✅ 可以 |
| 拼错时 `A.XX` | ✅ **AttributeError** | ✅ AttributeError | ✅ AttributeError |
| 值的类型安全 | ✅ 强 | ⚠️ 就是 int | ❌ 无 |

📌 **本项目的选择**：

```python
class ExitCode(IntEnum):   # ← 要当 int 用（sys.exit、比 returncode）
class FailureMode:         # ← 要 JSON 序列化，且值就是字符串
```

⚠️ **为什么 `FailureMode` 不用 `Enum`** —— 实测踩过：

```python
class FailureMode(Enum):
    IK_EARLY = "ik_early"

json.dump({"failure_mode": FailureMode.IK_EARLY}, f)
# TypeError: Object of type FailureMode is not JSON serializable
```

**契约要跨进程，先考虑可序列化。**

## 1.4 `Optional[str]` 是什么意思

```python
from typing import Optional
failure_mode: Optional[str] = None
```

`Optional[str]` ≡ `Union[str, None]` ≡ 「**要么是 str，要么是 None**」。

⚠️ **它只是给人和类型检查器看的注解，Python 运行时不强制**：

```python
failure_mode: Optional[str] = 123     # 运行时完全不报错！
```

📌 **所以才需要 `__post_init__` 手动校验** —— 注解不是校验。

> 这正是计划文档 §7.1 `ValidationResult` 的坑：`threshold: float` 只是注解，
> 实际塞 `'30-220'` 字符串进去，**没有任何东西会拦住**。

## 1.5 `from __future__ import annotations`

```python
from __future__ import annotations       # 必须是文件第一行代码
```

作用：**让所有类型注解变成「延迟求值」**（存成字符串，不立即解析）。

好处是可以在类内部引用类自己：

```python
@classmethod
def from_json(cls, path: str) -> TaskResult:    # ← 有这行 import 才不报错
```

没有它就得写成字符串 `-> "TaskResult"`。

## 1.6 `@classmethod` vs `@property`

```python
@property
def name(self) -> str:              # 访问：r.name       （不带括号）
    return f"{self.robot}::{self.task}"

@classmethod
def from_json(cls, path: str):      # 调用：TaskResult.from_json(p)
    return cls(**json.load(f))      # cls 就是 TaskResult 这个类本身
```

| | 第一个参数 | 怎么调 | 用途 |
|---|---|---|---|
| 普通方法 | `self`（实例） | `r.to_dict()` | 操作已有对象 |
| `@property` | `self` | `r.name` **无括号** | 伪装成属性的计算 |
| `@classmethod` | `cls`（类） | `TaskResult.from_json(...)` | **另一种构造方式** |

📌 `cls(**json.load(f))` 里的 `**` 是**字典解包**：

```python
d = {"robot": "panda", "task": "cover_cup", "success": True}
cls(**d)          # ≡ cls(robot="panda", task="cover_cup", success=True)
```

---

# 第二部分：`result_schema.py` 逐行（136 行）

## 2.1 模块 docstring（1-17 行）

```python
"""单次任务运行的结构化结果契约。

背景（Day 13-14）
----------------
重构前，`cicd_testing.py` 通过匹配子进程 stdout 里的 emoji 判断成败：
...
"""
```

**为什么值得写这么长**：三个月后你看到这个文件，会问「为什么不直接返回 bool」。docstring 就是回答这个问题的地方。

📌 **注释写「为什么」，代码本身表达「是什么」。**

## 2.2 imports（19-25 行）

```python
19: from __future__ import annotations    # 延迟注解求值（见 §1.5）
21: import json                            # to_json / from_json
22: import os                              # os.makedirs 建目录
23: from dataclasses import dataclass, asdict, field
24: from enum import IntEnum
25: from typing import Any, Dict, Optional
```

⚠️ **第 23 行的 `field` 从未被使用** —— 见[第七部分](#第七部分ruff-报的-12-个问题)。

## 2.3 `ExitCode`（28-41 行）

```python
28: class ExitCode(IntEnum):
39:     SUCCESS = 0        # 任务成功，判据全部满足
40:     FAILED = 1         # 任务失败，判据未满足（这是一个有效的测试结论）
41:     CONFIG_ERROR = 2   # 配置 / 环境错误，任务未能真正执行
```

**逐个说：**

| 行 | 值 | 为什么是这个数 |
|---|---|---|
| 39 | `0` | POSIX 约定：0 = 成功。**不能改** |
| 40 | `1` | POSIX 约定：1 = 一般性失败 |
| 41 | `2` | ⭐ **argparse 用的就是 2** —— 参数错误时 argparse 自己 `sys.exit(2)`。选它是为了和现有行为一致 |

⚠️ **41 行这个选择有个副作用**：`universal_task_runtime.py -r fake_robot` 会被 argparse 直接拒绝并退出 2，
**恰好**和我们的 `CONFIG_ERROR` 语义一致。这不是巧合，是刻意对齐的。

## 2.4 `FailureMode`（44-61 行）

```python
44: # 说明：FailureMode 用普通字符串常量而非 Enum，是为了让 asdict() 直接产出
45: # 可 JSON 序列化的值，避免调用方再做一次转换。
46: class FailureMode:
54:     NONE = None                 # 未失败
55:     IK_EARLY = "ik_early"       # 状态机中途 IK 求解失败，未走完全部状态
56:     FINAL_CHECK = "final_check" # 状态全部走完，但最终成功判据未满足
57:     TIMEOUT = "timeout"         # 超过墙钟超时，被强制终止
58:     CONFIG = "config"           # 配置/环境错误（如机器人名不在白名单）
59:     CRASH = "crash"             # 子进程异常退出（段错误等非契约退出码）
61:     ALL = (IK_EARLY, FINAL_CHECK, TIMEOUT, CONFIG, CRASH)
```

**54 行 `NONE = None` 为什么要单独定义？**

写 `failure_mode=FailureMode.NONE` 比写 `failure_mode=None` **表意更清楚** —— 前者说「这是一个明确的『无失败模式』状态」，后者只是「空」。

⚠️ **注意 61 行的 `ALL` 不含 `NONE`**：

```python
ALL = (IK_EARLY, FINAL_CHECK, TIMEOUT, CONFIG, CRASH)   # 5 个，没有 NONE
```

因为 `ALL` 是**校验白名单**，而 `None` 在校验里是单独处理的（第 95 行先判 `is not None`）。
把 `None` 放进 `ALL` 会让「成功但带失败模式」这种非法状态漏过去。

**为什么值是小写下划线字符串？**

因为它们会出现在 JSON 里、JUnit XML 的 `type` 属性里、命令行输出里。**小写下划线是这些场合的通用约定。**

## 2.5 `TaskResult` 字段（64-92 行）

```python
64: @dataclass
65: class TaskResult:
72:     robot: str                          # ← 无默认值，必填
73:     task: str                           # ← 无默认值，必填
74:     success: bool                       # ← 无默认值，必填
77:     completed_states: int = 0
78:     total_states: int = 0
82:     sim_time: float = 0.0
83:     wall_time: float = 0.0
85:     exit_code: int = ExitCode.FAILED
86:     error_message: Optional[str] = None
87:     failure_mode: Optional[str] = FailureMode.NONE
90:     seed: Optional[int] = None
91:     timestamp: str = ""
92:     stdout_tail: str = ""
```

**逐字段：**

| 行 | 字段 | 设计考量 |
|---|---|---|
| 72-74 | `robot`/`task`/`success` | **故意不给默认值** —— 三者缺一不可，忘了传就 TypeError |
| 77-78 | `completed_states`/`total_states` | 失败时看「走到哪一步」。`0/10` 和 `9/10` 排查方向完全不同 |
| 82-83 | `sim_time`/`wall_time` | ⭐ **分开记**。换台机器 `wall_time` 会变，`sim_time` 不该变。混用会让性能回归和物理回归分不清 |
| 85 | `exit_code` | ⭐ **默认 `FAILED` 不是 `SUCCESS`** —— 悲观默认。忘了设不会假装成功 |
| 86 | `error_message` | 给人看的细节 |
| 87 | `failure_mode` | 分类 |
| 90 | `seed` | ⭐ 复现用。没它红灯只是坏消息 |
| 91 | `timestamp` | `datetime.now().isoformat()`，排查时对时间线 |
| 92 | `stdout_tail` | ⚠️ **注释明确写「不参与任何判定」** —— 防止后人又拿它去 parse |

📌 **85 行的悲观默认是个通用技巧**：**默认值应该是「最安全的那个」，不是「最常见的那个」。**

## 2.6 ⭐⭐ `__post_init__` 三条不变式（94-107 行）

**今天最核心的 14 行。**

```python
94: def __post_init__(self):
95:     if self.failure_mode is not None and self.failure_mode not in FailureMode.ALL:
96:         raise ValueError(
97:             f"未知的 failure_mode: {self.failure_mode!r}，"
98:             f"允许值: {FailureMode.ALL}"
99:         )
100:    if self.success and self.failure_mode is not None:
101:        raise ValueError(
102:            f"矛盾的结果：success=True 但 failure_mode={self.failure_mode!r}"
103:        )
104:    if not self.success and self.failure_mode is None:
105:        raise ValueError(
106:            "矛盾的结果：success=False 但未指定 failure_mode"
107:        )
```

### 第 95 行拆开看

```python
if self.failure_mode is not None and self.failure_mode not in FailureMode.ALL:
   └────── 前半：不是 None ──────┘   └───── 后半：不在白名单 ─────┘
```

⚠️ **为什么前半必须先判 `is not None`？**

如果直接写 `if self.failure_mode not in FailureMode.ALL:`，那么成功的结果（`failure_mode=None`）会被误拦 —— 因为 `None not in ALL` 是 True。

**这两个条件的顺序不能换**，而且 `and` 的短路特性保证了：`is not None` 为假时，后半根本不求值。

### 第 97 行的 `!r` 是什么

```python
f"未知的 failure_mode: {self.failure_mode!r}"
                                        └┬┘
                            调用 repr() 而不是 str()
```

| 写法 | `failure_mode = "tiemout"` 时输出 |
|---|---|
| `{x}` | `未知的 failure_mode: tiemout` |
| `{x!r}` | `未知的 failure_mode: 'tiemout'` ← **带引号** |

📌 **带引号能看出「是不是字符串」「有没有多余空格」**。排查时这很重要 —— `'tiemout '`（尾部空格）和 `'tiemout'` 用 `{x}` 打印出来一模一样。

### 三条各自防什么

| 行 | 防的是 | 不防会怎样 |
|---|---|---|
| 95-99 | 拼写错误 | `"tiemout"` **悄悄变成一个新的失败类别**，在统计里单独占一行，你永远不知道自己少统计了一类超时 |
| 100-103 | 自相矛盾 | 成功却带失败模式，下游 JUnit 渲染和成功率统计全部失去意义 |
| 104-107 | ⭐ **偷懒** | 随手 `return success=False` 了事，红灯不带任何排查方向 |

📌 **第三条最值钱**：它把「说明失败原因」从**可选的好习惯**变成了**强制契约**。

## 2.7 `name` property（109-112 行）

```python
109: @property
110: def name(self) -> str:
111:     """用于 JUnit XML 的用例名。"""
112:     return f"{self.robot}::{self.task}"
```

`::` 是 **pytest 的用例路径分隔符**（`文件::类::方法`）。用同样的分隔符，让人一眼认出这是个「用例标识」。

⚠️ **实际上 `junit_report.py` 没有用这个 property** —— 它用的是 `classname`/`name` 分开的形式（见 §3.4）。
所以这是个**目前没有调用方的方法**。留着不算错，但值得知道。

## 2.8 序列化三件套（114-126 行）

```python
114: def to_dict(self) -> Dict[str, Any]:
115:     return asdict(self)
```

`asdict()` 是 dataclasses 提供的，**递归**把 dataclass 转成 dict。

⚠️ 因为 `FailureMode` 的值本来就是字符串，`asdict` 出来直接可 JSON 序列化 —— **这正是不用 Enum 的回报**。

```python
117: def to_json(self, path: str) -> None:
119:     os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
120:     with open(path, "w", encoding="utf-8") as f:
121:         json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
```

**119 行拆开**：

```python
os.path.abspath(path)      # "r.json"        → "/home/u/DISCOVERSE/r.json"
os.path.dirname(...)       # 取目录部分       → "/home/u/DISCOVERSE"
os.makedirs(..., exist_ok=True)   # 建目录，已存在不报错
```

⚠️ **为什么要先 `abspath`**：如果 path 是相对路径 `"r.json"`，`dirname` 会返回**空字符串** `""`，`os.makedirs("")` 会抛 `FileNotFoundError`。

**121 行两个参数**：

| 参数 | 不写会怎样 |
|---|---|
| `ensure_ascii=False` | 中文变成 `任务` 转义序列，人看不懂 |
| `indent=2` | 全挤在一行，diff 时看不出改了什么 |

```python
123: @classmethod
124: def from_json(cls, path: str) -> "TaskResult":
125:     with open(path, "r", encoding="utf-8") as f:
126:         return cls(**json.load(f))
```

⭐ **126 行有个隐藏的好处**：`cls(**...)` 会走 `__init__`，**于是 `__post_init__` 的三条校验又跑了一遍**。

📌 **意味着：从磁盘读回来的脏数据也会被拦住。** 契约在序列化边界的两侧都成立。

## 2.9 `from_config_error`（128-136 行）

```python
128: @classmethod
129: def from_config_error(cls, robot: str, task: str, message: str) -> "TaskResult":
130:     """构造一个"没跑起来"的结果。"""
131:     return cls(
132:         robot=robot, task=task, success=False,
133:         exit_code=ExitCode.CONFIG_ERROR,
134:         failure_mode=FailureMode.CONFIG,
135:         error_message=message,
136:     )
```

**这是一个「命名构造器」** —— 把「配置错误」这个高频组合固化成一个方法。

好处：调用方不会漏掉 133/134 行的搭配。**`exit_code=2` 和 `failure_mode=CONFIG` 必须同时出现**，写成方法就不会有人只写一半。

---

# 第三部分：`junit_report.py` 逐行（96 行）

## 3.1 为什么需要这个文件

契约是给机器读的（JSON），但**人要在 CI 网页上看**。JUnit XML 是 CI 世界的事实标准 —— Jenkins 的 `junit` 步骤、GitHub 的 Test Reporter、GitLab CI 都能原生解析。

## 3.2 imports（14-20 行）

```python
16: import xml.etree.ElementTree as ET     # 标准库 XML 构建
17: from typing import List, Sequence
18: from xml.dom import minidom            # 只为了美化缩进
20: from discoverse.testing.result_schema import TaskResult, FailureMode
```

⚠️ **17 行的 `List` 未被使用** —— 见第七部分。

## 3.3 `_failure_text()`（23-40 行）

```python
23: def _failure_text(r: TaskResult) -> str:
25:     lines = [
26:         f"robot          = {r.robot}",
27:         f"task           = {r.task}",
28:         f"failure_mode   = {r.failure_mode}",
29:         f"exit_code      = {r.exit_code}",
30:         f"completed      = {r.completed_states}/{r.total_states} 状态",
31:         f"sim_time       = {r.sim_time:.2f}s",
32:         f"wall_time      = {r.wall_time:.2f}s",
33:     ]
34:     if r.seed is not None:
35:         lines.append(f"seed           = {r.seed}   # 复现用")
36:     if r.error_message:
37:         lines.append(f"\n错误信息:\n{r.error_message}")
38:     if r.stdout_tail:
39:         lines.append(f"\n--- stdout 尾部 ---\n{r.stdout_tail}")
40:     return "\n".join(lines)
```

**26-32 行为什么要对齐等号**：这段文本会出现在 CI 网页的失败详情框里，**等宽字体下对齐才好扫读**。

**34 行为什么判 `is not None` 而不是 `if r.seed`**：

```python
if r.seed:          # ❌ seed=0 时不会打印！0 是合法种子
if r.seed is not None:   # ✅
```

⚠️ **这是个经典陷阱** —— `0`、`""`、`[]` 在布尔上下文里都是 False。

**36/38 行反而用了 `if r.xxx`**：因为空字符串确实该跳过，这里是**故意**的。

## 3.4 `build_junit_tree()`（43-86 行）

```python
43: def build_junit_tree(results, suite_name="discoverse.cicd") -> ET.ElementTree:
45:     total_time = sum(r.wall_time for r in results)
46:     failures = sum(1 for r in results if not r.success
47:                    and r.failure_mode != FailureMode.CONFIG)
50:     errors = sum(1 for r in results if r.failure_mode == FailureMode.CONFIG)
```

### ⭐ 46-50 行：failure 和 error 分开数

| 标签 | 语义 | 对应退出码 |
|---|---|---|
| `<failure>` | 断言失败 —— **跑完了**，被测对象没通过 | 1 |
| `<error>` | 测试自身出错 —— **根本没跑起来** | 2 |

📌 CI 面板会**分开计数**，一眼看出「产品坏了」还是「测试环境坏了」。

**46 行的 `sum(1 for ...)` 是什么**：生成器表达式，等价于 `len([x for x in ... if 条件])` 但不建中间列表。

```python
52:     testsuites = ET.Element("testsuites", {...})
59:     testsuite = ET.SubElement(testsuites, "testsuite", {...})
```

**为什么套两层**：JUnit schema 规定 `<testsuites>` 是根，可以含多个 `<testsuite>`。
即使只有一个 suite，**也得套两层**，否则某些解析器不认。

```python
68:     for r in results:
71:         case = ET.SubElement(testsuite, "testcase", {
72:             "classname": f"{suite_name}.{r.robot}",     # ← 机器人
73:             "name": r.task,                              # ← 任务
74:             "time": f"{r.wall_time:.3f}",
75:         })
76:         if r.success:
77:             continue                    # ← 成功的用例不加子节点
```

### ⭐ 72-73 行：映射方式决定了 CI 界面的分组

CI 按 `classname` 自动分组：

```
discoverse.cicd.airbot_play
    ├── place_block     ✅
    └── cover_cup       ❌
discoverse.cicd.panda
    ├── place_block     ✅
    └── cover_cup       ❌
```

于是：
- **某机器人整栏全红** → 这个机器人的配置/模型有问题
- **某任务在所有机器人下都红** → 这个任务的判据有问题

> **让报告的结构去承载诊断信息**，比在错误文本里写一百字有用。

**77 行 `continue` 是 JUnit 的约定**：**通过的用例就是一个空的 `<testcase/>`**，没有子节点。

```python
79:         tag = "error" if r.failure_mode == FailureMode.CONFIG else "failure"
80:         node = ET.SubElement(case, tag, {
81:             "type": str(r.failure_mode),
82:             "message": (r.error_message or f"{r.robot}/{r.task} 失败")[:200],
83:         })
84:         node.text = _failure_text(r)
```

**82 行两个技巧**：

```python
(r.error_message or f"{r.robot}/{r.task} 失败")[:200]
 └──── 为 None/空 时用兜底文案 ────┘         └─ 截断 ─┘
```

⚠️ **为什么截断 200**：`message` 是 XML **属性**，会显示在 CI 的列表页。太长会撑爆表格。
完整内容放在 84 行的 `node.text`（**元素正文**，显示在详情页）。

📌 **属性 = 摘要，正文 = 详情。** 这是 JUnit 的惯例。

## 3.5 `write_junit_xml()`（89-96 行）

```python
89: def write_junit_xml(results, output_path, suite_name="discoverse.cicd") -> str:
91:     tree = build_junit_tree(results, suite_name)
92:     xml_bytes = ET.tostring(tree.getroot(), encoding="utf-8")
93:     pretty = minidom.parseString(xml_bytes).toprettyxml(indent="  ", encoding="utf-8")
94:     with open(output_path, "wb") as f:
95:         f.write(pretty)
96:     return output_path
```

**92-93 行为什么要绕一圈**：`ElementTree` **不会**自动缩进，产出的是一整行。
`minidom.toprettyxml()` 能加缩进，但 minidom 不适合构建 —— **所以用 ET 构建，用 minidom 美化**。

**94 行注意是 `"wb"`（二进制）**：因为 93 行传了 `encoding="utf-8"`，`toprettyxml` 返回的是 `bytes` 而不是 `str`。

---

# 第四部分：`__init__.py` 逐行（13 行）

```python
1: """DISCOVERSE 测试基础设施。
2:
3: 本包提供 CICD 批量测试的结构化结果契约，替代早期基于
4: stdout emoji 字符串匹配的脆弱判定。
5: """
6:
7: from discoverse.testing.result_schema import (
8:     TaskResult,
9:     FailureMode,
10:    ExitCode,
11: )
12:
13: __all__ = ["TaskResult", "FailureMode", "ExitCode"]
```

**7-11 行的作用**：让调用方写

```python
from discoverse.testing import TaskResult          # ✅ 短
# 而不是
from discoverse.testing.result_schema import TaskResult   # ❌ 长
```

**13 行 `__all__` 的作用**：声明「这个包对外的公开接口是这三个」。

它影响 `from discoverse.testing import *`（只导入这三个），也是给读代码的人看的**契约声明**。

⚠️ **注意 `junit_report` 没有被 re-export** —— 调用方得写 `from discoverse.testing.junit_report import write_junit_xml`。
这是**有意的**：`TaskResult` 是核心契约，JUnit 只是其中一种渲染方式。

---

# 第五部分：runtime 的 5 处埋点逐行

⚠️ **`universal_task_runtime.py` 是上游代码，改动原则：只加不改。**

## 5.1 import（第 2、5、23 行）

```python
2:  import sys                                    # ← 新增，为了 sys.exit
5:  from datetime import datetime                 # ← 新增，为了 timestamp
23: from discoverse.testing import TaskResult, FailureMode, ExitCode   # ← 新增
```

## 5.2 埋点①：IK 失败（224-229 行）

```python
224: if not self.set_target_from_primitive(state_config):
225:     print(f"   ❌ 状态 {self.stm.state_idx} 设置失败")
226:     # 记录失败模式：状态机中途 IK 求解不收敛
227:     self.failure_mode = FailureMode.IK_EARLY        # ← 新增
228:     self.running = False
229:     return False
```

**语义**：状态机**没走完**就卡住了。`completed_states < total_states`。

**排查方向**：运动学、目标位姿是否可达。

## 5.3 埋点②：判据失败（233-239 行）

```python
233: else:
234:     self.success = self.check_task_success()
235:     # 状态全部走完，成败取决于最终判据
236:     if not self.success:
237:         self.failure_mode = FailureMode.FINAL_CHECK     # ← 新增
238:     self.running = False
239:     return True
```

**语义**：状态**全部走完**了，但最终判据没满足。`completed_states == total_states`。

**排查方向**：任务判据、物理参数。

📌 **①和②的区别是今天分类价值的核心** —— 都是失败，但一个是「走不到」，一个是「走到了没做对」。
**重构前这两个在报告里长得一模一样。**

## 5.4 埋点③：超时（241-246 行）

```python
241: elif self.mj_data.time > self.max_time:
242:     # 仿真时间超过 max_time：状态机没能在预算内走完
243:     print(f"   ⏱️  超过最大仿真时间 {self.max_time}s，终止")    # ← 新增
244:     self.failure_mode = FailureMode.TIMEOUT                    # ← 新增
245:     self.running = False
246:     return False
```

⚠️ **注意这是「仿真时间」超时，不是「墙钟时间」超时**。

两种超时来源不同：

| | 谁检测 | 含义 |
|---|---|---|
| 仿真超时（这里） | runtime 自己 | 状态机在仿真世界里没走完 |
| 墙钟超时 | `cicd_testing.py` 的 `subprocess.run(timeout=)` | 进程卡死了 |

**两者都归到 `FailureMode.TIMEOUT`**，但一个由子进程自报，一个由父进程判定。

## 5.5 埋点④：异常（271-276 行）

```python
271: except Exception as e:
272:     print(f"❌ 步进失败: {e}")
273:     self.failure_mode = FailureMode.CRASH          # ← 新增
274:     self.error_message = f"步进异常: {e}"           # ← 新增
275:     self.running = False
276:     return False
```

## 5.6 埋点⑤：`reset()` 初始化

```python
self.failure_mode = FailureMode.NONE      # ← 新增
self.error_message = None                 # ← 新增
```

⚠️ **这一处最容易漏**。不初始化的话，第二轮运行会**继承上一轮的失败模式** —— 上一轮 `ik_early`，这一轮成功了但 `failure_mode` 还挂着旧值，
于是 `__post_init__` 第 100 行当场抛「矛盾的结果」。

📌 **契约的校验会把「忘了重置状态」这类 bug 也一并暴露出来** —— 这是个意外的好处。

## 5.7 `_current_seed()`

```python
def _current_seed(self):
    rand_cfg = self.task.task_config.randomization or {}
    return (rand_cfg.get("settings") or {}).get("seed")
```

**两个 `or {}` 各防什么**：

```python
self.task.task_config.randomization or {}    # randomization 段可能不存在 → None
(rand_cfg.get("settings") or {})             # settings 段可能不存在 → None
.get("seed")                                  # seed 可能没写 → 返回 None
```

⚠️ **为什么不用 `.get("settings", {})`**：

```python
{"settings": None}.get("settings", {})    # → None ！默认值不生效
{"settings": None}.get("settings") or {}  # → {}   ✅
```

📌 **`.get(k, default)` 只在「键不存在」时用默认值；键存在但值是 `None` 时，返回的还是 `None`。**
YAML 里 `settings:` 后面空着就会解析成 `None` —— 所以这里必须用 `or`。

## 5.8 `build_result()`

```python
exit_code=ExitCode.SUCCESS if success else ExitCode.FAILED,
failure_mode=None if success else (self.failure_mode or FailureMode.FINAL_CHECK),
```

**第二行的 `or FINAL_CHECK` 是兜底**：万一某条失败路径忘了埋点，`failure_mode` 还是 `None`，
契约第 104 行会抛异常。用 `or` 兜一个默认分类，**保证契约永远能构造出来**。

⚠️ **这是个取舍**：兜底意味着「忘了埋点」不会被立刻发现，会被归到 `final_check`。
另一种做法是**不兜底，让它炸** —— 那样能立刻发现漏埋点，但代价是生产环境崩溃。

**这里选了前者**，因为契约的目的是「产出结果」，不是「惩罚开发者」。

## 5.9 ⭐ 最关键的一行

```python
_result = main(args.robot, args.task, sync=args.sync, once=args.once,
               headless=args.headless, result_json=args.result_json)

# 缺陷 #2 修复：把成败送出进程边界。
# 没有这一行，main() 正常返回 -> 解释器默认退出码 0 -> 任何调用方都分不出成败。
sys.exit(int(_result.exit_code))
```

**`int()` 为什么必须写**：`ExitCode` 虽然是 `IntEnum`，但 `sys.exit()` 对非 int 对象的处理是
**打印它然后退出码 1**。显式 `int()` 消除歧义。

---

# 第六部分：19 个测试逐个

## 6.1 `test_result_schema.py`（8 个）

| # | 测试名 | 断言什么 | 为什么需要 |
|---|---|---|---|
| 1 | `test_success_result_is_accepted` | 正常成功结果能构造 | **基线** —— 校验不能误伤合法输入 |
| 2 | `test_failure_requires_a_mode` | `success=False` 无 mode → ValueError | 守护第三条不变式 |
| 3 | `test_success_must_not_carry_failure_mode` | 成功带 mode → ValueError | 守护第二条 |
| 4 | `test_unknown_failure_mode_rejected` | `"tiemout"` → ValueError | 守护第一条 |
| 5 | `test_roundtrip_through_json` | 写盘再读回，`to_dict()` 相等 | ⭐ **跨进程不丢信息** |
| 6 | `test_json_is_plain_serializable` | JSON 里 `exit_code` 是 int | 守护「不用 Enum」这个决定 |
| 7 | `test_codes_are_distinct` | 0/1/2 互不相同 | 防手滑改重 |
| 8 | `test_config_error_is_not_a_task_failure` | `from_config_error` 产出 2+CONFIG | 守护命名构造器 |

**第 1 个测试为什么重要**：只测「非法输入被拒绝」是不够的 —— 万一校验写得太严，合法输入也被拒绝，那 2/3/4 全过但代码全废。

**辅助函数 `make_ok()`**：

```python
def make_ok(**kw):
    base = {"robot": "airbot_play", "task": "place_block", "success": True,
            "completed_states": 10, "total_states": 10, "exit_code": ExitCode.SUCCESS}
    base.update(kw)          # ← 允许调用方覆盖任意字段
    return TaskResult(**base)
```

📌 **这个模式叫「测试数据工厂」** —— 给一份合法默认值，测试只需说明「我要改哪个字段」。

## 6.2 `test_junit_report.py`（6 个）

**fixture `mixed_results`** 故意造了三种结果：成功、任务失败、配置错误 —— **一个 fixture 覆盖三条渲染路径**。

| # | 测试名 | 断言什么 |
|---|---|---|
| 1 | `test_xml_is_wellformed_and_counts_match` | `tests=3, failures=1, errors=1` |
| 2 | `test_config_error_renders_as_error_not_failure` | ⭐ panda 是 `<error>`，airbot 是 `<failure>` |
| 3 | `test_passing_case_has_no_child_nodes` | 成功用例是空节点 |
| 4 | `test_failure_text_carries_repro_info` | 正文含 `seed = 13` 和 `0/17 状态` |
| 5 | `test_classname_groups_by_robot` | classname 按机器人分组 |
| 6 | `test_empty_results_still_valid_xml` | ⭐ **空列表也产出合法 XML** |

**第 6 个为什么重要**：如果一次批量跑挂在最开头，`results` 是空的。
产出损坏的 XML 会让 **CI 的报告步骤**报错 —— **于是你看到的是「报告解析失败」而不是「测试失败」**，排查方向全错。

## 6.3 `test_exit_code_contract.py`（5 个）

**⚠️ 最重要的一个文件** —— 它真的起子进程跑 MuJoCo 仿真。

### fixture `task_seed`

```python
@pytest.fixture
def task_seed(request):
    seed = request.param                          # ← indirect 参数化传进来的值
    with open(TASK_YAML, encoding="utf-8") as f:
        original = f.read()                       # ← 存【原始文本】
    cfg = yaml.safe_load(original)
    cfg.setdefault("randomization", {}).setdefault("settings", {})["seed"] = seed
    with open(TASK_YAML, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
    try:
        yield seed
    finally:
        with open(TASK_YAML, "w", encoding="utf-8") as f:
            f.write(original)                     # ← ⭐ 写回原文，不是再 dump
```

**`setdefault` 链**：

```python
cfg.setdefault("randomization", {})       # 没有就建空 dict，返回它
   .setdefault("settings", {})            # 同上
   ["seed"] = seed                        # 赋值
```

⭐ **`finally` 里写 `original` 而不是重新 dump** —— 这是整个文件最讲究的一行：

| 做法 | 后果 |
|---|---|
| `f.write(original)` | ✅ **逐字节还原**，md5 不变，`git diff` 干净 |
| `yaml.safe_dump(原cfg)` | ❌ 重排键序、**丢掉所有注释**、改引号风格 → git diff 花掉 |

**`try/finally` 保证即使断言失败也会还原**，不污染工作区。

### `run_task()`

```python
def run_task(result_json=None):
    cmd = [sys.executable, RUNTIME, "-r", "airbot_play", "-t", "place_block", "-1", "--headless"]
    if result_json:
        cmd += ["--result-json", result_json]
    env = dict(os.environ, MUJOCO_GL="osmesa")
    # check=False：非零退出码正是本文件要断言的对象，不能让它抛异常
    return subprocess.run(cmd, capture_output=True, text=True, check=False,
                          timeout=TIMEOUT_S, cwd=DISCOVERSE_ROOT_DIR, env=env)
```

| 参数 | 作用 |
|---|---|
| `sys.executable` | 当前 python 解释器的绝对路径 —— **不是** `"python"`，避免走到系统 python |
| `capture_output=True` | 捕获 stdout/stderr（断言消息里要用） |
| `text=True` | 返回 str 而不是 bytes |
| ⭐ `check=False` | **非零退出码是预期输入，不是异常** |
| `env=dict(os.environ, MUJOCO_GL="osmesa")` | 在现有环境基础上覆盖一个变量 |

⚠️ **`check=False` 那行注释必须留着** —— ruff 的 `PLW1510` 规则会要求显式写 `check`，
而如果有人「顺手」改成 `check=True`，**今天所有工作会被原地毁掉**：非零退出码变成异常，就永远测不到退出码本身。

### 5 个用例

```python
@pytest.mark.parametrize("task_seed,expected_rc",
                         [(SEED_PASS, 0), (SEED_FAIL, 1)],
                         indirect=["task_seed"])
def test_exit_code_reflects_task_outcome(task_seed, expected_rc):
```

**`indirect=["task_seed"]` 什么意思**：

| | 普通 parametrize | `indirect` |
|---|---|---|
| 参数值 | 直接传给测试函数 | **先传给同名 fixture** |
| 这里 | `expected_rc` 直接用 | `task_seed` 的 42/13 传给 fixture，fixture 去改 YAML |

📌 所以这两行等于：「**先把配置改成 seed=42，跑，期望退出码 0**」和「**改成 seed=13，跑，期望 1**」。

| # | 测试名 | 断言 |
|---|---|---|
| 1-2 | `test_exit_code_reflects_task_outcome` | seed42→0，seed13→1 |
| 3 | `test_failure_writes_structured_result` | 结果文件 `failure_mode == "final_check"`，`completed == total` |
| 4 | `test_success_writes_structured_result` | `failure_mode is None`，`completed == total > 0` |
| 5 | `test_unknown_robot_is_config_error_not_task_failure` | 退出码 **2**，stderr 含「未知机器人」 |

**断言消息带 stdout 尾部**：

```python
assert proc.returncode == expected_rc, (
    f"seed={task_seed} 期望退出码 {expected_rc}，实际 {proc.returncode}\n"
    f"stdout 尾部:\n" + "\n".join(proc.stdout.splitlines()[-15:])
)
```

📌 **这个测试跑在 CI 上，红了的时候你看不到现场** —— 断言消息就是唯一的现场。

---

# 第七部分：ruff 报的 12 个问题

⚠️ **这些目前不影响 CI** —— lint job 只对 `tests/` 严格，`discoverse/` 是 `continue-on-error`。
但 `discoverse/testing/` 是**你新写的代码**，不是上游遗留。

```bash
env -u PYTHONPATH $PY -m ruff check discoverse/testing/
# Found 12 errors.
# [*] 8 fixable with the `--fix` option
```

| 规则 | 位置 | 说明 | 该不该修 |
|---|---|---|---|
| `F401` | `result_schema.py:23` | **`field` 从未使用** | ✅ **该修**，真问题 |
| `F401` | `junit_report.py:17` | `List` 从未使用 | ✅ 该修 |
| `I001` | `__init__.py:7` | import 未排序 | ✅ 自动修 |
| `UP037` | `result_schema.py:129` | `-> "TaskResult"` 引号多余（有 `from __future__`） | ✅ 自动修 |
| 其余 | 各处 | 格式类 | ✅ 自动修 |

**建议**：

```bash
env -u PYTHONPATH $PY -m ruff check discoverse/testing/ --fix
env -u PYTHONPATH MUJOCO_GL=osmesa $PY -m pytest tests/ -q    # 确认仍 141
```

📌 **修完要重跑测试** —— `--fix` 会动 import 顺序，虽然极少出问题，但**改了代码就要验证**是铁律。

---

## 附：三个文件的依赖关系

```
discoverse/testing/result_schema.py     ← 无外部依赖（只用标准库）
        ↑
        ├── discoverse/testing/junit_report.py      （渲染）
        ├── discoverse/testing/__init__.py          （re-export）
        │
        ├── examples/universal_tasks/universal_task_runtime.py   （生产者）
        └── examples/universal_tasks/cicd_testing.py             （消费者）
                ↑
        tests/unit/test_result_schema.py
        tests/unit/test_junit_report.py
        tests/integration/test_exit_code_contract.py
```

📌 **`result_schema.py` 只依赖标准库**（json/os/dataclasses/enum/typing）——
这是刻意的：**契约层不该依赖 MuJoCo、numpy 或任何重型库**，否则 Day 18-19 的数据校验想复用它时会被迫拖进一堆无关依赖。
