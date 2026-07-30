# DISCOVERSE - 具身智能机器人仿真平台

> 基于 MuJoCo + 3D Gaussian Splatting 的高保真机器人仿真框架  
> IROS 2025 | MIT License | Python 3.8+

---

## 项目概述

DISCOVERSE 是一个高保真机器人仿真平台，专注于：
- **通用操作**：支持 9 种机械臂 + 2 种双臂移动机器人
- **高保真渲染**：基于 3D Gaussian Splatting 的真实场景
- **策略学习**：集成 5 种主流模仿学习和强化学习算法
- **数据采集**：完整的仿真数据采集和验证系统

**项目规模**：382 个 Python 文件，768 MB 仓库

---

## 架构概览

```
DISCOVERSE/
├── discoverse/              # 核心库（52个文件）
│   ├── envs/               # 仿真环境（SimulatorBase）
│   ├── robots/             # 机器人IK实现（airbot_play, mmk2）
│   ├── robots_env/         # 机器人环境基类（7个base）
│   ├── task_base/          # 任务基类（4个base）
│   ├── universal_manipulation/  # 通用操作框架 ⭐
│   ├── configs/            # 配置文件（9机器人 + 5任务）
│   └── docker/             # Docker镜像
├── examples/               # 示例代码（84个文件）
│   ├── universal_tasks/    # 通用任务运行时 ⭐
│   ├── tasks_airbot_play/  # AirBot Play任务示例
│   ├── tasks_mmk2/         # MMK2双臂移动任务示例
│   └── ros1/, ros2/        # ROS集成
├── models/                 # 3D模型和MJCF场景
│   ├── mjcf/              # MuJoCo XML场景（13个任务环境）
│   ├── meshes/            # 3D网格（15类机器人）
│   └── urdf/              # URDF机器人描述
├── policies/              # 策略学习（237个文件）
│   ├── act/               # Action Chunking Transformer
│   ├── Diffusion-Policy/  # 扩散策略
│   ├── RDT/               # Robotics Diffusion Transformer
│   ├── openpi/            # OpenPI策略
│   └── RL/                # 强化学习（PPO）
└── scripts/               # 工具脚本
```

---

## 核心技术栈

### 仿真引擎
- **MuJoCo 3.2.0** - 高保真物理仿真
- **3D Gaussian Splatting** - 真实场景渲染
- **CUDA 11.8** - GPU加速

### 机器人支持
**机械臂**（9种）：
- AirBot Play, Franka Panda, UR5e, KUKA iiwa14
- ARX-X5, ARX-L5, Piper, RM65, xArm7

**双臂移动机器人**（2种）：
- **MMK2**：19 自由度（2轮 + 1升降 + 2头部 + 12臂 + 4夹爪）
- **Tok2**：16 自由度（简化版，腱传动底盘）

### 控制方法
- 位置控制 / 阻抗控制（力控）
- IK控制（Mink求解器）
- 差速驱动（MMK2/Tok2移动底盘）

### 策略学习
- **ACT** - Action Chunking Transformer
- **Diffusion Policy** - 扩散策略
- **RDT** - Robotics Diffusion Transformer
- **OpenPI** - Physical Intelligence开源策略
- **PPO** - 强化学习（Stable Baselines3）

---

## 关键模块说明

### 1. 通用操作框架（`discoverse/universal_manipulation/`）
**核心抽象**，支持多机器人多任务：
- `task_base.py` - UniversalTaskBase 任务基类
- `robot_interface.py` - 统一机器人接口
- `mink_solver.py` - IK求解器
- `recorder.py` - 数据记录器（视频+obs-action）
- `randomization.py` - 域随机化

### 2. CICD测试框架（`examples/universal_tasks/cicd_testing.py`）
自动化测试系统，支持：
- 9种机器人 × 5种任务 = 45个测试组合
- 并行执行、超时控制、JSON报告
- 状态机验证、成功率统计

