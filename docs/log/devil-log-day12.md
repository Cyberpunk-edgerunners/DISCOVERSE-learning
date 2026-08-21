# 魔鬼日志 · Day 12（2026-08-17）

> Jenkins 辅线 —— 本机 GPU 回归 + 渲染后端企业化改造
> 上接 [devil-log-day10-11.md](devil-log-day10-11.md)
> 体例：按实际发生顺序记录，**包括走错的路**。

---

## 开工状态

```
分支 feat/test-infra，与远端同步（6263899）
本机基线 122 passed, 4 skipped, 45 deselected, 15 xfailed
GitHub Actions 5-job 全绿（Day 10-11 产出）
```

⚠️ **注意一个矛盾**：checkpoint-day10-11 写着「工作区干净、已推送」，但实际 `docs/checkpoint/`、`docs/log/`、`docs/note/` 三个 Day 10-11 文件**一直没提交**。

📌 **文档声明与现实不符 —— 这本身就是今天主题的预演**，而且是自己写的文档。

---

## 一、开课前核实：计划文档 8 处照抄必炸

老规矩，先把计划文档 §Day 12 每条实跑一遍。**这次是历史最高纪录 —— 8 条全错。**

| 计划写的 | 实测 |
|---|---|
| `git url: 'git@github.com:...'`（SSH） | Jenkins 容器里 `/root/.ssh` 和 `/var/jenkins_home/.ssh` **都不存在** |
| `conda activate discoverse` | 容器里 `python3: not found` —— **纯 Java 环境，没有 Python** |
| `agent { docker { ... } }` | **`docker-workflow` 插件未安装**（89 个插件里没有）→ 语法直接报错 |
| `MUJOCO_GL = 'glfw'` | 无 DISPLAY，必崩（Day 8-9 同款） |
| `pytest tests/simulation` | 只有 5 个用例（Day 10-11 那个假绿灯） |
| `junit 'test-results/*.xml'` | 路径对，但**没人生成这个文件** |
| `0 3 * * *` 每天凌晨 3 点 | **机器那时候是关的** → 静默不跑 |
| `git clone`（未提及耗时） | 实测 **8 分钟只下 37/308 MB**，手动中断 |

**再说一次**：计划文档写于项目之外。**具体环境长什么样，只有实跑才知道。**

---

## 二、第一件事：搞清 Jenkins 是什么形态

```bash
systemctl status jenkins
# → Unit jenkins.service could not be found.
```

❌ 不是系统服务。

```bash
docker ps
# → 09409de0d618  jenkins/jenkins:lts  Up 10 hours  0.0.0.0:8080->8080/tcp  jenkins_server
```

✅ **Jenkins 本身是个容器。** 这决定了今天的一切。

### 2.1 摸清容器里有什么

```bash
docker exec jenkins_server sh -c 'which git docker python3 java'
# /usr/bin/git
# /usr/bin/docker
# /opt/java/openjdk/bin/java
#   ⚠️ python3 无输出
```

```bash
docker exec jenkins_server sh -c 'docker ps'
# → 输出里【包含它自己】
```

⭐ **容器里跑 `docker ps` 看到了自己** —— 说明它在指挥宿主机的 Docker。

```bash
docker inspect jenkins_server --format '{{json .Mounts}}'
```

三个挂载，每个都有用：

| 挂载 | 作用 |
|---|---|
| `/usr/bin/docker` | 宿主机的 docker **命令** |
| `/var/run/docker.sock` | ⭐ 宿主机 docker 的**控制通道** |
| `/home/ubuntu22/robot_platform/jenkins_home` → `/var/jenkins_home` | 数据目录 |

📌 **这是 DooD（兄弟容器）不是 DinD（嵌套）。** 起出来的容器和 Jenkins **平级**，归宿主机 dockerd 管。

⚠️ **挂载列表里没有项目目录** —— 这一点当时没在意，第 5 节付出了代价。

