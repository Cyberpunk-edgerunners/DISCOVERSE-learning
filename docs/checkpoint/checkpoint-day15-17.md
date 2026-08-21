# Checkpoint · Day 15-17（2026-08-19）

> 上一站：[checkpoint-day13-14.md](checkpoint-day13-14.md)
> 本站产出：`tests/mobile_manipulation/`（34 用例）、1 条真缺陷、1 个度量脚本
> 下一站：Day 18-19 数据质量验证器

---

## 一、下次开工第一件事

```bash
# 0) 环境（每个新终端都要）
PY=~/miniconda3/envs/discoverse/bin/python
#    ⚠️ 若 shell source 过 ROS，所有 pytest 命令前加 env -u PYTHONPATH

# 1) 基线核实
env -u PYTHONPATH MUJOCO_GL=osmesa $PY -m pytest tests/ -q | tail -2
#    预期：173 passed, 4 skipped, 45 deselected, 17 xfailed

# 2) 工作区干净
git diff --stat discoverse/configs/
#    预期：空

# 3) lint
env -u PYTHONPATH $PY -m ruff check tests/
#    预期：All checks passed!
```

⚠️ **本站的改动尚未提交**（见 §八）。

---

## 二、Day 15-17 成果【已核实】

| 产出 | 位置 | 验证方式 |
|---|---|---|
| 运动学测试 | `tests/mobile_manipulation/test_mmk2_kinematics.py` | 13 例（含 1 xfail），~0.6s |
| 差速底盘测试 | `test_differential_drive.py` | 7 例（含 1 xfail），~4.6s |
| 升降测试 | `test_slide_lift.py` | 9 例，~6.0s |
| 自碰撞测试 | `test_dual_arm_collision.py` | 5 例，~2.0s |
| 共享工具 | `conftest.py` | 坐标变换 / geom 归属 / qpos 寻址 |
| 度量脚本 | `scripts/mmk2_workspace_overlap.py` | 三档分辨率实跑 |

**测试数：141 → 173（+32）**，xfailed 15 → 17

**Docker 复核**（重建镜像，不挂载）：`173 passed ... in 19.32s` ✅

### 发现的缺陷

| 编号 | 缺陷 | 状态 |
|---|---|---|
| **Y** | `MMK2Base.wheel_distance = 0.189`，模型实测 **0.3265**（错 1.73×） | ⚠️ **未修**，xfail 钉住 |
| **Z** | `MMK2FK.__init__` 未初始化 `pos_modifidied` | ⚠️ 未修，xfail 钉住 |
| **AA** | `mmk2_ik.py:15` 裸 `except:` + `.npz` 缓存无版本戳 | **风险非缺陷**（实测 maxdiff=0），已加回归护栏 |
| **文档** | `CLAUDE.md` 19 维动作布局从第 11 位起错位 | ✅ **已修** |

---

## 三、⭐ 缺陷 Y 速查（下次要用 / 面试会讲）

### 现象

```
里程计推算 vs MuJoCo 真值（4000 步）
torque(1.0, 1.0)   yaw 误差 0.0005 rad     ← 直线几乎完美
torque(1.0, 0.5)   yaw 误差 0.5584 rad
torque(1.0,-1.0)   yaw 误差 1.9440 rad     ← 原地旋转错 111°
```

### 定位

```
误差比 4.6005 / 2.6565 = 1.7318
MJCF 实测轮距 0.16325 × 2 = 0.3265
0.3265 / 0.189            = 1.7275        ← 吻合
```

### 验证

```
wheel_distance=0.1890  →  yaw 误差 1.9440 rad
wheel_distance=0.3265  →  yaw 误差 0.0066 rad      ← 改善 294 倍
```

### ⚠️ 为什么不修（重要，别下次手贱改了）

`grep -rn "wheel_distance" --include=*.py .` → **4 个 ROS 遥操作文件**在用：

