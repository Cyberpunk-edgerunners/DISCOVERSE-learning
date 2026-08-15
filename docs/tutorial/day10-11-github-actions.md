# Day 10-11 — GitHub Actions：让测试自己跑，让失败自己喊

> 上接 [day08-09-docker-test-image.md](day08-09-docker-test-image.md)
> 本课产出：`.github/workflows/ci.yml`、README 徽章、一条真实的失败→修复→变绿闭环
> 预计耗时：两天各约 4 小时

---

## 这两天到底在干嘛（先建立直觉）

Day 8-9 你做了一件事：**把「我这儿能跑」变成「哪儿都能跑」**。

但还有个问题没解决 —— **得有人去跑它**。

现在的流程是这样的：你改完代码，想起来了，就跑一下 `pytest`；忘了，就不跑。**测试的价值完全取决于你记不记得。**

CI（Continuous Integration，持续集成）就是干掉这个「记不记得」。它的原理同样很笨：

> **每次你 `git push`，云端有台机器自动拉下你的代码，跑一遍测试，结果贴回 GitHub。**

就这么简单。没有魔法。

### 那它到底值钱在哪

值钱的不是「自动跑」，是这三件事：

| | 没有 CI | 有 CI |
|---|---|---|
| 谁来跑 | 你记得才跑 | **每次 push 必跑** |
| 在哪跑 | 你那台脏机器 | **干净机器，每次全新** |
| 失败了谁知道 | 你自己（如果你看了） | **GitHub 上一个红叉，所有人都看见** |

第二条尤其重要。你本机跑绿，可能只是因为你两个月前装过某个包。**CI 的 runner 每次都是全新的虚拟机** —— 它绿了，才叫真的绿。

这正是 Day 8-9 那句话的延续：容器是「干净环境」的**定义**，CI 是让这个定义**每次都被执行**。

### 两天怎么分

| | 做什么 | 核心收获 |
|---|---|---|
| **Day 10** | 建最小可用流水线，push 上去，**看它红** | 第一次 CI 失败是**必然事件**，不是意外 |
| **Day 11** | 分层（lint/unit/integration）+ 徽章 + 缓存 | CI 的成本是真金白银，**分层是省钱也是提速** |

📌 **Day 10 的目标不是「绿」，是「跑起来并如实反映真相」。** 一条第一次就绿的流水线，通常说明它什么都没测。

---

## ⚠️ 开课前必读：计划文档的 CI 部分照抄必炸

老规矩，我把计划文档 §Day 10-11 的每条命令都在本机实跑核实过。**这次问题比 Day 8-9 还多** —— 因为计划里的 YAML 是通用模板，而我们的项目这两周已经长出了自己的形状。

| 计划文档写的 | 实测结果 | 后果 |
|---|---|---|
| `ruff check discoverse/ tests/` | ❌ **277 个错误** | lint job 第一步就红，且红得没意义 |
| `black --check discoverse/ tests/` | ❌ **59 个文件要重排** | 同上 |
| `pytest tests/kinematics tests/simulation` | ⚠️ `tests/kinematics` **是空目录** | 只跑到 5 个用例，看着像成功 |
| `--cov=discoverse` | ⚠️ 覆盖率被稀释 **41% → 28%** | 和你两周积累的数字对不上 |
| `pip install -e .` | ❌ **漏 4 个包**（Day 8-9 的缺陷 L′） | unit job 直接 `ModuleNotFoundError` |
| `actions/checkout@v3` / `setup-python@v4` | ⚠️ 版本已过时 | GitHub 会警告，将来会停用 |
| `codecov/codecov-action@v3` | ⚠️ 需要注册第三方账号 + token | 卡住，且徽章拿不到 |
| nightly 用 `--count=50 -n 8` | ❌ 这仨插件**镜像里没装** | nightly job 必红 |

**再说一次**：这不是计划文档写得差。它写于项目之外。**具体项目长什么样，只有实跑才知道。**

📌 **你的工作不是执行计划，是把计划当假设，逐条验证。**

下面每一步，我都会告诉你**计划怎么写的、我实测到什么、所以应该怎么改**。

---

# Day 10

## Step 0｜准备（30 分钟，别跳过）

### 0.1 记住基线数字

```bash
cd /home/ubuntu22/workspaces/airbot-play/DISCOVERSE
source scripts/dev/env.sh && $PY -m pytest tests/ -q
```

预期看到（Day 9 结束的数字）：

```
122 passed, 4 skipped, 45 deselected, 15 xfailed in 2.96s
```

📌 **把这行抄在纸上。** 这两天的验收标准是：**GitHub 云端跑出来的数字，和这行一模一样。**

差一个用例，就说明云端环境和你本机不等价 —— 那正是 CI 要暴露的东西。

### 0.2 先把 Day 8-9 的东西提交掉

⚠️ **这一步是硬前提。** CI 跑的是**你 push 上去的代码**，不是你硬盘上的代码。没提交的文件，云端根本看不见。

```bash
git status --short
```

如果还有未提交的（Day 8-9 的产出），先提交：

```bash
git add -A
git commit -m "docs: Day 8-9 收尾"
```

### 0.3 确认远端仓库

```bash
git remote -v
git branch -vv
```

我这台机器的实测：

```
origin  git@github.com:Cyberpunk-edgerunners/DISCOVERSE-learning.git (fetch)
origin  git@github.com:Cyberpunk-edgerunners/DISCOVERSE-learning.git (push)

* feat/test-infra 07cded1 [origin/feat/test-infra: ahead 3]
```

**怎么读**：

- `origin` 是远端仓库的代号，指向你的 GitHub
- `ahead 3` = **你本地比远端多 3 个 commit**，也就是有 3 个 commit 还没推上去

📌 GitHub Actions 只认远端。`ahead 3` 意味着云端看到的还是三个 commit 之前的旧代码。

### 0.4 ⚠️ 一个容易被忽略的前提：仓库有多大

```bash
git count-objects -vH
```

实测：

```
size-pack: 308.34 MiB
```

**308 MB。** 为什么要关心这个数？

因为 CI 的第一步永远是 `checkout`（把代码拉到云端机器）。**308 MB 要拉，是要花时间的**，而 GitHub Actions 免费额度是按**分钟**计费的。

⚠️ 这里有个更隐蔽的点。看一眼：

```bash
cat .gitattributes
```

```
models/meshes filter=lfs diff=lfs merge=lfs -text
models/textures filter=lfs diff=lfs merge=lfs -text
```

**这声明了 `models/meshes` 走 Git LFS**（Large File Storage，大文件存储 —— git 里只存一个几百字节的「指针」，真身放在另一个服务器上）。

