"""缺陷 J：碰撞避让半径的键名不匹配。

实测（2026-07-31）：
    randomization.py:184 读的是 min_distance
    12 个任务物体的 YAML 写的全是 collision_radius
    -> .get() 取不到 -> 9/12 物体的半径静默塌到默认值 0.05

为什么兼容两个键名而不是只改一边：
    templates/randomization.yaml 用 min_distance（6 处），
    但实测【没有任何任务继承它】——
    唯一引用是该文件第 137 行的注释示例。
    它是给人照抄的文档模板，所以新键名要认，旧键名也要认，
    否则照模板抄的人会掉进同一个坑。
"""
import pytest

from discoverse.universal_manipulation.randomization import SceneRandomizer

pytestmark = pytest.mark.unit


@pytest.fixture
def radius_of():
    """返回一个能直接调 _get_collision_radius 的函数。

    用 __new__ 绕过 __init__：
      SceneRandomizer.__init__ 需要真实的 MjModel/MjData（要遍历 body、
      camera、light 存初始状态）。但取半径这件事跟模型毫无关系 ——
      它只是个纯粹的字典查找。

      为了测一个纯函数去加载 MuJoCo 模型，是把毫秒级测试变成百毫秒级，
      而且引入了一堆与被测行为无关的失败可能（模型文件缺失、
      mesh 加载失败……）。那些失败会伪装成"半径逻辑坏了"。
    """
    instance = SceneRandomizer.__new__(SceneRandomizer)
    return instance._get_collision_radius


# ---------- 单值行为 ----------

def test_reads_collision_radius(radius_of):
    """任务 YAML 用的键名，必须被读到。"""
    assert radius_of({"collision_radius": 0.12}) == 0.12


def test_reads_min_distance_as_fallback(radius_of):
    """模板用的旧键名，也要认（照模板抄的人不该掉坑）。"""
    assert radius_of({"min_distance": 0.03}) == 0.03


def test_collision_radius_wins_over_min_distance(radius_of):
    """两个键都在时，以任务 YAML 的键名为准。

    为什么是 collision_radius 优先：
      它是【实际被加载的】那个（12 处 vs 0 处）。
      优先级要给真正生效的一方，否则修复等于没修。
    """
    assert radius_of({"collision_radius": 0.12, "min_distance": 0.03}) == 0.12


def test_falls_back_to_default_when_absent(radius_of):
    """两个键都没有时才走默认值。

    这条守的是"默认值仍然存在" —— 修复不能让没配半径的物体炸掉。
    """
    assert radius_of({}) == 0.05


# ---------- 契约测试：对着真实配置 ----------

# 实测值（2026-07-31），非文档抄录。
# 写成脆断言：任何一个数字变了都要有人来看一眼，
# 而不是让测试悄悄跟着配置漂移。
DECLARED_RADII = [
    ("cover_cup",        "coffeecup_white", 0.05),
    ("cover_cup",        "plate_white",     0.10),
    ("cover_cup",        "cup_lid",         0.05),
    ("place_block",      "block_green",     0.05),
    ("place_block",      "bowl_pink",       0.12),
    ("place_coffeecup",  "coffeecup_white", 0.10),
    ("place_coffeecup",  "plate_white",     0.12),
    ("place_kiwi_fruit", "kiwi",            0.07),
    ("place_kiwi_fruit", "flower_bowl",     0.09),
    ("stack_block",      "block_green",     0.06),
    ("stack_block",      "block_red",       0.06),
    ("stack_block",      "block_blue",      0.06),
]


@pytest.fixture(scope="session")
def loaded_objects(task_config_dir):
    """{(任务名, 物体名): 物体配置} —— 经加载器解析 extends 后的最终配置。

    Day 2 方法论第 7 条：静态读 YAML != 运行时加载。
    place_block 等 3 个任务 extends 了 place_object.yaml，
    必须用加载器拿最终合并结果。
    """
    from discoverse.universal_manipulation.config_utils import (
        load_and_resolve_config, replace_variables,
    )
    from discoverse.universal_manipulation.task_config import TaskConfigLoader

    out = {}
    for path in sorted(task_config_dir.glob("*.yaml")):
        cfg = TaskConfigLoader.from_dict(
            replace_variables(load_and_resolve_config(str(path)))
        )
        for obj in ((cfg.randomization or {}).get("objects") or []):
            out[(path.stem, obj["name"])] = obj
    return out


@pytest.mark.parametrize("task,obj,declared", DECLARED_RADII)
def test_effective_radius_equals_declared(radius_of, loaded_objects, task, obj, declared):
    """【核心】每个物体实际生效的半径，必须等于它在 YAML 里声明的值。

    修复前：9/12 会红（全部塌到 0.05）
    修复后：12/12 绿

    这是缺陷 J 的回归测试 —— 键名再被改动一次，它会立刻红。
    """
    obj_config = loaded_objects.get((task, obj))
    assert obj_config is not None, f"{task}/{obj} 不在加载后的配置里，测试前提不成立"

    effective = radius_of(obj_config)
    assert effective == pytest.approx(declared), (
        f"{task}/{obj} 声明半径 {declared}，实际生效 {effective} "
        f"（缩小 {declared / effective:.1f}×）—— 避让距离静默失效"
    )