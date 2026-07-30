"""5 个任务配置的契约测试。

本文件的断言全部基于实测行为（2026-07-30），不基于文档描述。

关键背景：任务配置有 extends 继承机制（config_utils.py:17）。
  place_block / place_coffeecup / place_kiwi_fruit
      -> extends templates/place_object.yaml
  cover_cup / stack_block
      -> 无继承

因此判断"配置有什么"必须用加载器加载后再看，
直接读单个 YAML 文件会得到错误结论。
"""
import pytest

from discoverse.universal_manipulation.task_config import TaskConfigLoader

TASKS = [
    "cover_cup", "place_block", "place_coffeecup",
    "place_kiwi_fruit", "stack_block",
]

INHERITING_TASKS = ["place_block", "place_coffeecup", "place_kiwi_fruit"]

# 缺陷 B：camera_configs 为空的任务（实测）
#   根因有两种：
#     templates/place_object.yaml 缺 observation 段 -> 3 个继承者受害
#     stack_block 自己漏写
#   修复：改 1 个模板 + 1 个任务文件，而非 4 个任务各补一遍
MISSING_OBSERVATION = ["place_block", "place_coffeecup", "place_kiwi_fruit", "stack_block"]


def _minimal_config(**overrides):
    """构造能通过 _validate_config 的最小合法任务配置。

    实测必填项（task_config.py:_validate_config）：
        task_name, description
        states 或 task_states 之一，必须是非空 list
        每个 state 必须有 name 和 primitive

    注意 observation 不在必填清单里 —— 这正是缺陷 B 能存在的原因：
    校验函数存在，但未覆盖这个影响数据产出的关键字段。
    """
    cfg = {
        "task_name": "t",
        "description": "d",
        "states": [{"name": "s0", "primitive": "move"}],
    }
    cfg.update(overrides)
    return cfg


@pytest.fixture(scope="session")
def load_task(task_config_dir):
    """按名字加载任务配置，会话级缓存。

    加载器会自动处理 extends 并合并模板，
    拿到的是【最终配置】，不是原始 YAML 内容。
    """
    cache = {}

    def _load(name):
        if name not in cache:
            cache[name] = TaskConfigLoader(str(task_config_dir / f"{name}.yaml"))
        return cache[name]

    return _load


@pytest.mark.unit
@pytest.mark.parametrize("task_name", TASKS)
def test_task_name_matches_filename(load_task, task_name):
    """配置里的 task_name 必须与文件名一致。

    继承任务会从模板拿到 task_name='place_object'，
    子配置必须显式覆盖它，否则三个任务会同名。
    """
    assert load_task(task_name).task_name == task_name


@pytest.mark.unit
@pytest.mark.parametrize("task_name", TASKS)
def test_success_check_exists(load_task, task_name):
    """成功判据是任务的核心 —— 没有它就无法判断任务成败。"""
    sc = load_task(task_name).success_check
    assert sc is not None, f"{task_name} 缺 success_check"
    assert "conditions" in sc, f"{task_name} 的 success_check 缺 conditions"


@pytest.mark.unit
@pytest.mark.parametrize("task_name", INHERITING_TASKS)
def test_extends_actually_merged_template(load_task, task_name):
    """extends 必须真的把模板内容合并进来。

    验证方式：模板独有的 runtime_parameters 键必须出现在最终配置里。
    若 extends 是死配置（写了不读），这条会红。
    """
    cfg = load_task(task_name).config
    assert "extends" not in cfg, "合并后 extends 指令本身不应保留"
    rp = cfg.get("runtime_parameters", {})
    assert "source_object" in rp, f"{task_name} 未继承到模板的 runtime_parameters"


# ============================================================
# 缺陷 B：camera_configs 为空
#
# camera_configs 是数据采集时遍历相机的依据。
# 空列表意味着 for 循环一次都不执行 —— 采集流程正常跑完、
# 正常退出，一张图都没录，全程无报错。
# 具身智能项目里数据集就是产品，故严重度【高】。
# ============================================================

@pytest.mark.unit
@pytest.mark.parametrize("task_name", TASKS)
def test_camera_configs_nonempty(load_task, task_name):
    """每个任务都应至少配置一个相机。"""
    if task_name in MISSING_OBSERVATION:
        pytest.xfail(
            f"缺陷 B：{task_name} 的 camera_configs 为空 —— "
            f"数据采集会静默产出零张图像"
        )
    assert len(load_task(task_name).camera_configs) > 0


@pytest.mark.unit
@pytest.mark.parametrize("task_name", TASKS)
def test_camera_config_fields_wellformed(load_task, task_name):
    """相机配置项必须含渲染所需的四个字段。"""
    cams = load_task(task_name).camera_configs
    if not cams:
        pytest.skip(f"{task_name} 无相机配置（见缺陷 B）")
    for i, cam in enumerate(cams):
        for field in ("name", "fovy", "width", "height"):
            assert field in cam, f"{task_name} 第 {i} 个相机缺字段 {field}"


