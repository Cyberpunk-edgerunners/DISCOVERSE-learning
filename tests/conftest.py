"""
根级 fixture 定义。

conftest.py 是 pytest 的隐式插件文件：同目录及所有子目录的测试
自动可见这里定义的 fixture，无需 import。
"""
import os
from pathlib import Path

import pytest

# ---------- 路径类 fixture（session 级，纯常量） ----------

@pytest.fixture(scope="session")
def repo_root() -> Path:
    """仓库根目录。

    用 __file__ 反推而非 os.getcwd()：
    cwd 取决于用户在哪敲的 pytest，__file__ 不会变。
    """
    return Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def robot_config_dir(repo_root) -> Path:
    return repo_root / "discoverse" / "configs" / "robots"


@pytest.fixture(scope="session")
def task_config_dir(repo_root) -> Path:
    return repo_root / "discoverse" / "configs" / "tasks"


# ---------- MuJoCo fixture（作用域选择是本日重点） ----------

@pytest.fixture(scope="session")
def mj_model_factory():
    """MjModel 工厂 + 会话级缓存。

    为什么是 session 级：
      MjModel.from_xml_path 要解析 XML、加载 mesh/贴图、编译碰撞几何，
      单次可达数百 ms 到数秒。它是 *只读* 的编译产物，跨用例复用安全。

    为什么返回工厂函数而不是模型本身：
      不同用例要加载不同 XML。fixture 直接返回模型的话，
      一个 fixture 只能绑一个 XML。返回工厂 + 内部 dict 缓存，
      既能按需加载任意 XML，又保证同一 XML 只编译一次。
      这是 "factory as fixture" 模式。
    """
    import mujoco

    cache = {}

    def _make(xml_path):
        key = str(xml_path)
        if key not in cache:
            if not os.path.exists(key):
                pytest.skip(f"MJCF 不存在，跳过: {key}")
            cache[key] = mujoco.MjModel.from_xml_path(key)
        return cache[key]

    return _make


@pytest.fixture(scope="function")
def mj_data_factory(mj_model_factory):
    """MjData 工厂，function 级。

    为什么必须是 function 级：
      MjData 持有 qpos/qvel/ctrl/time 等 *可变* 仿真状态。
      若跨用例复用，用例 A 步进 1000 步后的状态会泄漏给用例 B，
      造成 "单跑绿、全跑红" 的经典测试间污染 —— 而且顺序一变就复现不了。
      MjData 构造很便宜（只分配数组），没有复用的必要。
    """
    import mujoco

    def _make(xml_path):
        model = mj_model_factory(xml_path)
        return model, mujoco.MjData(model)

    return _make
