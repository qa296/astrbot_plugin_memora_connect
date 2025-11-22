"""
测试配置管理模块
"""
import unittest
from config import MemorySystemConfig, MemoryConfigManager


class TestMemorySystemConfig(unittest.TestCase):
    """测试 MemorySystemConfig 类"""
    
    def test_config_creation_default(self):
        """测试默认配置创建"""
        config = MemorySystemConfig()
        self.assertTrue(config.enable_memory_system)
    
    def test_config_creation_with_value(self):
        """测试带值的配置创建"""
        config = MemorySystemConfig(enable_memory_system=False)
        self.assertFalse(config.enable_memory_system)
    
    def test_config_from_dict(self):
        """测试从字典创建配置"""
        config_dict = {'enable_memory_system': False}
        config = MemorySystemConfig.from_dict(config_dict)
        self.assertFalse(config.enable_memory_system)
    
    def test_config_from_dict_default(self):
        """测试从空字典创建配置（使用默认值）"""
        config = MemorySystemConfig.from_dict({})
        self.assertTrue(config.enable_memory_system)
    
    def test_config_to_dict(self):
        """测试配置转换为字典"""
        config = MemorySystemConfig(enable_memory_system=False)
        config_dict = config.to_dict()
        self.assertEqual(config_dict, {'enable_memory_system': False})


class TestMemoryConfigManager(unittest.TestCase):
    """测试 MemoryConfigManager 类"""
    
    def test_manager_creation_default(self):
        """测试默认配置管理器创建"""
        manager = MemoryConfigManager()
        self.assertTrue(manager.is_memory_system_enabled())
    
    def test_manager_creation_with_config(self):
        """测试带配置的管理器创建"""
        config = {'enable_memory_system': False}
        manager = MemoryConfigManager(config)
        self.assertFalse(manager.is_memory_system_enabled())
    
    def test_manager_is_enabled(self):
        """测试检查记忆系统是否启用"""
        manager = MemoryConfigManager({'enable_memory_system': True})
        self.assertTrue(manager.is_memory_system_enabled())
        
        manager = MemoryConfigManager({'enable_memory_system': False})
        self.assertFalse(manager.is_memory_system_enabled())
    
    def test_manager_set_enabled(self):
        """测试设置记忆系统启用状态"""
        manager = MemoryConfigManager()
        self.assertTrue(manager.is_memory_system_enabled())
        
        manager.set_memory_system_enabled(False)
        self.assertFalse(manager.is_memory_system_enabled())
        
        manager.set_memory_system_enabled(True)
        self.assertTrue(manager.is_memory_system_enabled())
    
    def test_manager_get_config(self):
        """测试获取配置对象"""
        manager = MemoryConfigManager({'enable_memory_system': False})
        config = manager.get_config()
        self.assertIsInstance(config, MemorySystemConfig)
        self.assertFalse(config.enable_memory_system)
    
    def test_manager_update_config(self):
        """测试更新配置"""
        manager = MemoryConfigManager()
        self.assertTrue(manager.is_memory_system_enabled())
        
        manager.update_config({'enable_memory_system': False})
        self.assertFalse(manager.is_memory_system_enabled())
        
        manager.update_config({'enable_memory_system': True})
        self.assertTrue(manager.is_memory_system_enabled())
    
    def test_manager_get_config_dict(self):
        """测试获取配置字典"""
        manager = MemoryConfigManager({'enable_memory_system': False})
        config_dict = manager.get_config_dict()
        self.assertEqual(config_dict, {'enable_memory_system': False})
    
    def test_manager_validate_config_valid(self):
        """测试验证有效配置"""
        manager = MemoryConfigManager({'enable_memory_system': True})
        self.assertTrue(manager.validate_config())
    
    def test_manager_validate_config_invalid(self):
        """测试验证无效配置"""
        manager = MemoryConfigManager()
        # 手动设置无效类型
        manager.config.enable_memory_system = "invalid"
        self.assertFalse(manager.validate_config())
    
    def test_manager_none_config(self):
        """测试传入 None 配置"""
        manager = MemoryConfigManager(None)
        self.assertTrue(manager.is_memory_system_enabled())
    
    def test_manager_empty_config(self):
        """测试传入空配置"""
        manager = MemoryConfigManager({})
        self.assertTrue(manager.is_memory_system_enabled())
    
    def test_manager_validate_config_exception(self):
        """测试配置验证时的异常处理"""
        manager = MemoryConfigManager()
        # 手动设置配置为会引发异常的值
        manager.config.enable_memory_system = None
        # 虽然None不是bool，但不应该引发异常，而是返回False
        result = manager.validate_config()
        self.assertFalse(result)
    
    def test_manager_validate_config_with_real_exception(self):
        """测试配置验证时触发真实异常"""
        manager = MemoryConfigManager()
        # 删除config属性以触发异常
        original_config = manager.config
        manager.config = None
        result = manager.validate_config()
        self.assertFalse(result)
        # 恢复
        manager.config = original_config


if __name__ == '__main__':
    unittest.main()
