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