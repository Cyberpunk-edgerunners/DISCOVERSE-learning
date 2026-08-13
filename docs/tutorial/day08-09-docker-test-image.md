# Day 8-9 — Docker 测试镜像：把「我这儿能跑」变成「哪儿都能跑」

> 上接 [day05-flake-analysis.md](day05-flake-analysis.md)（Day 6-7 产出的是 [defect-report.md](../defect-report.md)，无教程）
> 本课产出：`.dockerignore`、`requirements-test.txt`、`Dockerfile.test`、`docker-compose.test.yml`、`tests/unit/test_recorder.py`、瘦身量化记录
> 预计耗时：两天各约 4 小时

---

## 这两天到底在干嘛（先建立直觉）

假设你今天把测试写好了，交给同事，他跑一下 —— **挂了**。

为什么？因为你机器上装了一堆东西，你自己都不知道装过。测试悄悄依赖着它们。

**Docker 就是用来消灭这句话的**：「在我这儿是好的啊」。

它的原理很笨但很有效：**从一个空白的操作系统开始，把需要的东西一件件装进去，全过程写成一个文件**。这个文件叫 `Dockerfile`。谁拿到它，都能得到一模一样的环境。

今天要做的这个环境有个额外要求：**不能有显示器**。因为将来跑测试的是 CI 服务器（Day 10-11 要做的 GitHub Actions），那机器上没有屏幕。而机器人仿真要渲染画面 —— 没屏幕怎么渲染？这就是今天的技术核心。

### 两天怎么分

| | 做什么 | 核心收获 |
|---|---|---|
| **Day 8** | 把镜像建出来、跑通 | 干净环境会**抓出你环境里的脏东西** |
| **Day 9** | 瘦身 + 补 `recorder.py` 测试 | 「评估后决定不做」也是产出 |

---

## ⚠️ 开课前必读：计划文档有五处照抄必炸

我把计划文档 §Day 8-9 的每条命令都实跑核实过。结果:

| 计划文档写的 | 实测 | 后果 |
|---|---|---|
| `COPY requirements-test.txt` | ❌ 该文件**不存在** | `docker build` 直接失败 |
| `FROM nvidia/cuda:11.8.0-base` | ⚠️ GPU 本机能用，但 **CI runner 没有 GPU** | 白背 2 GB，CI 上还跑不起来 |
| `docker images \| grep discoverse` | ⚠️ Docker 29 改了输出列 | 拿不到体积数字 |
| 装完依赖就能跑 | ❌ **漏 4 个包** | 容器内 `import discoverse` 直接崩 |
| 步骤 3「多阶段构建」 | ⚠️ 收益可能≈0 | 白增复杂度（Day 9 会量化） |

**这不是计划文档写得差。** 它写于项目之外，描述的是「一般情况下该怎么做」。**具体项目的地基长什么样，只有实跑才知道。**

📌 **你的工作不是执行计划，是把计划当假设，逐条验证。** 这句话是这两天最重要的一句。

---

# Day 8

## Step 0｜准备（30 分钟，别跳过）

### 0.1 记住基线数字

```bash
cd /home/ubuntu22/workspaces/airbot-play/DISCOVERSE
source scripts/dev/env.sh && $PY -m pytest tests/ -q
```

预期看到:

```
113 passed, 4 skipped, 45 deselected, 10 xfailed in 3.04s
```

📌 **把这行抄在纸上。** 今天的验收标准不是「容器里能跑」，是「**容器里跑出一模一样的数字**」。差一个用例，都说明容器和本机不等价。

### 0.2 ⚠️ 坑 1：`source` 不跨命令持久（我自己撞的）

```bash
# ❌ 错的 —— 两条命令是两个独立进程
source scripts/dev/env.sh
$PY -m pytest tests/ -q          # 报错：-m: command not found
```

```bash
# ✅ 对的 —— 用 && 串在同一条命令里
source scripts/dev/env.sh && $PY -m pytest tests/ -q
```

**为什么**：`source` 改的是**当前 shell 进程**的变量。新开一个终端、或另起一条命令执行，都是新进程，变量不继承。

> 💡 **这就是你今天要做 Docker 的理由之一。** 环境靠人手工 `source` 维持是**脆弱**的 —— 忘了就跑错解释器，而且**不报错，只是行为不同**。
>
> `Dockerfile` 里的 `ENV` 是**焊死**的，进容器就一定在。

### 0.3 清磁盘（重要，否则今天会卡住）

先看现状:

```bash
df -h /
docker system df
```

我这台机器的实测:

```
/dev/nvme0n1p4  489G  383G  87G  82% /       ← 489G 的盘，用了 383G，只剩 87G

TYPE          TOTAL  ACTIVE  SIZE     RECLAIMABLE
Images        10     5       19.58GB  18.47GB (94%)
Build Cache   194    0       20.64GB  2.452GB      ← ACTIVE=0，全是残留
```

**怎么读这几个数**:

- `489G` 是**总容量**，`87G` 是**还剩多少能用**。不是两个数字打架，是同一行的不同字段
- 你只有**一个数据分区**（`/dev/nvme0n1p4`），Docker 存在 `/var/lib/docker`，**也在这个分区**
- 所以 `docker build` 吃掉的每个 G，都从那 87G 里扣

今天至少要建两个镜像，反复失败重建很吃空间。**先清**:

```bash
docker builder prune          # 最安全，20.64GB 里 ACTIVE=0，能拿回约 18GB
```

⚠️ **别跑 `docker system prune -a --volumes`**。你有 6 个 volume 共 12.48GB **全部 ACTIVE**，里面可能是 gitea 仓库或 jenkins 配置，`--volumes` 会**不可逆删掉**。

