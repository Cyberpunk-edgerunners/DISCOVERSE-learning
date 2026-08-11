# DISCOVERSE 小白入门讲解

> **写给谁**：只会基本 Python，不知道什么是物理引擎、不知道 pytest 的人。
> **本文自包含**：不需要跳转到其他文档，所有概念从零讲起。
> **不谈缺陷**：本文只讲「这东西是什么、怎么工作」。项目里发现的 bug 见 [../docs/defect-inventory-day02.md](../docs/defect-inventory-day02.md)。
> **所有代码行号均经实测核对**（2026-07-30，`feat/test-infra` 分支）。

---

## 零、怎么用这份文档

### 三种读法

| 你的情况 | 建议 |
|---|---|
| 完全新手，想搞懂这个项目 | 从第一章顺序读到第七章。第八到十二章按需 |
| 已经会 Python 和 MuJoCo | 跳到第五章（项目架构）|
| 只想查一个名词 | 直接看第十三章速查表 |

### 全文地图

| 章 | 讲什么 | 需要前置知识 |
|---|---|---|
| 一 | 具身智能是什么、为什么需要仿真 | 无 |
| 二 | 这个项目由哪几部分组成 | 无 |
| 三 | **MuJoCo 完全入门**（物理引擎 + MJCF 语法） | 无 |
| 四 | 三个时钟：物理步长 / 控制周期 / 渲染帧率 | 第三章 |
| 五 | 项目的两条并行架构 | 第三、四章 |
| 六 | 配置系统（robot YAML / task YAML / 继承） | 第三章 |
| 七 | 一个任务从命令行到物理步进的完整链路 | 第三到六章 |
| 八 | 逆运动学（IK）怎么解 | 第三章 |
| 九 | 域随机化：为什么每次都要打乱环境 | 第三章 |
| 十 | 数据采集与录制 | 第三章 |
| 十一 | 夹爪控制 | 第三章 |
| 十二 | 测试开发与 pytest 入门 | 无 |
| 十三 | 名词速查表 | 无 |

### 约定

- ⚠️ 标记「容易踩坑的地方」
- ✅ / ❌ 标记正确与错误做法
- 代码位置写成 `文件名:行号`，例如 `task_base.py:167`
- 命令行示例里的 `$PY` 指你的 Python 解释器（见第十二章环境说明）

---

## 一、具身智能与机器人仿真

### 1.1 具身智能是什么

一句话：**让 AI 控制一个有身体的机器人，在物理世界里做事。**

和你熟悉的 ChatGPT 对比一下：

| | ChatGPT | 具身智能 |
|---|---|---|
| 输入 | 文字 | **相机图像**（有时加关节角度） |
| 输出 | 文字 | **关节动作**（每个电机转多少度） |
| 有身体吗 | 没有 | **有** |
| 犯错的代价 | 说错一句话 | **摔坏一台 20 万的机械臂** |
| 反馈来源 | 人类点赞 | **物理世界**（东西抓起来了没有） |

最后两行是关键。**正因为犯错代价高、反馈来自物理世界，才必须先在仿真里练。**

英文叫 Embodied AI，"embodied" 就是「有身体的」。

### 1.2 为什么必须用仿真

假设你要教 AI 抓起一个方块。它需要试多少次？

强化学习和模仿学习这类方法，动辄需要**几十万到几百万次**尝试。算一下：

| | 真机器人 | 仿真 |
|---|---|---|
| 一次尝试耗时 | 约 10-30 秒（还要人工摆回原位） | 约 0.1-1 秒 |
| 一天能做多少次 | 约 100 次（还得有人看着） | **约 100 万次**（无人值守） |
| 摔坏了怎么办 | 送修，几千到几万块 | 按一下重置 |
| 能不能同时跑 100 个 | 要买 100 台机器人 | 开 100 个进程 |

**没有仿真，具身智能根本训不出来。** 这是整个领域的基础设施。

### 1.3 仿真的三个用途

在这个项目里，仿真同时干三件事：

**① 数据工厂** —— 最主要的用途。批量生成「看到什么 → 该怎么动」的配对数据，用来训练 AI。

```
跑 1000 遍「抓方块」任务
  → 每遍录下 300 帧图像 + 对应的关节指令
  → 得到 30 万条训练数据
  → 喂给模仿学习算法
```

**② 策略训练场** —— AI 直接在仿真里边试边学（强化学习）。

**③ 回归测试台** —— 改了代码之后，跑一遍仿真看有没有变差。**这就是你要做的测试开发工作。**

### 1.4 一个绕不开的难题：sim-to-real gap

仿真再好也不是真实世界。仿真里学会的技能搬到真机上，往往就不работает了。原因：

| 差异来源 | 例子 |
|---|---|
| 物理不准 | 仿真里的摩擦系数是个猜的数字 |
| 视觉不像 | 仿真渲染的图像和真实照片差别大 |
| 传感器噪声 | 真实相机有噪点、有畸变、会过曝 |
| 机械误差 | 真实电机有齿轮间隙、有延迟 |

这个差距叫 **sim-to-real gap**（仿真到真实的鸿沟）。**第九章讲的「域随机化」就是缩小它的主要手段之一。**

---

## 二、这个项目是什么

### 2.1 一句话定位

DISCOVERSE 是一个**机器人仿真平台**：给你一个虚拟的机械臂和虚拟的桌面场景，让你写代码控制它完成抓取、放置这类任务，并把过程录成训练数据。

是清华大学的项目（`pyproject.toml:29` 作者邮箱 `@mails.tsinghua.edu.cn`），发表在 IROS 2025，MIT 开源协议。

### 2.2 三大部分

```
DISCOVERSE/
├── models/       3D 模型和场景描述  ← 「世界长什么样」
├── discoverse/   核心 Python 库     ← 「怎么控制、怎么判断成功」
└── policies/     AI 算法            ← 「怎么学」
```

实测规模（`find` + `wc -l` 统计）：

| 部分 | 文件数 | 代码行数 | 说明 |
|---|---|---|---|
| `discoverse/` | 52 个 `.py` | 7,396 行 | **核心库，你主要看这里** |
| `examples/` | 84 个 `.py` | 18,542 行 | 示例和运行脚本 |
| `policies/` | 237 个 `.py` | — | 5 种 AI 算法，**本文不涉及** |
| `models/meshes/` | 957 个 `.obj` 等 | 427 MB | 3D 网格文件 |

`discoverse/` 内部：

| 子目录 | 文件 | 行数 | 干什么 |
|---|---|---|---|
| `universal_manipulation/` | 10 | **1,980** | **新架构，配置驱动**（重点） |
| `envs/` | 4 | 1,276 | 老架构的仿真器基类 |
| `robots_env/` | 7 | 946 | 老架构的机器人环境 |
| `task_base/` | 5 | 681 | 老架构的任务基类 |
| `robots/` | 5 | 546 | 解析法 IK 求解器 |
| `utils/` | 8 | 603 | 工具函数 |
| `configs/` | 0 | 0 | **YAML 配置文件**（不是代码） |

### 2.3 支持哪些机器人

**9 种机械臂**（固定底座，`discoverse/configs/robots/*.yaml` 各一个文件）：

| 名字 | 厂商 | 轴数 | 说明 |
|---|---|---|---|
| `airbot_play` | 有鹿机器人（国产） | 6 | **本项目主力**，仓库名 `airbot-play` 就是它 |
| `panda` | Franka Emika（德国） | 7 | 学术界最常用的研究平台 |
| `ur5e` | Universal Robots（丹麦） | 6 | 工业协作臂标杆 |
| `iiwa14` | KUKA（德国） | 7 | 工业级力控臂 |
| `xarm7` | UFACTORY（国产） | 7 | 中低成本 7 轴 |
| `piper` | AgileX 松灵（国产） | 6 | 轻量教育/科研 |
| `rm65` | RealMan 睿尔曼（国产） | 6 | 国产协作臂 |
| `arx_x5` / `arx_l5` | ARX 方舟无限（国产） | 6 | 同厂两个型号 |

> **6 轴 vs 7 轴**：空间中一个物体的位姿需要 6 个数确定（3 个位置 + 3 个朝向），所以 6 轴刚好够用。第 7 轴是**冗余**自由度 —— 同一个末端位姿有无穷多组关节角组合，可以用来绕开障碍物或避开奇异点。代价是 IK 求解更复杂。

**2 种双臂移动机器人**（有轮子，能走）：

| 名字 | 自由度 | 组成 |
|---|---|---|
| MMK2 | 19 | 2 轮 + 1 升降 + 2 头部 + 12 双臂 + 2 夹爪 |
| Tok2 | 16 | MMK2 简化版，无升降 |

⚠️ **新架构目前只支持固定底座的单臂机械臂。** 移动机器人只能走老架构（见第五章）。证据：新架构的数据记录函数叫 `recoder_single_arm`（单臂）。

### 2.4 支持哪些任务

`models/mjcf/task_environments/` 有 **13 个**场景 XML，但 `discoverse/configs/tasks/` 只有 **5 个**任务 YAML：

| 任务 | 描述 |
|---|---|
| `place_block` | 把绿方块放进粉碗 |
| `place_coffeecup` | 把咖啡杯放到白盘子上 |
| `place_kiwi_fruit` | 把猕猴桃放进花碗 |
| `stack_block` | 把三个方块叠起来 |
| `cover_cup` | 把杯盖盖到咖啡杯上 |

剩下 8 个场景（开抽屉、推鼠标、关笔记本等）只有老架构的 Python 脚本，还没迁移到新架构。

**所以「9 机械臂 × 5 任务 = 45 种组合」是新架构当前的测试矩阵。**

### 2.5 这个项目的核心设计思想

**机器人和场景是分开写的，运行时才拼起来。**

```
robot_airbot_play.xml     （只描述机械臂）
        +
place_block.xml           （只描述桌子、方块、碗）
        ↓ 运行时用 Python 拼接
airbot_play_place_block.xml   （完整场景）
```

好处是**组合爆炸被避免了**：9 种机械臂 × 13 种场景 = 117 种组合，但只需维护 9 + 13 = 22 个文件。

拼接代码在 `discoverse/envs/make_env.py`，第七章详讲。

---

## 三、MuJoCo 完全入门

### 3.1 物理引擎是什么

**物理引擎 = 一个会算物理的程序。**

你告诉它：
- 世界里有哪些物体，形状多大，多重
- 它们怎么连接（哪个关节连着哪两段）
- 现在给某个关节施加多大力矩

它算出：
- 0.002 秒后，每个物体移动到哪里了
- 有没有发生碰撞，碰撞产生多大的力

**MuJoCo** 全称 Multi-Joint dynamics with Contact（多关节接触动力学），Google DeepMind 开源，是机器人学习领域的标准工具。特点是**关节机构算得快又准**，特别适合机械臂。

### 3.2 三个核心概念

这三个词理解了，后面全部通顺。

```
MJCF（一个 XML 文件）
   ↓ 编译（耗时约 260 毫秒）
MjModel（不变的东西）  +  MjData（会变的东西）
   ↓ mj_step() 一步一步算
物理仿真
```

#### MJCF —— 机器人的「图纸」

MJCF = MuJoCo XML Configuration Format，就是 MuJoCo 用的 XML 格式。文件后缀 `.xml`，根标签是 `<mujoco>`。

它描述「世界长什么样」：有几个物体、什么形状、怎么连接、装了什么电机。

#### MjModel —— 编译后的「不变量」

```python
model = mujoco.MjModel.from_xml_path("robot_airbot_play.xml")
```

这一行做了很多事：读 XML → 解析 → 加载 3D 网格文件 → 计算碰撞几何 → 生成内部数据结构。**实测耗时约 260 毫秒**（不算快）。

`MjModel` 里装的都是**永远不变**的信息：

| 属性 | 含义 |
|---|---|
| `model.nq` | 描述姿态需要几个数字 |
| `model.nu` | 你能下几个控制指令 |
| `model.nv` | 速度维度 |
| `model.njnt` | 有几个关节 |
| `model.nkey` | 有几个预设姿态（keyframe） |

**因为不变，所以可以让所有测试共用一份** —— 这是第十二章 `scope="session"` 的理由。

#### MjData —— 运行时的「状态」

```python
data = mujoco.MjData(model)
```

装的是**每一刻都在变**的东西：

| 属性 | 含义 | 数组长度 |
|---|---|---|
| `data.qpos` | 现在所有关节的位置 | `model.nq` |
| `data.qvel` | 现在的速度 | `model.nv` |
| `data.ctrl` | 你下发的控制指令 | `model.nu` |
| `data.time` | 仿真到第几秒了 | 1 |
| `data.sensordata` | 所有传感器读数 | 依传感器而定 |

**因为会变，所以绝不能跨测试复用。** 测试 A 让机械臂跑了 1000 步，测试 B 拿到的就是「已经跑了 1000 步」的状态而不是初始状态 —— 这会导致「单独跑绿、一起跑红、换个顺序又绿了」的诡异 bug。

### 3.3 ⚠️ 最重要的一件事：`nq` 和 `nu` 为什么不相等

这是初学者最容易困惑的地方，也是理解这个项目的关键。

以 `airbot_play` 为例，实测：

```
nq = 8     ← 描述姿态需要 8 个数
nu = 7     ← 只能下 7 个指令
```

**为什么差 1？因为夹爪。**

```
6 个手臂关节  → 6 个 qpos，6 个 ctrl   （一对一）
夹爪         → 2 个 qpos，1 个 ctrl   ← 这里错位了！
──────────────────────────────────
合计          8 个 qpos，7 个 ctrl
```

夹爪物理上有**两根手指**，各自是一个独立关节（`endleft` 和 `endright`），所以占 **2 个 qpos**。

但你只需要下**一个**指令 —— 「张开 4 厘米」。两根手指被机械结构（齿轮或连杆）绑在一起，动作永远对称。所以只有 **1 个 ctrl**。

```python
你写:      data.ctrl[6] = 0.04         ← 1 个数
物理结果:   data.qpos[6] = 0.04  (左指)  ← 2 个数
           data.qpos[7] = -0.04 (右指)
```

#### 四种夹爪实现方式

不同机器人用不同方式实现这个「联动」，配置文件里的 `gripper.type` 字段记录了它：

