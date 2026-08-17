# Day 12 — Jenkins 辅线：当 CI 跑在你自己的机器上

> 上接 [day10-11-github-actions.md](day10-11-github-actions.md)
> 本课产出：`Jenkinsfile`（GPU 回归）、一个能手动触发的 Jenkins Pipeline job、一条「云端 / 本地」分工的明确论证
> 预计耗时：约 4 小时

---

## 今天到底在干嘛（先建立直觉）

Day 10-11 你已经有一条 5-job 的 GitHub Actions 流水线了，全绿。

那**为什么还要再搭一套 Jenkins**？

这是今天最重要的问题。如果答不上来，今天就是在做一件毫无意义的重复劳动 —— 而且面试官一定会问。

### 先说错误答案

❌ *「因为简历上写了 Jenkins。」*
❌ *「因为 Jenkins 是业界标准。」*
❌ *「多一条流水线更保险。」*

最后一条尤其危险。**两条一模一样的流水线不是双保险，是双倍维护成本 + 双倍 flake 概率。**

### 真正的答案：它们跑在不同的硬件上

| | GitHub Actions | Jenkins（本机） |
|---|---|---|
| 机器 | 微软云上的免费 runner | **你桌上这台** |
| GPU | ❌ **没有** | ✅ **RTX 4060** |
| 每次环境 | 全新虚拟机（干净） | 你的机器（脏，但**真实**） |
| 时长限制 | 单 job 6 小时，每月 2000 分钟 | **只受电费限制** |
| 谁能看到结果 | 全世界（公开仓库） | 只有你 |
| 数据 | 只能放公开的 | **可以放私有数据集** |

📌 **最关键的一行是 GPU 那行。**

GitHub 的免费 runner **物理上就没有显卡**。而这个项目 —— DISCOVERSE —— 核心卖点之一是 3D Gaussian Splatting 渲染，那是**必须有 GPU 才能跑的东西**。

所以分工是天然的：

> **轻量的、跟硬件无关的测试 → 云端（GitHub Actions，每次 push 都跑）**
> **重型的、需要 GPU 的测试 → 本地（Jenkins，夜里跑）**

这就叫**差异化 CI 策略**。它不是「两条流水线」，是**一条流水线的两个层次**。

### ⚠️ 但今天你会发现一个尴尬的事实

先剧透（细节见 Step 4）：**Day 8-9 做的那个 `discoverse:test` 镜像，根本没法用 GPU 渲染。**

它是个 CPU + osmesa 的镜像 —— 当时就是为了 GitHub Actions 特意那么做的。

📌 **这不是失败，这正是今天最有价值的发现。** 你会亲眼看到「我有 GPU」和「我的测试能用上 GPU」之间隔着多远。

**所以今天多出一节 Step 4.5**：按企业做法把渲染后端从**写死**改成**运行时可选**（`osmesa` / `egl` / `glfw`），并做一个带 EGL 的 GPU 镜像。**实测 EGL 比 osmesa 快 27 倍**（1561 vs 57 FPS）。

⚠️ **但请提前记住一句**：**打通「GPU 能用」不等于「有测试需要 GPU」。** 今天做完，后者仍然是零 —— 而**诚实地区分这两件事，是今天最难的部分**，比写 Dockerfile 难得多。

---

## ⚠️ 开课前必读：计划文档的 Jenkins 部分照抄，一行都跑不起来

老规矩。我把计划文档 §Day 12 的每一条都在本机实跑核实过。

**结论：那段 Jenkinsfile 照抄的话，会在第 1 个 stage 就失败，而且后面每个 stage 都有独立的坑。**

| 计划文档写的 | 实测结果 | 后果 |
|---|---|---|
| `git url: 'git@github.com:...'`（SSH） | ❌ Jenkins 容器里**没有任何 SSH key** | Checkout 直接失败 |
| `conda activate discoverse` | ❌ Jenkins 容器里**连 python3 都没有**，更没有 conda | 每个 sh 步骤都炸 |
| `agent { docker { ... } }` | ❌ **`docker-workflow` 插件没装**（89 个插件里没有） | Pipeline 语法直接报错 |
| `MUJOCO_GL = 'glfw'` | ❌ Jenkins 里**没有 DISPLAY**，glfw 必崩 | 与 Day 8-9 撞过的是同一个坑 |
| `pytest tests/simulation` | ⚠️ 只有 5 个用例 | 又是 Day 10-11 那个「5 passed 假绿灯」 |
| `junit 'test-results/*.xml'` | ⚠️ 路径对，但**没人生成这个文件** | 「空报告」，Jenkins 会警告 |
| 触发器 `0 3 * * *` 每天凌晨 3 点 | ⚠️ **你的机器凌晨 3 点大概率是关着的** | job 静默不跑，你以为在跑 |
| `git branch: 'feat/test-infra'` + 克隆 | ⚠️ 实测 **8 分钟还没克隆完**（仓库 308 MB） | 不是错，但慢到没法用 |

**再说一次**：这不是计划文档写得差，它写于项目之外。**具体环境长什么样，只有实跑才知道。**

📌 今天的每一步，我都会告诉你**计划怎么写的、我实测到什么、所以应该怎么改**。

---

## Step 0｜先搞清楚你的 Jenkins 是什么形态（30 分钟，绝对别跳过）

### 0.1 一个关键事实：你的 Jenkins 跑在 Docker 里

大多数网上教程假设 Jenkins 是用 `apt install jenkins` 装的系统服务。**你的不是。**

先自己确认：

```bash
systemctl status jenkins
```

我这台机器的实测：

```
Unit jenkins.service could not be found.
```

❌ 没有系统服务。那它在哪？

```bash
docker ps
```

实测（节选）：

```
CONTAINER ID   IMAGE                 STATUS        PORTS                                              NAMES
09409de0d618   jenkins/jenkins:lts   Up 10 hours   0.0.0.0:8080->8080/tcp, 0.0.0.0:50000->50000/tcp   jenkins_server
e2e70a883f06   gitea/gitea:latest    Up 10 hours   0.0.0.0:3000->3000/tcp, 0.0.0.0:222->22/tcp        gitea_server
7390a792dcf4   portainer/portainer-ce:latest  Up 10 hours   0.0.0.0:9443->9443/tcp                    portainer
```

✅ **Jenkins 是一个名叫 `jenkins_server` 的容器**，端口 8080 映射到宿主机。

📌 **这个区别决定了今天的一切。** 因为它意味着：

> **Jenkins 看到的文件系统，和你终端里看到的文件系统，不是同一个。**

这句话现在可能没感觉。Step 2 会让你痛一次。

### 0.2 摸清容器里有什么

```bash
docker exec jenkins_server sh -c 'which git docker python3 java'
```

实测：

```
/usr/bin/git
/usr/bin/docker
/opt/java/openjdk/bin/java
```

⚠️ **注意 `python3` 没有输出** —— 说明容器里**没有 Python**。

单独确认一下：

```bash
docker exec jenkins_server sh -c 'python3 -V'
```

```
sh: 1: python3: not found
```

📌 **这一条直接判了计划文档里 `conda activate discoverse` 的死刑。** Jenkins 容器是个纯 Java 环境，它**没有也不该有** Python。

那测试怎么跑？答案在下一节 —— 它有 `docker`。

### 0.3 ⭐ 最关键的一条：它能指挥宿主机的 Docker

```bash
docker exec jenkins_server sh -c 'docker ps'
```

实测：

```
CONTAINER ID   IMAGE                 STATUS        NAMES
7390a792dcf4   portainer/portainer-ce:latest  Up 10 hours   portainer
09409de0d618   jenkins/jenkins:lts   Up 10 hours   jenkins_server
```

⚠️ **看清楚了：容器里执行 `docker ps`，结果里出现了它自己。**

这说明 Jenkins 容器不是在跑自己的 Docker，而是**在指挥宿主机的 Docker**。

原理看挂载就明白：

```bash
docker inspect jenkins_server --format '{{json .Mounts}}' | python3 -m json.tool
```

实测（三条挂载，每条都有用）：

```json
[
  { "Source": "/usr/bin/docker",        "Destination": "/usr/bin/docker" },
  { "Source": "/var/run/docker.sock",   "Destination": "/var/run/docker.sock" },
  { "Source": "/home/ubuntu22/robot_platform/jenkins_home",
    "Destination": "/var/jenkins_home" }
]
```

| 挂载 | 作用 |
|---|---|
| `/usr/bin/docker` | 把宿主机的 docker **命令**塞进容器 |
| `/var/run/docker.sock` | 把宿主机的 docker **控制通道**塞进容器 ⭐ |
| `jenkins_home` | Jenkins 的数据目录（job 配置、workspace） |

### 📖 补充知识：什么是 docker.sock，为什么这叫「DinD」

**`/var/run/docker.sock` 是一个 Unix socket** —— 你可以把它想成「Docker 引擎的电话号码」。

平时你敲 `docker run ...`，实际发生的是：

```
docker 命令（客户端）  --通过 docker.sock 打电话-->  dockerd（真正干活的守护进程）
```

**`docker` 命令本身什么都不干**，它只是个打电话的。真正创建容器的是 `dockerd`。

所以，只要谁能访问 `docker.sock`，谁就能指挥 Docker —— **哪怕它自己就在一个容器里**。

这就是 Jenkins 容器能开容器的原理：

```
你 --> jenkins_server 容器 --> docker.sock --> 宿主机 dockerd --> 开一个新容器
```

⚠️ **一个非常常见的误解，务必掰正**：

这种做法俗称 **DinD（Docker in Docker）**，但它其实是 **DooD（Docker outside of Docker，「兄弟容器」）**：

