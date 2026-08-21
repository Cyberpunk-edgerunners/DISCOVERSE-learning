# 魔鬼日志 · Day 15-17（2026-08-19）

> 主题：MMK2 双臂轮式专项测试
> 目标缺陷：新发现 Y（轮距常量）、Z（FK 未初始化属性）、AA（tmats 缓存无版本戳）
> 基线：141 passed → 收工 173 passed

---

## 开工状态

```bash
env -u PYTHONPATH MUJOCO_GL=osmesa $PY -m pytest tests/ -q | tail -2
# 141 passed, 4 skipped, 45 deselected, 15 xfailed
```

前 14 天做的都是**通用测试基础设施**（pytest 骨架、Docker、CI、结果契约）——
换个项目也能用。今天第一次做**只有机器人项目才需要的测试**。

---

## 一、⭐ 开工第一小时：计划文档的示例代码一行都跑不了

计划文档 §Day 15-17 步骤 1 第一行：

```python
from discoverse.robots.mmk2.mmk2_fk import get_armjoint_pose_wrt_footprint
from discoverse.robots.mmk2.mmk2_fik import solve_mmk2_ik
```

**先 grep 再 import**：

```bash
grep -n "^def \|^class \|^    def " discoverse/robots/mmk2/*.py
```

```
mmk2_fk.py:8:class MMK2FK:
mmk2_ik.py:43:    def armIK_wrt_footprint(self, position, rotation, arm, slide, q_ref)
mmk2_fik.py:111:   def get_armjoint_pose_wrt_footprint(self, point3d, action, arm, slide, ...)
```

三处对不上：

1. `get_armjoint_pose_wrt_footprint` **不是自由函数**，是 `MMK2FIK` 的方法
2. `solve_mmk2_ik` **完全不存在**
3. 就算接上方法名，**签名也对不上** —— 计划文档以为它吃 `(joint_angles, arm)`，
   真实签名吃 `(point3d, action, arm, slide, ...)`，是**目标点 + 动作类型**不是关节角

后面又陆续发现 `arm='left'` 也是错的（真实取值 `'l'`/`'r'`）。

📌 **教训：任何「照文档写测试」的任务，第一步是 `grep` 不是 `import`。**
文档描述的是**作者以为的代码**，`grep` 给的是**实际的代码**。

---

## 二、两个上游接口坑【已核实】

### 2.1 `MMK2FK` 有未初始化属性

```python
MMK2FK().get_left_endeffector_pose()
# AttributeError: 'MMK2FK' object has no attribute 'pos_modifidied'
```

`__init__`（`mmk2_fk.py:9-13`）从未设 `self.pos_modifidied`，
但每个 getter 都读它（`:118`）。**必须先调至少一个 `set_*`。**

⚠️ 属性名拼写是 `pos_modifidied`（少个 `f`、多个 `i`），贯穿全文件。
**没有顺手改** —— 改了会把所有 setter 一起打断。

→ 登记为缺陷 Z，写 `xfail` 钉住，不修（有明确规避方式）。

### 2.2 `MMK2FIK` 已弃用

```
接口即将弃用, 请使用discoverse.robots.mmk2_ik      ← 构造时的黄色告警
```

改用 `MMK2IK`。**不只是新旧问题**：`MMK2FIK` 只能从 `pick`/`carry`/`look`
三个预设动作查表取姿态，那测的是查找表不是运动学；`MMK2IK` 直接吃 3×3 旋转矩阵。

---

## 三、⭐⭐ FK/IK 坐标系不一致：一个「在原点恰好通过」的陷阱

最小往返先跑通了：

```
FK endpoint pos (world): [0.48993 0.12677 1.23515]
IK solution: [0.10001 -0.2 0.3 0.1001 0.19999 0.0999]
joint err  : 最大 9.7e-05 rad          ← 闭合
```

**然后把底盘挪开**：

```
--- base translated (x=1, y=0.5) ---   IK FAILED
--- base rotated 90deg yaw ---         IK FAILED
```

原因：

- `MMK2FK.get_*_endeffector_pose()` 走 `get_site_tmat`，返回 **world 系**
- `MMK2IK.armIK_wrt_footprint()` 吃 **footprint 系**

**底盘在原点且无旋转时，两个坐标系数值上恰好相等** —— 所以往返「通过」了。

📌 这是「在恒等变换下测试」的经典陷阱。工业机器人上同形：
工具坐标系标定测试永远在 TCP=0 下跑，装上真实夹具才发现整条链路搞错了参考系。

→ 在 `conftest.py` 写了 `world_to_footprint()`，并**专门写一条「底盘非原点」用例**。

### 顺带：四元数约定