### 0.4 确认 Docker 在

```bash
docker version --format '{{.Server.Version}}'      # 预期 29.1.5
```

---

## Step 1｜读懂现有 Dockerfile（30 分钟）

项目已经有一个 Dockerfile，先搞清楚**为什么不能直接拿它跑测试**。

```bash
cat discoverse/docker/Dockerfile
```

### 1.1 自己先找问题

提示：看 **第 58 行**。别急着翻答案。

<details>
<summary>想好了再展开</summary>

```dockerfile
ENV MUJOCO_GL=glfw
```

**glfw 需要显示器。** 容器里没有 `$DISPLAY`，MuJoCo 一渲染就崩。

而 `scripts/dev/env.sh` 里设的是 `MUJOCO_GL=osmesa`。**你本机测试能跑，靠的就是 env.sh 这行覆盖掉了它。**

</details>

### 1.2 三种渲染后端

MuJoCo 要把 3D 场景画成图片，有三种画法:

| 后端 | 要显示器 | 要 GPU | 速度 | 什么时候用 |
|---|---|---|---|---|
| `glfw` | ✅ 要 | 要 | 快 | 本地开发，你要**亲眼看**仿真 |
| `egl` | ❌ 不要 | ✅ 要 | 快 | 有 GPU 的无头服务器 |
| **`osmesa`** | ❌ 不要 | ❌ **不要** | 慢 | **CI / 容器**（今天用这个） |

**osmesa = Off-Screen Mesa**，纯 CPU 软件渲染。慢，但**零环境依赖** —— 这正是 CI 要的。

### 1.3 数一数它背了多少没用的东西

```bash
grep -nE "^FROM|^RUN apt|torch|gaussian|x11-apps|mesa-utils|vim" discoverse/docker/Dockerfile
```

自己问：跑 `pytest tests/` 到底需不需要 `torch`（CUDA 版约 2.5 GB）？需不需要 `gaussian_renderer`（3D 高斯渲染）？需不需要 `vim`？

> 📌 这就是你的**瘦身论据**。面试时「我把镜像从 X 缩到 Y」是结果，**「我怎么判断哪些能砍」才是能力**。
>
> 判断依据是**跑测试实际用到什么**，不是「看着像不需要」。

---

## Step 2｜决策：选基础镜像 ⭐ 今天最重要的判断

计划文档说用 `FROM nvidia/cuda:11.8.0-base-ubuntu22.04`。**先验证这个前提成不成立。**

### 2.1 先确认容器到底能不能用 GPU

```bash
docker info --format '{{json .Runtimes}}' | python3 -m json.tool | grep -E '^\s{4}"'
```

本机输出（**已装 nvidia-container-toolkit 1.19.1**）:

```
    "io.containerd.runc.v2": {
    "nvidia": {          ← 有它，才能给容器分配 GPU
    "runc": {
```

**跑个对照实验**，亲眼看清 `--gpus` 这个开关的作用:

```bash
# 加 --gpus all：容器里能看到 GPU
docker run --rm --gpus all ubuntu:22.04 nvidia-smi | head -3

# 不加：同一个镜像，看不到
docker run --rm ubuntu:22.04 nvidia-smi 2>&1 | head -1
```

**实测输出**:

```
# 加 --gpus all
NVIDIA-SMI 580.95.05   Driver Version: 580.95.05   CUDA Version: 13.0
NVIDIA GeForce RTX 4060 ...   667MiB / 8188MiB

# 不加 --gpus
docker: Error response from daemon: ... exec: "nvidia-smi": executable file not found in $PATH
```

📌 **同一个 `ubuntu:22.04` 镜像，加不加 `--gpus` 结果完全不同。**

这说明 **GPU 不是镜像自带的，是运行时注入的** —— `nvidia-smi` 这个可执行文件根本不在镜像里，是 toolkit 在启动容器时从宿主机挂进去的。

**这点下一节要用**：既然 GPU 靠运行时注入，那**同一个镜像在有 GPU 的机器和没 GPU 的机器上行为就不一样** —— 而这正是 CI 出问题的根源。

> ⚠️ 如果你的 `Runtimes` 里**没有** `nvidia`，说明 toolkit 没装。装法:
> ```bash
> curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
>   | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg \
> && curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
>   | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
>   | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
> sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
> sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker
> ```
> **不装也能完成今天的课** —— 下面会解释为什么测试镜像根本不用 GPU。

### 2.2 关键判断：能用 ≠ 该用

**GPU 能用了。那测试镜像该不该用它？**

这是今天最容易想当然的地方 —— 「有 GPU 当然用啊」。**先想清楚测试镜像最终要跑在哪。**

答案是 **Day 10-11 的 GitHub Actions**。而:

> **GitHub Actions 的免费 runner 没有 GPU。**

所以:

```
测试镜像 FROM nvidia/cuda + 依赖 GPU
        ↓
本机跑：✅ 你有 4060，跑得欢
        ↓
推到 CI：❌ runner 无 GPU → 直接挂
        ↓
结果：这两天的活白干
```

📌 **这正是你今天要消灭的那句话的高级变种** ——「在我这儿是好的啊」。只不过这次「我这儿」的特殊之处是**有张显卡**。

### 2.3 再看一遍：测试真的需要 GPU 吗

| 问题 | 答案 |
|---|---|
| 测试跑多久？ | **113 个用例 3 秒**（Step 0.1 实测） |
| 瓶颈在渲染吗？ | 否 —— 测的是配置层和 IK 求解 |
| osmesa 慢，有影响吗？ | 3 秒和 5 秒的区别，无所谓 |
| 什么才真需要 GPU？ | 3DGS 渲染、策略训练（`policies/`）、大规模数采 |