| | 真 DinD | **你的情况（DooD）** |
|---|---|---|
| 新容器归谁管 | 容器内部另一个 dockerd | **宿主机的 dockerd** |
| 新容器在哪 | 嵌套在 Jenkins 容器里 | **和 Jenkins 容器平级，是「兄弟」** |
| `docker ps` 能看见吗 | 看不见宿主机的 | ✅ **能看见宿主机全部** |

📌 **「兄弟容器」这个词请记牢，Step 2 那个坑的全部原因就在这四个字里。**

> **面试可用点**：被问「你怎么在 Jenkins 里跑 Docker」时，如果答「用 DinD」，追问一句「是真嵌套还是挂 socket」就露馅了。
> 正确答法：*「挂宿主机的 docker.sock，所以严格说是 DooD 不是 DinD —— 起出来的是兄弟容器不是子容器。这个区别很实际：**因为是兄弟，`-v` 的路径参数是被宿主机 dockerd 解析的，写容器内的路径会静默挂空目录。**」*

⚠️ **顺带说安全**：挂 `docker.sock` 等于**把宿主机 root 权限交给了 Jenkins**（能起特权容器挂载宿主机根目录）。生产环境这么干要谨慎。你这是本机学习环境，可以接受 —— 但**得知道自己在接受什么**。

### 0.4 确认 GPU 真的能穿透到容器

Day 8-9 测过一次，今天再确认（这是 Jenkins 存在的全部理由）：

```bash
docker run --rm --gpus all discoverse:test nvidia-smi
```

实测：

```
NVIDIA-SMI 580.95.05    Driver Version: 580.95.05    CUDA Version: 13.0
NVIDIA GeForce RTX 4060 Laptop GPU   ...   8188MiB
```

✅ GPU 在容器里可见。

### 0.5 本课基线数字

```bash
cd /home/ubuntu22/workspaces/airbot-play/DISCOVERSE
source scripts/dev/env.sh && $PY -m pytest tests/ -q
```

```
122 passed, 4 skipped, 45 deselected, 15 xfailed in 2.96s
```

📌 **今天的验收标准：Jenkins 里跑出来的数字，和这行一模一样。** 差一个都要查。

### 0.6 打开 Jenkins Web 界面

浏览器访问 http://localhost:8080

⚠️ 如果你用 `curl` 试，会看到 `403`：

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080
# 403
```

**这是正常的**，不是坏了 —— 403 说明 Jenkins 活着并要求登录。浏览器里正常输账号密码即可。

> 忘了密码？初始密码在 `docker exec jenkins_server cat /var/jenkins_home/secrets/initialAdminPassword`（若该文件已被删，说明早就初始化过了，得走 Jenkins 的密码重置流程）。

---

## Step 1｜第一个 Pipeline：先让它跑起来，别管测试（40 分钟）

**新手最容易犯的错：一上来就写完整的 Jenkinsfile，然后面对一堆错误不知道哪里坏了。**

我们反过来：先跑一个**三行的、必然成功的** pipeline，把「Jenkins 能执行东西」这件事确认掉。

### 1.1 建 job

1. 浏览器打开 http://localhost:8080
2. 左侧 **New Item**（新建任务）
3. 名称填 `DISCOVERSE-GPU-Regression`
4. 类型选 **Pipeline**（不是 Freestyle）→ OK
5. 拉到最下面 **Pipeline** 区域，Definition 保持 **Pipeline script**（先不用 SCM）
6. 脚本框里粘贴：

```groovy
pipeline {
    agent any
    stages {
        stage('Hello') {
            steps {
                sh 'echo "Jenkins 活着"'
                sh 'whoami'
                sh 'pwd'
                sh 'docker --version'
            }
        }
    }
}
```

7. **Save** → 左侧 **Build Now**

### 1.2 看输出

点左下角那次构建（`#1`）→ **Console Output**。

实测输出的关键几行：

```
+ echo Jenkins 活着
Jenkins 活着
+ whoami
root
+ pwd
/var/jenkins_home/workspace/DISCOVERSE-GPU-Regression
+ docker --version
Docker version ...
```

✅ 三件事一次确认：

| 输出 | 说明 |
|---|---|
| `root` | Jenkins **以 root 跑**（这个镜像的配置），后面不用操心权限 |
| `/var/jenkins_home/workspace/...` | ⭐ **workspace 路径，记住它，Step 2 要用** |
| `Docker version ...` | docker 命令可用 |

### 📖 补充知识：Jenkinsfile 的基本结构

刚才那段 Groovy，逐层拆开：

```groovy
pipeline {              // 声明式 pipeline 的外壳，固定写法
    agent any           // 在哪台机器上跑。any = 随便哪个可用执行器
    stages {            // 阶段列表（Jenkins 会画成流程图）
        stage('Hello') {    // 一个阶段，引号里是显示名
            steps {         // 这个阶段要执行的步骤
                sh 'echo hi'    // sh = 执行 shell 命令
            }
        }
    }
}
```

几个今天会用到的补充块：

| 块 | 作用 |
|---|---|
| `environment { }` | 定义环境变量，整个 pipeline 可见 |
| `post { }` | **不管成功失败都要做的收尾**（归档报告等） |
| `options { }` | pipeline 级选项（超时、日志轮转等） |
| `triggers { }` | 自动触发条件（定时等） |

📌 **`post` 块是重点。** 测试失败时 pipeline 会中断，但**测试报告必须照样收集** —— 否则失败时你反而看不到失败详情，这是最需要报告的时刻。

---

## Step 2｜⭐ 今天最重要的一课：路径陷阱（40 分钟）

**这一步我建议你亲手踩一遍坑，别直接看答案。** 它是「Jenkins 在容器里」这个前提带来的最反直觉的后果，也是今天唯一一个**会静默失败**的问题。

### 2.1 先做一个看起来天经地义的事

在 job 里把脚本换成：

```groovy
pipeline {
    agent any
    stages {
        stage('路径实验') {
            steps {
                sh '''
                    mkdir -p /var/jenkins_home/probe
                    echo HELLO_FROM_JENKINS > /var/jenkins_home/probe/marker.txt
                    echo "--- Jenkins 自己读: ---"
                    cat /var/jenkins_home/probe/marker.txt

                    echo "--- 起个兄弟容器读同一个文件: ---"
                    docker run --rm -v /var/jenkins_home/probe:/mnt alpine:latest cat /mnt/marker.txt
                '''
            }
        }
    }
}
```

**逻辑上这毫无问题**：写个文件，然后把那个目录挂进容器读出来。

### 2.2 实测结果

```
--- Jenkins 自己读: ---
HELLO_FROM_JENKINS
--- 起个兄弟容器读同一个文件: ---
cat: can't open '/mnt/marker.txt': No such file or directory
```

❌ **文件不见了。**

⚠️ 而且注意：**`docker run` 本身成功了，没有任何报错。** 它挂上了一个**空目录**，然后 `cat` 才失败。

📌 **如果你的脚本不是 `cat` 而是 `pytest`，你会看到「collected 0 items」——一个绿灯或一个莫名其妙的失败，而根本不会想到是路径问题。**

### 2.3 为什么

回到 §0.3 那四个字：**兄弟容器**。

`docker run -v A:B` 这条命令，是 Jenkins 容器**发给宿主机 dockerd** 的。所以 **`A` 这个路径是由宿主机解析的，不是由 Jenkins 容器解析的**。

而宿主机上：

- `/home/ubuntu22/robot_platform/jenkins_home` ← **真实存在**
- `/var/jenkins_home` ← **根本不存在**（那是容器内部的名字）

⚠️ **Docker 遇到 `-v` 的源路径不存在时，不报错，而是「帮你」创建一个空目录。**

于是宿主机上凭空多出个 `/var/jenkins_home/probe`，空的，挂进容器 → 空的。

我实测确认了这个副作用：

```bash
ls -la /var/jenkins_home
```

```
drwxr-xr-x  4 root root 4096 Aug 16 23:21 .
drwxr-xr-x  2 root root 4096 Aug 16 23:21 probe     ← 被凭空创建出来的空目录
```

⚠️ **宿主机上被悄悄拉了泡屎**，root 所有，还得 `sudo rm -rf` 才能清掉。

### 2.4 修法：`-v` 左边永远写宿主机路径

```groovy
sh '''
    docker run --rm \
      -v /home/ubuntu22/robot_platform/jenkins_home/probe:/mnt \
      alpine:latest cat /mnt/marker.txt
'''
```

实测：

```
HELLO_FROM_JENKINS
```

✅ 通了。

### 2.5 记住这条规则

> **在挂了 docker.sock 的 Jenkins 里，`-v` 的左边（源路径）永远是宿主机路径，右边（目标路径）才是容器路径。**
>
> **Jenkins 自己的 `sh` 步骤用容器路径（`/var/jenkins_home/...`），`docker run -v` 用宿主机路径（`/home/ubuntu22/robot_platform/jenkins_home/...`）—— 同一个目录，两个名字，看你在跟谁说话。**

为了后面不写错，在 Jenkinsfile 里把这两个名字**显式定义成变量**：

```groovy
environment {
    // 同一个目录的两个名字 —— 见 Step 2
    WS_IN_JENKINS = "/var/jenkins_home/workspace/DISCOVERSE-GPU-Regression"
    WS_ON_HOST    = "/home/ubuntu22/robot_platform/jenkins_home/workspace/DISCOVERSE-GPU-Regression"
}
```

📌 **这是今天最值钱的一条知识。** 它不在任何计划文档里，因为它只在「Jenkins 本身是容器」时才出现 —— 而这恰好是你的环境。

> **面试可用点**：*「Jenkins 挂 docker.sock 跑兄弟容器时，`-v` 的源路径是宿主机 dockerd 解析的。写容器内路径不会报错，Docker 会创建一个空目录挂上去 —— 测试于是 collect 到 0 个用例，看起来像通过。我踩过一次，之后把宿主机路径和容器路径在 environment 里定义成两个显式变量。」*