| `type` 值 | 中文 | 实现方式 | 占几个 qpos |
|---|---|---|---|
| `two_finger_tendon` | 双指·肌腱 | 用 `<tendon>` 定义一根虚拟「绳子」拉两指 | 2 |
| `two_finger_equality` | 双指·等式约束 | 用 `<equality>` 声明「左指角度 = -右指角度」 | 2 |
| `two_finger_single` | 单指 | 只建模一个可动指，另一指焊死 | **1** |
| `multi_finger_equality` | 多指 | 三指或更多 + 等式约束 | 更多 |

**这解释了各机器人 qpos 的差异**（第六章有完整表格）。

### 3.4 逐行读懂一个真实的 MJCF

`models/mjcf/manipulator/robot_airbot_play.xml` 全文只有 27 行：

```xml
<mujoco model="airbot_play">
  <compiler angle="radian" meshdir="../../meshes/" texturedir="../../meshes/" autolimits="true"/>

  <include file="../scene/skybox.xml"/>
  <include file="airbot_play/airbot_play_dependencies.xml"/>
  <include file="airbot_play/airbot_play_appendix.xml"/>

  <worldbody>
    <body name="airbot_play_pose" pos="0 0 0.78" euler="0 0 0">
      <include file="airbot_play/airbot_play.xml"/>
    </body>
  </worldbody>

  <actuator>
    <include file="airbot_play/airbot_play_control.xml"/>
  </actuator>

  <sensor>
    <include file="airbot_play/airbot_play_sensor.xml"/>
  </sensor>

  <keyframe>
    <key name="home" qpos='0 -1 1.2 1.5708 -1.2 -1.5708 0 0' ctrl='0 -1 1.2 1.5708 -1.2 -1.5708 0'/>
  </keyframe>
</mujoco>
```

**这个文件自己几乎什么都不描述 —— 它是一张「目录」。** 真正内容全在被 `include` 的 5 个文件里。

#### `<include>` —— 就是纯文本粘贴

和 C 语言的 `#include` 一模一样：编译时把目标文件内容原地展开。**没有命名空间、没有作用域隔离。**

三条规则：

1. **路径相对于「当前 XML 所在目录」**，不是工作目录。本文件在 `manipulator/` 下，所以 `../scene/skybox.xml` 指向 `models/mjcf/scene/skybox.xml`。

2. **被包含的文件根标签必须是 `<mujocoinclude>`，不是 `<mujoco>`**。这是 MuJoCo 区分「完整模型」和「代码片段」的标记。

3. **名字全局共享**。`airbot_play.xml` 里定义了 `<joint name="joint1">`，`airbot_play_control.xml` 里就能直接 `joint="joint1"` 引用 —— 因为展开后它们在同一个文件里。

#### `<compiler>` —— 编译选项

```xml
<compiler angle="radian" meshdir="../../meshes/" texturedir="../../meshes/" autolimits="true"/>
```

| 属性 | 含义 |
|---|---|
| `angle="radian"` | 文件里所有角度按**弧度**解读（默认是度）。所以 `1.5708` = 90° = π/2 |
| `meshdir` | 3D 网格的搜索根目录。`<mesh file="airbot_play/link1.obj"/>` 实际找 `models/meshes/airbot_play/link1.obj` |
| `autolimits="true"` | 写了 `range` 就自动启用关节限位 |

#### `<body>` —— 刚体与运动学树

`airbot_play.xml` 是一串**层层嵌套**的 `<body>`：

```
arm_base （底座）
└── link1   joint1     ← pos="0 0 0.1172"
    └── link2   joint2
        └── link3   joint3
            └── link4   joint4
                └── link5   joint5
                    └── link6   joint6 + camera "eye_arm" + site "endpoint"
                        ├── left    endleft  （左夹爪指）
                        └── right   endright （右夹爪指）
```

**嵌套 = 父子连接关系。** 这叫**运动学树**（kinematic tree）：`link2` 写在 `link1` 内部，意味着 link1 转动时 link2 跟着走。

**子 body 的 `pos` 是相对父 body 的偏移**，不是世界坐标。`<body name="link1" pos="0 0 0.1172">` 表示 link1 的原点在 arm_base 原点上方 11.72 厘米。

`<inertial>` 是质量属性：

```xml
<inertial pos="7.9126e-05 -0.002527 -0.0041359" mass="0.54639"
          diaginertia="0.000346294 0.000325437 0.000286269"/>
```

`mass` 是质量（0.546 千克），`pos` 是质心位置，`diaginertia` 是转动惯量。这些数一般从 CAD 软件导出，不是手写的。

#### `<joint>` —— 关节（自由度）

```xml
<joint name="joint1" class="joint1"/>
```

看起来什么参数都没有，因为**参数全在 `class` 里**。这是 MuJoCo 的 `<default>` 机制（类似 CSS 的类）。看 `airbot_play_dependencies.xml:11-14`：

```xml
<default class='joint1'>
  <joint axis='0 0 1' range="-3.151 2.089" actuatorfrcrange="-24 24" damping="0.2" frictionloss='15' />
  <position ctrlrange="-3.151 2.089"/>
</default>
```

| 属性 | 含义 |
|---|---|
| `axis='0 0 1'` | 绕自己的 Z 轴旋转 |
| `range="-3.151 2.089"` | 可转 -180.5° 到 +119.7°（弧度） |
| `actuatorfrcrange="-24 24"` | 电机最大力矩 ±24 牛·米 |
| `damping="0.2"` | 阻尼（转速越快阻力越大，模拟粘性摩擦） |
| `frictionloss='15'` | 静摩擦（要克服 15 牛·米才能动，模拟减速器摩擦） |

**注意力矩分布**：joint1-3（大臂）是 ±24 牛·米、摩擦 15；joint4-6（腕部）是 ±8、摩擦 5。**越靠末端电机越小** —— 符合真实机械臂设计，因为大臂要撑住整条臂的重量。

**关节类型**：夹爪关节是**平移**而非旋转：

```xml
<default class='finger1'>
  <joint axis='0 1 0' range="-0.04 0" type='slide' damping="1"/>
</default>
```

`type='slide'` = 滑动关节（英文也叫 prismatic）。两指范围互为镜像（`-0.04~0` 和 `0~0.04`），各滑 4 厘米，合起来开口 8 厘米。

MuJoCo 的关节类型共四种：

| type | 中文 | 占几个 qpos |
|---|---|---|
| `hinge` | 铰链（旋转），**默认** | 1 |
| `slide` | 滑动（平移） | 1 |
| `ball` | 球关节 | 4（四元数） |
| `free` | **自由**（可以随便飞） | **7**（3 位置 + 4 四元数） |

⚠️ **`free` 关节非常重要**：它表示「这个物体不受约束，会掉、会滚、能被抓起来」。**这就是「可操作物体」的标志。** 桌子没有 joint，所以钉死在世界上。

#### `<geom>` —— 几何形状（碰撞 + 视觉分离）

这是初学者第二个容易困惑的点：**同一个 body 上挂了好几个 geom，有的用来「看」，有的用来「碰」**。

`airbot_play.xml:5-8`（arm_base 上有 4 个 geom）：

```xml
<geom type="box" pos="-0.02 0 0.005" size="0.0806 0.1375 0.0025" class="collision"/>
<geom type="box" pos="-0.015 0 0.045" size="0.07 0.05 0.04" class="collision"/>
<geom mesh="arm_base_0" material="Gree_Light_Base" class="visual"/>
<geom mesh="arm_base_1" material="Paint_Matte_Black" class="visual"/>
```

两个 `class` 的定义：

```xml
<default class="visual">
  <geom group="2" type="mesh" contype="0" conaffinity="0"/>
</default>
<default class="collision">
  <geom group="3" condim="6" friction="1 0.005 0.0001" type="mesh"/>
</default>
```

| class | `contype`/`conaffinity` | 用途 | 形状 |
|---|---|---|---|
| `visual` | **都是 0 → 完全不参与碰撞** | 只为了画面好看 | 精细 mesh |
| `collision` | 参与碰撞 | 物理计算 | **简单的 box** |

**为什么要分开？** 碰撞检测是仿真里最贵的运算。一个几万三角形的 mesh 做碰撞检测慢得没法用；换成 2 个 box，速度快几个数量级，而精度对抓取任务足够。**这是机器人仿真的标准做法。**

其他重要属性：

| 属性 | 含义 |
|---|---|
| `group="2"`/`"3"` | 渲染分组。MuJoCo viewer 里按数字键 2/3 可切换显示，方便调试 |
| `condim="6"` | 接触约束维度。6 = 同时算法向力 + 切向摩擦 + 扭转摩擦。**抓取任务必须用 6**，否则物体会从夹爪里「转」出去 |
| `friction="1 0.005 0.0001"` | 滑动 / 自旋 / 滚动摩擦系数 |

⚠️ **`size` 的坑**：对 `type="box"`，`size` 是**半长**（half-extent）。`size="0.0145 0.0145 0.0145"` 是边长 **2.9 厘米**的立方体，不是 1.45 厘米。

#### `<site>` —— 无质量的标记点

```xml
<site name="armbase"/>
<site name="endpoint" pos='0 0 0.015' euler="0 -1.5708 0"/>
```

**site 是一个「坐标系标签」** —— 没有质量、没有碰撞、不影响物理，纯粹用来标记「我关心这个位置和朝向」。

| site 名 | 用途 |
|---|---|
| `endpoint` | **末端执行器**（工具中心点，TCP）。逆运动学的目标就是让它到达指定位姿 |
| `armbase` | 底座参考系，用来算「末端相对底座」的位姿（比世界坐标更有用） |

这两个名字在配置文件里被引用（`airbot_play.yaml:7-8`）：

```yaml
base_link: "arm_base"
end_effector_site: "endpoint"
```

#### `<camera>` —— 相机

```xml
<body pos="-0.105 0 -0.12" euler="3.1416 0 1.5708">
  <camera name="eye_arm" euler="-0.5236 0 0" fovy="72.5376526571421"/>
</body>
```

`eye_arm` = **腕部相机**（eye-in-hand），装在 link6 上，跟着夹爪一起动。因为写在 body 内部，位姿自动跟随手臂。

`fovy` 是垂直视场角（单位是度），72.54° 对应一个广角镜头。`-0.5236` 弧度 = -30°，相机往下俯 30° 看着夹爪。

另一个相机 `eye_side`（第三人称侧视）在场景文件 `models/mjcf/scene/qz_lab3.xml:26` 里。

#### `<actuator>` —— 执行器（电机）

`airbot_play_control.xml` 全文：

```xml
<mujocoinclude>
  <position name="joint1" joint="joint1" kp="1000" ctrlrange="-3.151 2.089" forcerange="-300 300"/>
  <position name="joint2" joint="joint2" kp="1000" ctrlrange="-2.963 0.181" forcerange="-300 300"/>
  <position name="joint3" joint="joint3" kp="1000" ctrlrange="-0.094 3.161" forcerange="-300 300"/>
  <position name="joint4" joint="joint4" kp="350"  ctrlrange="-3.012 3.012" forcerange="-300 300"/>
  <position name="joint5" joint="joint5" kp="350"  ctrlrange="-1.859 1.859" forcerange="-300 300"/>
  <position name="joint6" joint="joint6" kp="100"  ctrlrange="-3.017 3.017" forcerange="-300 300"/>
  <position name='gripper' tendon='gripper_gear' kp="30" ctrlrange="0. 0.04" forcerange="-15 15"/>
</mujocoinclude>
```

**`<position>` = 位置伺服执行器。** 你给它一个「目标角度」，它内部跑一个 P 控制器算出力矩：

```
力矩 = kp × (目标角度 - 当前角度)
```

`kp` 是比例增益，也就是「刚度」：

| 执行器 | `kp` | 为什么 |
|---|---|---|
| joint1-3（大臂） | 1000 | 要撑住整条臂的重量 |
| joint4-5 | 350 | 负载小 |
| joint6（腕部） | 100 | 负载最小 |
| gripper（夹爪） | **30** | **软一点，抓东西不会捏碎** |

⚠️ **注意最后一行**：夹爪执行器不接 `joint`，而接 `tendon='gripper_gear'`。

**数一下：7 个 `<position>` → `nu = 7`。** 而 qpos 是 8。这就是 3.3 节讲的错位。

#### `<tendon>` + `<equality>` —— 夹爪联动的实现

`airbot_play_appendix.xml` 全文：

```xml
<mujocoinclude>
  <contact>
    <exclude body1='arm_base' body2='link2'/>
  </contact>

  <tendon>
    <fixed name='gripper_gear'>
      <joint joint='endleft'  coef='0.5'/>
      <joint joint='endright' coef='-0.5'/>
    </fixed>
  </tendon>

  <equality>
    <joint joint1='endleft' joint2='endright' polycoef='0 -1 0 0 0 '/>
  </equality>
</mujocoinclude>
```

三块，逐个看：

**`<contact><exclude>`** —— 告诉引擎「arm_base 和 link2 永远不用检查碰撞」。因为它们靠得很近，简化的碰撞几何可能造成**虚假的自碰撞**，导致手臂卡死。这是调仿真的常用手段。

**`<tendon>`** —— 「肌腱」，一个**虚拟的线性组合自由度**：

```
gripper_gear = 0.5 × endleft + (-0.5) × endright
```

两指对称张开到最大时：

```
0.5 × 0.04 - 0.5 × (-0.04) = 0.02 + 0.02 = 0.04
```

正好等于执行器的 `ctrlrange="0. 0.04"`。**所以「一个数字」就能控制「两根手指」。**

**`<equality>`** —— 等式约束，强制两指镜像同步：

```xml
<joint joint1='endleft' joint2='endright' polycoef='0 -1 0 0 0'/>
```

`polycoef` 是多项式系数 `[a0, a1, a2, a3, a4]`，约束形式：

```
endleft = a0 + a1×endright + a2×endright² + ...
```

这里 `a1 = -1`，即 **`endleft = -endright`**。物理上模拟真实夹爪里的齿轮同步机构。

> tendon 提供**控制入口**，equality 强制**物理同步** —— 双重保险。

#### `<sensor>` —— 传感器

`airbot_play_sensor.xml` 分四组：

```xml
<jointpos name="joint1_pos" joint="joint1" />          <!-- 关节角度 ×6 -->
<tendonpos name="gripper_pos" tendon="gripper_gear" /> <!-- 夹爪开口 -->

<jointvel name="joint1_vel" joint="joint1" />          <!-- 角速度 ×6 -->
<jointactuatorfrc name="joint1_torque" joint="joint1" /> <!-- 力矩 ×6 -->

<framepos  name="endpoint_pos"  objtype="site" objname="endpoint" reftype="site" refname="armbase"/>
<framequat name="endpoint_quat" objtype="site" objname="endpoint" reftype="site" refname="armbase"/>
```

