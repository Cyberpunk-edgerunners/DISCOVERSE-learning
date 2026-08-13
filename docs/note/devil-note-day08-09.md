# Devil Note · Day 8-9 — 容器化与隐式依赖的知识拆解

> 配套：[tutorial/day08-09-docker-test-image.md](../tutorial/day08-09-docker-test-image.md)（步骤）｜[log/devil-log-day08-09.md](../log/devil-log-day08-09.md)（过程实录）
> 本篇只讲**知识点**，不讲步骤。

---

## 一、容器是「干净环境」的可执行定义

**这两天最重要的一句话。**

你本机能跑测试，靠的是环境里堆了一层历史沉积：以前装某个功能顺带拉进来的包、系统自带的图形库、两个月前配的代理。**这些从未被声明过，但测试依赖它们。**

容器强迫你**把隐式依赖显式化**：

```
本机：能跑  ← 因为环境「脏」
容器：崩了  ← 因为环境「净」
       ↓
差集 = 你从未声明过的依赖
```

Day 8 抓出的两批依赖，都是这个差集里的东西。

> **「在我这儿是好的啊」的技术定义**：你的环境与目标环境的差集非空，而你不知道差在哪。
> **容器把这个差集变得可计算。**

---

## 二、依赖有三层，pip 只管中间那层

```
第 3 层  你写的代码                    ← git 管
第 2 层  Python 包（numpy, cv2…）      ← pip 管
第 1 层  系统库（.so 文件）            ← apt 管   ← ⚠️ pip 管不到
第 0 层  内核                          ← 宿主机提供（容器不带）
```

Day 8 两个缺陷正好分属两层：

| 缺陷 | 层 | 报错长相 |
|---|---|---|
| `yaml`/`av`/`OpenGL`/`PIL` 未声明 | 第 2 层 | `ModuleNotFoundError: No module named 'yaml'` |
| `libglib2.0-0` 缺失 | **第 1 层** | `ImportError: libgthread-2.0.so.0: cannot open shared object file` |

### 怎么一眼分辨

| 报错 | 是什么 | 去哪修 |
|---|---|---|
| `No module named 'X'` | Python 包 | `requirements.txt` / `pyproject.toml` |
| `libXXX.so.N: cannot open shared object file` | **系统库** | `Dockerfile` 的 `apt-get install` |

**看到 `.so` 就知道是 apt 的事。**

### 为什么 pip 管不到

```
pip install opencv-python
  └─ 装了 cv2 的 Python 封装 + 一个 .so 文件
        └─ 那个 .so 又动态链接了系统的 libgthread-2.0.so.0
              └─ pip 不管这一层，它假设系统上有
```

wheel 打包时会带一部分依赖库（`opencv_python.libs` 那 115 MB 就是），但不会带全 —— glib 这类"任何 Linux 桌面都有"的库通常被假设存在。

**在 slim 镜像里，这个假设不成立。**

### 排查工具

```bash
ldd /path/to/xxx.so | grep "not found"
```

`ldd` 列出一个 `.so` 依赖的所有库，`not found` 的就是缺的。这是查第 1 层缺失最直接的手段。

---

## 三、⭐ eager import：一个 `__init__.py` 决定整个包的依赖下限

```python
# discoverse/universal_manipulation/__init__.py
from .config_utils import (...)              # → yaml
from .robot_config import RobotConfigLoader  # → yaml
from .mink_solver import MinkIKSolver        # → mink, quadprog
from .randomization import SceneRandomizer   # → OpenGL, PIL
from .recorder import PyavImageEncoder, ...  # → av
```

**后果**：哪怕你只想用其中一个小功能——

```python
from discoverse.universal_manipulation import RobotConfigLoader   # 我只要这个
```

——Python 也会把 `av`、`OpenGL`、`PIL`、`yaml`、`mink` **全部加载一遍**。缺任何一个，**整个包 import 就失败**。

### 对立面：惰性导入

`discoverse/envs/simulator.py:246` 正好是个正面例子：

```python
def some_function():
    import screeninfo        # ← 函数内 import，用到才加载
```

所以 `screeninfo` 虽然被引用，测试却从来碰不到它。

### 这不只是"依赖声明"问题

