# Day 2 — pytest 测试骨架搭建

> 上接 [day01-am-architecture.md](day01-am-architecture.md)
> 本课产出：一个能跑、配置正确、fixture 经过自检的测试骨架
> 实际耗时：约 2 小时（其中 40 分钟卡在环境污染）

---

## 先破除一个错误认知

> ❌ 「搭测试骨架就是 `mkdir tests && touch conftest.py`，十分钟的事。」

这是把**创建文件**当成了**建立能力**。骨架的价值不在目录结构，在于：

1. 配置**真的生效了**（而不是被静默忽略）
2. 断言机制**真的会失败**（而不是永远为真）
3. fixture **真的被执行过**（而不是定义了没人用）
4. 环境**真的干净**（而不是碰巧能跑）

这四条每一条都要**主动验证**，而验证的方式是**让它先红一次**。今天一半时间花在这上面。

---

## 本课五步法

| Step | 做什么 | 验收标准 |
|---|---|---|
| 1 | 建目录骨架 | `tests/` 存在，含 `__init__.py` |
| 2 | 写 pytest 配置 | `configfile:` 指向正确文件，**无 WARNING** |
| 3 | **反向验证配置** | 故意写错 marker，**必须报错** |
| 4 | 写 conftest fixture | 每个 fixture 至少被求值一次 |
| 5 | 参数化真实数据 | 9 个机器人配置全覆盖 |

---

## Step 0｜环境准备（本课最大的坑）

### 0.1 不要用 conda activate

```bash
export PY=/home/ubuntu22/miniconda3/envs/discoverse/bin/python
```

**为什么用绝对路径解释器而非 `conda activate`**：

| | `conda activate` | `export PY=/绝对路径` |
|---|---|---|
| 需要 shell 初始化过 conda | 是 | 否 |
| **写进 CI / Dockerfile / cron** | 麻烦 | **直接可用** |

`conda activate` 在非交互式 shell 里默认**不工作**——`~/.bashrc` 的 conda 初始化块通常被 `[ -z "$PS1" ] && return` 挡在外面。Day 8-9 写 Dockerfile、Day 10-11 写 GitHub Actions 时，绝对路径解释器可以直接复用。

**额外好处**：不激活时，一旦哪条命令漏写了 `$PY`，会立刻炸。激活了反而会**掩盖**这类错误——本地跑得好好的，推到 CI 就挂。

### 0.2 清除 ROS 的 PYTHONPATH（关键）

如果你的机器装了 ROS，`~/.bashrc` 里的 `source /opt/ros/humble/setup.bash` 会导出 `PYTHONPATH`。这会让 pytest **启动阶段直接崩溃**：

```
ModuleNotFoundError: No module named 'lark'
```

**根因链**：

```
PYTHONPATH=/opt/ros/humble/lib/python3.10/site-packages
  -> 优先级高于 conda 环境隔离，强行注入 sys.path
  -> pytest 启动时 load_setuptools_entrypoints("pytest11")
     扫描并加载路径上所有已注册插件
  -> 发现 ROS 的 launch_testing
  -> import launch -> import lark（conda 环境没装）
  -> 崩
```

**关键认知**：conda 环境隔离的是 `site-packages`，但**挡不住 `PYTHONPATH`**。而 pytest 让问题更严重——普通脚本只有 `import` 到才会炸，pytest 会**主动扫描并加载**路径上的每一个插件，不管你用不用。

### 0.3 固化成 env.sh

第一版直接硬编码 `export PY=/home/ubuntu22/miniconda3/...` 能用，但**推到公开仓库后别人 clone 下来立刻失效**，也进不了 Docker/CI。改成探测式：

