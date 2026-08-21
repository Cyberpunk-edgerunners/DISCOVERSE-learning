"""MMK2 移动操作测试的共享 fixture 与几何工具。

被测对象：19 自由度双臂轮式机器人（2 轮 + 1 升降 + 2 头部 + 12 臂 + 2 夹爪）。

⚠️ 本目录的用例全部要加载 MJCF 并跑仿真步进，因此统一标 integration
（见 pyproject.toml 的 marker 定义："unit" 要求无 MuJoCo 依赖）。

⚠️ 不打 slow 标记：项目对 slow 的定义是"单用例 >10s"，
   实测本目录最慢的模块合计 ~2.9s 且分摊在 5 个用例上，单例远不够格。
   打了标记 = CI 主线跳过 = wheel_distance 缺陷在日常回归里隐身。
"""

import os

import mujoco
import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from discoverse import DISCOVERSE_ROOT_DIR

# ---------- 被测模型 ----------

MMK2_XML = os.path.join(DISCOVERSE_ROOT_DIR, "models", "mjcf", "mmk2_floor.xml")

# 实测的执行器布局（mj_id2name 逐个打印，2026-08-19）。
# ⚠️ 与 CLAUDE.md 不同：CLAUDE.md 从第 11 位起整体错位一格，
#    且把夹爪写成 2 个（实际是 1 个 tendon 执行器带动两指）。
#    交叉验证见 discoverse/robots_env/mmk2_base.py:178-184 的打印函数。
CTRL_WHEELS = slice(0, 2)  # 力矩 N·m，ctrlrange ±35
CTRL_LIFT = 2  # 位置，ctrlrange [-0.04, 0.87]，⚠️ 越大躯干越低
CTRL_HEAD = slice(3, 5)  # yaw, pitch
CTRL_LFT_ARM = slice(5, 11)
CTRL_LFT_GRIPPER = 11
CTRL_RGT_ARM = slice(12, 18)
CTRL_RGT_GRIPPER = 18

# 实测稳态所需步数：2000 步（4s 仿真时间）后升降残余变化 < 1e-5 m。
# 取 5000 留余量；再大会逼近 pyproject.toml 的 60s 用例超时。
LIFT_SETTLE_STEPS = 5000


# ---------- fixture ----------


@pytest.fixture(scope="session")
def mmk2_model(mj_model_factory):
    """MMK2 模型。

    复用根 conftest 的 session 级工厂（同一 XML 只编译一次）。
    只读，跨用例共享安全。
    """
    return mj_model_factory(MMK2_XML)


@pytest.fixture
def mmk2_data(mmk2_model):
    """每个用例一份全新的 MjData —— 绝不复用。

    MjData 持有 qpos/qvel/ctrl/time 等可变状态，跨用例复用会造成
    "上个用例把机器人开走了，这个用例从那开始"的测试间污染。

    ⚠️ 无需手动置底盘四元数：mj_resetData 从模型的 qpos0 恢复，
       实测 qpos[0:7] = [0,0,0,1,0,0,0]（四元数已是单位四元数）。
    """
    data = mujoco.MjData(mmk2_model)
    mujoco.mj_resetData(mmk2_model, data)
    mujoco.mj_forward(mmk2_model, data)
    return data


@pytest.fixture
def mmk2_model_data_factory(mmk2_model):
    """按需产出全新 MjData 的工厂。

    给"一个用例内需要多次独立仿真"的场景用（如扫描多个升降目标位）：
    每次调用都是干净状态，避免上一次的位形泄漏到下一次。
    """

    def _make():
        data = mujoco.MjData(mmk2_model)
        mujoco.mj_resetData(mmk2_model, data)
        mujoco.mj_forward(mmk2_model, data)
        return data

    return _make


@pytest.fixture(scope="session")
def wheel_geometry(mmk2_model):
    """从 MJCF 现算轮距与轮半径。

    ⭐ 刻意不使用 MMK2Base.wheel_distance —— 该常量为 0.189，
       与模型实测的 0.3265 不符（缺陷 Y，见 test_differential_drive.py）。
       测试若引用被测常量，就无法证伪该常量。
    """
    ys = []
    for name in ("lft_wheel_joint", "rgt_wheel_joint"):
        jid = mujoco.mj_name2id(mmk2_model, mujoco.mjtObj.mjOBJ_JOINT, name)
        assert jid >= 0, f"模型里找不到关节 {name}"
        ys.append(mmk2_model.body_pos[mmk2_model.jnt_bodyid[jid]][1])

    return {
        "wheel_distance": float(abs(ys[0] - ys[1])),  # 实测 0.3265
        "wheel_radius": 0.0838,  # 网格几何，非 body_pos 可得
    }


