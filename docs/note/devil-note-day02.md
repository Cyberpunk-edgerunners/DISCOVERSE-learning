# Devil Note · Day 2 — pytest 骨架的知识拆解

> 配套：[tutorial/day02-pytest-infra.md](tutorial/day02-pytest-infra.md)（步骤）｜[devil-log-day02.md](devil-log-day02.md)（过程实录）
> 本篇只讲**知识点**，不讲步骤。

---

## 一、环境隔离的三层模型

今天 40 分钟卡在 `ModuleNotFoundError: No module named 'lark'`。根因不是缺包，是**隔离层级搞错了**。

Python 的环境隔离有三层，**优先级从高到低**：

| 层 | 机制 | 谁能覆盖它 |
|---|---|---|
| 1 | `PYTHONPATH` 环境变量 | 只有 `unset` |
| 2 | conda / venv 的 `site-packages` | 被第 1 层压制 |
| 3 | 系统 Python 的 `site-packages` | 被前两层压制 |

**关键认知**：conda 环境隔离的是**第 2 层**，但 ROS 的 `setup.bash` 动的是**第 1 层**。第 1 层永远赢。

```bash
# 验证：conda 环境里也能看到 ROS 的路径
$PY -c "import sys; print([p for p in sys.path if 'ros' in p])"
```

### 为什么 pytest 让问题更严重

普通脚本：只有 `import launch_testing` 才会炸。
pytest：**启动时主动扫描并加载路径上所有已注册插件**，不管你用不用。

```
_pytest/config/__init__.py:1583
    self.pluginmanager.load_setuptools_entrypoints("pytest11")
```

`pytest11` 是 setuptools 的 entry point 组名。任何包只要在 `setup.py` 里声明了 `entry_points={"pytest11": [...]}`，pytest 就会自动加载它。ROS 的 `launch_testing` 恰好声明了。

**这解释了一个反直觉现象**：你的测试代码一行都没写，pytest 就崩了。

### 三种修复方案的对比

| 方案 | 做法 | 评价 |
|---|---|---|
| A | `-p no:launch_testing` | ❌ 要求插件**先被成功导入**才能禁用。导入期就炸的话来不及 |
| B | `unset PYTHONPATH` | ✅ **在最外层解决**，与 CI/Docker 环境一致 |
| C | `pip install lark` | ❌ 「喂饱错误」而非「消除错误」。下次 ROS 换个插件还会炸 |

**通用原则：环境问题在环境层解决，不要用框架参数打补丁。**

### 同一根因的第二种表现

反向验证时（故意设回 `PYTHONPATH`）撞出了完全不同的错误：

```
PluginValidationError: unknown hook 'pytest_launch_collect_makemodule'
in plugin launch_testing_ros_pytest_entrypoint
-> INTERNALERROR
```

`lark` 和 `PluginValidationError` 长得毫无关系，根因都是 `PYTHONPATH`。

> **错误信息也会骗人。** 排查时不要被表象牵着走——这是 Day 1「静态分析会骗人」的延伸。

---

## 二、pytest 的两个阶段：collection vs execution

这是今天第二个重要认知。

| 阶段 | 干什么 | 一个错误的影响范围 |
|---|---|---|
| **collection** | 导入模块、解析 marker、展开 parametrize | **整个文件的所有用例** |
| **execution** | 逐个执行用例 | 仅该用例 |

实测：一个 marker 拼写错误，让文件里另一个完全正常的测试也没跑：

```
collected 0 items / 1 error          <- 不是 1 items
Interrupted: 1 error during collection
```

### 为什么这在 CI 里危险

| CI 摘要显示 | 直觉严重度 | 实际严重度 |
|---|---|---|
| `200 failed` | 高 | 高 |
| `1 error` | **低** | **可能更高**（200 个用例集体消失） |

**看 CI 报告的顺序应该是**：

1. `collected N items` 的 N —— 和上次比有没有骤降？
2. errors —— 有没有 collection 失败？
3. failed —— 最后才看这个