MuJoCo/`MMK2FK` 返回 `wxyz`，scipy 的 `from_quat` 要 `xyzw`。
写反不报错，只会得到**合法但错误**的旋转 —— 只有往返测试抓得到。

---

## 四、slide 符号扫描【已核实】

```
slide= 0.00  err=9.74e-05  endpos=[0.48993 0.12677 1.23515]
slide= 0.30  err=9.74e-05  endpos=[0.48993 0.12677 0.93515]
slide= 0.87  err=9.74e-05  endpos=[0.48993 0.12677 0.36515]
```

两个结论：

1. ⭐ **slide 增大 → 躯干降低**（1.235 → 0.365，正好差 0.87）。执行器叫 "lift"，反直觉
2. **往返误差与 slide 无关**（恒 9.74e-05）→ FK 和 IK 对 slide 的符号约定**一致**

`mmk2_ik.py:63` 是 `tmat[2,3] -= slide`。若有人改成 `+=`，
单独跑 IK 不会报错（照样解得出关节角），**只有往返测试会红**。

---

## 五、⭐⭐⭐ 抓到真缺陷：轮距常量错 1.73 倍

### 5.1 先纠正一个前提：轮子是力矩控制

计划文档写 `action[0]=0.5 # 左轮速度`。看 `mmk2_control.xml:3-4`：

```xml
<motor name="lft_wheel_motor" .../>     ← <motor> 是力矩执行器
```

实测恒定 1.0 N·m：

```
step    0  wheel_qvel=[0.01811 0.01813]
step 1000  wheel_qvel=[1.10714 1.10785]
step 2500  wheel_qvel=[1.63472 1.63489]        ← 一路爬升，永不恒定
```

**恒力矩 ≠ 恒速度。**所以不能断言「跑 N 步走 X 米」，
必须**从轮子编码器读数推算位姿再与真值比对** —— 这正是真机里程计标定的做法。

### 5.2 里程计实测：直线对，转弯崩

用 `MMK2Base.wheel_radius=0.0838`、`wheel_distance=0.189`：

```
torque(1.0, 1.0)   yaw 误差 0.0005 rad     位置误差 0.0015 m
torque(1.0, 0.5)   yaw 误差 0.5584 rad     位置误差 0.1916 m
torque(1.0,-1.0)   yaw 误差 1.9440 rad     位置误差 0.0168 m      ← 111°！
```

⭐ **「直线对、转弯错」直接指向轮距** ——
直线时 `Δs_right - Δs_left = 0`，**轮距被乘以 0**，错得再离谱也看不出来。

### 5.3 定位

```
4.6005 / 2.6565 = 1.7318          ← 误差比
```

去 MJCF 量：

```
lft_wheel_joint body pos = [-0.02371  0.16325  0.082]
rgt_wheel_joint body pos = [-0.02371 -0.16325  0.082]
→ 真实轮距 = 0.16325 × 2 = 0.3265

0.3265 / 0.189 = 1.7275           ← 吻合
```

### 5.4 验证

```
wheel_distance=0.1890   yaw 误差 1.9440 rad
wheel_distance=0.3265   yaw 误差 0.0066 rad        ← 改善 294 倍
```

**缺陷 Y 成立。**

### 5.5 ⭐ 影响范围（这步不能省）

```bash
grep -rn "wheel_distance" --include=*.py .
```

```
examples/ros1/mmk2_ros1.py:68
examples/ros1/mmk2_ros1_joy.py:120
examples/ros2/mmk2_ros2.py:144
examples/ros2/mmk2_ros2_joy.py:127
discoverse/robots_env/mmk2_base.py:63
```

**4 个 ROS 遥操作文件**在用它做 `cmd_vel` 逆解 ——
任何通过 ROS 发角速度指令的人，实际转速都是期望值的 1.73 倍。
**这不是测试里的数字问题，是用户可见的行为缺陷。**

### 5.6 ⚠️ 为什么今天不修

这 4 个文件写的是：

```python
v_left = (msg.linear.x - msg.angular.z * self.wheel_distance) / self.wheel_radius
```

标准差速逆解应是 `ω·L/2`，**它们没有除以 2**。

所以这个变量的**语义本身是矛盾的**：

- 里程计公式按「全轮距」用：`Δθ = (Δs_r - Δs_l) / L`
- ROS 代码按「半轮距」用：少除以 2

**只改数值会让其中一边从「错 73%」变成「错 50%」。**

→ 正确修法：先消歧义（重命名 `wheel_base` / `half_wheel_base`）再统一取值，
且要改 ROS 文件，需单独 PR 验证。今天只 `xfail` 钉住。

---

