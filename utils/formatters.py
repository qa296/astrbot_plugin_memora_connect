"""
工具格式化模块
提供跨层使用的数据格式化函数
"""
import json
from datetime import datetime
from typing import Any, Dict, List


def format_timestamp(timestamp: float) -> str:
    """格式化时间戳为可读字符串"""
    try:
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError, OSError):
        return "未知时间"


def format_memory_summary(memory: Dict[str, Any], max_length: int = 100) -> str:
    """格式化记忆摘要"""
    content = memory.get("content", "")
    if len(content) > max_length:
        content = content[:max_length] + "..."
    return content


def format_score(score: float, decimals: int = 2) -> str:
    """格式化分数"""
    try:
        return f"{float(score):.{decimals}f}"
    except (ValueError, TypeError):
        return "0.00"


def format_list_as_string(items: List[Any], separator: str = ", ", max_items: int = 10) -> str:
    """格式化列表为字符串"""
    if not items:
        return ""
    items_str = [str(item) for item in items[:max_items]]
    result = separator.join(items_str)
    if len(items) > max_items:
        result += f" ... (共{len(items)}项)"
    return result


def truncate_text(text: str, max_length: int = 200, suffix: str = "...") -> str:
    """截断文本"""
    if not text or len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def escape_markdown(text: str) -> str:
    """转义Markdown特殊字符"""
    if not text:
        return ""
    special_chars = ['\\', '*', '_', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


def format_dict_pretty(data: Dict[str, Any], indent: int = 2) -> str:
    """美化格式化字典"""
    try:
        return json.dumps(data, ensure_ascii=False, indent=indent)
    except (ValueError, TypeError):
        return str(data)


def format_duration(seconds: float) -> str:
    """格式化时长"""
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"
