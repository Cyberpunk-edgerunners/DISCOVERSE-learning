# Checkpoint · Day 12（2026-08-17）

> 分支：`feat/test-infra` ｜ 状态：**Day 12 完成（Jenkins 5-stage 流水线，两档渲染后端均绿）**
> 历史见 [checkpoint-day10-11.md](checkpoint-day10-11.md)
> 用途：下次开工只读这一份即可接上。

**本文每条推断都标注「已核实 / 待核实」。** Day 12 有 **13 条推断被实测推翻**（计划文档 8 + 实施中 5），**单日最多**，累计 **33 条**。

---

## 一、下次开工第一件事

```bash
cd /home/ubuntu22/workspaces/airbot-play/DISCOVERSE
source scripts/dev/env.sh && $PY -m pytest tests/ -q
#   预期：122 passed, 4 skipped, 45 deselected, 15 xfailed

git status --short
#   预期：3 个 Day 10-11 文档 + 3 个 Day 12 文档未跟踪（见 §七）
```

⚠️ **`source` 只在当前终端窗口有效。** 新开终端不 source 的话 `$PY` 为空，命令会变成 `-m pytest ...` → `-m: command not found`。【已核实】

---

## 二、Day 12 成果【已核实，构建 #1-#10 实证】

### 2.1 提交清单（2 个 commit，已提交未推送）

| commit | 内容 |
|---|---|
| `8c14d67` | build: 新增 GPU 测试镜像（EGL 无头渲染） |
| `802fbe1` | ci: 新增 Jenkins GPU 回归流水线（Day 12） |

⚠️ **尚未 push。**【已核实】

### 2.2 产出文件

| 文件 | 说明 |
|---|---|
| `Jenkinsfile` | 176 行，5 stage，参数化双后端 |
| `discoverse/docker/Dockerfile.test.gpu` | 37 行（10 行有效指令），`FROM discoverse:test` + EGL |
| `docs/tutorial/day12-jenkins.md` | 主教程 |
| `docs/tutorial/day12-supplement-line-by-line.md` | **逐行解析**（Jenkinsfile/命令/日志/pytest 符号） |

### 2.3 Jenkins 流水线

```
job: DISCOVERSE-GPU-Regression
Definition: Pipeline script（⚠️ UI 粘贴，非 SCM —— 见 §七欠账）
stages: 环境自检 / 渲染后端自检 / 代码状态 / GPU 可见性 / 回归测试
参数: RENDER_BACKEND = osmesa | egl
```

| 构建 | 后端 | 镜像 | libEGL | 结果 |
|---|---|---|---|---|
| **#8** | `egl` | `discoverse:test-gpu` | **4** | ✅ 122 passed **2.83s** |
| **#9** | `osmesa` | `discoverse:test` | **0** | ✅ 122 passed **3.08s** |
| **#10** | `osmesa` | `discoverse:test` | 0 | ❌ 1 failed（**故意**，验证失败路径） |

⭐ **`libEGL 4 vs 0` 是参数真的换了镜像的铁证**，不只换了字符串。【已核实】

### 2.4 ⭐ EGL 改造实测数据【已核实】

| 后端 | FPS（480×640×100帧） | 画面均值 |
|---|---|---|
| `osmesa` CPU | **54 ~ 57** | 29.9 |
| **`egl` GPU** | **1561 ~ 1701** | **29.8** |

**体积代价**：1475.35 MB → 1477.25 MB = **+1.90 MB（+0.13%）**

⭐ **画面均值一致 → 换后端是等价变换**（不是「渲染错了所以快」）。【已核实】

### 2.5 数字对比

| 指标 | Day 11 结束 | **Day 12 结束** |
|---|---|---|
| 用例 | 122 | **122**（不变） |
| 覆盖率 TOTAL | 67% | **67%**（不变） |
| 定位缺陷总数 | 25 | **26**（+1） |
| 缺陷修复 | 6 | 6（不变） |
| commit | 13 | **15**（+2） |
| GitHub Actions job | 5 | 5 |
| **Jenkins stage** | **0** | **5** |
| **测试镜像** | 1 | **2** |

📌 **用例数和覆盖率都不动是预期结果** —— 今天只加基础设施，一行测试代码都没碰。**「换了渲染后端但数字纹丝不动」正是验收信号。**【已核实】