## 六、升降：6.06mm 稳态误差，是不是缺陷？

计划文档 `assert abs(err) < 0.005`。实测：

```
target= 0.000  →  err= 0.006063
target= 0.200  →  err= 0.006063
target= 0.500  →  err= 0.006063
target= 0.870  →  err= 0.000399      ← 撞关节上限，被硬约束挡住
target=-0.040  →  err= 0.006063
```

**6.06mm > 5mm，照抄计划文档必红。**

⭐ 但看误差的**结构**：五个目标位**六位小数完全相同**，**符号恒为正**。
结合「slide 越大躯干越低」→ 正偏置 = 躯干比目标略低 = **重力拽的**。

`<position>` 是比例控制器，稳态必须留位置偏差来产生抗重力的力：`误差 = 负载 / kp`。

📌 **结论：位置伺服的固有下垂，不是缺陷。**真机上也一样（无积分项的位置环必有静差）。

**所以没有简单放宽容差了事**，而是加了一条更有价值的断言：

```python
assert np.ptp(errors) < 1e-4      # 下垂偏置在各高度必须一致
```

各高度下垂应恒定；某处突然不一样 = 卡滞/干涉 —— 这是「精度 < 10mm」抓不到的故障。

### 顺带两个坑

- `qpos[2]` **不是升降**（那是底盘 Z，自由关节占 `qpos[0:7]`），升降在 `qpos[9]`
- 稳定时间：500 步 err=0.0099（还在动），2000 步后才进稳态

---

## 七、⭐⭐ 自碰撞：计划文档的检测是【空转】的

计划文档：

```python
geom1 = mj_model.geom(contact.geom1).name
if "left_arm" in geom1 and "right_arm" in geom2: ...
```

让双臂对撞后打印接触对：

```
ncon= 8
    ('51', '72')          ← 无名，打印的是 id
    ('52', '71')
    ('floor', '21')
    ('floor', 'lft_behind_wheel')
    ...
```

```
ngeom=73  named=11  unnamed=62
```

**手臂上的 geom 全部无名** → `"left_arm" in ''` 恒为 `False`
→ **测试永远通过，且从未检测过任何东西。**

⚠️ **这类「空转绿测试」比红测试危险得多** —— 红测试至少会引起注意。

### 修法：geom → body → 向上追溯

geom 没名字，但 body 有，且 body 树天然带着归属信息：

```
geom 51 chain: ['lft_finger_right_link', 'lft_arm_link6', ..., 'lft_arm_base', ...]
geom 72 chain: ['rgt_finger_left_link',  'rgt_arm_link6', ..., 'rgt_arm_base', ...]
```

重跑：

```
CROSS-ARM CONTACTS: {('lft_finger_right_link', 'rgt_finger_left_link'),
                     ('lft_finger_left_link',  'rgt_finger_right_link')}
```

**真的抓到了。**

📌 **命名靠人自觉，body 父子关系由物理模型强制。** 结构比命名可靠。

### ⭐ 还加了元测试

只写「安全位形应无碰撞」是不够的 —— 它通过可能是「真的没碰」，
也可能是「检测器坏了」（正如上面那个空转版本）。

所以先写 **`test_self_collision_detector_actually_detects`**：
摆一个**已知会碰**的位形，断言**必须检出**。它是安全测试的前提。

⚠️ 另外不能断言 `ncon == 0` —— 机器人站在地上，轮子与 floor 的接触恒存在。

---

## 八、⭐⭐ 变异测试：证明自己写的测试不是空转的

全天都在讲空转测试的危险。那**凭什么相信我自己写的测试**？

绿色不是证据。**把实现改坏看它红不红**才是。

把 `world_to_footprint` 最后一行换成「直接返回世界系位姿」：

```python
-   t_base_ee = np.linalg.inv(t_w_base) @ t_w_ee
-   return t_base_ee[:3, 3], t_base_ee[:3, :3]
+   return np.asarray(pos_w), np.asarray(rot_w)   # MUTANT
```

```
1 failed, 11 passed, 1 xfailed
FAILED test_mmk2_kinematics.py::test_roundtrip_with_base_off_origin
```

**恰好 1 条红，正是「底盘非原点」那条。**

同时证明两件事：

1. ✅ 那条用例是**真测试**
2. ⚠️ **另外 11 条全都通过了这个坏实现** —— 它们对坐标系错误完全无感

第 2 条才是重点：**没有那条用例，就是 11 条绿色测试 + 一个坏掉的坐标变换。**

⚠️ 做完 `cp` 还原，确认恢复 `12 passed, 1 xfailed` 才继续。

---

## 九、⭐ 我自己踩的 4 个坑（都是「没测就写」）