```bash
mkdir -p scripts/dev
cat > scripts/dev/env.sh <<'SHEOF'
# 用法: source scripts/dev/env.sh

# ---- Python 解释器：按优先级探测，不硬编码 ----
#   1. 调用者已设的 $PY        —— 显式覆盖优先（CI 会用到）
#   2. conda 环境 discoverse   —— 本项目约定
#   3. 当前激活的 conda 环境
#   4. PATH 上的 python3
if [ -z "$PY" ]; then
    for _cand in \
        "$HOME/miniconda3/envs/discoverse/bin/python" \
        "$HOME/anaconda3/envs/discoverse/bin/python" \
        "$CONDA_PREFIX/bin/python" \
        "$(command -v python3)"
    do
        [ -x "$_cand" ] && { export PY="$_cand"; break; }
    done
    unset _cand
fi
[ -z "$PY" ] && { echo "[env] 错误: 未找到 Python" >&2; return 1; }

export MUJOCO_GL=osmesa
[ -n "$PYTHONPATH" ] && unset PYTHONPATH

echo "[env] PY=$PY"
echo "[env] MUJOCO_GL=$MUJOCO_GL"
echo "[env] PYTHONPATH cleared (ROS decoupled)"
SHEOF

source scripts/dev/env.sh
```

**预期**：三行 `[env]` 回显。

**必须在模拟的全新环境里验证探测逻辑** —— 否则现有的 `$PY` 会让你误以为它工作正常：

```bash
env -u PY -u PYTHONPATH bash -c 'source scripts/dev/env.sh && $PY -m pytest tests/ -q 2>&1 | tail -2'
```

`env -u X` = 「在删掉变量 X 的环境里执行」。这和用 `( export ...; ... )` 做反向验证是同一个思路：**构造受控环境，看代码在里面的真实表现。**

再验证显式覆盖仍然优先（Day 10-11 的 CI 会自带 Python）：

```bash
PY=/usr/bin/python3 bash -c 'source scripts/dev/env.sh 2>&1 | head -1'
# 预期: [env] PY=/usr/bin/python3
```

**一个脚本适配四种环境**，靠的是「探测」而非「假设」：

| 场景 | `$PY` 解析到 |
|---|---|
| 你的机器 | `~/miniconda3/envs/discoverse/bin/python` |
| 同事（anaconda） | `~/anaconda3/envs/discoverse/bin/python` |
| Docker（无 conda） | `/usr/local/bin/python3` |
| GitHub Actions | runner 的 `python3` |

> **为什么不用 `-p no:launch_testing` 打补丁**：`-p no:` 要求插件**先被成功导入**才能禁用。ROS 那堆插件只要有一个在导入期就炸，`-p no:` 根本来不及。**环境隔离必须在更外层做。**

---

## Step 1｜目录骨架

```bash
mkdir -p tests/{unit,kinematics,simulation,mobile_manipulation,data}
touch tests/__init__.py
```

**分层依据**（不是随便分的）：

| 目录 | 依赖 | 典型耗时 | CI 策略 |
|---|---|---|---|
| `unit/` | 无 MuJoCo | 毫秒 | 每次 push |
| `kinematics/` | 加载 MJCF | 百毫秒 | 每次 push |
| `simulation/` | 跑仿真步进 | 秒 | 夜间 |
| `data/` | 文件 IO | 百毫秒 | 每次 push |

---

## Step 2｜pytest 配置

### 2.1 先看有没有现成的

```bash
grep -n -A 20 "\[tool.pytest" pyproject.toml
```

**本项目的发现**：上游**已经写了** `[tool.pytest.ini_options]`，`testpaths = ["tests"]`——但 `tests/` 目录**根本不存在**。

> **这本身就是一条缺陷**：配置声明了，从来没人跑过。**配置写了不代表跑过。**

### 2.2 决策：改上游配置，不要另建 pytest.ini

如果你另建 `pytest.ini`，pytest 会报：

```
configfile: pytest.ini (WARNING: ignoring pytest config in pyproject.toml!)
```

**配置文件优先级**（高→低）：`pytest.ini` > `pyproject.toml` > `tox.ini` > `setup.cfg`

两份配置并存时 pytest **静默丢弃**一份。今天你知道，三个月后改错文件会困惑很久。**唯一真相原则。**

