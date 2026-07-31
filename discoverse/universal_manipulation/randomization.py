"""
场景随机化实现

提供统一的场景随机化接口，支持物体位置、姿态和相机视角的随机化。
"""

import numpy as np
import mujoco

import OpenGL.GL as gl
from PIL import Image

from scipy.spatial.transform import Rotation
from typing import Dict, List, Any, Optional, Tuple
from discoverse.utils import get_random_texture, get_site_tmat

class SceneRandomizer:
    """场景随机化器"""
    
    def __init__(self, mj_model: mujoco.MjModel, mj_data: mujoco.MjData):
        """
        初始化场景随机化器
        
        Args:
            mj_model: MuJoCo模型
            mj_data: MuJoCo数据
        """
        self.mj_model = mj_model
        self.mj_data = mj_data
        self.viewer = None
        self.renderer = None

        # 存储初始状态
        self.initial_camera_poses = {}
        
        # 保存初始相机姿态
        for cam_id in range(mj_model.ncam):
            cam_name = mj_model.camera(cam_id).name
            if cam_name:
                self.initial_camera_poses[cam_name] = {
                    'pos': mj_model.camera(cam_id).pos.copy(),
                    'quat': mj_model.camera(cam_id).quat.copy()
                }
        
        # 保存初始光照状态
        self.initial_light_states = {}
        if mj_model.nlight > 0:
            self.initial_light_states = {
                'pos': mj_model.light_pos.copy(),
                'dir': mj_model.light_dir.copy(),
                'ambient': mj_model.light_ambient.copy(),
                'diffuse': mj_model.light_diffuse.copy(),
                'specular': mj_model.light_specular.copy(),
                'active': mj_model.light_active.copy(),
            }

        self.free_body_qpos_ids = {}
        for i in range(self.mj_model.nbody):
            if len(self.mj_model.body(i).name) and self.mj_model.body(i).dofnum == 6:
                jq_id = np.where(self.mj_model.jnt_bodyid == self.mj_model.body(i).id)[0]
                if jq_id.size:
                    self.free_body_qpos_ids[self.mj_model.body(i).name] = int(jq_id[0])

    def set_viewer(self, viewer):
        """设置可视化器引用"""
        self.viewer = viewer
    
    def set_renderer(self, renderer):
        self.renderer = renderer

    def exec_randomization(self, randomization_config: Dict[str, Any], max_attempts: int = 100) -> bool:
        """
        根据配置随机化场景
        
        Args:
            randomization_config: 随机化配置
            max_attempts: 最大尝试次数（避免位置冲突时的无限循环）
            
        Returns:
            是否成功随机化
        """
        # 保存设置以供其他方法使用
        self._current_settings = randomization_config.get('settings', {})
        
        # 从设置中获取最大尝试次数
        if 'max_attempts' in self._current_settings:
            max_attempts = self._current_settings['max_attempts']
        
        # 随机化物体 - 检查激活状态
        if 'objects' in randomization_config:
            objects_config = randomization_config['objects']
            self._randomize_objects(objects_config, max_attempts)
        
        # 随机化相机 - 检查激活状态
        if 'cameras' in randomization_config:
            cameras_config = randomization_config['cameras']
            if cameras_config.get('activate', True):  # 默认激活
                # 移除activate字段传递给具体的随机化方法
                cameras_config_clean = {k: v for k, v in cameras_config.items() if k != 'activate'}
                self._randomize_cameras(cameras_config_clean)
        
        # 随机化光照 - 检查激活状态
        if 'lighting' in randomization_config:
            lighting_config = randomization_config['lighting']
            if lighting_config.get('activate', True):  # 默认激活
                self._randomize_lighting(lighting_config)
        
        # 随机化桌面高度 - 检查激活状态
        if 'table_height' in randomization_config:
            table_config = randomization_config['table_height']
            if table_config.get('activate', True):  # 默认激活
                self._randomize_table_height(table_config)
        
        # 随机化材质 - 新功能
        if 'textures' in randomization_config:
            textures_config = randomization_config['textures']
            if textures_config.get('activate', True):  # 默认激活
                self._randomize_textures(textures_config)
        
        # 应用更改
        mujoco.mj_forward(self.mj_model, self.mj_data)
        
        return True
    
    def _object_pose(self, body_name):
        """获取物体的位姿（位置xyz和朝向wxyz）"""
        try:
            qid = self.mj_model.jnt_qposadr[self.free_body_qpos_ids[body_name]]
            return self.mj_data.qpos[qid:qid+7][...]
        except KeyError:
            raise KeyError(f"Body name '{body_name}' not found in free_body_qpos_ids. Available bodies: {list(self.free_body_qpos_ids.keys())}")

    def _randomize_objects(self, objects_config: List[Dict[str, Any]], max_attempts: int) -> bool:
        """
        随机化物体位置和姿态
        
        Args:
            objects_config: 物体随机化配置列表
            max_attempts: 最大尝试次数
            
        Returns:
            是否成功随机化
        """
        return self._randomize_objects_with_collision(objects_config, max_attempts)
    
    def _randomize_objects_with_collision(self, objects_config: List[Dict[str, Any]], max_attempts: int) -> bool:
        """
        基于边界框和碰撞检测的物体随机化
        
        Args:
            objects_config: 物体随机化配置列表
            max_attempts: 最大尝试次数
            
        Returns:
            是否成功
        """
        print("🎯 开始边界框随机化（支持碰撞检测）...")
        
        # 构建变换矩阵
        armbase_tmat = get_site_tmat(self.mj_data, "armbase")
        
        # 多次尝试随机化所有物体
        for attempt in range(max_attempts):
            placed_objects = []  # 已放置物体的信息 [(name, x, y, radius), ...]
            success = True
            
            for obj_config in objects_config:
                object_name = obj_config.get('name')
                print(f"  📦 随机化物体: {object_name}")
                if not object_name:
                    continue
                
                # 尝试为当前物体找到合适位置
                obj_success = False
                for obj_attempt in range(10):  # 每个物体最多尝试10次
                    new_pos = self._generate_random_position_in_bounds(
                        obj_config, armbase_tmat, object_name
                    )
                    
                    if new_pos is None:
                        break
                    
                    # 检查与已放置物体的碰撞
                    radius = self._get_collision_radius(obj_config)
                    if self._check_collision_2d(new_pos[:2], radius, placed_objects):
                        continue  # 有碰撞，重新尝试
                    
                    # 设置物体位置
                    joint_adr = self.mj_model.jnt_qposadr[self.free_body_qpos_ids[object_name]]
                    self.mj_data.qpos[joint_adr:joint_adr+3] = new_pos
                    
                    # 记录已放置的物体
                    placed_objects.append((object_name, new_pos[0], new_pos[1], radius))
                    obj_success = True
                    break

                if not obj_success:
                    success = False
                    break
            
            if success:
                print(f"✅ 边界框随机化成功 (尝试次数: {attempt + 1})")
                return True
                   
        print(f"❌ 边界框随机化失败，已达到最大尝试次数: {max_attempts}")
        return False
    
    def _generate_random_position_in_bounds(self, obj_config: Dict[str, Any], 
                                          armbase_tmat: np.ndarray, 
                                          object_name: str) -> Optional[np.ndarray]:
        """
        在边界框内生成随机位置
        
        Args:
            obj_config: 物体配置
            armbase_tmat: armbase的变换矩阵
            object_name: 物体名称
            
        Returns:
            世界坐标系中的新位置，如果失败返回None
        """        
        # 检查是否使用边界框模式
        if 'x_range' not in obj_config or 'y_range' not in obj_config:
            return None
        
        # 获取边界框参数
        x_range = obj_config['x_range']
        y_range = obj_config['y_range']
        
        local_x = np.random.uniform(x_range[0], x_range[1])
        local_y = np.random.uniform(y_range[0], y_range[1])
                
        local_pos = np.array([local_x, local_y, 0.0, 1.0])
        
        # 转换到世界坐标系
        world_pos = armbase_tmat @ local_pos
        joint_adr = self.mj_model.jnt_qposadr[self.free_body_qpos_ids[object_name]]
        current_z = self.mj_data.qpos[joint_adr + 2]
        world_pos[2] = current_z

        return world_pos[:3]

    def _get_collision_radius(self, obj_config: Dict[str, Any]) -> float:
        """取物体的碰撞避让半径。

        兼容两种键名：
          collision_radius —— 任务 YAML 实际使用（12 处，全部生效）
          min_distance     —— templates/randomization.yaml 使用（6 处）

        为什么两个都认：模板从未被任何任务 extends（唯一引用是它自己
        第 137 行的注释示例），但它是给人照抄的文档。只认新键名的话，
        照模板抄的人会掉进同一个坑；只认旧键名就是现在这个缺陷本身。

        优先级给 collision_radius —— 它是实际被加载的那一个。
        """
        return obj_config.get(
            'collision_radius',
            obj_config.get('min_distance', 0.05)
        )

    def _check_collision_2d(self, pos_2d: np.ndarray, radius: float, 
                           placed_objects: List[Tuple[str, float, float, float]]) -> bool:
        """
        检查2D平面上的碰撞
        
        Args:
            pos_2d: 待检查位置的XY坐标
            radius: 待检查物体的半径
            placed_objects: 已放置物体列表 [(name, x, y, radius), ...]
            
        Returns:
            是否发生碰撞
        """
        for name, x, y, other_radius in placed_objects:
            distance = np.hypot(pos_2d[0] - x, pos_2d[1] - y)
            min_distance = radius + other_radius
            if distance < min_distance:
                return True  # 发生碰撞
        return False  # 无碰撞
    
    def _randomize_cameras(self, cameras_config: Dict[str, Any]):
        """
        随机化相机视角
        
        Args:
            cameras_config: 相机随机化配置
        """
        for camera_name, camera_config in cameras_config.items():
            self._randomize_single_camera(camera_name, camera_config)
    
    def _randomize_single_camera(self, camera_name: str, camera_config: Dict[str, Any]):
        """
        随机化单个相机
        
        Args:
            camera_name: 相机名称
            camera_config: 相机随机化配置
        """
        try:
            cam_id = mujoco.mj_name2id(self.mj_model, mujoco.mjtObj.mjOBJ_CAMERA, camera_name)
            if cam_id < 0:
                print(f"❌ 未找到相机: {camera_name}")
                return
            
            camera = self.mj_model.camera(cam_id)
            
            # 获取初始姿态
            initial_pose = self.initial_camera_poses.get(camera_name)
            if not initial_pose:
                return
            
            # 随机化位置
            if 'position_offset' in camera_config:
                offset_range = camera_config['position_offset']
                if isinstance(offset_range, (list, tuple)) and len(offset_range) == 3:
                    offset = np.array([
                        2 * (np.random.random() - 0.5) * offset_range[0],
                        2 * (np.random.random() - 0.5) * offset_range[1],
                        2 * (np.random.random() - 0.5) * offset_range[2]
                    ])
                elif isinstance(offset_range, (int, float)):
                    offset = 2 * (np.random.random(3) - 0.5) * offset_range
                else:
                    offset = np.zeros(3)
                
                camera.pos[:] = initial_pose['pos'] + offset
            
            # 随机化朝向
            if 'orientation_offset' in camera_config:
                euler_range = camera_config['orientation_offset']
                
                # 将当前四元数转换为欧拉角
                current_quat = initial_pose['quat'][[1, 2, 3, 0]]  # (x, y, z, w)
                current_rotation = Rotation.from_quat(current_quat)
                current_euler = current_rotation.as_euler('xyz', degrees=False)
                
                # 应用随机偏移
                if isinstance(euler_range, (list, tuple)) and len(euler_range) == 3:
                    euler_offset = np.array([
                        2 * (np.random.random() - 0.5) * euler_range[0],
                        2 * (np.random.random() - 0.5) * euler_range[1],
                        2 * (np.random.random() - 0.5) * euler_range[2]
                    ])
                elif isinstance(euler_range, (int, float)):
                    euler_offset = 2 * (np.random.random(3) - 0.5) * euler_range
                else:
                    euler_offset = np.zeros(3)
                
                # 计算新的欧拉角并转换回四元数
                new_euler = current_euler + euler_offset
                new_rotation = Rotation.from_euler('xyz', new_euler, degrees=False)
                new_quat = new_rotation.as_quat()  # (x, y, z, w)
                
                # 转换为MuJoCo格式 (w, x, y, z)
                camera.quat[:] = [new_quat[3], new_quat[0], new_quat[1], new_quat[2]]
            
        except Exception as e:
            print(f"❌ 随机化相机 '{camera_name}' 时出错: {e}")
    
    def _generate_random_quaternion(self) -> np.ndarray:
        """
        生成随机单位四元数
        
        Returns:
            随机四元数 (w, x, y, z)
        """
        # 使用均匀分布生成随机四元数
        u1, u2, u3 = np.random.random(3)
        
        sqrt1_u1 = np.sqrt(1 - u1)
        sqrt_u1 = np.sqrt(u1)
        
        w = sqrt1_u1 * np.sin(2 * np.pi * u2)
        x = sqrt1_u1 * np.cos(2 * np.pi * u2)
        y = sqrt_u1 * np.sin(2 * np.pi * u3)
        z = sqrt_u1 * np.cos(2 * np.pi * u3)
        
        return np.array([w, x, y, z])
    
    def _randomize_lighting(self, lighting_config: Dict[str, Any]):
        """
        随机化光照设置
        
        Args:
            lighting_config: 光照随机化配置
        """

        if self.mj_model.nlight == 0:
            return
        
        # 随机化光源颜色
        if lighting_config.get('random_color', False):
            if lighting_config.get('individual_colors', False):
                # 为每个光源单独设置颜色
                for i in range(self.mj_model.nlight):
                    self.mj_model.light_ambient[i, :] = np.random.random(3) * 0.1
                    self.mj_model.light_diffuse[i, :] = np.random.random(3)
                    self.mj_model.light_specular[i, :] = np.random.random(3) * 0.3
            else:
                # 所有光源使用相同的随机化
                self.mj_model.light_ambient[:] = np.random.random(size=self.mj_model.light_ambient.shape) * 0.1
                self.mj_model.light_diffuse[:] = np.random.random(size=self.mj_model.light_diffuse.shape)
                self.mj_model.light_specular[:] = np.random.random(size=self.mj_model.light_specular.shape) * 0.3
        
        # 随机化光源激活状态
        if lighting_config.get('random_active', False):
            active_prob = lighting_config.get('active_probability', 0.5)
            self.mj_model.light_active[:] = np.int32(np.random.rand(self.mj_model.nlight) > (1 - active_prob)).tolist()
            
            # 确保至少有一个光源是激活的
            if np.sum(self.mj_model.light_active) == 0:
                self.mj_model.light_active[np.random.randint(self.mj_model.nlight)] = 1
        
        # 随机化光源位置
        if 'position_offset' in lighting_config:
            pos_config = lighting_config['position_offset']
            
            # 应用位置偏移
            if isinstance(pos_config, dict):
                xy_scale = pos_config.get('xy_scale', 0.3)
                z_scale = pos_config.get('z_scale', 0.2)
                
                self.mj_model.light_pos[:, :2] = (
                    self.mj_model.light_pos0[:, :2] + 
                    np.random.normal(scale=xy_scale, size=self.mj_model.light_pos[:, :2].shape)
                )
                self.mj_model.light_pos[:, 2] = (
                    self.mj_model.light_pos0[:, 2] + 
                    np.random.normal(scale=z_scale, size=self.mj_model.light_pos[:, 2].shape)
                )
            else:
                print(f"unsupported position_offset format: {pos_config}")

        # 随机化光源方向
        if lighting_config.get('random_direction', False):
            # 生成随机方向向量
            self.mj_model.light_dir[:] = np.random.random(size=self.mj_model.light_dir.shape) - 0.5
            self.mj_model.light_dir[:, 2] *= 2.0  # Z方向偏向向下
            
            # 归一化方向向量
            norms = np.linalg.norm(self.mj_model.light_dir, axis=1, keepdims=True)
            self.mj_model.light_dir[:] = self.mj_model.light_dir / (norms + 1e-8)
            
            # 确保光源向下照射
            self.mj_model.light_dir[:, 2] = -np.abs(self.mj_model.light_dir[:, 2])
            
        # 随机化光强
        if 'intensity_range' in lighting_config:
            intensity_config = lighting_config['intensity_range']
            
            if isinstance(intensity_config, dict):
                min_intensity = intensity_config.get('min', 0.5)
                max_intensity = intensity_config.get('max', 1.0)
            else:
                min_intensity, max_intensity = 0.5, 1.0
            
            # 为每个颜色通道应用强度缩放
            intensity_scale = np.random.uniform(min_intensity, max_intensity, size=(self.mj_model.nlight, 1))
            
            self.mj_model.light_ambient[:] *= intensity_scale
            self.mj_model.light_diffuse[:] *= intensity_scale
            self.mj_model.light_specular[:] *= intensity_scale
            
            # 限制最大值为1.0
            self.mj_model.light_ambient[:] = np.clip(self.mj_model.light_ambient, 0, 1)
            self.mj_model.light_diffuse[:] = np.clip(self.mj_model.light_diffuse, 0, 1)
            self.mj_model.light_specular[:] = np.clip(self.mj_model.light_specular, 0, 1)
        
    def _randomize_table_height(self, table_config: Dict[str, Any]):
        """
        随机化桌面高度
        
        Args:
            table_config: 桌面高度随机化配置
        """
        table_name = table_config.get('table_name', 'table')

        if not hasattr(self, "table_pos0"):
            self.table_pos0 = self.mj_model.body(table_name).pos.copy()

        height_range = table_config.get('height_range', [0.0, 0.1])  # 默认0-10cm
        object_list = table_config.get('affected_objects', [])  # 受影响的物体列表
        
        print(f"🪑 桌面高度随机化: {table_name}")
        
        # 生成随机高度变化量
        if isinstance(height_range, list) and len(height_range) == 2:
            change_height = np.random.uniform(float(height_range[0]), float(height_range[1]))
        else:
            print(f"⚠️ 无效的高度范围配置: {height_range}, 使用默认0-10cm")
            change_height = np.random.uniform(0, 0.1)  # 默认0-10cm

        self.mj_model.body(table_name).pos[:] = self.table_pos0.copy()
        self.mj_model.body(table_name).pos[2] = self.table_pos0[2] - change_height

        for obj_name in object_list:
            try:
                self._object_pose(obj_name)[2] -= change_height
            except KeyError:
                print(f"⚠️ 未找到物体 '{obj_name}'，无法调整高度")
        
        print(f"   🎯 桌面高度随机化完成")
    
    def _randomize_textures(self, textures_config: Dict[str, Any]):
        """
        随机化材质纹理
        
        Args:
            textures_config: 材质随机化配置
        """
        print("🎨 开始材质随机化...")
        
        # 检查是否有纹理对象配置
        if 'objects' not in textures_config:
            print("⚠️ 材质配置中未找到objects字段")
            return
        
        objects_config = textures_config['objects']
        if not isinstance(objects_config, list):
            print("❌ textures.objects应该是一个列表")
            return
        
        # 遍历每个材质对象配置
        for obj_config in objects_config:
            self._randomize_single_texture(obj_config)
    
    def _randomize_single_texture(self, obj_config: Dict[str, Any]):
        """
        随机化单个材质对象
        
        Args:
            obj_config: 单个材质对象配置
        """
        texture_name = obj_config.get('name')
        if not texture_name:
            print("⚠️ 材质配置中缺少name字段")
            return
        
        try:
            self.mj_model.texture(texture_name)  # 确保纹理存在
        except KeyError:
            print(f"❌ 未找到纹理: {texture_name}")
            return
        
        mtl_type = obj_config.get('mtl_type', 'texture_1k')
        if mtl_type == "texture_1k":
            random_texture_pil = get_random_texture()
        else:
            print(f"⚠️ 不支持的材质类型: {mtl_type}")
            return

        # 更新纹理数据
        self.mj_model.texture(texture_name).data = np.array(random_texture_pil)

        if self.viewer is not None:
            self._update_texture_viewer(texture_name)
        else:
            print("⚠️ 未设置查看器，无法更新纹理显示")
        
        if self.renderer is not None:
            self._update_texture_renderer(texture_name, random_texture_pil)
        else:
            print("⚠️ 未设置渲染器，无法更新纹理显示")

        print(f"   ✅ 材质 {texture_name} 随机化成功")

    def _update_texture_viewer(self, texture_name: str):
        """
        更新查看器中的纹理显示
        
        Args:
            texture_name: 纹理名称
        """

        try:
            texture_id = self.mj_model.texture(texture_name).id  # 确保纹理存在
            if hasattr(self.viewer, 'update_texture'):
                self.viewer.update_texture(texture_id)
        except KeyError:
            print(f"❌ 未找到纹理: {texture_name}")
            return

    def _update_texture_renderer(self, texture_name: str, mtl_img_pil):
        """
        更新渲染器中的纹理显示
        
        Args:
            texture_name: 纹理名称
        """
        try:
            tex_id = self.renderer.model.tex(texture_name).id
        except Exception as e:
            print(f"Texture '{texture_name}' not found: {e}")
            return

        tex_bind_id = self.renderer._mjr_context.texture[tex_id]
        gl.glBindTexture(gl.GL_TEXTURE_2D, tex_bind_id)
        
        try:
            width = gl.glGetTexLevelParameteriv(gl.GL_TEXTURE_2D, 0, gl.GL_TEXTURE_WIDTH)
            height = gl.glGetTexLevelParameteriv(gl.GL_TEXTURE_2D, 0, gl.GL_TEXTURE_HEIGHT)
        except Exception as e:
            print(f"Error getting texture dimensions: {e}")
            gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
            return

        try:
            if mtl_img_pil.mode != 'RGB':
                mtl_img_pil = mtl_img_pil.convert('RGB')

            if mtl_img_pil.size != (width, height):
                mtl_img_pil = mtl_img_pil.resize((width, height), Image.Resampling.LANCZOS)
            
            mtl_img = np.array(mtl_img_pil)
            mtl_img = np.flipud(mtl_img)
            mtl_img = np.ascontiguousarray(mtl_img, dtype=np.uint8)

            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_REPEAT)
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_REPEAT)

            gl.glTexSubImage2D(gl.GL_TEXTURE_2D, 0, 0, 0, width, height, 
                              gl.GL_RGB, gl.GL_UNSIGNED_BYTE, mtl_img.tobytes())
            
        except Exception as e:
            print(f"Error processing image for texture '{texture_name}': {e}")
            return
        finally:
            gl.glBindTexture(gl.GL_TEXTURE_2D, 0)