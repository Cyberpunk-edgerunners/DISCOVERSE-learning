"""recorder.py 的单元测试。

覆盖 recoder_single_arm（JSON 序列化）。PyavImageEncoder 见文件末尾。

⚠️ 函数名 recoder_single_arm 是上游的拼写（少个 r），不是笔误，
   不要"顺手修正"——__init__.py 的导出和 universal_task_runtime.py:345
   的调用点都依赖这个名字。
"""

import json

import numpy as np
import pytest

from discoverse.universal_manipulation.recorder import (
    PyavImageEncoder,
    recoder_single_arm,
)

# ---------- happy path ----------


@pytest.mark.unit
def test_writes_expected_json_structure(tmp_path):
    """正常输入 → JSON 结构与字段齐全。

    注意输入输出的键名不对称：输入是 'action'，输出是 'act'。
    这个映射没有文档，只能从实现读出来 —— 测试把它固定下来，
    以后有人改了键名会立刻红。
    """
    obs_lst = [
        {"time": 0.0, "jq": [1, 2], "action": [9, 9]},
        {"time": 0.1, "jq": [3, 4], "action": [8, 8]},
    ]

    recoder_single_arm(str(tmp_path), obs_lst)

    data = json.loads((tmp_path / "obs_action.json").read_text())
    assert data == {
        "time": [0.0, 0.1],
        "obs": {"jq": [[1, 2], [3, 4]]},
        "act": [[9, 9], [8, 8]],
    }


@pytest.mark.unit
def test_creates_nested_save_path(tmp_path):
    """save_path 不存在时应自动创建（含多层）。"""
    target = tmp_path / "a" / "b" / "c"
    assert not target.exists()

    recoder_single_arm(str(target), [{"time": 0.0, "jq": [1], "action": [2]}])

    assert (target / "obs_action.json").is_file()


@pytest.mark.unit
def test_empty_obs_list_yields_empty_arrays(tmp_path):
    """空列表 → 产出结构完整但数组为空的 JSON，而非报错或空文件。

    这是有意固定的行为：下游拿到的应该是一个合法 JSON，
    能被 json.load 解析出"这一轮没有数据"，
    而不是一个需要 try/except 才能读的坏文件。
    """
    recoder_single_arm(str(tmp_path), [])

    data = json.loads((tmp_path / "obs_action.json").read_text())
    assert data == {"time": [], "obs": {"jq": []}, "act": []}


@pytest.mark.unit
def test_extra_keys_in_obs_are_ignored(tmp_path):
    """obs 里多余的键被忽略，不影响输出。

    固定这个行为是因为真实 obs 字典（universal_task_runtime.py:108-115）
    可能携带额外字段，recorder 只挑它认识的三个。
    """
    recoder_single_arm(
        str(tmp_path), [{"time": 0.0, "jq": [1], "action": [2], "extra": "x"}]
    )

    data = json.loads((tmp_path / "obs_action.json").read_text())
    assert data == {"time": [0.0], "obs": {"jq": [[1]]}, "act": [[2]]}


# ---------- 缺陷：部分写入 ----------


@pytest.mark.unit
@pytest.mark.xfail(
    reason="缺陷：open(...,'w') 在循环之前就截断了文件，循环中途抛 KeyError 时"
    "留下一个 0 字节的 obs_action.json。下游用 os.path.exists() 判断"
    "'本轮采集成功' 会误判为成功，真去 json.load() 才炸。"
    "修复方案：先在内存 build 完 dict 再 open()，或写临时文件 + os.replace() 原子替换。",
    strict=True,
)
@pytest.mark.parametrize("missing", ["time", "jq", "action"])
def test_partial_write_leaves_no_corrupt_file(tmp_path, missing):
    """obs 缺任一必需键时，不应在磁盘上留下坏文件。

    ⚠️ 用装饰器 xfail 而非命令式 pytest.xfail()：
       后者会立即中断测试，下面的断言根本不执行，
       上游修好了也不会转成 XPASS 报警（见 checkpoint-day06-07 §4.3）。
       strict=True 保证缺陷被修复后这个测试会 XPASS 失败，提醒你更新它。
    """
    obs = {"time": 0.0, "jq": [1, 2], "action": [3, 4]}
    del obs[missing]

    with pytest.raises(KeyError):
        recoder_single_arm(str(tmp_path), [obs])

    # 要么不创建文件，要么创建一个合法可解析的文件 —— 不能留半截。
    written = tmp_path / "obs_action.json"
    if written.exists():
        assert written.stat().st_size > 0, "留下了 0 字节的坏文件"
        json.loads(written.read_text())  # 必须可解析


# ---------- 健壮性隐患：ndarray ----------


@pytest.mark.unit
@pytest.mark.xfail(
    reason="健壮性隐患（非当前可达缺陷）：json.dump 不接受 ndarray。"
    "唯一调用方 universal_task_runtime.py:111-112 已做 .tolist()，"
    "所以当前不可达。但函数从未声明'只接受 list'这一契约，"
    "新增调用方漏掉 .tolist() 即会炸，且同样留下半截文件。",
    strict=True,
)
def test_accepts_numpy_arrays(tmp_path):
    """ndarray 应能被序列化（或至少给出明确的类型错误且不留坏文件）。"""
    np = pytest.importorskip("numpy")

    recoder_single_arm(
        str(tmp_path), [{"time": 0.0, "jq": np.zeros(3), "action": np.ones(3)}]
    )

    data = json.loads((tmp_path / "obs_action.json").read_text())
    assert data["obs"]["jq"] == [[0.0, 0.0, 0.0]]


