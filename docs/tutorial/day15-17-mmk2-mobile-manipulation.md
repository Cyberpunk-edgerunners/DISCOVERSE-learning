# Day 15-17 — MMK2 双臂轮式专项：把工业机器人的验证思维搬进仿真

> 上接 [day13-14-result-contract.md](day13-14-result-contract.md)
> 本课产出：`tests/mobile_manipulation/` 4 个测试模块 + 1 条**真缺陷**（`wheel_distance` 错 1.73 倍）
> 服务对象：Day 18-19（数据质量验证）
> 预计耗时：约 12 小时（三天）
> ⚠️ **本文所有数值都是我先跑过一遍实测出来的**，计划文档里的示例代码**没有一个能直接跑**

---

## 今天到底在干嘛（先建立直觉）

前 14 天你做的事，本质上都是**「测试基础设施」**：

```
Day 2      pytest 骨架
Day 3-5    确定性 + flake 采样
Day 8-9    Docker 镜像
Day 10-12  GitHub Actions + Jenkins
Day 13-14  结果契约
```

这些东西**换个项目也能用** —— 它们不关心被测的是机器人还是电商网站。

今天不一样。今天第一次做**「只有机器人项目才需要的测试」**：

> **验证这台机器人的运动学、里程计、执行器，在仿真里的行为是否自洽。**

### ⭐ 为什么这一段最值钱

因为它是**唯一一段你的工业机器人背景能直接换算成筹码的内容**。

前面 14 天的产出，一个纯 CI/DevOps 工程师也做得出来。而今天要做的四件事：

| 今天做的 | 工业机器人里对应的 |
|---|---|
| FK→IK→FK 往返一致性 | 运动学标定验收 |
| 差速里程计推算 vs 真值 | AGV 里程计标定 |
| 升降轴定位精度 | 重复定位精度测试 |
| 双臂自碰撞检测 | 干涉检查 / 安全区规划 |

**这四件事你在真机上都做过。**今天只是把量具从激光跟踪仪换成 `mj_data.qpos`。

### 今天的一句话总结（先记住，最后再回来看）

> **仿真里的「真值」是免费的 —— 你能同时拿到「机器人以为自己在哪」和「机器人实际在哪」。
> 真机上要花几万块的标定实验，在这里就是两行 `numpy`。
> 所以仿真测试的重点不是「测机器人」，是「测那些描述机器人的常数对不对」。**

而今天最大的收获正是这个：**我们会抓到一个错了 1.73 倍的常数。**

---

## ⚠️ 开课前必读：今天会踩的 15 个坑（11 个来自计划文档 + 4 个我自己的）

我已经**全部踩过一遍**了。下表每一条都附了实测证据。

| # | 坑 | 后果 | 在哪讲 |
|---|---|---|---|
| 1 | ⭐ **计划文档的 API 全是编的** | `ImportError`，一行都跑不了 | Step 1.1 |
| 2 | **`MMK2FK` 有未初始化属性** | 直接读位姿 → `AttributeError` | Step 1.2 |
| 3 | **`MMK2FIK` 已弃用** | 构造时打印黄色告警，该用 `MMK2IK` | Step 1.3 |
| 4 | ⭐⭐ **FK 返回世界系，IK 吃 footprint 系** | 底盘在原点时**恰好**通过，一挪就炸 | Step 2.3 |
| 5 | **四元数约定不一致** | FK 给 `wxyz`，scipy 要 `xyzw` | Step 2.2 |
| 6 | ⭐ **CLAUDE.md 的 19 维动作布局是错的** | 从第 11 位起全错位 | Step 3.1 |
| 7 | ⭐⭐ **轮子是力矩控制不是速度控制** | 计划文档的直线测试前提不成立 | Step 3.2 |
| 8 | **计划文档把横纵轴搞反了** | 直线度公式会除以 0 | Step 3.3 |
| 9 | ⭐ **升降稳态误差 6.06mm > 计划的 5mm 容差** | 照抄计划文档，测试必红 | Step 4.2 |
| 10 | ⭐⭐ **73 个 geom 里 62 个没名字** | 计划的字符串匹配**永远匹配不到** → 空转绿测试 | Step 5.1 |
| 11 | **`qpos[2]` 不是升降** | 那是底盘 Z，升降在 `qpos[9]` | Step 4.1 |

### ⭐ 另外 4 个坑是**我自己写这篇教程时踩的**

它们没有一个来自计划文档 —— 全部来自「我以为我知道」。
我把它们原样留在文中，因为**它们的形态比前 11 个更常见**：

| # | 我以为 | 实测 | 在哪讲 |
|---|---|---|---|
| 12 | `mj_resetData` 后四元数是 `[0,0,0,0]`，要手动补 | 是 `[1,0,0,0]`，**不用补** | Step 6.2 |
| 13 | 模型加载要 1 秒，所以要 `scope="session"` | **0.14 秒**，原理由不成立（结论仍保留，但换理由） | Step 6.2 |
| 14 | ⭐⭐ 测试合计 55 秒，太慢，要打 `slow` 标记 | **实测 6 秒**，高估 9 倍；打标记会让缺陷在日常 CI 里隐身 | Step 6.3 |
| 15 | ⭐⭐ 工作空间重叠率「随网格步长失真」 | **比值相当稳定**（0.10 与 0.06 档均 48.1%）；真正的问题是**分母口径** | Step 5.5 |

> ⭐ **四个都是同一种错误：用「合理的猜测」代替「一条命令的测量」。**
> 而且四个都**不会报错** —— 多余的赋值无害，过大的 fixture scope 无害，
> `slow` 标记也不会让任何测试变红，写错的理由更是连代码都不碰。
> **它们的代价不是失败，是让你以为自己验证过了。**

📌 **第 15 条尤其值得看**：我用一条错误的理由，得出了一个**正确的结论**
（不该写成断言）。理由错了但结论对 —— 这种情况最难自查，
因为**结果看起来没问题，没有任何东西会提醒你回头。**
实测之后我才找到真正的理由，而那条理由比原来的**硬得多**。

### ⚠️ 计划文档 §Day 15-17 要改的地方（全部）

| 计划文档写的 | 实测 | 结论 |
|---|---|---|
| `from ... mmk2_fk import get_armjoint_pose_wrt_footprint` | 该模块里只有 `class MMK2FK` | **函数不存在** |
| `from ... mmk2_fik import solve_mmk2_ik` | 只有 `class MMK2FIK` 的方法 | **函数不存在** |
| `pose1 = get_armjoint_pose_wrt_footprint(joint_angles, arm='left')` | 真实签名吃 `point3d, action, arm, slide` | 参数完全对不上 |
| `arm='left'` | 真实取值是 `'l'` / `'r'` | 传 `'left'` 抛 `ValueError` |
| `action[0]=0.5` 当轮速 | `<motor>` 执行器，单位是 **N·m** | 语义错 |
| `straightness = abs(d[0])/abs(d[1])` | 机器人沿 **+x** 前进 | 分子分母写反 |
| `actual_h = mj_data.qpos[2]` | `qpos[2]` 是底盘 Z | 应为 `qpos[9]` |
| `assert abs(actual_h - h) < 0.005` | 稳态误差 **0.00606** | **必红** |
| `if "left_arm" in geom1` | 62/73 个 geom 无名 | **恒为 False** |
| `compute_reachable_workspace()` | 不存在 | 得自己写 |

📌 **这张表本身就是今天的一个交付物。**「照着方案文档写代码，发现方案文档是错的，
用实测数据把它改对」—— 这是比「写出四个测试」更值得讲的经历。

---

## Step 0｜环境（15 分钟）

和前 14 天一样，两个坑先交待：

### 0.1 用 conda 环境的 python

```bash
PY=~/miniconda3/envs/discoverse/bin/python
```

### 0.2 ⚠️ ROS 污染 PYTHONPATH

```bash
echo $PYTHONPATH     # 若含 /opt/ros/humble → pytest 报 No module named 'lark'
```

全天所有命令统一加 `env -u PYTHONPATH`。

### 0.3 基线

```bash
env -u PYTHONPATH MUJOCO_GL=osmesa $PY -m pytest tests/ -q | tail -2
# 141 passed, 4 skipped, 45 deselected, 15 xfailed      ← 开工前
```

📌 **记住 141。**收工时要能说清楚多出来的每一个测试是干嘛的。

---

## Step 1｜⭐ 先读代码，别信文档（60 分钟）

### 1.1 第一个坑：计划文档的 API 是编的

计划文档 §Day 15-17 步骤 1 第一行就是：

