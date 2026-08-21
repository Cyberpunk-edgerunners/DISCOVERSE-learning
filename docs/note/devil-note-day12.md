# 魔鬼笔记 · Day 12 —— Jenkins / 容器编排 / 图形栈的知识拆解

> 上接 [devil-note-day10-11.md](devil-note-day10-11.md)
> 体例：**概念 → 为什么这样设计 → 本项目实测 → 能迁移到别处的部分**
> 过程实录见 [devil-log-day12.md](../log/devil-log-day12.md)
> 逐行语法解析见 [day12-supplement-line-by-line.md](../tutorial/day12-supplement-line-by-line.md)

---

## 一、为什么要有第二条流水线

### 1.1 错误答案与正确答案

| ❌ 错误答案 | 为什么错 |
|---|---|
| 「简历上写了 Jenkins」 | 不是技术理由 |
| 「Jenkins 是业界标准」 | 那 GitHub Actions 也是 |
| 「多一条更保险」 | ⚠️ **两条一样的流水线不是双保险，是双倍维护 + 双倍 flake** |

⭐ **正确答案：它们跑在不同的硬件上。**

| | GitHub Actions | Jenkins（本机） |
|---|---|---|
| 机器 | 微软云免费 runner | **你桌上这台** |
| **GPU** | ❌ **物理上没有** | ✅ **RTX 4060** |
| 每次环境 | 全新 VM（干净） | 你的机器（脏，但**真实**） |
| 克隆速度 | ✅ 同数据中心，十几秒 | ❌ **实测 8 分钟没下完** |
| 时长 | 每月 2000 分钟 | 只受电费限制 |
| 私有数据 | ❌ | ✅ |

📌 **第三行和第四行方向相反** —— 这才是真实的取舍，不是「本地全面更好」。

### 1.2 能迁移的部分

> **差异化 CI 策略：轻量、跟硬件无关的测试走云端（每次 push）；重型、需特定硬件的走本地（定时）。**
>
> **它不是「两条流水线」，是「一条流水线的两个层次」。**

⚠️ 判断标准是**硬件和数据的约束**，不是工具偏好。答不出「为什么不能全放云端」，这条辅线就没有存在理由。

---

## 二、Docker 套 Docker：DinD vs DooD

### 2.1 docker.sock 是什么

**`/var/run/docker.sock` 是个 Unix socket** —— 可以理解成「Docker 引擎的电话号码」。

```
docker 命令（客户端）  --经 docker.sock 打电话-->  dockerd（真正干活的守护进程）
```

⭐ **`docker` 命令本身什么都不干**，它只是个打电话的。真正创建容器的是 `dockerd`。

**所以谁能访问 `docker.sock`，谁就能指挥 Docker —— 哪怕它自己就在容器里。**

### 2.2 ⚠️ 一个必须掰正的误解

| | 真 DinD | **本项目（DooD）** |
|---|---|---|
| 全称 | Docker **in** Docker | Docker **outside of** Docker |
| 新容器归谁管 | 容器内另一个 dockerd | **宿主机的 dockerd** |
| 新容器在哪 | **嵌套**在 Jenkins 容器里 | **平级，是「兄弟」** |
| `docker ps` 看得见宿主机的吗 | ❌ | ✅ **能，且包含自己** |

📌 **本项目实证**：容器里跑 `docker ps` 输出里**有 jenkins_server 自己** —— 这就是 DooD 的铁证。

⭐ **「兄弟容器」这四个字是今天所有路径问题的总根源。**

### 2.3 安全代价

⚠️ **挂 `docker.sock` = 把宿主机 root 权限交出去**（能起特权容器挂宿主机根目录）。

本机学习环境可接受，但**得知道自己在接受什么**。生产环境要用 rootless Docker、Kaniko 或专用构建节点。

### 2.4 能迁移的部分