**都不是今天的事。**

> 💡 **面试可用点**（这个讲法比「我没装 toolkit」强得多）:
>
> *「我装了 nvidia-container-toolkit，容器能用 GPU。但测试镜像我**故意选了 CPU + osmesa** —— 因为它最终要跑在 GitHub Actions 的免费 runner 上，那里没有 GPU。绑死 GPU 的镜像本机绿、CI 红，等于白做。而且测试瓶颈根本不在渲染，113 个用例 3 秒跑完。」*
>
> **「我评估过 GPU，主动选了不用」和「我环境里没 GPU 所以没用」，是完全不同的两句话。** 前者是权衡，后者是将就。

### 2.4 你要做的决策

选一个，**并在 Dockerfile 里用注释写下理由**:

| 候选 | 体积 | 优点 | 代价 |
|---|---|---|---|
| `nvidia/cuda:11.8.0-base` | 2 GB+ | 和现有 Dockerfile 一致 | **CI 无 GPU，等于白背 2 GB** |
| `ubuntu:22.04` | 78 MB | 干净，apt 生态全 | 要自己装 python |
| `python:3.10-slim` | ~130 MB | python 现成 | apt 包名偶有差异 |

⚠️ **Python 版本必须对上 3.10**（看 `tests/__pycache__/` 里是 `cpython-310`）。版本不一致会在依赖 wheel 上出岔子。

📌 **不要问我选哪个。** 自己选，Step 5 撞墙时你会知道选得对不对。

---

## Step 3｜写 `.dockerignore`（40 分钟，坑最多）

### 3.1 为什么需要它

`COPY . /workspace` 会把**整个仓库**塞进镜像。仓库 768 MB，其中 `models/` 占 439 MB。

仓库里**没有** `.dockerignore`（我确认过），你要新建。先放明显该排除的:

```
.git
__pycache__
*.pyc
policies/
submodules/
```

### 3.2 `models/` 要不要排除？—— 本步最容易踩死的地方

先查测试用不用:

```bash
grep -rn "mjcf\|models/" tests/ --include="*.py" | head
```

会看到 `test_conftest_fixtures.py`、`test_robot_config.py` 等**明确引用** `models/mjcf/manipulator/`。

所以 **`models/mjcf/` 必须留**（只有 12 MB，不痛）。

### 3.3 ⚠️ 坑 2：`meshes/` 有 427 MB，看着能砍 —— 砍不得

`models/meshes/` 是大头。测试代码里**一次都没提到它**:

```bash
grep -rn "meshes" tests/ --include="*.py"     # 空
```

**但别急着砍。** 看 MJCF 文件的第 3 行:

```bash
grep -n "meshdir" models/mjcf/manipulator/robot_airbot_play.xml
```

```xml
<compiler angle="radian" meshdir="../../meshes/" texturedir="../../meshes/" .../>
```

**MJCF 在编译期就要读 mesh 文件。** 验证它真的加载了:

```bash
source scripts/dev/env.sh && $PY -c "
import mujoco
m = mujoco.MjModel.from_xml_path('models/mjcf/manipulator/robot_airbot_play.xml')
print(f'nmesh={m.nmesh} ntex={m.ntex}')"
```

实测输出 `nmesh=14 ntex=2` —— **14 个 mesh 是真加载的**。

### 3.4 🔍 砍掉会发生什么（这才是重点）

砍掉 `meshes/` → `from_xml_path` 抛异常 → 但 `tests/conftest.py` 里有:

```python
if not os.path.exists(key):
    pytest.skip(f"MJCF 不存在，跳过: {key}")
```

**异常被 skip 兜住 → 测试变绿 → 但啥也没测。**

📌 **这是今天第一次遇见本项目的核心缺陷模式**:

> **声明了要做某事，实际没做，且失败时静默。**

`.dockerignore` 挡错东西**不会报错**，只会让测试悄悄降级成 skip。**唯一的防线是比对 Step 0.1 抄下来的数字。**

### 3.5 实测各子目录体积

```bash
du -sh models/meshes/*/ | sort -h | tail -5
```

| 目录 | 体积 |
|---|---|
| `universal_robots_ur5e/` | 30 M |
| `franka_emika_panda/` | 33 M |
| `piper/` | 38 M |
| **`object/`** | **241 M** ← 占一半以上 |
| 合计 | 427 M |

**决策题给你**：`object/`（241 MB，任务物体模型）测试用不用？

**判断方法不是猜，是实验**:

```bash
mv models/meshes/object /tmp/object_backup    # 临时移走
source scripts/dev/env.sh && $PY -m pytest tests/ -q    # 看 skip 数变不变
mv /tmp/object_backup models/meshes/object    # ⚠️ 务必移回来
```

**skip 数变了 = 需要它。** 没变 = 可以排除。

---

## Step 4｜写 `requirements-test.txt`（30 分钟）

计划文档假定它存在。它不存在。你要自己造。

### 4.1 数一数测试需要什么

**别猜，去数**:

```bash
grep -rhoP '^\s*(import|from)\s+\K[a-zA-Z_][a-zA-Z0-9_]*' tests/ --include="*.py" | sort -u
```

输出:

```
discoverse mink mujoco numpy os pathlib pytest re shutil subprocess sys
```

去掉标准库（`os`/`pathlib`/`re`/`shutil`/`subprocess`/`sys`），只剩 **5 个**：`discoverse`、`mink`、`mujoco`、`numpy`、`pytest`。

### 4.2 ⚠️ 但这个清单是不完整的

`tests/` 里 `import discoverse`。那 **`discoverse` 自己又 import 了什么**？

**这就是 Step 5 要你撞的墙。现在先按这 5 个写，故意让它不全。**

