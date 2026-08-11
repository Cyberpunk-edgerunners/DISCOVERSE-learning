# Devil Log · Day 2 — 过程实录

> 2026-07-29 / 07-30 ｜分支 `feat/test-infra`
> 这份是**踩坑实录**，按时间顺序。知识拆解见 [devil-note-day02.md](devil-note-day02.md)。

---

## 时间线概览

**上半场（Step 1-4，约 2 小时）**

| 时段 | 事件 | 结果 |
|---|---|---|
| 开场 | 纠结要不要 `conda activate` | 确定用绝对路径解释器 |
| ~40min | **卡在 `ModuleNotFoundError: lark`** | 定位到 ROS PYTHONPATH 污染 |
| ~15min | 发现 pyproject.toml 已有 pytest 配置 | 决定改上游，删自建 pytest.ini |
| ~10min | 反向验证 `--strict-markers` | 一次通过 |
| ~20min | 写 conftest + fixture 自检 | 7 passed |
| 收尾 | 写 checkpoint | **heredoc 静默截断，200 行只写了 15 行** |

**下半场（Step 5-8）**

| 时段 | 事件 | 结果 |
|---|---|---|
| 侦查 | 横向扫 9 个机器人 YAML | `ctrl_dim == arm + gripper` 9/9 成立 |
| 侦查 | 和 MJCF 对账 | **`qpos_dim` 4/9 不符 → 缺陷 H** |
| Step 5 | 写 `test_robot_config.py` | 61 passed, 4 xfailed |
| 迷失 | **「感觉乱七八糟被牵着走」** | 补写主线图进计划文档 |
| 侦查 | 任务配置结构 | **发现 extends 继承机制** |
| Step 6 | 写 `test_task_config.py` | **5 个测试全红 → 判断是测试错** |
| Step 7 | 覆盖率基线 | **5% → 30%** |
| Step 8 | 清理提交 | `ce88e8d` + `cc3fc02` |

**最终产出**：90 passed / 4 skipped / 9 xfailed，覆盖率 30%，7 条缺陷（4 条今日新增）

---

## 卡点 1｜`ModuleNotFoundError: No module named 'lark'`

### 现象

配置刚写完，第一次跑 `$PY -m pytest --collect-only`，直接吐了 40 行 traceback：

```
File ".../site-packages/_pytest/config/__init__.py", line 1583, in parse
    self.pluginmanager.load_setuptools_entrypoints("pytest11")
...
File "/opt/ros/humble/lib/python3.10/site-packages/launch_testing/__init__.py", line 15
    from . import tools
...
ModuleNotFoundError: No module named 'lark'
```

### 我的第一反应（错的）

「缺包，`pip install lark` 就行。」

**幸好先看了 traceback 的中间部分**，注意到一个矛盾：

- 我用的是 conda 环境的 `$PY`
- 但报错文件路径是 `/opt/ros/humble/lib/python3.10/site-packages/`

**conda 环境里的 python，为什么会去加载 `/opt/ros/` 下的模块？**

这个矛盾是整个排查的转折点。

### 排查

```bash
echo $PYTHONPATH
# /opt/ros/humble/lib/python3.10/site-packages:/opt/ros/humble/local/lib/python3.10/dist-packages
```

真相大白。`~/.bashrc` 里的 `source /opt/ros/humble/setup.bash` 导出了 `PYTHONPATH`，而**它的优先级高于 conda 的环境隔离**。

### 完整根因链

```
~/.bashrc: source /opt/ros/humble/setup.bash
  -> export PYTHONPATH=/opt/ros/humble/.../site-packages
  -> 任何 Python 进程启动时，这个路径都被加进 sys.path（优先级高于 conda）
  -> pytest 启动 -> load_setuptools_entrypoints("pytest11")
     （扫描 sys.path 上所有声明了 pytest11 entry point 的包）
  -> 找到 ROS 的 launch_testing
  -> import launch -> import lark
  -> lark 装在 ROS 的 python 里，没装在 conda 里
  -> 崩
```

**三件事凑到一起**才炸：ROS 导出 PYTHONPATH + launch_testing 注册成 pytest 插件 + pytest 无条件加载所有插件。

### 早期的一个线索被我忽略了

Day 0 装环境时 `pip list` 里有个 `launch-yaml 1.0.13`，当时觉得不起眼。**那就是 ROS 包混进来的信号**，但我没深究。

> **教训：`pip list` 里出现和项目无关的包名，值得追一下来源。**

