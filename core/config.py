"""
配置管理模块
包含记忆系统的配置类和配置管理器
"""

try:
    from astrbot.api import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


class MemorySystemConfig:
    """记忆系统配置数据类"""

    def __init__(
        self,
        enable_memory_system: bool = True,
        exclude_keywords: list = None,
        topic_trigger_interval_minutes: int = 5,
        topic_message_threshold: int = 12,
        recent_completed_sessions_count: int = 5,
    ):
        self.enable_memory_system = enable_memory_system
        self.exclude_keywords = exclude_keywords or []
        self.topic_trigger_interval_minutes = topic_trigger_interval_minutes
        self.topic_message_threshold = topic_message_threshold
        self.recent_completed_sessions_count = recent_completed_sessions_count

    @classmethod
    def from_dict(cls, config_dict):
        """从字典创建配置对象"""
        return cls(
            enable_memory_system=config_dict.get("enable_memory_system", True),
            exclude_keywords=config_dict.get("exclude_keywords", []),
            topic_trigger_interval_minutes=config_dict.get(
                "topic_trigger_interval_minutes", 5
            ),
            topic_message_threshold=config_dict.get("topic_message_threshold", 12),
            recent_completed_sessions_count=config_dict.get(
                "recent_completed_sessions_count", 5
            ),
        )

    def to_dict(self):
        """转换为字典"""
        return {
            "enable_memory_system": self.enable_memory_system,
            "exclude_keywords": self.exclude_keywords,
            "topic_trigger_interval_minutes": self.topic_trigger_interval_minutes,
            "topic_message_threshold": self.topic_message_threshold,
            "recent_completed_sessions_count": self.recent_completed_sessions_count,
        }


class MemoryConfigManager:
    """记忆系统配置管理器"""

    def __init__(self, config=None):
        """
        初始化配置管理器

        Args:
            config: 配置字典，如果为None则使用默认配置
        """
        if config is None:
            config = {}

        # 从配置中提取记忆系统相关配置
        memory_config_dict = {}

        # 处理主开关
        if "enable_memory_system" in config:
            memory_config_dict["enable_memory_system"] = bool(
                config["enable_memory_system"]
            )

        # 处理排除关键词
        if "exclude_keywords" in config:
            memory_config_dict["exclude_keywords"] = config["exclude_keywords"]

        # 创建配置对象
        self.config = MemorySystemConfig.from_dict(memory_config_dict)

        logger.info(
            f"记忆系统配置管理器初始化完成，主开关: {'开启' if self.config.enable_memory_system else '关闭'}"
        )

    def is_memory_system_enabled(self):
        """
        检查记忆系统是否启用

        Returns:
            bool: 记忆系统是否启用
        """
        return self.config.enable_memory_system

    def set_memory_system_enabled(self, enabled):
        """
        设置记忆系统启用状态

        Args:
            enabled: 是否启用记忆系统
        """
        self.config.enable_memory_system = enabled
        logger.info(f"记忆系统主开关设置为: {'开启' if enabled else '关闭'}")

    def get_config(self):
        """
        获取当前配置对象

        Returns:
            MemorySystemConfig: 当前配置对象
        """
        return self.config

    def update_config(self, config_dict):
        """
        更新配置

        Args:
            config_dict: 新的配置字典
        """
        old_enabled = self.config.enable_memory_system

        # 更新配置
        self.config = MemorySystemConfig.from_dict(config_dict)

        # 记录配置变更
        if old_enabled != self.config.enable_memory_system:
            logger.info(
                f"记忆系统主开关变更: {'开启' if self.config.enable_memory_system else '关闭'}"
            )

    def get_config_dict(self):
        """
        获取配置字典

        Returns:
            Dict[str, Any]: 配置字典
        """
        return self.config.to_dict()

    def validate_config(self):
        """
        验证配置是否有效

        Returns:
            bool: 配置是否有效
        """
        try:
            # 检查主开关是否为布尔值
            if not isinstance(self.config.enable_memory_system, bool):
                logger.error("enable_memory_system 必须是布尔值")
                return False

            return True

        except Exception as e:
            logger.error(f"配置验证失败: {e}")
            return False