### 4.3 pytest 插件也要列

```bash
source scripts/dev/env.sh && $PY -m pip list 2>/dev/null | grep -iE "pytest|coverage"
```

```
coverage 7.15.2          pytest 9.1.1             pytest-cov 7.1.0
pytest-json-report 1.5.0 pytest-metadata 3.1.1    pytest-repeat 0.9.4
pytest-timeout 2.4.0     pytest-xdist 3.8.0
```

**决策题**：`pytest-json-report`、`pytest-repeat`、`pytest-xdist` 是 Day 5 flake 实验用的，日常回归用不上。装不装？

> 两种都合理：**只装必需**（更瘦，但以后跑 flake 要重建镜像）/ **全装**（通用，多几十 MB）。
>
> 挑一个，**在文件里写注释说明理由**。这种「有意识的取舍」正是面试想看的。

### 4.4 版本要不要钉死？

```
pytest>=8.1.0     # 宽松：自动跟新版，但可能突然挂
pytest==9.1.1     # 钉死：可复现，但要手工升级
```

**测试镜像的核心价值是可复现。** 想想 Day 6-7 的缺陷 #3（pytest 超时未生效，怀疑是 pytest 9.1.1 与 pytest-timeout 2.4.0 的兼容问题，**根因至今未定位**）—— 版本浮动会让这种 bug 时有时无，更难查。

📌 我建议钉死，但**你自己决定并写理由**。

---

## Step 5｜写 Dockerfile → 构建 → 撞墙 ⭐ 今天的核心（90 分钟）

### 5.1 写 `Dockerfile.test`

不给完整代码，你自己写。要点:

1. `FROM` 用 Step 2 选的
2. **系统依赖**：osmesa 要 `libosmesa6-dev`。现有 Dockerfile 第 17 行已经装了，**可以照抄那一行**
3. **焊死环境变量**：`ENV MUJOCO_GL=osmesa` ← 整个镜像存在的理由
4. `COPY requirements-test.txt` → `pip install`
5. `COPY . /workspace` → `pip install -e .`
6. `CMD` 跑 pytest

⚠️ **分层顺序很重要**：**先** COPY 依赖清单装依赖，**再** COPY 源码。

**为什么**：Docker 按层缓存，某层没变就直接复用。源码天天改、依赖很少变 —— 依赖放前面，改源码时重建从几分钟变几秒。反过来放，每次改一行代码都要重装全部依赖。

### 5.2 构建

```bash
docker build -f discoverse/docker/Dockerfile.test -t discoverse:test .
```

### 5.3 跑，然后撞墙

```bash
docker run --rm discoverse:test pytest tests/ -q
```

**它会失败**，大概率是:

```
ModuleNotFoundError: No module named 'av'
```

（或 `OpenGL` / `PIL` / `yaml`，看 import 顺序）

### 5.4 🔍 诊断（今天最有价值的 30 分钟）

**先别 `pip install av`。** 先搞清楚**为什么** —— 测试代码里明明没有 `import av`。

自己查这条链:

```bash
# 第 1 问：谁 import 了 av？
grep -rn "import av" discoverse/universal_manipulation/

# 第 2 问：那个文件怎么被加载的？
cat discoverse/universal_manipulation/__init__.py

# 第 3 问：av 在核心依赖里吗？
grep -n "av\|PyOpenGL\|pillow\|pyyaml" pyproject.toml
```

### 5.5 ⚠️ 坑 3：第 3 问的结果会骗你

你会看到 4 个包**都有命中**:

```
72:    "PyOpenGL>=3.1.0",       ← 在 [xml-editor] 组
81:    "pyyaml",                ← 在 [act] 组
129:   "pillow>=10.2.0",        ← 在 [data-collection] 组
131:   "av"                     ← 在 [data-collection] 组
```

**「有命中」≠「在核心依赖里」。** 它们全在 `[project.optional-dependencies]` 的**可选组**里，而 `pip install -e .` **只装核心组**。

要看的是 `dependencies = [...]` 那一段（约 34-50 行）:

```bash
source scripts/dev/env.sh && $PY - <<'PYEOF'
core = open('pyproject.toml').read().split('dependencies = [')[1].split(']')[0]
for p in ['av','PyOpenGL','pillow','pyyaml']:
    print(f"{p:10} {'在核心' if p.lower() in core.lower() else '不在核心 ← 缺'}")
PYEOF
```

> 📌 **`grep` 只能告诉你字符串在不在，不能告诉你它在哪个语义块里。** 判断可达性要看**结构**。
>
> Day 6-7 踩过一模一样的坑 —— checkpoint §4.3 记的「配置继承下 grep 不足以判可达性」，是同一件事。

### 5.6 对答案

<details>
<summary>查完了再展开</summary>

**根因链**:

```
tests/  import discoverse.universal_manipulation
   ↓
__init__.py 是 eager import（全量加载，不是按需）
   ↓ 它无条件加载了：
   ├── recorder.py      → import av          （视频编码）
   ├── randomization.py → import OpenGL.GL
   │                    → from PIL import Image
   └── config_utils.py  → import yaml
   ↓
但 pyproject.toml 的核心 dependencies 里：
   av / PyOpenGL / pillow / pyyaml  ← 一个都没有
   （只在 optional 组，而 pip install -e . 不装 optional 组）
```

**本机为什么不炸**：这 4 个包在你环境里**全装着**。验证:

```bash
source scripts/dev/env.sh && $PY -c "import av, OpenGL, PIL, yaml; print('全都在')"
```

它们是被 optional 组或早期手工 pip 顺带装上的。

📌 **关键认知：你的开发环境是「脏」的，这份脏掩盖了依赖声明的缺失。**

