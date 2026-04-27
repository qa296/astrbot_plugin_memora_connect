"""
数据模型定义
包含记忆系统的核心数据结构：Element, ElementMemory, Memory, Connection
"""

import time
from dataclasses import dataclass


CATEGORIES = ("person", "object", "place", "action", "trait")

CATEGORY_NAMES = {
    "person": "人物",
    "object": "物品",
    "place": "场所",
    "action": "行为",
    "trait": "特征",
}


@dataclass
class Element:
    """元素节点，替代原来的 Concept"""

    id: str
    name: str
    category: str
    group_id: str = ""
    created_at: float = None
    last_accessed: float = None
    access_count: int = 0

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()
        if self.last_accessed is None:
            self.last_accessed = time.time()
        if self.category not in CATEGORIES:
            self.category = "trait"


@dataclass
class ElementMemory:
    """元素与记忆的关联"""

    element_id: str
    memory_id: str
    role: str = ""


@dataclass
class Memory:
    """记忆条目"""

    id: str
    content: str
    details: str = ""
    emotion: str = ""
    created_at: float = None
    last_accessed: float = None
    access_count: int = 0
    strength: float = 1.0
    allow_forget: bool = True
    group_id: str = ""

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()
        if self.last_accessed is None:
            self.last_accessed = time.time()
        if self.allow_forget is None:
            self.allow_forget = True


@dataclass
class Connection:
    """元素之间的连接"""

    id: str
    from_element: str
    to_element: str
    strength: float = 1.0
    last_strengthened: float = None

    def __post_init__(self):
        if self.last_strengthened is None:
            self.last_strengthened = time.time()


@dataclass
class Concept:
    """兼容旧数据迁移的概念节点"""

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