**⚠️ 为什么不直接读 `qpos`，要绕一圈用 sensor？**

因为**在真机上你只能拿到传感器读数**。用 sensor 接口写代码，仿真和真机可以共用同一套代码 —— 这就是 sim-to-real 的工程考量。

`reftype="site" refname="armbase"` 很重要：末端位姿是**相对底座**测量的，不是世界坐标。这样机械臂整体挪位置后读数不变。

⚠️ **传感器索引不是一对一的**。`endpoint_pos` 是 3 维、`endpoint_quat` 是 4 维，而 `joint1_pos` 是 1 维。所以「第 N 个传感器」和「sensordata 的第 N 个元素」不是一回事，要用 `mj_name2id` 按名字查。

#### `<keyframe>` —— 预设姿态

```xml
<key name="home" qpos='0 -1 1.2 1.5708 -1.2 -1.5708 0 0' ctrl='0 -1 1.2 1.5708 -1.2 -1.5708 0'/>
```

`home` 是「初始/归位姿态」。**数一下：`qpos` 8 个数，`ctrl` 7 个数** —— 又一次印证 8/7 错位。

运行时用它复位：

```python
mujoco.mj_resetDataKeyframe(mj_model, mj_data, mj_model.key(0).id)
```

⚠️ **`name="home"` 是硬要求。** `make_env.py:259-262` 明确按名字查找：

```python
for k in robot_keyframe.findall("key"):
    if k.get("name") == "home":
        key_elem = k
```

新增机械臂时如果 keyframe 不叫 `home`，拼接会静默丢掉它，后续 IK 会因为「模型没有 keyframe」而报错。

### 3.5 最常用的几个 API

```python
import mujoco

# 加载与初始化
model = mujoco.MjModel.from_xml_path("robot.xml")   # 编译 XML（贵，约 260ms）
data  = mujoco.MjData(model)                        # 分配状态（便宜）

# 前向运动学：只算位置，不推进时间
mujoco.mj_forward(model, data)

# 物理步进：推进一个 timestep
mujoco.mj_step(model, data)

# 复位
mujoco.mj_resetData(model, data)                              # 归零
mujoco.mj_resetDataKeyframe(model, data, model.key(0).id)     # 归到 keyframe

# 按名字查 id（找不到返回 -1，⚠️ 不抛异常！）
site_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "endpoint")

# 按名字访问（找不到会抛 KeyError）
pos = data.body("block_green").xpos      # 物体位置
```

⚠️ **`mj_name2id` 找不到时返回 `-1`，不抛异常。** 而 NumPy 里 `array[-1]` 是**最后一个元素** —— 所以名字写错会静默取到错误的数据。这是个很难查的坑。

对比：

| 写法 | 找不到时 |
|---|---|
| `mj_name2id(...)` | ❌ 返回 `-1`，静默取到末位元素 |
| `data.body("名字")` | ✅ 抛 `KeyError`，立刻发现 |

### 3.6 渲染后端：glfw / egl / osmesa

MuJoCo 渲染需要 OpenGL，而不同环境下可用的 OpenGL 实现不同。用环境变量 `MUJOCO_GL` 选择：

| 值 | 中文 | 用在哪 | 需要显示器 | 需要 GPU |
|---|---|---|---|---|
| `glfw` | 窗口渲染 | 本地开发，有屏幕 | ✅ 需要 | 是 |
| `egl` | GPU 离屏渲染 | 服务器有显卡 | ❌ 不需要 | 是 |
| `osmesa` | CPU 软件渲染 | CI、无显卡环境 | ❌ 不需要 | **不需要** |

```bash
export MUJOCO_GL=osmesa    # 无头环境（CI）用这个
export MUJOCO_GL=glfw      # 本地看画面用这个
```

⚠️ 在没有显示器的机器上用 `glfw` 会直接报错。**CI 环境必须用 `osmesa` 或 `egl`。**

---

## 四、三个时钟：timestep / decimation / render_fps

这一章讲一个容易混淆但很重要的概念：**仿真里有三个不同的时间频率。**

### 4.1 三个时钟分别是什么

| 名字 | 含义 | 典型值 |
|---|---|---|
| `opt.timestep` | **物理步长** —— 引擎每次积分推进多少秒 | 0.0025 或 0.005 秒 |
| `decimation` | **降采样倍数** —— 一次控制决策对应几个物理步 | 4 或 5 |
| `render_fps` | **渲染帧率** —— 每秒画几帧 | 24 或 60 |

关系：

```
控制周期 delta_t = opt.timestep × decimation
```

以 MMK2 为例（`mmk2_base.py` 实测）：

```
opt.timestep = 0.0025 秒   →  物理频率 = 1/0.0025 = 400 Hz
decimation   = 4
delta_t      = 0.0025 × 4 = 0.01 秒  →  控制频率 = 100 Hz
```

**所以：物理每秒算 400 次，但控制器每秒只做 100 次决策。**

### 4.2 为什么要分开

**物理需要小步长才稳定。** 步长太大，物体会「穿模」（一步跨过了墙）、数值会爆炸。

**但控制器不需要那么高频。** 真实机械臂的控制频率通常是 100-1000 Hz，而且每次决策都要算 IK、跑神经网络，很贵。

所以：

```
控制器决策 1 次
  → 物理引擎用同一个指令连续算 4 步
  → 省下 3 次决策的计算量
```

这是仿真的标准做法，叫 **frame skipping** 或 **action repeat**。

### 4.3 渲染为什么也要节流

渲染比物理更贵（要画几十万个三角形）。如果每个物理步都渲染，仿真会慢到没法用。

`simulator.py:649` 的节流逻辑：

```python
if self.config.enable_render and self.render_cnt-1 < self.mj_data.time * self.render_fps:
    self.render()
```

**注意它按「仿真时钟」节流，不是按挂钟时间。** `mj_data.time` 是仿真内部的时间。所以：

```
仿真时间走到 1.0 秒，render_fps=24
  → 应该已经画了 24 帧
  → 如果 render_cnt 还不到 24，就补一帧
```

好处：**渲染帧率与仿真速度解耦**。仿真跑得比实时快 10 倍时，录出来的视频仍然是正常的 24 fps。

### 4.4 ⚠️ 两条路线的 `step()` 实现不同

这个项目有两套架构（第五章详讲），它们的 `step()` 写法有一个**实质差异**：

**老架构** `simulator.py:639-652`：

```python
def step(self, action=None):
    for _ in range(self.decimation):
        self.updateControl(action)          # ← 在循环【内】
        mujoco.mj_step(self.mj_model, self.mj_data)
    ...
    return self.getObservation(), self.getPrivilegedObservation(), self.getReward(), terminated, {}
```

**新架构** `universal_task_runtime.py:252-255`：

```python
self.mj_data.ctrl[:self.mujoco_ctrl_dim] = self.action[:self.mujoco_ctrl_dim]   # ← 在循环【外】

for _ in range(decimation):
    mujoco.mj_step(self.mj_model, self.mj_data)
```

| | 老架构 | 新架构 |
|---|---|---|
| 控制指令写入位置 | **循环内**，每个物理步都重写 | **循环外**，5 个物理步共用 |
| 返回值 | 5 元组（Gym 风格） | `bool` |
| `decimation` 来源 | `config.decimation`（可配） | **硬编码的函数默认参数 `step(decimation=5)`** |

对位置伺服来说两者结果几乎相同（目标值不变，重复写入无害）。但**如果将来要做「步内插值」（每个物理步给略微不同的指令），只有老架构的结构支持。**

⚠️ 新架构的 `decimation` 无法通过 YAML 配置，只能改源码。

---

## 五、项目的两条并行架构

### 5.1 核心事实：这个项目有两套独立的框架

这是理解代码库最重要的一件事。实测（`grep` 验证）：

```
Route A（老）:  discoverse/envs/simulator.py  SimulatorBase（658 行）
                    ↑ 继承
                discoverse/robots_env/*_base.py（7 个文件）
                    ↑ 继承
                discoverse/task_base/*_task_base.py（4 个文件）
                    ↑ 使用
                examples/tasks_airbot_play/*.py（12 个）
                examples/tasks_mmk2/*.py（9 个）

Route B（新）:  discoverse/universal_manipulation/task_base.py  UniversalTaskBase（306 行）
                    ↑ 使用
                examples/universal_tasks/universal_task_runtime.py（509 行）
```

**实测：`universal_manipulation/` 里没有任何一行 import `SimulatorBase`。** 两条路线几乎完全独立。

唯一共享的东西：

| 共享项 | 位置 |
|---|---|
| `SimpleStateMachine` | `utils/statemachine.py` |
| `step_func`（线性插值） | `utils/__init__.py:68` |
| `get_body_tmat` / `get_site_tmat` | `utils/__init__.py` |
| `make_env`（XML 拼接） | `envs/make_env.py` |
| 最终都调 `mujoco.mj_step` | — |

### 5.2 两条路线的设计哲学对比

| 维度 | Route A（老） | Route B（新） |
|---|---|---|
| **扩展方式** | 写 Python 子类 | 写 YAML 配置 |
| 加新机器人 | 新建一个 `*_base.py` 子类 | 新建一个 `.yaml` + MJCF |
| 加新任务 | 抄一个脚本改 200 行 Python | 写 1 个 XML + 1 个 YAML |
| 动作序列 | `if stm.state_idx == N:` 链 | YAML `states` 列表 |
| 成功判定 | 手写 `check_success()` 方法 | YAML `success_check` 条件 |
| 随机化 | 手写，直接改 `qpos` 索引 | YAML 声明 |
| IK 求解 | **解析法**（闭式解，瞬间） | **迭代 QP**（mink 库，可能不收敛） |
| 配置载体 | Python 类 `BaseConfig` | YAML 文件 |
| 3DGS 高保真渲染 | ✅ 支持 | ❌ **未接入** |
| 移动机器人 | ✅ 支持（MMK2/Tok2） | ❌ 只支持固定底座单臂 |
| 代码量 | 多 | 少 |

**总结**：新架构更干净、更少代码、跨机器人复用好；但功能覆盖窄，且丢了 3DGS 渲染（这是论文的核心卖点）。

### 5.3 Route A：`SimulatorBase` 的生命周期

`SimulatorBase`（`simulator.py:42`）是老架构的核心类，一个「大而全」的对象：MuJoCo 模型加载 + GLFW 窗口 + 键鼠交互 + 可选 3DGS 渲染 + 物理循环。

完整流程：

```
__init__(config)                      simulator.py:73
  ├─ 解析 mjcf_file_path（相对/绝对）
  ├─ load_mjcf()                      :215
  │    ├─ from_xml_path 或 from_binary_path
  │    ├─ opt.timestep = config.timestep    ← :220 配置在这里进入 MuJoCo
  │    ├─ 建 mujoco.Renderer
  │    ├─ 扫描所有 dofnum==6 的 body → free_body_qpos_ids   ← :261-265 自由物体登记表
  │    └─ post_load_mjcf()            :269  （空钩子，子类覆盖）
  ├─ 可选建 3DGS 渲染器                :92-114
  ├─ 建 GLFW 窗口                      :122-191
  └─ mj_resetData + mj_forward         :194-195

reset()                               :601
  ├─ resetState()                     :555
  ├─ render()（可选）
  └─ return getObservation()

step(action)                          :639     ← 主循环，见 4.4 节
  ├─ for _ in range(decimation): updateControl + mj_step
  ├─ checkTerminated() → 若 True 则 resetState()
  ├─ post_physics_step()
  ├─ render()（按仿真时钟节流）
  └─ return (obs, priv_obs, reward, terminated, {})

view()                                :654     ← 只播放不算物理
  ├─ mj_data.time += delta_t
  ├─ mj_data.qvel[:] = 0
  └─ mj_forward + render
```

`view()` 值得单独说：它**只算运动学不算动力学**，用来回放录好的轨迹。把 `qvel` 强制归零，只做 `mj_forward`。

#### 6 个抽象方法 = 子类必须实现的契约

`simulator.py:612-634` 声明了 6 个方法，子类要填：

| 方法 | 返回什么 |
|---|---|
| `post_physics_step()` | 无（钩子，物理步后的自定义处理） |
| `getChangedObjectPose()` | 变化的物体位姿 |
| `checkTerminated()` | `bool`，任务是否该结束 |
| `getObservation()` | 观测字典 |
| `getPrivilegedObservation()` | 特权观测（真实状态，训练时可用，真机上拿不到） |
| `getReward()` | 强化学习的奖励值 |

> **「特权观测」是什么**：仿真里你能拿到物体的精确位置（上帝视角），但真机上只有相机图像。训练时用特权信息加速学习，部署时不用 —— 这叫 privileged learning。

#### `robots_env/` 的 7 个子类

统一模式：每个文件 = 一个 `XxxCfg(BaseConfig)` + 一个 `XxxBase(SimulatorBase)`。

| 文件 | 机器人 | qpos 维度 | ctrl 维度 | timestep / decimation |
|---|---|---|---|---|
| `airbot_play_base.py` | AirBot Play | 8 | 7 | 0.005 / 4 → 200Hz 物理，50Hz 控制 |
| `mmk2_base.py` | **MMK2** | **28** | **19** | 0.0025 / 4 → 400Hz / 100Hz |
| `tok2_base.py` | Tok2 | 25 | 16 | 0.0025 / 4 |
| `rm2_car_base.py` | 轮式小车 | 22 | 13 | 0.0025 / 4 |
| `skyrover_base.py` | 无人机 | — | — | 0.0025 / 4 |
| `hand_with_arm_base.py` | 灵巧手 + 臂 | — | — | 0.001 / 4 → 1kHz 物理 |
| `leaphand_sensor_env_base.py` | LEAP 手 | — | — | 0.001 / 4 |

#### MMK2 的 19 维控制布局

`mmk2_base.py:84-92` 定义了 19 个执行器的顺序：

| ctrl 索引 | 控制什么 |
|---|---|
| 0-1 | 左右轮速度（差速驱动） |
| 2 | 升降柱高度 |
| 3-4 | 头部偏航、俯仰 |
| 5-10 | 左臂 6 轴 |
| 11 | 左夹爪 |
| 12-17 | 右臂 6 轴 |
| 18 | 右夹爪 |

**而 qpos 是 28 维**，多出来的 9 个：

