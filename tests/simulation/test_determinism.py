"""确定性专项测试：配置里的 seed 是否真的生效。

本文件测的是【契约】而非【实现】：
    用户在 task YAML 里写 randomization.settings.seed: 42
    -> 两次运行应得到完全相同的场景

⚠️ 关键设计（详见 docs/tutorial/day03-step1-walkthrough.md 坑 C）：
   绝不能在测试里调 np.random.seed(42)。
   那样测试会【绿】—— 因为 randomization.py 消费的是全局 np.random，
   在外面 seed 全局当然确定。但真实用户走的是配置文件那条路，
   而那条路是断的。从错误的入口进去，测的是 numpy 不是本项目。
"""
import os

import mujoco
import numpy as np
import pytest

from discoverse.universal_manipulation.randomization import SceneRandomizer
from discoverse.universal_manipulation.task_config import TaskConfigLoader
from discoverse.universal_manipulation.config_utils import (
    load_and_resolve_config,
    replace_variables,
)

pytestmark = [pytest.mark.determinism, pytest.mark.integration]

ROBOT = "airbot_play"
TASK = "place_block"
# place_block 场景里仅有的两个自由体（实测 free_body_qpos_ids 确认）
FREE_BODIES = ["block_green", "bowl_pink"]


# ---------------------------------------------------------------- fixtures

@pytest.fixture(scope="session")
def task_xml(repo_root):
    """生成 robot x task 的 MJCF，返回路径。

    §0 坑 A：场景不是静态文件，是 make_env 现场拼出来的
    （9 机器人 x 5 任务 = 45 组合，不可能预存）。
    测试走和生产代码相同的构造路径，否则测的是自造场景。

    session 级：make_env 要读多个 XML 并做树合并，不便宜；
    产出是磁盘上的文件，只读复用安全。
    """
    from discoverse.envs.make_env import make_env
    from discoverse import DISCOVERSE_ASSETS_DIR

    xml_path = os.path.join(
        DISCOVERSE_ASSETS_DIR, "mjcf", "tmp", f"{ROBOT}_{TASK}.xml"
    )
    make_env(ROBOT, TASK, xml_path)
    if not os.path.exists(xml_path):
        pytest.skip(f"make_env 未产出 MJCF: {xml_path}")
    return xml_path


@pytest.fixture(scope="session")
def base_randomization_config(task_config_dir):
    """加载 place_block 的随机化配置（已解析 extends）。

    必须用加载器而非直接读 YAML —— Day 2 方法论第 7 条：
    静态读文件 != 运行时加载，extends 会改变最终内容。

    ⚠️ session 级 + 返回可变 dict：使用者必须 deepcopy（见 §4）。
    """
    cfg_path = str(task_config_dir / f"{TASK}.yaml")
    resolved = replace_variables(load_and_resolve_config(cfg_path))
    randomization = TaskConfigLoader.from_dict(resolved).randomization
    assert randomization is not None, f"{TASK} 没有 randomization 段，测试前提不成立"
    return randomization


# ---------------------------------------------------------------- helpers

def _randomize_once(xml_path, config, seed=None):
    """跑一次完整的场景随机化，返回所有自由体的位姿拼接结果。

    §3：每次调用都新建 MjData 和 SceneRandomizer。
    复用会导致状态泄漏 —— randomization.py 的 z 坐标沿用 mj_data
    当前值，第二次跑就不是从同一起点出发了。

    seed 走【构造参数】而非 config 字典：随机数生成器是有状态的，
    一个 randomizer 对应一条随机流。若在 exec_randomization 里重设 seed，
    连续调用两次会得到完全相同的场景 —— 那几乎肯定不是使用者想要的。
    真实调用链（task_base.py）同样是在构造时传入，
    由 test_task_base_wires_yaml_seed_to_randomizer 覆盖。

    返回: shape (14,) 的 float64 数组 = 2 个物体 x [x,y,z,qw,qx,qy,qz]
    """
    model = mujoco.MjModel.from_xml_path(xml_path)
    data = mujoco.MjData(model)
    mujoco.mj_resetData(model, data)
    # 必须 forward：_randomize_objects 要读 armbase site 的世界坐标，
    # 而 site 位置只有在前向运动学算过之后才有效。
    mujoco.mj_forward(model, data)

    randomizer = SceneRandomizer(model, data, seed=seed)
    randomizer.exec_randomization(config)

    return np.concatenate([
        np.asarray(randomizer._object_pose(name)).copy() for name in FREE_BODIES
    ])


