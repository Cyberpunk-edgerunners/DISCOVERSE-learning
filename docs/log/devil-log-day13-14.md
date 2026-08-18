# 魔鬼日志 · Day 13-14（2026-08-18）

> 主题：重构 `cicd_testing.py` 为结构化结果契约
> 目标缺陷：#2（退出码恒 0）、emoji 匹配（连带）、#12（表外机器人）
> 基线：122 passed → 收工 141 passed

---

## 开工状态

```bash
env -u PYTHONPATH MUJOCO_GL=osmesa $PY -m pytest tests/ -q | tail -2
# 122 passed, 4 skipped, 45 deselected, 15 xfailed
```

Day 10-11 的 GitHub Actions 五 job 全绿，Day 12 的 Jenkins job 也绿。
今天的任务就是**证明这些绿是假的**。

---

## 一、两个环境坑，开工前 20 分钟全交待在这

### 1.1 系统 python 没有依赖

```bash
python3 examples/universal_tasks/universal_task_runtime.py ...
# → ModuleNotFoundError: No module named 'mink'
```

依赖装在 conda 环境。全天统一：

```bash
PY=~/miniconda3/envs/discoverse/bin/python
```

### 1.2 ⚠️ ROS 污染 PYTHONPATH

```bash
$PY -m pytest tests/unit -q
# → ModuleNotFoundError: No module named 'lark'
#   （报错位置在 /opt/ros/humble/lib/python3.10/site-packages/launch/...）

echo $PYTHONPATH
# /opt/ros/humble/lib/python3.10/site-packages:/opt/ros/humble/local/lib/python3.10/dist-packages
```

shell 里 source 过 ROS，pytest 收集时去加载了 ROS 的包。

解法：`env -u PYTHONPATH`。全天所有 pytest 命令都带它。

---

## 二、缺陷 #2 实测复现【已核实】

```bash
cp discoverse/configs/tasks/place_block.yaml /tmp/place_block.yaml.bak

# 必然失败
sed -i "s/    seed: null/    seed: 13/" discoverse/configs/tasks/place_block.yaml
MUJOCO_GL=osmesa $PY examples/universal_tasks/universal_task_runtime.py \
    -r airbot_play -t place_block -1 --headless
echo "退出码 = $?"
```

```
   完成状态: 10/10
   任务成功: ❌ 否
⚠️ 第 1 轮任务未完全成功
退出码 = 0          ← 缺陷确认
```

对照（seed=42，必然成功）：

```
   任务成功: ✅ 是
退出码 = 0          ← 完全相同
```

**成功与失败对外无法区分。** 与 `defect-report.md` §四 记录一致。

> 💡 这个实验依赖 Day 3-4 修的缺陷 #1（seed 贯穿，commit `cd09b80`）。
> 没有可复现性，就构造不出「必然失败的输入」。

---

## 三、⭐ emoji 匹配：两个方向都会错【已核实】

复制 `cicd_testing.py:121` 的判定逻辑，喂四种输入：

```
  True  <- A. 真实成功
 False  <- B. 文案改成「第1轮任务完成」（去掉「成功」二字）
 False  <- C. 日志管道剥离 emoji
  True  <- D. 失败运行，日志里出现过「🎉…任务成功完成」字样
```

- B、C = **假阴性**（成功被判失败）
- D = **假阳性**（失败被判成功）← 致命

运算符优先级也确认了：

```bash
$PY -c "print((False or True and False) == (False or (True and False)))"
# True   → 实际是 A or (B and C)，非阅读直觉的 (A or B) and C
```

---

## 四、⭐ 意外收获：错误信息是彻底误导的【已核实】

跑未知机器人（重构前）：

```bash
$PY examples/universal_tasks/cicd_testing.py -r fake_robot -t place_block --serial
```

```
   ❌ 失败 (1.65s): Traceback (most recent call last): | ModuleNotFoundError: No module named 'gaussian_renderer'
```

**报的错和真实原因毫无关系。** 分流看子进程：

```bash
MUJOCO_GL=osmesa $PY examples/universal_tasks/universal_task_runtime.py \
    -r fake_robot -t place_block -1 --headless > /tmp/f.out 2> /tmp/f.err
# rc=2
```

- **stdout**：`Warning: gaussian_splatting renderer not found.`
- **stderr**：先是 `gaussian_renderer` 的 traceback（**良性，可选依赖**），
  然后才是真正的 `argparse: invalid choice: 'fake_robot'`

