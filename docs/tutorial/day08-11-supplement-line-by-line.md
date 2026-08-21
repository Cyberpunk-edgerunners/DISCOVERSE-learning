# Day 8-11 补充 — 逐行解析：Docker 测试镜像与 GitHub Actions CI

> 配套 [day08-09-docker-test-image.md](day08-09-docker-test-image.md)、[day10-11-github-actions.md](day10-11-github-actions.md)
> 用途：**查阅型文档**，不用从头读。看不懂哪一行就跳到哪一节。
> 覆盖：`Dockerfile.test` 99 行 + `.dockerignore` 70 行 + `requirements-test.txt` 66 行 + `ci.yml` 184 行 + `test_recorder.py` 254 行 + 全部命令行
> 面向：**没用过 Docker、没配过 CI 的读者**。每个概念从零讲起。

---

## 目录

- [第一部分：预备概念（10 个，不懂这些后面全是天书）](#第一部分预备概念10-个)
- [第二部分：`requirements-test.txt` 逐行（66 行）](#第二部分requirements-testtxt-逐行66-行)
- [第三部分：`.dockerignore` 逐行（70 行）](#第三部分dockerignore-逐行70-行)
- [第四部分：`Dockerfile.test` 逐行（99 行）](#第四部分dockerfiletest-逐行99-行)
- [第五部分：`ci.yml` 逐行（184 行）](#第五部分ciyml-逐行184-行)
- [第六部分：`test_recorder.py` 逐行（19% → 94% 那一步）](#第六部分test_recorderpy-逐行19--94-那一步)
- [第七部分：命令行逐字解析](#第七部分命令行逐字解析)
- [第八部分：面试问答速查](#第八部分面试问答速查)
- [第九部分：企业开发扩展](#第九部分企业开发扩展)

---

# 第一部分：预备概念（10 个）

## 1.1 Docker 是什么，为什么测试需要它

### 一句话

**Docker 把「操作系统 + 依赖 + 代码」打包成一个可以在任何机器上原样跑起来的东西。**

### 它解决的问题

```
你的机器：  Ubuntu 22 + Python 3.10 + 装了 libosmesa  →  测试全绿 ✅
同事机器：  macOS    + Python 3.12 + 没装 libosmesa   →  测试全红 ❌
CI 服务器： Ubuntu 24 + Python 3.11 + ???            →  ？？？
```

这就是著名的 **「在我这儿能跑」（works on my machine）** 问题。

Docker 的解法：**别用你的机器，用我打包好的这个。**

### 三个核心概念（必须分清）

| 概念 | 类比 | 说明 |
|---|---|---|
| **Dockerfile** | **菜谱** | 一份文本文件，写「怎么造这个环境」 |
| **镜像（image）** | **做好的预制菜** | 按菜谱造出来的只读产物 |
| **容器（container）** | **端上桌的那盘菜** | 镜像跑起来的一个实例，可以有很多个 |

```bash
docker build -f Dockerfile.test -t discoverse:test .    # 菜谱 → 镜像
docker run --rm discoverse:test pytest tests/ -q        # 镜像 → 容器（跑一次）
```

📌 **镜像是只读的、可分发的；容器是一次性的。**
`--rm` = 跑完就删掉容器（镜像还在）。

---

## 1.2 Docker 的分层与缓存 ⭐ 决定 Dockerfile 怎么写

**Dockerfile 里每一条指令产生一「层」（layer）。**

```dockerfile
FROM python:3.10-slim          # 第 1 层
RUN apt-get install ...        # 第 2 层
COPY requirements.txt /tmp/    # 第 3 层
RUN pip install -r ...         # 第 4 层
COPY . /workspace/             # 第 5 层
```

**Docker 会缓存每一层。** 重新 build 时：

```
第 1 层：输入没变 → 用缓存 ⚡
第 2 层：输入没变 → 用缓存 ⚡
第 3 层：requirements.txt 没变 → 用缓存 ⚡
第 4 层：上一层是缓存、命令没变 → 用缓存 ⚡
第 5 层：源码改了 → 重新执行 🐌
```

### ⭐ 关键规则：一层失效，后面全部失效

```
如果第 3 层变了 → 第 4、5 层的缓存全部作废，必须重跑
```

**这直接决定了 Dockerfile 的写法**：

```dockerfile
# ❌ 错的写法
COPY . /workspace/                              # 源码天天变
RUN pip install -r requirements-test.txt        # → 每次都重装依赖（几分钟）

# ✅ 对的写法（本项目）
COPY requirements-test.txt /tmp/                # 依赖清单很少变
RUN pip install -r /tmp/requirements-test.txt   # → 缓存命中
COPY . /workspace/                              # 源码变了只影响这层
```

📌 **原则：变化频率低的放前面，变化频率高的放后面。**
改一行代码的重建时间：从几分钟 → 几秒。

---

## 1.3 什么是 CI（持续集成）

**CI = Continuous Integration**：每次提交代码，自动跑一遍测试。

### 没有 CI 的世界

```
你：改代码 → 本地跑测试 → 绿 → push
同事：拉下来 → 红了
你：「我这儿是绿的啊」
```

原因可能是：你忘了跑某个测试、你的环境有个同事没有的包、你没提交某个文件……

### 有 CI 的世界

```
你：push
   ↓
GitHub 自动：在一台干净的机器上拉代码 → 装依赖 → 跑测试
   ↓
绿 → PR 可以合并
红 → PR 被挡住，并且告诉你哪条测试挂了
```

### ⭐ CI 真正值钱的地方（不是「自动跑测试」）

很多人以为 CI 的价值是「省得手动跑」。**不是。**

**CI 的核心价值是：它在一台你无法污染的干净机器上跑。**

```
你的机器：装了 50 个包，其中 10 个你已经忘了为什么装
CI 机器：  每次都从零开始
```

📌 **所以 CI 会发现一类你本地永远发现不了的 bug：依赖声明不完整。**

**本项目的缺陷 L′ 就是这么被抓到的**（详见 [1.7](#17-eager-import-链与缺陷-l)）。

---

## 1.4 GitHub Actions 的四个概念

```yaml
name: CI                          # ① workflow（流水线）的名字

on:                               # ② 触发条件
  push:
    branches: [main]

jobs:                             # ③ job（作业）
  unit:
    runs-on: ubuntu-latest        #    每个 job 一台独立的虚拟机
    steps:                        # ④ step（步骤）
      - uses: actions/checkout@v4 #    用别人写好的动作
      - run: pytest tests/        #    或者直接跑命令
```

| 层级 | 说明 |
|---|---|
| **workflow** | 一个 `.github/workflows/*.yml` 文件 = 一条流水线 |
| **job** | **一台独立的干净虚拟机**。job 之间默认并行、不共享任何东西 |
| **step** | job 里的一步。**同一 job 内的 step 共享文件系统和工作目录** |

### ⭐ 「每个 job 是独立虚拟机」的三个后果

```yaml
jobs:
  a:
    steps:
      - run: pip install foo      # 装在 a 的机器上
  b:
    steps:
      - run: python -c "import foo"   # ❌ 报错！b 是另一台机器
```

1. **job 之间要重复装环境**（所以本项目每个 job 都有自己的安装步骤）
2. **job 之间要传文件必须用 artifact**（上传/下载）
3. **job 默认并行** —— 想串行要用 `needs:`

📌 这就是 `ci.yml` 第 4-5 行注释说的：

> 设计原则：每个 job 是一台独立的干净虚拟机，job 之间不共享任何东西，各自从零备环境。

---

## 1.5 三种渲染后端 ⭐ 本项目 Docker/CI 的核心矛盾

MuJoCo 要画图（渲染相机画面），有三种方式：

| `MUJOCO_GL` | 全称 | 需要显示器 | 需要 GPU | 速度 | 适用 |
|---|---|---|---|---|---|
| `glfw` | OpenGL + 窗口 | ✅ **需要** | 需要 | 快 | 本地开发看画面 |
| **`osmesa`** | **Off-Screen Mesa** | ❌ 不需要 | ❌ 不需要 | **慢（纯 CPU）** | **CI / 容器** |
| `egl` | GPU 无头渲染 | ❌ 不需要 | ✅ **需要** | 快 | GPU 服务器 |

### 为什么这是核心矛盾

```
上游的 discoverse/docker/Dockerfile 第 58 行：ENV MUJOCO_GL=glfw
                                                            ↑
                              容器里没有显示器（没有 $DISPLAY）→ 一渲染就崩
```

**所以上游那个镜像不能直接拿来跑测试。** 这就是要新写 `Dockerfile.test` 的原因。

📌 **本项目做了两个镜像**：
- `Dockerfile.test` → `osmesa`（CPU，给 GitHub Actions 免费 runner）
- `Dockerfile.test.gpu` → `egl`（GPU，给 Day 12 的 Jenkins 自建机器）

---

## 1.6 pip 依赖的两种声明方式

| | `pyproject.toml` 的 `dependencies` | `requirements-test.txt` |
|---|---|---|
| 版本写法 | `numpy>=1.20.0`（**范围**） | `numpy==2.2.6`（**钉死**） |
| 用途 | **发布给别人用** —— 要兼容 | **复现一个环境** —— 要确定 |
| 谁读它 | `pip install -e .` | `pip install -r requirements-test.txt` |

### ⭐ 为什么测试镜像要钉死版本

```python
# requirements-test.txt 第 11-16 行的理由
版本策略：全部钉死（==）而非 >=。
  测试镜像的核心价值是可复现。参考缺陷 #3：
  pytest 超时未生效，怀疑是 pytest 9.1.1 与
  pytest-timeout 2.4.0 的版本兼容问题，根因至今未定位。
  版本浮动会让这类 bug 时有时无，更难查。
```

📌 **「版本浮动会让 bug 时有时无」是钉死版本的核心理由。**
一个只在某些版本组合下出现的 bug，如果版本每次都不同，你**永远查不出来**。

**代价**：要手工升级。文档里写「对测试环境来说这是优点」——
因为升级变成一个**有意识的决定**，而不是某天 CI 突然红了。

---

## 1.7 eager import 链与缺陷 L′ ⭐ 本项目最有教学价值的缺陷

### 什么是 eager import

```python
# discoverse/universal_manipulation/__init__.py 第 4-16 行
from .task_base import UniversalTaskBase
from .mink_solver import MinkIKSolver
from .recorder import recoder_single_arm
from .randomization import SceneRandomizer
# ... 共 7 个子模块，全部在 __init__ 里主动加载
```

**后果**：

```python
import discoverse.universal_manipulation
    ↓ 触发 __init__.py
    ↓ 加载全部 7 个子模块
    ↓ mink_solver.py:8   import mink        ← 缺一个
    ↓ recorder.py:6      import av          ← 缺一个
    ↓ randomization.py:10 import OpenGL.GL  ← 缺一个
    ↓
ModuleNotFoundError —— 连 import 都过不去
```

📌 **关键点**：**不是「运行某个功能时才报错」，而是「连 import 都失败」。**
任何一个子模块的模块级依赖缺失，整个包就废了。

### 缺陷 L 和 L′ 的完整故事 ⭐⭐

**这个缺陷炸了三次，每次都是同一个根因，但暴露在不同的环境**：

```
Day 6-7：本地发现缺 mink/quadprog  →  补上  →  本地绿 ✅
          ↑ 「看见什么缺就补什么」，没有走完整条 import 链

Day 8-9：进干净容器  →  💥 缺 av  →  补上  →  💥 缺 PyOpenGL  →  补上  →  💥 缺 pillow
          ↑ 容器是干净的，暴露了本地「碰巧装了」的包

Day 10：进 CI runner  →  💥 缺 pyyaml
          ↑ pip install -e . 只装核心组，而这 4 个包被错误地放在 optional 组里
```

**记录在 `pyproject.toml` 第 53-57 行**：

```python
⚠️ 修改前请先读 docs/defect-report.md 的缺陷 L / L′：
   Day 6-7 只补了 mink/quadprog（看见什么缺就补什么），
   没有走完整条链，导致 Day 8-9 在干净容器里、
   Day 10 在 CI runner 上又各炸一次。
```

### ⭐⭐ 「幸运的间接依赖」—— 最阴的一类问题

```python
# pyproject.toml 第 72-78 行
# randomization.py:10 —— `import OpenGL.GL as gl`
# ⚠️ 此前是靠 mujoco 间接拽进来的，属于「幸运的间接依赖」：
#    mujoco 哪天不再依赖它，这里就崩。显式声明即不再靠运气。
"PyOpenGL>=3.1.0",
# randomization.py:11 —— `from PIL import Image`
# ⚠️ 同上，此前靠 matplotlib 间接拽进来。
"pillow>=8.0.0",
```

**什么叫「幸运的间接依赖」**：

```
你的代码 import PIL
    ↓
你没声明 pillow
    ↓
但 matplotlib 依赖 pillow，而你装了 matplotlib
    ↓
所以 PIL 碰巧能 import ✅  ← 靠运气
    ↓
某天 matplotlib 换了实现不再依赖 pillow  →  💥 你的代码崩了
                                              而你什么都没改
```

📌 **这是依赖管理里最难查的一类问题**，因为：
- 本地永远不会暴露（你装了一堆东西）
- 只在**干净环境**下暴露
- 报错时看起来像是「第三方库的问题」

**解法只有一个：你 import 什么，就显式声明什么。**

**面试价值**：「我发现项目里有两个包是靠间接依赖『碰巧能用』的 ——
`PyOpenGL` 靠 mujoco 拽进来，`pillow` 靠 matplotlib 拽进来。
上游哪天改了传递依赖，这里就会崩，而我们什么都没改。
我把它们显式声明了 —— **不是加依赖，是把靠运气变成靠契约**。」

---

## 1.8 ⭐ 静默降级：本项目 Docker/CI 部分的核心主题

**这两天遇到的坑有一个共同模式：错误不会让你崩溃，而是让你「看起来正常」。**

### 三个真实案例

| 案例 | 表面现象 | 真相 |
|---|---|---|
| **漏装 `libglib2.0-0`** | `106 passed`（而非 113） | 7 个用例 ERROR，但数字看着很正常 |
| **`.dockerignore` 排除 `models/`** | **全绿** ✅ | `pytest.skip` 兜住了，**一个 MJCF 都没真正加载** |
| **CI 跑 `tests/kinematics`** | `5 passed` 绿灯 | 那是**空目录**，跑的是别的东西 |

### ⭐ 为什么「全绿」比「全红」更危险

```
全红 → 你会去查 → 找到问题
全绿 → 你会合并 → 问题带到生产
```

📌 **本项目的对策：记住基线数字，每次比对。**

```
本机基线：113 passed, 4 skipped, 45 deselected, 10 xfailed
容器必须：113 passed, 4 skipped, 45 deselected, 10 xfailed
          ↑ 一个都不能差
```

**这被写进了 `Dockerfile.test` 第 9-10 行**：

```dockerfile
# 验收：输出必须是 113 passed, 4 skipped, 45 deselected, 10 xfailed
#      —— 与本机 `source scripts/dev/env.sh && $PY -m pytest tests/ -q` 一致
```

📌 **「验收标准写在 Dockerfile 注释里」是个好习惯** ——
下一个人 build 出来数字不对，立刻知道有问题。

**通用方法论**：

> **绿灯不等于验证通过。要同时检查「跑了多少」和「跳过了多少」。**
> `-ra` 参数会汇总所有 skip/xfail 的原因，别让它们隐形。

---

## 1.9 `skip` 与「测试变绿但啥也没测」

```python
# tests/conftest.py 第 60-61 行
if not os.path.exists(key):
    pytest.skip(f"MJCF 不存在，跳过: {key}")
```

**这行代码的本意是好的**：文件不存在时，明确跳过而非报一个看不懂的错。

**但它同时制造了一个陷阱**：

```
.dockerignore 排除了 models/
    ↓
容器里 MJCF 文件不存在
    ↓
pytest.skip 静默兜住
    ↓
测试「全绿」，但一个模型都没加载过
```

📌 **`.dockerignore` 第 9-11 行专门警告了这件事**：

```
⚠️ 排错时注意：这里挡掉的东西，容器里就是「文件不存在」，
   而 tests/conftest.py 遇到 MJCF 不存在会 pytest.skip ——
   也就是「测试变绿但啥也没测」。改动本文件后必须比对 skip 数。
```

**「改动本文件后必须比对 skip 数」** —— 这是唯一可靠的检查方法。

---

## 1.10 测试覆盖率：19% → 94% 是怎么算的

```bash
pytest tests/ --cov --cov-report=term-missing
```

### 覆盖率的定义

```
行覆盖率 = 被测试执行过的代码行数 / 总代码行数
```

### ⚠️ 分母的选择决定了这个数字（本项目的关键配置）

```toml
# pyproject.toml 第 303-308 行
# 覆盖率作用域：只统计正在测试的模块。
# 不要写 --cov=discoverse —— policies/ 下 237 个策略学习文件会把
# 分母稀释到 2-3%，数字失去指导意义。
[tool.coverage.run]
source = ["discoverse/universal_manipulation"]
```

**实测对比**（`ci.yml` 第 94-96 行、`day10-11` 教程 Step 3.3）：

| 写法 | 分母 | 覆盖率 |
|---|---|---|
| `--cov=discoverse` | 2584 行 | **28%** |
| `--cov`（读配置） | 967 行 | **41%** |

**同一份测试，两个数字。** 差别只在于「统计谁」。

📌 **所以简历上写「94%」必须说清楚是什么的 94%** ——
本项目指的是 **`recorder.py` 这个模块**（Day 8-9 的 `c0b4561` commit：19% → 94%），
不是整个仓库。

**面试务必主动澄清**：「我说的 94% 是 `recorder.py` 这个核心模块的行覆盖率，
从 19% 提到 94%。整个 `universal_manipulation` 包是 41%，
而如果按整个 `discoverse` 算是 28% —— **分母不同数字完全不同，
所以报覆盖率必须同时报口径**。」

### ⭐ 覆盖率是下限指标，不是质量证明

```python
def divide(a, b):
    return a / b

def test_divide():
    assert divide(4, 2) == 2      # ✅ 100% 行覆盖率！
                                   # ❌ 但没测 b=0
```

📌 **100% 覆盖率的代码仍然可以充满 bug。**
覆盖率只能告诉你「**哪些代码肯定没测**」，不能告诉你「测得好不好」。

**更诚实的指标**：分支覆盖率（`--cov-branch`）、变异得分（见 Day 3-5 补充 1.4）。

---

# 第二部分：`requirements-test.txt` 逐行（66 行）

## 2.1 为什么单独一个文件（第 4-9 行）

```
# 为什么单独一个文件，而不是直接 pip install -e .：
#   1. Docker 分层缓存：依赖清单很少变，源码天天变。
#      先 COPY 这个文件装依赖，再 COPY 源码，
#      改代码时能复用依赖层缓存，重建从几分钟变几秒。
#   2. 这里只列「跑测试」需要的，比 pyproject.toml 的
#      完整依赖窄，镜像更小。
```

**两个理由，第 1 个是关键**（原理见 [1.2](#12-docker-的分层与缓存-⭐-决定-dockerfile-怎么写)）。

如果直接 `COPY . && pip install -e .`：
```
改一行代码 → COPY 层失效 → pip install 层失效 → 重装全部依赖（几分钟）
```

---

## 2.2 版本钉死策略（第 11-17 行）⭐

```
# 版本策略：全部钉死（==）而非 >=。
#   测试镜像的核心价值是可复现。参考缺陷 #3：
#   pytest 超时未生效，怀疑是 pytest 9.1.1 与
#   pytest-timeout 2.4.0 的版本兼容问题，根因至今未定位。
#   版本浮动会让这类 bug 时有时无，更难查。
#   代价是要手工升级 —— 对测试环境来说这是优点。
```

### ⭐ 「根因至今未定位」这句话很重要

**这是一个诚实的记录**：有个 bug 我没查出来，但我知道版本浮动会让它更难查。

```
版本浮动 + 时有时无的 bug = 永远查不出来
版本钉死 + 时有时无的 bug = 至少能确定不是版本问题
```

📌 **钉死版本不是为了「稳定」，是为了「排除一个变量」。**
调试的第一原则是**减少变量**。

### 「代价是要手工升级 —— 对测试环境来说这是优点」

| | 浮动版本 | 钉死版本 |
|---|---|---|
| 升级 | 自动（下次 build 就变了） | 手工改文件 |
| 何时发现新版本有问题 | **CI 突然红了，不知道为什么** | 你改的那一刻 |

📌 **让变更成为一个有意识的决定**，而不是「某天早上 CI 莫名其妙红了」。

---

## 2.3 依赖分组与注释（第 19-49 行）

```
# ---- 测试框架 ----
pytest==9.1.1
pytest-cov==7.1.0          # 覆盖率，pyproject.toml 里配了 [tool.coverage]
pytest-timeout==2.4.0      # MuJoCo 最常见的失败模式是死循环而非抛异常
coverage==7.15.2

# ---- 仿真核心 ----
mujoco==3.10.0
numpy==2.2.6
scipy==1.15.3

###------补充：eager import 链的全部硬依赖
# ---- IK 求解链路 ----
# universal_manipulation/__init__.py 会主动加载 mink_solver，
# 而 mink_solver.py:8 是模块级 import mink —— 缺失则整个包
# import 即失败（这是 Day 6-7 的缺陷 L）。
mink==1.2.0
quadprog==0.1.13           # mink_solver.py:45 的默认求解后端
pyyaml==6.0.3
av==17.1.0
PyOpenGL==3.1.10
pillow==12.2.0
```

### ⭐ 每个依赖都注明「为什么需要它」

```python
pytest-timeout==2.4.0      # MuJoCo 最常见的失败模式是死循环而非抛异常
quadprog==0.1.13           # mink_solver.py:45 的默认求解后端
```

📌 **注明理由的依赖清单，才能被安全地清理。**

没有注释的依赖清单，三个月后没人敢删任何一行 ——
「这个是干嘛的？不知道，别动」。这就是依赖膨胀的根源。

**企业实践**：注释里写**具体的文件:行号**（`mink_solver.py:45`）——
以后想验证「还需要吗」，直接去那一行看。

### `###------补充：eager import 链的全部硬依赖`

这行标记很有意思 —— **它记录了「这一组是后来补的」**。

对应 [1.7](#17-eager-import-链与缺陷-l) 的故事：Day 6-7 补了 mink/quadprog，
Day 8-9 在容器里又炸了三次，才把剩下的补齐。

---

## 2.4 ⭐ 「没有装的，以及理由」（第 52-66 行）

```
# ============================================================
# 没有装的，以及理由：
#
#   pytest-xdist / pytest-repeat / pytest-json-report
#     → Day 5 的 flake 采样实验用（--count=50 -n 8），
#       日常回归不需要。以后要在容器里跑 flake 实验再加。
#
#   torch / gaussian_renderer
#     → 3DGS 渲染和策略学习用，测试完全不涉及。
#       torch 的 CUDA 版约 2.5 GB，是原镜像最大的一块。
# ============================================================
```

### ⭐⭐ 这一段是全文件最值钱的部分

**大多数依赖清单只记录「装了什么」，不记录「没装什么、为什么」。**

后果：
```
新人：「这个镜像怎么跑不了 flake 实验？」
    ↓ 没有记录
新人：花半天排查，最后发现是缺插件
```

有了这段：
```
新人：看一眼 → 「哦，故意不装的，要用就加」→ 30 秒
```

📌 **「否定的决策」也是决策，也需要记录。**

**这个原则在企业开发里叫 ADR（Architecture Decision Record）**：
不只记录「我们选了 A」，还要记录「我们考虑过 B 和 C，为什么没选」。

### 数字很有说服力

```
torch 的 CUDA 版约 2.5 GB，是原镜像最大的一块
```

**对比**：
```
上游镜像（nvidia/cuda + torch）：  好几个 GB
本项目测试镜像（python:3.10-slim）：约 130 MB 基础 + 依赖
```

📌 **面试讲镜像优化时，一定要给出具体数字。**
「我优化了镜像体积」没有说服力，「从 GB 级降到几百 MB，
因为砍掉了测试根本用不到的 torch 和 CUDA」有说服力。

---

## 2.5 ⚠️ 文件末尾的「刻意留的坑」（第 63-65 行）

```
# ⚠️ 这份清单目前是不完整的 —— Step 5 构建后会撞
#    ModuleNotFoundError。那是刻意留的教学环节，
#    撞完请回到 Step 5.8 决定修在哪一层。
```

**这是教程的设计**：让你亲自撞一次「干净环境暴露依赖缺失」。

📌 **「修在哪一层」是个真问题**：

| 修在哪 | 效果 |
|---|---|
| `requirements-test.txt` | 镜像能跑了，但 `pip install -e .` 的用户还是崩 |
| **`pyproject.toml`** | ✅ **根因** —— 所有安装路径都修好了 |
| 两个都改 | ✅ 本项目的做法（前者钉死版本，后者声明范围） |

**只改 `requirements-test.txt` 是治标** ——
Day 10 在 CI 上用 `pip install -e .` 时又会炸一次（这正是缺陷 L′ 的发生过程）。

---

# 第三部分：`.dockerignore` 逐行（70 行）

## 3.1 `.dockerignore` vs `.gitignore`（第 3-7 行）

```
# 语法和 .gitignore 一样，但作用完全不同：
#   .gitignore   决定什么不进 git 仓库
#   .dockerignore 决定什么不进 Docker 镜像
# 两者互不影响，需要分别维护。
```

### 什么是「构建上下文」（build context）

```bash
docker build -f discoverse/docker/Dockerfile.test -t discoverse:test .
#                                                                    ↑
#                                                        构建上下文 = 当前目录
```

**执行 `docker build` 时，Docker 会把整个上下文目录打包发给 Docker 守护进程。**

```
仓库根目录 768 MB
    ↓ 没有 .dockerignore
全部 768 MB 被打包传输  ← 慢，而且 .git 的 312 MB 完全没用
    ↓ 有 .dockerignore
只传需要的部分
```

📌 **`.dockerignore` 必须放在**构建上下文的根目录**（即 `.` 指向的地方），
不是 Dockerfile 旁边。这是常见错误。

---

## 3.2 ⚠️ 核心警告（第 9-11 行）

```
# ⚠️ 排错时注意：这里挡掉的东西，容器里就是「文件不存在」，
#    而 tests/conftest.py 遇到 MJCF 不存在会 pytest.skip —— 
#    也就是「测试变绿但啥也没测」。改动本文件后必须比对 skip 数。
```

**这条警告在文件最开头，而不是埋在下面** —— 因为它是使用这个文件的**前提知识**。

📌 **「改动本文件后必须比对 skip 数」是可操作的检查清单。**
好的注释给出**动作**，而不只是描述现象。

---

## 3.3 排除项逐组解析（第 14-52 行）

```
# ---- 版本控制（312 MB，镜像里完全用不到）---
.git
.gitignore
.gitattributes
.gitmodules
```

**`.git` 是最大的一块（312 MB）且完全无用** ——
镜像里不需要版本历史，只需要**当前**的代码。

```
# ---- Python 运行时产物 ----
# 这些是本机 python 生成的缓存，架构/版本可能与容器不一致，
# 带进去反而可能引起诡异问题，让容器自己重新生成。
__pycache__
*.pyc
```

### ⭐ 这条不只是为了省体积

**`.pyc` 是编译后的字节码，和 Python 版本绑定**：

```
本机：Python 3.10 → __pycache__/foo.cpython-310.pyc
容器：Python 3.12 → 忽略 310 的 pyc，重新编译

但如果版本恰好相同，容器会用你本机的 pyc ——
而那个 pyc 可能是旧代码编译的  →  💥 诡异的行为不一致
```

📌 **这也解释了 `Dockerfile.test` 第 22-23 行为什么锁 3.10**：

```dockerfile
# 为什么锁 3.10：本机 tests/__pycache__ 是 cpython-310，
#   版本不一致会在依赖 wheel 上出岔子。
```

```
# ---- 策略学习（3.3 MB，但依赖 torch 等重型库，测试不涉及）----
policies
submodules
```

⚠️ **注意注释里的诚实**：`policies` 本身只有 3.3 MB ——
排除它**不是为了省体积**，是为了避免 `pip install -e .` 时
`setuptools` 扫到它、或者测试意外 import 到需要 torch 的东西。

---

## 3.4 ⭐⭐ 为什么没有排除 `models/`（第 54-70 行）

**这是全文件最有价值的一段，也是 Day 8-9 最大的坑。**

```
# ⚠️ 注意这里没有排除 models/
#
# 直觉上 models/ 有 439 MB，是瘦身大头，但：
#   tests/unit/test_conftest_fixtures.py 等直接加载
#   models/mjcf/manipulator/*.xml，而这些 XML 的 <compiler>
#   标签里写着 meshdir="../../meshes/" —— 编译期就要读 mesh 文件。
#   实测 robot_airbot_play.xml 加载后 nmesh=14, ntex=2。
#
# 排除 models/ 的后果不是报错，是 pytest.skip 静默兜住 →
# 测试全绿但一个 MJCF 都没真正加载过。
```

### 陷阱的完整机制

```
第 1 步：看到 models/ 有 439 MB → 「这是大头，砍了」
第 2 步：加进 .dockerignore
第 3 步：重新 build → 镜像从几百 MB 降到几十 MB 🎉
第 4 步：跑测试 → 全绿 ✅ 🎉🎉
第 5 步：提交，收工

真相：conftest.py 的 pytest.skip 把所有需要 MJCF 的测试都跳过了
      整个镜像里一个 MuJoCo 模型都没加载过
      IK 测试、确定性测试、mobile_manipulation 测试 —— 全部没跑
```

### ⭐ 为什么 `meshes/` 砍不得

```xml
<!-- models/mjcf/manipulator/robot_airbot_play.xml -->
<compiler meshdir="../../meshes/" .../>
```

**MuJoCo 在「编译 XML」阶段就要读 mesh 文件** —— 不是渲染时才读。

```python
mujoco.MjModel.from_xml_path("robot_airbot_play.xml")
    ↓ 解析 XML
    ↓ 读 meshdir 下的 14 个 .obj 文件      ← 缺了这里就失败
    ↓ 读 2 个贴图
    ↓ 编译碰撞几何
    ↓ 返回 MjModel
```

**实测证据**：`nmesh=14, ntex=2` —— 不是猜的，是加载后打印出来的。

📌 **「即使不渲染，也需要 mesh」是反直觉的。**
很多人以为「我只做单元测试不看画面，mesh 用不上」—— 错。

### ⭐ 留下的实验方法（第 67-69 行）

```
# 如果要进一步瘦身，用 Step 3.5 的实验法逐个目录验证，
# 例如 models/meshes/object/（241 MB）可能可以排除。
# 验证方式：mv 走 → 跑测试 → 看 skip 数变没变 → mv 回来。
```

**这个方法叫「实验法」，四步**：

```bash
# ① 记录基线
$PY -m pytest tests/ -q     # 113 passed, 4 skipped

# ② 把候选目录移走（不是删！）
mv models/meshes/object /tmp/

# ③ 重跑，比对
$PY -m pytest tests/ -q     # skip 数变了吗？

# ④ 移回来
mv /tmp/object models/meshes/
```

📌 **关键点**：
- **看 skip 数而不是 pass 数** —— skip 数变了说明有测试被静默跳过
- **`mv` 而不是 `rm`** —— 可逆
- **一次只动一个目录** —— 否则不知道是哪个引起的

**这是「二分法定位」的一个应用**，在企业开发里到处都用：
定位依赖、定位配置项、定位引起性能退化的 commit（`git bisect`）。

---

# 第四部分：`Dockerfile.test` 逐行（99 行）

## 4.1 文件头：用途与验收标准（第 1-11 行）

```dockerfile
# ============================================================
# Dockerfile.test —— DISCOVERSE 无头测试镜像
#
# 用途：在没有显示器、没有 GPU 的机器上跑 pytest。
#      最终目标运行环境是 GitHub Actions 的免费 runner。
#
# 构建：docker build -f discoverse/docker/Dockerfile.test -t discoverse:test .
# 运行：docker run --rm discoverse:test pytest tests/ -q
# 验收：输出必须是 113 passed, 4 skipped, 45 deselected, 10 xfailed
#      —— 与本机 `source scripts/dev/env.sh && $PY -m pytest tests/ -q` 一致
# ============================================================
```

### ⭐ 四要素俱全的文件头

| 要素 | 内容 |
|---|---|
| **用途** | 无头跑 pytest |
| **目标环境** | GitHub Actions 免费 runner ← **这决定了所有技术选型** |
| **怎么用** | build / run 命令可以直接复制 |
| **验收标准** | **具体数字** |

📌 **「最终目标运行环境」这一句决定了后面所有决策** ——
不用 GPU、不用 nvidia/cuda、用 osmesa。

**通用原则：写基础设施代码前，先明确它要跑在哪。**

---

## 4.2 ⭐⭐ 基础镜像的选择（第 13-24 行）

```dockerfile
# ---- 基础镜像 ----
# 为什么不是 nvidia/cuda（现有 Dockerfile 用的那个）：
#   本机已装 nvidia-container-toolkit，docker run --gpus all 确实能用 GPU。
#   但这个镜像最终要跑在 GitHub Actions 免费 runner 上，那里没有 GPU。
#   绑死 GPU 的镜像会「本机绿、CI 红」。
#   而且测试瓶颈根本不在渲染 —— 113 个用例 3 秒跑完，
#   测的是配置层和 IK 求解，不是渲染性能。
#   代价：nvidia/cuda:11.8.0-base 约 2 GB，这里约 130 MB。
FROM python:3.10-slim
```

### ⭐⭐ 「能用 ≠ 该用」——本项目最好的一次技术判断

**完整的推理链**：

```
① 事实：本机装了 nvidia-container-toolkit，--gpus all 确实能看到 GPU
       （教程 Step 2.1 做了实验证明：加 --gpus all 能看到，不加看不到）

② 但是：目标环境（GitHub Actions 免费 runner）没有 GPU

③ 后果：绑死 GPU 的镜像会「本机绿、CI 红」

④ 而且：测试瓶颈根本不在渲染 —— 113 个用例 3 秒跑完

⑤ 代价对比：nvidia/cuda 约 2 GB  vs  python:3.10-slim 约 130 MB
                                      ↑ 差 15 倍

⑥ 结论：用 python:3.10-slim
```

📌 **注意 ① 这一步**：他**先做了实验证明 GPU 能用**，然后才说「但我不用它」。

**这和「不知道能不能用所以不用」完全是两回事。**

**面试可以这样讲**：「我先验证了本机 Docker 确实能用 GPU ——
`--gpus all` 加与不加，`nvidia-smi` 的输出是不同的。
但我最后选了不带 GPU 的 `python:3.10-slim`，因为这个镜像的目标环境是
GitHub Actions 免费 runner，那里没有 GPU。**绑死 GPU 会造成「本机绿、CI 红」**。
而且实测测试瓶颈不在渲染 —— 113 个用例 3 秒跑完，测的是配置层和 IK。
镜像从 2 GB 降到 130 MB。**能用不等于该用，要看目标环境。**」

### 为什么锁 Python 3.10（第 22-23 行）

```dockerfile
# 为什么锁 3.10：本机 tests/__pycache__ 是 cpython-310，
#   版本不一致会在依赖 wheel 上出岔子。
```

`-slim` 后缀 = 精简版（不含编译工具链和文档），比完整版小很多。

---

## 4.3 `DEBIAN_FRONTEND=noninteractive`（第 26-28 行）

```dockerfile
# ---- 构建期不要交互式提问 ----
# apt 装某些包时会弹时区选择等对话框，容器里没人回答会挂住。
ENV DEBIAN_FRONTEND=noninteractive
```

**典型症状**：build 到某一步**卡住不动**，看起来像死机。

实际是 `tzdata` 在问「你在哪个时区？」——**容器里没有人能回答**。

📌 **所有基于 Debian/Ubuntu 的 Dockerfile 都应该加这一行。**

---

## 4.4 ⭐ 系统依赖（第 30-49 行）—— 每一个都有血泪史

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    libosmesa6-dev \
    libgl1 \
    libglx-mesa0 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
```

### 逐个包的理由

**① `libosmesa6-dev`**

```dockerfile
# libosmesa6-dev: osmesa 软件渲染的核心库。
#   ⚠️ 名字带 -dev 看着像编译期依赖，但 osmesa 运行期就要它，砍不得。
```

📌 **`-dev` 后缀通常表示「开发用的头文件」，构建完就能删。**
但 osmesa **运行期**就需要它 —— 这是个例外，砍了会崩。

**② `libgl1` / `libglx-mesa0`** — OpenGL 运行时，mujoco 链接时需要。

**③ `libglib2.0-0`** ⭐⭐ 最有教学价值的一个

```dockerfile
# libglib2.0-0: 提供 libgthread-2.0.so.0，opencv-python(cv2) 的运行时依赖。
#   ⚠️ 别删。pip 装的 opencv 只含 Python 层与自带的一部分 .so，
#      底层 glib 要系统提供 —— pip 管不到这一层。
#      缺它的症状很隐蔽：不是启动即崩，而是 7 个用例 ERROR
#      （106 passed 而非 113），因为 cv2 是在 fixture 里才被 import 的
#      （discoverse/envs/simulator.py:7）。见缺陷报告 §廿六。
```

### ⭐ 这段揭示了两个重要概念

**概念 1：pip 管不到系统库**

```
pip install opencv-python
    ↓ 装了什么
    ✅ Python 层的 cv2 模块
    ✅ 一部分打包好的 .so
    ❌ 底层的系统库（glib、X11……）  ← 必须用 apt 装
```

📌 **Python 包的依赖链有两层：pip 层和系统层。**
`requirements.txt` 只管前者。这是容器化时最常见的坑。

**概念 2：症状的隐蔽性**

```
不是：容器启动就崩（那样很容易发现）
而是：106 passed 而非 113   ← 看起来很正常！
```

**为什么**：`cv2` 是在 **fixture 里**才被 import 的（`simulator.py:7`），
不是在模块顶部。所以：

```
收集阶段：正常（没 import cv2）
执行阶段：某些用例的 fixture 触发 import → ERROR
结果：   106 passed + 7 errors
```

📌 **如果你不知道基线是 113，你会觉得 106 passed 挺好的。**

**这就是 [1.8](#18-⭐-静默降级本项目-dockerci-部分的核心主题) 说的静默降级。**

### `--no-install-recommends`（第 40 行）

```dockerfile
# --no-install-recommends: 不装「推荐」的附带包，能省不少体积。
```

apt 的包有三级依赖：`Depends`（必须）、`Recommends`（推荐）、`Suggests`（建议）。
默认会装 Recommends —— 通常包含文档、示例、GUI 工具，**容器里全都用不到**。

### ⭐ `rm -rf /var/lib/apt/lists/*` 必须同一个 RUN（第 41-43 行）

```dockerfile
# rm -rf /var/lib/apt/lists/*: 清 apt 索引缓存。
#   ⚠️ 必须和 apt-get install 在同一个 RUN 里 ——
#      Docker 每个 RUN 是一层，分开写的话缓存已经进了上一层，删了也不减体积。
```

**这是 Docker 分层的一个反直觉后果**：

```dockerfile
# ❌ 错的
RUN apt-get update && apt-get install -y foo    # 第 1 层：包含 apt 缓存（几十 MB）
RUN rm -rf /var/lib/apt/lists/*                  # 第 2 层：标记删除

# 结果：镜像里仍然有那几十 MB！
#       因为镜像 = 所有层的叠加，第 1 层的数据还在里面

# ✅ 对的
RUN apt-get update && apt-get install -y foo \
    && rm -rf /var/lib/apt/lists/*               # 一层：装完就删，这层不含缓存
```

📌 **Docker 的层是「只增不减」的。**
在后面的层里删除文件，只是**标记为不可见**，数据仍然占体积。

**通用规则：产生临时文件和清理它，必须在同一个 `RUN` 里。**

---

## 4.5 ⭐ 渲染后端：整个镜像存在的理由（第 51-60 行）

```dockerfile
# ---- 渲染后端：整个镜像存在的理由 ----
# glfw 需要显示器，容器里没有 $DISPLAY，一渲染就崩。
# 现有 discoverse/docker/Dockerfile 第 58 行写的正是 ENV MUJOCO_GL=glfw，
# 这就是它不能直接拿来跑测试的原因。
# osmesa = Off-Screen Mesa，纯 CPU 软件渲染，慢但零环境依赖。
#
# 写成 ENV 而不是靠 scripts/dev/env.sh：
#   source 出来的变量不跨进程，忘了 source 就跑错后端，而且不报错只是行为不同。
#   ENV 是焊死在镜像里的，进容器就一定在。
ENV MUJOCO_GL=osmesa
```

### ⭐ 「写成 ENV 而不是靠 env.sh」的理由

```bash
# 靠 env.sh
source scripts/dev/env.sh && pytest    # ✅ 有 MUJOCO_GL
pytest                                  # ❌ 忘了 source → 用默认 glfw → 崩
                                        #    或者更糟：不崩，但行为不同
```

```dockerfile
# 靠 ENV
ENV MUJOCO_GL=osmesa      # 焊死在镜像里，进容器就一定有
```

📌 **「而且不报错只是行为不同」是关键** ——
如果忘了 source 会立刻崩，那还好；
可怕的是它**能跑**，但用的是另一个渲染后端，结果微妙地不同。

**通用原则：让正确的做法成为默认的做法，而不是靠人记得。**

---

## 4.6 Python 环境变量（第 62-65 行）

```dockerfile
# PYTHONDONTWRITEBYTECODE: 不生成 .pyc，容器是一次性的，省体积
# PYTHONUNBUFFERED: 日志实时输出，否则 CI 里看不到进度只能等结束
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
```

### ⭐ `PYTHONUNBUFFERED=1` 在 CI 里非常重要

**默认行为**：Python 的 stdout 在**非终端**环境下是**块缓冲**的。

```
CI 里跑一个 10 分钟的测试
    ↓ 没有 PYTHONUNBUFFERED
前 10 分钟：日志页面完全空白  ← 你不知道它是在跑还是卡死了
第 10 分钟：所有输出一次性刷出来
```

📌 **这两个变量是容器化 Python 应用的标配。**

**一个 `ENV` 用 `\` 续行设置多个变量 = 只产生一层**，比写两个 `ENV` 省一层。

---

## 4.7 ⭐ 分层缓存的实践（第 67-84 行）

```dockerfile
WORKDIR /workspace

# ---- 先装依赖，再拷源码（分层缓存的关键）----
# Docker 按层缓存，某层的输入没变就直接复用。
# 依赖清单很少变、源码天天变，所以依赖必须放前面。
# 反过来写的话，改一行代码就要重装全部依赖。
COPY requirements-test.txt /tmp/requirements-test.txt
RUN pip install --no-cache-dir -r /tmp/requirements-test.txt

# ---- 再拷源码 ----
# 实际拷什么由仓库根的 .dockerignore 决定。
COPY . /workspace/

# ---- 装 discoverse 本体 ----
RUN pip install --no-cache-dir --no-deps -e .
```

### `--no-cache-dir`

pip 默认会把下载的包缓存在 `~/.cache/pip`，**在容器里这是纯粹的浪费体积**
（镜像是一次性的，不会再装第二次）。

### ⭐⭐ `--no-deps` 的深意（第 80-84 行）

```dockerfile
# --no-deps: 不让 pip 再去解析 pyproject.toml 的依赖。
#   依赖已由 requirements-test.txt 精确控制，
#   不加这个会把 pyproject 里的版本范围重新解一遍，破坏钉死的版本。
```

**没有 `--no-deps` 会发生什么**：

```
requirements-test.txt: numpy==2.2.6      ← 钉死
                       ↓ 装好了
pip install -e .
    ↓ 读 pyproject.toml: numpy>=1.20.0
    ↓ pip 检查：2.2.6 满足 >=1.20.0 吗？满足，不动
    ↓ 但其他包可能被升级/降级  →  💥 钉死的版本被破坏
```

📌 **`--no-deps` = 「我已经精确控制了依赖，你别管」。**

### ⭐⭐ 但这带来一个盲区 —— 而 CI 补上了它

```
镜像用 requirements-test.txt + --no-deps
    ↓
完全绕过了 pyproject.toml 的依赖声明
    ↓
所以：即使 pyproject.toml 的依赖声明是错的，镜像也能跑！
```

**这正是 `ci.yml` 里 `unit` job 存在的理由**（第 50-52 行）：

```yaml
# 为什么不直接用 Day 8-9 的镜像？见 Step 5 的对比 ——
# 这个 job 的额外价值是：它验证「pyproject.toml 声明的依赖是否完整」，
# 而镜像用 requirements-test.txt + --no-deps，恰好绕过了这个验证。
```

📌 **两个 job 不是重复，是互补 —— 各自覆盖对方的盲区。**
这是全项目 CI 设计里最精妙的一点，见 [5.5](#55-⭐⭐-unit-job-与-integration-job-的分工第-49-123-行)。

---

## 4.8 ⭐ 构建期自检（第 86-95 行）

```dockerfile
# ---- 构建期自检 ----
# 在 build 阶段就验证关键 import，把「运行时才发现依赖缺失」
# 提前到「构建时就失败」。失败越早越便宜。
#
# 📌 这一行就是 checkpoint-day06-07.md §2.2 说的那道守护：
#    「理想做法是 CI 里加一个干净环境 job 跑
#      pip install -e . && python -c "import discoverse.universal_manipulation"」
#    ⚠️ 也正是这一行会让你第一次 build 失败 —— 那是设计好的，见 Step 5.4。
RUN python -c "import mujoco; print('MuJoCo', mujoco.__version__)" \
    && python -c "import discoverse.universal_manipulation; print('discoverse OK')"
```

### ⭐ 「失败越早越便宜」（Shift Left）

```
发现问题的时机       →  修复成本
─────────────────────────────────
写代码时（IDE 报错）   →  秒级
构建时（本行）        →  分钟级
测试时               →  十几分钟
CI 上                →  几十分钟 + 阻塞别人
生产环境             →  💸💸💸
```

📌 **这一行把「依赖缺失」从「跑测试时才发现」提前到「build 时就失败」。**

**而且失败信息更清楚**：
```
# build 时失败：
ModuleNotFoundError: No module named 'av'     ← 一目了然

# 跑测试时失败：
ERROR tests/unit/test_recorder.py - ModuleNotFoundError...
ERROR tests/unit/test_mink_solver.py - ...
（7 个 collection error 刷屏，要往上翻才能看到根因）
```

### 为什么 `import discoverse.universal_manipulation` 就够了

因为 [1.7](#17-eager-import-链与缺陷-l) 讲的 **eager import 链** ——
这一个 import 会连锁加载全部 7 个子模块，**任何一个依赖缺失都会在这里暴露**。

📌 **用一行代码测出整条依赖链** —— 这是对代码结构的理解转化成的测试杠杆。

---

## 4.9 `CMD` 与可覆盖（第 97-99 行）

```dockerfile
# 默认跑全量回归。docker run 时可以覆盖，例如：
#   docker run --rm discoverse:test pytest tests/unit -v
CMD ["pytest", "tests/", "-q"]
```

### `CMD` vs `ENTRYPOINT`

| | 行为 |
|---|---|
| `CMD` | **默认命令，可被 `docker run` 后面的参数完全覆盖** |
| `ENTRYPOINT` | 固定的入口，`docker run` 的参数会**追加**在后面 |

```bash
docker run --rm discoverse:test                      # 跑 CMD：pytest tests/ -q
docker run --rm discoverse:test pytest tests/unit -v # 覆盖 CMD
docker run --rm discoverse:test bash                 # 进 shell 调试
```

📌 **用 `CMD` 保留了灵活性** —— 镜像既能一键跑全量，也能进去调试。

### JSON 数组形式（exec form）

```dockerfile
CMD ["pytest", "tests/", "-q"]     # ✅ exec form —— 直接执行，不经过 shell
CMD pytest tests/ -q                # ⚠️ shell form —— 包一层 /bin/sh -c
```

**exec form 更好**：进程是 PID 1，能正确接收 `docker stop` 发的信号。
shell form 下 pytest 是 sh 的子进程，信号可能传不到 → `docker stop` 要等 10 秒超时。

---

# 第五部分：`ci.yml` 逐行（184 行）

## 5.1 文件头与设计原则（第 1-7 行）

```yaml
# ============================================================
# ci.yml —— DISCOVERSE 测试流水线
#
# 设计原则：每个 job 是一台独立的干净虚拟机，
#          job 之间不共享任何东西，各自从零备环境。
# ============================================================
name: CI
```

**把「每个 job 是独立虚拟机」写在最上面** ——
这解释了后面为什么每个 job 都在重复装环境（原理见 [1.4](#14-github-actions-的四个概念)）。

---

## 5.2 触发条件 `on:`（第 9-20 行）

```yaml
on:
  push:
    branches: [feat/test-infra, main]
    # 改文档不该触发全量 CI（尤其 integration 要 build 镜像，好几分钟）。
    # ⚠️ 将来配了 branch protection 要回来重想 ——
    #    被跳过的 job 状态是 skipped 而非 success，PR 会一直卡在等待检查。
    paths-ignore:
      - "docs/**"
      - "source-notes/**"
      - "**.md"
  pull_request:
  workflow_dispatch: # ⭐ 允许在网页上手动触发，调试期靠它省下大量 push
```

### 三种触发方式

| 触发 | 何时 |
|---|---|
| `push` | 推到指定分支时 |
| `pull_request` | 开 PR 或 PR 更新时 |
| **`workflow_dispatch`** | **在 GitHub 网页上手动点按钮** |

### ⭐ `workflow_dispatch` 在调试期的价值

```
没有它：改 ci.yml → commit → push → 看结果 → 又改 → commit → push...
                                                    ↑ 一堆垃圾 commit

有了它：改好推一次 → 网页上反复点「Run workflow」调试
```

📌 **配 CI 时第一件事就是加 `workflow_dispatch`。**

### ⚠️ `paths-ignore` 的陷阱（第 13-14 行）

```yaml
# ⚠️ 将来配了 branch protection 要回来重想 ——
#    被跳过的 job 状态是 skipped 而非 success，PR 会一直卡在等待检查。
```

**这是一个真实的坑，很多团队踩过**：

```
配置：branch protection 要求 "unit" job 必须 success 才能合并
     +
     paths-ignore 让改文档的 PR 不触发 CI
     ↓
改文档的 PR：unit job 状态 = skipped（不是 success）
     ↓
PR 永远卡在「等待必需的检查」，无法合并  🔒
```

**官方解法**：用一个「总是运行但可能什么都不做」的 job 作为 required check，
或者用 `paths-filter` action 在 job 内部判断。

📌 **注释里写「将来配了 X 要回来重想」是很好的实践** ——
把已知的未来风险留给未来的自己。

---

## 5.3 ⭐ `concurrency` 取消旧 run（第 22-26 行）

```yaml
# 同一分支连续 push 时，取消还在跑的旧 run。
# 连推 3 个 commit 默认会并行跑 3 条流水线，前两条的结果你根本不会看，纯烧额度。
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

### 机制

```
group: CI-refs/heads/feat/test-infra     ← 同一个 group 内只允许一个 run

push commit A → 开始跑 run1
push commit B → run1 被取消，开始跑 run2      ← cancel-in-progress
push commit C → run2 被取消，开始跑 run3
```

### 为什么重要：GitHub Actions 是计费的

```
免费额度：每月 2000 分钟（私有仓库）
integration job 要 build 镜像：好几分钟
连推 3 个 commit：3 × 好几分钟 = 十几分钟，其中 2/3 是浪费
```

📌 **`${{ github.ref }}` 保证不同分支互不影响** ——
你推 feature 分支不会取消别人 main 分支的 run。

⚠️ **注意**：`main` 分支通常**不该**开 `cancel-in-progress`，
因为每个 commit 的 CI 结果都有记录价值。
更精细的写法：
```yaml
cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}
```

---

## 5.4 `smoke` job：先打通管道（第 29-47 行）

```yaml
  # ---- 第一个 job：只验证「代码能拉下来、python 能起来」----
  # 故意什么都不测。先把管道打通，再往里灌东西。
  smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.10" # 与 Dockerfile.test 锁的版本一致
      - name: 环境自报家门
        run: |
          python --version
          pwd
          ls -la
          echo "--- models 目录是否完整（防 LFS 指针）---"
          ls models/meshes/airbot_play/ | head -3
          head -c 60 models/meshes/airbot_play/arm_base_0.obj
```

### ⭐ 「故意什么都不测」的价值

**第一版 CI 应该极简。** 因为配 CI 时会遇到一堆和测试无关的问题：

```
YAML 缩进错了、分支名写错了、Actions 版本不对、
仓库权限不够、checkout 深度不够……
```

如果第一版就写满测试，**你分不清是 CI 配错了还是测试挂了**。

📌 **通用方法论：先让管道跑通（哪怕只 echo 一行），再往里加东西。**
这和 Day 2 「先写一条 `assert 1+1==2` 的 smoke test」是同一个思路。

### ⭐⭐ 「防 LFS 指针」检查

```bash
head -c 60 models/meshes/airbot_play/arm_base_0.obj
```

**这一步在检查什么**：

**Git LFS（Large File Storage）** 把大文件替换成一个**小指针文件**：

```
# 正常的 .obj 文件
v 0.123 0.456 0.789
v 0.234 0.567 0.890
...

# LFS 指针文件（只有 130 字节左右）
version https://git-lfs.github.com/spec/v1
oid sha256:4d7a2...
size 12345678
```

**如果 CI 没配好 LFS**：
```
checkout 下来的是指针文件
    ↓
MuJoCo 加载 XML → 读 mesh → 内容是一串文本 → 解析失败
    ↓
或者更糟：pytest.skip 兜住 → 全绿但啥也没测
```

`head -c 60` 打印前 60 字节 —— **一眼就能看出是真文件还是指针**。

📌 **这是 [1.8](#18-⭐-静默降级本项目-dockerci-部分的核心主题) 静默降级主题的又一个实例**，
而且是**主动加的探针**，不是被动等它出问题。

### `uses:` vs `run:`

```yaml
- uses: actions/checkout@v4      # 用别人写好的 Action（从 marketplace）
- run: python --version           # 直接跑 shell 命令
```

| Action | 作用 |
|---|---|
| `actions/checkout@v4` | **把代码拉下来**（不加这个，工作目录是空的！） |
| `actions/setup-python@v5` | 装指定版本的 Python |

`@v4` 是版本标签 —— **应该钉版本**，不要用 `@main`（别人改了你就崩）。

---

## 5.5 ⭐⭐ `unit` job 与 `integration` job 的分工（第 49-123 行）

**这是全文件最精妙的设计，面试必讲。**

```yaml
  unit:
    # 为什么不直接用 Day 8-9 的镜像？见 Step 5 的对比 ——
    # 这个 job 的额外价值是：它验证「pyproject.toml 声明的依赖是否完整」，
    # 而镜像用 requirements-test.txt + --no-deps，恰好绕过了这个验证。
```

```yaml
  integration:
    # 与 unit job 的分工见教程 Step 5.1：
    #   unit  验证 pyproject.toml 依赖声明完整性（pip install -e .）
    #   这里  验证镜像可复现性（requirements-test.txt + --no-deps）
    # 两者不是重复，各自覆盖对方的盲区。
```

### ⭐⭐ 两个 job 的盲区互补关系

```
┌────────────────────────────────────────────────────────────┐
│  unit job：pip install -e .（解 pyproject.toml）             │
│    ✅ 能发现：pyproject.toml 依赖声明不完整（缺陷 L′）         │
│    ❌ 发现不了：镜像构建有问题、系统依赖漏装                    │
├────────────────────────────────────────────────────────────┤
│  integration job：docker build + 镜像内跑                    │
│    ✅ 能发现：镜像构建失败、系统库缺失、容器内环境问题           │
│    ❌ 发现不了：pyproject.toml 依赖错误（--no-deps 绕过了）    │
└────────────────────────────────────────────────────────────┘
                            ↓
              两者叠加 = 覆盖完整
```

### 具体到缺陷 L′

```
Day 8-9：镜像里跑通了（用 requirements-test.txt 精确装）
             ↓ 但 pyproject.toml 的依赖声明仍然是错的（4 个包在 optional 组）
Day 10： unit job 用 pip install -e . →  💥 缺 pyyaml
             ↑ 只有这个 job 能抓到
```

**`unit` job 里刻意不加 `--no-deps`**（第 75-77 行）：

```yaml
# ⚠️ 这里刻意用 pip install -e .（不加 --no-deps）——
#    就是要让它去解 pyproject.toml，从而验证依赖声明的完整性。
#    这是缺陷 L′ 的守护测试。
```

📌 **「刻意用一个更慢/更麻烦的方式，为了验证某个契约」** ——
这是有意识的 CI 设计，不是偷懒。

**面试可以这样讲**：「我的 CI 里有两个跑测试的 job，看起来重复，其实是互补的。
`unit` job 用 `pip install -e .`，会去解 `pyproject.toml` 的依赖声明；
`integration` job 用 Docker 镜像，而镜像是 `requirements-test.txt` + `--no-deps`，
**恰好绕过了依赖声明的验证**。
所以只有 `unit` job 能抓到「依赖声明不完整」这类缺陷 —— 我的缺陷 L′ 就是这么被抓到的。
反过来，只有 `integration` job 能抓到系统库缺失、镜像构建问题。
**它们各自覆盖对方的盲区。**」

---

## 5.6 `unit` job 逐步解析（第 53-97 行）

### `cache: pip`（第 61 行）

```yaml
      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"
          cache: pip # ⭐ 缓存 pip 下载，第二次起能省几分钟
```

**缓存的是 pip 的下载包**，不是安装结果。第二次 build 时不用重新从 PyPI 下载。

### 系统依赖（第 63-72 行）

```yaml
      - name: 系统依赖
        # libosmesa6-dev: osmesa 软件渲染核心库（运行期就要，不是编译期）
        # libgl1 / libglx-mesa0: OpenGL 运行时，mujoco 链接需要
        # libglib2.0-0: cv2 的运行时依赖。⚠️ 漏了会变成 7 个 ERROR
        #               而不是崩溃 —— 看着像「106 passed」，很正常的样子
        # 不装 xvfb：osmesa 是离屏渲染，不需要虚拟显示器
        run: |
          sudo apt-get update
          sudo apt-get install -y --no-install-recommends \
            libosmesa6-dev libgl1 libglx-mesa0 libglib2.0-0
```

**和 `Dockerfile.test` 装的是同一组包** —— 因为两边都要跑同样的测试。

### ⭐ 「不装 xvfb」（第 68 行）

**`xvfb` = X Virtual FrameBuffer**，一个「假的显示器」。

**很多 CI 教程会让你装它**：
```yaml
- run: sudo apt-get install xvfb
- run: xvfb-run pytest tests/
```

📌 **但我们用 osmesa，它是离屏渲染，根本不需要显示器 —— 装了纯属浪费。**

**这条注释的价值**：防止后来的人「照着网上教程加回来」。

**通用原则：记录「为什么没做 X」和记录「为什么做了 Y」同样重要**
（同 [2.4](#24-⭐-没有装的以及理由第-52-66-行)）。

### ⭐ 干净环境 import 自检（第 83-89 行）

```yaml
      - name: ⭐ 干净环境 import 自检
        # checkpoint-day06-07 §2.2 要求的那道守护。
        # 放在跑测试之前 —— 失败越早越便宜，
        # 而且失败信息比一堆 collection error 清楚得多。
        run: |
          python -c "import mujoco; print('MuJoCo', mujoco.__version__)"
          python -c "import discoverse.universal_manipulation; print('discoverse OK')"
```

**和 `Dockerfile.test` 第 94-95 行完全一样的自检** —— 因为原理相同（见 [4.8](#48-⭐-构建期自检第-86-95-行)）。

📌 **在两个地方都放这道守护，是因为两条路径不同**：
- Dockerfile：`requirements-test.txt` 路径
- CI unit job：`pip install -e .` 路径

**两条路径都要验证。**

### ⚠️ 覆盖率参数（第 91-97 行）

```yaml
      - name: 跑测试
        env:
          MUJOCO_GL: osmesa
        # --cov 不带参数：读 pyproject.toml 的 source 配置。
        # ⚠️ 别写 --cov=discoverse，分母会从 967 涨到 2584，
        #    覆盖率数字 41% → 28%，和你两周积累的记录对不上。
        run: pytest tests/ -q --cov --cov-report=term-missing
```

**原理见 [1.10](#110-测试覆盖率19--94-是怎么算的)**。

📌 **「和你两周积累的记录对不上」是关键理由** ——
指标的**口径必须稳定**，否则趋势图毫无意义。

**企业实践**：覆盖率口径应该写进配置文件（本项目的 `[tool.coverage.run]`），
**而不是散落在各处的命令行参数里** —— 否则不同的人跑出不同的数字。

### `env:` 的作用域

```yaml
      - name: 跑测试
        env:
          MUJOCO_GL: osmesa      # 只对这一个 step 生效
        run: pytest tests/ -q
```

`env` 可以放在三个层级：workflow 级、job 级、step 级。**就近原则更清晰。**

---

## 5.7 `integration` job（第 99-123 行）

```yaml
  integration:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: 构建测试镜像
        # ⚠️ 构建上下文必须是仓库根（最后那个 .），
        #    .dockerignore 在这一层才生效。
        run: docker build -f discoverse/docker/Dockerfile.test -t discoverse:test .
```

### ⚠️ 构建上下文的坑（第 110-111 行）

```bash
docker build -f discoverse/docker/Dockerfile.test -t discoverse:test .
#            ↑ Dockerfile 在哪                                        ↑ 上下文在哪
```

**这两个是独立的！** 常见错误：

```bash
cd discoverse/docker && docker build -f Dockerfile.test -t discoverse:test .
#                                                                          ↑ 上下文变成 docker/ 目录
# → COPY . /workspace/ 只拷到 docker/ 里的几个文件
# → 而且仓库根的 .dockerignore 不生效
```

📌 **`.dockerignore` 必须在**上下文根目录**才生效** —— 见 [3.1](#31-dockerignore-vs-gitignore第-3-7-行)。

### ⭐⭐ 「证明容器内确实没有显示器」（第 114-118 行）

```yaml
      - name: 证明容器内确实没有显示器
        # 这条别删。它是「无头」这个卖点的唯一证据。
        # 预期输出 DISPLAY=[] （空）和 MUJOCO_GL=osmesa
        run: |
          docker run --rm discoverse:test sh -c 'echo "DISPLAY=[$DISPLAY]"; echo "MUJOCO_GL=$MUJOCO_GL"'
```

### ⭐ 「它是『无头』这个卖点的唯一证据」

**这一步不测任何功能** —— 它在**证明一个声称**。

```
声称：「这个镜像能在无显示器环境跑」
证据：DISPLAY=[]  （空的）
      MUJOCO_GL=osmesa
```

**为什么需要证据**：

```
如果哪天有人不小心在 Dockerfile 里加了 ENV DISPLAY=:0
    ↓
测试可能仍然全绿（osmesa 不看 DISPLAY）
    ↓
但「无头」这个性质已经悄悄消失了
```

📌 **`DISPLAY=[$DISPLAY]` 用方括号包起来是个小技巧** ——
如果不包，空值会打印成 `DISPLAY=`，你分不清是「空」还是「这行没执行」。
包起来看到 `DISPLAY=[]` 就确定是空的。

**通用方法论：把关键性质写成可执行的断言，而不是写在 README 里。**

### ⚠️ 「不要写 tests/kinematics」（第 120-123 行）

```yaml
      - name: 容器内跑全量测试
        # ⚠️ 不要写 tests/kinematics —— 那是空目录，
        #    会跑出「5 passed」的绿灯，和 122 的绿灯长得一样。
        run: docker run --rm discoverse:test pytest tests/ -q
```

**又一个静默降级的实例**：

```
pytest tests/kinematics    → 目录是空的 → 但 pytest 不报错
                            → 收集到 0 个（或收集到别处的几个）
                            → 输出「5 passed」绿灯 ✅
                            → 而实际上 117 个测试没跑
```

📌 **「绿灯长得都一样」是这两天最重要的一句话。**
`5 passed` 和 `122 passed` 都是绿色的 ✅，**颜色不携带信息，数字才携带**。

---

## 5.8 `lint` job：范围刻意收窄（第 126-160 行）

```yaml
  # ---- 代码规范：范围刻意收窄 ----
  # 为什么不 lint discoverse/：实测 ruff 277 errors、black 59 files。
  # 那是上游代码，一次性重排会制造巨大 diff 和 merge 冲突，
  # 且与「补测试」这个目标无关。一个 PR 只做一件事。
  # tests/ 是我们自己的地盘，已在 053a272 清零。
  lint:
```

### ⭐ 「一个 PR 只做一件事」

**这是一个非常成熟的工程判断**：

```
诱惑：既然配了 lint，顺手把 discoverse/ 的 277 个问题也修了吧
      ↓
后果：
  - PR 从「加测试」变成「加测试 + 重排 59 个文件」
  - diff 几千行，review 的人根本看不过来
  - 和别人的分支疯狂冲突
  - 真正的改动被淹没在格式化噪声里
```

📌 **格式化改动和逻辑改动绝不能混在一个 PR 里。**

### ⚠️ 版本必须钉死（第 141-144 行）

```yaml
      # ⚠️ 版本必须钉死：本机清债时用的就是这两个版本。
      #    不钉的话 CI 装最新版，新增规则会让刚清干净的 tests/ 又变红 ——
      #    而那不是代码变差了，是尺子换了。
      - run: pip install ruff==0.16.2 black==26.5.1
```

### ⭐⭐ 「那不是代码变差了，是尺子换了」

**这句话值得单独记住。**

```
今天：ruff 0.16.2 → tests/ 零错误 ✅
下周：ruff 0.17.0 发布，新增了 10 条规则
      ↓ CI 装最新版
      ↓ tests/ 突然 15 个错误 ❌
      ↓ 你的代码一行没改
```

📌 **lint 工具必须钉版本**，否则你的 CI 会因为**别人发布新版本**而变红。

**企业实践**：
- lint/formatter 版本钉死在 `requirements-dev.txt` 或 `.pre-commit-config.yaml`
- 升级工具版本是一个**独立的 PR**，专门处理新规则带来的改动

### `continue-on-error` 让技术债可见但不阻塞（第 152-160 行）

```yaml
      - name: discoverse/ 现状报告（不拦截）
        # continue-on-error: 这一步红了也不影响 job 整体结果。
        # 意图：把上游代码的规范债「可见化」，但不阻塞。
        # 等哪天真要还债了，把 continue-on-error 删掉即可。
        continue-on-error: true
        run: |
          echo "=== discoverse/ 规范债现状（仅报告）==="
          ruff check discoverse/ --statistics || true
          black --check discoverse/ 2>&1 | tail -3 || true
```

### ⭐ 「可见但不阻塞」是处理技术债的标准姿势

```
方案 A：不 lint discoverse/     →  债务完全不可见，只会越积越多
方案 B：强制 lint discoverse/   →  CI 永远红，或者被迫一次性重排
方案 C：报告但不阻塞 ✅          →  每次 CI 都能看到数字趋势
                                   等有余力了删掉 continue-on-error 即可
```

📌 **「等哪天真要还债了，把 continue-on-error 删掉即可」** ——
留下了一个**明确的升级路径**，而不是一个模糊的 TODO。

### `|| true` 的作用

```bash
ruff check discoverse/ --statistics || true
#                                    ↑ 前面的命令失败也返回 0
```

**双保险**：`continue-on-error` 是 GitHub Actions 层面的，`|| true` 是 shell 层面的。

⚠️ 注意 `run: |` 多行脚本默认是 `set -e`（一条失败就停），
所以中间那条失败会让后面的 `black` 不执行 —— `|| true` 保证两条都跑。

---

## 5.9 `nightly` job：flake 采样（第 163-184 行）

```yaml
  # ---- flake 采样：目前只手动触发 ----
  # 为什么不用 schedule 每天跑：--count=50 单次好几分钟，
  # GitHub 免费额度每月 2000 分钟。当前代码变动频率低，
  # 每天烧额度去跑一个没人天天看的报告不划算。
  # 等代码开始高频变动，把下面的 if 条件改掉即可。
  #
  # ⚠️ 三个插件刻意不进 requirements-test.txt ——
  #    只有 flake 实验用得到，不该让日常 build 背着它们。
  nightly:
    if: github.event_name == 'workflow_dispatch'
```

### ⭐ 成本意识

```
GitHub 免费额度：每月 2000 分钟
--count=50 单次：好几分钟
每天跑：30 × 好几分钟 = 大量额度
    ↓
而且「没人天天看」
```

📌 **CI 是有成本的资源，配置时要算账。**
这个判断展示了**工程师的成本意识**，面试很加分。

**而且给出了明确的触发条件**：「等代码开始高频变动，把 `if` 条件改掉即可」。

### `if:` 条件表达式

```yaml
if: github.event_name == 'workflow_dispatch'
#   ↑ 只在手动触发时跑，push/PR 都不跑
```

**要改成每天跑**，只需两步：
```yaml
on:
  schedule:
    - cron: '0 2 * * *'      # 每天凌晨 2 点（UTC）
jobs:
  nightly:
    if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'
```

### 运行时装插件（第 179-184 行）

```yaml
      - name: flake 采样
        run: |
          docker run --rm discoverse:test sh -c '
            pip install --no-cache-dir pytest-repeat pytest-xdist pytest-json-report &&
            pytest tests/ -m flake --count=20 -n 4 -q
          '
```

**三个插件在容器启动后才装**，而不是打进镜像。

📌 **理由（第 169-170 行）**：

> 三个插件刻意不进 `requirements-test.txt` ——
> 只有 flake 实验用得到，不该让日常 build 背着它们。

**权衡**：

| | 打进镜像 | 运行时装 |
|---|---|---|
| 日常 build | 慢一点、镜像大一点 | ✅ 不受影响 |
| flake 采样 | ✅ 快 | 每次多花几十秒 |

**因为 flake 采样很少跑**，所以选后者。

⚠️ 这也和 `requirements-test.txt` 第 55-57 行的注释呼应 ——
**同一个决策在两个文件里都有记录**，不会有人只看一处就搞错。

### `-m flake --count=20 -n 4`

对照 Day 5 的本地实验（`--count=50 -n 8`），CI 上**规模减半** ——
因为 GitHub runner 只有 2 核，`-n 8` 反而更慢。

---

# 第六部分：`test_recorder.py` 逐行（19% → 94% 那一步）

> commit `c0b4561`：test: 补 recorder 单测，覆盖率 19% -> 94%

## 6.1 文件头：上游的拼写错误（第 1-9 行）

```python
"""recorder.py 的单元测试。

覆盖 recoder_single_arm（JSON 序列化）。PyavImageEncoder 见文件末尾。

⚠️ 函数名 recoder_single_arm 是上游的拼写（少个 r），不是笔误，
   不要"顺手修正"——__init__.py 的导出和 universal_task_runtime.py:345
   的调用点都依赖这个名字。
"""
```

### ⭐ 「不要顺手修正」

`recoder` 应该是 `recorder`（少了个 r）。**看到这种错别字，本能想修。**

**但是**：
```
改函数名 → __init__.py 的导出要改 → 所有调用方要改
         → 下游用户的代码全部崩溃（这是个开源库！）
```

📌 **公开 API 的名字，即使拼错了也是契约。**

**企业实践的正确做法**（如果真要改）：
```python
def record_single_arm(...):        # 新名字
    ...

# 保留旧名字，标记废弃
recoder_single_arm = record_single_arm    # 兼容别名

# 或者加警告
def recoder_single_arm(*args, **kwargs):
    warnings.warn("请改用 record_single_arm", DeprecationWarning)
    return record_single_arm(*args, **kwargs)
```

---

## 6.2 Happy path 测试（第 22-46 行）

```python
@pytest.mark.unit
def test_writes_expected_json_structure(tmp_path):
    """正常输入 → JSON 结构与字段齐全。

    注意输入输出的键名不对称：输入是 'action'，输出是 'act'。
    这个映射没有文档，只能从实现读出来 —— 测试把它固定下来，
    以后有人改了键名会立刻红。
    """
    obs_lst = [
        {"time": 0.0, "jq": [1, 2], "action": [9, 9]},
        {"time": 0.1, "jq": [3, 4], "action": [8, 8]},
    ]

    recoder_single_arm(str(tmp_path), obs_lst)

    data = json.loads((tmp_path / "obs_action.json").read_text())
    assert data == {
        "time": [0.0, 0.1],
        "obs": {"jq": [[1, 2], [3, 4]]},
        "act": [[9, 9], [8, 8]],
    }
```

### `tmp_path` fixture

**pytest 内置**，每个测试拿到一个**独立的临时目录**，测试结束自动清理。

```python
def test_x(tmp_path):
    # tmp_path 是 pathlib.Path，例如 /tmp/pytest-of-user/pytest-123/test_x0
```

📌 **这就是 Day 3-5 补充 3.10 里说的「更好的做法」** ——
不用手动 `try/finally` 清理。

### ⭐ 「输入 `action`，输出 `act`」—— 把隐式契约显式化

```
输入: {"time": ..., "jq": ..., "action": ...}
                                   ↓ 改名
输出: {"time": ..., "obs": {"jq": ...}, "act": ...}
```

**这个映射没有任何文档**，只能读源码才知道。

📌 **测试的一个重要作用：把「只存在于实现里的契约」固定下来。**

```
今天：只有读过源码的人知道 action → act
明天：有人重构，觉得 act 太简写，改成 action
      ↓
      下游解析 JSON 的代码全部崩溃
      ↓
      而这条测试会立刻红，在合并前就拦住
```

**这叫「特征测试」（characterization test）**：
不是验证「应该怎样」，而是固定「现在是怎样」。
处理遗留代码时的标准手段。

---

## 6.3 边界条件测试（第 49-90 行）

```python
def test_creates_nested_save_path(tmp_path):
    """save_path 不存在时应自动创建（含多层）。"""
    target = tmp_path / "a" / "b" / "c"
    assert not target.exists()
    recoder_single_arm(str(target), [{"time": 0.0, "jq": [1], "action": [2]}])
    assert (target / "obs_action.json").is_file()


def test_empty_obs_list_yields_empty_arrays(tmp_path):
    """空列表 → 产出结构完整但数组为空的 JSON，而非报错或空文件。

    这是有意固定的行为：下游拿到的应该是一个合法 JSON，
    能被 json.load 解析出"这一轮没有数据"，
    而不是一个需要 try/except 才能读的坏文件。
    """
    recoder_single_arm(str(tmp_path), [])
    data = json.loads((tmp_path / "obs_action.json").read_text())
    assert data == {"time": [], "obs": {"jq": []}, "act": []}


def test_extra_keys_in_obs_are_ignored(tmp_path):
    """obs 里多余的键被忽略，不影响输出。

    固定这个行为是因为真实 obs 字典（universal_task_runtime.py:108-115）
    可能携带额外字段，recorder 只挑它认识的三个。
    """
```

### ⭐ 边界条件清单（覆盖率从 19% 涨到 94% 靠的就是这些）

| 测试 | 覆盖的边界 |
|---|---|
| happy path | 正常两条数据 |
| 嵌套路径 | 目录不存在（`makedirs` 分支） |
| **空列表** | **零条数据** |
| 多余的键 | 输入有额外字段 |
| 缺必需键 | 输入不完整（异常分支） |
| ndarray 输入 | 类型不符（异常分支） |

📌 **「空输入」是最常被忘记、也最常出 bug 的边界。**

### ⭐ 「有意固定的行为」

```python
这是有意固定的行为：下游拿到的应该是一个合法 JSON，
能被 json.load 解析出"这一轮没有数据"，
而不是一个需要 try/except 才能读的坏文件。
```

**空输入有三种合理设计**：

| 设计 | 下游怎么处理 |
|---|---|
| 抛异常 | `try/except` |
| 不创建文件 | `if os.path.exists()` |
| **写空结构 JSON** ✅ | **直接 `json.load()`，看到空数组** |

**第三种最好** —— 下游代码最简单，不需要特殊分支。

📌 **测试不只是验证行为，也是在「宣告」设计决策。**

---

## 6.4 ⭐⭐ 缺陷：部分写入（第 93-125 行）

```python
@pytest.mark.unit
@pytest.mark.xfail(
    reason="缺陷：open(...,'w') 在循环之前就截断了文件，循环中途抛 KeyError 时"
    "留下一个 0 字节的 obs_action.json。下游用 os.path.exists() 判断"
    "'本轮采集成功' 会误判为成功，真去 json.load() 才炸。"
    "修复方案：先在内存 build 完 dict 再 open()，或写临时文件 + os.replace() 原子替换。",
    strict=True,
)
@pytest.mark.parametrize("missing", ["time", "jq", "action"])
def test_partial_write_leaves_no_corrupt_file(tmp_path, missing):
    """obs 缺任一必需键时，不应在磁盘上留下坏文件。"""
    obs = {"time": 0.0, "jq": [1, 2], "action": [3, 4]}
    del obs[missing]

    with pytest.raises(KeyError):
        recoder_single_arm(str(tmp_path), [obs])

    # 要么不创建文件，要么创建一个合法可解析的文件 —— 不能留半截。
    written = tmp_path / "obs_action.json"
    if written.exists():
        assert written.stat().st_size > 0, "留下了 0 字节的坏文件"
        json.loads(written.read_text())  # 必须可解析
```

### ⭐⭐ 这是一个「原子性」缺陷

**问题机制**：

```python
f = open(path, "w")          # ← 这一刻文件就被截断成 0 字节了！
for obs in obs_lst:
    data["time"].append(obs["time"])      # ← 这里可能 KeyError
    ...
json.dump(data, f)           # ← 永远执行不到
```

**结果**：磁盘上留下一个 **0 字节的 `obs_action.json`**。

### 为什么这个缺陷很严重

```python
# 下游代码（很自然的写法）
if os.path.exists("obs_action.json"):
    print("本轮采集成功")        # ✅ 文件确实存在
    data = json.load(f)          # 💥 JSONDecodeError: Expecting value
```

📌 **「文件存在」被当成了「采集成功」的信号，但这个信号是假的。**

**在具身智能项目里后果更严重**：数据集就是产品。
一批数据里混进几个 0 字节文件，训练时才发现，而那时已经跑了几天。

### ⭐ 修复方案：原子写入

```python
# ❌ 现在的写法
with open(path, "w") as f:
    for obs in obs_lst:
        ...build...
    json.dump(data, f)

# ✅ 方案 1：先 build 再写
data = build_dict(obs_lst)        # 出错就出错，不碰文件
with open(path, "w") as f:
    json.dump(data, f)

# ✅ 方案 2：临时文件 + 原子替换（更彻底）
tmp = path + ".tmp"
with open(tmp, "w") as f:
    json.dump(data, f)
os.replace(tmp, path)             # ← 原子操作，要么全成功要么全不动
```

📌 **`os.replace()` 在同一文件系统内是原子的** ——
不存在「替换到一半」的中间状态。这是写文件的标准安全模式。

**企业扩展：原子性的通用模式**

| 场景 | 模式 |
|---|---|
| 写文件 | 临时文件 + `os.replace()` |
| 数据库 | 事务（`BEGIN` / `COMMIT` / `ROLLBACK`） |
| 多步 API 调用 | Saga 模式 / 补偿事务 |
| 部署 | 蓝绿部署 / 原子符号链接切换 |

**共同思想：中间状态不能对外可见。**

### ⚠️ 装饰器 `xfail` vs 命令式 `pytest.xfail()`（第 116-120 行）

```python
⚠️ 用装饰器 xfail 而非命令式 pytest.xfail()：
   后者会立即中断测试，下面的断言根本不执行，
   上游修好了也不会转成 XPASS 报警（见 checkpoint-day06-07 §4.3）。
   strict=True 保证缺陷被修复后这个测试会 XPASS 失败，提醒你更新它。
```

```python
# ❌ 命令式 —— 立即中断，后面的断言是死代码
def test_x():
    pytest.xfail("已知缺陷")
    assert something          # ← 永远不执行！

# ✅ 装饰器 —— 测试正常跑，只是把结果解释为 xfail
@pytest.mark.xfail(strict=True, reason="...")
def test_x():
    assert something          # ← 会执行，红了记 XFAIL，绿了记 XPASS→FAILED
```

📌 **这是 pytest 的一个真实陷阱**，很多人会混用。
`pytest.xfail()` 更像 `pytest.skip()` —— 立即中断。

### `@parametrize` + `@xfail` 叠加

```python
@pytest.mark.xfail(strict=True, reason="...")
@pytest.mark.parametrize("missing", ["time", "jq", "action"])
```

**生成 3 个用例，每个都标记为 xfail** —— 三个键缺任何一个都有同样的问题。

### `pytest.raises` 上下文管理器

```python
with pytest.raises(KeyError):
    recoder_single_arm(str(tmp_path), [obs])
```

**断言「这段代码必须抛出 KeyError」**。如果没抛（或抛了别的），测试失败。

📌 **注意这里的双层断言结构**：
1. 必须抛 `KeyError`（`pytest.raises`）
2. **而且**不能留下坏文件（后面的 `if written.exists()`）

**第 2 点才是这条测试的重点** —— 抛异常是对的，留坏文件才是缺陷。

---

## 6.5 健壮性隐患：ndarray（第 128-140 行）

```python
@pytest.mark.xfail(
    reason="健壮性隐患（非当前可达缺陷）：json.dump 不接受 ndarray。"
    "唯一调用方 universal_task_runtime.py:111-112 已做 .tolist()，"
    "所以当前不可达。但函数从未声明'只接受 list'这一契约，"
    "新增调用方漏掉 .tolist() 即会炸，且同样留下半截文件。",
    strict=True,
)
def test_accepts_numpy_arrays(tmp_path):
```

### ⭐ 「健壮性隐患」vs「当前可达缺陷」的区分

```
当前可达缺陷：现在就会出错          →  优先级高
健壮性隐患：  现在不会出错，但很脆弱  →  记录，不一定立刻修
```

**本例的情况**：

```
recoder_single_arm(path, obs_lst)
    ↓ 内部 json.dump
    ↓ 如果 obs["jq"] 是 ndarray → TypeError: Object of type ndarray is not JSON serializable

但是：唯一的调用方已经做了 .tolist()  →  当前不会触发
```

📌 **「函数从未声明『只接受 list』这一契约」是问题的核心。**

```
调用方碰巧做对了  ≠  函数是安全的
```

**新增一个调用方，忘了 `.tolist()` → 立刻炸**，而且因为 [6.4](#64-⭐⭐-缺陷部分写入第-93-125-行) 的
原子性问题，**还会留下半截文件**（两个缺陷叠加）。

### 企业实践：怎么把隐式契约变成显式的

```python
# ① 类型注解 + mypy
def recoder_single_arm(save_path: str, obs_lst: list[dict[str, list]]) -> None:

# ② 运行时校验
if isinstance(value, np.ndarray):
    value = value.tolist()          # 兼容
    # 或
    raise TypeError("obs 的值必须是 list，收到 ndarray。请先 .tolist()")

# ③ 文档字符串明确写出
"""Args:
    obs_lst: 每项必须是 {"time": float, "jq": list, "action": list}。
             ⚠️ 值必须是 Python list，不接受 np.ndarray。
"""
```

📌 **本项目选择了「用测试记录」（xfail）** ——
因为改函数签名会影响上游，超出改动范围。**这是合理的克制。**

---

# 第七部分：命令行逐字解析

## 7.1 Docker 基础命令

```bash
# 构建（⚠️ 注意最后那个 . 是构建上下文）
docker build -f discoverse/docker/Dockerfile.test -t discoverse:test .

# 跑默认命令（CMD）
docker run --rm discoverse:test

# 覆盖 CMD，跑指定测试
docker run --rm discoverse:test pytest tests/unit -v

# 进容器调试（最有用的一条）
docker run --rm -it discoverse:test bash
```

| 参数 | 作用 |
|---|---|
| `-f <path>` | **Dockerfile 的位置** |
| `-t <name>:<tag>` | 给镜像起名字（tag） |
| `.` | **构建上下文**（`.dockerignore` 在这一层生效） |
| `--rm` | 容器退出后自动删除（不加会堆积一堆停止的容器） |
| `-it` | 交互式终端（`-i` 保持 stdin，`-t` 分配 tty） |

### 排错常用

```bash
# 看镜像体积
docker images | grep discoverse

# 看每一层多大（找瘦身目标）
docker history discoverse:test

# 看构建上下文实际传了多少（build 输出第一行）
docker build ... 2>&1 | head -1
# → Sending build context to Docker daemon  445.2MB

# 清理（磁盘满了跑这个）
docker system df           # 先看占了多少
docker system prune -a     # ⚠️ 删除所有未使用的镜像
```

### ⭐ 验证「无头」

```bash
docker run --rm discoverse:test sh -c 'echo "DISPLAY=[$DISPLAY]"; echo "MUJOCO_GL=$MUJOCO_GL"'
# 预期：DISPLAY=[]
#       MUJOCO_GL=osmesa
```

### ⭐ 验证 GPU 能不能用（Day 8-9 Step 2.1 的实验）

```bash
# 加 --gpus all：容器里能看到 GPU
docker run --rm --gpus all nvidia/cuda:11.8.0-base nvidia-smi

# 不加：同一个镜像，看不到
docker run --rm nvidia/cuda:11.8.0-base nvidia-smi
# → 报错或看不到设备
```

📌 **这两条命令就是 [4.2](#42-⭐⭐-基础镜像的选择第-13-24-行) 里
「我先验证了 GPU 能用，然后才决定不用」的证据。**

---

## 7.2 基线比对（这两天最重要的命令）

```bash
# 本机基线
source scripts/dev/env.sh && $PY -m pytest tests/ -q

# 容器里
docker run --rm discoverse:test pytest tests/ -q

# 两边输出必须一致：
# 113 passed, 4 skipped, 45 deselected, 10 xfailed
```

### ⭐ 必须同时看四个数字

| 数字 | 变了说明什么 |
|---|---|
| `passed` | 少了 → 有测试没跑或挂了 |
| **`skipped`** | **多了 → 文件缺失被静默跳过** ⚠️ |
| `deselected` | 变了 → marker 筛选出问题 |
| `xfailed` | 少了 → 有 xfail 变成 XPASS（缺陷被修了？） |

📌 **只看 `passed` 是不够的** —— `106 passed` 和 `113 passed` 都是绿的。

### 让 skip 原因可见

```bash
$PY -m pytest tests/ -q -ra
#                        ↑ 汇总所有非通过用例（含 skip/xfail 的原因）
```

**`-ra` 应该是默认参数**（本项目已写进 `pyproject.toml` 的 `addopts`）。

---

## 7.3 覆盖率

```bash
# ⭐ --cov 不带参数：读 pyproject.toml 的 [tool.coverage.run] source
$PY -m pytest tests/ --cov --cov-report=term-missing

# ❌ 别这么写 —— 分母从 967 涨到 2584，数字对不上
$PY -m pytest tests/ --cov=discoverse

# 只看某个模块（比如 recorder 的 94%）
$PY -m pytest tests/unit/test_recorder.py \
    --cov=discoverse/universal_manipulation/recorder --cov-report=term-missing

# 生成 HTML 报告（能点进去看哪行没覆盖）
$PY -m pytest tests/ --cov --cov-report=html
# 打开 htmlcov/index.html
```

`--cov-report=term-missing` 会列出**具体哪些行没被覆盖**：

```
Name                  Stmts   Miss  Cover   Missing
─────────────────────────────────────────────────────
recorder.py              47      3    94%   88-90
                                             ↑ 这三行没测
```

📌 **`Missing` 那一列是你下一步要写什么测试的直接指引。**

---

## 7.4 CI 相关

```bash
# 本地验证 YAML 语法（推 push 之前）
python -c "import yaml; print(yaml.safe_load(open('.github/workflows/ci.yml')))"

# ⭐ 一个会让人怀疑人生的 YAML 冷知识（day10-11 Step 2.6）
python -c "
import yaml
d = yaml.safe_load(open('.github/workflows/ci.yml'))
print('触发条件:', list(d.keys()))
"
# → 触发条件: ['name', True, 'jobs']
#                     ↑↑↑↑ 'on' 被 YAML 解析成了布尔值 True！
```

### ⭐ YAML 的 `on` 陷阱

**YAML 1.1 规范里，`on` / `off` / `yes` / `no` 都是布尔值！**

```yaml
on:          # ← 被解析成 True: ...
  push:
```

📌 **GitHub Actions 内部做了特殊处理，所以能用。**
但你自己用 `yaml.safe_load` 解析时会看到 `True` 而不是 `'on'` ——
**不要以为是文件写错了。**

**同类陷阱**：
```yaml
version: 3.10        # → 浮点数 3.1！
version: "3.10"      # ✅ 必须加引号
country: NO          # → False（挪威的国家代码！）
```

### 用 gh CLI 看 CI 结果

```bash
gh run list --limit 5              # 最近 5 次运行
gh run view <run-id>               # 看某次的详情
gh run view <run-id> --log-failed  # ⭐ 只看失败的日志
gh run watch                       # 实时盯着当前运行
```

---

## 7.5 排查依赖问题（Day 8-9 Step 5.4 的诊断三问）

```bash
# 第 1 问：谁 import 了 av？
grep -rn 'import av' discoverse/

# 第 2 问：那个文件怎么被加载的？
grep -n 'recorder' discoverse/universal_manipulation/__init__.py

# 第 3 问：av 在核心依赖里吗？
grep -n 'av' pyproject.toml
```

### ⚠️ 第 3 问的结果会骗你（Step 5.5）

```bash
grep -n 'av' pyproject.toml
# → 158:    "av"        ← 找到了！在 data-collection 组里
```

**看起来「声明了」，但是**：

```toml
[project.optional-dependencies]
data-collection = [        # ← 这是 optional 组！
    ...
    "av"
]
```

📌 **`pip install -e .` 只装 `[project] dependencies`，不装 optional 组。**

**这就是缺陷 L′ 的完整机制** —— 4 个包被放在了 optional 组里，
本地因为装过 `[full]` 所以有，干净环境没有。

### 验证依赖链的终极命令

```bash
# 在干净环境里验证（这就是 CI unit job 做的事）
docker run --rm -v $(pwd):/src -w /src python:3.10-slim sh -c '
  pip install -e . -q &&
  python -c "import discoverse.universal_manipulation; print(\"OK\")"
'
```

📌 **这条命令可以在本地模拟「干净的 CI 环境」** ——
不用 push 就能验证依赖声明完整性。

---

# 第八部分：面试问答速查

## Q1「你为什么要做 Docker 测试镜像？」

> 因为「在我这儿能跑」不是可交付的状态。
>
> 我做之前有个具体的证据：项目本身有个 `Dockerfile`，但它第 58 行写的是
> `ENV MUJOCO_GL=glfw` —— **glfw 需要显示器，容器里没有 `$DISPLAY`，一渲染就崩**。
> 所以那个镜像不能拿来跑测试。
>
> 我新写了 `Dockerfile.test`，用 `osmesa` 纯 CPU 离屏渲染，零显示器依赖。
>
> **验收标准是数字对齐**：容器里必须跑出和本机完全一样的
> `113 passed, 4 skipped, 45 deselected, 10 xfailed` —— 我把这行写进了
> Dockerfile 的注释，因为**这两天遇到的坑基本都是「绿灯但没测」**，
> 只看颜色不看数字会被骗。

---

## Q2「基础镜像你怎么选的？」⭐

> 我先做了实验：本机装了 `nvidia-container-toolkit`，
> `docker run --gpus all` 加与不加，`nvidia-smi` 的输出确实不同 —— **GPU 是能用的**。
>
> **但我最后选了不带 GPU 的 `python:3.10-slim`**，理由有三条：
>
> ① 这个镜像的目标运行环境是 **GitHub Actions 免费 runner，那里没有 GPU**。
> 绑死 GPU 会造成「本机绿、CI 红」。
>
> ② 实测测试瓶颈根本不在渲染 —— 113 个用例 3 秒跑完，
> 测的是配置层和 IK 求解，不是渲染性能。
>
> ③ 体积：`nvidia/cuda:11.8.0-base` 约 2 GB，`python:3.10-slim` 约 130 MB，**差 15 倍**。
>
> **「能用」不等于「该用」，要看目标环境。**
> 后来 Day 12 做 Jenkins GPU 流水线时我又做了一个 EGL 的 GPU 镜像 ——
> 那个场景确实需要 GPU，所以两个镜像并存，各自服务不同的目标环境。

---

## Q3「你在容器化过程中踩过什么坑？」⭐⭐

> 最有价值的一个是 **`.dockerignore` 差点把 `models/` 排除掉**。
>
> `models/` 有 439 MB，直觉上是瘦身大头。但实际上测试会直接加载
> `models/mjcf/manipulator/*.xml`，而那些 XML 的 `<compiler>` 标签里写着
> `meshdir="../../meshes/"` —— **MuJoCo 在编译 XML 阶段就要读 mesh 文件，不是渲染时才读**。
> 实测 `robot_airbot_play.xml` 加载后 `nmesh=14, ntex=2`。
>
> **而排除它的后果不是报错，是测试全绿。**
> 因为 `conftest.py` 里遇到 MJCF 不存在会 `pytest.skip` —— 静默兜住了。
> 镜像瘦了一大圈，测试还是绿的，但**一个 MuJoCo 模型都没真正加载过**。
>
> 我在 `.dockerignore` 里专门写了警告：「改动本文件后必须比对 skip 数」，
> 并留下了一个可操作的实验法：`mv` 走 → 跑测试 → 看 skip 数变没变 → `mv` 回来。
>
> 另一个坑是漏装 `libglib2.0-0`（cv2 的系统依赖），症状是 `106 passed` 而不是 113 ——
> **看起来完全正常**。因为 cv2 是在 fixture 里才被 import 的，所以变成 7 个 ERROR 而不是启动崩溃。
>
> **这两个坑是同一个主题：错误不会让你崩溃，而是让你看起来正常。**

---

## Q4「你的 CI 里有两个跑测试的 job，不重复吗？」⭐⭐

> 看起来重复，**其实是互补的，各自覆盖对方的盲区**。
>
> - `unit` job 用 `pip install -e .`，**会去解 `pyproject.toml` 的依赖声明**
> - `integration` job 用 Docker 镜像，而镜像是 `requirements-test.txt` + `--no-deps`，
>   **恰好绕过了依赖声明的验证**
>
> 所以：
> - **只有 `unit` job 能抓到「依赖声明不完整」** —— 我的缺陷 L′ 就是这么被抓到的
> - **只有 `integration` job 能抓到系统库缺失、镜像构建问题**
>
> 我在 `unit` job 里**刻意不加 `--no-deps`**，并在注释里写明「这是缺陷 L′ 的守护测试」。
>
> 这个缺陷很有意思：它**炸了三次，每次在不同环境**。
> Day 6-7 本地发现缺 mink/quadprog，我「看见什么缺就补什么」，没走完整条链；
> Day 8-9 进干净容器又炸了三次（av、PyOpenGL、pillow）；
> Day 10 进 CI runner 再炸一次（pyyaml）。
>
> 根因是这个包的 `__init__.py` 有 **eager import 链** —— 主动加载全部 7 个子模块，
> 任一子模块的模块级依赖缺失，**整个包连 import 都过不去**。
> 而其中两个包（PyOpenGL、pillow）此前是**靠 mujoco 和 matplotlib 间接拽进来的**，
> 我在 `pyproject.toml` 里管这叫「幸运的间接依赖」——
> **上游哪天改了传递依赖，我们什么都没改就会崩**。

---

## Q5「CI 配置里有什么值得说的判断？」

> 三个：
>
> **① 第一版 CI 故意什么都不测。** 只验证「代码能拉下来、python 能起来」。
> 因为配 CI 时会遇到一堆和测试无关的问题（YAML 缩进、分支名、Actions 版本、权限），
> 如果第一版就写满测试，**你分不清是 CI 配错了还是测试挂了**。先打通管道，再灌东西。
>
> **② lint 的范围刻意收窄到 `tests/`。**
> 实测 `discoverse/` 有 ruff 277 errors、black 59 files。
> 那是上游代码，一次性重排会制造巨大 diff 和 merge 冲突，**且与「补测试」这个目标无关**。
> 但我用 `continue-on-error: true` 加了一个「现状报告」步骤，
> **让技术债可见但不阻塞** —— 等哪天要还债了，删掉那个标记即可。
>
> **③ lint 工具版本必须钉死。**
> 不钉的话 CI 装最新版，新增规则会让刚清干净的 `tests/` 又变红 ——
> **而那不是代码变差了，是尺子换了**。

---

## Q6「你的 94% 覆盖率是怎么算的？」⭐

> 我得先澄清口径，因为**分母不同数字完全不同**：
>
> - `recorder.py` 这个模块：**19% → 94%**（简历上写的这个）
> - 整个 `universal_manipulation` 包：**41%**
> - 如果按整个 `discoverse` 算：**28%**
>
> 差别只在于统计谁。我在 `pyproject.toml` 里把 `source` 限定为
> `discoverse/universal_manipulation`，并写了注释说明理由：
> `policies/` 下有 237 个策略学习文件，**算进去会把分母从 967 稀释到 2584**，
> 数字失去指导意义。
>
> 我在 CI 里也特意注明「别写 `--cov=discoverse`」——
> **指标的口径必须稳定，否则趋势图毫无意义。**
>
> 另外我想说，**覆盖率是下限指标，不是质量证明**。
> 100% 覆盖率的代码仍然可以充满 bug —— 一个 `divide(a, b)` 只测 `divide(4,2)`
> 就有 100% 行覆盖，但没测 `b=0`。
> 覆盖率只能告诉你「哪些代码**肯定**没测」。
> 更诚实的指标是分支覆盖率和变异得分。

---

## Q7「recorder 那 94% 具体测了什么？发现了什么？」

> 我按边界条件铺开：正常输入、嵌套路径创建、**空列表**、多余字段、缺必需键、ndarray 输入。
>
> 发现了一个**原子性缺陷**：`open(path, "w")` 在循环**之前**就把文件截断了，
> 循环中途抛 `KeyError` 时，磁盘上会留下一个 **0 字节的 `obs_action.json`**。
>
> **危害在于**：下游很自然会用 `os.path.exists()` 判断「本轮采集成功」——
> 文件确实存在，所以判定成功，**真去 `json.load()` 才炸**。
> 在具身智能项目里数据集就是产品，一批数据里混进几个 0 字节文件，
> 可能训练跑了几天才发现。
>
> 修复方案我写在 xfail 的 reason 里：先在内存 build 完 dict 再 `open()`，
> 或者写临时文件 + `os.replace()` 原子替换。
>
> 我还固定了一个**没有文档的隐式契约**：输入的键是 `action`，输出的键是 `act`。
> 这个映射只存在于实现里，测试把它固定下来 —— 有人改了键名会立刻红，
> 而不是让下游解析 JSON 的代码在生产环境崩溃。

---

# 第九部分：企业开发扩展

## 9.1 Docker 镜像优化的完整工具箱

**本项目用到的**：

| 手段 | 效果 |
|---|---|
| 选对基础镜像（`-slim`） | 2 GB → 130 MB |
| `.dockerignore` | 不传 312 MB 的 `.git` |
| `--no-install-recommends` | 省几十 MB |
| `rm -rf /var/lib/apt/lists/*` **同一层** | 省几十 MB |
| `pip --no-cache-dir` | 省几十 MB |
| 分层顺序（依赖在前） | **重建时间：几分钟 → 几秒** |

**企业实践里还有的**：

### 多阶段构建（multi-stage build）

```dockerfile
# 阶段 1：构建（含编译工具链）
FROM python:3.10 AS builder
RUN pip install --user -r requirements.txt

# 阶段 2：运行（只拷贝产物，不含编译工具）
FROM python:3.10-slim
COPY --from=builder /root/.local /root/.local
```

📌 **适用于需要编译的依赖**（C 扩展）。
本项目的依赖都有 wheel，所以没用上。

### 其他手段

```dockerfile
# 非 root 用户运行（安全）
RUN useradd -m appuser
USER appuser

# 健康检查
HEALTHCHECK --interval=30s CMD python -c "import discoverse" || exit 1

# 元数据标签（可追溯）
LABEL org.opencontainers.image.source="https://github.com/..."
LABEL org.opencontainers.image.revision="${GIT_SHA}"
```

📌 **`image.revision` 标签让你能从一个运行中的容器反查它是哪个 commit 构建的** ——
生产排障必备。

---

## 9.2 CI/CD 的分层与门禁设计

**本项目的分层**（对应 `ci.yml` 的 5 个 job）：

```
smoke        管道自检          秒级     每次 push
unit         单测 + 依赖验证    分钟级   每次 push
integration  容器内全量        几分钟   每次 push
lint         代码规范          秒级     每次 push
nightly      flake 采样        十几分钟 手动触发
```

### 企业实践的完整流水线

```
提交前（本地）：
  pre-commit hook → 格式化 + 快速 lint          秒级

PR 阶段：
  ├─ lint / typecheck                          秒级
  ├─ unit test                                 分钟级
  ├─ integration test                          几分钟
  ├─ security scan（依赖 CVE、密钥泄露）         分钟级
  └─ build 产物                                 几分钟
        ↓ 全绿才能合并（branch protection）

合并到 main：
  ├─ 全量回归 + E2E
  ├─ 性能基准（对比上次，退化就告警）
  └─ 部署到 staging

定时（nightly）：
  ├─ flake 采样
  ├─ 长时间稳定性测试
  └─ 依赖更新检查（dependabot）
```

### ⭐ 门禁（quality gate）设计原则

| 原则 | 说明 |
|---|---|
| **快的在前** | lint 秒级，先跑；E2E 十分钟，后跑 |
| **失败快速** | 第一个门禁红了就停，别浪费后面的资源 |
| **门禁要稳定** | **flake 的测试绝不能做门禁**（本项目把 flake 采样排除在门禁外） |
| **可绕过但留痕** | 紧急发版可以 override，但要记录谁批准的 |

📌 **本项目把 `-m 'not flake'` 写进 `addopts` 的默认值，
就是在保护门禁的稳定性** —— 不稳定的实验永远不会阻塞 PR。

---

## 9.3 依赖管理的成熟度阶梯

**本项目所处的位置和下一步**：

| 级别 | 做法 | 本项目 |
|---|---|---|
| 0 | 没有依赖文件，`pip install` 靠记忆 | — |
| 1 | `requirements.txt`，版本浮动 | — |
| **2** | **版本钉死 + 分组（test/dev/prod）** | ✅ **在这里** |
| 3 | **lock 文件**（`poetry.lock`、`pip-tools`）—— 连传递依赖都钉死 | 下一步 |
| 4 | 自动更新 + 自动测试（Dependabot / Renovate） | |
| 5 | SBOM + 漏洞扫描 + 供应链签名 | |

### ⭐ 级别 3：为什么钉死直接依赖还不够

```
requirements-test.txt:  mujoco==3.10.0        ← 钉死了
                            ↓ mujoco 依赖
                        absl-py>=1.0.0         ← 没钉！

今天：absl-py 1.4.0
下周：absl-py 2.0.0 发布，有 breaking change
      ↓
你的镜像重建 → 装了 2.0.0 → 💥
      ↓
而你的 requirements-test.txt 一个字都没改
```

**解法：lock 文件**

```bash
# pip-tools
pip-compile requirements-test.in -o requirements-test.txt
#   → 输出包含全部传递依赖的完整清单，每个都钉死

# 或者最简单的
pip freeze > requirements-lock.txt
```

📌 **本项目已经具备升级条件** —— 版本都钉死了，
只差把传递依赖也固化。这是一个**明确的、低成本的下一步**。

**面试可以主动说**：「我现在钉死了直接依赖，但传递依赖还是浮动的。
下一步应该用 `pip-compile` 生成 lock 文件 ——
现在 mujoco 的依赖如果发布 breaking change，我的镜像重建就会崩，
而我的 requirements 文件一个字都没改。」

---

## 9.4 「静默失败」的系统性防治

**这两天遇到的坑几乎都是同一类。整理成通用的防治手段**：

| 静默失败的形式 | 防治手段 |
|---|---|
| 文件缺失 → `skip` 兜住 | **比对 skip 数**；CI 设 skip 上限告警 |
| 测试路径写错 → 跑了 0 个 | 断言收集数量：`pytest --collect-only \| wc -l` |
| 配置键名拼错 → `.get()` 默认值 | **schema 校验**（`extra="forbid"`） |
| 依赖靠间接引入 | 显式声明；干净环境验证 |
| 环境变量没设 → 用了默认值 | **写进镜像 `ENV`**，不靠 `source` |
| 覆盖率口径变化 | 口径写进配置文件，不写命令行 |
| LFS 指针没拉下来 | **主动探针**（`head -c 60`） |

### ⭐ 通用原则：为关键性质加显式断言

```
不要相信「没报错 = 正常」
要为每个关键性质加一个会失败的检查
```

**本项目的实例**：

```yaml
# 「无头」这个性质
- run: docker run --rm discoverse:test sh -c 'echo "DISPLAY=[$DISPLAY]"'

# 「models 完整」这个性质
- run: head -c 60 models/meshes/airbot_play/arm_base_0.obj

# 「依赖完整」这个性质
- run: python -c "import discoverse.universal_manipulation"
```

📌 **每一条都在把「我以为成立的前提」变成「可执行的检查」。**

### 企业实践：CI 里的元断言

```yaml
- name: 断言测试数量没有意外下降
  run: |
    COUNT=$(pytest tests/ --collect-only -q | tail -1 | grep -oE '^[0-9]+')
    if [ "$COUNT" -lt 113 ]; then
      echo "::error::收集到 $COUNT 个用例，少于基线 113 —— 有测试被静默跳过？"
      exit 1
    fi
```

📌 **这类「测试的测试」在大型项目里非常值钱** ——
它防的是「测试基础设施本身坏掉」这类最难发现的问题。

---

## 9.5 从 GitHub Actions 到 Jenkins（Day 12 的铺垫）

**本项目做了两套流水线，理由值得讲**：

| | GitHub Actions | Jenkins（Day 12） |
|---|---|---|
| 机器 | GitHub 托管的 runner | **自建机器** |
| GPU | ❌ 免费版没有 | ✅ **有** |
| 镜像 | `Dockerfile.test`（osmesa/CPU） | `Dockerfile.test.gpu`（**EGL/GPU**） |
| 成本 | 免费额度 2000 分钟/月 | 自己的电费 |
| 适合 | PR 门禁、快速反馈 | **GPU 回归、长时间任务** |

### ⭐ 为什么两套都要

```
GitHub Actions：每个 PR 都跑 → 必须快、必须免费 → CPU + osmesa
Jenkins：      GPU 相关的回归 → 需要真 GPU → EGL
```

📌 **不是「Jenkins 比 GitHub Actions 好」或反过来，
而是两个不同的目标环境需要两套基础设施。**

**这也解释了为什么要做两个 Docker 镜像** ——
镜像是为目标环境服务的，目标环境不同，镜像就该不同。

**企业里的常见组合**：
- GitHub Actions / GitLab CI → PR 门禁（快、便宜）
- Jenkins / Buildkite 自建 → 重型任务（GPU、硬件在环、长时间压测）
- 两者通过 webhook 或 API 串联

---

## 相关文档

- [day08-09-docker-test-image.md](day08-09-docker-test-image.md) — Day 8-9 Docker 测试镜像
- [day10-11-github-actions.md](day10-11-github-actions.md) — Day 10-11 GitHub Actions
- [day00-02-supplement-line-by-line.md](day00-02-supplement-line-by-line.md) — 环境、pytest 骨架、配置层逐行
- [day03-05-supplement-line-by-line.md](day03-05-supplement-line-by-line.md) — 确定性、IK、flake 逐行
- [day12-supplement-line-by-line.md](day12-supplement-line-by-line.md) — Jenkins GPU 流水线逐行
- [day13-14-supplement-line-by-line.md](day13-14-supplement-line-by-line.md) — 结构化结果契约逐行
- [../defect-report.md](../defect-report.md) — 完整缺陷清单
