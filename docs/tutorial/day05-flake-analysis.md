# Day 5 — Flake 定量分析：从「测试不稳定」到「数据管道质量」

> 上接 [day04-ik-and-defects.md](day04-ik-and-defects.md)（Step 5-8 已完成）
> 本课产出：`docs/flakiness-analysis.md`（flake 热力图 + 根因分桶 + 数采质量报告）
> 预计耗时：约 4 小时

---

## 0｜⚠️ 先读这一节：计划文档的 Day 5 大半不可用

计划文档给的命令是：

```bash
pytest tests/integration/test_task_matrix.py --count=50 -n 8 --json-report ...
```

**我逐条验证过，结果如下：**

| 计划里写的 | 实测 |
|---|---|
| `tests/integration/test_task_matrix.py` | ❌ **文件不存在**，要自己写 |
| `-n 8`（pytest-xdist） | ✅ 已装 |
| `--json-report` | ❌ 未装（本课 Step 0 装） |
| seaborn 画热力图 | ❌ 未装（**用 matplotlib 即可，不必装**） |
| 45 组合 × 50 次 | ✅ 可行 —— 实测单次 **2.17s** |

**更重要的是：计划文档的分桶模型不完整。** 实测存在**第四个桶**（配置错误导致的必然崩溃），它根本不是 flake，混进统计会污染整张热力图。

---

## 本课六步

| Step | 做什么 | 时间 | 性质 |
|---|---|---|---|
| 0 | 装依赖 + 并行安全自检 | 15 min | 准备 |
| **1** | **验证 Day 3-4 的修复**（同 seed 复现） | 20 min | **两天工作的验收** |
| 2 | 手工采样 + 建立分桶模型 | 45 min | 认知建立 |
| 3 | 写 `test_task_matrix.py` | 45 min | 工程 |
| 4 | 全量跑 + 热力图 | 90 min | 数据 |
| 5 | 写分析报告（含数采质量视角） | 45 min | 产出 |

---

# 知识点前置：Flake 是什么，为什么它对具身智能特别重要

## 什么是 flake

**同样的代码、同样的输入，有时通过有时失败的测试。**

| | 稳定失败 | **flake** |
|---|---|---|
| 能复现 | ✅ | **随机** |
| 能定位 | ✅ | 难 |
| 团队反应 | 去修 | **「再跑一次就好了」** |

**flake 真正的伤害不是那 25% 的失败，是它摧毁了测试的可信度。**

一旦团队养成「红了就重跑」的习惯，**真正的缺陷也会被重跑掩盖过去**。测试套件从「质量闸门」退化成「随机噪声发生器」。

## 但在具身智能里，flake 还有第二重身份

这个项目的 `universal_task_runtime.py` 不是测试脚本，**它是数据采集器**。跑一次 = 采一条轨迹。

所以：

> **flake 率 = 数据采集的失败率 = 训练数据的偏斜程度。**