---

## Step 3｜代码从哪来：别在 Jenkins 里克隆（30 分钟）

### 3.1 计划文档的写法，以及它为什么不行

计划文档写的是：

```groovy
git branch: 'feat/test-infra',
    url: 'git@github.com:Cyberpunk-edgerunners/DISCOVERSE-learning.git'
```

**两个问题。**

**问题一：SSH 用不了。** 实测：

```bash
docker exec jenkins_server sh -c 'ls -la /root/.ssh; ls /var/jenkins_home/.ssh'
```

```
ls: cannot access '/root/.ssh': No such file or directory
ls: cannot access '/var/jenkins_home/.ssh': No such file or directory
```

❌ Jenkins 容器里**没有任何 SSH key**。`git@github.com:` 这种 SSH 地址必然认证失败。

**好消息**：仓库是公开的，HTTPS 免密可读。实测：

```bash
docker exec jenkins_server sh -c 'git ls-remote https://github.com/Cyberpunk-edgerunners/DISCOVERSE-learning.git HEAD'
```

```
8893a8c63de1b9ccf18efd68b1b1c1afca4e3a98        HEAD
```

✅ HTTPS 通。**所以 URL 要从 `git@github.com:` 改成 `https://github.com/`。**

**问题二（更致命）：这仓库克隆起来慢到没法用。**

```bash
git count-objects -vH | grep size-pack
```

```
size-pack: 308.34 MiB
```

我实测在 Jenkins 容器里跑 `git clone --depth 1`：**8 分钟后只下了 37 MB，仍未完成**，最后我手动中断了。

📌 **注意这里的对比**：GitHub Actions 克隆同一个仓库只要十几秒 —— 因为**微软的 runner 和 GitHub 在同一个数据中心**。而你家宽带到 GitHub 要跨太平洋。

⚠️ **这是「本地 CI」的一个真实代价，值得记进笔记**：本地 runner 省了云端额度、拿到了 GPU，但**丢掉了数据中心内网带宽**。

### 3.2 本课的选择：直接挂载本地仓库

既然代码就在这台机器上（`/home/ubuntu22/workspaces/airbot-play/DISCOVERSE`），**为什么要绕地球一圈再下回来？**

```groovy
sh '''
    docker run --rm -v /home/ubuntu22/workspaces/airbot-play/DISCOVERSE:/repo -w /repo \
      discoverse:test sh -c "ls tests/"
'''
```

实测：秒回。

### 3.3 ⚠️ 但必须诚实标注这个取舍

这不是免费的。**挂载本地仓库 = 测的是你工作区里的代码，包括没提交的改动。**

| | 挂载本地仓库（本课选择） | Jenkins 里克隆 |
|---|---|---|
| 速度 | ✅ 秒级 | ❌ 8 分钟+ |
| 测的是什么 | ⚠️ **工作区现状（含未提交改动）** | ✅ **git 里的确定版本** |
| 可复现 | ❌ 差 | ✅ 好 |
| 适合 | 本机快速回归 | 真正的夜间回归 |

📌 **CI 的核心价值之一是「在干净环境里跑」，挂载本地仓库恰恰削弱了这一点。** 必须承认。

**所以正确的定位是**：

> **今天做的 Jenkins job 是「本机 GPU 冒烟」，不是「纯净夜间回归」。**

想升级成后者，两条路（**今天不做，记进欠账**）：

1. **在宿主机上先 `git clone` 到一个专用目录**，Jenkins 只挂那个目录 —— 本地磁盘拷贝，秒级，且版本确定
2. **换成本地 Gitea**（你机器上 `gitea_server` 已经在跑，端口 3000）—— 局域网克隆，快且版本确定

⚠️ 另外为了不测到脏东西，pipeline 里**必须打印当前代码状态**，让每次构建自己说清楚测的是什么：

```groovy
sh '''
    cd /home/ubuntu22/workspaces/airbot-play/DISCOVERSE
    echo "commit: $(git log -1 --format=%h\\ %s)"
    echo "--- 未提交改动 ---"
    git status --short
'''
```

📌 **这行 `git status --short` 是这个方案的良心。** 它把「我测的可能是脏代码」这件事**每次构建都写在日志里**，而不是藏起来。

> 这正是 Day 10-11 那条教训的延续：**「决定不做」和「假装没看见」的分水岭，是有没有把代价量化并可见化。**

---

## Step 4｜⭐ 直面 GPU 的真相（40 分钟）

Jenkins 存在的全部理由是 GPU。现在验证这个理由到底成不成立。

### 4.1 GPU 确实能透进容器

```bash
docker run --rm --gpus all discoverse:test nvidia-smi --query-gpu=name --format=csv,noheader
```

实测：

```
NVIDIA GeForce RTX 4060 Laptop GPU
```

✅ 显卡在容器里可见。

### 4.2 但测试用得上它吗？动手试试 GPU 渲染

MuJoCo 用 GPU 渲染要走 **EGL** 后端（`MUJOCO_GL=egl`）。试：

```bash
docker run --rm --gpus all -e MUJOCO_GL=egl discoverse:test python -c "
import mujoco
m = mujoco.MjModel.from_xml_string('<mujoco><worldbody><body><geom size=\".1\"/></body></worldbody></mujoco>')
d = mujoco.MjData(m); r = mujoco.Renderer(m, 240, 320)
mujoco.mj_forward(m, d); r.update_scene(d)
print('EGL render OK', r.render().shape)
"
```

实测：

```
  File ".../mujoco/egl/egl_ext.py", line 27, in <module>
    from OpenGL import EGL
  File ".../OpenGL/raw/EGL/_types.py", line 87, in <module>
    raw_eglQueryString = _p.PLATFORM.EGL.eglQueryString
AttributeError: 'NoneType' object has no attribute 'eglQueryString'
```

❌ **崩了。**

查一下镜像里到底有没有 EGL 库：

```bash
docker run --rm discoverse:test sh -c 'ls /usr/lib/x86_64-linux-gnu/ | grep -iE "EGL|osmesa"'
```

实测：

```
libOSMesa.so
libOSMesa.so.6
libOSMesa.so.8
libOSMesa.so.8.0.0
```

⚠️ **一个 `libEGL` 都没有，只有 OSMesa。**

对照 CPU 路径（镜像默认 `MUJOCO_GL=osmesa`）：

```bash
docker run --rm discoverse:test python -c "
import mujoco, os
print('MUJOCO_GL =', os.environ.get('MUJOCO_GL'))
m = mujoco.MjModel.from_xml_string('<mujoco><worldbody><body><geom size=\".1\"/></body></worldbody></mujoco>')
d = mujoco.MjData(m); r = mujoco.Renderer(m, 240, 320)
mujoco.mj_forward(m, d); r.update_scene(d)
print('osmesa render OK', r.render().shape)
"
```

```
MUJOCO_GL = osmesa
osmesa render OK (240, 320, 3)
```

✅ CPU 渲染正常。

### 4.3 差距分五层，先量化

> **`--gpus all` 让显卡在容器里**可见**，但 `discoverse:test` 里没有任何 EGL 库，所以 MuJoCo **用不上**它。**

📌 **这不是失败。** 这是 Day 8-9 那个决策的**必然结果** —— 当时为了 GitHub Actions（无 GPU）特意做了个 CPU + osmesa 的瘦镜像，那个决策是对的。

| 层次 | 状态 |
|---|---|
| 宿主机有 GPU | ✅ RTX 4060 |
| nvidia-container-toolkit 装了 | ✅ `docker info` 里有 `nvidia` runtime |
| GPU 能透进容器 | ✅ `nvidia-smi` 在容器里有输出 |
| **镜像里有 EGL 库** | ❌ **没有** |
| **测试能用 GPU 渲染** | ❌ **不能** |
| **有需要 GPU 的测试吗** | ❌ **目前一个都没有** |

⚠️ **注意最后一行**：就算把 EGL 装上，**当前也没有测试会用到它** —— 122 个用例全是配置层和 CPU 仿真。

📌 **所以欠账的正确顺序是：先有需要 GPU 的测试，再有支持 GPU 的镜像。** 反过来做就是为了用显卡而用显卡。

**但第 4 层（镜像有没有 EGL）值得现在就打通** —— 因为它是**基础设施**，不是业务代码。基础设施可以先于需求存在，只要成本足够低。下一节就是量化这个成本。

---

## Step 4.5｜⭐ 按企业做法改造渲染后端（60 分钟）

### 4.5.1 先说清企业里的实际做法

上面 §4.2 的实测里，你已经见到硬编码 `ENV MUJOCO_GL=osmesa` 的问题了：**镜像被焊死在一个后端上**。

企业里怎么做？**一个镜像，三种后端，运行时选。**

| 后端 | 用在哪 | 特点 |
|---|---|---|
| `osmesa` | **CI（无 GPU）** | 纯 CPU 软渲染，慢但零依赖 |
| `egl` | **GPU 服务器 / 训练集群（无显示器）** | ⭐ **无头 + GPU 加速** |
| `glfw` | 开发者本机调试 | 要显示器，能开窗口看 |

📌 **`egl` 是企业环境的主力**，因为服务器**既没有显示器、又必须用 GPU** —— 这正是 `osmesa`（无 GPU）和 `glfw`（要显示器）都覆盖不到的格子。

⚠️ 而这恰好也是**你的 Jenkins 的处境**：跑在本机（有 GPU），但通过 Jenkins 执行（没有 DISPLAY）。

### 4.5.2 动手：给镜像装上 EGL

我实测过了，**代价比想象中小得多**。新建 `discoverse/docker/Dockerfile.test.gpu`：

