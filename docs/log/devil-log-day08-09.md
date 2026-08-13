# Devil Log · Day 8-9 — 过程实录

> 2026-08-12 ｜分支 `feat/test-infra`
> 这份是**踩坑实录**，按时间顺序。知识拆解见 [devil-note-day08-09.md](../note/devil-note-day08-09.md)。
> 步骤见 [tutorial/day08-09-docker-test-image.md](../tutorial/day08-09-docker-test-image.md)。

---

## 时间线概览

| 阶段 | 事件 | 结果 |
|---|---|---|
| 开工前 | 核对计划文档的 Day 8-9 | **五处照抄必炸**（含一个不存在的文件） |
| 准备 | 装 nvidia-container-toolkit | ✅ 装上了，然后**决定不用它** |
| 准备 | 清 docker 磁盘 | 87G → **109G**（回收 22G） |
| Step 5 | 第一次 build | ❌ 代理 `127.0.0.1:7897` 连不上 |
| Step 5 | 第二次 build | ❌ 代理 `172.17.0.1:7897`（**另一处配置**） |
| Step 5 | 第三次 build | ❌ `ModuleNotFoundError: yaml` ← **设计好的墙** |
| Step 5 | 第四次 build | ✅ 8 层全过 |
| 验收 | 容器内跑测试 | ❌ **106 passed, 7 errors**（缺系统库） |
| 验收 | 补 `libglib2.0-0` 后 | ✅ **113 passed** 与本机完全一致 |
| Step 6 | compose | ❌ 1 failed（`:ro` 挂载杀死一个合法测试） |
| Step 6 | 改挂载后 | ✅ 113 passed, exit code 0 |
| Step 7 | 多阶段构建评估 | **决定不做**（量化后收益 ≈ 0） |
| Step 9-10 | recorder 单测 | ✅ 覆盖率 **19% → 94%** |
| 收尾 | 全量回归 | ✅ **122 passed, 15 xfailed**，本机与容器一致 |

---

## 卡点 0｜计划文档的 Day 8-9 有五处不可用

开工前逐条核实，结果：

| 计划文档写的 | 实测 |
|---|---|
| `COPY requirements-test.txt` | ❌ **该文件全仓库不存在** |
| `FROM nvidia/cuda:11.8.0-base` | ⚠️ 前提需重新论证（见卡点 2） |
| `docker images \| grep discoverse` 看体积 | ⚠️ Docker 29 改了输出列，拿不到数字 |
| 装完依赖就能 import | ❌ **漏 4 个包** |
| 步骤 3「多阶段构建」 | ⚠️ 收益 ≈ 0（见卡点 8） |

**这不是计划文档写得差。** 它写于项目之外，描述的是「一般情况下 Docker 测试镜像该怎么做」。具体项目的地基长什么样，只有实跑才知道。

---

## 卡点 1｜`source env.sh` 不跨命令持久

第一条命令就撞了：

```bash
source scripts/dev/env.sh
$PY -m pytest tests/ -q
# /bin/bash: line 1: -m: command not found
```

`$PY` 是空的 —— `source` 只影响**当前 shell 进程**，两条独立命令是两个进程。

必须串起来：

```bash
source scripts/dev/env.sh && $PY -m pytest tests/ -q
```

> 📌 **这条坑本身就是今天要做 Docker 的理由**：环境靠人手工 `source` 维持是脆弱的 —— 忘了就跑错解释器，**而且不报错，只是行为不同**。`Dockerfile` 的 `ENV` 是焊死的。

---

## 卡点 2｜⚠️ 一个中途被推翻的前提

**开工时**：`docker info` 的 Runtimes 里只有 `runc`，没有 `nvidia`。于是写下结论：

> 「没有 nvidia-container-toolkit → GPU 用不了 → 该走 CPU 路线」

**然后用户问：为什么不能装上 toolkit 用 GPU？**

于是装了。三条命令，五分钟：

```bash
# 加源 → apt install → nvidia-ctk runtime configure → systemctl restart docker
```

