"""
时间维度记忆检索系统
实现历史今日检测和未闭合话题追踪
"""

import time
import sqlite3
import asyncio
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from astrbot.api import logger


@dataclass
class AnniversaryMemory:
    """历史今日记忆"""
    memory_id: str
    content: str
    event_description: str
    days_ago: int  # 多少天前
    original_date: datetime
    activation_count: int = 0


@dataclass
class OpenTopic:
    """未闭合话题"""
    topic_id: str
    question: str  # 问题内容
    asker_id: str  # 提问者ID
    asked_at: datetime
    context: str = ""  # 上下文
    group_id: str = ""


class TemporalMemorySystem:
    """
    时间维度记忆检索系统
    实现基于时间的特殊记忆检索功能
    """
    
    def __init__(self, memory_system):
        """
        初始化时间维度记忆系统
        
        Args:
            memory_system: 记忆系统实例
        """
        self.memory_system = memory_system
        
        # 未闭合话题存储：{group_id: List[OpenTopic]}
        self._open_topics: Dict[str, List[OpenTopic]] = {}
        
        # 历史今日缓存
        self._anniversary_cache: Dict[str, List[AnniversaryMemory]] = {}
        
        # 初始化数据库
        self._init_database()
        
        # 启动定时任务
        self._start_daily_scan_task()
        
        logger.info("时间维度记忆系统已初始化")
    
    def _init_database(self):
        """初始化数据库表"""
        try:
            db_path = self.memory_system.db_path
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # 创建未闭合话题表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS open_topics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic_id TEXT UNIQUE NOT NULL,
                    question TEXT NOT NULL,
                    asker_id TEXT NOT NULL,
                    asked_at REAL NOT NULL,
                    context TEXT DEFAULT '',
                    group_id TEXT DEFAULT '',
                    resolved INTEGER DEFAULT 0
                )
            """)
            
            # 创建历史今日触发记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS anniversary_triggers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    memory_id TEXT NOT NULL,
                    triggered_at REAL NOT NULL,
                    days_ago INTEGER NOT NULL,
                    group_id TEXT DEFAULT ''
                )
            """)
            
            conn.commit()
            conn.close()
            
            logger.info("时间维度记忆数据库表初始化完成")
            
        except Exception as e:
            logger.error(f"初始化时间维度记忆数据库失败: {e}", exc_info=True)
    
    def _start_daily_scan_task(self):
        """启动每日扫描任务"""
        async def daily_scan_loop():
            while True:
                try:
                    # 等待到凌晨
                    await self._wait_until_midnight()
                    
                    # 执行每日扫描
                    await self.daily_anniversary_scan()
                    
                except Exception as e:
                    logger.error(f"每日扫描任务异常: {e}", exc_info=True)
                    await asyncio.sleep(3600)  # 出错后等待1小时
        
        # 创建任务
        asyncio.create_task(daily_scan_loop())
        logger.info("每日扫描任务已启动")
    
    async def _wait_until_midnight(self):
        """等待到凌晨3点"""
        now = datetime.now()
        tomorrow = now + timedelta(days=1)
        midnight = tomorrow.replace(hour=3, minute=0, second=0, microsecond=0)
        seconds_until_midnight = (midnight - now).total_seconds()
        
        logger.info(f"等待 {seconds_until_midnight/3600:.1f} 小时后执行每日扫描")
        await asyncio.sleep(seconds_until_midnight)
    
    async def daily_anniversary_scan(self, group_id: str = ""):
        """
        每日历史今日扫描
        查找N天/月/年前的高激活记忆节点
        
        Args:
            group_id: 群组ID，空字符串表示扫描所有群组
        """
        try:
            logger.info("开始执行每日历史今日扫描")
            
            memory_graph = self.memory_system.memory_graph
            now = datetime.now()
            
            # 定义要检测的时间点（天数）
            check_points = [
                7,      # 1周前
                30,     # 1个月前
                100,    # 100天前
                365,    # 1年前
                730,    # 2年前
            ]
            
            anniversaries = []
            
            for memory in memory_graph.memories.values():
                # 群组过滤
                if group_id and getattr(memory, 'group_id', '') != group_id:
                    continue
                
                # 计算记忆的年龄（天数）
                memory_date = datetime.fromtimestamp(memory.created_at)
                days_ago = (now - memory_date).days
                
                # 检查是否匹配任何检查点
                for checkpoint in check_points:
                    # 允许1天的误差
                    if abs(days_ago - checkpoint) <= 1:
                        # 检查激活次数（高激活记忆）
                        if memory.access_count >= 3:  # 至少被访问3次
                            anniversary = AnniversaryMemory(
                                memory_id=memory.id,
                                content=memory.content,
                                event_description=self._generate_anniversary_description(
                                    memory, checkpoint
                                ),
                                days_ago=checkpoint,
                                original_date=memory_date,
                                activation_count=memory.access_count
                            )
                            anniversaries.append(anniversary)
                            
                            logger.info(f"发现历史今日记忆: {checkpoint}天前 - {memory.content[:50]}")
            
            # 保存到缓存
            cache_key = group_id or "default"
            self._anniversary_cache[cache_key] = anniversaries
            
            # 发布事件
            for anniversary in anniversaries:
                from .memory_events import MemoryEvent, MemoryEventType, get_event_bus
                event = MemoryEvent(
                    event_type=MemoryEventType.ANNIVERSARY_DETECTED,
                    group_id=group_id,
                    data={
                        "memory_id": anniversary.memory_id,
                        "event_description": anniversary.event_description,
                        "days_ago": anniversary.days_ago,
                        "content": anniversary.content
                    }
                )
                await get_event_bus().publish(event)
            
            # 记录到数据库
            await self._save_anniversary_triggers(anniversaries, group_id)
            
            logger.info(f"每日扫描完成，发现 {len(anniversaries)} 个历史今日记忆")
            
        except Exception as e:
            logger.error(f"每日历史今日扫描失败: {e}", exc_info=True)
    
    def _generate_anniversary_description(self, memory, days_ago: int) -> str:
        """
        生成历史今日描述
        
        Args:
            memory: 记忆对象
            days_ago: 多少天前
            
        Returns:
            str: 描述文本
        """
        if days_ago == 7:
            time_desc = "1周前"
        elif days_ago == 30:
            time_desc = "1个月前"
        elif days_ago == 100:
            time_desc = "100天前"
        elif days_ago == 365:
            time_desc = "1年前"
        elif days_ago == 730:
            time_desc = "2年前"
        else:
            time_desc = f"{days_ago}天前"
        
        return f"在{time_desc}的今天，{memory.content[:50]}"
    
    async def _save_anniversary_triggers(self, anniversaries: List[AnniversaryMemory], group_id: str):
        """保存历史今日触发记录"""
        try:
            db_path = self.memory_system.db_path
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            for anniversary in anniversaries:
                cursor.execute("""
                    INSERT INTO anniversary_triggers 
                    (memory_id, triggered_at, days_ago, group_id)
                    VALUES (?, ?, ?, ?)
                """, (
                    anniversary.memory_id,
                    time.time(),
                    anniversary.days_ago,
                    group_id
                ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"保存历史今日触发记录失败: {e}", exc_info=True)
    
    async def get_today_anniversaries(self, group_id: str = "") -> List[AnniversaryMemory]:
        """
        获取今日的历史今日记忆
        
        Args:
            group_id: 群组ID
            
        Returns:
            List[AnniversaryMemory]: 历史今日记忆列表
        """
        cache_key = group_id or "default"
        return self._anniversary_cache.get(cache_key, [])
    
    async def track_open_question(self, question: str, asker_id: str, 
                                  context: str = "", group_id: str = ""):
        """
        追踪未闭合的问题
        
        Args:
            question: 问题内容
            asker_id: 提问者ID
            context: 上下文
            group_id: 群组ID
        """
        try:
            # 检测是否是开放式问题
            if not self._is_open_question(question):
                return
            
            # 生成话题ID
            import hashlib
            topic_id = hashlib.md5(f"{question}_{asker_id}_{time.time()}".encode()).hexdigest()[:16]
            
            # 创建未闭合话题
            open_topic = OpenTopic(
                topic_id=topic_id,
                question=question,
                asker_id=asker_id,
                asked_at=datetime.now(),
                context=context,
                group_id=group_id
            )
            
            # 添加到缓存
            if group_id not in self._open_topics:
                self._open_topics[group_id] = []
            self._open_topics[group_id].append(open_topic)
            
            # 保存到数据库
            await self._save_open_topic(open_topic)
            
            logger.info(f"追踪到未闭合问题: {question[:50]}")
            
            # 发布事件
            from .memory_events import MemoryEvent, MemoryEventType, get_event_bus
            event = MemoryEvent(
                event_type=MemoryEventType.OPEN_TOPIC_FOUND,
                group_id=group_id,
                user_id=asker_id,
                data={
                    "topic_id": topic_id,
                    "question": question,
                    "context": context
                }
            )
            await get_event_bus().publish(event)
            
        except Exception as e:
            logger.error(f"追踪未闭合问题失败: {e}", exc_info=True)
    
    def _is_open_question(self, text: str) -> bool:
        """
        判断是否是开放式问题
        
        Args:
            text: 文本内容
            
        Returns:
            bool: 是否是开放式问题
        """
        # 检测问句标志
        question_markers = ["吗", "呢", "？", "?", "怎么", "为什么", "如何", "什么时候"]
        
        has_marker = any(marker in text for marker in question_markers)
        
        # 检测是否没有明确回答
        # 这里简化处理，实际可以用更复杂的NLP分析
        return has_marker
    
    async def _save_open_topic(self, topic: OpenTopic):
        """保存未闭合话题到数据库"""
        try:
            db_path = self.memory_system.db_path
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT OR IGNORE INTO open_topics 
                (topic_id, question, asker_id, asked_at, context, group_id, resolved)
                VALUES (?, ?, ?, ?, ?, ?, 0)
            """, (
                topic.topic_id,
                topic.question,
                topic.asker_id,
                topic.asked_at.timestamp(),
                topic.context,
                topic.group_id
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"保存未闭合话题失败: {e}", exc_info=True)
    
    async def get_open_topics(self, group_id: str = "", days: int = 7) -> List[Dict]:
        """
        获取未闭合话题列表
        
        Args:
            group_id: 群组ID
            days: 查询最近N天的话题
            
        Returns:
            List[Dict]: 未闭合话题列表
        """
        try:
            # 先从缓存加载
            if group_id not in self._open_topics:
                await self._load_open_topics(group_id)
            
            topics = self._open_topics.get(group_id, [])
            
            # 过滤时间范围
            cutoff_time = datetime.now() - timedelta(days=days)
            filtered_topics = [
                t for t in topics
                if t.asked_at >= cutoff_time
            ]
            
            # 转换为字典格式
            result = []
            for topic in filtered_topics:
                result.append({
                    "topic_id": topic.topic_id,
                    "question": topic.question,
                    "asker_id": topic.asker_id,
                    "asked_at": topic.asked_at.isoformat(),
                    "days_ago": (datetime.now() - topic.asked_at).days,
                    "context": topic.context
                })
            
            return result
            
        except Exception as e:
            logger.error(f"获取未闭合话题失败: {e}", exc_info=True)
            return []
    
    async def _load_open_topics(self, group_id: str):
        """从数据库加载未闭合话题"""
        try:
            db_path = self.memory_system.db_path
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT topic_id, question, asker_id, asked_at, context
                FROM open_topics
                WHERE group_id = ? AND resolved = 0
                ORDER BY asked_at DESC
                LIMIT 100
            """, (group_id,))
            
            rows = cursor.fetchall()
            conn.close()
            
            topics = []
            for row in rows:
                topic = OpenTopic(
                    topic_id=row[0],
                    question=row[1],
                    asker_id=row[2],
                    asked_at=datetime.fromtimestamp(row[3]),
                    context=row[4],
                    group_id=group_id
                )
                topics.append(topic)
            
            self._open_topics[group_id] = topics
            
        except Exception as e:
            logger.error(f"加载未闭合话题失败: {e}", exc_info=True)
    
    async def resolve_open_topic(self, topic_id: str, group_id: str = ""):
        """
        标记话题为已解决
        
        Args:
            topic_id: 话题ID
            group_id: 群组ID
        """
        try:
            # 从缓存中移除
            if group_id in self._open_topics:
                self._open_topics[group_id] = [
                    t for t in self._open_topics[group_id]
                    if t.topic_id != topic_id
                ]
            
            # 更新数据库
            db_path = self.memory_system.db_path
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE open_topics
                SET resolved = 1
                WHERE topic_id = ? AND group_id = ?
            """, (topic_id, group_id))
            
            conn.commit()
            conn.close()
            
            logger.info(f"话题已解决: {topic_id}")
            
        except Exception as e:
            logger.error(f"标记话题为已解决失败: {e}", exc_info=True)
    
    async def auto_detect_and_track_questions(self, message: str, sender_id: str, 
                                             group_id: str = ""):
        """
        自动检测并追踪消息中的开放式问题
        
        Args:
            message: 消息内容
            sender_id: 发送者ID
            group_id: 群组ID
        """
        # 分句
        sentences = []
        for sep in ["。", "！", "？", ".", "!", "?"]:
            if sep in message:
                sentences.extend(message.split(sep))
        
        if not sentences:
            sentences = [message]
        
        # 检查每个句子
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            
            if self._is_open_question(sentence):
                await self.track_open_question(
                    question=sentence,
                    asker_id=sender_id,
                    context=message,
                    group_id=group_id
                )