### 2.3 最终配置

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
python_classes = "Test*"
python_functions = "test_*"

markers = [
    "unit: 纯函数/配置层单测，无 MuJoCo 依赖，秒级",
    "integration: 需要加载 MJCF 或跑仿真步进",
    "slow: 单用例 >10s，CI 主线跳过",
    "determinism: 确定性/可复现性专项",
]

addopts = "--strict-markers --tb=short -ra"
timeout = 60
```

**每个参数为什么**：

| 参数 | 作用 | 不加的后果 |
|---|---|---|
| `--strict-markers` | marker 拼错直接报错 | 静默生成新 marker，`-m unit` 筛掉你以为在跑的用例 |
| `--tb=short` | traceback 只留一行源码 | 参数化批量失败时刷屏几百行 |
| `-ra` | 结尾汇总所有非通过用例 | skip/xfail 的原因看不见，**缺失隐形** |
| `timeout = 60` | 单用例超时 | MuJoCo 死循环会挂到 CI 平台上限才被杀 |

### 2.4 TOML vs INI 语法差异（易翻车）

| 项 | `pytest.ini` | `pyproject.toml` |
|---|---|---|
| 段名 | `[pytest]` | `[tool.pytest.ini_options]` |
| 字符串 | 裸写 | **必须引号** |
| 多值列表 | 换行缩进 | **必须真数组 `["a","b"]`** |

```toml
# ❌ TOML 里这样写是语法错误
markers =
    unit: 单元测试

# ✅ 必须是数组
markers = ["unit: 单元测试"]
```

### 2.5 验收

```bash
$PY -m pytest --collect-only
```

**必须看到**：

```
rootdir: /home/ubuntu22/workspaces/airbot-play/DISCOVERSE
configfile: pyproject.toml        <- 没有 WARNING
timeout: 60.0s                    <- 配置生效
collected 0 items
```

---

## Step 3｜反向验证配置真的生效（本课核心）

配置写了不代表生效。**故意制造一次失败**：

```bash
mkdir -p tests/unit
cat > tests/unit/test_smoke.py <<'EOF'
import pytest

@pytest.mark.unit
def test_framework_alive():
    assert 1 + 1 == 2

@pytest.mark.typo_marker_should_fail
def test_strict_markers_works():
    assert True
EOF

$PY -m pytest tests/unit/test_smoke.py
```

**预期是报错**：

```
collected 0 items / 1 error
ERROR tests/unit/test_smoke.py - Failed:
  'typo_marker_should_fail' not found in `markers` configuration option
Interrupted: 1 error during collection
```

### 从这个错误里读出的东西

注意 `collected 0 items` —— 好好的 `test_framework_alive` **也被连坐了**。

pytest 有两个阶段：

| 阶段 | 干什么 | 出错的后果 |
|---|---|---|
| **collection** | 导入模块、解析 marker、展开 parametrize | **整个文件的用例一个都不跑** |
| **execution** | 逐个执行用例 | 只有那一个用例失败 |

**这个区别在 CI 里非常要命**：一个 import 错误能让整个文件 200 个用例集体消失，而 CI 摘要只显示 "1 error"——**看起来比 "200 failed" 轻微得多，实际严重得多**。

> **看 CI 报告时，`collected N items` 的 N 比 pass/fail 更早暴露问题。**

### 改回正确版本

```bash
cat > tests/unit/test_smoke.py <<'EOF'
import pytest


@pytest.mark.unit
def test_framework_alive():
    assert 1 + 1 == 2


@pytest.mark.unit
def test_no_ros_pollution_in_syspath():
    """测试环境不应混入 ROS 的 site-packages。"""
    import sys

    ros_paths = [p for p in sys.path if "/opt/ros/" in p]
    assert not ros_paths, (
        f"ROS 路径混入 sys.path: {ros_paths}\n"
        f"修复: source scripts/dev/env.sh"
    )
EOF