装完实测：

```bash
docker info --format '{{json .Runtimes}}' | python3 -m json.tool | grep -E '^\s{4}"'
#     "io.containerd.runc.v2": {
#     "nvidia": {          ← 有了
#     "runc": {

docker run --rm --gpus all ubuntu:22.04 nvidia-smi
# NVIDIA GeForce RTX 4060 ... CUDA Version: 13.0     ← 容器能用 GPU 了
```

**前提没了，但结论仍然成立 —— 理由必须换。**

| | 原论据 | 新论据 |
|---|---|---|
| 说法 | 「没 toolkit，GPU 用不了」 | 「GPU 能用，但 **CI runner 没有**」 |
| 性质 | 被环境限制，**被动** | 主动权衡，**主动** |

新论据的核心：**GitHub Actions 免费 runner 无 GPU**。测试镜像绑死 GPU → Day 10-11 的 CI 直接跑不起来。加上 osmesa 跑 113 个用例只要 3 秒，GPU 不解决任何瓶颈。

> 📌 **这是本次最重要的方法论事件**：前提变了要**回头改论据**，而不是留着一个已经不成立的理由。
> **结论碰巧还对，不代表推理还对。**

顺带得到一个可验证的对照实验：

```bash
docker run --rm --gpus all ubuntu:22.04 nvidia-smi | head -3   # 看得到 GPU
docker run --rm ubuntu:22.04 nvidia-smi 2>&1 | head -1         # not found
```

**同一个镜像，加不加 `--gpus` 结果完全不同** —— 说明 `nvidia-smi` 根本不在镜像里，是 toolkit 在启动容器时从宿主机挂进去的。**而这正是 CI 会出问题的根源：镜像行为依赖宿主机有没有 GPU。**

---

## 卡点 3｜磁盘：489G 和 87G 不是矛盾

```
/dev/nvme0n1p4  489G  383G  87G  82% /
                 ↑     ↑     ↑
                总共  已用  剩余
```

只有**一个数据分区**，Docker 存在 `/var/lib/docker`，也在这个分区。所以 build 吃掉的每个 G 都从那 87G 里扣。

```
TYPE          TOTAL  ACTIVE  SIZE     RECLAIMABLE
Build Cache   194    0       20.64GB  2.452GB     ← ACTIVE=0，全是残留
```

`docker builder prune` 后显示只回收 2.452GB，但实际：

```
清理前: 489G  383G  87G   82%
清理后: 489G  361G  109G  77%     ← 实际释放 22G
```

**`RECLAIMABLE` 那列读窄了** —— 删掉缓存层后，被它们独占的镜像层也一并释放。

⚠️ 没跑 `docker system prune -a --volumes`：6 个 volume 共 12.48GB **全部 ACTIVE**，里面是 gitea 仓库和 jenkins 配置，`--volumes` 会不可逆删掉。

---

## 卡点 4｜两处代理配置，都指向一个死掉的代理

第一次 build 直接失败：

```
proxyconnect tcp: dial tcp 127.0.0.1:7897: connect: connection refused
```

查到**两处**配置：

| 位置 | 地址 | 管谁 |
|---|---|---|
| `/etc/systemd/system/docker.service.d/http-proxy.conf` | `127.0.0.1:7897` | docker daemon 拉镜像 |
| `~/.docker/config.json` | `172.17.0.1:7897` | **构建时容器内**的网络 |

清掉第一处后基础镜像下来了，但第二处又炸在 apt：

```
Err:1 http://deb.debian.org/debian trixie InRelease
  Could not connect to 172.17.0.1:7897 - connect (111: Connection refused)
E: Unable to locate package libosmesa6-dev
```

### ⚠️ 这里差点走错方向

`E: Unable to locate package libosmesa6-dev` **看着像包名写错了**（Debian vs Ubuntu 包名差异）。

实际不是 —— 是 `apt-get update` 三条源全部 `Failed to fetch`，索引没拉到，apt 才说"找不到包"。**绕开代理验证，三个包名全都存在：**

