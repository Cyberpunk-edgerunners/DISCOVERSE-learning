# 魔鬼日志 · Day 10-11（2026-08-16）

> GitHub Actions 主线 —— 从 0 到 5-job 全绿
> 上接 [devil-log-day08-09.md](devil-log-day08-09.md)
> 体例：按实际发生顺序记录，**包括走错的路**。

---

## 开工状态

```
分支 feat/test-infra，ahead 3（Day 8-9 的产出没推）
本机基线 122 passed, 4 skipped, 45 deselected, 15 xfailed
远端 origin/feat/test-infra 停在 eef1c4d
```

⚠️ **第一件事不是写 YAML，是把 Day 8-9 的东西推上去** —— CI 跑的是远端代码，本地没推等于云端看不见。

---

## 一、开课前核实：计划文档 8 处照抄必炸

老规矩，先把计划文档 §Day 10-11 的每条命令实跑一遍。

| 计划写的 | 实测 |
|---|---|
| `ruff check discoverse/ tests/` | **277 errors** |
| `black --check discoverse/ tests/` | **59 files would be reformatted** |
| `pytest tests/kinematics tests/simulation` | `tests/kinematics` **是空目录** → `4 passed, 1 xfailed`，只有 5 个用例 |
| `--cov=discoverse` | 分母 967→2584，覆盖率 **41%→28%** |
| `pip install -e .` | 漏 4 个包（缺陷 L′） |
| `actions/checkout@v3` / `setup-python@v4` | 版本过时 |
| `codecov/codecov-action@v3` | 需注册第三方 + token |
| nightly `--count=50 -n 8` | 三个插件镜像里都没装 |

📌 **`tests/kinematics` 那条最危险**：它是**绿的**。5 passed 的绿灯和 122 passed 的绿灯，在 GitHub 页面上长得一模一样。

---

## 二、额外挖到 3 件计划里没提的

### 2.1 `.gitattributes` 声明了 LFS

```
models/meshes filter=lfs diff=lfs merge=lfs -text
models/textures filter=lfs diff=lfs merge=lfs -text
```

**担心的链条**：LFS 指针 → `actions/checkout` 默认不拉 → MJCF 加载失败 → `conftest.py` 的 `pytest.skip` 静默兜住 → **CI 全绿但一个 MJCF 都没加载**。

**实测证伪前提**：

```bash
git lfs ls-files | wc -l                                          # → 0
git cat-file -p HEAD:models/meshes/airbot_play/arm_base_0.obj     # → mtllib material.mtl（真身）
git cat-file -s $(git rev-parse HEAD:...arm_base_0.obj)           # → 62028 字节
```

**是真实 obj，不是指针。** 文件在 LFS 规则生效前就已普通提交。

⚠️ **但隐患仍在**（本机 `/usr/bin/git-lfs 3.0.2` 装着）：将来加新 mesh 会变成指针，仓库进入「一半 LFS 一半不是」。

**对策**：smoke job 里加 `head -c 60 models/meshes/airbot_play/arm_base_0.obj`。一行命令换一个确定性。

### 2.2 仓库 308 MB

```
size-pack: 308.34 MiB
```

CI 每个 job 都要 checkout 一次。**5 个 job = 拉 5 次**（job 之间不共享）。

### 2.3 PyYAML 把 `on:` 解析成布尔

```python
d = yaml.safe_load(open('.github/workflows/ci.yml'))
list(d.keys())   # → ['name', True, 'concurrency', 'jobs']
'on' in d        # → False
```

YAML 1.1 把 `on`/`off`/`yes`/`no` 当布尔字面量。**GitHub 用 1.2，不受影响。**

⚠️ **危险在于误导排查方向**：写脚本查 `on` 配置发现「不存在」，会以为 workflow 写错了，去改一个没问题的地方。

---

## 三、Day 10：smoke job（`823a5b9`）

### 3.1 极简第一版

只做三件事：checkout、装 Python、打印环境。**故意什么都不测。**

理由：CI 反馈慢（本地 3 秒，CI 几分钟）。**一口气写 5 个 job 全红，不知道从哪查。**

### 3.2 结果：11 秒绿

关键输出：

```
/usr/bin/git log -1 --format=%H
823a5b969ee2ebf1b31761dfe8518fbaf991c695     ← 和本机 commit 一致

Python 3.10.20                                ← 和本机 conda 一致

--- models 目录是否完整（防 LFS 指针）---
mtllib material.mtl
usemtl material_0
v -0.07773600 0.030577                        ← 真身，不是 LFS 指针
```

📌 **§2.1 的担心在云端得到实证** —— 从「推理」变成「实测」。

### 3.3 一条警告，决定先不管

