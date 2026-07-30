# Checkpoint · Day 1（2026-07-28）

> 分支：`feat/test-infra` ｜ 状态：**上午完成，下午未开始**
> 用途：下次开工时**只读这一份**就能接上，不必重读 day00/day01 全文。

---

## 一、本日实际完成范围

| 计划项 | 状态 | 产出 |
|---|---|---|
| Day 1 上午｜全局架构鸟瞰 | ✅ 完成 | [architecture-notes.md](../architecture-notes.md)、[trace_chain.py](../../scripts/dev/trace_chain.py) |
| ├ Step 1 入口点普查 | ✅ | 三个入口走不同路线 |
| ├ Step 2 静态依赖扫描 | ✅ | 5 层依赖图，`utils` 为最底层 |
| ├ Step 3 运行时调用链追踪 | ✅ | monkey-patch 工具入库，4 探针 |
| ├ 架构图（Mermaid ×6） | ✅ | 分层/双路线/配置汇合/时序 ×3 |
| └ 三个架构问题 + 五个测试视角问题 | ✅ | architecture-notes 六、七节 |
| **Day 1 下午-2｜pytest 骨架 + 配置层单测** | ❌ **未开始** | — |

**未完成的部分原封不动顺延**，见第五节。

---

## 二、四个可复现的核心事实（后续测试的靶子）

这四条都带实测证据，是接下来几天所有测试用例的出发点。完整版见 [architecture-notes.md 第八节](../architecture-notes.md)。

### 缺陷 A｜Route B 运行时仍加载 `simulator.py`，并吞掉 3DGS 导入异常
- 证据：`import universal_task_runtime` 后 `'discoverse.envs.simulator' in sys.modules == True`
- 链路：`universal_task_runtime.py:13` → `envs/__init__.py:1` → `simulator.py:22`
- 归属：Day 10-11（CI 启动时间）、Day 13-14（Warning 污染 stdout 干扰字符串判定）

### 缺陷 B｜5 个任务 YAML 中 4 个缺 `observation:` 段 → 全程不录视频
- 证据：`trace_chain.py -t place_block` → **3/4**（`PyavImageEncoder.encode` 未触发）；`-t cover_cup` → **4/4**
- 根因：`camera_configs` 读 YAML `observation.cameras`（`task_config.py:172`），模板 `templates/place_object.yaml` 也没这段，`extends` 继承不到
- **回归锚点**：修好后 `-t place_block` 应变成 4/4
- 归属：Day 18-19 数据质量验证器

### 缺陷 C｜`record_fps` 默认值写法失效（靠巧合正确）
- `task_config.py:165-167`：`self.config.get('observation', {'fps': 30}).get('fps', 30)`
- 当前两条路结果都是 30，不表现为 bug，但行为随配置形态漂移
- 归属：**Day 1 下午配置层单测**，覆盖三种输入（无 `observation` / 有但无 `fps` / 有 `fps`）

### 缺陷 D｜随机性完全无种子控制
- 证据：`grep -rn "seed" discoverse/universal_manipulation/ examples/universal_tasks/universal_task_runtime.py` → **输出为空**
- 而 `randomization.py` 有 15+ 处全局 `np.random.*`（`:230-231`、`:299-304`、`:322-327`、`:350`、`:378-383`）
- 违反 CLAUDE.md 自己声明的「确定性仿真」原则
- 归属：**Day 3-4 确定性攻坚的核心靶子**

### 补充观察｜失败即删数据
`universal_task_runtime.py:341` 任务失败时 `shutil.rmtree(self.save_dir)` → 失败样本无法事后分析。Day 13-14 加保留开关。

---

## 三、方法论沉淀（本日最该带走的）

```
1. 划边界     —— 先排除 submodules / policies，别贪心
2. 普查入口   —— grep "__main__"，数量分布本身就是情报
3. 依赖测绘   —— 扫 import 方向推出分层，最底层 = 最好测的地方
4. 动态追踪   —— monkey-patch + traceback，静态阅读会骗人
5. 画图       —— 卡住的地方就是没懂的地方
6. 提测试问题 —— 纯函数在哪？全局状态在哪？随机性从哪进来？
```

**三条硬结论**：

1. **静态分析能证明「没写」，不能证明「没跑」。** 要断言 Route B 启动隔离性，断言点必须是 `sys.modules`，不能是 grep 源码。
2. **「关注缺失」是最高价值的信号。** 四个探针里没触发的那一个信息量最大 —— 它暴露了 4/5 任务不录视频。所以 `trace_chain.py` 末尾专门打印 `⬜ 未触发`，**不让缺失隐形**。
3. **「完成状态 10/10」不等于成功。** 状态机跑满全程、日志一片正常，`block_green` 与 `bowl_pink` 实际距离 0.2908 m（阈值 0.05 m）。任何基于「跑完没报错」的判定都不可靠 → Day 13-14 必须换成结构化结果契约。

