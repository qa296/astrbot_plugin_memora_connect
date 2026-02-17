import time
from datetime import datetime
from typing import Any

from astrbot.api import logger


class EnhancedMemoryDisplay:
    """增强记忆展示系统 - 支持详细记忆信息的格式化展示"""

    def __init__(self, memory_system):
        self.memory_system = memory_system

    def format_detailed_memory(self, memory, concept) -> str:
        """格式化详细记忆信息"""
        try:
            # 基础信息
            parts = [f"**{concept.name}**", f"{memory.content}"]

            # 详细信息
            if memory.details:
                parts.append(f"细节: {memory.details}")

            if memory.participants:
                participants = (
                    memory.participants.split(",")
                    if isinstance(memory.participants, str)
                    else memory.participants
                )
                # 特殊处理Bot身份标识
                formatted_participants = []
                for participant in participants:
                    participant = participant.strip()
                    if participant == "我":
                        formatted_participants.append("我(Bot)")
                    else:
                        formatted_participants.append(participant)
                parts.append(f"参与者: {', '.join(formatted_participants)}")

            if memory.location:
                parts.append(f"地点: {memory.location}")

            if memory.emotion:
                parts.append(f"情感: {memory.emotion}")

            if memory.tags:
                tags = (
                    memory.tags.split(",")
                    if isinstance(memory.tags, str)
                    else memory.tags
                )
                parts.append(f"标签: {', '.join(tags)}")

            # 时间信息
            created_time = datetime.fromtimestamp(memory.created_at).strftime(
                "%Y-%m-%d %H:%M"
            )
            parts.append(f"创建时间: {created_time}")

            # 记忆强度
            strength_bar = self._create_strength_bar(memory.strength)
            parts.append(f"记忆强度: {strength_bar} ({memory.strength:.2f})")

            # 访问统计
            if memory.access_count > 0:
                last_access = datetime.fromtimestamp(memory.last_accessed).strftime(
                    "%Y-%m-%d %H:%M"
                )
                parts.append(
                    f"访问次数: {memory.access_count} (最后访问: {last_access})"
                )

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

    def format_memory_list(self, memories: list[Any], concepts: dict[str, Any]) -> str:
        """格式化记忆列表"""
        try:
            if not memories:
                return "没有找到相关记忆"

            parts = [f"找到 {len(memories)} 条相关记忆\n"]

            for i, memory in enumerate(memories, 1):
                concept = concepts.get(memory.concept_id)
                if concept:
                    # 简洁格式
                    parts.append(f"{i}. **{concept.name}**: {memory.content}")

                    # 添加关键信息
                    details = []
                    if memory.emotion:
                        details.append(f"情感: {memory.emotion}")
                    if memory.location:
                        details.append(f"地点: {memory.location}")
                    if memory.participants:
                        participants = (
                            memory.participants.split(",")
                            if isinstance(memory.participants, str)
                            else memory.participants
                        )
                        # 特殊处理Bot身份标识，统计Bot参与的记忆
                        bot_count = sum(1 for p in participants if p.strip() == "我")
                        if bot_count > 0:
                            details.append(f"参与者: {len(participants)}人 (含Bot)")
                        else:
                            details.append(f"参与者: {len(participants)}人")

                    if details:
                        parts.append(f"   {', '.join(details)}")

                    # 记忆强度
                    strength_bar = self._create_strength_bar(memory.strength)
                    parts.append(f"   {strength_bar} ({memory.strength:.2f})\n")

            return "\n".join(parts)

        except Exception as e:
            logger.error(f"格式化记忆列表失败: {e}")
            return "记忆格式化失败"

    def format_memory_search_result(self, memories: list[Any], query: str) -> str:
        """格式化记忆搜索结果"""
        try:
            if not memories:
                return f"没有找到与 '{query}' 相关的记忆"

            parts = [f"搜索 '{query}' 的结果: 找到 {len(memories)} 条相关记忆\n"]

            # 按记忆强度排序
            memories.sort(key=lambda m: m.strength, reverse=True)

            for i, memory in enumerate(memories[:10], 1):  # 最多显示10条
                concept = self.memory_system.memory_graph.concepts.get(
                    memory.concept_id
                )
                if concept:
                    # 创建记忆卡片
                    card = self._create_memory_card(memory, concept, i)
                    parts.append(card)

            if len(memories) > 10:
                parts.append(f"\n...还有 {len(memories) - 10} 条记忆未显示")

            return "\n".join(parts)

        except Exception as e:
            logger.error(f"格式化搜索结果失败: {e}")
            return f"搜索失败: {str(e)}"

    def _create_memory_card(self, memory, concept, index: int) -> str:
        """创建记忆卡片"""
        try:
            lines = [
                f"{'=' * 50}",
                f"记忆 #{index} - {concept.name}",
                f"记忆ID: {memory.id}",
                f"内容: {memory.content}",
            ]

            # 详细信息
            info_lines = []
            if memory.details:
                info_lines.append(f"细节: {memory.details}")
            if memory.participants:
                participants = (
                    memory.participants.split(",")
                    if isinstance(memory.participants, str)
                    else memory.participants
                )
                # 特殊处理Bot身份标识
                formatted_participants = []
                for participant in participants:
                    participant = participant.strip()
                    if participant == "我":
                        formatted_participants.append("🤖 我(Bot)")
                    else:
                        formatted_participants.append(participant)
                info_lines.append(f"参与者: {', '.join(formatted_participants)}")
            if memory.location:
                info_lines.append(f"地点: {memory.location}")
            if memory.emotion:
                info_lines.append(f"情感: {memory.emotion}")
            if memory.tags:
                tags = (
                    memory.tags.split(",")
                    if isinstance(memory.tags, str)
                    else memory.tags
                )
                info_lines.append(f"标签: {', '.join(tags)}")

            if info_lines:
                lines.extend(info_lines)

            # 时间和统计信息
            created_time = datetime.fromtimestamp(memory.created_at).strftime(
                "%Y-%m-%d %H:%M"
            )
            allow_forget_text = "是" if getattr(memory, "allow_forget", True) else "否"
            lines.extend(
                [
                    f"创建: {created_time}",
                    f"允许遗忘: {allow_forget_text}",
                    f"强度: {memory.strength:.2f} | 👀 访问: {memory.access_count}次",
                    f"{'=' * 50}",
                ]
            )

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"创建记忆卡片失败: {e}")
            return f"💭 {memory.content}"

    def format_memory_statistics(self) -> str:
        """格式化记忆统计信息"""
        try:
            graph = self.memory_system.memory_graph

            if not graph.memories:
                return "记忆库为空"

            # 基础统计
            total_memories = len(graph.memories)
            total_concepts = len(graph.concepts)
            total_connections = len(graph.connections)

            # 计算平均记忆强度
            avg_strength = (
                sum(m.strength for m in graph.memories.values()) / total_memories
            )

            # 最近活动
            recent_memories = [
                m
                for m in graph.memories.values()
                if time.time() - m.created_at < 7 * 24 * 3600
            ]  # 7天内

            # 热门概念
            concept_counts = {}
            for memory in graph.memories.values():
                concept = graph.concepts.get(memory.concept_id)
                if concept:
                    concept_counts[concept.name] = (
                        concept_counts.get(concept.name, 0) + 1
                    )

            top_concepts = sorted(
                concept_counts.items(), key=lambda x: x, reverse=True
            )[:5]

            parts = [
                "记忆库统计",
                f"总记忆数: {total_memories}",
                f"总概念数: {total_concepts}",
                f"总连接数: {total_connections}",
                f"平均记忆强度: {avg_strength:.2f}",
                f"最近7天新增: {len(recent_memories)}条记忆",
            ]

            if top_concepts:
                parts.append("\n热门概念:")
                for concept, count in top_concepts:
                    parts.append(f"   {concept}: {count}条记忆")

            return "\n".join(parts)

        except Exception as e:
            logger.error(f"格式化记忆统计失败: {e}")
            return "获取统计信息失败"