```dockerfile
# ============================================================
# Dockerfile.test.gpu —— 在 Dockerfile.test 基础上加 EGL（GPU 无头渲染）
#
# 为什么单独一个文件而不是改原来的：
#   原镜像的目标运行环境是 GitHub Actions 免费 runner（无 GPU），
#   那里装 EGL 是纯浪费。两个用途，两个镜像。
#
# 构建：docker build -f discoverse/docker/Dockerfile.test.gpu -t discoverse:test-gpu .
# 运行：docker run --rm --gpus all -e MUJOCO_GL=egl discoverse:test-gpu pytest tests/ -q
# ============================================================
FROM discoverse:test

# ---- EGL 运行时库 ----
# libegl1 / libgles2: EGL 与 GLES 的 GLVND 派发库
# libglvnd0:          OpenGL Vendor Neutral Dispatch，负责在 Mesa/NVIDIA 之间选
RUN apt-get update && apt-get install -y --no-install-recommends \
    libegl1 \
    libgles2 \
    libglvnd0 \
    && rm -rf /var/lib/apt/lists/*

# ---- ⭐ 关键的一步：注册 NVIDIA 为 EGL vendor ----
# nvidia-container-toolkit 会把 libEGL_nvidia.so 注入容器，
# 但【不会】注入 GLVND 的 vendor 配置文件。
# 缺了它，libEGL 只认得镜像自带的 50_mesa.json，于是走软件渲染或直接失败。
# 这个 JSON 就是告诉 GLVND：「还有个叫 nvidia 的厂商，库名是这个」。
RUN mkdir -p /usr/share/glvnd/egl_vendor.d && \
    printf '{\n    "file_format_version" : "1.0.0",\n    "ICD" : {\n        "library_path" : "libEGL_nvidia.so.0"\n    }\n}\n' \
    > /usr/share/glvnd/egl_vendor.d/10_nvidia.json

# ---- 声明需要哪些驱动能力 ----
# 默认只给 compute,utility（够跑 CUDA，但不够渲染）。
# graphics 这一项就是 OpenGL/EGL 渲染所必需的。
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics

# ⚠️ 故意【不】改 MUJOCO_GL 的默认值 —— 仍然继承 osmesa。
#   理由：默认必须是「哪儿都能跑」的那个。
#   要 GPU 就显式 -e MUJOCO_GL=egl，让意图出现在命令行里。
```

构建：

```bash
cd /home/ubuntu22/workspaces/airbot-play/DISCOVERSE
docker build -f discoverse/docker/Dockerfile.test.gpu -t discoverse:test-gpu .
```

### 4.5.3 实测结果：值不值

**体积代价**（我实测）：

```
discoverse:test       1.55GB
discoverse:test-gpu   1.55GB      ← 只多几 MB，四舍五入没变
```

**性能收益**（480×640，渲染 100 帧）：

```bash
docker run --rm --gpus all -e MUJOCO_GL=egl discoverse:test-gpu python -c "
import mujoco, time, os
m = mujoco.MjModel.from_xml_string('<mujoco><worldbody><light pos=\"0 0 3\"/><body><geom size=\".1\" rgba=\"1 0 0 1\"/></body></worldbody></mujoco>')
d = mujoco.MjData(m); r = mujoco.Renderer(m, 480, 640)
mujoco.mj_forward(m, d); r.update_scene(d)
t = time.time()
for _ in range(100): img = r.render()
print('EGL/GPU -> %.0f FPS, mean=%.1f' % (100/(time.time()-t), img.mean()))
os._exit(0)   # ⚠️ 见 §4.5.4
"
```

我这台机器的实测对比：

| 后端 | FPS | 画面均值 |
|---|---|---|
| `osmesa`（CPU） | **57** | 29.9 |
| **`egl`（GPU）** | **1561 ~ 1682** | 29.8 |

⭐ **27 倍速度差，而画面均值一致（29.8 vs 29.9）** —— 说明**渲染结果等价，只是快了 27 倍**。

📌 **画面均值这个校验很重要**：只比 FPS 的话，你没法区分「渲染快了」和「渲染错了」。两个后端输出同一个数，才说明换后端是**等价变换**。

**全量测试两个后端都验证**：

```bash
docker run --rm --gpus all                    discoverse:test-gpu pytest tests/ -q  # 默认 osmesa
docker run --rm --gpus all -e MUJOCO_GL=egl   discoverse:test-gpu pytest tests/ -q  # 强制 egl
```

实测**两次都是**：

```
122 passed, 4 skipped, 45 deselected, 15 xfailed
```

✅ 换后端**不改变任何测试结果**，与基线一致。

### 4.5.4 ⚠️ 两个我踩到的坑，你会原样撞上

**坑一：`10_nvidia.json` 不写，EGL 就是死的。**

这是整件事的**唯一难点**，也是网上教程最常漏的一步。症状很迷惑 —— 我第一次只装了 `libegl1`，报错是：

```
AttributeError: 'NoneType' object has no attribute 'eglQueryString'
```

装上库之后换成了另一个错：

```
OpenGL.raw.EGL._errors.EGLError
```

排查方法是**直接问 EGL 它选了谁**：

```bash
docker run --rm --gpus all -e MUJOCO_GL=egl discoverse:test-gpu python -c "
from OpenGL import EGL
import ctypes, os
d = EGL.eglGetDisplay(EGL.EGL_DEFAULT_DISPLAY)
maj, minor = EGL.EGLint(), EGL.EGLint()
EGL.eglInitialize(d, ctypes.byref(maj), ctypes.byref(minor))   # ⚠️ 必须先 initialize
print('EGL', maj.value, '.', minor.value)
print('EGL vendor =', EGL.eglQueryString(d, EGL.EGL_VENDOR))
os._exit(0)
"
```

修好后应当输出：

```
EGL 1 . 5
EGL vendor = b'NVIDIA'
```

⚠️ **`eglInitialize` 那行不能省。** 少了它，`eglQueryString` 会直接报错：

```
EGLError(err = EGL_NOT_INITIALIZED, baseOperation = eglQueryString, ...)
```

📌 **`EGL_NOT_INITIALIZED` 是「你没初始化」，不是「你没有 GPU」** —— 别把这个错当成 EGL 装失败了。区分方法很简单：**跑一次渲染基准**，如果是 1500+ FPS 就说明 EGL 一切正常（Mesa 软渲染只有 50 上下）。

⚠️ 如果 vendor 输出是 `Mesa...`，才说明 vendor JSON 没生效 —— **你以为在用 GPU，实际在用 CPU 软渲染**，而且**不报错**。

📌 **又是那个模式：声明了（`-e MUJOCO_GL=egl`）但行为不符（实际走 Mesa），且失败时静默。** 这次来自 GLVND。**所以这条 `vendor == NVIDIA` 的断言必须进 pipeline**，见 §4.5.5。

**坑二：退出时的 `EGLError` 是噪声，不是失败。**

脚本跑完时你可能看到：

```
Traceback (most recent call last):
  File ".../mujoco/egl/__init__.py", line 131, in free
OpenGL.raw.EGL._errors.EGLError: <exception str() failed>
```

⚠️ **这发生在 `__del__` 析构里，渲染其实早就成功了。** 我确认过：`Renderer 创建成功` 和 FPS 都正常打印了，异常在**解释器退出阶段**才抛。

对策：小脚本里用 `os._exit(0)` 绕开析构。**pytest 跑全量时不受影响**（上面 122 passed 就是证据），所以**不用改任何测试代码**。

### 4.5.5 把后端选择做成 Jenkins 参数

现在把「运行时选后端」这件事接进 pipeline。在 `Jenkinsfile` 顶部加：

```groovy
parameters {
    choice(
        name: 'RENDER_BACKEND',
        choices: ['osmesa', 'egl'],
        description: 'osmesa=CPU软渲染(默认,零依赖) / egl=GPU无头渲染(快27倍,需 discoverse:test-gpu)'
    )
}
```

⚠️ **加了 `parameters` 之后，第一次 Build 仍是无参数的旧配置** —— Jenkins 要先跑一次才能「学到」参数。**第二次开始**左侧菜单才会变成 **Build with Parameters**。这是 Jenkins 的正常行为，别以为写错了。

然后镜像和后端联动：

```groovy
environment {
    // egl 需要装了 EGL 的镜像；osmesa 用原来那个
    TEST_IMAGE = "${params.RENDER_BACKEND == 'egl' ? 'discoverse:test-gpu' : 'discoverse:test'}"
}
```

**另外还要加一个「渲染后端自检」stage** —— 里面是 §4.5.4 那条 `vendor == NVIDIA` 的断言，用来挡住静默退化；回归 stage 则要把 `-e MUJOCO_GL=${RENDER_BACKEND}` 传进容器。

📌 **这三处改动（parameters / 自检 stage / -e 注入）已经合并进 Step 5.2 的完整 Jenkinsfile 里了**，直接照那份写即可，不用在这里拼。

### 4.5.6 ⚠️ 但要诚实：这仍然没让测试「需要」GPU

⭐ **这一节请务必想清楚，它是今天判断力的分水岭。**

装上 EGL 之后，事实变成了：

| 层次 | 改造前 | **改造后** |
|---|---|---|
| GPU 能透进容器 | ✅ | ✅ |
| 镜像里有 EGL 库 | ❌ | ✅ **已解决** |
| 测试**能**用 GPU 渲染 | ❌ | ✅ **已解决（27× 实测）** |
| **有测试真的需要 GPU 吗** | ❌ | ❌ **仍然没有** |

📌 **最后一行没变，而它才是根本。**

122 个用例跑 3 秒，全在配置层和 IK —— **它们几乎不渲染**。所以那 27 倍加速，**对当前的测试套件几乎没有收益**（实测两个后端总耗时都是 2.7 秒左右）。

**那为什么还值得做？** 因为投入产出比变了：