而且看 [universal_task_runtime.py:340-342](../../examples/universal_tasks/universal_task_runtime.py#L340)：

```python
if not self.success:
    shutil.rmtree(self.save_dir, ignore_errors=True)
    print(f"   ❌ 任务未成功，已删除保存目录: {self.save_dir}")
```

**失败的 run 被整个删掉。** 这个设计对模仿学习是对的（下面第 5.3 节详述），但它让 flake **完全隐形** —— 你只看到干净的数据集，看不到它是从多少次尝试里筛出来的。

**Day 5 的真正目标：把这个隐形的东西量化出来。**

---

# Step 0｜装依赖 + 并行安全自检（15 分钟）

## 0.1 装什么

```bash
cd /home/ubuntu22/workspaces/airbot-play/DISCOVERSE
source scripts/dev/env.sh
$PY -m pip install pytest-json-report pandas
```

| 包 | 作用 | 为什么需要 |
|---|---|---|
| `pytest-json-report` | 把测试结果导出为 JSON | 2250 条结果没法用肉眼看，必须结构化 |
| `pandas` | 表格数据处理 | 分组统计（按机器人 × 任务聚合成功率） |

**不需要 seaborn** —— matplotlib 的 `imshow` 画热力图完全够用，少一个依赖少一份风险。

⚠️ `pytest-xdist` **已经装了**（Day 2 装的），别重复装。

**验证：**

```bash
$PY -c "import xdist, pytest_jsonreport, pandas, matplotlib; print('全部可用')"
```

## 0.2 并行安全自检（这一步是 Day 3 的回报）

```bash
$PY -m pytest tests/ -q          # 串行
$PY -m pytest tests/ -q -n 4     # 4 进程并行
```

**实测两者都是 `113 passed, 4 skipped, 10 xfailed`。**

> 📌 **知识点：为什么这一步值得单独做**
>
> `-n 4` 会启动 4 个**独立进程**。如果测试依赖**进程级全局状态**，并行结果会和串行不同 —— 典型症状是「单跑绿、`-n 8` 跑红」，而且换个 worker 数就不复现。
>
> **Day 3 选 `np.random.Generator` 实例而非 `np.random.seed()` 全局种子，第 2 条理由就是这个。** 今天你真的用上了 `-n`，而它一次就通过 —— 这不是运气。
>
> **反过来说**：如果你现在跑 `-n 4` 发现结果不一致，就说明还有全局状态没被隔离。这个自检是**并行化的前置条件**。

## 0.3 `--count` 和 `-n` 的区别

| 参数 | 插件 | 作用 |
|---|---|---|
| `--count=50` | pytest-repeat | **每个测试重复 50 次**（纵向） |
| `-n 8` | pytest-xdist | **8 个进程并行** （横向） |

两者**正交**，可以叠加：`--count=50 -n 8` = 重复 50 次，用 8 个进程分摊。

**验证 repeat 能用：**

```bash
$PY -m pytest tests/simulation/ -q --count=3
# 实测：12 passed, 3 xfailed  （4 条测试 × 3 次 = 12）
```

⚠️ 注意用例 ID 变成了 `test_xxx[3-3]` 这种形式 —— 后缀是「第几次/共几次」。

---

# Step 1｜验证 Day 3-4 的修复（20 分钟）⭐ 优先级最高

**这一步计划文档里没有，但它比整个 Day 5 的其他部分加起来都重要。**

理由：如果 Day 3-4 修的 seed 没有真正生效，后面 2250 次采样的数据**全部需要重新解释**。

## 1.1 先测「不固定 seed」的基线

```bash
source scripts/dev/env.sh
for i in $(seq 1 30); do
  $PY examples/universal_tasks/universal_task_runtime.py \
      -r airbot_play -t place_block -1 --headless 2>&1 \
    | grep -oE "实际距离=[0-9.]+"
done
```

**实测结果**：成功 23 / 失败 7 = **76.7%**

对比 Day 0 基线 75% —— **基本没变**。

> ⚠️ **这个结果本身很重要，而且容易被误读。**
>
> 「修了两个缺陷，成功率没提升」看起来像白干。**不是的。**
>
> Day 3-4 修的是**可复现性**，不是成功率。缺陷 J（避让半径）修复后碰撞检测更严格，但实测 200 个 seed 里 **0% 违规** —— 说明碰撞本来就不是失败的主因。
>
> **区分「修复无效」和「修复的不是这个问题」，是排查能力的分水岭。** 下面 Step 2 会找出真正的主因。

## 1.2 关键验证：固定 seed 后是否完全一致

```bash
# 临时改配置（记得备份！）
cp discoverse/configs/tasks/place_block.yaml /tmp/pb.bak
sed -i 's/    seed: null/    seed: 42/' discoverse/configs/tasks/place_block.yaml

for i in $(seq 1 8); do
  $PY examples/universal_tasks/universal_task_runtime.py \
      -r airbot_play -t place_block -1 --headless 2>&1 \
    | grep -oE "实际距离=[0-9.]+"
done

# 必须还原！
cp /tmp/pb.bak discoverse/configs/tasks/place_block.yaml
grep -n "seed:" discoverse/configs/tasks/place_block.yaml   # 确认回到 null
```

**实测结果：**

```
实际距离=0.0024
实际距离=0.0024
实际距离=0.0024
实际距离=0.0024
实际距离=0.0024
实际距离=0.0024
实际距离=0.0024
实际距离=0.0024
```

**8/8 完全一致。**

> 📌 **这是 Day 3-4 两天工作的最终验收。**
>
> Day 3 的单元测试证明了「`SceneRandomizer` 的随机化可复现」，**这一步证明的是「整条端到端管道可复现」** —— 包含 IK 求解、物理步进、状态机、成功判定。
>
> 单元测试绿 ≠ 端到端可复现。中间任何一环有隐藏随机性都会破坏它。
>
> **这句话可以直接写进简历**：「修复后同一 seed 端到端跑 8 次，最终距离逐位一致（0.0024m）。」

## 1.3 失败也能复现吗（这是最有价值的部分）

```bash
cp discoverse/configs/tasks/place_block.yaml /tmp/pb.bak
sed -i "s/    seed: .*/    seed: 13/" discoverse/configs/tasks/place_block.yaml
for i in 1 2 3 4 5; do
  $PY examples/universal_tasks/universal_task_runtime.py -r airbot_play -t place_block -1 --headless 2>&1 | grep -oE "实际距离=[0-9.]+"
done
cp /tmp/pb.bak discoverse/configs/tasks/place_block.yaml
```

**实测：seed=13 五次全部 `0.2378`，稳定失败。**

> 📌 **这才是确定性最大的实用价值：flake 从「随机噩梦」变成「可复现缺陷」。**
>
> | | 修 seed 之前 | 修 seed 之后 |
> |---|---|---|
> | 失败能复现吗 | ❌ | ✅ `seed=13` |
> | 能单步调试吗 | ❌ 每次不一样 | ✅ |
> | 修完能验证吗 | ❌ 只能看统计 | ✅ 跑那个 seed |
>
> **一个不可复现的 bug 和一个可复现的 bug，难度差一个数量级。**

---

# Step 2｜手工采样与分桶模型（45 分钟）⭐ 本课核心认知

## 2.1 为什么「成功率 76.7%」这个数字没用

**它不可行动。** 你不知道该修什么。

**分桶（bucketing）= 按失败的根因把失败分类**，让数字变成行动指南。

## 2.2 实测得到的四个桶（计划文档只有三个）

```bash
for i in $(seq 1 40); do
  OUT=$($PY examples/universal_tasks/universal_task_runtime.py -r airbot_play -t place_block -1 --headless 2>&1)
  ST=$(echo "$OUT" | grep -oE "完成状态: [0-9]+/10" | head -1 | grep -oE "[0-9]+/10")
  D=$(echo "$OUT" | grep -oE "实际距离=[0-9.]+" | head -1 | cut -d= -f2)
  if echo "$OUT" | grep -q "任务成功: ✅"; then echo "SUCCESS"
  elif [ "$ST" != "10/10" ]; then echo "BUCKET1_早期失败 state=$ST"
  else echo "BUCKET2_判据失败 dist=$D"; fi
done | awk '{print $1}' | sort | uniq -c | sort -rn
```

**实测（40 次）：**

```
24 SUCCESS
14 BUCKET2_判据失败
 2 BUCKET1_早期失败
```

| Bucket | 现象 | 根因 | 占失败 |
|---|---|---|---|
| **1** | `完成状态: 1/10`，「状态 1 设置失败」 | IK 早期不收敛 | ~12% |
| **2** | `10/10` 走完但判据失败 | **抓取失败**（见 2.4） | **~88%** |
| 3 | 超时 | 死循环 | 本次未观察到 |
| **4** | **异常崩溃，无完成状态** | **配置错误，非 flake** | 见 2.5 |

## 2.3 双峰分布：一个强信号

把 Bucket 2 的最终距离排序：

```
成功组: 0.0018 ~ 0.0195   （n=16，均值 0.0088）
失败组: 0.1736 ~ 0.3714   （n=14，均值 0.2505）

阈值 0.05 —— 成功组最大 0.0195，失败组最小 0.1736
中间间隙 0.154 m，【完全没有样本】
```

> 📌 **知识点：分布形状比均值更有信息量**
>
> 如果失败是「差一点点」，你会看到 0.05 附近有密集样本 —— 那意味着**调阈值或调容差**能解决。
>
> 实测是**双峰**：要么放进碗里（<0.02），要么差得离谱（>0.17）。中间真空。
>
> **双峰 = 两种截然不同的结局，不是一个连续量的波动。** 这立刻排除了「精度不够」这类假设。
>
> **看直方图，不要只看均值和标准差。** 均值 0.0088 vs 0.2505 只告诉你「有差别」，双峰告诉你「是二元结局」。

## 2.4 追根因：四步排查 Bucket 2

⚠️ **预告：这一节的结论是「排除了几个原因，根因未确定」，不是「找到了根因」。**
中途我一度以为查清了，被 2.5 节的反例推翻。**排查过程比结论更值得读。**

### 第一步：失败距离等于什么？

固定 `seed=13`，查物体初始位置：

```
block_green: [-0.073,  0.8579, 0.7458]
bowl_pink:   [-0.0622, 1.0954, 0.7301]
两物体初始间距: 0.2378 m
```

**而失败时的「实际距离」恰好也是 0.2378 m。**

→ **方块根本没被搬动，停在原处。**

### 第二步：给状态机装探针

用 monkeypatch 在每个原语后打印方块高度（Day 1 学的打桩技术）：

```python
import sys, numpy as np
sys.path.insert(0, "examples/universal_tasks")
import universal_task_runtime as U
from discoverse.utils import get_body_tmat

E = U.UniversalRuntimeTaskExecutor
orig = E.set_target_from_primitive
cnt = [0]

def patched(self, state_config):
    r = orig(self, state_config)          # ← 必须 return 原函数结果，否则行为被改变
    cnt[0] += 1
    blk = get_body_tmat(self.mj_data, "block_green")[:3, 3]
    bwl = get_body_tmat(self.mj_data, "bowl_pink")[:3, 3]
    print(f"TRACE #{cnt[0]} prim={state_config.get('primitive'):16s} "
          f"grip={str(state_config.get('gripper_state')):6s} "
          f"blk_z={blk[2]:.4f} d_xy={np.linalg.norm(blk[:2]-bwl[:2]):.4f} ok={r}")
    return r

E.set_target_from_primitive = patched
U.main("airbot_play", "place_block", once=True, headless=True)
```

**实测对比：**

```
### seed=13（失败）
#1  move_to_object  open   blk_z=0.7458  d_xy=0.2378
#4  grasp_object    close  blk_z=0.7458  d_xy=0.2378
#8  move_to_object  close  blk_z=0.7458  d_xy=0.2378   ← 全程一动不动
#10 move_relative   open   blk_z=0.7458  d_xy=0.2378

### seed=2（成功）
#4  grasp_object    close  blk_z=0.6861  d_xy=0.1849
#7  move_to_object  close  blk_z=0.7329  d_xy=0.1820   ← 被抬起来了
#8  move_to_object  close  blk_z=0.7772  d_xy=0.0133   ← 搬到碗上方
```

**失败时方块的 z 坐标一微米都没变** → 夹爪走完了全套动作，但**根本没夹住**。

**同时排除了 IK**：失败的 run 里「状态 N 设置失败」出现 **0 次**，10 步全部 `ok=True`。

### 第三步：找几何规律

把物体位置转到 armbase 局部坐标，按「离基座距离」分组：

| block 离基座 | 样本 | Bucket 2 失败 |
|---|---|---|
| **< 0.315 m** | 11 | **0** ✅ |
| ≥ 0.315 m | 19 | **10（53%）** |

**这是一条清晰的界线。**

⚠️ 注意它是**必要不充分**条件：近处零失败，但远处也只有 53% 失败。「太远」是失败的**前提**，不是**唯一**原因。

### 第四步：读接触数据 —— 唯一的确凿证据

前三步都是**间接推断**。第四步直接问物理引擎。

MuJoCo 每步会算出所有**接触点**（contact），可以直接读：

```python
for i in range(d.ncon):              # ncon = 当前接触数量
    c = d.contact[i]
    b1 = m.geom_bodyid[c.geom1]      # 接触双方属于哪两个 body
    b2 = m.geom_bodyid[c.geom2]
```

**「抓到了」的物理定义：方块同时与左右两指有接触。**

实测（每 10 步采样一次，只显示关键段）：

```
### seed=2（成功）
step=110 state=3 grip=0.0400 接触=['table']
step=120 state=4 grip=0.0000 接触=['right', 'table']            ← 右指碰到了
step=130 state=4 grip=0.0000 接触=['left', 'right', 'table']    ← 两指都碰到 ✅
step=170 state=6 grip=0.0000 接触=['right']            blk_z=0.7329  ← 被抬起

### seed=13（失败）
step= 90 state=3 grip=0.0400 接触=['table']
step=100 state=4 grip=0.0000 接触=['table']            ← 夹爪合了，但没碰到方块
step=270 state=9 grip=0.0400 接触=['table']            ← 全程只有 table ❌
```

**seed=13 从头到尾，方块只和桌子接触，夹爪一次都没碰到它。**

`grip_ctrl` 从 0.04（张开）变为 0.0000（闭合）—— 指令发出去了，夹爪确实合上了，**但合在了空气里**。

> 📌 **知识点：能读事实的时候，不要用数字去推**
>
> 「末端离方块 8mm」只是个标量 —— 你不知道那 8mm 偏在哪个方向，也不知道够不够得着。
>
> 「有没有接触」是**布尔事实**，由物理引擎判定，不需要你解释。
>
> **前三步花了大量推理，第四步一条数据就定案。** 排查时先问「这个系统有没有直接暴露我要的事实」。

### 当前的准确结论

| 结论 | 状态 | 依据 |
|---|---|---|
| Bucket 2 = 抓取失败，方块全程不动 | ✅ **确凿** | 接触数据 |
| **IK 不是原因** | ✅ **确凿** | 末端偏离 IK 目标仅 0.5mm，比成功那次（1.5mm）**还准** |
| **手臂没到位不是原因** | ✅ **确凿** | 末端离方块 8.3mm，比成功那次（8.9mm）**还近** |
| 失败与「离基座 >0.315m」相关 | ⚠️ **弱相关** | 必要不充分，N=30 |
| **根因** | 🔍 **未确定** | 见下 |

**「未确定」是一个诚实的结论，不是失败。** 下面这一节说明为什么。

---

## 2.5 ⚠️⚠️ 一次真实的证伪 —— 本课最重要的一节

**这一节记录的是我自己犯的错。** 它比找到根因更有教学价值。

### 我当时的推理

拿到接触数据后，我进一步测量了**夹爪闭合瞬间方块在末端坐标系中的位置**（不只是距离，还有方向）：

| | seed=2（成功） | seed=13（失败） |
|---|---|---|
| **横向 (xy)** | 7.9mm | **1.5mm** |
| **轴向 (z)** | 4.1mm | **8.1mm** |
| 总距离 | 8.9mm | 8.3mm |

末端坐标系的 z 轴是**手指伸出的深度方向**。

于是我得出结论：

> 「seed=13 的方块在夹爪够不到的深度上，手指合拢时从它上方掠过。**根因彻底查清了。**」

**这个解释看起来完美**：它解释了为什么总距离相近却一个成功一个失败，也解释了为什么接触列表里从未出现 left/right。

### 然后我扩大了样本

跑 20 个 seed，测量每次抓取瞬间的轴向偏差：

| seed | 轴向 | 结果 |
|---|---|---|
| 0 | 10.0mm | FAIL |
| **4** | **7.5mm** | **OK** ← 反例 |
| 13 | 8.1mm | FAIL |
| **14** | **8.1mm** | **OK** ← **反例，数值与 13 完全一样** |
| 16 | 9.5mm | FAIL |

**seed=14 的轴向偏差和 seed=13 完全相同（8.1mm），但它成功了。**

四个候选变量的组间差异也全都很弱：

| 变量 | OK 均值 | FAIL 均值 | 差 |
|---|---|---|---|
| 轴向 | 4.06mm | 5.53mm | +1.5 |
| 横向 | 4.95mm | 4.69mm | −0.3 |
| blk_z | 0.666 | 0.689 | +0.02 |
| reach | 0.324 | 0.355 | +0.03 |

**没有任何一个变量能干净地分开两组。** N=20 下这些差异都在噪声范围内。

**假设证伪。**

### ⭐ 为什么我会犯这个错

我用**两个样本**（seed=2 vs seed=13）的对比，就宣布找到了根因。

> 📌 **成对对比是最容易产生假根因的方法。**
>
> 任何两次运行之间都有**几十个数值不同** —— 位置、高度、距离、角度、时序。你总能找到一个「看起来像原因」的，而且它**必然能解释这两个样本**（因为你就是从它们身上挑出来的）。
>
> 这在统计上叫**过拟合到样本**：解释力 100%，泛化能力 0。
>
> **唯一的解药是主动去找反例** —— 不是等它出现，是扩大样本**专门去找**。

**更讽刺的是**：我在本文 2.4 节亲手写下过

> 「两个样本的某个数值不同」不等于「那就是原因」—— 必须看整体分布。

**然后在下一轮里违反了它。**

> 📌 **知道一条原则，和在压力下遵守它，是两件事。**
>
> 找到一个「完美解释」的瞬间是最危险的 —— 那种「终于搞定了」的感觉会让你停止验证。
>
> **越是觉得自己找到了答案，越要去找反例。**

### 另一条被证伪的假设：桌面高度

更早的时候我怀疑是**桌面高度随机化**（失败时 blk_z=0.7458，成功时 0.6861，差 6cm）。

按 z 排序 30 个 seed：

```
z=0.6169 OK | z=0.6248 B2 | z=0.6273 OK | z=0.6286 OK | ...
z=0.7458 B2 | z=0.7491 OK | z=0.7540 B2
```

**交错分布，无阈值。** 假设证伪。

⚠️ **但这次证伪的方式本身也有局限**：单变量排序看不出规律，**不等于该变量无关** —— 它可能只在与其他变量组合时才起作用（交互效应）。

**「单变量无关」和「该变量不参与」是两个结论。** 前者是数据支持的，后者不是。

### 剩下的候选（留给你）

- 夹爪闭合速度 vs 手臂移动速度的时序竞争
- 接触摩擦/刚度参数
- **方块被随机化的朝向**（`_randomize_objects` 是否改了 quat —— 我全程没查过这个）
- 多因素耦合

### 这一节该怎么写进报告

**不要写「根因是 X」，写：**

> **已排除**：IK 求解（偏差 0.5mm）、手臂到位（8.3mm，优于成功组）
> **已确认**：夹爪闭合时与方块零接触（物理引擎接触数据）
> **已证伪**：轴向深度假设（seed=14 反例）、桌面高度假设（无阈值）
> **弱相关**：离基座距离 >0.315m（必要不充分）
> **未确定**：根因

**一份「排除了 A、B，证伪了 C、D，锁定在 E 范围内」的报告，比一份自信的错误结论有价值得多。**

---

## 2.6 关于「离基座 0.315m」这条线要不要写进报告

写，但**必须标注它的强度**。

`place_block.yaml` 的随机化范围（相对 armbase）：

```yaml
x_range: [0.2, 0.4]
y_range: [-0.2, 0.2]
```

角落处距离 = √(0.4² + 0.2²) = **0.447 m**。

**已知事实**：<0.315m 的 11 个样本零 Bucket-2 失败；≥0.315m 的 19 个样本中 10 个失败（53%）。

**能说的**：随机化范围包含了一片失败率显著更高的区域，且**该范围的设定没有任何证据表明参考过机械臂的可靠工作空间**。

**不能说的**：「根因是随机化范围太大」—— 因为远处也有 47% 成功，近处样本量也只有 11。

> 📌 **相关性的正确表述方式**
>
> ❌ 「因为太远所以失败」
> ✅ 「失败集中在 >0.315m 区域（10/19 vs 0/11），但该区域也有 47% 成功 —— 距离是**风险因子**，不是**充分原因**」
>
> 第二种写法更长、更啰嗦，但它是**对的**，而且读者能据此判断该不该采信。

## 2.7 ⚠️ Bucket 4：计划文档漏掉的一类

抽样测试其他组合时发现：

```bash
$PY examples/universal_tasks/universal_task_runtime.py -r panda -t cover_cup -1 --headless
```

**输出：**

```
Camera 'eye_arm' not found in the MJCF model.
❌ 运行时执行失败: The camera "eye_arm" does not exist.
```

**没有「完成状态」，没有距离 —— 直接崩溃。**

实测：`panda × cover_cup` 和 `ur5e × cover_cup` **每次必崩**。

> 📌 **这不是 flake，是配置缺陷。**
>
> `cover_cup` 对非 airbot_play 机器人声明了不存在的相机。它 100% 失败，**没有随机性**。
>
> **如果混进 flake 统计，会得到「panda × cover_cup 成功率 0%」这个看似惊人但完全误导的结论** —— 让你去调 IK 容差，而真正的问题是一行配置。
>
> **分桶的第一职责是把「不是 flake 的东西」剔出去。** 混入必然失败的组合，热力图上那格会永远是黑的，掩盖真正的信号。

**这与 Day 2 缺陷 B 同族** —— `camera_configs` 与实际 MJCF 不匹配。

---

# Step 3｜写 `test_task_matrix.py`（45 分钟）

计划文档假设这个文件存在，实际要自己写。

## 3.1 设计决策：为什么不用 pytest 直接跑 45 组合

**先想 2 分钟**：把「跑一次任务」写成一个 pytest 用例，用 `--count=50 -n 8`，行不行？

<details>
<summary>展开</summary>

**能跑，但有三个坑：**

1. **单次 2.17s，45×50 = 2250 次 ≈ 81 分钟**。pytest 的 `timeout=60` 会不会误杀？（不会，那是单用例超时）
2. **失败信息丢失**。pytest 只记录 pass/fail，而我们要的是**分桶** —— 需要解析「完成状态」「实际距离」。
3. **子进程 vs 进程内**。`universal_task_runtime.main()` 在进程内调用会污染全局状态（MuJoCo 模型、matplotlib）。用 `subprocess` 更干净。

**结论：用 pytest 做调度和报告，但每个用例内部用 `subprocess` 跑，并自己解析输出分桶。**

</details>

## 3.2 代码

创建 `tests/integration/__init__.py`（空）和 `tests/integration/test_task_matrix.py`：

```python
"""9 机器人 × 5 任务的 flake 矩阵采样。

⚠️ 这不是常规回归测试 —— 它是【数据采集实验】：
   常规测试问「代码对不对」，本文件问「这个组合的成功率是多少」。
   因此默认 skip，只在显式指定 -m flake 时运行。

用法：
    $PY -m pytest tests/integration/test_task_matrix.py -m flake \
        --count=20 -n 4 --json-report --json-report-file=flake.json

为什么用 subprocess 而非进程内调用 main()：
    universal_task_runtime 会加载 MuJoCo 模型、创建编码器、写文件。
    进程内重复调用会累积全局状态（Day 2-4 反复遇到的主题）。
    子进程保证每次运行完全隔离 —— 代价是 ~0.3s 的启动开销，值得。
"""
import os
import re
import subprocess
import sys

import pytest

pytestmark = pytest.mark.flake

ROBOTS = ["airbot_play", "arx_l5", "arx_x5", "iiwa14", "panda",
          "piper", "rm65", "ur5e", "xarm7"]
TASKS = ["cover_cup", "place_block", "place_coffeecup",
         "place_kiwi_fruit", "stack_block"]

RUNTIME = "examples/universal_tasks/universal_task_runtime.py"
TIMEOUT_S = 120


def _classify(stdout: str, returncode: int) -> dict:
    """把一次运行的输出分桶。

    四个桶（Day 5 实测，计划文档只列了前三个）：
      SUCCESS  任务成功
      BUCKET1  完成状态 < 10/10 —— IK 早期不收敛
      BUCKET2  完成状态 10/10 但判据失败 —— 抓取失败
      BUCKET3  超时
      BUCKET4  异常崩溃，无完成状态 —— 【配置缺陷，不是 flake】

    BUCKET4 必须单独成桶：它 100% 复现，混进 flake 统计会让
    热力图上那格永远是黑的，掩盖真正的随机性信号。
    """
    if returncode == -9 or "TIMEOUT" in stdout:
        return {"bucket": "BUCKET3_超时", "state": None, "dist": None}

    m_state = re.search(r"完成状态: (\d+)/(\d+)", stdout)
    m_dist = re.search(r"实际距离=([\d.]+)", stdout)
    dist = float(m_dist.group(1)) if m_dist else None

    if "任务成功: ✅" in stdout:
        return {"bucket": "SUCCESS", "state": m_state.group(0) if m_state else None,
                "dist": dist}

    if m_state is None:
        # 没跑到统计阶段 —— 崩溃
        return {"bucket": "BUCKET4_配置崩溃", "state": None, "dist": None}

    done, total = int(m_state.group(1)), int(m_state.group(2))
    if done < total:
        return {"bucket": "BUCKET1_早期IK失败", "state": f"{done}/{total}", "dist": dist}
    return {"bucket": "BUCKET2_判据失败", "state": f"{done}/{total}", "dist": dist}


@pytest.mark.parametrize("robot", ROBOTS)
@pytest.mark.parametrize("task", TASKS)
def test_task_combination(robot, task, repo_root, record_property):
    """跑一次 robot × task，把分桶结果记进报告。

    ⚠️ 本用例【故意不断言成功】—— 它是采样器，不是质量门。
    断言成功率会让 45 个组合里一大半永远红，测试失去意义。
    真正的判定留给 Step 5 的分析报告。

    唯一的断言：进程不能是配置崩溃（BUCKET4）——
    那是确定性缺陷，应该被修，不该被当成 flake 容忍。
    """
    proc = subprocess.run(
        [sys.executable, RUNTIME, "-r", robot, "-t", task, "-1", "--headless"],
        cwd=str(repo_root), capture_output=True, text=True, timeout=TIMEOUT_S,
        env={**os.environ, "MUJOCO_GL": "osmesa"},
    )
    result = _classify(proc.stdout, proc.returncode)

    # record_property 会写进 junit-xml / json-report，供后续聚合
    record_property("robot", robot)
    record_property("task", task)
    record_property("bucket", result["bucket"])
    record_property("state", result["state"])
    record_property("dist", result["dist"])

    if result["bucket"] == "BUCKET4_配置崩溃":
        pytest.fail(
            f"{robot} × {task} 配置缺陷（非 flake）：{proc.stdout.strip().splitlines()[-1]}"
        )
```

**注册 marker**（`pyproject.toml` 的 `markers` 列表里加一行）：

```toml
    "flake: flake 率采样实验，非常规回归；需显式 -m flake 运行，单次数分钟起",
```

**默认不跑**（`addopts` 里加）：

```toml
addopts = "--strict-markers --tb=short -ra -m 'not flake'"
```

> 📌 **知识点：为什么要默认排除**
>
> 这个文件跑一次 81 分钟。如果它混在 `pytest tests/` 里，**日常回归从 3 秒变成 81 分钟**，没人会再跑测试。
>
> **区分「回归测试」和「实验」**：
>
> | | 回归测试 | 实验 |
> |---|---|---|
> | 问的问题 | 代码对不对 | 这个数是多少 |
> | 频率 | 每次提交 | 偶尔 |
> | 有断言吗 | 必须有 | 可以没有 |
> | 耗时 | 秒级 | 分钟~小时 |
>
> **两者混在一起，回归测试会被拖垮。** marker + 默认排除是标准做法。

## 3.3 先小规模验证管道

**别一上来跑 81 分钟。**

```bash
$PY -m pytest tests/integration/test_task_matrix.py -m flake \
    -k "airbot_play and place_block" --count=5 -v
```

确认：能跑通、分桶正确、`record_property` 有数据。

---

# Step 4｜全量采样与热力图（90 分钟）

## 4.1 跑

```bash
$PY -m pytest tests/integration/test_task_matrix.py -m flake \
    --count=20 -n 4 \
    --json-report --json-report-file=/tmp/flake.json \
    --tb=no -q
```

**参数解释：**

| 参数 | 作用 |
|---|---|
| `--count=20` | 每组合 20 次（45×20=900 次，约 33 分钟；先别上 50） |
| `-n 4` | 4 进程并行（Step 0 已验证无污染） |
| `--json-report-file` | 结构化输出，供 pandas 聚合 |
| `--tb=no` | 不打 traceback（900 条会刷屏） |

> ⚠️ **为什么先 20 不是 50**
>
> 标准误 ≈ √(p(1-p)/N)：
>
> | N | p=0.75 时 95% 置信区间 |
> |---|---|
> | 10 | ±27% ← 几乎没用 |
> | **20** | **±19%** |
> | 50 | ±12% |
> | 200 | ±6% |
>
> **N=20 够区分「75%」和「40%」，不够区分「75%」和「70%」。**
>
> 先跑 20 看整体格局，值得深挖的组合再单独加大 N。**做实验前先问：我要区分多大的差异？那决定了 N。**
>
> Day 2 学过定性版：「9 个样本 5 对 4 错能定位缺陷，2 个样本 1 对 1 错无法判断」。这是它的定量版。

## 4.2 聚合与热力图

```python
"""从 flake.json 生成成功率热力图。"""
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")            # 无显示器环境必须
import matplotlib.pyplot as plt

ROBOTS = ["airbot_play","arx_l5","arx_x5","iiwa14","panda","piper","rm65","ur5e","xarm7"]
TASKS  = ["cover_cup","place_block","place_coffeecup","place_kiwi_fruit","stack_block"]

with open("/tmp/flake.json") as f:
    data = json.load(f)

# 收集 (robot, task) -> [bucket, ...]
from collections import defaultdict
cells = defaultdict(list)
for t in data["tests"]:
    props = dict(t.get("user_properties", []))
    if "robot" in props:
        cells[(props["robot"], props["task"])].append(props["bucket"])

rate = np.full((len(TASKS), len(ROBOTS)), np.nan)
note = {}
for i, task in enumerate(TASKS):
    for j, robot in enumerate(ROBOTS):
        b = cells.get((robot, task), [])
        if not b:
            continue
        rate[i, j] = sum(x == "SUCCESS" for x in b) / len(b) * 100
        # 主导失败模式
        fails = [x for x in b if x != "SUCCESS"]
        if fails:
            note[(i, j)] = max(set(fails), key=fails.count).split("_")[0]

fig, ax = plt.subplots(figsize=(11, 6))
im = ax.imshow(rate, cmap="RdYlGn", vmin=0, vmax=100, aspect="auto")
ax.set_xticks(range(len(ROBOTS))); ax.set_xticklabels(ROBOTS, rotation=45, ha="right")
ax.set_yticks(range(len(TASKS)));  ax.set_yticklabels(TASKS)

for i in range(len(TASKS)):
    for j in range(len(ROBOTS)):
        if np.isnan(rate[i, j]):
            ax.text(j, i, "—", ha="center", va="center")
        else:
            lbl = f"{rate[i,j]:.0f}%"
            if (i, j) in note:
                lbl += f"\n{note[(i,j)]}"
            ax.text(j, i, lbl, ha="center", va="center", fontsize=8)

ax.set_title("任务成功率热力图（每格 N=20，标注为主导失败桶）")
fig.colorbar(im, label="成功率 %")
fig.tight_layout()
fig.savefig("docs/assets/flake-heatmap.png", dpi=150)
print("已保存 docs/assets/flake-heatmap.png")
```

> 📌 **知识点：为什么格子里要标「主导失败模式」**
>
> 只有颜色的热力图告诉你**哪里差**，标注告诉你**为什么差**。
>
> 同样是 40% 成功率：
> - 全是 BUCKET1 → **IK 问题**，去调容差/工作空间
> - 全是 BUCKET2 → **抓取问题**，IK 是好的
> - 全是 BUCKET4 → **配置错误**，一行就能修
>
> **这是「可行动指标 vs 虚荣指标」的直接体现。**

⚠️ 中文字体：matplotlib 默认可能显示方块。要么装中文字体，要么把标签改成英文。**先跑通再美化。**

---

# Step 5｜写分析报告（45 分钟）

产出 `docs/flakiness-analysis.md`。**结构建议如下**，其中 5.3 是本课最有分量的一节。

## 5.1 必须包含的内容

| 章节 | 内容 |
|---|---|
| 摘要 | 总体成功率、样本量、最差/最好组合 |
| 方法 | N 的选择依据、分桶定义、剔除了什么（BUCKET4） |
| 热力图 | 图 + 一段解读 |
| 分桶统计 | 各桶占比，**按组合分组** |
| 根因 | Bucket 2 的可达距离分析（Step 2.4） |
| **数采质量影响** | **见 5.3** |
| 建议 | 按「影响 × 修复成本」排序 |

## 5.2 ⚠️ 报告里必须诚实标注的三件事

1. **BUCKET4 被剔除了**，以及为什么（它不是 flake）
2. **N=20 的置信区间是 ±19%** —— 不要把 70% 和 75% 说成有差别
3. **被证伪的假设**（桌面高度）—— 写进报告，它有信息量

> 📌 **一份不写「我试错过什么」的分析报告，可信度是打折的。**
> 读者无法判断你是「一次就想对了」还是「只试了一个假设就停了」。

## 5.3 ⭐ 数采质量视角：为什么这比测试稳定性更重要

**这一节是 Day 5 相对计划文档最大的增量。**

### 失败数据该不该保存？

回到 [universal_task_runtime.py:340](../../examples/universal_tasks/universal_task_runtime.py#L340)：失败的 run 被 `shutil.rmtree` 删掉。

**对模仿学习来说，这个选择基本正确：**

模仿学习（本项目的 ACT / Diffusion Policy / RDT）的训练目标是「给定观测 → 输出**专家会做的动作**」。**失败轨迹不是专家行为**，喂进去等于教学生「这样做也行」——而那样会失败。

| 用途 | 要失败数据吗 |
|---|---|
| **行为克隆 / 模仿学习** | ❌ 不要，会直接学错 |
| **强化学习（PPO）** | ✅ 要，负奖励是学习信号 |
| 离线 RL | ✅ 要，但必须标 reward |
| **失败检测器 / 价值函数** | ✅ **必须要**，没负样本没法训 |

⚠️ 本项目 `policies/` 下 ACT/DP/RDT 是 IL，PPO 是 RL —— **对前三个删掉是对的，对 PPO 就浪费了**。

### 但「删掉」≠「无所谓」—— 三个真实代价

#### 代价 1｜⚠️ 幸存者偏差（最严重）

结合 Step 2.4 的实测：

| block 离基座 | Bucket 2 失败率 |
|---|---|
| < 0.315 m | **0%** |
| ≥ 0.315 m | **53%** |

**失败集中在远距离。** 删掉失败之后，数据集里：

- 近距离样本：**全保留**
- 远距离样本：**只留下碰巧成功的那一半**

**数据分布被系统性扭曲。** 训出的策略在远处表现差，而**指标上看不出来** —— 因为验证集同样偏斜。

> 📌 **幸存者偏差（survivorship bias）**
>
> 二战时统计返航飞机的弹孔分布，想给弹孔多的地方加装甲。Abraham Wald 指出应该加在**没有弹孔**的地方 —— 因为**被打中那里的飞机根本没飞回来**。
>
> 你的数据集就是「飞回来的飞机」。**缺失的样本才携带最重要的信息。**

#### 代价 2｜失败率本身是被丢掉的质量信号

删除是**静默**的：目录没了，没有日志，没有计数。于是你不知道：

- 采集 100 条实际尝试了 133 次
- 失败集中在哪个区域
- 成功率随配置变化了没有

**「25% 的尝试失败了」本身就是关于任务设计的关键信息** —— 它告诉你随机化范围超出了可靠工作空间。

#### 代价 3｜诊断信息一起没了

Step 2.4 那些结论，我是**重新跑 30+ 次**才拿到的。如果失败被保留（哪怕只存元数据），五分钟就能做完。

### 建议：三级数据保留策略

| 级别 | 存什么 | 用途 |
|---|---|---|
| L1 | 成功轨迹（完整） | IL 训练 |
| **L2** | **失败的元数据**（seed、物体位姿、失败桶、最终距离） | **分析、复现、覆盖率** |
| L3 | 失败的完整轨迹 | RL、失败检测器 |

**L2 性价比最高** —— 一行 JSON 几百字节：

```jsonl
{"seed": 13, "robot": "airbot_play", "task": "place_block",
 "result": "fail", "bucket": 2, "final_dist": 0.2378,
 "block_pos": [-0.073, 0.8579, 0.7458], "block_reach": 0.3991,
 "states_completed": 10}
```

> 📌 **这里藏着「确定性」的第二重价值**
>
> 有了 seed（Day 3 刚修好），**失败随时可以精确重放** —— 不需要存 500MB 轨迹，存 32 字节的 seed 就够了。
>
> Day 3 修 seed 的理由是「可复现性」。现在有了第二个理由：**它让「不存失败数据」从有损选择变成廉价选择。**

---

## 本课方法论沉淀

1. **分桶的第一职责是剔除「不是 flake 的东西」**（BUCKET4）。混入必然失败的组合会掩盖真正的信号。
2. **分布形状比均值更有信息量。** 双峰意味着二元结局，不是连续量波动 —— 直接排除「精度不够」类假设。
3. **样本量决定你能回答什么问题。** 做实验前先问：我要区分多大的差异？
4. **区分「修复无效」和「修复的不是这个问题」。** 成功率没变不代表 Day 3-4 白干 —— 修的是可复现性。
5. **确定性最大的实用价值是把 flake 变成可复现缺陷。** 可复现的 bug 比不可复现的容易一个数量级。
6. **单元测试绿 ≠ 端到端可复现。** 中间任何一环的隐藏随机性都会破坏它，必须端到端验证。
7. **区分「回归测试」和「实验」**，用 marker 隔离，否则回归被拖垮。
8. **采样器不该有成功断言。** 45 个组合一大半永远红的话，测试就失去意义了。
9. **「两个样本某数值不同」≠「那就是原因」**，必须看整体分布。
10. ⭐ **成对对比是最容易产生假根因的方法。** 两次运行间有几十个数值不同，你总能挑出一个「完美解释」—— 那是**过拟合到样本**：解释力 100%，泛化能力 0。
11. ⭐ **越是觉得自己找到了答案，越要主动去找反例。** 不是等反例出现，是扩大样本专门去找。「终于搞定了」的感觉是最危险的时刻。
12. ⭐ **知道一条原则，和在压力下遵守它，是两件事。** 我在 2.4 节亲手写下「成对对比不可信」，然后在下一轮违反了它。
13. **能读事实的时候，不要用数字去推。** 接触数据是布尔事实，比「末端离方块 8mm」这种标量强得多。
14. **「单变量无关」≠「该变量不参与」。** 单变量排序看不出规律，可能是交互效应。
15. **「根因未确定」是诚实的结论，不是失败。** 「排除了 A、B，证伪了 C、D，锁定在 E 范围内」比一个自信的错误结论有价值。
16. **相关性要标注强度。** 「失败集中在 >0.315m（10/19 vs 0/11），但该区域也有 47% 成功」比「因为太远所以失败」啰嗦，但它是对的。
17. **报告里要写被证伪的假设。** 不写试错过程的分析报告，可信度打折。
18. **flake 率 = 训练数据的偏斜程度。** 在具身智能里它不只是测试问题。
19. **删掉失败数据对 IL 是对的，但代价是幸存者偏差 + 丢失质量信号。** L2 元数据是性价比最高的折中。

---

## 面试叙事

> 「Day 3-4 修完 seed 之后，我做的第一件事是端到端验证：同一个 seed 跑 8 次，最终距离逐位一致（0.0024m）。单元测试绿不代表整条管道可复现，中间任何一环有隐藏随机性都会破坏它。
>
> 然后我跑了 40 次采样做分桶。总体成功率 76.7%，和修复前的 75% 基本持平 —— **但这不代表修复无效，修的是可复现性不是成功率**。真正的价值体现在：现在 `seed=13` 能稳定复现失败，五次全部 0.2378m。**flake 从随机噩梦变成了可复现缺陷。**
>
> 分桶发现 88% 的失败是「状态机走完 10/10 但判据失败」。我给状态机装了探针，发现失败时方块的 z 坐标**全程一微米没变**，而 IK 报告 10 步全部收敛。进一步读 MuJoCo 的接触数据后确认：**失败时方块全程只与桌面接触，夹爪一次都没碰到它** —— 夹爪合上了，但合在空气里。
>
> 这一步我要特别说，因为**我中途下过一个错误结论**。我测了闭合瞬间方块在末端坐标系里的位置，发现失败样本的轴向偏差 8.1mm、成功样本 4.1mm，就宣布『方块在夹爪够不到的深度上，根因查清了』。这个解释看起来很完美 —— 它同时解释了『总距离相近却结果相反』和『接触列表里从没出现手指』。
>
> **然后我扩大到 20 个 seed，立刻出现反例**：seed=14 的轴向偏差也是 8.1mm，和失败样本完全一样，但它成功了。四个候选变量的组间差异全都在噪声范围内。假设证伪。
>
> 我犯的错是**用两个样本的对比下结论**。任何两次运行之间都有几十个数值不同，你总能挑出一个完美解释 —— 那是过拟合到样本，解释力 100%、泛化能力 0。讽刺的是我在报告前一节刚写过『两个样本某数值不同不等于那就是原因』，然后自己违反了。**知道一条原则，和在压力下遵守它，是两件事。**
>
> 所以我最终的结论是『根因未确定』，但排查是有产出的：**已排除** IK（偏差 0.5mm，比成功组还准）和手臂到位（8.3mm，比成功组还近）；**已确认**夹爪零接触；**已证伪**轴向深度和桌面高度两个假设；**弱相关**是离基座 >0.315m（10/19 失败 vs 近处 0/11，但远处也有 47% 成功，所以是风险因子不是充分原因）。
>
> 我认为**一份『排除了 A、B，证伪了 C、D，锁定在 E 范围内』的报告，比一份自信的错误结论有价值得多** —— 后者会让下一个人朝错误方向修。
>
> 还有一个发现改变了报告的定位：`cover_cup` 对 panda/ur5e 声明了不存在的相机，100% 崩溃。**它不是 flake，混进统计会让热力图上那格永远是黑的**，误导人去调 IK 容差，而真正的问题是一行配置。所以我把它单独分成第四个桶剔除。
>
> 最后我加了一节数采质量分析。这个项目失败的 run 会被直接删除 —— 对模仿学习这是对的，失败轨迹不是专家行为。**但代价是幸存者偏差**：失败集中在远距离，删掉之后远距离样本只剩下碰巧成功的那一半，训出的策略在远处会更差而指标上看不出来。我建议保留失败的元数据（几百字节的 JSON）而不是完整轨迹 —— **而这正好靠 seed 实现：有了确定性，存 32 字节就能精确重放，不需要存 500MB。**」

**这段叙事的结构**：验收上一阶段 → 承认数字没变并解释为什么不是白干 → 分桶 → 装探针 → 读接触数据 → **主动坦白一次错误结论及其方法论原因** → 给出「排除/确认/证伪/弱相关/未确定」的分层结论 → 发现分类模型本身的缺陷 → 上升到数据管道质量。

**面试官在听的是**：你会不会只报好消息、能不能自己推翻自己、以及是否理解测试之外的业务后果。

> ⚠️ **关于「根因未确定」会不会减分**
>
> 不会 —— 前提是你说清了**排除了什么、怎么排除的**。
>
> 面试官见过太多「我定位到根因是 X」然后一问细节就崩的候选人。**能主动说出「我这个结论错了，错在方法上」的人极少**，而这恰恰是排查能力的最强信号：你不只会查，还知道自己什么时候可能在骗自己。
>
> 反过来，如果你把「轴向深度是根因」这个**已被反例推翻**的结论讲出去，面试官追问「你验证过多少样本」时就会很难看。