```
Node.js 20 is deprecated. actions/checkout@v4, actions/setup-python@v5
are being forced to run on Node.js 24
```

⚠️ **教程里写「用 @v4 别用 @v3」是对的，但不完整** —— `@v4` 也已在淘汰路径上。

**决定不升**：正在往上加 job，这时候动 action 大版本，红了分不清是谁的锅。**一次只改一件事。**

> 📌 **「实测过」不等于「永远有效」，工具链会自己往前跑。**

---

## 四、Day 10：unit job —— 第一次真红（`4efb64d`）

### 4.1 改掉计划文档的 4 个问题

| 问题 | 改法 |
|---|---|
| `pip install -e .` 漏包 | **刻意保留**（就是要它暴露缺陷 L′） |
| `--cov=discoverse` | 改成 `--cov`，读 `pyproject.toml` 的 source 配置 |
| 装 `xvfb` | 删掉 —— osmesa 是离屏渲染，不需要虚拟显示器 |
| 漏 `libglib2.0-0` | 补上（Day 8-9 血泪：缺它变成 7 个 ERROR、106 passed） |

### 4.2 结果：`failed in 56s` —— 完全命中预言

⚠️ **炸之前一切看着都很顺**，pip 报了两次 `Successfully installed`，第一条自检也过了：

```
MuJoCo 3.11.0
```

**第二条炸了**：

```
File ".../universal_manipulation/__init__.py", line 4, in <module>
    from .config_utils import (
File ".../universal_manipulation/config_utils.py", line 2, in <module>
    import yaml
ModuleNotFoundError: No module named 'yaml'
Error: Process completed with exit code 1.
```

### 4.3 ⭐ 日志里藏着一条 Day 8-9 看不到的东西

pip 的 `Collecting` 行区分了直接/间接依赖：

```
Collecting numpy>=1.20.0 (from discoverse==1.9.0)        ← 直接，11 行，没有 pyyaml
...
Collecting pillow>=8 (from matplotlib>=3.5.0->...)       ← ⚠️ 间接！蹭 matplotlib
Collecting pyopengl (from mujoco>=3.2.0->...)            ← ⚠️ 间接！蹭 mujoco
```

**`pillow` 和 `PyOpenGL` 其实装上了 —— 但靠运气。**

📌 **Day 8-9 的容器发现不了这个**：`--no-deps` 跳过依赖解析，**根本不打印 `Collecting` 行**。

> **同一个 bug，换个环境多暴露一层。**

### 4.4 另一个观察：版本策略不一致

```
MuJoCo 3.11.0        ← CI（pyproject.toml 写 >=3.2.0，范围）
mujoco==3.10.0       ← 镜像（requirements-test.txt，钉死）
```

**不是 bug，但要知道它存在** —— 哪天 CI 绿而容器红，这可能是原因。

---

## 五、修复缺陷 L′（`b91fa52`）

### 5.1 先核实整条 eager import 链

**没有照抄 checkpoint 的清单** —— Day 6-7 的教训就是「看见什么缺补什么」。

```bash
cat -n discoverse/universal_manipulation/__init__.py | head -17
```

第 4-16 行主动加载**全部 7 个子模块**。逐个 grep：

| 包 | 谁 import |
|---|---|
| `pyyaml` | `config_utils.py:2`、`robot_config.py:8`、`task_config.py:8` |
| `av` | `recorder.py:6-7` |
| `PyOpenGL` | `randomization.py:10` |
| `pillow` | `randomization.py:11` |

**4 个包，7 处 import，全部在 eager 链上。**

### 5.2 三层验证

| 层 | 命令 | 结果 | 能证明什么 |
|---|---|---|---|
| 1 TOML 语法 | `tomli.load(...)` | 15 项 | 没写坏 |
| 2 本机回归 | `pytest tests/ -q` | 122 passed | 没改坏 |
| 3 干净环境 | 容器 `pip install -e .` | — | ⭐ **唯一能证明修好了的** |

⚠️ **第 2 层有盲区**：本机本来就装着那 4 个包，**改不改都绿**。

**第 1 次踩的坑**：用了 `tomllib` → `ModuleNotFoundError`。那是 Python 3.11+ 才有的，环境是 3.10。**改用 `tomli`**（pytest 恰好依赖它）。

**第 2 次踩的坑**：第 3 层用 `timeout 600` 跑容器，**2 分钟就被自己掐断**（干净容器要下 150MB，opencv 一个就 73MB）。后台重跑，20 分钟仍未完成。

**决策：放弃本地第 3 层，交给 CI。** 理由：**CI runner 本身就是干净环境**，本地再模拟一遍是重复劳动，而且更慢。

---

## 六、⭐ 一次真实的排查失误

推送后看 CI，**仍然是同样的 `ModuleNotFoundError`**。

