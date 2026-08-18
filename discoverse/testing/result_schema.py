"""单次任务运行的结构化结果契约。

背景（Day 13-14）
----------------
重构前，`cicd_testing.py` 通过匹配子进程 stdout 里的 emoji 判断成败：

    if "✅ 任务成功检查通过" in output or "🎉" in output and "任务成功完成" in output:

这条判定有三重脆弱性，且实测中两个方向都会出错：

1. 改动打印文案 / 日志管道剥离 emoji -> 成功被判为失败（假阴性）
2. 失败运行的日志里若出现过 "🎉 ... 任务成功完成" 字样 -> 失败被判为成功（假阳性）
3. `A or B and C` 实际是 `A or (B and C)`，与阅读直觉不符

本模块把"运行结果"从一段供人阅读的文字，变成一份供机器消费的数据。
判定依据不再是打印了什么，而是进程退出码 + 一份 JSON 结果文件。
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from enum import IntEnum
from typing import Any, Dict, Optional


class ExitCode(IntEnum):
    """进程退出码契约。

    CI 系统（GitHub Actions / Jenkins / GitLab CI）判断步骤成败的唯一依据
    就是退出码，因此这份契约必须稳定。

    刻意区分 FAILED 与 CONFIG_ERROR：前者是"被测对象没通过"，属于正常的
    测试结论；后者是"测试根本没跑起来"，属于基础设施问题。二者混为一谈会
    让配置写错看起来像任务回归，浪费排查时间。
    """

    SUCCESS = 0        # 任务成功，判据全部满足
    FAILED = 1         # 任务失败，判据未满足（这是一个有效的测试结论）
    CONFIG_ERROR = 2   # 配置 / 环境错误，任务未能真正执行


# 说明：FailureMode 用普通字符串常量而非 Enum，是为了让 asdict() 直接产出
# 可 JSON 序列化的值，避免调用方再做一次转换。
class FailureMode:
    """失败模式分类。

    区分失败模式的意义在于：同样是"红灯"，`IK_EARLY` 指向运动学问题，
    `FINAL_CHECK` 指向任务判据或物理参数，`TIMEOUT` 指向性能或死循环，
    `CONFIG` 则根本不是被测代码的问题。分类让红灯自带排查方向。
    """

    NONE = None                 # 未失败
    IK_EARLY = "ik_early"       # 状态机中途 IK 求解失败，未走完全部状态
    FINAL_CHECK = "final_check" # 状态全部走完，但最终成功判据未满足
    TIMEOUT = "timeout"         # 超过墙钟超时，被强制终止
    CONFIG = "config"           # 配置/环境错误（如机器人名不在白名单）
    CRASH = "crash"             # 子进程异常退出（段错误等非契约退出码）

    ALL = (IK_EARLY, FINAL_CHECK, TIMEOUT, CONFIG, CRASH)


@dataclass
class TaskResult:
    """一次 (robot, task) 运行的完整结果。

    字段设计原则：任何 CI 需要展示或断言的信息，都必须是独立字段，
    而不是埋在一段自由文本里等着被正则捞出来。
    """

    robot: str
    task: str
    success: bool

    # 进度：完成状态数 / 总状态数。即使失败，也能看出"走到哪一步"
    completed_states: int = 0
    total_states: int = 0

    # 时间：仿真时间与墙钟时间分开记录。
    # 仿真时间反映任务本身的长度，墙钟时间反映机器性能，二者不可混用。
    sim_time: float = 0.0
    wall_time: float = 0.0

    exit_code: int = ExitCode.FAILED
    error_message: Optional[str] = None
    failure_mode: Optional[str] = FailureMode.NONE

    # 运行环境快照，用于复现
    seed: Optional[int] = None
    timestamp: str = ""
    stdout_tail: str = ""   # 仅用于人工排查，不参与任何判定

    def __post_init__(self):
        if self.failure_mode is not None and self.failure_mode not in FailureMode.ALL:
            raise ValueError(
                f"未知的 failure_mode: {self.failure_mode!r}，"
                f"允许值: {FailureMode.ALL}"
            )
        if self.success and self.failure_mode is not None:
            raise ValueError(
                f"矛盾的结果：success=True 但 failure_mode={self.failure_mode!r}"
            )
        if not self.success and self.failure_mode is None:
            raise ValueError(
                "矛盾的结果：success=False 但未指定 failure_mode"
            )

    @property
    def name(self) -> str:
        """用于 JUnit XML 的用例名。"""
        return f"{self.robot}::{self.task}"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, path: str) -> None:
        """写入结果文件。子进程用它把结果交给父进程。"""
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, path: str) -> TaskResult:
        with open(path, "r", encoding="utf-8") as f:
            return cls(**json.load(f))

    @classmethod
    def from_config_error(cls, robot: str, task: str, message: str) -> TaskResult:
        """构造一个"没跑起来"的结果。"""
        return cls(
            robot=robot, task=task, success=False,
            exit_code=ExitCode.CONFIG_ERROR,
            failure_mode=FailureMode.CONFIG,
            error_message=message,
        )