### 方案选择

| 方案 | 做法 | 我的判断 |
|---|---|---|
| A | `-p no:launch_testing` | 先试了，**没用** |
| B | `unset PYTHONPATH` | ✅ 采用 |
| C | `pip install lark` | ❌ 喂饱错误 |

**为什么 A 没用**：`-p no:` 要求插件**先被成功导入**才能禁用。ROS 的插件在导入期就炸了，`-p no:` 根本来不及执行。

**为什么选 B 不选 C**：测试目标是 `discoverse` 核心库，**根本不需要 ROS**。Day 8-9 的 Docker 测试镜像也不会装 ROS。**现在就让本地环境向 CI 环境看齐**，避免「本地过、CI 挂」。

### 固化

写了 [scripts/dev/env.sh](../scripts/dev/env.sh)，三行：

```bash
export PY=/home/ubuntu22/miniconda3/envs/discoverse/bin/python
export MUJOCO_GL=osmesa
unset PYTHONPATH
```

**并写了一条回归测试** `test_no_ros_pollution_in_syspath`——把这个知识从脑子里搬进了会自动运行的地方。

**当天就派上用场了**：后面有一次我忘了 `source env.sh`（见卡点 3）。

---

## 卡点 2｜`EOFopts` —— 一个不是问题的问题

### 现象

heredoc 写 `pytest.ini` 后，终端显示：

```
timeout = 60
EOFopts = --strict-markers --tb=short -ra
```

`EOFopts` 是什么鬼？看起来 `EOF` 和 `addopts` 粘在一起了。

### 排查

```bash
cat -A pytest.ini | tail -5
```

```
timeout = 60$
addopts = --strict-markers --tb=short -ra$
```

`$` 是行尾符。**两行是分开的，文件完全正确。**

### 结论

**终端回显 ≠ 文件内容。** 多行粘贴含中文（宽字符）时，bash 的行编辑器在处理 heredoc 续行时会回显错位。

后面还出现了更离谱的：

```
$PY -m pytest --collect-onlybak 真相原则）"utf-8")条明确的失败。），不让缺失隐形
```

**全是显示假象，文件都是对的。**

### 养成的习惯

写完文件不看回显，跑：

```bash
wc -l <file> && tail -3 <file>
```

**这个习惯在卡点 4 救了我。**

---

## 卡点 3｜`source scripts/dev/env.sh: No such file or directory`

### 现象

跑一大段命令，结果里夹着这么一行：

```
bash: scripts/dev/env.sh: No such file or directory
```

但**后面的命令全都成功了**，最终输出是我想要的。

### 为什么会这样

我上一轮跳过了「创建 env.sh」这步，直接跑了后面的命令。之所以还能成功，是因为**环境变量还残留在当前终端**（更早手敲的 `export PY` / `unset PYTHONPATH` 仍然有效）。

**一旦关掉终端，lark 错误立刻回来。**

### 真正的教训

`source` 一个不存在的文件时，bash **只打印一行错误就继续往下执行**，不中断。这行错误被后面几十行输出冲走了，我差点没看见。

> **这正是 `-ra` 存在的理由——失败信息必须被汇总到末尾，否则在长输出里等于不存在。**
>
> 和 Day 1 `trace_chain.py` 末尾打印「未触发」是同一个设计。

---

## 卡点 4｜checkpoint 文件被静默截断（最惊险的一次）

### 现象

写 `checkpoint-day02.md`，heredoc 里有大约 200 行内容。命令跑完，**没有任何报错**。

第二天检查：

```bash
wc -l docs/checkpoint/checkpoint-day02.md
# 15
```

**只写入了 15 行**，而且断在一个 ` ```bash ` 代码块中间。

### 为什么会截断

heredoc 内容里嵌套了 ` ``` ` 代码围栏和大量特殊字符，某处触发了 bash 的解析边界。**但 bash 没有报任何错**——它认为自己正常结束了。

### 惊险在哪

这是一份**跨会话的交接文档**。如果我关机后回来直接用它，会发现：

- 只有「下次开工第一件事」
- 没有缺陷记录、没有方法论沉淀、没有 Step 5 的接续说明

**一整天的思考几乎丢掉，而且没有任何警告。**

### 补救

改用 Write 工具直接写文件，绕开 heredoc 的转义问题。

### 教训升级

卡点 2 的结论是「回显是假象，文件通常是对的」。
卡点 4 补充了下半句：**「但有时文件真的是错的，而且不会报错。」**

