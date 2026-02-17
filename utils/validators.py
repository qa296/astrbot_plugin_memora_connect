"""
工具验证模块
提供跨层使用的数据验证函数
"""

import re
from typing import Any


def validate_memory_id(memory_id: str) -> bool:
    """验证记忆ID格式"""
    if not memory_id or not isinstance(memory_id, str):
        return False
    # 检查是否以 memory_ 开头
    return memory_id.startswith("memory_")


def validate_concept_id(concept_id: str) -> bool:
    """验证概念ID格式"""
    if not concept_id or not isinstance(concept_id, str):
        return False
    return concept_id.startswith("concept_")


def validate_group_id(group_id: str) -> bool:
    """验证群组ID"""
    if group_id is None:
        return True
    if not isinstance(group_id, str):
        return False
    return True  # 群组ID可以是任意字符串


def validate_score(
    score: Any, min_val: float = 0.0, max_val: float = 1.0
) -> float | None:
    """验证分数范围"""
    try:
        score_float = float(score)
        if min_val <= score_float <= max_val:
            return score_float
        return None
    except (ValueError, TypeError):
        return None


def validate_timestamp(timestamp: Any) -> bool:
    """验证时间戳"""
    if timestamp is None:
        return True
    try:
        if isinstance(timestamp, (int, float)):
            return timestamp > 0
        return False
    except (ValueError, TypeError):
        return False


def sanitize_text(text: str, max_length: int = 10000) -> str:
    """清理文本"""
    if not text or not isinstance(text, str):
        return ""
    # 移除特殊字符但保留中文、英文、数字和基本标点
    text = re.sub(r'[^\w\u4e00-\u9fff\s，。！？、；：""' "【】（）—…]", "", text)
    # 限制长度
    if len(text) > max_length:
        text = text[:max_length]
    return text.strip()


def validate_json_string(json_str: str) -> bool:
    """验证JSON字符串"""
    import json

    try:
        json.loads(json_str)
        return True
    except (ValueError, TypeError):
        return False
