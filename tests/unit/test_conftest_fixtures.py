"""conftest 中 fixture 的自检。

fixture 是懒加载的：没有用例请求它就永不执行。
本文件确保每个根级 fixture 至少被求值一次，
否则 conftest 里的错误会一直潜伏到某个真实用例第一次用到它。
"""
import pytest


@pytest.mark.unit
def test_repo_root_points_at_real_repo(repo_root):
    """repo_root 必须指向真正的仓库根，而非 tests/ 或 cwd。"""
    assert (repo_root / "discoverse").is_dir()
    assert (repo_root / "pyproject.toml").is_file()


@pytest.mark.unit
def test_config_dirs_exist(robot_config_dir, task_config_dir):
    assert robot_config_dir.is_dir(), f"机器人配置目录不存在: {robot_config_dir}"
    assert task_config_dir.is_dir(), f"任务配置目录不存在: {task_config_dir}"


@pytest.mark.unit
def test_robot_config_dir_has_nine_yamls(robot_config_dir):
    """9 个机械臂配置，数量变化应被显式感知（新增机器人时这条会红，提醒你更新 ROBOTS 列表）。"""
    yamls = sorted(p.stem for p in robot_config_dir.glob("*.yaml"))
    assert len(yamls) == 9, f"预期 9 个，实际 {len(yamls)}: {yamls}"


@pytest.mark.integration
def test_mj_model_factory_loads_and_caches(mj_model_factory, repo_root):
    """MjModel 工厂：能加载真实 MJCF，且同一路径返回同一对象（缓存生效）。"""
    xml = repo_root / "models" / "mjcf" / "manipulator" / "robot_airbot_play.xml"
    m1 = mj_model_factory(xml)
    m2 = mj_model_factory(xml)
    assert m1 is m2, "session 级缓存未生效，同一 XML 被重复编译"
    assert m1.nq > 0, "模型没有自由度，XML 可能没加载对"


@pytest.mark.integration
def test_mj_data_factory_isolates_state(mj_data_factory, repo_root):
    """MjData 工厂：两次调用必须返回不同实例，但共享同一个 model。

    这条直接验证 function 级作用域的意义 —— 状态隔离。
    """
    xml = repo_root / "models" / "mjcf" / "manipulator" / "robot_airbot_play.xml"
    model_a, data_a = mj_data_factory(xml)
    model_b, data_b = mj_data_factory(xml)

    assert model_a is model_b, "model 应复用（只读）"
    assert data_a is not data_b, "data 必须独立（可变），否则测试间状态污染"

    # 证明状态确实隔离：改 a 不影响 b
    data_a.qpos[0] = 0.5
    assert data_b.qpos[0] != 0.5