**所以 `wc -l && tail -3` 不是可选步骤，是必选步骤。**

> 💡 **面试可以这么讲**：
> 「我写交接文档时用 heredoc，跑完没报错，第二天发现 200 行只写入了 15 行，断在代码块中间。这让我意识到**「命令没报错」和「命令做对了」是两回事**。之后我给所有文件写入操作加了一步 `wc -l && tail -3` 验证——用两秒钟的检查，换掉一类静默失败。这和我在测试里坚持『新写的断言必须先红一次』是同一个原则：**不要相信没被验证过的成功。**」

---

## 意外收获｜反向验证撞出了更严重的问题

### 计划

我写了 `test_no_ros_pollution_in_syspath`，想验证它「有能力变红」——**一个永远为真的断言等于没写**。

```bash
(
  export PYTHONPATH=/opt/ros/humble/lib/python3.10/site-packages
  $PY -m pytest ...::test_no_ros_pollution_in_syspath -q -p no:launch_testing
)
```

**预期**：`FAILED`，错误信息是我写的「ROS 路径混入 sys.path」。

### 实际

```
PluginValidationError: unknown hook 'pytest_launch_collect_makemodule'
in plugin launch_testing_ros_pytest_entrypoint
INTERNALERROR
```

**完全不是我预期的失败方式。**

### 读出了什么

1. `-p no:launch_testing` 挡住了那一个插件，但 ROS 的 site-packages 里**还有另一个**插件 `launch_testing_ros_pytest_entrypoint`，它注册了 pytest 9 已移除的 hook。

2. **污染发生的位置比我以为的还要靠前**——pytest 连收集阶段都进不去就崩溃，我的断言**根本没机会执行**。

3. 这反过来印证了当初选方案 B（`unset PYTHONPATH`）而不是方案 A（`-p no:`）是对的。**`-p no:` 是打地鼠，永远挡不完。**

### 那条断言还留着吗

留着，但**注释改准确了**——它守的是第三种、也是最隐蔽的一种污染：

| 场景 | 谁抓到 |
|---|---|
| PYTHONPATH 污染，插件能加载 | pytest 自己（lark 错误） |
| PYTHONPATH 污染，hook 不兼容 | pytest 自己（INTERNALERROR） |
| **`.pth` / `sitecustomize` / 代码污染 sys.path** | **我的断言** |

第三种不会让 pytest 崩溃，只会让 `import` 悄悄取到错版本的模块。**没有断言就完全不可见。**

> **反向验证的回报常常超出计划。** 我本来只想确认断言能变红，结果发现了一个更早、更严重的失败模式，还顺便验证了架构决策。

---

## 一个「不是 bug 的现象」：靠巧合正确

侦查 `RobotConfigLoader` 时发现（缺陷 E）：

```python
# robot_config.py:129
@property
def arm_joints(self):
    return self.config['kinematics']['arm_joint_names']   # 返回 list

# robot_config.py:134
@property
def arm_joints_count(self):
    return self.config['kinematics']['arm_joints']        # 返回 int
```

**属性名和 YAML 键交叉错位了。** 名字叫 `arm_joints` 的属性，返回的是 `arm_joint_names`。

### 阴险之处

计划文档里的示例断言：

```python
assert len(loader.arm_joints) > 0
```

**这条会通过。** 因为 `arm_joints` 返回列表，`len()` 恰好能用。

但如果你按直觉理解 `arm_joints` 是「关节数量」，写出 `assert loader.arm_joints == 6`，就会困惑为什么失败。

**它不表现为异常，而是「靠巧合正确」**——和 Day 1 发现的缺陷 C（`record_fps` 默认值）是同一个物种。

### 怎么处理（Step 5 待做）

三条测试并存：

```python
# 1. 钉死当前行为
def test_arm_joints_current_behavior_returns_names(...):
    assert isinstance(value, list)

# 2. 记录期望行为（可执行的缺陷报告）
@pytest.mark.xfail(reason="缺陷 E", strict=True)
def test_arm_joints_should_be_int_count(...):
    assert isinstance(loader.arm_joints, int)

# 3. 绕开命名争议，断言跨字段自洽
def test_joint_count_matches_names_length(...):
    assert loader.arm_joints_count == len(loader.arm_joint_names)
```

**第 2 条是重点：`xfail(strict=True)` 把缺陷变成了可执行的文档。** 修复后它会变成 `XPASS` 失败，提醒你去掉 xfail 标记。

