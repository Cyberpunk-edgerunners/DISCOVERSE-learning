# 缺陷清单 · Day 2 通读补充（缺陷 J-R）

> **产出于**：2026-07-30，对 `discoverse/`（52 文件 7396 行）+ `examples/universal_tasks/` 的一次系统通读
> **方法**：逐文件 Read + 运行时实测（加载真实配置、编译真实 MJCF 对账）
> **与已有编号的衔接**：缺陷 A-D 见 [architecture-notes.md](architecture-notes.md) 第八节；E/G/H/I 见 [checkpoint/checkpoint-day02.md](checkpoint/checkpoint-day02.md) 第五节。本文新增 **J-R 共 9 条**
> **证据标准**：每条都亲自 Read 过对应行号。agent 报告但我未复核的另列于第六节，明确标注 **待复核**
> **配套**：原理讲解见 [../source-notes/DISCOVERSE小白入门讲解.md](../source-notes/DISCOVERSE小白入门讲解.md)（不含缺陷评判）

---

## 一、摘要

| 编号 | 一句话 | 严重度 | 可达性 |
|---|---|---|---|
| **J** | `collision_radius` 键名不匹配，**9/12 物体的避让半径静默失效** | **高** | 每次 reset 都发生 |
| **K** | 夹爪工厂函数假多态，9/9 机器人都被当 tendon 夹爪控制 | **高** | 每次运行 |
| **L** | `mink` / `quadprog` 未声明为依赖，`pip install` 后直接 ImportError | **高** | 全新安装必然触发 |
| **M** | `step()` 返回值语义重载，超时/异常/正常结束无法区分 | 中 | 可达 |
| **N** | fail-closed 的副作用：配置写错 → 静默删数据 → 无限循环 | 中 | 可达 |
| **O** | `mink_solver` 的 `dt` 被硬编码遮蔽，YAML 配置无效 | ~~中~~ **低** | 每次 IK 求解，但**无行为影响**（见第九节） |
| **P** | `panda.yaml` 有重复键 + 乱码残留 | 中 | 靠 PyYAML 行为侥幸不炸 |
| **Q** | `conditions` 空列表 → 恒判定成功 | 中 | **当前不可达** |
| **R** | `randomize_scene` 返回类型与注解不符 | 低 | 可达 |

**另有一条重要修正**（第二节）：checkpoint-day02 里「`except` 返回 True」的假设**被证伪**。