如果真是 LFS，CI 里的 `actions/checkout` **默认不拉 LFS 文件**，你会拿到一堆指针文件 —— MJCF 加载失败 → `conftest.py` 的 `pytest.skip` 静默兜住 → **CI 全绿但一个 MJCF 都没加载过**。这正是 Day 8-9 §5.2 那个坑的翻版。

**但我实测了，这里没事**：

```bash
git lfs ls-files | wc -l          # → 0
git cat-file -p HEAD:models/meshes/airbot_play/arm_base_0.obj | head -3
```

```
mtllib material.mtl
usemtl material_0
v -0.07773600 0.03057700 0.04823000
```

**是真实的 obj 内容，不是 LFS 指针。** 说明这些文件在 LFS 规则生效之前就已经以普通方式提交了，`.gitattributes` 是后来加的（或者从未真正启用）。

📌 **结论：不用管 LFS，普通 checkout 就能拿到完整 mesh。**

⚠️ **但记一笔**：`.gitattributes` 里的声明还在。**将来谁往 `models/meshes/` 加新文件，如果他机器上装了 git-lfs，那个新文件就会变成 LFS 指针** —— 而老文件不是。仓库会处于「一半 LFS 一半不是」的状态，CI 上表现为「只有新加的那个 mesh 加载失败」。

> 📌 **这又是同一个模式**：**声明了但行为不符，且失败时静默。** 从 Day 2 到现在，这个模式出现第几次了？

**处理建议**：Day 11 有余力时，在 CI 里加一条断言 —— checkout 后检查任一 mesh 文件的前几个字节不是 `version https://git-lfs`。一行 `grep -q` 的事，能防住整类问题。

---

## Step 1｜理解 GitHub Actions 的三个概念（20 分钟，纯理论但必须懂）

在写 YAML 之前，先搞清三个词。它们是嵌套关系：

```
workflow（工作流）  = 一个 .yml 文件，比如 ci.yml
  └── job（任务）    = 一台独立的虚拟机
        └── step（步骤）= 一条命令 或 一个别人写好的动作
```

**关键理解 —— job 之间是完全隔离的**：

| | 含义 |
|---|---|
| 每个 job | **一台全新的虚拟机**，开机 → 干活 → 销毁 |
| job A 装的东西 | job B **看不到** |
| job 默认 | **并行跑**（除非你用 `needs` 声明依赖） |

📌 **这是新手最大的误解来源。** 很多人写：job1 装依赖，job2 跑测试 —— 然后 job2 报 `command not found`。因为 job2 是另一台机器，job1 装的东西跟它没关系。

**每个 job 必须自己从零把环境备齐。**

### 1.1 触发条件（`on:`）

```yaml
on:
  push:                        # 有人 push 就跑
    branches: [feat/test-infra]
  pull_request:                # 有人开 PR 就跑
  schedule:
    - cron: '0 2 * * *'        # 每天固定时间跑
  workflow_dispatch:           # ⭐ 在网页上手动点一下就跑
```

⚠️ **`workflow_dispatch` 计划文档里没有，但你一定要加。**

**为什么**：调试 CI 的时候，没有它你**每改一行 YAML 就得 push 一次**。加上它，你可以在 GitHub 网页上点个按钮就重跑。

📌 这是本课最实用的一条小技巧。**先加上，你今天会用它十几次。**

### 1.2 一个最小的 job 长什么样

```yaml
jobs:
  hello:                          # job 的名字，你随便起
    runs-on: ubuntu-latest        # 用什么机器（GitHub 免费提供）
    steps:
      - uses: actions/checkout@v4 # 别人写好的动作：把代码拉下来
      - run: echo "hello"         # 你自己的命令
```

**`uses` vs `run` 的区别**：

| | 是什么 | 例子 |
|---|---|---|
| `run` | **一条 shell 命令**，就是你在终端敲的那些 | `run: pytest tests/ -q` |
| `uses` | **别人封装好的动作**，从 GitHub 市场拉 | `uses: actions/checkout@v4` |

`@v4` 是版本号。⚠️ **计划文档写的是 `@v3`** —— 实测那是好几年前的版本，GitHub 现在会打黄色警告，且已宣布逐步停用。**用 `@v4`。**

---

## Step 2｜写第一版 ci.yml：只做一件事（40 分钟）

### 2.1 为什么第一版要极简

新手最常见的翻车方式：**一口气写完 5 个 job，push，全红，不知道从哪查。**

CI 调试有个特点让这件事格外痛苦：**反馈慢**。本地跑测试 3 秒，CI 跑一轮要好几分钟。所以：

📌 **每次只加一个 job，绿了再加下一个。** 慢就是快。

### 2.2 建目录

```bash
mkdir -p .github/workflows
```

⚠️ **路径必须一字不差**：`.github/workflows/`。前面有个点，`workflows` 有 s。写错了 GitHub 完全不理你，**而且不报错** —— 页面上什么都不显示，你会以为是别的问题。

> 📌 又一个「静默失败」。你现在应该对这四个字很敏感了。

### 2.3 第一版内容

新建 `.github/workflows/ci.yml`：

```yaml
# ============================================================
# ci.yml —— DISCOVERSE 测试流水线
#
# 设计原则：每个 job 是一台独立的干净虚拟机，
#          job 之间不共享任何东西，各自从零备环境。
# ============================================================
name: CI

on:
  push:
    branches: [feat/test-infra, main]
  pull_request:
  workflow_dispatch: # ⭐ 允许在网页上手动触发，调试期靠它省下大量 push

jobs:
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

**逐段解释**：

| 写法 | 干嘛的 |
|---|---|
| `name: CI` | 这条流水线的显示名，会出现在 GitHub 页面上 |
| `runs-on: ubuntu-latest` | 用 GitHub 提供的 Ubuntu 机器 |
| `- name: xxx` | 给这一步起个名字，**失败时你在页面上一眼能看到是哪步炸的** |
| `run: \|` | 竖线表示「下面是多行命令」 |

📌 **那个 `head -c 60` 是刻意的** —— 如果输出是 `version https://git-lfs...`，说明踩了 Step 0.4 说的 LFS 坑。**一行命令换一个确定性。**

### 2.4 push 上去

```bash
git add .github/workflows/ci.yml
git commit -m "ci: 最小可用流水线（smoke job）"
git push
```

然后打开浏览器：

```
https://github.com/Cyberpunk-edgerunners/DISCOVERSE-learning/actions
```

**你应该看到一条正在转圈的记录。** 点进去能看到每一步的实时输出。

### 2.5 ⚠️ 如果页面上什么都没有

按这个顺序查：

