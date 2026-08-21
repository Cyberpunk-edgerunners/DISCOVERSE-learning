"""MMK2 差速底盘：直线度与里程计推算精度。

⚠️ 轮子是力矩执行器，不是速度执行器。
    models/mjcf/mobile_chassis/mmk2/mmk2_control.xml:3-4 用的是 <motor>
    （其余全是 <position>），ctrl 单位是 N·m。
    实测恒定 1.0 N·m 下轮速一路爬升 0.018 → 1.63 rad/s，永不恒定。

    这对测试设计是根本性的：不能断言"跑 N 步走 X 米"，
    必须从轮子编码器读数推算位姿，再与真值比对 ——
    这恰是真机里程计标定的做法（编码器 vs 激光跟踪仪）。

⭐ 本文件钉住缺陷 Y：MMK2Base.wheel_distance = 0.189，
   而 MJCF 实测轮距为 0.3265（±0.16325 × 2），错 1.73 倍。
"""

import mujoco
import numpy as np
import pytest

from .conftest import base_yaw

pytestmark = [pytest.mark.integration]

# 步进预算：4000 步 = 8s 仿真时间，实测约 0.47s 墙钟。
DRIVE_STEPS = 4000

# 里程计容差：用实测轮距时 yaw 误差 ≤ 0.0066 rad（原地旋转工况）。
# 取 0.05 rad 留一个量级余量。
ODOM_YAW_ATOL = 0.05
ODOM_POS_ATOL = 0.02

# 直线度：横向漂移 / 纵向位移。实测 0.05%，阈值取 5%。
STRAIGHTNESS_MAX = 0.05


def drive(model, data, torque_left, torque_right, wheel_distance, wheel_radius,
          steps=DRIVE_STEPS):
    """施加恒定轮力矩并逐步做差速里程计推算。

    返回 (odom_xytheta, truth_xytheta)。

    差速运动学：
        Δs = (Δs_left + Δs_right) / 2
        Δθ = (Δs_right - Δs_left) / L
    """
    # 轮子转角在 qpos[7:9]（底盘自由关节占 qpos[0:7]）。
    prev_phi = data.qpos[7:9].copy()
    odom = np.zeros(3)  # x, y, theta

    for _ in range(steps):
        data.ctrl[:] = 0.0
        data.ctrl[0] = torque_left
        data.ctrl[1] = torque_right
        mujoco.mj_step(model, data)

        phi = data.qpos[7:9].copy()
        d_phi = phi - prev_phi
        prev_phi = phi

        ds_l, ds_r = wheel_radius * d_phi[0], wheel_radius * d_phi[1]
        ds = (ds_l + ds_r) / 2.0
        d_theta = (ds_r - ds_l) / wheel_distance

        # 中点积分：用半步航向推进，比前向欧拉在转弯时准得多。
        odom[0] += ds * np.cos(odom[2] + d_theta / 2.0)
        odom[1] += ds * np.sin(odom[2] + d_theta / 2.0)
        odom[2] += d_theta

    truth = np.array([data.qpos[0], data.qpos[1], base_yaw(data)])
    return odom, truth


def test_wheel_torque_not_velocity(mmk2_model, mmk2_data):
    """钉住"轮子是力矩控制"这一前提。

    若将来有人把 <motor> 换成 <velocity>，本文件其余测试的
    建模假设就全部失效 —— 让这件事立刻可见，而不是让里程计测试
    以一个费解的方式变红。

    判据：恒定力矩下轮速必须持续增长（力矩→加速度），
          速度控制则会立刻稳定在目标值。
    """
    speeds = []
    for _ in range(4):
        for _ in range(500):
            mmk2_data.ctrl[:] = 0.0
            mmk2_data.ctrl[0] = 1.0
            mmk2_data.ctrl[1] = 1.0
            mujoco.mj_step(mmk2_model, mmk2_data)
        speeds.append(float(mmk2_data.qvel[6]))

    assert all(b > a for a, b in zip(speeds, speeds[1:])), (
        f"轮速未持续增长，执行器可能已从力矩改为速度控制：{speeds}"
    )


def test_straight_line_motion(mmk2_model, mmk2_data, wheel_geometry):
    """等力矩 → 直线：横向漂移 / 纵向位移 < 5%。

    ⚠️ 机器人沿 +x 前进，所以 x 是纵向、y 是横向。
       计划文档的 abs(d[0])/abs(d[1]) 把两者写反了，必然除以 ~0。
    """
    start = mmk2_data.qpos[:2].copy()
    drive(mmk2_model, mmk2_data, 1.0, 1.0, **wheel_geometry)
    displacement = mmk2_data.qpos[:2].copy() - start

    longitudinal = abs(displacement[0])
    lateral = abs(displacement[1])

    # ⭐ 前置断言：先证明机器人真的动了。
    # 没有它的话，"一步没动"会让 0/0 或 0/极小值 通过测试。
    # 凡是"比值 < 阈值"的断言，都必须先断言分母足够大。
    assert longitudinal > 0.1, (
        f"机器人几乎没有前进（{longitudinal:.4f} m），直线度测试无意义"
    )

    straightness = lateral / longitudinal
    assert straightness < STRAIGHTNESS_MAX, (
        f"直线度 {straightness:.2%} 超出 {STRAIGHTNESS_MAX:.0%}"
        f"（纵向 {longitudinal:.4f} m，横向 {lateral:.4f} m）"
    )


