#!/usr/bin/env python3
"""Universal Task CICD 批量测试。

Day 13-14 重构说明
-----------------
重构前，本脚本靠匹配子进程 stdout 里的 emoji 判断成败：

    if "✅ 任务成功检查通过" in output or "🎉" in output and "任务成功完成" in output:

实测证明这条判定两个方向都会错：改文案/日志剥离 emoji -> 假阴性；
失败日志里出现过 "🎉…任务成功完成" 字样 -> 假阳性。

重构后判定依据变成两条硬信息：
  1. 子进程退出码（0=成功 / 1=任务失败 / 2=配置错误）
  2. 子进程写出的结构化 JSON 结果文件

stdout 从此只用于人工排查，不参与任何判定。
"""

import os
import sys
import json
import time
import argparse
import subprocess
import concurrent.futures
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from discoverse import DISCOVERSE_ROOT_DIR
from discoverse.testing import TaskResult, FailureMode, ExitCode
from discoverse.testing.junit_report import write_junit_xml

# 白名单：与 universal_task_runtime.py 的 argparse choices 保持一致
SUPPORTED_ROBOTS = [
    "airbot_play", "panda", "ur5e", "iiwa14",
    "arx_x5", "arx_l5", "piper", "rm65", "xarm7",
]
SUPPORTED_TASKS = [
    "place_block", "cover_cup", "stack_block",
    "place_kiwi_fruit", "place_coffeecup",
]


class UnknownTargetError(ValueError):
    """用户指定了白名单之外的机器人或任务。"""


def validate_selection(robots: Sequence[str], tasks: Sequence[str]) -> None:
    """校验用户输入，未知项直接报错而非静默丢弃。

    重构前的行为：未知机器人会被照常提交执行，子进程被 argparse 拒绝，
    父进程把它记成一条普通的"测试失败"，错误信息还是无关的 traceback。
    结果是拼错机器人名看起来像任务回归，排查方向完全跑偏。
    """
    unknown_robots = [r for r in robots if r not in SUPPORTED_ROBOTS]
    unknown_tasks = [t for t in tasks if t not in SUPPORTED_TASKS]
    problems = []
    if unknown_robots:
        problems.append(
            f"未知机器人 {unknown_robots}，支持的有: {SUPPORTED_ROBOTS}")
    if unknown_tasks:
        problems.append(
            f"未知任务 {unknown_tasks}，支持的有: {SUPPORTED_TASKS}")
    if problems:
        raise UnknownTargetError("; ".join(problems))