$PY -m pytest tests/unit/test_smoke.py -v
```

**预期**：`2 passed`

第二条测试把「怎么正确配置环境」这个知识，从脑子里搬进了**可执行、会自动运行、失败时自带修复指引**的地方。

### 顺便验证 marker 筛选

```bash
$PY -m pytest tests/unit -m unit -q          # 预期 2 passed
$PY -m pytest tests/unit -m "not unit" -q    # 预期 2 deselected
```

---

## Step 4｜conftest.py 与 fixture 作用域

### 4.1 conftest.py 是什么

pytest 的**隐式插件文件**：同目录及所有子目录的测试自动可见这里定义的 fixture，**无需 import**。

### 4.2 作用域选择（本日最重要的知识点）

```python
@pytest.fixture(scope="session")
def mj_model_factory():
    """MjModel 工厂 + 会话级缓存。

    为什么 session 级：
      MjModel.from_xml_path 要解析 XML、加载 mesh、编译碰撞几何，
      单次数百 ms。它是 *只读* 的编译产物，跨用例复用安全。

    为什么返回工厂函数而不是模型本身：
      不同用例要加载不同 XML。fixture 直接返回模型的话，
      一个 fixture 只能绑一个 XML。返回工厂 + 内部 dict 缓存，
      既能按需加载任意 XML，又保证同一 XML 只编译一次。
      这是 "factory as fixture" 模式。
    """
    import mujoco

    cache = {}

    def _make(xml_path):
        key = str(xml_path)
        if key not in cache:
            if not os.path.exists(key):
                pytest.skip(f"MJCF 不存在，跳过: {key}")
            cache[key] = mujoco.MjModel.from_xml_path(key)
        return cache[key]

    return _make


@pytest.fixture(scope="function")
def mj_data_factory(mj_model_factory):
    """MjData 工厂，function 级。

    为什么必须 function 级：
      MjData 持有 qpos/qvel/ctrl/time 等 *可变* 状态。
      跨用例复用的话，用例 A 步进 1000 步后的状态会泄漏给用例 B，
      造成 "单跑绿、全跑红" 的经典测试间污染 —— 顺序一变就复现不了。
      MjData 构造很便宜，没有复用的必要。
    """
    import mujoco

    def _make(xml_path):
        model = mj_model_factory(xml_path)
        return model, mujoco.MjData(model)

    return _make
```

**作用域的二维判断**：

```
              可变？
              否              是
        贵？是│ session ✅   │ 两难(需深拷贝) │
           否 │ 随便         │ function ✅    │
```

**默认 function**，只在证明「既贵又不可变」后才放宽。

> **代价不对称**：作用域选窄只是慢；**选宽是测试间污染**——单跑绿、全跑红、换顺序不复现，最难查的一类 flake。

### 4.3 fixture 必须被求值一次

fixture 是**懒加载**的：没有用例请求它就永不执行。定义了没人用 = 没验证。

```python
@pytest.mark.integration
def test_mj_data_factory_isolates_state(mj_data_factory, repo_root):
    """验证 function 级作用域真的隔离了状态。"""
    xml = repo_root / "models" / "mjcf" / "manipulator" / "robot_airbot_play.xml"
    model_a, data_a = mj_data_factory(xml)
    model_b, data_b = mj_data_factory(xml)

    assert model_a is model_b, "model 应复用（只读）"
    assert data_a is not data_b, "data 必须独立（可变）"

    data_a.qpos[0] = 0.5
    assert data_b.qpos[0] != 0.5
```

### 4.4 验收

```bash
$PY -m pytest tests/unit -v
```

**预期**：`7 passed in 0.27s`

注意耗时从 `0.01s` 涨到 `0.27s`——**那 0.26 秒就是 MuJoCo 编译 XML 的开销**。这是 `session` 作用域的实测依据：换成 function 级，每个用到模型的用例都要付这 0.26s。二三十个用例时就是 0.26s vs 8s 的差别。

---

## Step 5｜参数化真实配置（9 种机械臂）

### 5.1 先侦查，不要照抄文档的字段名

**这一步的规矩：断言必须建立在实测事实上，不是文档描述上。**

```bash
$PY - <<'PYEOF'
import yaml
c = yaml.safe_load(open('discoverse/configs/robots/airbot_play.yaml'))
for k, v in c['kinematics'].items():
    print(f"  {k:24s} {type(v).__name__:6s} {str(v)[:70]}")
