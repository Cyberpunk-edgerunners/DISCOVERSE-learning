"""MMK2 升降轴：定位精度与重力下垂特征。

⚠️ 计划文档的两处错误：
    actual_h = mj_data.qpos[2]     → qpos[2] 是底盘 Z，升降在 qpos[9]
    assert abs(err) < 0.005        → 实测稳态误差 6.06mm，必红

⭐ 6.06mm 不是缺陷，是位置伺服的固有重力下垂：
    误差 ≈ 重力负载 / kp，无积分项的位置环必然有静差。
    识别依据是误差的【结构】而非大小 —— 五个目标位的误差
    在六位小数上完全相同（0.006063），是恒定偏置而非随机噪声。
"""

import mujoco
import numpy as np
import pytest

from .conftest import CTRL_LIFT, LIFT_SETTLE_STEPS, qpos_adr

pytestmark = [pytest.mark.integration]

# 定位容差：实测稳态误差 6.06mm，取 10mm（约 65% 余量）。
LIFT_POS_ATOL = 0.010

# 下垂一致性容差：五个目标位的误差极差。实测 < 1e-5。
DROOP_PTP_ATOL = 1e-4

# 升降行程（ctrlrange 实测 [-0.04, 0.87]）。
# ⚠️ 不是 CLAUDE.md 写的 [0, 0.87]：有 4cm 负向余量。
LIFT_MIN, LIFT_MAX = -0.04, 0.87


def settle_lift(model, data, target, steps=LIFT_SETTLE_STEPS):
    """把升降开到 target 并跑到稳态，返回实际关节位置。"""
    adr = qpos_adr(model, "slide_joint")
    for _ in range(steps):
        data.ctrl[:] = 0.0
        data.ctrl[CTRL_LIFT] = target
        mujoco.mj_step(model, data)
    return float(data.qpos[adr])


def test_lift_joint_is_not_qpos_2(mmk2_model):
    """钉住升降的 qpos 下标 —— 计划文档把它写成 qpos[2]。

    底盘自由关节占 qpos[0:7]（3 位置 + 4 四元数），
    qpos[2] 是底盘 Z。升降在 qpos[9]。
    """
    assert qpos_adr(mmk2_model, "slide_joint") == 9


def test_lift_ctrlrange_has_negative_margin(mmk2_model):
    """钉住升降行程 [-0.04, 0.87]（CLAUDE.md 写成 [0, 0.87]）。"""
    lo, hi = mmk2_model.actuator_ctrlrange[CTRL_LIFT]
    assert (lo, hi) == pytest.approx((LIFT_MIN, LIFT_MAX), abs=1e-6)


@pytest.mark.parametrize("target", [0.0, 0.2, 0.5, LIFT_MIN])
def test_lift_positioning_accuracy(mmk2_model, mmk2_data, target):
    """升降定位精度：稳态误差 < 10mm。

    ⚠️ 不含 0.87：该目标撞上关节上限被硬约束挡住，
       误差反而只有 0.4mm，不能代表伺服精度。
    """
    actual = settle_lift(mmk2_model, mmk2_data, target)
    err = abs(actual - target)
    assert err < LIFT_POS_ATOL, (
        f"目标 {target:.3f} m 实际 {actual:.5f} m，误差 {err * 1000:.2f} mm"
    )


def test_lift_droop_is_constant_bias_not_noise(mmk2_model, mmk2_model_data_factory):
    """⭐ 比精度更有价值的断言：下垂偏置在各高度必须一致。

    重力下垂是系统性的（误差 = 负载 / kp），所以各目标位的误差应当相同。
    若某个高度突然偏离，说明该处存在卡滞、碰撞或机构干涉 ——
    这是"精度 < 10mm"这条断言抓不到的故障。

    实测五个目标位误差均为 0.006063（六位一致），极差 < 1e-5。
    """
    errors = []
    for target in (0.0, 0.2, 0.5):
        data = mmk2_model_data_factory()
        errors.append(settle_lift(mmk2_model, data, target) - target)

    spread = float(np.ptp(errors))
    assert spread < DROOP_PTP_ATOL, (
        f"各高度下垂不一致（极差 {spread:.2e}），可能存在卡滞：{errors}"
    )

    # 下垂方向必须为正：slide 越大躯干越低，重力把它往下拽 →
    # 实际值总是比目标【大】。符号反了说明升降语义被改过。
    assert all(e > 0 for e in errors), f"下垂方向异常：{errors}"


def test_lift_settles_within_budget(mmk2_model, mmk2_model_data_factory):
    """稳定时间：2000 步后必须进入稳态。

    实测 target=0.2：500 步误差 0.0099（还在动），
    2000 步 0.006070，5000 步 0.006063 —— 2000 步后基本不动。

    ⚠️ 别把 500 步的读数当成"精度不够"，那是还没走完。
    """
    early = settle_lift(mmk2_model, mmk2_model_data_factory(), 0.2, steps=2000)
    late = settle_lift(mmk2_model, mmk2_model_data_factory(), 0.2, steps=5000)

    assert abs(early - late) < 1e-4, (
        f"2000 步尚未稳定：2000 步 {early:.6f} vs 5000 步 {late:.6f}"
    )


def test_out_of_range_command_is_clamped_in_physics(mmk2_model, mmk2_data):
    """超范围指令：物理上被限幅，但 ctrl 数组保留原值。

    ⚠️ 别写 assert data.ctrl[2] <= 0.87 —— 那会失败。
       actuator_ctrllimited=True 只影响施加到关节的力，不改写 ctrl 数组。
       要断言的是 qpos，不是 ctrl。

    ⚠️ 注意这与走 MMK2Base.updateControl 的路径行为不同：
       mmk2_base.py:193 自己做了一次 np.clip，那条路径下 ctrl 数组是干净的。
    """
    adr = qpos_adr(mmk2_model, "slide_joint")
    over = 2.0

    for _ in range(3000):
        mmk2_data.ctrl[:] = 0.0
        mmk2_data.ctrl[CTRL_LIFT] = over
        mujoco.mj_step(mmk2_model, mmk2_data)

    assert mmk2_data.ctrl[CTRL_LIFT] == pytest.approx(over), (
        "ctrl 数组被改写了 —— MuJoCo 的限幅不应修改 ctrl"
    )
    assert mmk2_data.qpos[adr] <= LIFT_MAX + 1e-3, (
        f"关节越过上限：{mmk2_data.qpos[adr]:.5f} > {LIFT_MAX}"
    )
