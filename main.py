"""AstrBot Memora Connect - 记忆增强插件

赋予AI记忆与印象/好感的能力！模仿生物海马体，通过概念节点与关系连接构建记忆网络，
具备记忆形成、提取、遗忘、巩固功能，采用双峰时间分布回顾聊天，打造有记忆能力的智能对话体验。
"""
from astrbot.api.star import register

from .plugin import MemoraConnectPlugin

# 插件注册
__all__ = ['MemoraConnectPlugin']

# 导出已注册的插件类
@register(
    "astrbot_plugin_memora_connect",
    "qa296",
    "赋予AI记忆与印象/好感的能力！  模仿生物海马体，通过概念节点与关系连接构建记忆网络，具备记忆形成、提取、遗忘、巩固功能，采用双峰时间分布回顾聊天，打造有记忆能力的智能对话体验。",
    "0.2.6",
    "https://github.com/qa296/astrbot_plugin_memora_connect"
)
class MemoraConnect(MemoraConnectPlugin):
    """插件导出类"""
    pass
