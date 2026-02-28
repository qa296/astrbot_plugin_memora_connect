"""
用户画像系统
实现亲密度量化、兴趣偏好提取和禁忌词学习
"""

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from astrbot.api import logger


@dataclass
class IntimacyScore:
    """亲密度评分数据类"""

    user_id: str
    group_id: str = ""

    # 三维评分
    interaction_frequency: float = 0.0  # 互动频度 (0-1)
    interaction_depth: float = 0.0  # 互动深度 (0-1)
    emotional_value: float = 0.0  # 情感价值 (0-1)

    # 综合得分
    total_score: float = 0.0  # 0-100

    # 统计信息
    total_interactions: int = 0
    last_interaction: datetime = field(default_factory=datetime.now)
    first_interaction: datetime = field(default_factory=datetime.now)

    # 缓存时间
    cached_at: datetime = field(default_factory=datetime.now)

    def calculate_total_score(self) -> float:
        """
        计算综合亲密度得分

        Returns:
            float: 0-100的综合得分
        """
        # 加权平均
        weights = {"frequency": 0.4, "depth": 0.3, "emotional": 0.3}

        score = (
            self.interaction_frequency * weights["frequency"]
            + self.interaction_depth * weights["depth"]
            + self.emotional_value * weights["emotional"]
        ) * 100

        self.total_score = min(100.0, max(0.0, score))
        return self.total_score

    def is_cache_valid(self, cache_duration_seconds: int = 3600) -> bool:
        """
        检查缓存是否有效

        Args:
            cache_duration_seconds: 缓存有效期（秒）

        Returns:
            bool: 缓存是否有效
        """
        elapsed = (datetime.now() - self.cached_at).total_seconds()
        return elapsed < cache_duration_seconds

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "user_id": self.user_id,
            "group_id": self.group_id,
            "score": self.total_score,
            "sub_scores": {
                "interaction_frequency": self.interaction_frequency,
                "interaction_depth": self.interaction_depth,
                "emotional_value": self.emotional_value,
            },
            "statistics": {
                "total_interactions": self.total_interactions,
                "last_interaction": self.last_interaction.isoformat(),
                "first_interaction": self.first_interaction.isoformat(),
                "days_known": (datetime.now() - self.first_interaction).days,
            },
        }


@dataclass
class UserInterest:
    """用户兴趣数据类"""

    concept_id: str
    concept_name: str
    weight: float  # 兴趣权重 (0-1)
    interaction_count: int = 0
    last_interacted: datetime = field(default_factory=datetime.now)


