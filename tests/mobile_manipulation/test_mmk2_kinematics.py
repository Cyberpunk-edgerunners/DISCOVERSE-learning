"""MMK2 双臂运动学：FK→IK→FK 往返一致性。

判定标准（工业机器人运动学标定的迁移）：
    往返测的不是"IK 准不准"，而是"FK 和 IK 用的是不是同一个模型"。
    真机上这两者可能来自不同来源（FK 来自 URDF，IK 来自厂商固件），
    参数不一致时单独看每个都对，串起来就飘。

实测容差依据（2026-08-19）：
    往返最大关节误差 9.7e-05 rad（解析解的浮点残差量级）
    → 取实测值的 10 倍作为断言容差：1e-3 rad

⚠️ 计划文档 §Day 15-17 步骤 1 的示例代码全部不可用：
    get_armjoint_pose_wrt_footprint / solve_mmk2_ik 这两个自由函数不存在，
    arm='left' 也不是合法取值（真实取值是 'l' / 'r'）。
"""

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from .conftest import quat_wxyz_to_matrix, world_to_footprint

pytestmark = [pytest.mark.integration]

# 往返容差：实测 9.7e-05 rad，取 10 倍余量。
# 1e-6 会必红（低于解析解浮点残差），1e-2 太松（符号错误可能漏过）。
ROUNDTRIP_ATOL = 1e-3

# 一组落在双臂可达空间内的关节角（实测 IK 可解）。
Q_SAMPLE = np.array([0.1, -0.2, 0.3, 0.1, 0.2, 0.1])


@pytest.fixture(scope="module")
def fk():
    """MMK2 正运动学（基于 MuJoCo 模型）。"""
    from discoverse.robots.mmk2.mmk2_fk import MMK2FK

    return MMK2FK()


@pytest.fixture(scope="module")
def ik():
    """MMK2 逆运动学。

    ⚠️ 刻意用 MMK2IK 而非 MMK2FIK：
      - MMK2FIK 已被上游标记弃用（mmk2_fik.py:72 打印告警）
      - MMK2FIK 只能从 pick/carry/look 三个预设动作里挑姿态，
        那测的是查找表不是运动学；MMK2IK 直接吃 3x3 旋转矩阵。
    """
    from discoverse.robots.mmk2.mmk2_ik import MMK2IK

    return MMK2IK()


def fk_endpoint(fk, arm, q, slide, base_pos=(0, 0, 0), base_quat=(1, 0, 0, 0)):
    """摆好位形后取末端位姿（world 系）。

    ⚠️ 必须先调 set_*：MMK2FK.__init__ 从未初始化 self.pos_modifidied，
       而每个 getter 都读它（mmk2_fk.py:118）。直接调 getter 会
       AttributeError。见 test_fk_getter_before_setter_raises。
    """
    fk.set_base_pose(list(base_pos), list(base_quat))
    fk.set_slide_joint(slide)
    fk.set_head_joints([0, 0])
    fk.set_left_arm_joints(q if arm == "l" else np.zeros(6))
    fk.set_right_arm_joints(q if arm == "r" else np.zeros(6))
    fk.forward_kinematics()

    if arm == "l":
        return fk.get_left_endeffector_pose()
    return fk.get_right_endeffector_pose()


def roundtrip_error(fk, ik, arm, q, slide, base_pos=(0, 0, 0), base_quat=(1, 0, 0, 0)):
    """FK→(坐标变换)→IK，返回最大关节角误差。"""
    pos_w, quat_w = fk_endpoint(fk, arm, q, slide, base_pos, base_quat)
    rot_w = quat_wxyz_to_matrix(quat_w)
    pos_f, rot_f = world_to_footprint(pos_w, rot_w, np.asarray(base_pos), base_quat)
    solution = np.asarray(ik.armIK_wrt_footprint(pos_f, rot_f, arm, slide, q))
    return np.abs(solution - q).max()


@pytest.mark.parametrize("arm", ["l", "r"])
def test_fk_ik_roundtrip_closes(fk, ik, arm):
    """基础往返：底盘在原点，双臂各自闭合。"""
    err = roundtrip_error(fk, ik, arm, Q_SAMPLE, slide=0.0)
    assert err < ROUNDTRIP_ATOL, f"{arm} 臂往返误差 {err:.3e} 超出 {ROUNDTRIP_ATOL}"


@pytest.mark.parametrize("slide", [0.0, 0.1, 0.3, 0.5, 0.87])
def test_fk_ik_roundtrip_across_slide_range(fk, ik, slide):
    """沿升降轴全行程扫描，往返必须处处闭合。

    ⭐ 这条测的是 FK 与 IK 对 slide 符号约定的一致性。
       mmk2_ik.py:63 用的是 tmat[2,3] -= slide；若有人改成 +=，
       单独跑 IK 不会报错（照样解得出关节角），只有本测试会红。
    """
    err = roundtrip_error(fk, ik, "l", Q_SAMPLE, slide=slide)
    assert err < ROUNDTRIP_ATOL, f"slide={slide} 往返误差 {err:.3e}"


