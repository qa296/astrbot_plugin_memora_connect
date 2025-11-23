"""
实时话题计算引擎
实现动态话题聚类、语义匹配和生命线追踪
"""

import time
import asyncio
import hashlib
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict
from astrbot.api import logger


@dataclass
class TopicCluster:
    """话题簇数据类"""
    topic_id: str
    keywords: Set[str]  # 话题关键词集合
    messages: List[Dict] = field(default_factory=list)  # 相关消息列表
    participants: Set[str] = field(default_factory=set)  # 参与者ID集合
    
    # 时间相关
    created_at: datetime = field(default_factory=datetime.now)
    last_active: datetime = field(default_factory=datetime.now)
    first_appear_time: datetime = field(default_factory=datetime.now)
    
    # 统计信息
    activation_count: int = 0  # 总激活次数
    message_count: int = 0  # 消息数量
    
    # 热度相关
    recent_message_timestamps: List[float] = field(default_factory=list)  # 最近消息时间戳
    
    def calculate_heat(self) -> float:
        """
        计算实时热度
        基于最近1小时的消息频率
        
        Returns:
            float: 热度值 (0-1)
        """
        now = time.time()
        one_hour_ago = now - 3600
        
        # 统计最近1小时的消息数
        recent_count = sum(1 for ts in self.recent_message_timestamps if ts > one_hour_ago)
        
        # 归一化热度值 (假设每小时超过10条消息为满热度)
        heat = min(recent_count / 10.0, 1.0)
        return heat
    
    def get_lifetime_seconds(self) -> float:
        """
        获取生命周期（秒）
        
        Returns:
            float: 从创建到现在的秒数
        """
        return (datetime.now() - self.created_at).total_seconds()
    
    def get_idle_seconds(self) -> float:
        """
        获取空闲时间（秒）
        
        Returns:
            float: 从最后活跃到现在的秒数
        """
        return (datetime.now() - self.last_active).total_seconds()
    
    def add_message(self, message: str, user_id: str, timestamp: Optional[float] = None):
        """
        添加消息到话题
        
        Args:
            message: 消息内容
            user_id: 用户ID
            timestamp: 消息时间戳，默认为当前时间
        """
        if timestamp is None:
            timestamp = time.time()
        
        self.messages.append({
            "content": message,
            "user_id": user_id,
            "timestamp": timestamp
        })
        
        self.participants.add(user_id)
        self.recent_message_timestamps.append(timestamp)
        
        # 只保留最近1小时的时间戳
        one_hour_ago = time.time() - 3600
        self.recent_message_timestamps = [
            ts for ts in self.recent_message_timestamps if ts > one_hour_ago
        ]
        
        self.message_count += 1
        self.activation_count += 1
        self.last_active = datetime.now()
    
    def calculate_depth(self) -> int:
        """
        计算话题讨论深度（讨论了几轮）
        简单实现：消息数量 / 参与者数量
        
        Returns:
            int: 讨论轮数
        """
        if not self.participants:
            return 0
        return max(1, self.message_count // len(self.participants))
    
    def to_dict(self) -> Dict:
        """转换为字典格式"""
        return {
            "topic_id": self.topic_id,
            "keywords": list(self.keywords),
            "participants": list(self.participants),
            "created_at": self.created_at.isoformat(),
            "last_active": self.last_active.isoformat(),
            "first_appear_time": self.first_appear_time.isoformat(),
            "activation_count": self.activation_count,
            "message_count": self.message_count,
            "heat": self.calculate_heat(),
            "lifetime_seconds": self.get_lifetime_seconds(),
            "idle_seconds": self.get_idle_seconds(),
            "depth": self.calculate_depth()
        }


class TopicEngine:
    """
    流式话题聚类引擎
    实时聚合和分析对话话题
    """
    
    def __init__(self, memory_system, similarity_threshold: float = 0.7):
        """
        初始化话题引擎
        
        Args:
            memory_system: 记忆系统实例
            similarity_threshold: 话题合并的相似度阈值 (0-1)
        """
        self.memory_system = memory_system
        self.similarity_threshold = similarity_threshold
        
        # 话题簇存储：{group_id: {topic_id: TopicCluster}}
        self.topics: Dict[str, Dict[str, TopicCluster]] = defaultdict(dict)
        
        # 话题历史：用于追踪话题的完整生命周期
        self.topic_history: Dict[str, List[TopicCluster]] = defaultdict(list)
        
        # 配置
        self.topic_expire_hours = 24  # 话题过期时间（小时）
        self.max_topics_per_group = 50  # 每个群组最多保留的活跃话题数
        
        # 缓存
        self._embedding_cache: Dict[str, List[float]] = {}
        
        logger.info(f"话题引擎已初始化，相似度阈值: {similarity_threshold}")
    
    def _generate_topic_id(self, keywords: Set[str], group_id: str) -> str:
        """
        生成话题ID
        
        Args:
            keywords: 关键词集合
            group_id: 群组ID
            
        Returns:
            str: 话题ID
        """
        content = f"{group_id}_{'_'.join(sorted(keywords))}_{int(time.time())}"
        return hashlib.md5(content.encode()).hexdigest()[:16]
    
    async def _extract_keywords(self, message: str) -> Set[str]:
        """
        从消息中提取关键词
        
        Args:
            message: 消息内容
            
        Returns:
            Set[str]: 关键词集合
        """
        try:
            # 使用记忆系统的LLM提取关键词
            llm_provider = await self.memory_system.get_llm_provider()
            if not llm_provider:
                # 降级：简单分词
                return self._simple_keyword_extraction(message)
            
            prompt = f"""请从以下消息中提取2-5个核心关键词，用逗号分隔：
消息：{message}
关键词："""
            
            try:
                response = await llm_provider.text_chat(prompt=prompt, context=[])
                keywords_str = response.completion_text.strip()
                keywords = set(kw.strip() for kw in keywords_str.split(',') if kw.strip())
                return keywords if keywords else self._simple_keyword_extraction(message)
            except Exception:
                return self._simple_keyword_extraction(message)
                
        except Exception as e:
            logger.debug(f"提取关键词失败: {e}")
            return self._simple_keyword_extraction(message)
    
    def _simple_keyword_extraction(self, message: str) -> Set[str]:
        """
        简单的关键词提取（降级方案）
        
        Args:
            message: 消息内容
            
        Returns:
            Set[str]: 关键词集合
        """
        # 使用jieba分词
        try:
            import jieba
            words = jieba.cut(message)
            # 过滤停用词和短词
            keywords = set(w for w in words if len(w) > 1)
            # 最多返回5个词
            return set(list(keywords)[:5]) if keywords else {"对话"}
        except:
            # 最基础的降级：直接使用前10个字符
            return {message[:10] if len(message) > 10 else message}
    
    async def _calculate_topic_similarity(self, keywords1: Set[str], keywords2: Set[str]) -> float:
        """
        计算两个话题的语义相似度
        
        Args:
            keywords1: 话题1的关键词集合
            keywords2: 话题2的关键词集合
            
        Returns:
            float: 相似度 (0-1)
        """
        if not keywords1 or not keywords2:
            return 0.0
        
        # 方法1：Jaccard相似度（词汇重叠）
        intersection = keywords1 & keywords2
        union = keywords1 | keywords2
        jaccard_sim = len(intersection) / len(union) if union else 0.0
        
        # 方法2：如果有嵌入向量，使用语义相似度
        try:
            embedding_provider = await self.memory_system.get_embedding_provider()
            if embedding_provider:
                text1 = " ".join(keywords1)
                text2 = " ".join(keywords2)
                
                # 获取或计算嵌入向量
                if text1 not in self._embedding_cache:
                    emb1 = await embedding_provider.get_embedding(text1)
                    self._embedding_cache[text1] = emb1
                else:
                    emb1 = self._embedding_cache[text1]
                
                if text2 not in self._embedding_cache:
                    emb2 = await embedding_provider.get_embedding(text2)
                    self._embedding_cache[text2] = emb2
                else:
                    emb2 = self._embedding_cache[text2]
                
                # 计算余弦相似度
                import numpy as np
                cos_sim = np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))
                
                # 加权组合
                return 0.3 * jaccard_sim + 0.7 * float(cos_sim)
        except Exception as e:
            logger.debug(f"计算语义相似度失败，使用Jaccard相似度: {e}")
        
        return jaccard_sim
    
    async def add_message_to_topic(self, message: str, user_id: str, group_id: str = ""):
        """
        将消息添加到话题系统
        自动进行话题聚类、合并等操作
        
        Args:
            message: 消息内容
            user_id: 用户ID
            group_id: 群组ID
        """
        try:
            # 1. 提取关键词
            keywords = await self._extract_keywords(message)
            if not keywords:
                return
            
            # 2. 查找匹配的话题
            matched_topic = await self._find_matching_topic(keywords, group_id)
            
            timestamp = time.time()
            
            if matched_topic:
                # 更新已有话题
                matched_topic.add_message(message, user_id, timestamp)
                matched_topic.keywords.update(keywords)  # 扩充关键词
                logger.debug(f"消息已添加到话题: {matched_topic.topic_id}")
                
                # 发布话题更新事件
                from .memory_events import MemoryEvent, MemoryEventType, get_event_bus
                event = MemoryEvent(
                    event_type=MemoryEventType.MEMORY_TRIGGERED,
                    group_id=group_id,
                    user_id=user_id,
                    data={
                        "topic_id": matched_topic.topic_id,
                        "keywords": list(keywords),
                        "heat": matched_topic.calculate_heat()
                    }
                )
                await get_event_bus().publish(event)
            else:
                # 创建新话题
                topic_id = self._generate_topic_id(keywords, group_id)
                new_topic = TopicCluster(
                    topic_id=topic_id,
                    keywords=keywords
                )
                new_topic.add_message(message, user_id, timestamp)
                
                self.topics[group_id][topic_id] = new_topic
                logger.info(f"创建新话题: {topic_id}, 关键词: {keywords}")
                
                # 发布话题创建事件
                from .memory_events import MemoryEvent, MemoryEventType, get_event_bus
                event = MemoryEvent(
                    event_type=MemoryEventType.TOPIC_CREATED,
                    group_id=group_id,
                    user_id=user_id,
                    data={
                        "topic_id": topic_id,
                        "keywords": list(keywords)
                    }
                )
                await get_event_bus().publish(event)
            
            # 3. 检查是否需要合并话题
            await self._try_merge_topics(group_id)
            
            # 4. 清理过期话题
            await self._cleanup_expired_topics(group_id)
            
        except Exception as e:
            logger.error(f"添加消息到话题失败: {e}", exc_info=True)
    
    async def _find_matching_topic(self, keywords: Set[str], group_id: str) -> Optional[TopicCluster]:
        """
        查找匹配的话题
        
        Args:
            keywords: 消息关键词
            group_id: 群组ID
            
        Returns:
            Optional[TopicCluster]: 匹配的话题，如果没有则返回None
        """
        if group_id not in self.topics:
            return None
        
        best_match = None
        best_similarity = 0.0
        
        # 查找最相似的活跃话题
        for topic in self.topics[group_id].values():
            # 跳过长时间未活跃的话题
            if topic.get_idle_seconds() > 3600:  # 1小时
                continue
            
            similarity = await self._calculate_topic_similarity(keywords, topic.keywords)
            if similarity > best_similarity and similarity >= 0.5:  # 至少50%相似度
                best_similarity = similarity
                best_match = topic
        
        return best_match
    
    async def _try_merge_topics(self, group_id: str):
        """
        尝试合并相似度高的话题
        
        Args:
            group_id: 群组ID
        """
        if group_id not in self.topics:
            return
        
        topics_list = list(self.topics[group_id].values())
        if len(topics_list) < 2:
            return
        
        # 检查所有话题对
        merged = set()
        for i, topic1 in enumerate(topics_list):
            if topic1.topic_id in merged:
                continue
                
            for topic2 in topics_list[i+1:]:
                if topic2.topic_id in merged:
                    continue
                
                # 计算相似度
                similarity = await self._calculate_topic_similarity(
                    topic1.keywords, topic2.keywords
                )
                
                # 如果相似度超过阈值，合并
                if similarity >= self.similarity_threshold:
                    # 合并到topic1
                    topic1.keywords.update(topic2.keywords)
                    topic1.messages.extend(topic2.messages)
                    topic1.participants.update(topic2.participants)
                    topic1.recent_message_timestamps.extend(topic2.recent_message_timestamps)
                    topic1.message_count += topic2.message_count
                    topic1.activation_count += topic2.activation_count
                    
                    # 更新时间
                    if topic2.created_at < topic1.created_at:
                        topic1.created_at = topic2.created_at
                    if topic2.last_active > topic1.last_active:
                        topic1.last_active = topic2.last_active
                    
                    # 删除topic2
                    del self.topics[group_id][topic2.topic_id]
                    merged.add(topic2.topic_id)
                    
                    logger.info(f"话题合并: {topic2.topic_id} -> {topic1.topic_id}, 相似度: {similarity:.2f}")
                    
                    # 发布合并事件
                    from .memory_events import MemoryEvent, MemoryEventType, get_event_bus
                    event = MemoryEvent(
                        event_type=MemoryEventType.TOPIC_MERGED,
                        group_id=group_id,
                        data={
                            "merged_from": topic2.topic_id,
                            "merged_to": topic1.topic_id,
                            "similarity": similarity
                        }
                    )
                    await get_event_bus().publish(event)
    
    async def _cleanup_expired_topics(self, group_id: str):
        """
        清理过期话题
        
        Args:
            group_id: 群组ID
        """
        if group_id not in self.topics:
            return
        
        now = time.time()
        expire_threshold = self.topic_expire_hours * 3600
        expired_topics = []
        
        for topic_id, topic in list(self.topics[group_id].items()):
            if topic.get_idle_seconds() > expire_threshold:
                # 移到历史记录
                self.topic_history[group_id].append(topic)
                del self.topics[group_id][topic_id]
                expired_topics.append(topic_id)
                
                logger.debug(f"话题已过期: {topic_id}")
                
                # 发布过期事件
                from .memory_events import MemoryEvent, MemoryEventType, get_event_bus
                event = MemoryEvent(
                    event_type=MemoryEventType.TOPIC_EXPIRED,
                    group_id=group_id,
                    data={
                        "topic_id": topic_id,
                        "lifetime_seconds": topic.get_lifetime_seconds()
                    }
                )
                await get_event_bus().publish(event)
        
        # 限制历史记录大小
        if len(self.topic_history[group_id]) > 1000:
            self.topic_history[group_id] = self.topic_history[group_id][-1000:]
        
        # 如果活跃话题过多，移除最不活跃的
        if len(self.topics[group_id]) > self.max_topics_per_group:
            # 按热度排序
            sorted_topics = sorted(
                self.topics[group_id].items(),
                key=lambda x: x[1].calculate_heat()
            )
            # 移除热度最低的话题
            for topic_id, topic in sorted_topics[:len(sorted_topics) - self.max_topics_per_group]:
                self.topic_history[group_id].append(topic)
                del self.topics[group_id][topic_id]
                logger.debug(f"话题因数量限制被移除: {topic_id}")
    
    async def get_topic_relevance(self, message: str, group_id: str = "", 
                                  max_results: int = 5) -> List[Tuple[str, float, Dict]]:
        """
        获取消息与现有话题的相关性
        
        Args:
            message: 当前消息
            group_id: 群组ID
            max_results: 最多返回结果数
            
        Returns:
            List[Tuple[topic_id, score, info]]: [(话题ID, 相关性分数, 话题信息)]
            话题信息包含：keywords, participants, depth, heat, lifetime
        """
        try:
            # 提取消息关键词
            keywords = await self._extract_keywords(message)
            if not keywords:
                return []
            
            if group_id not in self.topics or not self.topics[group_id]:
                return []
            
            results = []
            now = time.time()
            
            for topic_id, topic in self.topics[group_id].items():
                # 计算语义相似度
                similarity = await self._calculate_topic_similarity(keywords, topic.keywords)
                
                # 时间衰减：越近的话题权重越高
                idle_hours = topic.get_idle_seconds() / 3600
                time_decay = max(0.1, 1.0 - (idle_hours / 24))  # 24小时内线性衰减
                
                # 最终得分 = 语义相似度 * 时间衰减权重
                final_score = similarity * time_decay
                
                if final_score > 0.1:  # 过滤低分结果
                    results.append((
                        topic_id,
                        final_score,
                        {
                            "keywords": list(topic.keywords),
                            "participants": list(topic.participants),
                            "depth": topic.calculate_depth(),
                            "heat": topic.calculate_heat(),
                            "lifetime": topic.get_lifetime_seconds(),
                            "last_active": topic.last_active.isoformat()
                        }
                    ))
            
            # 按分数降序排序
            results.sort(key=lambda x: x[1], reverse=True)
            
            return results[:max_results]
            
        except Exception as e:
            logger.error(f"获取话题相关性失败: {e}", exc_info=True)
            return []
    
    async def get_topic_timeline(self, topic_id: str, group_id: str = "") -> Optional[Dict]:
        """
        获取话题的生命线信息
        
        Args:
            topic_id: 话题ID
            group_id: 群组ID
            
        Returns:
            Optional[Dict]: 话题生命线信息
        """
        # 先在活跃话题中查找
        if group_id in self.topics and topic_id in self.topics[group_id]:
            topic = self.topics[group_id][topic_id]
            return {
                "topic_id": topic_id,
                "status": "active",
                "first_appear_time": topic.first_appear_time.isoformat(),
                "created_at": topic.created_at.isoformat(),
                "last_active": topic.last_active.isoformat(),
                "total_activations": topic.activation_count,
                "message_count": topic.message_count,
                "lifetime_seconds": topic.get_lifetime_seconds(),
                "idle_seconds": topic.get_idle_seconds(),
                "heat": topic.calculate_heat(),
                "keywords": list(topic.keywords),
                "participants": list(topic.participants)
            }
        
        # 在历史记录中查找
        if group_id in self.topic_history:
            for topic in self.topic_history[group_id]:
                if topic.topic_id == topic_id:
                    return {
                        "topic_id": topic_id,
                        "status": "expired",
                        "first_appear_time": topic.first_appear_time.isoformat(),
                        "created_at": topic.created_at.isoformat(),
                        "last_active": topic.last_active.isoformat(),
                        "total_activations": topic.activation_count,
                        "message_count": topic.message_count,
                        "lifetime_seconds": topic.get_lifetime_seconds(),
                        "keywords": list(topic.keywords),
                        "participants": list(topic.participants)
                    }
        
        return None
    
    async def find_resurrected_topics(self, message: str, group_id: str = "", 
                                     silence_days: int = 7) -> List[str]:
        """
        查找被"复活"的话题（沉默N天后被重新提起）
        
        Args:
            message: 当前消息
            group_id: 群组ID
            silence_days: 沉默天数阈值
            
        Returns:
            List[str]: 被复活的话题ID列表
        """
        try:
            keywords = await self._extract_keywords(message)
            if not keywords:
                return []
            
            resurrected = []
            silence_seconds = silence_days * 86400
            
            # 在历史记录中查找匹配的话题
            if group_id in self.topic_history:
                for topic in self.topic_history[group_id]:
                    if topic.get_idle_seconds() < silence_seconds:
                        continue
                    
                    similarity = await self._calculate_topic_similarity(keywords, topic.keywords)
                    if similarity >= 0.6:  # 相似度阈值
                        resurrected.append(topic.topic_id)
                        logger.info(f"话题复活: {topic.topic_id}, 沉默了 {topic.get_idle_seconds()/86400:.1f} 天")
                        
                        # 发布复活事件
                        from .memory_events import MemoryEvent, MemoryEventType, get_event_bus
                        event = MemoryEvent(
                            event_type=MemoryEventType.TOPIC_RESURRECTED,
                            group_id=group_id,
                            data={
                                "topic_id": topic.topic_id,
                                "silence_days": topic.get_idle_seconds() / 86400,
                                "keywords": list(topic.keywords)
                            }
                        )
                        await get_event_bus().publish(event)
            
            return resurrected
            
        except Exception as e:
            logger.error(f"查找复活话题失败: {e}", exc_info=True)
            return []
    
    def get_all_active_topics(self, group_id: str = "") -> List[Dict]:
        """
        获取所有活跃话题
        
        Args:
            group_id: 群组ID
            
        Returns:
            List[Dict]: 话题信息列表
        """
        if group_id not in self.topics:
            return []
        
        return [topic.to_dict() for topic in self.topics[group_id].values()]
    
    def get_topic_statistics(self, group_id: str = "") -> Dict:
        """
        获取话题统计信息
        
        Args:
            group_id: 群组ID
            
        Returns:
            Dict: 统计信息
        """
        if group_id not in self.topics:
            return {
                "active_topics": 0,
                "archived_topics": 0,
                "total_messages": 0
            }
        
        active_topics = self.topics[group_id]
        archived_topics = self.topic_history.get(group_id, [])
        
        total_messages = sum(topic.message_count for topic in active_topics.values())
        
        return {
            "active_topics": len(active_topics),
            "archived_topics": len(archived_topics),
            "total_messages": total_messages,
            "avg_heat": sum(t.calculate_heat() for t in active_topics.values()) / len(active_topics) if active_topics else 0
        }