```bash
docker run --rm -e HTTP_PROXY= -e HTTPS_PROXY= python:3.10-slim sh -c '
apt-get update -qq; for p in libosmesa6-dev libgl1 libglx-mesa0; do
  apt-cache show $p >/dev/null 2>&1 && echo "OK $p" || echo "MISS $p"; done'
# OK libosmesa6-dev
# OK libgl1
# OK libglx-mesa0
```

> 📌 **排错时先看有没有前置步骤失败。** 日志里那三行 `Failed to fetch` 才是真因，`Unable to locate package` 只是它的下游症状。

### 时间维度上的教训

那个 systemd 代理配置的创建日期是 **6 月 22 日** —— **雷埋了快两个月才炸**，因为这期间没用 Docker 拉过镜像。

**这正是今天课程主题本身**：配置声明了但实际不成立，且平时不报错。区别在于前面几个是设计好让人撞的，这个是真实世界自己送上门的 —— 而且**没有任何人做错什么，只是环境随时间漂移了**。

---

## 卡点 5｜⭐ 设计好的墙：4 个未声明依赖

第三次 build，8 层过了 7 层，卡在最后的自检：

```
0.632 MuJoCo 3.10.0                          ← 这句成功了
0.724 File "/workspace/discoverse/universal_manipulation/config_utils.py", line 2
0.724     import yaml
0.724 ModuleNotFoundError: No module named 'yaml'
```

### 第 1 问：谁 import 了它们

```bash
grep -rn "^import yaml\|^import av\|^import OpenGL\|^from PIL" discoverse/universal_manipulation/
```

```
robot_config.py:8:import yaml
recorder.py:6:import av
recorder.py:7:import av.video
config_utils.py:2:import yaml
randomization.py:10:import OpenGL.GL as gl
randomization.py:11:from PIL import Image
task_config.py:8:import yaml
```

### 第 2 问：怎么被拉进来的

`__init__.py` 是 **eager import** —— 无条件加载全部子模块：

```python
from .config_utils import (...)      # ← 第 4 行就炸了
from .robot_config import RobotConfigLoader
...
from .randomization import SceneRandomizer     # → OpenGL, PIL
from .recorder import PyavImageEncoder, ...    # → av
```

### 第 3 问：⚠️ grep 会骗你

```bash
grep -n "\"av\"\|PyOpenGL\|pillow\|pyyaml" pyproject.toml
# 72:    "PyOpenGL>=3.1.0",
# 81:    "pyyaml",
# 129:   "pillow>=10.2.0",
# 131:   "av"
```

**四个全都命中，看着没问题。** 但按结构查：

```bash
$PY - <<'EOF'
core = open('pyproject.toml').read().split('dependencies = [')[1].split(']')[0]
for p in ['pyyaml','av','PyOpenGL','pillow']:
    print(f"{p:10} {'在核心' if p.lower() in core.lower() else '不在核心 ← 缺'}")
EOF
# pyyaml     不在核心  ← 缺
# av         不在核心  ← 缺
# PyOpenGL   不在核心  ← 缺
# pillow     不在核心  ← 缺
```

**它们全在 `[project.optional-dependencies]` 的可选组里**（`xml-editor` / `act` / `data-collection`），而 `pip install -e .` **只装核心组**。

> 📌 **grep 只能告诉你字符串在不在，不能告诉你它在哪个语义块里。**
> Day 6-7 §4.3 记过一模一样的坑（「配置继承下 grep 不足以判可达性」）。

### 这条缺陷的真正含义

| | 缺陷 L（Day 6-7 已修） | **今天发现的** |
|---|---|---|
| 缺失的包 | `mink`、`quadprog` | `pyyaml`、`av`、`PyOpenGL`、`pillow` |
| 机制 | `__init__.py` eager import | **完全相同** |
| 位置 | 同一个文件 | **同一个文件** |

**缺陷 L 当时只修了一半** —— 看见 `mink` 缺就补 `mink`，没有系统性走完整条 eager import 链。