一度以为修复无效。核查顺序：

```bash
git log --oneline -3                          # 本地有 b91fa52 ✅
git ls-remote origin refs/heads/feat/test-infra
#   → 85e7beadb648... 远端确实是最新的 ✅
git show HEAD:pyproject.toml | grep pyyaml    # → 第 69 行有 ✅
```

⚠️ **一度怀疑第 108 行那个 `pyyaml` 造成冲突** —— 查了，它在 `[act]` optional 组里，与核心组无关。

**真相：看的是旧 run 的日志。** GitHub Actions 页面停在打开时那次，**不自动刷新**。

| 哈希 | 是哪次 |
|---|---|
| `4efb64d` | 修复前（贴的那份） |
| `85e7bea` | 修复后（该看的那份） |

📌 **核对 `git log -1 --format=%H` 是第一动作。** 一次失败的日志会一直挂在那儿，**看起来和新的一模一样**。

> **差点根据一份旧日志去改一个已经修好的东西。**

---

## 七、unit job 转绿（`85e7bea`）

```
Collecting pyyaml>=6.0 (from discoverse==1.9.0)       ← ⭐ 直接依赖了
Collecting av>=10.0.0 (from discoverse==1.9.0)
Collecting PyOpenGL>=3.1.0 (from discoverse==1.9.0)   ← ⭐ 不再蹭 mujoco
Collecting pillow>=8.0.0 (from discoverse==1.9.0)     ← ⭐ 不再蹭 matplotlib

MuJoCo 3.11.0
discoverse OK

122 passed, 4 skipped, 45 deselected, 15 xfailed in 8.92s
TOTAL    967    317    67%
```

**`succeeded in 1m 5s`。** 数字与本机完全一致，覆盖率分母是 967（`--cov` 不带参数生效）。

**副产品**：pip 缓存建立（215 MB）。上次失败时是 `pip cache is not found` —— **job 失败缓存不保存**。

---

## 八、Day 11：integration job（`ea8b16f`）

推之前先在本机验镜像（改过 `pyproject.toml`，而镜像里 `RUN pip install --no-deps -e .` 会重读它）。

**CI 结果**：

```
DISPLAY=[]
MUJOCO_GL=osmesa

122 passed, 4 skipped, 45 deselected, 15 xfailed in 4.30s
```

⭐ **四处数字一致**（本机 conda / 本机容器 / CI unit / CI integration），且 **unit 用 mujoco 3.11.0、integration 用 3.10.0** —— 两条独立路径互证。

**新观察**：容器里多一条警告，unit job 没有：

```
discoverse/__init__.py:11: DeprecationWarning: invalid escape sequence '\('
```

**未修**（在 `discoverse/` 里，属上游代码）。记入欠账。

---

## 九、Day 11：lint job —— 数字对不上（`053a272` + `67b0d3d`）

### 9.1 ⚠️ 教程里的 10 errors 失效了

实跑 `ruff check tests/`：

```
Found 2 errors.
```

而且重复函数报的是 **`test_validate_config_rejects_missing_required_fields`（199/218）**，不是教程写的 `..._should_require_observation`（214/251）。

**查因**：

```bash
git status --short
#   M tests/simulation/test_determinism.py
#   M tests/unit/test_mink_solver.py
#   M tests/unit/test_randomization_config.py
#   M tests/unit/test_recorder.py
#   M tests/unit/test_task_config.py     ← 18 deletions
```

**文件已经被改过** —— 第一组重复已删、`ruff --fix` 已跑过一轮。

> 📌 **删掉第一组后，ruff 才报出第二组。** **lint 要反复跑到干净为止。**

### 9.2 两组重复都逐字节相同

```bash
diff <(sed -n '197,207p' ...) <(sed -n '216,226p' ...)
# → 完全相同
```

**所以零可观测后果**，122 passed 一直是对的。

⚠️ **但这是运气**：若两份有差异，症状会是「你以为测 A，实际测 B」，**表面完全正常**。

### 9.3 `subprocess.run` 那条

`test_task_matrix.py:79` 靠 `returncode` 分类（`_classify`），**非零是预期输入**。加 `check=False` + 注释，**不改变行为，只是把隐式契约写明**。

### 9.4 范围决策

| 范围 | ruff | black |
|---|---|---|
| `tests/` | 2 → 0 | 9 files → 0 |
| `discoverse/` | **277** | **59 files** |

**决策**：`tests/` 严格拦截；`discoverse/` 用 `continue-on-error: true` **仅报告**。

📌 **`continue-on-error` 是「不做」和「假装没看见」的分水岭。**

### 9.5 钉死 lint 版本

```yaml
- run: pip install ruff==0.16.2 black==26.5.1
```

