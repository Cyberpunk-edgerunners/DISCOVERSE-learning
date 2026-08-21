# Day 15-17 补充 — 逐行解析：MMK2 专项测试的每一行代码与命令

> 配套 [day15-17-mmk2-mobile-manipulation.md](day15-17-mmk2-mobile-manipulation.md)
> 用途：**查阅型文档**，不用从头读。看不懂哪一行就跳到哪一节。
> 覆盖：`tests/mobile_manipulation/` 全部 915 行 + 度量脚本 123 行 + 全部命令行
> 面向：**没写过机器人测试、也不熟 MuJoCo 的读者**。每个概念从零讲起。

---

## 目录

- [第一部分：预备概念（9 个，不懂这些后面全是天书）](#第一部分预备概念9-个)
- [第二部分：命令行逐字解析](#第二部分命令行逐字解析)
- [第三部分：`conftest.py` 逐行（215 行）](#第三部分conftestpy-逐行215-行)
- [第四部分：`test_mmk2_kinematics.py` 逐行（200 行）](#第四部分test_mmk2_kinematicspy-逐行200-行)
- [第五部分：`test_differential_drive.py` 逐行（214 行）](#第五部分test_differential_drivepy-逐行214-行)
- [第六部分：`test_slide_lift.py` 逐行（134 行）](#第六部分test_slide_liftpy-逐行134-行)
- [第七部分：`test_dual_arm_collision.py` 逐行（152 行）](#第七部分test_dual_arm_collisionpy-逐行152-行)
- [第八部分：度量脚本逐行（123 行）](#第八部分度量脚本逐行123-行)

---

# 第一部分：预备概念（9 个）

## 1.1 MuJoCo 的两个核心对象：`MjModel` 和 `MjData`

这是全篇最重要的概念。**搞混这两个，后面每个 fixture 都看不懂。**

```python
model = mujoco.MjModel.from_xml_path("mmk2_floor.xml")   # 编译产物
data  = mujoco.MjData(model)                              # 运行时状态
```

打个比方：

| | 类比 | 内容 | 可变吗 |
|---|---|---|---|
| `MjModel` | **程序的可执行文件** | 有几个关节、每个关节的范围、连杆质量、几何形状 | ❌ 只读 |
| `MjData` | **进程的内存** | 此刻各关节在哪、速度多少、受什么力、仿真到第几秒 | ✅ 每步都变 |

**一个 `MjModel` 可以配多个 `MjData`** —— 就像一个 `.exe` 能同时开多个进程。

📌 **这直接决定了 fixture 的作用域**（见 [3.4](#34-mmk2_model-fixture45-53-行)）：
`MjModel` 只读 → 可以 `scope="session"` 全局共享；
`MjData` 可变 → 必须每个测试新建，否则上个测试把机器人开走了，下个测试从那开始。

### 一步仿真发生了什么

```python
data.ctrl[:] = some_action      # ① 你给控制指令
mujoco.mj_step(model, data)     # ② 物理引擎推进一个 timestep（本项目 0.002s）
print(data.qpos)                # ③ 读出新状态
```

`mj_step` 内部：算受力 → 解约束（接触、关节限位）→ 积分 → 更新 `qpos`/`qvel`。

---

## 1.2 `qpos` / `qvel` / `ctrl` 分别是什么

这三个数组是全篇出现频率最高的东西。

```python
data.qpos    # 广义坐标（generalized position）—— 每个关节「在哪」
data.qvel    # 广义速度 —— 每个关节「多快」
data.ctrl    # 控制输入 —— 你给执行器的指令
```

### ⚠️ 三者长度不一样，这是最容易错的地方

本项目 MMK2 实测：

```
nq = 28      len(data.qpos)  = 28
nv = 27      len(data.qvel)  = 27      ← 比 qpos 少 1
nu = 19      len(data.ctrl)  = 19      ← 又少 8
```

**为什么 `nq` 比 `nv` 多 1？**

因为底盘是「自由关节」（free joint），可以在空间里任意平移旋转：

| | 表示方法 | 占几个数 |
|---|---|---|
| 位置 | `(x, y, z)` | 3 |
| **姿态** | **四元数 `(w, x, y, z)`** | **4** |
| → `qpos` 合计 | | **7** |
| 线速度 | `(vx, vy, vz)` | 3 |
| **角速度** | **`(ωx, ωy, ωz)`** | **3** |
| → `qvel` 合计 | | **6** |

**四元数用 4 个数表示 3 个自由度**（多出来的那个被「模长必须为 1」这个约束吃掉了），
所以位置比速度多 1 个数。

📌 **结论：绝对不要用「第几个关节」去数 `qpos` 的下标。**
本项目的 MMK2：

```
qpos[0:3]   底盘 x, y, z
qpos[3:7]   底盘四元数 (w,x,y,z)
qpos[7]     左轮转角
qpos[8]     右轮转角
qpos[9]     ⭐ 升降 —— 计划文档误写成 qpos[2]（那是底盘 z！）
qpos[10:12] 头部 yaw, pitch
qpos[12:18] 左臂 6 轴
...
```

**正确做法**（见 [3.9](#39-qpos_adr95-104-行)）：按名字查下标。

**为什么 `nu` 只有 19？**
因为不是每个自由度都有电机驱动 —— 底盘的 6 个自由度是被轮子**间接**驱动的，
夹爪的两根手指由**一个** tendon（腱）执行器带动。

---

## 1.3 执行器类型：`<motor>` vs `<position>`

MJCF（MuJoCo 的模型格式）里，执行器有不同类型，**`ctrl` 的物理含义完全不同**：

```xml
<motor   name="lft_wheel_motor" joint="lft_wheel_joint"/>   <!-- ctrl = 力矩 N·m -->
<position name="lift" joint="slide_joint"/>                  <!-- ctrl = 目标位置 m -->
```

| 类型 | `ctrl` 的含义 | 行为 |
|---|---|---|
| `<motor>` | **力矩/力** | 施加恒定力矩 → 物体**持续加速**（直到阻力平衡） |
| `<position>` | **目标位置** | 内部有个比例控制器，把关节**拉向**目标 |

### ⭐ 为什么这个区分是今天的关键

计划文档写 `action[0] = 0.5  # 左轮速度` —— **「速度」两个字是错的**。

实测恒定 1.0 N·m 力矩下的轮速：

```
step    0  →  0.018 rad/s
step 1000  →  1.107 rad/s
step 2500  →  1.635 rad/s      ← 一直在涨，永远不恒定
```

📌 所以**不能**写「跑 100 步应该走 X 米」这种断言 ——
位移是时间的非线性函数。必须**读实际轮子转角来推算**。

### 📖 扩展：`<position>` 执行器为什么有稳态误差

`<position>` 内部是个比例控制器（P 控制器）：

```
输出力 = kp × (目标位置 - 当前位置)
```

升降轴要**对抗重力**。稳态时（不再运动），力必须平衡：

```
kp × 误差 = 重力负载
→ 误差 = 重力负载 / kp        ← 恒定，且不可能为 0
```

**这就是实测 6.06mm 稳态误差的来源** —— 不是缺陷，是 P 控制器的固有性质。
要消掉它需要积分项（PID 里的 I），MuJoCo 的 `<position>` 没有。

---

## 1.4 pytest 的 `fixture` 是什么

**fixture = 测试的「准备工作」，写一次，多个测试复用。**

不用 fixture 的写法（每个测试重复 4 行）：

```python
def test_a():
    model = mujoco.MjModel.from_xml_path(...)   # 重复
    data = mujoco.MjData(model)                  # 重复
    ...

def test_b():
    model = mujoco.MjModel.from_xml_path(...)   # 又重复
    data = mujoco.MjData(model)
    ...
```

用 fixture：

```python
@pytest.fixture
def mmk2_data(mmk2_model):        # ← 声明它需要 mmk2_model
    data = mujoco.MjData(mmk2_model)
    mujoco.mj_resetData(mmk2_model, data)
    return data                    # ← return 的东西会被送给测试

def test_a(mmk2_data):            # ← 参数名 = fixture 名，pytest 自动注入
    assert mmk2_data.qpos[9] == 0
```

**机制**：pytest 看到测试函数的参数名，去找同名的 fixture，
调用它，把返回值传进来。这叫**依赖注入**。

fixture 之间也能互相依赖（`mmk2_data` 依赖 `mmk2_model`），pytest 会自动排好顺序。

---

## 1.5 ⭐ fixture 的 `scope`：本文最关键的设计决策

```python
@pytest.fixture(scope="session")    # 整个测试会话只执行一次
@pytest.fixture(scope="module")     # 每个 .py 文件执行一次
@pytest.fixture                     # 默认 = "function"，每个测试函数执行一次
```

### 怎么选？只问一个问题

> **这个 fixture 返回的东西，有没有可能被测试改？**

| 对象 | 会被改吗 | scope | 理由 |
|---|---|---|---|
| `MjModel` | ❌ 只读 | `session` | 共享安全，省编译时间 |
| `MjData` | ✅ 每步都改 | `function`（默认） | 共享 = 灾难 |

### ⚠️ 如果 `MjData` 用了 `session` 会怎样

```python
# 假想的错误写法
@pytest.fixture(scope="session")
def mmk2_data(mmk2_model):
    return mujoco.MjData(mmk2_model)
```

```
test_straight_line     跑 4000 步，机器人开到了 (0.9, 0)
test_odometry_turning  从 (0.9, 0) 开始 —— 但它以为自己从 (0,0) 开始
→ 断言失败
→ 单独跑 test_odometry_turning 却是绿的
→ 「单跑绿、全跑红」，而且换个执行顺序就复现不了
```

📌 **这是测试领域最难查的一类 bug，叫「测试间污染」（test pollution）。**
避免它的成本极低（`MjData` 构造只要 0.0004 秒），没有任何理由去共享。

---

## 1.6 `pytest.mark` 标记与 `pytestmark`

```python
pytestmark = [pytest.mark.integration]     # 给整个文件的所有测试打标记
```

标记的用途：**筛选要跑哪些测试**。

```bash
pytest -m integration        # 只跑标记为 integration 的
pytest -m "not slow"         # 跳过慢的
```

本项目 `pyproject.toml` 定义了 5 个标记：

```toml
"unit: 纯函数/配置层单测，无 MuJoCo 依赖，秒级",
"integration: 需要加载 MJCF 或跑仿真步进",
"slow: 单用例 >10s，CI 主线跳过",
"determinism: 确定性/可复现性专项",
"flake: flake 率采样实验，非常规回归",
```

⚠️ **今天的 4 个模块全部标 `integration`** —— 因为都要加载 MJCF 并跑仿真。

⚠️ **`--strict-markers` 是开着的**，标记拼错会**直接报错**而不是静默创建一个新标记。
这是好事：`@pytest.mark.integraton`（少个 i）会当场炸，而不是让这个测试
在 `-m integration` 时被悄悄漏掉。

---

## 1.7 `@pytest.mark.parametrize`：一个函数变多个测试

```python
@pytest.mark.parametrize("slide", [0.0, 0.1, 0.3, 0.5, 0.87])
def test_roundtrip_across_slide_range(fk, ik, slide):
    ...
```

**这一个函数会变成 5 个独立测试**：

```
test_roundtrip_across_slide_range[0.0]
test_roundtrip_across_slide_range[0.1]
test_roundtrip_across_slide_range[0.3]
test_roundtrip_across_slide_range[0.5]
test_roundtrip_across_slide_range[0.87]
```

**好处**：一个失败不影响其他的继续跑，而且失败信息直接告诉你是哪个参数。

对比手写循环：

```python
def test_bad():
    for slide in [0.0, 0.1, 0.3, 0.5, 0.87]:
        assert roundtrip(slide) < 1e-3    # ← 第一个失败就停，后面 4 个不知道
```

📌 **这也是「初稿估 19 个用例、实际 34 个」的原因** ——
参数化让「测试函数数」和「用例数」脱钩。
**估工作量按函数数，估 CI 时长按展开后的用例数。**

---

## 1.8 `xfail`：把「已知缺陷」变成资产

```python
@pytest.mark.xfail(reason="缺陷 Y：...", strict=True)
def test_wheel_distance_constant_matches_model(...):
    assert MMK2Base.wheel_distance == pytest.approx(0.3265)
```

`xfail` = **expected failure**（预期失败）。

| 实际结果 | pytest 报告 | 含义 |
|---|---|---|
| 测试失败 | `xfailed` | ✅ 缺陷还在，符合预期，**不算 CI 失败** |
| 测试通过 | `XPASS` | ⚠️ 缺陷被修好了！ |

### ⭐ `strict=True` 是关键

```python
strict=True    # XPASS 会被判为【失败】
```

**为什么要这样？**

假设有人修好了 `wheel_distance`。如果 `strict=False`，测试变成 `xpass`，
CI 还是绿的，**没人知道这个 xfail 该删了**，它会永远留在代码里当噪声。

`strict=True` 则会红：「你修好了缺陷，请把这条 xfail 删掉」。

📌 **`xfail` 是「缺陷登记」的可执行形式** —— 比写在文档里的缺陷列表强，
因为它会在缺陷被修复时**主动提醒你**。

---

## 1.9 四元数与旋转矩阵：两种约定

三维旋转有多种表示法，今天用到两种：

| 表示 | 长什么样 | 谁在用 |
|---|---|---|
| **四元数** | 4 个数 | MuJoCo、`MMK2FK` 的返回值 |
| **旋转矩阵** | 3×3 = 9 个数 | `MMK2IK` 的输入参数 |

### ⚠️ 四元数的顺序有两种约定，而且互不兼容

```
MuJoCo / MMK2FK :  [w, x, y, z]      ← 实部在前
scipy           :  [x, y, z, w]      ← 实部在后
```

所以转换要**重排下标**：

```python
Rotation.from_quat(quat[[1, 2, 3, 0]])
#                       ↑  ↑  ↑  ↑
#                       x  y  z  w      从 wxyz 里按这个顺序取
```

📌 **写反了不会报错**，只会得到一个**合法但错误**的旋转。
然后 IK 要么解出完全不同的姿态，要么报「不可达」。

⭐ **这类错误只有往返测试（FK→IK→FK）能抓到** ——
单独看 FK 是对的，单独看 IK 也是对的，只有串起来才暴露。

---

# 第二部分：命令行逐字解析

## 2.1 主力命令拆解

```bash
env -u PYTHONPATH MUJOCO_GL=osmesa $PY -m pytest tests/ -q
```

逐段拆：

| 片段 | 作用 |
|---|---|
| `env` | 「在修改过的环境变量下运行某命令」 |
| `-u PYTHONPATH` | **u = unset**，删掉 `PYTHONPATH` 这个变量 |
| `MUJOCO_GL=osmesa` | 设一个环境变量（只对这条命令有效） |
| `$PY` | 之前定义的变量，展开成 conda 环境的 python 路径 |
| `-m pytest` | **以模块方式运行** pytest（见 2.4） |
| `tests/` | 只收集这个目录下的测试 |
| `-q` | quiet，少输出（一个字符一个测试） |

### 2.2 ⚠️ 为什么要 `-u PYTHONPATH`

如果你的 shell 里 source 过 ROS：

```bash
echo $PYTHONPATH
# /opt/ros/humble/lib/python3.10/site-packages:...
```

Python 会**优先**从 `PYTHONPATH` 列的目录找包。ROS 的目录里有一堆同名包，
于是 pytest 会加载到 ROS 的版本，报出莫名其妙的错：

```
ModuleNotFoundError: No module named 'lark'
```

`env -u PYTHONPATH` 把这个变量**临时删掉**（只对这条命令，不影响你的 shell）。

📖 **扩展：为什么不 `export PYTHONPATH=` 直接清空？**
可以，但那会污染你当前 shell 的后续所有命令。`env -u` 的作用域**只有这一条命令**，
更安全 —— 这是「最小作用域原则」。

### 2.3 `MUJOCO_GL` 的三个取值

MuJoCo 渲染需要 OpenGL 上下文，有三种后端：

| 值 | 用途 | 需要显示器吗 |
|---|---|---|
| `glfw` | 开窗口交互 | ✅ 需要 |
| `osmesa` | **纯 CPU 软件渲染** | ❌ 不需要 |
| `egl` | GPU 无头渲染 | ❌ 不需要（但要 GPU 驱动） |

📌 **CI 里必须用 `osmesa` 或 `egl`** —— 服务器没有显示器，用 `glfw` 会崩。

⚠️ 今天的测试其实**不渲染图像**（只跑物理），但 `import mujoco` 时某些路径
仍会尝试初始化 GL，所以统一设上更省事。

### 2.4 ⚠️ `python -m pytest` vs 直接 `pytest`

```bash
pytest tests/           # ❌ 用系统 PATH 里的 pytest
$PY -m pytest tests/    # ✅ 用指定 python 的 pytest
```

**区别**：`-m` 形式会把**当前目录**加进 `sys.path`，而且**保证用的是 `$PY` 这个
解释器的环境**。直接敲 `pytest` 可能用到系统 python 的 pytest，
那个环境里没装 `mujoco`、`mink` 等依赖 → `ModuleNotFoundError`。

📌 **本项目依赖装在 conda 环境**，所以全程用：

```bash
PY=~/miniconda3/envs/discoverse/bin/python
```

## 2.5 输出怎么读

```
173 passed, 4 skipped, 45 deselected, 17 xfailed in 21.22s
```

| 字段 | 含义 |
|---|---|
| `passed` | 通过 |
| `skipped` | 被 `pytest.skip()` 主动跳过（如缺文件） |
| **`deselected`** | **被 `-m` 标记筛选掉的**（本项目 `addopts` 里有 `-m 'not flake'`） |
| `xfailed` | 预期失败的（已知缺陷），**不算 CI 失败** |

⚠️ `deselected` 不是「跳过」—— 它们是**根本没被选中**。
本项目默认排除 `flake` 标记的测试（那些要跑几分钟做采样）。

## 2.6 只跑单个文件 / 单个测试

```bash
# 单文件
$PY -m pytest tests/mobile_manipulation/test_slide_lift.py -q

# 单个测试函数（:: 分隔）
$PY -m pytest tests/mobile_manipulation/test_slide_lift.py::test_lift_positioning_accuracy -q

# 参数化的某一个
$PY -m pytest "tests/.../test_slide_lift.py::test_lift_positioning_accuracy[0.2]" -q

# 按名字模糊匹配
$PY -m pytest tests/ -k "odometry" -q
```

⚠️ 带 `[]` 的要加引号，否则 shell 会把方括号当通配符。

## 2.7 只收集不运行（数数用）

```bash
$PY -m pytest tests/mobile_manipulation/ --collect-only -q | tail -1
# 34 tests collected in 0.02s
```

📌 **写测试时先 `--collect-only` 确认参数化展开的数量对不对**，
比跑完再数快得多。

## 2.8 Docker 复核命令

```bash
docker build -q -f discoverse/docker/Dockerfile.test -t discoverse:test .
docker run --rm discoverse:test pytest tests/ -q
```

| 片段 | 作用 |
|---|---|
| `-q` (build) | 安静模式，只输出最终镜像 ID |
| `-f <path>` | 指定 Dockerfile（不用默认的 `./Dockerfile`） |
| `-t discoverse:test` | 给镜像打标签（`名字:标签`） |
| `.` | **构建上下文** = 当前目录（会被打包发给 docker daemon） |
| `--rm` | 容器退出后自动删除，不留垃圾 |

### ⚠️⚠️ 绝对不要挂载源码目录

```bash
# ❌ 错误做法（Day 13-14 踩过）
docker run --rm -v "$PWD":/work -w /work discoverse:test pytest tests/ -q
```

**为什么错**：镜像里的代码烤在 `/workspace`（见 `Dockerfile.test:67,78`）。
挂到 `/work` 会造成**两份代码**，Python 的 import 可能解析到镜像里那份**旧的**，
于是你调试了一个 CI 里根本不存在的问题。

**正确做法**：改了代码就**重新 build**。镜像有层缓存，只有代码层会重建，很快。

## 2.9 lint 命令

```bash
env -u PYTHONPATH $PY -m ruff check tests/
# All checks passed!
```

⚠️ **`tests/` 是严格模式** —— CI 里这条命令不带 `|| true`，**必须全绿**。
而 `discoverse/` 只是 `--statistics || true`（仅报告，不阻断），
因为历史遗留 277 个问题。

`scripts/` 目录**完全不在 CI lint 范围内**（已有 113 个历史问题）。

---

# 第三部分：`conftest.py` 逐行（215 行）

## 3.1 `conftest.py` 是什么

**pytest 的「隐式插件文件」** —— 不需要 import，同目录及子目录的测试自动可见。

```
tests/
├── conftest.py                    ← 根级，所有测试可见
└── mobile_manipulation/
    ├── conftest.py                ← 只有本目录可见
    └── test_slide_lift.py         ← 能用上面两个 conftest 的所有 fixture
```

📌 **子目录的 conftest 可以使用父目录 conftest 的 fixture**（今天就是这么干的：
`mmk2_model` 依赖根级的 `mj_model_factory`）。

## 3.2 模块 docstring（1-11 行）

```python
"""MMK2 移动操作测试的共享 fixture 与几何工具。

被测对象：19 自由度双臂轮式机器人（2 轮 + 1 升降 + 2 头部 + 12 臂 + 2 夹爪）。

⚠️ 本目录的用例全部要加载 MJCF 并跑仿真步进，因此统一标 integration
（见 pyproject.toml 的 marker 定义："unit" 要求无 MuJoCo 依赖）。

⚠️ 不打 slow 标记：项目对 slow 的定义是"单用例 >10s"，
   实测本目录最慢的模块合计 ~2.9s 且分摊在 5 个用例上，单例远不够格。
   打了标记 = CI 主线跳过 = wheel_distance 缺陷在日常回归里隐身。
"""
```

📌 **为什么把「不打 slow 标记」写进 docstring？**

因为这是一个**反直觉的决定**。下一个人看到「这些测试要跑 11 秒」，
第一反应就是打 `slow`。docstring 提前拦住他，并给出理由和数据。

> ⭐ **注释要解释「为什么不这么做」，而不只是「做了什么」。**
> 代码本身已经说清楚做了什么。

## 3.3 常量区（24-40 行）

```python
MMK2_XML = os.path.join(DISCOVERSE_ROOT_DIR, "models", "mjcf", "mmk2_floor.xml")
```

⚠️ **用 `os.path.join` 而不是字符串拼接** —— 跨平台（Windows 用 `\`）。
`DISCOVERSE_ROOT_DIR` 是项目在 `discoverse/__init__.py` 里定义的根目录常量，
比写死绝对路径可靠。

```python
CTRL_WHEELS = slice(0, 2)      # 力矩 N·m，ctrlrange ±35
CTRL_LIFT = 2
CTRL_LFT_ARM = slice(5, 11)
CTRL_LFT_GRIPPER = 11
CTRL_RGT_ARM = slice(12, 18)
CTRL_RGT_GRIPPER = 18
```

### 📖 `slice` 对象是什么

```python
CTRL_LFT_ARM = slice(5, 11)
data.ctrl[CTRL_LFT_ARM] = [0, 0, 0, 0, 0, 0]
# 完全等价于
data.ctrl[5:11] = [0, 0, 0, 0, 0, 0]
```

`a[5:11]` 这个语法，Python 内部就是构造了一个 `slice(5, 11)` 传给 `__getitem__`。
把它**存进变量**，就能给这个下标范围**起名字**。

📌 **好处**：`data.ctrl[CTRL_LFT_ARM]` 比 `data.ctrl[5:11]` 可读得多，
而且改布局时只需改一处。

⚠️ **这个布局是今天钉死的重点** —— CLAUDE.md 旧版从第 11 位起整体错位一格。

```python
LIFT_SETTLE_STEPS = 5000
```

**为什么是 5000？** 注释里写了依据：

```python
# 实测稳态所需步数：2000 步（4s 仿真时间）后升降残余变化 < 1e-5 m。
# 取 5000 留余量；再大会逼近 pyproject.toml 的 60s 用例超时。
```

> ⭐ **每个魔数都要有出处。**「实测 2000 够，取 5000 留余量，上限受超时约束」——
> 三句话让下一个人知道这个数能不能改、往哪个方向改。

## 3.4 `mmk2_model` fixture（46-53 行）

```python
@pytest.fixture(scope="session")
def mmk2_model(mj_model_factory):
    """MMK2 模型。

    复用根 conftest 的 session 级工厂（同一 XML 只编译一次）。
    只读，跨用例共享安全。
    """
    return mj_model_factory(MMK2_XML)
```

**`mj_model_factory` 来自根级 `tests/conftest.py`**，是个「工厂 fixture」：

```python
# tests/conftest.py（Day 2 就写好的）
@pytest.fixture(scope="session")
def mj_model_factory():
    cache = {}
    def _make(xml_path):
        if xml_path not in cache:
            cache[xml_path] = mujoco.MjModel.from_xml_path(xml_path)
        return cache[xml_path]
    return _make
```

### 📖 扩展：为什么要「工厂 fixture」这个模式

普通 fixture 只能返回**一个固定的东西**。但不同测试要加载**不同的 XML**。

**方案 A**（不好）：给每个 XML 写一个 fixture → 重复代码。
**方案 B**（本项目）：返回一个**函数**，调用时传参数 → 一个 fixture 服务所有 XML，
且内部 `dict` 缓存保证同一个 XML 只编译一次。

这叫 **"factory as fixture"**，是 pytest 官方推荐模式之一。

📌 **今天复用了它而不是自己再写一遍加载逻辑** —— 遵循 CLAUDE.md 的
「优先扩展现有框架，而非创建新抽象」。

## 3.5 `mmk2_data` fixture（56-69 行）

```python
@pytest.fixture
def mmk2_data(mmk2_model):
    data = mujoco.MjData(mmk2_model)
    mujoco.mj_resetData(mmk2_model, data)
    mujoco.mj_forward(mmk2_model, data)
    return data
```

逐行：

| 行 | 作用 |
|---|---|
| `MjData(model)` | 分配状态数组（实测 0.0004 秒，极便宜） |
| `mj_resetData` | 把状态恢复到模型定义的初始值 `qpos0` |
| `mj_forward` | **算一次前向动力学**，填充派生量（各 body 的世界坐标、接触等） |

### ⚠️ 为什么需要 `mj_forward`

`MjData` 刚创建时，`qpos` 有值了，但**由它推导出来的东西还是空的**：

```python
data.xpos          # 各 body 的世界坐标 —— 还没算
data.ncon          # 接触点数量 —— 还没检测
```

`mj_forward` = 「只算不推进时间」，把这些派生量填好。
`mj_step` = `mj_forward` + 积分一个时间步。

📌 **测试里如果只想看「这个位形下有没有碰撞」而不想推进仿真，
就用 `mj_forward`。**

### 📖 我踩过的一个坑（写在注释里）

```python
    ⚠️ 无需手动置底盘四元数：mj_resetData 从模型的 qpos0 恢复，
       实测 qpos[0:7] = [0,0,0,1,0,0,0]（四元数已是单位四元数）。
```

我原本以为 `mj_resetData` 之后四元数是 `[0,0,0,0]`（非法，会导致 NaN），
所以要手动补 `data.qpos[3:7] = [1,0,0,0]`。

**实测是错的**，不用补。

⭐ **为什么会有这个误解？**因为我在早期实验脚本里手写过这行，
之后就默认「不写会出问题」—— **但我从没验证过不写会怎样**。

> **无害的多余代码，代价是你以为自己懂了。**

## 3.6 `mmk2_model_data_factory` fixture（72-86 行）

```python
@pytest.fixture
def mmk2_model_data_factory(mmk2_model):
    """给"一个用例内需要多次独立仿真"的场景用。"""
    def _make():
        data = mujoco.MjData(mmk2_model)
        mujoco.mj_resetData(mmk2_model, data)
        mujoco.mj_forward(mmk2_model, data)
        return data
    return _make
```

**为什么需要它？**看使用场景（升降下垂一致性测试）：

```python
def test_lift_droop_is_constant_bias_not_noise(mmk2_model, mmk2_model_data_factory):
    errors = []
    for target in (0.0, 0.2, 0.5):
        data = mmk2_model_data_factory()      # ← 每次全新，互不干扰
        errors.append(settle_lift(mmk2_model, data, target) - target)
```

一个测试里要跑 **3 次独立仿真**。如果共用一个 `MjData`，
第二次会从第一次的终点开始 —— 测的就不是「从静止升到 0.2」了。

📌 **fixture 返回值 vs 返回工厂：**
- 要**一个**对象 → 直接返回对象（`mmk2_data`）
- 要**多个**同类对象 → 返回工厂函数（`mmk2_model_data_factory`）

## 3.7 ⭐ `wheel_geometry` fixture（89-105 行）

```python
@pytest.fixture(scope="session")
def wheel_geometry(mmk2_model):
    """从 MJCF 现算轮距与轮半径。

    ⭐ 刻意不使用 MMK2Base.wheel_distance —— 该常量为 0.189，
       与模型实测的 0.3265 不符（缺陷 Y）。
       测试若引用被测常量，就无法证伪该常量。
    """
    ys = []
    for name in ("lft_wheel_joint", "rgt_wheel_joint"):
        jid = mujoco.mj_name2id(mmk2_model, mujoco.mjtObj.mjOBJ_JOINT, name)
        assert jid >= 0, f"模型里找不到关节 {name}"
        ys.append(mmk2_model.body_pos[mmk2_model.jnt_bodyid[jid]][1])

    return {
        "wheel_distance": float(abs(ys[0] - ys[1])),   # 实测 0.3265
        "wheel_radius": 0.0838,
    }
```

### 逐行拆

```python
jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
```

**按名字查 ID**。MuJoCo 内部一切都用整数 ID 索引，`mj_name2id` 做名字→ID 的转换。
`mjOBJ_JOINT` 指定「我要查的是关节」（还有 `mjOBJ_BODY`、`mjOBJ_GEOM` 等）。

⚠️ **找不到时返回 `-1`**，不抛异常。所以下一行必须自己检查：

```python
assert jid >= 0, f"模型里找不到关节 {name}"
```

📌 **不写这个断言的后果**：`jid = -1` → `model.jnt_bodyid[-1]` 是
**Python 的负数索引**，会取到**最后一个元素**！于是你拿到一个完全无关的
body 的位置，而且**不报错**。这是典型的静默失败。

```python
ys.append(model.body_pos[model.jnt_bodyid[jid]][1])
#                        ↑ 关节属于哪个 body   ↑ 取 y 分量
```

三层索引：关节 ID → 它所属的 body ID → 那个 body 的位置 → y 分量。

实测两个轮子的 y 是 `+0.16325` 和 `-0.16325`，所以轮距 = `0.3265`。

### ⭐⭐ 为什么这个 fixture 是全文最重要的设计

```python
# ❌ 如果这么写
from discoverse.robots_env.mmk2_base import MMK2Base
wheel_distance = MMK2Base.wheel_distance     # 0.189
```

那么里程计测试会用 **0.189** 去推算，也用 **0.189** 去…… 等等，
真值是 MuJoCo 给的，不受这个常量影响。所以测试**会红**。

**但问题在于**：如果测试用被测常量，当有人「修正」了常量，
测试的行为也跟着变，**你就无法用测试来判断常量对不对**。

> ⭐ **测试若引用被测对象的常量，就无法证伪该常量。**
> 必须有一个**独立的信息源** —— 这里是 MJCF 模型本身。

📖 **扩展：这在测试理论里叫「测试预言」（test oracle）问题。**
测试需要一个「正确答案的来源」，且这个来源**必须独立于被测实现**。
今天的 oracle 是 MJCF；Day 13-14 用 `junitparser` 独立复核自己生成的 XML，
是同一个道理。

⚠️ **`wheel_radius = 0.0838` 是硬编码的**，因为轮半径存在网格几何里，
不能像 `body_pos` 那样直接读。这是个**已知的不完美**，注释里写明了。

## 3.8 为什么 `wheel_geometry` 返回 dict

```python
return {"wheel_distance": ..., "wheel_radius": ...}
```

配合调用处的 `**` 解包：

```python
drive(model, data, 1.0, 1.0, **wheel_geometry)
# 等价于
drive(model, data, 1.0, 1.0, wheel_distance=0.3265, wheel_radius=0.0838)
```

### 📖 `**` 解包语法

```python
d = {"a": 1, "b": 2}
f(**d)          # 等价于 f(a=1, b=2)
```

📌 **好处**：`drive()` 的签名里两个参数是**显式命名**的，
所以将来要单独替换其中一个（如测试用错误的轮距）很自然：

```python
drive(model, data, 1.0, 1.0,
      wheel_distance=MMK2Base.wheel_distance,        # 故意用错的
      wheel_radius=wheel_geometry["wheel_radius"])   # 这个还用对的
```

## 3.9 `qpos_adr()`（112-118 行）

```python
def qpos_adr(model, joint_name):
    """取关节在 qpos 里的起始下标。"""
    jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, joint_name)
    assert jid >= 0, f"模型里找不到关节 {joint_name}"
    return model.jnt_qposadr[jid]
```

**`jnt_qposadr`** = 「关节 → 它在 `qpos` 数组里的起始位置」的映射表。

为什么需要它？回顾 [1.2](#12-qpos--qvel--ctrl-分别是什么)：
自由关节占 7 个、滑动/铰链关节各占 1 个，**长度不一**，
所以「第 N 个关节」和「`qpos` 第 N 个元素」**完全不是一回事**。

```python
qpos_adr(model, "slide_joint")    # → 9
```

📌 **计划文档写 `qpos[2]` 是升降，实际 `qpos[2]` 是底盘的 z 坐标。**
用这个函数就不会犯这种错。

## 3.10 `quat_wxyz_to_matrix()`（124-131 行）

```python
def quat_wxyz_to_matrix(quat_wxyz):
    return Rotation.from_quat(np.asarray(quat_wxyz)[[1, 2, 3, 0]]).as_matrix()
```

### 逐层拆

```python
np.asarray(quat_wxyz)      # 转成 numpy 数组（可能传进来的是 list）
[[1, 2, 3, 0]]             # ⭐ numpy 的「花式索引」
```

### 📖 花式索引（fancy indexing）

```python
a = np.array([10, 20, 30, 40])
a[[1, 2, 3, 0]]            # → array([20, 30, 40, 10])
#  ↑ 用一个下标列表，按指定顺序重排
```

对 `[w, x, y, z]` 用 `[[1,2,3,0]]` → 取出 `[x, y, z, w]`。**正是 scipy 要的顺序。**

⚠️ **注意双层方括号**：`a[[1,2,3,0]]` 外层是索引语法，内层是列表。
写成 `a[1,2,3,0]` 会被当成多维索引 → 报错。

```python
.as_matrix()               # 四元数 → 3×3 旋转矩阵
```

📌 **为什么要转成矩阵？**因为 `MMK2IK.armIK_wrt_footprint()` 的参数就是 3×3 矩阵。

## 3.11 ⭐⭐ `world_to_footprint()`（134-152 行）

**全文最关键的函数。**

```python
def world_to_footprint(pos_w, rot_w, base_pos, base_quat_wxyz):
    t_w_base = np.eye(4)
    t_w_base[:3, :3] = quat_wxyz_to_matrix(base_quat_wxyz)
    t_w_base[:3, 3] = base_pos

    t_w_ee = np.eye(4)
    t_w_ee[:3, :3] = rot_w
    t_w_ee[:3, 3] = pos_w

    t_base_ee = np.linalg.inv(t_w_base) @ t_w_ee
    return t_base_ee[:3, 3], t_base_ee[:3, :3]
```

### 📖 先补概念：4×4 齐次变换矩阵

机器人学里表示「位姿」（位置 + 姿态）的标准形式：

```
      ┌                    ┐
      │  R11 R12 R13   px  │     R = 3×3 旋转矩阵（姿态）
  T = │  R21 R22 R23   py  │     p = 3×1 平移向量（位置）
      │  R31 R32 R33   pz  │
      │   0   0   0     1  │     最后一行永远是 [0 0 0 1]
      └                    ┘
```

**为什么要凑成 4×4？**因为这样「旋转 + 平移」可以用**一次矩阵乘法**表达，
而且**可以连乘**：

```
T_world_ee = T_world_base @ T_base_ee
```

坐标系变换像链条一样串起来，这是机器人学最基础的工具。

### 逐行

```python
t_w_base = np.eye(4)                                    # 先造 4×4 单位阵
t_w_base[:3, :3] = quat_wxyz_to_matrix(base_quat_wxyz)  # 左上角 3×3 填旋转
t_w_base[:3, 3] = base_pos                              # 右上角 3×1 填平移
```

`np.eye(4)` 生成单位阵，**最后一行天然就是 `[0,0,0,1]`**，不用手动填。

命名约定 `t_w_base` = **T_world_base** = 「base 在 world 中的位姿」。

```python
t_base_ee = np.linalg.inv(t_w_base) @ t_w_ee
```

数学上：

```
T_base_ee = T_world_base⁻¹ @ T_world_ee
            └───────────┘
            world→base 的逆变换
```

`@` 是 Python 的**矩阵乘法**运算符（`*` 是逐元素乘，**不是**矩阵乘）。

```python
return t_base_ee[:3, 3], t_base_ee[:3, :3]
#             位置          姿态
```

### ⭐⭐ 为什么这个函数是必需的（不是可选的）

```
MMK2FK.get_*_endeffector_pose()  →  world 系
MMK2IK.armIK_wrt_footprint()     ←  footprint 系
```

**底盘在原点且无旋转时，`T_world_base` = 单位阵**，于是：

```
T_base_ee = I⁻¹ @ T_world_ee = T_world_ee
```

**两个坐标系数值上完全相等** —— 所以「忘记做变换」的实现也能通过测试。

📌 **变异测试证明**：把这个函数改成「直接返回世界系位姿」，
12 条用例里**只有 1 条**（`test_roundtrip_with_base_off_origin`）会红，
**另外 11 条全部通过这个坏实现**。

> ⭐ **这类陷阱叫「恒等陷阱」：当两个本该不同的东西在某个特殊输入下恰好相同，
> 用那个输入做的测试无法区分「实现正确」和「实现遗漏」。**

**常见的危险默认值**：原点、单位四元数、单位矩阵、`scale=1.0`、`dt=1.0`、`offset=0`。

## 3.12 `body_chain()`（155-163 行）

```python
def body_chain(model, body_id):
    """从 body 一路向上追溯到 worldbody，返回名字列表。"""
    names = []
    while body_id > 0:
        names.append(mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id) or "?")
        body_id = model.body_parentid[body_id]
    return names
```

### 📖 MuJoCo 的 body 树

机器人是一棵**树**：

```
world (id=0)
└── mmk2
    └── agv_link
        └── slide_link
            ├── lft_arm_base → lft_arm_link1 → ... → lft_finger_right_link
            └── rgt_arm_base → rgt_arm_link1 → ... → rgt_finger_left_link
```

`model.body_parentid[i]` = 「body i 的父节点是谁」。
一路往上走到 `id == 0`（world）就停。

```python
while body_id > 0:      # id=0 是 worldbody，到它就停
```

```python
... or "?"
```

**`or` 的短路特性**：`mj_id2name` 找不到名字时返回 `None`，
`None or "?"` → `"?"`。这是 Python 里给「可能是 None」的值设默认值的惯用法。

实测输出：

```
geom 51 的 body 链: ['lft_finger_right_link', 'lft_arm_link6', ..., 'lft_arm_base',
                     'slide_link', 'agv_link', 'mmk2']
```

## 3.13 ⭐ `arm_side()`（166-180 行）

```python
def arm_side(model, geom_id):
    """判断 geom 属于左臂 / 右臂 / 都不是，返回 "L" / "R" / None。"""
    for name in body_chain(model, model.geom_bodyid[geom_id]):
        if name.startswith(("lft_arm", "lft_finger")):
            return "L"
        if name.startswith(("rgt_arm", "rgt_finger")):
            return "R"
    return None
```

### 📖 `str.startswith` 可以接元组

```python
name.startswith(("lft_arm", "lft_finger"))
# 等价于
name.startswith("lft_arm") or name.startswith("lft_finger")
```

传元组表示「**任意一个**匹配即可」。比写两个 `or` 简洁。

### ⭐⭐ 为什么不直接看 geom 的名字

计划文档的写法：

```python
geom1 = mj_model.geom(contact.geom1).name
if "left_arm" in geom1 and "right_arm" in geom2:
    pytest.fail(...)
```

**实测**：

```
ngeom=73  named=11  unnamed=62
```

**73 个 geom 里只有 11 个有名字，手臂上的全部无名。**

于是 `geom1` 是空字符串 `''`，`"left_arm" in ''` **恒为 `False`** ——
**测试永远通过，且从未检测过任何东西。**

> ⭐ **命名靠人自觉（可缺失、可拼错、可不一致）；
> body 父子关系由物理模型强制（不写就建不出模型）。
> 当直接的标识不可用时，往结构里找。**

## 3.14 `cross_arm_contacts()`（182-200 行）

```python
def cross_arm_contacts(model, data):
    hits = set()
    for i in range(data.ncon):
        con = data.contact[i]
        side1, side2 = arm_side(model, con.geom1), arm_side(model, con.geom2)
        if side1 and side2 and side1 != side2:
            hits.add((
                body_chain(model, model.geom_bodyid[con.geom1])[0],
                body_chain(model, model.geom_bodyid[con.geom2])[0],
            ))
    return hits
```

### 逐行

```python
data.ncon         # 当前检测到的接触点【数量】
data.contact[i]   # 第 i 个接触点的详细信息
con.geom1         # 参与接触的第一个 geom 的 ID
```

```python
if side1 and side2 and side1 != side2:
```

三个条件：
1. `side1` 非 None → geom1 属于某条手臂
2. `side2` 非 None → geom2 属于某条手臂
3. `side1 != side2` → **分属左右**（排除「同一条手臂自己碰自己」）

```python
body_chain(...)[0]     # 取链条的第一个元素 = geom 直接所属的 body 名
```

```python
hits = set()           # 用集合去重
```

**为什么去重**：同一对 body 之间可能有多个接触点（比如两个手指面接触），
我们只关心「哪两个部件碰了」，不关心碰了几个点。

### ⚠️ 为什么不能直接 `assert data.ncon == 0`

实测双臂对撞时：

```
ncon = 8
  ('floor', 'lft_behind_wheel')     ← 轮子和地板，正常
  ('floor', 'rgt_behind_wheel')     ← 正常
  ('floor', '21')                   ← 正常
  ('floor', '23')                   ← 正常
  ('51', '72')                      ← 真正的自碰撞
  ('52', '71')                      ← 真正的自碰撞
```

**机器人站在地上，接触数永远 > 0。**必须筛选。

## 3.15 `step_with_ctrl()` 与 `base_yaw()`（202-215 行）

```python
def step_with_ctrl(model, data, ctrl, n_steps):
    for _ in range(n_steps):
        data.ctrl[:] = ctrl
        mujoco.mj_step(model, data)
```

⚠️ **`data.ctrl[:] = ctrl` 的 `[:]` 不能省**：

```python
data.ctrl[:] = ctrl     # ✅ 把值【拷贝进】MuJoCo 的数组
data.ctrl = ctrl        # ❌ 把 Python 名字重新绑定，MuJoCo 看不到
```

`data.ctrl` 是一个指向 C 层内存的 numpy 视图。**必须原地赋值**。

```python
def base_yaw(data):
    return Rotation.from_quat(data.qpos[[4, 5, 6, 3]]).as_euler("xyz")[2]
```

`qpos[3:7]` 是 `[w,x,y,z]`，所以 `qpos[[4,5,6,3]]` = `[x,y,z,w]`（scipy 顺序）。

`.as_euler("xyz")` → 转成欧拉角 `[roll, pitch, yaw]`，取 `[2]` = **yaw（偏航）**。

📖 **扩展：为什么用 yaw 而不是完整姿态？**
地面移动机器人只在平面运动，`roll`/`pitch` 恒为 0，**只有 yaw 有意义**。
这也是差速里程计只推算 `(x, y, θ)` 三个量的原因。

---

# 第四部分：`test_mmk2_kinematics.py` 逐行（200 行）

## 4.1 文件头与常量（1-30 行）

```python
pytestmark = [pytest.mark.integration]

ROUNDTRIP_ATOL = 1e-3
Q_SAMPLE = np.array([0.1, -0.2, 0.3, 0.1, 0.2, 0.1])
```

### ⭐ `ROUNDTRIP_ATOL = 1e-3` 这个数怎么来的

**不是拍脑袋。**实测往返误差是 `9.7e-05` rad，取 **10 倍余量**：

| 容差 | 评价 |
|---|---|
| `1e-6` | ❌ 必红（低于解析解的浮点残差） |
| **`1e-3`** | ✅ 比实测大一个量级，留浮点/平台余量 |
| `1e-2` | ⚠️ 太松，符号错误都可能漏过 |

> ⭐ **定容差的原则：先测量，再取实测值的 10 倍。**
> 拍脑袋定的容差要么天天红（噪声），要么什么都抓不到（空转）。

## 4.2 `fk` / `ik` fixture（33-52 行）

```python
@pytest.fixture(scope="module")
def fk():
    from discoverse.robots.mmk2.mmk2_fk import MMK2FK
    return MMK2FK()
```

### 📖 为什么 import 写在函数里（延迟导入）

```python
def fk():
    from discoverse.robots.mmk2.mmk2_fk import MMK2FK    # ← 函数内 import
```

**如果写在文件顶部**，那么 pytest **收集**测试时就会执行 import。
`MMK2FK.__init__` 会加载整个 MJCF 模型（要几百毫秒）。
即使你只想 `--collect-only` 数个数，也得等它加载。

📌 **延迟导入让「收集阶段」保持轻量。**这在大型测试套件里很重要。

### `scope="module"` 的理由

`MMK2FK` 内部持有 `mj_model` + `mj_data`，**是有状态的**。
但每个测试用之前都会调 `set_*` 重新设定全部关节，**等于每次都重置**，
所以模块内共享安全，且省掉重复加载模型的开销。

⚠️ **这是个「有条件的安全」** —— 依赖于「每个用例都完整设置所有关节」这个约定。
`fk_endpoint()` 辅助函数保证了这一点（见 4.3）。

```python
@pytest.fixture(scope="module")
def ik():
    from discoverse.robots.mmk2.mmk2_ik import MMK2IK
    return MMK2IK()
```

⚠️ **为什么用 `MMK2IK` 而不是 `MMK2FIK`**（注释里写了）：

1. `MMK2FIK` 已被上游标记弃用（构造时打印黄色告警）
2. ⭐ `MMK2FIK` 只能从 `pick`/`carry`/`look` **三个预设动作**查表取姿态 ——
   那测的是**查找表**不是运动学；`MMK2IK` 直接吃任意 3×3 旋转矩阵

## 4.3 `fk_endpoint()` 辅助函数（55-71 行）

```python
def fk_endpoint(fk, arm, q, slide, base_pos=(0, 0, 0), base_quat=(1, 0, 0, 0)):
    fk.set_base_pose(list(base_pos), list(base_quat))
    fk.set_slide_joint(slide)
    fk.set_head_joints([0, 0])
    fk.set_left_arm_joints(q if arm == "l" else np.zeros(6))
    fk.set_right_arm_joints(q if arm == "r" else np.zeros(6))
    fk.forward_kinematics()

    if arm == "l":
        return fk.get_left_endeffector_pose()
    return fk.get_right_endeffector_pose()
```

### ⚠️ 为什么必须调**所有**的 `set_*`

注释写了：

```python
    ⚠️ 必须先调 set_*：MMK2FK.__init__ 从未初始化 self.pos_modifidied，
       而每个 getter 都读它（mmk2_fk.py:118）。直接调 getter 会 AttributeError。
```

看上游源码：

```python
# mmk2_fk.py:9-13
def __init__(self, mjcf_path=None):
    self.mj_model = ...
    self.mj_data = ...
    # ← 从未设置 self.pos_modifidied

# mmk2_fk.py:118（每个 getter 都有）
if self.pos_modifidied:          # ← 读一个不存在的属性
    self.forward_kinematics()
```

**这个属性只在 `set_*` 方法里被创建。**所以不调 setter 就直接 getter → `AttributeError`。

⚠️ 拼写是 `pos_modifidied`（少个 `f`、多个 `i`），**原文如此，不要"顺手修正"** ——
改了会把所有 setter 一起打断（它们都用这个拼写）。

### `q if arm == "l" else np.zeros(6)`

**三元表达式**：测哪条臂就给哪条臂设 `q`，另一条设零位。
保证「另一条臂」处于确定状态，避免它残留上次的值。

### 默认参数用元组而非列表

```python
base_pos=(0, 0, 0)          # ✅ 元组，不可变
base_pos=[0, 0, 0]          # ⚠️ 列表，可变
```

📖 **Python 经典陷阱：可变默认参数**

```python
def bad(items=[]):          # ❌ 这个 [] 只创建一次！
    items.append(1)
    return items

bad()   # [1]
bad()   # [1, 1]     ← 上次的残留！
```

默认参数在**函数定义时**求值一次，之后所有调用共享同一个对象。
用元组（不可变）就没有这个风险。

## 4.4 `roundtrip_error()`（74-80 行）

```python
def roundtrip_error(fk, ik, arm, q, slide, base_pos=(0,0,0), base_quat=(1,0,0,0)):
    pos_w, quat_w = fk_endpoint(fk, arm, q, slide, base_pos, base_quat)
    rot_w = quat_wxyz_to_matrix(quat_w)
    pos_f, rot_f = world_to_footprint(pos_w, rot_w, np.asarray(base_pos), base_quat)
    solution = np.asarray(ik.armIK_wrt_footprint(pos_f, rot_f, arm, slide, q))
    return np.abs(solution - q).max()
```

**完整的往返链条**：

```
关节角 q
  │ FK
  ▼
末端位姿（world 系）
  │ quat wxyz → 旋转矩阵
  ▼
末端位姿（world 系，矩阵形式）
  │ world_to_footprint
  ▼
末端位姿（footprint 系）
  │ IK
  ▼
解出的关节角 solution
  │
  ▼
误差 = max(|solution - q|)
```

```python
np.abs(solution - q).max()      # 逐元素求绝对值，取最大的那个
```

📌 **用 `max` 而不是 `mean`**：我们要保证**每一个**关节都准，
平均值会掩盖单个关节的大偏差。

## 4.5 基础往返测试（83-87 行）

```python
@pytest.mark.parametrize("arm", ["l", "r"])
def test_fk_ik_roundtrip_closes(fk, ik, arm):
    err = roundtrip_error(fk, ik, arm, Q_SAMPLE, slide=0.0)
    assert err < ROUNDTRIP_ATOL, f"{arm} 臂往返误差 {err:.3e} 超出 {ROUNDTRIP_ATOL}"
```

### 📖 断言的第二个参数

```python
assert 条件, "失败时显示的消息"
```

⭐ **消息里一定要带上实际值**（`{err:.3e}`），否则失败时你只知道
「断言失败了」，不知道**差多少** —— 是差一点点（该调容差）还是差 100 倍（真有 bug）。

`{err:.3e}` 是格式化：科学计数法，3 位小数 → `9.737e-05`。

## 4.6 ⭐ slide 全行程扫描（90-99 行）

```python
@pytest.mark.parametrize("slide", [0.0, 0.1, 0.3, 0.5, 0.87])
def test_fk_ik_roundtrip_across_slide_range(fk, ik, slide):
    """⭐ 这条测的是 FK 与 IK 对 slide 符号约定的一致性。"""
    err = roundtrip_error(fk, ik, "l", Q_SAMPLE, slide=slide)
    assert err < ROUNDTRIP_ATOL, f"slide={slide} 往返误差 {err:.3e}"
```

### ⭐ 这条测试真正在测什么

不是「IK 准不准」，而是 **「FK 和 IK 对升降的符号约定是否一致」**。

看上游 IK 源码：

```python
# mmk2_ik.py:62-63
tmat = self.TMat_footprint2chest.copy()
tmat[2, 3] -= slide           # ← 【减】
```

**如果有人把 `-=` 改成 `+=`**：
- 单独跑 IK：不会报错，照样解得出关节角（只是解错了）
- **只有往返测试会红**

📌 **这就是往返测试的核心价值：它测的是「两个组件是否用同一个模型」。**

真机上同形：FK 来自 URDF，IK 来自厂商固件，参数不一致时
单独看每个都对，**串起来就飘**。

## 4.7 slide 语义测试（102-116 行）

```python
def test_slide_lowers_torso(fk):
    """升降语义：slide 增大 → 末端 Z 降低（反直觉，必须钉住）。"""
    z_at = {}
    for slide in (0.0, 0.87):
        pos, _ = fk_endpoint(fk, "l", Q_SAMPLE, slide)
        z_at[slide] = pos[2]

    drop = z_at[0.0] - z_at[0.87]
    assert drop == pytest.approx(0.87, abs=1e-3)
```

### 📖 `pytest.approx` 是什么

浮点数不能用 `==` 比较：

```python
0.1 + 0.2 == 0.3        # False！实际是 0.30000000000000004
```

`pytest.approx` 做**带容差的比较**：

```python
drop == pytest.approx(0.87, abs=1e-3)      # |drop - 0.87| < 1e-3
```

| 参数 | 含义 |
|---|---|
| `abs=1e-3` | 绝对容差 |
| `rel=1e-6` | 相对容差（按比例） |

⚠️ **量纲有意义时用 `abs`**（这里是米），**跨数量级比较时用 `rel`**。

### 为什么这条测试重要

实测 slide 0→0.87，末端 Z 从 **1.235 降到 0.365** —— 正好差 0.87。

**执行器叫 "lift"（举升），但数值越大躯干越低。**这是反直觉的，
必须用测试钉住，否则下一个人一定会写反。

## 4.8 ⭐⭐ 底盘非原点测试（119-136 行）

```python
def test_roundtrip_with_base_off_origin(fk, ik):
    """⭐ 底盘不在原点时往返仍须闭合 —— 本文件最有价值的一条。"""
    base_pos = (1.0, 0.5, 0.0)
    base_quat = Rotation.from_euler("z", np.pi / 2).as_quat()[[3, 0, 1, 2]]

    err = roundtrip_error(fk, ik, "l", Q_SAMPLE, slide=0.0,
                          base_pos=base_pos, base_quat=base_quat)
    assert err < ROUNDTRIP_ATOL
```

### 逐行

```python
Rotation.from_euler("z", np.pi / 2)      # 绕 z 轴转 90°
.as_quat()                                # → scipy 的 xyzw
[[3, 0, 1, 2]]                            # ⭐ xyzw → wxyz（MuJoCo 顺序）
```

⚠️ **注意这次是 `[[3,0,1,2]]`，和 3.10 的 `[[1,2,3,0]]` 相反** ——
因为方向反了（这次是 scipy → MuJoCo）。

### ⭐⭐ 为什么这是最有价值的一条

**变异测试实证**：把 `world_to_footprint` 改成不做变换：

```
1 failed, 11 passed, 1 xfailed
FAILED test_roundtrip_with_base_off_origin        ← 只有它红
```

**另外 11 条全部通过了那个坏实现。**

📌 **同时平移 + 旋转 90°**，不只是平移 —— 因为只平移的话，
旋转部分仍是单位阵，**姿态的变换错误依然测不出来**。

> ⭐ **要跳出恒等陷阱，必须让所有相关分量都非平凡。**

## 4.9 边界行为测试（139-155 行）

```python
def test_unreachable_target_raises(ik):
    with pytest.raises(ValueError):
        ik.armIK_wrt_footprint(np.array([5.0, 0.0, 1.2]), np.eye(3), "l", 0.0)
```

### 📖 `pytest.raises` 上下文管理器

```python
with pytest.raises(ValueError):
    某段应该抛异常的代码
```

- 代码**抛了** `ValueError` → 测试**通过**
- 代码**没抛**异常 → 测试**失败**（"DID NOT RAISE"）
- 代码抛了**别的**异常 → 测试**失败**

📌 **为什么要测「不可达时抛异常」？**

这是**钉住当前的好行为**。如果将来有人「优化」成返回 `None`：

```python
try:
    jq = solve(...)
except ValueError:
    return None          # ← 「优化」
```

那么调用方拿到 `None` 会在**别的地方**崩溃，或者更糟 ——
把 `None` 当成有效结果继续用。**响亮的失败变成静默失败。**

```python
def test_invalid_arm_raises(ik):
    with pytest.raises(ValueError):
        ik.armIK_wrt_footprint(..., "left", 0.0)    # ← 计划文档写的 'left'
```

顺带**钉住取值域是 `'l'`/`'r'`**。

## 4.10 tmats 缓存护栏（158-183 行）

```python
def test_ik_tmats_cache_matches_mjcf():
    """回归护栏：IK 的缓存变换矩阵必须与从 MJCF 现算的一致。"""
    solver = MMK2IK()
    fresh = solver.generate_tmats()

    for key, cached in (
        ("footprint2chest", solver.TMat_footprint2chest),
        ...
    ):
        np.testing.assert_allclose(cached, fresh[key], atol=1e-9,
                                   err_msg=f"{key} 缓存与 MJCF 不一致")
```

### 📖 `np.testing.assert_allclose`

numpy 版的「近似相等」断言，**专为数组设计**：

```python
np.testing.assert_allclose(实际, 期望, atol=容差, err_msg="失败消息")
```

失败时会打印**详细的差异报告**（哪个位置差多少、最大差值、不匹配的元素比例），
比自己写 `assert (a - b).max() < tol` 的信息量大得多。

### ⭐ 这条测试今天不抓 bug

**实测当前 `maxdiff = 0`，缓存是对的。**

那为什么还写？看上游源码：

```python
# mmk2_ik.py:13-19
try:
    tmats = np.load(".../mmk2_ik_tmats.npz")
except:                                    # ← 裸 except
    tmats = self.generate_tmats()
    np.savez(...)
```

两个问题：
1. **裸 `except:`** 会吞掉 `KeyboardInterrupt`、`MemoryError`
2. ⭐ **缓存文件不带版本戳** —— 有人改了 MJCF 里的臂基座位置，
   这个 `.npz` **不会失效**，IK 继续用旧矩阵，**且不报错**

> ⭐ **这类测试叫「回归护栏」（regression guard）：
> 它今天不抓 bug，它防止明天产生 bug。**

📌 **要区分「已发生的缺陷」和「没有防护的风险」** ——
我在缺陷表里把它标为「风险，非缺陷」，不能包装成战果。

## 4.11 缺陷 Z 的 xfail（186-200 行）

```python
@pytest.mark.xfail(
    reason="缺陷 Z：MMK2FK.__init__ 未初始化 pos_modifidied，"
           "直接调 getter 会 AttributeError（mmk2_fk.py:9-13 vs :118）",
    strict=True,
)
def test_fk_getter_before_setter_raises():
    from discoverse.robots.mmk2.mmk2_fk import MMK2FK
    MMK2FK().get_left_endeffector_pose()
```

**测试体只有一行**，且**没有任何 assert**。

📖 **为什么不用 `pytest.raises(AttributeError)`？**

```python
# 方案 A（本项目采用）
@pytest.mark.xfail(strict=True)
def test_...():
    MMK2FK().get_left_endeffector_pose()      # 会抛 AttributeError → xfailed

# 方案 B
def test_...():
    with pytest.raises(AttributeError):
        MMK2FK().get_left_endeffector_pose()   # 断言它抛异常 → passed
```

**语义完全不同**：

| | 表达的意思 |
|---|---|
| 方案 A（xfail） | 「**这是个缺陷**，现在会炸，修好后请删掉这条」 |
| 方案 B（raises） | 「**这是正确行为**，就该抛 AttributeError」 |

📌 **`AttributeError` 不是正确行为**，所以必须用 xfail。
`strict=True` 保证缺陷修复后 CI 会提醒删除这条测试。

---

# 第五部分：`test_differential_drive.py` 逐行（214 行）

## 5.1 常量（25-34 行）

```python
DRIVE_STEPS = 4000          # 4000 步 = 8s 仿真时间，实测约 0.47s 墙钟
ODOM_YAW_ATOL = 0.05        # 实测（正确轮距）≤ 0.0066 rad，取一个量级余量
ODOM_POS_ATOL = 0.02
STRAIGHTNESS_MAX = 0.05     # 实测 0.05%，阈值取 5%
```

📖 **「仿真时间」vs「墙钟时间」**

```
4000 步 × 0.002 s/步 = 8 秒（仿真世界里过了 8 秒）
实际计算耗时           = 0.47 秒（现实世界）
```

仿真比实时**快 17 倍** —— 因为这个模型不算复杂，且没有渲染。

## 5.2 ⭐⭐ `drive()` 核心函数（36-70 行）

```python
def drive(model, data, torque_left, torque_right, wheel_distance, wheel_radius,
          steps=DRIVE_STEPS):
    prev_phi = data.qpos[7:9].copy()
    odom = np.zeros(3)                      # x, y, theta

    for _ in range(steps):
        data.ctrl[:] = 0.0
        data.ctrl[0] = torque_left
        data.ctrl[1] = torque_right
        mujoco.mj_step(model, data)

        phi = data.qpos[7:9].copy()
        d_phi = phi - prev_phi
        prev_phi = phi

        ds_l, ds_r = wheel_radius * d_phi[0], wheel_radius * d_phi[1]
        ds = (ds_l + ds_r) / 2.0
        d_theta = (ds_r - ds_l) / wheel_distance

        odom[0] += ds * np.cos(odom[2] + d_theta / 2.0)
        odom[1] += ds * np.sin(odom[2] + d_theta / 2.0)
        odom[2] += d_theta

    truth = np.array([data.qpos[0], data.qpos[1], base_yaw(data)])
    return odom, truth
```

### ⚠️ `.copy()` 为什么不能省

```python
prev_phi = data.qpos[7:9].copy()
```

`data.qpos[7:9]` 返回的是一个**视图**（view），不是拷贝 ——
它指向 MuJoCo 内部的同一块内存。

```python
prev_phi = data.qpos[7:9]        # ❌ 视图
mujoco.mj_step(...)              # MuJoCo 改了内存
phi = data.qpos[7:9]
d_phi = phi - prev_phi           # → 永远是 0！因为两者指向同一块内存
```

📌 **这是 numpy + C 扩展库最经典的坑。**凡是要「记住上一时刻的值」，
**必须 `.copy()`**。

### 差速运动学公式

```python
ds_l = wheel_radius * d_phi[0]       # 左轮走过的弧长 = 半径 × 转角
ds_r = wheel_radius * d_phi[1]

ds      = (ds_l + ds_r) / 2          # 车体中心前进距离 = 两轮平均
d_theta = (ds_r - ds_l) / wheel_distance   # 转过的角度 = 两轮差 / 轮距
```

📖 **直观理解**：
- 两轮走一样多 → `ds_r - ds_l = 0` → 不转向，直行
- 右轮比左轮多走 → 向左偏（右边跑得快）
- 两轮反向等速 → `ds = 0`，原地旋转

### ⭐ 中点积分

```python
odom[0] += ds * np.cos(odom[2] + d_theta / 2.0)
#                                 ↑ 用【半步】的航向
```

**为什么加 `d_theta / 2`？**

这一小段运动中，航向从 `θ` 变到 `θ + Δθ`。用哪个角度算位移？

| 方法 | 用的角度 | 精度 |
|---|---|---|
| 前向欧拉 | `θ`（起点） | 差 |
| 后向欧拉 | `θ + Δθ`（终点） | 差 |
| **中点法** | **`θ + Δθ/2`（中点）** | **好** |

转弯时前两者会系统性地偏向一边，中点法**误差是二阶的**（小得多）。

📌 **这是数值积分的常识，但很多里程计实现会忽略它。**

## 5.3 力矩控制前提测试（73-94 行）

```python
def test_wheel_torque_not_velocity(mmk2_model, mmk2_data):
    speeds = []
    for _ in range(4):
        for _ in range(500):
            mmk2_data.ctrl[:] = 0.0
            mmk2_data.ctrl[0] = 1.0
            mmk2_data.ctrl[1] = 1.0
            mujoco.mj_step(mmk2_model, mmk2_data)
        speeds.append(float(mmk2_data.qvel[6]))

    assert all(b > a for a, b in zip(speeds, speeds[1:]))
```

### 📖 `zip(speeds, speeds[1:])` 的技巧

```python
speeds       = [0.68, 1.10, 1.37, 1.53]
speeds[1:]   =       [1.10, 1.37, 1.53]
zip(...)     = [(0.68,1.10), (1.10,1.37), (1.37,1.53)]
```

**把相邻元素两两配对** —— 检查「是否严格递增」的惯用法。

```python
all(b > a for a, b in zip(...))     # 所有相邻对都递增
```

### 为什么要这条测试

**它保护的是整个文件的建模假设。**

如果将来有人把 `<motor>` 改成 `<velocity>`（速度控制），
那么「从编码器推算」的整套逻辑就没必要了，而且
`drive()` 里的力矩语义全错。

📌 **让这件事立刻可见**，而不是让里程计测试以一个费解的方式变红。

⚠️ `qvel[6]` 是左轮的角速度 —— 注意 `qvel` 和 `qpos` 下标不同！
`qpos[7]` 对应 `qvel[6]`（因为自由关节在 qpos 占 7、qvel 占 6）。

## 5.4 直线度测试（97-121 行）

```python
def test_straight_line_motion(mmk2_model, mmk2_data, wheel_geometry):
    start = mmk2_data.qpos[:2].copy()
    drive(mmk2_model, mmk2_data, 1.0, 1.0, **wheel_geometry)
    displacement = mmk2_data.qpos[:2].copy() - start

    longitudinal = abs(displacement[0])     # x 是纵向
    lateral = abs(displacement[1])          # y 是横向

    assert longitudinal > 0.1, "机器人几乎没有前进，直线度测试无意义"

    straightness = lateral / longitudinal
    assert straightness < STRAIGHTNESS_MAX
```

### ⚠️ 计划文档把轴搞反了

```python
straightness = abs(displacement[0]) / abs(displacement[1])   # 计划文档
```

实测机器人沿 **+x** 前进：`xy = [0.606, 0.0003]`。

代入计划文档的公式：`0.606 / 0.0003 = 1955`，断言 `< 0.05` **必红**。
而且横向漂移恰好为 0 时直接 `ZeroDivisionError`。

### ⭐⭐ 前置断言是关键

```python
assert longitudinal > 0.1, "机器人几乎没有前进，直线度测试无意义"
```

**没有这行会怎样？**

```
机器人一步没动 → longitudinal ≈ 0, lateral ≈ 0
→ straightness = 0/0 或 0/极小值
→ 可能得到 0 或 nan
→ 0 < 0.05 → 【通过】
```

**一个完全没动的机器人，通过了「直线度」测试。**又一个空转绿测试。

> ⭐ **凡是「比值 < 阈值」的断言，都必须先断言分母足够大。**
> 这和 Day 5 的教训一脉相承：**永远先证明测试真的执行了。**

## 5.5 里程计主测试（124-157 行）

```python
@pytest.mark.parametrize(
    ("torque_left", "torque_right", "label"),
    [
        (1.0, 1.0, "直线"),
        (1.0, 0.5, "缓转弯"),
        (1.0, -1.0, "原地旋转"),
    ],
)
def test_odometry_matches_ground_truth(mmk2_model, mmk2_data, wheel_geometry,
                                       torque_left, torque_right, label):
    odom, truth = drive(mmk2_model, mmk2_data, torque_left, torque_right,
                        **wheel_geometry)
    yaw_err = abs(odom[2] - truth[2])
    pos_err = float(np.linalg.norm(odom[:2] - truth[:2]))
    assert yaw_err < ODOM_YAW_ATOL, f"[{label}] 偏航推算误差 {yaw_err:.4f} rad ..."
```

### 📖 多参数 parametrize

```python
@pytest.mark.parametrize(("a", "b", "c"), [(1,2,"x"), (3,4,"y")])
```

**参数名用元组，值也用元组列表** —— 一次注入多个参数。

`label` 这个参数**不参与计算**，只用来让失败消息可读：

```
[原地旋转] 偏航推算误差 1.9440 rad（推算 -4.6005 vs 真值 -2.6565）
```

⭐ **比 `test_odometry[1.0--1.0]` 这种自动生成的 ID 好懂得多。**

### `np.linalg.norm`

```python
np.linalg.norm([dx, dy])        # = sqrt(dx² + dy²)，欧氏距离
```

### ⭐ 这条测试的设计核心

```python
                        **wheel_geometry      # ← 从 MJCF 现算的 0.3265
```

**刻意不用 `MMK2Base.wheel_distance`。**

如果用了被测常量，这条测试会红 —— 但那时它红是因为「常量错」还是
「里程计公式错」？**分不清。**

用独立的真值源（MJCF），这条测试就只测**里程计公式**，
常量的对错由下面那条专门的 xfail 负责。

> ⭐ **一条测试只测一件事。**

## 5.6 ⭐ 解释性测试（160-185 行）

```python
def test_straight_line_hides_wheel_distance_error(mmk2_model, mmk2_data,
                                                  wheel_geometry):
    """⭐ 证明"为什么必须用转弯工况标定轮距"。"""
    from discoverse.robots_env.mmk2_base import MMK2Base

    odom_wrong, truth = drive(
        mmk2_model, mmk2_data, 1.0, 1.0,
        wheel_distance=MMK2Base.wheel_distance,          # 错误的 0.189
        wheel_radius=wheel_geometry["wheel_radius"],
    )
    pos_err = float(np.linalg.norm(odom_wrong[:2] - truth[:2]))
    assert pos_err < ODOM_POS_ATOL, "前提不成立：直线工况本应对轮距不敏感"
```

### 这条测试很特别：它断言「用错误的常量也能通过」

**这不是在测试代码正确性，是在测试「我的解释是对的」。**

我的解释是：

> 直线时 `Δs_r - Δs_l = 0`，**轮距被乘以 0**，所以错得再离谱也不影响直线里程计。

这条测试**把这个解释变成可执行的断言**。如果哪天这条测试红了，
说明我的解释错了（直线工况其实对轮距敏感），那么缺陷 Y 的整个分析都要重来。

📌 **工业 AGV 的常识：轮距标定必须用原地旋转，不能用直线跑。**
这条测试是这句话的形式化。

> ⭐ **测试不只用来验证代码，也可以用来固定「你对系统的理解」。**

## 5.7 ⭐⭐ 缺陷 Y 的 xfail（188-214 行）

```python
@pytest.mark.xfail(
    reason="缺陷 Y：MMK2Base.wheel_distance = 0.189，"
           "而 MJCF 实测轮距为 0.3265（±0.16325 × 2），错 1.73 倍。"
           "影响 4 个 ROS 遥操作文件的 cmd_vel 逆解。",
    strict=True,
)
def test_wheel_distance_constant_matches_model(wheel_geometry):
    from discoverse.robots_env.mmk2_base import MMK2Base
    assert MMK2Base.wheel_distance == pytest.approx(
        wheel_geometry["wheel_distance"], abs=1e-4)
```

### docstring 里记录了完整的实测数据

```
实测影响（原地旋转，4000 步）：
    wheel_distance=0.189   → yaw 推算 -4.6005 vs 真值 -2.6565，误差 1.944 rad (111°)
    wheel_distance=0.3265  → yaw 推算 -2.6631 vs 真值 -2.6565，误差 0.0066 rad
    改善 294 倍。
```

📌 **为什么把数据写进 docstring 而不只写在缺陷报告里？**

因为**代码和文档会分离**。半年后有人看到这条 xfail，
第一个问题是「这缺陷严重吗？值得修吗？」——
答案就在眼前，不用去翻文档。

### ⚠️ 为什么不直接修

docstring 里写了完整理由：

```
⚠️ 今天刻意不修，因为该变量的语义本身是矛盾的：
    - 里程计公式按"全轮距"用它：Δθ = (Δs_r - Δs_l) / L
    - 4 个 ROS 文件按"半轮距"用它：v_l = (v - ω·L) / r（少除以 2）
    只改数值会让其中一边从"错 73%"变成"错 50%"。
```

| 取值 | 里程计 | ROS 遥操作 |
|---|---|---|
| 0.189（现状） | 错 73% | 错 15.7% |
| 0.3265（"修正"） | ✅ 对 | **错 100%** |

> ⭐ **一个变量被两处按不同语义使用时，没有任何单一取值是对的。**
> 修法必须先**消除歧义**（重命名），再统一取值。

---

# 第六部分：`test_slide_lift.py` 逐行（134 行）

## 6.1 常量（22-30 行）

```python
LIFT_POS_ATOL = 0.010        # 实测稳态误差 6.06mm，取 10mm（约 65% 余量）
DROOP_PTP_ATOL = 1e-4        # 各高度误差极差，实测 < 1e-5
LIFT_MIN, LIFT_MAX = -0.04, 0.87
```

⚠️ **`LIFT_MIN = -0.04` 不是 0** —— CLAUDE.md 旧版写成 `[0, 0.87]`，
实测 `ctrlrange` 有 4cm 负向余量。

## 6.2 `settle_lift()`（32-39 行）

```python
def settle_lift(model, data, target, steps=LIFT_SETTLE_STEPS):
    adr = qpos_adr(model, "slide_joint")
    for _ in range(steps):
        data.ctrl[:] = 0.0
        data.ctrl[CTRL_LIFT] = target
        mujoco.mj_step(model, data)
    return float(data.qpos[adr])
```

`float(...)` 把 numpy 标量转成 Python 原生 float —— 让失败消息里的
输出更干净（`0.20606` 而不是 `np.float64(0.20606)`）。

## 6.3 两条「钉布局」测试（42-54 行）

```python
def test_lift_joint_is_not_qpos_2(mmk2_model):
    assert qpos_adr(mmk2_model, "slide_joint") == 9
```

**测试名字直接写出被纠正的错误**（`is_not_qpos_2`）。
下一个人看到这个名字就知道：曾经有人以为是 `qpos[2]`。

```python
def test_lift_ctrlrange_has_negative_margin(mmk2_model):
    lo, hi = mmk2_model.actuator_ctrlrange[CTRL_LIFT]
    assert (lo, hi) == pytest.approx((LIFT_MIN, LIFT_MAX), abs=1e-6)
```

📖 **`pytest.approx` 可以直接比较元组/列表** —— 逐元素比较。

## 6.4 定位精度测试（57-68 行）

```python
@pytest.mark.parametrize("target", [0.0, 0.2, 0.5, LIFT_MIN])
def test_lift_positioning_accuracy(mmk2_model, mmk2_data, target):
    """⚠️ 不含 0.87：该目标撞上关节上限被硬约束挡住，
       误差反而只有 0.4mm，不能代表伺服精度。"""
    actual = settle_lift(mmk2_model, mmk2_data, target)
    err = abs(actual - target)
    assert err < LIFT_POS_ATOL, f"目标 {target:.3f} m 实际 {actual:.5f} m，误差 {err*1000:.2f} mm"
```

### ⭐ 为什么刻意排除 0.87

实测：

```
target=0.870  →  err = 0.000399      ← 只有 0.4mm！
其他所有目标   →  err = 0.006063      ← 6.06mm
```

**0.87 是关节上限**，机器人被**硬约束**挡住，而不是被伺服**控制**到位。
把它放进「定位精度」测试会让平均精度**看起来更好**，
但那是假象 —— 测的不是同一个东西。

> ⭐ **样本里混进「因为别的原因恰好正确」的用例，会稀释测试的判别力。**

`{err*1000:.2f} mm` —— 把米转成毫米显示，人更容易判断严重程度。

## 6.5 ⭐⭐ 下垂一致性测试（71-92 行）

```python
def test_lift_droop_is_constant_bias_not_noise(mmk2_model, mmk2_model_data_factory):
    errors = []
    for target in (0.0, 0.2, 0.5):
        data = mmk2_model_data_factory()          # ← 每次全新
        errors.append(settle_lift(mmk2_model, data, target) - target)

    spread = float(np.ptp(errors))
    assert spread < DROOP_PTP_ATOL, f"各高度下垂不一致（极差 {spread:.2e}），可能存在卡滞"

    assert all(e > 0 for e in errors), f"下垂方向异常：{errors}"
```

### 📖 `np.ptp` = peak to peak

```python
np.ptp([1.0, 1.5, 1.2])       # → 0.5（最大值 - 最小值）
```

「极差」，衡量一组数的**离散程度**。

### ⭐⭐ 这条测试的价值

**「定位精度 < 10mm」抓不到的故障，这条能抓到。**

物理原理：重力下垂 = `负载 / kp`，**在各高度应当恒定**。

| 观察 | 推论 |
|---|---|
| 各高度误差相同 | ✅ 正常的重力下垂 |
| 某个高度突然不同 | ⚠️ **该处有卡滞 / 碰撞 / 机构干涉** |

而卡滞可能只让误差从 6.06mm 变成 8mm —— **仍然 < 10mm，精度测试是绿的**。

```python
assert all(e > 0 for e in errors)
```

**方向断言**：slide 越大躯干越低（4.7 已钉住），重力把它往下拽
→ 实际值总是比目标**大** → 误差恒为正。

符号反了说明升降语义被改过。

> ⭐ **误差的结构（一致性、方向）比误差的大小更有信息量。**

## 6.6 稳定时间测试（95-108 行）

```python
def test_lift_settles_within_budget(mmk2_model, mmk2_model_data_factory):
    early = settle_lift(mmk2_model, mmk2_model_data_factory(), 0.2, steps=2000)
    late  = settle_lift(mmk2_model, mmk2_model_data_factory(), 0.2, steps=5000)
    assert abs(early - late) < 1e-4
```

**注意两次都用全新的 `MjData`** —— 是两次**独立**的仿真，
不是「跑 2000 步后再跑 3000 步」。

📌 **这条测试保护 `LIFT_SETTLE_STEPS = 5000` 这个常量的合理性。**
如果哪天物理参数变了、系统响应变慢，5000 步不够稳，这条会红。

## 6.7 限幅测试（111-134 行）

```python
def test_out_of_range_command_is_clamped_in_physics(mmk2_model, mmk2_data):
    adr = qpos_adr(mmk2_model, "slide_joint")
    over = 2.0

    for _ in range(3000):
        mmk2_data.ctrl[:] = 0.0
        mmk2_data.ctrl[CTRL_LIFT] = over
        mujoco.mj_step(mmk2_model, mmk2_data)

    assert mmk2_data.ctrl[CTRL_LIFT] == pytest.approx(over)      # ctrl 未被改写
    assert mmk2_data.qpos[adr] <= LIFT_MAX + 1e-3                # 物理被限幅
```

### ⚠️ 两条断言方向相反，这是重点

```
ctrl 数组     →  保留原值 2.0        （MuJoCo 不改写你的输入）
qpos（物理）  →  被限制在 0.87        （施加的力被限幅）
```

📌 **别写 `assert data.ctrl[2] <= 0.87`** —— 那会失败。
`actuator_ctrllimited=True` 只影响**施加到关节的力**，不改写 `ctrl` 数组。

### ⚠️ 两条路径行为不同

```python
# 路径 A：直接操作 mj_data（本测试）
data.ctrl[2] = 2.0            # ctrl 里存的是 2.0

# 路径 B：走 MMK2Base.updateControl（mmk2_base.py:193）
self.mj_data.ctrl[:] = np.clip(action, ctrlrange[:,0], ctrlrange[:,1])
#                       ↑ 自己先 clip 了，ctrl 里存的是 0.87
```

**测试要写清用的哪条路径。**

---

# 第七部分：`test_dual_arm_collision.py` 逐行（152 行）

## 7.1 位形常量（33-39 行）

```python
POSE_COLLIDING = [0.0, -1.5, 1.5, 0.0, 0.0, 0.0]     # 双臂内收，会撞
POSE_SAFE      = [0.0,  0.0, 0.0, 0.0, 0.0, 0.0]     # 垂放，不撞
```

这两组是**实测出来的** —— 我先跑了一遍确认 `POSE_COLLIDING` 真的产生跨臂接触。

📌 **别凭想象写「应该会撞」的位形。**如果它其实不撞，
元测试就会红，而你会以为是检测器坏了。

## 7.2 `pose_arms()`（42-50 行）

```python
def pose_arms(model, data, left_q, right_q, slide=0.3, steps=SETTLE_STEPS):
    ctrl = data.ctrl.copy()
    ctrl[:] = 0.0
    ctrl[CTRL_LIFT] = slide
    ctrl[CTRL_LFT_ARM] = left_q
    ctrl[CTRL_RGT_ARM] = right_q
    step_with_ctrl(model, data, ctrl, steps)
    return cross_arm_contacts(model, data)
```

```python
ctrl = data.ctrl.copy()      # 先拷一份，得到正确长度(19)的数组
ctrl[:] = 0.0                # 再清零
```

📖 **为什么不直接 `np.zeros(19)`？**
可以，但 `.copy()` 保证长度**永远和模型一致** ——
如果将来模型加了执行器，这里自动跟上，不用改数字。

## 7.3 ⭐ 执行器布局钉死测试（53-90 行）

```python
def test_actuator_layout_is_pinned(mmk2_model):
    expected = [
        (0, "lft_wheel_motor"), (1, "rgt_wheel_motor"), (2, "lift"),
        (3, "head_yaw"), (4, "head_pitch"),
        (5, "lft_joint1"), (10, "lft_joint6"), (11, "lft_gripper"),
        (12, "rgt_joint1"), (17, "rgt_joint6"), (18, "rgt_gripper"),
    ]
    assert mmk2_model.nu == 19

    for idx, name in expected:
        actual = mujoco.mj_id2name(mmk2_model, mujoco.mjtObj.mjOBJ_ACTUATOR, idx)
        assert actual == name, f"执行器 {idx} 应为 {name}，实为 {actual}"

    for idx in (CTRL_LFT_GRIPPER, CTRL_RGT_GRIPPER):
        assert mmk2_model.actuator_trntype[idx] == mujoco.mjtTrn.mjTRN_TENDON

    for idx in range(CTRL_WHEELS.start, CTRL_WHEELS.stop):
        lo, hi = mmk2_model.actuator_ctrlrange[idx]
        assert (lo, hi) == pytest.approx((-35.0, 35.0))
```

### 三组断言，各管一件事

| 断言 | 保护什么 |
|---|---|
| 名字 ↔ 下标 | CLAUDE.md 的布局表 |
| `mjTRN_TENDON` | 「夹爪是 1 个执行器不是 2 个」 |
| `ctrlrange ±35` | `test_differential_drive` 的力矩假设 |

### ⭐ 只挑边界索引验证

```python
(5, "lft_joint1"), (10, "lft_joint6"),      # 只验首尾，不验 6,7,8,9
```

**首尾对了，中间不会错** —— MJCF 是顺序定义的。
全列出来会让测试冗长而不增加判别力。

📌 **这条测试的真正作用：让「MJCF 改了但文档没改」立刻可见。**

## 7.4 ⭐⭐ 归属逻辑元测试（93-117 行）

```python
def test_arm_side_resolves_unnamed_geoms(mmk2_model):
    named = sum(1 for i in range(mmk2_model.ngeom)
                if mujoco.mj_id2name(mmk2_model, mujoco.mjtObj.mjOBJ_GEOM, i))
    assert named < mmk2_model.ngeom, "前提变了：geom 现在都有名字了，本方案可简化"

    sides = [arm_side(mmk2_model, i) for i in range(mmk2_model.ngeom)]
    assert sides.count("L") > 0
    assert sides.count("R") > 0

    unnamed_resolved = sum(
        1 for i in range(mmk2_model.ngeom)
        if sides[i] and not mujoco.mj_id2name(mmk2_model, mujoco.mjtObj.mjOBJ_GEOM, i)
    )
    assert unnamed_resolved > 0, "无名 geom 全部未能归属 —— 退化为按名字匹配"
```

### ⭐⭐ 最后那条断言是精髓

```python
assert unnamed_resolved > 0
```

**为什么不能只断言「有 geom 被归到左臂」？**

因为那 11 个**有名字**的 geom 也可能被归上 ——
于是即使 `arm_side` 退化成「只认有名字的」，前面的断言仍然通过。

**必须专门断言「有无名 geom 被成功归属」**，
才能证明「走 body 祖先链」这个方案真的在起作用。

> ⭐ **测试要针对「你真正依赖的那个性质」，而不是它的一个较弱的推论。**

### 📖 `sum(1 for ... if ...)` 惯用法

```python
sum(1 for i in range(n) if 条件)      # 数满足条件的元素个数
```

生成器表达式，不构造中间列表，内存友好。

## 7.5 ⭐⭐ 检测器元测试（120-131 行）

```python
def test_self_collision_detector_actually_detects(mmk2_model, mmk2_data):
    """⭐⭐ 核心元测试：已知会碰的位形必须被检出。

    这是下面"安全位形"测试的前提。若本测试通过而安全测试也通过，
    后者才可信；否则"没检出碰撞"可能只是检测器坏了。
    """
    hits = pose_arms(mmk2_model, mmk2_data, POSE_COLLIDING, POSE_COLLIDING)
    assert hits, "检测器失效：已知碰撞位形却报告无跨臂接触"
```

### ⭐⭐⭐ 为什么这条测试是全文最能体现测试功力的

计划文档只写了「安全位形不应有碰撞」这一半：

```python
if collision: pytest.fail(...)      # 计划文档
```

**只写这一半是不够的**，因为它通过时有两种可能：

```
① 真的没碰            ✅ 我们想要的结论
② 检测器坏了          ❌ 但测试无法区分
```

**而计划文档的检测器恰恰就是坏的**（字符串匹配恒为 False）——
所以它的测试永远通过，且从未检测过任何东西。

📌 **元测试（meta-test）= 测试「测试本身有效」的测试。**

```
元测试通过  →  检测器能工作
     ↓
安全测试通过 →  这才真的说明「安全」
```

```python
assert hits, "..."
```

📖 **空集合是 falsy** —— `assert hits` 等价于 `assert len(hits) > 0`，
更 Pythonic。

## 7.6 安全位形测试（134-142 行）

```python
def test_safe_pose_has_no_self_collision(mmk2_model, mmk2_data):
    hits = pose_arms(mmk2_model, mmk2_data, POSE_SAFE, POSE_SAFE)
    assert not hits, f"垂放位形出现意外自碰撞：{hits}"
```

失败消息里带上 `{hits}` —— 直接告诉你**哪两个部件**碰了，不用再去调试。

## 7.7 地面接触筛选测试（145-152 行）

```python
def test_ground_contacts_exist_but_are_not_self_collision(mmk2_model, mmk2_data):
    hits = pose_arms(mmk2_model, mmk2_data, POSE_SAFE, POSE_SAFE)
    assert mmk2_data.ncon > 0, "机器人应当与地面有接触"
    assert not hits, "地面接触被误判为自碰撞"
```

### 两条断言构成一个「夹逼」

```
ncon > 0        →  确实【有】接触（机器人站在地上）
not hits        →  但【没有】跨臂接触
```

**如果有人把 `cross_arm_contacts` 简化成 `return data.ncon > 0`**，
第二条断言会红。

📌 **这条测试保护的是「筛选逻辑」本身。**

---

# 第八部分：度量脚本逐行（123 行）

## 8.1 为什么是脚本不是测试

模块 docstring 写了 5 条理由，核心两条：

```
1. ⭐ 分母口径未定义时，阈值可以被"选"成任何结论：
       重叠 / 单臂可达  = 44.9% ~ 48.4%   → 远超 30%
       重叠 / 并集      = 29.0% ~ 31.8%   → 骑在 30% 线上
2. ⭐ 在"重叠/并集"口径下，结论对采样分辨率敏感：
       --step 0.15 → 29.0%（断言失败）
       --step 0.06 → 31.8%（断言通过）
```

> ⭐ **红绿取决于测试自己的参数，而非机器人有没有问题 —— 这是 flaky 断言。**
> 只不过随机源不是时序或并发，是**测试作者选的一个常数**。

## 8.2 `build_grid()`（44-49 行）

```python
def build_grid(x_range, y_range, z_range, step):
    axes = [np.arange(lo, hi + step/2, step) for lo, hi in (x_range, y_range, z_range)]
    return np.array(list(itertools.product(*axes))), axes
```

### 📖 `hi + step/2` 是干嘛的

```python
np.arange(0, 0.8, 0.1)          # → [0, 0.1, ..., 0.7]  ⚠️ 不含 0.8！
np.arange(0, 0.85, 0.1)         # → [0, 0.1, ..., 0.8]  ✅
```

`np.arange` **不含终点**。加 `step/2` 保证终点被包含，
而且不会因浮点误差多出一个点。

### 📖 `itertools.product`

```python
list(itertools.product([1,2], [3,4]))
# → [(1,3), (1,4), (2,3), (2,4)]      笛卡尔积
```

`product(*axes)` 把三个轴的所有组合生成出来 = 三维网格的全部点。

`*axes` 是**解包**：`product(axes[0], axes[1], axes[2])`。

## 8.3 `reachable_mask()`（52-67 行）

```python
def reachable_mask(solver, points, arm, slide, rotation):
    mask = np.zeros(len(points), dtype=bool)
    for i, point in enumerate(points):
        try:
            solver.armIK_wrt_footprint(point, rotation, arm, slide)
        except ValueError:
            continue
        except Exception as exc:  # noqa: BLE001
            print(f"  [warn] 点 {point} 抛出非预期异常 {type(exc).__name__}: {exc}")
            continue
        mask[i] = True
    return mask
```

### ⭐ 两个 `except` 分层，语义不同

```python
except ValueError:      continue                    # 预期：不可达
except Exception as exc: print(warn); continue      # 意外：但要【可见】
```

📌 **不要用一个裸 `except: continue` 把两者混为一谈** ——
那样的话，如果 IK 因为别的原因（比如传参错误）抛异常，
你会得到一张「全不可达」的图，**而且完全不知道为什么**。

对比上游 `mmk2_ik.py:15` 的裸 `except:` —— 那正是缺陷 AA 的一部分。

### 📖 `# noqa: BLE001`

告诉 ruff：「这一行我故意捕获宽泛异常，别报警」。

`BLE001` = blind-except。**加 `noqa` 时必须说明理由**（注释里写了
「度量脚本，任何异常都记为不可达但要可见」）。

## 8.4 `main()` 与结果输出（70-121 行）

```python
parser.add_argument("--step", type=float, default=0.08, help="网格步长（m）")
```

📖 **`argparse` 让脚本可配置** —— 而不是改代码里的常量。
这正是「可以横向对比不同分辨率」的前提。

```python
masks = {}
for arm, label in (("l", "左臂"), ("r", "右臂")):
    masks[arm] = reachable_mask(solver, points, arm, args.slide, rotation)
```

```python
overlap = masks["l"] & masks["r"]        # 布尔数组的【与】= 交集
union   = masks["l"] | masks["r"]        # 【或】= 并集
```

📖 **numpy 布尔数组支持集合运算**：

```python
a = np.array([True, True, False])
b = np.array([True, False, False])
a & b      # → [True, False, False]     逐元素与
a | b      # → [True, True, False]      逐元素或
a.sum()    # → 2                        True 算作 1
```

⚠️ **用 `&` `|` 不是 `and` `or`** —— 后者对数组会报
「truth value is ambiguous」。

```python
ratio = n_overlap / denom if denom else float("nan")
```

**防除零**：`denom` 为 0 时返回 `nan` 而不是崩溃。
度量脚本应当在退化情况下**继续输出**，而不是中断。

## 8.5 ⭐ 结尾的免责声明（116-120 行）

```python
print("\n注：本脚本不设阈值判定 —— 结论取决于选哪个分母。")
print("    比值对 --step 较稳健（0.10 与 0.06 两档实测一致），")
print("    但绝对体积随步长抖动约 10%，且过粗的网格会抹平左右臂的真实不对称。")
print("    宜用于横向比较（如改动 MJCF 前后同参数对比），不作绝对结论。")
```

### ⚠️ 我在这里改过一次错误的说法

**初版**我写的是「数字随 --step 变化（网格越粗越失真）」——
**没验证就写了**。

实测三档后发现**比值相当稳定**：

| 步长 | 重叠/单臂 | 重叠/并集 |
|---|---|---|
| 0.15 | 44.9% | 29.0% |
| 0.10 | **48.1%** | 31.5% |
| 0.06 | **48.1%** | 31.8% |

**0.10 和 0.06 完全相同。**因为比值的分子分母**同步失真，误差抵消了**。

📌 **绝对体积确实抖 ~10%，但比值不抖。**
我把对绝对值的直觉，错误地套用到了比值上。

> ⭐⭐ **这是我今天第 4 次「没测就写」。**
> 而且最隐蔽 —— **理由错了，但结论（不该写成断言）是对的**。
> 结果看起来没问题，**没有任何东西会提醒你回头**。

---

## 附录：全部命令速查

```bash
# ---------- 环境 ----------
PY=~/miniconda3/envs/discoverse/bin/python
export MUJOCO_GL=osmesa                    # 无显示器环境

# ---------- 测试 ----------
env -u PYTHONPATH MUJOCO_GL=osmesa $PY -m pytest tests/ -q            # 全量
env -u PYTHONPATH MUJOCO_GL=osmesa $PY -m pytest tests/mobile_manipulation/ -q
env -u PYTHONPATH MUJOCO_GL=osmesa $PY -m pytest tests/ -k "odometry" -q   # 名字筛选
env -u PYTHONPATH MUJOCO_GL=osmesa $PY -m pytest tests/mobile_manipulation/ --collect-only -q

# ---------- lint ----------
env -u PYTHONPATH $PY -m ruff check tests/          # 严格，必须全绿

# ---------- Docker（重建，不挂载！）----------
docker build -q -f discoverse/docker/Dockerfile.test -t discoverse:test .
docker run --rm discoverse:test pytest tests/ -q

# ---------- 度量脚本 ----------
env -u PYTHONPATH MUJOCO_GL=osmesa $PY scripts/mmk2_workspace_overlap.py --step 0.1

# ---------- 查执行器/关节表 ----------
env -u PYTHONPATH MUJOCO_GL=osmesa $PY -c "
import mujoco, os
from discoverse import DISCOVERSE_ROOT_DIR
m = mujoco.MjModel.from_xml_path(os.path.join(DISCOVERSE_ROOT_DIR,'models/mjcf/mmk2_floor.xml'))
for i in range(m.nu):
    print(i, mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_ACTUATOR, i), m.actuator_ctrlrange[i])
"

# ---------- 量真实轮距（缺陷 Y 的证据）----------
env -u PYTHONPATH MUJOCO_GL=osmesa $PY -c "
import mujoco, os
from discoverse import DISCOVERSE_ROOT_DIR
m = mujoco.MjModel.from_xml_path(os.path.join(DISCOVERSE_ROOT_DIR,'models/mjcf/mmk2_floor.xml'))
for nm in ['lft_wheel_joint','rgt_wheel_joint']:
    jid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, nm)
    print(nm, m.body_pos[m.jnt_bodyid[jid]])
"
# → ±0.16325 → 轮距 0.3265，而 MMK2Base.wheel_distance = 0.189
```
