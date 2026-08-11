问题1,感觉三个有部分共用的类有部分是自己独有的

## 三个降噪技巧

### 技巧 1｜先聚合，再看细节

你已经无意识地用了一次。对比这两条：

```bash
# ❌ 96 行，无法消化
grep -rl "if __name__" --include=*.py . | grep -v submodules | grep -v policies | sort

# ✅ 15 行，一眼看清结构
grep -rl "if __name__" --include=*.py examples/ | cut -d/ -f2 | sort | uniq -c | sort -rn
```

第二条多了什么？`cut` + `sort` + `uniq -c` + `sort -rn`。这四件套叫**聚合统计**，是命令行降噪的万能药：

| 命令 | 作用 | 记忆方式 |
|---|---|---|
| `cut -d/ -f2` | 按 `/` 切分，取第 2 段 | 把 `examples/tasks_mmk2/box_pick.py` 变成 `tasks_mmk2` |
| `sort` | 排序 | `uniq` 只能去重**相邻**行，所以必须先排序 |
| `uniq -c` | 去重并**计数** | `-c` = count |
| `sort -rn` | 按数字**倒序** | `-r`=reverse，`-n`=numeric（不加 `-n` 会按字符串排，10 会排在 9 前面） |

**这四件套你要背下来。** 遇到任何「输出太多」的场景，先想能不能聚合。

聚合之后你立刻看到了真正的信息：

```
12 tasks_airbot_play    ← 最多，说明这是主力
 9 tasks_mmk2           ← 次之
 9 robots
 2 universal_tasks      ← 只有 2 个，但它是「通用框架」
```

**这个分布本身就是情报**：`universal_tasks` 只有 2 个入口却号称「通用」，而 `tasks_airbot_play` 有 12 个 —— 说明新框架覆盖面还很小，老代码是主体。这个判断你不需要读任何代码就得出了。

### 技巧 2｜数量差异 = 信号

看这段你已经跑过的输出：

```
--- examples/universal_tasks ---
      1 from discoverse.universal_manipulation import UniversalTaskBase, ...
      1 from discoverse.envs import make_env
--- examples/tasks_airbot_play ---
     12 from discoverse.robots import AirbotPlayIK
     12 from discoverse.robots_env.airbot_play_base import AirbotPlayCfg
     12 from discoverse.envs import make_env
```

**左边那个数字是重点，不是右边的类名。**

- `12` 意味着：这个 import 出现在**全部 12 个文件**里 → 它是该目录的**标准套路**
- `1` 意味着：只有 1 个文件用 → 该目录只有 1 个主文件

**数字一致（都是 12）说明高度模板化** —— 12 个任务脚本结构雷同。

> 💡 **测试意义**：高度模板化 = 一份 fixture 能覆盖 12 个任务。这直接决定你的测试代码能不能复用。
>
> 反过来，如果 12 个文件的 import 各不相同，说明每个任务都是「手工作坊」，测试成本会高得多。

### 技巧 3｜关注「缺失」，而非「存在」

这是最高级的技巧，也最反直觉。

看依赖扫描的输出：

```
envs                     -> from discoverse.utils
universal_manipulation   -> from discoverse.utils          ← 注意这里
robots_env               -> from discoverse.envs from discoverse.utils
task_base                -> from discoverse.robots from discoverse.robots_env from discoverse.utils
```

新手看到的是「谁依赖谁」。熟手看到的是 —— **`universal_manipulation` 竟然不依赖 `envs`**。

**为什么这是重点？**

因为 `envs/simulator.py` 是 658 行的仿真基类，是项目的核心。`robots_env` 依赖它，`task_base` 间接依赖它。**唯独最新的 `universal_manipulation` 绕开了它，自己重写了一套。**

**「本该出现却没出现的东西」比「出现的东西」信息量大得多。**

同类思维在测试里到处是用：
- 日志里**没有**错误 ≠ 没出错（可能异常被吞了 —— 你已经见过缺陷 #1）
- 测试**全绿** ≠ 没 bug（可能根本没覆盖到）
- 配置项**声明了**但代码里 grep 不到 → 死配置（缺陷 #2 的 seed 就是这么找到的）

> ✍️ 把这条写进 devil-note：**「关注缺失」是我今天学到的最重要的思维方式。**

---

## 你跑的每条命令，逐字拆解

现在补上命令本身。**不要求背，要求能看懂 + 会查。**

### 命令 1

```bash
grep -rl "if __name__ == .__main__." --include=*.py . | grep -v submodules | grep -v policies | sort
```