> **📌 Day 3-4 更新（2026-08-05）**：新增缺陷 **S / T / U**，并修正 **J / O / H** 的记录。
> 全部见 **[第九节](#九day-3-4-更新)**。当前修复状态一览：
>
> | 缺陷 | 状态 | commit |
> |---|---|---|
> | J | ✅ 已修 | `8cfbc38` |
> | O | ✅ 已修（严重度降为低） | `c722ca8` |
> | **U**（新） | ✅ 已修 | `c722ca8` |
> | **S**（新） | ⏸ 未修，`xfail(strict)` 守着 | — |
> | **T**（新） | ⏸ 未修 | — |
> | H | 🔍 根因已查明，**待决策**（语义未定义） | — |
> | 「seed 未消费」 | ✅ 已修 | `cd09b80` |

---

## 二、⚠️ 实测修正：一条已记录的假设不成立

### 原记录

`docs/checkpoint/checkpoint-day02.md` 第四节写着：

> [task_base.py:165-167](../discoverse/universal_manipulation/task_base.py#L165) 的 `except` 吞异常后返回什么？**若返回 `True`，则任何条件检查出错都判定成功** —— 这直接解释 Day 1 那条「完成状态 10/10 但实际距离 0.2908m」。**可能是整个项目最严重的缺陷。**

### 实测结果：返回 `False`，不是 `True`

```python
# discoverse/universal_manipulation/task_base.py:140-167
def _evaluate_condition(self, condition) -> bool:
    condition_type = condition.get('type')
    try:
        if condition_type == 'distance':
            return self._check_distance_condition(condition)
        ...
        else:
            print(f"警告：未知的条件类型: {condition_type}")
            return False                                    # ← 未知类型也是 False
    except Exception as e:
        print(f"条件检查失败 ({condition.get('description', '未知条件')}): {e}")
        return False                                        # ← 是 False
```

**这里是 fail-closed（出错就算失败）的，安全。** 假设不成立。

> **教训**：这条假设从 Day 1 带到 Day 2，两天里被当作「最高优先线索」。**它只需要 5 秒钟的 `sed -n '165,167p'` 就能证伪。**
>
> 未经核实的推断一旦写进交接文档，就会被后续所有决策当作事实。**checkpoint 里的每一条都应该标注「已核实 / 待核实」。**

### Day 1 那个现象的真正解释

见下方**缺陷 M**。

---

## 三、高严重度缺陷

### 缺陷 J｜`collision_radius` 从未被读取，11/13 物体的避让半径静默失效

**位置**：[randomization.py:184](../discoverse/universal_manipulation/randomization.py#L184)

**现象**：代码读 `min_distance`，但所有任务 YAML 写的都是 `collision_radius`。

```python
# randomization.py:184
radius = obj_config.get('min_distance', 0.05)
```

```yaml
# place_block.yaml:32
      collision_radius: 0.12  # 碗的直径较大，需要更大的避让距离
```

**键名对不上** → `.get()` 取不到 → **全部落到默认值 0.05**。

**实测量化**（用加载器加载真实配置对比）：

| 任务 | 物体 | YAML 声明 | 实际生效 | 偏差 |
|---|---|---|---|---|
| place_block | bowl_pink | 0.120 | 0.050 | **缩小 2.4×** |
| place_coffeecup | plate_white | 0.120 | 0.050 | **缩小 2.4×** |
| place_coffeecup | coffeecup_white | 0.100 | 0.050 | 缩小 2.0× |
| cover_cup | plate_white | 0.100 | 0.050 | 缩小 2.0× |
| place_kiwi_fruit | flower_bowl | 0.090 | 0.050 | 缩小 1.8× |
| place_kiwi_fruit | kiwi | 0.070 | 0.050 | 缩小 1.4× |
| stack_block | block_green/red/blue | 0.060 | 0.050 | 缩小 1.2× |
| cover_cup | coffeecup_white, cup_lid | 0.050 | 0.050 | 恰好相同 |
| place_block | block_green | 0.050 | 0.050 | 恰好相同 |

**13 个物体中 11 个受影响。** 只有 2 个恰好声明值就是 0.05 才没事。

**根因**：`templates/randomization.yaml` 用的是 `min_distance`（6 处），实际任务 YAML 用的是 `collision_radius`（13 处）。**模板与实现演进不同步**，代码跟着模板写，配置跟着另一套约定写。

**影响**：

- 容器类物体（碗、盘子）受影响最重 —— **正是 pick-and-place 最怕重叠的地方**
- `place_block.yaml:32` 的注释「碗的直径较大，需要更大的避让距离」**完全无效**
- **方块可以生成在碗里** → 任务开局就是失败状态 → 静默污染训练数据
- 可能解释部分 62.5%-75% 的 flake 率

**复现**：

```bash
source scripts/dev/env.sh
$PY - <<'PYEOF'
from discoverse.universal_manipulation.task_config import TaskConfigLoader
import glob, os
for f in sorted(glob.glob('discoverse/configs/tasks/*.yaml')):
    r = TaskConfigLoader(f).randomization or {}
    for o in (r.get('objects') or []):
        d, a = o.get('collision_radius'), o.get('min_distance', 0.05)
        if d and abs(d-a) > 1e-9:
            print(f"{os.path.basename(f)[:-5]:18s} {o['name']:18s} 声明{d} 实际{a}")
PYEOF
```

**修复方向**（两个都要做）：

1. 代码兼容两个键名：`obj_config.get('collision_radius', obj_config.get('min_distance', 0.05))`
2. 统一约定并更新 `templates/randomization.yaml`

**回归测试**：断言每个物体的实际生效半径 == YAML 声明值。

---

### 缺陷 K｜夹爪工厂函数假多态

**位置**：[gripper_controller.py:70-71](../discoverse/universal_manipulation/gripper_controller.py#L70)

```python
def create_gripper_controller(gripper_config, mj_model, mj_data) -> GripperController:
    return TwoFingerGripper(gripper_config, mj_model, mj_data)
```

**无条件返回同一个类，完全无视 `gripper_config["type"]`。**

而文件头 docstring 声称：

```
支持三种夹爪实现模式：
1. tendon控制 (如airbot_play)
2. equality约束 (如panda)
3. 单关节控制 (如ur5e)
```

**全文件只定义了 `TwoFingerGripper` 一个类。**

**实测**：4 种 `type` 值全部得到同一控制器：

| `type` | 机器人 | 得到的控制器 |
|---|---|---|
| `two_finger_tendon` | airbot_play, iiwa14, xarm7 | `TwoFingerGripper` |
| `two_finger_equality` | panda | `TwoFingerGripper`（应为 equality 版） |
| `two_finger_single` | arx_l5, arx_x5, piper, ur5e | `TwoFingerGripper`（应为单关节版） |
| `multi_finger_equality` | rm65 | `TwoFingerGripper`（应为多指版） |

**为什么现在没炸**：所有类型的控制方式恰好都归约为「写一个标量到一个 ctrl 位」。**这是巧合式正确** —— 一旦遇到需要两个 ctrl 位的夹爪（独立控制两指），就会静默出错。

**附带问题**（同文件 [:26-31](../discoverse/universal_manipulation/gripper_controller.py#L26)）：

```python
# 从配置文件获取控制范围，但优先使用从MJCF文件中读取的实际关节范围
self.config_ctrl_range = gripper_config["ctrl_range"]
# 如果配置中指定了关节名称，尝试从MJCF获取真实范围
# 使用配置中指定的控制范围
self.ctrl_range = self.config_ctrl_range          # ← 注释描述的逻辑未实现
```

注释说「优先使用从 MJCF 读取的实际关节范围」，代码直接用配置值。**注释与实现不符，比没有注释更误导。**

**另外**：`sensor_index`（`:35-42` 解析）和 `grasp_threshold`（YAML 声明）**从未被使用** → **没有抓取检测功能**。

**修复方向**：工厂函数按 `type` 分派；或者删掉 docstring 里未实现的承诺、把 `type` 明确标为文档字段。

---

### 缺陷 L｜`mink` / `quadprog` 未声明为依赖

**位置**：[pyproject.toml:36-46](../pyproject.toml#L36) vs [mink_solver.py:8](../discoverse/universal_manipulation/mink_solver.py#L8)

**实测**：

```
pyproject.toml 核心依赖 9 个：
  numpy scipy opencv-python mujoco psutil matplotlib screeninfo mediapy tqdm

grep "mink\|quadprog" pyproject.toml  →  零命中
```

但：

```
discoverse/universal_manipulation/mink_solver.py:8      import mink
examples/universal_tasks/universal_task_runtime.py:7    import mink
```

**后果**：`pip install discoverse` 之后跑 universal_tasks 直接 `ModuleNotFoundError: No module named 'mink'`。

`quadprog` 同理 —— robot YAML 里 `solver_type: "quadprog"` 需要它作为 mink 的后端。

`av`（PyAV，视频编码）也只在 `data-collection` extra 里，核心依赖没有 → 不装 extra 就录不了视频。

**修复方向**：把 `mink`、`quadprog` 加入核心依赖；`av` 视情况移入核心或在 `PyavImageEncoder` 里给出明确的安装提示。

⚠️ **这条也影响 Day 8-9 的 Docker 镜像** —— Dockerfile 里同样没有 `pip install mink`。

---

## 四、中严重度缺陷

### 缺陷 M｜`step()` 返回值语义重载 —— Day 1 现象的真正解释

**位置**：[universal_task_runtime.py:213-262](../examples/universal_tasks/universal_task_runtime.py#L213)

`step()` 的返回值有 **5 个出处、2 种值、5 种含义**：

| 返回 | 行号 | 含义 |
|---|---|---|
| `True` | :230 | **状态全部跑完，正常结束** |
| `True` | :257 | 本步执行成功，继续 |
| `False` | :223 | 原语设置失败（IK 不收敛） |
| `False` | :234 | **超时**（`mj_data.time > max_time`） |
| `False` | :262 | **抛异常**（`except Exception` 打印后返回） |

而 `run()` 的循环只写（`:281`）：

```python
while self.running:
    if not self.step():
        break
```

**三种 `False` 无法区分。**

#### 这怎么解释「完成状态 10/10 但实际距离 0.2908m」

```
任务超时退出（:234 返回 False）
  → run() 循环 break
  → self.success 保持 __init__ 里的初值 False（:375）
  → 但 self.stm.state_idx 已经推进到了 10
  → :331 打印 "完成状态: 10/10"
  → :332 打印 "任务成功: ❌ 否"
```

**所以不是「伪造成功」，而是「进度指标与成功判定脱钩」。**

两个具体问题：

1. **`step()` 返回值重载** —— 调用方无法区分超时、异常、正常结束，也就无法做差异化处理（超时该重试？异常该报警？）
2. **日志把 `state_idx/total_states` 呈现为"完成状态"** —— 状态机走完所有状态 ≠ 任务达成。这个措辞误导读者以为「执行到位了，只是判据太严」

**修复方向**：返回枚举而非 bool（`StepResult.RUNNING / DONE / TIMEOUT / IK_FAILED / EXCEPTION`）；日志改成「状态机进度」而非「完成状态」。

---

### 缺陷 N｜fail-closed 的副作用：配置写错 → 静默删数据 → 无限循环

**位置**：[task_base.py:165-167](../discoverse/universal_manipulation/task_base.py#L165) + [universal_task_runtime.py:340-342](../examples/universal_tasks/universal_task_runtime.py#L340)

第二节说明了 `_evaluate_condition` 的 `except` 返回 `False` 是安全的。**但它有一个副作用链**：

```
YAML 里 body 名写错（如 "blok_green"）
  → self.mj_data.body("blok_green") 抛 KeyError
  → 被 :165 的 except Exception 捕获
  → 打印一行中文 + 返回 False
  → 判定「任务失败」
  → universal_task_runtime.py:341 shutil.rmtree(save_dir) 删掉数据
  → 外层 while True 继续下一轮（:457）
  → 无限循环：每轮都跑满 20 秒、每轮都删自己的数据
  → 且不提示「你的配置写错了」
```

**问题不在 fail-closed，而在于「配置错误」和「任务失败」被归为同一类。**

- 任务失败（没抓起来）→ 删数据是**正确**的
- 配置错误（名字写错）→ 应该**立刻崩掉并告诉用户**

⚠️ **附带的数据丢失问题**：`save_dir` 不带序号（`:385`）：

```python
self.save_dir = os.path.join(DISCOVERSE_ROOT_DIR, "data", f"{robot_name}_{task_name}")
```

无限循环模式下每轮共用同一目录 → **第 1 轮成功存的数据会被第 2 轮的失败删掉**。

对比老架构 `place_block.py:117` 用 `"{:03d}".format(data_idx)` 分目录 —— **新架构在这点上退化了**。

**修复方向**：

1. `except` 里区分异常类型 —— `KeyError`（名字错）应该 re-raise，只有真正的数值/几何异常才吞
2. `save_dir` 加序号

---

### 缺陷 O｜`mink_solver` 的 `dt` 被硬编码遮蔽

**位置**：[mink_solver.py:50](../discoverse/universal_manipulation/mink_solver.py#L50) vs [:126](../discoverse/universal_manipulation/mink_solver.py#L126)

```python
# :50  从配置读
self.dt = self.solver_config.get('dt', 2e-3)

# :126  在 solve_ik 里又硬编码
dt = 1e-3
```

后续迭代用的是局部变量 `dt`，**`self.dt` 从未被使用**。

**实测**：9 个 robot YAML 都写了 `dt: 0.002`，实际生效的是 `0.001`。

**影响**：`dt` 是积分步长，直接影响收敛速度与 `max_iterations` 的配合。**调 YAML 里的 `dt` 是无效操作** —— 有人调参调半天没效果还找不到原因。

**修复方向**：`:126` 改用 `self.dt`；或者删掉配置项并在文档说明 dt 固定。

---

### 缺陷 P｜`panda.yaml` 有重复键 + 乱码残留

**位置**：[configs/robots/panda.yaml:6-17](../discoverse/configs/robots/panda.yaml#L6)

实测文件内容：

```yaml
 6	kinematics:                          ← 第一个 kinematics
 7	  base_link: "panda_link0"
 8	  end_effector_site: "endpoint"
 9	  qpos_dim: 9
10	  ctrl_dim: 8
11	  arm_joints: 7
12	  posture_cost: 0.01                 ← 这两个字段本该在 ik_solver 下
13	  dt: 0.002                          # 积分时间步长 (参考示例)ika Panda 7-DOF协作机械臂"
                                            ↑ 乱码残留
14
15	# ============== 机械臂结构配置 ==============
16	kinematics:                          ← 第二个 kinematics（重复键！）
17	  base_link: "panda_link0"
```

两个问题：

1. **重复的 `kinematics:` 键** —— YAML 规范里这是错误
2. **第 13 行末尾有乱码** `(参考示例)ika Panda 7-DOF协作机械臂"` —— 明显是复制粘贴事故的残留

**为什么没炸**：PyYAML 的 `safe_load` 遇到重复键**静默取最后一个**，不报警。实测：

```
重复键的胜者内容: ['base_link', 'end_effector_site', 'qpos_dim', 'ctrl_dim', 'arm_joints', 'arm_joint_names']
posture_cost 还在 kinematics 里吗: False       ← 第一个块的内容被丢弃
ik_solver.posture_cost: 0.01                   ← 正确位置也有一份，所以功能正常
```

**第二个块内容完整正确，且 `posture_cost`/`dt` 在 `ik_solver:` 下也各有一份** → 程序正常工作。**纯靠 PyYAML 的行为侥幸不出问题。**

**修复方向**：删掉第 6-13 行的整个第一块。

**回归测试**：用自定义 loader 检测重复键，对 9 个 robot YAML 全部断言无重复键。

---

### 缺陷 Q｜`conditions` 空列表 → 恒判定成功（当前不可达）

**位置**：[task_base.py:101-113](../discoverse/universal_manipulation/task_base.py#L101)、[:129-130](../discoverse/universal_manipulation/task_base.py#L129)

```python
def _check_simple_conditions(self, success_config) -> bool:
    conditions = success_config.get('conditions', [])       # 缺失 → 空列表
    for i, condition in enumerate(conditions):              # 空列表 → 循环不执行
        ...
        if not result:
            return False
    return True                                             # ← 直接返回 True
```

**零个条件被检查，判定成功。**

`_check_combined_conditions` 走 `and` 分支时同理，因为 Python 里 `all([]) == True`（实测确认）。

**可达性：当前不可达。** 实测 5 个任务的 conditions 数量：

| 任务 | method | conditions 数 |
|---|---|---|
| cover_cup | combined | 3 |
| place_block | simple | 1 |
| place_coffeecup | combined | 2 |
| place_kiwi_fruit | combined | 2 |
| stack_block | combined | 3 |

**全部非空，所以这条路径现在走不到。** 它是潜在缺陷：任何人新增任务时漏写 `conditions`，就会得到一个「永远成功」的任务。

**附带**（[task_base.py:90](../discoverse/universal_manipulation/task_base.py#L90)）：

```python
success_config = self.task_config.success_check     # 可能是 None
method = success_config.get('method', 'simple')     # → AttributeError
```

`success_check` 属性可能返回 `None`（`task_config.py:177` 是 `.get('success_check')`）。此时 `.get()` 抛 `AttributeError`，**且这行在 try/except 之外**（那个 try 在更深一层的 `_evaluate_condition` 里）→ 异常直接传播出 `check_success()`。

同样**当前不可达**（5 个任务都有 `success_check`）。

**修复方向**：空 conditions 应报错或返回 `False`；`success_check` 为 `None` 时给出明确错误信息。

---

## 五、低严重度

### 缺陷 R｜`randomize_scene` 返回类型与注解不符

**位置**：[task_base.py:78-81](../discoverse/universal_manipulation/task_base.py#L78)

```python
def randomize_scene(self, max_attempts: int = 100) -> bool:
    if not self.randomization_config:
        return                                              # ← 返回 None
    self.randomizer.exec_randomization(self.randomization_config, max_attempts)
                                                            # ← 无 return，也是 None
```

声明 `-> bool`，**两条路径都返回 `None`**，而且丢弃了 `exec_randomization` 的真实返回值。

**影响**：调用方若写 `if not task.randomize_scene(): retry()` 会**永远进入重试分支**。目前调用方都忽略返回值（`universal_task_runtime.py:361`），所以是潜在问题。

**修复方向**：`return False` / `return self.randomizer.exec_randomization(...)`。

---

### 附：机器人白名单与 YAML 是两份需手工同步的真相

**位置**：[task_base.py:71](../discoverse/universal_manipulation/task_base.py#L71)

```python
if robot_name in ["airbot_play", "panda", "arx_x5", "arx_l5", "piper", "ur5e", "rm65", "xarm7", "iiwa14"]:
    return RobotInterface(self.robot_config, mj_model, mj_data)
else:
    raise NotImplementedError(f"Robot '{robot_name}' interface not implemented yet")
```

9 个名字硬编码在 Python 里，与 `discoverse/configs/robots/` 下的 9 个 YAML 文件构成**两份需要手工同步的真相**。

**违背项目自己的「配置驱动」原则**：新增机器人时光加 YAML 不够，还得改这行列表。

而且白名单里所有分支返回**同一个** `RobotInterface` —— 它纯粹是门禁，没有任何按机器人分派的行为。

**修复方向**：改为检查配置文件是否存在，或直接删掉白名单。

---

## 六、待复核（agent 报告，我未亲自确认）

以下由探索 agent 报告，**我没有逐行 Read 确认**。Day 6-7 写正式报告前必须自行验证。

| 待复核项 | 声称的位置 | 声称的问题 |
|---|---|---|
| `mj_name2id` 返回 -1 使 except 成死代码 | `robot_interface.py:70-83, 98-127` | 名字写错时静默 append `-1`，索引取到 sensordata 末位元素 → 录进数据集的 `jq` 是错的 |
| `grasp_object`/`release_object` 无 handler | `universal_task_runtime.py:137-192` | **已部分确认**：`grep "primitive =="` 只有 :137/:167 两处命中；实测 4 种 primitive 名共出现 55 次（`grasp_object` 6 次、`release_object` 6 次）。但「fallback 恰好正确」这个推断我未运行验证 |
| 光照强度跨 episode 累乘 | `randomization.py:442-449` | `intensity_range` 原地乘 `light_ambient/diffuse/specular`，无恢复 → `random_color` 为 false 时逐轮变暗 |
| `merge_states_array` 按位置索引合并 | `config_utils.py:63-85` | 子配置中间插入一个 state 会静默替换错误的后续步骤 |
| `@abstractmethod` 在非 ABC 类上失效 | `simulator.py:612-634` | `SimulatorBase` 不继承 `ABC`，装饰器无效，类可直接实例化 |
| `__str__` 引用不存在的成员 | `robot_interface.py:152`、`task_config.py:206` | `print(obj)` 抛 `AttributeError` |
| `SimulatorBase` 的可变类属性 | `simulator.py:45-52, 71` | `img_rgb_obs_s = {}` 等是类级可变对象，多实例会互相污染 |
| `_validate_solution` 不检查关节限位 | `mink_solver.py:181-195` | 只查 NaN/Inf，名字和 docstring 都说「验证有效性」 |
| `cicd_testing.py` 靠 grep emoji 判定成败 | `cicd_testing.py:121` | 且 `A or B and C` 优先级问题；声称 `"✅ 任务成功检查通过"` 字符串从未被输出 |
| `close_laptop` 在 CLI choices 里但无 YAML | `universal_task_runtime.py:502` | 选了会 `FileNotFoundError` |
| `observation.fovy` 被注释掉不生效 | `universal_task_runtime.py:394-396` | YAML 里的 `fovy` 是死字段 |
| `Dockerfile.vnc` 的 CMD 相对路径不符 | `discoverse/docker/Dockerfile.vnc` | 与实际文件位置对不上 |
| `discoverse-check` 入口点模块路径无效 | `pyproject.toml:218` | `scripts/` 不是包，装上后 ImportError |

---

## 七、贯穿模式：静默的空集合与未消费的配置

把 Day 1-2 发现的缺陷横向对比，**同一个模式出现了 6 次**：

| 实例 | 现象 | 后果 |
|---|---|---|
| `camera_configs` 返回 `[]`（缺陷 B） | `observation` 缺失 → 空列表 | `for cam in cams:` 不执行 → **零张图像**，采集流程正常退出 |
| `conditions` 为空（缺陷 Q） | 键缺失 → 空列表 | `for` 不执行 → **恒判定成功** |
| `settings.seed`（缺陷 D） | 声明 6 处 | **无任何代码读取** → 仿真不可复现且无开关 |
| `testpaths = ["tests"]`（缺陷 G） | 指向不存在的目录 | 配置从未生效，无人跑过测试 |
| `collision_radius`（缺陷 J） | **键名不匹配** | 11/13 物体避让半径静默缩小到 0.05 |
| `settings.collision_check` 等 4 字段 | 声明但无代码读取 | 配置是装饰 |

### Python 语义根源

四条规则共同造就了这个模式：

```python
for x in []:          # 空序列 → 循环体一次都不执行，不报错
    ...

all([])               # → True   ← 空集合的「全部满足」是真
any([])               # → False

d.get('k', default)              # 键【不存在】时用 default
{'k': None}.get('k', default)    # → None，不是 default！
None.get('x')                    # → AttributeError

d.get('wrong_key', fallback)     # 键名写错 = 键不存在 → 静默用 fallback
```

**共同特征：它们都不报错。** 空集合在 Python 里是合法的「假值」，但不是错误。

### 判断标准

**影响产出正确性的配置，缺失必须报错；只影响行为偏好的配置，才可以有默认值。**

| 配置 | 缺失时兜默认值 | 合适吗 |
|---|---|---|
| 日志级别 | INFO | ✅ 不影响正确性 |
| 重试次数 | 3 | ✅ |
| **相机列表** | `[]`（不录图） | ❌ **产出物直接错** |
| **记录帧率** | 30 | ❌ 数据集帧率与预期不符 |
| **避让半径** | 0.05 | ❌ 物体重叠，数据污染 |
| **成功判据** | 空列表 → 恒真 | ❌ **最坏的一种** |

> 💡 **面试可以这么讲**：
> 「我在这个项目里发现同一个 bug 模式出现了 6 次：**配置声明了但代码从未读取，或者键名不匹配导致静默回退默认值**。它们的共同点是 Python 的空集合和 `.get()` 都不报错 —— `for` 遇到空列表安静跳过，`all([])` 是 True，`.get()` 键名写错就用默认值。
>
> 最严重的一条是物体避让半径：配置里给碗写了 0.12 米并注释「碗直径较大需要更大避让距离」，代码读的却是另一个键名，实际生效 0.05 —— **13 个物体里 11 个都被缩小了，方块可以生成在碗里，静默污染训练数据。**
>
> 所以我给默认值定了一条判断标准：**影响产出正确性的配置，缺失必须炸；只影响行为偏好的，才可以兜默认值。** 前者用 `.get(k, default)` 是在把 bug 伪装成正常运行。」

---

## 八、Day 6-7 建议的处理顺序

按「影响 × 修复成本」排：

| 顺序 | 缺陷 | 理由 |
|---|---|---|
| 1 | **J**（collision_radius） | 影响最大（数据质量），修复最简单（一行 `.get`） |
| 2 | **L**（mink 依赖） | 影响全新安装，修复是加两行依赖声明 |
| 3 | **P**（panda.yaml 乱码） | 删 8 行即可，且是「配置文件也会有 bug」的好案例 |
| 4 | **O**（dt 遮蔽） | 一行改动 |
| 5 | **N**（配置错误静默删数据） | 需要区分异常类型，改动稍大 |
| 6 | **K**（夹爪假多态） | 要么实现三种、要么删承诺，是设计决策 |
| 7 | **M**（step 返回值重载） | 需要引入枚举，涉及调用方 |
| 8 | Q / R / 白名单 | 潜在问题，优先级低 |

**每条修复都应配一条回归测试** —— 用 `xfail(strict=True)` 记录当前行为，修复后自动转 XPASS 提醒撤标记。

---

## 九、Day 3-4 更新

> 产出于 2026-08-03 ~ 08-05。**本节所有数字均为实测**，推翻了本文件与 checkpoint 中的若干推断。

### 9.1 对已有条目的修正

| 缺陷 | 原记录 | **实测修正** |
|---|---|---|
| **J** | 「13 物体 11 受影响」 | **12 物体 9 受影响**（另 3 个声明值恰好就是 0.05） |
| **J** | 「模板与任务两边都是真实用户，只改一边会破坏另一边」 | ❌ **`templates/randomization.yaml` 从未被任何任务 `extends`** —— 唯一引用是它自己第 137 行的注释示例。兼容双键名仍正确，但理由变为「保护未来照模板抄的人」 |
| **O** | 严重度「中」 | **降为「低」** —— 实测修复前后 IK 解逐位相同，见 9.2 |
| **H** | 「iiwa14 差 6 最可疑，可能有 FREE 关节占 7 个 qpos」 | ❌ **4 个模型零个 FREE 关节**，真因是夹爪连杆建模，见 9.5 |

### 9.2 缺陷 O 重新定性：休眠缺陷

**位置**：[mink_solver.py:126](../discoverse/universal_manipulation/mink_solver.py#L126)（局部 `dt = 1e-3` 遮蔽 [:50](../discoverse/universal_manipulation/mink_solver.py#L50) 的 `self.dt`）

**实测**：9/9 机器人 YAML 均声明 `ik_solver.dt: 0.002`，全部无效。但**修复前后 IK 解逐位相同**（`atol=1e-9`）：

| 末端偏移 | dt=1e-3 | dt=2e-3 | 解相同 |
|---|---|---|---|
| 2cm | 1 迭代 err=0.000589 | 1 迭代 err=0.000589 | ✅ |
| 5cm | 1 迭代 err=0.003180 | 1 迭代 err=0.003180 | ✅ |
| 10cm | 2 迭代 err=0.000742 | 2 迭代 err=0.000742 | ✅ |
| 15cm | 2 迭代 err=0.003363 | 2 迭代 err=0.003363 | ✅ |

**原因**：`mink.solve_ik` 内部将任务误差**除以 dt** 得期望速度，`integrate_inplace` 又**乘以 dt** 积分回去 —— 一除一乘，dt 约掉。它仅在配置了 `mink.VelocityLimit` 时才影响单步位移上限。

**为什么仍然修**：一旦引入速度限制，配置写 0.002 实际按 0.001 算，**限幅严一倍**而配置文件看起来完全正确 —— 缺陷 J 的剧本重演。修复成本一行、实测零风险。

**未写行为测试**：无可观测差异，写了也是永远为真的断言。

**状态**：✅ 已修 `c722ca8`

> 📌 **方法论：「配置无效」和「配置无效且有害」是两回事。**
> 判据是「如果它生效了，行为会变吗」——
> J 生效后 0.05→0.12 行为大变（高）；O 生效后逐位相同（低）。
> **不要因为缺陷模式相同就假设严重度相同。**

### 9.3 缺陷 S｜`get_random_texture()` 的随机源不受管控

**位置**：[utils/__init__.py:86-97](../discoverse/utils/__init__.py#L86)

```python
def get_random_texture():
    if 贴图目录存在:
        random.choice(...)                       # stdlib random（当前不可达）
    else:
        np.random.randint(0, 255, (768,768,3))   # numpy 全局流（当前可达）
```

**两个分支，两种未受管控的随机源。** 实测连续两次调用返回的噪声图**不同**。

**严重度**：中 ｜ **可达性**：else 分支当前活跃（`TEXTURE_1K_PATH` 未配置）

**影响**：即使 `SceneRandomizer` 已 seed，贴图选择仍不可复现。影响视觉域随机化的可复现性，不影响物体位姿。

**为什么未修**：`get_random_texture` 是模块级函数，没有 `self.rng` 可用；修它要改公共签名，牵连全部 4 个调用方（`task_base/airbot_task_base.py:110`、`randomization.py:553`、`examples/tasks_airbot_play/place_coffeecup.py`、`utils/__init__.py:140` 导出）。

**状态**：⏸ 未修，由 `tests/simulation/test_determinism.py::test_texture_randomization_respects_seed` 的 `xfail(strict=True)` 守着。修好后 XPASS 报 FAILED，强制撤标记。

> 📌 **关键认知：随机性是从 import 边界溜走的。**
> Day 3 的修复范围是 `randomization.py`，而 `randomization.py:553` 调用的 `utils` 函数不知道 rng 的存在。
> **确定性的边界不是「我改过的文件」，而是整条调用链。**

### 9.4 缺陷 U｜`posture_task` 目标跨调用泄漏

**位置**：[mink_solver.py:120](../discoverse/universal_manipulation/mink_solver.py#L120)

**原代码**只在 `reference_qpos is not None` 时设 posture 目标，且 `set_target_from_configuration` **也在 if 块内** —— 不传 reference 时根本不设，于是沿用上一次。

**实测**（同一 target/qpos 连续三次调用）：

```
第1次(无ref):  [3.84020671e-06, -7.16114078e-01, 1.00542549e+00]
第2次(有ref):  [4.42028460e-06, -7.16113819e-01, 1.00542520e+00]
第3次(无ref):  [4.42028460e-06, -7.16113819e-01, 1.00542520e+00]  ← 跟着第2次，没回到第1次
```

**第 1 次与第 3 次输入完全相同，输出却不同。**

**严重度**：中 ｜ **影响**：任务序列（抓→抬→移→放）中某一步传了 reference，后续所有步骤沿用它，而调用方毫不知情。与 seed 缺陷同类 —— **隐藏状态让「相同输入」得到「不同输出」**。

**修复对应两个独立契约**：

| 改动 | 作用 |
|---|---|
| 把 `set_target_from_configuration` 挪出 if 块 | **消除泄漏** |
| 补 else 分支恢复 `_default_posture_qpos` | **保持原有默认姿态** |

⚠️ 第二点**不是修泄漏**：挪出 `set_target` 后有没有 else 都不泄漏。else 决定「默认姿态取谁」—— 无 else 时 `temp_config` 保持 `mink.Configuration` 的默认值 **qpos0**（airbot_play 全 0），与 home（`[0,-1,1.2,1.5708,-1.2,-1.5708]`）差得很远，影响冗余自由度下的解选择。**那是行为变更，不是修复。**

**⚠️ 同时证伪**：计划文档记载的「`self.configuration` 状态泄漏，需 `try/finally`」**不成立** —— [solve_ik:99](../discoverse/universal_manipulation/mink_solver.py#L99) 每次入口 `configuration.update(current_qpos)` 已隔离它，两次同参调用解逐位相同。

**状态**：✅ 已修 `c722ca8`，3 条回归测试守着

> 📌 **状态泄漏的判定标准**：不是「对象有可变字段」，而是
> **「调用 N 次后的输出，是否只由第 N 次的输入决定？」**
>
> | 字段 | 每次入口重置 | 泄漏 |
> |---|---|---|
> | `self.configuration` | ✅ 被 `current_qpos` 覆盖 | ❌ |
> | `posture_task` target | ❌ 只在给 reference 时更新 | ✅ |

### 9.5 缺陷 H 根因查明（待决策，不改数字）

逐个遍历 MJCF 的 `jnt_type`，**4 个模型零个 FREE 关节**，推翻原猜测。真因是**夹爪建模复杂度超出配置作者的假设**：

| 机器人 | 臂 | 夹爪 | 实际 nq | YAML | 差 |
|---|---|---|---|---|---|
| arx_x5 | 6 HINGE | 2 SLIDE（`finger_joint1/2`） | 8 | 7 | 1 |
| piper | 6 HINGE | 2 SLIDE | 8 | 7 | 1 |
| rm65 | 6 HINGE | 6 HINGE + 2 SLIDE | 14 | 12 | 2 |
| **iiwa14** | **7 HINGE** | **8 HINGE** | **15** | **9** | **6** |

**iiwa14 的夹爪**是 Robotiq 式平行连杆机构：`left/right` 各 4 个 `driver` / `coupler` / `spring_link` / `follower` 关节，由约束耦合成 **1 个物理自由度**，但每根连杆各占 1 个 qpos。YAML 按「2 根手指」计数得 9。

**⚠️ 待决策，故不改数字**：`qpos_dim` 的语义未定义 —— 指模型 `nq`（15），还是可控自由度（7 臂 + 1 夹爪 = 8）？连杆是**被约束的从动关节**，算 1 个还是 8 个取决于定义。**在有共识之前改数字只是把一个错误换成另一个错误。**

**状态**：🔍 xfail reason 已从「原因不明」升级为「根因已知 + 待决策点明确」

> 📌 **`ctrl_dim` 9/9 全对，`qpos_dim` 4/9 出错** —— 写错 `ctrl_dim` 立刻 `ValueError`；写错 `qpos_dim`，`qpos[:9]` 在 `nq=15` 上完全合法，静默丢掉后 6 个。
>
> **「哪里没有反馈，哪里就有缺陷。」测试的本质工作，就是给原本不会炸的地方装上会炸的机制。**

### 9.6 缺陷 T｜库代码用 print 代替 logging

**位置**：多处（`envs/simulator.py:22` 附近、`randomization.py` 全文、`utils/__init__.py:95`）

- `ModuleNotFoundError` 的完整 traceback 打在 **stderr**，配套 `Warning: gaussian_splatting renderer not found` 打在 **stdout** —— 同一件事拆到两个流
- `exec_randomization` 往 stdout 刷 emoji 日志且无法关闭

**影响**：**真错误和假错误在输出里长得一模一样。** CI 日志里混进一条真的 `ModuleNotFoundError`，没人会注意到。无法按级别过滤。

**严重度**：低 ｜ **状态**：⏸ 未修

### 9.7 Day 3-4 的处理顺序修正

原第八节按「影响 × 修复成本」排序。实测后建议插入一条新维度：**谁会干扰谁的验证**。

缺陷 J 被插到 seed 修复之前，**不是因为它更严重**，而是因为碰撞半径不对 → 重叠判定不对 → 重试次数不对 → 随机数消耗次数不对，会让 seed 修复的验证结果变成两个缺陷的叠加。

> 📌 **一次只改一个变量。** 两个缺陷同时在场时无法归因。
> 这也是为什么分多次 commit —— `git bisect` 只有在一个 commit 做一件事时才有用。