---

# 下半场（Step 5-8）

---

## 侦查｜先验证假设，再写断言

写 `test_robot_config.py` 前，我想写这条断言：

```python
assert ctrl_dim == arm_joints + gripper.ctrl_dim
```

`airbot_play` 是 `7 == 6 + 1`，成立。**但只验了 1 个样本就想写进 9 个的参数化测试** —— 这是没有根据的推断。

横向扫完 9 个：**9/9 全部成立**，覆盖了 6+1=7 和 7+1=8 两种情况。**这才敢写。**

### 然后做了一件计划外的事：和 MJCF 对账

YAML 是**人写的描述**，MJCF 编译结果是**物理引擎的事实**。两者不一致时 MJCF 是真相。

```
robot           qpos_dim    nq  ctrl_dim    nu   verdict
airbot_play            8     8         7     7   OK
arx_x5                 7     8         7     7   QPOS 不符
iiwa14                 9    15         8     8   QPOS 不符
piper                  7     8         7     7   QPOS 不符
rm65                  12    14         7     7   QPOS 不符
（其余 4 个 OK）
```

**4/9 不符 → 缺陷 H。**

### 这个分布本身就是最有价值的信息

**`ctrl_dim` vs `nu` 是 9/9 全对，只有 `qpos_dim` 错。** 为什么？

| 字段 | 写错的后果 | 会被发现吗 |
|---|---|---|
| `ctrl_dim` | `data.ctrl[:] = 长度不符数组` → **立刻 ValueError** | ✅ 开发马上修 |
| `qpos_dim` | `qpos[:9]` 在 `nq=15` 上**完全合法**，静默丢掉后 6 个 | ❌ 没人发现 |

**会炸的字段维护得好，不会炸的字段积累错误。** 这是软件工程的普遍规律，而且**这个规律本身就是找 bug 的地图** —— 下次进新项目，优先怀疑那些「写错也不会炸」的地方。

> 💡 **面试可以这么讲**：
> 「我对账配置文件和 MuJoCo 编译结果时发现，控制维度 9 个机器人全对，位置维度 4 个错。这个分布不是偶然——控制维度写错会立刻抛 ValueError，位置维度写错只是数组切片静默截断。**所以我形成了一个习惯：进新项目先找那些『写错也不会炸』的字段，那里的 bug 密度最高。**」

---

## 迷失｜「感觉乱七八糟被牵着走，找不到主线」

Step 5 中途我说了这句话。**这是真实的感受，不是错觉。**

三个原因：

1. **真实的测试开发是「侦查 → 假设 → 验证」的循环，不是线性推进。** 但没人提前告诉我会这样，我以为跑偏了。
2. **「建设」和「侦查」的命令混在一起。** 写 conftest 是永久产出；`$PY - <<PYEOF` 侦查脚本跑完就没了。我问「这部分代码存在哪里」就是察觉到了这一点。
3. **64KB 的计划文档颗粒度太细**，细节淹没了骨架。

**解决方式**：把三周主线写进计划文档的 `4.0 主线图` 节，并在文档顶部加导航「迷路了跳到 4.0」。

**三句话概括三周**：

```
第 1 周：搞清楚项目怎么工作，建立能自动验证它的基础设施
第 2 周：用这套基础设施覆盖核心功能，挖出真实缺陷
第 3 周：让这一切自动运行（CI + Docker），整理成能对外讲的东西
```

**教训**：**方向感是需要主动维护的东西，不是自然产生的。** 执行细节文档和定位文档必须分开，混在一起两个功能都会失效。

---

## 侦查｜发现 extends 继承机制（静态分析第三次骗我）

直接读 5 个任务 YAML，看到：

```
cover_cup          有 observation ✅
place_block        无 ❌
place_coffeecup    无 ❌
place_kiwi_fruit   无 ❌
stack_block        无 ❌
```

看起来印证了计划文档说的「4/5 任务缺 observation」。**差一点就直接写断言了。**

**但我注意到三个任务有 `extends: templates/place_object.yaml`。**

```yaml
# place_block.yaml
extends: templates/place_object.yaml    ← 配置继承
task_name: place_block
```

**那 3 个任务可能从模板继承了 observation。** 我看到的是**原始 YAML**，不是**合并后的最终配置**。

### 三步验证

