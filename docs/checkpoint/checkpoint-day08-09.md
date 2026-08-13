# Checkpoint · Day 8-9（2026-08-12）

> 分支：`feat/test-infra` ｜ 状态：**Day 8-9 完成（Docker 测试镜像跑通 + recorder 单测），文档待提交**
> 历史见 [checkpoint-day06-07.md](checkpoint-day06-07.md)
> 用途：下次开工只读这一份即可接上。

**本文每条推断都标注「已核实 / 待核实」。** Day 8-9 有 **6 条既有推断被实测推翻**（见第五节），累计 **17 条**（去重后）。

---

## 一、下次开工第一件事

```bash
cd /home/ubuntu22/workspaces/airbot-play/DISCOVERSE
source scripts/dev/env.sh && $PY -m pytest tests/ -q
#   预期：122 passed, 4 skipped, 45 deselected, 15 xfailed

docker compose -f docker-compose.test.yml up --abort-on-container-exit
#   预期：同样的数字 + exited with code 0

git status --short
#   预期：有未提交文件（见第二节 2.1）
```

⚠️ **工作区当前不干净** —— Day 8-9 的产出尚未提交。

---

## 二、Day 8-9 成果【已核实，实跑】

### 2.1 未提交文件清单

| 文件 | 内容 | 性质 |
|---|---|---|
| `.dockerignore` | 排除 `.git`(312MB)/`policies`/`docs` 等 | 新建 |
| `requirements-test.txt` | 测试镜像依赖，版本全部钉死 | 新建 |
| `discoverse/docker/Dockerfile.test` | CPU + osmesa 无头测试镜像 | 新建 |
| `docker-compose.test.yml` | 运行时配置 | 新建 |
| `tests/unit/test_recorder.py` | **9 passed + 5 xfail** | 新建 |
| `docs/tutorial/day08-09-docker-test-image.md` | 教程 | 新建 |
| `docs/log/devil-log-day08-09.md` | 过程实录 | 新建 |
| `docs/note/devil-note-day08-09.md` | 知识拆解 | 新建 |
| `docs/checkpoint/checkpoint-day06-07.md` | Day 7 遗留未提交 | 新建 |
| `docs/defect-report.md` | **仅改了总表**，正文待写（见第六节） | 修改 |

### 2.2 镜像

```
discoverse:test    1.55 GB
```

**验收全部通过**：

| 项 | 结果 |
|---|---|
| 容器内测试数字 | ✅ 与本机完全一致 |
| 无显示器验证 | ✅ `DISPLAY=[]` `MUJOCO_GL=osmesa` |
| compose | ✅ `exited with code 0` |
| 本机回归 | ✅ 无回退 |

### 2.3 数字对比

| 指标 | Day 7 结束 | **Day 9 结束** |
|---|---|---|
| 用例 | 113 | **122**（+9） |
| xfail | 10 | **15**（+5） |
| 覆盖率 TOTAL | 62% | **67%** |
| **`recorder.py`** | **19%** | **94%** |
| 定位缺陷总数 | 20 | **23**（+3） |
| commit | 4 | 4（**本次未提交**） |

---

## 三、新增 3 条缺陷【已核实，实跑】

### 3.1 缺陷 L′｜另外 4 个包未声明 —— **缺陷 L 只修了一半** 🟠 High

```
干净容器 pip install -e . 后：
  import discoverse.universal_manipulation
  → ModuleNotFoundError: No module named 'yaml'
```

**根因**：`__init__.py` eager import 全部子模块，而这 4 个只声明在 optional 组：

| 包 | 谁 import | 在 pyproject 的哪个组 |
|---|---|---|
| `pyyaml` | `config_utils.py:2`、`robot_config.py:8`、`task_config.py:8` | `[act]` |
| `av` | `recorder.py:6-7` | `[data-collection]` |
| `PyOpenGL` | `randomization.py:10` | `[xml-editor]` |
| `pillow` | `randomization.py:11` | `[data-collection]` |

**`pip install -e .` 只装核心组。**