| 查什么 | 命令 |
|---|---|
| 文件路径对不对 | `git ls-files .github/` 应输出 `.github/workflows/ci.yml` |
| 真的 push 上去了吗 | `git log origin/feat/test-infra -1 --oneline` |
| 分支名对不对 | `on.push.branches` 里要包含你当前分支 |
| YAML 语法 | 见下 |

**YAML 语法自查**（在本机就能验，别浪费一次 push）：

```bash
source scripts/dev/env.sh
$PY -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('YAML 语法 OK')"
```

⚠️ **YAML 对缩进极度敏感**，而且**只认空格，不认 Tab**。这是新手最常见的翻车点。VSCode 里可以开 `"editor.renderWhitespace": "all"` 把空格显示出来。

📌 但注意：**语法 OK ≠ 语义 OK**。上面那条命令只能验「是合法 YAML」，验不出「`runs-on` 拼成了 `runs_on`」。后者只有 GitHub 才知道。

### 2.6 ⚠️ 一个会让你怀疑人生的 YAML 冷知识

如果你想用 Python 检查 `on:` 这段配置对不对，会撞上这个：

```bash
source scripts/dev/env.sh
$PY -c "
import yaml
d = yaml.safe_load(open('.github/workflows/ci.yml'))
print('顶层 keys:', list(d.keys()))
print(\"'on' in d ?\", 'on' in d)
"
```

实测输出：

```
顶层 keys: ['name', True, 'concurrency', 'jobs']
'on' in d ? False
```

**`on` 这个 key 变成了 `True`。**

**为什么**：YAML 1.1 规定 `on` / `off` / `yes` / `no` 都是**布尔字面量**。PyYAML 遵循 1.1，所以把没加引号的 `on` 解析成了布尔真。

📌 **GitHub Actions 自己不受影响** —— 它用的解析器按 YAML 1.2 处理，`on` 就是字符串。**所以你的 workflow 是好的，只是你的检查脚本读不到。**

⚠️ **这个坑的危险之处在于它会误导你的排查方向**：你写脚本查 `on` 配置，发现「`on` 不存在」，于是以为 workflow 写错了，跑去改一个根本没问题的地方。

**要在 Python 里读它，用 `d[True]`**：

```bash
$PY -c "
import yaml
d = yaml.safe_load(open('.github/workflows/ci.yml'))
print('触发条件:', list(d[True] if True in d else d['on']))
"
# → 触发条件: ['push', 'pull_request', 'workflow_dispatch']
```

> 📌 **这是「同一份文本，两个解析器给出不同结果」的典型案例。** 和 Day 8-9 那个「本机有 libx264、容器未必有」是同一类问题：**你验证用的工具，和真正执行的工具，不是同一个。**

---

## Step 3｜加 unit job：第一次真正跑测试（60 分钟）

### 3.1 先看计划文档怎么写的

```yaml
  unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Install dependencies
        run: |
          sudo apt-get update
          sudo apt-get install -y libosmesa6-dev xvfb
          pip install -e .
          pip install pytest pytest-cov pytest-xdist
      - name: Run unit tests
        env:
          MUJOCO_GL: osmesa
        run: pytest tests/unit -v --cov=discoverse --cov-report=xml
```

**这段有四个问题，我逐个实测给你看。**

### 3.2 ⚠️ 问题一：`pip install -e .` 装不全 —— 就是缺陷 L′

Day 8-9 已经实测过了（checkpoint §3.1）：

```
干净容器 pip install -e . 后：
  import discoverse.universal_manipulation
  → ModuleNotFoundError: No module named 'yaml'
```

缺的四个包：`pyyaml`、`av`、`PyOpenGL`、`pillow`。它们只声明在 optional 组里，而 `__init__.py` 是 eager import（一导入包就加载全部子模块）。

📌 **CI runner 就是一个干净环境。** 你会**完完整整地**再撞一次这个坑。

**这是好事。** 这正是 CI 的价值 —— 它把「本机脏所以看不见的问题」变成一个红叉。

**怎么处理**，你有两条路：

| 方案 | 做法 | 评价 |
|---|---|---|
| A | CI 里加一行 `pip install pyyaml av PyOpenGL pillow` | ❌ **治标**。跟 `--no-deps` 一样是绕过去，真 bug 还在 |
| B | **改 `pyproject.toml`，把这 4 个包补进核心 `dependencies`** | ✅ **治本** |

**选 B。** 这是 checkpoint §六「优先级 2」挂着的待办，**今天顺手清掉**。

```bash
# 改之前先看现在长什么样
grep -n -A25 "^dependencies" pyproject.toml
```

改完后**必须在本机验证**（别等 CI 告诉你）：

```bash
source scripts/dev/env.sh && $PY -m pytest tests/ -q
# 预期：122 passed, 4 skipped, 45 deselected, 15 xfailed —— 一个都不能少
```

⚠️ 但本机验证有个盲区：**你本机已经装了那 4 个包，所以改不改 `pyproject.toml` 你都是绿的。** 真正的验证只能在干净环境做 —— 也就是 Day 8-9 那个镜像，或者今天这条 CI。

> 📌 **这就是这两周反复出现的主题**：**你需要一个你控制不了的环境来告诉你真相。**

### 3.3 ⚠️ 问题二：`--cov=discoverse` 会让覆盖率数字对不上

我实测了两种写法：

```bash
# A) 计划文档的写法
$PY -m pytest tests/unit -q --cov=discoverse --cov-report=term
# → TOTAL   2584   1864   28%

# B) 项目 pyproject.toml 里配好的作用域
$PY -m pytest tests/unit -q --cov --cov-report=term
# → TOTAL    967    573   41%
```

**同一批测试，28% vs 41%。**

**为什么差这么多**：`pyproject.toml` 里早就配好了：

```toml
[tool.coverage.run]
source = ["discoverse/universal_manipulation"]
```

分母只算**你正在测的模块**（967 行）。而 `--cov=discoverse` 把整个 `discoverse/` 都算进分母（2584 行）—— 包括你根本没打算测的渲染、ROS 桥接等等。

📌 **覆盖率不是越大越好，是「分母要有意义」。** 把没打算测的代码算进分母，数字会一路走低，然后你就不看它了 —— **一个没人看的指标等于没有**。

**改法：直接写 `--cov`，让它读 `pyproject.toml` 的配置。**

⚠️ 顺带一提：`pyproject.toml` 里那条注释已经写清楚了原因 ——「不要写 `--cov=discoverse`，`policies/` 下 237 个策略学习文件会把分母稀释到 2-3%」。**这是你自己两周前留的路标，今天派上用场了。**

### 3.4 ⚠️ 问题三：`xvfb` 装了没用

计划文档装了 `xvfb`（虚拟显示器）。但 Day 8-9 已经决定用 **osmesa 软件渲染**，压根不需要虚拟显示器。

