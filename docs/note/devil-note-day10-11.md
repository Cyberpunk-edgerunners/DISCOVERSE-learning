# 魔鬼笔记 · Day 10-11 —— CI/CD 的知识拆解

> 上接 [devil-note-day08-09.md](devil-note-day08-09.md)
> 体例：**概念 → 为什么这样设计 → 本项目实测 → 能迁移到别处的部分**
> 过程实录见 [devil-log-day10-11.md](../log/devil-log-day10-11.md)

---

## 一、CI/CD 到底是什么

### 1.1 拆词

| | 全称 | 干什么 |
|---|---|---|
| **CI** | Continuous **Integration**（持续集成） | 每次改动自动**验证**没搞坏 |
| **CD** | Continuous **Delivery/Deployment** | 验证过了自动**发布** |

⚠️ **本项目做的全是 CI，CD 一点没碰** —— 它不是要部署的服务，没有「发布」这个动作。

**面试时别把 CI 说成 CI/CD。** 说清楚做了哪一半，比含糊带过更可信。

### 1.2 ⭐ `ci.yml` 只是按钮，不是机器

```
ci.yml            = 一张「先做A、再做B」的清单       ← 183 行，10 分钟写完
真正值钱的        = A 和 B 本身能不能自动跑、算不算数  ← 前 9 天挣的
```

看 `ci.yml` 里 `run:` 后面跟的是什么：

| 那行命令 | 哪天做出来的 |
|---|---|
| `pytest tests/ -q --cov` | Day 2-9 的 122 个测试 |
| `docker build -f .../Dockerfile.test` | Day 8-9 的无头镜像 |
| `ruff check tests/` | 刚清完债才能这么写 |

📌 **流水线的价值 = 它调用的那些东西的价值。** 没有那 122 个测试，`ci.yml` 是个每次都绿的空壳。

**这条是本阶段最该带走的认知。**

---

## 二、GitHub Actions 的三层结构

```
workflow（工作流）= 一个 .yml 文件
  └── job（任务）  = 一台独立的虚拟机
        └── step   = 一条命令 或 一个别人写好的动作
```

### 2.1 ⚠️ job 之间完全隔离

| | |
|---|---|
| 每个 job | **一台全新虚拟机**：开机 → 干活 → **销毁** |
| job A 装的东西 | job B **看不到** |
| 默认 | **并行**（除非用 `needs` 声明依赖） |
| step 之间 | **串行**，从上到下 |

📌 **新手最大误解来源**：以为 job1 装依赖、job2 能用。**每个 job 必须自己从零备环境。**

⚠️ **注意 job 并行、step 串行 —— 方向正好相反**，容易混。

**本项目实证**：5 个 job 各自 checkout 一次 308 MB 仓库，各自下载同样的 action。

### 2.2 `uses` vs `run`

| | 是什么 |
|---|---|
| `run` | **一条 shell 命令**，就是终端里敲的那些 |
| `uses` | **别人封装好的动作**，从 GitHub 市场拉 |

日志里能看到 `uses` 被解析成确切版本：

```
Download action repository 'actions/checkout@v4' (SHA:11d5960a...)
```

📌 **`@v4` 是会移动的标签，SHA 才是那一刻的真身。** 日志记 SHA 是为了将来能查「当时到底跑的哪个版本」。

---

## 三、⭐ 依赖声明：本阶段的核心知识

### 3.1 三种依赖的区别

| | 谁声明的 | pip 日志长什么样 |
|---|---|---|
| **直接依赖** | 你自己（`pyproject.toml`） | `Collecting X (from discoverse==1.9.0)` |
| **间接依赖** | 你的依赖的依赖 | `Collecting X (from matplotlib->discoverse==1.9.0)` |
| **幸运的间接依赖** | ⚠️ **没人**（你 import 了但没声明，碰巧被别人拽进来） | 同上，**但你的代码在直接用它** |

**箭头 `->` 就是分界线。**

### 3.2 「幸运的间接依赖」为什么是定时炸弹

本项目实测（修复前）：

```
Collecting pillow>=8 (from matplotlib>=3.5.0->discoverse==1.9.0)
Collecting pyopengl (from mujoco>=3.2.0->discoverse==1.9.0)
```

而 `randomization.py:10-11` **直接 import 了这两个**。