```python
from discoverse.robots.mmk2.mmk2_fk import get_armjoint_pose_wrt_footprint
from discoverse.robots.mmk2.mmk2_fik import solve_mmk2_ik
```

**先别 `pip install`，先 `grep`：**

```bash
grep -n "^def \|^class \|^    def " discoverse/robots/mmk2/*.py
```

实测输出：

```
mmk2_fk.py:8:class MMK2FK:
mmk2_fk.py:111:    def get_left_endeffector_pose(self):
mmk2_fk.py:125:    def get_right_endeffector_pose(self):
mmk2_ik.py:9:class MMK2IK:
mmk2_ik.py:43:    def armIK_wrt_footprint(self, position, rotation, arm, slide, q_ref=np.zeros(6)):
mmk2_fik.py:7:class MMK2FIK:
mmk2_fik.py:111:    def get_armjoint_pose_wrt_footprint(self, point3d, action, arm, slide, q_ref, action_rot):
```

三件事对不上：

1. **没有 `get_armjoint_pose_wrt_footprint` 这个自由函数** —— 它是 `MMK2FIK` 的**方法**
2. **没有 `solve_mmk2_ik`** —— 完全虚构
3. 就算把方法名接上，**签名也对不上**：计划文档以为它是 `(joint_angles, arm)`，
   真实签名是 `(point3d, action, arm, slide, q_ref, action_rot)` —— 它吃的是**目标点 + 动作类型**，
   不是关节角

> ⭐ **方法论：任何「照着文档写测试」的任务，第一步都是 `grep` 而不是 `import`。**
> 文档描述的是**作者以为的代码**，`grep` 给的是**实际的代码**。
> 这两者的差值，往往就是缺陷藏身的地方。

### 1.2 ⚠️ 第二个坑：`MMK2FK` 有个没初始化的属性

先跑一下最朴素的用法：

```python
from discoverse.robots.mmk2.mmk2_fk import MMK2FK
fk = MMK2FK()
fk.get_left_endeffector_pose()
```

实测：

```
model loaded, nq= 28 nu= 19 nv= 27
AttributeError: 'MMK2FK' object has no attribute 'pos_modifidied'
```