**降噪套路**（输出太多时按序想）：想清问题 → 能否聚合（`cut`/`sort`/`uniq -c`/`sort -rn`）→ 能否过滤（`grep -v`）→ 能否只看头部 → 数量差异 → 什么该出现却没出现。

---

## 四、环境与工具速查（下次开工直接抄）

```bash
cd /home/ubuntu22/workspaces/airbot-play/DISCOVERSE

# ⚠️ 必须用绝对路径解释器：conda 未激活时 `python` 会报 No such file or directory
#    系统 /usr/bin/python3 没装 mujoco。这个习惯到写 CI 时会救命。
PY=/home/ubuntu22/miniconda3/envs/discoverse/bin/python

# 调用链追踪（默认 4 探针）
MUJOCO_GL=osmesa $PY scripts/dev/trace_chain.py -r airbot_play -t cover_cup     # 预期 4/4
MUJOCO_GL=osmesa $PY scripts/dev/trace_chain.py -r airbot_play -t place_block   # 预期 3/4（缺陷 B）

# 追单个目标 + 完整调用栈
MUJOCO_GL=osmesa $PY scripts/dev/trace_chain.py -r airbot_play -t cover_cup \
    --probe discoverse.universal_manipulation.mink_solver:MinkIKSolver.solve_ik --full-stack
```

**monkey-patch 六要点**（`trace_chain.py:52-78`，缺一不可）：
① `import module` 拿目标，不能 `from x import y`（那样只改副本）
② 先保存原函数
③ 替身用 `*args/**kwargs` 保签名兼容
④ **必须 `return orig(...)`**，否则行为被改变
⑤ `setattr` 替换类属性 → 全实例生效
⑥ **必须在目标被调用之前替换**（`trace_chain.py:104-110` 的顺序：先打桩，后 `import universal_task_runtime`）

**基线数字**：`place_block` 成功率 75%（Day 0 实测）。

---

## 五、下次开工：Day 1 下午-2（原样顺延）

**目标**：pytest 骨架 + 配置层单测，把「精通 Pytest」坐实。

```bash
mkdir -p tests/{unit,kinematics,simulation,mobile_manipulation,data}
touch tests/__init__.py
```

要建的文件：
- `tests/conftest.py` —— 根 fixture。**作用域选择理由是面试必问**：
  - `mj_model_factory` 用 `scope="session"`（XML 解析 + mesh 加载慢，跨用例复用）
  - `mj_data` 用 `scope="function"`（含可变仿真状态，不新建会测试间污染）
- `tests/pytest.ini` —— markers（unit/integration/slow）、`timeout=60`、`--strict-markers --tb=short`
- `tests/unit/test_robot_config.py` —— 9 个 YAML × 必填字段，`@pytest.mark.parametrize`
- `tests/unit/test_task_config.py` —— `extends` 模板继承解析；**顺带钉死缺陷 C 的三种输入**
- `tests/unit/test_gripper_controller.py`
- `tests/unit/test_success_conditions.py` —— 5 种 condition 类型
- `tests/kinematics/test_ik_solver.py`
- `tests/data/test_recorder.py`

**验收标准**：
```bash
pytest tests/unit -v            # 全绿
pytest tests/ --collect-only    # 至少收集到 20 个测试
```

**之后**：Day 3-4 确定性攻坚（TDD 红→绿，靶子＝缺陷 D 的 seed 贯穿 + IK 状态泄漏）。

---

## 六、文件索引

| 文件 | 内容 |
|---|---|
| [docs/architecture-notes.md](../architecture-notes.md) | 本日主产出：架构图、调用链、配置体系、4 个缺陷 |
| [docs/devil-note-day01.md](../devil-note-day01.md) | 卡点与解决过程、三个降噪技巧、命令逐字拆解 |
| [docs/devil-log-day01.md](../devil-log-day01.md) | 面试话术片段 |
| [scripts/dev/trace_chain.py](../../scripts/dev/trace_chain.py) | 可复用的调用链追踪工具 |
| [docs/DISCOVERSE三周测试开发魔鬼计划.md](../DISCOVERSE三周测试开发魔鬼计划.md) | 总计划，Day 1 下午起顺延 |

**未提交**：本日所有产出仍在工作区（`docs/`、`scripts/dev/`、`CLAUDE.md`、`.claude/` 均为 untracked）。
