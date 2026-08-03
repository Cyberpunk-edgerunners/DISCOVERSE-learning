"""
通用任务基类

提供便利的任务执行接口，整合所有组件。
"""

import os
import mujoco
import numpy as np
from typing import Optional

from .robot_config import RobotConfigLoader
from .task_config import TaskConfigLoader
from .robot_interface import RobotInterface
from .randomization import SceneRandomizer
from .config_utils import load_and_resolve_config, replace_variables

class UniversalTaskBase:
    """通用任务基类"""
    
    def __init__(self, 
                 robot_config_path: str,
                 task_config_path: str,
                 mj_model: mujoco.MjModel,
                 mj_data: mujoco.MjData,
                 robot_interface: Optional[RobotInterface] = None):
        """
        初始化通用任务
        
        Args:
            robot_config_path: 机械臂配置文件路径
            task_config_path: 任务配置文件路径
            mj_model: MuJoCo模型
            mj_data: MuJoCo数据
            robot_interface: 机械臂接口（可选，会自动创建）
        """
        # 加载配置 - 使用模板化配置解析
        self.robot_config = RobotConfigLoader(robot_config_path)
        
        resolved_config = load_and_resolve_config(task_config_path)
        config = replace_variables(resolved_config)
        self.task_config = TaskConfigLoader.from_dict(config)
        
        # 创建机械臂接口
        if robot_interface is None:
            robot_interface = self._create_robot_interface(mj_model, mj_data)
        self.robot_interface = robot_interface
        
        # 存储模型引用
        self.mj_model = mj_model
        self.mj_data = mj_data
    
        # 从配置里取随机种子。三层都可能缺失或为 None：
        #   randomization 段可能不存在；settings 可能不存在；seed 可能是 null。
        # None 是合法值 —— default_rng(None) 表示从系统熵源取种，
        # 即保持"YAML 不写 seed 就每次随机"的原有语义。
        _rand_cfg = self.task_config.randomization or {}
        _seed = (_rand_cfg.get('settings') or {}).get('seed')
        self.randomizer = SceneRandomizer(self.mj_model, self.mj_data, seed=_seed)

        if self.task_config.randomization is not None and self.task_config.validate_randomization_config():
            self.randomization_config = self.task_config.randomization
        else:
            self.randomization_config = None

    def _create_robot_interface(self, mj_model: mujoco.MjModel, mj_data: mujoco.MjData):
        """
        根据机械臂类型创建对应的接口
        
        Args:
            mj_model: MuJoCo模型
            mj_data: MuJoCo数据
            
        Returns:
            机械臂接口实例
        """
        robot_name = self.robot_config.robot_name.lower()
        if robot_name in ["airbot_play", "panda", "arx_x5", "arx_l5", "piper", "ur5e", "rm65", "xarm7", "iiwa14"]:
            return RobotInterface(self.robot_config, mj_model, mj_data)
        else:
            raise NotImplementedError(f"Robot '{robot_name}' interface not implemented yet")
    
    # ============== 随机化相关方法 ==============
    
    def randomize_scene(self, max_attempts: int = 100) -> bool:
        if not self.randomization_config:
            return
        self.randomizer.exec_randomization(self.randomization_config, max_attempts)
    
    # ============== 任务执行相关方法 ==============
    def check_success(self) -> bool:
        """检查任务是否成功"""
        return self._check_configured_success()

    def _check_configured_success(self) -> bool:
        """根据配置文件检查成功条件"""
        success_config = self.task_config.success_check
        method = success_config.get('method', 'simple')

        if method == 'simple':
            return self._check_simple_conditions(success_config)
        elif method == 'combined':
            return self._check_combined_conditions(success_config)
        else:
            print(f"警告：未知的成功检查方法: {method}")
            return False
   
    def _check_simple_conditions(self, success_config) -> bool:
        """检查简单成功条件（单一条件检查）"""
        conditions = success_config.get('conditions', [])
        
        print(f"   📋 检查 {len(conditions)} 个简单条件...")
        for i, condition in enumerate(conditions):
            description = condition.get('description', f'条件{i+1}')
            result = self._evaluate_condition(condition)
            status = "✅ 通过" if result else "❌ 失败"
            print(f"     {i+1}. {description}: {status}")
            if not result:
                return False
        return True
    
    def _check_combined_conditions(self, success_config) -> bool:
        """检查组合成功条件（多条件逻辑组合）"""
        conditions = success_config.get('conditions', [])
        operator = success_config.get('operator', 'and')
        
        print(f"   📋 检查 {len(conditions)} 个组合条件 (操作符: {operator})...")
        results = []
        for i, condition in enumerate(conditions):
            description = condition.get('description', f'条件{i+1}')
            result = self._evaluate_condition(condition)
            results.append(result)
            status = "✅ 通过" if result else "❌ 失败"
            print(f"     {i+1}. {description}: {status}")
        
        if operator == 'and':
            final_result = all(results)
        elif operator == 'or':
            final_result = any(results)
        else:
            print(f"警告：未知的逻辑操作符: {operator}")
            return False
            
        print(f"   🔍 组合结果 ({operator}): {'✅ 通过' if final_result else '❌ 失败'}")
        return final_result
    
    def _evaluate_condition(self, condition) -> bool:
        """评估单个成功条件
        
        Args:
            condition (dict): 条件配置
            
        Returns:
            bool: 条件满足返回True，否则返回False
        """
        condition_type = condition.get('type')
        
        try:
            if condition_type == 'distance':
                return self._check_distance_condition(condition)
            elif condition_type == 'distance_2d':
                return self._check_distance_2d_condition(condition)
            elif condition_type == 'position':
                return self._check_position_condition(condition)
            elif condition_type == 'orientation':
                return self._check_orientation_condition(condition)
            elif condition_type == 'height':
                return self._check_height_condition(condition)
            else:
                print(f"警告：未知的条件类型: {condition_type}")
                return False
        except Exception as e:
            print(f"条件检查失败 ({condition.get('description', '未知条件')}): {e}")
            return False
    
    def _check_distance_condition(self, condition) -> bool:
        """检查3D距离条件"""
        obj1 = condition.get('object1')
        obj2 = condition.get('object2')
        threshold = condition.get('threshold', 0.1)
        
        pos1 = self.mj_data.body(obj1).xpos
        pos2 = self.mj_data.body(obj2).xpos
        distance = np.linalg.norm(pos1 - pos2)
        
        return distance < threshold
    
    def _check_distance_2d_condition(self, condition) -> bool:
        """检查2D距离条件（忽略Z轴）"""
        obj1 = condition.get('object1')
        obj2 = condition.get('object2')
        threshold = condition.get('threshold', 0.1)
        
        pos1 = self.mj_data.body(obj1).xpos[:2]  # 只取x,y坐标
        pos2 = self.mj_data.body(obj2).xpos[:2]
        distance = np.linalg.norm(pos1 - pos2)
        
        # 调试信息
        description = condition.get('description', '2D距离检查')
        print(f"       🔍 {description}: 实际距离={distance:.4f}m, 阈值={threshold}m")
        
        return distance < threshold
    
    def _check_position_condition(self, condition) -> bool:
        """检查位置条件"""
        obj = condition.get('object')
        axis = condition.get('axis', 'z')
        threshold = condition.get('threshold')
        operator = condition.get('operator', '>')
        
        if threshold is None:
            return False
            
        pos = self.mj_data.body(obj).xpos
        axis_map = {'x': 0, 'y': 1, 'z': 2}
        axis_idx = axis_map.get(axis, 2)
        value = pos[axis_idx]
        
        # 调试信息
        description = condition.get('description', f'{axis}轴位置检查')
        print(f"       🔍 {description}: 实际值={value:.4f}, {operator}{threshold}")
        
        if operator == '>':
            return value > threshold
        elif operator == '<':
            return value < threshold
        elif operator == '>=':
            return value >= threshold
        elif operator == '<=':
            return value <= threshold
        else:
            return False
    
    def _check_orientation_condition(self, condition) -> bool:
        """检查方向条件"""
        obj = condition.get('object')
        axis = condition.get('axis', 'z')
        direction = condition.get('direction', 'up')
        threshold = condition.get('threshold', 0.9)
        
        # 获取物体的旋转四元数
        quat = self.mj_data.body(obj).xquat
        
        # 将四元数转换为旋转矩阵
        rotation_matrix = np.zeros(9)  # 使用一维数组
        import mujoco
        mujoco.mju_quat2Mat(rotation_matrix, quat)
        rotation_matrix = rotation_matrix.reshape((3, 3))  # 重塑为3x3矩阵
        
        # 获取物体的局部轴在世界坐标系中的方向
        axis_map = {'x': 0, 'y': 1, 'z': 2}
        axis_idx = axis_map.get(axis, 2)
        object_axis = rotation_matrix[:, axis_idx]
        
        # 定义目标方向
        direction_map = {
            'up': np.array([0, 0, 1]),
            'down': np.array([0, 0, -1]),
            'forward': np.array([1, 0, 0]),
            'backward': np.array([-1, 0, 0]),
            'left': np.array([0, 1, 0]),
            'right': np.array([0, -1, 0])
        }
        target_direction = direction_map.get(direction, np.array([0, 0, 1]))
        
        # 计算点积（余弦值）
        dot_product = np.dot(object_axis, target_direction)
        return dot_product > threshold
    
    def _check_height_condition(self, condition) -> bool:
        """检查高度条件（Z轴位置的简化版本）"""
        return self._check_position_condition({
            'object': condition.get('object'),
            'axis': 'z',
            'threshold': condition.get('threshold'),
            'operator': condition.get('operator', '>')
        })

    @staticmethod
    def create_from_configs(robot_name: str, 
                           task_name: str,
                           mj_model,
                           mj_data,
                           configs_root: Optional[str] = None) -> 'UniversalTaskBase':
        """
        便利函数：从配置名称创建任务
        
        Args:
            robot_name: 机械臂名称
            task_name: 任务名称
            mj_model: MuJoCo模型
            mj_data: MuJoCo数据
            configs_root: 配置文件根目录
            
        Returns:
            任务实例
        """
        if configs_root is None:
            from discoverse import DISCOVERSE_ROOT_DIR
            configs_root = os.path.join(DISCOVERSE_ROOT_DIR, "discoverse", "configs")
        
        robot_config_path = os.path.join(configs_root, "robots", f"{robot_name}.yaml")
        task_config_path = os.path.join(configs_root, "tasks", f"{task_name}.yaml")
        
        return UniversalTaskBase(
            robot_config_path=robot_config_path,
            task_config_path=task_config_path,
            mj_model=mj_model,
            mj_data=mj_data
        )
    
    def __str__(self) -> str:
        """字符串表示"""
        return f"UniversalTaskBase({self.robot_config.robot_name}, {self.task_config.task_name})" 