# Checkpoint · Day 10-11（2026-08-16）

> 分支：`feat/test-infra` ｜ 状态：**Day 10-11 完成（GitHub Actions 5-job 流水线全绿），工作区干净、已推送**
> 历史见 [checkpoint-day08-09.md](checkpoint-day08-09.md)
> 用途：下次开工只读这一份即可接上。

**本文每条推断都标注「已核实 / 待核实」。** Day 10-11 有 **3 条既有推断被实测推翻**（见第五节），累计 **20 条**（去重后）。

---

## 一、下次开工第一件事

```bash
cd /home/ubuntu22/workspaces/airbot-play/DISCOVERSE
source scripts/dev/env.sh && $PY -m pytest tests/ -q
#   预期：122 passed, 4 skipped, 45 deselected, 15 xfailed

$PY -m ruff check tests/ && $PY -m black --check tests/
#   预期：All checks passed! / 14 files would be left unchanged

git status --short
#   预期：空（Day 10-11 产出已全部提交推送）
```

✅ **工作区干净**，与远端同步（`feat/test-infra` 无 ahead/behind）。

---

## 二、Day 10-11 成果【已核实，实跑 + CI 实证】

### 2.1 提交清单（7 个 commit，全部已推送）

| commit | 内容 |
|---|---|
| `823a5b9` | ci: 最小可用流水线（smoke job） |
| `4efb64d` | ci: 加 unit job |
| **`b91fa52`** | **fix: 补齐 eager import 链的 4 个未声明依赖（缺陷 L′）** |
| `85e7bea` | docs: Day 10-11 教程补入 CI 实测日志与三层验证法 |
| `ea8b16f` | ci: 加 integration job（Docker 镜像跑全量测试） |
| `053a272` | style: 清理 tests/ 的 lint 债 |
| `67b0d3d` | ci: 加 lint job（tests/ 严格，discoverse/ 仅报告） |
| `c8c22b6` | ci: 加 nightly job（手动触发 flake 采样） |
| `6263899` | ci: README 徽章 + concurrency 取消 + 文档路径过滤 |

### 2.2 `.github/workflows/ci.yml`（183 行，5 个 job）

```
jobs: ['smoke', 'unit', 'integration', 'lint', 'nightly']
触发: ['push', 'pull_request', 'workflow_dispatch']
paths-ignore: ['docs/**', 'source-notes/**', '**.md']
concurrency: 已配置（cancel-in-progress）
```

| job | 验证什么 | 状态 |
|---|---|---|
| `smoke` | 代码能拉下来、python 能起来、**mesh 不是 LFS 指针** | ✅ 11s |
| `unit` | ⭐ **`pyproject.toml` 依赖声明完整性**（`pip install -e .`） | ✅ 1m5s，122 passed |
| `integration` | ⭐ **镜像可复现性**（`requirements-test.txt` + `--no-deps`） | ✅ 122 passed |
| `lint` | `tests/` 严格；`discoverse/` 仅报告（`continue-on-error`） | ✅ |
| `nightly` | flake 采样，**仅 `workflow_dispatch` 手动触发** | 未跑（设计如此） |

📌 **`unit` 与 `integration` 不是重复** —— 两条依赖路径互补，各补对方盲区。**这是面试题的标准答案**，见 §六。

### 2.3 ⭐ 四处数字一致【本次最强证据】

```
122 passed, 4 skipped, 45 deselected, 15 xfailed
```

| 环境 | 依赖来源 | mujoco 版本 | 结果 |
|---|---|---|---|
| 本机 conda | 历史累积（脏） | 3.10.0 | ✅ |
| 本机容器 | `requirements-test.txt` 钉死 | 3.10.0 | ✅ |
| **CI unit** | `pyproject.toml` 范围解析 | **3.11.0** | ✅ |
| **CI integration** | `requirements-test.txt` 钉死 | 3.10.0 | ✅ |

⚠️ **注意 mujoco 版本不同但结果相同** —— 两条独立路径互证，比单条路径绿有说服力得多。

### 2.4 数字对比

| 指标 | Day 9 结束 | **Day 11 结束** |
|---|---|---|
| 用例 | 122 | **122**（不变，见下） |
| 覆盖率 TOTAL | 67% | **67%** |
| 定位缺陷总数 | 23 | **25**（+2） |
| **缺陷修复** | 5 | **6**（+1，缺陷 L′） |
| commit | 4 | **13**（+9） |
| CI job | 0 | **5** |

