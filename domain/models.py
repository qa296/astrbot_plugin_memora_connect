"""Memora Connect v2 领域层数据模型。纯数据结构，零 IO。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

CATEGORY_NAMES = {
    "person": "人物",
    "object": "物品",
    "place": "场所",
    "action": "行为",
    "trait": "特征",
}

CATEGORIES = tuple(CATEGORY_NAMES)


@dataclass
class Memory:
    """一条结构化记忆。strength 为显著度（0~1）。"""

    id: str
    scope_id: str
    content: str
    details: str = ""
    emotion: str = ""
    participants: list[str] = field(default_factory=list)
    embedding: bytes | None = None
    strength: float = 1.0
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 0


@dataclass
class Element:
    """实体节点（人物/物品/场所/行为/特征）。"""

    id: str
    scope_id: str
    name: str
    category: str = "trait"
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 0


@dataclass
class Impression:
    """对一个人的印象与好感度。"""

    scope_id: str
    subject: str
    score: float = 0.5
    summary: str = ""
    updated_at: float = field(default_factory=time.time)


@dataclass
class Session:
    """话题会话（形成管线的中间产物，持久化）。"""

    id: str
    scope_id: str
    topic: str = ""
    status: str = "ongoing"  # ongoing | completed | open_question
    rounds: int = 0
    summary: str = ""
    keywords: list[str] = field(default_factory=list)
    emotion: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class Message:
    """raw_messages 缓冲中的一条原始消息。"""

    seq: int
    content: str
    sender_id: str
    sender_name: str
    ts: float


@dataclass
class FormedElements:
    """一次会话分析中提取的元素与关系（写给 storage 的形态）。"""

    elements: list[dict] = field(default_factory=list)
    relations: list[dict] = field(default_factory=list)


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def score_verbal(score: float) -> str:
    """把 0~1 的好感度分数转成可注入的中文描述。"""
    if score >= 0.8:
        return "很高"
    if score >= 0.6:
        return "较高"
    if score >= 0.4:
        return "一般"
    if score >= 0.2:
        return "较低"
    return "很低"