看源码 [mmk2_fk.py:9-13](discoverse/robots/mmk2/mmk2_fk.py#L9-L13)：

```python
def __init__(self, mjcf_path=None):
    ...
    self.mj_model = mujoco.MjModel.from_xml_path(mjcf_path)
    self.mj_data  = mujoco.MjData(self.mj_model)
    # ← 没有 self.pos_modifidied = True
```

而每个 getter 都写着 [mmk2_fk.py:118](discoverse/robots/mmk2/mmk2_fk.py#L118)：

```python
if self.pos_modifidied:      # ← 属性只在 setter 里被创建
    self.forward_kinematics()
```

**所以必须先调至少一个 `set_*`，才能调 `get_*`。**

顺带注意拼写：`pos_modifidied`（少了个 `f`，多了个 `i`）。这个拼写贯穿全文件，
**不要「顺手修正」** —— 改了会把所有 setter 一起打断。

📌 **这是个真缺陷，但今天不修。**今天只在测试里用 `pytest.fixture` 保证调用顺序，
并写一条 `xfail` 把它钉住。理由：修它要动上游文件，而它有明确的规避方式；
今天的主线是里程计那条**没有规避方式**的缺陷。

### 1.3 ⚠️ 第三个坑：`MMK2FIK` 已被弃用

```python
MMK2FIK()
# 接口即将弃用, 请使用discoverse.robots.mmk2_ik      ← 黄色告警
```

见 [mmk2_fik.py:72](discoverse/robots/mmk2/mmk2_fik.py#L72)。

两者的差别不只是「新旧」：

| | `MMK2FIK`（旧） | `MMK2IK`（新） |
|---|---|---|
| 变换矩阵 | **硬编码常量**（`mmk2_fik.py:8-31`） | 从 `mmk2_ik_tmats.npz` 加载，缺失则从 MJCF 重算 |
| 目标姿态 | `action` 字符串（`"pick"`/`"carry"`/`"look"`）查表 | 直接吃 3×3 旋转矩阵 |
| 适合做什么 | 任务脚本（语义化） | **测试**（能表达任意姿态） |

**今天用 `MMK2IK`。**理由：往返一致性测试需要喂**任意姿态**，
而旧接口只能从三个预设动作里挑一个 —— 那测的就不是运动学了，是那张查找表。

### 📖 补充知识：`mmk2_ik_tmats.npz` 的隐患

[mmk2_ik.py:13-19](discoverse/robots/mmk2/mmk2_ik.py#L13-L19)：

```python
try:
    tmats = np.load(".../mmk2_ik_tmats.npz")
except:                                    # ← 裸 except
    print("Failed to load mmk2_ik_tmats.npz")
    tmats = self.generate_tmats()
    np.savez(".../mmk2_ik_tmats.npz", **tmats)
```

两个问题：

1. **裸 `except:`** 会吞掉 `KeyboardInterrupt`、`MemoryError`，也会把「文件损坏」
   和「文件不存在」当成同一件事
2. ⭐ **缓存文件不带版本戳** —— 如果有人改了 MJCF 里的臂基座位置，
   这个 `.npz` **不会失效**，IK 会继续用旧的变换矩阵，**而且不报错**

第 2 条是典型的**静默失效**风险。今天写一条测试钉住它：
从 MJCF 现算一遍，和缓存比对。

⚠️ **先说清楚当前状态：缓存现在是对的。**实测：

```
footprint2chest    maxdiff=0.000e+00  MATCH
chest2lft_base     maxdiff=0.000e+00  MATCH
chest2rgt_base     maxdiff=0.000e+00  MATCH
```

所以这**不是**一条已经发生的缺陷，是一条**没有防护的风险**。

📌 **两者的区别要说清**，别把风险包装成缺陷：

> 「缓存和现算完全一致」**不代表**这个设计是安全的 ——
> 只代表**目前还没有人改过 MJCF**。
> 测试的价值不在于今天它是绿的，而在于**将来有人改 MJCF 时它会变红**。

这类测试有个名字：**回归护栏**（regression guard）。
它今天不抓 bug，它防止明天产生 bug。

---

## Step 2｜FK→IK→FK 往返一致性（150 分钟）

这是你的主场。先把工业机器人那套思维摆出来：

> 往返一致性测的**不是「IK 准不准」**，测的是**「FK 和 IK 用的是不是同一个模型」**。
>
> 真机上这两者可能来自不同部门（FK 来自 URDF，IK 来自厂商固件），
> 参数不一致时，单独看每个都对，串起来就飘。

### 2.1 先跑通最小往返

```python
q = np.array([0.1, -0.2, 0.3, 0.1, 0.2, 0.1])

fk.set_base_pose([0,0,0], [1,0,0,0])
fk.set_slide_joint(0.0)
fk.set_head_joints([0,0])
fk.set_left_arm_joints(q)
fk.set_right_arm_joints(np.zeros(6))
fk.forward_kinematics()

pos, quat = fk.get_left_endeffector_pose()
rot = Rotation.from_quat(quat[[1,2,3,0]]).as_matrix()
q2  = ik.armIK_wrt_footprint(pos, rot, 'l', 0.0, q)
```

实测：

```
FK endpoint pos (world): [0.48993 0.12677 1.23515] quat [0.75859 -0.54908 0.31105 -0.16216]
IK solution: [ 0.10001 -0.2  0.3  0.1001  0.19999  0.0999 ]
joint err  : [ 0.00001 -0.  -0.  0.0001 -0.00001 -0.0001 ]
```

**最大关节误差 9.7e-05 rad。**闭合了。

### 2.2 ⚠️ 四元数约定：`wxyz` vs `xyzw`

上面那行 `quat[[1,2,3,0]]` 不是随手写的：

| 谁 | 约定 |
|---|---|
| MuJoCo / `MMK2FK` 返回值 | `[w, x, y, z]` |
| `scipy.spatial.transform.Rotation.from_quat` | `[x, y, z, w]` |

看 [mmk2_fk.py:122](discoverse/robots/mmk2/mmk2_fk.py#L122)，FK 内部是这么转的：

```python
Rotation.from_matrix(...).as_quat()[[3, 0, 1, 2]]     # xyzw → wxyz
```

所以我们要**反着来**：`[[1,2,3,0]]`（wxyz → xyzw）。

📌 **写反了会怎样？**不会报错。会得到一个**合法但错误**的旋转，
然后 IK 要么解出一个完全不同的姿态，要么抛 `ValueError` 说不可达。
**这是个只能靠往返测试抓出来的错误** —— 单看 FK 或单看 IK 都是对的。

### 2.3 ⭐⭐ 最大的坑：FK 是世界系，IK 是 footprint 系

上面的往返之所以闭合，是因为**底盘恰好在原点**。

我把底盘挪开再试：

```
--- base translated (x=1, y=0.5) ---   err=None (IK FAILED)  pos=[1.48993 0.62677 1.23515]
--- base rotated 90deg yaw ---         err=None (IK FAILED)  pos=[-0.12677 0.48993 1.23515]
```

**两个都炸了。**原因：

- `MMK2FK.get_left_endeffector_pose()` 走的是 `get_site_tmat(...)`，返回的是 **world 系**位姿
- `MMK2IK.armIK_wrt_footprint()` 顾名思义，吃的是 **footprint（底盘）系**位姿

底盘在原点且无旋转时，这两个坐标系**数值上恰好相等**，于是测试通过。
**一旦底盘移动，同样的代码就错了 —— 而且是「静默给出错误答案」或「误报不可达」。**

> ⭐⭐ **这就是「在恒等变换下测试」的经典陷阱。**
> 我在工业机器人上见过一模一样的形态：工具坐标系标定测试永远在 TCP=0 下跑，
> 装上真实夹具才发现整条链路搞错了参考系。

**修法**：测试里显式做变换，别依赖巧合。

```python
def world_to_footprint(pos_w, rot_w, base_pos, base_quat):
    """把世界系位姿转到 footprint 系。"""
    T_w_base = np.eye(4)
    T_w_base[:3, :3] = Rotation.from_quat(np.asarray(base_quat)[[1,2,3,0]]).as_matrix()
    T_w_base[:3,  3] = base_pos
    T_w_ee = np.eye(4)
    T_w_ee[:3, :3] = rot_w
    T_w_ee[:3,  3] = pos_w
    T_base_ee = np.linalg.inv(T_w_base) @ T_w_ee
    return T_base_ee[:3, 3], T_base_ee[:3, :3]
```

📌 **然后必须写一条「底盘非原点」的用例。**
只在原点测，等于没测这条链路。这条用例是今天最有价值的一个测试。

### 2.4 升降轴的符号：沿着 slide 扫一遍

工业机器人经验告诉你：**凡是有耦合轴的地方，先扫一遍看符号**。

实测（左臂，同一组关节角，只改 slide）：

```
slide= 0.00  err=9.74e-05  endpos=[0.48993 0.12677 1.23515]
slide= 0.10  err=9.74e-05  endpos=[0.48993 0.12677 1.13515]
slide= 0.30  err=9.74e-05  endpos=[0.48993 0.12677 0.93515]
slide= 0.50  err=9.74e-05  endpos=[0.48993 0.12677 0.73515]
slide= 0.87  err=9.74e-05  endpos=[0.48993 0.12677 0.36515]
```

两个结论：

1. ⭐ **slide 增大 → 末端 Z 降低**（1.235 → 0.365，正好差 0.87）。
   「lift」这个执行器名字是反直觉的：**数值越大，躯干越低**。
2. **往返误差与 slide 无关**（恒为 9.74e-05）—— 说明 FK 和 IK 对 slide 的符号约定**一致**。

看 [mmk2_ik.py:62-63](discoverse/robots/mmk2/mmk2_ik.py#L62-L63) 就明白了：

```python
tmat = self.TMat_footprint2chest.copy()
tmat[2, 3] -= slide           # ← 减
```

📌 **这条「一致性」正是往返测试的真正价值。**
如果哪天有人把 IK 里的 `-=` 改成 `+=`，单独跑 IK 不会报错（它照样解得出关节角），
只有往返测试会立刻红。

### 2.5 右臂对称性

```
右臂 slide=0.0  err=9.62e-05  pos=[0.48993 -0.12677 1.38685]
右臂 slide=0.3  err=9.62e-05  pos=[0.48993 -0.12677 1.08685]
```

注意左右臂末端 **Z 不同**（1.235 vs 1.387），Y 符号相反。
**别写「左右臂应完全镜像」的断言** —— 实测它们的安装高度就不一样。

> ⭐ **写断言前先测量。**「应该对称」是假设，`1.235 ≠ 1.387` 是事实。

### 2.6 边界行为：不可达 & 非法参数

```
unreachable -> ValueError OK: Invalid target position (arm-local) posi=[3.56648 0.111 3.42298]
bad arm     -> ValueError OK: Invalid arm
```

好消息：`MMK2IK` 在不可达时**抛异常**而不是静默返回垃圾。
这值得写一条测试**钉住**这个行为 —— 防止将来有人「优化」成返回 `None`。

### 2.7 `q_ref` 的影响：实测无影响

```
q_ref=exact    -> jointerr=9.74e-05  sol=[0.10001 -0.2 0.3 0.1001 0.19999 0.0999]
q_ref=zeros    -> jointerr=9.74e-05  sol=[0.10001 -0.2 0.3 0.1001 0.19999 0.0999]
q_ref=negated  -> jointerr=9.74e-05  sol=[0.10001 -0.2 0.3 0.1001 0.19999 0.0999]
```

**三个不同的参考位形，解出同一个答案。**说明底层 `AirbotPlayIK.properIK` 是
**解析解**（选支策略固定），不是数值迭代。

📌 **别写「换 q_ref 会跳到另一个解支」的测试** —— 那是数值 IK 的行为，这里没有。

### 2.8 容差怎么定（面试会问）

实测往返误差量级是 **1e-4 rad**（≈0.006°）。所以：

| 容差 | 评价 |
|---|---|
| `atol=1e-6` | ❌ 必红。这是解析解的浮点残差下限之上 |
| `atol=1e-3` | ✅ **推荐**。比实测大一个量级，留出浮点/平台余量 |
| `atol=1e-2` | ⚠️ 太松，符号错误都可能漏过 |

> ⭐ **定容差的原则：先测量，再取实测值的 10 倍。**
> 拍脑袋定的容差要么天天红（噪声），要么什么都抓不到（空转）。
> 这条原则和 Day 5 定 flake 阈值是同一套思路。

---

## Step 3｜差速底盘：⭐ 今天抓到真缺陷的地方（180 分钟）

### 3.1 ⚠️ 先纠正 CLAUDE.md 的动作布局

`CLAUDE.md` 里写着：

```python
action[0:2]   # 左右轮
action[2]     # 升降
action[3:5]   # 头部
action[5:11]  # 左臂6轴
action[11:17] # 右臂6轴      ← 错
action[17:19] # 左右夹爪      ← 错
```

**实测执行器表**（`mj_id2name` 逐个打印）：

```
 0 lft_wheel_motor    ctrlrange=[-35. 35.]     ← 力矩
 1 rgt_wheel_motor    ctrlrange=[-35. 35.]     ← 力矩
 2 lift               ctrlrange=[-0.04 0.87]
 3 head_yaw           ctrlrange=[-0.5  0.5]
 4 head_pitch         ctrlrange=[-1.18 0.16]
 5..10 lft_joint1..6
11 lft_gripper        trntype=3(tendon)  ctrlrange=[0. 1.]    ← 1 个，不是 2 个
12..17 rgt_joint1..6
18 rgt_gripper        trntype=3(tendon)  ctrlrange=[0. 1.]
```

**正确布局**：

```python
action[0:2]    # 左右轮（力矩 N·m）
action[2]      # 升降（位置，越大越低）
action[3]      # head_yaw
action[4]      # head_pitch
action[5:11]   # 左臂 6 轴
action[11]     # 左夹爪（1 个 tendon 执行器，0=闭 1=开）
action[12:18]  # 右臂 6 轴
action[18]     # 右夹爪
```

交叉验证 —— [mmk2_base.py:178-184](discoverse/robots_env/mmk2_base.py#L178-L184) 自己的打印函数：

```python
print("    left  grp = {}".format(...self.mj_data.ctrl[11:12]...))    # ← 11:12
print("    right arm = {}".format(...self.mj_data.ctrl[12:18]...))    # ← 12:18
print("    right grp = {}".format(...self.mj_data.ctrl[18:19]...))    # ← 18:19
```

**代码是对的，CLAUDE.md 是错的。**从第 11 位起整体错位一格。

> ⭐ **「文档和代码打架，信代码；但两个都要留证据。」**
> 今天写一条测试把这个布局**钉死**（断言执行器名字和索引的对应关系），
> 这样将来谁改了 MJCF，测试会告诉他文档也得改。

顺带两条：
- **升降范围是 `[-0.04, 0.87]`，不是 `[0, 0.87]`** —— 有 4cm 的负向余量
- 夹爪是 `trntype=3`（tendon 传动），**一个执行器带动两根手指**

### 3.2 ⭐⭐ 第七个坑：轮子是力矩控制

计划文档写：

```python
action[0] = 0.5  # 左轮速度
action[1] = 0.5  # 右轮速度
```

**「速度」两个字是错的。**看 [mmk2_control.xml:3-4](models/mjcf/mobile_chassis/mmk2/mmk2_control.xml#L3-L4)：

```xml
<motor name="lft_wheel_motor" class="wheel" joint="lft_wheel_joint"/>
<motor name="rgt_wheel_motor" class="wheel" joint="rgt_wheel_joint"/>
```

`<motor>` 是**力矩执行器**（其余全是 `<position>`）。`ctrl` 的单位是 **N·m**。

实测（左右各给恒定 1.0 N·m）：

```
step    0  xy=[0.      0.]  wheel_qvel=[0.01811 0.01813]
step  500  xy=[0.03132 0.]  wheel_qvel=[0.68288 0.68369]
step 1000  xy=[0.10761 0.]  wheel_qvel=[1.10714 1.10785]
step 1500  xy=[0.21215 0.]  wheel_qvel=[1.37033 1.37082]
step 2000  xy=[0.33419 0.]  wheel_qvel=[1.53353 1.53384]
step 2500  xy=[0.46709 0.]  wheel_qvel=[1.63472 1.63489]
```

**轮速一路往上爬**（0.018 → 1.63 rad/s），在阻尼作用下趋于渐近速度。
恒力矩 ≠ 恒速度。

📌 **这对测试设计的影响是根本性的：**

| 如果是速度控制 | 实际是力矩控制 |
|---|---|
| 可以断言「跑 100 步走 X 米」 | ❌ 位移是时间的非线性函数 |
| 可以直接验证运动学公式 | 必须**从实际轮子编码器读数**推算 |
| 不需要等待稳态 | 需要考虑加速段 |

**所以今天的里程计测试必须这么写**：不预测位移，而是
**读 `qpos[7:9]`（轮子转角）→ 用差速运动学推算位姿 → 和 `qpos[0:3]` 真值比对**。

这恰好就是**真机上里程计标定的做法** —— 你不预测机器人跑多远，
你拿编码器读数算它「以为」自己在哪，再和外部真值（激光跟踪仪 / OptiTrack）比。

### 3.3 ⚠️ 计划文档的直线度公式除以 0

```python
straightness = abs(displacement[0]) / abs(displacement[1])   # 计划文档
assert straightness < 0.05
```

实测机器人沿 **+x 前进**：`xy=[0.60644, 0.00031]`。

代入计划文档的公式：`0.606 / 0.00031 = 1955`，断言 `< 0.05` **必红**。
而且如果侧向漂移恰好为 0，直接 `ZeroDivisionError`。

**分子分母写反了。**正确写法：

```python
lateral      = abs(displacement[1])       # y 是侧向
longitudinal = abs(displacement[0])       # x 是纵向
assert longitudinal > 0.1, "机器人根本没动，测试无意义"    # ← 先证明前提
assert lateral / longitudinal < 0.05
```

📌 **注意那条 `longitudinal > 0.1` 的前置断言。**
没有它的话，「机器人一步没动」会让 `0/0` 或 `0/极小值` **通过**测试 ——
又一个空转绿测试。

> ⭐ **凡是「比值 < 阈值」的断言，都必须先断言分母足够大。**
> 这是我在 Day 5 flake 分析里学到的同一课：**永远先证明测试真的执行了。**

实测直线度：`0.00031 / 0.60644 = 0.05%`，远好于 5% 阈值。

### 3.4 ⭐⭐⭐ 抓到真缺陷：`wheel_distance` 错了 1.73 倍

现在做真正的里程计测试。差速运动学：

```
Δs  = (Δs_left + Δs_right) / 2
Δθ  = (Δs_right - Δs_left) / L        ← L = 轮距
```

常数从 [mmk2_base.py:62-63](discoverse/robots_env/mmk2_base.py#L62-L63) 拿：

```python
wheel_radius   = 0.0838
wheel_distance = 0.189
```

实测（推算位姿 vs MuJoCo 真值）：

```
torque(1.0, 1.0)   odom=[0.898  0.0009 0.0012]  truth=[0.897  0.0005 0.0007]  poserr=0.0015m  yawerr=0.0005rad
torque(1.0, 0.5)   odom=[0.453 -0.401 -1.3216]  truth=[0.578 -0.256 -0.7632]  poserr=0.1916m  yawerr=0.5584rad
torque(1.0,-1.0)   odom=[0.009  0.003 -4.6005]  truth=[0.0001 0.017 -2.6565]  poserr=0.0168m  yawerr=1.9440rad
```

**直线时几乎完美（0.5 mrad），一转弯就崩（1.94 rad ≈ 111°）。**

> ⭐ **这个「直线对、转弯错」的模式，直接指向轮距。**
> 因为直线时 `Δs_right - Δs_left = 0`，**`L` 被乘以了 0** —— 它错得再离谱也看不出来。
> 只有转弯才会暴露它。
>
> **在工业 AGV 上这是常识：轮距标定必须用原地旋转，不能用直线跑。**

算一下比值：`4.6005 / 2.6565 = 1.7318`。

去 MJCF 里量真实轮距：

```bash
lft_wheel_joint body=lft_wheel_link pos=[-0.02371  0.16325  0.082]
rgt_wheel_joint body=rgt_wheel_link pos=[-0.02371 -0.16325  0.082]
```

**真实轮距 = 0.16325 × 2 = 0.3265 m。**

```
0.3265 / 0.189 = 1.7275        ← 和误差比 1.7318 吻合
```

**验证**：用 0.3265 重跑：

```
--- wheel_distance=0.1890 (MMK2Base 常量) ---
   torque(1.0, 0.5)  yaw_odom=-1.3216  yaw_true=-0.7632  err=0.5584  | poserr=0.1916
   torque(1.0,-1.0)  yaw_odom=-4.6005  yaw_true=-2.6565  err=1.9440  | poserr=0.0168

--- wheel_distance=0.3265 (模型实测) ---
   torque(1.0, 0.5)  yaw_odom=-0.7650  yaw_true=-0.7632  err=0.0019  | poserr=0.0016
   torque(1.0,-1.0)  yaw_odom=-2.6631  yaw_true=-2.6565  err=0.0066  | poserr=0.0003
```

**偏航误差从 1.9440 rad 降到 0.0066 rad —— 改善 294 倍。**

📌 **缺陷成立。**`discoverse/robots_env/mmk2_base.py:63` 的 `wheel_distance = 0.189`
与 MJCF 模型不符，应为 `0.3265`。

### 3.5 ⭐ 缺陷的影响范围（这一步不能省）

抓到缺陷别急着改，**先查谁在用**：

```bash
grep -rn "wheel_distance" --include=*.py .
```

```
examples/ros1/mmk2_ros1.py:68        (msg.linear.x - msg.angular.z * self.wheel_distance) / self.wheel_radius
examples/ros1/mmk2_ros1_joy.py:120   ...
examples/ros2/mmk2_ros2.py:144       ...
examples/ros2/mmk2_ros2_joy.py:127   ...
discoverse/robots_env/mmk2_base.py:63
```

**4 个 ROS 遥操作文件在用它做 `cmd_vel` 逆解。**

也就是说：**任何通过 ROS 给 MMK2 发角速度指令的人，拿到的实际转速都是期望值的 1.73 倍。**
这不是「测试里的一个数不对」，是**用户可见的行为缺陷**。

⚠️ **但注意公式本身还有第二个问题**：标准差速逆解是

```
v_left  = (v - ω·L/2) / r        ← 除以 2
```

而这 4 个文件写的是 `- ω * wheel_distance`，**没有除以 2**。
所以如果 `wheel_distance` 原本被当成「半轮距」（0.16325），那 `0.189` 仍然错，
只是错 15.7% 而非 73%。

> ⭐ **这就是为什么「只改常量」是危险的修法。**
> 这个变量的**语义本身是模糊的** —— 是轮距还是半轮距？
> 里程计代码按「全轮距」用，ROS 代码按「半轮距」用。
>
> **正确的修法是先消除歧义**（重命名为 `wheel_base` / `half_wheel_base`），
> 再统一取值。今天先写测试**钉住实测值 0.3265**，把缺陷登记进缺陷报告，
> 修法留给专门的 PR —— 因为它要改 ROS 文件，需要单独验证。

📌 **今天的测试策略**：
- 里程计测试用**从 MJCF 现算的轮距**（`2 × |body_pos[1]|`），断言误差 < 0.05 rad
- 另写一条 `xfail` 测试：断言 `MMK2Base.wheel_distance == 实测轮距` —— 钉住缺陷

---

## Step 4｜升降轴定位精度（90 分钟）

### 4.1 ⚠️ `qpos[2]` 不是升降

计划文档写 `actual_h = mj_data.qpos[2]`。

实测关节表：

```
 0 <unnamed>          type=0(free)  qposadr= 0        ← 底盘自由关节，占 qpos[0:7]
 1 lft_wheel_joint    type=3(hinge) qposadr= 7
 2 rgt_wheel_joint    type=3(hinge) qposadr= 8
 3 slide_joint        type=2(slide) qposadr= 9  range=[-0.04 0.87]     ← 升降在这
```

`qpos[2]` 是**底盘的 Z 坐标**（实测静止时 `0.0`）。升降是 **`qpos[9]`**。

> ⭐ **自由关节占 7 个 qpos（3 位置 + 4 四元数）但只占 6 个 qvel。**
> 这就是 `nq=28` 而 `nv=27` 的原因。
> **索引 qpos 时永远用 `mj_model.jnt_qposadr[jid]`，别数格子。**

正确写法：

```python
jid  = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, "slide_joint")
adr  = m.jnt_qposadr[jid]
actual = d.qpos[adr]
```

### 4.2 ⭐ 第九个坑：稳态误差 6.06mm，计划文档的 5mm 容差必红

计划文档：

```python
assert abs(actual_h - h) < 0.005   # 5mm 容差
```

实测（每个目标跑到稳态）：

```
target= 0.000  after 5000 steps  qpos[9]= 0.00606  err= 0.006063
target= 0.200  after 5000 steps  qpos[9]= 0.20606  err= 0.006063
target= 0.500  after 5000 steps  qpos[9]= 0.50606  err= 0.006063
target= 0.870  after 5000 steps  qpos[9]= 0.87040  err= 0.000399
target=-0.040  after 5000 steps  qpos[9]=-0.03394  err= 0.006063
```

**稳态误差恒为 0.006063 m = 6.06 mm > 5 mm。照抄计划文档，测试必红。**

⭐ **但关键是：这是不是缺陷？**

看误差的**结构**：

1. **每个目标的误差完全相同**（0.006063，六位一致）
2. **符号恒为正**（实际位置总是比目标**大**）
3. **只有 0.87 例外**（0.0004）—— 因为它撞上了关节上限，被硬约束挡住了

**这不是随机噪声，是恒定偏置。**

结合 Step 2.4 的发现（**slide 越大躯干越低**），正偏置 = 躯干比目标**略低** =
**重力把它拽下来了**。`<position>` 执行器是比例控制器，
稳态下必须留一个位置偏差来产生抵抗重力的力：

```
误差 = 重力负载 / kp
```

📌 **结论：这是位置伺服的固有下垂（droop），不是缺陷。**
真机上也一样 —— 任何没有积分项的位置环都有静差。

**所以正确的做法不是把容差放宽到 10mm 就完事**，而是：

```python
# ① 定位精度：容差按实测定，10mm（实测 6.06mm，留 65% 余量）
assert abs(actual - target) < 0.010

# ② ⭐ 更有价值的断言：偏置的一致性
#    重力下垂应该是恒定的；如果某个高度突然不一样，说明有卡滞/碰撞
errors = [measure(h) - h for h in [0.0, 0.2, 0.5]]
assert np.ptp(errors) < 1e-4, f"下垂不一致，可能存在卡滞: {errors}"
```

> ⭐⭐ **这是今天第二个方法论收获：**
> **「误差的结构比误差的大小更有信息量。」**
> 6.06mm 单独看只是「差一点」；「六位小数完全相同」告诉你这是系统偏置而非噪声，
> 于是你知道该去找伺服增益，而不是去找随机源。
>
> 这和 Day 5 区分 flake（随机）和 bug（确定）是同一套思路。

### 4.3 稳定时间

```
target=0.200  after  500 steps  err=0.009923      ← 还在动
target=0.200  after 2000 steps  err=0.006070      ← 基本稳了
target=0.200  after 5000 steps  err=0.006063      ← 稳态
```

**2000 步（4 秒仿真时间）后进入稳态。**测试里至少跑 2000 步再测量，
否则测的是瞬态。

📌 **别把 500 步的 0.0099 当成「精度不够」** —— 那是还没走完。

### 4.4 超范围指令：MuJoCo 会 clip，但 `ctrl` 数组不变

```
d.ctrl[2] = 2.0  →  qpos[9] = 0.8704   (ctrl 里存的还是 2.0)
```

`actuator_ctrllimited = True`，所以**物理上被限幅**，但 `d.ctrl` 数组里
**保存的仍是原始值 2.0**。

📌 **别写 `assert d.ctrl[2] <= 0.87`** —— 那会失败。
要断言的是 `qpos`，不是 `ctrl`。

顺带：[mmk2_base.py:193](discoverse/robots_env/mmk2_base.py#L193) 的
`updateControl` 自己也做了一次 `np.clip`，所以走 `MMK2Base` 的路径里
`ctrl` 数组是干净的，直接操作 `mj_data` 则不是。**两条路径行为不同**，测试要写清用的哪条。

---

## Step 5｜双臂自碰撞检测（120 分钟）

### 5.1 ⭐⭐ 第十个坑：62/73 个 geom 没有名字

计划文档：

```python
geom1 = mj_model.geom(contact.geom1).name
if "left_arm" in geom1 and "right_arm" in geom2:
    pytest.fail(...)
```

我先让双臂对撞，然后打印接触对：

```
ncon= 8
    ('51', '72')                          ← 无名，我打印的是 id
    ('52', '71')
    ('floor', '21')
    ('floor', '23')
    ('floor', 'lft_behind_wheel')
    ('floor', 'rgt_behind_wheel')
```

统计：

```
ngeom=73  named=11  unnamed=62
```

**73 个 geom 里只有 11 个有名字。**手臂上的 geom **全部无名**。

所以计划文档那个 `if "left_arm" in geom1` —— `geom1` 是 `''`（空字符串），
`"left_arm" in ''` 恒为 `False`。

> ⭐⭐⭐ **这是今天最危险的一个坑，因为它不报错。**
> 测试会**永远通过**。你会以为「自碰撞检测通过了」，
> 实际上这个测试**从来没有检测过任何东西**。
>
> **这类「空转绿测试」比红测试危险得多** —— 红测试至少会引起注意。

### 5.2 正确做法：geom → body → 向上追溯

geom 没名字，但**body 有**。而且 MuJoCo 的 body 树天然带着「属于哪条手臂」的信息：

```python
def body_chain(m, bid):
    """从 body 一路向上追溯到 worldbody。"""
    out = []
    while bid > 0:
        out.append(mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, bid) or "?")
        bid = m.body_parentid[bid]
    return out

def arm_side(m, gid):
    """判断这个 geom 属于左臂 / 右臂 / 都不是。"""
    for name in body_chain(m, m.geom_bodyid[gid]):
        if name.startswith("lft_arm") or name.startswith("lft_finger"):
            return "L"
        if name.startswith("rgt_arm") or name.startswith("rgt_finger"):
            return "R"
    return None
```

验证一下无名 geom 51 和 72 到底是谁：

```
geom 51 body chain: ['lft_finger_right_link', 'lft_arm_link6', ..., 'lft_arm_base', 'slide_link', 'agv_link', 'mmk2']
geom 72 body chain: ['rgt_finger_left_link', 'rgt_arm_link6', ..., 'rgt_arm_base', 'slide_link', 'agv_link', 'mmk2']
```

**追溯成功。**再跑一次对撞检测：

```
CROSS-ARM CONTACTS: {('lft_finger_right_link', 'rgt_finger_left_link'),
                     ('lft_finger_left_link',  'rgt_finger_right_link')}
```

**真的抓到了左右手指的互相碰撞。**

> ⭐ **方法论：当直接的标识不可用时，往结构里找。**
> geom 名字缺失是数据问题，但 body 的**父子关系**是结构，
> 结构比命名可靠得多 —— 命名靠人自觉，结构由物理模型强制。

### 5.3 ⚠️ 自碰撞测试的两种写法，语义完全相反

这里要小心，别把两件事混成一个测试：

| 测试 | 断言 | 意图 |
|---|---|---|
| **A. 检测器有效性** | 摆一个**已知会碰**的位形 → 断言 `检测到碰撞` | 证明检测器**能工作** |
| **B. 安全位形** | 摆一个**任务用的**位形 → 断言 `没有碰撞` | 证明这个位形**安全** |

计划文档只写了 B（`pytest.fail if collision`）。

**只写 B 是不够的** —— 因为 B 通过可能是「真的没碰」，
也可能是「检测器坏了」（正如 5.1 那个空转测试）。

📌 **必须先有 A。**A 是 B 的**元测试**：它证明当碰撞真的发生时，你的检测代码看得见。

```python
def test_self_collision_detector_actually_detects():
    """元测试：已知碰撞位形必须被检出。若此测试通过而安全测试也通过，后者才可信。"""
    ...双臂内收...
    assert cross_arm_contacts(m, d), "检测器失效：已知碰撞位形却报告无碰撞"
```

> ⭐ **这条元测试是今天四个模块里最能体现测试功力的一个。**
> 面试里可以直接讲：「我发现原方案的自碰撞测试恒为真空通过，
> 所以我加了一条元测试来证明检测器本身有效。」

### 5.4 ⚠️ 别对 `ncon` 直接断言

实测 `ncon=8`，其中 4 个是**轮子和地板的正常接触**：

```
('floor', 'lft_behind_wheel'), ('floor', 'rgt_behind_wheel'), ('floor','21'), ('floor','23')
```

**机器人站在地上，接触数永远 > 0。**

```python
assert d.ncon == 0        # ❌ 永远失败
```

必须按「双方都属于手臂且分属左右」筛选。

### 5.5 关于「工作空间重叠率 > 30%」

计划文档步骤 4 还有：

```python
overlap = left_workspace.intersection(right_workspace)
assert overlap.volume / left_workspace.volume > 0.3
```

`compute_reachable_workspace()` **不存在**，得自己写。

我的结论是**不把它写成测试**，改写成 `scripts/mmk2_workspace_overlap.py` 度量脚本。
但**得出这个结论的过程本身值得复盘 —— 因为我第一版的理由是错的。**

### 5.5.1 ❌ 我最初的理由（其中一条不成立）

初稿我给了三条理由：

1. 成本高（网格采样 IK，每点一次调用）
2. 阈值「> 30%」没有出处
3. **「数字随网格步长变化，网格越粗越失真」** ← **这条我没验证就写了**

第 3 条听起来天经地义 —— 网格越粗，体积估计当然越不准。**于是我直接写进了脚本注释和教程。**

### 5.5.2 ⭐ 实测：比值出乎意料地稳定

三档分辨率跑下来：

| 步长 | 采样点数 | 重叠/单臂 | **重叠/并集** | 左臂可达体积 |
|---|---|---|---|---|
| 0.15 m | 1,323 | 44.9% | **29.0%** | 0.2329 m³ |
| 0.10 m | 1,287 | 48.1% | **31.5%** | 0.2350 m³ |
| 0.06 m | 5,292 | 48.1% / 48.4% | **31.8%** | 0.2143 m³ |

**0.10 和 0.06 两档的「重叠/单臂」完全相同（48.1%）。**

我的第 3 条理由不成立。原因也不难理解：

> **体积的绝对值确实在抖**（0.2143～0.2350 m³，约 10%），
> 但比值的**分子和分母同步失真**，误差大部分抵消掉了。

📌 **这是一个典型的「合理直觉 ≠ 事实」**。
「粗网格不准」是对的 —— 但「不准」体现在绝对值上，不体现在比值上。
**我把对绝对值的直觉，套用到了比值上。**

### 5.5.3 ⭐⭐ 真正的理由：分母的选择决定结论

推翻了第 3 条，反而找到了一条**更硬**的理由。看那一列加粗的数字：

```
计划文档的阈值：            > 30%
「重叠/单臂」实测：        44.9% ~ 48.4%    → 轻松通过，阈值形同虚设
「重叠/并集」实测：        29.0% ~ 31.8%    → 正好骑在 30% 线上
```

**同一台机器人，同一份 MJCF，换个分母，结论从「远超标准」变成「勉强及格」。**

而且在「重叠/并集」这个口径下：

- 步长 0.15 → **29.0%，断言失败**
- 步长 0.06 → **31.8%，断言通过**

> ⭐⭐ **如果照计划文档写成 `assert ratio > 0.3`，这个测试的红绿
> 取决于你把 `--step` 设成多少，而不取决于机器人有没有问题。**
>
> 这是一个 **flaky 断言** —— 只不过它的「随机源」不是时序或并发，
> 而是**采样分辨率这个测试自己引入的参数**。

📌 **Day 5 我们量化过 flake 率，当时的随机源是仿真本身。
今天这个更隐蔽：随机源是测试作者自己选的一个常数。**

### 5.5.4 顺带一个佐证：粗网格会抹平真实的不对称

注意 0.15 那一档：**左右臂可达点数完全相等（69 / 69）**。
而 0.06 档是 **992 / 986** —— 不相等。

Step 2.5 已经实测过左右臂**安装高度不同**（末端 Z 1.235 vs 1.387）。
所以两臂**本来就不该对称**。

> ⚠️ **粗网格给出的「完美对称」是假象。**
> 如果有人在 0.15 步长下写一条「左右臂可达体积应相等」的测试，
> 它会绿 —— 并且掩盖真实的不对称。

### 5.5.5 结论

**不写成测试，写成度量脚本**，理由更新为：

1. ✅ **阈值没有出处**（原因 2，成立）
2. ✅ ⭐ **分母口径未定义时，阈值可以被「选」成任何结论**（新，最硬）
3. ✅ **在关键口径下，结论对采样分辨率敏感** —— 断言会 flaky（新）
4. ✅ **它测的是几何不是行为**，MJCF 不变它就不会变红（原因 3，成立）
5. ⚠️ 成本（原因 1）—— 实测 0.06 步长 5292 点约几分钟，确实不该进 CI 主线

> ⭐ **「能写」不等于「该写」。**
> 一个阈值拍脑袋、口径未定义、且红绿取决于自身参数的测试，
> 是**纯负债**：它消耗 CI 时间，制造虚假的覆盖率信心，红了没人知道怎么办。
>
> **替代方案**：[scripts/mmk2_workspace_overlap.py](scripts/mmk2_workspace_overlap.py)
> 输出三个口径的数字供人看，**明确声明不做阈值判定**。
> 等有了明确需求（比如「某任务要求双臂在指定区域协作」）再决定要不要变成断言。

📌 **这个判断本身要写进 checkpoint** —— 「我拒绝实现方案里的一个测试并给出了理由」
比「我实现了方案里所有的测试」更能说明你在思考。
**而「我的第一版理由被自己的实测推翻了」更值得写。**

---

## Step 6｜组装成测试模块（120 分钟）

### 6.1 目录结构

```
tests/mobile_manipulation/
├── __init__.py
├── conftest.py                        # fixture + 几何工具（坐标变换/geom 归属）
├── test_mmk2_kinematics.py            # Step 2 —— 13 例
├── test_differential_drive.py         # Step 3 —— 7 例
├── test_slide_lift.py                 # Step 4 —— 9 例
└── test_dual_arm_collision.py         # Step 5 —— 5 例
```

⭐ **`conftest.py` 里放的不只是 fixture，还有四个几何工具函数**：

| 函数 | 为什么必须共享 |
|---|---|
| `quat_wxyz_to_matrix` | wxyz/xyzw 约定转换，写反不报错 —— 只能有一处 |
| `world_to_footprint` | FK 世界系 → IK footprint 系，本目录最易错的一环 |
| `arm_side` / `cross_arm_contacts` | geom→body 祖先链归属，替代失效的字符串匹配 |
| `qpos_adr` | 按名字取 qpos 下标，杜绝"数格子"数错 |

📌 **把易错的转换收敛到一处，是本目录最重要的结构决策。**
如果每个测试文件各写一遍坐标变换，就会有四份可能各自写错的实现 ——
而且它们互相「印证」，全错时反而看起来一致。

⚠️ **`__init__.py` 不能忘** —— 项目里 `tests/unit`、`tests/integration` 都有，
这是 Day 2 定下的规矩（避免同名测试文件冲突）。

### 6.2 ⭐ fixture 设计：`MjModel` 只读可共享，`MjData` 必须每例全新

实测 `MjModel.from_xml_path` 加载 `mmk2_floor.xml` 约 **0.14 秒**
（三次：0.223 / 0.112 / 0.093，首次含磁盘缓存未命中），`MjData` 分配 0.0004 秒。

⚠️ **说实话：0.14 秒 × 19 个用例 = 2.7 秒，这点开销其实无所谓。**
我一开始以为是 1 秒才决定用 `scope="session"`，实测后这个理由**不成立**。

📌 **但结论不变，理由要换。**`scope="session"` 在这里仍然值得，
不是为了省 2.7 秒，而是因为**它表达了「模型是只读的」这个设计意图**。

> ⭐ **别用编造的性能数字论证设计决策。**
> 如果我把「加载要 1 秒」写进教程，下一个人会基于这个假数字做他的决策。
> **性能优化必须先测量** —— 这条在 Day 5 讲过，今天我自己又差点违反。

**真正不能妥协的是另一半：`MjData` 绝对不能共享** ——
上一个用例把机器人开走了，下一个用例就从那开始。

```python
@pytest.fixture(scope="session")
def mmk2_model():
    """模型只读，跨 session 复用（加载约 1s）。"""
    path = os.path.join(DISCOVERSE_ROOT_DIR, "models/mjcf/mmk2_floor.xml")
    return mujoco.MjModel.from_xml_path(path)

@pytest.fixture
def mmk2_data(mmk2_model):
    """每个用例一份全新的 MjData —— 绝不复用。"""
    d = mujoco.MjData(mmk2_model)
    mujoco.mj_resetData(mmk2_model, d)
    mujoco.mj_forward(mmk2_model, d)
    return d
```

### 📖 顺带澄清一个我自己差点写错的地方

我一度以为「`mj_resetData` 之后底盘四元数是 `[0,0,0,0]`，必须手动置单位四元数」。
**实测是错的**：

```
fresh MjData      qpos[0:7] = [0. 0. 0. 1. 0. 0. 0.]
after mj_resetData qpos[0:7] = [0. 0. 0. 1. 0. 0. 0.]
```

`mj_resetData` 是从模型的 `qpos0` 恢复，而 `qpos0` 里自由关节的四元数本来就是
`[1,0,0,0]`。**不需要手动补。**

📌 **那我为什么会以为要补？**因为我在 Step 2.3 的实验里手写了 `d.qpos[3:7]=[1,0,0,0]`，
之后就默认「不写会出问题」—— 但我从没验证过不写会怎样。

> ⭐ **这是「防御性代码掩盖认知空白」的典型形态。**
> 那行赋值是无害的，所以它永远不会暴露我的误解 ——
> 它只会让我在教程里写下一句错误的解释，然后传给下一个人。
>
> Day 13-14 Step 3.3 已经踩过同一类坑（「先写防御性代码再读接口」）。
> **这次的教训更细：无害的多余代码，代价是你以为自己懂了。**

> ⭐ **`scope="session"` 用在只读对象上是优化，用在可变对象上是灾难。**
> 判断标准很简单：**这个 fixture 有没有可能被用例改？**
> `MjModel` 不会（我们只读），`MjData` 每步都在改。

### 6.3 测试清单与耗时预算

**先实测仿真步进速度**（别拍脑袋估）：

```
4000 次 mj_step                : 0.47s   （每 1000 步约 0.117s）
底盘模块 3 组 × 4000 步        : 1.4s
升降模块 5 目标 × 5000 步      : 2.9s
```

| 模块 | 用例数 | 关键断言 | 实测耗时 |
|---|---|---|---|
| `test_mmk2_kinematics.py` | **13**（含 1 xfail） | 往返误差 < 1e-3 rad；**底盘非原点**；slide 全行程扫描；不可达抛异常；tmats 缓存护栏 | ~0.6s |
| `test_differential_drive.py` | **7**（含 1 xfail） | 直线度 < 5%（含分母前置断言）；里程计 yaw 误差 < 0.05 rad；**xfail 钉 `wheel_distance`** | ~4.6s |
| `test_slide_lift.py` | **9** | 定位误差 < 10mm；**下垂一致性 ptp < 1e-4**；稳定时间；限幅行为 | ~6.0s |
| `test_dual_arm_collision.py` | **5** | **元测试：已知碰撞必检出**；安全位形无碰撞；执行器布局钉死 | ~2.0s |
| **合计** | **34**（32 passed + 2 xfailed） | | **~11.5s** |

⚠️ **我初稿估的是 19 个用例，实际写出来 34 个。**
差额几乎全部来自 `@pytest.mark.parametrize`：slide 全行程扫描一条就展开成 5 个，
左右臂往返展开成 2 个，升降目标位展开成 4 个。

📌 **参数化会让"用例数"和"你写的测试函数数"脱钩。**
估工作量时按**函数数**估，估 CI 时长时按**展开后的用例数**估。

### ⚠️ 我原本打算在这里加 `@pytest.mark.slow`，实测后撤销了

我的初稿写的是「合计约 55 秒，太慢，要打 `slow` 标记，CI 的 unit job 里
`-m "not slow"` 跳过」。

**实测总计约 6 秒 —— 我高估了 9 倍。**

📌 **所以不加标记。**理由：

- 6 秒完全可以留在 unit job 里，**每次 push 都跑**
- 打了 `slow` 标记 = 默认跳过 = **今天抓到的 `wheel_distance` 缺陷在日常 CI 里看不见**

> ⭐⭐ **这是今天第三个方法论收获，而且是我自己差点犯的错：**
> **「基于估算的性能优化，会换来真实的覆盖率损失。」**
> 我为了省一个不存在的 49 秒，差点把唯一能抓到里程计缺陷的测试挪出主流程。
>
> **测量的成本（一条命令，30 秒）远低于错误决策的成本。**

**而且项目里的 marker 定义本身就否决了这个想法。**看 `pyproject.toml:289`：

```toml
"slow: 单用例 >10s，CI 主线跳过",
```

**判据是「单用例 >10s」，不是「模块合计」。**我最慢的模块 2.9 秒**分摊在 5 个用例上**，
单个用例连 1 秒都不到 —— **按项目自己的定义，它压根不够格打 `slow`。**

> ⭐ **打标记前先读标记的定义。**
> 我差点按自己脑子里的「慢」去打一个项目里已经有精确定义的标记。

### 6.4 ⚠️ 用对 marker：这些是 `integration` 不是 `unit`

`pyproject.toml:287-288` 的定义：

```toml
"unit: 纯函数/配置层单测，无 MuJoCo 依赖，秒级",
"integration: 需要加载 MJCF 或跑仿真步进",
```

**今天 4 个模块全部要加载 MJCF 并跑仿真步进 → 全部是 `integration`。**

```python
pytestmark = pytest.mark.integration      # 放模块顶部，整个文件生效
```

⚠️ **`--strict-markers` 是开着的**（`addopts`），marker 拼错会**直接报错**而非静默吞掉。
这是好事，但意味着不能随手编一个 `@pytest.mark.kinematics`。

### 6.5 ⚠️ 每个用例有 60 秒超时

```toml
timeout = 60
```

我最慢的用例远低于此，**但要注意**：如果哪天有人把步数从 5000 调到 500000
（比如为了「更接近稳态」），会撞上超时 —— 而超时的报错信息**不会告诉你是步数的问题**。

📌 **所以测试里的步数要写成有名字的常量并注释清楚依据**：

```python
# 2000 步（4s 仿真时间）后升降进入稳态，实测残余变化 < 1e-5 m。
# 取 5000 留余量；再大会逼近 pyproject.toml 的 60s 用例超时。
_LIFT_SETTLE_STEPS = 5000
```

### 6.6 ⭐⭐ 变异测试：证明测试真的在测东西

今天全文反复讲「空转绿测试」的危险。那么 —— **凭什么相信我自己写的测试不是空转的？**

绿色不是证据。**把实现改坏，看测试红不红**，才是证据。

我把 `world_to_footprint` 的最后一行换成「直接返回世界系位姿」（即
**故意不做坐标变换**，模拟一个忘了这回事的实现）：

```python
-   t_base_ee = np.linalg.inv(t_w_base) @ t_w_ee
-   return t_base_ee[:3, 3], t_base_ee[:3, :3]
+   return np.asarray(pos_w), np.asarray(rot_w)   # MUTANT
```

实测结果：

```
1 failed, 11 passed, 1 xfailed
FAILED tests/mobile_manipulation/test_mmk2_kinematics.py::test_roundtrip_with_base_off_origin
```

**恰好一条红，而且正是 Step 2.3 里那条「底盘非原点」的用例。**

📌 **这个结果同时证明了两件事：**

1. ✅ `test_roundtrip_with_base_off_origin` **是真测试** —— 它抓得到坐标系错误
2. ⚠️ 另外 **11 条全都通过了这个坏实现** —— 它们对坐标系错误**完全无感**

第 2 条才是重点。如果我没写那条「底盘非原点」的用例，
**我会有 11 条绿色测试，和一个坏掉的坐标变换。**

> ⭐⭐ **变异测试是「元测试」的通用形式。**
> Step 5.3 的自碰撞元测试（已知碰撞必检出）是同一个思想的特例：
> **先制造一个必然失败的场景，确认测试会红，再去相信它的绿。**
>
> 成本：改一行、跑一次、改回来，不到一分钟。
> 收益：把「我觉得这个测试有用」变成「我验证过这个测试有用」。

⚠️ **做完记得改回来并重跑。**我用 `cp` 备份原文件再还原，
还原后确认 `12 passed, 1 xfailed` 才继续。

### 6.7 收工验收

```bash
env -u PYTHONPATH MUJOCO_GL=osmesa $PY -m pytest tests/ -q | tail -2
# 实测：173 passed, 4 skipped, 45 deselected, 17 xfailed in 21.69s
#       141 + 32 = 173；xfailed 15 + 2（缺陷 Y、Z）= 17

env -u PYTHONPATH $PY -m ruff check tests/
# All checks passed!        ← tests/ 是严格模式，必须全绿
```

⚠️ **别忘了 Docker 复核**（Day 13-14 的教训）：

```bash
docker build -q -f discoverse/docker/Dockerfile.test -t discoverse:test .
docker run --rm discoverse:test pytest tests/ -q
```

**不要挂载 `-v "$PWD":/work`** —— 镜像里的代码烤在 `/workspace`，
挂到别的路径会制造「两份代码」，import 解析到旧的那份。

---

## Step 7｜今天的缺陷登记（30 分钟）

| 编号 | 缺陷 | 证据 | 影响 | 今天怎么处理 |
|---|---|---|---|---|
| **新 · Y** | `MMK2Base.wheel_distance = 0.189`，模型实测 0.3265 | yaw 误差 1.944 rad → 0.0066 rad | **4 个 ROS 遥操作文件**的 `cmd_vel` 角速度全错 1.73× | `xfail` 钉住 + 进缺陷报告，**不改**（语义歧义需单独 PR） |
| **新 · Z** | `MMK2FK.__init__` 未初始化 `pos_modifidied` | 直接调 getter → `AttributeError` | 首次使用必炸 | `xfail` 钉住，不改（有规避方式） |
| **新 · AA**<br>（风险，非缺陷） | `mmk2_ik.py:15` 裸 `except:` + `.npz` 缓存无版本戳 | 实测缓存与现算 **maxdiff=0，当前一致** | MJCF 若改动，IK 会静默用旧变换 | 写「缓存 vs 现算」回归护栏 |
| **文档 · CLAUDE.md** | 19 维动作布局从第 11 位起错位；夹爪写成 2 个；slide 范围写成 `[0,0.87]` | 执行器表实测 | 照文档写代码会控错关节 | 测试钉死布局 + 更新 CLAUDE.md |

⚠️ **缺陷 Y 的修复不在今天。**理由已在 Step 3.5 讲透：
`wheel_distance` 到底是轮距还是半轮距，里程计代码和 ROS 代码的用法**互相矛盾**，
只改数值会让其中一边从「错 73%」变成「错 50%」。**先钉住，再消歧义。**

---

## ⭐ Step 8｜今天给后面留了什么（20 分钟，别跳过）

### 8.1 `FailureMode` 需要补移动操作的类别

Day 13-14 的 `FailureMode.ALL` 目前是：

```
ik_early / final_check / timeout / config / crash
```

移动操作的失败原因更多，光看 `final_check` 不知道往哪查：

| 建议新增 | 含义 | 排查方向 |
|---|---|---|
| `base_pose` | 底盘没到位 | 里程计、导航、地面摩擦 |
| `slide_range` | 升降行程不够 | 目标高度超出 `[-0.04, 0.87]` |
| `self_collision` | 双臂/臂-躯干干涉 | 轨迹规划、双臂协同顺序 |

📌 **但今天先别加。**Day 13-14 的契约有一条不变式：
`failure_mode` 必须在 `FailureMode.ALL` 内，**拼错当场炸**。
加类别是**扩展契约**，应该等到真有 MMK2 任务在跑并产出这些失败时再加 ——
否则就是在为想象中的需求扩接口。

**今天只在 checkpoint 里记下这个提案。**

### 8.2 给 Day 18-19 的接口

数据质量验证要检查轨迹平滑度。今天的里程计代码**正好是它需要的前置能力**：

```
今天：轮子编码器 → 差速运动学 → 推算位姿 → 和真值比对
Day 18-19：推算位姿序列 → 速度/加速度 → 平滑度指标
```

⚠️ **但要提醒 Day 18-19 的自己**：**别用 `wheel_distance` 常量**，
它是错的（缺陷 Y）。用从 MJCF 现算的轮距，或者直接用 `qpos[0:3]` 真值。

### 8.3 一句话交接

> **今天证明了一件事：仿真里最容易错的不是物理，是那些「描述物理的常数」。
> 因为常数不会崩溃、不会抛异常、不会在直线上暴露 —— 它只在你转弯的时候，
> 悄悄把 111 度当成 152 度告诉你。**

---

## 收工清单

- [x] `tests/mobile_manipulation/` 4 个模块 + `conftest.py` + `__init__.py`
- [x] `pytest tests/ -q` → **173 passed, 4 skipped, 45 deselected, 17 xfailed**（21.69s）
- [x] `ruff check tests/` → All checks passed
- [x] Docker 内复核（**不挂载**，重建镜像）→ **173 passed**（19.32s）
- [x] ⭐ 变异测试：破坏 `world_to_footprint` → 恰好 1 红，证明测试非空转
- [ ] 缺陷报告新增 Y / Z / AA 三条
- [ ] `CLAUDE.md` 修正 19 维动作布局
- [ ] `scripts/` 下的 workspace 重叠度量脚本（**非测试**）
- [ ] checkpoint 记录 `FailureMode` 扩展提案

---

## 附录 A：本文所有实测数据的复现命令

```bash
PY=~/miniconda3/envs/discoverse/bin/python
export MUJOCO_GL=osmesa

# 执行器/关节表（Step 3.1、4.1）
env -u PYTHONPATH $PY -c "
import mujoco, os
from discoverse import DISCOVERSE_ROOT_DIR
m = mujoco.MjModel.from_xml_path(os.path.join(DISCOVERSE_ROOT_DIR,'models/mjcf/mmk2_floor.xml'))
for i in range(m.nu):
    print(i, mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_ACTUATOR, i), m.actuator_ctrlrange[i])
"

# 真实轮距（Step 3.4）
env -u PYTHONPATH $PY -c "
import mujoco, os
from discoverse import DISCOVERSE_ROOT_DIR
m = mujoco.MjModel.from_xml_path(os.path.join(DISCOVERSE_ROOT_DIR,'models/mjcf/mmk2_floor.xml'))
for nm in ['lft_wheel_joint','rgt_wheel_joint']:
    jid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, nm)
    print(nm, m.body_pos[m.jnt_bodyid[jid]])
"
# → ±0.16325 → 轮距 0.3265，而 MMK2Base.wheel_distance = 0.189
```

## 附录 B：五个数字，面试时能直接说

| 数字 | 出处 | 说明什么 |
|---|---|---|
| **1.73×** | `0.3265 / 0.189` | 轮距常量错误倍数，导致偏航推算错 111°（1.944 rad → 0.0066 rad，改善 294 倍） |
| **6.06 mm** | 升降稳态误差，五个目标位全相同 | 重力下垂，**不是缺陷**；识别「恒定偏置 vs 随机噪声」 |
| **62 / 73** | 无名 geom 占比 | 原方案的字符串匹配自碰撞检测**恒为空转** |
| **1 红 / 11 绿** | 变异测试：破坏 `world_to_footprint` | 只有「底盘非原点」那条用例抓得到坐标系错误，**其余 11 条对它完全无感** |
| **29.0% vs 31.8%** | 工作空间重叠率，`--step` 0.15 vs 0.06 | 阈值 30% 的红绿取决于测试自己的参数 —— **flaky 断言** |

### 一句话版本（面试开场）

> 「我把工业机器人的运动学标定思维迁移到仿真测试，写了 34 个用例。
> 过程中发现方案文档里的示例代码没有一行能跑，
> 并抓到一个真缺陷：轮距常量错了 1.73 倍 —— 它在直线上完全看不出来，
> 因为直线时轮距被乘以 0，只有转弯才会暴露。这正是 AGV 轮距标定
> 必须用原地旋转的原因。」