| 片段 | 含义 |
|---|---|
| `grep` | 文本搜索 |
| `-r` | recursive，递归搜子目录 |
| `-l` | **只列文件名**，不显示匹配内容（小写 L，不是数字 1） |
| `"if __name__ == .__main__."` | 搜索的模式。`.` 是通配符，匹配任意单字符 —— 这里用来绕过引号问题（源码里可能是 `'` 或 `"`） |
| `--include=*.py` | 只搜 `.py` 文件 |
| `.` | 从当前目录开始 |
| `\| grep -v submodules` | 管道传给下一个 grep，`-v` = invert，**排除**含该词的行 |
| `\| sort` | 排序 |

**关键概念：管道 `|`** —— 把左边命令的输出，当成右边命令的输入。这是命令行的灵魂，能把简单工具串成复杂查询。

### 命令 2

```bash
grep -rl "if __name__ == .__main__." --include=*.py examples/ | cut -d/ -f2 | sort | uniq -c | sort -rn
```

新增部分就是技巧 1 讲的聚合四件套。

`cut -d/ -f2` 的实际效果：

```
输入: examples/tasks_mmk2/box_pick.py
      ^^^^^^^^ ^^^^^^^^^^ ^^^^^^^^^^^
      第1段    第2段       第3段        （用 / 分隔）
输出: tasks_mmk2
```

### 命令 3

```bash
grep -rhoE "from discoverse[.a-z_]* import [A-Za-z_, ]+" $d/*.py | sort | uniq -c | sort -rn | head -5
```

| 片段 | 含义 |
|---|---|
| `-h` | 不显示文件名（多文件搜索时 grep 默认加文件名前缀，这里不要） |
| `-o` | **only-matching**，只输出匹配的**部分**，不输出整行 |
| `-E` | 用扩展正则（支持 `+`、`\|`、`()` 等） |
| `[.a-z_]*` | 正则：`.`、小写字母、下划线，重复 0 次或多次 |
| `[A-Za-z_, ]+` | 大小写字母、下划线、逗号、空格，1 次或多次 |
| `head -5` | 只取前 5 行 |

> 💡 `-o` 是这条命令的关键。没有 `-o`，输出的是整行（含缩进、注释），`uniq -c` 就无法聚合了 —— 因为整行几乎不可能完全相同。
>
> **`-o` 让「统计模式出现次数」成为可能。** 这个技巧非常常用。

### 命令 4（我写错的那条）

```bash
for pkg in envs universal_manipulation robots_env robots task_base utils; do
  n=$(grep -rhoE "from discoverse\.[a-z_]+" discoverse/$pkg/*.py 2>/dev/null | sort -u | grep -v "discoverse\.$pkg" | tr '\n' ' ')
  printf "%-24s -> %s\n" "$pkg" "${n:-（无内部依赖）}"
done
```

| 片段 | 含义 |
|---|---|
| `for pkg in A B C; do ... done` | shell 循环，`$pkg` 依次取 A、B、C |
| `n=$(...)` | 命令替换：把命令的输出**存进变量** `n` |
| `2>/dev/null` | 把错误输出（fd 2）丢进黑洞 —— 某些目录没有 `.py` 文件会报错，不想看 |
| `sort -u` | 排序并去重（`-u` = unique，等于 `sort \| uniq`） |
| `grep -v "discoverse\.$pkg"` | 排除自己 import 自己 |
| `tr '\n' ' '` | translate，把换行符换成空格 → 多行变一行 |
| `printf "%-24s"` | 格式化输出，左对齐占 24 字符宽（为了对齐好看） |
| `${n:-（无内部依赖）}` | 如果 `$n` 为空，就用默认值 |

**这条命令的 bug 在哪**：`discoverse/$pkg/*.py` 只匹配**一层**。`robots/` 下有子目录 `robots/mmk2/`，其中的文件没被扫到。

正确写法：

```bash
find discoverse/$pkg -name "*.py" | xargs grep -rhoE "from discoverse\.[a-z_]+"
```

或者简单粗暴：

```bash
grep -rhoE "from discoverse\.[a-z_]+" discoverse/$pkg/ 2>/dev/null
```

## 一套可复用的「降噪套路」

以后任何时候输出太多，按这个顺序想：

```
1. 我想回答什么问题？        （最重要，先想清楚）
2. 能不能聚合？              cut / sort / uniq -c / sort -rn
3. 能不能过滤？              grep -v 排除噪音
4. 能不能只看头部？          head / tail
5. 数量差异在哪？            数字本身就是情报
6. 什么该出现却没出现？      最高级的信号
```

---

# Day 1 上午｜Step 3 调用链追踪实操记录

> 产出：[architecture-notes.md](architecture-notes.md) + [scripts/dev/trace_chain.py](../scripts/dev/trace_chain.py)
> 实跑组合：`airbot_play × place_block`、`airbot_play × cover_cup`（均 `MUJOCO_GL=osmesa` 无头）

## 卡点 1｜`python: No such file or directory`

第一次跑追踪脚本：