📌 **用例数不变是预期结果，不是没干活**：删掉的两个重复函数本来就只被 pytest 收集到一个。**「改了很多但数字不动」本身就是一条验收信号。**

---

## 三、缺陷 L′ 已修复【已核实，CI 实证】

### 3.1 修复内容

`pyproject.toml` 核心 `dependencies`：**11 项 → 15 项**

| 新增 | 谁 import |
|---|---|
| `pyyaml>=6.0` | `config_utils.py:2`、`robot_config.py:8`、`task_config.py:8` |
| `av>=10.0.0` | `recorder.py:6-7` |
| `PyOpenGL>=3.1.0` | `randomization.py:10` |
| `pillow>=8.0.0` | `randomization.py:11` |

**修复前 CI 报错**（`4efb64d` 那次 run）：

```
File ".../universal_manipulation/__init__.py", line 4, in <module>
    from .config_utils import (
File ".../universal_manipulation/config_utils.py", line 2, in <module>
    import yaml
ModuleNotFoundError: No module named 'yaml'
Error: Process completed with exit code 1.
```

**修复后**（`85e7bea` 那次 run）：

```
MuJoCo 3.11.0
discoverse OK
```

### 3.2 ⭐ 新发现：「幸运的间接依赖」【已核实】

CI 日志的 `Collecting` 行暴露了 Day 8-9 看不到的一层：

| 包 | 修复前 | 修复后 |
|---|---|---|
| `pyyaml` | **完全没有** | `(from discoverse==1.9.0)` |
| `av` | **完全没有** | `(from discoverse==1.9.0)` |
| **`pillow`** | **`(from matplotlib->...)`** ⚠️ | `(from discoverse==1.9.0)` |
| **`PyOpenGL`** | **`(from mujoco->...)`** ⚠️ | `(from discoverse==1.9.0)` |

⚠️ **后两个修复前其实装上了 —— 但靠运气。** matplotlib 哪天不再依赖 pillow，`randomization.py:11` 就崩，**而你一行代码都没改**。

📌 **Day 8-9 的容器看不到这一层**，因为 `--no-deps` 跳过依赖解析，**根本不打印 `Collecting` 行**。

> **同一个 bug，换个环境多暴露一层。**

---

## 四、新增 2 条缺陷【已核实，ruff 实测】

### 4.1 缺陷 AA｜`test_task_config.py` 两组测试函数重复定义 🟡 Medium

```
F811 Redefinition of unused `test_validate_config_should_require_observation` (214 / 251)
F811 Redefinition of unused `test_validate_config_rejects_missing_required_fields` (199 / 218)
```

Python 后定义的同名函数**直接顶掉**前者 → **两个测试从未执行**，而 **pytest 完全不报错**。

⚠️ **两组各自逐字节相同**（已 `diff` 验证），所以**零可观测后果** —— 122 passed 一直是对的。

📌 **但这是运气**：若两份有差异，症状会是「你以为测 A，实际测 B」，**表面完全正常**。

**修复**：各删前者（`053a272`）。用例数不变。

### 4.2 缺陷 AB｜`subprocess.run` 未显式声明 `check` 🟢 Low

`tests/integration/test_task_matrix.py:79` —— 该用例靠 `returncode` 分类（`_classify`），非零是**预期输入**而非异常。

**修复**：显式 `check=False` + 注释说明意图。**不改变行为，只是把隐式契约写明。**

### 4.3 待办：`discoverse/__init__.py:11` 无效转义序列 🟢 Low

```
DeprecationWarning: invalid escape sequence '\(' —— __logo__ = """
```

⚠️ **只在容器里出现，unit job 没有**（两边警告过滤不同）。未来 Python 版本会变成语法错误。

**未修** —— 在 `discoverse/` 里，属上游代码，一次只改一件事。

---

## 五、Day 10-11 被推翻的三条推断【已核实】

### 5.1 ⭐ 「`tests/` 有 10 个 ruff 错误」—— 数字来自动手前，已过时

| | 内容 |
|---|---|
| **原记录**（教程 Step 6.3 初稿） | `ruff check tests/` → 10 errors；重复函数在 214/251 行 |
| **实测**（清债过程中） | 删掉第一组后重跑，**只剩 2 errors**，且重复函数变成 **199/218 行的另一个** |

**原因**：中途已做过一轮 `ruff --fix` + 删除，**旧数字失效**。

> 📌 **教训**：**lint 要反复跑到干净为止。** 修完一轮会暴露下一轮 —— 同一文件里的第二组重复，是删掉第一组后才报出来的。