---

## 三、⭐ 路径陷阱：第一次亲手复现

写了个「天经地义」的实验：容器内写文件，再挂进兄弟容器读。

```groovy
mkdir -p /var/jenkins_home/probe
echo HELLO_FROM_JENKINS > /var/jenkins_home/probe/marker.txt
cat /var/jenkins_home/probe/marker.txt                    # → HELLO_FROM_JENKINS ✅
docker run --rm -v /var/jenkins_home/probe:/mnt alpine cat /mnt/marker.txt
```

实测：

```
cat: can't open '/mnt/marker.txt': No such file or directory
```

⚠️ **`docker run` 本身没报错** —— 它成功挂了一个**空目录**，是 `cat` 才失败。

**根因**：`-v` 的源路径由**宿主机 dockerd** 解析。宿主机上：

- `/home/ubuntu22/robot_platform/jenkins_home` ← 真实存在
- `/var/jenkins_home` ← **不存在**（那是容器内的名字）

⚠️ **Docker 遇到源路径不存在时不报错，而是「帮你」创建一个空目录。**

```bash
ls -la /var/jenkins_home
# drwxr-xr-x 2 root root 4096 probe     ← 宿主机上凭空多出来的，root 所有
```

**修法**：`-v` 左边写宿主机路径 → `HELLO_FROM_JENKINS` ✅

> 📌 **规则：`sh` 步骤用容器路径，`docker run -v` 左边用宿主机路径。同一个目录，两个名字。**

---

## 四、代码从哪来：克隆方案被实测否决

### 4.1 SSH 不通，但 HTTPS 通

```bash
docker exec jenkins_server sh -c 'ls -la /root/.ssh; ls /var/jenkins_home/.ssh'
# → 两个都 No such file or directory
```

```bash
docker exec jenkins_server sh -c 'git ls-remote https://github.com/.../DISCOVERSE-learning.git HEAD'
# → 8893a8c63de1...   ✅ 公开仓库，HTTPS 免密可读
```

### 4.2 但克隆慢到不可用

```bash
git count-objects -vH | grep size-pack
# size-pack: 308.34 MiB
```

在 Jenkins 里跑 `git clone --depth 1`：**8 分钟后只下了 37 MB**，手动中断。

📌 **对比**：GitHub Actions 克隆同一仓库十几秒 —— **微软 runner 和 GitHub 在同一数据中心**，而你家宽带要跨太平洋。

⚠️ **「本地 CI 更快」是个想当然，对大仓库恰恰相反。**

### 4.3 决策：挂载本地工作区

代码就在这台机器上，没必要绕地球一圈。

⚠️ **代价必须写明**：测的是**工作区现状（含未提交改动）**，不是 git 里的确定版本。

**对策**：pipeline 里强制打印 `git status --short`，**把「可能测的是脏代码」每次构建都写进日志**。

> 这是「决定不做」和「假装没看见」的分水岭。

---

## 五、⭐ 直面 GPU：链条断在第四层

### 5.1 GPU 能透进容器

```bash
docker run --rm --gpus all discoverse:test nvidia-smi --query-gpu=name --format=csv,noheader
# → NVIDIA GeForce RTX 4060 Laptop GPU  ✅
```

### 5.2 但 MuJoCo 用不上

```bash
docker run --rm --gpus all -e MUJOCO_GL=egl discoverse:test python -c "import mujoco; ..."
```

```
File ".../OpenGL/raw/EGL/_types.py", line 87
    raw_eglQueryString = _p.PLATFORM.EGL.eglQueryString
AttributeError: 'NoneType' object has no attribute 'eglQueryString'
```

⚠️ **崩在 `import mujoco`，连模型都没建** —— 是**后端加载失败**，不是渲染失败。

