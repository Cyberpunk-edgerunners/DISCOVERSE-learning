import pytest


@pytest.mark.unit
def test_framework_alive():
    assert 1 + 1 == 2


@pytest.mark.unit
def test_no_ros_pollution_in_syspath():
    """测试环境不应混入 ROS 的 site-packages。

    背景：ROS Humble 的 setup.bash 导出 PYTHONPATH，优先级高于 conda
    环境隔离。已实测的两种崩溃方式（均发生在 pytest 启动/收集阶段，
    早于本断言执行）：
      1. launch_testing 作为 pytest11 插件被加载 -> 缺 lark -> ModuleNotFoundError
      2. launch_testing_ros_pytest_entrypoint 注册了 pytest 9 已移除的 hook
         -> PluginValidationError -> INTERNALERROR

    本断言守的是第三种、也是最隐蔽的一种：sys.path 被 .pth 文件、
    sitecustomize 或运行时代码污染，pytest 能正常启动，但 import 会
    静默取到错误版本的模块。这类污染没有断言就完全不可见。

    修复：source scripts/dev/env.sh（内含 unset PYTHONPATH）
    """
    import sys

    ros_paths = [p for p in sys.path if "/opt/ros/" in p]
    assert not ros_paths, (
        f"ROS 路径混入 sys.path: {ros_paths}\n"
        f"修复: source scripts/dev/env.sh (内含 unset PYTHONPATH)"
    )