| 视角 | eager import 的代价 |
|---|---|
| 依赖管理 | 可选依赖变成硬依赖 |
| **镜像体积** | **`av` 单独占 106 MB，而测试从不录视频** |
| 启动速度 | import 一个包要加载全部子模块 |
| 故障隔离 | 视频编码坏了 → **配置加载也用不了** |

> 📌 **Day 9 给惰性导入方案补上了量化价值**：昨天只能说「治本」，今天能说「省 106 MB」。
> **能把架构改进换算成数字，说服力完全不同。**

---

## 四、⭐⭐ grep 判断不了语义块

Day 8 差点被骗过去：

```bash
grep -n "pyyaml" pyproject.toml
# 81:    "pyyaml",          ← 有！那没问题吧？
```

**有，但在 `[project.optional-dependencies]` 的 `act` 组里。** 而 `pip install -e .` 只装核心 `dependencies`。

```toml
dependencies = [              # ← 核心：一定装
    "numpy", "mujoco", ...
]

[project.optional-dependencies]   # ← 可选：要显式指定才装
act = ["pyyaml", ...]              # pip install -e ".[act]"
```

### 正确做法：按结构查

```python
core = open('pyproject.toml').read().split('dependencies = [')[1].split(']')[0]
for p in ['pyyaml','av','PyOpenGL','pillow']:
    print(f"{p:10} {'在核心' if p.lower() in core.lower() else '不在核心'}")
```

### 这个教训出现过两次

| 时间 | 场景 |
|---|---|
| Day 6-7 §4.3 | 「配置继承下 grep 不足以判可达性」 |
| **Day 8** | 「grep 命中 ≠ 在核心依赖」 |

> **`grep` 回答的是「这些字符出现过吗」，不是「它在语义上生效吗」。**
> 判断可达性必须看**结构**：它在哪个块里、那个块什么时候生效、谁会读它。

---

## 五、修在哪一层决定谁受益

发现 4 个包缺失后，有三个改法：

| 方案 | 改哪 | 谁受益 | 代价 |
|---|---|---|---|
| A | `requirements-test.txt` | **只有容器** | 5 分钟，但 `pip install -e .` 的用户照样崩 |
| B | `pyproject.toml` 核心依赖 | 所有安装者 | 核心依赖变重（av 拖 ffmpeg 约 30-40 MB） |
| C | `__init__.py` 改惰性导入 | 所有人 + **省 106 MB** | 改动大，可能破坏现有 import 路径 |

### 关键认知：A 和 B 修的不是同一个问题

```
问题一：我的容器跑不起来      → 改 requirements-test.txt
问题二：任何人 pip install -e . 都会崩   → 改 pyproject.toml
```

**第二个问题跟 Docker 一点关系都没有。** 容器只是把它照出来了。

而 `Dockerfile.test` 里的 `--no-deps` 让容器**完全绕过** `pyproject.toml`：

```dockerfile
RUN pip install --no-cache-dir --no-deps -e .
```

所以只改 `pyproject.toml` **不会让容器变绿**，只改 `requirements-test.txt` **不会修好真 bug**。

> 📌 **容器像体检报告。它告诉你"血糖高"——**
> 改 requirements = 让这次体检数值好看；改 pyproject = 治血糖。

---

## 六、「评估后决定不做」是合格产出

计划文档要求做多阶段构建。量化后的结论是**不做**：

| 检查项 | 实测 | 含义 |
|---|---|---|
| 镜像里有编译器吗 | gcc/g++/make/cmake **全无** | 没有工具链可砍 |
| 依赖要现场编译吗 | **10/10 是预编译 wheel** | 不需要 builder 阶段 |
| apt 层装了什么 | osmesa + glib，**运行期必需** | 砍了就跑不了 |

多阶段的唯一价值是「编译期依赖不进最终镜像」。**这里根本没有编译期依赖。**

> **面试可用点**：
> *「计划里有多阶段构建这一步。我先量了——依赖全是预编译 wheel，apt 层只有运行期必需的 osmesa 库，多阶段能省的不到 20 MB，却让 Dockerfile 复杂一倍。所以我没做，把时间投到覆盖率 19% 的 recorder 模块上了。」*
>
> **「我评估后决定不做」比「我照着做了」更能体现判断力** —— 前提是**真的量过**。

### 同一天还有第二个「不做」