```bash
docker run --rm discoverse:test sh -c 'ls /usr/lib/x86_64-linux-gnu/ | grep -iE "EGL|osmesa"'
# libOSMesa.so, libOSMesa.so.6, libOSMesa.so.8, libOSMesa.so.8.0.0
#   ⚠️ 一个 libEGL 都没有
```

📌 **这是 Day 8-9 决策的必然结果** —— 当时为 GitHub Actions（无 GPU）特意做了 CPU + osmesa 瘦镜像，那个决策是对的。

---

## 六、EGL 改造：三次尝试才通

### 6.1 第一次：只装 libegl1 —— 失败

```dockerfile
RUN apt-get install -y libegl1 libgles2 libglvnd0
```

报错从 `AttributeError` 变成了：

```
OpenGL.raw.EGL._errors.EGLError
```

**进展了（库找到了），但仍不通。**

### 6.2 排查：直接问 EGL 选了谁

```bash
docker run --rm --gpus all discoverse:egl-probe sh -c 'ls /usr/share/glvnd/egl_vendor.d/'
# → 50_mesa.json          ⚠️ 只有 Mesa

docker run --rm --gpus all discoverse:egl-probe sh -c 'ls /usr/lib/x86_64-linux-gnu/ | grep -i EGL'
# → libEGL_nvidia.so.0    ⭐ NVIDIA 的库【在】！
# → libnvidia-eglcore.so.580.95.05
```

⭐ **根因锁定**：nvidia-container-toolkit **注入了 `libEGL_nvidia.so`，却没注入 GLVND 的 vendor 配置**。libEGL 只认得 `50_mesa.json`，压根不知道 NVIDIA 的存在。

### 6.3 第二次：手写 vendor JSON —— 通了

```dockerfile
RUN mkdir -p /usr/share/glvnd/egl_vendor.d && \
    printf '{\n    "file_format_version" : "1.0.0",\n    "ICD" : {\n        "library_path" : "libEGL_nvidia.so.0"\n    }\n}\n' \
    > /usr/share/glvnd/egl_vendor.d/10_nvidia.json
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics
```

```bash
docker run --rm --gpus all -e MUJOCO_GL=egl discoverse:test-gpu python -c "..."
# → EGL 渲染成功 (480, 640, 3) mean=29.8 -> 1561 FPS
```

### 6.4 实测数据

| 后端 | FPS（480×640×100帧） | 画面均值 |
|---|---|---|
| `osmesa` CPU | **54 ~ 57** | 29.9 |
| **`egl` GPU** | **1561 ~ 1701** | 29.8 |

⭐ **31 倍，且画面均值一致** —— 说明是**等价变换**，不是「渲染错了所以快」。

**体积代价**（实测）：

```
discoverse:test      1475.35 MB
discoverse:test-gpu  1477.25 MB
差值                 +1.90 MB (+0.13%)
```

**全量测试两个后端均 `122 passed`。**

### 6.5 ⚠️ 一个噪声：退出时的 EGLError

```
File ".../mujoco/egl/__init__.py", line 131, in free
OpenGL.raw.EGL._errors.EGLError
```

发生在 `__del__` 析构里，**渲染早已成功**（`Renderer 创建成功` 和 FPS 都打印了）。

**对策**：小脚本用 `os._exit(0)` 绕开。**pytest 全量不受影响**（122 passed 就是证据），不改任何测试代码。

---

## 七、⭐ 我自己的探针写错了

给用户的 vendor 探针漏了 `eglInitialize`：

```
EGLError(err = EGL_NOT_INITIALIZED, baseOperation = eglQueryString, ...)
```

⚠️ **当时手上有两个矛盾证据**：

| 证据 | 指向 |
|---|---|
| `1701 FPS` | GPU 渲染在工作 |
| `EGLError` | EGL 坏了 |

⭐ **该信性能数字** —— Mesa 软渲染物理上到不了 1701（它只有 54）。报错只说明**探针写错了**，不代表被探测对象有问题。