# ============================================================
# 缺陷 C：record_fps 的双层静默默认值
#   task_config.py:167
#     return self.config.get('observation', {'fps': 30}).get('fps', 30)
#                                          ^^^^^^^^^^^^        ^^
# ============================================================

@pytest.mark.unit
def test_record_fps_reads_real_value():
    """有 fps 配置时必须读真值，不能被默认值覆盖。"""
    loader = TaskConfigLoader.from_dict(_minimal_config(observation={"fps": 25}))
    assert loader.record_fps == 25


@pytest.mark.unit
@pytest.mark.parametrize("bad_config,label", [
    (_minimal_config(), "无 observation 键"),
    (_minimal_config(observation={}), "observation 为空 dict"),
])
def test_record_fps_silently_defaults_to_30(bad_config, label):
    """钉死【当前】行为：配置缺失时静默返回 30。

    这不是"正确行为"，而是把缺陷固化下来防止无声变化。
    修复方向：影响产出正确性的配置缺失时应报错，而非兜默认值。
    """
    assert TaskConfigLoader.from_dict(bad_config).record_fps == 30


@pytest.mark.unit
def test_record_fps_crashes_on_null_observation():
    """缺陷 C 的崩溃分支：observation: null 触发 AttributeError。

    根因：dict.get(key, default) 只在【键不存在】时用默认值。
    键存在但值为 None 时返回 None，随后 None.get('fps') 炸。

        {'observation': None}.get('observation', {'fps': 30})  -> None
        None.get('fps', 30)  -> AttributeError

    YAML 里 `observation:` 后面留空就会产生 None，很容易写出。
    """
    loader = TaskConfigLoader.from_dict(_minimal_config(observation=None))
    with pytest.raises(AttributeError):
        _ = loader.record_fps


@pytest.mark.unit
def test_camera_configs_crashes_on_null_observation():
    """camera_configs 有同样的 null 崩溃路径。"""
    loader = TaskConfigLoader.from_dict(_minimal_config(observation=None))
    with pytest.raises(AttributeError):
        _ = loader.camera_configs


# ============================================================
# 缺陷 I：_validate_config 未覆盖 observation
#   task_config.py:_validate_config 的 required_fields 只有
#   ['task_name', 'description']。observation 影响数据采集产出，
#   缺失时 camera_configs 静默返回 []，但校验放行。
#   这是缺陷 B 能存在于 4/5 任务的直接原因。
# ============================================================

@pytest.mark.unit
def test_validate_config_rejects_missing_required_fields():
    """钉死【当前】校验行为：task_name / description / states 缺一即报错。"""
    for missing in ("task_name", "description", "states"):
        cfg = _minimal_config()
        del cfg[missing]
        with pytest.raises(ValueError, match="Missing required field|states|state"):
            TaskConfigLoader.from_dict(cfg)


@pytest.mark.unit
@pytest.mark.xfail(
    strict=True,
    reason="缺陷 I：_validate_config 未把 observation 列为必填，"
           "导致 4/5 任务缺相机配置却能通过校验",
)
def test_validate_config_should_require_observation():
    """记录【期望】行为：缺 observation 应在加载期报错。

    理由：observation 决定数据采集录什么。缺失时 camera_configs
    返回空列表，采集流程正常跑完却零张图像 —— 影响产出正确性的
    配置，缺失必须快速失败，而非静默兜默认值。

    修复后去掉本 xfail 标记即变绿。
    """
    with pytest.raises(ValueError):
        TaskConfigLoader.from_dict(_minimal_config())


# ============================================================
# 缺陷 I：_validate_config 未覆盖 observation
#   task_config.py:_validate_config 的 required_fields 只有
#   ['task_name', 'description']。observation 影响数据采集产出，
#   缺失时 camera_configs 静默返回 []，但校验放行。
#   这是缺陷 B 能存在于 4/5 任务的直接原因。
# ============================================================

@pytest.mark.unit
def test_validate_config_rejects_missing_required_fields():
    """钉死【当前】校验行为：task_name / description / states 缺一即报错。"""
    for missing in ("task_name", "description", "states"):
        cfg = _minimal_config()
        del cfg[missing]
        with pytest.raises(ValueError, match="Missing required field|states|state"):
            TaskConfigLoader.from_dict(cfg)


@pytest.mark.unit
@pytest.mark.xfail(
    strict=True,
    reason="缺陷 I：_validate_config 未把 observation 列为必填，"
           "导致 4/5 任务缺相机配置却能通过校验",
)
def test_validate_config_should_require_observation():
    """记录【期望】行为：缺 observation 应在加载期报错。

    理由：observation 决定数据采集录什么。缺失时 camera_configs
    返回空列表，采集流程正常跑完却零张图像 —— 影响产出正确性的
    配置，缺失必须快速失败，而非静默兜默认值。

    修复后去掉本 xfail 标记即变绿。
    """
    with pytest.raises(ValueError):
        TaskConfigLoader.from_dict(_minimal_config())
