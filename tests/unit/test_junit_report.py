"""JUnit XML 渲染的单元测试（Day 13-14）。

守护点：XML 必须能被 CI 原生解析，且 failure / error 的语义不能混。
"""

import xml.etree.ElementTree as ET

import pytest

from discoverse.testing import ExitCode, FailureMode, TaskResult
from discoverse.testing.junit_report import write_junit_xml

pytestmark = pytest.mark.unit


@pytest.fixture
def mixed_results():
    return [
        TaskResult(robot="airbot_play", task="place_block", success=True,
                   completed_states=10, total_states=10,
                   wall_time=2.0, exit_code=ExitCode.SUCCESS),
        TaskResult(robot="airbot_play", task="cover_cup", success=False,
                   completed_states=0, total_states=17, wall_time=2.1,
                   exit_code=ExitCode.FAILED,
                   failure_mode=FailureMode.IK_EARLY, seed=13),
        TaskResult(robot="panda", task="cover_cup", success=False,
                   wall_time=2.3, exit_code=ExitCode.CONFIG_ERROR,
                   failure_mode=FailureMode.CONFIG,
                   error_message='The camera "eye_arm" does not exist.'),
    ]


def test_xml_is_wellformed_and_counts_match(tmp_path, mixed_results):
    out = tmp_path / "junit.xml"
    write_junit_xml(mixed_results, str(out))
    root = ET.parse(str(out)).getroot()

    assert root.tag == "testsuites"
    assert root.get("tests") == "3"
    # 1 个任务失败记 failure，1 个配置错误记 error —— 二者分开计数
    assert root.get("failures") == "1"
    assert root.get("errors") == "1"


def test_config_error_renders_as_error_not_failure(tmp_path, mixed_results):
    """配置错误 = 测试没跑起来，与"被测对象没通过"在 CI 面板上含义不同。"""
    out = tmp_path / "junit.xml"
    write_junit_xml(mixed_results, str(out))
    root = ET.parse(str(out)).getroot()

    cases = {(c.get("classname"), c.get("name")): c
             for c in root.iter("testcase")}
    panda = cases[("discoverse.cicd.panda", "cover_cup")]
    assert [child.tag for child in panda] == ["error"]

    airbot = cases[("discoverse.cicd.airbot_play", "cover_cup")]
    assert [child.tag for child in airbot] == ["failure"]


def test_passing_case_has_no_child_nodes(tmp_path, mixed_results):
    out = tmp_path / "junit.xml"
    write_junit_xml(mixed_results, str(out))
    root = ET.parse(str(out)).getroot()
    cases = {(c.get("classname"), c.get("name")): c
             for c in root.iter("testcase")}
    assert list(cases[("discoverse.cicd.airbot_play", "place_block")]) == []


def test_failure_text_carries_repro_info(tmp_path, mixed_results):
    """失败详情里必须带 seed 与状态进度，否则看到红灯也无从复现。"""
    out = tmp_path / "junit.xml"
    write_junit_xml(mixed_results, str(out))
    text = out.read_text(encoding="utf-8")
    assert "seed           = 13" in text
    assert "0/17 状态" in text


def test_classname_groups_by_robot(tmp_path, mixed_results):
    """按机器人分组，让"某个机器人整体挂掉"一眼可辨。"""
    out = tmp_path / "junit.xml"
    write_junit_xml(mixed_results, str(out))
    root = ET.parse(str(out)).getroot()
    names = {c.get("classname") for c in root.iter("testcase")}
    assert names == {"discoverse.cicd.airbot_play", "discoverse.cicd.panda"}


def test_empty_results_still_valid_xml(tmp_path):
    """空结果不能产出损坏的 XML —— 否则 CI 报告步骤会以解析错误告终。"""
    out = tmp_path / "junit.xml"
    write_junit_xml([], str(out))
    root = ET.parse(str(out)).getroot()
    assert root.get("tests") == "0"