```python
# examples/ros{1,2}/mmk2_ros{1,2}{,_joy}.py
v_left = (v - ω * wheel_distance) / wheel_radius
#              ↑ 标准公式应是 ω * L / 2 —— 它们【没有除以 2】
```

**语义矛盾**：里程计按「全轮距」用，ROS 按「半轮距」用。

| 取值 | 里程计 | ROS |
|---|---|---|
| 0.189（现状） | 错 73% | 错 15.7% |
| 0.3265（"修正"） | ✅ | **错 100%** |

📌 **正确修法**：先重命名消歧义（`wheel_base` / `half_wheel_base`），
再统一取值，且要改 4 个 ROS 文件 —— **需单独 PR 验证**。

---

## 四、⭐ MMK2 接口速查（实测，与 CLAUDE.md 旧版不同）

### 19 维动作布局

```python
action[0:2]    # 左右轮【力矩 N·m】<motor>，ctrlrange ±35
action[2]      # 升降位置 [-0.04, 0.87] ⚠️ 数值越大躯干越【低】
action[3]      # head_yaw   [-0.5, 0.5]
action[4]      # head_pitch [-1.18, 0.16]
action[5:11]   # 左臂 6 轴
action[11]     # 左夹爪（1 个 tendon 执行器，0=闭 1=开）
action[12:18]  # 右臂 6 轴
action[18]     # 右夹爪
```

⚠️ 旧 CLAUDE.md 写 `[11:17]` 右臂、`[17:19]` 双夹爪 —— **从第 11 位起错位一格**。
已由 `test_actuator_layout_is_pinned` 钉死。

### qpos 布局（nq=28, nv=27, nu=19）

| 内容 | 下标 |
|---|---|
| 底盘自由关节 | `qpos[0:7]`（3 位置 + 4 四元数）⚠️ 占 7 个 qpos 但只占 6 个 qvel |
| 左右轮转角 | `qpos[7:9]` |
| **升降** | **`qpos[9]`** ⚠️ 不是 `qpos[2]`（那是底盘 Z） |
| 头部 | `qpos[10:12]` |

📌 **索引 qpos 永远用 `model.jnt_qposadr[jid]`，别数格子。**

### 坐标系与约定

| 项 | 值 |
|---|---|
| `MMK2FK.get_*_endeffector_pose()` | **world 系**，四元数 `wxyz` |
| `MMK2IK.armIK_wrt_footprint()` | **footprint 系**，吃 3×3 旋转矩阵 |
| scipy `Rotation.from_quat` | 要 `xyzw` → 转换用 `quat[[1,2,3,0]]` |
| `arm` 取值 | `'l'` / `'r'`（**不是** `'left'`） |
| slide 符号 | `mmk2_ik.py:63` 是 `tmat[2,3] -= slide` |

### 实测容差基准

| 项 | 实测 | 建议断言 |
|---|---|---|
| FK→IK 往返 | 9.7e-05 rad | `< 1e-3`（10 倍余量） |
| 升降稳态误差 | **6.06 mm**（恒定，重力下垂） | `< 10 mm` |
| 升降稳定时间 | 2000 步（4s） | 跑 5000 步 |
| 里程计（正确轮距） | yaw 0.0066 rad | `< 0.05` |
| 直线度 | 0.05% | `< 5%` |

---

## 五、⭐ 方法论收获（面试可直接用）

1. **仿真里最容易错的是「描述物理的常数」** —— 不崩溃、不抛异常、不留痕迹
2. ⭐ **测试若引用被测常量，就无法证伪该常量** —— 轮距要从 MJCF 现算
3. ⭐⭐ **空转绿测试比红测试危险** —— 红的有人看，空转的制造虚假覆盖
4. **让测试先失败一次**：元测试 / 前置断言 / 变异测试，是同一件事的三种形式
5. ⭐ **恒等陷阱** —— 底盘在原点时 world 系与 footprint 系恰好相等，
   于是「忘了坐标变换」的实现完美通过