### 第三类失败：INTERNALERROR

比 collection error 更靠前的一种失败——**pytest 框架自身崩溃**。

| | 退出码 | 生成报告文件？ |
|---|---|---|
| 全部通过 | 0 | 是 |
| 有测试失败 | 1 | 是 |
| **INTERNALERROR** | **3** | **否**（junit-xml / json-report / coverage 全无） |

**Day 10-11 的坑预警**：如果 CI 脚本这样写——

```yaml
# ❌ 危险
- run: pytest --junitxml=report.xml || true
- run: python check_report.py report.xml   # 报告不存在 -> 可能判定为"没有失败"
```

`INTERNALERROR` 时 `report.xml` 根本不生成，检查脚本可能把它当成"没有失败"而放行。

**正确做法：CI 判定必须基于退出码，不能基于报告内容。**

---

## 三、fixture 作用域：一个二维决策

### 决策矩阵

```
                    对象是否可变？
                    不可变          可变
   构造  贵    │  session ✅    │  两难，需深拷贝  │
   成本  便宜  │  随便          │  function ✅     │
```

MuJoCo 的两个对象正好落在对角线上：

| 对象 | 构造成本 | 可变？ | 作用域 |
|---|---|---|---|
| `MjModel` | 贵（解析 XML + 编译几何，~260ms） | 否（只读编译产物） | **session** |
| `MjData` | 便宜（只分配数组） | **是**（qpos/qvel/ctrl/time） | **function** |

### 代价不对称——这是决策的关键

| 选错方向 | 后果 | 可发现性 |
|---|---|---|
| 该 session 选了 function | 慢 | 高（跑一次就知道） |
| **该 function 选了 session** | **测试间状态污染** | **极低** |

状态污染的典型症状：

- 单独跑 `test_b` → 绿
- 跑整个文件 → `test_b` 红
- 换个顺序 → 又绿了
- CI 上偶发失败，本地永远复现不了

**这是最难查的一类 flake。** 所以：**默认 function，只在证明「既贵又不可变」后才放宽。**

### factory as fixture 模式

**问题**：不同用例要加载不同的 XML，但 fixture 是「一个 fixture 一个值」。

**错误做法**：

```python
@pytest.fixture(scope="session")
def airbot_model():
    return mujoco.MjModel.from_xml_path("...robot_airbot_play.xml")

@pytest.fixture(scope="session")
def panda_model():   # 9 个机器人要写 9 个 fixture
    return mujoco.MjModel.from_xml_path("...robot_panda.xml")
```

**正确做法**——fixture 返回一个**函数**：

```python
@pytest.fixture(scope="session")
def mj_model_factory():
    cache = {}
    def _make(xml_path):
        key = str(xml_path)
        if key not in cache:
            cache[key] = mujoco.MjModel.from_xml_path(key)
        return cache[key]
    return _make
```

**同时拿到三个好处**：

1. 一个 fixture 服务任意数量的 XML
2. `cache` 闭包变量随 session 作用域存活 → 同一 XML 只编译一次
3. 用例里显式写出加载哪个 XML，可读性更好

**验证缓存真的生效**：

```python
m1 = mj_model_factory(xml)
m2 = mj_model_factory(xml)
assert m1 is m2      # 用 is 而非 ==，比的是对象身份
```

### fixture 是懒加载的

**没有用例请求它，它永不执行。** 所以 conftest 里写错的 fixture 可以潜伏很久，直到某个真实用例第一次用到它才暴露。

**对策**：写一个 `test_conftest_fixtures.py`，让每个 fixture 至少被求值一次。

---

## 四、配置文件的「唯一真相」原则

### pytest 配置文件优先级

高 → 低：`pytest.ini` > `pyproject.toml [tool.pytest.ini_options]` > `tox.ini` > `setup.cfg`

**发现有两份时 pytest 会警告**：

```
configfile: pytest.ini (WARNING: ignoring pytest config in pyproject.toml!)
```

