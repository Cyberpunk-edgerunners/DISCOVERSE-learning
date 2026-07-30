"""9 个机械臂配置的契约测试。

分三层：
  1. 配置文件自身的字段完整性与自洽性（不加载 MuJoCo，unit）
  2. 配置与 MJCF 的一致性（需编译 XML，integration）
  3. 已知缺陷的 xfail 记录（可执行的缺陷报告）
"""
import pytest

from discoverse.universal_manipulation.robot_config import RobotConfigLoader

ROBOTS = [
    "airbot_play", "arx_l5", "arx_x5", "iiwa14", "panda",
    "piper", "rm65", "ur5e", "xarm7",
]

# qpos_dim 与 MJCF 实际 nq 不符的机器人（实测 2026-07-30）
# 格式: robot -> (YAML 声明值, MJCF 实际值)
# 详见缺陷 H。修好配置后从这里删掉，测试会自动开始守护它。
QPOS_DIM_MISMATCH = {
    "arx_x5": (7, 8),
    "iiwa14": (9, 15),
    "piper":  (7, 8),
    "rm65":   (12, 14),
}


@pytest.fixture(scope="session")
def load_robot(robot_config_dir):
    """按名字加载机器人配置，会话级缓存（YAML 解析结果只读）。"""
    cache = {}

    def _load(name):
        if name not in cache:
            cache[name] = RobotConfigLoader(str(robot_config_dir / f"{name}.yaml"))
        return cache[name]

    return _load


# ============================================================
# 第 1 层：配置自身（unit，无 MuJoCo）
# ============================================================

@pytest.mark.unit
@pytest.mark.parametrize("robot_name", ROBOTS)
def test_robot_name_matches_filename(load_robot, robot_name):
    """配置里的 robot_name 必须与文件名一致，否则按名字查找会静默取到错的机器人。"""
    assert load_robot(robot_name).robot_name == robot_name


@pytest.mark.unit
@pytest.mark.parametrize("robot_name", ROBOTS)
def test_joint_count_matches_names_length(load_robot, robot_name):
    """整数计数必须等于名字列表长度。

    绕开缺陷 E 的命名争议，直接断言两个字段互相自洽。
    """
    loader = load_robot(robot_name)
    assert loader.arm_joints_count == len(loader.arm_joint_names)


@pytest.mark.unit
@pytest.mark.parametrize("robot_name", ROBOTS)
def test_ctrl_dim_covers_arm_and_gripper(load_robot, robot_name):
    """ctrl_dim == 手臂关节数 + 夹爪控制维度。

    已实测 9/9 成立（6+1=7 与 7+1=8 两种情况都覆盖）。
    """
    loader = load_robot(robot_name)
    expected = loader.arm_joints_count + loader.gripper["ctrl_dim"]
    assert loader.ctrl_dim == expected, (
        f"{robot_name}: ctrl_dim={loader.ctrl_dim} "
        f"!= arm({loader.arm_joints_count}) + gripper({loader.gripper['ctrl_dim']})"
    )


@pytest.mark.unit
@pytest.mark.parametrize("robot_name", ROBOTS)
def test_end_effector_site_is_nonempty_string(load_robot, robot_name):
    """末端执行器 site 名是 IK 求解的锚点，为空会导致运行时才炸。"""
    site = load_robot(robot_name).end_effector_site
    assert isinstance(site, str) and site.strip()


# ============================================================
# 第 2 层：配置 vs MJCF（integration，需编译 XML）
#
# YAML 是人写的描述，MJCF 编译结果是物理引擎的事实。
# 不一致时 MJCF 是真相 —— IK 按 YAML 的维度切 qpos 数组，
# 维度错了就会静默取错关节。
# ============================================================

@pytest.mark.integration
@pytest.mark.parametrize("robot_name", ROBOTS)
def test_ctrl_dim_matches_mjcf_nu(load_robot, mj_model_factory, repo_root, robot_name):
    """ctrl_dim 必须等于 MJCF 编译出的执行器数 nu。

    这一维度维护得好（9/9 通过），因为写错会立刻炸：
    data.ctrl[:] = 长度不符的数组 -> ValueError。
    """
    xml = repo_root / "models" / "mjcf" / "manipulator" / f"robot_{robot_name}.xml"
    model = mj_model_factory(xml)
    declared = load_robot(robot_name).ctrl_dim
    assert model.nu == declared, (
        f"{robot_name}: YAML ctrl_dim={declared}, MJCF nu={model.nu}"
    )