**修法**：补上 `EGL.eglInitialize(d, ctypes.byref(maj), ctypes.byref(minor))`。

```
EGL 1 . 5
EGL vendor = b'NVIDIA'
```

> 📌 **排查时先问：是被测对象坏了，还是我的测量工具坏了？**
> **这正是这三周反复出现的主题** —— `tests/kinematics` 空目录、被覆盖的重复函数，都是「测量工具本身没被验证」。

---

## 八、Jenkinsfile 五轮迭代（构建 #1 → #10）

### 8.1 #1 三行 Hello —— 成功

先确认「Jenkins 能执行东西」，再往上加。

```
whoami → root
pwd    → /var/jenkins_home/workspace/DISCOVERSE-GPU-Regression
docker --version → 29.1.5
```

### 8.2 #2 路径实验 —— 故意失败

见第三节。

### 8.3 #3 路径修复版 —— 成功

错误写法和正确写法**并排跑**，同一次构建里对比最强烈。

### 8.4 #5 完整版第一跑 —— 一次暴露四个问题

```
+ echo === 后端  / 镜像 discoverse:test ===        ← ① 变量空
+ [  = egl ]
nvidia-smi: not found                              ← ② 容器里没装
cd: can't cd to /home/ubuntu22/workspaces/...      ← ③ 看不到项目目录
hudson.AbortException: No test report files ...    ← ④ post 二次抛异常
（十几行 Java 栈）
```

| # | 根因 | 修法 |
|---|---|---|
| ① | `params.X` 不是环境变量 | `environment { RENDER_BACKEND = "${params.RENDER_BACKEND}" }` |
| ② | Jenkins 容器只有 git/docker/java | 删掉这行，交给兄弟容器 |
| ③ | ⭐ **项目目录没挂进 Jenkins 容器** | 用 `docker run -v` + `alpine/git` |
| ④ | `allowEmptyResults: false` | 改 `true` |

⚠️ **① 最阴**：`[ "" = egl ]` 恒假 → **选了 egl 却跑 osmesa，全绿不报错**。它是被 ③ 「救」出来的 —— 要不是 `cd` 失败让构建变红，这个静默 bug 会一直藏着。

⚠️ **③ 的两个附加坑**（实测）：

```
git: 'sh' is not a git command              ← alpine/git 的 entrypoint 是 git，要 --entrypoint sh
fatal: detected dubious ownership in ...    ← 要 git config --global --add safe.directory /repo
```

### 8.5 ⭐ #7 最阴的一次：SUCCESS 但报告是空的

```
Running on Jenkins in /var/jenkins_home/workspace/DISCOVERSE-GPU-Regression@2
                                                                          ↑↑
-v .../jenkins_home/workspace/DISCOVERSE-GPU-Regression/test-results:/out
                                                      ↑ 没有 @2
...
122 passed, 4 skipped, 45 deselected, 15 xfailed
No test report files were found. Configuration error?
Finished: SUCCESS
```

**根因**：并发构建时 Jenkins 分配 `@2` workspace，而 `WS_ON_HOST` 是用 `${JOB_NAME}` 硬拼的 —— **JOB_NAME 不含 `@2`**。

实测确认 XML 确实生成了，只是在隔壁：

```bash
find .../workspace/ -name results.xml
# .../DISCOVERSE-GPU-Regression/test-results/results.xml  (22227 bytes)  ← 写对了，找错了
```

**修法（两条一起）**：

```groovy
WS_ON_HOST = "${WORKSPACE.replace('/var/jenkins_home', '/home/ubuntu22/robot_platform/jenkins_home')}"
options { disableConcurrentBuilds() }
```

> ⭐ **通用规律：同一个东西有两个名字时，永远从一个【推导】出另一个，别两边各写一份硬编码。**
> 两份硬编码在正常情况下看起来一模一样 —— 直到一个没预料到的后缀出现，**而分叉时没有任何报错**。

