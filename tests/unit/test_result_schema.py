"""结果契约的单元测试（Day 13-14）。

这些用例守护的是一件事：**结果不能自相矛盾**。
契约一旦允许 success=True 同时带 failure_mode，下游的 JUnit 渲染、
成功率统计、失败模式分布就全部失去意义。
"""

import json

import pytest

from discoverse.testing import ExitCode, FailureMode, TaskResult

pytestmark = pytest.mark.unit


def make_ok(**kw):
    base = {"robot": "airbot_play", "task": "place_block", "success": True,
            "completed_states": 10, "total_states": 10,
            "exit_code": ExitCode.SUCCESS}
    base.update(kw)
    return TaskResult(**base)


class TestContractValidation:
    def test_success_result_is_accepted(self):
        r = make_ok()
        assert r.success is True
        assert r.failure_mode is None
        assert r.exit_code == 0

    def test_failure_requires_a_mode(self):
        """失败必须说明失败模式，否则红灯不带任何排查方向。"""
        with pytest.raises(ValueError, match="未指定 failure_mode"):
            TaskResult(robot="a", task="b", success=False)

    def test_success_must_not_carry_failure_mode(self):
        with pytest.raises(ValueError, match="矛盾的结果"):
            TaskResult(robot="a", task="b", success=True,
                       failure_mode=FailureMode.TIMEOUT)

    def test_unknown_failure_mode_rejected(self):
        """拼错的失败模式必须当场报错，而不是混进统计里变成新类别。"""
        with pytest.raises(ValueError, match="未知的 failure_mode"):
            TaskResult(robot="a", task="b", success=False,
                       failure_mode="tiemout")


class TestSerialization:
    def test_roundtrip_through_json(self, tmp_path):
        """跨进程边界后信息不能丢 —— 这正是契约存在的理由。"""
        original = TaskResult(
            robot="panda", task="cover_cup", success=False,
            completed_states=3, total_states=17,
            sim_time=1.25, wall_time=2.5,
            exit_code=ExitCode.FAILED,
            failure_mode=FailureMode.IK_EARLY,
            seed=13,
        )
        path = tmp_path / "r.json"
        original.to_json(str(path))
        restored = TaskResult.from_json(str(path))
        assert restored.to_dict() == original.to_dict()

    def test_json_is_plain_serializable(self, tmp_path):
        """failure_mode 用字符串常量而非 Enum，确保 json.dump 不需额外编码器。"""
        path = tmp_path / "r.json"
        make_ok().to_json(str(path))
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert raw["failure_mode"] is None
        assert isinstance(raw["exit_code"], int)


class TestExitCodeContract:
    def test_codes_are_distinct(self):
        """0/1/2 必须互不相同：CI 靠它们区分成功、失败与配置错误。"""
        assert ExitCode.SUCCESS == 0
        assert ExitCode.FAILED == 1
        assert ExitCode.CONFIG_ERROR == 2
        assert len({ExitCode.SUCCESS, ExitCode.FAILED, ExitCode.CONFIG_ERROR}) == 3

    def test_config_error_is_not_a_task_failure(self):
        """区分二者的意义：配置错误不该被当成任务回归去排查。"""
        r = TaskResult.from_config_error("fake", "place_block", "未知机器人")
        assert r.exit_code == ExitCode.CONFIG_ERROR
        assert r.failure_mode == FailureMode.CONFIG
        assert r.success is False
