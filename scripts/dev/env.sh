# 用法: source scripts/dev/env.sh
# 目的: 建立一个与 ROS 解耦的、可复现的测试环境。

# conda 环境的解释器绝对路径。
# 不用 conda activate: 非交互式 shell(CI/Docker/cron) 里 activate 默认不工作。
export PY=/home/ubuntu22/miniconda3/envs/discoverse/bin/python

# 无头渲染后端。CI 无显示器, glfw 会直接失败。
export MUJOCO_GL=osmesa

# 关键: 清除 ROS Humble 注入的 PYTHONPATH。
#   /opt/ros/humble/.../site-packages 里的 launch_testing 注册为 pytest11 插件,
#   pytest 启动时无条件加载它 -> 依赖 lark(未装进 conda) -> ModuleNotFoundError。
#   PYTHONPATH 优先级高于 conda 的环境隔离, 必须显式清掉。
#   测试目标是 discoverse 核心库, 不需要 ROS。
unset PYTHONPATH

echo "[env] PY=$PY"
echo "[env] MUJOCO_GL=$MUJOCO_GL"
echo "[env] PYTHONPATH cleared (ROS decoupled)"