### 3. MMK2双臂移动机器人（⭐ 重点）
**文件位置**：
- `discoverse/robots_env/mmk2_base.py` - 控制基类
- `discoverse/robots/mmk2/mmk2_fik.py` - IK求解器
- `models/mjcf/mobile_chassis/mmk2/` - MJCF模型

**控制接口**：
```python
# 19 自由度控制
action = np.zeros(19)
action[0:2]   # 左右轮速度（差速驱动）
action[2]     # 升降高度（0-0.87m）
action[3:5]   # 头部云台（俯仰+偏航）
action[5:11]  # 左臂6轴
action[11:17] # 右臂6轴
action[17:19] # 左右夹爪
```

### 4. 数据采集（`discoverse/universal_manipulation/recorder.py`）
**功能**：
- 视频编码（H.264, MP4）
- obs-action对记录（JSON/zarr格式）
- 多相机同步录制
- 时间戳精确记录

---

## 配置系统

### 机器人配置（`discoverse/configs/robots/*.yaml`）
```yaml
# airbot_play.yaml 示例
robot_name: airbot_play
dof: 6
joint_limits: [...]
workspace:
  x_min: 0.2
  x_max: 0.6
  ...
```

### 任务配置（`discoverse/configs/tasks/*.yaml`）
```yaml
# place_block.yaml 示例
task_name: place_block
scene: task_environments/place_block.xml
success_conditions:
  - type: distance
    object_a: block
    object_b: target
    threshold: 0.05
```

---

## 常用工作流

### 1. 运行单个任务
```bash
# AirBot Play 放置方块
python examples/tasks_airbot_play/place_block.py

# MMK2 抓取盒子
python examples/tasks_mmk2/box_pick.py
```

### 2. 批量测试（CICD）
```bash
python examples/universal_tasks/cicd_testing.py \
  --robots airbot_play panda ur5e \
  --tasks place_block cover_cup \
  --headless \
  --report test_report.json
```

### 3. 数据采集
```bash
python scripts/tasks_data_gen.py \
  --robot airbot_play \
  --task place_block \
  --num_episodes 100 \
  --output_dir ./datasets/
```

### 4. 策略训练
```bash
# RDT
cd policies/RDT
bash train.sh

# Diffusion Policy
cd policies/Diffusion-Policy
python train.py --config configs/airbot_play_place_block.yaml
```

---

## 开发指南

### 添加新机器人
1. 在 `models/mjcf/manipulator/` 创建MJCF模型
2. 在 `discoverse/configs/robots/` 添加配置YAML
3. 在 `discoverse/robots_env/` 创建环境基类（可选）
4. 实现IK求解器（可选）

### 添加新任务
1. 在 `models/mjcf/task_environments/` 创建场景XML
2. 在 `discoverse/configs/tasks/` 添加任务配置
3. 在 `examples/tasks_*/` 创建任务示例脚本
4. 定义成功条件（distance/position/orientation）

### 自定义数据记录
```python
from discoverse.universal_manipulation.recorder import Recorder

recorder = Recorder(output_dir='./data', fps=30)
recorder.start_recording()

# 仿真循环
for step in range(1000):
    obs, action = ...
    recorder.record_step(obs, action)

recorder.stop_recording()
```

---

## Docker使用

### 标准镜像
```bash
cd discoverse/docker
docker build -t discoverse:latest -f Dockerfile .
docker run --gpus all -it discoverse:latest
```

### VNC远程访问
```bash
docker build -t discoverse:vnc -f Dockerfile.vnc .
docker run -p 6901:6901 --gpus all discoverse:vnc
# 浏览器访问 http://localhost:6901
```

---

## 测试体系

### 现有测试
- **策略测试**：`policies/openpi/` 下 14 个测试文件
- **CICD框架**：`examples/universal_tasks/cicd_testing.py`
- **硬件在环**：`examples/hardware_sim/example/`

### 测试覆盖现状
- 整体覆盖率：~5%（需提升到75%+）
- 核心模块：基本无单元测试（待补充）