**理由**：不钉的话 CI 装最新版，新增规则会让刚清干净的 `tests/` 又变红 —— **而那不是代码变差了，是尺子换了**。

---

## 十、收尾（`c8c22b6` + `6263899`）

### 10.1 nightly：做手动触发版

```yaml
if: github.event_name == 'workflow_dispatch'
```

**不做 schedule 的理由**：`--count` 单次数分钟 × 每天 × 2000 分钟/月额度，而当前代码变动频率低，**没什么可监控的**。

三个插件（`pytest-repeat`/`xdist`/`json-report`）**容器内临时装**，不进 `requirements-test.txt` —— 只有 flake 实验用得到。

### 10.2 徽章

```markdown
[![CI](.../badge.svg?branch=feat/test-infra)](...)
```

⚠️ **`?branch=` 不能漏**：不加则查默认分支 main，而 main 上没有 `ci.yml` → **显示灰色 `no status`**。

📌 **「显示了但显示错了」比「不显示」更糟** —— 会以为是缓存或网络问题。

### 10.3 省钱

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

paths-ignore: ["docs/**", "source-notes/**", "**.md"]
```

⚠️ **`paths-ignore` 将来配 branch protection 要回来重想** —— 被跳过的 job 状态是 `skipped` 而非 `success`，PR 会一直卡在等待检查。

---

## 十一、最终状态

```
jobs: ['smoke', 'unit', 'integration', 'lint', 'nightly']
ci.yml 183 行
9 个 commit，全部已推送，工作区干净
122 passed, 4 skipped, 45 deselected, 15 xfailed
```

---

## 十二、两天踩的坑汇总

| # | 坑 | 表现 | 教训 |
|---|---|---|---|
| 1 | job 之间不共享环境 | — | 每个 job 是独立虚拟机，各自从零备环境 |
| 2 | PyYAML 把 `on:` 当布尔 | 脚本报「`on` 不存在」 | YAML 1.1 vs 1.2；**workflow 本身没问题** |
| 3 | `pip install -e .` 漏 4 包 | `ModuleNotFoundError: yaml` | **缺陷 L′**；CI 是干净环境，必然复现 |
| 4 | `--cov=discoverse` | 41%→28% | 分母要有意义 |
| 5 | `tests/kinematics` 空目录 | **5 passed 绿灯** | 和 122 的绿灯长得一样 |
| 6 | `tomllib` 在 3.10 不存在 | `ModuleNotFoundError` | 用 `tomli` |
| 7 | `timeout 600` 掐断容器 | 自己把验证掐了 | 干净容器要下 150MB，别掐 |
| **8** | **⭐ 看了旧 run 的日志** | **以为修复无效** | **核对 commit 哈希是第一动作** |
| 9 | 教程里的 lint 数字失效 | 10 errors → 实际 2 | **改过之后旧数字就废了** |
| 10 | 删第一组重复才暴露第二组 | — | **lint 要反复跑到干净** |
| 11 | 徽章不加 `?branch=` | 灰色 `no status` | 默认查 main，而 workflow 在 feature 分支 |
| 12 | lint 工具版本不钉 | CI 可能红 | **尺子变了不等于代码变差** |

⚠️ **坑 5 和坑 10 是同一类**：**它们都表现为绿灯或无声**。

---

## 十三、这两天真正学到的

1. **CI 的价值不是「自动」，是「在一个你控制不了的环境里执行」。** 本机脏、镜像用 `--no-deps` 绕过 `pyproject.toml` —— **CI 是第一个不给绕的**。

2. **`ci.yml` 只有 183 行，10 分钟能写完** —— 但它调用的每一样东西都是前 9 天挣出来的。**没有那 122 个测试，它就是个每次都绿的空壳。**

3. **「决定不做」再次成为产出**，且都有量化依据：

   | 不做 | 依据 |
   |---|---|
   | 不 lint `discoverse/` | 277 errors / 59 files，与本 PR 目标无关 |
   | 不做 codecov | 需第三方账号，数字日志里已有 |
   | 不做 schedule nightly | 单次数分钟 × 每天 × 2000 分钟额度 |
   | 不升 action 大版本 | 正在加 job，一次只改一件事 |

4. **同一个 bug，换个环境多暴露一层。** 容器抓到「4 个包缺失」，CI 多抓到「其中 2 个是蹭来的」。

---

## 下一步

**Day 12：Jenkins 辅线（GPU 夜间回归）。**

⚠️ 先想清它和 GitHub Actions 的分工 —— 本机 RTX 4060 + nvidia-container-toolkit 已可用（Day 8-9 §4.1），**差异化才是理由**，别做成两条一样的流水线。

欠账见 [checkpoint-day10-11.md](../checkpoint/checkpoint-day10-11.md) §七。