| | 原理 | 需要 $DISPLAY 吗 |
|---|---|---|
| xvfb | 假装有个显示器 | 要（假的那个） |
| **osmesa** | **纯 CPU 离屏渲染** | **不要** |

**删掉 `xvfb`。** 每个不必要的 apt 包都是 CI 时间。

### 3.5 ⚠️ 问题四：`libglib2.0-0` 不能漏

Day 8-9 血泪教训（Dockerfile.test 注释里写着，缺陷报告 §廿六）：

> 缺它的症状很隐蔽：不是启动即崩，而是 **7 个用例 ERROR（106 passed 而非 113）**，因为 `cv2` 是在 fixture 里才被 import 的。

📌 **CI 上你会看到「106 passed」这种看着挺正常的数字。** 如果你没记住基线 122，你根本发现不了。

**这就是 Step 0.1 让你把数字抄在纸上的原因。**

### 3.6 改好的 unit job

追加到 `ci.yml` 的 `jobs:` 下面：

```yaml
  # ---- 单元测试：不依赖 Docker，直接在 runner 上装环境 ----
  # 为什么不直接用 Day 8-9 的镜像？见 Step 5 的对比 ——
  # 这个 job 的额外价值是：它验证「pyproject.toml 声明的依赖是否完整」，
  # 而镜像用 requirements-test.txt + --no-deps，恰好绕过了这个验证。
  unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"
          cache: pip # ⭐ 缓存 pip 下载，第二次起能省几分钟

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

      - name: 安装 discoverse
        # ⚠️ 这里刻意用 pip install -e .（不加 --no-deps）——
        #    就是要让它去解 pyproject.toml，从而验证依赖声明的完整性。
        #    这是缺陷 L′ 的守护测试。
        run: |
          python -m pip install --upgrade pip
          pip install -e .
          pip install pytest pytest-cov pytest-timeout

      - name: ⭐ 干净环境 import 自检
        # checkpoint-day06-07 §2.2 要求的那道守护。
        # 放在跑测试之前 —— 失败越早越便宜，
        # 而且失败信息比一堆 collection error 清楚得多。
        run: |
          python -c "import mujoco; print('MuJoCo', mujoco.__version__)"
          python -c "import discoverse.universal_manipulation; print('discoverse OK')"

      - name: 跑测试
        env:
          MUJOCO_GL: osmesa
        # --cov 不带参数：读 pyproject.toml 的 source 配置。
        # ⚠️ 别写 --cov=discoverse，分母会从 967 涨到 2584，
        #    覆盖率数字 41% → 28%，和你两周积累的记录对不上。
        run: pytest tests/ -q --cov --cov-report=term-missing
```

### 3.7 push，然后**期待它红**

```bash
git add -A
git commit -m "ci: 加 unit job"
git push
```

📌 **如果它第一次就绿了，反而要警惕** —— 去日志里确认那个 `122 passed` 是真的出现了，而不是测试根本没跑起来。

**大概率你会看到红。** 常见的三种，对照查：

| 报错 | 根因 | 修哪 |
|---|---|---|
| `ModuleNotFoundError: No module named 'yaml'` | 缺陷 L′，`pyproject.toml` 没补全 | 回 Step 3.2 |
| `ImportError: libgthread-2.0.so.0` | 少装 `libglib2.0-0` | Step 3.5 |
| 数字是 106 或其它 | 同上，cv2 相关用例 ERROR 了 | Step 3.5 |
| `E: Unable to locate package` | apt 索引没拉到 | 确认有 `apt-get update` |

⚠️ **最后那条是 Day 8-9 §5.3 的教训**：`Unable to locate package` **不是包名错了**，是 `apt-get update` 失败。**下游症状会伪装成根因。日志要从上往下读。**

### 3.8 怎么读 CI 日志（这个技能比写 YAML 重要）

在 GitHub Actions 页面点进失败的 run：

1. **左边**是 job 列表，红叉的那个点进去
2. **右边**是每个 step，展开红色的那个
3. ⚠️ **别只看最后一行**

第 3 条最关键。**最后一行往往是「下游症状」**。要从上往下扫，找**第一个**异常。

📌 Day 8-9 那次踩坑是最好的例子：最后报的是「找不到包」，真因在几十行之前的三行 `Failed to fetch`。**如果只看最后一行，你会去改包名，然后怎么改都不对。**

---

## Step 4｜Day 10 验收

```bash
# 1. 本机基线没变（改 pyproject.toml 不能引入回退）
source scripts/dev/env.sh && $PY -m pytest tests/ -q
#   必须还是：122 passed, 4 skipped, 45 deselected, 15 xfailed

# 2. YAML 语法合法
source scripts/dev/env.sh && $PY -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('OK')"

# 3. ⭐ 容器里也验一遍（Day 8-9 的镜像还在服役）
docker run --rm discoverse:test pytest tests/ -q

# 4. 云端：Actions 页面 unit job 绿，且日志里能找到 122 passed
```

⚠️ **第 4 条要「点进日志确认数字」，不能只看绿灯。** 绿灯只说明「进程退出码是 0」。

> 📌 想想 Day 0 记录的**缺陷 #1**：`main()` 吞掉所有异常，进程退出码恒为 0，CI 无法区分「任务失败」和「程序崩溃」。
>
> **绿灯从来不等于正确。** 你两周前就亲手记录过这件事了。

---

# Day 11

## Step 5｜加 integration job：把 Day 8-9 的镜像接进来（60 分钟）

### 5.1 先想清楚：为什么要两个 job 跑同一批测试

现在 `unit` job 已经在跑 `tests/` 全量了。再用 Docker 跑一遍，不是重复吗？

**不是。它们验证的是不同的东西**：

| | `unit` job | `integration` job |
|---|---|---|
| 环境来源 | `pip install -e .` 解 `pyproject.toml` | `requirements-test.txt` + `--no-deps` |
| 验证什么 | ✅ **依赖声明是否完整**（缺陷 L′ 的守护） | ✅ **镜像是否可复现** |
| 速度 | 快（有 pip 缓存） | 慢（要 build 镜像） |
| 贴近谁 | 贴近「新人 clone 下来能不能跑」 | 贴近「生产环境部署」 |

📌 **`--no-deps` 让镜像绕过了 `pyproject.toml`** —— 这是 Day 8-9 checkpoint 明确记下的（§六优先级 2）。所以**镜像绿了不代表依赖声明是对的**。两个 job 各补一个盲区。

**能说清「为什么这不是重复」，比写出这个 YAML 更值钱。** 这是面试会问的那种问题。

### 5.2 ⚠️ 计划文档的 integration job 有个隐形坑