> **面试被问「你怎么在 Jenkins 里跑 Docker」时，答「用 DinD」会露馅。**
>
> 正确答法：*「挂宿主机的 docker.sock，严格说是 DooD 不是 DinD —— 起出来的是兄弟容器不是子容器。这个区别很实际：因为是兄弟，`-v` 的路径参数由宿主机 dockerd 解析，写容器内路径会静默挂空目录。」*

---

## 三、⭐ 路径的三种形态（今天最值钱的知识）

同一个「路径」概念，今天以**三种不同的方式**咬人。

### 3.1 形态一：`-v` 源路径写错 → 静默挂空目录

```bash
# 在 Jenkins 容器里执行
docker run -v /var/jenkins_home/probe:/mnt alpine cat /mnt/marker.txt
# → cat: can't open ... （docker run 本身【不报错】）
```

**原因**：`-v A:B` 里的 `A` 由**宿主机** dockerd 解析。宿主机上没有 `/var/jenkins_home`。

⚠️ **Docker 遇到源路径不存在时不报错，而是创建一个空目录挂上去。**

📌 **换成 pytest 的话，症状是 `collected 0 items`** —— 可能是绿灯，可能是个查半天的怪失败。

### 3.2 形态二：`sh` 步骤访问不到宿主机目录

```bash
cd /home/ubuntu22/workspaces/airbot-play/DISCOVERSE
# → cd: can't cd to ...
```

**原因**：Jenkins 容器只挂了三样东西（jenkins_home / docker.sock / docker 二进制），**项目目录不在其中**。

| 谁 | 看得到项目目录吗 |
|---|---|
| 宿主机 | ✅ |
| **Jenkins 容器**（`sh`） | ❌ |
| **兄弟容器**（`docker run -v`） | ✅ 由宿主机解析 |

> ⭐ **通则：在这套 Jenkins 里，凡是要碰宿主机文件的操作，都得进兄弟容器。`sh` 只能碰 jenkins_home。**

### 3.3 ⭐ 形态三：两份硬编码在 `@2` 出现时分叉

```groovy
// ❌ 硬拼
WS_ON_HOST = ".../workspace/${JOB_NAME}"        // JOB_NAME 不含 @2

// ✅ 推导
WS_ON_HOST = "${WORKSPACE.replace('/var/jenkins_home', '/home/.../jenkins_home')}"
```

并发构建时 Jenkins 分配 `xxx@2` workspace：

| | 值 |
|---|---|
| `WORKSPACE` | `.../DISCOVERSE-GPU-Regression**@2**` |
| `JOB_NAME` | `DISCOVERSE-GPU-Regression` |

**症状**：`SUCCESS` + `122 passed` + **报告是空的**。

> ⭐⭐ **最能迁移的一条规律**：
>
> **同一个东西有两个名字时，永远从一个【推导】出另一个，不要两边各写一份硬编码。**
>
> 两份硬编码在「正常情况」下看起来完全一致 —— 直到某个没预料到的变化（`@2`、别名、大小写、尾斜杠）出现，它们才分叉。**而分叉时没有任何报错。**

⚠️ 适用范围远超 Jenkins：容器/宿主机路径、内网/外网域名、测试/生产配置、DB 主从连接串……**任何「同一实体的两种表示」。**

---

## 四、Linux 图形栈：osmesa / EGL / GLFW

### 4.1 三个后端各解决什么

| 后端 | 要显示器吗 | 用 GPU 吗 | 典型场景 |
|---|---|---|---|
| **GLFW** | ✅ **要** | ✅ | 开发者本机，能开窗口看 |
| **OSMesa** | ❌ 不要 | ❌ **纯 CPU** | CI（无 GPU 无显示器） |
| **EGL** | ❌ 不要 | ✅ **要** | ⭐ **GPU 服务器 / 训练集群** |

⭐ **EGL 填的是「既没显示器、又必须用 GPU」这个格子** —— 这正是 osmesa 和 glfw 都覆盖不到的地方。