| | 现在 | matplotlib 哪天不再依赖 pillow |
|---|---|---|
| pillow 在不在 | 在（蹭的） | **不在 → 代码崩** |
| 你改过代码吗 | — | **没有。是别人的依赖变了** |

📌 **声明依赖的意义就是不靠运气。**

### 3.3 eager import 链

```python
# universal_manipulation/__init__.py 第 4-16 行
from .config_utils import (...)      # → import yaml
from .robot_config import ...        # → import yaml
from .mink_solver import ...         # → import mink
from .randomization import ...       # → import OpenGL, PIL
from .recorder import ...            # → import av
```

**「eager（急切）import」** = 一导入包就加载全部子模块。

⚠️ **后果**：`import discoverse.universal_manipulation` 会拉起整条链，**任一环缺失就整包崩** —— 不是「运行某脚本才报错」，是连 import 都过不去。

**对应的 traceback 特征**：

```
File ".../__init__.py", line 4, in <module>      ← in <module> = 模块顶层
File ".../config_utils.py", line 2, in <module>  ← 不在任何函数里
ModuleNotFoundError: No module named 'yaml'
```

📌 **`in <module>` 是 eager import 的标志。**

### 3.4 ⚠️ traceback 要从下往上读

| 位置 | 是什么 |
|---|---|
| 最下面 | ⭐ **真因** |
| 上面几行 | 怎么走到那儿的（调用路径） |
| 最上面 | 起点 |

**Day 8-9 §5.3 是同一个道理**：`Unable to locate package` 不是包名错了，真因在几十行之前的 `Failed to fetch`。

> **下游症状会伪装成根因。日志要从上往下读，traceback 要从下往上读。**

---

## 四、pytest 的四种结局

`122 passed, 4 skipped, 45 deselected, 15 xfailed`

**pytest 分两步干活**：

```
第 1 步 收集（collect）—— 扫描 tests/，找出所有 test_ 函数
第 2 步 执行（run）    —— 挑出要跑的
```

| 词 | 跑了吗 | 什么意思 |
|---|---|---|
| `passed` | ✅ | 正常通过 |
| `xfailed` | ✅ | **预先声明「现在必挂」**，真挂了 → 符合预期 |
| `skipped` | ❌ | **运行时**才发现条件不满足 |
| **`deselected`** | ❌ | **运行前**就按规则筛掉 |

⚠️ **`skipped` vs `deselected`**：

- `skipped` = 走到门口，发现进不去
- `deselected` = **压根没被叫号**

### 4.1 那 45 个是怎么被筛掉的

```toml
# pyproject.toml
addopts = "--strict-markers --tb=short -ra -m 'not flake'"
                                          ↑
                          「只跑没有 flake 标记的」
```

`test_task_matrix.py` 的 45 个用例标了 `@pytest.mark.flake`，**每次自动排除**。

📌 **这是刻意的分层**：把测试分成「随时跑的」和「偶尔跑的」。日常回归 3 秒跑完，是因为那 45 个重活被排除了。**不排除的话每次好几分钟，你就不会想跑测试了。**

要跑它们得显式指定：`pytest tests/ -m flake`。

---

## 五、lint：和测试互补的另一半

### 5.1 lint 不是测试

| | 干什么 | 能发现 |
|---|---|---|
| **测试** | **真的运行**代码 | 逻辑错误 |
| **lint** | **不运行**，只读源码 | 拼写、重复定义、没用的导入 |

📌 **本项目实证**：122 个测试全绿，但 lint 抓到**两个测试函数从未执行**（同名被覆盖）。

> **测试证明「跑了的东西是对的」，lint 能发现「有东西根本没跑」。**

### 5.2 ruff vs black

| | 管什么 | 会改变行为吗 |
|---|---|---|
| **black** | **长相**（排版、空格、引号） | ❌ 绝不 |
| **ruff** | **毛病**（有没有问题） | 可能（如删无用 import） |

**black 的设计哲学**：「the uncompromising formatter」—— 几乎无配置项，**不给你选**。好处是团队再也不为「大括号换不换行」吵架。

**ruff 的特点**：Rust 写的，**快**，适合放进 CI。

### 5.3 ⚠️ lint 要反复跑到干净

**本项目实测**：删掉第一组重复函数后，ruff 才报出**同一文件里的第二组**。

📌 **修完一轮会暴露下一轮。** 「跑一次修完」是不够的。

### 5.4 范围决策：本阶段最需要判断力的一步

