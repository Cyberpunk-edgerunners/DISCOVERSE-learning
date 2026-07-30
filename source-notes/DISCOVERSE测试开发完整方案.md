# DISCOVERSE 测试开发完整方案

> **面向对象**：从传统测试转型具身智能测试开发  
> **分析角度**：企业级全栈测试架构（Docker + CI/CD + 仿真验证）  
> **重点领域**：双臂轮式移动操作机器人  
> **生成日期**：2026-07-26

---

## 目录

1. [项目概览与测试现状](#一项目概览与测试现状)
2. [具身智能测试的核心挑战](#二具身智能测试的核心挑战)
3. [测试架构设计](#三测试架构设计)
4. [双臂轮式机器人专项测试](#四双臂轮式机器人专项测试)
5. [CI/CD 流水线设计](#五cicd-流水线设计)
6. [Docker 测试环境](#六docker-测试环境)
7. [数据采集与验证增强](#七数据采集与验证增强)
8. [测试工具开发](#八测试工具开发)
9. [实施路线图](#九实施路线图)
10. [关键代码示例](#十关键代码示例)

---

## 一、项目概览与测试现状

### 1.1 DISCOVERSE 项目背景

**核心技术**：
- 基于 MuJoCo 3.2.0 的高保真物理仿真
- 3D Gaussian Splatting 真实场景渲染
- 支持 9 种机械臂 + 2 种双臂移动机器人
- 集成 5 种主流策略学习算法（ACT/DP/RDT/OpenPI/PPO）

**项目规模**：
- Python 文件：382 个
- 核心模块：52 个（`discoverse/`）
- 示例代码：84 个（`examples/`）
- 策略算法：237 个文件（`policies/`）
- 仓库大小：768 MB

### 1.2 当前测试覆盖情况

#### ✅ 已有测试资产

1. **CI/CD 测试框架**
   - 文件：`/home/ubuntu22/workspaces/airbot-play/DISCOVERSE/examples/universal_tasks/cicd_testing.py`
   - 功能：9 种机械臂 × 5 种任务 = 45 个测试组合
   - 特性：并行执行、JSON 报告、超时控制

2. **策略模块测试**
   - 位置：`/home/ubuntu22/workspaces/airbot-play/DISCOVERSE/policies/openpi/`
   - 数量：14 个 `*_test.py` 文件
   - 框架：pytest + unittest

3. **硬件在环测试**
   - 位置：`/home/ubuntu22/workspaces/airbot-play/DISCOVERSE/examples/hardware_sim/example/`
   - 类型：真实机器人与仿真联合测试

4. **安装验证脚本**
   - `scripts/check_installation.py`
   - `scripts/check_mujoco_install.py`

#### ❌ 测试缺口分析

1. **无自动化 CI/CD**
   - 缺少 `.github/workflows/` 配置
   - 缺少 GitLab CI 配置
   - 无自动化测试触发机制

2. **核心模块测试不足**
   - 52 个核心文件无对应单元测试
   - 缺少 `tests/` 目录结构
   - 无测试覆盖率报告

3. **测试文档缺失**
   - README 未提及测试运行方法
   - 无测试编写规范
   - 无 CI/CD 使用文档

4. **数据质量验证薄弱**
   - 无数据集版本管理（DVC/Git LFS）
   - 缺少数据质量自动检查
   - Sim2Real 验证工具缺失

### 1.3 企业测试需求分析

从企业角度看，DISCOVERSE 作为具身智能仿真平台需要：

| 测试类型 | 当前状态 | 企业需求 | 优先级 |
|---------|---------|---------|--------|
| **单元测试** | 14 个文件（策略模块） | 核心模块 80% 覆盖率 | P0 |
| **集成测试** | CICD 测试框架 | 自动化 CI 触发 | P0 |
| **性能测试** | 无 | IK/推理/仿真性能基准 | P1 |
| **数据验证** | 基础 Recorder | 质量检查 + 版本管理 | P0 |
| **回归测试** | 手动运行 | 自动化回归套件 | P1 |
| **Sim2Real** | 无 | 仿真-真实数据对比 | P2 |

---

## 二、具身智能测试的核心挑战

### 2.1 物理仿真的确定性

**挑战**：
- MuJoCo 数值积分的浮点误差
- 多线程渲染的随机性
- 接触检测的非确定性

**解决方案**：
```python
# tests/simulation/test_determinism.py
def test_simulation_determinism():
    """验证相同种子产生相同轨迹"""
    def run_simulation(seed):
        env = make_env('airbot_play', 'place_block', seed=seed)
        trajectory = []
        for _ in range(100):
            action = env.action_space.sample()
            obs, _, _, _ = env.step(action)
            trajectory.append(obs['joint_positions'])
        return np.array(trajectory)
    
    traj1 = run_simulation(seed=42)
    traj2 = run_simulation(seed=42)
    
    # 允许小的数值误差（1e-6）
    np.testing.assert_allclose(traj1, traj2, rtol=1e-5, atol=1e-6)
```

### 2.2 IK 求解器的精度验证

**挑战**：
- 多解性（同一目标多个关节配置）
- 奇异点附近的不稳定
- 碰撞约束下的可达性

**测试策略**：
```python
# tests/kinematics/test_ik_accuracy.py
@pytest.mark.parametrize("robot", ["airbot_play", "panda", "mmk2_left"])
def test_ik_accuracy(robot):
    """测试 IK 求解精度"""
    ik_solver = get_ik_solver(robot)
    test_cases = generate_reachable_poses(robot, num=100)
    
    success_count = 0
    position_errors = []
    orientation_errors = []
    
    for target_pose in test_cases:
        joint_solution = ik_solver.solve(target_pose)
        
        if joint_solution is not None:
            actual_pose = ik_solver.forward_kinematics(joint_solution)
            pos_error = np.linalg.norm(actual_pose[:3] - target_pose[:3])
            ori_error = rotation_distance(actual_pose[3:], target_pose[3:])
            
            if pos_error < 0.003 and ori_error < 0.01:  # 3mm, 0.57°
                success_count += 1
            
            position_errors.append(pos_error)
            orientation_errors.append(ori_error)
    
    # 断言和指标记录
    assert success_count / len(test_cases) > 0.95
    logger.info(f"平均位置误差: {np.mean(position_errors)*1000:.2f}mm")
    logger.info(f"平均姿态误差: {np.mean(orientation_errors)*180/np.pi:.2f}°")
```

### 2.3 多模态传感器数据同步

**挑战**：
- RGB-D 对齐
- 多相机时间戳同步
- 点云数据完整性

**验证方法**：
```python
# tests/sensors/test_multimodal_sync.py
def test_camera_depth_alignment():
    """测试 RGB 和深度图对齐"""
    env = create_env_with_cameras()
    obs = env.reset()
    
    rgb = obs['camera/color/image']  # (H, W, 3)
    depth = obs['camera/aligned_depth/image']  # (H, W)
    
    # 1. 尺寸一致性
    assert rgb.shape[:2] == depth.shape[:2]
    
    # 2. 深度值合理性
    assert depth.min() >= 0
    assert depth.max() < 10.0  # 10米内
    assert np.sum(depth == 0) < 0.1 * depth.size  # 空洞<10%
    
    # 3. 对齐精度验证
    # 已知场景中有一个立方体在 (0.5, 0.0, 0.3)
    cube_pos = env.get_object_position("target_cube")
    pixel_x, pixel_y = project_3d_to_pixel(cube_pos, env.camera_intrinsics)
    depth_at_cube = depth[pixel_y, pixel_x]
    
    # 反投影回 3D
    reconstructed_pos = pixel_to_world(
        pixel_x, pixel_y, depth_at_cube, 
        env.camera_intrinsics, env.camera_extrinsics
    )
    
    # 允许 5cm 误差
    assert np.linalg.norm(reconstructed_pos - cube_pos) < 0.05
```

### 2.4 策略学习的评估指标

**挑战**：
- 成功率受环境随机性影响
- 训练曲线不稳定
- Overfitting 到仿真环境

**多维度评估**：
```python
# tests/policies/test_policy_quality.py
@dataclass
class PolicyMetrics:
    success_rate: float
    avg_execution_time: float
    smoothness_score: float  # 动作平滑度
    energy_efficiency: float  # 能量效率
    collision_count: int
    
def evaluate_policy(policy, env_name, num_episodes=100):
    """全面评估策略性能"""
    metrics = []
    
    for episode in range(num_episodes):
        env = make_env(env_name, randomize=True)
        obs = env.reset()
        
        trajectory = []
        collisions = 0
        total_energy = 0
        
        for step in range(500):
            action = policy.predict(obs)
            obs, reward, done, info = env.step(action)
            
            trajectory.append(action)
            total_energy += np.sum(np.abs(action))
            if info.get('collision', False):
                collisions += 1
            
            if done:
                break
        
        # 计算指标
        smoothness = calculate_smoothness(np.array(trajectory))
        
        metrics.append(PolicyMetrics(
            success_rate=float(info.get('success', False)),
            avg_execution_time=step * env.dt,
            smoothness_score=smoothness,
            energy_efficiency=1.0 / (total_energy + 1e-6),
            collision_count=collisions
        ))
    
    return aggregate_metrics(metrics)
```

---

## 三、测试架构设计

### 3.1 分层测试金字塔

```
         ┌─────────────────┐
         │  E2E Tests (5%)  │  ← 完整数据流：采集→训练→部署
         └─────────────────┘
       ┌───────────────────────┐
       │ Integration Tests (20%)│ ← 模块协同、任务执行
       └───────────────────────┘
     ┌───────────────────────────────┐
     │   Unit Tests (75%)             │ ← 单函数、单类测试
     └───────────────────────────────┘
```

### 3.2 测试目录结构

```
DISCOVERSE/
├── tests/                          # 新增测试目录
│   ├── conftest.py                # pytest 配置和 fixtures
│   ├── unit/                      # 单元测试
│   │   ├── test_simulator.py
│   │   ├── test_ik_solver.py
│   │   ├── test_recorder.py
│   │   ├── test_config_loader.py
│   │   └── test_randomization.py
│   ├── integration/               # 集成测试
│   │   ├── test_universal_tasks.py
│   │   ├── test_ros_integration.py
│   │   └── test_policy_inference.py
│   ├── simulation/                # 仿真专项测试
│   │   ├── test_determinism.py
│   │   ├── test_physics_accuracy.py
│   │   └── test_contact_dynamics.py
│   ├── kinematics/                # 运动学测试
│   │   ├── test_ik_accuracy.py
│   │   ├── test_trajectory_planning.py
│   │   └── test_collision_detection.py
│   ├── sensors/                   # 传感器测试
│   │   ├── test_camera_calibration.py
│   │   ├── test_multimodal_sync.py
│   │   └── test_lidar_rendering.py
│   ├── policies/                  # 策略测试
│   │   ├── test_policy_loading.py
│   │   ├── test_inference_speed.py
│   │   └── test_policy_quality.py
│   ├── mobile_manipulation/       # 双臂轮式专项
│   │   ├── test_mmk2_control.py
│   │   ├── test_differential_drive.py
│   │   ├── test_dual_arm_coordination.py
│   │   └── test_mobile_navigation.py
│   ├── e2e/                       # 端到端测试
│   │   ├── test_data_collection_pipeline.py
│   │   ├── test_training_pipeline.py
│   │   └── test_deployment_workflow.py
│   ├── benchmarks/                # 性能基准测试
│   │   ├── benchmark_ik_solver.py
│   │   ├── benchmark_inference.py
│   │   └── benchmark_simulation_fps.py
│   └── fixtures/                  # 测试数据和 fixtures
│       ├── robot_configs/
│       ├── task_configs/
│       └── test_trajectories/
├── examples/
│   └── universal_tasks/
│       └── cicd_testing.py        # 保留原有 CI/CD 测试
└── pyproject.toml                 # 更新测试配置
```

### 3.3 pytest 配置增强

```toml
# pyproject.toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
python_classes = "Test*"
python_functions = "test_*"

# 测试标记
markers = [
    "unit: 单元测试（快速）",
    "integration: 集成测试（中速）",
    "simulation: 仿真测试（需要 MuJoCo）",
    "kinematics: 运动学测试",
    "sensors: 传感器测试",
    "policies: 策略测试",
    "mobile: 移动操作测试",
    "e2e: 端到端测试（慢速）",
    "benchmark: 性能基准测试",
    "slow: 长时间运行测试（>30s）",
    "gpu: 需要 GPU",
    "hardware: 需要真实硬件",
]

# 并行执行
addopts = [
    "-v",
    "--strict-markers",
    "--tb=short",
    "--cov=discoverse",
    "--cov-report=html",
    "--cov-report=term-missing",
    "-n", "auto",  # pytest-xdist 并行
]

# 超时设置
timeout = 300
timeout_method = "thread"

# 日志配置
log_cli = true
log_cli_level = "INFO"
log_file = "tests/logs/pytest.log"
```

---

## 四、双臂轮式机器人专项测试

### 4.1 MMK2 机器人概述

**硬件配置**：
- 差速驱动底盘：2 个驱动轮（轮距 0.189m，轮径 0.0838m）
- 升降机构：行程 0.87m，速度 0.05 m/s
- 双臂系统：每个臂 6 DOF + 2 指夹爪
- 传感器：双自由度云台 + RGB-D 相机 + IMU

**控制自由度**：19 DOF
```python
# discoverse/robots_env/mmk2_base.py
CONTROL_DIMS = {
    'base_wheels': 2,      # 左右轮速度
    'base_lift': 1,        # 升降高度
    'head_pan_tilt': 2,    # 云台俯仰偏航
    'left_arm': 6,         # 左臂关节
    'right_arm': 6,        # 右臂关节
    'left_gripper': 2,     # 左夹爪
    'right_gripper': 2,    # 右夹爪
}
```

### 4.2 差速驱动测试

```python
# tests/mobile_manipulation/test_differential_drive.py
import pytest
import numpy as np

class TestDifferentialDrive:
    """差速驱动底盘测试"""
    
    def test_straight_line_motion(self):
        """测试直线运动"""
        env = make_env('mmk2', 'navigation')
        env.reset()
        
        initial_pos = env.get_base_position()
        
        # 相同轮速 → 直线运动
        for _ in range(100):
            action = np.zeros(19)
            action[0] = 0.5  # 左轮
            action[1] = 0.5  # 右轮
            env.step(action)
        
        final_pos = env.get_base_position()
        displacement = final_pos - initial_pos
        
        # 验证：沿 X 轴移动，Y/Z 方向偏移小
        assert displacement[0] > 0.3  # 前进 > 30cm
        assert abs(displacement[1]) < 0.05  # 横向偏移 < 5cm
        assert abs(displacement[2]) < 0.01  # 高度变化 < 1cm
    
    def test_turning_radius(self):
        """测试转弯半径"""
        env = make_env('mmk2', 'navigation')
        env.reset()
        
        # 左轮静止，右轮转动 → 左转
        trajectory = []
        for _ in range(200):
            action = np.zeros(19)
            action[0] = 0.0   # 左轮
            action[1] = 0.5   # 右轮
            env.step(action)
            trajectory.append(env.get_base_position()[:2])
        
        trajectory = np.array(trajectory)
        
        # 拟合圆形轨迹
        center, radius = fit_circle(trajectory)
        
        # 理论转弯半径 = 轮距/2 = 0.0945m
        assert abs(radius - 0.0945) < 0.01  # 误差 < 1cm
    
    def test_odometry_accuracy(self):
        """测试里程计精度"""
        env = make_env('mmk2', 'navigation')
        env.reset()
        
        # 执行一个正方形轨迹
        commands = [
            ('forward', 1.0),
            ('turn_left', np.pi/2),
            ('forward', 1.0),
            ('turn_left', np.pi/2),
            ('forward', 1.0),
            ('turn_left', np.pi/2),
            ('forward', 1.0),
        ]
        
        for cmd, param in commands:
            execute_motion_command(env, cmd, param)
        
        final_pos = env.get_base_position()
        initial_pos = np.array([0, 0, 0])
        
        # 理论上应该回到起点
        error = np.linalg.norm(final_pos[:2] - initial_pos[:2])
        assert error < 0.1  # 累积误差 < 10cm
```

### 4.3 双臂协同控制测试

```python
# tests/mobile_manipulation/test_dual_arm_coordination.py
import pytest
import numpy as np

class TestDualArmCoordination:
    """双臂协同控制测试"""
    
    def test_bimanual_grasping(self):
        """测试双臂协同抓取"""
        env = make_env('mmk2', 'bimanual_pick')
        obs = env.reset()
        
        # 目标：两个臂同时抓取长方体的两端
        box_pose = env.get_object_pose('long_box')
        
        # 计算左右抓取点
        left_target = box_pose @ np.array([-0.15, 0, 0, 1])
        right_target = box_pose @ np.array([0.15, 0, 0, 1])
        
        # IK 求解
        from discoverse.robots.mmk2.mmk2_fik import MMK2FIK
        ik_solver = MMK2FIK()
        
        left_joints = ik_solver.solve_left_arm(left_target[:3], left_target[3:])
        right_joints = ik_solver.solve_right_arm(right_target[:3], right_target[3:])
        
        assert left_joints is not None
        assert right_joints is not None
        
        # 执行抓取
        action = construct_mmk2_action(
            left_arm=left_joints,
            right_arm=right_joints,
            left_gripper='close',
            right_gripper='close'
        )
        
        for _ in range(50):
            obs, _, done, info = env.step(action)
        
        # 验证：两个臂都成功抓取
        assert info['left_grasp_success']
        assert info['right_grasp_success']
        
        # 验证：力平衡（两侧力矩相等）
        left_force = obs['left_gripper_force']
        right_force = obs['right_gripper_force']
        assert abs(left_force - right_force) / (left_force + right_force) < 0.2
    
    def test_arm_collision_avoidance(self):
        """测试双臂碰撞避免"""
        env = make_env('mmk2', 'dual_arm_workspace')
        env.reset()
        
        # 让两个臂向中间移动（可能碰撞）
        left_target = np.array([0.3, 0.0, 0.5])
        right_target = np.array([0.3, 0.0, 0.5])
        
        ik_solver = MMK2FIK(collision_check=True)
        
        left_joints = ik_solver.solve_left_arm(left_target, check_collision=True)
        right_joints = ik_solver.solve_right_arm(right_target, check_collision=True)
        
        if left_joints is not None and right_joints is not None:
            # IK 求解成功，执行并检查碰撞
            action = construct_mmk2_action(
                left_arm=left_joints,
                right_arm=right_joints
            )
            
            collision_detected = False
            for _ in range(100):
                obs, _, _, info = env.step(action)
                if info.get('self_collision', False):
                    collision_detected = True
                    break
            
            assert not collision_detected, "检测到自碰撞"
```

### 4.4 移动操作任务测试

```python
# tests/mobile_manipulation/test_mobile_manipulation_tasks.py
import pytest

class TestMobileManipulationTasks:
    """移动操作任务测试"""
    
    @pytest.mark.parametrize("task", [
        "box_pick", "drawer_open", "cabinet_door_open",
        "kiwi_pick", "kiwi_place", "pan_pick"
    ])
    def test_mmk2_task_execution(self, task):
        """测试 MMK2 各类任务执行"""
        env = make_env('mmk2', task)
        obs = env.reset()
        
        max_steps = 500
        success = False
        
        for step in range(max_steps):
            # 使用预训练策略或手工策略
            action = get_task_policy(task).predict(obs)
            obs, reward, done, info = env.step(action)
            
            if done:
                success = info.get('success', False)
                break
        
        # 记录结果
        result = {
            'task': task,
            'success': success,
            'steps': step + 1,
            'final_reward': reward
        }
        
        # 保存到基准数据库
        save_benchmark_result('mmk2_tasks', result)
        
        # 断言：至少 50% 成功率（多次运行统计）
        historical_success_rate = get_historical_success_rate('mmk2', task)
        assert historical_success_rate > 0.5, \
            f"{task} 历史成功率 {historical_success_rate:.1%} < 50%"
    
    def test_navigation_to_target(self):
        """测试导航到目标位置"""
        env = make_env('mmk2', 'navigation')
        env.reset()
        
        target_pos = np.array([2.0, 1.5, 0.0])  # 2米前，1.5米右
        
        # 执行导航
        navigator = MMK2Navigator(env)
        trajectory = navigator.plan_path(
            start=env.get_base_position(),
            goal=target_pos
        )
        
        for waypoint in trajectory:
            controller_action = navigator.track_waypoint(waypoint)
            for _ in range(10):
                env.step(controller_action)
        
        final_pos = env.get_base_position()
        distance_error = np.linalg.norm(final_pos[:2] - target_pos[:2])
        
        assert distance_error < 0.1  # 10cm 精度
    
    def test_lift_mechanism(self):
        """测试升降机构"""
        env = make_env('mmk2', 'height_adjustment')
        env.reset()
        
        # 测试升降到不同高度
        target_heights = [0.0, 0.3, 0.6, 0.87]  # 最高 0.87m
        
        for target_h in target_heights:
            # 发送升降指令
            action = np.zeros(19)
            action[2] = target_h  # lift joint
            
            for _ in range(100):
                obs, _, _, _ = env.step(action)
            
            current_h = obs['lift_position']
            assert abs(current_h - target_h) < 0.01  # 1cm 精度
```

---

## 五、CI/CD 流水线设计

### 5.1 GitHub Actions 工作流架构

```yaml
# .github/workflows/ci-main.yml
name: CI - Main Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]
  schedule:
    - cron: '0 2 * * *'  # 每天凌晨 2 点

jobs:
  # ========== Job 1: 代码质量检查 ==========
  code-quality:
    runs-on: ubuntu-22.04
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      
      - name: Install dependencies
        run: |
          pip install black isort flake8 mypy
      
      - name: Black format check
        run: black --check discoverse/ tests/
      
      - name: isort import check
        run: isort --check-only discoverse/ tests/
      
      - name: flake8 lint
        run: flake8 discoverse/ --max-line-length=100
      
      - name: Type check with mypy
        run: mypy discoverse/ --ignore-missing-imports

  # ========== Job 2: 单元测试 ==========
  unit-tests:
    runs-on: ubuntu-22.04
    strategy:
      matrix:
        python-version: ['3.8', '3.10', '3.11']
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}
      
      - name: Cache pip packages
        uses: actions/cache@v3
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ hashFiles('pyproject.toml') }}
      
      - name: Install dependencies
        run: |
          pip install -e ".[test]"
      
      - name: Run unit tests
        run: |
          pytest tests/unit/ \
            -v \
            --cov=discoverse \
            --cov-report=xml \
            --cov-report=html \
            --junit-xml=test-results-${{ matrix.python-version }}.xml
      
      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml
          flags: unittests-py${{ matrix.python-version }}
      
      - name: Upload test results
        uses: actions/upload-artifact@v3
        if: always()
        with:
          name: test-results-${{ matrix.python-version }}
          path: test-results-*.xml

  # ========== Job 3: 仿真测试 (需要 GPU) ==========
  simulation-tests:
    runs-on: [self-hosted, linux, gpu]
    container:
      image: ghcr.io/${{ github.repository }}/discoverse:latest
      options: --gpus all
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Run simulation tests
        run: |
          pytest tests/simulation/ \
            -m "not slow" \
            --junit-xml=simulation-results.xml
      
      - name: Run kinematics tests
        run: |
          pytest tests/kinematics/ \
            --junit-xml=kinematics-results.xml
      
      - name: Run sensor tests
        run: |
          pytest tests/sensors/ \
            --junit-xml=sensor-results.xml

  # ========== Job 4: Docker 镜像构建 ==========
  docker-build:
    runs-on: ubuntu-22.04
    needs: [code-quality, unit-tests]
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v2
      
      - name: Login to GitHub Container Registry
        uses: docker/login-action@v2
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Build and push
        uses: docker/build-push-action@v4
        with:
          context: ./discoverse/docker
          file: ./discoverse/docker/Dockerfile
          push: ${{ github.event_name != 'pull_request' }}
          tags: |
            ghcr.io/${{ github.repository }}/discoverse:latest
            ghcr.io/${{ github.repository }}/discoverse:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  # ========== Job 5: 集成测试 ==========
  integration-tests:
    runs-on: [self-hosted, linux, gpu]
    needs: docker-build
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Run CICD test framework
        run: |
          python examples/universal_tasks/cicd_testing.py \
            --robots airbot_play panda ur5e \
            --tasks place_block cover_cup \
            --headless \
            --timeout 300 \
            --report ci_report.json
      
      - name: Parse test results
        run: |
          python scripts/parse_cicd_report.py ci_report.json
      
      - name: Upload results
        uses: actions/upload-artifact@v3
        with:
          name: integration-test-results
          path: ci_report.json

  # ========== Job 6: 性能基准测试 ==========
  benchmark:
    runs-on: [self-hosted, linux, gpu]
    if: github.event_name == 'schedule' || github.event_name == 'push'
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Run benchmarks
        run: |
          pytest tests/benchmarks/ \
            --benchmark-only \
            --benchmark-json=benchmark.json
      
      - name: Upload to performance DB
        run: |
          python scripts/upload_benchmarks.py \
            benchmark.json \
            --commit ${{ github.sha }} \
            --branch ${{ github.ref_name }}

  # ========== Job 7: 测试报告汇总 ==========
  report:
    runs-on: ubuntu-22.04
    needs: [unit-tests, simulation-tests, integration-tests]
    if: always()
    
    steps:
      - name: Download all artifacts
        uses: actions/download-artifact@v3
      
      - name: Generate HTML report
        run: |
          python scripts/generate_test_report.py \
            --output test-report.html
      
      - name: Publish to GitHub Pages
        uses: peaceiris/actions-gh-pages@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./test-report
```

### 5.2 自托管 Runner 配置

对于需要 GPU 的仿真测试，需要自托管 Runner：

```bash
# 在具有 GPU 的服务器上设置 Runner
# 安装 Docker + nvidia-docker2
sudo apt-get update
sudo apt-get install docker.io nvidia-docker2
sudo systemctl restart docker

# 安装 GitHub Actions Runner
mkdir actions-runner && cd actions-runner
curl -o actions-runner-linux-x64-2.311.0.tar.gz \
  -L https://github.com/actions/runner/releases/download/v2.311.0/actions-runner-linux-x64-2.311.0.tar.gz
tar xzf ./actions-runner-linux-x64-2.311.0.tar.gz

# 配置
./config.sh \
  --url https://github.com/YOUR_ORG/DISCOVERSE \
  --token YOUR_TOKEN \
  --labels linux,gpu,self-hosted

# 运行为服务
sudo ./svc.sh install
sudo ./svc.sh start
```

### 5.3 PR 评论机器人

```yaml
# .github/workflows/pr-comment.yml
name: PR Comment Bot

on:
  workflow_run:
    workflows: ["CI - Main Pipeline"]
    types: [completed]

jobs:
  comment:
    runs-on: ubuntu-22.04
    if: github.event.workflow_run.event == 'pull_request'
    
    steps:
      - name: Download test results
        uses: actions/download-artifact@v3
        with:
          name: integration-test-results
      
      - name: Parse and comment
        uses: actions/github-script@v6
        with:
          script: |
            const fs = require('fs');
            const report = JSON.parse(fs.readFileSync('ci_report.json'));
            
            const successRate = report.summary.success_rate;
            const emoji = successRate > 0.9 ? '✅' : successRate > 0.7 ? '⚠️' : '❌';
            
            const comment = `
            ## ${emoji} CI Test Results
            
            **Success Rate**: ${(successRate * 100).toFixed(1)}%
            **Total Tests**: ${report.summary.total_tests}
            **Passed**: ${report.summary.passed}
            **Failed**: ${report.summary.failed}
            
            ### Failed Tests
            ${report.failed_tests.map(t => `- ${t.robot} / ${t.task}: ${t.error}`).join('\n')}
            
            [View full report](${report.report_url})
            `;
            
            github.rest.issues.createComment({
              issue_number: context.payload.workflow_run.pull_requests[0].number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: comment
            });
```

---

## 六、Docker 测试环境

### 6.1 优化的测试 Dockerfile

```dockerfile
# discoverse/docker/Dockerfile.test
FROM nvidia/cuda:11.8.0-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV MUJOCO_GL=glfw

# 基础依赖
RUN apt-get update && apt-get install -y \
    python3.10 python3.10-dev python3-pip \
    git wget curl \
    libgl1-mesa-dev libgl1-mesa-glx libglew-dev \
    libosmesa6-dev patchelf \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt /tmp/
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

# MuJoCo
RUN mkdir -p /root/.mujoco \
    && wget https://github.com/google-deepmind/mujoco/releases/download/3.2.0/mujoco-3.2.0-linux-x86_64.tar.gz -O mujoco.tar.gz \
    && tar -xf mujoco.tar.gz -C /root/.mujoco \
    && rm mujoco.tar.gz

ENV LD_LIBRARY_PATH=/root/.mujoco/mujoco-3.2.0/lib:$LD_LIBRARY_PATH

# 安装 DISCOVERSE
WORKDIR /workspace
COPY . /workspace/
RUN pip3 install -e ".[test]"

# 测试入口
ENTRYPOINT ["pytest"]
CMD ["tests/", "-v"]
```

### 6.2 Docker Compose 测试编排

```yaml
# docker-compose.test.yml
version: '3.8'

services:
  # 单元测试（无需 GPU）
  unit-tests:
    build:
      context: .
      dockerfile: discoverse/docker/Dockerfile.test
    command: pytest tests/unit/ -v --cov=discoverse --cov-report=xml
    volumes:
      - ./tests:/workspace/tests
      - ./discoverse:/workspace/discoverse
      - ./coverage:/workspace/coverage
    environment:
      - MUJOCO_GL=osmesa
  
  # 仿真测试（需要 GPU）
  simulation-tests:
    build:
      context: .
      dockerfile: discoverse/docker/Dockerfile.test
    command: pytest tests/simulation/ tests/kinematics/ -v
    runtime: nvidia
    volumes:
      - ./tests:/workspace/tests
      - ./discoverse:/workspace/discoverse
      - ./models:/workspace/models
    environment:
      - MUJOCO_GL=glfw
      - NVIDIA_VISIBLE_DEVICES=all
  
  # 集成测试
  integration-tests:
    build:
      context: .
      dockerfile: discoverse/docker/Dockerfile.test
    command: |
      python examples/universal_tasks/cicd_testing.py
        --robots airbot_play panda
        --tasks place_block
        --headless
        --report /results/integration.json
    runtime: nvidia
    volumes:
      - ./examples:/workspace/examples
      - ./test-results:/results
    environment:
      - MUJOCO_GL=egl
```

### 6.3 CI 专用轻量镜像

```dockerfile
# discoverse/docker/Dockerfile.ci-slim
FROM nvidia/cuda:11.8.0-runtime-ubuntu22.04

# 仅安装必要依赖，减小镜像体积
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 python3-pip \
    libgl1 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 预安装 Python 包（利用层缓存）
RUN pip3 install --no-cache-dir \
    mujoco==3.2.0 \
    numpy==1.24.3 \
    pytest==8.1.0 \
    pytest-xdist==3.5.0

COPY . /app
WORKDIR /app
RUN pip3 install --no-cache-dir -e .

# 镜像大小对比：
# Dockerfile (完整): 8.5 GB
# Dockerfile.ci-slim: 4.2 GB ✓
```

---

## 七、数据采集与验证增强

### 7.1 数据质量检查器

```python
# discoverse/data_validation/data_validator.py
from dataclasses import dataclass
from typing import List, Dict, Optional
import numpy as np
import cv2

@dataclass
class ValidationResult:
    """验证结果"""
    passed: bool
    metric_name: str
    value: float
    threshold: float
    message: str

class DataValidator:
    """数据质量验证器基类"""
    
    def validate(self, data: Dict) -> List[ValidationResult]:
        raise NotImplementedError

class ImageQualityValidator(DataValidator):
    """图像质量验证"""
    
    def __init__(self, 
                 min_brightness: float = 30,
                 max_brightness: float = 220,
                 min_sharpness: float = 100,
                 max_saturation: float = 0.9):
        self.min_brightness = min_brightness
        self.max_brightness = max_brightness
        self.min_sharpness = min_sharpness
        self.max_saturation = max_saturation
    
    def validate(self, data: Dict) -> List[ValidationResult]:
        results = []
        image = data['image']
        
        # 1. 亮度检查
        brightness = np.mean(image)
        results.append(ValidationResult(
            passed=(self.min_brightness <= brightness <= self.max_brightness),
            metric_name='brightness',
            value=brightness,
            threshold=f'{self.min_brightness}-{self.max_brightness}',
            message=f'图像亮度 {brightness:.1f}'
        ))
        
        # 2. 清晰度检查（Laplacian 方差）
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
        results.append(ValidationResult(
            passed=(sharpness > self.min_sharpness),
            metric_name='sharpness',
            value=sharpness,
            threshold=self.min_sharpness,
            message=f'图像清晰度 {sharpness:.1f} (越高越好)'
        ))
        
        # 3. 过曝检查
        over_exposed_ratio = np.sum(image > 250) / image.size
        results.append(ValidationResult(
            passed=(over_exposed_ratio < 0.05),
            metric_name='over_exposure',
            value=over_exposed_ratio,
            threshold=0.05,
            message=f'过曝比例 {over_exposed_ratio:.2%}'
        ))
        
        # 4. 欠曝检查
        under_exposed_ratio = np.sum(image < 5) / image.size
        results.append(ValidationResult(
            passed=(under_exposed_ratio < 0.05),
            metric_name='under_exposure',
            value=under_exposed_ratio,
            threshold=0.05,
            message=f'欠曝比例 {under_exposed_ratio:.2%}'
        ))
        
        return results

class JointStateValidator(DataValidator):
    """关节状态验证"""
    
    def __init__(self, robot_config):
        self.joint_limits = robot_config['joint_limits']
        self.max_velocity = robot_config['max_joint_velocity']
        self.max_jerk = robot_config['max_jerk']
    
    def validate(self, data: Dict) -> List[ValidationResult]:
        results = []
        positions = data['joint_positions']
        velocities = data['joint_velocities']
        
        # 1. 关节限位检查
        for i, (pos, limits) in enumerate(zip(positions, self.joint_limits)):
            in_limit = limits[0] <= pos <= limits[1]
            results.append(ValidationResult(
                passed=in_limit,
                metric_name=f'joint_{i}_limit',
                value=pos,
                threshold=f'{limits[0]:.2f} ~ {limits[1]:.2f}',
                message=f'关节 {i} 位置 {pos:.3f} rad'
            ))
        
        # 2. 速度检查
        for i, (vel, max_vel) in enumerate(zip(velocities, self.max_velocity)):
            safe = abs(vel) <= max_vel
            results.append(ValidationResult(
                passed=safe,
                metric_name=f'joint_{i}_velocity',
                value=abs(vel),
                threshold=max_vel,
                message=f'关节 {i} 速度 {vel:.3f} rad/s'
            ))
        
        # 3. 平滑度检查（Jerk）
        if 'joint_accelerations' in data:
            accelerations = data['joint_accelerations']
            if len(data['history']) > 1:
                prev_acc = data['history'][-1]['joint_accelerations']
                jerk = np.abs(accelerations - prev_acc) / data['dt']
                
                for i, j in enumerate(jerk):
                    smooth = j <= self.max_jerk[i]
                    results.append(ValidationResult(
                        passed=smooth,
                        metric_name=f'joint_{i}_jerk',
                        value=j,
                        threshold=self.max_jerk[i],
                        message=f'关节 {i} Jerk {j:.2f} rad/s³'
                    ))
        
        return results

class TrajectoryValidator(DataValidator):
    """轨迹验证"""
    
    def validate(self, data: Dict) -> List[ValidationResult]:
        results = []
        trajectory = np.array(data['trajectory'])  # (T, dim)
        
        # 1. 轨迹长度检查
        length = len(trajectory)
        results.append(ValidationResult(
            passed=(length >= 10),
            metric_name='trajectory_length',
            value=length,
            threshold=10,
            message=f'轨迹长度 {length} 步'
        ))
        
        # 2. 平滑度检查（相邻帧差异）
        if length > 1:
            diffs = np.diff(trajectory, axis=0)
            max_diff = np.max(np.abs(diffs))
            results.append(ValidationResult(
                passed=(max_diff < 0.1),
                metric_name='trajectory_smoothness',
                value=max_diff,
                threshold=0.1,
                message=f'最大帧间差 {max_diff:.4f}'
            ))
        
        # 3. 重复检查（相邻帧相同）
        if length > 1:
            repeated_frames = np.sum(np.all(diffs == 0, axis=1))
            repeat_ratio = repeated_frames / (length - 1)
            results.append(ValidationResult(
                passed=(repeat_ratio < 0.3),
                metric_name='trajectory_repetition',
                value=repeat_ratio,
                threshold=0.3,
                message=f'重复帧比例 {repeat_ratio:.2%}'
            ))
        
        return results

class MultiModalSyncValidator(DataValidator):
    """多模态同步验证"""
    
    def validate(self, data: Dict) -> List[ValidationResult]:
        results = []
        
        # 检查时间戳一致性
        timestamps = {
            'rgb': data.get('rgb_timestamp'),
            'depth': data.get('depth_timestamp'),
            'joint_state': data.get('joint_state_timestamp'),
        }
        
        ts_values = [v for v in timestamps.values() if v is not None]
        if len(ts_values) > 1:
            max_drift = max(ts_values) - min(ts_values)
            results.append(ValidationResult(
                passed=(max_drift < 0.05),  # 50ms
                metric_name='timestamp_sync',
                value=max_drift,
                threshold=0.05,
                message=f'最大时间戳漂移 {max_drift*1000:.1f} ms'
            ))
        
        # RGB-D 对齐检查
        if 'rgb' in data and 'depth' in data:
            rgb_shape = data['rgb'].shape[:2]
            depth_shape = data['depth'].shape[:2]
            aligned = (rgb_shape == depth_shape)
            results.append(ValidationResult(
                passed=aligned,
                metric_name='rgbd_alignment',
                value=1.0 if aligned else 0.0,
                threshold=1.0,
                message=f'RGB {rgb_shape} vs Depth {depth_shape}'
            ))
        
        return results
```

### 7.2 数据集版本管理（DVC）

```yaml
# .dvc/config
[core]
    remote = myremote
    autostage = true

['remote "myremote"']
    url = s3://my-bucket/discoverse-datasets
    # 或使用本地存储
    # url = /data/dvc-storage
```

```bash
# 初始化 DVC
cd DISCOVERSE
dvc init

# 跟踪数据集
dvc add datasets/airbot_play_place_block_v1.0/
git add datasets/airbot_play_place_block_v1.0.dvc .gitignore
git commit -m "Add airbot_play place_block dataset v1.0"

# 打标签
git tag -a data-v1.0 -m "Dataset version 1.0"
dvc push

# 其他开发者拉取
git pull
git checkout data-v1.0
dvc pull
```

```python
# scripts/dataset_versioning.py
import dvc.api
import yaml
from pathlib import Path

class DatasetVersionManager:
    """数据集版本管理器"""
    
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)
    
    def create_version(self, dataset_path: str, version: str, metadata: dict):
        """创建数据集版本"""
        # 1. 用 DVC 跟踪
        os.system(f'dvc add {dataset_path}')
        
        # 2. 保存元数据
        metadata_file = Path(dataset_path).with_suffix('.yaml')
        with open(metadata_file, 'w') as f:
            yaml.dump({
                'version': version,
                'created_at': datetime.now().isoformat(),
                'num_episodes': metadata['num_episodes'],
                'robot': metadata['robot'],
                'task': metadata['task'],
                'total_frames': metadata['total_frames'],
                'validation_results': metadata.get('validation_results', {}),
            }, f)
        
        # 3. Git 提交
        os.system(f'git add {dataset_path}.dvc {metadata_file}')
        os.system(f'git commit -m "Add dataset {version}"')
        os.system(f'git tag -a data-{version} -m "Dataset version {version}"')
        
        # 4. 推送
        os.system('dvc push')
        os.system('git push --tags')
    
    def load_version(self, version: str) -> Path:
        """加载指定版本的数据集"""
        os.system(f'git checkout data-{version}')
        os.system('dvc pull')
        
        # 返回数据集路径
        dvc_files = list(Path('.').glob('datasets/**/*.dvc'))
        return Path(dvc_files[0].stem)
```

### 7.3 Sim2Real 验证工具

```python
# scripts/validate_sim2real_gap.py
import numpy as np
from scipy import stats
import matplotlib.pyplot as plt

class Sim2RealValidator:
    """仿真-真实数据对比验证"""
    
    def __init__(self):
        self.metrics = {}
    
    def compare_distributions(self, sim_data: np.ndarray, real_data: np.ndarray, 
                             metric_name: str) -> dict:
        """比较两个分布的统计特性"""
        result = {
            'metric': metric_name,
            'sim_mean': np.mean(sim_data),
            'real_mean': np.mean(real_data),
            'sim_std': np.std(sim_data),
            'real_std': np.std(real_data),
        }
        
        # KS 检验（分布是否相同）
        ks_stat, ks_pvalue = stats.ks_2samp(sim_data, real_data)
        result['ks_statistic'] = ks_stat
        result['ks_pvalue'] = ks_pvalue
        result['distributions_match'] = (ks_pvalue > 0.05)
        
        # 均值差异
        mean_diff = abs(result['sim_mean'] - result['real_mean'])
        mean_diff_percent = mean_diff / (abs(result['real_mean']) + 1e-6) * 100
        result['mean_diff_percent'] = mean_diff_percent
        
        # 标准差比率
        std_ratio = result['sim_std'] / (result['real_std'] + 1e-6)
        result['std_ratio'] = std_ratio
        
        return result
    
    def validate_trajectory_similarity(self, sim_traj: np.ndarray, 
                                      real_traj: np.ndarray) -> dict:
        """验证轨迹相似度"""
        # DTW 距离
        from scipy.spatial.distance import euclidean
        from fastdtw import fastdtw
        
        distance, path = fastdtw(sim_traj, real_traj, dist=euclidean)
        
        # 归一化 DTW 距离
        normalized_dtw = distance / len(path)
        
        return {
            'dtw_distance': distance,
            'normalized_dtw': normalized_dtw,
            'trajectory_similar': (normalized_dtw < 0.1),
        }
    
    def generate_report(self, output_path: str):
        """生成可视化报告"""
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        
        # 绘制各指标对比
        # ...（省略绘图代码）
        
        plt.savefig(output_path)
        print(f'报告已保存到 {output_path}')

# 使用示例
validator = Sim2RealValidator()

# 加载数据
sim_joint_velocities = load_sim_data('sim_data.zarr')['joint_velocities']
real_joint_velocities = load_real_data('real_data.zarr')['joint_velocities']

# 比较分布
result = validator.compare_distributions(
    sim_joint_velocities.flatten(),
    real_joint_velocities.flatten(),
    'joint_velocity'
)

print(f"均值差异: {result['mean_diff_percent']:.1f}%")
print(f"分布匹配: {result['distributions_match']}")
```

---

## 八、测试工具开发

### 8.1 测试辅助工具集

```python
# tests/utils/test_helpers.py
import numpy as np
from contextlib import contextmanager
import time

@contextmanager
def timer(name: str):
    """计时上下文管理器"""
    start = time.time()
    yield
    elapsed = time.time() - start
    print(f'{name} 耗时: {elapsed:.3f}s')

def generate_reachable_poses(robot_name: str, num_samples: int = 100) -> list:
    """生成机器人可达位姿"""
    from discoverse.robots import get_robot_config
    
    config = get_robot_config(robot_name)
    workspace = config['workspace']
    
    poses = []
    for _ in range(num_samples):
        x = np.random.uniform(workspace['x_min'], workspace['x_max'])
        y = np.random.uniform(workspace['y_min'], workspace['y_max'])
        z = np.random.uniform(workspace['z_min'], workspace['z_max'])
        
        # 随机姿态（四元数）
        quat = random_quaternion()
        
        poses.append(np.concatenate([[x, y, z], quat]))
    
    return poses

def random_quaternion():
    """生成随机单位四元数"""
    u1, u2, u3 = np.random.uniform(0, 1, 3)
    return np.array([
        np.sqrt(1-u1) * np.sin(2*np.pi*u2),
        np.sqrt(1-u1) * np.cos(2*np.pi*u2),
        np.sqrt(u1) * np.sin(2*np.pi*u3),
        np.sqrt(u1) * np.cos(2*np.pi*u3)
    ])

def assert_joint_state_valid(joint_state: np.ndarray, robot_config: dict):
    """断言关节状态有效"""
    limits = robot_config['joint_limits']
    for i, (pos, (low, high)) in enumerate(zip(joint_state, limits)):
        assert low <= pos <= high, \
            f"关节 {i} 位置 {pos:.3f} 超出限位 [{low:.3f}, {high:.3f}]"

def create_test_env(robot: str, task: str, **kwargs):
    """创建测试环境（带默认参数）"""
    from discoverse.envs import make_env
    
    default_kwargs = {
        'render_mode': 'offscreen',
        'width': 640,
        'height': 480,
        'seed': 42,
    }
    default_kwargs.update(kwargs)
    
    return make_env(robot, task, **default_kwargs)

class MockPolicy:
    """Mock 策略用于测试"""
    def __init__(self, action_dim: int):
        self.action_dim = action_dim
    
    def predict(self, obs):
        return np.random.uniform(-1, 1, self.action_dim)
```

### 8.2 测试数据生成器

```python
# tests/fixtures/data_generator.py
import numpy as np
from pathlib import Path

class TestDataGenerator:
    """测试数据生成器"""
    
    @staticmethod
    def generate_trajectory(length: int, dim: int, smooth: bool = True):
        """生成测试轨迹"""
        if smooth:
            # 平滑轨迹（正弦曲线）
            t = np.linspace(0, 4*np.pi, length)
            trajectory = np.zeros((length, dim))
            for i in range(dim):
                frequency = np.random.uniform(0.5, 2.0)
                amplitude = np.random.uniform(0.1, 1.0)
                trajectory[:, i] = amplitude * np.sin(frequency * t + i)
        else:
            # 随机轨迹
            trajectory = np.random.randn(length, dim)
        
        return trajectory
    
    @staticmethod
    def generate_test_images(num_images: int, shape=(480, 640, 3)):
        """生成测试图像"""
        images = []
        for i in range(num_images):
            # 生成带纹理的图像
            image = np.random.randint(0, 255, shape, dtype=np.uint8)
            # 添加一些结构（避免纯噪声）
            image[100:200, 200:300] = [255, 0, 0]  # 红色方块
            images.append(image)
        return np.array(images)
```

### 8.3 性能分析工具

```python
# tests/utils/profiling.py
import cProfile
import pstats
import io
from functools import wraps

def profile_function(output_file=None):
    """函数性能分析装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            profiler = cProfile.Profile()
            profiler.enable()
            
            result = func(*args, **kwargs)
            
            profiler.disable()
            
            # 输出结果
            s = io.StringIO()
            ps = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
            ps.print_stats(20)  # 前 20 项
            
            print(s.getvalue())
            
            if output_file:
                ps.dump_stats(output_file)
            
            return result
        return wrapper
    return decorator

# 使用示例
@profile_function('ik_solver.prof')
def test_ik_performance():
    solver = get_ik_solver('airbot_play')
    for _ in range(1000):
        target = np.random.rand(7)
        solver.solve(target)
```

---

## 九、实施路线图

### 9.1 阶段划分

#### 🚀 阶段 1：基础设施（2 周）

**目标**：建立 CI/CD 基础和测试框架

| 任务 | 工作量 | 负责人 | 产出 |
|------|-------|--------|------|
| 创建 GitHub Actions 工作流 | 3 天 | DevOps | `.github/workflows/ci-main.yml` |
| 扩展测试目录结构 | 2 天 | 测试开发 | `tests/` 完整目录 |
| 优化 Docker 测试镜像 | 3 天 | DevOps | `Dockerfile.test` + `docker-compose.test.yml` |
| 实现数据验证模块 | 4 天 | 测试开发 | `data_validation/` 包 |
| 配置代码覆盖率 | 2 天 | 测试开发 | Codecov 集成 |

**验收标准**：
- ✅ PR 自动触发 CI 测试
- ✅ 测试结果自动评论到 PR
- ✅ Docker 镜像可在 CI 中运行
- ✅ 代码覆盖率报告可见

#### 🔧 阶段 2：核心测试用例（3 周）

**目标**：覆盖核心模块的单元和集成测试

| 任务 | 工作量 | 负责人 | 产出 |
|------|-------|--------|------|
| 仿真测试套件 | 5 天 | 仿真工程师 | `tests/simulation/` 10+ 测试 |
| IK/运动学测试 | 4 天 | 控制工程师 | `tests/kinematics/` 8+ 测试 |
| 传感器测试 | 3 天 | 感知工程师 | `tests/sensors/` 6+ 测试 |
| 策略测试框架 | 4 天 | AI 工程师 | `tests/policies/` 框架 |
| 双臂移动测试 | 5 天 | 机器人工程师 | `tests/mobile_manipulation/` |

**验收标准**：
- ✅ 核心模块测试覆盖率 > 60%
- ✅ 所有 9 种机械臂 IK 测试通过
- ✅ MMK2 专项测试套件完成

#### 📊 阶段 3：数据质量和增强（2 周）

**目标**：提升数据采集和验证能力

| 任务 | 工作量 | 负责人 | 产出 |
|------|-------|--------|------|
| DVC 数据版本管理 | 3 天 | 数据工程师 | DVC 配置 + 流程文档 |
| Sim2Real 验证工具 | 4 天 | 测试开发 | `validate_sim2real_gap.py` |
| 性能基准测试 | 4 天 | 性能工程师 | `tests/benchmarks/` |
| CI 报告增强 | 3 天 | 前端开发 | HTML 可视化报告 |

**验收标准**：
- ✅ 数据集可通过 DVC 版本管理
- ✅ Sim2Real 对比报告可生成
- ✅ 性能基准数据可追踪

#### 🎯 阶段 4：端到端和监控（2 周）

**目标**：完整流水线测试和生产监控

| 任务 | 工作量 | 负责人 | 产出 |
|------|-------|--------|------|
| 端到端测试 | 5 天 | 测试开发 | `tests/e2e/` 3 个完整流程 |
| Grafana 监控面板 | 3 天 | DevOps | Dashboard + 告警 |
| 测试文档编写 | 4 天 | 技术文档 | 完整测试文档 |
| 团队培训 | 2 天 | 测试负责人 | 培训材料 + 答疑 |

**验收标准**：
- ✅ 数据采集→训练→部署流程可自动化测试
- ✅ 性能指标实时可视化
- ✅ 团队成员掌握测试编写

### 9.2 里程碑

```
Week 1-2   [████████░░] 阶段 1: 基础设施
Week 3-5   [░░████████] 阶段 2: 核心测试
Week 6-7   [░░░░██████] 阶段 3: 数据质量
Week 8-9   [░░░░░░████] 阶段 4: E2E & 监控
```

### 9.3 人力需求

| 角色 | 人数 | 时间投入 | 关键技能 |
|------|------|---------|---------|
| **测试开发** | 2 | 全职 9 周 | pytest, CI/CD, Python |
| **DevOps** | 1 | 50% 9 周 | Docker, GitHub Actions, Linux |
| **仿真工程师** | 1 | 30% 5 周 | MuJoCo, 物理仿真 |
| **控制工程师** | 1 | 30% 4 周 | 运动学, IK 算法 |
| **数据工程师** | 1 | 50% 3 周 | DVC, 数据管道 |
| **技术文档** | 1 | 30% 4 周 | Markdown, 技术写作 |

---

## 十、关键代码示例

### 10.1 完整的测试用例示例

```python
# tests/integration/test_mmk2_box_pick_task.py
import pytest
import numpy as np
from discoverse.envs import make_env
from discoverse.robots.mmk2.mmk2_fik import MMK2FIK

class TestMMK2BoxPickTask:
    """MMK2 双臂抓取盒子集成测试"""
    
    @pytest.fixture
    def env(self):
        """创建测试环境"""
        env = make_env('mmk2', 'box_pick', 
                      render_mode='offscreen',
                      seed=42)
        yield env
        env.close()
    
    @pytest.fixture
    def ik_solver(self):
        """IK 求解器"""
        return MMK2FIK()
    
    def test_task_initialization(self, env):
        """测试任务初始化"""
        obs = env.reset()
        
        # 验证观测空间
        assert 'rgb' in obs
        assert 'depth' in obs
        assert 'joint_positions' in obs
        assert len(obs['joint_positions']) == 19
        
        # 验证目标物体存在
        box_pos = env.get_object_position('target_box')
        assert box_pos is not None
        assert 0.3 <= box_pos[0] <= 0.6  # 在可达范围内
    
    def test_dual_arm_ik(self, env, ik_solver):
        """测试双臂 IK 求解"""
        obs = env.reset()
        box_pose = env.get_object_pose('target_box')
        
        # 计算抓取点
        left_grasp = box_pose[:3] + np.array([-0.1, 0, 0])
        right_grasp = box_pose[:3] + np.array([0.1, 0, 0])
        
        # IK 求解
        left_joints = ik_solver.solve_left_arm(left_grasp)
        right_joints = ik_solver.solve_right_arm(right_grasp)
        
        assert left_joints is not None, "左臂 IK 求解失败"
        assert right_joints is not None, "右臂 IK 求解失败"
        
        # 验证关节在限位内
        assert np.all(left_joints >= ik_solver.left_arm_limits[:, 0])
        assert np.all(left_joints <= ik_solver.left_arm_limits[:, 1])
    
    def test_full_task_execution(self, env, ik_solver):
        """测试完整任务执行"""
        obs = env.reset()
        
        # 状态机
        states = ['approach', 'grasp', 'lift', 'place']
        current_state = 0
        
        for step in range(500):
            if current_state >= len(states):
                break
            
            state_name = states[current_state]
            action = self._get_action_for_state(
                state_name, obs, env, ik_solver
            )
            
            obs, reward, done, info = env.step(action)
            
            # 状态转换
            if self._state_completed(state_name, obs, info):
                current_state += 1
            
            if done:
                break
        
        # 验证成功
        assert info.get('success', False), "任务执行失败"
        assert current_state == len(states), "未完成所有状态"
    
    def _get_action_for_state(self, state, obs, env, ik_solver):
        """根据状态生成动作"""
        # 简化实现
        return np.zeros(19)
    
    def _state_completed(self, state, obs, info):
        """检查状态是否完成"""
        if state == 'approach':
            return obs['ee_to_box_distance'] < 0.05
        elif state == 'grasp':
            return info.get('grasped', False)
        # ...
        return False
    
    @pytest.mark.benchmark
    def test_task_execution_time(self, env, benchmark):
        """性能基准测试"""
        def run_episode():
            obs = env.reset()
            for _ in range(100):
                action = env.action_space.sample()
                obs, _, done, _ = env.step(action)
                if done:
                    break
        
        result = benchmark(run_episode)
        assert result.stats.mean < 5.0, "任务执行时间过长"
```

### 10.2 CI/CD 测试报告解析器

```python
# scripts/parse_cicd_report.py
import json
import sys
from pathlib import Path

def parse_cicd_report(report_path: str):
    """解析 CICD 测试报告"""
    with open(report_path) as f:
        report = json.load(f)
    
    total = len(report['results'])
    passed = sum(1 for r in report['results'] if r['success'])
    failed = total - passed
    success_rate = passed / total if total > 0 else 0
    
    print(f"\n{'='*60}")
    print(f"CICD 测试报告")
    print(f"{'='*60}")
    print(f"总测试数: {total}")
    print(f"通过: {passed} ✅")
    print(f"失败: {failed} ❌")
    print(f"成功率: {success_rate:.1%}")
    print(f"{'='*60}\n")
    
    if failed > 0:
        print("失败的测试:")
        for result in report['results']:
            if not result['success']:
                print(f"  ❌ {result['robot']} / {result['task']}")
                print(f"     错误: {result['error_message']}")
                print(f"     完成状态: {result['states_completed']}/{result['total_states']}")
    
    # 返回退出码
    return 0 if success_rate >= 0.9 else 1

if __name__ == '__main__':
    exit_code = parse_cicd_report(sys.argv[1])
    sys.exit(exit_code)
```

---

## 十一、关键指标和成功标准

### 11.1 测试覆盖率目标

| 模块 | 当前覆盖率 | 目标覆盖率 | 优先级 |
|------|-----------|-----------|--------|
| `discoverse/envs/` | 0% | 80% | P0 |
| `discoverse/robots/` | 0% | 70% | P0 |
| `discoverse/universal_manipulation/` | 0% | 85% | P0 |
| `discoverse/task_base/` | 0% | 75% | P1 |
| `discoverse/utils/` | 0% | 60% | P2 |
| **整体** | **~5%** | **≥75%** | - |

### 11.2 性能基准

| 指标 | 基准值 | 目标 |
|------|-------|------|
| **IK 求解速度** | 5-10 ms | <5 ms (p95) |
| **仿真 FPS** | 30-60 | ≥50 (稳定) |
| **策略推理延迟** | 20-50 ms | <30 ms (p99) |
| **单元测试执行时间** | N/A | <5 分钟 |
| **集成测试执行时间** | ~20 分钟 | <15 分钟 |

### 11.3 数据质量指标

| 指标 | 阈值 | 检查方法 |
|------|------|---------|
| **图像清晰度** | Laplacian 方差 > 100 | `ImageQualityValidator` |
| **关节轨迹平滑度** | Jerk < 10 rad/s³ | `JointStateValidator` |
| **时间戳同步误差** | < 50 ms | `MultiModalSyncValidator` |
| **数据集完整性** | 丢帧率 < 1% | 自动检查脚本 |

---

## 十二、总结与建议

### 12.1 当前项目优势

✅ **完善的仿真基础**：基于 MuJoCo + 3DGS 的高保真仿真  
✅ **通用化框架**：支持多种机器人和任务的统一接口  
✅ **端到端测试起点**：已有 `cicd_testing.py` 框架  
✅ **策略学习集成**：5 种主流算法开箱即用  
✅ **文档完善**：23 个 MD 文档涵盖各方面

### 12.2 关键不足

❌ **无自动化 CI/CD**：缺少 GitHub Actions 配置  
❌ **测试覆盖不足**：核心模块无单元测试  
❌ **数据质量薄弱**：缺少版本管理和质量检查  
❌ **性能未量化**：无基准测试和回归追踪

### 12.3 测试开发转型建议

对于从传统测试转型具身智能测试开发的你，建议的学习路径：

#### 📚 第 1 周：理论基础
- 阅读 `/source-notes/1.DISCOVERSE源码深度分析.md`
- 运行示例：`examples/tasks_airbot_play/place_block.py`
- 理解 MuJoCo 物理仿真基础

#### 🔧 第 2-3 周：测试框架实践
- 阅读 `examples/universal_tasks/cicd_testing.py`
- 编写第一个单元测试（从简单的工具函数开始）
- 配置 pytest 和测试环境

#### 🤖 第 4-5 周：具身智能专项
- 学习 MMK2 双臂轮式机器人控制
- 理解 IK 求解器测试方法
- 掌握传感器数据验证

#### 🚀 第 6+ 周：CI/CD 和自动化
- 搭建 GitHub Actions 工作流
- 实现数据版本管理（DVC）
- 开发性能监控系统

### 12.4 快速上手命令

```bash
# 1. 环境检查
python scripts/check_installation.py

# 2. 运行现有测试
pytest policies/openpi/ -v

# 3. 运行 CICD 测试框架（手动）
python examples/universal_tasks/cicd_testing.py \
  --robots airbot_play \
  --tasks place_block \
  --headless

# 4. Docker 测试
docker build -f discoverse/docker/Dockerfile.test -t discoverse:test .
docker run --gpus all discoverse:test tests/unit/ -v

# 5. 代码覆盖率检查
pytest tests/ --cov=discoverse --cov-report=html
# 查看 htmlcov/index.html
```

### 12.5 关键文件速查

| 用途 | 文件路径 |
|------|---------|
| **CI/CD 测试框架** | `/home/ubuntu22/workspaces/airbot-play/DISCOVERSE/examples/universal_tasks/cicd_testing.py` |
| **数据记录器** | `/home/ubuntu22/workspaces/airbot-play/DISCOVERSE/discoverse/universal_manipulation/recorder.py` |
| **MMK2 控制** | `/home/ubuntu22/workspaces/airbot-play/DISCOVERSE/discoverse/robots_env/mmk2_base.py` |
| **IK 求解器** | `/home/ubuntu22/workspaces/airbot-play/DISCOVERSE/discoverse/universal_manipulation/mink_solver.py` |
| **Docker 镜像** | `/home/ubuntu22/workspaces/airbot-play/DISCOVERSE/discoverse/docker/Dockerfile` |
| **机器人配置** | `/home/ubuntu22/workspaces/airbot-play/DISCOVERSE/discoverse/configs/robots/*.yaml` |

---

## 附录

### A. pytest Markers 完整列表

```python
# pyproject.toml [tool.pytest.ini_options] markers
unit               # 单元测试（快速，< 1s）
integration        # 集成测试（中速，< 30s）
simulation         # 仿真测试（需要 MuJoCo）
kinematics         # 运动学测试
sensors            # 传感器测试
policies           # 策略测试
mobile             # 移动操作测试
e2e                # 端到端测试（慢速，> 60s）
benchmark          # 性能基准测试
slow               # 长时间运行测试
gpu                # 需要 GPU
hardware           # 需要真实硬件
mmk2               # MMK2 专用测试
airbot_play        # AirBot Play 专用测试
```

### B. 常用测试命令

```bash
# 运行所有单元测试
pytest tests/unit/ -v

# 运行特定标记的测试
pytest -m "simulation and not slow" -v

# 并行测试
pytest tests/ -n auto

# 代码覆盖率
pytest tests/ --cov=discoverse --cov-report=html

# 性能基准测试
pytest tests/benchmarks/ --benchmark-only

# 详细输出
pytest tests/ -vv --tb=long

# 只运行失败的测试
pytest --lf

# 交互式调试
pytest --pdb
```

### C. 资源链接

- **DISCOVERSE 官方仓库**: [GitHub](https://github.com/...)
- **MuJoCo 文档**: https://mujoco.readthedocs.io/
- **pytest 文档**: https://docs.pytest.org/
- **DVC 文档**: https://dvc.org/doc
- **GitHub Actions**: https://docs.github.com/en/actions

---

**文档版本**: v1.0  
**最后更新**: 2026-07-26  
**维护者**: DISCOVERSE 测试团队