def _assert_identical(first, second, context):
    """§5：先给人看得懂的诊断，再失败。"""
    if not np.array_equal(first, second):
        diff = np.abs(first - second)
        pytest.fail(
            f"{context}\n"
            f"  最大偏差: {diff.max():.9f}（期望 0，PRNG 是确定性算法）\n"
            f"  第一次:   {np.array2string(first, precision=6)}\n"
            f"  第二次:   {np.array2string(second, precision=6)}"
        )


# ---------------------------------------------------------------- 测试

def test_config_seed_makes_randomization_reproducible(
    task_xml, base_randomization_config
):
    """【核心】同一个 seed 两次随机化，结果应完全相同。

    Day 3 写下时是红灯：randomization.py 有 25 处裸 np.random.*，
    消费进程级全局随机流；settings.seed 声明于 6 处 YAML，零个读取者。

    Step 4 修复：SceneRandomizer 接受 seed 参数，
    建 np.random.default_rng(seed) 实例，25 处改用 self.rng.*。
    """
    first = _randomize_once(task_xml, base_randomization_config, seed=42)
    second = _randomize_once(task_xml, base_randomization_config, seed=42)

    _assert_identical(
        first, second,
        "同一个 seed=42，两次随机化结果却不同 —— 随机流未被 seed 隔离"
    )


def test_different_seeds_produce_different_scenes(
    task_xml, base_randomization_config
):
    """【反向哨兵】不同 seed 应得到不同场景。

    为什么需要这条：上一条测试有个平凡解 —— 如果随机化
    根本没执行（config 为 None、物体名写错、randomize 被跳过），
    两次结果自然完全相同，测试会【绿】但什么都没验证。

    这条测试保证「随机化确实在发生」。
    两条一起才构成完整的判据：既确定，又真的随机。

    注意：修复前这条会【偶然通过】（因为全局随机流本就每次不同），
    修复后它才真正在验证 seed 的区分能力。

    Day 3 自检 2 实测证明了它不可省：注入 np.random.seed(42)
    这个"部分正确的假修复"时，本文件其他测试全绿，只有这条会红。
    """
    a = _randomize_once(task_xml, base_randomization_config, seed=42)
    b = _randomize_once(task_xml, base_randomization_config, seed=1234)

    assert not np.array_equal(a, b), (
        "seed=42 与 seed=1234 得到了完全相同的场景 —— "
        "随机化很可能根本没有执行，上一条测试的绿灯是平凡解"
    )


def test_randomization_actually_moves_objects(task_xml, base_randomization_config):
    """【前提校验】随机化确实改变了物体位置。

    比上一条更基础：确认 exec_randomization 不是空操作。
    如果这条红了，前两条测试的结论全部无意义 —— 先修这个。

    这叫【测试的前提断言】：把「我以为成立的前提」写成可执行的检查。
    """
    model = mujoco.MjModel.from_xml_path(task_xml)
    data = mujoco.MjData(model)
    mujoco.mj_resetData(model, data)
    mujoco.mj_forward(model, data)
    randomizer = SceneRandomizer(model, data, seed=42)

    before = np.concatenate([
        np.asarray(randomizer._object_pose(n)).copy() for n in FREE_BODIES
    ])
    randomizer.exec_randomization(base_randomization_config)
    after = np.concatenate([
        np.asarray(randomizer._object_pose(n)).copy() for n in FREE_BODIES
    ])

    assert not np.array_equal(before, after), (
        "exec_randomization 执行前后物体位姿完全没变 —— 随机化是空操作"
    )