---

## 三、⭐ Day 12 被推翻的 13 条【已核实】

### 3.1 计划文档 8 条（照抄一行跑不起来）

| # | 计划写的 | 实测 |
|---|---|---|
| 1 | `git@github.com:`（SSH） | Jenkins 容器**无任何 SSH key** |
| 2 | `conda activate discoverse` | 容器里 **`python3: not found`** |
| 3 | `agent { docker { } }` | **`docker-workflow` 插件未装**（89 个里没有） |
| 4 | `MUJOCO_GL='glfw'` | 无 DISPLAY 必崩 |
| 5 | `pytest tests/simulation` | 只有 5 个用例（假绿灯） |
| 6 | `junit 'test-results/*.xml'` | 路径对但**没人生成该文件** |
| 7 | `0 3 * * *` 凌晨 3 点 | **机器那时是关的** → 静默不跑 |
| 8 | `git clone` | **8 分钟只下 37/308 MB** |

### 3.2 ⭐ 实施中 5 条（我自己犯的）

| # | 症状 | 根因 | 修法 |
|---|---|---|---|
| 9 | `[  = egl ]` 恒假，**选 egl 跑 osmesa** | `params.X` 不是环境变量 | `environment { RENDER_BACKEND = "${params.RENDER_BACKEND}" }` |
| 10 | `cd: can't cd to ...` | **Jenkins 容器没挂项目目录** | 改用兄弟容器 + `alpine/git` |
| 11 | `nvidia-smi: not found` | 容器里没装（**不是没 GPU**） | 删掉，交给兄弟容器 |
| 12 | junit 抛 Java 栈盖住真错因 | `allowEmptyResults: false` | 改 `true` |
| 13 | ⭐ **SUCCESS + 122 passed + 空报告** | **`@2` workspace 路径错位** | 从 `WORKSPACE` 推导 + `disableConcurrentBuilds()` |

⚠️ **第 13 条最阴 —— 它以「成功」的形式失败。** 是靠「Tests 菜单不存在」才发现的。【已核实】

### 3.3 另外两个当场撞到的细节【已核实】

| 现象 | 原因 |
|---|---|
| `git: 'sh' is not a git command` | `alpine/git` 的 **entrypoint 是 `git`**，需 `--entrypoint sh` |
| `fatal: detected dubious ownership` | git 拒绝操作属主不同的仓库，需 `safe.directory` |

---

## 四、⭐ 方法论收获（面试可直接用）

### 4.1 同一个东西两个名字 → 永远推导，别硬编码

```groovy
// ❌ 两份硬编码：@2 出现时分叉，且无任何报错
WS_ON_HOST = ".../workspace/${JOB_NAME}"

// ✅ 推导：后缀自动跟上
WS_ON_HOST = "${WORKSPACE.replace('/var/jenkins_home', '/home/.../jenkins_home')}"
```

📌 **适用范围远超 Jenkins**：容器/宿主机路径、内网/外网域名、测试/生产配置 —— **任何「同一实体的两种表示」。**

### 4.2 能力 ≠ 收益

```
✅ GPU 透进容器  ✅ 镜像有 EGL  ✅ 能 GPU 渲染（31×）
❌ 有测试真的需要 GPU        ← 仍然是零，而这层才是根本
```

⚠️ **实测：单帧渲染 31 倍，全量测试只快 0.25s（3.08s→2.83s）** —— 因为 122 个用例几乎不渲染。

> **微基准的加速比，和端到端的收益，可以差两个数量级。**
> **基础设施可以先于需求存在（成本够低且验证过），但不能反过来为了用它去编需求。**

### 4.3 排查先问：工具坏了还是对象坏了

矛盾证据：`1701 FPS`（正常）vs `EGLError`（异常）。

⭐ **该信性能数字** —— Mesa 软渲染物理上到不了 1701（只有 54）。报错只说明**探针漏了 `eglInitialize`**。

📌 **三周来的同类**：`tests/kinematics` 空目录、重复函数被覆盖、vendor 探针写错、报告收集器指向空目录 —— **全是「测量工具本身」出问题**。

### 4.4 「声明了但行为不符，且失败时静默」——今天 +5