关键验证 —— 去看**成功**运行的日志：

```bash
grep -c "gaussian_renderer" /tmp/seed42.log
# 2      ← 成功的运行里也有这个 Traceback
```

根因：`_extract_error_message()` 按关键词扫描（`Traceback`/`Error`/…），
最后 `" | ".join(error_lines[-3:])` 只留 3 行 → 真正的 argparse 报错被挤掉。

> ⚠️ **修正计划文档**：问题 12 不是「静默丢弃」。
> 机器人照常提交执行了，子进程拒绝了它，父进程把它记成一次**普通任务失败** + 一条**无关错误信息**。
> 后果：拼错机器人名 → 看起来像任务回归 → 排查方向全错。

---

## 五、实现

### 5.1 新包 `discoverse/testing/`

- `result_schema.py`：`ExitCode`(IntEnum 0/1/2)、`FailureMode`(字符串常量)、`TaskResult`(dataclass)
- `junit_report.py`：手写 ElementTree 渲染

两个设计决定，都是踩了才定的：

1. **`failure_mode` 用字符串常量而非 Enum** —— 一开始用 Enum，`json.dump` 抛
   `TypeError: Object of type FailureMode is not JSON serializable`。契约要跨进程，先考虑可序列化。
2. **不用 `_pytest.junitxml.LogXML`**（计划文档建议） —— 与 pytest 内部 `Item`/`TestReport`
   强耦合，得伪造一堆内部对象。JUnit schema 很小，手写更可控。

`__post_init__` 三条校验（守门人）：

```
拦截成功 -> success=True 且有 failure_mode
拦截成功 -> success=False 但无 failure_mode
拦截成功 -> 未知 failure_mode（如拼错的 "tiemout"）
```

### 5.2 ⚠️ 一次返工：先读接口再写代码

`build_result()` 里取 seed，我第一版写了一长串防御性表达式：

```python
seed=(self.task.task_config.randomization.get("settings", {}) or {}).get("seed")
     if isinstance(getattr(self.task.task_config, "randomization", None), dict) else None,
```

写完去查 `task_config.py:180`，发现 `randomization` 本来就是返回 `dict | None` 的 `@property`。
那串代码不但多余，而且**类型不符时会静默返回 None** —— 又一个静默失败。

改成与 `task_base.py:58` 一致的读法：

```python
rand_cfg = self.task.task_config.randomization or {}
return (rand_cfg.get("settings") or {}).get("seed")
```

### 5.3 关键的一行

```python
sys.exit(int(_result.exit_code))
```

---

## 六、修复验证【已核实】

```
seed=13 → 退出码 = 1   failure_mode = "final_check"   completed 10/10   seed 13
seed=42 → 退出码 = 0   failure_mode = null            completed 10/10
```

未知机器人：

```
❌ 参数错误: 未知机器人 ['fake_robot']，支持的有: [...]
退出码 = 2
```

真实批量（2 机器人 × 2 任务，串行）：

```
🧪 airbot_play - place_block   ✅ 成功 (2.08s, 10/10 状态)
🧪 airbot_play - cover_cup     ❌ 失败 (2.14s) [ik_early]
🧪 panda       - place_block   ✅ 成功 (2.12s, 10/10 状态)
🧪 panda       - cover_cup     ❌ 失败 (2.38s) [config] ValueError: The camera "eye_arm" does not exist.

🔎 失败模式分布:  ik_early: 1   config: 1
批量退出码 = 1
```

**两个 cover_cup 失败，机制完全不同** —— 重构前它们长得一模一样。

---

## 七、⚠️ 差点误判：把 flake 当成分类器 bug

批量里 `airbot_play/cover_cup` 报 `ik_early` `0/17`，
单跑却是 `final_check` `17/17`。第一反应是分类器写错了。

**先采样，再下结论**（6 次）：

```
第1次: ik_early    0/17
第2次: ik_early    9/17
第3次: final_check 17/17
第4次: final_check 17/17
第5次: ik_early    0/17
第6次: final_check 17/17
```

分类器没错 —— `cover_cup.yaml` 的 seed 是 `null`，任务本身 flaky，
两种失败机制各占一半。`failure_mode` 反而把 flake 的**结构**照出来了。

---

