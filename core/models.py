"""
数据模型定义
包含记忆系统的核心数据结构：Concept, Memory, Connection
"""

import time
from dataclasses import dataclass


@dataclass
class Concept:
    """概念节点"""

    id: str
    name: str
    created_at: float = None
    last_accessed: float = None
    access_count: int = 0

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()
        if self.last_accessed is None:
            self.last_accessed = time.time()


@dataclass
class Memory:
    """记忆条目"""

    id: str
    concept_id: str
    content: str
    details: str = ""  # 详细描述
    participants: str = ""  # 参与者
    location: str = ""  # 地点
    emotion: str = ""  # 情感
    tags: str = ""  # 标签
    created_at: float = None
    last_accessed: float = None
    access_count: int = 0
    strength: float = 1.0
    allow_forget: bool = True
    group_id: str = ""  # 群组ID，用于群聊隔离

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()
        if self.last_accessed is None:
            self.last_accessed = time.time()
        if self.allow_forget is None:
            self.allow_forget = True


@dataclass
class Connection:
    """概念之间的连接"""

    id: str
    from_concept: str
    to_concept: str
    strength: float = 1.0
    last_strengthened: float = None

    def __post_init__(self):
        if self.last_strengthened is None:
            self.last_strengthened = time.time()