```yaml
      - run: docker run --rm discoverse:test pytest tests/kinematics tests/simulation -v
```

我实测了：

```bash
$PY -m pytest tests/kinematics tests/simulation -q
# → 4 passed, 1 xfailed in 1.73s
```

**只有 5 个用例。** 因为：

```bash
ls tests/kinematics/
# → 空目录
```

`tests/kinematics/` **是个空目录**（Day 2 建的骨架，还没填内容）。所以这条命令实际只跑了 `tests/simulation`。

⚠️ **危险在于它是绿的。** 一条跑了 5 个用例的绿灯，和一条跑了 122 个用例的绿灯，在 GitHub 页面上**长得一模一样**。

> 📌 **又是「声明了但行为不符，且失败时静默」。** 这个模式，从 Day 2 到今天，你数一下出现几次了？

**改法：跑全量 `tests/`。** 反正 3 秒的事。

### 5.3 integration job

```yaml
  # ---- 集成测试：用 Day 8-9 的镜像跑 ----
  # 与 unit job 的分工见教程 Step 5.1：
  #   unit  验证 pyproject.toml 依赖声明完整性（pip install -e .）
  #   这里  验证镜像可复现性（requirements-test.txt + --no-deps）
  # 两者不是重复，各自覆盖对方的盲区。
  integration:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: 构建测试镜像
        # ⚠️ 构建上下文必须是仓库根（最后那个 .），
        #    .dockerignore 在这一层才生效。
        run: docker build -f discoverse/docker/Dockerfile.test -t discoverse:test .

      - name: 证明容器内确实没有显示器
        # 这条别删。它是「无头」这个卖点的唯一证据。
        # 预期输出 DISPLAY=[] （空）和 MUJOCO_GL=osmesa
        run: |
          docker run --rm discoverse:test sh -c 'echo "DISPLAY=[$DISPLAY]"; echo "MUJOCO_GL=$MUJOCO_GL"'

      - name: 容器内跑全量测试
        # ⚠️ 不要写 tests/kinematics —— 那是空目录，
        #    会跑出「5 passed」的绿灯，和 122 的绿灯长得一样。
        run: docker run --rm discoverse:test pytest tests/ -q
```

⚠️ **注意我没用 `docker compose`。** Day 8-9 记下过一个坑（checkpoint §六优先级 3）：

> `docker run` 绿、`docker compose` 红实际发生过 —— `:ro` 挂载杀死了 `test_task_base_wires_yaml_seed_to_randomizer`。**CI 里怎么跑，本地就要怎么验。**

**这句话反过来也成立**：本地怎么验，CI 里就要怎么跑。CI 里用 `docker run`，那本地验收也用 `docker run`。

📌 **想在 CI 里用 compose？可以，但那就要先在本地把 `:ro` 那个问题解决掉。** 别把一个已知会红的东西塞进 CI。

---

## Step 6｜lint job：这一步要做个真实的决策（60 分钟）

### 6.1 实测：照抄计划文档会红成什么样

```bash
source scripts/dev/env.sh
$PY -m pip install ruff -q
$PY -m ruff check discoverse/ tests/
```

实测输出：

```
Found 277 errors.
[*] 113 fixable with the `--fix` option
```

```bash
$PY -m black --check discoverse/ tests/
```

```
Oh no! 💥 💔 💥
59 files would be reformatted, 7 files would be left unchanged.
```

**277 个 lint 错误，59 个文件格式不符。**

### 6.2 停下来想一想

你现在有三个选择。**这是今天最需要判断力的一步**，不要急着敲命令。

| 方案 | 做法 | 后果 |
|---|---|---|
| A | `ruff check --fix` + `black` 全改一遍 | ⚠️ **一次改 59 个文件**，全是别人的代码。混在你的测试 commit 里，diff 爆炸，review 无法进行 |
| B | 直接删掉 lint job | ⚠️ 简历上「CI/CD 流水线」少一块 |
| C | **只 lint 你自己写的代码**（`tests/`），且**先只报告不拦截** | ✅ |

**选 C。理由有三层**：

1. **你是来做测试的，不是来重排版的。** 一个 PR 只做一件事，这是基本工程素养。
2. **格式化 59 个上游文件会制造巨大的 merge 冲突**，且对上游仓库毫无价值。
3. **`tests/` 是你的地盘**，从第一天就该干净。

### 6.3 ⚠️ 但「只查 tests/」也不是零成本 —— 先实测

**别以为收窄范围就万事大吉了。** 实测：

```bash
$PY -m ruff check tests/
# → Found 10 errors.  [*] 7 fixable with the `--fix` option.

$PY -m black --check tests/
# → 9 files would be reformatted, 5 files would be left unchanged.
```

**`tests/` 自己也有 10 个 ruff 错误、9 个文件格式不符。**

📌 **这个量级完全可以现在还清** —— 10 个错误 vs 277 个，9 个文件 vs 59 个，而且**全是你自己写的代码**，不会跟上游冲突。

**这就是「范围收窄」的真正意义**：不是逃避，是**把债切成还得起的块**。

### 6.4 ⭐ 其中一个不是格式问题，是真 bug

ruff 报的 10 条里，有这么一条：

```
tests/unit/test_task_config.py:251:5
  `test_validate_config_should_require_observation` redefined here
  previous definition at tests/unit/test_task_config.py:214:5
```

**同一个测试函数定义了两次。** Python 里后定义的同名函数**直接顶掉**前面的 —— 所以第 214 行那个**从来没有被执行过**。

我把两处都读了，实测结论：**两份代码逐字节完全相同**（同样的 `xfail(strict=True)`、同样的 reason、同样的函数体）。**是一次复制粘贴事故**，不是两个不同版本。

📌 **好消息**：既然完全一样，删哪个都行，**用例总数不变**（pytest 本来就只收集到一个）。基线仍是 `122 passed`。

⚠️ **坏消息更值得想**：正因为它们一样，**这个 bug 没有造成任何可观测的后果** —— 测试数不变、结果不变、没有任何报错。

> 📌 **如果两份不一样呢？** 那就是「你以为在测 A，实际在测 B」，而**表面现象完全相同**。
>
> 这次是运气好。**下次不一定。**

**怎么修**：删掉第 214 行那份（连同它上面的 `@pytest.mark.unit` 和 `@pytest.mark.xfail` 装饰器），保留第 251 行那份 —— 因为后者紧跟在一段解释缺陷 I 的注释块后面，上下文更完整。

修完验证：

```bash
source scripts/dev/env.sh && $PY -m pytest tests/unit/test_task_config.py -q
source scripts/dev/env.sh && $PY -m pytest tests/ -q
#   预期仍是 122 passed —— 数字不变才对
```

