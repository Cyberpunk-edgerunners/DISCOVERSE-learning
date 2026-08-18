"""DISCOVERSE 测试基础设施。

本包提供 CICD 批量测试的结构化结果契约，替代早期基于
stdout emoji 字符串匹配的脆弱判定。
"""

from discoverse.testing.result_schema import (
    ExitCode,
    FailureMode,
    TaskResult,
)

__all__ = ["ExitCode", "FailureMode", "TaskResult"]
