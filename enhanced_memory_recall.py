xiimport asyncio
import json
import time
import re
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from astrbot.api import logger


@dataclass
class MemoryRecallResult:
    """记忆召回结果"""
    memory: str
    relevance_score: float
    memory_type: str  # 'semantic', 'keyword', 'associative', 'temporal'
    concept_id: str
    metadata: Dict[str, Any]


class EnhancedMemoryRecall:
    """增强记忆召回系统"""
    
    def __init__(self, memory_system):
        self.memory_system = memory_system
        self.recall_strategies = {
            'semantic': 0.4,      # 语义相似度
            'keyword': 0.25,      # 关键词匹配
            'associative': 0.2,   # 联想记忆
            'temporal': 0.1,      # 时间关联
            'strength': 0.05      # 记忆强度
        }
        
    async def recall_all_relevant_memories(
        self, 
        query: str, 
        max_memories: int = 10,
        include_context: bool = True
    ) -> List[MemoryRecallResult]:
        """
        召回所有相关记忆，使用多维度召回策略
        
        Args:
            query: 查询内容
            max_memories: 最大返回记忆数量
            include_context: 是否包含上下文信息
            
        Returns:
            按相关性排序的记忆列表
        """
        try:
            if not self.memory_system.memory_graph.memories:
                return []
            
            all_results = []
            
            # 1. 语义搜索召回
            semantic_results = await self._semantic_recall(query)
            all_results.extend(semantic_results)
            
            # 2. 关键词召回
            keyword_results = await self._keyword_recall(query)
            all_results.extend(keyword_results)
            
            # 3. 联想记忆召回
            associative_results = await self._associative_recall(query)
            all_results.extend(associative_results)
            
            # 4. 时间关联召回
            temporal_results = await self._temporal_recall(query)
            all_results.extend(temporal_results)
            
            # 5. 高权重记忆召回
            strength_results = await self._strength_based_recall(query)
            all_results.extend(strength_results)
            
            # 去重和排序
            unique_results = self._deduplicate_and_rank(all_results)
            
            # 限制数量
            final_results = unique_results[:max_memories]
            
            logger.info(f"增强记忆召回完成: 找到{len(final_results)}条相关记忆")
            return final_results
            
        except Exception as e:
            logger.error(f"增强记忆召回失败: {e}")
            return []
    
    async def _semantic_recall(self, query: str) -> List[MemoryRecallResult]:
        """基于语义相似度的召回"""
        try:
            if not query:
                return []
                
            query_embedding = await self.memory_system.get_embedding(query)
            if not query_embedding:
                logger.debug("无法获取查询的嵌入向量")
                return []
            
            results = []
            memories_snapshot = list(self.memory_system.memory_graph.memories.values())
            
            logger.debug(f"开始语义召回，查询: {query}, 记忆总数: {len(memories_snapshot)}")
            
            for i, memory in enumerate(memories_snapshot):
                try:
                    memory_embedding = await self.memory_system.get_embedding(memory.content)
                    if memory_embedding:
                        similarity = self._cosine_similarity(query_embedding, memory_embedding)
                        logger.debug(f"记忆 {i+1} 相似度: {similarity}")
                        
                        if similarity > 0.3:  # 相似度阈值
                            concept = self.memory_system.memory_graph.concepts.get(memory.concept_id)
                            if concept:
                                results.append(MemoryRecallResult(
                                    memory=memory.content,
                                    relevance_score=similarity * self.recall_strategies['semantic'],
                                    memory_type='semantic',
                                    concept_id=memory.concept_id,
                                    metadata={
                                        'concept_name': concept.name,
                                        'memory_strength': memory.strength,
                                        'last_accessed': memory.last_accessed
                                    }
                                ))
                except Exception as e:
                    logger.debug(f"处理记忆 {i+1} 时出错: {e}")
                    continue
            
            logger.debug(f"语义召回完成，找到 {len(results)} 条相关记忆")
            return results
            
        except Exception as e:
            logger.error(f"语义召回失败: {e}")
            return []
    
    async def _temporal_recall(self, query: str) -> List[MemoryRecallResult]:
        """基于时间关联的召回"""
        try:
            current_time = time.time()
            time_window = 24 * 3600  # 24小时时间窗口
            
            results = []
            
            for memory in self.memory_system.memory_graph.memories.values():
                time_diff = current_time - memory.last_accessed
                
                # 时间衰减因子
                if time_diff < time_window:
                    temporal_score = 1.0 - (time_diff / time_window)
                    
                    concept = self.memory_system.memory_graph.concepts.get(memory.concept_id)
                    if concept:
                        relevance = temporal_score * self.recall_strategies['temporal']
                        results.append(MemoryRecallResult(
                            memory=memory.content,
                            relevance_score=relevance,
                            memory_type='temporal',
                            concept_id=memory.concept_id,
                            metadata={
                                'hours_ago': time_diff / 3600,
                                'concept_name': concept.name,
                                'memory_strength': memory.strength
                            }
                        ))
            
            return results
            
        except Exception as e:
            logger.error(f"时间关联召回失败: {e}")
            return []
    
    async def _strength_based_recall(self, query: str) -> List[MemoryRecallResult]:
        """基于记忆强度的召回"""
        try:
            # 获取所有记忆，按强度排序
            all_memories = list(self.memory_system.memory_graph.memories.values())
            all_memories.sort(key=lambda m: m.strength, reverse=True)
            
            results = []
            
            # 取前20%的高强度记忆
            top_memories = all_memories[:max(5, len(all_memories) // 5)]
            
            for memory in top_memories:
                concept = self.memory_system.memory_graph.concepts.get(memory.concept_id)
                if concept:
                    relevance = memory.strength * self.recall_strategies['strength']
                    results.append(MemoryRecallResult(
                        memory=memory.content,
                        relevance_score=relevance,
                        memory_type='strength',
                        concept_id=memory.concept_id,
                        metadata={
                            'concept_name': concept.name,
                            'memory_strength': memory.strength,
                            'access_count': memory.access_count
                        }
                    ))
            
            return results
            
        except Exception as e:
            logger.error(f"强度召回失败: {e}")
            return []
    
    def _extract_keywords(self, text: str) -> List[str]:
        """从文本中提取关键词"""
        try:
            # 提取中文关键词
            words = re.findall(r'\b[\u4e00-\u9fff]{2,6}\b', text)
            
            # 过滤常用词
            stop_words = {
                "你好", "谢谢", "再见", "请问", "可以", "这个", "那个",
                "什么", "怎么", "为什么", "因为", "所以", "但是"
            }
            
            keywords = [word for word in words if word not in stop_words and len(word) >= 2]
            
            # 返回前8个关键词
            return keywords[:8]
            
        except Exception as e:
            logger.error(f"关键词提取失败: {e}")
            return []
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """计算余弦相似度"""
        try:
            if len(vec1) != len(vec2) or len(vec1) == 0:
                return 0.0
            
            dot_product = sum(a * b for a, b in zip(vec1, vec2))
            magnitude1 = sum(a * a for a in vec1) ** 0.5
            magnitude2 = sum(b * b for b in vec2) ** 0.5
            
            if magnitude1 == 0 or magnitude2 == 0:
                return 0.0
            
            return dot_product / (magnitude1 * magnitude2)
            
        except Exception:
            return 0.0
    
    def _deduplicate_and_rank(self, results: List[MemoryRecallResult]) -> List[MemoryRecallResult]:
        """去重并按相关性排序"""
        try:
            # 按记忆内容去重
            seen_memories = {}
            for result in results:
                if result.memory not in seen_memories:
                    seen_memories[result.memory] = result
                else:
                    # 合并相同记忆的分数
                    existing = seen_memories[result.memory]
                    existing.relevance_score = max(existing.relevance_score, result.relevance_score)
            
            # 转换为列表并排序
            unique_results = list(seen_memories.values())
            unique_results.sort(key=lambda x: x.relevance_score, reverse=True)
            
            return unique_results
            
        except Exception as e:
            logger.error(f"去重排序失败: {e}")
            return results
    
    async def generate_memory_summary(self, memories: List[MemoryRecallResult]) -> str:
        """为召回的记忆生成智能摘要"""
        try:
            if not memories:
                return ""
            
            # 按类型分组
            grouped_memories = {}
            for memory in memories:
                if memory.memory_type not in grouped_memories:
                    grouped_memories[memory.memory_type] = []
                grouped_memories[memory.memory_type].append(memory)
            
            # 生成摘要
            summary_parts = []
            
            if 'semantic' in grouped_memories:
                semantic_memories = grouped_memories['semantic'][:3]
                if semantic_memories:
                    summary_parts.append(f"语义相关: {len(semantic_memories)}条记忆")
            
            if 'keyword' in grouped_memories:
                keyword_memories = grouped_memories['keyword'][:3]
                if keyword_memories:
                    concepts = list(set([m.metadata.get('concept_name', '') for m in keyword_memories]))
                    summary_parts.append(f"关键词匹配: 涉及{', '.join(concepts[:2])}等主题")
            
            if 'associative' in grouped_memories:
                associative_memories = grouped_memories['associative'][:2]
                if associative_memories:
                    summary_parts.append(f"联想记忆: {len(associative_memories)}条相关记忆")
            
            # 构建最终摘要
            if summary_parts:
                return "【记忆摘要】" + "; ".join(summary_parts)
            else:
                return f"【记忆提示】找到{len(memories)}条相关记忆"
                
        except Exception as e:
            logger.error(f"生成记忆摘要失败: {e}")
            return f"【记忆提示】找到{len(memories)}条相关记忆"
    
    def format_memories_for_llm(self, memories: List[MemoryRecallResult]) -> str:
        """将记忆格式化为LLM友好的上下文"""
        try:
            if not memories:
                return ""
            
            # 按相关性排序
            memories.sort(key=lambda x: x.relevance_score, reverse=True)
            
            # 构建上下文
            context_parts = ["【相关记忆】"]
            
            for i, memory in enumerate(memories[:5], 1):  # 最多5条
                context_parts.append(f"{i}. {memory.memory}")
            
            # 添加元信息
            if len(memories) > 5:
                context_parts.append(f"...还有{len(memories)-5}条相关记忆")
            
            return "\n".join(context_parts)
            
        except Exception as e:
            logger.error(f"格式化记忆上下文失败: {e}")
            return ""
    
    async def _keyword_recall(self, query: str) -> List[MemoryRecallResult]:
        """基于关键词的召回"""
        try:
            if not query:
                return []
                
            keywords = self._extract_keywords(query)
            if not keywords:
                return []
            
            results = []
            query_lower = query.lower()
            
            for memory in self.memory_system.memory_graph.memories.values():
                memory_lower = memory.content.lower()
                concept = self.memory_system.memory_graph.concepts.get(memory.concept_id)
                
                # 计算关键词匹配度
                keyword_score = 0
                matched_keywords = []
                
                for keyword in keywords:
                    if keyword in memory_lower:
                        keyword_score += 1
                        matched_keywords.append(keyword)
                
                if keyword_score > 0:
                    relevance = (keyword_score / len(keywords)) * self.recall_strategies['keyword']
                    results.append(MemoryRecallResult(
                        memory=memory.content,
                        relevance_score=relevance,
                        memory_type='keyword',
                        concept_id=memory.concept_id,
                        metadata={
                            'matched_keywords': matched_keywords,
                            'concept_name': concept.name if concept else '',
                            'memory_strength': memory.strength
                        }
                    ))
            
            return results
            
        except Exception as e:
            logger.error(f"关键词召回失败: {e}")
            return []
    
    async def _associative_recall(self, query: str) -> List[MemoryRecallResult]:
        """基于联想记忆的召回"""
        try:
            if not query:
                return []
                
            # 找到与查询相关的概念
            related_concepts = []
            query_lower = query.lower()
            
            for concept in self.memory_system.memory_graph.concepts.values():
                if query_lower in concept.name.lower():
                    related_concepts.append(concept.id)
            
            if not related_concepts:
                return []
            
            results = []
            
            # 通过记忆图进行联想
            for concept_id in related_concepts:
                # 获取相邻概念
                neighbors = self.memory_system.memory_graph.get_neighbors(concept_id)
                
                for neighbor_id, strength in neighbors:
                    if strength > 0.3:  # 连接强度阈值
                        # 获取相邻概念下的记忆
                        neighbor_memories = [
                            m for m in self.memory_system.memory_graph.memories.values()
                            if m.concept_id == neighbor_id
                        ]
                        
                        # 按强度排序，取前2条
                        neighbor_memories.sort(key=lambda m: m.strength, reverse=True)
                        
                        for memory in neighbor_memories[:2]:
                            concept = self.memory_system.memory_graph.concepts.get(neighbor_id)
                            if concept:
                                relevance = strength * self.recall_strategies['associative']
                                results.append(MemoryRecallResult(
                                    memory=memory.content,
                                    relevance_score=relevance,
                                    memory_type='associative',
                                    concept_id=neighbor_id,
                                    metadata={
                                        'original_concept': concept_id,
                                        'connection_strength': strength,
                                        'concept_name': concept.name
                                    }
                                ))
                 
            return results
            
        except Exception as e:
            logger.error(f"联想记忆召回失败: {e}")
            return []

    async def recall_relevant_memories_for_injection(self, message: str) -> List[MemoryRecallResult]:
        """为自动注入召回相关记忆"""
        try:
            if not self.memory_system.memory_graph.memories:
                return []
                
            recall_mode = self.memory_system.memory_config.get("recall_mode", "simple")
            all_results = []
            
            # 基础召回策略（所有模式都包含）
            keyword_results = await self._keyword_recall(message)
            all_results.extend(keyword_results)
            
            associative_results = await self._associative_recall(message)
            all_results.extend(associative_results)
            
            temporal_results = await self._temporal_recall(message)
            all_results.extend(temporal_results)
            
            strength_results = await self._strength_based_recall(message)
            all_results.extend(strength_results)
            
            # 仅在嵌入模式下添加语义召回
            if recall_mode == "embedding":
                semantic_results = await self._semantic_recall(message)
                all_results.extend(semantic_results)
            
            # 去重和排序
            unique_results = self._deduplicate_and_rank(all_results)
            
            # 限制数量
            max_memories = self.memory_system.memory_config.get("max_injected_memories", 5)
            return unique_results[:max_memories]
            
        except Exception as e:
            logger.error(f"为注入召回记忆失败: {e}")
            return []

    def should_inject_memories(self, memories: List[MemoryRecallResult]) -> bool:
        """决定是否应该注入记忆"""
        if not memories:
            return False
            
        threshold = self.memory_system.memory_config.get("memory_injection_threshold", 0.3)
        max_relevance = max([m.relevance_score for m in memories])
        
        return max_relevance >= threshold

    def format_memories_for_injection(self, memories: List[MemoryRecallResult]) -> str:
        """将记忆格式化为注入上下文"""
        try:
            if not memories:
                return ""
                
            # 按相关性排序
            memories.sort(key=lambda x: x.relevance_score, reverse=True)
            
            # 构建上下文
            context_parts = ["【相关记忆】"]
            
            for i, memory in enumerate(memories[:5], 1):
                context_parts.append(f"{i}. {memory.memory}")
            
            # 添加元信息
            if len(memories) > 5:
                context_parts.append(f"...还有{len(memories)-5}条相关记忆")
            
            return "\n".join(context_parts)
            
        except Exception as e:
            logger.error(f"格式化注入记忆失败: {e}")
            return ""