| 案例 | 来源 |
|---|---|
| `-v` 写容器内路径 → 挂空目录 | **Docker** |
| 缺 vendor JSON → 静默退化 Mesa | **GLVND** |
| `params.X` 未桥接 → 恒走 else | **Jenkins 变量作用域** |
| `sh` 里 `cd` → 路径不存在 | **Docker 挂载范围** |
| `@2` 错位 → SUCCESS 但报告空 | **Jenkins 并发 workspace** |

⚠️ **五条没有一条是项目代码的锅。**

> ⭐ **它不是某个人的坏习惯，是基础设施的普遍属性：默认行为倾向于「让你继续跑下去」，而不是「让你知道出事了」。**
>
> **对策只有一个：把关键假设写成断言**（`vendor == NVIDIA`、`head -c 60` 查 LFS、构建期 import 自检、`git status` 进日志）。

### 4.5 DooD ≠ DinD

📌 挂 `docker.sock` 起的是**兄弟容器**不是子容器。被问「怎么在 Jenkins 里跑 Docker」时答「DinD」会露馅。

---

## 五、新增缺陷线索【已核实】

### 5.1 缺陷 AC｜测试把临时产物写进源码树 🟡 Medium

`models/mjcf/tmp/*.xml` —— 导致「只读挂载被测代码」这个标准安全做法用不了。

**实测**：`-v ...:/repo:ro` → **7 errors**

```
OSError: [Errno 30] Read-only file system: '/repo/models/mjcf/tmp/airbot_play_place_block.xml'
```

去掉 `:ro` → 122 passed，且**不污染工作区**（该目录已在 `.gitignore`）。

**未修** —— 属 `discoverse/` 上游代码，一次只改一件事。

### 5.2 ⚠️ 容器以 root 写文件的连带问题【已核实】

容器里是 root，写进宿主机的文件（`.pytest_cache/`、`@2` workspace）**普通用户删不掉**。

**对策**：`docker run --rm -v <目录>:/s alpine rm -rf /s/xxx` —— **谁造的谁清**。

📌 `pytest -p no:cacheprovider` 可从源头避免 `.pytest_cache`（**已在 Jenkinsfile 里用了**）。

---

## 六、环境速查

```bash
source scripts/dev/env.sh
$PY -m pytest tests/ -q
#   122 passed, 4 skipped, 45 deselected, 15 xfailed

# ---- 两个测试镜像 ----
docker build -f discoverse/docker/Dockerfile.test     -t discoverse:test .
docker build -f discoverse/docker/Dockerfile.test.gpu -t discoverse:test-gpu .

# ---- 两档后端（都必须 122 passed）----
docker run --rm --gpus all -e MUJOCO_GL=osmesa discoverse:test-gpu pytest tests/ -q
docker run --rm --gpus all -e MUJOCO_GL=egl    discoverse:test-gpu pytest tests/ -q

# ---- EGL vendor 断言（⚠️ eglInitialize 不能漏）----
docker run --rm --gpus all -e MUJOCO_GL=egl discoverse:test-gpu python -c "
from OpenGL import EGL
import ctypes, os
d = EGL.eglGetDisplay(EGL.EGL_DEFAULT_DISPLAY)
maj, minor = EGL.EGLint(), EGL.EGLint()
EGL.eglInitialize(d, ctypes.byref(maj), ctypes.byref(minor))
print('EGL', maj.value, '.', minor.value, 'vendor =', EGL.eglQueryString(d, EGL.EGL_VENDOR))
os._exit(0)
"
#   预期：EGL 1 . 5  /  vendor = b'NVIDIA'
#   ⚠️ 若是 Mesa → 静默退化，10_nvidia.json 没生效

# ---- Jenkins ----
#   http://localhost:8080  → job: DISCOVERSE-GPU-Regression
#   ⚠️ 容器名 jenkins_server；数据在 /home/ubuntu22/robot_platform/jenkins_home
docker exec jenkins_server sh -c 'docker ps'      # 验证 DooD 可用

# ⚠️ 路径铁律：sh 步骤用容器路径，docker run -v 左边用【宿主机】路径
#   容器内: /var/jenkins_home/...
#   宿主机: /home/ubuntu22/robot_platform/jenkins_home/...
```

---

## 七、Day 13+ 待办

### 优先级 1：Day 13-14 结构化结果契约（计划内容）

重构 `cicd_testing.py`，替换 emoji 字符串匹配。