`mediapy` 拖着 ipython → jedi 共约 40 MB，实测卸载后仍 113 passed。**但决定保留**——`discoverse/task_base/` 下 5 个文件模块级 import 它，Day 15-17 的 MMK2 测试要用。

**为省 40 MB 给两周后的自己埋坑，不划算。**

---

## 七、前提变了，要回头改论据

Day 8 开工时写下：

> 「没有 nvidia-container-toolkit → GPU 用不了 → 该走 CPU 路线」

装上 toolkit 后，前提没了。**但结论仍然成立** —— 理由必须换：

> 「GPU 能用，但 CI runner 没有 → 仍然走 CPU 路线」

| | 旧论据 | 新论据 |
|---|---|---|
| 性质 | 被环境限制，**被动** | 主动权衡，**主动** |
| 面试听感 | 「他环境不行」 | 「他知道 CI 约束」 |

> 📌 **结论碰巧还对，不代表推理还对。**
>
> 这是 checkpoint 体系「每条标注已核实/待核实」的意义：**核实的是推理链，不只是结论**。累计 17 条推断被推翻，靠的就是回头查。

---

## 八、`COPY` 是拍照片，`volumes` 是开窗户

这是理解容器文件系统的核心比喻。

| | `COPY .` | `volumes` 挂载 |
|---|---|---|
| 发生时机 | **build 时** | **run 时** |
| 本质 | 快照，独立副本 | 直通宿主机，共享 |
| 容器改了会影响宿主机吗 | ❌ 不会 | ✅ **会** |
| 宿主机改了容器看得到吗 | ❌ 看不到（要重建） | ✅ 立刻看到 |

### Day 9 的两次印证

**其一**：写完 `test_recorder.py` 后 `docker run` 说文件不存在（镜像是之前建的快照），但 `docker compose` 能看到（挂了 `./tests`）。

**其二**：`test_task_base_wires_yaml_seed_to_randomizer` 要往 `discoverse/configs/tasks/` 写临时文件。挂 `:ro` → `OSError [Errno 30]`；不挂 → 用镜像内副本，可写且**不污染宿主机**。

### 什么时候要 rebuild

| 改了什么 | 要 rebuild |
|---|---|
| `Dockerfile` / `requirements.txt` / `.dockerignore` | ✅ |
| `docker-compose.yml` | ❌ 运行时读的 |
| 挂载了的目录（`tests/`） | ❌ |
| 没挂载的目录（`discoverse/`） | ✅ |

---

## 九、⭐ 镜像只定义了一半的环境

`docker run` 绿、`docker compose` 红 —— **同一个镜像，两种结果**。

差别只在挂载配置。

```
环境 = 镜像（build 时固化） + 运行时配置（挂载/环境变量/网络）
```

如果本地只测过 `docker run`，而 CI 用 compose，**那一半没被测过的配置会在 CI 上炸**。

> 📌 **Day 10-11 的直接教训**：CI 里怎么跑，本地就要怎么验。

---

## 十、断言强度：非空 ≠ 正确

写 `PyavImageEncoder` 测试时的关键选择：

```python
# 弱断言
assert out.stat().st_size > 0        # 一个损坏的 MP4 同样非空

# 强断言：往返验证（round-trip）
with av.open(str(out)) as container:
    frames = list(container.decode(video=0))
assert len(frames) == 3
assert (frames[0].width, frames[0].height) == (64, 48)
```

**数据编进去 → 从磁盘读回来 → 内容对得上。** 这才证明编码链路真的走通了。

### 同一个原则的其他形态

| 场景 | 弱断言 | 强断言 |
|---|---|---|
| 写 JSON | 文件存在 | `json.load()` 能解析且结构正确 |
| 写视频 | 文件非空 | 能解码回相同帧数尺寸 |
| 配置加载 | 不抛异常 | **值真的被下游消费了**（§1.3 的模式） |

> **「没报错」是最弱的断言。** 它只排除了最显眼的失败方式。

---

## 十一、mock 的代价

`PyavImageEncoder` 要真调 H.264 编码器。教程预警「本机有 libx264、容器未必有」，实测两边都有 —— 因为 `av` 的 PyPI wheel **自带完整 ffmpeg**（`av.libs` 那 72 MB）。