@pytest.mark.integration
@pytest.mark.parametrize("robot_name", ROBOTS)
def test_qpos_dim_matches_mjcf_nq(load_robot, mj_model_factory, repo_root, robot_name):
    """qpos_dim 必须等于 MJCF 编译出的 nq。

    缺陷 H：4/9 不符（arx_x5, iiwa14, piper, rm65）。

    这类错误不抛异常 —— qpos[:9] 在 nq=15 的模型上完全合法，
    只是静默丢掉后 6 个关节。IK 拿到残缺状态却照样算出"看起来合理"
    的解，机器人动到错误位置，全程无报错。

    对比 ctrl_dim（9/9 通过）：会炸的字段维护得好，
    不会炸的字段积累错误。
    """
    if robot_name in QPOS_DIM_MISMATCH:
        declared, actual = QPOS_DIM_MISMATCH[robot_name]
        pytest.xfail(f"缺陷 H：{robot_name} 声明 qpos_dim={declared}，MJCF nq={actual}")

    xml = repo_root / "models" / "mjcf" / "manipulator" / f"robot_{robot_name}.xml"
    model = mj_model_factory(xml)
    assert model.nq == load_robot(robot_name).qpos_dim


# ============================================================
# 第 3 层：缺陷 E —— 属性名与 YAML 键交叉错位
#   YAML  arm_joints (int)   <-> Python  arm_joints_count
#   YAML  arm_joint_names    <-> Python  arm_joints (list)
#
# 源码自身是自洽的（类型注解 List[str] 与 docstring 都正确），
# 问题在跨层命名冲突会诱导误用 —— 严重度定为「中，可维护性」，
# 而非功能缺陷。证据：计划文档 L350 的示例就被误导了。
# ============================================================

@pytest.mark.unit
@pytest.mark.parametrize("robot_name", ROBOTS)
def test_arm_joints_current_behavior_returns_names(load_robot, robot_name):
    """钉死【当前】行为：arm_joints 返回名字列表，而非计数。"""
    value = load_robot(robot_name).arm_joints
    assert isinstance(value, list)
    assert all(isinstance(j, str) for j in value)


# ============================================================
# 错误处理
# ============================================================

@pytest.mark.unit
def test_missing_file_raises_filenotfound(robot_config_dir):
    """缺文件必须是明确的 FileNotFoundError，不能是 None 或空配置。"""
    with pytest.raises(FileNotFoundError):
        RobotConfigLoader(str(robot_config_dir / "no_such_robot.yaml"))


@pytest.mark.unit
def test_missing_required_field_raises(tmp_path):
    """缺必填字段必须在加载期报错（快速失败），而不是拖到运行时。

    tmp_path 是 pytest 内置 fixture：每个用例独立的临时目录，自动清理。
    写"坏配置"测试时用它，不要污染仓库。
    """
    bad = tmp_path / "broken.yaml"
    bad.write_text("robot_name: broken\n", encoding="utf-8")
    with pytest.raises((ValueError, KeyError)):
        RobotConfigLoader(str(bad))


# ============================================================
# MMK2 占位（完整测试见 Day 15-17）
# ============================================================

@pytest.mark.integration
def test_mmk2_mjcf_loads_with_expected_dof(mj_model_factory, repo_root):
    """MMK2 烟雾测试：模型能加载，且执行器数符合文档描述的 19 DOF。

    文档（CLAUDE.md）描述的 19 维动作空间：
        [0:2]   左右轮速度（差速驱动）
        [2]     升降高度
        [3:5]   头部云台（俯仰+偏航）
        [5:11]  左臂 6 轴
        [11:17] 右臂 6 轴
        [17:19] 左右夹爪

    只验证维度，不验证语义。目的是早期预警：
    若 MJCF 被改坏或文档与实际不符，现在就知道，
    而不是等到 Day 15-17 开工才踩坑。
    """
    xml = repo_root / "models" / "mjcf" / "mmk2_floor.xml"
    model = mj_model_factory(xml)
    assert model.nu == 19, (
        f"文档描述 MMK2 为 19 DOF，MJCF 实际 nu={model.nu}。"
        f"需核对是文档过时还是模型变更。"
    )