| # | 我以为 | 实测 |
|---|---|---|
| 12 | `mj_resetData` 后四元数是 `[0,0,0,0]`，要手动补 | 是 `[1,0,0,0]`，**不用补** |
| 13 | 模型加载要 1 秒，所以要 `scope="session"` | **0.14 秒**，原理由不成立 |
| 14 | 测试合计 55 秒，要打 `slow` 标记 | **实测 6 秒**，高估 9 倍 |
| 15 | 工作空间重叠率「随网格步长失真」 | **比值相当稳定**，真正问题是分母口径 |

### 第 14 条差点造成实际损失

我原本要给底盘和升降用例打 `@pytest.mark.slow`，CI 主线 `-m "not slow"` 跳过。

**打了标记 = 默认跳过 = 今天抓到的 `wheel_distance` 缺陷在日常 CI 里看不见。**

而且 `pyproject.toml:289` 对 slow 的定义是「**单用例** >10s」——
我最慢的模块 2.9s 分摊在 5 个用例上，**按项目自己的定义压根不够格**。

📌 **为了省一个不存在的 49 秒，差点把唯一能抓到缺陷的测试挪出主流程。**

### 第 15 条：理由错了但结论对

我说「工作空间重叠率随网格失真」，没验证。实测三档：

| 步长 | 重叠/单臂 | 重叠/并集 |
|---|---|---|
| 0.15 | 44.9% | **29.0%** |
| 0.10 | 48.1% | **31.5%** |
| 0.06 | 48.1% / 48.4% | **31.8%** |

**比值很稳定**（0.10 与 0.06 档「重叠/单臂」完全相同）。
绝对体积确实抖 ~10%，但比值分子分母同步失真，**误差抵消了**。

**但推翻它反而找到更硬的理由**：

```
计划文档阈值 > 30%
「重叠/单臂」 44.9~48.4%  → 轻松通过，阈值形同虚设
「重叠/并集」 29.0~31.8%  → 骑在 30% 线上：step=0.15 失败，step=0.06 通过
```

**红绿取决于测试自己的参数，不取决于机器人有没有问题** —— flaky 断言，
只是随机源是「采样分辨率」这个作者选的常数。

⚠️ 还有个佐证：0.15 档左右臂可达点数**完全相等（69/69）**，
0.06 档是 992/986。两臂**本来就不对称**（安装高度 1.235 vs 1.387）——
**粗网格的「完美对称」是假象。**

→ 不写成测试，改写 `scripts/mmk2_workspace_overlap.py` 度量脚本，明确声明不做阈值判定。

---

## 十、收工核实

```bash
env -u PYTHONPATH MUJOCO_GL=osmesa $PY -m pytest tests/ -q | tail -2
# 173 passed, 4 skipped, 45 deselected, 17 xfailed in 21.17s
#   141 → 173（+32）；xfailed 15 → 17（缺陷 Y、Z）

env -u PYTHONPATH $PY -m ruff check tests/
# All checks passed!
```

Docker 复核（**重建镜像，不挂载** —— Day 13-14 的教训）：

```bash
docker build -q -f discoverse/docker/Dockerfile.test -t discoverse:test .
docker run --rm discoverse:test pytest tests/ -q
# 173 passed, 4 skipped, 45 deselected, 17 xfailed in 19.32s
```

模块分布：

| 文件 | 用例 | 耗时 |
|---|---|---|
| `test_mmk2_kinematics.py` | 13（含 1 xfail） | ~0.6s |
| `test_differential_drive.py` | 7（含 1 xfail） | ~4.6s |
| `test_slide_lift.py` | 9 | ~6.0s |
| `test_dual_arm_collision.py` | 5 | ~2.0s |
| **合计** | **34** | **~11.5s** |

⚠️ 初稿估 19 个用例，实际 34 —— 差额几乎全来自 `parametrize` 展开。
**估工作量按函数数，估 CI 时长按展开后用例数。**

---

## 遗留

1. **缺陷 Y 未修**（轮距）—— 语义歧义需单独 PR，且要改 4 个 ROS 文件
2. **缺陷 Z 未修**（FK 未初始化属性）—— 有规避方式
3. **缺陷 AA 只加了护栏**（tmats 缓存无版本戳）—— 实测当前缓存与现算 maxdiff=0，
   是**风险不是已发生的缺陷**
4. **`FailureMode` 未扩展** —— 移动操作需要 `base_pose`/`slide_range`/`self_collision`，
   但今天没有 MMK2 任务在跑并产出这些失败，**不为想象中的需求扩接口**
5. **`CLAUDE.md` 已修正**动作布局，但 `source-notes/` 下的方案文档还没同步