### 5.2 「计划文档的 lint 范围（`discoverse/ tests/`）可用」

| | 内容 |
|---|---|
| **计划文档** | `ruff check discoverse/ tests/` + `black --check discoverse/ tests/` |
| **实测** | **277 errors / 59 files** —— 照抄则 lint job 必红且红得没意义 |

**决策**：`tests/` 严格拦截，`discoverse/` 用 `continue-on-error: true` **仅报告**。

📌 **这是「不做」和「假装没看见」的分水岭** —— 债被量化且每次 CI 可见。

### 5.3 「`.gitattributes` 声明 LFS，CI checkout 拿不到 mesh」

| | 内容 |
|---|---|
| **原担心** | `models/meshes filter=lfs` → `actions/checkout` 默认不拉 LFS → 静默 skip |
| **实测** | `git lfs ls-files` = 0；blob 里是真实 obj 内容；**CI 日志确认拿到真身** |

**风险机制描述是对的，但本项目不满足触发条件** —— 文件在 LFS 规则生效前就已普通提交。

⚠️ **但隐患仍在**：将来谁在装了 git-lfs 的机器上加新 mesh，那个新文件会变成指针，**仓库进入「一半 LFS 一半不是」**。smoke job 里那行 `head -c 60` 就是这道守护。

---

## 六、⭐ 方法论收获（面试可直接用）

### 6.1 `unit` 与 `integration` 为什么不是重复

| | `unit` | `integration` |
|---|---|---|
| 装法 | `pip install -e .`（解 `pyproject.toml`） | `requirements-test.txt` + `--no-deps` |
| 验证 | ✅ **依赖声明完整性** | ✅ **镜像可复现性** |
| 版本策略 | 范围（跟随上游，装到 3.11.0） | 钉死（3.10.0） |
| 贴近 | 「新人 clone 能不能跑」 | 「生产环境部署」 |

📌 **缺陷 L′ 只有 `unit` 能抓到** —— 镜像的 `--no-deps` 恰好绕过了 `pyproject.toml`。

### 6.2 一次真实的排查失误【值得记住】

**修复推送后，看到 CI 仍报同样的 `ModuleNotFoundError`，一度以为没修好。**

**真相**：看的是**旧 run 的日志**。GitHub Actions 页面停在打开时那次，不自动刷新。

📌 **核对 `git log -1 --format=%H` 那行输出是第一动作**：

| 哈希 | 是哪次 |
|---|---|
| `4efb64d` | 修复前 |
| `85e7bea` | 修复后 |

> **一次失败的日志会一直挂在那儿，看起来和新的一模一样。**

### 6.3 「声明了但行为不符，且失败时静默」——本阶段又添 3 例

累计模式清单（见 [defect-report.md](../defect-report.md) §1.3）：

| 案例 | 声明 | 实际 |
|---|---|---|
| `MUJOCO_GL=glfw` | 有渲染后端 | 无头环境不可用 |
| 4 个未声明依赖 | 核心依赖完整 | 干净环境崩 |
| `.dockerignore` 挡 MJCF | 要测 | pytest.skip 兜住 |
| `recoder_single_arm` | 有产物 | 0 字节坏文件 |
| **`tests/kinematics` 空目录** | **要测** | **5 passed 假绿灯** |
| **两组重复测试函数** | **要测** | **前者从未执行** |
| **`.gitattributes` 声明 LFS** | **走 LFS** | **实际没走**（本次无害） |

⚠️ **最后两条是自己写的代码。** 该模式**与「谁写的」无关，与「有没有工具去查」有关**。

---

## 七、Day 12+ 待办

### 优先级 1：Jenkins 辅线（Day 12 计划内容）

⚠️ **先想清分工，别做成两条一样的流水线。**

- GitHub Actions 免费 runner **无 GPU** —— 已按此设计（CPU + osmesa）
- 本机 **RTX 4060 + nvidia-container-toolkit 已装可用**（Day 8-9 §4.1 实测）
- **差异化**：轻量测试走云端，需 GPU 的重型测试走本地

### 优先级 2：CI 自身的欠账