本机四个包全装着（被 optional 组顺带装的），所以**任何在现有环境里的验证都发现不了它。只有干净容器能。**

---

## 卡点 6｜⚠️ 计划外：pip 管不到的系统库

修完 4 个包，build 过了。跑测试：

```
106 passed, 4 skipped, 45 deselected, 10 xfailed, 7 errors
```

**106 + 7 = 113** —— 数量对得上，是这 7 个跑不起来。

7 个 ERROR 的最后一行完全相同：

```
File "discoverse/envs/simulator.py:7: import cv2
E   ImportError: libgthread-2.0.so.0: cannot open shared object file
```

### 怎么认出这是什么类型的错

| 长这样 | 是什么 | 谁负责装 |
|---|---|---|
| `No module named 'yaml'` | **Python 包**缺失 | pip |
| `libXXX.so.N: cannot open shared object file` | **系统库**缺失 | apt |

**看到 `.so` 就知道是 apt 的事。** 这是它和卡点 5 那 4 个包的关键区别：

```
Python 包未声明   → pip 装不全
系统库未声明      → pip 根本管不到      ← 更深一层
```

`pip install opencv-python` 装了 cv2 的 Python 封装和 `.so`，但那个 `.so` 又链接了系统的 `libgthread-2.0.so.0` —— **pip 不管这一层**。

补 `libglib2.0-0` 后：

```
113 passed, 4 skipped, 45 deselected, 10 xfailed in 2.65s     ← 与本机完全一致
```

### 失败方式本身有信息

不是启动就崩，而是 **7 个 ERROR**。因为 `cv2` 不在测试文件顶部 import，而是**在 fixture 里**才被拉进来（`test_determinism.py:47 → discoverse/envs/__init__.py:1 → simulator.py:7`）。

只影响用到 `discoverse.envs` 的 7 个用例，其余 106 个照常绿。

> 📌 **所以「数字必须一模一样」是对的验收标准。** 只看「跑起来了没报错」，106 passed 看着挺正常。

---

## 卡点 7｜`docker run` 绿、`docker compose` 红

同一个镜像，compose 跑出 1 failed：

```
OSError: [Errno 30] Read-only file system:
  '/workspace/discoverse/configs/tasks/_tmp_seed_wiring_test.yaml'
```

`test_task_base_wires_yaml_seed_to_randomizer` 要在 `tasks/` 目录内创建临时 YAML。测试注释解释了原因：

> 为什么临时文件放在 tasks/ 目录内：
> `place_block.yaml` 头部有 `extends: "templates/place_object.yaml"`，是相对路径。放到 `tmp_path` 会解析失败。

**这是配置继承机制的约束，不是测试写得随便。**

而 compose 里挂了 `./discoverse:/workspace/discoverse:ro` —— 只读，写不了。

### 三个选项

| 方案 | 会往宿主机 `discoverse/` 写吗 |
|---|---|
| A 挂载但去掉 `:ro` | ✅ **会写** |
| **B 完全不挂 `discoverse/`** | ❌ **不会** —— 容器改的是镜像内副本 |
| C 保持 `:ro` + 给测试加 skip | ❌ 为迁就配置而砍覆盖 |

选 B。关键区别：

> **`COPY` 是拍照片，`volumes` 是开窗户。**
> `COPY .` 在 build 时拍了张快照进镜像（独立的）；`volumes` 是开个窗户直通宿主机（共享的）。

改完 `113 passed`，`exited with code 0`。

> 📌 **镜像只定义了一半的环境，另一半在运行时配置里。**
> 如果 Day 10-11 在 CI 里用 compose 而本地只测过 `docker run`，就会在 CI 上撞这个。

---

## 卡点 8｜多阶段构建：量化后决定不做

计划文档的步骤 3。**先证明它值不值得做。**

多阶段的经典价值是**编译期依赖不进最终镜像**（gcc / build-essential）。所以关键问题是：镜像里有多少体积是编译工具链？