# ---------- PyavImageEncoder ----------
#
# 为什么不 mock av：
#   av 的 PyPI wheel 自带完整 ffmpeg（av.libs 约 72 MB），
#   实测本机与容器内 h264/libx264 均可用，不依赖系统装 ffmpeg。
#   mock 掉就只是在测自己写的假对象，编码链路一行没走到。
#   真编码 3 帧 64x48 只需约 0.1s，代价可接受。


@pytest.mark.unit
def test_encoder_writes_decodable_mp4(tmp_path):
    """编码若干帧后 close，产出的 MP4 应能被解码回相同帧数与尺寸。

    这是本文件里唯一一条真正的端到端验收：
    只断言"文件非空"是不够的 —— 一个损坏的 MP4 同样非空。
    必须解码回来，才证明编码链路真的走通了。
    """
    av = pytest.importorskip("av")

    enc = PyavImageEncoder(width=64, height=48, save_path=str(tmp_path), id=0, fps=30)
    for i in range(3):
        enc.encode(np.full((48, 64, 3), i * 80, dtype=np.uint8), timestamp=i * 0.1)
    enc.close()

    out = tmp_path / "cam_0.mp4"
    assert out.stat().st_size > 0

    with av.open(str(out)) as container:
        frames = list(container.decode(video=0))

    assert len(frames) == 3
    assert (frames[0].width, frames[0].height) == (64, 48)


@pytest.mark.unit
def test_encoder_filename_follows_cam_id_pattern(tmp_path):
    """文件名格式为 cam_{id}.mp4，且 id 允许 str 或 int。

    固定这个约定是因为下游按此模式扫描多相机录像；
    改名会静默断开数据管道（找不到文件 ≠ 报错）。
    """
    enc = PyavImageEncoder(64, 48, str(tmp_path), id="left")
    assert enc.av_file_path.endswith("cam_left.mp4")
    enc.close()


@pytest.mark.unit
def test_encode_rejects_non_monotonic_timestamp(tmp_path):
    """时间戳倒退时应拒绝（recorder.py:58 的 assert）。

    这是本模块少见的"失败得很响亮"的地方，值得固定住 ——
    倒退的时间戳会让编码器产出无法正常播放的视频。
    """
    enc = PyavImageEncoder(64, 48, str(tmp_path), 0)
    enc.encode(np.zeros((48, 64, 3), np.uint8), timestamp=1.0)

    with pytest.raises(AssertionError, match="Time error"):
        enc.encode(np.zeros((48, 64, 3), np.uint8), timestamp=0.5)

    enc.close()


@pytest.mark.unit
def test_close_is_idempotent(tmp_path):
    """重复 close 不应抛异常。

    close() 里把 self.container 置 None 并做了判空，
    所以二次调用安全 —— 固定住，避免以后重构时丢掉这个判空。
    """
    enc = PyavImageEncoder(64, 48, str(tmp_path), 0)
    enc.encode(np.zeros((48, 64, 3), np.uint8), timestamp=0.0)

    enc.close()
    enc.close()  # 不应抛


@pytest.mark.unit
def test_remove_av_file_deletes_output(tmp_path):
    """remove_av_file() 应删除已产出的文件。"""
    enc = PyavImageEncoder(64, 48, str(tmp_path), 1)
    enc.encode(np.zeros((48, 64, 3), np.uint8), timestamp=0.0)
    enc.close()
    assert (tmp_path / "cam_1.mp4").exists()

    enc.remove_av_file()

    assert not (tmp_path / "cam_1.mp4").exists()


@pytest.mark.unit
@pytest.mark.xfail(
    reason="健壮性隐患：未调用 close() 时，PyAV 从未把缓冲刷到磁盘 —— "
    "文件完全不存在（实测：encode 3 帧后 os.path.exists() 为 False）。"
    "采集进程中途崩溃/被 kill 时，整段录像静默丢失，且不留任何痕迹。"
    "调用方 universal_task_runtime.py 没有 try/finally 保护。"
    "修复方案：实现 __enter__/__exit__ 使其可用于 with 语句，"
    "或在调用方加 finally: encoder.close()。",
    strict=True,
)
def test_frames_survive_without_explicit_close(tmp_path):
    """未显式 close 时，已编码的帧不应完全丢失。

    对比 recoder_single_arm 的部分写入缺陷：
      那个留下 0 字节坏文件（下游误判为成功）；
      这个连文件都不创建（下游至少能发现"没有产出"）。
    两者都是"失败时静默"，但后者的失败模式反而更安全。
    """
    enc = PyavImageEncoder(64, 48, str(tmp_path), 7)
    for i in range(3):
        enc.encode(np.zeros((48, 64, 3), np.uint8), timestamp=i * 0.1)
    # 故意不 close —— 模拟进程崩溃

    assert (tmp_path / "cam_7.mp4").exists(), "未 close 时整段录像丢失"
