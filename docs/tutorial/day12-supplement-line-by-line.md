# Day 12 补充 — 逐行解析：Jenkinsfile、命令行、构建日志

> 配套 [day12-jenkins.md](day12-jenkins.md)
> 用途：**查阅型文档**，不用从头读。看不懂哪一行就跳到哪一节。
> 覆盖：Jenkinsfile 全部 176 行 + 今天用过的每条命令 + Jenkins 日志每种记号

---

## 目录

- [第一部分：Groovy / Jenkinsfile 语法基础](#第一部分groovy--jenkinsfile-语法基础)
- [第二部分：Jenkinsfile 逐行解析](#第二部分jenkinsfile-逐行解析)
- [第三部分：命令行逐条解析](#第三部分命令行逐条解析)
- [第四部分：Jenkins 构建日志逐行解析](#第四部分jenkins-构建日志逐行解析)
- [第五部分：pytest 输出符号表](#第五部分pytest-输出符号表)

---

# 第一部分：Groovy / Jenkinsfile 语法基础

看 Jenkinsfile 前先建立五个概念，否则每行都像天书。

## 1.1 它是 Groovy，不是 YAML

⚠️ **GitHub Actions 用 YAML，Jenkins 用 Groovy** —— 两者语法完全不同。

| | YAML（GitHub Actions） | Groovy（Jenkinsfile） |
|---|---|---|
| 结构靠 | **缩进** | **大括号 `{}`** |
| 注释 | `#` | `//` 或 `/* */` |
| 字符串 | `"x"` / `'x'` / 裸写 | `'x'`（死的）/ `"x"`（可插值） |
| 缩进错了 | ❌ 直接报错 | ✅ 无所谓（只影响可读性） |

📌 **所以 Jenkinsfile 里缩进纯粹是给人看的**，写错不影响运行 —— 但大括号少一个就全崩。

## 1.2 ⭐ 单引号 vs 双引号（最容易踩的坑）

**这是 Groovy 最重要的一条语法规则**：

```groovy
def name = "世界"

'你好 ${name}'    // → 你好 ${name}     ← 单引号：原样，不解析
"你好 ${name}"    // → 你好 世界        ← 双引号：解析 ${}
```

| 引号 | Groovy 叫法 | `${}` 会被 |
|---|---|---|
| `'...'` | String | **原样保留** |
| `"..."` | GString（可插值） | **Groovy 展开** |
| `'''...'''` | 多行 String | **原样保留** |
| `"""..."""` | 多行 GString | **Groovy 展开** |

⭐ **本项目 Jenkinsfile 里 `sh` 全部用三个单引号 `'''`。**

**为什么**：因为我们希望 `${RENDER_BACKEND}` 由 **shell** 展开，而不是 Groovy。

```groovy
sh '''
    echo ${RENDER_BACKEND}     ← 单引号：Groovy 不管，原样交给 shell，shell 读环境变量
'''

sh """
    echo ${RENDER_BACKEND}     ← 双引号：Groovy 先展开成 echo osmesa，再交给 shell
"""
```

⚠️ **两种都能工作，但含义不同**：

| 写法 | 谁展开 | 变量来源 |
|---|---|---|
| `'''` + `${X}` | **shell** | `environment {}` 注入的环境变量 |
| `"""` + `${X}` | **Groovy** | Groovy 变量 / `params.X` |

📌 **本项目统一用 `'''`（shell 展开）**，因为 `environment {}` 里的东西天然是环境变量。这也是为什么 §5.3.1 那个 bug 要靠「把 params 桥接进 environment」来修 —— **`params.X` 不是环境变量，shell 看不见它**。

## 1.3 声明式 pipeline 的固定骨架

```groovy
pipeline {              // ← 外壳，固定写法
    agent any           // ← 必须有，且必须是 pipeline 的第一个块
    parameters { }      // ← 可选：构建参数
    environment { }     // ← 可选：环境变量
    options { }         // ← 可选：pipeline 级选项
    stages {            // ← 必须有
        stage('名字') {  // ← 至少一个
            steps { }   // ← 每个 stage 必须有
        }
    }
    post { }            // ← 可选：收尾
}
```

⚠️ **这些块必须是 `pipeline {}` 的直接子块。** 写到外面 Jenkins 直接报语法错（你踩过一次）。

📌 **顺序不强制**（`environment` 放 `stages` 后面也能跑），但按上面这个顺序写可读性最好。

## 1.4 方法调用可以省略括号和逗号

Groovy 允许省略，所以同一件事有多种写法：

```groovy
junit testResults: 'test-results/*.xml', allowEmptyResults: true
junit(testResults: 'test-results/*.xml', allowEmptyResults: true)   // 等价
```

📌 **`key: value` 是「命名参数」**，顺序无所谓。而 `junit 'test-results/*.xml'` 是简写形式（只传第一个位置参数）。

## 1.5 三元运算符

```groovy
条件 ? 真时的值 : 假时的值
```

例（第 42 行）：

```groovy
TEST_IMAGE = "${params.RENDER_BACKEND == 'egl' ? 'discoverse:test-gpu' : 'discoverse:test'}"
```

读作：「如果参数是 egl，就用 test-gpu 镜像，否则用 test 镜像」。

---

# 第二部分：Jenkinsfile 逐行解析

## 第 1-10 行：文件头注释

```groovy
// Jenkinsfile —— DISCOVERSE 本机 GPU 回归（Day 12）
//
// ⚠️ 与 .github/workflows/ci.yml 的分工：
//   GitHub Actions = 每次 push 的准入门槛（云端、干净、无 GPU）
//   Jenkins        = 本机冒烟 + GPU 基础设施验证（本机、真实硬件）
//   两者不是互备，是互补。详见 docs/tutorial/day12-jenkins.md
//
// ⚠️ 路径规则（Step 2 的血泪）：Jenkins 自己在容器里，
//   而 `docker run -v` 的源路径由宿主机 dockerd 解析。
//   → sh 步骤用容器路径，docker -v 左边用宿主机路径。
```

`//` 是 Groovy 单行注释。

📌 **为什么把「分工」和「路径规则」写在文件最顶上**：这两条是**读这个文件必须先知道的前提**。半年后你（或同事）打开它，第一眼就该看到「这不是 GitHub Actions 的备份」和「路径有陷阱」。

> **注释写「为什么」，不写「是什么」。** `agent any` 后面写 `// 设置 agent` 是废话；写 `// 本机只有一个执行器，无需选节点` 才有价值。

## 第 12 行：`pipeline {`

```groovy
pipeline {
```

声明式 pipeline 的开始。⚠️ **整个文件必须被这一个 `pipeline {}` 包住。**

📌 Jenkins 有两种 pipeline 语法：

| | 声明式（Declarative） | 脚本式（Scripted） |
|---|---|---|
| 开头 | `pipeline {` | `node {` |
| 结构 | **强制**（stages/steps/post） | 自由的 Groovy |
| 校验 | ✅ 语法错立刻报 | ❌ 跑到才知道 |
| 推荐 | ⭐ **新项目用这个** | 复杂逻辑才用 |

## 第 13 行：`agent any`

```groovy
    agent any
```

**「在哪台机器上跑」**。

| 写法 | 含义 |
|---|---|
| `agent any` | 随便哪个可用执行器（**本机只有一个，就是 Jenkins 自己**） |
| `agent none` | pipeline 级不分配，每个 stage 自己指定 |
| `agent { label 'gpu' }` | 只在打了 `gpu` 标签的节点上跑 |
| `agent { docker { image '...' } }` | ⚠️ **需要 docker-workflow 插件，你没装** |

📌 **`agent any` 决定了 `sh` 步骤跑在 Jenkins 容器内部** —— 这正是「Jenkins 容器看不到项目目录」那个坑的根源。

## 第 15-23 行：`parameters` 块

```groovy
    // ⚠️ 加了 parameters 后，第一次 Build 仍是旧配置（无参数）。
    //    Jenkins 要先跑一次才「学到」参数，第二次起菜单才变成 Build with Parameters。
    parameters {
        choice(
            name: 'RENDER_BACKEND',
            choices: ['osmesa', 'egl'],
            description: 'osmesa=CPU软渲染(默认,零依赖) / egl=GPU无头渲染(实测快27倍,需 discoverse:test-gpu)'
        )
    }
```

| 行 | 作用 |
|---|---|
| `parameters {` | 声明构建参数，Jenkins 会渲染成表单 |
| `choice(...)` | 下拉框类型的参数 |
| `name: 'RENDER_BACKEND'` | 参数名 → 后续用 `params.RENDER_BACKEND` 读 |
| `choices: ['osmesa', 'egl']` | 选项列表，**第一个是默认值** |
| `description: '...'` | 显示在表单上的说明文字 |

⚠️ **`choices` 第一个元素就是默认值** —— 所以 `osmesa` 是默认，符合「默认必须是哪儿都能跑的那个」这条原则。

**其他参数类型**（今天没用到）：

```groovy
string(name: 'TAG', defaultValue: 'latest', description: '...')
booleanParam(name: 'SKIP_TESTS', defaultValue: false, description: '...')
text(name: 'NOTES', defaultValue: '', description: '多行文本')
password(name: 'TOKEN', defaultValue: '', description: '输入时打码')
```

📌 **第一次 Build 没有参数表单** —— Jenkins 必须先执行一次 Jenkinsfile 才知道有哪些参数。这是 Jenkins 的固有行为，不是配置错误。

## 第 25-43 行：`environment` 块

```groovy
    environment {
```

定义**环境变量**，在所有 `sh` 步骤里可见。

### 第 28 行：REPO_ON_HOST

```groovy
        REPO_ON_HOST = '/home/ubuntu22/workspaces/airbot-play/DISCOVERSE'
```

被测代码在**宿主机**上的绝对路径。

⚠️ **用单引号** —— 这是个死字符串，不需要插值。

📌 **它只能给 `docker run -v` 用，不能给 `cd` 用**（Jenkins 容器看不到这个路径）。

### 第 34 行：WS_IN_JENKINS

```groovy
        WS_IN_JENKINS = "${WORKSPACE}"
```

`WORKSPACE` 是 **Jenkins 内置变量**，值为当前构建的工作目录（容器内路径）。

实测值：`/var/jenkins_home/workspace/DISCOVERSE-GPU-Regression`

⚠️ **用双引号** —— 因为要插值 `${WORKSPACE}`。

**其他常用内置变量**：

| 变量 | 含义 | 实测值 |
|---|---|---|
| `WORKSPACE` | 工作目录 | `/var/jenkins_home/workspace/DISCOVERSE-GPU-Regression` |
| `JOB_NAME` | job 名 | `DISCOVERSE-GPU-Regression` |
| `BUILD_NUMBER` | 第几次构建 | `10` |
| `BUILD_URL` | 本次构建的网址 | `http://localhost:8080/job/.../10/` |
| `JENKINS_HOME` | Jenkins 数据目录 | `/var/jenkins_home` |

### ⭐ 第 35 行：WS_ON_HOST（今天最重要的一行）

```groovy
        WS_ON_HOST = "${WORKSPACE.replace('/var/jenkins_home', '/home/ubuntu22/robot_platform/jenkins_home')}"
```

**拆开看**：

```groovy
WORKSPACE                                    // "/var/jenkins_home/workspace/xxx"
  .replace('/var/jenkins_home',              //   把这段前缀
           '/home/ubuntu22/robot_platform/jenkins_home')   //   换成这段
// 结果: "/home/ubuntu22/robot_platform/jenkins_home/workspace/xxx"
```

`.replace(a, b)` 是 Java/Groovy 的字符串方法：把所有 `a` 换成 `b`。

⭐ **为什么必须用推导，而不是硬拼**：

```groovy
// ❌ 错误写法（我最初的版本）
WS_ON_HOST = "/home/ubuntu22/robot_platform/jenkins_home/workspace/${JOB_NAME}"
```

并发构建时 Jenkins 会分配 `xxx@2` 的 workspace：

| | 值 |
|---|---|
| `WORKSPACE` | `/var/jenkins_home/workspace/DISCOVERSE-GPU-Regression**@2**` |
| `JOB_NAME` | `DISCOVERSE-GPU-Regression`（**没有 @2**） |

于是 XML 写进不带 `@2` 的目录，Jenkins 去带 `@2` 的目录找 → **报告永远是空的，而构建显示 SUCCESS**。

> 📌 **通用规律：同一个东西有两个名字时，永远【从一个推导出另一个】，别两边各写一份硬编码。**

### 第 39 行：RENDER_BACKEND 桥接

```groovy
        RENDER_BACKEND = "${params.RENDER_BACKEND}"
```

⚠️ **看起来像废话（自己赋值给自己），其实是必需的。**

| 名字 | 是什么 | shell 里能读到吗 |
|---|---|---|
| `params.RENDER_BACKEND` | Groovy 对象的属性 | ❌ **不能** |
| `RENDER_BACKEND`（environment 里的） | **环境变量** | ✅ 能 |

**不写这行的后果**（§5.3.1 实测）：

```
+ echo === 后端  / 镜像 discoverse:test ===      ← 空
+ [  = egl ]                                      ← [ "" = egl ] 恒假
+ echo ℹ️ CPU 软渲染路径                          ← 选了 egl 却走 osmesa，全绿
```

📌 **这个 bug 静默** —— 不报错，只是永远走 else 分支。

### 第 42 行：TEST_IMAGE 联动

```groovy
        TEST_IMAGE = "${params.RENDER_BACKEND == 'egl' ? 'discoverse:test-gpu' : 'discoverse:test'}"
```

三元运算符：参数是 `egl` → 用 GPU 镜像；否则 → 用普通镜像。

⭐ **这一行让「选后端」自动变成「换镜像」** —— 用户只需选一次，不用同时记得改镜像名。

**实测证据**（构建 #8 vs #9）：

```
#8 (egl):    libEGL  : 4      ← discoverse:test-gpu
#9 (osmesa): libEGL  : 0      ← discoverse:test
```

## 第 45-50 行：`options` 块

```groovy
    options {
        disableConcurrentBuilds()
        timeout(time: 30, unit: 'MINUTES')
        timestamps()
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }
```

| 行 | 作用 |
|---|---|
| `disableConcurrentBuilds()` | ⭐ **同一时刻只跑一个构建** → 从根上不产生 `@2` workspace |
| `timeout(time: 30, unit: 'MINUTES')` | 超过 30 分钟自动中止（防死循环挂一夜） |
| `timestamps()` | ⭐ **每行日志前加时间戳** → 就是日志里 `15:12:43` 那列 |
| `buildDiscarder(logRotator(numToKeepStr: '20'))` | 只保留最近 20 次构建记录，防磁盘塞满 |

📌 **`timeout` 是 CI 的标配** —— MuJoCo 最常见的失败模式是**死循环而非抛异常**（你 `pyproject.toml` 里那个 `timeout = 60` 是同一个思路，只是作用在单个用例上）。

## 第 52 行：`stages {`

```groovy
    stages {
```

所有阶段的容器。⚠️ **必须有，且至少含一个 `stage`。**

📌 Jenkins 会把每个 `stage` 画成流程图上的一个方块（Pipeline Overview 页面）。**分 stage 不只是好看 —— 失败时你一眼看出卡在哪一步。**

---

## 第 54-73 行：stage「环境自检」

```groovy
        stage('环境自检') {
            steps {
                sh '''
```

- `stage('环境自检')` — 括号里是显示名，可以用中文
- `steps { }` — 这个 stage 要执行的步骤
- `sh '''` — 执行 shell 脚本；`'''` 是多行单引号（**不插值，交给 shell**）

### 第 57-59 行

```bash
                    echo "=== Jenkins 侧（容器内，只有 git/docker/java）==="
                    whoami; pwd
                    docker --version
```

| 命令 | 作用 | 实测输出 |
|---|---|---|
| `echo "..."` | 打印 | `=== Jenkins 侧... ===` |
| `whoami` | 当前用户 | `root` |
| `pwd` | 当前目录 | `/var/jenkins_home/workspace/DISCOVERSE-GPU-Regression` |
| `docker --version` | Docker 版本 | `Docker version 29.1.5` |

📌 **`;` 是 shell 的命令分隔符** —— `whoami; pwd` 等于分两行写。

### 第 65-70 行：镜像存在性检查

```bash
                    docker image inspect ${TEST_IMAGE} > /dev/null \
                      && echo "✅ ${TEST_IMAGE} 存在" \
                      || { echo "❌ 镜像不存在。构建命令（项目根目录执行）:"; \
                           echo "   docker build -f ..."; \
                           exit 1; }
```

**逐个符号拆解**：

| 符号 | 含义 |
|---|---|
| `docker image inspect X` | 查看镜像 X 的详情；**镜像不存在时退出码非 0** |
| `> /dev/null` | 把标准输出丢弃（我们只要退出码，不要那一大坨 JSON） |
| `\`（行尾） | **续行符** —— 告诉 shell「这行没写完」 |
| `A && B` | A 成功（退出码 0）才执行 B |
| `A \|\| B` | A 失败（退出码非 0）才执行 B |
| `{ ...; }` | 把多条命令组成一组（⚠️ **最后一条后面的 `;` 不能省**） |
| `exit 1` | 以退出码 1 结束脚本 → **Jenkins 判定这个 stage 失败** |

⭐ **这三行连起来读**：

> 「镜像在 → 打印存在；镜像不在 → 打印构建命令并**让构建失败**」

📌 **`exit 1` 是关键**。没有它，脚本会继续往下跑，后面的 stage 会以更难懂的方式失败（比如「找不到 pytest」）。**在最早的地方失败，用最清楚的话说明原因** —— 这就是「快速失败」（fail fast）。

⚠️ **注意错误提示里给了完整的修复命令**。好的报错不只说「错了」，还说「怎么修」。

---

## 第 75-99 行：stage「渲染后端自检」

### 第 78 行：条件判断

```bash
                    if [ "${RENDER_BACKEND}" = "egl" ]; then
```

| 部分 | 含义 |
|---|---|
| `if ...; then ... else ... fi` | shell 的条件语句（⚠️ **结尾是 `fi`，不是 `endif`**） |
| `[ A = B ]` | 字符串相等判断（`[` 其实是个命令，所以**两边必须有空格**） |
| `"${RENDER_BACKEND}"` | ⚠️ **必须加双引号** |

⭐ **为什么变量要加引号**：如果变量是空的，`[ ${X} = egl ]` 会变成 `[ = egl ]` —— **语法错误**。加了引号变成 `[ "" = egl ]` —— **合法，且结果为假**。

📌 **这正是 §5.3.1 那个 bug 没有崩、而是静默走 else 的原因。** 引号救了它，但也藏了它。

### 第 82-92 行：EGL vendor 断言

```bash
                        docker run --rm --gpus all -e MUJOCO_GL=egl ${TEST_IMAGE} python -c "
from OpenGL import EGL
import ctypes, os, sys
d = EGL.eglGetDisplay(EGL.EGL_DEFAULT_DISPLAY)
maj, minor = EGL.EGLint(), EGL.EGLint()
EGL.eglInitialize(d, ctypes.byref(maj), ctypes.byref(minor))
v = EGL.eglQueryString(d, EGL.EGL_VENDOR)
print('EGL', maj.value, '.', minor.value, 'vendor =', v)
sys.stdout.flush()
os._exit(0 if v and b'NVIDIA' in v else 1)
"
```

**docker 部分**：

| 参数 | 作用 |
|---|---|
| `docker run` | 起一个新容器 |
| `--rm` | **容器退出后自动删除**（不加会堆积一堆 Exited 容器） |
| `--gpus all` | 把所有 GPU 透传进容器 |
| `-e MUJOCO_GL=egl` | 设环境变量（**覆盖镜像里 `ENV` 的默认值**） |
| `${TEST_IMAGE}` | 用哪个镜像 |
| `python -c "..."` | 执行后面这段 Python 代码 |

**Python 部分逐行**：

| 行 | 作用 |
|---|---|
| `from OpenGL import EGL` | 导入 PyOpenGL 的 EGL 模块 |
| `d = EGL.eglGetDisplay(EGL.EGL_DEFAULT_DISPLAY)` | 拿到默认显示设备的句柄 |
| `maj, minor = EGL.EGLint(), EGL.EGLint()` | 创建两个 C 整型变量，**用来接收版本号** |
| `EGL.eglInitialize(d, ctypes.byref(maj), ctypes.byref(minor))` | ⚠️ **初始化** —— 少了这行下一行必报 `EGL_NOT_INITIALIZED` |
| `v = EGL.eglQueryString(d, EGL.EGL_VENDOR)` | 查询厂商名 |
| `print(...)` | 打印，实测 `EGL 1 . 5 vendor = b'NVIDIA'` |
| `sys.stdout.flush()` | ⚠️ **强制把输出刷出去** —— 因为下一行 `os._exit` 会跳过正常清理 |
| `os._exit(0 if ... else 1)` | ⭐ **断言**：是 NVIDIA 退出 0，否则退出 1（→ stage 失败） |

⭐ **`ctypes.byref(maj)` 是什么**：EGL 是 C 语言库，`eglInitialize` 要求传**指针**（让它把版本号写进去）。`byref` 就是「取地址」，相当于 C 里的 `&maj`。

⭐ **`os._exit()` vs `sys.exit()`**：

| | 行为 |
|---|---|
| `sys.exit()` | 正常退出，**执行析构函数** → ⚠️ MuJoCo 的 EGL 析构会抛 `EGLError` 噪声 |
| `os._exit()` | **立即退出**，跳过一切清理 → ✅ 干净 |

📌 **`b'NVIDIA'` 前面的 `b` 表示字节串**（不是普通字符串）。C 库返回的是字节，所以要用 `b'...'` 比较。

⚠️ **`v and b'NVIDIA' in v`** —— 先判断 `v` 非空（防 `None`），再判断包含关系。**顺序不能反**，否则 `v` 是 `None` 时 `in` 会抛异常。

---

## 第 101-123 行：stage「代码状态」

### 第 114-120 行

```bash
                    docker run --rm --entrypoint sh \
                      -v ${REPO_ON_HOST}:/repo -w /repo alpine/git:latest \
                      -c 'git config --global --add safe.directory /repo;
                          echo "commit : $(git log -1 --format="%h %s")";
                          echo "branch : $(git rev-parse --abbrev-ref HEAD)";
                          echo "=== 未提交改动（非空即说明测的是脏代码）===";
                          git status --short'
```

| 参数 | 作用 |
|---|---|
| `--entrypoint sh` | ⚠️ **覆盖镜像的入口程序** |
| `-v ${REPO_ON_HOST}:/repo` | 把宿主机的项目目录挂到容器里的 `/repo` |
| `-w /repo` | 容器启动后的工作目录（相当于先 `cd /repo`） |
| `alpine/git:latest` | 一个只有 git 的极小镜像 |
| `-c '...'` | 交给 `sh` 执行的命令串 |

⭐ **为什么必须 `--entrypoint sh`**：

`alpine/git` 镜像的 `ENTRYPOINT` 就是 `git`。所以：

```bash
docker run alpine/git sh -c 'xxx'
# 实际执行： git sh -c 'xxx'
# 报错：     git: 'sh' is not a git command
```

覆盖后才变成正常的 `sh -c 'xxx'`。（这是我实测撞到的。）

⭐ **为什么要 `safe.directory`**：

git 2.35.2+ 有个安全机制：**拒绝操作「属主不是当前用户」的仓库**（防止别人在共享目录放恶意 `.git/config`）。

容器里是 root，而宿主机文件属于 `ubuntu22` → git 拒绝 → 报 `dubious ownership`。

`git config --global --add safe.directory /repo` 就是告诉 git「这个目录我信得过」。

**git 子命令**：

| 命令 | 作用 | 实测输出 |
|---|---|---|
| `git log -1 --format="%h %s"` | 最近 1 次提交的**短哈希**和**标题** | `6263899 ci: README 徽章...` |
| `git rev-parse --abbrev-ref HEAD` | 当前分支名 | `feat/test-infra` |
| `git status --short` | 精简格式的状态 | `?? docs/...` |

**`git status --short` 的记号**：

| 记号 | 含义 |
|---|---|
| `??` | 未跟踪（新文件，git 完全不认识） |
| ` M` | 已修改，**未暂存** |
| `M ` | 已修改，**已暂存** |
| `A ` | 新增且已暂存 |
| `D ` | 已删除 |

⚠️ **构建 #10 里出现的 ` M tests/unit/test_smoke.py`** —— 那就是你加的故意失败用例，**流水线当场把「测的是脏代码」喊了出来**。

📌 **`$(...)` 是命令替换** —— 先执行括号里的命令，把输出嵌进当前位置。

---

## 第 125-138 行：stage「GPU 可见性」

### 第 129-130 行

```bash
                    docker run --rm --gpus all ${TEST_IMAGE} \
                      nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
```

| 部分 | 作用 |
|---|---|
| `nvidia-smi` | NVIDIA 官方的 GPU 查询工具 |
| `--query-gpu=name,memory.total` | 只要这两个字段（不要默认那一大张表） |
| `--format=csv,noheader` | CSV 格式，**不要表头** |

实测输出：`NVIDIA GeForce RTX 4060 Laptop GPU, 8188 MiB`

⚠️ **这条必须在容器里跑** —— Jenkins 容器里没装 `nvidia-smi`（你踩过）。

### 第 133-135 行：渲染库清点

```bash
                    docker run --rm ${TEST_IMAGE} sh -c \
                      'echo "libEGL  : $(ls /usr/lib/x86_64-linux-gnu/ | grep -ci egl)"; \
                       echo "libOSMesa: $(ls /usr/lib/x86_64-linux-gnu/ | grep -ci osmesa)"'
```

| 部分 | 作用 |
|---|---|
| `ls /usr/lib/x86_64-linux-gnu/` | 列出系统库目录 |
| `\|` | 管道：把左边的输出喂给右边 |
| `grep -ci egl` | `-c` 只输出**计数**，`-i` 忽略大小写 |

⭐ **这两行是今天最有说服力的证据**：

| 构建 | 镜像 | libEGL | libOSMesa |
|---|---|---|---|
| #9 `osmesa` | `discoverse:test` | **0** | 4 |
| #8 `egl` | `discoverse:test-gpu` | **4** | 4 |

📌 **`0` 和 `4` 证明参数不只换了字符串，是真的换了镜像。**

---

## 第 140-158 行：stage「回归测试」

### 第 143 行

```bash
                    mkdir -p ${WS_IN_JENKINS}/test-results
```

- `mkdir -p` — 创建目录，`-p` 表示「已存在也不报错，且自动创建父目录」
- ⚠️ **用 `WS_IN_JENKINS`（容器路径）** —— 因为这是 Jenkins **自己**在创建目录

### 第 148-155 行：核心命令

```bash
                    docker run --rm --gpus all \
                      -e MUJOCO_GL=${RENDER_BACKEND} \
                      -v ${REPO_ON_HOST}:/repo \
                      -v ${WS_ON_HOST}/test-results:/out \
                      -w /repo \
                      ${TEST_IMAGE} \
                      pytest tests/ -q -p no:cacheprovider \
                             --junitxml=/out/results.xml
```

| 行 | 作用 |
|---|---|
| `-e MUJOCO_GL=${RENDER_BACKEND}` | 注入后端（**覆盖镜像 ENV 的 osmesa 默认值**） |
| `-v ${REPO_ON_HOST}:/repo` | 挂被测代码（⚠️ **宿主机路径**，⚠️ **不加 `:ro`**） |
| `-v ${WS_ON_HOST}/test-results:/out` | 挂报告输出目录（⚠️ **宿主机路径**） |
| `-w /repo` | 工作目录设为代码根 |
| `pytest tests/` | 只跑 tests 目录 |
| `-q` | quiet，精简输出 |
| `-p no:cacheprovider` | ⭐ **禁用 pytest 缓存插件** |
| `--junitxml=/out/results.xml` | ⭐ **输出 JUnit XML 格式报告** |

⭐ **`-p no:cacheprovider` 为什么要加**：

`-p no:X` 的意思是「禁用名为 X 的插件」。`cacheprovider` 是 pytest 内置的缓存插件，默认会在项目根写一个 `.pytest_cache/` 目录。

**实测对比**（我在一个空目录里跑同一个用例）：

```bash
docker run --rm -v $PWD:/w -w /w discoverse:test pytest -q -p no:cacheprovider test_x.py
ls -a   # →  . .. test_x.py                    ← 干净

docker run --rm -v $PWD:/w -w /w discoverse:test pytest -q test_x.py
ls -a   # →  . .. .pytest_cache test_x.py      ← 多了缓存目录
```

⚠️ **在 Jenkins 场景下这个目录是有害的**：容器里是 root，写出来的 `.pytest_cache/` **属主是 root**，而你是 `ubuntu22` —— 想删还得 `sudo`（你今天清 `@2` 目录时已经尝过这个滋味）。

📌 **本项目 `.gitignore:262` 已经忽略了 `.pytest_cache/`**（实测确认），所以它不会被误提交。但「不进 git」和「不该被创建」是两回事 —— **CI 里的容器不该往你的工作区拉屎**。

> ⭐ 这条和 §5.4 那个 `:ro` 的坑是**同一个主题**：本课直接挂载工作区，所以要格外留意「容器会往被测代码目录里写什么」。

⭐ **两个 `-v` 都必须是宿主机路径** —— 这是 Step 2 那条铁律。

⚠️ **`:ro`（只读）不能加**：测试运行时会往 `models/mjcf/tmp/` 写临时 MJCF 文件。实测加了 `:ro` 会炸出 7 个 errors。

---

## 第 161-176 行：`post` 块

```groovy
    post {
        always { ... }
        success { ... }
        failure { ... }
    }
```

**`post` 的所有条件块**：

| 块 | 何时执行 |
|---|---|
| `always` | ⭐ **总是**（成功失败都跑） |
| `success` | 仅成功 |
| `failure` | 仅失败 |
| `unstable` | 测试失败但构建没崩（如 junit 标记为 unstable） |
| `changed` | 本次结果与上次**不同**时 |
| `aborted` | 被手动中止或超时 |

### 第 166 行：junit

```groovy
            junit testResults: 'test-results/*.xml', allowEmptyResults: true
```

| 参数 | 作用 |
|---|---|
| `junit` | JUnit 插件提供的步骤，**解析 XML 并生成 Tests 页面** |
| `testResults: 'test-results/*.xml'` | 去哪找报告（⚠️ **相对 `WORKSPACE`**） |
| `allowEmptyResults: true` | ⭐ **找不到报告时只警告，不抛异常** |

⚠️ **为什么必须放在 `always` 里**：

**测试失败时，pipeline 会中断** —— 但报告必须照样收集。**失败的时刻才是最需要报告的时刻。**

构建 #10 的实证：

```
1 failed, 122 passed, ...
Recording test results          ← ⭐ FAILURE 的构建里照样收了
Finished: FAILURE
```

⚠️ **`allowEmptyResults: true` 的理由**（§5.3.4）：写 `false` 时，如果前面 stage 就失败了（没产出 XML），post 会**再抛一个异常**，控制台最下面变成一堆 Java 栈，**真正的错因被埋在几十行以上**。

> **`post` 的职责是收集，不是制造新的失败。**

### 第 167 行：archiveArtifacts

```groovy
            archiveArtifacts artifacts: 'test-results/*.xml', allowEmptyArchive: true
```

把文件**存档**到 Jenkins（构建页面可下载）。

📌 **`junit` 和 `archiveArtifacts` 的区别**：

| | junit | archiveArtifacts |
|---|---|---|
| 做什么 | **解析** XML → 生成 Tests 页面、趋势图 | **原样保存**文件 |
| 结果 | 结构化的测试列表 | 一个可下载的附件 |

### 第 171 行：success

```groovy
            echo "✅ 通过（后端 ${params.RENDER_BACKEND}）。注意：当前无任何用例真正需要 GPU，两档预期同为 122 passed"
```

⚠️ **这里用双引号** —— 因为要插值 `${params.RENDER_BACKEND}`（Groovy 层展开，不是 shell）。

📌 **文案刻意提醒「无用例真正需要 GPU」** —— 防止半年后自己或别人误以为这条流水线在跑 GPU 测试。**让文档待在它被读到的地方。**

---

# 第三部分：命令行逐条解析

## 3.1 环境准备

```bash
source scripts/dev/env.sh
```

| 部分 | 含义 |
|---|---|
| `source`（或 `.`） | ⭐ **在当前 shell 里执行**，而不是开子进程 |
| `scripts/dev/env.sh` | 脚本路径 |

⭐ **为什么必须用 `source` 而不是 `bash xxx.sh`**：

```
bash env.sh   → 开一个子进程 → 子进程里设了变量 → 子进程退出 → 变量没了 ❌
source env.sh → 在当前 shell 执行 → 变量留在当前 shell ✅
```

**它做三件事**：设 `$PY`、设 `MUJOCO_GL=osmesa`、清掉 ROS 注入的 `PYTHONPATH`。

⚠️ **只在当前终端窗口有效** —— 新开终端要重来。你那次 `-m: command not found` 就是因为新窗口没 source，`$PY` 是空的，命令变成了 `-m pytest ...`。

## 3.2 pytest

```bash
$PY -m pytest tests/ -q | tail -1
```

| 部分 | 含义 |
|---|---|
| `$PY` | 环境变量，指向 conda 里的 python |
| `-m pytest` | ⭐ **以模块方式运行** pytest |
| `tests/` | 只测这个目录 |
| `-q` | quiet |
| `\| tail -1` | 只显示最后一行 |

⭐ **`python -m pytest` vs 直接 `pytest`**：

| | 区别 |
|---|---|
| `pytest` | 用 PATH 里找到的那个（**可能是别的环境的**） |
| `python -m pytest` | ✅ **用这个 python 对应的 pytest**，且把当前目录加进 `sys.path` |

📌 **CI 里一律用 `python -m pytest`** —— 避免「装了两个 python，跑错了那个」。

## 3.3 Docker 构建

```bash
docker build -f discoverse/docker/Dockerfile.test.gpu -t discoverse:test-gpu .
```

| 部分 | 含义 |
|---|---|
| `docker build` | 构建镜像 |
| `-f <路径>` | 指定 Dockerfile（不加则用当前目录的 `Dockerfile`） |
| `-t discoverse:test-gpu` | 打标签，格式 `名字:标签` |
| `.` | ⭐ **构建上下文** —— 最后那个点 |

⭐ **「构建上下文」是什么**：

`.` 表示「把当前目录的内容发给 Docker 守护进程」。Dockerfile 里的 `COPY . /workspace/` 复制的就是这个上下文里的东西。

⚠️ **所以 `docker build` 必须在项目根目录跑** —— 在别处跑，上下文就错了。（`.dockerignore` 控制哪些文件被排除。）

## 3.4 Docker 运行

```bash
docker run --rm --gpus all -e MUJOCO_GL=egl discoverse:test-gpu pytest tests/ -q
```

| 参数 | 含义 |
|---|---|
| `--rm` | 退出后自动删除容器 |
| `--gpus all` | 透传全部 GPU |
| `-e K=V` | 设环境变量 |
| `-v A:B` | ⭐ 挂载：**宿主机的 A** → **容器里的 B** |
| `-w DIR` | 容器内工作目录 |
| `--entrypoint X` | 覆盖镜像入口程序 |
| 镜像名后面的 | 覆盖镜像的默认 `CMD` |

## 3.5 docker exec

```bash
docker exec jenkins_server sh -c 'ls /var/jenkins_home'
```

⭐ **`run` 和 `exec` 的区别**：

| | 作用 |
|---|---|
| `docker run` | **新建**一个容器并运行 |
| `docker exec` | 在**已在运行**的容器里执行命令 |

📌 `jenkins_server` 已经跑了 6 个月，所以查它内部要用 `exec`。

## 3.6 git 命令

```bash
git checkout tests/unit/test_smoke.py
```

⚠️ **把文件恢复成 git 里的样子，丢弃未提交改动 —— 不可逆。**

```bash
git add A B C          # 把改动放进暂存区（staging area）
git status --short     # 查看状态
git commit -m "..."    # 把暂存区的东西提交
git reset              # 清空暂存区（不动文件内容）
```

📌 **git 的三个区**：

```
工作区（你的文件） --git add--> 暂存区 --git commit--> 仓库
```

---

# 第四部分：Jenkins 构建日志逐行解析

以构建 #10 的真实日志为例。

## 4.1 开头部分

```
Started by user zzy
[Pipeline] Start of Pipeline
[Pipeline] node
Running on Jenkins in /var/jenkins_home/workspace/DISCOVERSE-GPU-Regression
[Pipeline] {
```

| 行 | 含义 |
|---|---|
| `Started by user zzy` | 触发方式：**用户手动**（其他可能：定时、webhook、上游 job） |
| `[Pipeline] Start of Pipeline` | pipeline 引擎启动 |
| `[Pipeline] node` | 正在分配执行节点（对应 `agent any`） |
| `Running on Jenkins in <path>` | ⭐ **分到了哪个节点 + workspace 路径** |
| `[Pipeline] {` | 进入一个代码块 |

⚠️ **`[Pipeline] xxx` 都是 Jenkins 自己打的**，不是你的脚本输出。它在告诉你「我正在执行 Jenkinsfile 的哪一部分」。

📌 **`Running on Jenkins in ...` 这行要盯住** —— 出现 `@2` 就说明有并发 workspace（你踩过的那个坑）。

## 4.2 包裹块

```
[Pipeline] withEnv
[Pipeline] {
[Pipeline] timeout
Timeout set to expire in 30 min
[Pipeline] {
[Pipeline] timestamps
[Pipeline] {
```

| 行 | 对应 Jenkinsfile 的 |
|---|---|
| `withEnv` | `environment { }` 块 |
| `timeout` + `Timeout set to expire in 30 min` | `options { timeout(...) }` |
| `timestamps` | `options { timestamps() }` |

📌 **这些是层层嵌套的「包裹器」** —— 每个 `[Pipeline] {` 都对应后面一个 `[Pipeline] }`。

## 4.3 stage 执行

```
[Pipeline] stage
[Pipeline] { (环境自检)
[Pipeline] sh
15:12:43  + echo === Jenkins 侧（容器内，只有 git/docker/java）===
15:12:43  === Jenkins 侧（容器内，只有 git/docker/java）===
```

⭐ **注意这两行的区别**（初学最困惑的地方）：

| 行 | 是什么 |
|---|---|
| `+ echo === Jenkins 侧 ===` | ⭐ **shell 的「命令回显」** —— 即将执行的命令 |
| `=== Jenkins 侧 ===` | ⭐ **命令的实际输出** |

📌 **`+` 开头的行是 shell 在说「我要执行这条了」**（因为 Jenkins 的 `sh` 默认带 `set -x`）。**不带 `+` 的才是真正的输出。**

⚠️ **`15:12:43` 那列是 `timestamps()` 加的**，不是脚本的一部分。

## 4.4 变量已展开

```
15:12:43  + echo === 后端 osmesa / 镜像 discoverse:test ===
```

📌 **回显里显示的是展开后的值** —— 你写的是 `${RENDER_BACKEND}`，回显显示 `osmesa`。

⭐ **这就是排查变量问题的最快方法**：#7 那次回显是 `=== 后端  / 镜像 ... ===`（后端后面空白），**一眼看出变量没传进来**。

## 4.5 条件分支

```
15:12:43  + [ osmesa = egl ]
15:12:43  + echo ℹ️ CPU 软渲染路径，与 GitHub Actions 一致
```

回显把判断本身也打出来了：`[ osmesa = egl ]` → 假 → 走 else。

⚠️ **#7 那次是 `+ [  = egl ]`** —— 中间是空的，说明变量为空。**这一行就是那个 bug 的铁证。**

## 4.6 stage 结束与跳过

```
[Pipeline] }
[Pipeline] // stage
```

`// stage` 表示「stage 块到此结束」（`//` 在这里是 Jenkins 的标记，不是注释）。

**失败后的跳过**：

```
[Pipeline] { (GPU 可见性)
Stage "GPU 可见性" skipped due to earlier failure(s)
```

📌 **默认行为：一个 stage 失败，后面的全部跳过。** 想改可以用 `post` 或 `catchError`。

## 4.7 post 阶段

```
[Pipeline] { (Declarative: Post Actions)
[Pipeline] junit
15:12:55  Recording test results
15:12:55  [Checks API] No suitable checks publisher found.
[Pipeline] archiveArtifacts
15:12:55  Archiving artifacts
```

| 行 | 含义 |
|---|---|
| `Declarative: Post Actions` | 进入 `post {}` 块 |
| `Recording test results` | ⭐ **junit 正在解析 XML** |
| `[Checks API] No suitable checks publisher found` | ⚠️ **无害** —— GitHub Checks 集成没配（本地 Jenkins 用不上） |
| `Archiving artifacts` | archiveArtifacts 在存档 |

⚠️ **#7 那次这里是**：

```
No test report files were found. Configuration error?
'test-results/*.xml' doesn't match anything: 'test-results' exists but not 'test-results/*.xml'
```

📌 **第二行信息量极大**：「目录存在，但里面没有 xml」→ 说明**路径对了一半** → 正是 `@2` 错位的症状。

## 4.8 结尾

```
[Pipeline] End of Pipeline
ERROR: script returned exit code 1
Finished: FAILURE
```

| 行 | 含义 |
|---|---|
| `ERROR: script returned exit code 1` | 某个 `sh` 返回了非 0 |
| `Finished: FAILURE` | ⭐ **最终状态** |

**Jenkins 的构建状态**：

| 状态 | 颜色 | 含义 |
|---|---|---|
| `SUCCESS` | 🔵/🟢 | 全部成功 |
| `FAILURE` | 🔴 | 有步骤失败 |
| `UNSTABLE` | 🟡 | 构建成功但测试有失败 |
| `ABORTED` | ⚪ | 被中止/超时 |

---

# 第五部分：pytest 输出符号表

```
....x............................xxxx.....x............................. [ 50%]
..................xx.xx................F..............xxxx.ssss......x   [100%]
```

**每个字符代表一个用例**：

| 符号 | 含义 |
|---|---|
| `.` | passed（通过） |
| `F` | **failed**（失败） |
| `E` | **error**（用例外崩溃，如 fixture 报错） |
| `s` | skipped（跳过） |
| `x` | **xfail** —— 预期失败，且**确实失败了** ✅ 符合预期 |
| `X` | **xpass** —— 预期失败，**却通过了** ⚠️ 值得警惕 |

⭐ **`x` 是本项目的特色** —— 你用 `xfail` 把已知缺陷「登记在案」：**测试不报红，但缺陷不会被遗忘**。

## 结尾统计行

```
1 failed, 122 passed, 4 skipped, 45 deselected, 15 xfailed in 2.86s
```

| 字段 | 含义 |
|---|---|
| `1 failed` | 失败 1 个 |
| `122 passed` | 通过 122 个 |
| `4 skipped` | 跳过 4 个 |
| `45 deselected` | ⭐ **被筛掉，从未运行** |
| `15 xfailed` | 预期失败 15 个 |

⭐ **`deselected` 来自 `pyproject.toml` 的 `addopts = "... -m 'not flake'"`** —— 那 45 个 flake 采样用例默认不跑。

## ⚠️ 为什么 Jenkins 显示 141 而不是 122

```
122 passed + 4 skipped + 15 xfailed = 141   ← Jenkins Tests 页面的 tests
        4 skipped + 15 xfailed = 19         ← Jenkins 显示的 skipped
```

**两处信息损失**：

1. **JUnit 格式没有 xfail 概念**（它是 Java 世界的标准，比 pytest 老）→ xfail 只能塞进 `skipped`
2. **45 个 deselected 根本不进 XML** → 它们在收集阶段就被筛掉，从未运行

📌 **这不是 bug，是格式转换的固有损失。** 心里有数即可，别去「修」。

> ⭐ **这正是 Day 13-14「结构化结果契约」要解决的问题**：当你需要机器可读的结果时，**通用格式会丢掉领域特有的信息**。JUnit 丢了 xfail，而 xfail 恰恰是你这个项目最重要的状态之一。

---

## 附：今天五个「静默失败」速查

| # | 症状 | 根因 | 修法 |
|---|---|---|---|
| 1 | `[  = egl ]` 恒假，选 egl 跑 osmesa | `params.X` 不是环境变量 | `environment { RENDER_BACKEND = "${params.RENDER_BACKEND}" }` |
| 2 | `cd: can't cd to ...` | Jenkins 容器没挂项目目录 | 放进兄弟容器 `docker run -v` |
| 3 | `nvidia-smi: not found` | Jenkins 容器没装它 | 在兄弟容器里跑 |
| 4 | junit 抛 Java 栈盖住真错因 | `allowEmptyResults: false` | 改 `true` |
| 5 | ⭐ **SUCCESS + 122 passed + 空报告** | `@2` workspace 路径错位 | 从 `WORKSPACE` 推导，+ `disableConcurrentBuilds()` |

📌 **五条的共性：声明了但行为不符，且失败时静默。** 分别来自 Jenkins 变量作用域、Docker 挂载、容器镜像内容、Jenkins 插件参数、Jenkins 并发机制 —— **没有一条是项目代码的锅**。

> **基础设施的默认行为倾向于「让你继续跑下去」，而不是「让你知道出事了」。**
> **对策只有一个：把关键假设写成断言。**