PYEOF
```

**实测结果**（和直觉相反）：

```
arm_joints          int    6                    ← YAML 里是整数
arm_joint_names     list   ['joint1', ...]      ← 这才是列表
```

而 `robot_config.py` 的属性：

| 属性名 | 返回的 YAML 键 | 类型 |
|---|---|---|
| `arm_joints` | `arm_joint_names` | **list** |
| `arm_joints_count` | `arm_joints` | **int** |

**交叉错位了**（缺陷 E）。源码自身是自洽的（类型注解 `List[str]` 和 docstring 都正确），问题在**跨层命名冲突诱导误用** —— 计划文档里 `len(loader.arm_joints) > 0` 就是被它骗的。

**严重度定「中，可维护性」而非功能缺陷。** 缺陷报告里把「命名不一致」写成「功能 bug」，是失去信誉最快的方式。

### 5.2 横向验证假设（关键步骤）

想写这条断言：

```python
assert ctrl_dim == arm_joints + gripper.ctrl_dim
```

`airbot_play` 是 `7 == 6+1` 成立。**但只验 1 个样本就推广到 9 个是没根据的。**

横向扫完：**9/9 成立**（覆盖 6+1=7 和 7+1=8 两种），才敢写。

### 5.3 和 MJCF 对账（本课最有价值的一步）

YAML 是**人写的描述**，MJCF 编译结果是**物理引擎的事实**。不一致时 MJCF 是真相。

```bash
$PY - <<'PYEOF'
import mujoco, yaml, glob, os
print(f"{'robot':14s} {'qpos_dim':>9s} {'nq':>5s} {'ctrl_dim':>9s} {'nu':>5s}   verdict")
print("-" * 62)
for f in sorted(glob.glob('discoverse/configs/robots/*.yaml')):
    name = os.path.basename(f)[:-5]
    k = yaml.safe_load(open(f))['kinematics']
    m = mujoco.MjModel.from_xml_path(f"models/mjcf/manipulator/robot_{name}.xml")
    v = []
    if m.nq != k['qpos_dim']: v.append("QPOS 不符")
    if m.nu != k['ctrl_dim']: v.append("CTRL 不符")
    print(f"{name:14s} {k['qpos_dim']:9d} {m.nq:5d} {k['ctrl_dim']:9d} {m.nu:5d}   "
          f"{' + '.join(v) if v else 'OK'}")
PYEOF
```

**实测结果：`ctrl_dim` 9/9 全对，`qpos_dim` 4/9 不符**（arx_x5、iiwa14、piper、rm65）→ 缺陷 H。

#### 这个分布本身是最有价值的信息

| 字段 | 写错的后果 | 正确率 |
|---|---|---|
| `ctrl_dim` | `data.ctrl[:] = 长度不符数组` → **立刻 ValueError** | **9/9** |
| `qpos_dim` | `qpos[:9]` 在 `nq=15` 上**合法**，静默丢掉后 6 个 | **4/9 错** |

**会炸的字段维护得好，不会炸的字段积累错误。** 这不是本项目的特殊问题，是软件工程的普遍规律 —— **而这个规律本身就是找 bug 的地图**。

进新项目时优先怀疑：数组长度/切片边界、可选配置字段、日志内容、数值单位。

#### MuJoCo 的 nq 和 nu 是什么

| | 含义 | 对应 YAML | 对应 data |
|---|---|---|---|
| `nq` | 位置状态有几个数 | `qpos_dim` | `data.qpos` |
| `nu` | 能下几个控制指令 | `ctrl_dim` | `data.ctrl` |

**`nq` 常大于 `nu`**：夹爪只有 1 个控制量（「张开 0.04 米」），但物理上两个手指各占 1 个 qpos。两指被机械约束绑定，所以 1 个指令驱动 2 个自由度。

这解释了 `gripper.type` 的差异：`two_finger_tendon`/`equality` 占 2 个 qpos，`two_finger_single`（只建模一个可动指）占 1 个，`multi_finger` 占更多。

### 5.4 写测试

完整文件见 [tests/unit/test_robot_config.py](../../tests/unit/test_robot_config.py)。三层结构：

| 层 | marker | 内容 |
|---|---|---|
| 1 | `unit` | 配置自身的字段完整性与自洽性（不加载 MuJoCo） |
| 2 | `integration` | 配置 vs MJCF 对账（需编译 XML） |
| 3 | `unit` | 已知缺陷的 xfail 记录 |

**验收**：`61 passed, 4 xfailed`

### 5.5 参数化 vs 循环（本步核心收益）

```python
# ❌ 循环：第一个失败就停，看不到分布
def test_all():
    for robot in ROBOTS:
        assert check(robot)