def test_slide_lowers_torso(fk):
    """升降语义：slide 增大 → 末端 Z 降低（反直觉，必须钉住）。

    执行器名叫 "lift"，但数值越大躯干越低。实测 slide 0→0.87
    末端 Z 从 1.235 降到 0.365，正好差 0.87。
    """
    z_at = {}
    for slide in (0.0, 0.87):
        pos, _ = fk_endpoint(fk, "l", Q_SAMPLE, slide)
        z_at[slide] = pos[2]

    drop = z_at[0.0] - z_at[0.87]
    assert drop == pytest.approx(0.87, abs=1e-3), (
        f"slide 行程与末端 Z 降幅不符：降了 {drop:.5f}，应为 0.87"
    )


def test_roundtrip_with_base_off_origin(fk, ik):
    """⭐ 底盘不在原点时往返仍须闭合 —— 本文件最有价值的一条。

    FK 返回 world 系，IK 吃 footprint 系。底盘在原点且无旋转时
    两个坐标系数值上恰好相等，于是"忘记做坐标变换"的实现也能通过
    上面所有用例。只有把底盘挪开才会暴露。

    实测：不做变换时这两个位形都会让 IK 抛 ValueError（误报不可达）。
    """
    base_pos = (1.0, 0.5, 0.0)
    base_quat = Rotation.from_euler("z", np.pi / 2).as_quat()[[3, 0, 1, 2]]

    err = roundtrip_error(
        fk, ik, "l", Q_SAMPLE, slide=0.0, base_pos=base_pos, base_quat=base_quat
    )
    assert err < ROUNDTRIP_ATOL, (
        f"底盘位移+旋转后往返误差 {err:.3e} —— 检查 world→footprint 变换"
    )


def test_unreachable_target_raises(ik):
    """不可达目标必须抛 ValueError，而不是静默返回垃圾。

    钉住当前的好行为，防止将来有人"优化"成返回 None ——
    那会把一个响亮的失败变成静默失败。
    """
    with pytest.raises(ValueError):
        ik.armIK_wrt_footprint(np.array([5.0, 0.0, 1.2]), np.eye(3), "l", 0.0)


def test_invalid_arm_raises(ik):
    """非法臂标识必须抛 ValueError。

    顺带钉住取值域是 'l'/'r' —— 计划文档写的 arm='left' 会走到这里。
    """
    with pytest.raises(ValueError):
        ik.armIK_wrt_footprint(np.array([0.4, 0.1, 1.2]), np.eye(3), "left", 0.0)


def test_ik_tmats_cache_matches_mjcf():
    """回归护栏：IK 的缓存变换矩阵必须与从 MJCF 现算的一致。

    ⚠️ 这不是一条已发生的缺陷 —— 实测当前 maxdiff=0，缓存是对的。
       它防的是将来：mmk2_ik.py:13-19 用裸 except 加载 mmk2_ik_tmats.npz，
       缓存文件不带版本戳。若有人改了 MJCF 里的臂基座位置，
       这个 .npz 不会失效，IK 会继续用旧变换且不报错（静默失效）。

    本测试今天不抓 bug，它让明天的 MJCF 改动变红。
    """
    from discoverse.robots.mmk2.mmk2_ik import MMK2IK

    solver = MMK2IK()
    fresh = solver.generate_tmats()

    for key, cached in (
        ("footprint2chest", solver.TMat_footprint2chest),
        ("chest2lft_base", solver.TMat_chest2lft_base),
        ("chest2rgt_base", solver.TMat_chest2rgt_base),
    ):
        np.testing.assert_allclose(
            cached,
            fresh[key],
            atol=1e-9,
            err_msg=f"{key} 缓存与 MJCF 不一致 —— 删除 mmk2_ik_tmats.npz 重新生成",
        )


@pytest.mark.xfail(
    reason="缺陷 Z：MMK2FK.__init__ 未初始化 pos_modifidied，"
    "直接调 getter 会 AttributeError（mmk2_fk.py:9-13 vs :118）",
    strict=True,
)
def test_fk_getter_before_setter_raises():
    """钉住缺陷 Z：构造后直接读位姿应当可用，实际会炸。

    今天不修：改动属于上游文件，且有明确规避方式（先调任一 set_*）。
    注意属性名拼写是 pos_modifidied（原文如此），贯穿全文件，
    "顺手修正"会把所有 setter 一起打断。
    """
    from discoverse.robots.mmk2.mmk2_fk import MMK2FK

    MMK2FK().get_left_endeffector_pose()