## 八、JUnit XML 验证：不能只用自己的解析器

自己解析（ElementTree）：

```
root: testsuites {'tests': '4', 'failures': '1', 'errors': '1'}
  airbot_play::cover_cup   -> ['failure']
  airbot_play::place_block -> ['passed']
  panda::cover_cup         -> ['error']       ← 配置错误归 error
  panda::place_block       -> ['passed']
```

第三方独立解析器复核：

```bash
$PY -m pip install junitparser -q
```

```
解析成功  tests=4 failures=1 errors=1
```

**结论一致。** 自己写的 XML 用自己的解析器验证，构不成证据。

---

## 九、⚠️ 容器里的坑：一个我自己造出来的问题

宿主机 141 passed 全绿。挂载进容器跑：

```bash
docker run --rm -v "$PWD":/work -w /work discoverse:test \
    pytest tests/integration/test_exit_code_contract.py -q
# 4 failed → ModuleNotFoundError: No module named 'discoverse.testing'
```

**但容器里手动 import 是成功的**：

```bash
python -c "import discoverse.testing; print('ok')"   # ok
python -c "import discoverse; print(discoverse.__file__)"
# /work/discoverse/__init__.py
```

### 走过的弯路

去翻 `__editable___discoverse_1_9_0_finder.py`，发现 `NAMESPACES` 里有一份
**构建时冻结的子包清单**，不含 `discoverse.testing`。看起来完全说得通，
差点写进教程当结论。

### 真正的原因

```
MAPPING: dict[str, str] = {'discoverse': '/workspace/discoverse'}
```

镜像里代码烤在 **`/workspace`**，我挂到了 **`/work`**。工作目录一变：

```bash
cd /tmp && python -c "import discoverse; print(discoverse.__file__)"
# /workspace/discoverse/__init__.py    ← 镜像里那份【旧】代码
```

而且 —— 这个坑是**我自己造的**。CI 根本不挂载：

```bash
grep -n "docker run" .github/workflows/ci.yml
# run: docker run --rm discoverse:test pytest tests/ -q      ← 无 -v
```

CI 是**重建镜像**（`COPY . /workspace/`）。按 CI 的方式重来：

```bash
docker build -q -f discoverse/docker/Dockerfile.test -t discoverse:test-day13 .
docker run --rm discoverse:test-day13 pytest tests/ -q | tail -2
# 141 passed, 4 skipped, 45 deselected, 15 xfailed
docker run --rm discoverse:test-day13 pytest tests/integration/test_exit_code_contract.py -q
# 5 passed
```

**容器内与宿主机完全一致。**

---

## 十、lint

CI 对 `tests/` 是严格模式。第一次跑 6 个错误：

```
2 I001    unsorted-imports
2 PLW1510 subprocess-run-without-check
1 C408    unnecessary-collection-call
1 SIM115  open-file-with-context-handler
```

`PLW1510` 手动改，且**必须是 `check=False`** —— 非零退出码正是被测对象：

```python
# check=False：非零退出码正是本文件要断言的对象，不能让它抛异常
return subprocess.run(cmd, ..., check=False, ...)
```

```bash
env -u PYTHONPATH $PY -m ruff check tests/
# All checks passed!
```

---

## 十一、收工核实

```bash
env -u PYTHONPATH MUJOCO_GL=osmesa $PY -m pytest tests/ -q | tail -2
# 141 passed, 4 skipped, 45 deselected, 15 xfailed      （122 → 141，+19）

git diff --stat discoverse/configs/
# （空）—— 测试 fixture 逐字节还原了配置文件
md5sum discoverse/configs/tasks/place_block.yaml
# 7d225acd3537ae3aef210152119e779d   （与开工前一致）
```

新增 19 个测试 = 8（契约）+ 6（JUnit）+ 5（退出码集成）

---

## 遗留

1. **缺陷 X（段错误→139）未修**，只加了交叉校验去**检测**。它只在 glfw 交互模式出现，
   CI 全程 headless，属于「恰好绕开」而非「安全」。
2. **`cover_cup` flake 未修**（已量化：6 次采样两种模式各半）。
3. **批量 JUnit XML 尚未接进 CI job**（Jenkinsfile 已有 `junit` 步骤消费 pytest 的 XML）。
4. `universal_task_runtime.py` 的打印文案仍是自由文本；若将来有别的消费者，应考虑结构化日志。