> 这个警告本身是好设计——pytest 没有静默做选择，而是明确告诉你「有两份，我用了这份，扔了那份」。**又一次「不让缺失隐形」。** 很多工具遇到这种情况一声不吭。

### TOML vs INI 语法差异（跨格式迁移必查）

| 项 | `pytest.ini`（INI） | `pyproject.toml`（TOML） |
|---|---|---|
| 段名 | `[pytest]` | `[tool.pytest.ini_options]` |
| 字符串 | `addopts = --strict-markers` | `addopts = "--strict-markers"` |
| 多值 | 换行缩进（隐式列表） | `["a", "b"]`（**真数组**） |
| 数字 | `timeout = 60`（实为字符串） | `timeout = 60`（真整数） |
| 注释 | `#` 或 `;` | 只有 `#` |

**最常踩的坑**——把 INI 的多行 markers 直接搬进 TOML：

```toml
# ❌ TOML 语法错误
markers =
    unit: 单元测试
    slow: 慢速测试

# ✅
markers = ["unit: 单元测试", "slow: 慢速测试"]
```

> **跨格式迁移配置时，整段重写比逐行 sed 更安全。**

---

## 五、四个 addopts 参数的真实价值

```toml
addopts = "--strict-markers --tb=short -ra"
timeout = 60
```

| 参数 | 不加会怎样 | 什么时候救你 |
|---|---|---|
| `--strict-markers` | marker 拼错时 pytest **静默创建新 marker** | 你写 `@pytest.mark.unittest`（多个 test），`-m unit` 筛不到它，这个测试**从此再没跑过**，而 CI 全绿 |
| `--tb=short` | 完整 traceback | 9 个参数化用例同时失败时，刷屏几百行找不到重点 |
| `-ra` | skip/xfail 的原因不显示 | 一个 `pytest.skip("MJCF 不存在")` 静默跳过，你以为跑了 |
| `timeout = 60` | 无超时 | MuJoCo 死循环时，CI 挂到平台上限（通常 6 小时）才被杀 |

**共同点：它们都在对抗「静默」。**

`--strict-markers` 和 Day 1 那条「静态分析能证明没写，不能证明没跑」是同一条线：**系统必须在缺失时发出声音。**

---

## 六、「脆」断言的价值

```python
def test_robot_config_dir_has_nine_yamls(robot_config_dir):
    yamls = sorted(p.stem for p in robot_config_dir.glob("*.yaml"))
    assert len(yamls) == 9, f"预期 9 个，实际 {len(yamls)}: {yamls}"
```

看起来很脆——加个机器人就红了。**这是故意的。**

| 写法 | 新增第 10 个机器人时 | 后果 |
|---|---|---|
| `assert len(yamls) > 0` | 绿 | `ROBOTS` 列表不会更新，**新机器人完全不被测试**，无任何信号 |
| `assert len(yamls) == 9` | 红，信息是「预期 9 实际 10」 | 一分钟内补上列表 |

**用一次可控的、信息明确的失败，换掉一个静默的覆盖漏洞。**

> 💡 **面试可以这么讲**：
> 「我会刻意写一些『脆』的断言，比如配置文件数量必须等于 9。它在新增机器人时必然失败——但这正是目的：失败信息是『预期 9 实际 10』，一秒就知道要去更新参数化列表。如果写成 `> 0`，新机器人会静默地不被任何测试覆盖，而 CI 一片绿。**我宁可要一个吵闹的正确，也不要一个安静的错误。**」

---

## 七、反向验证：让断言先红一次

**一个永远为真的断言等于没写。** 今天做了两次反向验证：

### 验证 1｜`--strict-markers` 真的生效

```python
@pytest.mark.typo_marker_should_fail   # 故意拼错
def test_strict_markers_works():
    assert True
```

预期报错，实际报错 ✅

### 验证 2｜ROS 污染断言真的会红

