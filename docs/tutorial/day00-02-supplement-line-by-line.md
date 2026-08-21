# Day 0-2 补充 — 逐行解析：环境、pytest 骨架、配置层契约测试

> 配套 [day00-setup.md](day00-setup.md)、[day01-am-architecture.md](day01-am-architecture.md)、[day02-pytest-infra.md](day02-pytest-infra.md)
> 用途：**查阅型文档**，不用从头读。看不懂哪一行就跳到哪一节。
> 覆盖：`scripts/dev/env.sh` 53 行 + `pyproject.toml` 测试段 + `tests/conftest.py` 84 行
> ＋ `test_smoke.py` / `test_conftest_fixtures.py` / `test_robot_config.py` / `test_task_config.py` 全部
> ＋ 全部命令行
> 面向：**没搭过测试框架、也不熟 pytest 的读者**。每个概念从零讲起。
> 每节末尾的 **📖 企业级扩展** 是面试加分项，日常做题用不到。

---

## 目录

- [第一部分：预备概念（7 个，不懂这些后面全是天书）](#第一部分预备概念7-个)
- [第二部分：`env.sh` 逐行（53 行）](#第二部分envsh-逐行53-行)
- [第三部分：`pyproject.toml` 测试配置逐行](#第三部分pyprojecttoml-测试配置逐行)
- [第四部分：`conftest.py` 逐行（84 行）](#第四部分conftestpy-逐行84-行)
- [第五部分：冒烟与自检测试逐行](#第五部分冒烟与自检测试逐行)
- [第六部分：`test_robot_config.py` 逐行（241 行）](#第六部分test_robot_configpy-逐行241-行)
- [第七部分：`test_task_config.py` 关键段逐行](#第七部分test_task_configpy-关键段逐行)
- [第八部分：命令行逐字解析](#第八部分命令行逐字解析)
- [第九部分：面试问答速查](#第九部分面试问答速查)

---

# 第一部分：预备概念（7 个）

## 1.1 pytest 是怎么找到你的测试的

你敲 `pytest`，它做四件事，**顺序很重要**：

```
① 读配置        找 pyproject.toml / pytest.ini / setup.cfg
② 收集(collect) 按 python_files/python_classes/python_functions 规则扫描文件
③ 加载 conftest 每进入一层目录，自动 import 该层的 conftest.py
④ 执行(run)     按 marker 筛选后，逐个跑
```

**⭐ 关键认知：② 和 ④ 是两个独立阶段。**

很多新手的困惑「为什么我的测试没跑」，答案几乎都在 ②：文件名不叫 `test_*.py`、
函数名不叫 `test_*`、或者被 marker 筛掉了。这时 pytest 的输出是
`0 items collected` 而不是报错 —— **它不认为「没找到测试」是错误**。

```bash
# 排查收集阶段的专用命令：只收集不执行
pytest --collect-only -q
```

📌 这条命令在本项目 Day 2 用了无数次。**任何「测试行为不符合预期」的排查，
第一步都是它** —— 先确认 pytest 到底看见了什么。

### 📖 企业级扩展：CI 里最阴的一类事故

`pytest tests/kinematics` 指向一个**空目录**时，pytest 退出码是 **5**（`NO_TESTS_COLLECTED`），
不是 0 也不是 1。但很多 CI 脚本只判断 `if [ $? -ne 0 ]`，于是：

| 情况 | 退出码 | 幼稚脚本的判断 |
|---|---|---|
| 122 个测试全过 | 0 | ✅ 绿 |
| 目录写错，0 个测试 | 5 | ❌ 红（还算走运） |
| 目录写错 + `--exitfirst` 等参数吞掉 | 0 | ✅ **绿灯，但什么都没测** |

本项目 `ci.yml:121` 那条 `⚠️ 不要写 tests/kinematics` 的注释，防的就是这个。
成熟团队的做法是**断言用例数下界**：

```bash
pytest tests/ -q | tee out.txt
grep -qE "[0-9]{3,} passed" out.txt || { echo "用例数异常偏少"; exit 1; }
```

Day 13-14 的「结构化结果契约」正是把这套 `grep` 判定升级掉的产物。

---

## 1.2 fixture 是什么：依赖注入，不是全局变量

```python
@pytest.fixture
def repo_root():
    return Path(__file__).resolve().parent.parent

def test_something(repo_root):      # ← 名字对上，pytest 自动传进来
    assert (repo_root / "discoverse").is_dir()
```

**机制**：pytest 看到测试函数的参数名，去 conftest 和当前文件里找同名 fixture，
调用它，把返回值塞进去。这就是**依赖注入（DI）**。

和普通的 `setUp()` 相比，fixture 的三个优势：

| | `setUp()`（unittest 风格） | fixture |
|---|---|---|
| 粒度 | 整个测试类共用一套 | 每个用例按需申请 |
| 组合 | 继承，多重继承会打架 | 参数列表，随意组合 |
| 作用域 | 只有 per-test | function/class/module/session 可选 |

📌 **最重要的性质：fixture 是懒加载的。** 没有任何用例申请它，它**永远不执行**。

这直接导致了一个坑 —— 见 [5.2](#52-为什么要给-fixture-写自检测试)。

---

## 1.3 fixture 的四种作用域

```python
@pytest.fixture(scope="function")   # 默认：每个用例新建一次
@pytest.fixture(scope="class")      # 每个测试类一次
@pytest.fixture(scope="module")     # 每个 .py 文件一次
@pytest.fixture(scope="session")    # 整个 pytest 进程一次
```

**⭐ 选择标准只有一条：这个对象是可变的吗？**

```
只读  → session（省时间，复用安全）
可变  → function（必须隔离，否则测试间污染）
```

本项目的实例（见 [第四部分](#第四部分conftestpy-逐行84-行)）：

| 对象 | 可变？ | 作用域 | 理由 |
|---|---|---|---|
| `repo_root` | ❌ 纯常量 | session | 算一次就够 |
| `MjModel` | ❌ 编译产物 | session | 编译一次数百 ms，复用安全 |
| `MjData` | ✅ 仿真状态 | function | 复用 = 状态泄漏 |

### 📖 企业级扩展：「单跑绿、全跑红」的标准诊断流程

这是测试间污染的经典症状。三条命令定位：

```bash
# ① 单独跑那个用例 —— 绿？那就是污染
pytest tests/unit/test_foo.py::test_bar -q

# ② 随机化执行顺序，看是否稳定复现（需 pytest-random-order）
pytest tests/ -p random_order --random-order-seed=12345

# ③ 二分定位污染源（需 pytest-bisect，或手工二分）
pytest tests/ --lf   # last-failed，先缩小范围
```

**根因永远是这三者之一**：模块级全局变量、`scope` 开太大的 fixture、
或者进程级单例（比如 `np.random` 的全局流 —— 这正是 Day 3 的主题）。

---

## 1.4 marker：给测试贴标签

```python
@pytest.mark.unit           # 贴标签
def test_fast_thing(): ...
```

```bash
pytest -m unit              # 只跑贴了 unit 的
pytest -m "not flake"       # 跑所有没贴 flake 的
pytest -m "unit or integration"
```

本项目定义了 5 个（`pyproject.toml:286-292`）：

| marker | 含义 | 典型耗时 |
|---|---|---|
| `unit` | 纯函数/配置层，无 MuJoCo | 毫秒 |
| `integration` | 要编译 MJCF 或跑仿真 | 百毫秒～秒 |
| `slow` | 单用例 >10s | —— |
| `determinism` | 确定性专项 | 秒 |
| `flake` | 采样实验，**默认不跑** | 分钟起 |

### ⚠️ `--strict-markers` 是必须的

不加它，**marker 打错字会静默生效**：

```python
@pytest.mark.unti          # 打错了
def test_x(): ...
```

- 不加 `--strict-markers`：pytest 默默创建一个叫 `unti` 的新 marker，
  这个用例从此**再也不会被 `-m unit` 选中**，而且没有任何提示。
- 加了：直接报错 `'unti' not found in markers configuration option`。

📌 **本项目 `addopts` 第一个参数就是它**（`pyproject.toml:297`）。

---

## 1.5 `conftest.py` 是什么

**一句话：pytest 的隐式插件文件，同目录及所有子目录的测试自动可见，无需 import。**

```
tests/
├── conftest.py              ← 全项目可见（repo_root, mj_model_factory…）
├── unit/
│   └── test_robot_config.py     ← 能用上面的 fixture
└── mobile_manipulation/
    ├── conftest.py          ← 只有本目录可见（MMK2 专用）
    └── test_mmk2_kinematics.py
```

**层级叠加**：`tests/mobile_manipulation/` 里的测试能同时看到两个 conftest 的 fixture。
同名时内层覆盖外层。

### 📖 企业级扩展：conftest 会变成「隐式全局变量的垃圾场」

大团队里 conftest 最常见的腐化路径：

```
第 1 个月：3 个 fixture，清爽
第 6 个月：40 个 fixture，其中 12 个没人用了但不敢删
第 1 年：  没人知道某个 fixture 被谁依赖，改一行炸 200 个用例
```

**防腐三条规则**（本项目已经在做前两条）：

1. **给 conftest 自身写测试** —— `test_conftest_fixtures.py` 就是干这个的（[5.2](#52-为什么要给-fixture-写自检测试)）
2. **就近原则** —— 只有 MMK2 用的 fixture 放 `mobile_manipulation/conftest.py`，不要往根上堆
3. 定期跑 `pytest --fixtures | grep -c fixture` 数一数，超过 ~30 个就该拆了

---

## 1.6 参数化：一个函数，N 个用例

```python
@pytest.mark.parametrize("robot_name", ROBOTS)   # ROBOTS 有 9 个
def test_robot_name_matches_filename(load_robot, robot_name):
    assert load_robot(robot_name).robot_name == robot_name
```

**这一个函数会生成 9 个独立用例**，报告里长这样：

```
test_robot_name_matches_filename[airbot_play] PASSED
test_robot_name_matches_filename[arx_l5]      PASSED
test_robot_name_matches_filename[iiwa14]      FAILED
...
```

### ⭐ 为什么不能用 for 循环

```python
# ❌ 循环：第一个失败就 raise，后面 8 个根本没跑
def test_all_robots(load_robot):
    for name in ROBOTS:
        assert load_robot(name).robot_name == name

# ✅ 参数化：9 个独立用例，失败的是哪几个一目了然
```

📌 **这个区别在本项目产生了直接价值**：缺陷 H（`qpos_dim` 不匹配）如果用循环写，
你只会知道「有个机器人不对」；用参数化才能一眼看出是
**arx_x5 / iiwa14 / piper / rm65 这 4 个**，而且差值分别是 1、6、1、2 ——
**差值的分布本身就是根因线索**（见 [6.3](#63-qpos_dim_root_cause-第-39-49-行)）。

---

## 1.7 xfail vs skip：不要混用

| | 含义 | 什么时候用 |
|---|---|---|
| `skip` | **不该跑** | 缺依赖、平台不支持、环境不具备 |
| `xfail` | **该跑，且预期失败** | 已知缺陷，代码本身有问题 |

```python
pytest.skip("MJCF 不存在")                    # 环境问题
pytest.xfail("缺陷 H：声明 qpos_dim=9，实际 15")  # 代码问题
```

### ⭐ `strict=True` 是精髓

```python
@pytest.mark.xfail(strict=True, reason="缺陷 X 未修")
```

| | 缺陷仍在 | 缺陷被修好了 |
|---|---|---|
| `strict=False`（默认） | XFAIL（绿） | XPASS（绿）← **静默** |
| `strict=True` | XFAIL（绿） | **FAILED（红）** ← 强制有人来撤标记 |

📌 **为什么这很重要**：`strict=True` 让「缺陷被修复」也是一个需要处理的事件。
否则三个月后没人知道那条 xfail 还成不成立，注释腐烂成谎言。

本项目用它钉死了缺陷 Y（`wheel_distance`）、贴图随机化等**暂不修复**的问题 ——
简历里那句「暂不修复的以 xfail(strict) 钉住，防止行为静默漂移」说的就是这个。

### 📖 企业级扩展：xfail 是「可执行的缺陷报告」

传统做法是缺陷进 Jira，代码里留个 `# TODO: JIRA-1234`。问题是：

- 注释**不会被执行**，缺陷修好了没人删它
- Jira 单和代码的对应关系靠人维护，必然腐烂

`xfail(strict=True)` 把缺陷登记**做成了 CI 的一部分**：

```
缺陷存在 → 每次 CI 都验证它「仍然存在」（XFAIL）
缺陷修复 → CI 立刻红（XPASS），强制清理
```

面试时这样讲：**「我把缺陷追踪从文档层下沉到了可执行层。」**

---

# 第二部分：`env.sh` 逐行（53 行）

📁 `scripts/dev/env.sh`

## 2.1 为什么需要这个文件（第 1-2 行）

```bash
# 用法: source scripts/dev/env.sh
# 目的: 建立一个与 ROS 解耦的、可复现的测试环境。
```

**⚠️ 注意是 `source` 不是 `bash`。**

```bash
bash scripts/dev/env.sh     # ❌ 起一个子进程，设完变量进程就死了，父 shell 什么都没变
source scripts/dev/env.sh   # ✅ 在当前 shell 里执行，变量留下来
.      scripts/dev/env.sh   # ✅ 同上，POSIX 简写
```

这是 Day 8-9 教程里记录过的一个真实的坑：

```bash
# ❌ 错的 —— 两条命令是两个独立进程
source scripts/dev/env.sh
$PY -m pytest tests/          # 新进程，$PY 是空的

# ✅ 对的 —— 用 && 串在同一条命令里
source scripts/dev/env.sh && $PY -m pytest tests/
```

---

## 2.2 解释器探测（第 4-23 行）

```bash
if [ -z "$PY" ]; then
    for _cand in \
        "$HOME/miniconda3/envs/discoverse/bin/python" \
        "$HOME/anaconda3/envs/discoverse/bin/python" \
        "$CONDA_PREFIX/bin/python" \
        "$(command -v python3)"
    do
        if [ -x "$_cand" ]; then
            export PY="$_cand"
            break
        fi
    done
    unset _cand
fi
```

**逐个拆**：

| 片段 | 含义 |
|---|---|
| `[ -z "$PY" ]` | `-z` = zero length。「如果 `$PY` 是空的」 |
| `"$PY"` 加引号 | **必须加**。不加的话 `$PY` 为空时表达式变成 `[ -z ]`，语法错 |
| `for _cand in \` | `\` 是续行符，把多行拼成一行 |
| `[ -x "$_cand" ]` | `-x` = executable。文件存在**且可执行** |
| `export PY=` | `export` 让子进程也能看到（`$PY -m pytest` 要用） |
| `break` | 找到第一个就停 —— 这就是「优先级」的实现 |
| `unset _cand` | 清理临时变量。因为是 `source`，不清理会污染用户 shell |

**⭐ 为什么第一个候选是 `$PY` 自己（即 `-z` 判断）**

这叫**「显式覆盖优先」**模式：

```bash
PY=/usr/bin/python3.11 source scripts/dev/env.sh   # 我就要用这个
```

CI 里非常有用 —— 脚本不用改，环境变量一设就换解释器。

**`command -v python3` 是什么**

```bash
command -v python3    # → /usr/bin/python3   （POSIX 标准，推荐）
which python3         # → /usr/bin/python3   （不是 POSIX，某些系统没有）
type -p python3       # → /usr/bin/python3   （bash 专用）
```

📌 写脚本一律用 `command -v`。

### 📖 企业级扩展：为什么不硬编码路径

原版是 `PY=/home/ubuntu22/miniconda3/envs/discoverse/bin/python`。
commit `d612bc4` 把它改成了探测式。**这不是洁癖，是三个具体的失效场景**：

| 场景 | 硬编码的后果 |
|---|---|
| 换台机器 | 路径不存在，`$PY` 指向一个不存在的文件，报错信息还很难懂 |
| 进 Docker | 容器里没有 `/home/ubuntu22`，直接崩 |
| 同事 clone | 他的用户名不是 ubuntu22 |

**通用原则：脚本里任何 `/home/<具体用户名>/` 都是 bug。**

---

## 2.3 渲染后端（第 30-32 行）

```bash
export MUJOCO_GL=osmesa
```

MuJoCo 有三种渲染后端，**选错的症状差别很大**：

| 后端 | 全称 | 需要 | 速度 | 选它的场景 |
|---|---|---|---|---|
| `glfw` | —— | **显示器** | 快 | 本地开发看画面 |
| `osmesa` | Off-Screen Mesa | 无 | **慢**（纯 CPU） | CI、无头服务器 |
| `egl` | —— | GPU + 驱动 | 快 | 有 GPU 的无头机（Day 12 用） |

**⚠️ 在无显示器环境用 glfw 的症状**：不是「渲染出黑图」，而是**进程直接崩**，
报错通常是 `GLFWError: X11: The DISPLAY environment variable is missing`。

---

## 2.4 ⭐ 清除 ROS 的 PYTHONPATH（第 34-48 行）—— 本文件的核心

```bash
if [ -n "$PYTHONPATH" ]; then
    unset PYTHONPATH
    _ros_cleared="yes"
else
    _ros_cleared="already clean"
fi
```

`[ -n "$X" ]`：`-n` = non-zero length，和 `-z` 相反。

**这五行是整个 Day 0-2 最值得讲的技术点。** 先讲清楚出了什么事。

### 事故链条

```
① 你装了 ROS Humble，~/.bashrc 里有 source /opt/ros/humble/setup.bash
② 那个脚本 export PYTHONPATH=/opt/ros/humble/lib/python3.10/site-packages:...
③ PYTHONPATH 的优先级【高于】conda 环境的 site-packages
④ ROS 的 launch_testing 包通过 entry_points 注册为 pytest11 插件
⑤ pytest 启动时【无条件】加载所有 pytest11 插件
⑥ launch_testing 需要 lark，但 lark 装在 ROS 环境不在 conda 环境
⑦ ModuleNotFoundError —— 而且是在 pytest 自己启动阶段，还没轮到你的测试
```

### ⚠️ 为什么不能用 `-p no:launch_testing` 打补丁

```bash
pytest -p no:launch_testing tests/     # ❌ 没用
```

注释第 41-42 行写得很清楚：

> 不能用 `pytest -p no:launch_testing` 打补丁 ——
> 那要求插件先被成功导入才能禁用，导入期就炸的话来不及。

**这是一个很好的通用认知：禁用机制本身依赖于「加载成功」这个前提。**
加载阶段就崩的东西，没法用「加载后禁用」去救。

同类问题还有第二种崩法（第 37-38 行）：

```
launch_testing_ros_pytest_entrypoint 注册了 pytest 9 已移除的 hook
→ PluginValidationError → INTERNALERROR
```

`INTERNALERROR` 是 pytest 自己崩了，不是你的测试失败 —— **看到这个词就该想到插件问题**。

### 📖 企业级扩展：PYTHONPATH 是一类系统性风险

`PYTHONPATH` 的问题不止 ROS。**任何往 `PYTHONPATH` 里塞东西的系统都有同样风险**：
Bazel、部分 CI 镜像、conda 的某些激活钩子、`sitecustomize.py`。

**Python 的模块搜索顺序**（`sys.path` 从前往后）：

```
1. 脚本所在目录（或 '' = cwd）
2. $PYTHONPATH            ← ROS 塞在这
3. 标准库
4. site-packages          ← conda 环境在这，排在后面！
```

📌 **conda 的「环境隔离」根本管不住 `PYTHONPATH`** —— 这是它的设计边界，不是 bug。

**成熟团队的三层防御**：

| 层 | 做法 | 本项目对应 |
|---|---|---|
| 环境层 | `unset PYTHONPATH` | `env.sh:44` |
| 容器层 | 根本不装 ROS | `Dockerfile.test`（Day 8-9） |
| **断言层** | **测试里断言 sys.path 干净** | `test_smoke.py::test_no_ros_pollution_in_syspath` |

第三层是很多团队漏掉的 —— 见 [5.1](#51-test_smokepy-逐行32-行)。

---

## 2.5 回显（第 50-53 行）

```bash
echo "[env] PY=$PY"
echo "[env] MUJOCO_GL=$MUJOCO_GL"
echo "[env] PYTHONPATH cleared (ROS decoupled): $_ros_cleared"
unset _ros_cleared
```

**为什么要 echo**：`source` 是静默执行的，不打印你根本不知道它干了什么、有没有生效。

📌 **通用原则：任何修改环境的脚本，都应该把「最终状态」打出来。**
CI 日志里这三行经常是排查问题的第一手线索。

---

# 第三部分：`pyproject.toml` 测试配置逐行

📁 `pyproject.toml:280-317`

## 3.1 为什么配置写在 pyproject.toml 而不是 pytest.ini

Day 2 教程 §2.2 的决策：**改上游配置，不要另建 `pytest.ini`。**

理由：pytest 的配置文件查找有优先级，**同时存在会静默取一个**：

```
pytest.ini  >  pyproject.toml  >  tox.ini  >  setup.cfg
```

如果你新建 `pytest.ini`，上游 `pyproject.toml` 里的配置**全部失效**，
而且没有任何警告。后来的人看到两个文件会彻底困惑。

---

## 3.2 收集规则（第 281-284 行）

```toml
testpaths = ["tests"]
python_files = "test_*.py"
python_classes = "Test*"
python_functions = "test_*"
```

| 键 | 作用 |
|---|---|
| `testpaths` | 不带参数敲 `pytest` 时的默认搜索目录 |
| `python_files` | 哪些文件算测试文件 |
| `python_classes` | 哪些类算测试类（**注意：不能有 `__init__` 方法**） |
| `python_functions` | 哪些函数算测试 |

**⚠️ `python_classes = "Test*"` 的陷阱**：一个叫 `TestConfig` 的**数据类**会被 pytest
当成测试类去收集，然后因为它有 `__init__` 而报 warning 并跳过。命名要避开。

---

## 3.3 marker 声明（第 286-292 行）

```toml
markers = [
    "unit: 纯函数/配置层单测，无 MuJoCo 依赖，秒级",
    "integration: 需要加载 MJCF 或跑仿真步进",
    "slow: 单用例 >10s，CI 主线跳过",
    "determinism: 确定性/可复现性专项",
    "flake: flake 率采样实验，非常规回归；需显式 -m flake 运行，单次数分钟起",
]
```

**⚠️ TOML 语法坑**（Day 2 §2.4 记录过）：

```toml
# ❌ INI 语法，在 TOML 里是语法错误
markers =
    unit: ...
    integration: ...

# ✅ TOML 必须是数组
markers = ["unit: ...", "integration: ..."]
```

冒号前是 marker 名，冒号后是描述（`pytest --markers` 会打印出来）。

---

## 3.4 ⭐ `addopts`（第 294-297 行）

```toml
# --strict-markers: marker 拼写错误直接报错，而非静默生成新 marker 吞掉用例筛选
# --tb=short:       traceback 只留一行源码，参数化批量失败时不刷屏
# -ra:              结尾汇总所有非通过用例（含 skip/xfail 的原因），不让缺失隐形
addopts = "--strict-markers --tb=short -ra -m 'not flake'"
```

`addopts` = **每次跑 pytest 都自动加上的参数**。逐个讲：

### `--strict-markers`
见 [1.4](#14-marker给测试贴标签)。

### `--tb=short`

traceback 的详细程度，五个档：

| 值 | 输出量 | 适用 |
|---|---|---|
| `--tb=long` | 完整栈 + 每帧局部变量 | 单个疑难 bug |
| `--tb=short`（本项目） | 每帧一行 | **参数化批量失败** |
| `--tb=line` | 每个失败一行 | 只想知道哪些红了 |
| `--tb=no` | 无 | 只看统计 |
| `--tb=native` | Python 原生格式 | 对接外部工具 |

📌 **为什么本项目选 short**：45 个参数化组合同时失败时，`long` 会输出几千行，
真正有用的信息被淹没。

### ⭐ `-ra`

`-r` 后面跟字符表示「汇总哪些类型」：

```
a = all except passed   （本项目用的）
f = failed    E = error    s = skipped
x = xfailed   X = xpassed  p = passed
```

**为什么这个参数很重要**：不加它，`skip` 和 `xfail` 只在统计行显示个数字：

```
113 passed, 4 skipped, 10 xfailed
```

**4 个 skip 是哪 4 个？为什么 skip？** 不知道。加了 `-ra`：

```
SKIPPED [1] tests/conftest.py:61: MJCF 不存在，跳过: /workspace/models/mjcf/xxx.xml
XFAIL tests/unit/test_robot_config.py::test_qpos_dim_matches_mjcf_nq[iiwa14]
  缺陷 H：iiwa14 声明 qpos_dim=9，MJCF nq=15。根因（Day 4 实测）：...
```

📌 **`-ra` 把「静默跳过」变成「可见的账」。**
Day 8-9 建 Docker 镜像时，`skip` 数从 4 变成 11 就是靠它发现的
（`.dockerignore` 排掉了 `models/`，MJCF 全部找不到 → 静默 skip → 测试还是绿的）。

**这条经验值得单独记住：绿灯有两种，「都过了」和「都没跑」。**

### `-m 'not flake'`

默认排除 flake 采样实验。因为它单次要跑几分钟，不该混进日常回归。
要跑必须显式 `-m flake` —— 见 [第八部分](#第八部分命令行逐字解析)。

---

## 3.5 超时（第 299-301 行）

```toml
# MuJoCo 仿真最常见的失败模式是死循环而非抛异常。
# 无超时则 CI 会挂到平台上限才被杀；有超时则变成一条明确的失败。
timeout = 60
```

**这个注释点破了一个关键认知：机器人仿真的失败模式和普通软件不一样。**

| 领域 | 典型失败 | 表现 |
|---|---|---|
| Web 后端 | 抛异常 | 立刻红，栈很清楚 |
| **机器人仿真** | **不收敛 / 死循环** | **挂住，什么都不打印** |

没有超时的话，GitHub Actions 会跑到 **6 小时**上限才杀掉，
日志里只有一句 `The job running on runner has exceeded the maximum execution time`。

### ⚠️ 已知问题：这个 timeout 和用例内的不一致

`docs/experiments/flake-2026-08-07.meta.yaml:27-30` 记录了：

> BUCKET3 的 12 例里至少 1 例是撞上 pytest 全局 timeout=60s
> 而非任务真超时 —— `pyproject.toml` 的 timeout 先于用例内的 `TIMEOUT_S=120` 生效，
> 导致归桶不准。

**这是一个真实的、诚实记录的测量误差**。面试时主动讲这种事，比讲「我的数据完美」可信得多。

---

## 3.6 ⭐ 覆盖率作用域（第 303-317 行）

```toml
# 覆盖率作用域：只统计正在测试的模块。
# 不要写 --cov=discoverse —— policies/ 下 237 个策略学习文件会把
# 分母稀释到 2-3%，数字失去指导意义。
[tool.coverage.run]
source = ["discoverse/universal_manipulation"]
omit = ["*/__pycache__/*", "*/tests/*"]
```

**这一段是简历里「覆盖率 5% → 94%」那个数字的定义所在**，必须讲清楚，
否则面试官问「94% 是什么的 94%」会答不上来。

### 分母决定一切

| 写法 | 分母 | 覆盖率 | 意义 |
|---|---|---|---|
| `--cov=discoverse` | 2584 行 | 28% | 含 policies/ 237 个策略文件，**没测也不打算测** |
| `source = universal_manipulation` | 967 行 | 41% | **正在测的模块** |
| 单看 `recorder.py` | —— | 19% → **94%** | 简历里那个数字 |

📌 **诚实的表述**：「**核心模块**单元测试覆盖率由 5% 提升至 94%」——
简历原文用的就是「核心模块」，这个限定词是准确的，不要在面试时说成「整个项目 94%」。

### 📖 企业级扩展：覆盖率的三个常见误用

1. **把覆盖率当质量指标** —— 100% 覆盖率的代码可以一个断言都没有：
   ```python
   def test_foo():
       foo()          # 跑过了，覆盖率 100%，但没验证任何东西
   ```
   **对策**：变异测试（mutation testing，`mutmut` / `cosmic-ray`）——
   故意改坏代码，看测试红不红。Day 4 的「变异验证」就是手工做这件事
   （见 Day 3-5 补充的 IK 那节）。

2. **对分母做手脚** —— 把没测的文件加进 `omit`，数字立刻好看。
   **对策**：`omit` 的每一条都要有注释说明理由。

3. **分支覆盖 vs 行覆盖**：
   ```toml
   [tool.coverage.run]
   branch = true    # 本项目没开，可以作为改进项讲
   ```
   行覆盖只问「这行跑过吗」，分支覆盖问「`if` 的两个分支都走过吗」。

### `exclude_lines`（第 313-317 行）

```toml
exclude_lines = [
    "pragma: no cover",
    "if __name__ == .__main__.:",
    "raise NotImplementedError",
]
```

这三行**不计入分母**。注意 `if __name__ == .__main__.:` 里的 `.` 是**正则的任意字符**
（匹配引号，避免转义地狱），不是打错字。

---

# 第四部分：`conftest.py` 逐行（84 行）

📁 `tests/conftest.py`

## 4.1 文件头（第 1-6 行）

```python
"""
根级 fixture 定义。

conftest.py 是 pytest 的隐式插件文件：同目录及所有子目录的测试
自动可见这里定义的 fixture，无需 import。
"""
```

见 [1.5](#15-conftestpy-是什么)。

---

## 4.2 `repo_root`（第 16-23 行）

```python
@pytest.fixture(scope="session")
def repo_root() -> Path:
    """仓库根目录。

    用 __file__ 反推而非 os.getcwd()：
    cwd 取决于用户在哪敲的 pytest，__file__ 不会变。
    """
    return Path(__file__).resolve().parent.parent
```

**⭐ `__file__` vs `os.getcwd()` —— 这是个必须理解的区别**

```python
os.getcwd()    # 你在哪敲的命令
__file__       # 这个 .py 文件在哪
```

```bash
cd /home/ubuntu22/workspaces/airbot-play/DISCOVERSE && pytest    # cwd = 仓库根
cd tests && pytest                                              # cwd = tests/ ← 变了！
```

用 `getcwd()` 的话第二种情况下所有路径都错。**`__file__` 永远指向文件自己的位置。**

**`.resolve()` 干什么**：把相对路径、符号链接、`..` 全部展开成绝对真实路径。

```python
Path("tests/conftest.py").resolve()
# → /home/ubuntu22/workspaces/airbot-play/DISCOVERSE/tests/conftest.py
```

**两个 `.parent`**：

```
/…/DISCOVERSE/tests/conftest.py    ← __file__
/…/DISCOVERSE/tests                ← .parent
/…/DISCOVERSE                      ← .parent.parent  ✅
```

---

## 4.3 配置目录 fixture（第 26-33 行）

```python
@pytest.fixture(scope="session")
def robot_config_dir(repo_root) -> Path:
    return repo_root / "discoverse" / "configs" / "robots"
```

**⭐ 注意 fixture 可以依赖 fixture** —— `robot_config_dir` 的参数就是 `repo_root`。
pytest 会自动解析这条依赖链。

**`/` 运算符**：`pathlib.Path` 重载了它做路径拼接。

```python
repo_root / "discoverse" / "configs"        # ✅ 跨平台，Windows 上自动变 \
repo_root + "/discoverse/configs"           # ❌ Path 不支持 +
os.path.join(repo_root, "discoverse")       # ✅ 老写法，也对但啰嗦
```

---

## 4.4 ⭐ `mj_model_factory`（第 39-65 行）—— 本文件最重要的设计

```python
@pytest.fixture(scope="session")
def mj_model_factory():
    import mujoco
    cache = {}

    def _make(xml_path):
        key = str(xml_path)
        if key not in cache:
            if not os.path.exists(key):
                pytest.skip(f"MJCF 不存在，跳过: {key}")
            cache[key] = mujoco.MjModel.from_xml_path(key)
        return cache[key]

    return _make
```

这里有**三个独立的设计决策**，逐个讲。

### 决策一：为什么 `scope="session"`

```
MjModel.from_xml_path 要解析 XML、加载 mesh/贴图、编译碰撞几何，
单次可达数百 ms 到数秒。它是 *只读* 的编译产物，跨用例复用安全。
```

`test_robot_config.py` 有 9 个机器人 × 2 个 integration 测试 = 18 次调用。
不缓存的话是 18 次编译，缓存后是 9 次。

### ⭐ 决策二：为什么返回**工厂函数**而不是模型本身

这是 **"factory as fixture"** 模式，值得单独理解。

```python
# ❌ 直接返回模型：一个 fixture 只能绑一个 XML
@pytest.fixture(scope="session")
def mj_model():
    return mujoco.MjModel.from_xml_path("robot_airbot_play.xml")
# 那 9 个机器人怎么办？写 9 个 fixture？

# ✅ 返回工厂：一个 fixture 服务任意 XML
def test_x(mj_model_factory):
    model = mj_model_factory("robot_panda.xml")
```

**通用规律：当 fixture 需要「参数」时，就返回一个函数。**

### 决策三：`import mujoco` 为什么在函数体内

```python
def mj_model_factory():
    import mujoco        # ← 不在文件顶部
```

**延迟导入（lazy import）**。理由：`conftest.py` 在 pytest 启动时**一定会被导入**，
如果在顶部 `import mujoco`，那么：

- 没装 mujoco 的环境下，**连 `pytest --collect-only` 都跑不了**
- 纯 unit 测试（不需要 mujoco）也被拖累

放在函数体内，只有真正申请这个 fixture 的用例才会触发导入。

### ⚠️ `pytest.skip` 在 fixture 里的行为

```python
if not os.path.exists(key):
    pytest.skip(f"MJCF 不存在，跳过: {key}")
```

在 fixture 里调 `pytest.skip`，**申请这个 fixture 的用例会被标记为 skipped**，
而不是 error。

**但这正是 Day 8-9 那个坑的来源**（见 `.dockerignore` 第 9-11 行的警告）：

```
排除 models/ 的后果不是报错，是 pytest.skip 静默兜住 →
测试全绿但一个 MJCF 都没真正加载过。
```

📌 **所以 `-ra` 和「比对 skip 数」是配套的防御措施**。

---

## 4.5 `mj_data_factory`（第 68-84 行）

```python
@pytest.fixture(scope="function")
def mj_data_factory(mj_model_factory):
    import mujoco

    def _make(xml_path):
        model = mj_model_factory(xml_path)
        return model, mujoco.MjData(model)

    return _make
```

**注释把理由说透了**：

```
MjData 持有 qpos/qvel/ctrl/time 等 *可变* 仿真状态。
若跨用例复用，用例 A 步进 1000 步后的状态会泄漏给用例 B，
造成 "单跑绿、全跑红" 的经典测试间污染 —— 而且顺序一变就复现不了。
MjData 构造很便宜（只分配数组），没有复用的必要。
```

**注意返回的是 `(model, data)` 元组** —— 因为调用方通常两个都要，
而 `model` 已经在工厂内部拿到了，再让调用方申请一次 `mj_model_factory` 是浪费。

---

# 第五部分：冒烟与自检测试逐行

## 5.1 `test_smoke.py` 逐行（32 行）

📁 `tests/unit/test_smoke.py`

```python
@pytest.mark.unit
def test_framework_alive():
    assert 1 + 1 == 2
```

**看起来很蠢，但它有明确用途**：验证「pytest 能启动、能收集、能执行」这条链路本身。

📌 **什么时候它有价值**：CI 上一堆测试红了，你不知道是代码坏了还是环境坏了。
这条绿 → 框架没问题，是代码；这条红 → 环境问题，别去看代码。

### ⭐ `test_no_ros_pollution_in_syspath`（第 9-32 行）

```python
def test_no_ros_pollution_in_syspath():
    import sys
    ros_paths = [p for p in sys.path if "/opt/ros/" in p]
    assert not ros_paths, (
        f"ROS 路径混入 sys.path: {ros_paths}\n"
        f"修复: source scripts/dev/env.sh (内含 unset PYTHONPATH)"
    )
```

**这条测试是 [2.4](#24--清除-ros-的-pythonpath第-34-48-行-本文件的核心) 的第三层防御。**

docstring 里的分层非常清楚：

```
已实测的两种崩溃方式（均发生在 pytest 启动/收集阶段，早于本断言执行）：
  1. launch_testing 作为 pytest11 插件被加载 -> 缺 lark -> ModuleNotFoundError
  2. launch_testing_ros_pytest_entrypoint 注册了 pytest 9 已移除的 hook
     -> PluginValidationError -> INTERNALERROR

本断言守的是第三种、也是最隐蔽的一种：sys.path 被 .pth 文件、
sitecustomize 或运行时代码污染，pytest 能正常启动，但 import 会
静默取到错误版本的模块。这类污染没有断言就完全不可见。
```

**⭐ 这段话体现的思维方式值得学**：作者明确区分了

| | 症状 | 需要断言吗 |
|---|---|---|
| 崩法 1、2 | pytest **启动就崩** | ❌ 不需要 —— 它自己会喊 |
| **崩法 3** | **静默取到错版本的模块** | ✅ **必须断言 —— 否则完全不可见** |

**通用原则：写测试要防的是「静默的错」，不是「会自己喊的错」。**

### ⚠️ 断言的错误信息包含修复方法

```python
f"修复: source scripts/dev/env.sh (内含 unset PYTHONPATH)"
```

📌 **好的断言信息回答三个问题**：什么错了、错成什么样、怎么修。
半年后撞到这条的人（可能就是你自己）能立刻动手，不用去翻文档。

---

## 5.2 为什么要给 fixture 写自检测试

📁 `tests/unit/test_conftest_fixtures.py`

```python
"""conftest 中 fixture 的自检。

fixture 是懒加载的：没有用例请求它就永不执行。
本文件确保每个根级 fixture 至少被求值一次，
否则 conftest 里的错误会一直潜伏到某个真实用例第一次用到它。
"""
```

**这是 [1.2](#12-fixture-是什么依赖注入不是全局变量) 那个「懒加载」性质的直接后果。**

场景：你改了 `robot_config_dir` 的路径拼接，打错一个字母。
如果当天没有用例申请它，**CI 全绿**，问题潜伏到下周有人写新测试才爆。

### 逐个测试

```python
def test_repo_root_points_at_real_repo(repo_root):
    """repo_root 必须指向真正的仓库根，而非 tests/ 或 cwd。"""
    assert (repo_root / "discoverse").is_dir()
    assert (repo_root / "pyproject.toml").is_file()
```

**⭐ 断言的选择很讲究**：不是 `assert repo_root == "/home/..."`（硬编码，换机器就红），
而是**断言「这个目录里应该有什么」** —— 这叫**特征断言**，跨环境稳定。

```python
def test_robot_config_dir_has_nine_yamls(robot_config_dir):
    yamls = sorted(p.stem for p in robot_config_dir.glob("*.yaml"))
    assert len(yamls) == 9, f"预期 9 个，实际 {len(yamls)}: {yamls}"
```

**这条是故意写「脆」的**。docstring 说明了意图：

> 9 个机械臂配置，数量变化应被显式感知（新增机器人时这条会红，提醒你更新 ROBOTS 列表）。

📌 **这是一个重要的测试设计模式：「哨兵测试」**。
它不是在防 bug，是在**防止某个隐含前提悄悄失效**。
`test_robot_config.py` 里那个 `ROBOTS` 列表是手写的 9 个名字 ——
有人加了第 10 个机器人，那个列表不会自动更新，新机器人**永远不被测试**。
这条哨兵就是为了让这件事**必须被人注意到**。

### `test_mj_data_factory_isolates_state`（第 41-56 行）

```python
def test_mj_data_factory_isolates_state(mj_data_factory, repo_root):
    model_a, data_a = mj_data_factory(xml)
    model_b, data_b = mj_data_factory(xml)

    assert model_a is model_b, "model 应复用（只读）"
    assert data_a is not data_b, "data 必须独立（可变），否则测试间状态污染"

    # 证明状态确实隔离：改 a 不影响 b
    data_a.qpos[0] = 0.5
    assert data_b.qpos[0] != 0.5
```

**⭐ `is` vs `==` 在这里是核心**：

```python
a is b     # 同一个对象（内存地址相同）
a == b     # 值相等
```

这条测试要验证的恰恰是**对象身份**，不是值：
- `model_a is model_b` → 缓存生效了
- `data_a is not data_b` → 隔离生效了

**最后两行是「行为验证」而非「结构验证」**：光断言 `is not` 还不够，
万一 `MjData` 内部共享了 numpy 数组呢？改一个看另一个变不变，才是真的证明。

📌 **这个模式叫「先证明结构，再证明行为」**，比只做其中一半可靠得多。

---

# 第六部分：`test_robot_config.py` 逐行（241 行）

📁 `tests/unit/test_robot_config.py`

## 6.1 三层架构（第 1-7 行）

```python
"""9 个机械臂配置的契约测试。

分三层：
  1. 配置文件自身的字段完整性与自洽性（不加载 MuJoCo，unit）
  2. 配置与 MJCF 的一致性（需编译 XML，integration）
  3. 已知缺陷的 xfail 记录（可执行的缺陷报告）
"""
```

**⭐ 这个分层是本文件最值得讲的结构设计。** 三层的判据完全不同：

| 层 | 问的问题 | 真理来源 | marker |
|---|---|---|---|
| 1 | 配置**自己**自洽吗 | 配置内部 | `unit` |
| 2 | 配置和**物理引擎**一致吗 | **MJCF 编译结果** | `integration` |
| 3 | 已知的不一致，钉住了吗 | 实测记录 | xfail |

**第 2 层的「真理来源」这句话很关键**（第 119-121 行）：

```
YAML 是人写的描述，MJCF 编译结果是物理引擎的事实。
不一致时 MJCF 是真相 —— IK 按 YAML 的维度切 qpos 数组，
维度错了就会静默取错关节。
```

📌 **面试可讲**：「我在测试里明确定义了『谁是真理来源』。
配置文件是人的意图，编译产物是机器的事实，两者冲突时以事实为准 ——
这决定了断言该往哪个方向写。」

---

## 6.2 `QPOS_DIM_MISMATCH`（第 25-33 行）

```python
# qpos_dim 与 MJCF 实际 nq 不符的机器人（实测 2026-07-30）
# 格式: robot -> (YAML 声明值, MJCF 实际值)
# 详见缺陷 H。修好配置后从这里删掉，测试会自动开始守护它。
QPOS_DIM_MISMATCH = {
    "arx_x5": (7, 8),
    "iiwa14": (9, 15),
    "piper": (7, 8),
    "rm65": (12, 14),
}
```

**⭐ 「修好配置后从这里删掉，测试会自动开始守护它」** —— 这句话描述了一个很优雅的机制：

```
缺陷登记表（这个 dict）
    ↓ 在表里 → xfail（已知，不阻塞）
    ↓ 不在表 → 正常断言（守护）
```

删掉一行 = 从「已知缺陷」升级为「受保护的契约」。**登记和守护是同一份数据驱动的。**

---

## 6.3 ⭐ `QPOS_DIM_ROOT_CAUSE`（第 35-49 行）

```python
# 缺陷 H 的根因（Day 4 实测，逐个 MJCF 遍历 jnt_type 得出）。
# 原 checkpoint 猜测「iiwa14 差 6 最可疑，可能有 FREE 关节占 7 个 qpos」——
# 实测【没有任何 FREE 关节】，4 个模型全是 HINGE + SLIDE。
# 真相是夹爪建模复杂度超出配置作者的假设。
QPOS_DIM_ROOT_CAUSE = {
    "arx_x5": "6 臂 HINGE + 2 夹爪 SLIDE(finger_joint1/2)=8；YAML 按 7 计",
    "piper": "6 臂 HINGE + 2 夹爪 SLIDE(finger_joint1/2)=8；YAML 按 7 计",
    "rm65": "6 臂 HINGE + 夹爪 6 HINGE + 2 SLIDE=14；YAML 按 12 计",
    "iiwa14": (
        "7 臂 HINGE + 夹爪 8 HINGE=15。夹爪是 Robotiq 式平行连杆机构，"
        "left/right 各 4 个 driver/coupler/spring_link/follower 关节，"
        "由约束耦合成 1 个物理自由度但各占 1 个 qpos。"
        "YAML 按『2 根手指』计数得 9，差 6"
    ),
}
```

**这段是整个 Day 0-2 最有面试价值的内容，因为它记录了一次「猜测被实测推翻」。**

### 猜测 vs 实测

| | 内容 |
|---|---|
| **原猜测** | iiwa14 差 6，可能有 FREE 关节（FREE 占 7 个 qpos） |
| **实测方法** | 遍历 MJCF 的 `jnt_type` |
| **实测结果** | **零个 FREE 关节**，全是 HINGE + SLIDE |
| **真相** | 夹爪建模复杂度超出配置作者假设 |

**怎么实测的**（可复现命令）：

```bash
source scripts/dev/env.sh && $PY -c "
import mujoco, collections
m = mujoco.MjModel.from_xml_path('models/mjcf/manipulator/robot_iiwa14.xml')
print('nq =', m.nq)
for i in range(m.njnt):
    name = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, i)
    print(f'{i:2d}  {mujoco.mjtJoint(m.jnt_type[i]).name:12s}  {name}')
"
```

`jnt_type` 的四个取值和它们占的 qpos 数：

| 类型 | qpos 占位 | qvel 占位 | 说明 |
|---|---|---|---|
| `mjJNT_FREE` | **7** | 6 | 自由体（3 位置 + 4 四元数） |
| `mjJNT_BALL` | 4 | 3 | 球关节（四元数） |
| `mjJNT_SLIDE` | 1 | 1 | 滑动 |
| `mjJNT_HINGE` | 1 | 1 | 转动 |

📌 **原猜测为什么合理但错了**：iiwa14 差 6，而 FREE 关节占 7 —— 数字很接近，
「7 - 1 = 6」很容易脑补成一个解释。**但接近不等于正确。**
真相是 Robotiq 夹爪的平行连杆机构：每侧 4 个关节（driver / coupler / spring_link / follower），
被约束耦合成 1 个物理自由度，**但各占 1 个 qpos**。

### 📖 企业级扩展：「差值的分布」是根因线索

四个机器人的差值：`+1, +6, +1, +2`。

如果全是 `+7`，那 FREE 关节假设就成立了。**差值不一致，说明根因不是单一机制** ——
这个推理方向本身值得在面试时讲。

**这就是 [1.6](#16-参数化一个函数n-个用例) 说的「参数化的额外价值」**：
循环只会告诉你「有问题」，参数化给你的是**分布**，而分布是可以用来推理的。

---

## 6.4 ⚠️ 待决策注释（第 51-54 行）

```python
# ⚠️ 待决策：qpos_dim 的语义未定义 —— 指模型 nq（15），
# 还是可控自由度（7 臂 + 1 夹爪 = 8）？
# iiwa14 那 8 根连杆是被约束绑定的从动关节，算 1 个还是 8 个取决于定义。
# 在语义有共识之前不改数字 —— 否则只是把一个错误换成另一个错误。
```

**⭐ 「在语义有共识之前不改数字」是一个很成熟的判断。**

新手看到「YAML 写 9，实际 15」的第一反应是把 9 改成 15。但：

- 如果 `qpos_dim` 的语义是「模型总 nq」→ 应该是 15
- 如果语义是「可控自由度」→ 应该是 8
- **两个都不是 9，但改成哪个取决于谁在用它、怎么用**

不搞清楚就改，只是**把一个已知错误换成一个未知错误**，而且丢掉了 xfail 的记录。

📌 **面试可讲**：「我发现了 4 个配置不一致，但没有全改 ——
其中一个的语义本身是模糊的，改数字前需要先定义语义。
我把它 xfail 钉住并写下了两种可能的解释，留给有上下文的人决策。」

**这比「我修了 4 个 bug」更能体现工程判断力。**

---

## 6.5 `load_robot` fixture（第 57-67 行）

```python
@pytest.fixture(scope="session")
def load_robot(robot_config_dir):
    """按名字加载机器人配置，会话级缓存（YAML 解析结果只读）。"""
    cache = {}

    def _load(name):
        if name not in cache:
            cache[name] = RobotConfigLoader(str(robot_config_dir / f"{name}.yaml"))
        return cache[name]

    return _load
```

又一个 **factory-as-fixture + 缓存**（同 [4.4](#44--mj_model_factory第-39-65-行-本文件最重要的设计)）。
`scope="session"` 的理由写在括号里：**YAML 解析结果只读**。

---

## 6.6 第 1 层测试（第 75-113 行）

```python
@pytest.mark.unit
@pytest.mark.parametrize("robot_name", ROBOTS)
def test_joint_count_matches_names_length(load_robot, robot_name):
    """整数计数必须等于名字列表长度。

    绕开缺陷 E 的命名争议，直接断言两个字段互相自洽。
    """
    loader = load_robot(robot_name)
    assert loader.arm_joints_count == len(loader.arm_joint_names)
```

**⭐ 「绕开命名争议，断言互相自洽」是一个实用技巧。**

缺陷 E 是命名混乱（见 [6.8](#68-第-3-层缺陷-e第-170-187-行)）：不知道该叫什么才对。
但**不管叫什么，「计数」和「名字列表长度」必须相等** —— 这个断言不依赖命名问题的答案。

📌 **通用原则：找到那些「无论争议怎么解决都必须成立」的不变量，先把它们钉住。**

### `test_ctrl_dim_covers_arm_and_gripper`（第 93-105 行）

```python
loader = load_robot(robot_name)
expected = loader.arm_joints_count + loader.gripper["ctrl_dim"]
assert loader.ctrl_dim == expected, (
    f"{robot_name}: ctrl_dim={loader.ctrl_dim} "
    f"!= arm({loader.arm_joints_count}) + gripper({loader.gripper['ctrl_dim']})"
)
```

docstring：「已实测 9/9 成立（6+1=7 与 7+1=8 两种情况都覆盖）」。

**注意断言信息把三个数都打出来了** —— 失败时你立刻知道是哪一项不对，不用再去查。

---

## 6.7 ⭐ 第 2 层：会炸的字段 vs 不会炸的字段（第 125-167 行）

这两个测试放在一起看，是**本文件最深刻的观察**。

```python
def test_ctrl_dim_matches_mjcf_nu(...):
    """ctrl_dim 必须等于 MJCF 编译出的执行器数 nu。

    这一维度维护得好（9/9 通过），因为写错会立刻炸：
    data.ctrl[:] = 长度不符的数组 -> ValueError。
    """

def test_qpos_dim_matches_mjcf_nq(...):
    """qpos_dim 必须等于 MJCF 编译出的 nq。

    缺陷 H：4/9 不符（arx_x5, iiwa14, piper, rm65）。

    这类错误不抛异常 —— qpos[:9] 在 nq=15 的模型上完全合法，
    只是静默丢掉后 6 个关节。IK 拿到残缺状态却照样算出"看起来合理"
    的解，机器人动到错误位置，全程无报错。

    对比 ctrl_dim（9/9 通过）：会炸的字段维护得好，
    不会炸的字段积累错误。
    """
```

### ⭐⭐ 「会炸的字段维护得好，不会炸的字段积累错误」

**这一句是整个 Day 0-2 最值得写进简历/面试的洞察。**

| 字段 | 写错的后果 | 实测正确率 |
|---|---|---|
| `ctrl_dim` | `data.ctrl[:] = arr` → **ValueError，立刻炸** | **9/9 ✅** |
| `qpos_dim` | `qpos[:9]` 在 nq=15 上**完全合法** → 静默丢 6 个关节 | **4/9 ❌** |

**为什么会这样**：Python 的切片不越界报错。

```python
qpos = np.zeros(15)
qpos[:9]           # ✅ 完全合法，返回前 9 个
qpos[:20]          # ✅ 也合法！返回全部 15 个，不报错
```

📌 **推论（这是可以推广到任何项目的方法论）**：

> **系统里「不会自己报错的地方」，就是缺陷的聚集地。**
> 找 bug 应该优先去那些「写错了也不会崩」的字段、路径、配置。

这条推论在本项目反复被验证：
- 缺陷 J：`.get()` 取不到键 → 静默用默认值（Day 3）
- 缺陷 B：`camera_configs` 为空 → `for` 循环零次 → 采集完成但没录数据
- Day 8-9：`.dockerignore` 排掉 models/ → `pytest.skip` 静默兜住

**全部是同一个模式。**

### 📖 企业级扩展：把这条推论变成流程

```
代码走读时，对每个配置字段问：
    「如果这个值是错的，程序会崩吗？」
        会崩   → 低优先级（它自己会暴露）
        不会崩 → ⭐ 高优先级，写测试钉住
```

进一步，**在代码里主动制造「会崩」**：

```python
# ❌ 静默
radius = obj.get("collision_radius", 0.05)

# ✅ 缺失时明确失败（fail fast）
if "collision_radius" not in obj:
    raise KeyError(f"物体 {obj['name']} 未声明 collision_radius")
```

这叫 **fail fast** 原则 —— 把静默错误转化成响亮的错误。

---

## 6.8 第 3 层：缺陷 E（第 170-187 行）

```python
# ============================================================
# 第 3 层：缺陷 E —— 属性名与 YAML 键交叉错位
#   YAML  arm_joints (int)   <-> Python  arm_joints_count
#   YAML  arm_joint_names    <-> Python  arm_joints (list)
#
# 源码自身是自洽的（类型注解 List[str] 与 docstring 都正确），
# 问题在跨层命名冲突会诱导误用 —— 严重度定为「中，可维护性」，
# 而非功能缺陷。证据：计划文档 L350 的示例就被误导了。
# ============================================================
```

**交叉错位长这样**：

```
YAML 里 arm_joints        是【整数】
Python 里 arm_joints      是【名字列表】     ← 同名，不同类型！
Python 里 arm_joints_count 才是那个整数
```

于是任何人看到 `config.arm_joints` 都会以为是数字（因为 YAML 里是数字），
实际拿到 list。

**⭐ 严重度定级的推理很讲究**：

> 源码自身是自洽的（类型注解与 docstring 都正确），
> 问题在跨层命名冲突会**诱导误用** —— 严重度定为「中，可维护性」，而非功能缺陷。
> **证据：计划文档 L350 的示例就被误导了。**

📌 **「有人已经被它坑了」是最硬的严重度证据。** 不是「我觉得这样不好」，
而是「这里有一个真实的误用案例」。

```python
def test_arm_joints_current_behavior_returns_names(load_robot, robot_name):
    """钉死【当前】行为：arm_joints 返回名字列表，而非计数。"""
```

**注意「钉死【当前】行为」的措辞** —— 这不是在说「这样是对的」，
而是「不管对不对，**先记录下来**，改动必须是有意识的」。这类测试叫
**characterization test（表征测试）**，是遗留系统改造的标准手法。

---

## 6.9 错误处理测试（第 195-212 行）

```python
def test_missing_file_raises_filenotfound(robot_config_dir):
    """缺文件必须是明确的 FileNotFoundError，不能是 None 或空配置。"""
    with pytest.raises(FileNotFoundError):
        RobotConfigLoader(str(robot_config_dir / "no_such_robot.yaml"))
```

**`pytest.raises` 的语义**：这段代码**必须**抛出这个异常，不抛就是测试失败。

```python
with pytest.raises(FileNotFoundError):
    do_something()          # 抛了 → 通过；没抛 → FAILED: DID NOT RAISE
```

**⭐ 为什么这条测试有价值**：「缺文件返回 None」是很常见的偷懒实现，
后果是错误延迟到很远的地方才暴露（`AttributeError: 'NoneType' has no attribute 'robot_name'`），
栈里根本看不出是文件缺失。

```python
def test_missing_required_field_raises(tmp_path):
    """缺必填字段必须在加载期报错（快速失败），而不是拖到运行时。

    tmp_path 是 pytest 内置 fixture：每个用例独立的临时目录，自动清理。
    写"坏配置"测试时用它，不要污染仓库。
    """
    bad = tmp_path / "broken.yaml"
    bad.write_text("robot_name: broken\n", encoding="utf-8")
    with pytest.raises((ValueError, KeyError)):
        RobotConfigLoader(str(bad))
```

**`tmp_path` 是 pytest 内置 fixture**，值得记住：

| fixture | 类型 | 作用域 |
|---|---|---|
| `tmp_path` | `pathlib.Path` | function（每个用例一个新目录） |
| `tmp_path_factory` | 工厂 | session |
| `capsys` | 捕获 stdout/stderr | function |
| `monkeypatch` | 临时改环境变量/属性，自动还原 | function |

**`pytest.raises((ValueError, KeyError))` 传元组** = 「这两个里任意一个都算过」。
用元组是因为实现可能抛哪个不确定，而测试关心的是「**有没有明确报错**」，
不是「报的是哪一种」。

---

## 6.10 MMK2 占位测试（第 220-241 行）

```python
def test_mmk2_mjcf_loads_with_expected_dof(mj_model_factory, repo_root):
    """MMK2 烟雾测试：模型能加载，且执行器数符合文档描述的 19 DOF。

    文档（CLAUDE.md）描述的 19 维动作空间：
        [0:2]   左右轮速度（差速驱动）
        ...
        [11:17] 右臂 6 轴
        [17:19] 左右夹爪

    只验证维度，不验证语义。目的是早期预警：
    若 MJCF 被改坏或文档与实际不符，现在就知道，
    而不是等到 Day 15-17 开工才踩坑。
    """
```

**⚠️ 注意 docstring 里抄的这个布局是【错的】** —— Day 15-17 实测发现
右臂是 `[12:18]` 不是 `[11:17]`，从第 11 位起整体错位一格。

**但这条测试当时是对的**，因为它**只断言 `model.nu == 19`，不断言布局**。

📌 **这体现了一个判断力**：Day 2 时还没有能力验证布局语义，
所以只钉住能验证的部分（维度），并在 docstring 里明确写「**只验证维度，不验证语义**」。

**没有验证的东西，就不要假装验证了。**

---

# 第七部分：`test_task_config.py` 关键段逐行

📁 `tests/unit/test_task_config.py`

## 7.1 ⭐ extends 继承机制（第 5-12 行）

```python
"""5 个任务配置的契约测试。

关键背景：任务配置有 extends 继承机制（config_utils.py:17）。
  place_block / place_coffeecup / place_kiwi_fruit
      -> extends templates/place_object.yaml
  cover_cup / stack_block
      -> 无继承

因此判断"配置有什么"必须用加载器加载后再看，
直接读单个 YAML 文件会得到错误结论。
"""
```

**⭐⭐ 「静态读文件 ≠ 运行时加载」是 Day 2 方法论第 7 条，全项目反复引用。**

```python
# ❌ 错的：只看到子配置自己写了什么
import yaml
cfg = yaml.safe_load(open("place_block.yaml"))
print(cfg.get("runtime_parameters"))     # → None（其实继承了！）

# ✅ 对的：走加载器，拿最终合并结果
cfg = TaskConfigLoader("place_block.yaml")
print(cfg.config["runtime_parameters"])  # → {'source_object': ...}
```

📌 **这条方法论在 Day 3 又救了一次**（`test_randomization_config.py:96-98` 直接引用它）。

### 📖 企业级扩展：配置继承是缺陷的高发区

任何有继承/覆盖/合并的配置系统（Spring 的 profile、K8s 的 kustomize、
Helm 的 values 覆盖、webpack 的 merge）都有同一类问题：

```
「我明明配了 X，为什么没生效」
    → 被上层覆盖了 / 合并策略不是你以为的那种（深合并 vs 浅合并）
```

**排查的第一步永远是：把最终合并结果 dump 出来。**

```bash
kubectl kustomize .                     # K8s
helm template . -f values.yaml          # Helm
$PY -c "from ...task_config import TaskConfigLoader; \
        import json; print(json.dumps(TaskConfigLoader('x.yaml').config, indent=2))"
```

**缺陷 B 就是这么找到的** —— 见 [7.3](#73--缺陷-b修一处还是四处)。

---

## 7.2 `_minimal_config` 辅助函数（第 42-59 行）

```python
def _minimal_config(**overrides):
    """构造能通过 _validate_config 的最小合法任务配置。

    实测必填项（task_config.py:_validate_config）：
        task_name, description
        states 或 task_states 之一，必须是非空 list
        每个 state 必须有 name 和 primitive

    注意 observation 不在必填清单里 —— 这正是缺陷 B 能存在的原因：
    校验函数存在，但未覆盖这个影响数据产出的关键字段。
    """
    cfg = {
        "task_name": "t",
        "description": "d",
        "states": [{"name": "s0", "primitive": "move"}],
    }
    cfg.update(overrides)
    return cfg
```

**`**overrides` 语法**：把关键字参数收集成 dict。

```python
_minimal_config()                          # 基础版
_minimal_config(task_name="custom")        # 改一个字段
_minimal_config(observation={"cameras": []})  # 加一个字段
```

**⭐ 这个模式叫 Object Mother / Test Data Builder**，用来避免每个测试
都重复写一遍完整的配置字典。

### ⭐ 最后那句注释才是重点

> **注意 observation 不在必填清单里 —— 这正是缺陷 B 能存在的原因：
> 校验函数存在，但未覆盖这个影响数据产出的关键字段。**

**「校验函数存在」≠「校验是充分的」。** 这又是 [6.7](#67--第-2-层会炸的字段-vs-不会炸的字段第-125-167-行)
那条推论的变体：有校验的字段维护得好，没被校验的字段积累错误。

---

## 7.3 ⭐ 缺陷 B：修一处还是四处

```python
# 缺陷 B：camera_configs 为空的任务（实测）
#   根因有两种：
#     templates/place_object.yaml 缺 observation 段 -> 3 个继承者受害
#     stack_block 自己漏写
#   修复：改 1 个模板 + 1 个任务文件，而非 4 个任务各补一遍
MISSING_OBSERVATION = [
    "place_block", "place_coffeecup", "place_kiwi_fruit", "stack_block",
]
```

**⭐ 「改 1 个模板 + 1 个任务文件，而非 4 个任务各补一遍」是根因分析的直接产出。**

```
表象：4 个任务都缺 observation
    ↓ 如果不做根因分析
    改 4 个文件（治标，模板还是坏的，下个继承者继续中招）
    ↓ 做了根因分析
    3 个是模板的锅 + 1 个是自己漏写 → 改 2 个文件（治本）
```

📌 **面试可讲**：「同一个表象有两个不同根因，修复方式也不同。
如果按表象修，会在模板里留下地雷，下一个继承模板的任务还会中招。」

### 缺陷 B 的严重度（第 113-120 行）

```python
# camera_configs 是数据采集时遍历相机的依据。
# 空列表意味着 for 循环一次都不执行 —— 采集流程正常跑完、
# 正常退出，一张图都没录，全程无报错。
# 具身智能项目里数据集就是产品，故严重度【高】。
```

**⭐ 「具身智能项目里数据集就是产品」这句定级理由很有说服力。**

同样是「for 循环零次」，在不同项目里严重度完全不同：

| 场景 | 后果 | 严重度 |
|---|---|---|
| 日志系统少记一条 | 少条日志 | 低 |
| **具身智能数据采集** | **产出物是空的，但流程显示成功** | **高** |

**定级要基于业务影响，不是技术表象。**

---

## 7.4 extends 生效验证（第 99-110 行）

```python
def test_extends_actually_merged_template(load_task, task_name):
    """extends 必须真的把模板内容合并进来。

    验证方式：模板独有的 runtime_parameters 键必须出现在最终配置里。
    若 extends 是死配置（写了不读），这条会红。
    """
    cfg = load_task(task_name).config
    assert "extends" not in cfg, "合并后 extends 指令本身不应保留"
    rp = cfg.get("runtime_parameters", {})
    assert "source_object" in rp, f"{task_name} 未继承到模板的 runtime_parameters"
```

**两个断言各守一件事**：

1. `"extends" not in cfg` —— 指令**被消费掉了**（不是原样留着）
2. `"source_object" in rp` —— 模板内容**真的进来了**

**⭐ 「若 extends 是死配置（写了不读），这条会红」** ——
这是在防一类特定的缺陷：**配置项存在但没有任何代码读它**。

📌 这类缺陷在本项目出现过至少两次：
- `settings.seed` 声明于 6 处 YAML，**零个读取者**（缺陷，Day 3 修）
- `templates/randomization.yaml` 的 `min_distance`，**没有任何任务继承它**（Day 3 发现）

**排查方法很简单**：

```bash
# 配置里声明了这个键，代码里有人读吗？
grep -rn "seed" discoverse/configs/ | wc -l        # 6 处声明
grep -rn "\.get(.seed.\|\[.seed.\]" discoverse/    # 0 处读取  ← 死配置！
```

---

# 第八部分：命令行逐字解析

## 8.1 环境准备

```bash
source scripts/dev/env.sh && $PY -m pytest tests/ -q
```

| 片段 | 含义 |
|---|---|
| `source` | 在**当前** shell 执行（见 [2.1](#21-为什么需要这个文件第-1-2-行)） |
| `&&` | 前一条**成功**才执行后一条（`env.sh` 找不到解释器会 `return 1`） |
| `$PY` | `env.sh` 导出的解释器路径 |
| `-m pytest` | **用这个解释器的 pytest**，而不是 PATH 上的 |
| `-q` | quiet，每个用例一个字符而不是一行 |

### ⭐ `python -m pytest` vs 直接 `pytest`

**这个区别值得单独记**：

```bash
pytest tests/              # 用 PATH 上第一个 pytest，它绑定的解释器不一定是你想要的
$PY -m pytest tests/       # 明确用 $PY 这个解释器的 pytest
```

还有一个副作用差异：

| | `sys.path[0]` |
|---|---|
| `pytest` | pytest 自己算的 rootdir |
| `python -m pytest` | **当前工作目录**（多了这一条） |

📌 **本项目一律用 `-m` 形式**，因为环境里有 conda + 系统 python + 可能的 ROS python，
不明确指定就是碰运气。

---

## 8.2 pytest 常用组合

```bash
# 只收集不执行 —— 排查「测试没跑」的第一步
$PY -m pytest --collect-only -q

# 数一数收集到几个
$PY -m pytest --collect-only -q | tail -1

# 只跑 unit
$PY -m pytest tests/ -m unit -q

# 只跑某个文件
$PY -m pytest tests/unit/test_robot_config.py -v

# 只跑某个用例
$PY -m pytest tests/unit/test_robot_config.py::test_missing_file_raises_filenotfound

# ⭐ 只跑某个参数化实例（注意方括号要转义或加引号）
$PY -m pytest "tests/unit/test_robot_config.py::test_qpos_dim_matches_mjcf_nq[iiwa14]"

# 按名字模糊匹配
$PY -m pytest tests/ -k "qpos or ctrl" -v

# 上次失败的重跑
$PY -m pytest tests/ --lf

# 先跑上次失败的，再跑其他
$PY -m pytest tests/ --ff

# 第一个失败就停
$PY -m pytest tests/ -x

# 显示最慢的 10 个用例
$PY -m pytest tests/ --durations=10
```

**⚠️ `-k` 和 `-m` 的区别**：

```bash
-k "qpos"      # 按【测试名字】模糊匹配
-m unit        # 按【marker】筛选
```

---

## 8.3 marker 相关

```bash
# 看有哪些 marker（含描述）
$PY -m pytest --markers

# 跑 flake 实验（必须显式指定，因为 addopts 里默认排除了）
$PY -m pytest tests/integration/test_task_matrix.py -m flake --count=50 -n 8
```

**⚠️ `-m flake` 会覆盖 `addopts` 里的 `-m 'not flake'` 吗？**

**会。** 命令行参数优先于 `addopts`，同一个选项后出现的覆盖先出现的。
可以自己验证：

```bash
$PY -m pytest tests/ -m flake --collect-only -q | tail -3
# 应该看到 45 个用例（9 机器人 × 5 任务）而不是 0
```

---

## 8.4 覆盖率

```bash
# ⭐ --cov 不带参数：读 pyproject.toml 的 [tool.coverage.run] source
$PY -m pytest tests/ -q --cov --cov-report=term-missing

# ❌ 别这么写 —— 分母从 967 涨到 2584，数字对不上
$PY -m pytest tests/ -q --cov=discoverse

# 生成 HTML 报告
$PY -m pytest tests/ --cov --cov-report=html
xdg-open htmlcov/index.html
```

`--cov-report` 的几种：

| 值 | 输出 |
|---|---|
| `term` | 终端，只有百分比 |
| `term-missing` | 终端 + **哪些行没覆盖**（本项目用这个） |
| `html` | 可点击的网页报告 |
| `xml` | Cobertura 格式，给 CI 工具吃 |

📌 **`term-missing` 那列行号是最有用的** —— 它直接告诉你下一个测试该写什么。

---

## 8.5 侦查类命令（Day 1-2 大量使用）

```bash
# 看某个配置文件真实长什么样（不要凭文档猜字段名）
cat discoverse/configs/robots/airbot_play.yaml

# ⭐ 看【加载后】的最终配置（extends 已合并）
source scripts/dev/env.sh && $PY -c "
from discoverse.universal_manipulation.task_config import TaskConfigLoader
import json
print(json.dumps(TaskConfigLoader('discoverse/configs/tasks/place_block.yaml').config,
                 indent=2, ensure_ascii=False))
"

# 数一数某个目录有多少配置
ls discoverse/configs/robots/*.yaml | wc -l

# 找死配置：声明了但没人读的键
grep -rn "collision_radius" discoverse/configs/ | wc -l
grep -rn "collision_radius" discoverse/ --include="*.py"
```

**⭐ Day 2 §5.1 的原则：「先侦查，不要照抄文档的字段名」。**

本项目的 `CLAUDE.md` 里就有过时描述（MMK2 的执行器布局），
**文档是人写的，会腐烂；代码和配置文件是事实。**

---

# 第九部分：面试问答速查

> 下面每条都基于本文档已经讲过的实际代码，可以直接展开细节。

## Q1「你的测试框架是怎么搭的？」

**三层结构 + 一条方法论。**

```
第 1 层  配置自身自洽性       unit，毫秒级，无 MuJoCo 依赖
第 2 层  配置 vs MJCF 一致性  integration，需编译 XML
第 3 层  已知缺陷 xfail 登记   可执行的缺陷报告
```

方法论：**明确定义「谁是真理来源」**。YAML 是人的意图，MJCF 编译结果是物理引擎的事实，
冲突时以事实为准 —— 这决定了断言往哪个方向写。

---

## Q2「你怎么发现那些缺陷的？有方法论吗？」

**有，一条推论：「系统里不会自己报错的地方，就是缺陷的聚集地。」**

实证（[6.7](#67--第-2-层会炸的字段-vs-不会炸的字段第-125-167-行)）：

| 字段 | 写错会崩吗 | 实测正确率 |
|---|---|---|
| `ctrl_dim` | 会（ValueError） | 9/9 ✅ |
| `qpos_dim` | 不会（切片不越界） | 4/9 ❌ |

**同一个配置文件、同一批作者、同类字段，正确率差这么多，唯一的变量是「写错了会不会立刻暴露」。**

按这条推论去找，后面几个缺陷都在同一个模式上：
- 缺陷 J：`.get()` 取不到键 → 静默用默认值
- 缺陷 B：`camera_configs` 空 → for 循环零次 → 采集"成功"但没数据
- Day 8-9：`.dockerignore` 排掉 models/ → `pytest.skip` 静默兜住 → 测试全绿

---

## Q3「xfail 和直接注释掉测试有什么区别？」

**xfail(strict=True) 让「缺陷被修复」也成为一个必须被处理的事件。**

| | 缺陷仍在 | 缺陷被修好 |
|---|---|---|
| 注释掉 / TODO | 无感知 | **无感知，注释腐烂成谎言** |
| `xfail(strict=False)` | XFAIL 绿 | XPASS 绿，静默 |
| **`xfail(strict=True)`** | XFAIL 绿 | **FAILED 红，强制清理** |

**我把缺陷追踪从文档层下沉到了可执行层。**

---

## Q4「94% 覆盖率是怎么算的？」

**先说清楚分母**（这是加分点，说明你知道这个数字可以被操纵）：

| 分母范围 | 行数 | 覆盖率 |
|---|---|---|
| `--cov=discoverse` | 2584 | 28%（含 policies/ 237 个策略文件，不在测试范围） |
| `universal_manipulation` | 967 | 41% |
| **`recorder.py` 单文件** | —— | **19% → 94%** ← 简历里这个数字 |

简历原文是「**核心模块**覆盖率」，这个限定词是准确的。

**同时我知道覆盖率不等于质量** —— 100% 覆盖可以一个断言都没有。
所以 Day 4 做了手工变异验证：注释掉修复代码，看测试红不红。
**有一次红不了，说明测试没守住完整契约**（见 Day 3-5 补充的 IK 那节）。

---

## Q5「为什么 fixture 要分作用域？」

**判据只有一条：这个对象可变吗。**

```
只读 → session（MjModel 编译一次数百 ms，复用安全）
可变 → function（MjData 复用 = 状态泄漏）
```

**不隔离的后果是「单跑绿、全跑红」**，而且**顺序一变就复现不了** ——
这是最难查的一类 bug，因为它不稳定。

我在 `test_conftest_fixtures.py` 里专门写了一条测试证明隔离真的生效：
先断言对象身份（`data_a is not data_b`），再断言行为（改 a 不影响 b）。
**光断言身份不够，万一内部共享了 numpy 数组呢。**

---

## Q6「ROS 那个环境问题具体是什么？」

**三层崩法，我防了第三层**（前两层它自己会喊）：

```
1. launch_testing 作为 pytest11 插件被加载 → 缺 lark → ModuleNotFoundError
2. launch_testing_ros 注册了 pytest 9 已移除的 hook → INTERNALERROR
3. ⭐ sys.path 被污染，pytest 能启动，但 import 静默取到错版本的模块
```

**第三层没有断言就完全不可见**，所以我写了 `test_no_ros_pollution_in_syspath`。

顺带一个认知：**不能用 `pytest -p no:launch_testing` 打补丁** ——
那要求插件先被成功导入才能禁用，**导入期就崩的话来不及**。
禁用机制本身依赖「加载成功」这个前提。

---

## Q7「配置继承那块你踩过什么坑？」

**「静态读文件 ≠ 运行时加载」** —— 这是我总结的方法论第 7 条。

`place_block.yaml` 自己没写 `runtime_parameters`，但它 `extends` 了模板。
直接 `yaml.safe_load` 会得出「这个配置没有 X」的错误结论，
必须走加载器拿最终合并结果。

**缺陷 B 就是这么定位的**：4 个任务都缺 `observation`，但根因有两个 ——
3 个是模板缺失（继承受害），1 个是自己漏写。
**所以修复是改 2 个文件而不是 4 个** —— 按表象修会在模板里留地雷。

---

## 📖 附：可以主动抛出的三个「反思点」

面试时主动讲不完美的地方，可信度远高于「一切顺利」。

**① 一个待决策的缺陷我没有修**

`qpos_dim` 语义本身是模糊的（指模型 nq 还是可控自由度？）。
不搞清楚就改数字，只是把一个已知错误换成一个未知错误。
我 xfail 钉住 + 写下两种解释，留给有上下文的人决策。

**② 一个测量误差我如实记录了**

flake 实验里 BUCKET3 的 12 例，至少 1 例是撞上 `pyproject.toml` 的全局
`timeout=60` 而非用例内的 `TIMEOUT_S=120` —— **两个超时配置打架，导致归桶不准**。
写进了实验元数据的 `caveats`。

**③ 一个猜测被我自己的实测推翻了**

原本猜 iiwa14 差 6 是因为有 FREE 关节（占 7 个 qpos，7-1=6 很像）。
遍历 `jnt_type` 实测发现**零个 FREE 关节**，真相是 Robotiq 夹爪的平行连杆机构。
**数字接近不等于机制正确。**

---

## 相关文档

- [day00-setup.md](day00-setup.md) — Day 0 环境就绪
- [day01-am-architecture.md](day01-am-architecture.md) — Day 1 架构鸟瞰
- [day02-pytest-infra.md](day02-pytest-infra.md) — Day 2 pytest 骨架
- [day03-05-supplement-line-by-line.md](day03-05-supplement-line-by-line.md) — 确定性、IK、flake 逐行
- [day08-11-supplement-line-by-line.md](day08-11-supplement-line-by-line.md) — Docker 与 CI 逐行
- [../defect-report.md](../defect-report.md) — 完整缺陷清单
