import time
from datetime import datetime
from typing import Any

from astrbot.api import logger


class EnhancedMemoryDisplay:
    """增强记忆展示系统 - 支持详细记忆信息的格式化展示"""

    def __init__(self, memory_system):
        self.memory_system = memory_system

    def _get_element_info(self, memory) -> tuple[str, list[str], list[str]]:
        """获取记忆的元素信息，返回 (first_element_name, element_names, element_details)"""
        graph = self.memory_system.memory_graph
        mem_elements = graph.get_memory_elements(memory.id)
        if mem_elements:
            names = [f"{e.name}({e.category})" for e, _ in mem_elements]
            detail_parts = []
            for e, role in mem_elements:
                if role:
                    detail_parts.append(f"{e.name}[{role}]")
                else:
                    detail_parts.append(e.name)
            return mem_elements[0][0].name if mem_elements else "", names, detail_parts

        return "", [], []

    def format_detailed_memory(self, memory, concept=None) -> str:
        try:
            concept_name, element_names, _ = self._get_element_info(memory)
            display_name = concept_name or (concept.name if concept else "")
            parts = [f"**{display_name}**", f"{memory.content}"]

            if getattr(memory, "details", ""):
                parts.append(f"细节: {memory.details}")

            if element_names:
                parts.append(f"元素: {', '.join(element_names)}")

            if getattr(memory, "emotion", ""):
                parts.append(f"情感: {memory.emotion}")

            created_time = datetime.fromtimestamp(memory.created_at).strftime("%Y-%m-%d %H:%M")
            parts.append(f"创建时间: {created_time}")

            strength_bar = self._create_strength_bar(memory.strength)
            parts.append(f"记忆强度: {strength_bar} ({memory.strength:.2f})")

            if memory.access_count > 0:
                last_access = datetime.fromtimestamp(memory.last_accessed).strftime("%Y-%m-%d %H:%M")
                parts.append(f"访问次数: {memory.access_count} (最后访问: {last_access})")

            return "\n".join(parts)

        except Exception as e:
            logger.error(f"格式化详细记忆失败: {e}")
            return f"{memory.content}"

    def _create_strength_bar(self, strength: float) -> str:
        """创建记忆强度进度条"""
        try:
            # 将强度转换为0-10的整数
            level = max(0, min(10, int(strength * 10)))
            filled = "█" * level
            empty = "░" * (10 - level)
            return f"{filled}{empty}"
        except:
            return "░░░░░░░░░░"

    def format_memory_list(self, memories: list[Any], concepts: dict[str, Any] = None) -> str:
        try:
            if not memories:
                return "没有找到相关记忆"

            parts = [f"找到 {len(memories)} 条相关记忆\n"]

            for i, memory in enumerate(memories, 1):
                concept_name, element_names, _ = self._get_element_info(memory)
                display_name = concept_name or ""

                parts.append(f"{i}. **{display_name}**: {memory.content}")

                details = []
                if getattr(memory, "emotion", ""):
                    details.append(f"情感: {memory.emotion}")
                if element_names:
                    details.append(f"元素: {len(element_names)}个")

                if details:
                    parts.append(f"   {', '.join(details)}")

                strength_bar = self._create_strength_bar(memory.strength)
                parts.append(f"   {strength_bar} ({memory.strength:.2f})\n")

            return "\n".join(parts)

        except Exception as e:
            logger.error(f"格式化记忆列表失败: {e}")
            return "记忆格式化失败"

    def format_memory_search_result(self, memories: list[Any], query: str) -> str:
        try:
            if not memories:
                return f"没有找到与 '{query}' 相关的记忆"

            parts = [f"搜索 '{query}' 的结果: 找到 {len(memories)} 条相关记忆\n"]

            memories.sort(key=lambda m: m.strength, reverse=True)

            for i, memory in enumerate(memories[:10], 1):
                concept_name, element_names, _ = self._get_element_info(memory)
                card = self._create_memory_card(memory, concept_name, element_names, i)
                parts.append(card)

            if len(memories) > 10:
                parts.append(f"\n...还有 {len(memories) - 10} 条记忆未显示")

            return "\n".join(parts)

        except Exception as e:
            logger.error(f"格式化搜索结果失败: {e}")
            return f"搜索失败: {str(e)}"

    def _create_memory_card(self, memory, concept_name: str = "", element_names: list[str] = None, index: int = 0) -> str:
        try:
            display_name = concept_name or "记忆"
            lines = [
                f"{'=' * 50}",
                f"记忆 #{index} - {display_name}",
                f"记忆ID: {memory.id}",
                f"内容: {memory.content}",
            ]

            info_lines = []
            if getattr(memory, "details", ""):
                info_lines.append(f"细节: {memory.details}")
            if element_names:
                info_lines.append(f"元素: {', '.join(element_names)}")
            if getattr(memory, "emotion", ""):
                info_lines.append(f"情感: {memory.emotion}")

            if info_lines:
                lines.extend(info_lines)

            created_time = datetime.fromtimestamp(memory.created_at).strftime("%Y-%m-%d %H:%M")
            allow_forget_text = "是" if getattr(memory, "allow_forget", True) else "否"
            lines.extend([
                f"创建: {created_time}",
                f"允许遗忘: {allow_forget_text}",
                f"强度: {memory.strength:.2f} | 访问: {memory.access_count}次",
                f"{'=' * 50}",
            ])

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"创建记忆卡片失败: {e}")
            return f"{memory.content}"

    def format_memory_statistics(self) -> str:
        try:
            graph = self.memory_system.memory_graph

            if not graph.memories:
                return "记忆库为空"

            total_memories = len(graph.memories)
            total_elements = len(getattr(graph, "elements", {}))
            total_connections = len(graph.connections)

            avg_strength = sum(m.strength for m in graph.memories.values()) / total_memories

            recent_memories = [
                m for m in graph.memories.values()
                if time.time() - m.created_at < 7 * 24 * 3600
            ]

            from ..core.models import CATEGORY_NAMES

            element_counts: dict[str, int] = {}
            for elem in getattr(graph, "elements", {}).values():
                cat = CATEGORY_NAMES.get(elem.category, elem.category)
                element_counts[cat] = element_counts.get(cat, 0) + 1

            top_elements = sorted(element_counts.items(), key=lambda x: x[1], reverse=True)

            # 统计热门元素（按关联记忆数排序）
            element_memory_count: dict[str, int] = {}
            for em in graph.element_memories:
                elem = graph.elements.get(em.element_id)
                if elem:
                    element_memory_count[elem.name] = element_memory_count.get(elem.name, 0) + 1
            top_element_names = sorted(element_memory_count.items(), key=lambda x: x[1], reverse=True)[:5]

            parts = [
                "记忆库统计",
                f"总记忆数: {total_memories}",
                f"总元素数: {total_elements}",
                f"总连接数: {total_connections}",
                f"平均记忆强度: {avg_strength:.2f}",
                f"最近7天新增: {len(recent_memories)}条记忆",
            ]

            if top_elements:
                parts.append("\n元素分布:")
                for cat, count in top_elements:
                    parts.append(f"   {cat}: {count}个")

            if top_element_names:
                parts.append("\n热门元素:")
                for name, count in top_element_names:
                    parts.append(f"   {name}: {count}条关联记忆")

            return "\n".join(parts)

        except Exception as e:
            logger.error(f"格式化记忆统计失败: {e}")
            return "获取统计信息失败"