这也解释了为什么这个缺陷能活到今天 —— **任何在现有环境里的验证都发现不了它。只有干净容器能。**

</details>

### 5.7 📌 停下来，认识到你发现了什么

**你刚找到一个新缺陷，而且它和 Day 6-7 修的缺陷 L 是同一个根。**

| | 缺陷 L（Day 6-7 已修） | **你刚发现的** |
|---|---|---|
| 缺失的包 | `mink`、`quadprog` | `av`、`PyOpenGL`、`pillow`、`pyyaml` |
| 机制 | `__init__.py` eager import | **完全相同** |
| 后果 | 干净环境 import 就崩 | **完全相同** |

**说明缺陷 L 当时只修了一半。** 修的人（几天前的你）看见 `mink` 缺就补 `mink`，**没有系统性检查整条 eager import 链**。

> 💡 **面试可用点**，讲法:
>
> *「Day 6-7 我修了一个依赖声明缺失的缺陷。Day 8 做 Docker 镜像时干净容器又炸了 —— **同一个根因，另外四个包**。这让我意识到我当时是**在修症状**。真正的修法不是补包名，是**加一道守护**。」*
>
> 而 [checkpoint-day06-07.md](../checkpoint/checkpoint-day06-07.md) §2.2 已经写了这道守护该长什么样:
>
> > ⚠️ **未加守护测试**：理想做法是 CI 里加一个干净环境 job 跑 `pip install -e . && python -c "import discoverse.universal_manipulation"`。
>
> **今天的镜像就是那个「干净环境」。** 你正在建的，恰好就是当时说「留给 Day 10-11」的那道防线。

### 5.8 修，但要想清楚修在哪一层

| 方案 | 做什么 | 优点 | 代价 |
|---|---|---|---|
| **A** | 在 `requirements-test.txt` 补 4 个包 | 5 分钟搞定 | **只修了容器，`pip install -e .` 的用户照样崩** |
| **B** | 在 `pyproject.toml` 核心依赖补 | 修在根上，所有人受益 | 核心依赖变重（`av` 拖 ffmpeg 约 30-40 MB） |
| **C** | 改 `__init__.py` 为惰性导入 | **治本**，重依赖真正可选 | 改动大，可能破坏现有 import |

⚠️ **C 有风险**：`__all__` 导出的名字改成惰性后，`from discoverse.universal_manipulation import recoder_single_arm` 的行为会变。**动它之前先跑全量回归。**

📌 **我的建议**：今天做 **B**（和缺陷 L 修法一致，改同一个地方），把 **C** 记进缺陷报告当「根治方案」。**你自己定，理由写进 commit message。**

### 5.9 验收

```bash
docker run --rm discoverse:test pytest tests/ -q
```

**必须和 Step 0.1 的数字一模一样**:

```
113 passed, 4 skipped, 45 deselected, 10 xfailed
```

⚠️ **skip 数变多了别放过** —— 那是你的 `.dockerignore` 把 MJCF 挡在外面了（Step 3.4 讲的陷阱）。

---

## Step 6｜compose + 量化（45 分钟）

### 6.1 `docker-compose.test.yml`

计划文档的骨架基本可用，注意两点:

1. `version: '3.8'` 在新版 compose 里**已废弃**，会警告，删掉
2. 挂载 `./tests:/workspace/tests:ro` 的意义是**改测试不用重建镜像**。但 `:ro` 是只读 —— 要生成覆盖率报告的话，输出目录不能只读

### 6.2 ⚠️ 坑 4：Docker 29 改了 `docker images` 输出

计划文档说 `docker images | grep discoverse` 看体积。**在 Docker 29 上拿不到。** 亲眼看:

```bash
docker images | head -3
```

```
WARNING: This output is designed for human readability. For machine-readable output, please use --format.
IMAGE          ID       DISK USAGE   CONTENT SIZE   EXTRA
```

列名变成 `DISK USAGE`/`CONTENT SIZE`，**没有 `SIZE` 列**，且 `CONTENT SIZE` 多显示 `0B`。

**正确用法**:

```bash
docker images --format '{{.Repository}}:{{.Tag}}\t{{.Size}}' | grep discoverse
```

### 6.3 Day 8 收尾验收

```bash
# 1. 能构建
docker build -f discoverse/docker/Dockerfile.test -t discoverse:test .

# 2. 数字与本机一致
docker run --rm discoverse:test pytest tests/ -q

# 3. ⭐ 证明容器里真没显示器（证明 osmesa 生效，不是碰巧）
docker run --rm discoverse:test sh -c 'echo "DISPLAY=[$DISPLAY]"; echo "MUJOCO_GL=$MUJOCO_GL"'
#    → DISPLAY=[]   MUJOCO_GL=osmesa

# 4. compose 能跑
docker compose -f docker-compose.test.yml up --abort-on-container-exit

# 5. 本机回归没被搞坏
source scripts/dev/env.sh && $PY -m pytest tests/ -q
```

**第 3 条别跳过。** 它证明的是「**在没有显示器的情况下**跑通了」，而不只是「跑通了」。两者的区别，就是这个镜像有没有价值。

---

# Day 9

## 今天为什么不只做 Docker

计划文档 Day 8-9 的步骤 3 是「多阶段构建优化」。**但我核实后认为它在你这个场景收益很小**（Step 7 会量化）。

所以今天拆两半:

| 半天 | 做什么 |
|---|---|
| 上午 | 多阶段构建 —— **先量收益，再决定做不做** |
| 下午 | **`recorder.py` 单测** ← 今天真正的价值 |

下午那半的理由:

```bash
source scripts/dev/env.sh && $PY -m pytest tests/ -q --cov --cov-report=term-missing 2>&1 | grep -E "recorder|randomization|TOTAL"
```