6. ⭐ **误差的结构比大小更有信息量** —— 6.06mm 单看是「超标」，
   「六位小数全相同」告诉你是系统偏置而非噪声
7. ⭐ **被乘以 0 的项** —— 直线时 `Δs_r - Δs_l = 0`，轮距错得再离谱也看不出；
   **AGV 轮距标定必须用原地旋转**
8. **一个变量被两处按不同语义使用时，没有任何单一取值是对的**
9. **结构比命名可靠** —— geom 名字可缺失（62/73 无名），body 父子关系由模型强制
10. ⭐ **性能优化、容差、阈值，每个数字都必须来自测量** —— 今天我自己错了 4 次
11. **拒绝实现一个测试也是产出** —— 阈值可被「选」成任何结论的断言是纯负债
12. **不为想象中的需求扩接口** —— `FailureMode` 等真有消费者再加

---

## 六、⚠️ 我自己踩的 4 个坑（同一种病）

| 我以为 | 实测 | 危害 |
|---|---|---|
| `mj_resetData` 后四元数要手动补 | 是 `[1,0,0,0]`，不用补 | 错误的解释传给读者 |
| 模型加载 1 秒 | **0.14 秒** | 用假数字论证设计决策 |
| ⭐⭐ 测试合计 55 秒，该打 `slow` | **实测 6 秒** | **差点把缺陷挪出 CI 主线** |
| ⭐⭐ 重叠率随网格失真 | 比值很稳定 | **理由错了但结论对 —— 最难自查** |

⚠️ **四个都不会报错。**代价不是失败，是让你以为自己验证过了。

📌 `pyproject.toml:289` 对 slow 的定义是「**单用例** >10s」——
最慢模块 2.9s 分摊在 5 个用例上，**按项目自己的定义压根不够格**。
**打标记前先读标记的定义。**

---

## 七、遗留问题（按优先级）

| # | 问题 | 说明 |
|---|---|---|
| 1 | **缺陷 Y 未修** | 语义歧义，需重命名 + 改 4 个 ROS 文件，单独 PR |
| 2 | **缺陷 Z 未修** | `MMK2FK` 未初始化属性，有规避方式（先调 `set_*`） |
| 3 | **缺陷报告未登记 Y/Z/AA** | `docs/defect-report.md` 还没写进去 |
| 4 | **`source-notes/` 方案文档未同步** | CLAUDE.md 已修，但方案文档的 Day 15-17 章节仍是错的 API |
| 5 | **`FailureMode` 未扩展** | 提案：`base_pose` / `slide_range` / `self_collision`，等有消费者再加 |
| 6 | **`tests/mobile_manipulation/` 未接进 CI 的专门 job** | 目前随 `pytest tests/` 全量跑，够用 |
| 7 | **缺陷 X（段错误→139）仍未修** | Day 13-14 遗留，仅 `MUJOCO_GL=glfw` 交互模式出现 |
| 8 | **`cover_cup` flake 未修** | Day 13-14 遗留，根因之一是 `cover_cup.yaml` 的 `seed: null` |

---

## 八、⚠️ 未提交的改动

```
 M CLAUDE.md                                    ← 19 维布局修正
 M docs/tutorial/day12-jenkins.md               ← Day 12 遗留
?? tests/mobile_manipulation/                   ← 本站主要产出
?? scripts/mmk2_workspace_overlap.py
?? docs/tutorial/day15-17-mmk2-mobile-manipulation.md
?? docs/log/devil-log-day15-17.md
?? docs/note/devil-note-day15-17.md
?? docs/checkpoint/checkpoint-day15-17.md       ← 本文
?? docs/{checkpoint,log,note}/*day10-11*, *day12*   ← 更早的遗留文档
```

⚠️ **Day 10-11 / Day 12 的 6 个文档也还未跟踪** —— 一并提交时别漏。

建议的提交拆分：

