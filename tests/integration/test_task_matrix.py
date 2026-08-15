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

ROBOTS = [
    "airbot_play",
    "arx_l5",
    "arx_x5",
    "iiwa14",
    "panda",
    "piper",
    "rm65",
    "ur5e",
    "xarm7",
]
TASKS = [
    "cover_cup",
    "place_block",
    "place_coffeecup",
    "place_kiwi_fruit",
    "stack_block",
]

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
        return {
            "bucket": "SUCCESS",
            "state": m_state.group(0) if m_state else None,
            "dist": dist,
        }

    if m_state is None:
        # 没跑到统计阶段 —— 崩溃
        return {"bucket": "BUCKET4_配置崩溃", "state": None, "dist": None}

    done, total = int(m_state.group(1)), int(m_state.group(2))
    if done < total:
        return {
            "bucket": "BUCKET1_早期IK失败",
            "state": f"{done}/{total}",
            "dist": dist,
        }
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
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=TIMEOUT_S,
        env={**os.environ, "MUJOCO_GL": "osmesa"},
        check=False,  # 本用例靠 returncode 分类，非零是预期输入而非异常
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