# ✅ 参数化：9 个独立用例
@pytest.mark.parametrize("robot_name", ROBOTS)
def test_one(robot_name):
    assert check(robot_name)
```

**「能看到分布」是关键能力。** `qpos_dim` 跑出「5 通过 4 失败」，才能判断「是那 4 个配置错了」而非「我的公式错了」。

> **样本量就是判断力**：9 个样本 5 对 4 错 → 能定位缺陷。2 个样本 1 对 1 错 → **无法判断谁错**。这也是先测 9 种机械臂而非 2 种双臂机器人的核心理由。

---

## Step 6｜任务配置层（5 个任务）

### 6.1 侦查发现了继承机制

直接读 5 个任务 YAML，看到 4 个缺 `observation`。**差一点就直接写断言了。**

但注意到三个任务有 `extends`：

```yaml
# place_block.yaml
extends: templates/place_object.yaml
```

**`extends` 是 YAML 版的类继承** —— 加载时会合并模板内容（子覆盖父），然后丢弃 `extends` 键本身。类比 Docker 的 `FROM`、CSS 的 `@extend`。

**所以看到的是原始 YAML，不是合并后的最终配置。** 必须三步验证：

| 步骤 | 命令 | 结果 |
|---|---|---|
| 模板里有什么 | 读 `templates/place_object.yaml` | **observation 是 None** |
| 代码处理 extends 吗 | `grep -rn "extends" discoverse/` | ✅ `config_utils.py:17` |
| 加载后实际如何 | 用 `TaskConfigLoader` 加载 | 打印「📄 加载模板」，确实合并 |

**结论：extends 正常工作，但模板本身缺字段。**

### 6.2 为什么这个区分至关重要

| 假想的根因 | 修复方式 |
|---|---|
| 4 个任务各自漏写 | 改 4 个 YAML |
| **模板缺字段 + 1 处漏写** | **改 2 个文件**（1 个模板修好 3 个任务） |

**报错根因的缺陷报告，比不报更糟。** 按第一种去修，开发会给 3 个子任务各自补一遍，重复配置，下次新增任务还会再缺。

> **这是「静态分析会骗人」的第三次现身** —— 静态读文件和运行时加载，看到的是两个不同的东西。

### 6.3 撞上「5 个测试全红」

写完跑，5 个测试全挂同一个错：

```
ValueError: Missing required field in task config: description
```

**判断「代码错」还是「测试错」的三条依据**：

| 线索 | 指向 |
|---|---|
| 5 个失败**全在同一处**（构造阶段，一行断言未执行） | 系统性问题 |
| 报的是 `Missing required field` | **设计好的校验正常工作** |
| 真实的 5 个 YAML 都有 `description` | **测试数据不真实** |

**结论：改测试，不改代码。**

**但不要猜着改** —— 先查清完整清单：

```bash
$PY -c "
import inspect
from discoverse.universal_manipulation.task_config import TaskConfigLoader
print(inspect.getsource(TaskConfigLoader._validate_config))
"
```

（`inspect.getsource` 比 `sed -n` 好：不用猜行号。）

清单比预想的多：`task_name` + `description` + `states`（非空 list，每个 state 需 `name` 和 `primitive`）。**只补 `description` 会再红一次。**

**副产品：清单里没有 `observation`** → 缺陷 I，而它正是缺陷 B 能存在的直接原因。**「有验证」≠「验证够」。**

### 6.4 三个缺陷的钉法

**缺陷 B**（`camera_configs` 为空 → 采集零张图像）：

```python
if task_name in MISSING_OBSERVATION:
    pytest.xfail(f"缺陷 B：{task_name} 的 camera_configs 为空")