class UserProfilingSystem:
    """
    用户画像系统
    管理用户的亲密度、兴趣偏好和禁忌词
    """

    def __init__(self, memory_system):
        """
        初始化用户画像系统

        Args:
            memory_system: 记忆系统实例
        """
        self.memory_system = memory_system

        # 亲密度缓存：{(user_id, group_id): IntimacyScore}
        self._intimacy_cache: dict[tuple[str, str], IntimacyScore] = {}

        # 兴趣偏好缓存：{(user_id, group_id): List[UserInterest]}
        self._interest_cache: dict[tuple[str, str], list[UserInterest]] = {}

        # 配置
        self.cache_duration = 3600  # 1小时缓存

        # 初始化数据库表
        self._init_database()


    def _init_database(self):
        """初始化数据库表"""
        try:
            db_path = self.memory_system.db_path
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # 创建用户兴趣表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_interests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    group_id TEXT DEFAULT '',
                    concept_id TEXT NOT NULL,
                    concept_name TEXT NOT NULL,
                    weight REAL NOT NULL,
                    interaction_count INTEGER DEFAULT 0,
                    last_interacted REAL NOT NULL,
                    UNIQUE(user_id, group_id, concept_id)
                )
            """)

            # 创建亲密度缓存表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS intimacy_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    group_id TEXT DEFAULT '',
                    interaction_frequency REAL DEFAULT 0.0,
                    interaction_depth REAL DEFAULT 0.0,
                    emotional_value REAL DEFAULT 0.0,
                    total_score REAL DEFAULT 0.0,
                    total_interactions INTEGER DEFAULT 0,
                    first_interaction REAL NOT NULL,
                    last_interaction REAL NOT NULL,
                    cached_at REAL NOT NULL,
                    UNIQUE(user_id, group_id)
                )
            """)

            conn.commit()
            conn.close()


        except Exception as e:
            logger.error(f"初始化用户画像数据库失败: {e}", exc_info=True)

    async def calculate_intimacy(
        self, user_id: str, group_id: str = "", force_recalculate: bool = False
    ) -> IntimacyScore:
        """
        计算用户亲密度

        Args:
            user_id: 用户ID
            group_id: 群组ID
            force_recalculate: 是否强制重新计算（忽略缓存）

        Returns:
            IntimacyScore: 亲密度评分对象
        """
        try:
            cache_key = (user_id, group_id)

            # 检查缓存
            if not force_recalculate and cache_key in self._intimacy_cache:
                cached_score = self._intimacy_cache[cache_key]
                if cached_score.is_cache_valid(self.cache_duration):
                    return cached_score

            # 重新计算
            score = IntimacyScore(user_id=user_id, group_id=group_id)

            # 从记忆图谱中统计
            memory_graph = self.memory_system.memory_graph

            # 1. 计算互动频度
            user_memories = [
                m
                for m in memory_graph.memories.values()
                if user_id in (m.participants or "")
                and (not group_id or getattr(m, "group_id", "") == group_id)
            ]

            if user_memories:
                score.total_interactions = len(user_memories)

                # 计算时间跨度
                timestamps = [m.created_at for m in user_memories]
                score.first_interaction = datetime.fromtimestamp(min(timestamps))
                score.last_interaction = datetime.fromtimestamp(max(timestamps))

                days_known = (datetime.now() - score.first_interaction).days + 1

                # 互动频度 = 总互动数 / 认识天数，归一化到0-1
                score.interaction_frequency = min(
                    1.0, score.total_interactions / (days_known * 5)
                )

                # 2. 计算互动深度
                # 深度 = 平均记忆详细程度
                total_detail_length = sum(len(m.details or "") for m in user_memories)
                avg_detail_length = total_detail_length / len(user_memories)
                score.interaction_depth = min(1.0, avg_detail_length / 100)

                # 3. 计算情感价值
                # 基于印象系统的好感度
                impression = self.memory_system.get_person_impression_summary(
                    group_id, user_id
                )
                if impression and "score" in impression:
                    score.emotional_value = impression["score"]
                else:
                    # 默认中性
                    score.emotional_value = 0.5

            # 计算总分
            score.calculate_total_score()
            score.cached_at = datetime.now()

            # 更新缓存
            self._intimacy_cache[cache_key] = score

            # 持久化到数据库
            await self._save_intimacy_to_db(score)

            return score

        except Exception as e:
            logger.error(f"计算亲密度失败: {e}", exc_info=True)
            # 返回默认值
            return IntimacyScore(user_id=user_id, group_id=group_id)

    async def _save_intimacy_to_db(self, score: IntimacyScore):
        """保存亲密度到数据库"""
        try:
            db_path = self.memory_system.db_path
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT OR REPLACE INTO intimacy_cache 
                (user_id, group_id, interaction_frequency, interaction_depth, 
                 emotional_value, total_score, total_interactions, 
                 first_interaction, last_interaction, cached_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    score.user_id,
                    score.group_id,
                    score.interaction_frequency,
                    score.interaction_depth,
                    score.emotional_value,
                    score.total_score,
                    score.total_interactions,
                    score.first_interaction.timestamp(),
                    score.last_interaction.timestamp(),
                    score.cached_at.timestamp(),
                ),
            )

            conn.commit()
            conn.close()

        except Exception as e:
            logger.error(f"保存亲密度到数据库失败: {e}", exc_info=True)

    async def get_intimacy(self, user_id: str, group_id: str = "") -> dict:
        """
        获取用户亲密度（API接口）

        Args:
            user_id: 用户ID
            group_id: 群组ID

        Returns:
            Dict: {score: 0-100, sub_scores: {...}}
        """
        intimacy = await self.calculate_intimacy(user_id, group_id)
        return intimacy.to_dict()

    async def batch_get_intimacy(
        self, user_ids: list[str], group_id: str = ""
    ) -> list[dict]:
        """
        批量获取用户亲密度

        Args:
            user_ids: 用户ID列表
            group_id: 群组ID

        Returns:
            List[Dict]: 亲密度列表
        """
        results = []
        for user_id in user_ids:
            intimacy = await self.get_intimacy(user_id, group_id)
            results.append(intimacy)
        return results

    async def extract_user_interests(
        self, user_id: str, group_id: str = "", top_k: int = 5
    ) -> list[tuple[str, float]]:
        """
        提取用户兴趣偏好
        基于用户与概念节点的共现关系

        Args:
            user_id: 用户ID
            group_id: 群组ID
            top_k: 返回TOP K个兴趣

        Returns:
            List[Tuple[concept_name, weight]]: [(概念名, 权重分数)]
        """
        try:
            # 检查缓存
            cache_key = (user_id, group_id)
            if cache_key in self._interest_cache:
                cached_interests = self._interest_cache[cache_key]
                sorted_interests = sorted(
                    cached_interests, key=lambda x: x.weight, reverse=True
                )
                return [(i.concept_name, i.weight) for i in sorted_interests[:top_k]]

            # 从记忆图谱中统计
            memory_graph = self.memory_system.memory_graph

            # 统计用户参与的概念
            concept_counter = defaultdict(int)

            for memory in memory_graph.memories.values():
                # 检查群组和参与者
                if group_id and getattr(memory, "group_id", "") != group_id:
                    continue

                if user_id not in (memory.participants or ""):
                    continue

                # 统计概念
                concept_id = memory.concept_id
                if concept_id and concept_id in memory_graph.concepts:
                    concept_counter[concept_id] += 1

            if not concept_counter:
                return []

            # 计算权重
            total_interactions = sum(concept_counter.values())
            interests = []

            for concept_id, count in concept_counter.items():
                concept = memory_graph.concepts[concept_id]
                weight = count / total_interactions

                interest = UserInterest(
                    concept_id=concept_id,
                    concept_name=concept.name,
                    weight=weight,
                    interaction_count=count,
                    last_interacted=datetime.now(),
                )
                interests.append(interest)

            # 缓存
            self._interest_cache[cache_key] = interests

            # 持久化到数据库
            await self._save_interests_to_db(user_id, group_id, interests)

            # 排序并返回
            sorted_interests = sorted(interests, key=lambda x: x.weight, reverse=True)
            return [(i.concept_name, i.weight) for i in sorted_interests[:top_k]]

        except Exception as e:
            logger.error(f"提取用户兴趣失败: {e}", exc_info=True)
            return []

    async def _save_interests_to_db(
        self, user_id: str, group_id: str, interests: list[UserInterest]
    ):
        """保存兴趣到数据库"""
        try:
            db_path = self.memory_system.db_path
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # 先删除旧记录
            cursor.execute(
                "DELETE FROM user_interests WHERE user_id = ? AND group_id = ?",
                (user_id, group_id),
            )

            # 插入新记录
            for interest in interests:
                cursor.execute(
                    """
                    INSERT INTO user_interests 
                    (user_id, group_id, concept_id, concept_name, weight, 
                     interaction_count, last_interacted)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        user_id,
                        group_id,
                        interest.concept_id,
                        interest.concept_name,
                        interest.weight,
                        interest.interaction_count,
                        interest.last_interacted.timestamp(),
                    ),
                )

            conn.commit()
            conn.close()

        except Exception as e:
            logger.error(f"保存兴趣到数据库失败: {e}", exc_info=True)

    async def get_user_interests(self, user_id: str, group_id: str = "") -> list[dict]:
        """
        获取用户兴趣（API接口）

        Args:
            user_id: 用户ID
            group_id: 群组ID

        Returns:
            List[Dict]: TOP 5概念节点 + 权重分数
        """
        interests = await self.extract_user_interests(user_id, group_id, top_k=5)
        return [{"concept": name, "weight": weight} for name, weight in interests]

    async def add_taboo_word(
        self, user_id: str, word: str, reason: str = "", group_id: str = ""
    ):
        """
        添加禁忌词

        Args:
            user_id: 用户ID
            word: 禁忌词
            reason: 原因
            group_id: 群组ID
        """
        try:
            cache_key = (user_id, group_id)

            # 检查是否已存在
            if cache_key in self._taboo_words:
                for taboo in self._taboo_words[cache_key]:
                    if taboo.word == word:
                        logger.debug(f"禁忌词已存在: {word}")
                        return
            else:
                self._taboo_words[cache_key] = []

            # 创建禁忌词
            taboo = TabooWord(word=word, reason=reason)
            self._taboo_words[cache_key].append(taboo)

            # 保存到数据库
            db_path = self.memory_system.db_path
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT OR IGNORE INTO taboo_words 
                (user_id, group_id, word, reason, added_at, triggered_count)
                VALUES (?, ?, ?, ?, ?, 0)
            """,
                (user_id, group_id, word, reason, taboo.added_at.timestamp()),
            )

            conn.commit()
            conn.close()

            logger.info(f"添加禁忌词: {word}, 用户: {user_id}")

            # 发布事件
            from ..infrastructure.events import (
                MemoryEvent,
                MemoryEventType,
                get_event_bus,
            )

            event = MemoryEvent(
                event_type=MemoryEventType.TABOO_ADDED,
                group_id=group_id,
                user_id=user_id,
                data={"word": word, "reason": reason},
            )
            await get_event_bus().publish(event)

        except Exception as e:
            logger.error(f"添加禁忌词失败: {e}", exc_info=True)

    async def check_taboo(
        self, user_id: str, content: str, group_id: str = ""
    ) -> list[str]:
        """
        检查内容是否包含禁忌词

        Args:
            user_id: 用户ID
            content: 要检查的内容
            group_id: 群组ID

        Returns:
            List[str]: 触发的禁忌词列表
        """
        try:
            cache_key = (user_id, group_id)

            # 从缓存或数据库加载
            if cache_key not in self._taboo_words:
                await self._load_taboo_words(user_id, group_id)

            if cache_key not in self._taboo_words:
                return []

            triggered = []
            for taboo in self._taboo_words[cache_key]:
                if taboo.word in content:
                    triggered.append(taboo.word)
                    taboo.triggered_count += 1

                    # 更新数据库
                    await self._update_taboo_trigger_count(
                        user_id, group_id, taboo.word
                    )

                    # 发布事件
                    from ..infrastructure.events import (
                        MemoryEvent,
                        MemoryEventType,
                        get_event_bus,
                    )

                    event = MemoryEvent(
                        event_type=MemoryEventType.TABOO_DETECTED,
                        group_id=group_id,
                        user_id=user_id,
                        data={
                            "word": taboo.word,
                            "content": content[:50],  # 只记录前50字符
                        },
                    )
                    await get_event_bus().publish(event)

            return triggered

        except Exception as e:
            logger.error(f"检查禁忌词失败: {e}", exc_info=True)
            return []

    async def _load_taboo_words(self, user_id: str, group_id: str):
        """从数据库加载禁忌词"""
        try:
            db_path = self.memory_system.db_path
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT word, reason, added_at, triggered_count
                FROM taboo_words
                WHERE user_id = ? AND group_id = ?
            """,
                (user_id, group_id),
            )

            rows = cursor.fetchall()
            conn.close()

            cache_key = (user_id, group_id)
            self._taboo_words[cache_key] = []

            for row in rows:
                taboo = TabooWord(
                    word=row[0],
                    reason=row[1],
                    added_at=datetime.fromtimestamp(row[2]),
                    triggered_count=row[3],
                )
                self._taboo_words[cache_key].append(taboo)

        except Exception as e:
            logger.error(f"加载禁忌词失败: {e}", exc_info=True)

    async def _update_taboo_trigger_count(self, user_id: str, group_id: str, word: str):
        """更新禁忌词触发次数"""
        try:
            db_path = self.memory_system.db_path
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                UPDATE taboo_words
                SET triggered_count = triggered_count + 1
                WHERE user_id = ? AND group_id = ? AND word = ?
            """,
                (user_id, group_id, word),
            )

            conn.commit()
            conn.close()

        except Exception as e:
            logger.error(f"更新禁忌词触发次数失败: {e}", exc_info=True)

    async def learn_taboo_from_message(
        self, user_id: str, message: str, group_id: str = ""
    ):
        """
        从消息中自动学习禁忌词
        检测用户的反感表达

        Args:
            user_id: 用户ID
            message: 消息内容
            group_id: 群组ID
        """
        try:
            # 检测反感关键词
            rejection_patterns = [
                "别",
                "不要",
                "不想",
                "不喜欢",
                "讨厌",
                "反感",
                "别剧透",
                "不说",
                "不聊",
                "不谈",
                "停止",
            ]

            message_lower = message.lower()
            has_rejection = any(
                pattern in message_lower for pattern in rejection_patterns
            )

            if not has_rejection:
                return

            # 使用LLM提取被拒绝的主题
            llm_provider = await self.memory_system.get_llm_provider()
            if not llm_provider:
                return

            prompt = f"""从以下用户消息中提取用户不想讨论的话题或关键词（1-3个词）：
消息：{message}
话题："""

            try:
                response = await llm_provider.text_chat(prompt=prompt, context=[])
                topics = response.completion_text.strip()

                if topics and len(topics) > 0:
                    # 添加为禁忌词
                    for topic in topics.split(","):
                        topic = topic.strip()
                        if topic:
                            await self.add_taboo_word(
                                user_id=user_id,
                                word=topic,
                                reason=f"从消息中自动学习: {message[:30]}",
                                group_id=group_id,
                            )
                            logger.info(f"自动学习禁忌词: {topic}")

            except Exception as e:
                logger.debug(f"LLM提取禁忌词失败: {e}")

        except Exception as e:
            logger.error(f"自动学习禁忌词失败: {e}", exc_info=True)
