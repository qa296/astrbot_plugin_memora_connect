"""测试配置管理模块"""
import pytest
from config import MemorySystemConfig, MemoryConfigManager


class TestMemorySystemConfig:
    """测试MemorySystemConfig类"""
    
    def test_config_creation_with_defaults(self):
        """测试使用默认值创建配置"""
        config = MemorySystemConfig()
        assert config.enable_memory_system is True
    
    def test_config_creation_with_custom_value(self):
        """测试使用自定义值创建配置"""
        config = MemorySystemConfig(enable_memory_system=False)
        assert config.enable_memory_system is False
    
    def test_config_from_dict_with_value(self):
        """测试从字典创建配置（有值）"""
        config_dict = {'enable_memory_system': False}
        config = MemorySystemConfig.from_dict(config_dict)
        assert config.enable_memory_system is False
    
    def test_config_from_dict_without_value(self):
        """测试从字典创建配置（无值，使用默认）"""
        config_dict = {}
        config = MemorySystemConfig.from_dict(config_dict)
        assert config.enable_memory_system is True
    
    def test_config_to_dict(self):
        """测试转换为字典"""
        config = MemorySystemConfig(enable_memory_system=False)
        config_dict = config.to_dict()
        assert config_dict == {'enable_memory_system': False}


class TestMemoryConfigManager:
    """测试MemoryConfigManager类"""
    
    def test_manager_creation_with_none(self):
        """测试使用None创建管理器"""
        manager = MemoryConfigManager(config=None)
        assert manager.config.enable_memory_system is True
    
    def test_manager_creation_with_empty_dict(self):
        """测试使用空字典创建管理器"""
        manager = MemoryConfigManager(config={})
        assert manager.config.enable_memory_system is True
    
    def test_manager_creation_with_config(self):
        """测试使用配置字典创建管理器"""
        manager = MemoryConfigManager(config={'enable_memory_system': False})
        assert manager.config.enable_memory_system is False
    
    def test_is_memory_system_enabled(self):
        """测试检查记忆系统是否启用"""
        manager = MemoryConfigManager(config={'enable_memory_system': True})
        assert manager.is_memory_system_enabled() is True
        
        manager = MemoryConfigManager(config={'enable_memory_system': False})
        assert manager.is_memory_system_enabled() is False
    
    def test_set_memory_system_enabled(self):
        """测试设置记忆系统启用状态"""
        manager = MemoryConfigManager(config={'enable_memory_system': True})
        assert manager.is_memory_system_enabled() is True
        
        manager.set_memory_system_enabled(False)
        assert manager.is_memory_system_enabled() is False
        
        manager.set_memory_system_enabled(True)
        assert manager.is_memory_system_enabled() is True
    
    def test_get_config(self):
        """测试获取配置对象"""
        manager = MemoryConfigManager(config={'enable_memory_system': False})
        config = manager.get_config()
        assert isinstance(config, MemorySystemConfig)
        assert config.enable_memory_system is False
    
    def test_update_config(self):
        """测试更新配置"""
        manager = MemoryConfigManager(config={'enable_memory_system': True})
        assert manager.is_memory_system_enabled() is True
        
        manager.update_config({'enable_memory_system': False})
        assert manager.is_memory_system_enabled() is False
    
    def test_get_config_dict(self):
        """测试获取配置字典"""
        manager = MemoryConfigManager(config={'enable_memory_system': False})
        config_dict = manager.get_config_dict()
        assert config_dict == {'enable_memory_system': False}
    
    def test_validate_config_valid(self):
        """测试验证有效配置"""
        manager = MemoryConfigManager(config={'enable_memory_system': True})
        assert manager.validate_config() is True
        
        manager = MemoryConfigManager(config={'enable_memory_system': False})
        assert manager.validate_config() is True
    
    def test_validate_config_invalid(self):
        """测试验证无效配置"""
        manager = MemoryConfigManager(config={'enable_memory_system': True})
        # 直接修改为无效值
        manager.config.enable_memory_system = "invalid"
        assert manager.validate_config() is False
    
    def test_validate_config_with_exception(self):
        """测试验证配置时发生异常"""
        manager = MemoryConfigManager(config={'enable_memory_system': True})
        # 删除config属性，使验证时抛出异常
        original_config = manager.config
        manager.config = None
        assert manager.validate_config() is False
        manager.config = original_config