| 步骤 | 命令 | 结果 |
|---|---|---|
| 1. 模板里有什么 | 读 `templates/place_object.yaml` | **observation 是 None** |
| 2. 代码处理 extends 吗 | `grep -rn "extends"` | ✅ `config_utils.py:17-18` 有处理 |
| 3. 加载后实际如何 | 用 `TaskConfigLoader` 加载 | 打印「📄 加载模板」，确实合并了 |

**结论：extends 机制正常工作，但模板本身缺字段。**

### 为什么这个区分至关重要

如果没查就写断言，会跑出「4 红 1 绿」，我们会以为验证了缺陷 B。**但根因可能完全不同，修复方式也完全不同**：

| 假想的根因 | 修复方式 |
|---|---|
| 4 个任务各自漏写 | 改 4 个 YAML |
| **模板缺字段 + 1 处漏写** | **改 2 个文件**（1 个模板修好 3 个任务） |

**报错根因的缺陷报告，比不报更糟。** 如果按第一种去修，开发会给 3 个子任务各自补一遍 observation，**重复配置，下次新增任务还会再缺一次**。

> 💡 **面试可以这么讲**：
> 「我发现 5 个任务里 4 个缺相机配置。但我没直接报『4 个配置文件有问题』—— 我先查了加载机制，发现其中 3 个通过 `extends` 继承同一个模板，而**模板本身缺这个字段**。真正的根因是『1 个模板缺字段 + 1 个任务漏写』，改 2 个文件而不是 4 个。**只报现象的话，开发会给 3 个子任务各自补一遍，重复配置，下次新增任务还会再缺。**」

**这是「静态分析会骗人」的第三次现身**（Day 1 是 grep 漏子目录、探针不触发；今天是读文件 ≠ 运行时加载）。

---

## 卡点 5｜5 个测试同时全红 —— 判断出是「测试错」不是「代码错」（今天最有价值的一段）

### 现象

`test_task_config.py` 写完跑，5 个测试全挂，全是同一个错：

```
ValueError: Missing required field in task config: description
```

### 我的判断过程

**新手在这里有两种失败模式**：

| 模式 | 后果 |
|---|---|
| 总怀疑代码 | 提一堆假缺陷，浪费开发时间，信誉受损 |
| **总怀疑自己** | 遇红就改测试迁就，**把真 bug 洗白**（更危险） |

我用了三条线索判断：

| 线索 | 指向 |
|---|---|
| 5 个失败**全在同一处**（`from_dict` 构造阶段，一行断言都没执行到） | 系统性问题，不是分散的 bug |
| 报的是 `Missing required field` | **这是设计好的校验，正在正常工作** |
| 真实的 5 个 YAML 都有 `description` | **我的测试数据不真实** |

**结论：`_validate_config` 是对的，我给的最小配置不完整。改测试。**

### 但没有直接猜着改

先查清必填字段清单：

```bash
$PY -c "import inspect; from ... import TaskConfigLoader; print(inspect.getsource(TaskConfigLoader._validate_config))"
```

（`inspect.getsource` 比 `sed -n` 好，不用猜行号。）

结果比我猜的多：

```
task_name, description                   必填
states 或 task_states 之一，必须非空 list
每个 state 必须有 name + primitive
```

**如果我只补 `description` 就重跑，还会再红一次。** 一次查清，一次改对。

### 副产品：发现了缺陷 I

必填清单里**没有 `observation`**。

```python
required_fields = ['task_name', 'description']    # 没有 observation
```

**校验函数存在，但漏了关键字段。** 这是缺陷 B 能存在于 4/5 任务的**直接原因** —— 配置缺相机却能通过校验、正常加载。

**「有验证」和「验证够」是两回事。** 而且这个区分决定缺陷报告怎么写：

| 说法 | 开发的反应 |
|---|---|
| 「缺少配置校验」 | 「我们有 `_validate_config` 啊」→ 争议 |
| **「`_validate_config` 未覆盖 `observation`，导致 4/5 任务缺相机却通过校验」** | 精确，直接可修 |

> 💡 **面试可以这么讲**：
> 「我写的 5 个测试同时失败。我先判断这是『测试错』还是『代码错』——三条依据：失败全集中在构造阶段而非断言、报的是设计好的校验错误、而真实配置文件都有那个字段。所以是我的测试数据不真实。**但我没有直接猜着改，先用 `inspect.getsource` 打印出完整的必填字段清单**，发现比我以为的多两项。一次查清一次改对。**顺带发现校验清单里没有 observation——那正是另一个缺陷能存在的直接原因。**」