```bash
docker run --rm discoverse:test sh -c 'for t in gcc g++ cc make ld cmake; do
  command -v $t >/dev/null 2>&1 && echo "有 $t" || echo "无 $t"; done'
# 无 gcc / 无 g++ / 无 cc / 无 make / 无 ld / 无 cmake
```

**一个编译器都没有。**

再验证依赖是否需要现场编译：

```bash
$PY -m pip download --no-deps --dest /tmp/wheelcheck \
  mujoco numpy scipy opencv-python av pyyaml PyOpenGL pillow mink quadprog
# .whl: 10    .tar.gz: 0
```

**10 个包全部预编译。**

| 检查项 | 实测 | 含义 |
|---|---|---|
| 编译器 | 全无 | 没有工具链可砍 |
| 依赖 | 10/10 是 wheel | 不需要 builder 阶段 |
| apt 层 | osmesa + glib | **运行期必需**，砍了 MuJoCo 跑不了 |

**收益 ≈ 0 MB，代价是 Dockerfile 复杂一倍。决定不做。**

⚠️ `libosmesa6-dev` 是个陷阱：名字带 `-dev` 看着像编译期依赖，**但 osmesa 软件渲染运行期就要它**。

### 真正的体积在哪

```
726 MB  pip install
458 MB  COPY .（主要是 models/）
239 MB  apt install
122 MB  基础镜像
─────────
1.55 GB
```

按包看：

| 包 | 体积 | 测试需要吗 |
|---|---|---|
| opencv(`cv2`+libs) | 193 MB | ✅ |
| scipy | 136 MB | ✅ |
| **av + av.libs** | **106 MB** | ❌ 只有 recorder 用，测试不录视频 |
| **jedi** | **34 MB** | ❌ 代码补全库 |

追 jedi 的来源：

```
requirements-test.txt 里的 mediapy → ipython → jedi (34 MB)
```

实测卸载 `mediapy`+`ipython`+`jedi` 后仍 **113 passed**。

**但决定保留** —— `discoverse/task_base/` 下 5 个文件（`mmk2_task_base.py` 等）模块级 `import mediapy`，Day 15-17 的 MMK2 测试要用。为省 40 MB 埋坑不划算。

⚠️ 这里有个同名陷阱：

```
discoverse/task_base/                            ← import mediapy
discoverse/universal_manipulation/task_base.py   ← 当前测试用的是这个
```

**`av` 那 106 MB 给了惰性导入方案一个量化价值** —— 昨天只能说「治本」，今天能说「省 106 MB」。

---

## 卡点 9｜recorder.py：先让它红

`recorder.py` 只有 91 行，覆盖率 **19%**，Day 2 至今没动。

### 实验 A：obs 缺键

```python
obs_lst = [{"time":0.0, "jq":[1,2,3]}]      # 故意漏 'action'
recoder_single_arm(d, obs_lst)
```

```
抛异常: KeyError: 'action'
json 存在: True | 大小: 0        ← ⚠️
```

**异常抛出了，但磁盘上留下一个 0 字节的 `obs_action.json`。**

根因在第 79 行：

```python
with open(os.path.join(save_path, "obs_action.json"), "w") as fp:   # ← "w" 立即截断
    save_dict = {...}
    for obs in obs_lst:            # ← 循环里才抛异常
        ...
    json.dump(save_dict, fp)       # ← 永远走不到
```

**下游用 `os.path.exists()` 判断"本轮采集成功"会误判为成功**，真去 `json.load()` 才炸。

### 实验 B：ndarray

```
TypeError: Object of type ndarray is not JSON serializable
文件大小: 31 字节（写了一半）
```

**但要诚实定级** —— 唯一调用方 `universal_task_runtime.py:111-112` 已做 `.tolist()`：

| | 实验 A | 实验 B |
|---|---|---|
| 当前可达 | ✅ | ❌ **不可达** |
| 定级 | **真缺陷** | **健壮性隐患** |

### 实验 C：编码器不 close

写 `PyavImageEncoder` 测试时顺手探的：