```bash
MUJOCO_GL=osmesa python /tmp/trace_chain.py
# env: ‘python’: No such file or directory
```

**原因**：conda 环境没激活，`PATH` 里只有 `/usr/bin/python3`，而系统 python **没装 mujoco**。

**解法**：用绝对路径的解释器，绕开激活状态问题：

```bash
MUJOCO_GL=osmesa /home/ubuntu22/miniconda3/envs/discoverse/bin/python scripts/dev/trace_chain.py
```

**反思**：`day00-setup.md:98-100` 早就把这个坑写成了「新手最高频翻车点」，我还是踩了。**读过 ≠ 记住**。教训：脚本化的东西不要依赖「当前 shell 状态」这种隐式前提，写绝对路径最稳 —— 这个习惯到写 CI 时会救命，因为 CI runner 里根本没有「已激活的 conda 环境」。

## 卡点 2｜探针不触发，我第一反应是「我写错了」

四个探针跑完，`PyavImageEncoder.encode` 一次都没打印。

**我的第一反应**：monkey-patch 打歪了。怀疑了三件事 ——
1. `rc.PyavImageEncoder` 拿到的是不是副本？（不是，`import module` 形式是对的）
2. 是不是 `encode` 在替换前就已经被绑定了？（不是，替换发生在 `import universal_task_runtime` 之前）
3. 是不是无头模式下不录视频？（这个方向对了一半）

**实际根因**：**探针没错，被测系统的配置缺了。** 顺着 `camera_encoders` 往上追：

```
universal_task_runtime.py:389  for cam_name in self.camera_cfgs.keys():   ← 空字典，循环体不执行
universal_task_runtime.py:80   self.camera_cfgs = {... task_config.camera_configs}
task_config.py:172             return self.config.get('observation', {}).get('cameras', [])
```

然后清点 YAML：

```bash
for f in discoverse/configs/tasks/*.yaml; do printf "%-50s %s\n" "$f" "$(grep -c '^observation:' $f)"; done
# cover_cup.yaml  1     ← 只有这一个有
# 其余 4 个        0
```

**验证**：换成 `-t cover_cup` 重跑 → 探针立刻触发，4/4。根因确认。

**这就是「技巧 3｜关注缺失」的第一次实战。** 四个探针里，**没触发的那一个信息量最大** —— 它暴露了「5 个任务里 4 个跑完全程不录任何视频」这个静默失效。如果我只看触发的三个探针，这个缺陷完全看不见，而且它躺在最常用的 demo 任务 `place_block` 上。

> 💡 **把这条写进方法论**：跑完任何一组探针/断言，都要**显式列出没触发的那些**。所以我在入库的 `trace_chain.py` 末尾专门加了 `⬜ 未触发` 的输出 —— 不让「缺失」隐形。这个设计比脚本本身重要。

## 收获｜动静结合才拿到完整事实

教程「答案对照」说：`universal_manipulation` 完全绕开 `SimulatorBase`。我 grep 验证，输出为空，**结论成立**。

但运行时探了一下：

```python
import universal_task_runtime
print('discoverse.envs.simulator' in sys.modules)   # True
```

而且伴随一条被吞掉的 `ModuleNotFoundError: No module named 'gaussian_renderer'`。

链路是：`universal_task_runtime.py:13 from discoverse.envs import make_env` → `envs/__init__.py:1 from .simulator import SimulatorBase`。

**两个结论都对，合起来才是完整事实**：包源码层面确实绕开了，运行时入口没绕开。Route B 想摆脱 659 行历史包袱的目标**没真正达成**，只是把耦合从「继承」挪到了「import」。

> 💡 **对测试的直接影响**：要断言「Route B 启动隔离性」，断言点必须是 `sys.modules`，不能是 grep 源码。**静态分析能证明「没写」，不能证明「没跑」。**

## 三个还没想透的问题

1. `place_block` 状态机跑满 10/10，但成功条件失败（block 与 bowl 实距 0.2908 m，阈值 0.05 m）。**状态机「执行完了」而物体没被搬走** —— 是原语高度参数不对（`grasp_height: 0.005` 太低抓不住？），还是抓取了但中途掉落？需要保留失败样本才能查，但 `:341` 在失败时直接 `rmtree` 删掉了数据。**这个「失败即删数据」本身要改。**
2. 随机化在 `executor.__init__ → reset()` 里就执行了，且直接改写 `mj_model`（光照、桌面高度、材质）。那么 fixture 里 `mj_model` 用 `session` 作用域**一定会串味**。下午学作用域时要重点想这个。
3. `make_env` 落盘到固定路径 `models/mjcf/tmp/{robot}_{task}.xml`，`save_dir` 也是固定的 `data/{robot}_{task}`。**pytest-xdist 并行跑会互相覆盖** —— 45 组合并行是刚需，这个必须先解决。