```bash
# ① 测试主体
git add tests/mobile_manipulation/ scripts/mmk2_workspace_overlap.py CLAUDE.md
git commit -m "test(mmk2): 新增移动操作专项测试，抓到轮距常量缺陷（Day 15-17）"

# ② 文档
git add docs/
git commit -m "docs: Day 10-17 教程/实录/笔记/checkpoint"
```

---

## 九、与计划文档的差异【已核实】

| 计划文档 | 实际 | 原因 |
|---|---|---|
| `import get_armjoint_pose_wrt_footprint` / `solve_mmk2_ik` | **两个函数都不存在** | 是类方法，签名也完全不同 |
| `arm='left'` | `'l'` / `'r'` | 传 `'left'` 抛 `ValueError` |
| `action[0]=0.5` 当轮速 | **力矩 N·m** | `<motor>` 执行器 |
| `abs(d[0])/abs(d[1])` 算直线度 | 分子分母写反 | 机器人沿 +x 走 |
| `qpos[2]` 是升降 | `qpos[9]` | `qpos[2]` 是底盘 Z |
| 升降容差 `< 5mm` | 实测 **6.06mm** | 重力下垂，改用 10mm + 一致性断言 |
| `if "left_arm" in geom1` | **62/73 geom 无名** | 改用 body 祖先链 |
| 工作空间重叠率断言 `> 30%` | **拒绝实现** | 分母口径可选，结论对分辨率敏感 → flaky |
| 预估 4 个模块 19 用例 | 34 用例 | `parametrize` 展开 |

📌 **计划文档 §Day 15-17 的示例代码没有一行能直接跑。**
这张表本身是交付物之一。

---

## 十、文档产出

| 类型 | 文件 |
|---|---|
| 教程 | `docs/tutorial/day15-17-mmk2-mobile-manipulation.md`（约 1400 行） |
| 实录 | `docs/log/devil-log-day15-17.md` |
| 笔记 | `docs/note/devil-note-day15-17.md` |
| 本文 | `docs/checkpoint/checkpoint-day15-17.md` |

⚠️ **本站没写「逐行解析」补充文档**（Day 12、Day 13-14 有）。
今天的代码以测试为主，逻辑都在断言里且已带注释，逐行价值不高。
若面试需要，优先补的是**缺陷 Y 的完整复现脚本**。

---

## 十一、下一站：Day 18-19 数据质量验证器

**主题**：对应「策略学习的数据是产品」这个具身智能核心命题。

### 今天留给它的两样东西

**① 结果契约（Day 13-14）+ 移动操作的失败模式提案**

```python
# 建议新增（等真有消费者再加）
base_pose       # 底盘没到位 → 查里程计、导航、地面摩擦
slide_range     # 升降行程不够 → 目标超出 [-0.04, 0.87]
self_collision  # 双臂/臂-躯干干涉 → 查轨迹规划、协同顺序
```

**② 里程计推算能力**

```
今天：轮子编码器 → 差速运动学 → 推算位姿 → 与真值比对
Day 18-19：推算位姿序列 → 速度/加速度 → 轨迹平滑度指标
```

⚠️ **提醒 Day 18-19 的自己**：**别用 `MMK2Base.wheel_distance`**，它是错的（缺陷 Y）。
用 `conftest.py` 的 `wheel_geometry` fixture（从 MJCF 现算），
或直接用 `qpos[0:3]` 真值。

### ⚠️ 计划文档 §7.1 的 `ValidationResult` 有已知毛病

Day 13-14 已指出：`threshold` 字段一处塞 str 一处塞 float。
**Day 18-19 应复用 `discoverse/testing/` 的契约，而非另起炉灶。**

---

## 十二、一句话交接

> **今天证明了一件事：仿真里最容易错的不是物理，是那些「描述物理的常数」。
> 因为常数不会崩溃、不会抛异常、不会在直线上暴露 ——
> 它只在你转弯的时候，悄悄把 111 度当成 152 度告诉你。**