### 6.5 还清 tests/ 的规范债

```bash
source scripts/dev/env.sh

# 1. 先看 ruff 要改什么（--diff 只看不改）
$PY -m ruff check tests/ --diff

# 2. 自动修可修的
$PY -m ruff check tests/ --fix

# 3. 剩下的手工处理（重复函数那条就在这里）
$PY -m ruff check tests/

# 4. black 格式化
$PY -m black tests/

# 5. ⭐ 关键一步：确认没改坏
$PY -m pytest tests/ -q
#   必须还是 122 passed, 4 skipped, 45 deselected, 15 xfailed
```

⚠️ **第 5 步不能省。** `--fix` 和 `black` 都会改你的源码。虽然理论上是「等价变换」，但**「理论上安全」和「实测安全」是两回事** —— 这是这两周反复出现的教训。

📌 **建议单独开一个 commit** 提交格式化改动，别和逻辑改动混在一起。将来 `git blame` 时能一眼跳过纯格式的那次提交。

### 6.6 lint job

```yaml
  # ---- 代码规范：范围刻意收窄 ----
  # 为什么不 lint discoverse/：实测 ruff 277 errors、black 59 files。
  # 那是上游代码，一次性重排会制造巨大 diff 和 merge 冲突，
  # 且与「补测试」这个目标无关。一个 PR 只做一件事。
  # tests/ 是我们自己的地盘，从第一天就该干净。
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"
          cache: pip

      - run: pip install ruff black

      - name: ruff（只查 tests/）
        run: ruff check tests/

      - name: black（只查 tests/）
        run: black --check tests/

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

📌 **`continue-on-error: true` 是这个 job 的精髓。** 它表达了一个成熟的工程判断：

> **「我知道这里有债，我量化了它，我选择现在不还，但我让它一直可见。」**

这比「假装没看见」和「一次性还清搞乱整个仓库」都强。

---

## Step 7｜nightly job：又一个需要决策的地方（30 分钟）

### 7.1 计划文档写的

```yaml
      - run: docker run --rm discoverse:test pytest tests/integration/test_task_matrix.py --count=50 -n 8 --json-report
```

⚠️ **实测：这仨插件镜像里都没有。**

看 `requirements-test.txt` 的注释（你 Day 8 自己写的）：

```
#   pytest-xdist / pytest-repeat / pytest-json-report
#     → Day 5 的 flake 采样实验用（--count=50 -n 8），
#       日常回归不需要。以后要在容器里跑 flake 实验再加。
```

**「以后」就是现在。**

### 7.2 三个选择

| 方案 | 代价 | 建议 |
|---|---|---|
| A | 往 `requirements-test.txt` 加三个插件，镜像变大 | 日常 build 每次都背着它们 |
| B | nightly job 里 `docker run` 时临时 `pip install` | 每晚多花一点时间，**镜像保持干净** |
| C | **本阶段不做 nightly，先留 `workflow_dispatch` 手动版** | ✅ 推荐 |

**推荐 C，理由是成本**：

`schedule` 每天自动跑，而 flake 采样是 `--count=50`，**每次好几分钟**。GitHub 免费额度每月 2000 分钟。**每天烧掉几分钟去跑一个你现在还不会天天看的报告，不划算。**

📌 **Day 5 你已经把 flake 率测出来了。** nightly 的价值是「监控它有没有变坏」—— 而现在代码几乎不动，没什么可监控的。

**先做手动触发版，等代码开始高频变动了再改成 schedule。** 一行 `on:` 的事。

### 7.3 nightly job（手动触发版）

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
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - run: docker build -f discoverse/docker/Dockerfile.test -t discoverse:test .

      - name: flake 采样
        run: |
          docker run --rm discoverse:test sh -c '
            pip install --no-cache-dir pytest-repeat pytest-xdist pytest-json-report &&
            pytest tests/ -m flake --count=20 -n 4 -q
          '
```

⚠️ **注意 `-m flake`**。`pyproject.toml` 里配了 `addopts = "-m 'not flake'"`，所以 flake 用例**默认是被排除的**（那 45 个 `deselected` 就是它们）。要跑就得显式指定。

📌 **这也是为什么 `122 passed` 后面跟着 `45 deselected`。** 如果你从没搞清那 45 个是什么，现在清楚了。

---

## Step 8｜README 徽章（20 分钟）

### 8.1 CI 徽章

在 [README.md](../../README.md) 顶部（标题下面第一行）加：

```markdown
[![CI](https://github.com/Cyberpunk-edgerunners/DISCOVERSE-learning/actions/workflows/ci.yml/badge.svg?branch=feat/test-infra)](https://github.com/Cyberpunk-edgerunners/DISCOVERSE-learning/actions/workflows/ci.yml)
```

**`?branch=feat/test-infra` 是我加的，计划文档没有。**

**为什么要加**：不加的话徽章显示**默认分支（main）**的状态。而你的 CI 跑在 `feat/test-infra` 上，`main` 上压根没有这个 workflow —— **徽章会显示 `no status` 或干脆是灰的**。

📌 **这个坑很典型**：徽章「显示不对」比「不显示」更糟糕，因为你会以为是网络问题、缓存问题，然后去查一堆无关的东西。

### 8.2 ⚠️ codecov 徽章：建议先不做

计划文档要加 codecov。**我的建议是本阶段跳过**：

| 问题 | 说明 |
|---|---|
| 要注册第三方服务 | codecov.io，还要授权访问你的仓库 |
| 私有仓库要 token | 得配 GitHub Secrets |
| **对你的目标没有增量价值** | 覆盖率数字你 CI 日志里已经有了 |

**替代方案 —— 让覆盖率数字出现在 GitHub 页面上**，零第三方依赖：

在 unit job 的最后加一步：

```yaml
      - name: 覆盖率写进 Job Summary
        # $GITHUB_STEP_SUMMARY 是 GitHub 提供的一个特殊文件，
        # 往里写的 markdown 会渲染在 Actions 页面顶部。
        # 零第三方依赖，不用注册任何服务。
        if: always() # ⚠️ 即使测试失败也要出报告 —— 失败时的覆盖率同样有信息量
        run: |
          {
            echo "## 覆盖率"
            echo '```'
            coverage report 2>/dev/null | tail -20
            echo '```'
          } >> $GITHUB_STEP_SUMMARY
```

📌 **`if: always()` 这个细节值得记。** 默认情况下，前一步失败后面就不跑了。但报告类的步骤**恰恰在失败时最有用**。

---

## Step 9｜省钱与提速（30 分钟）

CI 分钟数是真金白银（免费账户每月 2000 分钟）。三个立竿见影的手段：

### 9.1 pip 缓存（已经加了）

```yaml
      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"
          cache: pip # 就这一行