```bash
(
  export PYTHONPATH=/opt/ros/humble/lib/python3.10/site-packages
  $PY -m pytest tests/unit/test_smoke.py::test_no_ros_pollution_in_syspath -q
)
```

外层 `( )` 让 `export` 只在子 shell 生效，**不污染当前终端**——这是验证环境相关断言的标准手法。

**结果超出预期**：不是 `AssertionError`，而是 `INTERNALERROR`。说明污染发生的位置比预想的还靠前——pytest 连收集阶段都进不去，断言根本没机会执行。

**那这条断言还有用吗？有，但守的是第二道防线**：

| 污染场景 | 结果 | 谁抓到 |
|---|---|---|
| PYTHONPATH 含 ROS，插件能加载 | 崩在启动（lark） | pytest 自己 |
| PYTHONPATH 含 ROS，hook 不兼容 | INTERNALERROR | pytest 自己 |
| **`.pth` / `sitecustomize` / 运行时代码污染 sys.path** | pytest 正常启动 | **你的断言** ✅ |

第三种才是靶区——**不会让 pytest 崩溃、只会让 import 悄悄取到错版本模块**的污染。

> **收获**：原本要验证「断言能变红」，结果验出了一个更早、更严重的失败模式。**反向验证的回报常常超出计划。**

---

## 八、命令行技巧补充

### `cat -A` 查隐藏字符

怀疑文件有尾随空格、CRLF、tab 时：

```bash
cat -A pytest.ini | tail -5
```

| 符号 | 含义 |
|---|---|
| `$` | 行尾 |
| `^I` | tab |
| `^M` | Windows 换行（CRLF 的 CR） |

今天用它证明了 `EOFopts` 是终端回显假象，文件内容其实正确。

### heredoc 写完必须验证

```bash
wc -l <file> && tail -3 <file>
```

**今天的教训**：`checkpoint-day02.md` 第一次写入时 heredoc **静默截断**——预期 200 行，实际写入 15 行，**没有任何报错**。

**判断标准永远是 `wc`/`tail` 的实际内容，不是粘贴时的终端回显。**

### 子 shell 隔离环境变量

```bash
( export FOO=bar; command )    # FOO 只在括号内有效
```

写环境相关的验证脚本时必用。

### `inspect.getsource` 打印函数源码

```python
import inspect
from discoverse.universal_manipulation.task_config import TaskConfigLoader
print(inspect.getsource(TaskConfigLoader._validate_config))
```

**比 `sed -n '74,100p'` 好在哪**：不用猜行号，也不会因为文件被改动而取错范围。查「这个函数到底怎么实现的」时首选。

相关：`inspect.signature(f)` 看参数、`inspect.getfile(cls)` 看定义在哪个文件。

---

## 九、参数化 vs 循环（今天的核心收益）

```python
# ❌ 循环
def test_all_robots():
    for robot in ROBOTS:
        assert check(robot)      # 第一个失败就停

# ✅ 参数化
@pytest.mark.parametrize("robot_name", ROBOTS)
def test_one_robot(robot_name):
    assert check(robot_name)     # 9 个独立用例
```

| | 循环 | 参数化 |
|---|---|---|
| 失败后续用例 | **停止** | 继续 |
| 报告里看到 | 「第 3 个失败」 | **`test_x[iiwa14] FAILED`** |
| 能看到分布吗 | ❌ | ✅ **「9 个里 4 个不符」** |

**「能看到分布」是今天最关键的能力。** `qpos_dim` 测试跑出 5 通过 4 失败，才让我能判断「是那 4 个配置错了」而不是「我的公式错了」。

用循环的话只会看到「第 3 个失败」，然后陷入猜测。

> **样本量就是判断力**：9 个样本 5 对 4 错 → 能定位缺陷。2 个样本 1 对 1 错 → **无法判断谁错**。这也是 Day 2 测 9 种机械臂而不是先测 MMK2（只有 2 种双臂机器人）的核心理由。

### 参数化的复利效应

加第 10 个机器人时，只需在 `ROBOTS` 列表加一行，**7 个测试函数自动全部覆盖它** —— 一行代码换 7 个新用例。