| 范围 | ruff | black |
|---|---|---|
| `tests/`（自己写的） | 2 | 9 files |
| `discoverse/`（上游的） | **277** | **59 files** |

三个坏选择：

| 做法 | 后果 |
|---|---|
| 全改 | **一次动 59 个文件**，PR 没法 review，且与上游冲突 |
| 让它红 | CI 永远红 → **红灯失去意义** |
| 删掉 lint job | 少一块能力证明 |

**第四个选择**：

```yaml
- name: ruff（只查 tests/）
  run: ruff check tests/              # 严格拦截

- name: discoverse/ 现状报告（不拦截）
  continue-on-error: true             # ⭐ 报告但不阻塞
  run: ruff check discoverse/ --statistics || true
```

📌 **`continue-on-error` 表达的是**：

> 「我知道这里有债，**我量化了它**（277 个），我选择现在不还，但**让它每次 CI 都可见**。」

**这是「不做」和「假装没看见」的分水岭。**

### 5.5 为什么要钉死 lint 版本

```yaml
- run: pip install ruff==0.16.2 black==26.5.1
```

不钉的话 CI 装最新版，**新增规则会让刚清干净的 `tests/` 又变红**。

📌 **而那不是代码变差了，是尺子换了。** 区分这两者很重要 —— 否则你会去「修」一个没坏的东西。

---

## 六、覆盖率的分母

```bash
pytest tests/unit --cov=discoverse   # → TOTAL 2584 1864 28%
pytest tests/unit --cov              # → TOTAL  967  573 41%
```

**同一批测试，28% vs 41%。**

差别在 `pyproject.toml`：

```toml
[tool.coverage.run]
source = ["discoverse/universal_manipulation"]
```

📌 **覆盖率不是越大越好，是「分母要有意义」。** 把没打算测的代码算进分母，数字一路走低，然后你就不看它了 —— **一个没人看的指标等于没有**。

---

## 七、CI 成本控制

免费额度每月 2000 分钟，三个手段：

### 7.1 pip 缓存

```yaml
- uses: actions/setup-python@v5
  with:
    cache: pip
```

日志证据：

```
第一次： pip cache is not found
成功后： Cache saved with the key: setup-python-Linux-x64-...-pip-035e02d0...
```

⚠️ **job 失败缓存不保存** —— 所以第一次红的那轮没建立缓存。

📌 **缓存 key 含依赖清单指纹** —— 改 `pyproject.toml` 依赖，key 就变，**缓存自动失效**，不会拿到过期的东西。

### 7.2 并发取消

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

连推 3 个 commit 默认并行跑 3 条流水线，**前两条的结果你根本不会看**。

### 7.3 路径过滤

```yaml
paths-ignore: ["docs/**", "source-notes/**", "**.md"]
```

⚠️ **规则**：只有当本次改动的文件**全部**被忽略时才跳过。

⚠️ **将来配 branch protection 要回来重想** —— 被跳过的 job 状态是 `skipped` 而非 `success`，**PR 会一直卡在等待检查**。

---

## 八、徽章

**本质是一张图片**，Markdown 里就是「可点击的图片」。

| | `img.shields.io` 那种 | GitHub 生成的那种 |
|---|---|---|
| 内容 | **写死在 URL 里** | **实时查询** |
| 会变吗 | ❌ | ✅ 随 CI 结果变色 |
| 能造假吗 | ✅ 随便写 | ❌ 点进去能看真实记录 |

```
https://img.shields.io/badge/License-MIT-green.svg
                             ↑名称   ↑值  ↑颜色      ← 全是手打的
```

📌 **懂行的人只认第二种。**

⚠️ **`?branch=feat/test-infra` 不能漏**：不加则查默认分支 main，而 main 上没有 `ci.yml` → 显示灰色 `no status`。

📌 **「显示了但显示错了」比「不显示」更糟** —— 你会以为是缓存或网络问题，去查一堆无关的东西。

---

## 九、⭐ 分层验证：为什么两个 job 不是重复

| | `unit` | `integration` |
|---|---|---|
| 装法 | `pip install -e .` 解 `pyproject.toml` | `requirements-test.txt` + `--no-deps` |
| 验证 | ✅ **依赖声明完整性** | ✅ **镜像可复现性** |
| 版本策略 | 范围（装到 mujoco 3.11.0） | 钉死（3.10.0） |
| 贴近 | 「新人 clone 能不能跑」 | 「生产环境部署」 |

