# 魔鬼笔记 · Day 13-14 —— 结果契约 / 进程边界 / 可诊断性

> 本篇是知识拆解，不是操作步骤。操作见 [day13-14-result-contract.md](../tutorial/day13-14-result-contract.md)

---

## 一、⭐ 核心认知：「结果」是数据，不是文字

今天所有缺陷的根源可以压缩成一句话：

> **成败被表达成给人看的文字，而不是给机器读的数据。**

这个错误一旦犯下，会**连锁**产生一串补偿性 hack：

```
退出码恒为 0（信息没送出进程边界）
  → 下游无法用退出码判定
    → 只好去 parse stdout
      → 但 stdout 是给人看的，格式随时会变
        → 于是匹配 emoji（"最稳定"的特征）
          → 但 emoji 在日志管道里会被剥离
            → 而且失败日志里也可能出现成功字样（假阳性）
```

每一层 hack 都是在**错误的地基上**加固。正确的做法不是把匹配写得更聪明，而是**换一个信息通道**。

### 判断标准

> 任何需要**用正则从自由文本里捞出来**的信息，都说明设计出了问题。

CI 需要展示或断言的每一条信息，都应该是**独立字段**。

---

## 二、进程边界：函数返回值和退出码是两个世界

### 2.1 信息是怎么蒸发的

```
check_success()  逐条判定           ✅ 算对了
    ↓ return
executor.run()   return self.success ✅ 传上来了
    ↓ return
main()           拿到 success        ✅ 收到了
    ↓ ???
进程退出                             ❌ 没了
```

Python 的 `main()` 正常返回时，解释器默认以 **0** 退出。返回值**不会**自动变成退出码。

```python
sys.exit(0 if success else 1)   # 必须显式写这一行
```

### 2.2 退出码速查

| 码 | 含义 |
|---|---|
| 0 | 成功 |
| 1 | 一般性失败 |
| 2 | 命令用法错误（argparse 默认用它） |
| 126 | 找到了但不可执行 |
| 127 | 命令不存在 |
| 128+N | 被信号 N 杀死 |
| 130 | Ctrl-C（128+2，SIGINT） |
| **139** | **段错误（128+11，SIGSEGV）** |

139 是本项目的现实威胁（缺陷 X）：MuJoCo viewer 清理时段错误，
会让**一次成功的运行**返回 139。所以新契约必须能识别「非契约退出码」。

### 2.3 为什么要区分 1 和 2

| 码 | 性质 |
|---|---|
| 1 | **有效结论** —— 测试系统正常工作，给出了「不通过」这个正确答案 |
| 2 | **无效结论** —— 测试系统自己坏了，没有给出答案 |

混为一谈的代价：拼错一个机器人名，看起来像任务回归，
于是去查一个根本不存在的仿真 bug。

> 「被测对象坏了」和「测试环境坏了」是两类完全不同的事件，
> 不能共用一个信号。

---

## 三、⭐ 让非法状态无法表示

```python
def __post_init__(self):
    if self.failure_mode is not None and self.failure_mode not in FailureMode.ALL:
        raise ValueError(...)                    # 拼错的模式当场炸
    if self.success and self.failure_mode is not None:
        raise ValueError("矛盾的结果：...")       # 成功不能带失败模式
    if not self.success and self.failure_mode is None:
        raise ValueError("矛盾的结果：...")       # 失败必须说明原因
```

这是 "make illegal states unrepresentable" 的实践。

**与其在下游到处写 `if` 防御脏数据，不如让脏数据构造不出来。**

第三条尤其值钱：它把「说明失败原因」从一个**可选的好习惯**，变成了**强制契约**。
堵死了「随手 `return success=False` 了事」的懒惰写法 —— 那正是重构前的老路。

第一条防的是另一类静默失败：`"tiemout"` 这种拼写错误如果不校验，
会**悄悄变成一个新的失败类别**，在统计里单独占一行，而你永远不会发现自己少统计了一类超时。

---

## 四、⭐ 可诊断性：分类比布尔值有用得多

### 4.1 `success=False` 说的太少

它只告诉你「红了」。但红灯有很多种：

| 失败模式 | 该查什么 |
|---|---|
| `ik_early` | 运动学、目标位姿是否可达 |
| `final_check` | 任务判据、物理参数 |
| `timeout` | 性能、死循环 |
| `config` | **根本不是被测代码的问题** |
| `crash` | 段错误、内存 |

> **一个好的红灯，应该自带排查方向。**

### 4.2 实测证据

Day 13-14 的批量测试里，两个 `cover_cup` 都失败：

- `airbot_play` → `ik_early`（IK 求解不收敛）
- `panda` → `config`（缺相机 `eye_arm`，与任务逻辑无关）

**重构前，这两个在报告里长得一模一样**，都是「❌ 失败」加一条无关的 traceback。

### 4.3 意外的副产品：分类照出了 flake 的结构

`cover_cup` 采样 6 次：

```
ik_early    0/17     ik_early 9/17     final_check 17/17
final_check 17/17    ik_early 0/17     final_check 17/17
```

它不只是「有时失败」，而是「**以两种不同机制失败**」：
有时物体被随机到 IK 够不着的位置，有时够得着但没放准。