```
底盘位置(3) + 底盘朝向四元数(4) = 7      ← 移动机器人的 free 关节
左夹爪第二指(1) + 右夹爪第二指(1) = 2    ← 镜像的从动指
─────────────────────────────────
28 = 19 + 7 + 2
```

> **差速驱动**（differential drive）：像坦克一样，靠左右轮转速差来转向，没有方向盘。两轮同速 = 直行，左慢右快 = 左转。

---

## 六、配置系统

### 6.1 YAML 语法速成

YAML 是一种配置文件格式，比 JSON 更适合人写。

```yaml
robot_name: panda          # 键: 值
dof: 7                     # 数字不加引号
enabled: true              # 布尔值

kinematics:                # 嵌套（靠【缩进】表示层级，不是括号）
  base_link: "panda_link0"
  qpos_dim: 9

arm_joint_names:           # 列表（每项前面一个短横线）
  - joint1
  - joint2

ranges: [0.2, 0.6]         # 列表也可以写成一行

# 这是注释
```

⚠️ **三个常见坑**：

**① 缩进必须用空格，不能用 Tab。**

**② 键后面留空 = 值是 `None`，不是空字典。**

```yaml
observation:               # ← 后面什么都没写
```

```python
config['observation']       # → None（不是 {}）
config['observation'].get('fps')    # → AttributeError！
```

**③ 重复的键会被静默覆盖。** YAML 规范说这是错误，但 PyYAML 的 `safe_load` **静默取最后一个**，不报警。

> ⚠️ 这个项目的 `panda.yaml` 就有两个 `kinematics:` 键（第 6 行和第 16 行）。实测 PyYAML 取了第二个（内容正确的那个），所以程序能跑 —— 但第一个块里的内容被无声吞掉了。**详见缺陷文档。**

### 6.2 三层配置体系

这个项目的配置分三层，各管一件事：

| 层 | 文件 | 管什么 |
|---|---|---|
| **MJCF** | `models/mjcf/**/*.xml` | 物理世界：形状、质量、关节、电机 |
| **robot YAML** | `discoverse/configs/robots/*.yaml` | 这个机器人怎么控制：维度、索引、IK 参数 |
| **task YAML** | `discoverse/configs/tasks/*.yaml` | 这个任务怎么做：动作序列、成功判据、随机化 |

⚠️ **三层之间的名字必须手工保持一致，代码不会校验。** 比如 robot YAML 里写 `end_effector_site: "endpoint"`，MJCF 里就必须有 `<site name="endpoint">`。

### 6.3 robot 配置逐字段解读

以 `discoverse/configs/robots/airbot_play.yaml` 为例。

#### `kinematics:` 运动学结构

```yaml
kinematics:
  base_link: "arm_base"              # 基座 body 名，必须与 MJCF 一致
  end_effector_site: "endpoint"      # 末端 site 名，IK 的控制目标
  qpos_dim: 8                        # 状态维度 = 6 臂 + 2 夹爪指
  ctrl_dim: 7                        # 指令维度 = 6 臂 + 1 夹爪
  arm_joints: 6                      # 臂关节数
  arm_joint_names: [joint1, ..., joint6]   # 顺序敏感！
```

⚠️ **`arm_joint_names` 的顺序决定了 IK 解怎么映射到 ctrl 数组。** 顺序写错，机械臂会以诡异的姿态乱动。

#### ⚠️ 一个必须知道的命名陷阱

`robot_config.py` 里有两个属性，名字和 YAML 键**交叉错位**：

| Python 属性 | 实际返回的 YAML 键 | 类型 |
|---|---|---|
| `loader.arm_joints` | `arm_joint_names` | **list**（名字列表） |
| `loader.arm_joints_count` | `arm_joints` | **int**（数量 6） |

```
YAML: arm_joints (int 6) ─────┐    ┌──> Python: arm_joints (list)
                              ╳
YAML: arm_joint_names (list) ─┘    └──> Python: arm_joints_count (int)
```

**同一个标识符 `arm_joints`，在配置层和代码层含义相反。**

源码本身是自洽的（类型注解写的是 `List[str]`，docstring 说「关节名称列表」），但**跨层看就会困惑**。

❌ 按直觉写：`assert loader.arm_joints == 6` → 失败
✅ 正确写法：`assert loader.arm_joints_count == 6`
✅ 或者：`assert len(loader.arm_joints) == 6`

#### `gripper:` 夹爪

```yaml
gripper:
  type: "two_finger_tendon"       # 夹爪类型（4 种，见 3.3 节）
  ctrl_dim: 1                     # 占几个 ctrl
  ctrl_index: 6                   # 在 ctrl 数组的第几位（0-based）
  qpos_joints: ["endleft", "endright"]
  qpos_indices: [6, 7]            # 在 qpos 数组的哪几位
  tendon_name: "gripper_gear"     # 对应 MJCF 的 tendon 名
  ctrl_range: [0.0, 0.04]         # 0=闭合，0.04=完全打开
  default_position: 0.04
  close_position: 0.0
  sensor_name: "gripper_pos"
```

`ctrl_index: 6` 就是 ctrl 数组的第 7 位（0 起数），前面 0-5 是 6 个臂关节。

⚠️ **这个数字必须和 MJCF 里 `<position name='gripper'>` 的位置严格对应，没有自动校验。**

#### `ik_solver:` 逆运动学参数

```yaml
ik_solver:
  solver_type: "quadprog"          # 二次规划求解器
  position_tolerance: 0.01         # 位置收敛阈值 1cm
  orientation_tolerance: 0.05      # 姿态收敛阈值 0.05 弧度（约 2.9°）
  max_iterations: 50               # 最多迭代 50 次
  damping: 1.0                     # 阻尼系数
  position_cost: 100.0             # 位置任务权重
  orientation_cost: 10.0           # 姿态权重
  posture_cost: 0.01               # 姿态保持权重
  dt: 0.002                        # 积分步长
```

**三个 cost 的比例决定优先级**：

```
position_cost 100  >>  orientation_cost 10  >>  posture_cost 0.01
```

意思是「**位置最重要，朝向次之，尽量少动关节**」。

### 6.4 九个机器人的维度对照表

实测数据（读 YAML + 编译 MJCF 对比）：

| 机器人 | 臂关节 | `ctrl_dim` | MJCF `nu` | `qpos_dim` | MJCF `nq` | 夹爪类型 |
|---|---|---|---|---|---|---|
| airbot_play | 6 | 7 | 7 ✅ | 8 | 8 ✅ | two_finger_tendon |
| arx_l5 | 6 | 7 | 7 ✅ | 8 | 8 ✅ | two_finger_single |
| arx_x5 | 6 | 7 | 7 ✅ | 7 | **8** ⚠️ | two_finger_single |
| iiwa14 | 7 | 8 | 8 ✅ | 9 | **15** ⚠️ | two_finger_tendon |
| panda | 7 | 8 | 8 ✅ | 9 | 9 ✅ | two_finger_equality |
| piper | 6 | 7 | 7 ✅ | 7 | **8** ⚠️ | two_finger_single |
| rm65 | 6 | 7 | 7 ✅ | 12 | **14** ⚠️ | multi_finger_equality |
| ur5e | 6 | 7 | 7 ✅ | 8 | 8 ✅ | two_finger_single |
| xarm7 | 7 | 8 | 8 ✅ | 15 | 15 ✅ | two_finger_tendon |

**规律**：

- `ctrl_dim == arm_joints + gripper.ctrl_dim` —— **9/9 全部成立**
- `ctrl_dim == MJCF nu` —— **9/9 全部成立**
- `qpos_dim == MJCF nq` —— **只有 5/9 成立**（4 个不符，标 ⚠️）

⚠️ 那 4 个不符的属于缺陷，详见缺陷文档。

**为什么 `nu` 全对而 `nq` 有错？** 因为写错 `ctrl_dim` 会**立刻炸**（给 `data.ctrl` 赋值时长度不匹配 → `ValueError`），而写错 `qpos_dim` 只是**静默切错数组**（`qpos[:9]` 在 `nq=15` 的模型上完全合法，只是少取了 6 个）。

> **会炸的字段维护得好，不会炸的字段积累错误。** 这是软件工程的普遍规律。

### 6.5 task 配置逐字段解读

以 `discoverse/configs/tasks/cover_cup.yaml`（唯一完全自包含的任务）为例。

#### `observation:` 观测配置

```yaml
observation:
  fps: 30                # 数据录制帧率（不是仿真帧率！）
  cameras:
    - name: "eye_side"   # 第三人称相机
      fovy: 60
      width: 640
      height: 480
    - name: "eye_arm"    # 腕部相机
      fovy: 72.54
      width: 640
      height: 480
```

**为什么叫 `observation`（观测）？** 这是强化学习/模仿学习的标准术语：

```
Observation（机器人看到什么） → 策略网络 → Action（怎么动）
```

在具身智能里，「观测」通常就是相机图像。所以 `observation` 配置 = 「用什么相机、多大分辨率、多少帧率去看世界」。

⚠️ **只有 `cover_cup` 定义了 `observation`。** 其余 4 个任务没有这一节，导致 `camera_configs` 返回空列表 → **不录任何视频**。详见缺陷文档。

#### `success_check:` 成功判定

```yaml
success_check:
  method: "combined"     # simple 或 combined
  operator: "and"        # combined 时用：and 或 or
  conditions:
    - type: "orientation"
      object: "coffeecup_white"
      axis: "z"
      direction: "up"
      threshold: 0.99
      description: "咖啡杯直立（底部朝下）"
    - type: "distance_2d"
      object1: "coffeecup_white"
      object2: "plate_white"
      threshold: 0.04
      description: "咖啡杯在盘子上"
```

**两种 `method`**（`task_base.py:88-99`）：

| method | 行为 |
|---|---|
| `simple` | **短路** —— 遇到第一个不满足就返回失败 |
| `combined` | **全部评估** 后按 `operator` 归约（`and` → 全部满足；`or` → 任一满足） |

**五种 `type`**（`task_base.py:152-161`）：

| type | 实现位置 | 判断什么 |
|---|---|---|
| `distance` | `task_base.py:169` | 两物体 3D 欧氏距离 < 阈值 |
| `distance_2d` | `:181` | **只算 XY 平面**（忽略高度） |
| `position` | `:197` | 某个坐标轴的值，支持 `> < >= <=` |
| `orientation` | `:227` | 物体某轴与目标方向的余弦 > 阈值 |
| `height` | `:263` | 高度检查（内部转发给 `position`） |

`orientation` 的原理：把物体的四元数转成旋转矩阵，取出某一列（就是物体局部轴在世界系的方向），和目标方向做点积。

```
threshold: 0.99  →  余弦 > 0.99  →  倾斜角 < 约 8°  →  算「直立」
```

#### `runtime_parameters:` 运行时参数

```yaml
runtime_parameters:
  source_object: "block_green"
  target_location: "bowl_pink"
  approach_height: 0.05
  grasp_height: 0.005
```

这是**变量表**，供 `${...}` 占位符替换。第 6.7 节详讲。

#### `states:` 动作序列

这是任务的核心 —— 第七章详讲。

### 6.6 `extends` 配置继承

三个「放置类」任务的动作流程完全一样，只有「抓什么、放哪里」不同。所以做了个**模板**：

```
discoverse/configs/tasks/templates/place_object.yaml   ← 通用「抓取并放置」流程
```

然后各任务声明继承：

```yaml
# place_block.yaml（只有 89 行）
extends: "templates/place_object.yaml"

task_name: "place_block"
description: "将绿色方块抓取并放入粉色碗中"

runtime_parameters:
  source_object: "block_green"      # 只写差异部分
  target_location: "bowl_pink"
  approach_height: 0.05
```

**这个文件里没有 `states`，也没有 `success_check`** —— 全从模板继承。

#### 继承是怎么实现的

`config_utils.py:4-33`：

```python
def load_and_resolve_config(config_path: str) -> dict:
    with open(config_path) as f:
        config = yaml.safe_load(f)
    if 'extends' in config:
        template_path = config['extends']
        if not os.path.isabs(template_path):
            base_dir = os.path.dirname(config_path)       # 相对于当前配置文件
            template_path = os.path.join(base_dir, template_path)
        template_config = load_and_resolve_config(template_path)   # ← 递归！
        merged_config = merge_configs(template_config, config)
        return merged_config
    return config
```

**注意是递归调用** → 模板本身也可以有 `extends`，支持多级继承链。

合并规则（`merge_configs`，`config_utils.py:36-60`）：

| 数据类型 | 合并方式 |
|---|---|
| `dict` | **深度递归合并**（子配置只需覆盖想改的键） |
| `states` 列表 | 特殊处理，**按索引逐个覆盖** |
| 其他（含普通 list） | **整体替换** |

#### ⚠️ 对测试的重要影响

```
直接读 place_block.yaml   → 看到 5 个顶层键
用加载器加载              → 得到 12 个键（模板提供了 7 个）
```

**所以判断「配置里有什么」必须用加载器加载，不能直接读 YAML 文件。**

```python
# ❌ 错误：只看到原始文件内容
config = yaml.safe_load(open('place_block.yaml'))
assert 'states' in config     # 失败！states 在模板里

# ✅ 正确：加载器会处理 extends
from discoverse.universal_manipulation.task_config import TaskConfigLoader
loader = TaskConfigLoader('place_block.yaml')
assert 'states' in loader.config    # 通过
```

### 6.7 变量替换 `${param}`

模板里用 `${参数名}` 做占位符：

```yaml
# place_object.yaml（模板）
- name: "approach_source_above"
  primitive: "move_to_object"
  params:
    object_name: "${source_object}"
    offset: [0, 0, "${approach_height}"]
```

子配置提供值：

```yaml
# place_block.yaml
runtime_parameters:
  source_object: "block_green"
  approach_height: 0.05
```

最终得到：

```yaml
    object_name: "block_green"
    offset: [0, 0, 0.05]
```

#### 一个精巧的类型保持技巧

`config_utils.py:88-122` 的实现把整个配置序列化成 JSON 字符串再做文本替换：

```python
config_str = json.dumps(config, ensure_ascii=False)
for key, value in runtime_params.items():
    quoted_pattern = f"\"${{{key}}}\""              # 匹配 "${key}"（带引号）
    if isinstance(value, (int, float)):
        quoted_replacement = str(value)             # 数值：去掉引号！
    else:
        quoted_replacement = f'"{value}"'           # 字符串：保留引号
    config_str = config_str.replace(quoted_pattern, quoted_replacement)

    inline_pattern = f"${{{key}}}"                  # 匹配嵌在字符串中的 ${key}
    config_str = config_str.replace(inline_pattern, str(value))
return json.loads(config_str)
```