📌 **缺陷 L′ 只有 `unit` 能抓到** —— 镜像的 `--no-deps` 恰好绕过了 `pyproject.toml`，**所以镜像绿了、真 bug 还在**。

**而四处跑出同一个数字**（本机/容器/CI unit/CI integration），且**两条路径用了不同的 mujoco 版本** —— 这比单条路径绿有说服力得多。

---

## 十、可迁移的经验

### 10.1 排查 CI 问题的顺序

1. ⭐ **先核对 commit 哈希**（`git log -1 --format=%H`）—— 确认在看哪次 run
2. **从上往下读日志**，找第一个异常，别只看最后一行
3. **traceback 从下往上读**，最下面是真因
4. 本地能验的先本地验（YAML 语法、lint、测试），**省一次往返**

⚠️ **第 1 条是本阶段的血泪**：GitHub Actions 页面不自动刷新，**一次失败的日志会一直挂在那儿，看起来和新的一模一样**。差点据此去改一个已经修好的东西。

### 10.2 加 job 的节奏

📌 **每次只加一个 job，绿了再加下一个。**

CI 反馈慢（本地 3 秒 vs CI 几分钟）。一口气写 5 个 job 全红，**不知道从哪查**。

**必加 `workflow_dispatch`** —— 否则每改一行 YAML 就得 push 一次。

### 10.3 「一次只改一件事」的三次应用

| 场景 | 决定 |
|---|---|
| Node 20 弃用警告 | **不升 action 版本** —— 正在加 job，红了分不清谁的锅 |
| `discoverse/` 277 个 lint 错误 | **不改** —— 与「补测试」目标无关 |
| `__init__.py` 转义序列警告 | **不改** —— 在上游代码里 |

**三次都记进了欠账清单，不是忘了。**

---

## 十一、「声明了但行为不符，且失败时静默」——第 N 次

| 案例 | 声明 | 实际 |
|---|---|---|
| `MUJOCO_GL=glfw` | 有渲染后端 | 无头环境不可用 |
| 4 个未声明依赖 | 核心依赖完整 | 干净环境崩 |
| `.dockerignore` 挡 MJCF | 要测 | pytest.skip 兜住 |
| `recoder_single_arm` | 有产物 | 0 字节坏文件 |
| **`tests/kinematics` 空目录** | **要测** | **5 passed 假绿灯** |
| **两组重复测试函数** | **要测** | **前者从未执行** |
| **`.gitattributes` 声明 LFS** | **走 LFS** | **实际没走**（本次无害） |

⚠️ **最后两条是自己写的代码。**

📌 **该模式与「谁写的」无关，与「有没有工具去查」有关。** 这个认识比抓到任何单个 bug 都重要。

---

## 十二、面试可用的三段

### 12.1 被问「你搭过 CI 吗」

> 「搭的时候第一次就红了 —— 干净 runner 上 `pip install -e .` 之后 import 直接崩，因为有 4 个包被 eager import 链拽进来却没写进核心依赖。
>
> 这问题我几天前在 Docker 镜像里撞过一次，但当时用 `--no-deps` 绕过去了，**所以镜像绿了、真 bug 还在**。**CI 是第一个不给我绕过去机会的环境。**」

### 12.2 被问「unit 和 integration 不是重复吗」

> 「不是。`unit` 用 `pip install -e .` 解 `pyproject.toml`，验的是**依赖声明完整性**；`integration` 用钉死版本 + `--no-deps`，验的是**镜像可复现性**。
>
> 缺陷 L′ 只有前者能抓到，因为镜像的 `--no-deps` 恰好跳过了依赖解析。**两者各补对方的盲区。**」

### 12.3 被问「代码规范怎么管的」

> 「我把 lint 范围刻意收窄到 `tests/`——`discoverse/` 有 277 个 ruff 错误，那是上游代码，一次性重排会制造巨大 diff 且和补测试这个目标无关。
>
> 我用 `continue-on-error` 把这笔债做成**每次 CI 都可见的报告**，而不是假装没看见。」

📌 **第三段最值钱** —— 它展示的是判断力：知道什么不该做，以及怎么让「不做」保持可追踪。

---

## 十三、一句话

**`ci.yml` 只有 183 行，10 分钟能写完 —— 但它调用的每一样东西都是前 9 天挣出来的。**

**而它第一次运行就抓到了一个本机和容器都发现不了的真 bug。**