class UniversalTaskCICD:
    """通用任务 CICD 批量测试器。"""

    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = output_dir or os.path.join(DISCOVERSE_ROOT_DIR, "cicd_reports")
        os.makedirs(self.output_dir, exist_ok=True)
        self.results: List[TaskResult] = []

    def run_single_test(self, robot: str, task: str, timeout: int = 120) -> TaskResult:
        """运行单个 (robot, task)，返回结构化结果。

        判定优先级：结果文件 > 退出码。结果文件信息更丰富（含失败模式、
        完成状态数、seed）；退出码是它缺失时的兜底，也是交叉校验的依据。
        """
        script = os.path.join(
            DISCOVERSE_ROOT_DIR, "examples/universal_tasks/universal_task_runtime.py")
        # 结果文件按 robot/task 命名，避免并行时互相覆盖
        result_file = os.path.join(self.output_dir, f".result_{robot}_{task}.json")
        if os.path.exists(result_file):
            os.remove(result_file)

        cmd = [
            sys.executable, script,
            "-r", robot, "-t", task,
            "-1", "--headless",
            "--result-json", result_file,
        ]

        print(f"🧪 测试: {robot} - {task}")
        start = time.time()

        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=timeout, cwd=DISCOVERSE_ROOT_DIR,
            )
        except subprocess.TimeoutExpired:
            elapsed = time.time() - start
            print(f"   ⏰ 超时 ({timeout}s)")
            return TaskResult(
                robot=robot, task=task, success=False,
                wall_time=elapsed, exit_code=ExitCode.FAILED,
                failure_mode=FailureMode.TIMEOUT,
                error_message=f"墙钟超时: 超过 {timeout}s 未结束",
                timestamp=datetime.now().isoformat(),
            )

        elapsed = time.time() - start
        stdout_tail = "\n".join(proc.stdout.strip().splitlines()[-15:])

        result = self._load_result_file(result_file, robot, task)

        if result is None:
            # 没有结果文件：退化到退出码判定
            result = self._result_from_returncode(
                proc.returncode, robot, task, proc.stderr)

        # 交叉校验：结果文件与退出码不一致说明契约被破坏（如段错误）
        if proc.returncode not in (ExitCode.SUCCESS, ExitCode.FAILED, ExitCode.CONFIG_ERROR):
            result = TaskResult(
                robot=robot, task=task, success=False,
                completed_states=result.completed_states,
                total_states=result.total_states,
                wall_time=elapsed, exit_code=proc.returncode,
                failure_mode=FailureMode.CRASH,
                error_message=(f"子进程异常退出码 {proc.returncode}"
                               f"（负数为信号，139 通常是段错误）"),
                timestamp=datetime.now().isoformat(),
            )
        elif result.success and proc.returncode != ExitCode.SUCCESS:
            result.success = False
            result.failure_mode = FailureMode.CRASH
            result.error_message = (
                f"结果文件称成功，但退出码为 {proc.returncode}，契约不一致")
            result.exit_code = proc.returncode

        result.wall_time = elapsed
        result.stdout_tail = stdout_tail

        if result.success:
            print(f"   ✅ 成功 ({elapsed:.2f}s, {result.completed_states}/{result.total_states} 状态)")
        else:
            print(f"   ❌ 失败 ({elapsed:.2f}s) [{result.failure_mode}] "
                  f"{(result.error_message or '')[:80]}")
        return result

    @staticmethod
    def _load_result_file(path: str, robot: str, task: str) -> Optional[TaskResult]:
        if not os.path.exists(path):
            return None
        try:
            return TaskResult.from_json(path)
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            print(f"   ⚠️  结果文件损坏 ({e})，退化到退出码判定")
            return None

    @staticmethod
    def _result_from_returncode(rc: int, robot: str, task: str,
                                stderr: str) -> TaskResult:
        """无结果文件时，仅凭退出码构造结果。"""
        if rc == ExitCode.SUCCESS:
            return TaskResult(
                robot=robot, task=task, success=True,
                exit_code=rc, timestamp=datetime.now().isoformat())
        mode = FailureMode.CONFIG if rc == ExitCode.CONFIG_ERROR else FailureMode.FINAL_CHECK
        # stderr 尾部通常才是真正的失败原因（argparse 报错、异常栈末行）
        tail = "\n".join(stderr.strip().splitlines()[-5:]) if stderr else ""
        return TaskResult(
            robot=robot, task=task, success=False,
            exit_code=rc, failure_mode=mode,
            error_message=f"无结果文件，退出码={rc}。stderr 尾部:\n{tail}",
            timestamp=datetime.now().isoformat(),
        )

    def run_batch_tests(self, robots: List[str], tasks: List[str],
                        parallel: bool = True, max_workers: int = 4,
                        timeout: int = 120) -> Dict[str, Any]:
        print("🚀 开始批量测试")
        print(f"   机械臂: {robots}")
        print(f"   任务: {tasks}")
        print(f"   并行: {parallel} (max_workers={max_workers})")
        print(f"   总计: {len(robots)} × {len(tasks)} = {len(robots) * len(tasks)} 个测试")
        print("=" * 70)

        cases = [(r, t) for r in robots for t in tasks]
        start = time.time()

        if parallel:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
                futures = [ex.submit(self.run_single_test, r, t, timeout)
                           for r, t in cases]
                for fut in concurrent.futures.as_completed(futures):
                    self.results.append(fut.result())
        else:
            for r, t in cases:
                self.results.append(self.run_single_test(r, t, timeout))

        # 结果顺序固定，便于 diff 两次运行的报告
        self.results.sort(key=lambda r: (r.robot, r.task))
        return self._generate_statistics(time.time() - start)

    def _generate_statistics(self, total_time: float) -> Dict[str, Any]:
        total = len(self.results)
        passed = sum(1 for r in self.results if r.success)

        def group(key):
            out = {}
            for r in self.results:
                k = getattr(r, key)
                bucket = out.setdefault(k, {"total": 0, "success": 0})
                bucket["total"] += 1
                bucket["success"] += int(r.success)
            for bucket in out.values():
                bucket["failure"] = bucket["total"] - bucket["success"]
                bucket["success_rate"] = bucket["success"] / bucket["total"]
            return out

        # 失败模式分布：一眼看出红灯集中在哪一类问题
        modes: Dict[str, int] = {}
        for r in self.results:
            if not r.success:
                modes[str(r.failure_mode)] = modes.get(str(r.failure_mode), 0) + 1

        wall_times = [r.wall_time for r in self.results if r.success]
        return {
            "summary": {
                "total_tests": total,
                "successful_tests": passed,
                "failed_tests": total - passed,
                "success_rate": passed / total if total else 0.0,
                "total_execution_time": total_time,
            },
            "robot_statistics": group("robot"),
            "task_statistics": group("task"),
            "failure_modes": modes,
            "performance": {
                "avg_wall_time": sum(wall_times) / len(wall_times) if wall_times else 0.0,
                "min_wall_time": min(wall_times) if wall_times else 0.0,
                "max_wall_time": max(wall_times) if wall_times else 0.0,
            },
            "failures": [r.to_dict() for r in self.results if not r.success],
        }

    def save_reports(self, stats: Dict[str, Any], junit_path: Optional[str] = None):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        results_file = os.path.join(self.output_dir, f"test_results_{ts}.json")
        with open(results_file, "w", encoding="utf-8") as f:
            json.dump([r.to_dict() for r in self.results], f,
                      indent=2, ensure_ascii=False)
        print(f"📄 详细结果: {results_file}")

        stats_file = os.path.join(self.output_dir, f"test_statistics_{ts}.json")
        with open(stats_file, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
        latest = os.path.join(self.output_dir, "latest_statistics.json")
        with open(latest, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
        print(f"📊 统计信息: {stats_file}")

        junit_path = junit_path or os.path.join(self.output_dir, "junit_results.xml")
        write_junit_xml(self.results, junit_path)
        print(f"🧾 JUnit XML: {junit_path}")

    def print_summary(self, stats: Dict[str, Any]):
        print("\n" + "=" * 70)
        print("📊 测试摘要")
        print("=" * 70)
        s = stats["summary"]
        print(f"总测试数: {s['total_tests']}")
        print(f"成功: {s['successful_tests']} ({s['success_rate']:.1%})")
        print(f"失败: {s['failed_tests']}")
        print(f"总耗时: {s['total_execution_time']:.2f}s")

        if stats["failure_modes"]:
            print("\n🔎 失败模式分布:")
            for mode, n in sorted(stats["failure_modes"].items(),
                                  key=lambda kv: -kv[1]):
                print(f"  {mode}: {n}")

        print("\n🤖 机械臂成功率:")
        for robot, st in sorted(stats["robot_statistics"].items()):
            print(f"  {robot}: {st['success']}/{st['total']} ({st['success_rate']:.1%})")

        print("\n📋 任务成功率:")
        for task, st in sorted(stats["task_statistics"].items()):
            print(f"  {task}: {st['success']}/{st['total']} ({st['success_rate']:.1%})")

        if stats["failures"]:
            print(f"\n❌ 失败详情 ({len(stats['failures'])} 个):")
            for f in stats["failures"][:10]:
                print(f"  {f['robot']}-{f['task']} [{f['failure_mode']}] "
                      f"{f['completed_states']}/{f['total_states']} 状态")


def main():
    parser = argparse.ArgumentParser(description="Universal Task CICD Testing")
    parser.add_argument("-r", "--robots", nargs="+", help="指定机械臂 (默认: 全部)")
    parser.add_argument("-t", "--tasks", nargs="+", help="指定任务 (默认: 全部)")
    parser.add_argument("-o", "--output", type=str, help="输出目录")
    parser.add_argument("--junit-xml", type=str, help="JUnit XML 输出路径")
    parser.add_argument("--serial", action="store_true", help="串行执行 (默认: 并行)")
    parser.add_argument("--workers", type=int, default=4, help="并行工作数 (默认: 4)")
    parser.add_argument("--timeout", type=int, default=120,
                        help="单个测试超时/秒 (默认: 120)")
    args = parser.parse_args()

    robots = args.robots or SUPPORTED_ROBOTS
    tasks = args.tasks or SUPPORTED_TASKS

    try:
        validate_selection(robots, tasks)
    except UnknownTargetError as e:
        print(f"❌ 参数错误: {e}", file=sys.stderr)
        # 配置错误与"测试失败"用不同退出码，便于 CI 区分基础设施问题
        sys.exit(ExitCode.CONFIG_ERROR)

    cicd = UniversalTaskCICD(output_dir=args.output)
    stats = cicd.run_batch_tests(
        robots=robots, tasks=tasks,
        parallel=not args.serial, max_workers=args.workers,
        timeout=args.timeout,
    )
    cicd.save_reports(stats, junit_path=args.junit_xml)
    cicd.print_summary(stats)

    # 批量测试的退出码同样必须反映成败，否则 CI 依旧永远绿灯
    sys.exit(ExitCode.SUCCESS if stats["summary"]["failed_tests"] == 0
             else ExitCode.FAILED)


if __name__ == "__main__":
    main()