**「带引号 vs 不带引号」的区分是关键**：

```yaml
offset: [0, 0, "${approach_height}"]
```

`"${approach_height}"` 带引号 → 匹配 `quoted_pattern` → 替换成裸数字 `0.05` → JSON 解析回来是 **float 0.05**，不是字符串 `"0.05"`。

⚠️ **所以模板里所有数值占位符必须加引号。** 不加的话，YAML 解析阶段就报错（`${` 不是合法的 YAML 标量起始）。

而 `description: "${source_object}在${target_location}的5cm范围内"` 这种嵌在字符串里的，走 `inline_pattern` 分支，替换成 `"block_green在bowl_pink的5cm范围内"`。

---

## 七、一个任务从命令行到物理步进

这一章把前面所有概念串起来。

### 7.1 先跑起来看看

```bash
cd /home/ubuntu22/workspaces/airbot-play/DISCOVERSE
python examples/universal_tasks/universal_task_runtime.py -r airbot_play -t place_block -s -1
```

命令行参数（`universal_task_runtime.py:496-508`）：

| 参数 | 含义 |
|---|---|
| `-r` / `--robot` | 9 种机械臂选 1（默认 `airbot_play`） |
| `-t` / `--task` | 任务选 1（默认 `place_block`） |
| `-s` / `--sync` | **放慢到实时速度**，方便肉眼观察 |
| `-1` / `--once` | 只跑一轮（默认是无限循环刷数据） |
| `--headless` | 不开窗口（服务器/CI 用） |

不加 `-s` 时仿真会全速跑（比实时快很多），画面一闪而过。**初学者建议一定加 `-s -1`。**

⚠️ `--headless` 时要配合 `export MUJOCO_GL=osmesa`（见 3.6 节）。

### 7.2 完整链路

```
① 命令行参数解析                    universal_task_runtime.py:496
        ↓
② generate_robot_task_model()        :404
   └─ make_env(robot_name, task_name)      envs/make_env.py:275
        ├─ 读 models/mjcf/manipulator/robot_airbot_play.xml
        ├─ 读 models/mjcf/task_environments/place_block.xml
        ├─ 拼接（见 7.3）
        └─ 输出 models/mjcf/tmp/airbot_play_place_block.xml
        ↓
③ mujoco.MjModel.from_xml_path(...)  :432   ← 编译，约 260ms
   mujoco.MjData(mj_model)           :433
        ↓
④ create_simple_visualizer()         :410   ← 可选，开 MuJoCo viewer 窗口
        ↓
⑤ UniversalTaskBase(...)             :441
   ├─ RobotConfigLoader(robots/airbot_play.yaml)
   ├─ load_and_resolve_config(tasks/place_block.yaml)   ← 处理 extends
   ├─ replace_variables(...)                            ← 替换 ${param}
   ├─ TaskConfigLoader.from_dict(...)
   ├─ RobotInterface(...)  ← 内含 MinkIKSolver + GripperController
   └─ SceneRandomizer(...)
        ↓
⑥ UniversalRuntimeTaskExecutor(...)  :448
   └─ resolved_states = task_config.get_resolved_states()
        ↓
⑦ while True:  executor.run()        :457
        ↓
⑧ run() 内部 while self.running:     :280
   └─ self.step()                    :213   ← 见 7.5
```

**命名约定链条**（一处不对就崩）：

```
robot 名 "airbot_play" → models/mjcf/manipulator/robot_airbot_play.xml
                       → discoverse/configs/robots/airbot_play.yaml
task 名 "place_block"  → models/mjcf/task_environments/place_block.xml
                       → discoverse/configs/tasks/place_block.yaml
合成产物               → models/mjcf/tmp/airbot_play_place_block.xml
数据输出               → data/airbot_play_place_block/
```

### 7.3 XML 是怎么拼起来的

**关键认知：任务场景 XML 里没有机器人**，只有一个占位标记。

`models/mjcf/task_environments/place_block.xml` 全文（18 行）：

```xml
<mujoco model="place_block">
  <include file="../object/bowl_dependencies.xml"/>
  <compiler angle="radian" meshdir="../../meshes/" texturedir="../../meshes/"/>
  <worldbody>
    <site name="manipulator_locate" pos="0.3 1. 0.71" euler="0 0 3.1416"/>
    <body name="block_green" pos="0 0.85 0.7145">
      <joint type="free" frictionloss="0.00001"/>
      <inertial pos="0 0 0" mass="0.001" diaginertia="1e-7 1e-7 1e-7"/>
      <geom rgba="0.21 0.36 0.21 1" size="0.0145 0.0145 0.0145" type="box" class="obj_collision" group="1"/>
    </body>
    <body name="bowl_pink" pos="0 1.03 0.6988">
      <joint type="free" frictionloss="0.00001"/>
      <include file="../object/bowl_pink.xml"/>
    </body>
  </worldbody>
  <include file="../scene/qz_lab3.xml"/>
</mujoco>
```

四个要点：

**① `<site name="manipulator_locate">` 是机械臂的安装位置占位符。**

它本身什么都不做，但 `make_env.py:227` 会读它，然后 `:233-238` 用它的 `pos`/`euler` **覆盖**机械臂 body 的位姿：

```python
if child.tag == "body" and child.get("name") == f"{arm_name}_pose":
    set_arm_pose = True
    for key in ["pos", "euler", "quat"]:
        if manipulator_locate is not None and manipulator_locate.get(key):
            child.set(key, manipulator_locate.get(key))
```

所以 `robot_airbot_play.xml` 里写的 `pos="0 0 0.78"` **拼接后会被丢弃**，换成任务文件里的 `pos="0.3 1. 0.71" euler="0 0 3.1416"`（3.1416 弧度 = 180°，让手臂转身面对桌子）。

⚠️ `make_env.py:239` 有个断言：

```python
assert set_arm_pose, "未找到机械臂位姿设置节点..."
```

**所以 `<body name="{机器人名}_pose">` 的命名约定是强制的。**

**② `<joint type="free"/>` 标记「可操作物体」。**

物体可以在空中自由平移+旋转 —— 会掉、会滚、能被抓起来。对比场景里的桌子（没有 joint），那是钉死在世界上的。

**一个 free joint 占 7 个 qpos**（3 位置 + 4 四元数）。

**③ 物体可以内联也可以 include。** 简单方块直接写 `<geom type="box">`；碗形状复杂，用 `<include>` 引入 mesh，同时在文件顶部 include 对应的 `_dependencies.xml`（因为 `<asset>` 只能放在根层级）。

**④ 场景 include 放最后。** `make_env.py:199-200` 会特殊处理带 `/scene/` 的 include，把它们挪到末尾，同时丢弃机械臂自带的 skybox，避免两个场景冲突。

#### keyframe 拼接（`make_env.py:252-270`）

这一步很精巧：

```python
env_model = mujoco.MjModel.from_xml_path(pure_task_xml_path)   # 单独加载纯任务 XML
env_data = mujoco.MjData(env_model)
mujoco.mj_forward(env_model, env_data)
env_qpos = env_data.qpos.copy().tolist()                       # 拿到物体的初始 qpos
...
robot_qpos = list(map(float, key_elem.get("qpos").split()))    # 机械臂的 8 个 qpos
keyframe_qpos = robot_qpos + env_qpos                          # 拼接
key_elem.set("qpos", " ".join(map(str, keyframe_qpos)))
```

**为什么要这样？** 因为合并后模型的 qpos 顺序是「机械臂在前，物体在后」（worldbody 里机械臂先添加）。所以 `home` keyframe 也必须按这个顺序拼。

以 `airbot_play` + `place_block` 为例：

```
qpos = [机械臂 8 个] + [block_green 7 个] + [bowl_pink 7 个] = 22 个
```

> **想看拼好的完整 XML 长什么样？** 去 `models/mjcf/tmp/` 目录翻。那是自动生成的产物目录。

也可以单独跑拼接工具：

```bash
python discoverse/envs/make_env.py --robot airbot_play --task place_block
```

### 7.4 状态机与 primitive（原语）

#### `states` 是什么

`states` 是一个**有序列表**，每项是一个「动作步骤」。状态机从索引 0 开始，一个做完自动进下一个。

```yaml
- name: "approach_source_above"     # 人类可读名字（必填，仅用于日志）
  primitive: "move_to_object"       # 原语类型（必填）
  params:                           # 原语参数（依 primitive 而定）
    object_name: "${source_object}"
    offset: [0, 0, "${approach_height}"]
  gripper_state: "open"             # "open" | "close"，可选，默认 "open"
  delay: "${stabilize_time}"        # 完成后额外等待（仿真秒），可选，默认 0
```

⚠️ **校验只查两个字段**（`task_config.py:94-98`）：`name` 和 `primitive`。**`params` 的内容完全不校验** —— 参数名写错不会报错，会静默用默认值。

#### 什么是「原语」（primitive）

**原语 = 一个「动作积木」。**

你不用写「关节 1 转到 0.3 弧度、关节 2 转到 -1.1 弧度…」，只说「移动到咖啡杯上方 10 厘米」，剩下的 IK 求解交给框架。

**好处是跨机器人复用**：同一份 `place_block.yaml` 在 6 轴的 airbot_play 和 7 轴的 panda 上都能跑，因为「移到某物上方」这个描述与机器人无关。

#### ⚠️ 实际只有两个原语被实现

YAML 里出现 4 种名字（实测统计）：

| primitive 名 | 出现次数 | 有实现吗 |
|---|---|---|
| `move_to_object` | 23 | ✅ `universal_task_runtime.py:137` |
| `move_relative` | 20 | ✅ `:167` |
| `grasp_object` | 6 | ❌ **没有分支** |
| `release_object` | 6 | ❌ **没有分支** |

`grep -n "primitive ==" universal_task_runtime.py` 只有两行命中（137 和 167）。

**那 `grasp_object` 怎么还能工作？** 因为函数末尾有一段**无条件执行**的代码（`:189-192`，缩进在 if/elif 链**之外**）：

```python
if gripper_state == "open":
    self.target_control[self.gripper_ctrl_idx] = self.task.robot_interface.gripper_controller.open()
elif gripper_state == "close":
    self.target_control[self.gripper_ctrl_idx] = self.task.robot_interface.gripper_controller.close()
```

所以 `grasp_object` 状态走到这里时：

- 没有 IK 分支匹配 → `target_control[:6]` **保持上一个状态的值**（手臂不动）
- `gripper_state: "close"` 生效 → 夹爪合上

**净效果就是「原地闭合夹爪」—— 恰好就是抓取该有的行为。**

⚠️ 但这是**巧合式正确**：`grasp_type`、`force` 这些参数完全被忽略；写任何未知的 primitive 名（比如 `primitive: "fly_to_moon"`）都不会报错，只会静默变成「原地 + 改夹爪状态」。

#### 两个真实原语的行为

**`move_to_object`**（`:137-165`）—— 移到某物体位置 + 偏移：

```python
object_tmat = get_body_tmat(self.mj_data, object_name)
target_pos = object_tmat[:3, 3] + offset            # 物体位置 + 世界系偏移
target_rmat = self.mj_data.site_xmat[site_id].reshape(3, 3).copy()   # ← 保持当前朝向
solution, converged, _ = ik_solver.solve_ik(target_pos, target_rmat, full_qpos)
if converged:
    self.target_control[:self.n_arm_joints] = solution[:self.n_arm_joints]
else:
    return False        # IK 不收敛 → 整个任务失败
```

⚠️ **`target_rmat` 取的是【当前】末端朝向** —— 即「只改位置，朝向保持不动」。YAML 里的 `keep_orientation: true` 参数**代码根本没读**，朝向总是保持。

⚠️ **`offset` 是世界坐标系偏移**，不是物体局部坐标系。老架构用的是 `+ 0.1 * tmat[:3, 2]`（沿物体局部 Z 轴）—— **物体直立时两者等价，倾斜时不等价。**

**`move_relative`**（`:167-187`）—— 从当前末端位置做相对位移：

```python
current_pos = self.mj_data.site_xpos[site_id].copy()
target_pos = current_pos + offset
```

有个巧妙用法：`offset: [0, 0, 0]` 表示「哪也不去」，配合 `delay` 就成了**纯等待状态**：

```yaml
- name: "wait_before_grasp"
  primitive: "move_relative"
  params:
    offset: [0, 0, 0]          # 位移为零
  gripper_state: "open"
  delay: "${stabilize_time}"   # 唯一作用是等这么久
```

因为框架**没有 `wait` 原语**，就用现有积木凑出「等待」语义。

#### 一个完整的 10 步动作序列

`templates/place_object.yaml` 的 `states`（实际执行的版本）：

| # | 状态名 | primitive | 夹爪 | 干什么 |
|---|---|---|---|---|
| 0 | approach_source_above | move_to_object | open | 移到方块上方 5cm |
| 1 | approach_source_grasp | move_to_object | open | 下降到抓取高度 |
| 2 | wait_before_grasp | move_relative（零位移） | open | **等 0.35 秒让物理稳定** |
| 3 | grasp_source | grasp_object | **close** | 原地合爪 |
| 4 | stabilize_grasp | move_relative（零位移） | close | 等待抓稳 |
| 5 | lift_source | move_relative | close | 抬起 7cm |
| 6 | move_above_target | move_to_object | close | 移到碗上方 |
| 7 | lower_to_target | move_to_object | close | 下降到放置高度 |
| 8 | release_source | release_object | **open** | 原地开爪 |
| 9 | lift_away | move_relative | open | 抬手离开 |

⚠️ **模板里同时有 `task_states`（8 步）和 `states`（10 步）两份序列，内容不同。** `task_config.py:150` 的取值逻辑：

```python
states = self.config.get('states', self.config.get('task_states', []))
```

**`states` 优先** → 实际跑的是 10 步版本。注释说 `states` 是「向后兼容」，但它才是真正执行的那份 —— 命名反直觉。

### 7.5 `step()` 每一步做什么

`universal_task_runtime.py:213-262` 是整个运行时的心脏：