@pytest.mark.parametrize(
    ("torque_left", "torque_right", "label"),
    [
        (1.0, 1.0, "直线"),
        (1.0, 0.5, "缓转弯"),
        (1.0, -1.0, "原地旋转"),
    ],
)
def test_odometry_matches_ground_truth(
    mmk2_model, mmk2_data, wheel_geometry, torque_left, torque_right, label
):
    """里程计推算 vs MuJoCo 真值。

    ⭐ 仿真的独特价值：能同时拿到"机器人以为自己在哪"和"它实际在哪"。
       真机上这要靠激光跟踪仪 / OptiTrack。

    ⚠️ 本测试刻意使用从 MJCF 现算的轮距（wheel_geometry fixture），
       而非 MMK2Base.wheel_distance —— 后者是错的（见下面的 xfail）。
    """
    odom, truth = drive(
        mmk2_model, mmk2_data, torque_left, torque_right, **wheel_geometry
    )

    yaw_err = abs(odom[2] - truth[2])
    pos_err = float(np.linalg.norm(odom[:2] - truth[:2]))

    assert yaw_err < ODOM_YAW_ATOL, (
        f"[{label}] 偏航推算误差 {yaw_err:.4f} rad "
        f"（推算 {odom[2]:.4f} vs 真值 {truth[2]:.4f}）"
    )
    assert pos_err < ODOM_POS_ATOL, (
        f"[{label}] 位置推算误差 {pos_err:.4f} m "
        f"（推算 {odom[:2]} vs 真值 {truth[:2]}）"
    )


def test_straight_line_hides_wheel_distance_error(
    mmk2_model, mmk2_data, wheel_geometry
):
    """⭐ 证明"为什么必须用转弯工况标定轮距"。

    直线时 Δs_right - Δs_left = 0，轮距被乘以 0 —— 它错得再离谱
    也不影响直线里程计。这是工业 AGV 的常识：轮距标定必须用原地旋转。

    本测试同时是上面 xfail 的解释：错误的常量在直线上"看起来是对的"。
    """
    from discoverse.robots_env.mmk2_base import MMK2Base

    odom_wrong, truth = drive(
        mmk2_model,
        mmk2_data,
        1.0,
        1.0,
        wheel_distance=MMK2Base.wheel_distance,  # 错误的 0.189
        wheel_radius=wheel_geometry["wheel_radius"],
    )

    # 即便用错误轮距，直线工况下的位置推算依然准确。
    pos_err = float(np.linalg.norm(odom_wrong[:2] - truth[:2]))
    assert pos_err < ODOM_POS_ATOL, (
        f"前提不成立：直线工况本应对轮距不敏感，实测位置误差 {pos_err:.4f} m"
    )


@pytest.mark.xfail(
    reason="缺陷 Y：MMK2Base.wheel_distance = 0.189，"
    "而 MJCF 实测轮距为 0.3265（±0.16325 × 2），错 1.73 倍。"
    "影响 4 个 ROS 遥操作文件的 cmd_vel 逆解。",
    strict=True,
)
def test_wheel_distance_constant_matches_model(wheel_geometry):
    """钉住缺陷 Y：代码里的轮距常量必须与 MJCF 一致。

    实测影响（原地旋转，4000 步）：
        wheel_distance=0.189   → yaw 推算 -4.6005 vs 真值 -2.6565，误差 1.944 rad (111°)
        wheel_distance=0.3265  → yaw 推算 -2.6631 vs 真值 -2.6565，误差 0.0066 rad
        改善 294 倍。

    ⚠️ 今天刻意不修，因为该变量的语义本身是矛盾的：
        - 里程计公式按"全轮距"用它：Δθ = (Δs_r - Δs_l) / L
        - 4 个 ROS 文件按"半轮距"用它：v_l = (v - ω·L) / r（少除以 2）
          examples/ros{1,2}/mmk2_ros{1,2}{,_joy}.py
        只改数值会让其中一边从"错 73%"变成"错 50%"。
        正确修法是先消歧义（重命名 wheel_base / half_wheel_base）再统一取值，
        且要改 ROS 文件，需单独 PR 验证。
    """
    from discoverse.robots_env.mmk2_base import MMK2Base

    assert MMK2Base.wheel_distance == pytest.approx(
        wheel_geometry["wheel_distance"], abs=1e-4
    )