- **成本**：一个 15 行的 Dockerfile，体积几乎不增，**测试结果零变化**
- **收益**：`egl` 这条路**被验证可用了**，而且验证过程本身挖出了 `10_nvidia.json` 这个隐藏依赖

> **基础设施可以先于需求存在，前提是成本足够低且被验证过。**
> **但绝不能因为「基础设施做好了」就去编造需求来用它。**

⚠️ **所以定位仍然是**：今天做的是**能力储备 + 一条静默退化的防线**（vendor 断言），**不是**「Jenkins 在跑 GPU 测试」。简历和面试里都不该那么说。

> **面试可用点**（这段比「我搭了 Jenkins」值钱得多）：
>
> *「我搭 Jenkins 的理由是 GitHub 免费 runner 没 GPU，而这项目有 3DGS 渲染。但实测后我发现链条断在中间：GPU 能透进容器，可我 Day 8-9 那个测试镜像是为云端 CI 特意做的 CPU + osmesa 瘦镜像，没有 libEGL。」*
>
> *「我把渲染后端从写死改成了运行时可选的三档（osmesa / egl / glfw），做了个加 EGL 的 GPU 镜像。**最坑的是 nvidia-container-toolkit 会注入 libEGL_nvidia.so，但不注入 GLVND 的 vendor JSON** —— 缺了那个文件，EGL 会静默退化到 Mesa 软渲染，你以为在用 GPU 其实没有。所以我在 pipeline 里加了断言，直接查 eglQueryString 的 vendor 必须是 NVIDIA。实测 EGL 比 osmesa 快 27 倍（1561 vs 57 FPS），而画面均值一致，说明是等价变换。」*
>
> *「**但我不会说 Jenkins 在跑 GPU 测试** —— 我当前 122 个用例没一个真的需要 GPU，两个后端跑完都是 2.7 秒。这是能力储备，成本是 15 行 Dockerfile，收益是这条路被验证过了。**基础设施可以先于需求，但不能反过来为了用显卡去编需求。**」*
>
> 📌 **第三段最值钱** —— 它证明你不会被自己刚做完的东西推着走。

### 4.6 那今天的 Jenkins job 到底测什么

**诚实的定位**：

| | GitHub Actions | **Jenkins（今天）** |
|---|---|---|
| 触发 | 每次 push 自动 | **手动 / 定时** |
| 代码来源 | git clone（干净） | **本机工作区（含未提交）** |
| 环境 | 云端全新 runner | **本机真实环境** |
| GPU | 无 | **可用（egl 已打通），但无测试需要** |
| 渲染后端 | 固定 osmesa | **参数可选 osmesa / egl** |
| 定位 | **准入门槛** | **本机冒烟 + GPU 能力储备** |

📌 它验证了「宿主机 → Jenkins 容器 → 兄弟容器 → GPU + EGL + 测试 + 报告」这条**完整链路**是通的。等真有 GPU 测试那天，**只要把参数切到 `egl`**。

---

## Step 5｜写真正的 Jenkinsfile（50 分钟）

现在把前四步的结论合成一个文件。

### 5.1 先解决报告问题：JUnit XML

Jenkins 不认识 pytest 的文字输出，它认识 **JUnit XML** —— 一种通用的测试结果格式。

pytest 内置支持，加个参数即可：

```bash
pytest tests/ -q --junitxml=/out/results.xml
```

先在本机验证这条链路（**报告要落到宿主机上，Jenkins 才收得到**）：

```bash
mkdir -p /tmp/jx && docker run --rm -v /tmp/jx:/out discoverse:test \
  pytest tests/ -q --junitxml=/out/results.xml 2>&1 | tail -2
head -c 300 /tmp/jx/results.xml
```

实测：

```
122 passed, 4 skipped, 45 deselected, 15 xfailed in 3.04s
<?xml version="1.0" encoding="utf-8"?><testsuites name="pytest tests"><testsuite name="pytest"
 errors="0" failures="0" skipped="19" tests="141" time="3.037" ...
```

✅ XML 生成成功。

### ⚠️ 一个会让你困惑的数字：为什么 XML 里是 `tests="141"`

pytest 说 `122 passed`，XML 却写 `tests="141"`、`skipped="19"`。**别慌，都对**：

```
122 passed + 4 skipped + 15 xfailed = 141   ← XML 的 tests
        4 skipped + 15 xfailed = 19         ← XML 的 skipped
```

📌 **两处差异要理解**：

1. **JUnit 格式没有「xfail」这个概念**（它是 Java 世界的标准，比 pytest 老）。pytest 只能把 xfail 塞进 `skipped` 里。
2. **那 45 个 deselected 根本不在 XML 里** —— 它们被 `-m 'not flake'` 在收集阶段就筛掉了，从未运行。

⚠️ **所以 Jenkins 界面上会显示「141 tests, 19 skipped」，和你背了两周的「122 passed」对不上。** 这不是 bug，是**格式转换的信息损失**。心里有数即可，别去「修」它。

### 5.2 完整的 Jenkinsfile

在**仓库根目录**创建 `Jenkinsfile`（没有扩展名，J 大写）：

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