```python
def step(self, decimation=5):
    try:
        if self.stm.trigger():                              # 刚进入新状态？
            if self.stm.state_idx < self.total_states:
                state_config = self.resolved_states[self.stm.state_idx]
                self.current_delay = state_config.get("delay", 0.0)
                if not self.set_target_from_primitive(state_config):   # 算目标关节角
                    return False                                       # IK 失败
                if self.current_delay > 0:
                    self.delay_start_sim_time = self.mj_data.time
            else:
                self.success = self.check_task_success()     # 全部状态跑完 → 判定成功
                self.running = False
                return True
        elif self.mj_data.time > self.max_time:              # 超时（20 仿真秒）
            self.running = False
            return False
        else:
            self.stm.update()

        if self.check_action_done():                         # 到位了？
            self.current_delay = 0.0
            self.stm.next()                                  # 进下一个状态

        # 平滑插值，避免关节瞬移
        for i in range(self.n_arm_joints):
            self.action[i] = step_func(
                self.action[i], self.target_control[i],
                self.move_speed * float(decimation) * self.joint_move_ratio[i] * self.mj_model.opt.timestep
            )
        self.action[self.gripper_ctrl_idx] = self.target_control[self.gripper_ctrl_idx]  # 夹爪不插值

        self.mj_data.ctrl[:self.mujoco_ctrl_dim] = self.action[:self.mujoco_ctrl_dim]

        for _ in range(decimation):
            mujoco.mj_step(self.mj_model, self.mj_data)

        return True
    except Exception as e:
        print(f"❌ 步进失败: {e}")
        self.running = False
        return False
```

#### `joint_move_ratio` —— 让所有关节同时到位

`:195-196`：

```python
dif = np.abs(current_ctrl - self.target_control)
self.joint_move_ratio = dif / (np.max(dif) + 1e-6)
```

走得远的关节速度快、走得近的慢，比例正好抵消距离差 → **同步抵达**。否则短距离关节先到位就停下，动作会很别扭。

#### `check_action_done()` —— 怎么判断「到位了」

`:91-105`：

```python
position_error = np.linalg.norm(current_qpos[:self.n_arm_joints] - self.target_control[:self.n_arm_joints])
position_done = position_error < 0.02
```

⚠️ 这个 `0.02` 是**关节角度的 L2 范数**，单位是弧度（代码注释写「2cm容差」不准确）。

⚠️ **它不检查速度。** 老架构的 `checkActionDone` 同时要求 `|qvel|.sum() < 0.1`（速度也要降下来），新架构没有 → **可能在手臂还在摆动时就判定到位并进入下一状态**。

#### 硬编码的常量

| 常量 | 值 | 位置 | 能配置吗 |
|---|---|---|---|
| `move_speed` | 1.5 | `:73` | ❌ |
| `max_time` | 20.0 仿真秒 | `:74` | ❌ |
| `viewer_fps` | 60 | `:50` | ❌ |
| `decimation` | 5 | `:213` 默认参数 | ❌ |
| 到位阈值 | 0.02 | `:96` | ❌ |

**想调只能改源码。**

### 7.6 数据在哪一步被录下来

`run()` 循环里（`:311-316`）：

```python
if len(obs_lst) < self.mj_data.time * self.record_frq:
    obs = self.get_observation()
    imgs = obs.pop('img')
    for cam_id, img in imgs.items():
        self.camera_encoders[cam_id].encode(img, obs["time"])
    obs_lst.append(obs)
```

**按 `record_frq`（来自 `observation.fps`）抽帧**，不是每个物理步都录。

观测格式（`:107-118`）：

```python
obs = {
    "time": self.mj_data.time,
    "jq": self.mj_data.sensordata[self.joint_pos_sensor_idx].tolist(),   # 关节位置
    "action": self.action[:self.mujoco_ctrl_dim].tolist(),               # 下发指令
    "img": {}                                                            # 各相机图像
}
```

⚠️ **`jq` 从 `sensordata` 读，不是从 `qpos`** —— 保持与真机一致（见 3.4 节 sensor 部分）。

---

## 八、逆运动学（IK）

### 8.1 什么是逆运动学

两个方向的问题：

| | 名称 | 问题 | 难度 |
|---|---|---|---|
| 正向 | **正运动学**（FK） | 已知各关节角度 → 末端在哪 | **简单**，矩阵连乘即可 |
| 反向 | **逆运动学**（IK） | 已知想让末端到某位姿 → 各关节该转多少 | **难**，通常无闭式解 |

**为什么 IK 难**：

- 可能**没有解**（目标点在工作空间外，手伸不到）
- 可能有**无穷多解**（7 轴机器人的冗余自由度）
- 可能有**多个离散解**（肘部朝上还是朝下）
- 靠近**奇异点**时数值不稳定（某些姿态下关节速度会趋于无穷）

### 8.2 两条路线的两种解法

| | Route A（老） | Route B（新） |
|---|---|---|
| 方法 | **解析法**（闭式解） | **迭代 QP**（mink 库） |
| 位置 | `robots/airbot_play/airbot_play_ik.py` | `universal_manipulation/mink_solver.py` |
| 速度 | 瞬间（直接算公式） | 需要迭代，最多 50 次 |
| 会失败吗 | 不会（要么有解要么无解） | **会不收敛** |
| 通用性 | ❌ 每个机器人写一套 | ✅ 任何机器人通用 |
| 多解处理 | 用参考角度 `ref_q` 挑分支 | 用「姿态保持」代价隐式挑 |

**解析法**：针对特定机械臂的几何结构，用三角函数推导出公式。快而准，但换个机器人就得重新推。

**迭代法**：把 IK 变成一个优化问题 —— 「找一组关节角，使末端位姿尽量接近目标」，然后梯度下降式地一步步逼近。通用，但慢且可能失败。

### 8.3 mink 求解器怎么工作

`mink_solver.py` 用 `mink` 库（基于二次规划）。核心是**两个「任务」加权**：

```python
# mink_solver.py:55 附近
FrameTask(                              # 任务 1：末端要到目标位姿
    frame_name=end_effector_site,
    position_cost=100.0,                # 位置权重
    orientation_cost=10.0,              # 朝向权重
)
PostureTask(                            # 任务 2：关节尽量别乱动
    cost=0.01                           # 权重很小
)
```

**权重比例决定优先级**：

```
position 100  >>  orientation 10  >>  posture 0.01
```

意思是「**位置最重要，朝向次之，在满足前两者的前提下尽量少动关节**」。

`PostureTask` 的作用是**解决多解问题**：7 轴机器人有无穷多解，加一个「尽量接近当前姿态」的软约束，就能挑出一个「动得最少」的解 —— 这也让动作看起来更自然。

#### 迭代过程

```python
for iteration in range(max_iterations):     # 最多 50 次
    velocity = mink.solve_ik(configuration, tasks, dt, solver_type, damping)
    configuration.integrate_inplace(velocity, dt)      # 沿速度积分一小步
    pos_err, ori_err = compute_error()
    if pos_err < position_tolerance and ori_err < orientation_tolerance:
        converged = True
        break
```

每次迭代解一个小的二次规划问题，得到「关节该以什么速度动」，然后积分一小步。反复逼近直到误差够小。

⚠️ **`dt` 有个坑**：配置里写 `dt: 0.002`，代码 `:50` 读进 `self.dt`，但 `:126` 又硬编码了 `dt = 1e-3`，实际用的是后者。**YAML 里的 `dt` 是死配置。** 详见缺陷文档。

#### 为什么需要 keyframe

`mink_solver.py:72-77` 要求模型必须有 keyframe：

```python
if mj_model.nkey > 0:
    # 用 key(0).qpos 初始化 configuration 和 posture 目标
else:
    raise ValueError("MuJoCo model does not contain keyframes")
```

因为 `PostureTask` 需要一个「参考姿态」，而迭代也需要一个起点。**这就是 7.3 节 `make_env` 要费劲拼接 keyframe 的原因。**

#### 返回值

```python
return solution, converged and is_valid, solve_info
```

调用方**必须检查第二个返回值**：

```python
solution, converged, _ = ik_solver.solve_ik(...)
if converged:
    self.target_control[:n] = solution[:n]
else:
    return False       # 放弃这个状态，整个任务失败
```

⚠️ `_validate_solution`（`:181`）只检查 NaN/Inf，**不检查关节限位** —— 尽管方法名和 docstring 都说是「验证解的有效性」。

---

## 九、域随机化

### 9.1 为什么要故意打乱环境

如果每次训练都是「方块永远在 (0.3, 0.85)、光照永远一样、桌子永远这么高」，AI 学到的可能是：

```
「把手伸到 (0.3, 0.85) 就完事了」    ← 死记硬背，不是真的会抓
```

换个位置就失效，搬到真机上更是完全不行。

**域随机化**（Domain Randomization）就是每次任务开始前随机改变环境，强迫 AI 学到**真正的规律**（「看到绿方块 → 伸手过去」）而不是记住坐标。

这是缩小 sim-to-real gap（见 1.4 节）的核心技术之一。

### 9.2 五类随机化

配置在任务 YAML 的 `randomization:` 节，实现在 `randomization.py`（611 行，模块里最大的文件）。

| 类别 | 随机什么 | 为什么 |
|---|---|---|
| `objects` | 物体位置 | 最重要 —— 逼 AI 真的用视觉定位 |
| `cameras` | 相机位姿 | 真机相机安装有误差 |
| `lighting` | 光照颜色/亮度/方向/开关 | 真实环境光照千变万化 |
| `table_height` | 桌面高度 | 真机桌子高度不一定 |
| `textures` | 桌布/墙面贴图 | 背景不该影响判断 |

```yaml
randomization:
  objects:
    - name: "block_green"
      x_range: [0.2, 0.4]        # 在 armbase 坐标系下的绝对范围
      y_range: [-0.2, 0.2]
      collision_radius: 0.05     # 避让半径
  cameras:
    activate: true
    eye_side:
      position_offset: [0.05, 0.05, 0.05]      # ±5cm
      orientation_offset: [0.05, 0.05, 0.05]   # ±0.05 弧度
  lighting:
    activate: true
    random_color: true
    random_active: true
    active_probability: 0.8       # 每个灯 80% 概率亮着
    intensity_range: {min: 0.1, max: 0.9}
  table_height:
    activate: true
    table_name: "table"
    height_range: [-0.05, 0.1]
    affected_objects: ["block_green", "bowl_pink"]    # ⚠️ 必须列全
  settings:
    max_attempts: 50
    seed: null
```

⚠️ **`affected_objects` 必须列全所有桌上的物体。** 桌子升高时物体要一起抬，否则会**穿模掉进桌子里**。这是个手工维护的列表，加新物体容易忘。

⚠️ **只随机 `eye_side`（第三人称），不随机 `eye_arm`（腕部）** —— 因为真机上腕部相机是刚性安装在手臂上的，位置不会变。

### 9.3 物体位置的碰撞重试算法

随机放物体有个问题：**可能重叠**（方块生成在碗里）。所以要检测碰撞并重试。

`randomization.py:146` 的 `_randomize_objects_with_collision`：

```
外层循环 max_attempts 次（比如 50）：
    placed_objects = []
    对每个物体：
        内层循环 10 次：
            在 x_range × y_range 内均匀采样一个位置
            检查与所有 placed_objects 的 2D 距离
            如果都够远 → 接受，加入 placed_objects，break
        如果 10 次都失败 → 整个外层重来
    如果所有物体都放好 → 成功返回
```

碰撞检测很简单（`:243`）—— 只算 XY 平面距离：

```python
if np.hypot(dx, dy) < radius + other_radius:
    return True     # 碰撞了
```

#### 为什么在 armbase 坐标系采样

`randomization.py:160` 先取机械臂底座的变换矩阵：

```python
armbase_tmat = get_site_tmat(mj_data, "armbase")
...
world_pos = armbase_tmat @ local_pos          # :236
```

**因为要保证物体落在机械臂够得到的范围内。** 如果用世界坐标，换个机械臂安装位置就全乱了。用底座坐标系，`x_range: [0.2, 0.4]` 的含义永远是「机械臂前方 20-40 厘米」。

Z 坐标不随机（`:238-239` 保持原值）—— 物体得放在桌面上，不能悬空。

### 9.4 均匀随机旋转：Shoemake 方法

`randomization.py:342` 的 `_generate_random_quaternion`：

```python
u1, u2, u3 = np.random.random(3)
# Shoemake's method
```

**为什么不能直接随机三个欧拉角？** 因为那样得到的旋转**不是均匀分布**的 —— 会在某些朝向聚集（类似在地球表面按经纬度均匀采样，会在两极密集）。

Shoemake 方法用 3 个 [0,1) 均匀随机数构造四元数，保证在旋转空间（SO(3)）上均匀。

⚠️ 实测这个函数**从未被调用** —— 是死代码。

### 9.5 ⚠️ 可复现性问题

这一节讲原理，具体缺陷见缺陷文档。

**「可复现」的含义**：同一个随机种子 → 同样的随机数序列 → 完全一样的仿真结果。

**为什么重要**：

| 场景 | 没有可复现性的后果 |
|---|---|
| 复现 bug | 「刚才失败了」但再跑一次就好了，无法调试 |
| 数据集划分 | 无法保证训练集/测试集不重叠 |
| 回归测试 | 测试结果随机波动，无法判断改动是好是坏 |
| 论文实验 | 别人无法复现你的结果 |

**怎么做到**：

```python
# ❌ 用全局随机数生成器 —— 不可控
np.random.uniform(0, 1)

# ✅ 用独立的生成器实例 —— 可控
rng = np.random.default_rng(seed=42)
rng.uniform(0, 1)
```

实测这个项目的现状：

```
randomization.py 里有 25 处 np.random.*   ← 全是全局生成器
该文件里 seed 关键词零命中
6 个 YAML 声明了 settings.seed: null
但没有任何 .py 读取这个字段
utils/__init__.py:86 还用了 stdlib random.choice（第二个独立的全局生成器）
```

**结论：仿真不可复现，且没有任何开关能让它可复现。** 这是 Day 3-4 要攻坚的核心问题。

---

## 十、数据采集与录制

### 10.1 采集什么

具身智能的训练数据是 **obs-action 对**（观测-动作配对）：

```
第 0 帧：  相机看到的图像  →  机械臂该下发的指令
第 1 帧：  相机看到的图像  →  机械臂该下发的指令
...
```

AI 学的就是这个映射：**看到这样的画面，就该这样动。**

### 10.2 落盘格式

一次成功的任务产出：

```
data/airbot_play_place_block/
├── cam_0.mp4          ← eye_side 相机录的视频
├── cam_1.mp4          ← eye_arm 相机录的视频
└── obs_action.json    ← 关节数据 + 指令
```