⚠️ **与缺陷 L 同一文件、同一机制。** Day 6-7 修的时候只补了 `mink`/`quadprog`，**没有系统性走完整条 eager import 链**。

**当前状态**：`requirements-test.txt` 已补（容器绿了），**`pyproject.toml` 未改** —— 因为 `Dockerfile.test` 用了 `--no-deps`，容器绕过了它。**真 bug 仍在。**

### 3.2 缺陷 Y｜`recoder_single_arm` 部分写入留 0 字节坏文件 🟡 Medium

```
obs 缺 'action' 键：
  抛异常 KeyError: 'action'
  但磁盘留下 obs_action.json，大小 0 字节
```

根因在 `recorder.py:79`：`open(..., "w")` **在循环之前**就截断了文件，循环中途抛异常 → 留下空文件。

**下游用 `os.path.exists()` 判断"本轮采集成功"会误判为成功。**

**守护**：`test_recorder.py::test_partial_write_leaves_no_corrupt_file` 3 个 xfail(strict)。

### 3.3 缺陷 Z｜`PyavImageEncoder` 未 close 则整段录像丢失 🟡 Medium

```
encode 3 帧后不调用 close()：
  os.path.exists(av_file_path) → False        ← 文件完全不存在
```

PyAV 从未把缓冲刷到磁盘。采集进程被 kill → **整段录像静默丢失，不留任何痕迹**。

调用方 `universal_task_runtime.py` **没有 try/finally 保护**。

**守护**：`test_recorder.py::test_frames_survive_without_explicit_close` 1 个 xfail(strict)。

### 3.4 ⭐ 两种失败模式的对比【本次最有价值的观察】

| | 缺陷 Y | 缺陷 Z |
|---|---|---|
| 结果 | 留 **0 字节**文件 | **文件不存在** |
| 下游 `exists()` | **True → 误判成功** | False → 知道没产出 |
| 危险程度 | ⚠️ **更危险** | 相对安全 |

**"什么都没有"比"半截坏东西"安全** —— 前者无法被误认为成功。

---

## 四、环境变更【已核实】

### 4.1 nvidia-container-toolkit 已安装

```bash
docker info --format '{{json .Runtimes}}' | grep -o nvidia    # 有
docker run --rm --gpus all ubuntu:22.04 nvidia-smi            # 能看到 RTX 4060
```

版本 1.19.1，驱动 580.95.05，CUDA 13.0。

⚠️ **但测试镜像刻意不用 GPU** —— 见第五节 5.1。

### 4.2 两处代理配置已清除

| 位置 | 原值 | 状态 |
|---|---|---|
| `/etc/systemd/system/docker.service.d/http-proxy.conf` | `127.0.0.1:7897` | 已重命名为 `.disabled` |
| `~/.docker/config.json` | `172.17.0.1:7897` | 已清空（备份在 `.bak-20260811`） |

**那个 systemd 配置的创建日期是 6 月 22 日** —— 雷埋了近两个月，因为期间没用 Docker 拉过镜像。

### 4.3 磁盘

```
清理前: 489G  383G  87G   82%
清理后: 489G  361G  109G  77%      ← docker builder prune 释放 22G
```

⚠️ **别跑 `docker system prune -a --volumes`** —— 6 个 volume 共 12.48GB **全部 ACTIVE**（gitea 仓库 + jenkins 配置），会不可逆删除。

---

## 五、Day 8-9 被推翻的六条推断【已核实，实跑】

### 5.1 ⭐ 「没装 toolkit 所以 GPU 用不了」—— 前提被消除，论据必须换

| | 内容 |
|---|---|
| **原记录**（本次开工时写的） | 「无 nvidia-container-toolkit → GPU 拿不到 → 走 CPU 路线」 |
| **实测** | 装上就能用；**该走 CPU 的真正理由是「CI runner 无 GPU」** |

**结论没变，理由变了**：

| | 旧论据 | 新论据 |
|---|---|---|
| 性质 | 被环境限制，**被动** | 主动权衡，**主动** |