这也是为什么要写「脆」的断言 `assert len(yamls) == 9`：**它在新增机器人时强制你回来更新列表**，否则新机器人会静默地不被任何测试覆盖。

---

## 十、xfail vs skip：不要混用

同一个 `place_block`，在两个测试里得到不同待遇：

```
XFAIL   test_camera_configs_nonempty[place_block]      ← 已知缺陷
SKIPPED test_camera_config_fields_wellformed[...]      ← 前提不满足
```

| | 含义 | 用在哪 |
|---|---|---|
| **xfail** | 「这个断言**应该**成立，但因已知缺陷不成立」 | 记录缺陷 |
| **skip** | 「这个断言的**前提**不满足，无法判断」 | 环境缺失、数据不存在 |

具体到这里：

- `test_camera_configs_nonempty` → **应该有相机，但没有** → 缺陷 → **xfail**
- `test_camera_config_fields_wellformed` → 检查「每个相机是否有 name/fovy/…」，但**一个相机都没有，无从检查** → **skip**

**混用的后果**：如果第一条也用 skip，缺陷 B 就变成了「跳过」—— 听起来像环境问题。**skip 会掩盖缺陷，xfail 会记录缺陷。**

### 两种 xfail 写法的关键区别

```python
# 写法 A：函数调用式（运行时决定）
if robot_name in QPOS_DIM_MISMATCH:
    pytest.xfail("缺陷 H：...")

# 写法 B：装饰器 + strict
@pytest.mark.xfail(strict=True, reason="缺陷 I：...")
def test_should_require_observation():
    ...
```

| | 缺陷被修复后 |
|---|---|
| A 函数调用 | 执行到这行就跳过，**永远不会 XPASS** |
| **B `strict=True`** | 断言真的执行；通过了 → **XPASS 报为失败** |

**`strict=True` 的意思是「如果这个测试意外通过了，把它当失败报出来」。**

**为什么要这样**：假设某天有人给 `_validate_config` 加上了 `observation` 必填，这条测试会通过 → `strict=True` 让它报 XPASS 失败 → **强制有人回来删掉 xfail 标记**。

不加 `strict` 的话，XPASS 只是个提示，很容易被忽略，然后标记永远留着，**假装缺陷还存在**。

> **`strict=True` 让「缺陷已修复」这件事也不会静默发生。** 又是同一个原则：不让变化隐形。

### 什么时候用 A 什么时候用 B

- **A（函数调用）**：参数化中只有**部分参数**要 xfail。装饰器会作用于全部 9 个用例，而我只想让特定 4 个 xfail，另外 5 个必须真正通过。
- **B（装饰器 + strict）**：整个测试都是「期望行为」的记录。

---

## 十一、覆盖率是下限指标，不是质量证明

```
Name                   Stmts   Miss  Cover   Missing
task_config.py            99     43    57%   59, 71-72, 110-138, ...
```

| 列 | 含义 |
|---|---|
| `Stmts` | 可执行语句总数（不含空行、注释） |
| `Miss` | 一次都没被执行的语句数 |
| `Cover` | (Stmts - Miss) / Stmts |
| **`Missing`** | **没执行到的具体行号** ← 最有用 |

### 高覆盖不代表测得好

```python
def divide(a, b):
    return a / b

def test_divide():
    assert divide(6, 2) == 3      # 覆盖率 100%，但 b=0 完全没测
```

**覆盖率只回答「这行被执行过吗」，不回答「所有情况都测了吗」。**

反过来看今天：

```python
# record_fps 只有 1 行代码
return self.config.get('observation', {'fps': 30}).get('fps', 30)
```

我写了 **4 个测试**（正常值 / 无键 / 空 dict / null 崩溃）。**覆盖率上只算 1 行**，但验证了 4 条执行路径，其中一条是崩溃分支。

**所以：低覆盖率一定有问题（大片代码没测），高覆盖率不保证质量。** 它适合找**完全没测的区域**，不适合证明**测得充分**。