`obs_action.json` 的结构（`recorder.py:76` 的 `recoder_single_arm`）：

```json
[
  {"time": 0.05, "obs": {"jq": [0.0, -1.0, 1.2, ...]}, "act": [0.0, -1.0, ...]},
  {"time": 0.10, "obs": {"jq": [...]}, "act": [...]},
  ...
]
```

**图像存视频而不是一堆 PNG**，因为：

| | 一堆 PNG | MP4 视频 |
|---|---|---|
| 体积 | 大（每帧独立压缩） | **小 10-50 倍**（帧间压缩） |
| 读取速度 | 慢（几百个文件） | 快（单文件顺序读） |

### 10.3 视频编码：`PyavImageEncoder`

`recorder.py:9` 用 PyAV 库（FFmpeg 的 Python 绑定）编码 H.264：

```python
class PyavImageEncoder:
    def __init__(self, width, height, save_path, id, fps=24):
        os.makedirs(save_path, exist_ok=True)
        # 删掉已存在的同名文件
        self.container = av.open(f"{save_path}/cam_{id}.mp4", mode='w')
        self.stream = self.container.add_stream('h264', ...)
        self.stream.pix_fmt = 'yuv420p'
        self.stream.options = {'preset': 'fast'}
        self.stream.time_base = Fraction(1, 1000000)     # 微秒精度
```

`time_base = 1/1000000` 是**微秒级时间基准**，为了支持 VFR（可变帧率）—— 仿真的帧间隔不一定完全均匀。

#### 时间戳与单调性断言

`recorder.py:48` 的 `encode`：

```python
def encode(self, image, timestamp):
    cur_time = timestamp - self.start_time
    assert cur_time >= self.last_time         # ← 时间戳必须单调递增
    frame.pts = int(cur_time * 1e6)           # 转微秒
    ...
```

**`pts`**（Presentation Time Stamp，显示时间戳）告诉播放器「这一帧该在第几微秒显示」。

⚠️ **那个 `assert` 很重要**：如果时间戳倒退，编码出的视频会时序错乱。断言让问题在录制时就暴露，而不是等到播放时发现视频是乱的。

> 这是「快速失败」原则的好例子：**宁可在录制阶段崩掉，也不要产出一个坏数据集。**

### 10.4 多相机同步

每个相机一个独立的 encoder：

```python
self.camera_encoders = {}
for cam_name in self.camera_cfgs:
    self.camera_encoders[cam_id] = PyavImageEncoder(width, height, save_dir, cam_id, fps)
```

录制时**用同一个 `obs["time"]`** 喂给所有 encoder：

```python
for cam_id, img in imgs.items():
    self.camera_encoders[cam_id].encode(img, obs["time"])
```

**所以多相机是严格同步的** —— 因为它们共享同一个仿真时钟。这比真机容易得多（真机要处理各相机的曝光延迟、传输延迟）。

### 10.5 ⚠️ 失败时删除数据的设计

`universal_task_runtime.py:340-346`：

```python
if not self.success:
    shutil.rmtree(self.save_dir, ignore_errors=True)
    print(f"   ❌ 任务未成功，已删除保存目录: {self.save_dir}")
else:
    recoder_single_arm(self.save_dir, obs_lst)
```

**设计意图是好的**：失败的任务（比如没抓起来）不该进训练集，否则 AI 会学到错误示范。

⚠️ **但实现有问题**：`save_dir` 不带序号（`:385`）：

```python
self.save_dir = os.path.join(DISCOVERSE_ROOT_DIR, "data", f"{robot_name}_{task_name}")
```

无限循环模式下每轮都用**同一个目录**，所以：

```
第 1 轮成功 → 存了数据
第 2 轮失败 → rmtree 把第 1 轮的数据一起删了
```

对比老架构 `place_block.py:117` 用 `"{:03d}".format(data_idx)` 分目录 —— **新架构在这点上反而退化了。** 详见缺陷文档。

---

## 十一、夹爪控制

### 11.1 四种夹爪类型的物理含义

（3.3 节讲过 qpos 差异，这里讲控制逻辑）

| `type` | 物理机构 | MJCF 实现 |
|---|---|---|
| `two_finger_tendon` | 两指靠**绳/齿轮**联动 | `<tendon>` + `<equality>` |
| `two_finger_equality` | 两指靠**约束**同步 | `<equality>` |
| `two_finger_single` | 只有一指能动 | 单个 `slide` 关节 |
| `multi_finger_equality` | 三指或更多 | 多个 `<equality>` |

**但从控制角度看，四者都一样**：给一个标量（开口大小），写进 `data.ctrl` 的某一位。

### 11.2 类的结构

`gripper_controller.py`（71 行）：

```python
class GripperController(ABC):              # :17  抽象基类
    def __init__(self, gripper_config, mj_model, mj_data):
        self.ctrl_index = gripper_config["ctrl_index"]
        self.ctrl_range = gripper_config["ctrl_range"]
        ...
    @abstractmethod
    def set_position(self, position) -> bool: ...

    def open(self) -> float:                # :49
        return self.config["default_position"]     # ← 返回数值，不直接驱动！

    def close(self) -> float:               # :53
        return self.config["close_position"]

class TwoFingerGripper(GripperController):  # :57
    def set_position(self, position) -> bool:
        normalized_pos = np.clip(position, self.ctrl_range[0], self.ctrl_range[1])
        self.mj_data.ctrl[self.ctrl_index] = normalized_pos
        return True

def create_gripper_controller(gripper_config, mj_model, mj_data):   # :70  工厂函数
    return TwoFingerGripper(gripper_config, mj_model, mj_data)
```

### 11.3 ⚠️ `open()` / `close()` 返回数值而不是驱动

这个设计容易误解：

```python
gripper_controller.open()      # ❌ 不会让夹爪张开！
```

它只是**返回**「张开对应的控制值」（比如 0.04）。调用方拿到这个数自己写进控制数组：

```python
# universal_task_runtime.py:189-192
if gripper_state == "open":
    self.target_control[self.gripper_ctrl_idx] = gripper_controller.open()
```

**为什么这样设计**：因为运行时要做插值和统一的 `ctrl` 写入（见 7.5 节），不希望夹爪控制器绕过这个流程直接改 `mj_data`。

⚠️ 所以 `set_position()` 方法（会直接写 `mj_data.ctrl`）**实际从未被运行时调用**。

### 11.4 ⚠️ 工厂函数没有真正分派

`gripper_controller.py:70-71` 的工厂函数**无条件返回 `TwoFingerGripper`**，完全不看 `gripper_config["type"]`。

而文件头的 docstring 声称：

```
支持三种夹爪实现方式：
1. tendon控制 (如airbot_play)
2. equality约束 (如panda)
3. 单关节控制 (如ur5e)
```

**但全文件只定义了一个类。** 4 种 `type` 值全部得到同一个控制器。

**为什么还能跑**：因为所有类型的控制方式恰好都归约为「写一个标量到一个 ctrl 位」。**这是巧合式正确** —— 一旦遇到需要两个 ctrl 位的夹爪（比如独立控制两指），就会静默出错。

详见缺陷文档。

---

## 十二、测试开发与 pytest 入门

### 12.1 测试开发是什么

**一句话：测试开发 ≠ 点点点。是「写代码去验证别人的代码」。**

| | 手工测试 | **测试开发** |
|---|---|---|
| 做什么 | 按文档点界面，记录 bug | **写程序自动验证** |
| 产出 | bug 列表 | **可复用的测试代码 + CI 流水线** |
| 每个版本 | 重新点一遍 | **代码自动跑** |
| 要写代码吗 | 不用 | **要，这是主要工作** |

### 12.2 测试的本质：断言

**所有测试都是一句话**：「我认为 X 应该是 Y，如果不是就报错。」

```python
assert 实际值 == 期望值, "失败时显示这句话"
```

`assert` 后面的表达式为 `False` 时，测试失败。就这么简单。

**难的不是写 `assert`，是知道该断言什么。**

| 断言 | 评价 |
|---|---|
| `assert loader is not None` | ❌ 几乎永远为真，等于没测 |
| `assert len(loader.arm_joints) > 0` | ❌ 看着合理，但**语义搞错了**（想测数量，实际测了列表非空） |
| `assert model.nq == loader.qpos_dim` | ✅ **好断言**：跨两个独立信源对账，能抓真 bug |

**第三条就是本项目抓到「4/9 机器人 qpos_dim 与 MJCF 不符」的那条。**

### 12.3 三个测试层次

| 层次 | 测什么 | 快慢 | 本项目的例子 |
|---|---|---|---|
| **单元测试** | 一个函数/一个类 | 毫秒 | 读 YAML 检查字段自洽 |
| **集成测试** | 两个组件配合 | 百毫秒 | 配置 vs MJCF 编译结果对账 |
| **端到端** | 整个流程 | 秒~分钟 | 跑完整任务看有没抓到方块 |

⚠️ **有些 bug 只有集成测试能发现。** `qpos_dim` 那个缺陷，单看 YAML 它自己是自洽的，只有和 MJCF 对账才暴露。

### 12.4 pytest 的五样语法

pytest 是 Python 最主流的测试框架。全部语法就这五样。

#### ① 函数名以 `test_` 开头

```python
def test_something():      # ✅ pytest 自动找到
    assert 1 + 1 == 2

def check_something():     # ❌ 被忽略（名字不对）
    assert 1 + 1 == 2
```

**pytest 靠扫描文件名和函数名找测试**，不用你注册。规则可配置（`pyproject.toml`）：

```toml
python_files = "test_*.py"        # 哪些文件算测试文件
python_functions = "test_*"       # 哪些函数算测试
```

#### ② `assert` —— 自动展开中间值

pytest 的 `assert` 比原生 Python 强：失败时**自动打印两边的实际值**。

```python
assert model.nu == 19
```

失败时显示：

```
assert 8 == 19
```

它自动帮你算出了两边的值。这个功能叫 assertion rewriting，是 pytest 的招牌。

#### ③ `@pytest.mark.xxx` —— 贴标签

```python
@pytest.mark.unit          # 贴个 "unit" 标签
def test_foo(): ...
```

用途是**筛选运行**：

```bash
pytest -m unit             # 只跑贴了 unit 的（毫秒级，每次提交都跑）
pytest -m integration      # 只跑要加载 MJCF 的（较慢）
pytest -m "not slow"       # 跑除了 slow 之外的
```

标签需要先在配置里声明：

```toml
markers = [
    "unit: 纯函数/配置层单测，无 MuJoCo 依赖，秒级",
    "integration: 需要加载 MJCF 或跑仿真步进",
]
```

#### ④ `@pytest.mark.parametrize` —— 一个函数变多个测试

```python
@pytest.mark.parametrize("robot_name", ["panda", "ur5e", "piper"])
def test_foo(robot_name):
    assert check(robot_name)
```

**pytest 会跑三次**，每次 `robot_name` 不同：

```
test_foo[panda] PASSED
test_foo[ur5e]  PASSED
test_foo[piper] PASSED
```

方括号里就是参数值，失败时能精确定位是哪个机器人。

**语法拆解**：

```python
@pytest.mark.parametrize("robot_name", ROBOTS)
#                         ↑参数名      ↑值的列表
def test_foo(robot_name):
#            ↑必须和上面的参数名一致
```

##### ⚠️ 为什么不用 for 循环

```python
# ❌ 循环写法
def test_foo():
    for robot in ROBOTS:
        assert check(robot)      # 第一个失败就停，后面 8 个不知道结果

# ✅ 参数化
@pytest.mark.parametrize("robot_name", ROBOTS)
def test_foo(robot_name):
    assert check(robot_name)     # 9 个独立用例，各自成败
```

**这个区别很关键。** 参数化能让你一次看到「9 个里 5 个通过 4 个失败」这样的**分布** —— 而分布正是判断「代码错」还是「我的断言错」的依据（见 12.8 节）。用循环只会看到「第 3 个失败」。

#### ⑤ Fixture —— 测试的准备工作

**定义**：

```python
@pytest.fixture
def my_data():
    return {"a": 1}
```

**使用** —— 把 fixture 名字写成函数参数：

```python
def test_foo(my_data):        # 参数名 = fixture 名
    assert my_data["a"] == 1
```

**pytest 看到参数名，自动去找同名 fixture，调用它，把返回值传进来。** 这叫**依赖注入**。

##### `conftest.py` —— 共享 fixture 的特殊文件

放在 `tests/conftest.py` 里的 fixture，**同目录和所有子目录的测试都能直接用，不需要 import**。

```python
# tests/conftest.py
@pytest.fixture(scope="session")
def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent
```

```python
# tests/unit/test_foo.py
def test_bar(repo_root):      # 直接用，不用 import
    assert (repo_root / "discoverse").is_dir()
```

### 12.5 Fixture 作用域：一个二维决策

`scope` 参数决定 fixture 活多久：

```python
@pytest.fixture(scope="function")   # 默认：每个测试重新创建
@pytest.fixture(scope="session")    # 整场只创建一次，所有测试共用
```

**怎么选？看两个维度**：

```
                    对象可变吗？
                    不可变          可变
   构造  贵    │  session ✅   │  两难，需深拷贝  │
   成本  便宜  │  随便         │  function ✅     │
```

MuJoCo 的两个对象正好落在对角线上：

| 对象 | 构造成本 | 可变吗 | 该选 |
|---|---|---|---|
| `MjModel` | **贵**（编译 XML，约 260ms） | 不可变（只读编译产物） | **session** |
| `MjData` | 便宜（只分配数组） | **可变**（qpos/qvel/ctrl/time） | **function** |

#### ⚠️ 代价不对称 —— 这是决策的关键

| 选错方向 | 后果 | 好发现吗 |
|---|---|---|
| 该 session 选了 function | 慢 | ✅ 跑一次就知道 |
| **该 function 选了 session** | **测试间状态污染** | ❌ **极难发现** |

状态污染的典型症状：

- 单独跑 `test_b` → 绿
- 跑整个文件 → `test_b` 红
- 换个执行顺序 → 又绿了
- CI 上偶发失败，本地永远复现不了

**这是最难查的一类不稳定测试。** 所以规则是：**默认 function，只在证明「既贵又不可变」后才放宽到 session。**

#### factory-as-fixture 模式

**问题**：不同测试要加载不同的 XML，但一个 fixture 只能返回一个值。

❌ 笨办法：