于是选择**不 mock**：

| | mock `av` | 真编码 |
|---|---|---|
| 速度 | 快 | 3 帧 64×48 约 0.1s |
| 环境依赖 | 无 | 需要编码器（实测两边都有） |
| **测到了什么** | **自己写的假对象** | **真实编码链路** |
| 覆盖率数字 | 虚高 | 真实 |

> ⚠️ **mock 掉外部依赖后，覆盖率数字会好看，但那些行只是"被执行过"，不是"被验证过"。**
> 判断标准：**这个 mock 让测试失去了发现什么缺陷的能力？**

---

## 十二、两种失败模式：静默坏文件 vs 静默无文件

`recorder.py` 一个文件里有两个缺陷，失败方式恰好互补：

| | `recoder_single_arm` | `PyavImageEncoder` |
|---|---|---|
| 触发 | obs 缺键 | 未调 `close()` |
| 结果 | 留下 **0 字节**文件 | **文件完全不存在** |
| 下游 `os.path.exists()` | **True → 误判为成功** | False → 知道没产出 |
| 危险程度 | ⚠️ **更危险** | 相对安全 |

**"什么都没有"比"半截坏东西"安全**，因为前者无法被误认为成功。

### 根因：`with open()` 的位置

```python
with open(path, "w") as fp:      # ← "w" 立即截断/创建文件
    for obs in obs_lst:          # ← 循环里才可能抛异常
        ...
    json.dump(save_dict, fp)     # ← 抛异常就永远走不到
```

**文件在数据准备好之前就被创建了。**

### 三种修法

| 方案 | 评价 |
|---|---|
| 循环里加 `try/except` | 治标，坏文件还是留下了 |
| 先在内存 build 完 dict，再 `open()` | ✅ 异常时文件根本不会被创建 |
| **写临时文件 + `os.replace()`** | ✅✅ **原子写（atomic write）** |

`os.replace()` 在同一文件系统上是**原子操作** —— 要么完全替换，要么完全没发生，不存在中间状态。这是工业界处理"要么完整要么不存在"的标准做法。

---

## 十三、可达性分析决定缺陷定级

`recoder_single_arm` 不能序列化 ndarray 是真的：

```
TypeError: Object of type ndarray is not JSON serializable
```

**但唯一调用方已经做了 `.tolist()`**（`universal_task_runtime.py:111-112`），所以这条路径**当前不可达**。

| | 缺键（实验 A） | ndarray（实验 B） |
|---|---|---|
| 当前可达 | ✅ | ❌ |
| 定级 | **真缺陷** | **健壮性隐患** |
| 报告写法 | 缺陷条目 | 备注：依赖调用方自觉，无防御 |

> 📌 **「我发现了 N 个 bug」不如「我能说清哪几个真会咬人」。**
> Day 6-7 把缺陷 H 从「高」降到「低」，用的是同一种分析。

**但也别一笔勾销** —— 隐患的本质是**契约没写下来**：函数从未声明"我只接受 list"。新增调用方漏掉 `.tolist()` 就会炸。

---

## 十四、失败方式本身携带信息

容器第一次跑测试：`106 passed, 7 errors`。

**106 + 7 = 113** —— 数量对得上，说明不是测试内容变了，是这 7 个跑不起来。

而且 7 个 ERROR 的**最后一行完全相同** → 同一个根因，只需修一处。

### 为什么是 ERROR 而不是启动就崩

`cv2` 不在测试文件顶部 import，是**在 fixture 里**才被拉进来：

```
test_determinism.py:47 → discoverse/envs/__init__.py:1 → simulator.py:7 → import cv2
```

所以只影响用到 `discoverse.envs` 的 7 个用例。

> 📌 **这就是「数字必须一模一样」的意义**。只看「跑起来了没报错」，106 passed 看着挺正常。
> **差 7 个用例才是信号。**

### 排错的通用顺序

```
1. 数字差多少？        → 确定范围（7 个 vs 全崩）
2. 最后一行是什么？    → 那才是根因，上面是调用栈
3. 多个错误一样吗？    → 一样 = 一个根因
4. 哪类缺失？          → No module = pip / .so = apt
5. 顺调用栈反推是谁要的
6. 查谁提供            → apt-cache search
```

---

## 十五、下游症状会伪装成根因