```

第二次起，pip 下载从几分钟变几秒。

### 9.2 并发取消

在 `ci.yml` 顶部（`jobs:` 之前）加：

```yaml
# 同一分支连续 push 时，取消还在跑的旧 run。
# 你连推 3 个 commit，默认会同时跑 3 条流水线 ——
# 前两条的结果你根本不会看，纯烧额度。
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

📌 **调试 CI 的时候你会连续 push 很多次，这条能省掉一大半浪费。**

### 9.3 路径过滤

改文档不该触发全量 CI：

```yaml
on:
  push:
    branches: [feat/test-infra, main]
    paths-ignore:
      - "docs/**"
      - "source-notes/**"
      - "**.md"
```

⚠️ **但有个反直觉的点**：`paths-ignore` 和「必须通过的检查」（branch protection）配合时会出问题 —— 被跳过的 job 状态是 `skipped` 而不是 `success`，PR 会**一直卡在等待检查**。

📌 **本阶段你还没配 branch protection，所以现在加是安全的。** 但记住这个坑，将来配了要回来重新想。

---

## Step 10｜Day 11 验收清单

```bash
# 1. 本机基线 —— ⚠️ 做完 Step 6.4/6.5 的清债后，数字必须【不变】
source scripts/dev/env.sh && $PY -m pytest tests/ -q
#   仍应是：122 passed, 4 skipped, 45 deselected, 15 xfailed
#   ⚠️ 数字变了 = 格式化改坏了东西，回去查，别往下走

# 2. YAML 语法 + job 清单 + 触发条件
#    ⚠️ 用 d[True] 读 on —— PyYAML 会把 on 解析成布尔（见 Step 2.6）
source scripts/dev/env.sh && $PY -c "
import yaml
d = yaml.safe_load(open('.github/workflows/ci.yml'))
print('jobs:', list(d['jobs']))
print('触发:', list(d[True] if True in d else d['on']))
"
#   预期：jobs: ['smoke', 'unit', 'integration', 'lint', 'nightly']
#         触发: ['push', 'pull_request', 'workflow_dispatch']

# 3. lint 在本机先过（别浪费一次 push）
source scripts/dev/env.sh && $PY -m ruff check tests/ && $PY -m black --check tests/

# 4. 容器闭环
docker build -f discoverse/docker/Dockerfile.test -t discoverse:test .
docker run --rm discoverse:test pytest tests/ -q

# 5. 云端：4 个 job 全绿（nightly 是手动的，不会自动跑）

# 6. ⭐ 点进 unit job 日志，确认数字与本机一致
```

**验收的核心是第 6 条。** 前 5 条都可能「绿着骗你」。

---

## 附｜完整 ci.yml 参考

⚠️ **不要直接照抄这一段就完事。** 上面每一步都是「先看计划怎么写 → 实测 → 所以改成这样」，那个过程才是这两天的价值。这里只是给你拼装时对照用。

**我已经把下面这份整体喂给 `yaml.safe_load` 验过**：语法合法，5 个 job 全部正确解析（`smoke` / `unit` / `integration` / `lint` / `nightly`）。

<details>
<summary>展开完整 ci.yml</summary>

```yaml
name: CI

on:
  push:
    branches: [feat/test-infra, main]
    paths-ignore:
      - "docs/**"
      - "source-notes/**"
      - "**.md"
  pull_request:
  workflow_dispatch:

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"
      - name: 环境自报家门
        run: |
          python --version
          echo "--- 防 LFS 指针 ---"
          head -c 60 models/meshes/airbot_play/arm_base_0.obj

  unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"
          cache: pip
      - name: 系统依赖
        run: |
          sudo apt-get update
          sudo apt-get install -y --no-install-recommends \
            libosmesa6-dev libgl1 libglx-mesa0 libglib2.0-0
      - name: 安装 discoverse
        run: |
          python -m pip install --upgrade pip
          pip install -e .
          pip install pytest pytest-cov pytest-timeout
      - name: 干净环境 import 自检
        run: |
          python -c "import mujoco; print('MuJoCo', mujoco.__version__)"
          python -c "import discoverse.universal_manipulation; print('discoverse OK')"
      - name: 跑测试
        env:
          MUJOCO_GL: osmesa
        run: pytest tests/ -q --cov --cov-report=term-missing
      - name: 覆盖率写进 Job Summary
        if: always()
        run: |
          {
            echo "## 覆盖率"
            echo '```'
            coverage report 2>/dev/null | tail -20
            echo '```'
          } >> $GITHUB_STEP_SUMMARY

  integration:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: 构建测试镜像
        run: docker build -f discoverse/docker/Dockerfile.test -t discoverse:test .
      - name: 证明容器内确实没有显示器
        run: |
          docker run --rm discoverse:test sh -c 'echo "DISPLAY=[$DISPLAY]"; echo "MUJOCO_GL=$MUJOCO_GL"'
      - name: 容器内跑全量测试
        run: docker run --rm discoverse:test pytest tests/ -q

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"
          cache: pip
      - run: pip install ruff black
      - name: ruff（只查 tests/）
        run: ruff check tests/
      - name: black（只查 tests/）
        run: black --check tests/
      - name: discoverse/ 现状报告（不拦截）
        continue-on-error: true
        run: |
          echo "=== discoverse/ 规范债现状（仅报告）==="
          ruff check discoverse/ --statistics || true
          black --check discoverse/ 2>&1 | tail -3 || true

  nightly:
    if: github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker build -f discoverse/docker/Dockerfile.test -t discoverse:test .
      - name: flake 采样
        run: |
          docker run --rm discoverse:test sh -c '
            pip install --no-cache-dir pytest-repeat pytest-xdist pytest-json-report &&
            pytest tests/ -m flake --count=20 -n 4 -q
          '
