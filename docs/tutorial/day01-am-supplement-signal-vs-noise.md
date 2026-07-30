# 补课 — 怎么从海量输出里抓住重点

> 你问的两个问题是新手和熟手的真正分界线：
> 1. 命令看不懂
> 2. 输出太多，不知道抓什么
>
> 命令可以查手册，**「从噪音里抓重点」才是核心能力**。这一课专门讲后者。

---

## 先记住一个原则

> **看输出之前，先想清楚你在问什么问题。**

新手的做法：跑命令 → 看到一屏输出 → 试图理解每一行 → 淹没。

熟手的做法：**先在心里立一个问题** → 跑命令 → **只找能回答那个问题的部分** → 其余全部无视。

区别不在阅读速度，在**是否带着问题去看**。

举例，你刚跑的第一条命令输出了 96 行文件路径。

- 如果你的问题是「这项目有哪些入口」→ 96 行都是答案，但**没用**，因为你记不住
- 如果你的问题是「**入口集中在哪几个目录**」→ 你只需要看目录名，96 行瞬间坍缩成 5 个目录
- 如果你的问题是「**哪个入口是我要测的主线**」→ 96 行里只有 2 行相关（`universal_tasks/`）

**同一份输出，问题不同，重点完全不同。**

---

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

（去掉 `*.py`，直接给目录，`-r` 才能真正生效）

> ⚠️ **这个 bug 的教训比命令本身值钱**：
>
> `-r` 和 `*.py` 语义冲突 —— 前者说「递归」，后者说「只这一层」，shell 先展开 `*.py`，`-r` 就没用了。
>
> **命令没报错，结果静默错误。** 这比报错危险得多：报错你会去查，静默错你会当成真相往下推理。
>
> **怎么防**：交叉验证。用另一种方法算一遍，看结果是否一致。比如：
> ```bash
> find discoverse/robots -name "*.py" | wc -l    # robots 下总共几个 py 文件？
> ls discoverse/robots/*.py | wc -l              # 只有一层的话几个？
> ```
> 两个数字不等 → 说明有子目录 → 你的扫描漏了。

---

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

## 关于「命令看不懂」的正确心态

**不要试图背下所有命令。** 熟手也天天查手册。

真正需要建立的是这三样：

1. **知道「有这么个工具」** —— 遇到「要统计出现次数」时能想到 `uniq -c`，具体参数可以查
2. **理解组合逻辑** —— `|` 管道、`$()` 命令替换、`for` 循环，这三个撑起 90% 的场景
3. **怀疑输出** —— 永远问「这结果可能怎么骗我」，然后交叉验证

第 3 点才是测试开发的核心素养。命令行能力是手艺，可以慢慢练；**怀疑精神是职业本能，现在就要建立。**

> 💡 **面试可以这么讲**：
> 「我在做依赖分析时写了个 grep 命令扫模块依赖，得出结论后觉得不对劲 —— 一个包不可能完全没有内部依赖。回头检查发现 `-r` 和 `*.py` 语义冲突，命令只扫了一层目录，静默漏掉了子目录。我改用 find + xargs 重扫，结论修正了。**这件事让我养成了对工具输出做交叉验证的习惯。**」
>
> 这段话比「我熟练使用 Linux 命令」有说服力一百倍 —— 它展示的是**发现自己错误的能力**。

---

## 现在回到 Day 1 上午

修正后的分层结论：

```
第0层  discoverse/__init__.py    路径常量（不算功能依赖）
第1层  utils                     真正的最底层
第2层  robots  /  envs           都只依赖 utils，互不依赖
第3层  robots_env                依赖 envs
       universal_manipulation    只依赖 utils —— 刻意绕开 envs ⚠️
第4层  task_base                 依赖 robots + robots_env
```

**你现在可以回答测试问题了**：

- **从哪写第一批测试？** → `utils`（最底层，无依赖，不用 mock）
- **哪里有架构风险？** → `universal_manipulation` 绕开 `envs` 自成一套
- **fixture 能不能复用？** → 不能，两条路线初始化方式不同

请继续 Day 1 上午的 **Step 3（monkey patch 调用链追踪）**。那一步比 grep 更能揭示真相 —— 因为静态分析会骗人，你刚刚已经亲身体会过了。
