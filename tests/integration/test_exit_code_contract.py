"""退出码契约的回归测试（Day 13-14，守护缺陷 #2 的修复）。

为什么这是最重要的一个测试文件
-----------------------------
CI 判断步骤成败的唯一依据就是退出码。修复前，任务失败时退出码仍为 0，
流水线永远绿灯 —— 一个不会红的测试比没有测试更危险，因为它制造虚假信心。

本文件用"必然失败的 seed"和"必然成功的 seed"两个输入，
断言退出码确实随任务成败改变。

⚠️ 这个测试之所以写得出来，完全依赖缺陷 #1（seed 未贯穿）已被修复：
   没有可复现的 seed，就构造不出"必然失败"的输入。
"""

import json
import os
import subprocess
import sys

import pytest
import yaml

from discoverse import DISCOVERSE_ROOT_DIR

pytestmark = [pytest.mark.integration, pytest.mark.slow]

RUNTIME = os.path.join(DISCOVERSE_ROOT_DIR,
                       "examples/universal_tasks/universal_task_runtime.py")
TASK_YAML = os.path.join(DISCOVERSE_ROOT_DIR,
                         "discoverse/configs/tasks/place_block.yaml")

# 实测标定：airbot_play + place_block 下，seed 42 必成，seed 13 必败。
SEED_PASS, SEED_FAIL = 42, 13
TIMEOUT_S = 300


@pytest.fixture
def task_seed(request):
    """临时把 place_block 的 seed 改成指定值，测试结束后恢复原文件。

    直接改配置文件而非传参，是因为 seed 目前只能经 YAML 注入；
    用 fixture 保证即使断言失败也会还原，不污染工作区。
    """
    seed = request.param
    with open(TASK_YAML, encoding="utf-8") as f:
        original = f.read()
    cfg = yaml.safe_load(original)
    cfg.setdefault("randomization", {}).setdefault("settings", {})["seed"] = seed
    with open(TASK_YAML, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
    try:
        yield seed
    finally:
        with open(TASK_YAML, "w", encoding="utf-8") as f:
            f.write(original)


def run_task(result_json=None):
    cmd = [sys.executable, RUNTIME, "-r", "airbot_play", "-t", "place_block",
           "-1", "--headless"]
    if result_json:
        cmd += ["--result-json", result_json]
    env = dict(os.environ, MUJOCO_GL="osmesa")
    # check=False：非零退出码正是本文件要断言的对象，不能让它抛异常
    return subprocess.run(cmd, capture_output=True, text=True, check=False,
                          timeout=TIMEOUT_S, cwd=DISCOVERSE_ROOT_DIR, env=env)


@pytest.mark.parametrize("task_seed,expected_rc",
                         [(SEED_PASS, 0), (SEED_FAIL, 1)],
                         indirect=["task_seed"])
def test_exit_code_reflects_task_outcome(task_seed, expected_rc):
    """退出码必须反映任务成败 —— CI 的唯一判定依据。"""
    proc = run_task()
    assert proc.returncode == expected_rc, (
        f"seed={task_seed} 期望退出码 {expected_rc}，实际 {proc.returncode}\n"
        f"stdout 尾部:\n" + "\n".join(proc.stdout.splitlines()[-15:])
    )


@pytest.mark.parametrize("task_seed", [SEED_FAIL], indirect=True)
def test_failure_writes_structured_result(task_seed, tmp_path):
    """失败运行必须留下结构化结果，且内容与退出码一致。"""
    out = tmp_path / "result.json"
    proc = run_task(result_json=str(out))

    assert proc.returncode == 1
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["success"] is False
    assert data["exit_code"] == 1
    assert data["seed"] == SEED_FAIL
    # 该 seed 下状态机能走完全部状态，失败发生在最终判据
    assert data["failure_mode"] == "final_check"
    assert data["completed_states"] == data["total_states"]


@pytest.mark.parametrize("task_seed", [SEED_PASS], indirect=True)
def test_success_writes_structured_result(task_seed, tmp_path):
    out = tmp_path / "result.json"
    proc = run_task(result_json=str(out))

    assert proc.returncode == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["success"] is True
    assert data["failure_mode"] is None
    assert data["completed_states"] == data["total_states"] > 0


def test_unknown_robot_is_config_error_not_task_failure():
    """未知机器人应以配置错误码退出，而非被记成一次普通的任务失败。"""
    cicd = os.path.join(DISCOVERSE_ROOT_DIR,
                        "examples/universal_tasks/cicd_testing.py")
    proc = subprocess.run(
        [sys.executable, cicd, "-r", "fake_robot", "-t", "place_block", "--serial"],
        capture_output=True, text=True, check=False,
        timeout=120, cwd=DISCOVERSE_ROOT_DIR)

    assert proc.returncode == 2, "未知机器人必须以 CONFIG_ERROR(2) 退出"
    assert "未知机器人" in proc.stderr