📌 **今天的 JUnit XML 是热身** —— 已见过「机器可读格式」长什么样，以及**格式转换会丢信息**：

```
122 passed + 4 skipped + 15 xfailed = 141   ← XML 的 tests
        4 skipped + 15 xfailed = 19         ← XML 的 skipped
45 deselected 根本不进 XML
```

⚠️ **JUnit 没有 xfail 概念** —— 而 xfail 恰恰是本项目最重要的状态之一。**这正是需要自定义契约的理由。**【已核实】

### 优先级 2：Day 12 自身欠账

- [ ] **`Jenkinsfile` 目前是 UI 粘贴，非 SCM 模式** —— 仓库里有文件但 Jenkins 不读它，**改一处另一处不会跟着变**。升级路径：Definition 改 `Pipeline script from SCM`，URL 用 `file:///home/ubuntu22/workspaces/airbot-play/DISCOVERSE`（本地磁盘，秒级）或 Gitea（:3000），**避开 8 分钟跨太平洋克隆**
- [ ] **写一个真正需要 GPU 的测试** —— ⚠️ EGL 已就绪，**缺的是需求那一侧**
- [ ] 给 `glfw` 补一档（需 DISPLAY），凑齐三档
- [ ] 考虑把 `MUJOCO_GL` 做成 pytest fixture 参数，同一批渲染测试跑两个后端 —— **跨后端一致性才是 EGL 真正能带来的测试价值**
- [ ] Jenkins 定时触发（等确定机器常开时段，用 `H` 打散）
- [ ] 缺陷 AC 写进 `defect-report.md`

### 优先级 3：文档欠账（累积）

- [ ] ⚠️ **Day 10-11 的 3 个文档一直未提交**（checkpoint/log/note）—— 而 checkpoint-day10-11 里写着「工作区干净、已推送」，**文档与现实不符**
- [ ] Day 12 的 3 个文档（本文 + log + note）也待提交
- [ ] `defect-report.md` 缺 §廿九（缺陷 AA）、§三十（缺陷 AB）、新增 §卅一（缺陷 AC）
- [ ] `defect-inventory-day02.md` 未收录 V/W/X 且用旧编号
- [ ] 缺陷 #3（pytest 超时未生效）根因仍未定位
- [ ] `discoverse/__init__.py:11` 无效转义序列

### 优先级 4：覆盖率盲区（未变）

| 模块 | 覆盖率 | 备注 |
|---|---|---|
| **`task_base.py`** | **28%** | ⚠️ **最大盲区**，162 statements 漏 117 |
| `robot_interface.py` | 56% | |
| `task_config.py` | 63% | |
| `randomization.py` | 69% | |

### 优先级 5：CI 欠账（Day 10-11 遗留，未动）

- [ ] `actions/checkout@v4` / `setup-python@v5` 的 Node 20 弃用警告
- [ ] `paths-ignore` 与 branch protection 的冲突
- [ ] `nightly` 仍只手动触发

---

## 八、Day 0-12 累计

| | Day 11 结束 | **Day 12 结束** |
|---|---|---|
| 用例 | 122 | **122** |
| 覆盖率 | 67% | **67%** |
| commit | 13 | **15** |
| 缺陷修复 | 6 | 6 |
| 定位缺陷总数 | 25 | **26** |
| 被推翻的文档推断 | 20 | **33（+13，单日最多）** |
| GitHub Actions job | 5 | 5 |
| **Jenkins stage** | **0** | **5** |
| **测试镜像** | 1 | **2（CPU / GPU）** |

**Day 12 的产出是一条 5-stage 本机流水线 + 一个 EGL 镜像 + 五个「以成功形式出现的失败」。**

> **最值得带走的一条**：`Jenkinsfile` 只有 176 行，但它调用的每一样东西 —— 122 个测试、无头镜像、EGL 栈、GPU 直通 —— **都是前 11 天挣出来的**。
>
> 而今天真正的收获不是那条流水线，是**五个静默失败**，以及从中提炼的那条规律：**同一个东西有两个名字时，永远从一个推导出另一个。**
>
> ⚠️ 以及一条必须守住的诚实：**我打通了 GPU 渲染（31×），但我一个需要 GPU 的测试都没有。** 这是能力储备，不是业务收益 —— **说清楚这个区别，比多搭一条流水线值钱。**