```python
@pytest.fixture(scope="session")
def airbot_model():
    return mujoco.MjModel.from_xml_path("...robot_airbot_play.xml")

@pytest.fixture(scope="session")
def panda_model():        # 9 个机器人要写 9 个 fixture
    return mujoco.MjModel.from_xml_path("...robot_panda.xml")
```

✅ 好办法 —— **fixture 返回一个函数**：

```python
@pytest.fixture(scope="session")
def mj_model_factory():
    cache = {}                                # ← 闭包变量，随 session 存活

    def _make(xml_path):
        key = str(xml_path)
        if key not in cache:
            cache[key] = mujoco.MjModel.from_xml_path(key)
        return cache[key]

    return _make                              # ← 返回函数本身（不加括号！）
```

用法：

```python
def test_foo(mj_model_factory):
    model = mj_model_factory("robot_panda.xml")     # 这里才真正调用
```

**三个好处**：

1. 一个 fixture 服务任意数量的 XML
2. `cache` 随 session 作用域存活 → 同一个 XML 只编译一次
3. 测试里显式写出加载哪个 XML，可读性好

**验证缓存真的生效**：

```python
m1 = mj_model_factory(xml)
m2 = mj_model_factory(xml)
assert m1 is m2       # 用 is 不用 ==，比的是「是否同一个对象」
```

#### ⚠️ Fixture 是懒加载的

**没有测试请求它，它永不执行。** 所以 `conftest.py` 里写错的 fixture 可以潜伏很久，直到某个测试第一次用到才暴露。

**对策**：专门写一个 `test_conftest_fixtures.py`，让每个 fixture 至少被求值一次。

### 12.6 三个常用工具

#### `pytest.raises` —— 断言「应该报错」

```python
with pytest.raises(FileNotFoundError):
    RobotConfigLoader("不存在的文件.yaml")
```

读作：「我期望这段代码抛 `FileNotFoundError`。如果它没抛、或抛了别的异常，测试失败。」

**为什么需要**：有时候正确行为就是报错。打开不存在的文件如果**默默返回 None**，那才是 bug。

```python
with pytest.raises((ValueError, KeyError)):    # 元组 = 这几种任意一种都接受
```

#### ⚠️ `xfail` vs `skip` —— 不要混用

| | 含义 | 什么时候用 |
|---|---|---|
| **xfail** | 「这个断言**应该**成立，但因**已知缺陷**不成立」 | 记录缺陷 |
| **skip** | 「这个断言的**前提**不满足，无法判断」 | 环境缺失、依赖不可用、数据不存在 |

本项目的实际例子（同一个 `place_block`，两种待遇）：

```
XFAIL   test_camera_configs_nonempty[place_block]        应该有相机但没有 → 是缺陷
SKIPPED test_camera_config_fields_wellformed[place_block] 一个相机都没有，无从检查字段
```

⚠️ **用错的后果**：如果第一条也用 skip，缺陷就被伪装成了「环境问题」。测试报告里一片 skipped，看起来无害，实际藏着真 bug。

> **skip 掩盖缺陷，xfail 记录缺陷。**

#### `strict=True` —— 缺陷修好了要通知你

```python
@pytest.mark.xfail(strict=True, reason="缺陷 I：_validate_config 未把 observation 列为必填")
def test_should_require_observation():
    ...
```

`strict=True` 的意思：**「如果这个测试意外通过了，把它当失败报出来。」**

**为什么要这样**：某天有人修了这个缺陷 → 测试通过 → 报 `XPASS` 失败 → **强制有人回来删掉这个 xfail 标记**。

不加 `strict` 的话，`XPASS` 只是个提示，很容易被忽略，然后标记永远留着，**假装缺陷还存在**。

> **`strict=True` 让「缺陷已修复」这件事也不会静默发生。**

#### `tmp_path` —— pytest 送的临时目录

```python
def test_bad_config(tmp_path):
    bad = tmp_path / "broken.yaml"          # tmp_path 是 pathlib.Path
    bad.write_text("robot_name: broken\n")
    with pytest.raises(ValueError):
        TaskConfigLoader(str(bad))
```

`tmp_path` 是 pytest **内置** fixture，不用自己定义。每个测试拿到一个**独立的空目录**，测试结束自动清理。

**写「坏配置」测试时必用** —— 不要在仓库里建临时文件。

### 12.7 覆盖率：一个下限指标

**覆盖率 = 你的测试执行了百分之几的代码。**

```bash
pytest --cov=discoverse.universal_manipulation --cov-report=term-missing
```

输出：

```
Name                       Stmts   Miss  Cover   Missing
robot_config.py               77     11    86%   58, 78, 85, 92, 98-102
randomization.py             300    274     9%   28-62, 66, 69, ...
```

| 列 | 含义 |
|---|---|
| `Stmts` | 可执行语句总数（不含空行、注释） |
| `Miss` | 一次都没被执行的语句数 |
| `Cover` | 覆盖率 |
| **`Missing`** | **没执行到的具体行号** ← 最有用的一列 |

#### ⚠️ 覆盖率高 ≠ 测得好

```python
def divide(a, b):
    return a / b

def test_divide():
    assert divide(6, 2) == 3      # 覆盖率 100%，但 b=0 完全没测
```

反过来说：`record_fps` 这个属性**只有 1 行代码**，但本项目为它写了 **4 个测试**（正常值 / 键缺失 / 空字典 / null 崩溃）。覆盖率只算 1 行，但实际验证了 4 条执行路径。

> **覆盖率是「下限指标」**：低了一定有问题（大片代码没测）；高了不保证质量。
> **看报告主要看 `Missing` 那列**找完全没碰过的区域，不要盯总百分比。

#### ⚠️ 覆盖率作用域别写太宽

```bash
pytest --cov=discoverse                    # ❌ policies/ 下 237 个文件会把分母稀释到 2-3%
pytest --cov=discoverse.universal_manipulation   # ✅ 限定到正在测的模块
```

### 12.8 ⚠️ 最重要的一件事：测试红了，是代码错还是测试错

**新手的两种失败模式**：

| 模式 | 后果 |
|---|---|
| 总怀疑代码 | 提一堆假缺陷，浪费开发时间，**信誉受损** |
| 总怀疑自己 | 遇红就改测试迁就，**把真 bug 洗白**（更危险） |

**正确的判断顺序**：

**① 找独立的第二信源。**

配置说 `ctrl_dim=7`，那 MJCF 编译出的 `nu` 是几？**两者不一致时 MJCF 是真相**（它是物理引擎真正加载的东西），配置只是描述。

**② 看分布。**

```
1/9 不符  → 大概率那 1 个配置错了
7/9 不符  → 几乎肯定是我的断言公式错了
```

⚠️ **这就是样本量的价值。** 只有 2 个样本时，1 对 1 错**无法判断谁错**。这也是本项目 Day 2 先测 9 种机械臂而不是先测 MMK2 的核心理由。

**③ 看失败位置是否集中。**

本项目实际发生过：5 个测试同时全红，**全倒在同一处**（构造配置阶段），报的是 `ValueError: Missing required field: description`。

判断依据：

| 线索 | 指向 |
|---|---|
| 失败全在同一处 | 系统性问题，不是分散的 bug |
| 报的是「缺必填字段」 | **这是校验功能正在正常工作** |
| 真实的 5 个 YAML 都有 `description` | **是我的测试数据不真实** |

**结论：改测试，不改代码。**

> 💡 **面试可以这么讲**：
> 「测试红了我先判断是代码错还是测试错。方法是找独立第二信源、看失败分布、看失败位置是否集中。**分不清的时候，测试就失去了价值 —— 它既不能给我信心，也不能给我信号。**」

### 12.9 环境配置：一个真实的坑

本项目实测遇到的问题：装了 ROS 的机器上，pytest **启动阶段就崩**：

```
ModuleNotFoundError: No module named 'lark'
```

**根因链**：

```
~/.bashrc 里 source /opt/ros/humble/setup.bash
  → export PYTHONPATH=/opt/ros/humble/lib/python3.10/site-packages
  → PYTHONPATH 优先级高于 conda 环境隔离，强行注入 sys.path
  → pytest 启动时扫描并加载 sys.path 上【所有】已注册插件
  → 发现 ROS 的 launch_testing（它注册成了 pytest 插件）
  → import 它 → 需要 lark → conda 环境没装
  → 崩
```

**Python 的环境隔离有三层，优先级从高到低**：

| 层 | 机制 | 谁能覆盖它 |
|---|---|---|
| 1 | `PYTHONPATH` 环境变量 | **只有 unset** |
| 2 | conda / venv 的 `site-packages` | 被第 1 层压制 |
| 3 | 系统 Python 的 `site-packages` | 被前两层压制 |

⚠️ **conda 隔离的是第 2 层，挡不住第 1 层。**

**修复**（三种方案对比）：

| 方案 | 评价 |
|---|---|
| `pip install lark` | ❌ 「喂饱错误」。下次 ROS 换个插件还会炸 |
| `pytest -p no:launch_testing` | ❌ 要求插件**先导入成功**才能禁用，导入期就炸的话来不及 |
| **`unset PYTHONPATH`** | ✅ **在最外层断根** |

> **环境问题在环境层解决，不要用框架参数打补丁。**

固化成脚本 `scripts/dev/env.sh`：

```bash
export PY=/path/to/conda/envs/discoverse/bin/python
export MUJOCO_GL=osmesa
unset PYTHONPATH
```

用法：`source scripts/dev/env.sh`，然后所有命令用 `$PY -m pytest ...`。

**为什么用 `$PY -m pytest` 而不是直接 `pytest`**：保证解释器与装包环境一致，且 `-m` 会把当前目录加进 `sys.path`。

---

## 十三、名词速查表

按拼音排序。括号里是本文详细讲解的章节。

| 名词 | 一句话解释 |
|---|---|
| **assertion rewriting** | pytest 的招牌功能：`assert a == b` 失败时自动打印 a 和 b 的实际值（12.4） |
| **conftest.py** | pytest 的特殊文件，里面的 fixture 同目录和子目录都能直接用，无需 import（12.4） |
| **ctrl** | `data.ctrl`，你下发的控制指令数组，长度 = `nu`（3.2） |
| **decimation** | 降采样倍数：一次控制决策对应几个物理步（第四章） |
| **域随机化** | Domain Randomization，每次任务前随机改变环境，缩小 sim-to-real gap（第九章） |
| **extends** | 任务 YAML 的继承机制，子配置只写差异部分（6.6） |
| **fixture** | pytest 的「测试准备工作」，靠参数名自动注入（12.4） |
| **flake** | 不稳定测试：同样代码有时通过有时失败 |
| **free 关节** | `type="free"`，物体可自由飞，占 7 个 qpos。是「可操作物体」的标志（3.4） |
| **具身智能** | Embodied AI，让 AI 控制有身体的机器人在物理世界做事（1.1） |
| **keyframe** | MJCF 里的预设姿态。本项目要求必须叫 `home`（3.4） |
| **逆运动学 / IK** | 已知末端目标位姿 → 求各关节角度。通常无闭式解（第八章） |
| **MjData** | MuJoCo 的「会变的状态」：qpos/qvel/ctrl/time（3.2） |
| **MjModel** | MuJoCo 的「不变的模型」：编译 XML 的产物，约 260ms（3.2） |
| **MJCF** | MuJoCo 用的 XML 格式，描述世界长什么样（3.1） |
| **mocap 体** | `mocap="true"`，不受物理影响、可用代码任意瞬移的幽灵物体。本项目用作 IK 目标可视化（7.3） |
| **MUJOCO_GL** | 选渲染后端的环境变量：`glfw`/`egl`/`osmesa`（3.6） |
| **nq** | qpos 的维度：描述姿态需要几个数（3.2、3.3） |
| **nu** | ctrl 的维度：能下几个控制指令（3.2、3.3） |
| **observation** | 「观测」，强化学习术语，在具身智能里通常指相机图像（6.5） |
| **parametrize** | pytest 装饰器：一个测试函数展开成多个独立用例（12.4） |
| **primitive / 原语** | 动作积木，如「移到某物上方」。本项目实际只实现了 2 个（7.4） |
| **qpos** | `data.qpos`，所有关节的当前位置数组，长度 = `nq`（3.2） |
| **site** | MJCF 里无质量的坐标系标记点，用来标记末端执行器等（3.4） |
| **skip** | pytest：「前提不满足，无法判断」。⚠️ 不要用它掩盖缺陷（12.6） |
| **sim-to-real gap** | 仿真与真实世界的差距，具身智能的核心难题（1.4） |
| **tendon** | MJCF 的「肌腱」，虚拟的线性组合自由度。用来让一个指令控制两根手指（3.4） |
| **timestep** | `opt.timestep`，物理积分步长，典型值 0.0025-0.005 秒（第四章） |
| **xfail** | pytest：「断言应成立但因已知缺陷不成立」。配 `strict=True` 用（12.6） |
| **覆盖率** | 测试执行了百分之几的代码。是**下限指标**，高了不保证质量（12.7） |
| **运动学树** | MJCF 里 `<body>` 的嵌套结构，表示父子连接关系（3.4） |
| **执行器 / actuator** | MJCF 的电机。`<position>` 是位置伺服，靠 `kp` 算力矩（3.4） |

---

## 附：还没讲的部分

本文有意跳过的模块，各一句话定位：

| 模块 | 是什么 | 为什么跳过 |
|---|---|---|
| `policies/` | 5 种 AI 算法（ACT、Diffusion Policy、RDT、OpenPI、PPO） | 237 个文件，属于「怎么学」而非「怎么仿真」 |
| `discoverse/aigc/` | Rodin 文本/图像生成 3D 资产 | 辅助工具 |
| `discoverse/gaussian_web_renderer/` | 把 3DGS 渲染流推到浏览器 | 辅助工具 |
| 3DGS 高保真渲染 | 3D Gaussian Splatting，把实拍照片重建成可渲染的 3D 场景 | 是论文核心卖点，但**新架构尚未接入**，只有老架构支持 |
| `examples/tasks_mmk2/` | MMK2 双臂移动机器人的 9 个任务脚本 | 走老架构，新架构不支持移动底盘 |

> **3DGS 是什么**：一种把真实场景拍成照片后重建为「一堆带颜色的 3D 高斯椭球」的技术，渲染效果接近照片级真实，远超 MuJoCo 默认的 OpenGL 渲染。这是 DISCOVERSE 论文的核心卖点，也是缩小 sim-to-real gap 的关键手段。