# ---------- 几何工具 ----------


def qpos_adr(model, joint_name):
    """取关节在 qpos 里的起始下标。

    ⚠️ 不要数格子：底盘自由关节占 7 个 qpos（3 位置 + 4 四元数）
       但只占 6 个 qvel —— 这正是 nq=28 而 nv=27 的原因。
       计划文档把升降写成 qpos[2]，那其实是底盘 Z；升降在 qpos[9]。
    """
    jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, joint_name)
    assert jid >= 0, f"模型里找不到关节 {joint_name}"
    return model.jnt_qposadr[jid]


def quat_wxyz_to_matrix(quat_wxyz):
    """MuJoCo 的 wxyz 四元数 → 3x3 旋转矩阵。

    ⚠️ 约定不一致：MuJoCo / MMK2FK 返回 [w,x,y,z]，
       scipy 的 from_quat 要 [x,y,z,w]。写反不会报错，
       只会得到一个合法但错误的旋转 —— 只有往返测试抓得到。
    """
    return Rotation.from_quat(np.asarray(quat_wxyz)[[1, 2, 3, 0]]).as_matrix()


def world_to_footprint(pos_w, rot_w, base_pos, base_quat_wxyz):
    """世界系位姿 → footprint（底盘）系位姿。

    ⭐ 这个变换是必需的，不是可选的：
       MMK2FK.get_*_endeffector_pose() 返回 world 系，
       而 MMK2IK.armIK_wrt_footprint() 吃 footprint 系。
       底盘在原点且无旋转时两者数值上恰好相等 —— 于是"不做变换"的
       测试会通过。一旦底盘移动就错，且是静默给出错误答案。
    """
    t_w_base = np.eye(4)
    t_w_base[:3, :3] = quat_wxyz_to_matrix(base_quat_wxyz)
    t_w_base[:3, 3] = base_pos

    t_w_ee = np.eye(4)
    t_w_ee[:3, :3] = rot_w
    t_w_ee[:3, 3] = pos_w

    t_base_ee = np.linalg.inv(t_w_base) @ t_w_ee
    return t_base_ee[:3, 3], t_base_ee[:3, :3]


def body_chain(model, body_id):
    """从 body 一路向上追溯到 worldbody，返回名字列表。"""
    names = []
    while body_id > 0:
        names.append(
            mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id) or "?"
        )
        body_id = model.body_parentid[body_id]
    return names


def arm_side(model, geom_id):
    """判断 geom 属于左臂 / 右臂 / 都不是，返回 "L" / "R" / None。

    ⭐ 为什么走 body 祖先链而不是 geom 名字：
       实测 73 个 geom 里只有 11 个有名字，手臂上的 geom 全部无名。
       计划文档的 `if "left_arm" in geom1` 恒为 False —— 空转绿测试。
       命名靠人自觉，body 父子关系由物理模型强制，后者可靠得多。
    """
    for name in body_chain(model, model.geom_bodyid[geom_id]):
        if name.startswith(("lft_arm", "lft_finger")):
            return "L"
        if name.startswith(("rgt_arm", "rgt_finger")):
            return "R"
    return None


def cross_arm_contacts(model, data):
    """返回所有"左臂 geom 与右臂 geom"之间的接触，元素为 (body名, body名)。

    ⚠️ 不要直接断言 d.ncon == 0：机器人站在地上，
       轮子与 floor 的接触恒存在（实测双臂对撞时 ncon=8，其中 4 个是地面）。
    """
    hits = set()
    for i in range(data.ncon):
        con = data.contact[i]
        side1, side2 = arm_side(model, con.geom1), arm_side(model, con.geom2)
        if side1 and side2 and side1 != side2:
            hits.add(
                (
                    body_chain(model, model.geom_bodyid[con.geom1])[0],
                    body_chain(model, model.geom_bodyid[con.geom2])[0],
                )
            )
    return hits


def step_with_ctrl(model, data, ctrl, n_steps):
    """保持 ctrl 恒定，步进 n_steps。

    每步都重设 ctrl：位置执行器会保持上次的值，但显式重设让
    "这段仿真期间施加了什么"在代码里一目了然。
    """
    for _ in range(n_steps):
        data.ctrl[:] = ctrl
        mujoco.mj_step(model, data)


def base_yaw(data):
    """底盘偏航角（rad），从自由关节四元数取。"""
    return Rotation.from_quat(data.qpos[[4, 5, 6, 3]]).as_euler("xyz")[2]