CLAUDE.md 里「提升到 75%+」要这样理解：**75% 不是终点，是「不再有大片盲区」的意思。**

### 作用域必须限定

```toml
[tool.coverage.run]
source = ["discoverse/universal_manipulation"]
```

**不要写 `--cov=discoverse`** —— `policies/` 下 237 个策略学习文件会把分母稀释到 2-3%，这个数字既不能告诉你哪里没测，也不能作为进度基线。**指标的作用域必须和工作范围一致，否则指标本身就是噪声。**

---

## 十二、默认值什么时候是缺陷

`.get(key, default)` 本身没错，**错在用它兜底关键配置**。

判断标准：**这个配置缺失时，用默认值继续跑，比报错更好吗？**

| 配置 | 缺失时用默认值 | 合适吗 |
|---|---|---|
| 日志级别 | INFO | ✅ 不影响正确性 |
| 重试次数 | 3 | ✅ |
| **相机列表** | `[]`（不录任何图） | ❌ **产出物直接错** |
| **记录帧率** | 30 | ❌ 数据集帧率与预期不符 |

**规则：影响产出正确性的配置，缺失必须报错；只影响行为偏好的配置，才可以有默认值。**

### 空集合是最坏的默认值

```python
return self.config.get('observation', {}).get('cameras', [])
```

`[]` 在 Python 里是**假值但不是错误**：

```python
for cam in []:      # 循环体一次都不执行，安静跳过
    render(cam)
```

**数据采集流程正常跑完、正常退出，一张图都没录，全程无报错。**

在具身智能项目里**数据即产品**。采集配置的静默错误比代码崩溃严重得多 —— 崩溃你马上知道，静默错误要几周后训练效果差了才发现，而且会去怀疑算法、调超参，根本想不到是采集配置错了。

### `.get()` 的一个陷阱

```python
{'observation': None}.get('observation', {'fps': 30})    # → None，不是默认值！
None.get('fps', 30)                                       # → AttributeError
```

**`.get(k, default)` 只在【键不存在】时用默认值。** 键存在但值为 `None` 时返回 `None`。

而 YAML 里 `observation:` 后面留空就产生 `None`：

```yaml
observation:        # ← 这就是 None
task_name: foo
```

**这是非常容易写出的配置形态**，所以缺陷 C 的崩溃分支是真实风险，不是理论问题。

---

## 十三、配置继承（extends）与测试

### 机制

```yaml
# place_block.yaml
extends: templates/place_object.yaml   ← 继承声明
task_name: place_block                 ← 只写差异
runtime_parameters:
  source_object: block_green
```

加载流程：读子配置 → 发现 `extends` → 加载模板 → 合并（**子覆盖父**）→ 丢弃 `extends` 键本身（它是指令不是数据）。

**类比**：Python 的类继承、Docker 的 `FROM`、CSS 的 `@extend`。

### 对测试的影响（关键）

**不能只读单个 YAML 文件判断配置内容。**

```
读 place_block.yaml        → 5 个键
用加载器加载               → 12 个键（模板给了 7 个）
```

**必须用加载器加载后再断言。** 今天差一点就基于原始文件写了断言，得出错误的根因。

### 验证 extends 真的生效

```python
def test_extends_actually_merged_template(load_task, task_name):
    cfg = load_task(task_name).config
    assert "extends" not in cfg, "合并后 extends 指令本身不应保留"
    assert "source_object" in cfg.get("runtime_parameters", {})
```

**为什么要专门测这个**：如果 `extends` 是死配置（写了不读），三个任务会静默丢失全部模板内容。这条断言排除了这种可能，把缺陷 B 的根因锁定在「模板缺字段」。

---

## 十四、判断「代码错」还是「测试错」

**这是测试开发最核心也最难的判断。**

两种失败模式：