```

**缺陷 C**（`record_fps` 双层默认值 + null 崩溃）：

```python
return self.config.get('observation', {'fps': 30}).get('fps', 30)
#                                     ↑第一层        ↑第二层
```

**`.get(k, default)` 的陷阱**：只在**键不存在**时用默认值。键存在但值为 `None` 时返回 `None`，随后 `None.get()` 炸。而 YAML 里 `observation:` 后面留空就产生 `None` —— **很容易写出的形态**。

**缺陷 I**（校验漏字段）用装饰器 + `strict=True`：

```python
@pytest.mark.xfail(strict=True, reason="缺陷 I：...")
def test_validate_config_should_require_observation():
    with pytest.raises(ValueError):
        TaskConfigLoader.from_dict(_minimal_config())
```

**验收**：`21 passed, 4 skipped, 5 xfailed`

### 6.5 xfail vs skip 不要混用

| | 含义 | 用在哪 |
|---|---|---|
| **xfail** | 「断言**应该**成立，但因已知缺陷不成立」 | 记录缺陷 |
| **skip** | 「断言的**前提**不满足，无法判断」 | 环境缺失、数据不存在 |

同一个 `place_block`：
- `test_camera_configs_nonempty` → 应该有相机但没有 → **xfail**
- `test_camera_config_fields_wellformed` → 一个相机都没有，无从检查字段 → **skip**

**skip 会掩盖缺陷，xfail 会记录缺陷。**

### 6.6 `strict=True` 的作用

| 写法 | 缺陷修复后 |
|---|---|
| `pytest.xfail("...")` 函数调用 | 执行到就跳过，**永不 XPASS** |
| `@pytest.mark.xfail(strict=True)` | 断言真的执行；通过了 → **XPASS 报为失败** |

**`strict=True` 强制有人在缺陷修复后回来撤销标记。** 不加的话标记会永远留着，**假装缺陷还存在**。

**什么时候用哪个**：参数化中只有部分参数要 xfail → 用函数调用式（装饰器会作用于全部）；整个测试是「期望行为」的记录 → 用装饰器 + strict。

---

## Step 7｜覆盖率基线

```bash
$PY -m pytest tests/ --cov --cov-report=term-missing -q
```

**作用域必须限定**（已写进 `pyproject.toml`）：

```toml
[tool.coverage.run]
source = ["discoverse/universal_manipulation"]
```

**不要写 `--cov=discoverse`** —— `policies/` 下 237 个文件会把分母稀释到 2-3%。**指标的作用域必须和工作范围一致，否则指标本身就是噪声。**

**实测基线**：

```
randomization.py    300 语句   9%    ← Day 3-4 主战场
task_base.py        160 语句  16%    ← 含最高优先线索
robot_config.py      77 语句  86%    ← 今天测的
config_utils.py      48 语句  98%
TOTAL               961 语句  30%    ← 从 ~5% 起步
```

### 覆盖率是下限指标，不是质量证明

```python
def test_divide():
    assert divide(6, 2) == 3      # 覆盖率 100%，但 b=0 完全没测