📌 **企业环境的主力是 EGL**，因为服务器天然没有显示器却有卡。**而这恰好也是 Jenkins 的处境**（本机有 GPU，但通过 Jenkins 执行没有 DISPLAY）。

### 4.2 GLVND：为什么需要一个 vendor JSON

**GLVND = OpenGL Vendor Neutral Dispatch**（厂商中立派发层）。

**要解决的问题**：一台机器可能同时有 Mesa（开源）和 NVIDIA（闭源）两套 OpenGL 实现。程序调用 `eglInitialize` 时，**由谁来响应？**

GLVND 的答案：读 `/usr/share/glvnd/egl_vendor.d/*.json`，按文件名排序依次尝试。

```
50_mesa.json     → libEGL_mesa.so.0
10_nvidia.json   → libEGL_nvidia.so.0     ← 数字小的优先
```

### 4.3 ⭐ 本项目实测：toolkit 只做了一半

```bash
# 库【在】
ls /usr/lib/x86_64-linux-gnu/ | grep -i EGL
# → libEGL_nvidia.so.0 ✅   libnvidia-eglcore.so.580.95.05 ✅

# 但配置【不在】
ls /usr/share/glvnd/egl_vendor.d/
# → 50_mesa.json   ⚠️ 只有 Mesa
```

⚠️ **nvidia-container-toolkit 注入了驱动库，却不注入 GLVND vendor 配置。**

**后果**：libEGL 压根不知道 NVIDIA 的存在 → 走 Mesa 或直接失败。

**修法**：手写 `10_nvidia.json`（37 行 Dockerfile，10 行有效指令）。

### 4.4 实测收益与代价

| | osmesa | egl |
|---|---|---|
| FPS（480×640×100帧） | **54 ~ 57** | **1561 ~ 1701** |
| 画面均值 | 29.9 | **29.8** |
| 全量测试 | 122 passed | 122 passed |

**体积**：1475.35 MB → 1477.25 MB，**+1.90 MB（+0.13%）**

⭐ **画面均值一致这条比 FPS 重要** —— 只比 FPS 的话，你分不清「渲染快了」和「渲染错了」。两个后端输出同一个数，才证明换后端是**等价变换**。

### 4.5 能迁移的部分

> **面试**：*「nvidia-container-toolkit 会注入 libEGL_nvidia.so，但不注入 GLVND 的 vendor JSON。缺了那个文件，EGL 会静默退化到 Mesa 软渲染 —— 你以为在用 GPU 其实没有。所以我在 pipeline 里加了断言，直接查 eglQueryString 的 vendor 必须是 NVIDIA。」*

📌 **通用形态**：**「依赖装了一半」比「完全没装」更危险** —— 后者立刻崩，前者静默降级。

---

## 五、Jenkins 声明式 Pipeline 的心智模型

### 5.1 与 GitHub Actions 的结构对照

| | GitHub Actions | Jenkins |
|---|---|---|
| 语言 | YAML | **Groovy** |
| 结构靠 | 缩进 | **大括号** |
| 顶层 | `jobs:` | `stages {}` |
| 单元 | `job`（**各一台全新 VM**） | `stage`（**同一个 workspace**） |
| 并行性 | job **默认并行** | stage **默认串行** |
| 环境隔离 | ✅ 每个 job 全新 | ❌ **共享 workspace** |

⚠️ **最大差异：GitHub Actions 的 job 之间完全隔离，Jenkins 的 stage 之间共享工作目录。**

📌 所以 Jenkins 里「前一个 stage 装的东西后一个能用」 —— 这既是方便，也是**脏状态的来源**。

### 5.2 `params.X` vs `environment` 里的 X

| 名字 | 是什么 | shell 里读得到吗 |
|---|---|---|
| `params.RENDER_BACKEND` | Groovy 对象属性 | ❌ **不能** |
| `environment { RENDER_BACKEND = ... }` | **环境变量** | ✅ |