pipeline {
    agent any

    // ⚠️ 加了 parameters 后，第一次 Build 仍是旧配置（无参数）。
    //    Jenkins 要先跑一次才「学到」参数，第二次起菜单才变成 Build with Parameters。
    parameters {
        choice(
            name: 'RENDER_BACKEND',
            choices: ['osmesa', 'egl'],
            description: 'osmesa=CPU软渲染(默认,零依赖) / egl=GPU无头渲染(实测快27倍,需 discoverse:test-gpu)'
        )
    }

    environment {
        // 被测代码：宿主机上的工作区（docker -v 要用宿主机路径）
        // ⚠️ Jenkins 容器【看不到】这个路径，只有兄弟容器能。见 §5.3.2
        REPO_ON_HOST = '/home/ubuntu22/workspaces/airbot-play/DISCOVERSE'

        // 同一个 workspace 的两个名字 —— 别写混
        // ⚠️ WS_ON_HOST 必须【从 WORKSPACE 推导】，不能用 ${JOB_NAME} 硬拼：
        //    并发构建时 Jenkins 会分配 xxx@2 这样的 workspace，而 JOB_NAME 不含 @2，
        //    两个路径就错开了 —— XML 写进 A，Jenkins 去 B 找，报告永远是空的。见 §5.3.5
        WS_IN_JENKINS = "${WORKSPACE}"
        WS_ON_HOST    = "${WORKSPACE.replace('/var/jenkins_home', '/home/ubuntu22/robot_platform/jenkins_home')}"

        // ⚠️ 必须把参数桥接成环境变量 —— 否则 sh 里的 ${RENDER_BACKEND} 是【空串】，
        //    `[ "" = egl ]` 恒假，会静默走到 osmesa 分支。见 §5.3.1
        RENDER_BACKEND = "${params.RENDER_BACKEND}"

        // 后端与镜像联动：egl 需要装了 EGL 的镜像
        TEST_IMAGE = "${params.RENDER_BACKEND == 'egl' ? 'discoverse:test-gpu' : 'discoverse:test'}"
    }

    options {
        disableConcurrentBuilds()             // 从根上不产生 xxx@2 的并发 workspace（§5.3.5）
        timeout(time: 30, unit: 'MINUTES')   // 卡死时兜底，别挂一夜
        timestamps()                          // 每行日志带时间戳
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }

    stages {

        stage('环境自检') {
            steps {
                sh '''
                    echo "=== Jenkins 侧（容器内，只有 git/docker/java）==="
                    whoami; pwd
                    docker --version

                    # ⚠️ 这里【不要】跑 nvidia-smi —— Jenkins 容器里没装（§0.2）。
                    #    GPU 信息交给「GPU 可见性」stage，那是在兄弟容器里跑的。

                    echo "=== 后端 ${RENDER_BACKEND} / 镜像 ${TEST_IMAGE} ==="
                    docker image inspect ${TEST_IMAGE} > /dev/null \
                      && echo "✅ ${TEST_IMAGE} 存在" \
                      || { echo "❌ 镜像不存在。构建命令（项目根目录执行）:"; \
                           echo "   docker build -f discoverse/docker/Dockerfile.test     -t discoverse:test ."; \
                           echo "   docker build -f discoverse/docker/Dockerfile.test.gpu -t discoverse:test-gpu ."; \
                           exit 1; }
                '''
            }
        }

        stage('渲染后端自检') {
            steps {
                sh '''
                    if [ "${RENDER_BACKEND}" = "egl" ]; then
                        # ⚠️ 必须断言 vendor 真的是 NVIDIA。
                        #    只 -e MUJOCO_GL=egl 而 vendor 落到 Mesa 的话，
                        #    会静默退化成 CPU 软渲染 —— 见教程 §4.5.4 坑一。
                        docker run --rm --gpus all -e MUJOCO_GL=egl ${TEST_IMAGE} python -c "
from OpenGL import EGL
import ctypes, os, sys
d = EGL.eglGetDisplay(EGL.EGL_DEFAULT_DISPLAY)
maj, minor = EGL.EGLint(), EGL.EGLint()
EGL.eglInitialize(d, ctypes.byref(maj), ctypes.byref(minor))  # 不初始化就查会 EGL_NOT_INITIALIZED
v = EGL.eglQueryString(d, EGL.EGL_VENDOR)
print('EGL', maj.value, '.', minor.value, 'vendor =', v)
sys.stdout.flush()
os._exit(0 if v and b'NVIDIA' in v else 1)
"
                        echo "✅ EGL 走的是 NVIDIA，不是 Mesa 软渲染"
                    else
                        echo "ℹ️ CPU 软渲染路径，与 GitHub Actions 一致"
                    fi
                '''
            }
        }

        stage('代码状态') {
            // ⚠️ 本课直接挂宿主机工作区（未 clone），所以必须把
            //    「测的到底是哪份代码」写进日志。见教程 Step 3.3。
            //
            // ⚠️⚠️ 不能写 `cd ${REPO_ON_HOST}` —— Jenkins 容器【看不到】项目目录！
            //    它只挂了 jenkins_home / docker.sock / docker 二进制（§0.3）。
            //    路径要交给【兄弟容器】，由宿主机 dockerd 解析。见 §5.3.2。
            //
            // ⚠️ --entrypoint sh：alpine/git 的 entrypoint 是 git 本身，
            //    不覆盖的话 `sh -c` 会被当成 git 子命令。
            // ⚠️ safe.directory：git 拒绝操作属主不同的仓库。
            steps {
                sh '''
                    docker run --rm --entrypoint sh \
                      -v ${REPO_ON_HOST}:/repo -w /repo alpine/git:latest \
                      -c 'git config --global --add safe.directory /repo;
                          echo "commit : $(git log -1 --format="%h %s")";
                          echo "branch : $(git rev-parse --abbrev-ref HEAD)";
                          echo "=== 未提交改动（非空即说明测的是脏代码）===";
                          git status --short'
                '''
            }
        }

        stage('GPU 可见性') {
            // 这是 Jenkins 相对 GitHub Actions 的唯一硬件优势，单独成 stage 留证据
            steps {
                sh '''
                    docker run --rm --gpus all ${TEST_IMAGE} \
                      nvidia-smi --query-gpu=name,memory.total --format=csv,noheader

                    echo "=== 镜像内渲染库清点 ==="
                    docker run --rm ${TEST_IMAGE} sh -c \
                      'echo "libEGL  : $(ls /usr/lib/x86_64-linux-gnu/ | grep -ci egl)"; \
                       echo "libOSMesa: $(ls /usr/lib/x86_64-linux-gnu/ | grep -ci osmesa)"'
                '''
            }
        }

        stage('回归测试') {
            steps {
                sh '''
                    mkdir -p ${WS_IN_JENKINS}/test-results

                    # ⚠️ -v 左边全是宿主机路径（Step 2）
                    # ⚠️ 不加 :ro —— 测试会往 models/mjcf/tmp/ 写临时 MJCF（§5.4）
                    # ⚠️ MUJOCO_GL 由参数注入，覆盖镜像里 ENV 的默认值
                    docker run --rm --gpus all \
                      -e MUJOCO_GL=${RENDER_BACKEND} \
                      -v ${REPO_ON_HOST}:/repo \
                      -v ${WS_ON_HOST}/test-results:/out \
                      -w /repo \
                      ${TEST_IMAGE} \
                      pytest tests/ -q -p no:cacheprovider \
                             --junitxml=/out/results.xml
                '''
            }
        }
    }

    post {
        always {
            // ⚠️ 必须在 always 里 —— 测试失败时才最需要这份报告
            // ⚠️ allowEmptyResults:true —— 若写 false，前面 stage 失败导致没产出 XML 时，
            //    post 会【再抛一个异常】，把真正的错因埋在两层 traceback 下面。见 §5.3.3
            junit testResults: 'test-results/*.xml', allowEmptyResults: true
            archiveArtifacts artifacts: 'test-results/*.xml', allowEmptyArchive: true
        }
        success {
            // ⚠️ 别把「跑在 egl 上」说成「跑了 GPU 测试」—— 见 §4.5.6
            echo "✅ 通过（后端 ${params.RENDER_BACKEND}）。注意：当前无任何用例真正需要 GPU，两档预期同为 122 passed"
        }
        failure {
            echo '❌ 失败。排查顺序：1) 镜像在不在 2) -v 路径是不是宿主机路径 3) egl 档看 vendor 是否 NVIDIA 4) 工作区是否脏'
        }
    }
}
```

### 5.3 ⭐ 第一次跑必然踩的四个坑（真实构建日志）

⚠️ **上面那份 Jenkinsfile 已经是修正版。** 但你若照着更早的版本写，第一次构建会一次性暴露四个问题 —— 我把真实日志留在这里，因为**每一个都对应一条通用规律**。

#### 5.3.1 坑一：`${RENDER_BACKEND}` 在 `sh` 里是空串

真实日志：

```
+ echo === 后端  / 镜像 discoverse:test ===     ← 「后端」后面什么都没有
+ [  = egl ]                                     ← 展开成了 [ = egl ]
+ echo ℹ️ CPU 软渲染路径
```

**原因**：`parameters {}` 声明的参数存在 `params.` 命名空间里，**不会自动变成 shell 环境变量**。

**修**：在 `environment {}` 里桥接一次：

```groovy
environment {
    RENDER_BACKEND = "${params.RENDER_BACKEND}"
}
```

⚠️ **注意这个 bug 的形态**：`[ "" = egl ]` 恒为假，于是**永远走 osmesa 分支** —— 你选了 egl，它跑了 osmesa，**全绿，不报错**。

📌 **又是「声明了但行为不符，且失败时静默」。** 这次是 Jenkins 的变量作用域。

#### 5.3.2 ⭐ 坑二：Jenkins 容器看不到你的项目目录

真实日志：

```
+ cd /home/ubuntu22/workspaces/airbot-play/DISCOVERSE
cd: can't cd to /home/ubuntu22/workspaces/airbot-play/DISCOVERSE
```

⚠️ **这是 Step 2 路径课的第二种形态，而且更隐蔽。**

回看 §0.3 那三个挂载：`jenkins_home`、`docker.sock`、`docker` 二进制 —— **没有你的项目目录**。

| 谁 | 看得到 `/home/ubuntu22/workspaces/...` 吗 |
|---|---|
| 宿主机 | ✅ |
| **Jenkins 容器**（`sh` 步骤） | ❌ **看不到** |
| **兄弟容器**（`docker run -v`） | ✅ 路径由**宿主机** dockerd 解析 |

📌 **所以「回归测试」stage 一直是对的**（它用 `docker run -v`），**错的是「代码状态」stage 用了 `cd`**。

**修**：把 git 操作也放进兄弟容器：

```groovy
docker run --rm --entrypoint sh \
  -v ${REPO_ON_HOST}:/repo -w /repo alpine/git:latest \
  -c 'git config --global --add safe.directory /repo; git log -1 --oneline; git status --short'
```

⚠️ **两个附加细节**（都是我实测撞到的）：

1. **`--entrypoint sh` 不能省** —— `alpine/git` 的 entrypoint 就是 `git`，不覆盖的话 `sh -c ...` 会被当成 git 子命令，报 `git: 'sh' is not a git command`
2. **`safe.directory` 不能省** —— git 拒绝操作属主与当前用户不同的仓库

> ⭐ **一条通则**：**在这套 Jenkins 里，凡是要碰宿主机文件的操作，都得进兄弟容器。** `sh` 步骤只能碰 `jenkins_home`。

#### 5.3.3 坑三：`nvidia-smi: not found`

真实日志：

```
nvidia-smi: not found
⚠️ 宿主机看不到 GPU        ← 这句话是错的
```

⚠️ **不是宿主机没 GPU，是 Jenkins 容器里没装 `nvidia-smi`**（§0.2 只有 git/docker/java）。

📌 **顺带批评一下我自己写的那句 `|| echo "⚠️ 宿主机看不到 GPU"`** —— **兜底文案撒了谎**。它把「命令不存在」说成了「硬件不存在」，会把人引向完全错误的排查方向。

> **写 fallback 文案时，别断言你没验证过的原因。** 老实说「nvidia-smi 不可用」就好。

**修**：这行整个删掉，GPU 信息交给「GPU 可见性」stage（那是 `docker run --gpus all` 跑的）。

#### 5.3.4 坑四：`post` 把真正的错因盖住了

真实日志：

```
No test report files were found. Configuration error?
hudson.AbortException: ...
	at hudson.tasks.junit.JUnitParser...
	（十几行 Java 栈）
```

这**不是独立问题** —— 测试 stage 被 skip 了，当然没有 XML。

⚠️ **但它暴露了设计缺陷**：`allowEmptyResults: false` 让 post 阶段**又抛一个异常**，于是控制台最下面是一堆 Java 栈，而**真正的错因（`cd` 失败）在上面几十行外**。

**修**：

```groovy
junit testResults: 'test-results/*.xml', allowEmptyResults: true
```

📌 **通则：`post` 块的职责是收集，不是制造新的失败。** 一个在失败路径上还会再失败的收尾逻辑，会**放大排查成本** —— 你要先剥掉它的错，才能看到原始的错。

#### 5.3.5 ⭐ 坑五：`@2` —— 报告写对了，Jenkins 却找错了地方

⚠️ **这个最阴**：所有 stage **全绿**，`122 passed` 也打出来了，**但报告是空的**，而且构建状态是 `SUCCESS`。

真实日志：

```
Running on Jenkins in /var/jenkins_home/workspace/DISCOVERSE-GPU-Regression@2
                                                                          ↑↑ 注意这个
+ mkdir -p /var/jenkins_home/workspace/DISCOVERSE-GPU-Regression@2/test-results
+ docker run ... -v /home/ubuntu22/robot_platform/jenkins_home/workspace/DISCOVERSE-GPU-Regression/test-results:/out ...
                                                                                            ↑ 这里没有 @2