**这段经历的价值**：它证明我既不盲目相信测试结果，也不盲目怀疑自己。**分不清「代码错」和「测试错」时，测试就失去了价值——它既不能给我信心，也不能给我信号。**

---

## Step 7｜覆盖率基线 5% → 30%

```
randomization.py    300 语句   9%    ← 最大模块，几乎没测
task_base.py        160 语句  16%    ← 含最高优先线索
robot_config.py      77 语句  86%    ← 今天的主战场
config_utils.py      48 语句  98%    ← 只差第 83 行
TOTAL               961 语句  30%
```

### 覆盖率报告直接给出了 Day 3-4 的工作清单

**`task_base.py:149-167` 从未被任何测试执行过** —— 而那里正是 checkpoint 标记的「最高优先线索」（`except` 吞异常后返回什么？若返回 `True` 则任何检查出错都判定成功）。

**覆盖率报告确认了这段代码从未被验证。** 它可能解释 Day 1 那条「完成状态 10/10 但实际距离 0.2908m」。

### 但覆盖率高 ≠ 测得好

```python
# record_fps 只有 1 行代码
return self.config.get('observation', {'fps': 30}).get('fps', 30)
```

我给它写了 **4 个测试**（正常值 / 无键 / 空 dict / null 崩溃）。**覆盖率上只算 1 行**，但验证了 4 条执行路径，其中一条是崩溃分支。

反过来，`assert divide(6,2) == 3` 覆盖率 100%，但 `b=0` 完全没测。

**覆盖率是下限指标**：低覆盖一定有问题，高覆盖不保证质量。**看 `Missing` 那列找盲区，不要盯总百分比。**

---

## 卡点 6｜我自己犯的错：加 .gitignore 前没先看已有什么

让用户追加 `.pytest_cache/` 等规则，结果 `git diff --cached` 显示**三条重复** —— 上游 `# CI/CD 产物` 段落早就有了。

**这正是我今天反复强调却自己没做的事：先侦查，再动手。**

`git diff --cached` 在提交前抓住了它。**diff 审查是最后一道防线**，跳过它这三条重复就进版本库了。

---

## 卡点 7｜误粘贴终端输出

用户把上一轮的终端输出（含提示符 `ubuntu22@...$`）整块贴回终端，bash 逐行执行，产生几十行 `command not found`。

**本次无损** —— 那些行凑不出可执行命令。**但同样操作在别的场景可能出事**：如果输出里恰好有一行 `rm -rf build/`，粘回去就真的执行了。

**习惯**：从终端复制时只选命令，不带提示符；长命令写进脚本再执行。

---

## 今日六条硬结论

1. **「命令没报错」≠「命令做对了」。**
   `source` 不存在的文件只打一行错就继续；heredoc 截断完全不报错。**必须显式验证副作用。**

2. **同一个根因可以有多种完全不同的表现。**
   `lark` 和 `PluginValidationError` 看起来毫无关系，根因都是 `PYTHONPATH`。**错误信息也会骗人。**

3. **环境问题在环境层解决。**
   `-p no:` 是打地鼠，`pip install lark` 是喂饱错误，`unset PYTHONPATH` 才是断根。**这条同时决定了 Docker 镜像和 CI 配置怎么写。**

4. **静态读文件 ≠ 运行时加载。**
   `extends` 继承机制让「读 YAML 看到缺失」和「加载后是否缺失」成为两个问题。**这是「静态分析会骗人」的第三次现身。**

5. **测试红了，先判断是「代码错」还是「测试错」。**
   三条依据：失败位置是否集中、错误类型是否是设计好的行为、测试数据是否真实。**分不清的时候，测试就失去了价值。**

6. **「写错也不会炸」的字段，bug 密度最高。**
   `ctrl_dim` 9/9 对（写错立刻 ValueError），`qpos_dim` 4/9 错（写错只是静默截断）。**这个规律本身就是找 bug 的地图。**

---

## 明天的第一件事

```bash
cd /home/ubuntu22/workspaces/airbot-play/DISCOVERSE
source scripts/dev/env.sh
$PY -m pytest tests/ -q     # 预期 90 passed, 4 skipped, 9 xfailed
```

然后接 [checkpoint-day02.md](checkpoint/checkpoint-day02.md) 第九节的 Day 3-4 待办。

**第一件事**：查 `task_base.py:149-167` 的 `except` 吞异常后返回什么。覆盖率报告已确认这段代码从未被执行过，而它可能是整个项目最严重的缺陷。