**不桥接的后果**（实测）：

```
+ [  = egl ]        ← [ "" = egl ] 恒假
```

⚠️ **选了 egl 却跑 osmesa，全绿不报错。**

### 5.3 ⭐ `post` 块的设计意图

| 块 | 何时跑 |
|---|---|
| `always` | ⭐ **总是** |
| `success` / `failure` / `unstable` / `aborted` / `changed` | 按结果 |

⭐ **报告收集必须放 `always`** —— **测试失败时才最需要报告**。放 `success` 里的话，最需要它的时刻反而两手空空。

⚠️ **且 `post` 自己不能再失败**：`allowEmptyResults: false` 会在前置 stage 失败时**再抛一个异常**，把真正的错因埋在十几行 Java 栈之下。

> **`post` 的职责是收集，不是制造新的失败。**

### 5.4 配置即代码

| | UI 里粘贴 | Jenkinsfile 进 git |
|---|---|---|
| 能 review | ❌ | ✅ |
| 有历史 | ❌ 只有最后一次 | ✅ |
| 能回滚 | ❌ | ✅ |
| 换机器 | ❌ 没了 | ✅ |

📌 **Jenkins 自身的数据**（job 配置、构建历史、凭据）在 `jenkins_home/`，**git 管不了也不该管**（`secrets/`、`credentials.xml` 是明文）。

要版本化 Jenkins 实例本身需要 **JCasC**（Configuration as Code）或 **Job DSL** —— 那是平台运维范畴，本项目不做。

---

## 六、⭐ 本阶段最重要的认知：能力 ≠ 收益

### 6.1 三层，今天推进了两层

```
✅ 宿主机有 GPU
✅ nvidia-container-toolkit 装了
✅ GPU 透进容器（nvidia-smi 有输出）
✅ 镜像里有 EGL 库              ← 今天打通
✅ 测试能用 GPU 渲染（31×）      ← 今天打通
❌ 有测试【真的需要】GPU          ← 仍然是零，而这一层才是根本
```

### 6.2 实测：31 倍加速，端到端收益为负

| 构建 | 后端 | 耗时 |
|---|---|---|
| #8 | `egl` | **2.83s** |
| #9 | `osmesa` | **3.08s** |

⚠️ **只差 0.25s，而且这 0.25s 里还有 GPU 上下文初始化的开销。**

**因为 122 个用例几乎不渲染** —— 全是配置层和 IK 求解。

📌 **单帧渲染 54→1701 FPS（31×），全量测试 3.08s→2.83s（8%）** —— **同一个改动，微基准上 31 倍，端到端上几乎为零。**

> ⭐ **这是「优化了不该优化的地方」的教科书案例。**
> **微基准的加速比，和端到端的收益，可以差两个数量级。**

### 6.3 那为什么还值得做

| | |
|---|---|
| **成本** | 37 行 Dockerfile（10 行有效指令），**+1.90 MB（0.13%）**，测试结果零变化 |
| **收益** | `egl` 路径被**验证可用**；挖出 `10_nvidia.json` 这个隐藏依赖；多了一条静默退化的防线 |

> ⭐ **基础设施可以先于需求存在 —— 前提是成本足够低且被验证过。**
> ⚠️ **但绝不能因为基础设施做好了，就去编造需求来用它。**

### 6.4 能迁移的部分

> **面试**：*「我把 EGL 打通了，实测 31 倍，但我当前 122 个用例没一个真的需要 GPU，两档跑完都是 3 秒左右。所以这是能力储备，不是业务收益 —— 我不会说 Jenkins 在跑 GPU 测试。正确顺序是先有需要 GPU 的测试，再去做 GPU 镜像。」*
>
> 📌 **这段展示的是「不被自己刚做完的东西推着走」的判断力**，比「我搭了 GPU 流水线」值钱得多。

---

## 七、⭐ 「声明了但行为不符，且失败时静默」—— 第 N 次