```

反过来，`record_fps` 只有 **1 行代码**，我写了 **4 个测试**（正常值/无键/空dict/null崩溃）。覆盖率只算 1 行，但验证了 4 条路径。

**低覆盖率一定有问题，高覆盖率不保证质量。** 看 `Missing` 那列找盲区，不要盯总百分比。

---

## Step 8｜清理与提交

```bash
touch tests/unit/__init__.py     # git 只跟踪文件不跟踪目录；也避免同名测试文件导入冲突
```

**加 `.gitignore` 规则前先 grep** —— 我这一步犯了错，追加了三条上游已有的规则，靠 `git diff --cached` 才抓住。**diff 审查是最后一道防线。**

**分两个 commit**：

| commit | 内容 | 为什么分开 |
|---|---|---|
| `ce88e8d` | 骨架（配置 + conftest + env.sh） | 「测试框架怎么搭的」 |
| `cc3fc02` | 测试用例（549 行） | 「谁写了这些断言」 |

**commit message 是缺陷报告的第一稿。** Day 6-7 写 `defect-report.md` 时，`git log` 里已有全部素材：精确数字、根因、影响范围。

---

## 本课要带走的方法论（换项目照用）

1. **新写的断言必须亲手让它红一次。** 永远为真的断言等于没写。
2. **配置写了不代表生效。** 看 `configfile:` 行，看有没有 WARNING。
3. **`collected N items` 的 N 比 pass/fail 更早暴露问题。**
4. **fixture 作用域默认 function**，只在证明「既贵又不可变」后才放宽。
5. **环境隔离在最外层做**，不要用框架参数打补丁。
6. **写完文件用 `wc -l && tail -3` 验证**，不要看终端回显。
7. **断言前先横向验证假设。** 1 个样本成立不能推广到 9 个。
8. **找独立的第二信源。** 配置说什么不算，引擎编译出什么才算。
9. **参数化而非循环** —— 才能看到「9 个里 4 个错」这样的分布。
10. **测试红了先判断是「代码错」还是「测试错」**：失败位置是否集中、错误类型是否是设计好的行为、测试数据是否真实。
11. **静态读文件 ≠ 运行时加载。** 有继承/合并机制时必须用加载器验证。
12. **「写错也不会炸」的字段，bug 密度最高。**
13. **影响产出正确性的配置，缺失必须报错**；只影响行为偏好的才可以有默认值。
14. **覆盖率是下限指标**，看 Missing 列找盲区。

---

## 今日验收清单

- [ ] `source scripts/dev/env.sh` 三行回显正常
- [ ] `$PY -m pytest --collect-only` 显示 `configfile: pyproject.toml` 且无 WARNING
- [ ] 故意写错 marker 能报错（反向验证）
- [ ] `$PY -m pytest tests/ -q` → **90 passed, 4 skipped, 9 xfailed**
- [ ] 覆盖率 **30%**，且能说清为什么不用 `--cov=discoverse`
- [ ] `-m unit` / `-m integration` 筛选正确，耗时有明显差异
- [ ] 能说清 `mj_model_factory` 用 session、`mj_data_factory` 用 function 的理由
- [ ] 能说清 xfail 和 skip 的区别，以及 `strict=True` 的作用
- [ ] 能说清缺陷 B 的根因为什么是「模板缺字段」而非「4 个任务漏写」

---

## 下次预告：Day 3-4 确定性攻坚

**第一件事**：查 [task_base.py:149-167](../../discoverse/universal_manipulation/task_base.py#L149)。覆盖率报告确认这段代码**从未被任何测试执行过**，而那里有 `except` 吞异常的可疑写法。

**若吞异常后返回 `True`，则任何条件检查出错都判定为成功** —— 这直接解释 Day 1 那条「完成状态 10/10 但实际距离 0.2908m」。可能是整个项目最严重的缺陷。

**主线目标**：`randomization.py` 300 语句只覆盖 9%，有 20+ 处裸 `np.random.*` 从未被 seed，`settings.seed: null` 是死配置。用 TDD 红→绿的方式让「同种子 → 同结果」成立。