### 8.6 #8 / #9 两档验收 —— 全绿

| | #8 `egl` | #9 `osmesa` |
|---|---|---|
| 镜像 | `discoverse:test-gpu` | `discoverse:test` |
| 后端自检 | `EGL 1.5 vendor = b'NVIDIA'` | `CPU 软渲染路径` |
| **libEGL** | **4** | **0** |
| 结果 | `122 passed` **2.83s** | `122 passed` **3.08s** |

⭐ **`libEGL: 4 vs 0` 证明参数真的换了镜像**，不只是换了个字符串。

⚠️ **注意耗时：egl 档只快 0.25s，几乎没差** —— 31 倍渲染加速在端到端上收益接近零，因为 122 个用例几乎不渲染。

### 8.7 #10 故意弄红 —— 验证失败路径

```
1 failed, 122 passed, 4 skipped, 45 deselected, 15 xfailed
Recording test results          ← ⭐ FAILURE 的构建里【照样】收了报告
Archiving artifacts
Finished: FAILURE
```

⭐ **这是 `post { always { junit } }` 存在的全部理由。** 若写成 `post { success { } }`，此刻两手空空 —— **而这恰恰是最需要报告的时刻。**

**意外收获**：「代码状态」stage 当场抓到脏代码：

```
 M tests/unit/test_smoke.py
```

📌 §4.3 加那行 `git status --short` 的价值被证实了 —— 半年后看这次构建，会立刻知道「#10 测的不是干净代码」。

---

## 九、收尾

```bash
git checkout tests/unit/test_smoke.py
source scripts/dev/env.sh && $PY -m pytest tests/ -q | tail -1
# → 122 passed, 4 skipped, 45 deselected, 15 xfailed   ✅ 回到基线
grep -c "deliberate_failure" tests/unit/test_smoke.py   # → 0
```

**提交**：

```
8c14d67  build: 新增 GPU 测试镜像（EGL 无头渲染）
802fbe1  ci: 新增 Jenkins GPU 回归流水线（Day 12）
```

⚠️ **踩到一个小坑**：新终端没 `source scripts/dev/env.sh`，`$PY` 为空，命令变成 `-m pytest ...` → `-m: command not found`。**`source` 只在当前终端窗口有效。**

⚠️ **清理时又撞一次 root 权限**：容器以 root 写的 `.pytest_cache` / `@2` 目录，普通用户删不掉。**用 `docker run --rm -v ... alpine rm -rf` 清 —— 谁造的谁清。**

---

## 十、今天走错的路（完整清单）

| # | 走错的 | 代价 | 修正 |
|---|---|---|---|
| 1 | 照抄计划文档的 SSH clone | — | 改 HTTPS，最终改挂载 |
| 2 | 试图在 Jenkins 里 clone | **8 分钟** | 改挂载本地工作区 |
| 3 | 只装 libegl1 就以为够了 | 一次构建 | 补 `10_nvidia.json` |
| 4 | **vendor 探针漏 eglInitialize** | 一次误判 | 补初始化 |
| 5 | `params.X` 直接用在 sh 里 | 静默走错分支 | 桥接进 environment |
| 6 | `cd ${REPO_ON_HOST}` | 构建失败 | 改兄弟容器 |
| 7 | `nvidia-smi` 写在 Jenkins 侧 | 误导性文案 | 删掉 |
| 8 | `allowEmptyResults: false` | 真错因被埋 | 改 true |
| 9 | **`WS_ON_HOST` 用 JOB_NAME 硬拼** | **SUCCESS 但报告空** | 从 WORKSPACE 推导 |
| 10 | 挂载加 `:ro` | 7 errors | 去掉 |

📌 **10 条里有 6 条是我自己在实施过程中犯的，不是计划文档的锅。**

> **一次暴露四个问题的失败，比一次只暴露一个的失败更值钱。**