### 7.1 今天新增五例

| 案例 | 声明 | 实际 | 来源 |
|---|---|---|---|
| `-v` 写容器内路径 | 挂载了代码 | **挂了个凭空造的空目录** | Docker |
| `-e MUJOCO_GL=egl` 缺 vendor JSON | 用 GPU 渲染 | **静默退化成 Mesa** | GLVND |
| `${RENDER_BACKEND}` 未桥接 | 按参数选后端 | **恒走 osmesa 分支** | Jenkins 变量作用域 |
| `sh` 里 `cd` 项目目录 | 访问被测代码 | **容器里根本没这路径** | Docker 挂载 |
| **`WS_ON_HOST` 硬拼** | **收集测试报告** | **SUCCESS + 空报告** | Jenkins 并发 workspace |

### 7.2 ⭐ 这次的新认识

⚠️ **五条没有一条是项目代码的锅** —— 分别来自 Docker、GLVND、Jenkins 的三个不同机制。

📌 **累计看，这个模式已经在以下地方各出现过**：

```
项目代码      → MUJOCO_GL=glfw、未声明依赖、camera_configs 为空
我自己的测试  → tests/kinematics 空目录、重复函数被覆盖
Docker        → -v 静默创建空目录
GLVND         → 缺 vendor JSON 静默降级
Jenkins       → 变量作用域、挂载范围、并发 workspace
```

> ⭐⭐ **结论：它不是某个人的坏习惯，是【基础设施的普遍属性】。**
>
> **默认行为倾向于「让你继续跑下去」，而不是「让你知道出事了」。**
>
> **因为对工具作者而言，「报错打断用户」的代价，往往看起来比「悄悄用个兜底值」更高。**

### 7.3 唯一的对策

**把关键假设写成断言。**

| 假设 | 断言 |
|---|---|
| EGL 走的是 NVIDIA | `os._exit(0 if b'NVIDIA' in v else 1)` |
| mesh 不是 LFS 指针 | `head -c 60 ...`（Day 10-11） |
| 依赖声明完整 | 构建期 `python -c "import ..."`（Day 8-9） |
| 测的是干净代码 | `git status --short` 打进日志 |

📌 **注意这四条的共性：都是把「我以为」变成「机器每次都查」。**

---

## 八、排查方法论：先问工具还是对象

今天出现一次典型的矛盾证据：

| 证据 | 指向 |
|---|---|
| `1701 FPS` | GPU 渲染在工作 ✅ |
| `EGLError` | EGL 坏了 ❌ |

⭐ **该信性能数字** —— Mesa 软渲染物理上到不了 1701（实测只有 54）。报错只说明**探针写错了**（漏了 `eglInitialize`），不代表被探测对象有问题。

> ⭐ **排查时先问：是被测对象坏了，还是我的测量工具坏了？**

📌 **这是三周来反复出现的主题**：

| 天 | 测量工具本身的问题 |
|---|---|
| Day 10-11 | `tests/kinematics` 空目录 → 5 passed 假绿灯 |
| Day 10-11 | 重复函数被覆盖 → 两个测试从未执行 |
| **Day 12** | **vendor 探针漏 eglInitialize → 误判 EGL 坏了** |
| **Day 12** | **`WS_ON_HOST` 错位 → 报告收集器指向空目录** |

⚠️ **测试代码、探针、报告收集器 —— 全都是「测量工具」，全都需要被验证。**

> **「谁来测试测试本身」不是哲学问题，是每天都在发生的工程问题。**

---

## 九、一句话总结

> **Jenkinsfile 只有 176 行，但它调用的每一样东西 —— 122 个测试、无头镜像、EGL 栈、GPU 直通 —— 都是前 11 天挣出来的。**
>
> **而今天真正的产出不是那条流水线，是五个「以成功形式出现的失败」，和那条从中提炼出来的规律：同一个东西有两个名字时，永远从一个推导出另一个。**