```python
enc = PyavImageEncoder(64, 48, d, 9)
for i in range(3):
    enc.encode(np.zeros((48,64,3), np.uint8), i*0.1)
print("close 前文件存在:", os.path.exists(enc.av_file_path))   # False
enc.close()
print("close 后大小:", os.path.getsize(enc.av_file_path))       # 1636
```

**不 close 则文件完全不存在** —— PyAV 从未把缓冲刷到磁盘。采集进程被 kill → 整段录像静默丢失。

### ⭐ 两种失败模式的对比

| | 失败后果 | 哪个更危险 |
|---|---|---|
| `recoder_single_arm` | 留 **0 字节**坏文件 | ⚠️ 下游 `exists()` 判为成功 |
| `PyavImageEncoder` | **连文件都没有** | 下游至少知道"没产出" |

**同一个文件里两种失败模式，后者反而更安全。**

---

## 卡点 10｜编码器测试：预期的坑没出现

教程预警「本机有 libx264、容器里未必有」，会造成"本机绿、CI 红"。实测：

```
本机   : h264 True, libx264 True
容器里 : h264 True, libx264 True
```

**两边都有。** 因为 `av` 的 PyPI wheel **自带完整 ffmpeg**（就是那 106 MB 里的 `av.libs`），不依赖系统装 ffmpeg。

所以决定**不 mock，写真编码测试** —— mock 掉就只是在测自己写的假对象，编码链路一行没走到。真编码 3 帧 64×48 只要约 0.1s。

而且断言写成**往返验证**（round-trip）而非只查文件非空：

```python
with av.open(str(out)) as container:
    frames = list(container.decode(video=0))
assert len(frames) == 3
assert (frames[0].width, frames[0].height) == (64, 48)
```

> **一个损坏的 MP4 同样非空。** 只断言"文件存在且非空"等于没验证。

---

## 卡点 11｜新测试不在镜像里

写完 `test_recorder.py` 后：

```bash
docker run --rm discoverse:test pytest tests/unit/test_recorder.py -q
# ERROR: file or directory not found: tests/unit/test_recorder.py
```

镜像是写测试**之前**建的，`COPY . /workspace/` 的快照不含新文件。

但 compose 挂了 `./tests`，所以：

```bash
docker compose -f docker-compose.test.yml up --abort-on-container-exit
# 122 passed, 4 skipped, 45 deselected, 15 xfailed
```

**没重建镜像，却看到了新测试** —— 又一次印证 `COPY`（快照）与 `volumes`（窗户）的区别。

---

## Day 8-9 最终数字

| 指标 | Day 7 结束 | **Day 9 结束** |
|---|---|---|
| 用例 | 113 | **122**（+9） |
| xfail | 10 | **15**（+5） |
| 覆盖率 TOTAL | 62% | **67%** |
| `recorder.py` | **19%** | **94%** |
| 定位缺陷总数 | 20 | **23**（+3） |
| 被推翻的文档推断 | 16 | **17**（+1，见卡点 2） |
| 镜像 | — | `discoverse:test` **1.55 GB** |

**容器与本机数字完全一致**：`122 passed, 4 skipped, 45 deselected, 15 xfailed`，`exit code 0`。

无显示器验证：

```
DISPLAY=[]
MUJOCO_GL=osmesa
```

---

## 未完成（Day 10+）

- [ ] 缺陷报告 §廿三~§廿五 正文（总表已补，详细章节待写）
- [ ] `pyproject.toml` 补 4 个核心依赖（**独立于容器的真 bug**，`--no-deps` 让容器绕过了它）
- [ ] `randomization.py` 覆盖率 69%，是当前最大盲区（recorder 已让位）
- [ ] `task_base.py` 覆盖率 **28%**，比 randomization 更低
- [ ] Day 10-11：GitHub Actions —— 这两天的镜像 + 测试就是 CI 的内容物
- [ ] checkpoint §七的欠账（inventory 编号不一致、45 组合相机存在性测试）