> 📌 **本次最重要的方法论事件：前提变了要回头改论据。结论碰巧还对，不代表推理还对。**

⚠️ 教程 Step 2 已更新为新论据。**旧说法可能散落在其他地方，引用前先核实。**

### 5.2 「`models/meshes/` 427 MB 是瘦身大头，可以砍」

| | 内容 |
|---|---|
| **原推断** | 测试 grep `meshes` 为空 → 可以排除 |
| **实测** | MJCF 第 3 行 `meshdir="../../meshes/"`，编译期就要读；`robot_airbot_play.xml` 加载后 `nmesh=14 ntex=2` |

**砍掉的后果不是报错**，是 `from_xml_path` 抛异常 → `conftest.py` 的 `pytest.skip` 静默兜住 → **测试全绿但一个 MJCF 都没加载**。

### 5.3 「`E: Unable to locate package libosmesa6-dev` 是包名错了」

| | 内容 |
|---|---|
| **原推断** | Debian trixie 与 Ubuntu 包名有差异 |
| **实测** | 三个包名**全都存在**；真因是 `apt-get update` 因代理失败，索引没拉到 |

**下游症状伪装成根因。** 日志里那三行 `Failed to fetch` 才是真的。

### 5.4 「本机有 libx264，容器里未必有」

| | 内容 |
|---|---|
| **原预警**（教程 Step 10.2） | 会造成"本机绿、CI 红" |
| **实测** | 两边 `h264`/`libx264` 都是 True —— `av` 的 PyPI wheel **自带完整 ffmpeg**（`av.libs` 72 MB） |

所以编码测试**不需要 mock**，可以真编码。

### 5.5 「多阶段构建能瘦身」

| | 内容 |
|---|---|
| **计划文档** | 步骤 3 要求做多阶段 |
| **实测** | 镜像里 gcc/g++/make/cmake **全无**；10 个依赖包 **10/10 是预编译 wheel**，0 个 `.tar.gz` |

多阶段的唯一价值是"编译工具链不进最终镜像"，**这里根本没有工具链**。收益 ≈ 0，**决定不做**。

### 5.6 「jedi 34 MB 是误装，可删」

| | 内容 |
|---|---|
| **原推断** | 代码补全库，测试用不到 |
| **实测** | 链条是 `mediapy → ipython → jedi`；卸载后确实仍 113 passed |
| **但** | `discoverse/task_base/` 下 5 个文件模块级 `import mediapy`，**Day 15-17 的 MMK2 测试要用** |

**决定保留** —— 为省 40 MB 给两周后埋坑不划算。

⚠️ **同名陷阱**：
```
discoverse/task_base/                            ← import mediapy
discoverse/universal_manipulation/task_base.py   ← 当前测试用的是这个
```

---

## 六、Day 10+ 待办

### 优先级 1：提交 + 补完缺陷报告

- [ ] **提交 Day 8-9 全部产出**（工作区当前不干净）
- [ ] [defect-report.md](../defect-report.md) **总表已补 §廿三~§廿五，正文未写** —— 三条缺陷各需一节完整格式（影响模块 → 复现 → 预期vs实际 → 根因 → 修复方案 → 回归验证 → 影响范围）
- [ ] §1.3 的贯穿模式表应补入新案例（这两天该模式出现 5 次，见 note 第十七节）

### 优先级 2：`pyproject.toml` 的真 bug

- [ ] 核心 `dependencies` 补 `pyyaml`/`av`/`PyOpenGL`/`pillow`

⚠️ **这是独立于容器的真 bug** —— `Dockerfile.test` 的 `--no-deps` 让容器绕过了 `pyproject.toml`，所以**容器绿了不代表 bug 修好**。

**待决策**：是否顺带做惰性导入（方案 C）。今天给它补上了量化价值：**`av` + `av.libs` = 106 MB，而测试从不录视频**。

### 优先级 3：Day 10-11 GitHub Actions

这两天的镜像 + 测试就是 CI 的内容物。**两条实测教训必须带进去**：

