"""MMK2 双臂协同：自碰撞检测与执行器布局。

⚠️ 计划文档的自碰撞测试是【空转】的：
    geom1 = mj_model.geom(contact.geom1).name
    if "left_arm" in geom1 and "right_arm" in geom2: ...

    实测 73 个 geom 里只有 11 个有名字，手臂上的全部无名 ——
    该条件恒为 False，测试永远通过且从未检测过任何东西。
    这类"空转绿测试"比红测试危险：红测试至少会引起注意。

⭐ 因此本文件先写【元测试】（证明检测器能工作），再写安全测试。
   没有元测试的话，安全测试通过可能是"真的没碰"，
   也可能是"检测器坏了" —— 两者无法区分。
"""

import mujoco
import pytest

from .conftest import (
    CTRL_LFT_ARM,
    CTRL_LFT_GRIPPER,
    CTRL_LIFT,
    CTRL_RGT_ARM,
    CTRL_RGT_GRIPPER,
    CTRL_WHEELS,
    arm_side,
    cross_arm_contacts,
    step_with_ctrl,
)

pytestmark = [pytest.mark.integration]

SETTLE_STEPS = 4000

# 实测会导致左右手指互撞的位形（双臂向内收拢）。
POSE_COLLIDING = [0.0, -1.5, 1.5, 0.0, 0.0, 0.0]

# 双臂垂放，互不干涉。
POSE_SAFE = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


def pose_arms(model, data, left_q, right_q, slide=0.3, steps=SETTLE_STEPS):
    """摆好双臂位形并步进到稳定，返回跨臂接触集合。"""
    ctrl = data.ctrl.copy()
    ctrl[:] = 0.0
    ctrl[CTRL_LIFT] = slide
    ctrl[CTRL_LFT_ARM] = left_q
    ctrl[CTRL_RGT_ARM] = right_q
    step_with_ctrl(model, data, ctrl, steps)
    return cross_arm_contacts(model, data)


def test_actuator_layout_is_pinned(mmk2_model):
    """钉死 19 维执行器布局。

    ⚠️ CLAUDE.md 的布局是错的：它写 action[11:17] 是右臂、
       action[17:19] 是双夹爪 —— 从第 11 位起整体错位一格，
       且把夹爪写成 2 个（实际是 1 个 tendon 执行器带动两指）。
       交叉验证见 mmk2_base.py:178-184 的打印函数。

    本测试让"MJCF 改了但文档没改"立刻可见。
    """
    expected = [
        (0, "lft_wheel_motor"),
        (1, "rgt_wheel_motor"),
        (2, "lift"),
        (3, "head_yaw"),
        (4, "head_pitch"),
        (5, "lft_joint1"),
        (10, "lft_joint6"),
        (11, "lft_gripper"),
        (12, "rgt_joint1"),
        (17, "rgt_joint6"),
        (18, "rgt_gripper"),
    ]

    assert mmk2_model.nu == 19, f"执行器数应为 19，实为 {mmk2_model.nu}"

    for idx, name in expected:
        actual = mujoco.mj_id2name(mmk2_model, mujoco.mjtObj.mjOBJ_ACTUATOR, idx)
        assert actual == name, f"执行器 {idx} 应为 {name}，实为 {actual}"

    # 夹爪是 tendon 传动（trntype=3），各占【一个】执行器。
    for idx in (CTRL_LFT_GRIPPER, CTRL_RGT_GRIPPER):
        assert mmk2_model.actuator_trntype[idx] == mujoco.mjtTrn.mjTRN_TENDON

    # 轮子力矩范围 ±35 N·m —— 与 test_differential_drive 的建模假设一致。
    for idx in range(CTRL_WHEELS.start, CTRL_WHEELS.stop):
        lo, hi = mmk2_model.actuator_ctrlrange[idx]
        assert (lo, hi) == pytest.approx((-35.0, 35.0))


def test_arm_side_resolves_unnamed_geoms(mmk2_model):
    """⭐ 元测试之一：证明"按 body 祖先链归属"确实可用。

    实测 73 个 geom 里 62 个无名，所以必须能把无名 geom 归到左/右臂。
    若此断言失败，cross_arm_contacts 就是瞎的，
    下面所有碰撞测试的结论都不可信。
    """
    named = sum(
        1
        for i in range(mmk2_model.ngeom)
        if mujoco.mj_id2name(mmk2_model, mujoco.mjtObj.mjOBJ_GEOM, i)
    )
    assert named < mmk2_model.ngeom, "前提变了：geom 现在都有名字了，本方案可简化"

    sides = [arm_side(mmk2_model, i) for i in range(mmk2_model.ngeom)]
    assert sides.count("L") > 0, "没有任何 geom 被归到左臂 —— 归属逻辑失效"
    assert sides.count("R") > 0, "没有任何 geom 被归到右臂 —— 归属逻辑失效"

    # 必须有【无名】geom 被成功归属，否则等于退化成按名字匹配。
    unnamed_resolved = sum(
        1
        for i in range(mmk2_model.ngeom)
        if sides[i] and not mujoco.mj_id2name(mmk2_model, mujoco.mjtObj.mjOBJ_GEOM, i)
    )
    assert unnamed_resolved > 0, "无名 geom 全部未能归属 —— 退化为按名字匹配"


def test_self_collision_detector_actually_detects(mmk2_model, mmk2_data):
    """⭐⭐ 核心元测试：已知会碰的位形必须被检出。

    这是下面"安全位形"测试的前提。若本测试通过而安全测试也通过，
    后者才可信；否则"没检出碰撞"可能只是检测器坏了。

    实测该位形产生的跨臂接触：
        (lft_finger_right_link, rgt_finger_left_link)
        (lft_finger_left_link,  rgt_finger_right_link)
    """
    hits = pose_arms(mmk2_model, mmk2_data, POSE_COLLIDING, POSE_COLLIDING)
    assert hits, "检测器失效：已知碰撞位形却报告无跨臂接触"


def test_safe_pose_has_no_self_collision(mmk2_model, mmk2_data):
    """双臂垂放位形不应有自碰撞。

    ⚠️ 不要断言 data.ncon == 0：机器人站在地上，
       轮子与 floor 的接触恒存在（实测双臂对撞时 ncon=8，其中 4 个是地面）。
       必须按"双方都属手臂且分属左右"筛选。
    """
    hits = pose_arms(mmk2_model, mmk2_data, POSE_SAFE, POSE_SAFE)
    assert not hits, f"垂放位形出现意外自碰撞：{hits}"


def test_ground_contacts_exist_but_are_not_self_collision(mmk2_model, mmk2_data):
    """钉住"地面接触不算自碰撞"这条筛选逻辑。

    若有人把 cross_arm_contacts 简化成"ncon > 0 即碰撞"，本测试会红。
    """
    hits = pose_arms(mmk2_model, mmk2_data, POSE_SAFE, POSE_SAFE)
    assert mmk2_data.ncon > 0, "机器人应当与地面有接触"
    assert not hits, "地面接触被误判为自碰撞"