def test_task_base_wires_yaml_seed_to_randomizer(task_xml, task_config_dir):
    """【接线测试】YAML 里的 seed 必须经 UniversalTaskBase 传到 SceneRandomizer。

    为什么单独写这条：
      本文件其他测试都直接构造 SceneRandomizer，绕过了 task_base。
      组件正确 != 调用方接对了线。缺陷 J（键名不匹配）、seed 断链、
      Day 2 缺陷 B（模板缺 observation 段）—— 全都是"接线"缺陷：
      每个零件单看都对，装到一起不工作。

    为什么改真实文件而不是改内存 dict：
      UniversalTaskBase.__init__ 从【文件路径】加载配置。
      改一个已构造对象的 task_config.config 不会影响下次构造 ——
      这正是真实用户的操作路径（编辑 YAML 再运行）。

    为什么临时文件放在 tasks/ 目录内：
      place_block.yaml 头部有 extends: "templates/place_object.yaml"，
      是相对路径。放到 tmp_path 会解析失败。
    """
    import shutil
    import mujoco
    from discoverse.universal_manipulation.task_base import UniversalTaskBase

    src = task_config_dir / f"{TASK}.yaml"
    tmp_cfg = task_config_dir / "_tmp_seed_wiring_test.yaml"
    robot_cfg = str(task_config_dir.parent / "robots" / f"{ROBOT}.yaml")

    shutil.copy(src, tmp_cfg)
    try:
        text = tmp_cfg.read_text(encoding="utf-8")
        assert "seed: null" in text, "前提不成立：源配置里没有 seed: null"
        tmp_cfg.write_text(text.replace("seed: null", "seed: 42"), encoding="utf-8")

        def _run_via_task_base():
            model = mujoco.MjModel.from_xml_path(task_xml)
            data = mujoco.MjData(model)
            mujoco.mj_resetData(model, data)
            mujoco.mj_forward(model, data)
            task = UniversalTaskBase(robot_cfg, str(tmp_cfg), model, data)
            task.randomize_scene()
            return np.concatenate([
                np.asarray(task.randomizer._object_pose(n)).copy()
                for n in FREE_BODIES
            ])

        first = _run_via_task_base()
        second = _run_via_task_base()
    finally:
        # 必须删掉 —— 测试绝不能给仓库留下文件。
        # 用 try/finally 保证断言失败时也会清理。
        tmp_cfg.unlink(missing_ok=True)

    _assert_identical(
        first, second,
        "YAML 写了 seed: 42，经 UniversalTaskBase 两次运行结果却不同 —— "
        "task_base 没把配置里的 seed 传给 SceneRandomizer"
    )

@pytest.mark.xfail(
    strict=True,
    reason="已知缺陷：utils/get_random_texture() 的两个分支都用未受管控的"
           "随机源 —— if 分支用 stdlib random.choice（当前 TEXTURE_1K_PATH "
           "未配置故不可达），else 分支用 np.random 全局流（当前可达）。"
           "二者都不受 SceneRandomizer.rng 管控，贴图选择因此不可复现。"
           "未在 Step 4 修复：get_random_texture 是模块级函数，没有 rng 可用，"
           "修它要改公共函数签名并牵连全部 4 个调用方。",
)
def test_texture_randomization_respects_seed():
    """贴图随机化应受 seed 管控 —— 当前不成立。

    为什么用 xfail 而不是 TODO 注释：
      注释不会被执行，三个月后没人知道它还成不成立。
      xfail(strict=True) 每次 CI 都跑；一旦有人修好了，
      XPASS 会报为 FAILED，强制有人回来撤掉这个标记。
      让"缺陷已修复"也不会静默发生。

    随机性是从 import 边界溜走的：
      Step 4 把 randomization.py 的 25 处改成了 self.rng.*，
      但 randomization.py:553 调的是 utils.get_random_texture()，
      那个函数完全不知道 rng 的存在。
      确定性的边界不是"我改过的文件"，而是整条调用链。
    """
    from discoverse.utils import get_random_texture

    # 修复后应成立的契约：SceneRandomizer(seed=42) 建立的随机流，
    # 应该覆盖它触发的【全部】随机性，包括经 import 调进 utils 的那段。
    # 当前 get_random_texture() 不接受任何 rng 参数，只能无参调用，
    # 内部各走各的全局流 —— 所以两次结果必然不同。
    first = np.asarray(get_random_texture())
    second = np.asarray(get_random_texture())

    assert np.array_equal(first, second), (
        "两次取贴图结果不同 —— get_random_texture 使用了不受 rng 管控的随机源"
    )