1. **CI runner 无 GPU** —— 镜像已按此设计
2. **镜像只定义了一半环境**，另一半在运行时配置里 —— `docker run` 绿、`docker compose` 红实际发生过（`:ro` 挂载杀死了 `test_task_base_wires_yaml_seed_to_randomizer`）。**CI 里怎么跑，本地就要怎么验**

另外 checkpoint-day06-07 §2.2 提的那道守护（干净环境 `pip install -e . && python -c "import ..."`）**今天已经以 `Dockerfile.test` 最后那个自检 RUN 的形式实现了** —— CI 里直接 build 这个镜像即可。

### 优先级 4：覆盖率盲区已换人

`recorder.py` 从 19% 升到 94%，**不再是最大盲区**。当前排序：

| 模块 | 覆盖率 | 备注 |
|---|---|---|
| **`task_base.py`** | **28%** | ⚠️ **新的最大盲区**，162 statements 漏 117 |
| `robot_interface.py` | 56% | |
| `task_config.py` | 63% | |
| `randomization.py` | 69% | |

### 优先级 5：更早的欠账（Day 5-7 遗留，未动）

- [ ] `defect-inventory-day02.md` 未收录 V/W/X，且用旧编号
- [ ] Day 6-7 §4.1-4.3 的三条更正尚未回写到 inventory 与 tutorial
- [ ] 45 组合的 `test_declared_cameras_exist_in_mjcf`（能防住整类"配置引用不存在的模型实体"）
- [ ] BUCKET2 根因（优先查物体朝向）
- [ ] 缺陷 #3（pytest 超时未生效）**根因仍未定位**

---

## 七、环境速查

```bash
source scripts/dev/env.sh

# 本机回归（3 秒）
$PY -m pytest tests/ -q
#   122 passed, 4 skipped, 45 deselected, 15 xfailed

# 覆盖率
$PY -m pytest tests/ -q --cov --cov-report=term-missing 2>&1 | grep -E "recorder|TOTAL"

# ---- Docker ----
# ⚠️ 所有 docker 命令必须在项目根目录跑（build context 是 .）

docker build -f discoverse/docker/Dockerfile.test -t discoverse:test .
docker run --rm discoverse:test pytest tests/ -q
docker compose -f docker-compose.test.yml up --abort-on-container-exit

# 证明容器内无显示器（这条别跳过）
docker run --rm discoverse:test sh -c 'echo "DISPLAY=[$DISPLAY]"; echo "MUJOCO_GL=$MUJOCO_GL"'

# 镜像体积（Docker 29 必须用 --format，没有 SIZE 列了）
docker images --format '{{.Repository}}:{{.Tag}}\t{{.Size}}' | grep discoverse

# 什么时候要 rebuild
#   Dockerfile.test / requirements-test.txt / .dockerignore  → 要
#   docker-compose.test.yml                                  → 不用（运行时读）
#   tests/                                                   → 不用（compose 挂载了）
#   discoverse/                                              → 要（没挂载，用镜像内副本）
```

---

## 八、Day 0-9 累计

| | Day 7 结束 | **Day 9 结束** |
|---|---|---|
| 用例 | 113 | **122** |
| 覆盖率 | 62% | **67%** |
| commit | 4 | 4（**待提交**） |
| 缺陷修复 | 5 | 5 |
| 定位缺陷总数 | 20 | **23** |
| 严重度基于实测下调 | 2 | 2 |
| 被推翻的文档推断 | 16 | **17** |

**Day 8-9 的产出是一个可复现的测试环境 + 一个从 19% 到 94% 的模块 + 3 条新缺陷。**

> **最值得带走的一条**：容器抓出的两批缺失依赖（4 个 Python 包 + 1 个系统库），**在本机环境里永远发现不了** —— 因为本机是"脏"的。
>
> 而其中 4 个 Python 包证明了 Day 6-7 修的缺陷 L **只修了症状**：看见 `mink` 缺就补 `mink`，没走完整条 eager import 链。
>
> **真正的产出不是镜像，是那道「干净环境能否 import」的守护 —— 镜像只是让这道守护可执行。**