### 运行测试
```bash
# 运行现有测试
pytest policies/openpi/ -v

# 运行CICD测试框架
python examples/universal_tasks/cicd_testing.py --robots airbot_play --tasks place_block
```

**详细测试开发方案**：见 `source-notes/DISCOVERSE测试开发完整方案.md`

---

## 重要注意事项

### 1. MuJoCo渲染设置
```bash
export MUJOCO_GL=glfw    # 有显示器
export MUJOCO_GL=osmesa  # 无显示器（CI环境）
export MUJOCO_GL=egl     # GPU加速无头渲染
```

### 2. 大文件管理
- `models/` 目录包含大量3D模型（~500MB）
- `policies/` 子模块需要单独初始化：
  ```bash
  python scripts/setup_submodules.py
  ```

### 3. 性能考虑
- 仿真FPS：30-60（取决于场景复杂度）
- IK求解速度：5-10 ms（单次）
- 策略推理延迟：20-50 ms

### 4. 已知问题
- 某些复杂场景的接触检测可能不稳定
- 多相机渲染可能导致内存占用高
- 详见 `discoverse/doc/troubleshooting.md`

---

## 文档资源

### 官方文档（`discoverse/doc/`）
- `usage.md` - 使用指南
- `troubleshooting.md` - 故障排查（13KB）
- `automated_data_generation.md` - 自动数据生成
- `imitation_learning/` - 模仿学习文档
- `hardware_sim/README.md` - 硬件在环仿真

### 源码分析文档（`source-notes/`）
- `1.DISCOVERSE源码深度分析.md` - 核心分析（36KB）
- `2.DISCOVERSE架构图·时序图.md` - 架构可视化
- `DISCOVERSE测试开发完整方案.md` - 测试开发方案（64KB）⭐

---

## 协作建议

### 对 Claude 的建议

1. **代码修改前先读取**：核心文件（simulator.py, recorder.py, mmk2_base.py）应先Read再修改
2. **利用现有基础**：优先扩展 `universal_manipulation` 框架，而非创建新抽象
3. **遵循配置驱动**：新机器人/任务应通过YAML配置，而非硬编码
4. **测试优先**：参考 `cicd_testing.py` 编写集成测试
5. **文档同步**：代码变更应同步更新相应文档

### 关键设计原则

- **通用性**：支持多种机器人的统一接口
- **可扩展性**：模块化设计，易于添加新机器人/任务
- **可复现性**：确定性仿真（相同种子→相同结果）
- **数据驱动**：完整的数据采集和验证流程

---

## 快速参考

### 关键类和函数

```python
# 创建环境
from discoverse.envs import make_env
env = make_env('airbot_play', 'place_block', render_mode='human')

# 通用任务基类
from discoverse.universal_manipulation.task_base import UniversalTaskBase

# IK求解
from discoverse.universal_manipulation.mink_solver import MinkSolver
solver = MinkSolver(robot_config)
joints = solver.solve(target_pose)

# 数据记录
from discoverse.universal_manipulation.recorder import Recorder
recorder = Recorder(output_dir='./data')
```

### 环境变量

```bash
MUJOCO_GL=glfw              # MuJoCo渲染后端
PYTHONPATH=.                # Python路径（如果未安装）
CUDA_VISIBLE_DEVICES=0      # 指定GPU
```

### 常用路径

```bash
discoverse/envs/simulator.py                          # 仿真器基类
discoverse/universal_manipulation/task_base.py        # 任务基类
discoverse/robots_env/mmk2_base.py                    # MMK2控制
examples/universal_tasks/cicd_testing.py              # CICD测试
models/mjcf/task_environments/                        # 任务场景
```

---

## 联系和支持

- **GitHub Issues**: 报告bug和功能请求
- **Documentation**: `discoverse/doc/` 目录
- **Examples**: `examples/` 目录包含84个示例
- **测试开发指南**: `source-notes/DISCOVERSE测试开发完整方案.md`

---

**最后更新**: 2026-07-26  
**维护者**: DISCOVERSE Team  
**许可证**: MIT License