- [ ] `actions/checkout@v4` / `setup-python@v5` **仍报 Node 20 弃用警告**。根治是升到 `@v5`/`@v6`。**当时刻意不升 —— 一次只改一件事**，现在 5 个 job 全绿了，可以单独一个 commit 升级
- [ ] `paths-ignore` ⚠️ **将来配 branch protection 要回来重想** —— 被跳过的 job 状态是 `skipped` 而非 `success`，PR 会一直卡在等待检查
- [ ] `nightly` 目前只手动触发。等代码开始高频变动，改 `if` 条件为 `schedule`
- [ ] 本机 lint 版本已钉死在 job 里（`ruff==0.16.2` / `black==26.5.1`），**升级时要同步改两处**

### 优先级 3：覆盖率盲区（未变）

| 模块 | 覆盖率 | 备注 |
|---|---|---|
| **`task_base.py`** | **28%** | ⚠️ **最大盲区**，162 statements 漏 117 |
| `robot_interface.py` | 56% | |
| `task_config.py` | 63% | |
| `randomization.py` | 69% | |

### 优先级 4：文档欠账（Day 5-9 遗留，仍未动）

- [ ] [defect-report.md](../defect-report.md) 需新增 §廿九（缺陷 AA）、§三十（缺陷 AB）
- [ ] `defect-inventory-day02.md` 未收录 V/W/X，且用旧编号
- [ ] Day 6-7 §4.1-4.3 的三条更正尚未回写到 inventory 与 tutorial
- [ ] 45 组合的 `test_declared_cameras_exist_in_mjcf`
- [ ] BUCKET2 根因（优先查物体朝向）
- [ ] 缺陷 #3（pytest 超时未生效）**根因仍未定位**
- [ ] `discoverse/__init__.py:11` 无效转义序列（见 §4.3）

---

## 八、环境速查

```bash
source scripts/dev/env.sh

# 本机回归（3 秒）
$PY -m pytest tests/ -q
#   122 passed, 4 skipped, 45 deselected, 15 xfailed

# lint（推 CI 前必跑，省一次往返）
$PY -m ruff check tests/ && $PY -m black --check tests/

# 覆盖率
$PY -m pytest tests/ -q --cov --cov-report=term-missing 2>&1 | grep -E "task_base|TOTAL"
#   ⚠️ 别写 --cov=discoverse，分母 967→2584，41%→28%，与历史记录对不上

# ---- Docker（所有命令必须在项目根跑）----
docker build -f discoverse/docker/Dockerfile.test -t discoverse:test .
docker run --rm discoverse:test pytest tests/ -q
docker run --rm discoverse:test sh -c 'echo "DISPLAY=[$DISPLAY]"; echo "MUJOCO_GL=$MUJOCO_GL"'

# ---- CI ----
# YAML 语法 + 结构（⚠️ 用 d[True] 读 on —— PyYAML 把 on 解析成布尔）
$PY -c "
import yaml
d = yaml.safe_load(open('.github/workflows/ci.yml'))
print('jobs:', list(d['jobs']))
print('触发:', list(d[True]))
"
#   jobs: ['smoke', 'unit', 'integration', 'lint', 'nightly']

# flake 用例（默认被 addopts 的 -m 'not flake' 排除，即那 45 个 deselected）
$PY -m pytest tests/ -m flake -q --collect-only | tail -3

# CI 页面
#   https://github.com/Cyberpunk-edgerunners/DISCOVERSE-learning/actions
#   ⚠️ 页面不自动刷新。核对日志里 git log -1 --format=%H 的输出，确认在看哪次 run
```

---

## 九、Day 0-11 累计

| | Day 9 结束 | **Day 11 结束** |
|---|---|---|
| 用例 | 122 | **122** |
| 覆盖率 | 67% | **67%** |
| commit | 4 | **13** |
| 缺陷修复 | 5 | **6** |
| 定位缺陷总数 | 23 | **25** |
| 严重度基于实测下调 | 2 | 2 |
| 被推翻的文档推断 | 17 | **20** |
| **CI job** | **0** | **5（全绿）** |

**Day 10-11 的产出是一条 5-job 流水线 + 缺陷 L′ 的根治 + 两个幽灵测试的清除。**

> **最值得带走的一条**：`ci.yml` 只有 183 行，10 分钟能写完 —— **但它调用的每一样东西都是前 9 天挣出来的**。没有那 122 个测试、那个无头镜像、那次确定性修复，这条流水线就是个每次都绿的空壳。
>
> 而它第一次运行就抓到了一个**本机和容器都发现不了**的真 bug：镜像用 `--no-deps` 绕过了 `pyproject.toml`，**所以镜像绿了、真 bug 还在**。
>
> **CI 是第一个不给我绕过去机会的环境。**