> `failure_mode` 把「flake」这个模糊概念，变成了可分解、可分别处理的现象。

---

## 五、⭐ 关键词捞错误：为什么必然失效

### 5.1 机制

```python
error_keywords = ["❌", "失败", "Failed", "Error", "Exception", "Traceback", ...]
for line in lines:
    if any(keyword in line for keyword in error_keywords):
        error_lines.append(line.strip())
return " | ".join(error_lines[-3:])       # ← 只留最后 3 行
```

### 5.2 为什么在本项目必然失效

`discoverse/envs/simulator.py:22` 有一个**可选依赖**的导入失败：

```
Traceback (most recent call last):
  File ".../simulator.py", line 22, in <module>
    from gaussian_renderer.gs_renderer_mujoco import GSRendererMuJoCo
ModuleNotFoundError: No module named 'gaussian_renderer'
```

**它每次运行都出现 —— 包括成功的运行**（实测：成功日志里 grep 到 2 处）。

于是关键词扫描永远能捞到它，`[-3:]` 又把真正的错误挤掉。
结果：「机器人名写错了」被报告成「缺少 gaussian_renderer 模块」。

### 5.3 一般化的教训

> 用关键词去日志里捞错误，捞到的往往是**噪声里最响的那条**，而不是真正的原因。
> 只要项目里存在一个「良性的 Traceback」，这套机制就彻底失效 —— 而且是**静默**失效。

这与 Day 2 以来反复出现的主题同源：**静默的错误比响亮的错误危险得多**。

---

## 六、JUnit XML：failure vs error

| 标签 | 语义 | 对应退出码 |
|---|---|---|
| `<failure>` | 断言失败 —— 测试跑完了，被测对象没通过 | 1 |
| `<error>` | 测试自身出错 —— 根本没跑起来 | 2 |

CI 面板会**分开计数**，一眼看出「产品坏了」还是「测试环境坏了」。

### `classname` / `name` 的映射有讲究

用 `classname=机器人`、`name=任务`，CI 界面自动按机器人分组：

- 某机器人整栏全红 → 这个机器人的配置/模型有问题
- 某任务在所有机器人下都红 → 这个任务的判据有问题

> **让报告的结构去承载诊断信息**，比在错误文本里写一百字有用。

---

## 七、契约要跨进程，就得先考虑可序列化

一开始把 `FailureMode` 写成 `Enum`，`json.dump()` 直接抛：

```
TypeError: Object of type FailureMode is not JSON serializable
```

改用普通字符串常量类后，`asdict()` 直接产出可序列化的值，调用方零转换。

对照 `ExitCode` —— 它用 `IntEnum` 是**对的**，因为：

```python
sys.exit(ExitCode.FAILED)              # IntEnum 成员就是 int，直接可用
proc.returncode == ExitCode.SUCCESS    # 直接比较
```

普通 `Enum` 做这两件事都会出错。

> **选类型的依据是「它要跨越什么边界」**：
> 跨进程序列化 → 字符串；要当 int 用 → IntEnum。

---

## 八、⭐ 验证方法论

### 8.1 别用自己的解析器验证自己的输出

我写 XML，我用 `ElementTree` 解析，我说它对 —— **这构不成证据**。
万一我对 JUnit 格式的理解本身就是错的？

用**独立的第三方**解析器（`junitparser`）复核，结论一致，才算验证。

> 这是 Day 10-11 「三层验证法」的延续：自己的断言只是第一层。

### 8.2 看到不一致，先采样再改代码

批量报 `ik_early`、单跑报 `final_check` → 第一反应「分类器写错了」。

**先采样 6 次**，才看清是被测对象本身 flaky。

> 在 flaky 的被测对象上，**单次运行不构成证据**。

### 8.3 别停在第一个「看起来合理」的解释上

容器 `ModuleNotFoundError` 那个坑：
editable install 的 finder 里确实有一份构建时冻结的子包清单，
确实不含新包，看起来完全说得通 —— **但它不是原因**。

真正的原因是 `/workspace` vs `/work` 路径错配。

> 「看起来合理」和「经过验证」之间，差着一个实验。

### 8.4 验证环境必须与 CI 一致

我用 `-v $PWD:/work` 挂载调试，而 CI 是**重建镜像、不挂载**。
于是我花时间调试了一个 **CI 里根本不会发生**的问题。

---

## 九、缺陷之间有依赖关系

今天的核心实验（构造「必然失败的输入」）**完全依赖** Day 3-4 修的缺陷 #1：

```
缺陷 #1 修复（seed 贯穿，commit cd09b80）
    ↓ 使仿真可复现
可以构造「必然失败的 seed=13」和「必然成功的 seed=42」
    ↓ 使断言成为可能
可以写 test_exit_code_reflects_task_outcome
    ↓
缺陷 #2 的回归测试才写得出来
```

> **修 bug 的顺序不是随意的。** 有些缺陷是另一些缺陷的**前置条件**。
> 「可复现性」尤其常常是其他一切验证工作的地基。

---

## 十、一句话总结

> **今天做的事，是把「这次跑得怎么样」从一段给人看的文字，
> 变成一份给机器读的、不能自相矛盾的、自带排查方向的数据。**

副产品：CI 终于会红了。