```

</details>

⚠️ **两个提醒**：

1. **别一次性把这份 push 上去。** 按 Step 2 → 3 → 5 → 6 → 7 一个 job 一个 job 加，绿了再加下一个。**一口气全推，红了你不知道从哪查。**
2. `nightly` 里那三个插件是**容器内临时装**的，别顺手加进 `requirements-test.txt` —— 理由见 Step 7.2。

---

## 两天的坑汇总

| # | 坑 | 表现 | 教训 |
|---|---|---|---|
| 1 | job 之间不共享环境 | job2 `command not found` | **每个 job 是一台独立虚拟机**，各自从零备环境 |
| 2 | `.github/workflows/` 路径写错 | 页面上**什么都不显示** | 又一个静默失败 |
| 3 | YAML 缩进/Tab | 语法错误 | 只认空格；push 前本机 `yaml.safe_load` 验一遍 |
| 3b | **PyYAML 把 `on:` 解析成 `True`** | 检查脚本报「`on` 不存在」 | YAML 1.1 vs 1.2 差异；**workflow 本身没问题**，是你的检查工具不同 |
| 4 | `pip install -e .` 漏 4 个包 | `ModuleNotFoundError: yaml` | **缺陷 L′**；CI 是干净环境，必然复现 |
| 5 | 漏 `libglib2.0-0` | **106 passed**（看着很正常） | `.so` 缺失 pip 管不到；**必须比对基线数字** |
| 6 | `--cov=discoverse` | 41% → 28% | **分母要有意义**；读 `pyproject.toml` 的配置 |
| 7 | `tests/kinematics` 是空目录 | **5 passed 的绿灯** | 和 122 的绿灯长得一模一样 |
| 8 | `ruff` 277 / `black` 59 files | lint job 全红 | **范围收窄 + `continue-on-error`**，别一次改 59 个文件 |
| 8b | 收窄后 `tests/` 仍有 10 errors / 9 files | lint job 还是红 | **收窄不等于零成本**，只是把债切成还得起的块 |
| 9 | **同名测试函数定义两次** | 后者覆盖前者，**pytest 完全不报错** | 两份恰好逐字节相同，**所以零可观测后果** —— 运气好而已 |
| 10 | nightly 三个插件镜像里没有 | job 必红 | 你 Day 8 的注释里写着「以后再加」—— 以后到了 |
| 11 | 徽章不加 `?branch=` | 显示 `no status` | 默认看 main，而 workflow 在 feature 分支 |
| 12 | `actions/*@v3` | 黄色警告 | 用 `@v4` / `setup-python@v5` |
| 13 | 连续 push 并行烧额度 | 额度莫名消耗 | `concurrency` + `cancel-in-progress` |

⚠️ **坑 5、7、9 是同一类**：**它们都表现为「绿灯」。**

**这两天最该带走的技能不是写 YAML，是「不相信绿灯」。**

---

## 这两天真正学到的

**表面**：写了个 YAML，push 上去变绿了。

**实际是四件事**：

1. **CI 的价值不是「自动」，是「在一个你控制不了的环境里执行」。** 你本机是脏的 —— 它绿了不算数。CI runner 每次全新，它绿了才算数。**这是 Day 8-9 那个容器的自然延续：容器是干净环境的定义，CI 是让这个定义每次都被执行。**

2. **同一个缺陷模式，两周内出现第 N 次：**
   - `MUJOCO_GL=glfw` 在无头环境（声明了后端，实际不可用）
   - 4 个未声明依赖（声明了核心依赖，实际不全）
   - `.dockerignore` 挡掉 MJCF → skip（声明了要测，实际没测）
   - `recoder_single_arm` 留 0 字节文件（声明了产物，实际是坏的）
   - **`tests/kinematics` 空目录 → 5 passed 的绿灯**（声明了要测，实际没测）
   - **同名测试函数被覆盖**（声明了要测，实际只跑了一个）

   **共性：声明了但行为不符，且失败时静默。**

   ⚠️ 而最后两条**是你自己写的代码**。📌 **这说明该模式与「谁写的」无关，与「有没有工具去查」有关。** 这个认识比抓到任何单个 bug 都重要。

   ⚠️ 尤其注意重复函数那条：**两份恰好逐字节相同，所以它零后果。** 如果两份有一点差异，症状会是「你以为在测 A，实际在测 B」，而**表面现象完全一样** —— 测试数不变、全绿、无警告。**这次是运气好，而不是防住了。**

3. **「决定不做」再次成为产出。** 这两天做了三个「不做」的决策，每个都有量化依据：

   | 不做什么 | 依据 |
   |---|---|
   | 不 lint `discoverse/` | 实测 277 errors / 59 files，与本 PR 目标无关 |
   | 不做 codecov | 需第三方账号，而数字日志里已有 |
   | 不做 schedule nightly | `--count=50` 单次数分钟 × 每天 × 2000 分钟额度 |

   📌 **注意第一个用了 `continue-on-error` 把债「可见化」** —— 这是「不做」和「假装没看见」的分水岭。

4. **一条第一次就绿的流水线，通常说明它什么都没测。** 这两天你至少见了三种「绿着骗你」的方式（106 passed、5 passed、被覆盖的测试）。

> **面试可用点**：被问「你搭过 CI 吗」时，别只答「用 GitHub Actions 写了个流水线」。
>
> 答：*「搭的时候第一次就红了 —— 干净 runner 上 `pip install -e .` 之后 import 直接崩，因为有 4 个包被 eager import 链拽进来却没写进核心依赖。这个问题我几天前在 Docker 镜像里撞过一次，但当时用 `--no-deps` 绕过去了，所以镜像绿了、真 bug 还在。**CI 是第一个不给我绕过去机会的环境。***
>
> *「另外我把 lint 范围刻意收窄到 `tests/`——`discoverse/` 有 277 个 ruff 错误，那是上游代码，一次性重排会制造巨大 diff 且和补测试这个目标无关。我用 `continue-on-error` 把这笔债做成了每次 CI 都可见的报告，而不是假装没看见。」*
>
> 📌 **第二段比第一段值钱。** 它展示的是判断力 —— 知道什么不该做，以及怎么让「不做」保持可追踪。

---

## 下一步

- **Day 12**：Jenkins 辅线（GPU 夜间回归）。⚠️ 先想清楚**它和 GitHub Actions 的分工**，别做成两条一模一样的流水线。Day 8-9 已实测「本机装了 nvidia-container-toolkit，GPU 确实能用」—— 这是 Jenkins 的差异化基础。
- **顺手能清的欠账**（见 checkpoint-day08-09 §六）：
  - `defect-report.md` §廿三~§廿五 **正文未写**（只补了总表）
  - `defect-inventory-day02.md` 未收录 V/W/X 且用旧编号
  - `task_base.py` 28% 是**当前最大覆盖率盲区**（162 statements 漏 117）

**记得写 `docs/checkpoint/checkpoint-day10-11.md`** —— 老规矩，每条结论标注「已核实 / 待核实」，记下被推翻的推断（累计 17 条，这两天大概率 +2 以上）。

⚠️ 关于基线数字：**这两天做完，`122 passed` 应当保持不变。**

这点值得单独说 —— 你会删掉一个重复的测试函数、跑 `ruff --fix`、跑 `black`，改动了不少文件，但**用例数一个都不该变**。因为那个重复函数本来就只被收集到一个，而格式化是等价变换。

📌 **「改了很多但数字不动」本身就是一条验收信号。** 数字要是动了，说明有东西被改坏了 —— 回去查，别记进 checkpoint 当新基线。
