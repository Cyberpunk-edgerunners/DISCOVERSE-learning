# 用法: source scripts/dev/env.sh
# 目的: 建立一个与 ROS 解耦的、可复现的测试环境。

# ---- Python 解释器 ----
# 按优先级探测，不硬编码绝对路径（否则换机器/进 CI 就失效）:
#   1. 调用者已设的 $PY        —— 显式覆盖优先
#   2. conda 环境 discoverse   —— 本项目约定的环境名
#   3. 当前激活的 conda 环境
#   4. PATH 上的 python3
if [ -z "$PY" ]; then
    for _cand in \
        "$HOME/miniconda3/envs/discoverse/bin/python" \
        "$HOME/anaconda3/envs/discoverse/bin/python" \
        "$CONDA_PREFIX/bin/python" \
        "$(command -v python3)"
    do
        if [ -x "$_cand" ]; then
            export PY="$_cand"
            break
        fi
    done
    unset _cand
fi

if [ -z "$PY" ]; then
    echo "[env] 错误: 未找到 Python 解释器。请手动设置: export PY=/path/to/python" >&2
    return 1 2>/dev/null || exit 1
fi

# ---- 渲染后端 ----
# 无头渲染。CI 无显示器, glfw 会直接失败。
export MUJOCO_GL=osmesa

# ---- 关键: 清除 ROS 注入的 PYTHONPATH ----
#   ROS Humble 的 setup.bash 导出 PYTHONPATH, 其中 launch_testing 注册为
#   pytest11 插件, pytest 启动时无条件加载它 -> 依赖 lark(未装进 conda)
#   -> ModuleNotFoundError; 另有 launch_testing_ros_pytest_entrypoint
#   注册了 pytest 9 已移除的 hook -> PluginValidationError -> INTERNALERROR。
#   PYTHONPATH 优先级高于 conda 的环境隔离, 必须显式清掉。
#   测试目标是 discoverse 核心库, 不需要 ROS。
#   注意: 不能用 `pytest -p no:launch_testing` 打补丁 ——
#   那要求插件先被成功导入才能禁用, 导入期就炸的话来不及。
if [ -n "$PYTHONPATH" ]; then
    unset PYTHONPATH
    _ros_cleared="yes"
else
    _ros_cleared="already clean"
fi

echo "[env] PY=$PY"
echo "[env] MUJOCO_GL=$MUJOCO_GL"
echo "[env] PYTHONPATH cleared (ROS decoupled): $_ros_cleared"
unset _ros_cleared