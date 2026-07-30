#!/usr/bin/env python
"""调用链追踪工具 —— monkey-patch + traceback 打印真实调用栈。

静态 grep 只能看出「谁 import 谁」，看不出「哪条路径真的被执行」。
本工具给任意函数打桩，在首次调用时打印完整调用栈，用来验证静态分析的结论。

用法：
    # 默认 4 个探针（IK / 随机化 / 视频编码）
    MUJOCO_GL=osmesa python scripts/dev/trace_chain.py -r airbot_play -t cover_cup

    # 只追某一个目标
    MUJOCO_GL=osmesa python scripts/dev/trace_chain.py -r airbot_play -t place_block \
        --probe discoverse.universal_manipulation.mink_solver:MinkIKSolver.solve_ik

末尾会打印「本次实际触发的探针」。**没触发的探针和触发的一样重要** ——
例如 PyavImageEncoder.encode 在 place_block 下不触发，说明该任务全程不录视频。
"""
import argparse
import importlib
import os
import sys
import traceback

DISCOVERSE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 默认探针：覆盖三条核心链路（运动学 / 随机化 / 数据流）
DEFAULT_PROBES = [
    "discoverse.universal_manipulation.mink_solver:MinkIKSolver.solve_ik",
    "discoverse.universal_manipulation.randomization:SceneRandomizer.exec_randomization",
    "discoverse.universal_manipulation.randomization:SceneRandomizer._generate_random_position_in_bounds",
    "discoverse.universal_manipulation.recorder:PyavImageEncoder.encode",
]

# 调用栈里只保留项目自身的帧，滤掉 mujoco / numpy 等第三方噪音
STACK_KEEP = ("discoverse", "universal_task_runtime", "trace_chain")

fired = []


def resolve_probe(spec):
    """把 "module:Class.method" 或 "module:function" 解析成 (owner, attr)。"""
    if ":" not in spec:
        raise ValueError(f"探针格式应为 module:Class.method 或 module:function，收到: {spec}")
    module_path, target = spec.split(":", 1)
    owner = importlib.import_module(module_path)
    *parents, attr = target.split(".")
    for parent in parents:
        owner = getattr(owner, parent)
    return owner, attr


def make_probe(owner, attr, label, verbose_stack=True):
    """给 owner.attr 打桩，首次调用时打印完整调用栈。

    这套 monkey-patch 模式的六个要点，缺一不可：
      ① 通过模块对象拿到目标（不能 from x import y，那样改不到原处）
      ② 先保存原函数
      ③ 替身用 *args/**kwargs 保证签名兼容
      ④ 必须 return orig(...)，否则程序行为被改变
      ⑤ 用 setattr 替换类属性，所有实例生效
      ⑥ 必须在目标被调用之前完成替换
    """
    orig = getattr(owner, attr)                      # ②

    def traced(*args, **kwargs):                     # ③
        if label not in fired:
            fired.append(label)
            print(f"\n{'=' * 70}")
            print(f"### PROBE [{label}] 首次调用，调用栈（外 → 内）：")
            for line in traceback.format_stack()[:-1]:
                line = line.rstrip()
                if not verbose_stack and not any(k in line for k in STACK_KEEP):
                    continue
                print(line)
            print(f"{'=' * 70}\n")
        return orig(*args, **kwargs)                 # ④

    setattr(owner, attr, traced)                     # ⑤


def main():
    parser = argparse.ArgumentParser(
        description="monkey-patch 调用链追踪（Day1 上午 Step3 工具）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("-r", "--robot", default="airbot_play", help="机械臂名称")
    parser.add_argument("-t", "--task", default="cover_cup", help="任务名称")
    parser.add_argument(
        "--probe",
        action="append",
        metavar="MODULE:Class.method",
        help="追踪目标，可重复传。不传则使用默认的 4 个探针",
    )
    parser.add_argument("--full-stack", action="store_true",
                        help="打印完整调用栈（默认只保留项目自身的帧）")
    parser.add_argument("--headed", action="store_true", help="带可视化窗口运行（默认无头）")
    args = parser.parse_args()

    # universal_task_runtime.py 不是包内模块，需手动加入搜索路径
    sys.path.insert(0, os.path.join(DISCOVERSE_ROOT, "examples", "universal_tasks"))

    specs = args.probe or DEFAULT_PROBES
    for spec in specs:
        owner, attr = resolve_probe(spec)            # ①
        label = spec.split(":", 1)[1]
        make_probe(owner, attr, label, verbose_stack=args.full_stack)
    print(f"🔎 已安装 {len(specs)} 个探针: {[s.split(':', 1)[1] for s in specs]}")

    import universal_task_runtime as u               # ⑥ 替换完成后才导入并运行

    u.main(args.robot, args.task, once=True, headless=not args.headed)

    print(f"\n### 本次运行实际触发的探针（{len(fired)}/{len(specs)}）：")
    for label in sorted(fired):
        print(f"   ✅ {label}")
    missed = [s.split(":", 1)[1] for s in specs if s.split(":", 1)[1] not in fired]
    for label in sorted(missed):
        print(f"   ⬜ {label}  ← 未触发：这条链路在本组合下不执行，本身就是情报")


if __name__ == "__main__":
    main()