```
discoverse/universal_manipulation/randomization.py   303   93   69%
discoverse/universal_manipulation/recorder.py         63   51   19%   ← 这里
TOTAL                                                967  364   62%
```

**63 个 statement 漏了 51 个。** 而 `recorder.py` 只有 91 行 —— 小到一下午能啃透，却是**数据采集的最后一环**：它写坏了，前面所有仿真都白跑。

---

## Step 7｜多阶段构建：先证明它值不值得做（上午）

**别直接抄计划文档的模板。** 先问：多阶段能省什么？

它的经典价值是**编译期依赖不进最终镜像**:

```
builder 阶段：gcc / make / build-essential / *-dev 头文件 → 编译出 wheel
runtime 阶段：只 COPY 编译产物，不带编译器              → 省几百 MB
```

**它省的是「编译工具链」，不是「python 包本身」。**

### 7.1 量一下

```bash
docker history discoverse:test --format '{{.Size}}\t{{.CreatedBy}}' --no-trunc | head -15
```

看哪几层最大：apt 层有多大？里面有没有 gcc？pip 层有多大？

### 7.2 判断依据

| 情况 | 多阶段收益 | 做不做 |
|---|---|---|
| apt 层含 gcc/build-essential，几百 MB | 大 | ✅ 做 |
| 依赖全是**预编译 wheel** | **≈0** | ❌ 不做，纯增复杂度 |
| 只有 `libosmesa6-dev` 这类**运行期也要**的库 | **0** | ❌ 砍不得 |

⚠️ **`libosmesa6-dev` 是陷阱**：名字带 `-dev` 看着像编译期依赖，**但 osmesa 软件渲染运行期就要它**。砍掉 → MuJoCo 渲染直接失败。

**验证方法**（别猜）:

```bash
source scripts/dev/env.sh && $PY -m pip download --no-deps --dest /tmp/wheelcheck \
  mujoco numpy scipy opencv-python av 2>&1 | grep -iE "\.whl|\.tar\.gz" | head
```

`.whl` = 预编译，装的时候**不需要编译器**。`.tar.gz` = 源码包，**要现场编译** —— 那才需要 builder 阶段。

### 7.3 做出决定并写下来

📌 **两个结论都是合格产出**:

- **「做了多阶段，省了 X MB」** → Dockerfile 注释写明省在哪
- **「量过了，收益 < 20 MB，不做」** → checkpoint 写明**量化依据**

> 💡 **面试可用点**：第二种答案往往更值钱。
>
> *「计划里有多阶段构建这一步。我先量了 —— 依赖全是预编译 wheel，apt 层只有运行期必需的 osmesa 库，多阶段能省的不到 20 MB，却让 Dockerfile 复杂一倍、调试变难。所以我没做，把时间投到覆盖率 19% 的 recorder 模块上了。」*
>
> **「我评估后决定不做」比「我照着做了」更能体现判断力** —— 前提是你**真的量过**。

### 7.4 补上瘦身量化

如果 Day 8 你从 `nvidia/cuda`（2 GB+）换到了 `python:3.10-slim`（130 MB），**那才是主要瘦身来源**:

```bash
docker images --format '{{.Repository}}:{{.Tag}}\t{{.Size}}' | grep discoverse
```

| 镜像 | 体积 | 数据来源 |
|---|---|---|
| `discoverse:orig` | ? GB | 实测 / **估算**（标注清楚） |
| `discoverse:test` | ? MB | 实测 |

📌 没真建 `orig`（要下 torch+cu118 约 2.5 GB）就**必须标「估算」**。累计 16 条推断被实测推翻 —— **编个好看的数字比没数字更糟**。

---

## Step 8｜读懂 recorder.py（下午开始）

```bash
cat discoverse/universal_manipulation/recorder.py     # 只有 91 行
```

两个单元:

| 单元 | 行 | 干什么 |
|---|---|---|
| `PyavImageEncoder` | 9-74 | H.264 视频编码 |
| `recoder_single_arm` | 76-91 | obs-action 序列写成 JSON |

（`recoder` 是原作者的拼写，**别顺手改** —— 会断掉 `__init__.py` 的导出和调用点。）

### 8.1 看它的调用方

```bash
grep -rn "recoder_single_arm" --include="*.py" . | grep -v recorder.py
```

只有一处：`examples/universal_tasks/universal_task_runtime.py:345`。

看它喂什么进去:

```bash
sed -n '108,115p' examples/universal_tasks/universal_task_runtime.py
```

```python
"jq"     : self.mj_data.sensordata[...].tolist(),    # ← 注意 .tolist()
"action" : self.action[:self.mujoco_ctrl_dim].tolist(),
```

📌 **记住这个 `.tolist()`**，Step 9 会用到。

---

## Step 9｜TDD：先让它红 ⭐

**不要先写「能通过的测试」。** 先写**探测行为的实验**，看它到底怎么坏。

我跑过两个，你自己**亲手复现**（别抄结论）。

### 实验 A：obs 缺键会怎样

```bash
source scripts/dev/env.sh && $PY - <<'PYEOF'
import os, tempfile
from discoverse.universal_manipulation.recorder import recoder_single_arm
d = tempfile.mkdtemp()
obs_lst = [{"time":0.0, "jq":[1,2,3]}]      # 故意漏 'action'
try:
    recoder_single_arm(d, obs_lst)
except Exception as e:
    print(f"抛异常: {type(e).__name__}: {e}")
f = os.path.join(d,"obs_action.json")
print("json 存在:", os.path.exists(f), "| 大小:", os.path.getsize(f))
PYEOF
```

**实测**:

```
抛异常: KeyError: 'action'
json 存在: True | 大小: 0
```

### 9.1 🔍 停下来，看懂发生了什么

**异常抛出了，但磁盘上留下一个 0 字节的 `obs_action.json`。**

根因在第 79 行:

```python
with open(os.path.join(save_path, "obs_action.json"), "w") as fp:   # ← 先开文件（"w" 立即截断）
    save_dict = {...}
    for obs in obs_lst:            # ← 循环里才可能抛异常
        save_dict["time"].append(obs['time'])
        ...
    json.dump(save_dict, fp)       # ← 抛异常就永远走不到这
```

`open(..., "w")` **在循环之前就建好并截断了文件**。循环中途抛异常 → `with` 退出 → 留下**空文件**。

**为什么严重**：下游拿到一个**存在但是空的** JSON。

- 下游用 `os.path.exists()` 判断「这条数据采集成功了」→ **判断为成功**
- 真去 `json.load()` → `JSONDecodeError`，但可能训练流水线已经跑到一半

> 📌 **今天第二次遇见同一个模式**：**声明了产物，实际是坏的，且失败时留下看似正常的痕迹。**
>
> Day 8 你遇见过三次（glfw 无头失效 / 未声明依赖 / dockerignore 挡 MJCF），加上这次是第四次。
>
> **能在新模块里认出老模式，就是「经验」的定义。**

### 实验 B：ndarray 能序列化吗

```bash
source scripts/dev/env.sh && $PY - <<'PYEOF'
import os, tempfile, numpy as np
from discoverse.universal_manipulation.recorder import recoder_single_arm
d = tempfile.mkdtemp()
obs_lst = [{"time":0.0, "jq":np.zeros(7), "action":np.ones(7)}]
try:
    recoder_single_arm(d, obs_lst)
except Exception as e:
    print(f"抛异常: {type(e).__name__}: {e}")
f=os.path.join(d,"obs_action.json"); print("大小:", os.path.getsize(f))
PYEOF
```

**实测**：`TypeError: Object of type ndarray is not JSON serializable`，文件 31 字节（**写了一半**）。

### 9.2 ⚠️ 但这条要诚实定级

还记得 Step 8.1 那个 `.tolist()` 吗？**唯一的调用方已经转成 list 了**，所以这条路径**当前不可达**。

| | 实验 A（缺键） | 实验 B（ndarray） |
|---|---|---|
| 当前可达？ | ✅ 可达 | ❌ **不可达**（调用方有 `.tolist()`） |
| 定级 | **真缺陷** | **健壮性隐患** |
| 怎么写进报告 | 缺陷条目 | 备注：**依赖调用方自觉**，无防御 |

> 💡 Day 6-7 你把缺陷 H 从「高」降到「低」，靠的就是这种可达性分析。**「我发现了 N 个 bug」不如「我能说清哪几个真会咬人」。**
>
> 但也别把 B 一笔勾销 —— 它是**契约没写下来**：`recoder_single_arm` 从没声明「我只接受 list」。哪天有人新加调用点忘了 `.tolist()`，就炸。

---

## Step 10｜写测试

在 `tests/unit/test_recorder.py` 里写。

### 10.1 `recoder_single_arm` 部分（好写，先做）

覆盖:

1. **happy path**：正常 obs 列表 → JSON 结构正确、字段齐全
2. **空列表**：`obs_lst=[]` → 应该产出什么？（先想清楚**期望**再写断言）
3. **缺键 → 不留坏文件**（**这条会红**，因为是真缺陷）
4. `save_path` 不存在时会不会自动建

第 3 条用 xfail 标注。参照现有写法:

```bash
grep -n "xfail" tests/unit/test_task_config.py | head -3
```

⚠️ **坑 5：别用命令式 `pytest.xfail()`** —— checkpoint §4.3 记着这个坑：它**立即中断测试**，后面断言根本不执行，上游修好了也不会报警。**用装饰器** `@pytest.mark.xfail(reason=...)`。

### 10.2 `PyavImageEncoder` 部分（硬骨头）

它要真调 H.264 编码器。三个决策:

| 问题 | 选项 |
|---|---|
| 容器里有 libx264 吗？ | Day 8 的镜像**未必装**了 |
| 要不要 mock `av`？ | mock 掉就测不到真编码；不 mock 就依赖外部编码器 |
| 加什么 marker？ | `unit`？`integration`？（它写磁盘、调编码器） |

**先验证编码器在不在**:

```bash
source scripts/dev/env.sh && $PY -c "
import av
print('h264:', 'h264' in av.codecs_available)
print('libx264:', 'libx264' in av.codecs_available)"
```

我这台**本机两个都是 True**。

📌 ⚠️ **坑 6：本机有、容器里未必有。** 如果容器里没有，你就制造了一个「本机绿、CI 红」的测试 —— **这正是 Day 8 那个镜像要消灭的东西**。

**建议**：先用能力探测做优雅降级（`pytest.importorskip` 或查 `codecs_available`），然后在 Day 8 的 `Dockerfile.test` 里补上编码器依赖，**再进容器验证一遍**。

这形成闭环 —— **上午的镜像给下午的测试当裁判**。

### 10.3 跑起来看覆盖率

```bash
source scripts/dev/env.sh && $PY -m pytest tests/unit/test_recorder.py -v
source scripts/dev/env.sh && $PY -m pytest tests/ -q --cov --cov-report=term-missing 2>&1 | grep -E "recorder|TOTAL"
```

**目标**：`recorder.py` 从 19% → 70%+，TOTAL 从 62% 往上走。

---

## Step 11｜补进缺陷报告

把**实验 A** 按 [defect-report.md](../defect-report.md) 的统一格式写进去:

> 影响模块 → 复现步骤 → 预期 vs 实际 → 根因分析 → 修复方案 → 回归验证 → 影响范围

编号接着现有的排（当前 20 条，见 checkpoint §三）。

**修复方案那栏**，想想哪种对:

| 方案 | 评价 |
|---|---|
| 循环里加 `try/except` | 治标，坏文件还是留下了 |
| **先在内存 build 完 dict，再 `open()` 写** | ✅ 异常时文件根本不会被创建 |
| 写临时文件 + 成功后 `os.replace()` | ✅✅ **原子写**，最稳 |

📌 第三种是工业界处理「要么完整、要么不存在」的标准做法，叫 **atomic write**。`os.replace()` 在同一文件系统上是原子操作。**知道这个名字本身就是加分项。**

⚠️ **改代码前先跑全量回归留基线**，改完再跑一次对比。

---

## Day 9 验收清单

```bash
# 1. 多阶段决策有量化依据（做 or 不做都要有数）
docker history discoverse:test --format '{{.Size}}\t{{.CreatedBy}}' | head

# 2. 新测试通过
source scripts/dev/env.sh && $PY -m pytest tests/unit/test_recorder.py -v

# 3. recorder 覆盖率显著提升
source scripts/dev/env.sh && $PY -m pytest tests/ -q --cov --cov-report=term-missing 2>&1 | grep -E "recorder|TOTAL"

# 4. 全量回归无回退（用例数只增不减）
source scripts/dev/env.sh && $PY -m pytest tests/ -q

# 5. ⭐ 容器里也跑得通（闭环验证）
docker run --rm discoverse:test pytest tests/ -q
```

⚠️ **第 5 条最容易被跳过，但它是这两天的闭环**：新测试如果在容器里挂了（比如缺 libx264），说明镜像还不完备。

---

## 两天的坑汇总

| # | 坑 | 表现 | 教训 |
|---|---|---|---|
| 1 | `source env.sh` 不跨命令持久 | `-m: command not found` | 环境靠手工维持是脆弱的 —— **这正是要 Docker 的理由** |
| 2 | `meshes/` 427 MB 看着能砍 | 砍了 → 加载抛异常 → **被 skip 兜成绿灯** | 大目录先查**谁在引用**，别按体积决策 |
| 3 | `grep` 命中 ≠ 在核心依赖 | 4 个包全命中，其实都在 optional 组 | grep 判断不了**语义块**，要看结构 |
| 4 | Docker 29 改了 `docker images` 列名 | 拿不到体积数字 | 工具会变，命令要现验 |
| 5 | 命令式 `pytest.xfail()` | 测试**立即中断**，上游修好也不报警 | 用装饰器 |
| 6 | 本机有 libx264、容器未必有 | 本机绿、CI 红 | **进容器验证才算数** |

另外两条**开课前就核实掉**的（所以你不会撞上）：`requirements-test.txt` 不存在、eager import 拽进 4 个未声明依赖。

还有一条**中途变了的**：开课时本机没装 nvidia-container-toolkit，所以「走 CPU 路线」的理由是「GPU 用不了」。装完之后 GPU 能用了，**结论没变但理由换了** —— 变成「CI runner 无 GPU，所以主动不用」。

> 📌 这件事本身值得记进 checkpoint：**前提变了要回头改论据，而不是留着一个已经不成立的理由。** 结论碰巧还对，不代表推理还对。

**踩到新的记下来**，checkpoint 要写。

---

## 这两天真正学到的

**表面**：写了个 Dockerfile，补了几个测试。

**实际是四件事**:

1. **容器是「干净环境」的可执行定义。** 你本机能跑，是因为环境里堆了历史遗留的包。容器强迫你**把隐式依赖显式化** —— 这就是它抓出 4 个缺失依赖的原因。

2. **同一个缺陷模式，两天出现四次**：
   - `MUJOCO_GL=glfw` 在无头环境（声明了后端，实际不可用）
   - 4 个未声明依赖（声明了核心依赖，实际不全）
   - `.dockerignore` 挡掉 MJCF → skip（声明了要测，实际没测）
   - `recoder_single_arm` 异常留下 0 字节文件（声明了产物，实际是坏的）

   **共性：声明了但行为不符，且失败时静默。** 这是 [defect-report.md](../defect-report.md) §1.3 归纳的模式。**能识别模式，比能修单个 bug 高一个层级。**

3. **「评估后决定不做」是合格产出。** 多阶段构建量化后说「收益 < 20 MB，不值得」，比闷头照抄更有价值 —— 前提是**真的量过**。

4. **「我修了缺陷 L」和「我根治了依赖声明问题」是两回事。** 这两天证明了前者。守护测试（Day 10-11 的 CI）才是后者。

> **面试可用点**：被问「你怎么保证测试环境可复现」时，别只答「我用了 Docker」。
>
> 答：*「我做 Docker 测试镜像时，干净容器里 import 直接崩了 —— 发现有 4 个包被包的 eager import 链拽进来，却没写进核心依赖。本机跑得通是因为开发环境脏。**这说明我几天前修的同类缺陷只修了症状。** 所以真正的产出不是镜像，是那道『干净环境能否 import』的守护 —— 镜像只是让这道守护可执行。」*

---

## 下一步

- **Day 10-11**：GitHub Actions —— 这两天的镜像 + 测试就是 CI 的内容物
- **checkpoint §七的欠账**（inventory 编号不一致、45 组合相机存在性测试）有余力就顺手清

**记得写 `docs/checkpoint/checkpoint-day08-09.md`** —— 按惯例每条结论标注「已核实 / 待核实」，记下被推翻的推断（累计 16 条，这两天大概率 +1）。