...
122 passed, 4 skipped, 45 deselected, 15 xfailed in 3.04s
...
No test report files were found. Configuration error?
'test-results/*.xml' doesn't match anything: 'test-results' exists but not 'test-results/*.xml'
```

**根因**：Jenkins 在**并发构建**时会给第二个构建分配独立 workspace，名字加 `@2` 后缀。

而 `WS_ON_HOST` 是用 `${JOB_NAME}` 拼的 —— **`JOB_NAME` 永远是 `DISCOVERSE-GPU-Regression`，不含 `@2`**。于是：

| | 路径 |
|---|---|
| pytest 把 XML 写到（`-v` 指定） | `.../DISCOVERSE-GPU-Regression/test-results/` |
| Jenkins 去找（`${WORKSPACE}` 相对） | `.../DISCOVERSE-GPU-Regression@2/test-results/` |

实测确认 XML 确实生成了，只是在隔壁：

```bash
find /home/ubuntu22/robot_platform/jenkins_home/workspace/ -name results.xml
# .../DISCOVERSE-GPU-Regression/test-results/results.xml  (22227 bytes)   ← 写对了，找错了
```

**修（两条一起上）**：

```groovy
// 1. 从 WORKSPACE 推导，而不是用 JOB_NAME 拼 —— @2 会自动跟上
WS_ON_HOST = "${WORKSPACE.replace('/var/jenkins_home', '/home/ubuntu22/robot_platform/jenkins_home')}"

// 2. 从根上不产生并发 workspace
options { disableConcurrentBuilds() }
```

📌 **⭐ 这是今天路径课的第三种形态，也是最值得记的一条通用规律**：

> **同一个东西有两个名字时，永远【从一个推导出另一个】，不要两边各写一份硬编码。**
>
> 两份硬编码在「正常情况」下看起来完全一致 —— 直到某个你没预料到的后缀（`@2`）出现，它们才分叉。**而分叉时没有任何报错。**

⚠️ **注意这个 bug 的形态**：构建 `SUCCESS`、测试 `122 passed`、报告为空。**如果你只看构建是绿的，会以为一切正常。**

📌 **今天第 N 次撞见同一个模式：声明了（要收集报告）但行为不符（收了个空），且失败时静默。** 这次来自 Jenkins 的并发 workspace 机制。

---

### 5.4 ⚠️ 一个我实测踩到的坑：不能挂 `:ro`

「被测代码只读挂载」听起来是好习惯，我一开始就是这么写的：

```groovy
-v ${REPO_ON_HOST}:/repo:ro     // ← 加了 :ro
```

实测结果：

```
115 passed, 4 skipped, 45 deselected, 15 xfailed, 7 errors in 2.49s
```

❌ **7 个 error**，比基线少了 7 个 passed。查原因：

```
E   OSError: [Errno 30] Read-only file system: '/repo/models/mjcf/tmp/airbot_play_place_block.xml'
```

📌 **根因**：测试运行时会往**仓库目录里**写临时 MJCF 文件（`models/mjcf/tmp/`）。只读挂载直接把这条路堵死。

**去掉 `:ro` 后**：

```
122 passed, 4 skipped, 45 deselected, 15 xfailed in 2.66s
```

✅ 与基线一致。

⚠️ **顺带确认了一件重要的事** —— 跑完之后：

```bash
git status --short
```

工作区**没有多出任何文件**（那个 tmp 目录已在 `.gitignore` 里）。所以读写挂载不会污染仓库。

📌 **但这本身是个值得记的缺陷线索**：**测试把中间产物写进源码树**，而不是写进 `tmp_path`。这让「只读挂载被测代码」这个标准做法用不了。**记进缺陷清单，今天不修**（改的是 `discoverse/` 里的上游代码，且一次只改一件事）。

### 5.5 让 Jenkins 用这个文件

刚才 job 里的脚本是直接粘的。改成从仓库读 `Jenkinsfile` 更专业，但**这里有个陷阱**：

⚠️ 「Pipeline script from SCM」会让 Jenkins **自己去 clone 仓库** —— 就是 §3.1 那个 8 分钟还没完的操作。

**所以本课先用最简单的方式**：job 配置里仍选 **Pipeline script**，把 `Jenkinsfile` 内容**粘贴进去**。

📌 文件仍然要提交进仓库（简历和面试要能拿出来看），只是**暂时手动同步**。

> **想升级成 SCM 模式**（记进欠账）：把 Definition 改成 `Pipeline script from SCM`，SCM 选 Git，URL 用**本地路径** `file:///home/ubuntu22/workspaces/airbot-play/DISCOVERSE`（本地磁盘克隆，秒级），Branch 填 `feat/test-infra`，Script Path 填 `Jenkinsfile`。

---

## Step 6｜跑起来，验收（30 分钟）

### 6.1 先在终端预演一遍

**别直接点 Build。** 先在终端跑一遍 Jenkins 将要执行的完整命令 —— 失败了排查成本低得多：

```bash
docker exec jenkins_server sh -c '
  mkdir -p /var/jenkins_home/workspace/DISCOVERSE-GPU-Regression/test-results
  docker run --rm --gpus all \
    -v /home/ubuntu22/workspaces/airbot-play/DISCOVERSE:/repo \
    -v /home/ubuntu22/robot_platform/jenkins_home/workspace/DISCOVERSE-GPU-Regression/test-results:/out \
    -w /repo discoverse:test \
    sh -c "nvidia-smi --query-gpu=name --format=csv,noheader; pytest tests/ -q -p no:cacheprovider --junitxml=/out/results.xml 2>&1 | tail -2"
'
```

我实测的输出：

```
NVIDIA GeForce RTX 4060 Laptop GPU
122 passed, 4 skipped, 45 deselected, 15 xfailed in 2.66s
```

✅ **两件事同时成立**：GPU 可见 + 数字与基线**完全一致**。

确认 XML 落到了 Jenkins 看得见的地方：

```bash
docker exec jenkins_server ls -la /var/jenkins_home/workspace/DISCOVERSE-GPU-Regression/test-results/
```

### 6.2 Build Now

回到 http://localhost:8080 的 job 页面 → **Build Now**。

**验收清单**：

- [ ] **5 个 stage 全绿**（环境自检 / 渲染后端自检 / 代码状态 / GPU 可见性 / 回归测试）
- [ ] Console Output 里 `nvidia-smi` 有 RTX 4060 输出
- [ ] Console Output 里有 `122 passed`
- [ ] 页面出现 **Test Result** 链接，点进去有测试列表
- [ ] Test Result 显示 **141 tests / 19 skipped**（⚠️ 与 122 的差异见 §5.1）
- [ ] `test-results/results.xml` 在 Artifacts 里可下载
- [ ] `git status --short` 那段输出里，你能确认测的是哪份代码

**然后再跑一次 `egl` 档**（⚠️ 第一次 Build 后菜单才会出现 **Build with Parameters**，见 §4.5.5）：

- [ ] `RENDER_BACKEND=egl` 时，镜像自动切成 `discoverse:test-gpu`
- [ ] 「渲染后端自检」stage 打印 **`EGL vendor = b'NVIDIA'`**（⚠️ 若是 Mesa 就是静默退化了）
- [ ] 仍然是 **`122 passed`** —— **两档数字必须一致**，否则换后端就不是等价变换

⚠️ 如果 `egl` 档报「镜像不存在」，说明 §4.5.2 那个镜像还没构建：

```bash
docker build -f discoverse/docker/Dockerfile.test.gpu -t discoverse:test-gpu .
```

### 6.3 故意弄红一次

⚠️ **一条从没红过的流水线，你并不知道它红的时候什么样。** Day 10-11 的教训。

临时在测试里加个必失败的用例：

```bash
cat >> tests/unit/test_smoke.py <<'EOF'


def test_deliberate_failure_delete_me():
    """Day 12 故意失败——验证 Jenkins 报告链路。验证完立即删。"""
    assert 1 == 2, "故意的"
EOF
```

再 **Build Now**，确认：

- [ ] 构建变**红**
- [ ] **Test Result 里能看到这个失败用例的名字和 assert 详情** ⭐

📌 **最后一条是重点。** 它证明 `post { always { junit ... } }` 真的生效了 —— **失败时报告照样被收集**。如果 `junit` 写在 `success` 里，这时候你什么都看不到。

验证完**立刻删掉**：

```bash
cd /home/ubuntu22/workspaces/airbot-play/DISCOVERSE
git checkout tests/unit/test_smoke.py
$PY -m pytest tests/ -q | tail -1   # 确认回到 122 passed
```

### 6.4 定时触发：别照抄凌晨 3 点

计划文档写 `0 3 * * *`（每天凌晨 3 点）。

⚠️ **你的机器凌晨 3 点大概率是关机或休眠的** —— job 静默不跑，而你以为它在跑。**这又是一个「声明了但行为不符，且失败时静默」**（两周内第 N 次）。

**两个选择**：

**A. 干脆不加定时**（今天推荐）—— 手动 Build Now。诚实。

**B. 加 `H` 让它落在你开机的时段**：

```groovy
triggers {
    cron('H 14 * * 1-5')    // 工作日下午 2 点左右
}
```

### 📖 补充知识：Jenkins 的 `H` 是什么

Jenkins 的 cron 比标准 cron 多一个 **`H`（hash）**：

| 写法 | 含义 |
|---|---|
| `0 14 * * *` | 每天 14:00:00 **整点**触发 |
| `H 14 * * *` | 每天 14 点内**某个固定分钟**触发（由 job 名 hash 决定） |

📌 **为什么要有 H**：如果 50 个 job 都写 `0 14 * * *`，它们会在同一秒一起启动，把机器压垮。`H` 让 Jenkins 把它们**均匀打散**到那一小时里，但对**同一个 job 每次都是同一分钟**（稳定可预期）。

⚠️ **能用 `H` 就用 `H`** —— 除非你真的需要精确整点。

---

## 今天的验收标准

- [ ] 能说清 Jenkins 和 GitHub Actions 的分工，且**理由是硬件不是习惯**
- [ ] 理解「Jenkins 在容器里」→ 兄弟容器 → `-v` 路径必须写宿主机路径
- [ ] `Jenkinsfile` 和 `Dockerfile.test.gpu` 已提交进仓库
- [ ] job 手动触发成功，Console 里有 GPU 信息和 `122 passed`
- [ ] Test Result 页面有数据，且**失败时也有**（§6.3 验证过）
- [ ] **`RENDER_BACKEND` 参数两档都跑过，都是 `122 passed`**
- [ ] **`egl` 档能看到 `EGL vendor = NVIDIA`**（不是 Mesa —— 见 §4.5.4 坑一）
- [ ] **能说清「GPU 可见」/「GPU 可用」/「有测试需要 GPU」三者的区别**，且知道自己停在哪一层
- [ ] 工作区干净，`122 passed` 未变

---

## 今天真正学到的

**表面**：装了个 Jenkins job，跑了一遍测试。

**实际是五件事**：

1. **「本地 CI」和「云端 CI」的取舍是硬件和网络，不是工具偏好。**

   | | 云端赢 | 本地赢 |
   |---|---|---|
   | 干净环境 | ✅ 每次全新 VM | ❌ 你的脏机器 |
   | 克隆速度 | ✅ 同数据中心，十几秒 | ❌ **实测 8 分钟没下完** |
   | GPU | ❌ 免费 runner 没有 | ✅ **RTX 4060** |
   | 时长 | ❌ 每月 2000 分钟 | ✅ 只限电费 |
   | 私有数据 | ❌ | ✅ |

   📌 **注意第二行是我今天才实测到的** —— 「本地更快」是个想当然，**对大仓库恰恰相反**。

2. **⭐ 兄弟容器的路径陷阱，是今天最值钱的知识。**

   `docker run -v A:B` 里的 `A` 由**宿主机** dockerd 解析。在 Jenkins 容器里写 `/var/jenkins_home/...` 不会报错 —— **Docker 会在宿主机凭空造一个空目录挂上去**，然后你的测试 collect 到 0 个用例，看起来像通过。

   ⚠️ 这**又是**那个模式：**声明了但行为不符，且失败时静默。** 两周内第 N 次，这次来自 Docker 本身。

3. **「GPU 可见」≠「GPU 可用」≠「有测试需要 GPU」—— 三层，今天推进了两层。**

   ```
   ✅ 宿主机有 GPU
   ✅ nvidia-container-toolkit 装了
   ✅ GPU 透进容器（nvidia-smi 有输出）
   ✅ 镜像里有 EGL 库          ← 今天打通（15 行 Dockerfile）
   ✅ 测试能用 GPU 渲染        ← 今天打通（实测 27×）
   ❌ 有测试真的需要 GPU        ← 仍然没有，而这一层才是根本
   ```

   📌 **最后一层没变，它比前面五层加起来都重要。** 122 个用例跑 3 秒，两个后端耗时几乎一样 —— **那 27 倍加速对当前套件毫无收益**。

   ⭐ **所以要同时守住两条**：
   - **基础设施可以先于需求存在** —— 前提是成本足够低（15 行、体积几乎不增、测试结果零变化）且**被验证过**
   - **但绝不能因为基础设施做好了，就去编造需求来用它**

4. **⭐ 渲染后端改造：企业做法是「一个镜像，运行时选后端」。**

   | 后端 | 场景 | 实测 FPS |
   |---|---|---|
   | `osmesa` | CI（无 GPU） | **57** |
   | `egl` | **GPU 服务器（无显示器）** | **1561~1682** |
   | `glfw` | 开发者本机 | 要显示器 |

   📌 **`egl` 填的是「既没显示器、又要 GPU」这个格子** —— 服务器和你的 Jenkins 都在这个格子里。

   ⚠️ **最大的坑**：nvidia-container-toolkit 注入 `libEGL_nvidia.so`，**却不注入 GLVND 的 vendor JSON**。缺了它，`-e MUJOCO_GL=egl` 会**静默退化成 Mesa 软渲染** —— **又是那个模式：声明了但行为不符，且失败时静默**，这次来自 GLVND。所以 pipeline 里必须断言 `EGL vendor == NVIDIA`。

5. **又一次「决定不做」，且都有量化依据。**

   | 不做什么 | 依据 |
   |---|---|
   | 不在 Jenkins 里 clone | 实测 8 分钟只下 37/308 MB |
   | **不改原 `Dockerfile.test` 加 EGL** | 它的目标是 GitHub Actions（无 GPU），装了纯浪费 → **单独 `.gpu` 文件** |
   | **不把默认 `MUJOCO_GL` 改成 egl** | 默认必须是「哪儿都能跑」的那个 |
   | **不为了用上 EGL 去造 GPU 测试** | 当前 0 个测试需要，造了就是自欺 |
   | 不加凌晨 3 点定时 | 机器那时候是关的，会静默不跑 |
   | 不用 SCM 模式读 Jenkinsfile | 同第一条，且本课目标是先跑通 |
   | 不修「测试写进源码树」 | 属 `discoverse/` 上游代码，一次只改一件事 |

   📌 **每一条都写进了 Dockerfile / Jenkinsfile 注释或欠账，而不是烂在脑子里。**

6. **一个新缺陷线索：测试把临时文件写进源码树。**

   `models/mjcf/tmp/*.xml` —— 导致「只读挂载被测代码」这个标准安全做法直接用不了（7 errors）。**今天不修，记进清单。**

7. **⭐ 「声明了但行为不符，且失败时静默」——今天一天撞见两次新的。**

   | 案例 | 声明 | 实际 |
   |---|---|---|
   | **`docker run -v` 写容器内路径** | 挂载了代码 | **挂了个凭空造的空目录** |
   | **`-e MUJOCO_GL=egl` 缺 vendor JSON** | 用 GPU 渲染 | **静默退化成 Mesa 软渲染** |

   ⚠️ **注意这两条都不是项目代码的锅** —— 一个是 Docker 的行为，一个是 GLVND 的行为。

   📌 **两周下来，这个模式已经在项目代码、我自己写的测试、Docker、GLVND 里各出现过。** 它不是某个人的坏习惯，是**基础设施的普遍属性**：**默认行为倾向于「让你继续跑下去」，而不是「让你知道出事了」。** 对策只有一个 —— **把关键假设写成断言**（`vendor == NVIDIA`、`head -c 60` 查 LFS 指针、构建期 import 自检）。

> **面试可用点**：被问「你为什么同时用 GitHub Actions 和 Jenkins」时，别答「因为都会」。
>
> 答：*「分工是硬件决定的：GitHub 免费 runner 没 GPU，而这项目有 3DGS 渲染，所以轻量测试走云端当每次 push 的准入门槛，需要 GPU 的走本机 Jenkins。我把渲染后端从写死的 osmesa 改成运行时三档可选（osmesa/egl/glfw），并做了个带 EGL 的 GPU 镜像，实测 EGL 比 osmesa 快 27 倍且画面均值一致。**但我不会说我在跑 GPU 测试** —— 我 122 个用例没一个真需要 GPU，两个后端跑完都是 2.7 秒。这是能力储备，不是业务收益。」*
>
> *「搭的过程里最坑的是路径：Jenkins 自己跑在容器里，挂了 docker.sock，起出来的是**兄弟容器**不是子容器 —— `-v` 的源路径是宿主机 dockerd 解析的。我一开始写容器内路径，Docker 不报错，直接在宿主机造了个空目录挂上,测试 collect 到 0 个用例像是通过了。EGL 那边是同一类问题：toolkit 注入了 libEGL_nvidia.so 但不注入 GLVND vendor JSON，缺了它会静默退化成软渲染。**两个都是「声明了但行为不符且失败时静默」，所以我把它们都写成了 pipeline 里的断言。**」*
>
> 📌 **两段的共同点：都在讲「我发现了什么」而不是「我配置了什么」。** 配置谁都会抄，发现不会。

---

## 下一步

- **Day 13-14**：重构 `cicd_testing.py` 为结构化结果契约（替换 emoji 字符串匹配）。⚠️ 今天的 JUnit XML 正好是**热身** —— 你已经见过「机器可读的结果格式」长什么样，以及**格式转换会损失信息**（141 vs 122）。

- **今天新增的欠账**：
  - [ ] 缺陷线索：测试往 `models/mjcf/tmp/` 写文件，导致 `:ro` 挂载不可用（7 errors）
  - [ ] Jenkins 用 SCM 模式读 Jenkinsfile（用 `file://` 本地路径或 Gitea，避开 8 分钟克隆）
  - [ ] **写一个真正需要 GPU 的测试**（渲染回归/3DGS）—— ⚠️ **EGL 已就绪，缺的是需求那一侧**
  - [ ] **给 `glfw` 补一档**（开发者本机调试用，需 DISPLAY），把三档凑齐
  - [ ] **考虑把 `MUJOCO_GL` 的取值做成 pytest fixture 参数**，让同一批渲染测试在两个后端各跑一遍（**跨后端一致性**才是 EGL 真正能带来的测试价值）
  - [ ] Jenkins 定时触发（等确定机器常开时段）

- **老欠账**（未动，见 checkpoint-day10-11 §七）：
  - [ ] `task_base.py` 28% —— **仍是最大覆盖率盲区**
  - [ ] `defect-report.md` 缺 §廿九、§三十
  - [ ] `discoverse/__init__.py:11` 无效转义序列

**记得写 `docs/checkpoint/checkpoint-day12.md`** —— 老规矩，每条标注「已核实 / 待核实」，记下被推翻的推断（累计 20 条，今天计划文档被推翻了 8 条，**这是单日最多的一次**）。

⚠️ 关于基线数字：**今天做完，`122 passed` 必须保持不变** —— 而且**两个渲染后端都必须是这个数**。今天只加了 `Jenkinsfile` 和 `Dockerfile.test.gpu`，一行测试代码都没碰。

📌 **「换了渲染后端但数字不动」正是验收信号** —— 说明换后端是等价变换。数字要是动了，说明 EGL 那条路改变了被测行为，**那才是真问题**。

📌 **如果数字动了，第一嫌疑是 §6.3 那个故意失败的用例没删干净。**
