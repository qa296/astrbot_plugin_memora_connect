import asyncio
import time
from datetime import datetime
import re
from typing import Dict, List, Any, TYPE_CHECKING
from dataclasses import dataclass
try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from .main import MemorySystem


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
    
    def __init__(self, memory_system: 'MemorySystem'):
        self.memory_system = memory_system
        self.recall_strategies = {
            'semantic': 0.55,     # 语义相似度
            'keyword': 0.2,       # 关键词匹配
            'associative': 0.2,   # 联想记忆
            'temporal': 0.03,     # 时间关联
            'strength': 0.02      # 记忆强度
        }
        
    async def recall_all_relevant_memories(
        self,
        query: str,
        max_memories: int = 10,
        include_context: bool = True,
        group_id: str = ""
    ) -> List[MemoryRecallResult]:
        """
        召回所有相关记忆，使用多维度召回策略
        
        Args:
            query: 查询内容
            max_memories: 最大返回记忆数量
            include_context: 是否包含上下文信息
            group_id: 群组ID，用于群聊隔离
            
        Returns:
            按相关性排序的记忆列表
        """
        try:
            if not self.memory_system.memory_graph.memories:
                return []
            
            all_results = []
            
            # 并发执行全部五种切记策略
            tasks = [
                self._semantic_recall(query, group_id),
                self._keyword_recall(query, group_id),
                self._associative_recall(query, group_id),
                self._temporal_recall(query, group_id),
                self._strength_based_recall(query, group_id)
            ]
            results = await asyncio.gather(*tasks)
            for res in results:
                all_results.extend(res)
            
            # 去重和排序
            unique_results = self._deduplicate_and_rank(all_results)
            
            # 限制数量
            final_results = unique_results[:max_memories]
            
            logger.debug(f"增强记忆召回完成: 找到{len(final_results)}条相关记忆")
            return final_results
            
        except Exception as e:
            logger.error(f"增强记忆召回失败: {e}")
            return []
    
    async def _semantic_recall(self, query: str, group_id: str = "") -> List[MemoryRecallResult]:
        """基于语义相似度的召回 - 使用并填充缓存"""
        try:
            if not query:
                return []
                
            # 检查当前回忆模式，如果不是embedding模式，直接返回空列表
            if self.memory_system.memory_config["recall_mode"] not in ["embedding"]:
                logger.debug("语义召回跳过：当前不是embedding模式")
                return []
                
            if not self.memory_system.embedding_cache:
                logger.debug("语义召回跳过：embedding_cache 未就绪")
                return []
                
            # 检查是否配置了嵌入提供商
            provider = await self.memory_system.get_embedding_provider()
            if not provider:
                logger.debug("语义召回跳过：嵌入提供商不可用")
                return []
                
            # 1. 获取查询的嵌入向量
            query_embedding = await self.memory_system.get_embedding(query)
            if not query_embedding:
                logger.debug("语义召回失败：无法获取查询的嵌入向量")
                return []
            
            results = []
            # 过滤群聊记忆
            memories_snapshot = []
            for memory in self.memory_system.memory_graph.memories.values():
                # 如果启用了群聊隔离，检查群聊ID
                memory_group_id = getattr(memory, 'group_id', '')
                if group_id:
                    if memory_group_id == group_id:
                        memories_snapshot.append(memory)
                elif not group_id:  # 如果没有群聊ID，只获取默认记忆
                    if not memory_group_id:
                        memories_snapshot.append(memory)

            logger.debug(f"开始语义召回，查询: {query}, 记忆总数: {len(memories_snapshot)}")
            
            # 2. 批量获取所有记忆的嵌入向量（智能利用缓存）
            memory_embeddings = {}
            tasks = []
            for memory in memories_snapshot:
                # get_embedding 会自动处理缓存：命中则返回，未命中则计算、缓存后返回
                task = asyncio.create_task(self.memory_system.embedding_cache.get_embedding(memory.id, memory.content, group_id))
                tasks.append((memory.id, task))

            # 并发执行所有获取任务
            failed_embeddings = 0
            for memory_id, task in tasks:
                try:
                    embedding = await task
                    if embedding:
                        memory_embeddings[memory_id] = embedding
                    else:
                        failed_embeddings += 1
                except Exception as e:
                    failed_embeddings += 1
                    logger.warning(f"获取记忆 {memory_id} 的嵌入向量失败: {e}")

            # 3. 在内存中计算相似度
            if failed_embeddings:
                logger.debug(f"语义召回嵌入失败数: {failed_embeddings}")
            for memory in memories_snapshot:
                if memory.id in memory_embeddings:
                    similarity = self._cosine_similarity(query_embedding, memory_embeddings[memory.id])
                    
                    if similarity > 0.3:  # 相似度阈值
                        concept = self.memory_system.memory_graph.concepts.get(memory.concept_id)
                        if concept:
                            results.append(MemoryRecallResult(
                                memory=memory.content,
                                relevance_score=similarity * self.recall_strategies['semantic'],
                                memory_type='semantic',
                                concept_id=memory.concept_id,
                                metadata={
                                    'memory_id': memory.id,
                                    'concept_name': concept.name,
                                    'memory_strength': memory.strength,
                                    'last_accessed': memory.last_accessed,
                                    'source': 'cached_semantic',
                                    'similarity': similarity,
                                    'group_id': group_id
                                }
                            ))
            
            logger.debug(f"缓存语义召回完成，找到 {len(results)} 条相关记忆")
            return results
            
        except Exception as e:
            logger.error(f"语义召回失败: {e}")
            return []
    
    async def _temporal_recall(self, query: str, group_id: str = "") -> List[MemoryRecallResult]:
        """基于时间关联的召回"""
        try:
            current_time = time.time()
            time_window = 24 * 3600  # 24小时时间窗口
            
            results = []
            
            for memory in self.memory_system.memory_graph.memories.values():
                # 群聊隔离检查
                memory_group_id = getattr(memory, 'group_id', '')
                if group_id:
                    if memory_group_id != group_id:
                        continue
                elif not group_id:
                    if memory_group_id:
                        continue
                
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
                                'memory_id': memory.id,
                                'hours_ago': time_diff / 3600,
                                'concept_name': concept.name,
                                'memory_strength': memory.strength,
                                'group_id': group_id
                            }
                        ))
            
            return results
            
        except Exception as e:
            logger.error(f"时间关联召回失败: {e}")
            return []
    
    async def _strength_based_recall(self, query: str, group_id: str = "") -> List[MemoryRecallResult]:
        """基于记忆强度的召回"""
        try:
            # 获取所有记忆，按强度排序
            all_memories = list(self.memory_system.memory_graph.memories.values())
            
            # 群聊隔离过滤
            filtered_memories = []
            for memory in all_memories:
                memory_group_id = getattr(memory, 'group_id', '')
                if group_id:
                    if memory_group_id == group_id:
                        filtered_memories.append(memory)
                elif not group_id:
                    if not memory_group_id:
                        filtered_memories.append(memory)
            
            filtered_memories.sort(key=lambda m: m.strength, reverse=True)
            
            results = []
            
            # 取前20%的高强度记忆
            top_memories = filtered_memories[:max(5, len(filtered_memories) // 5)]
            
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
                            'memory_id': memory.id,
                            'concept_name': concept.name,
                            'memory_strength': memory.strength,
                            'access_count': memory.access_count,
                            'group_id': group_id
                        }
                    ))
            
            return results
            
        except Exception as e:
            logger.error(f"强度召回失败: {e}")
            return []
    
    def _extract_keywords(self, text: str) -> List[str]:
        """从文本中提取关键词"""
        try:
            stop_words = {
                "你好", "谢谢", "再见", "请问", "可以", "这个", "那个",
                "什么", "怎么", "为什么", "因为", "所以", "但是",
                "我", "你", "他", "她", "它", "我们", "你们", "他们", "她们", "它们",
                "啊", "呀", "呢", "吧", "哈", "吗", "喔", "哦"
            }
            
            try:
                import jieba
                words = [w.strip() for w in jieba.cut(text) if w.strip()]
            except Exception:
                words = re.findall(r'[\u4e00-\u9fff]{2,6}', text)
            
            keywords = [word for word in words if word not in stop_words and len(word) >= 2]
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
    
    def format_memories_for_llm(self, memories: List[MemoryRecallResult], include_ids: bool = False) -> str:
        """将记忆格式化为LLM友好的上下文"""
        try:
            if not memories:
                return ""
            
            # 按相关性排序
            memories.sort(key=lambda x: x.relevance_score, reverse=True)
            
            # 构建上下文
            context_parts = ["【相关记忆】"]
            
            for i, memory in enumerate(memories[:5], 1):  # 最多5条
                memory_obj = None
                for mem in self.memory_system.memory_graph.memories.values():
                    if mem.content == memory.memory:
                        memory_obj = mem
                        break
                
                time_str = ""
                if memory_obj and memory_obj.created_at:
                    try:
                        dt = datetime.fromtimestamp(memory_obj.created_at)
                        time_str = f"[记录于: {dt.strftime('%Y-%m-%d %H:%M:%S')}] "
                    except Exception:
                        pass
                
                prefix = ""
                if memory_obj and memory_obj.participants:
                    if "我" in memory_obj.participants:
                        prefix = "我记得: "

                context_parts.append(f"{i}. {time_str}{prefix}{memory.memory}")
                if include_ids:
                    memory_id = memory.metadata.get("memory_id") if memory.metadata else None
                    if not memory_id and memory_obj:
                        memory_id = getattr(memory_obj, "id", "")
                    if memory_id:
                        context_parts.append(f"   记忆ID: {memory_id}")

                if memory_obj:
                    details = getattr(memory_obj, "details", "") or ""
                    participants = getattr(memory_obj, "participants", "") or ""
                    location = getattr(memory_obj, "location", "") or ""
                    emotion = getattr(memory_obj, "emotion", "") or ""
                    tags = getattr(memory_obj, "tags", "") or ""
                    extra_fields = [
                        ("细节", details),
                        ("参与者", participants),
                        ("地点", location),
                        ("情感", emotion),
                        ("标签", tags),
                    ]
                    for label, value in extra_fields:
                        if value:
                            context_parts.append(f"   {label}: {value}")
            
            # 添加元信息
            if len(memories) > 5:
                context_parts.append(f"...还有{len(memories)-5}条相关记忆")
            
            return "\n".join(context_parts)
            
        except Exception as e:
            logger.error(f"格式化记忆上下文失败: {e}")
            return ""
    
    async def _keyword_recall(self, query: str, group_id: str = "", keywords: List[str] = None) -> List[MemoryRecallResult]:
        """基于关键词的召回"""
        try:
            if not query:
                return []

            if keywords is None:
                keywords = self._extract_keywords(query)
            if not keywords:
                return []
            
            results = []
            query_lower = query.lower()
            
            for memory in self.memory_system.memory_graph.memories.values():
                # 群聊隔离过滤
                memory_group_id = getattr(memory, 'group_id', '')
                if group_id:
                    if memory_group_id != group_id:
                        continue
                elif not group_id:
                    if memory_group_id:
                        continue
                
                concept = self.memory_system.memory_graph.concepts.get(memory.concept_id)
                details = getattr(memory, 'details', '') or ''
                tags = getattr(memory, 'tags', '') or ''
                concept_name = concept.name if concept else ''
                searchable_text = f"{memory.content} {details} {tags} {concept_name}".lower()
                
                # 计算关键词匹配度
                keyword_score = 0
                matched_keywords = []
                
                for keyword in keywords:
                    if keyword in searchable_text:
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
                            'memory_id': memory.id,
                            'matched_keywords': matched_keywords,
                            'keyword_total': len(keywords),
                            'concept_name': concept.name if concept else '',
                            'memory_strength': memory.strength,
                            'group_id': group_id
                        }
                    ))
            
            return results
            
        except Exception as e:
            logger.error(f"关键词召回失败: {e}")
            return []
    
    async def _associative_recall(self, query: str, group_id: str = "") -> List[MemoryRecallResult]:
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
                        
                        # 群聊隔离过滤
                        filtered_memories = []
                        for memory in neighbor_memories:
                            memory_group_id = getattr(memory, 'group_id', '')
                            if group_id:
                                if memory_group_id == group_id:
                                    filtered_memories.append(memory)
                            elif not group_id:
                                if not memory_group_id:
                                    filtered_memories.append(memory)
                        
                        # 按强度排序，取前2条
                        filtered_memories.sort(key=lambda m: m.strength, reverse=True)
                        
                        for memory in filtered_memories[:2]:
                            concept = self.memory_system.memory_graph.concepts.get(neighbor_id)
                            if concept:
                                relevance = strength * self.recall_strategies['associative']
                                results.append(MemoryRecallResult(
                                    memory=memory.content,
                                    relevance_score=relevance,
                                    memory_type='associative',
                                    concept_id=neighbor_id,
                                    metadata={
                                        'memory_id': memory.id,
                                        'original_concept': concept_id,
                                        'connection_strength': strength,
                                        'concept_name': concept.name,
                                        'group_id': group_id
                                    }
                                ))
                  
            return results
            
        except Exception as e:
            logger.error(f"联想记忆召回失败: {e}")
            return []

    def _filter_injection_results(self, results: List[MemoryRecallResult], keywords: List[str], semantic_primary: bool) -> List[MemoryRecallResult]:
        try:
            if not results:
                return []

            keyword_total = len(keywords)
            if keyword_total >= 4:
                min_keyword_matches = 2
            elif keyword_total == 3:
                min_keyword_matches = 2
            else:
                min_keyword_matches = 1

            semantic_min_similarity = 0.45

            semantic_primary_effective = semantic_primary
            primary_results = []
            for result in results:
                if result.memory_type == "semantic":
                    similarity = result.metadata.get("similarity", 0)
                    if similarity >= semantic_min_similarity:
                        primary_results.append(result)

            if not primary_results or not semantic_primary:
                semantic_primary_effective = False
                primary_results = []
                for result in results:
                    if result.memory_type == "keyword":
                        matched = len(result.metadata.get("matched_keywords", []))
                        total = result.metadata.get("keyword_total", keyword_total)
                        ratio = matched / total if total else 0
                        if matched >= min_keyword_matches and ratio >= 0.5:
                            primary_results.append(result)
                    elif result.memory_type == "semantic":
                        similarity = result.metadata.get("similarity", 0)
                        if similarity >= semantic_min_similarity:
                            primary_results.append(result)

            if not primary_results:
                return []

            primary_concepts = {r.concept_id for r in primary_results if r.concept_id}
            primary_ids = {id(r) for r in primary_results}
            semantic_primary_concepts = {r.concept_id for r in primary_results if r.memory_type == "semantic" and r.concept_id}

            filtered = []
            for result in results:
                if id(result) in primary_ids:
                    filtered.append(result)
                    continue

                if result.memory_type == "keyword":
                    matched = len(result.metadata.get("matched_keywords", []))
                    total = result.metadata.get("keyword_total", keyword_total)
                    ratio = matched / total if total else 0
                    if matched >= min_keyword_matches and ratio >= 0.5:
                        if not semantic_primary_effective or result.concept_id in semantic_primary_concepts:
                            filtered.append(result)
                elif result.memory_type == "associative":
                    original_concept = result.metadata.get("original_concept")
                    if original_concept and original_concept in primary_concepts:
                        filtered.append(result)
                elif result.memory_type in {"temporal", "strength"}:
                    if result.concept_id in primary_concepts:
                        filtered.append(result)

            return filtered

        except Exception as e:
            logger.error(f"注入结果过滤失败: {e}")
            return results

    async def recall_relevant_memories_for_injection(self, message: str, group_id: str = "") -> List[MemoryRecallResult]:
        """为自动注入召回相关记忆"""
        try:
            if not self.memory_system.memory_graph.memories:
                return []
                
            enable_associative = self.memory_system.memory_config.get("enable_associative_recall", True)
            keywords = self._extract_keywords(message)
            all_results = []

            semantic_results = await self._semantic_recall(message, group_id)
            semantic_primary = bool(semantic_results)
            all_results.extend(semantic_results)
            
            # 基础召回策略（所有模式都包含）
            keyword_results = await self._keyword_recall(message, group_id, keywords=keywords)
            all_results.extend(keyword_results)
            
            if enable_associative:
                associative_results = await self._associative_recall(message, group_id)
                all_results.extend(associative_results)
            
            temporal_results = await self._temporal_recall(message, group_id)
            all_results.extend(temporal_results)
            
            strength_results = await self._strength_based_recall(message, group_id)
            all_results.extend(strength_results)
            
            # 去重和排序
            unique_results = self._deduplicate_and_rank(all_results)

            # 注入专用过滤
            filtered_results = self._filter_injection_results(unique_results, keywords, semantic_primary)
            
            # 限制数量
            max_memories = self.memory_system.memory_config.get("max_injected_memories", 5)
            return filtered_results[:max_memories]
            
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
                # 获取完整的记忆对象以检查参与者信息
                memory_obj = None
                for mem in self.memory_system.memory_graph.memories.values():
                    if mem.content == memory.memory:
                        memory_obj = mem
                        break
                
                # 格式化时间
                time_str = ""
                if memory_obj and memory_obj.created_at:
                    try:
                        dt = datetime.fromtimestamp(memory_obj.created_at)
                        time_str = f"[记录于: {dt.strftime('%Y-%m-%d %H:%M:%S')}] "
                    except Exception:
                        pass
                
                # 如果找到记忆对象，检查是否包含Bot的发言
                if memory_obj and memory_obj.participants:
                    if "我" in memory_obj.participants:
                        # 如果参与者包含"我"，说明是Bot的发言，使用第一人称格式
                        context_parts.append(f"{i}. {time_str}我记得: {memory.memory}")
                    else:
                        # 否则使用第三人称格式
                        context_parts.append(f"{i}. {time_str}{memory.memory}")
                else:
                    # 如果没有参与者信息，使用默认格式
                    context_parts.append(f"{i}. {time_str}{memory.memory}")
            
            # 添加元信息
            if len(memories) > 5:
                context_parts.append(f"...还有{len(memories)-5}条相关记忆")
            
            return "\n".join(context_parts)
            
        except Exception as e:
            logger.error(f"格式化注入记忆失败: {e}")
            return ""

    async def get_embedding_cache_stats(self) -> Dict[str, Any]:
        """获取嵌入向量缓存的统计信息"""
        try:
            if self.memory_system.embedding_cache:
                return await self.memory_system.embedding_cache.get_cache_stats()
            else:
                return {
                    "cached_memories": 0,
                    "cache_hit_rate": 0.0,
                    "total_requests": 0,
                    "status": "embedding_cache_not_enabled"
                }
        except Exception as e:
            logger.error(f"获取嵌入向量缓存统计失败: {e}")
            return {}
    
    async def trigger_precomputation_for_uncached_memories(self, memory_ids: List[str] = None) -> bool:
        """触发未缓存认忆的预计算任务"""
        try:
            if not self.memory_system.embedding_cache:
                logger.warning("嵌入向量缓存未启用")
                return False
            
            if not self.memory_system.memory_graph.memories:
                logger.warning("没有记忆需要预计算")
                return False
            
            # 如果没有指定记忆ID，则处理所有未缓存的记忆
            if not memory_ids:
                memory_ids = list(self.memory_system.memory_graph.memories.keys())
            
            # 统计预计算状态
            total_count = len(memory_ids)
            uncached_memory_ids = []
            
            for memory_id in memory_ids:
                # 获取记忆对象以传递group_id
                memory = self.memory_system.memory_graph.memories.get(memory_id)
                if memory:
                    memory_group_id = getattr(memory, 'group_id', '')
                    if not await self.memory_system.embedding_cache._get_cached_embedding(memory_id, memory_group_id):
                        uncached_memory_ids.append(memory_id)
                else:
                    # 如果找不到记忆对象，使用空group_id
                    if not await self.memory_system.embedding_cache._get_cached_embedding(memory_id):
                        uncached_memory_ids.append(memory_id)
            
            if not uncached_memory_ids:
                logger.info(f"所有 {total_count} 条记忆的嵌入向量已经缓存")
                return True
            
            # 分批触发预计算任务
            batch_size = 50
            success_count = 0
            
            for i in range(0, len(uncached_memory_ids), batch_size):
                batch_memory_ids = uncached_memory_ids[i:i + batch_size]
                priority = 3 if i == 0 else 2  # 第一批高优先级
                
                await self.memory_system.embedding_cache.schedule_precompute_task(
                    batch_memory_ids, priority=priority
                )
                success_count += len(batch_memory_ids)
                
                # 避免过于频繁的调度
                if i + batch_size < len(uncached_memory_ids):
                    await asyncio.sleep(0.1)
            
            logger.info(f"已触发预计算任务: {success_count}/{total_count} 条记忆")
            return True
            
        except Exception as e:
            logger.error(f"触发预计算任务失败: {e}")
            return False
