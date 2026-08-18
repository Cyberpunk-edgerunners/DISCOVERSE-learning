"""把 TaskResult 列表渲染为 JUnit XML。

为什么是 JUnit XML
-----------------
它是 CI 世界的事实标准：GitHub Actions 的 Test Reporter、Jenkins 的
`junit` 步骤（本仓库 Jenkinsfile:166 已在消费）、GitLab CI 都能原生解析它，
把结果渲染成可点击的用例列表、失败趋势图和"新增失败"高亮。

自己拼 XML 而不复用 pytest 的 LogXML：后者与 pytest 的 Item/Report 对象
强耦合，为了几十行输出去构造假的 pytest 内部对象得不偿失。JUnit XML 的
schema 本身很小，手写反而更清楚、更可控。
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Sequence
from xml.dom import minidom

from discoverse.testing.result_schema import FailureMode, TaskResult


def _failure_text(r: TaskResult) -> str:
    """失败详情：给人看的排查线索，结构化字段在属性里已有一份。"""
    lines = [
        f"robot          = {r.robot}",
        f"task           = {r.task}",
        f"failure_mode   = {r.failure_mode}",
        f"exit_code      = {r.exit_code}",
        f"completed      = {r.completed_states}/{r.total_states} 状态",
        f"sim_time       = {r.sim_time:.2f}s",
        f"wall_time      = {r.wall_time:.2f}s",
    ]
    if r.seed is not None:
        lines.append(f"seed           = {r.seed}   # 复现用")
    if r.error_message:
        lines.append(f"\n错误信息:\n{r.error_message}")
    if r.stdout_tail:
        lines.append(f"\n--- stdout 尾部 ---\n{r.stdout_tail}")
    return "\n".join(lines)


def build_junit_tree(results: Sequence[TaskResult],
                     suite_name: str = "discoverse.cicd") -> ET.ElementTree:
    total_time = sum(r.wall_time for r in results)
    failures = sum(1 for r in results if not r.success
                   and r.failure_mode != FailureMode.CONFIG)
    # 配置错误记为 error 而非 failure：它不是"被测对象没通过"，
    # 而是"测试没跑起来"。CI 面板上二者的含义完全不同。
    errors = sum(1 for r in results if r.failure_mode == FailureMode.CONFIG)

    testsuites = ET.Element("testsuites", {
        "name": suite_name,
        "tests": str(len(results)),
        "failures": str(failures),
        "errors": str(errors),
        "time": f"{total_time:.3f}",
    })
    testsuite = ET.SubElement(testsuites, "testsuite", {
        "name": suite_name,
        "tests": str(len(results)),
        "failures": str(failures),
        "errors": str(errors),
        "skipped": "0",
        "time": f"{total_time:.3f}",
    })

    for r in results:
        # classname 用 robot、name 用 task：CI 界面会按 classname 分组，
        # 于是"某个机器人整体挂掉"和"某个任务在所有机器人上挂掉"一眼可辨。
        case = ET.SubElement(testsuite, "testcase", {
            "classname": f"{suite_name}.{r.robot}",
            "name": r.task,
            "time": f"{r.wall_time:.3f}",
        })
        if r.success:
            continue

        tag = "error" if r.failure_mode == FailureMode.CONFIG else "failure"
        node = ET.SubElement(case, tag, {
            "type": str(r.failure_mode),
            "message": (r.error_message or f"{r.robot}/{r.task} 失败")[:200],
        })
        node.text = _failure_text(r)

    return ET.ElementTree(testsuites)


def write_junit_xml(results: Sequence[TaskResult], output_path: str,
                    suite_name: str = "discoverse.cicd") -> str:
    tree = build_junit_tree(results, suite_name)
    xml_bytes = ET.tostring(tree.getroot(), encoding="utf-8")
    pretty = minidom.parseString(xml_bytes).toprettyxml(indent="  ", encoding="utf-8")
    with open(output_path, "wb") as f:
        f.write(pretty)
    return output_path