| 模式 | 后果 |
|---|---|
| 总怀疑代码 | 提假缺陷，浪费开发时间，**信誉受损** |
| **总怀疑自己** | 遇红就改测试迁就，**把真 bug 洗白**（更危险） |

### 三条判断依据

1. **找独立的第二信源。**
   配置说 `ctrl_dim=7`，MJCF 编译出 `nu=7` 吗？两者不一致时 **MJCF 是真相**（它是引擎真正加载的），配置只是描述。

2. **看分布。**
   1/9 不符 → 大概率那 1 个错了。7/9 不符 → 几乎肯定是我的公式错了。**这就是为什么要参数化而不是循环。**

3. **看失败位置是否集中。**
   5 个测试全挂在 `from_dict` 构造阶段、一行断言都没执行到 → 系统性问题，是我的测试数据不对。若分散在不同断言 → 更可能是被测代码的问题。

### 判断出「测试错」之后也别猜着改

用 `inspect.getsource` 打印出完整的必填字段清单，**一次查清一次改对**。如果只补 `description` 就重跑，还会因为缺 `states` 再红一次。

---

## 十五、「写错也不会炸」的字段，bug 密度最高

今天最有价值的一个规律：

| 字段 | 写错的后果 | 9 个机器人的正确率 |
|---|---|---|
| `ctrl_dim` | `data.ctrl[:] = 长度不符数组` → **立刻 ValueError** | **9/9 全对** |
| `qpos_dim` | `qpos[:9]` 在 `nq=15` 上**合法**，静默丢掉后 6 个 | **4/9 错** |

**会炸的字段维护得好，不会炸的字段积累错误。**

这不是这个项目的特殊问题，是**软件工程的普遍规律**：错误只有在被感知时才会被修复。

**而这个规律本身就是找 bug 的地图** —— 进新项目时优先怀疑：

- 数组长度 / 切片边界（越界才炸，截断不炸）
- 可选配置字段（有默认值兜底）
- 日志和错误消息里的内容（没人对它断言）
- 数值精度和单位（弧度/角度、米/毫米）

---

## 十六、三个还没想透的问题

1. **`session` 缓存的 `MjModel` 真的完全只读吗？** MuJoCo 有些 API（如 `mj_setConst`）会写回 model。如果某个测试调了这类 API，session 缓存就变成污染源了。→ Day 3-4 确定性测试时要验。

2. **`timeout = 60` 用 signal 方式实现，对 C 扩展里的死循环有效吗？** pytest-timeout 的 signal 方式依赖 Python 层的信号处理，MuJoCo 步进是 C 代码。如果卡在 C 里，SIGALRM 可能要等回到 Python 层才被处理。→ 需要构造一个真死循环验证。

3. **`tests/unit/` 没有 `__init__.py` 会怎样？** 目前能跑（pytest 用 rootdir-based 导入）。但如果两个子目录出现同名测试文件（`unit/test_config.py` 和 `data/test_config.py`），会不会冲突？→ **Step 8 已补上 `__init__.py`，但冲突场景仍未实测验证**（需要真的建两个同名文件试一次）。

4. **`iiwa14` 的 `nq` 为什么比声明值多 6？** 其余三个不符的机器人差 1-2，可由夹爪建模方式（tendon / equality / single）解释。差 6 超出这个范围。假设是 XML 里混入了 `FREE` 类型关节（占 7 个 qpos，`9 + 7 - 1 = 15`），但**未验证**。→ Day 6-7 查根因，命令见 checkpoint 第三节。

5. **`config_utils.py:83` 那条未覆盖的分支重要吗？**
   ```python
   if i < len(result):
       result[i] = override_state      # 覆盖已有状态
   else:
       result.append(override_state)   # 第 83 行，未覆盖
   ```
   是 `states` 列表合并的分支：子配置 states 比模板多时才走到。今天测的 3 个继承任务都不超过模板长度。**纯列表操作看似风险低，但这类「只在特定数据形态下才走到」的分支是真实 bug 的常见藏身处。** → Day 8-9 构造一个 states 更长的配置补上。