```
E: Unable to locate package libosmesa6-dev
```

**看着像包名写错了**（Debian vs Ubuntu 差异）。实际不是——上面还有：

```
Err:1 http://deb.debian.org/debian trixie InRelease
  Could not connect to 172.17.0.1:7897
W: Failed to fetch ... (×3)
```

`apt-get update` 三条源全部失败 → 索引没拉到 → apt 才说"找不到包"。

绕开代理验证，三个包名**全都存在**。

> 📌 **排错时先看有没有前置步骤失败。** 日志要从上往下读，不是只看最后一行。
>
> 与知识点十四并不矛盾：**pytest 的每个 ERROR 块内部**最后一行是根因；**整段构建日志**要看最早的失败。

---

## 十六、环境会随时间漂移

那个 systemd 代理配置的创建日期是 **6 月 22 日** —— 雷埋了近两个月才炸，因为这期间没用 Docker 拉过镜像。

| | 声明 | 实际 |
|---|---|---|
| `HTTP_PROXY=127.0.0.1:7897` | 走代理 | **代理软件早就不跑了** |

**没有任何人做错什么。** 配置写的时候是对的，代理停了之后就不对了，而**没有任何机制会告诉你这件事**。

> **这是容器化最根本的价值**：`Dockerfile` 里的一切都是显式声明的，从零开始构建，**不会有历史包袱**。
>
> 本机环境是**累积**的，容器环境是**声明**的。

---

## 十七、贯穿模式在 Day 8-9 出现了五次

[defect-report.md](../defect-report.md) §1.3 归纳的模式：**声明了但行为不符，且失败时静默。**

这两天遇见五次：

| # | 声明 | 实际 |
|---|---|---|
| 1 | `MUJOCO_GL=glfw`（现有 Dockerfile:58） | 无头环境下不可用 |
| 2 | 核心依赖齐全 | **少 4 个包** |
| 3 | `HTTP_PROXY=...:7897` | 代理早已停止 |
| 4 | `:ro` 挂载保护源码 | **顺带杀死一个合法测试** |
| 5 | `recoder_single_arm` 产出 JSON | **0 字节坏文件** |

其中第 4 条尤其值得注意——**它不是缺陷，是一个正确配置的副作用**。说明这个模式不限于 bug，**任何"声明"都可能有未预期的下游影响**。

> **能在新场景里认出老模式，就是"经验"的定义。**

---

## 十八、Day 8-9 方法论清单

1. **计划文档是假设，不是事实** —— 逐条验证，五处不可用
2. **前提变了要回头改论据** —— 结论对不代表推理对
3. **grep 判断不了语义块** —— 可达性要看结构
4. **修在哪一层决定谁受益** —— 容器绿 ≠ bug 修好
5. **评估后不做也是产出** —— 前提是真的量过
6. **断言强度：非空 ≠ 正确** —— 往返验证才算数
7. **可达性决定定级** —— 说清哪几个真会咬人
8. **数字必须一模一样** —— 106 passed 也是失败
9. **下游症状会伪装成根因** —— 日志从上往下读
10. **mock 的代价是失去发现缺陷的能力**

---

## 十九、Day 8-9 被推翻的假设

| 假设 | 实测 |
|---|---|
| 「没装 toolkit 所以 GPU 用不了」 | 装上就能用；**该走 CPU 是因为 CI runner 无 GPU** |
| 「`meshes/` 427 MB 是瘦身大头，可以砍」 | MJCF `meshdir` 编译期就要读，砍了被 `pytest.skip` 静默兜住 |
| 「`E: Unable to locate package` 是包名错了」 | 是 `apt-get update` 因代理失败，包名全对 |
| 「本机有 libx264、容器未必有」 | 两边都有，`av` wheel 自带 ffmpeg |
| 「多阶段构建能瘦身」 | 镜像里一个编译器都没有，收益 ≈ 0 |
| 「jedi 34 MB 是误装，可删」 | 是 `mediapy → ipython → jedi`，而 mediapy 给 MMK2 用 |

**累计 17 条写进文档的推断被实测推翻**（Day 7 时是 16 条）。

> 排查就是不断提出假设并杀死它们。**「我不知道」是合法结论，「我猜是 X」写成「根因是 X」不是。**
