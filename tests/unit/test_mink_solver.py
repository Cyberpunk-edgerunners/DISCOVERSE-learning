"""MinkIKSolver 的状态隔离契约。

判定标准（见 devil-note-day04.md）：
    调用 N 次后的输出，是否只由第 N 次的输入决定？

实测（2026-08-04）：
    self.configuration      -> 不泄漏（solve_ik:99 每次入口被 update 覆盖）
    self.posture_task target -> 【泄漏】（:120 只在给 reference 时更新，否则沿用）
"""

import os

import mujoco
import numpy as np
import pytest

pytestmark = [pytest.mark.integration]

ROBOT = "airbot_play"
TASK = "place_block"


@pytest.fixture(scope="module")
def solver_env(task_config_dir):
    """构造 IK 求解器所需的模型 / 配置 / 参考位姿。

    module 级：make_env + 模型编译不便宜，而本文件的用例
    都只【读】这些对象，真正可变的 solver 在每个用例里新建。
    """
    from discoverse import DISCOVERSE_ASSETS_DIR
    from discoverse.envs.make_env import make_env
    from discoverse.universal_manipulation.robot_config import RobotConfigLoader

    xml = os.path.join(DISCOVERSE_ASSETS_DIR, "mjcf", "tmp", f"{ROBOT}_{TASK}.xml")
    make_env(ROBOT, TASK, xml)

    model = mujoco.MjModel.from_xml_path(xml)
    data = mujoco.MjData(model)
    robot_config = RobotConfigLoader(
        str(task_config_dir.parent / "robots" / f"{ROBOT}.yaml")
    )

    if model.nkey == 0:
        pytest.skip("模型无 keyframe，MinkIKSolver 构造会失败")

    home_qpos = model.key(0).qpos.copy()
    data.qpos[:] = home_qpos
    mujoco.mj_forward(model, data)

    site_id = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_SITE, robot_config.end_effector_site
    )
    assert site_id >= 0, f"找不到末端 site: {robot_config.end_effector_site}"

    return {
        "model": model,
        "data": data,
        "robot_config": robot_config,
        "home_qpos": home_qpos,
        # 取当前末端位姿做基准 —— 保证目标可达。
        # 随手编一个坐标很可能不可达，届时 converged=False，
        # 测试红了却和状态泄漏无关。
        "ee_pos": data.site_xpos[site_id].copy(),
        "ee_mat": data.site_xmat[site_id].reshape(3, 3).copy(),
    }


@pytest.fixture
def make_solver(solver_env):
    """每个用例新建 solver —— 它持有可变状态，绝不能跨用例复用。"""
    from discoverse.universal_manipulation.mink_solver import MinkIKSolver

    def _make():
        return MinkIKSolver(
            solver_env["robot_config"], solver_env["model"], solver_env["data"]
        )

    return _make


def test_repeated_solve_is_deterministic(solver_env, make_solver):
    """【已核实不泄漏】同参数连续调用两次，解应相同。

    这条守的是 self.configuration —— solve_ik:99 每次入口
    self.configuration.update(current_qpos) 已经隔离了它。
    计划文档要求加 try/finally 恢复 configuration，实测【不需要】。

    这条测试的价值是【防止有人日后把那行 update 删掉】。
    """
    solver = make_solver()
    target = solver_env["ee_pos"] + np.array([0.08, 0.0, 0.0])

    first, _, _ = solver.solve_ik(target, solver_env["ee_mat"], solver_env["home_qpos"])
    second, _, _ = solver.solve_ik(
        target, solver_env["ee_mat"], solver_env["home_qpos"]
    )

    np.testing.assert_allclose(first, second, atol=0, rtol=0)


# @pytest.mark.xfail(
#     strict=True,
#     reason="缺陷 U：mink_solver.py:120 的 posture_task target 只在 "
#            "reference_qpos is not None 时更新，没有 else 分支恢复默认。"
#            "先传一次 reference 之后，后续【不传 reference】的调用会沿用它 —— "
#            "同样的输入得到不同的输出。与 self.configuration 不同，"
#            "它没有『每次入口重置』的保护。",
# )
def test_posture_target_does_not_leak_across_calls(solver_env, make_solver):
    """【回归】reference_qpos 不应污染后续不传 reference 的调用。

    判定：调用 N 次后的输出，是否只由第 N 次的输入决定？
    第 1 次和第 3 次输入完全相同（同 target、同 qpos、都不给 reference），
    所以输出必须相同。

    缺陷 U（Day 4 修复）：mink_solver.py:120 原本只有 if 分支，
    传过一次 reference 之后后续调用会沿用它。修复是补 else 分支，
    恢复到构造时记住的 _default_posture_qpos。
    """
    solver = make_solver()
    target = solver_env["ee_pos"] + np.array([0.08, 0.0, 0.0])
    ori = solver_env["ee_mat"]
    home = solver_env["home_qpos"]

    reference = home.copy()
    reference[:6] += 0.3  # 一个明显不同的参考构型

    first, _, _ = solver.solve_ik(target, ori, home)
    solver.solve_ik(target, ori, home, reference_qpos=reference)  # 污染源
    third, _, _ = solver.solve_ik(target, ori, home)

    np.testing.assert_allclose(
        third,
        first,
        atol=0,
        rtol=0,
        err_msg="第 3 次调用与第 1 次输入完全相同，解却不同 —— "
        "posture_task target 被第 2 次调用污染",
    )


def test_default_posture_target_is_home_not_qpos0(solver_env, make_solver):
    """不传 reference 时，posture 目标应是构造时的 home，而非模型 qpos0。

    【这条测试来自一次失败的变异验证】（Day 4）：
    注释掉 solve_ik 里的 else 分支后，test_posture_target_does_not_leak
    仍然全绿 —— 说明它没能守住完整契约。

    原因：真正消除泄漏的是把 set_target_from_configuration 挪出 if 块。
    挪出后，不传 reference 时 temp_config 保持新建状态，
    而 mink.Configuration(model) 的默认值是【qpos0】（airbot_play 为全 0），
    不是 key(0).qpos（home，[0,-1,1.2,1.5708,-1.2,-1.5708]）。
    两者都不泄漏，但默认姿态取谁是另一个契约 —— 那是行为变更，不是修复。

    else 分支的作用因此不是「修泄漏」，而是「保持原有默认行为」：
    构造时 _setup_ik_tasks 用的就是 key(0).qpos。
    """
    import mink

    solver = make_solver()
    home = solver_env["home_qpos"]

    # 不传 reference_qpos
    solver.solve_ik(solver_env["ee_pos"], solver_env["ee_mat"], home)

    expected = mink.Configuration(solver_env["model"])
    expected.update(home)
    n = len(solver.posture_task.target_q)

    np.testing.assert_allclose(
        solver.posture_task.target_q,
        expected.q[:n],
        atol=0,
        rtol=0,
        err_msg="不传 reference 时 posture 目标不是 home —— "
        "可能退化成了 qpos0（else 分支缺失或失效）",
    )
