"""
用户画像系统
基于 Element 图谱计算亲密度、兴趣偏好和禁忌词。
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
        """计算综合亲密度得分"""
        weights = {"frequency": 0.4, "depth": 0.3, "emotional": 0.3}
        score = (
            self.interaction_frequency * weights["frequency"]
            + self.interaction_depth * weights["depth"]
            + self.emotional_value * weights["emotional"]
        ) * 100
        self.total_score = min(100.0, max(0.0, score))
        return self.total_score

    def is_cache_valid(self, cache_duration_seconds: int = 3600) -> bool:
        """检查缓存是否有效"""
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

    element_id: str
    element_name: str
    category: str
    weight: float  # 兴趣权重 (0-1)
    interaction_count: int = 0
    access_count: int = 0
    last_interacted: datetime = field(default_factory=datetime.now)


@dataclass
class TabooWord:
    """禁忌词数据类"""

    word: str
    reason: str = ""
    added_at: datetime = field(default_factory=datetime.now)
    triggered_count: int = 0


class UserProfilingSystem:
    """
    用户画像系统
    管理用户的亲密度、兴趣偏好和禁忌词。
    兴趣和亲密度均从 Element 图谱实时计算，不再维护 user_interests/intimacy_cache 旧表。
    """

    def __init__(self, memory_system):
        self.memory_system = memory_system
        self._intimacy_cache: dict[tuple[str, str], IntimacyScore] = {}
        self._interest_cache: dict[tuple[str, str], list[UserInterest]] = {}
        self._taboo_words: dict[tuple[str, str], list[TabooWord]] = {}
        self.cache_duration = 3600  # 1小时缓存
        self._init_database()

    def _init_database(self):
        """仅初始化禁忌词表；兴趣和亲密度从 Element 图谱计算。"""
        try:
            db_path = self.memory_system.db_path
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS taboo_words (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    group_id TEXT DEFAULT '',
                    word TEXT NOT NULL,
                    reason TEXT DEFAULT '',
                    added_at REAL NOT NULL,
                    triggered_count INTEGER DEFAULT 0,
                    UNIQUE(user_id, group_id, word)
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"初始化用户画像数据库失败: {e}", exc_info=True)

    def _is_same_person(self, element_name: str, user_id: str) -> bool:
        """宽松匹配用户ID和 person Element 名称。"""
        if not element_name or not user_id:
            return False
        element_name = str(element_name).strip()
        user_id = str(user_id).strip()
        return element_name == user_id or element_name in user_id or user_id in element_name

    def _get_user_memories(self, user_id: str, group_id: str = "") -> list:
        """从 Element 图谱中获取与用户 person Element 相关的记忆。"""
        memory_graph = self.memory_system.memory_graph
        user_memories = []
        seen = set()

        for elem in getattr(memory_graph, "elements", {}).values():
            if elem.category != "person":
                continue
            if group_id and elem.group_id != group_id:
                continue
            if not self._is_same_person(elem.name, user_id):
                continue

            for memory in memory_graph.get_element_memories(elem.id):
                if group_id and getattr(memory, "group_id", "") != group_id:
                    continue
                if memory.id not in seen:
                    seen.add(memory.id)
                    user_memories.append(memory)

        return user_memories

    async def calculate_intimacy(
        self, user_id: str, group_id: str = "", force_recalculate: bool = False
    ) -> IntimacyScore:
        """计算用户亲密度。"""
        try:
            cache_key = (user_id, group_id)
            if not force_recalculate and cache_key in self._intimacy_cache:
                cached_score = self._intimacy_cache[cache_key]
                if cached_score.is_cache_valid(self.cache_duration):
                    return cached_score

            score = IntimacyScore(user_id=user_id, group_id=group_id)
            user_memories = self._get_user_memories(user_id, group_id)

            if user_memories:
                score.total_interactions = len(user_memories)
                timestamps = [m.created_at for m in user_memories if m.created_at]
                if timestamps:
                    score.first_interaction = datetime.fromtimestamp(min(timestamps))
                    score.last_interaction = datetime.fromtimestamp(max(timestamps))

                days_known = max(1, (datetime.now() - score.first_interaction).days + 1)
                score.interaction_frequency = min(
                    1.0, score.total_interactions / (days_known * 5)
                )

                total_detail_length = sum(len(getattr(m, "details", "") or "") for m in user_memories)
                avg_detail_length = total_detail_length / len(user_memories)
                score.interaction_depth = min(1.0, avg_detail_length / 100)

                impression = self.memory_system.get_person_impression_summary(
                    group_id, user_id
                )
                if impression and "score" in impression:
                    score.emotional_value = float(impression["score"])
                else:
                    score.emotional_value = 0.5

            score.calculate_total_score()
            score.cached_at = datetime.now()
            self._intimacy_cache[cache_key] = score
            return score

        except Exception as e:
            logger.error(f"计算亲密度失败: {e}", exc_info=True)
            return IntimacyScore(user_id=user_id, group_id=group_id)

    async def _save_intimacy_to_db(self, score: IntimacyScore):
        """兼容旧测试/调用：亲密度不再单独落库。"""
        return None

    async def get_intimacy(self, user_id: str, group_id: str = "") -> dict:
        """获取用户亲密度（API接口）。"""
        intimacy = await self.calculate_intimacy(user_id, group_id)
        return intimacy.to_dict()

    async def batch_get_intimacy(
        self, user_ids: list[str], group_id: str = ""
    ) -> list[dict]:
        """批量获取用户亲密度。"""
        results = []
        for user_id in user_ids:
            intimacy = await self.get_intimacy(user_id, group_id)
            results.append(intimacy)
        return results

    async def extract_user_interests(
        self, user_id: str, group_id: str = "", top_k: int = 5
    ) -> list[tuple[str, float]]:
        """从 Element 访问频次和用户相关记忆共现中提取兴趣偏好。"""
        try:
            cache_key = (user_id, group_id)
            if cache_key in self._interest_cache:
                cached_interests = self._interest_cache[cache_key]
                sorted_interests = sorted(
                    cached_interests, key=lambda x: x.weight, reverse=True
                )
                return [
                    (f"{i.element_name}({i.category})", i.weight)
                    for i in sorted_interests[:top_k]
                ]

            memory_graph = self.memory_system.memory_graph
            user_memories = self._get_user_memories(user_id, group_id)
            if not user_memories:
                return []

            counts: dict[tuple[str, str, str], int] = defaultdict(int)
            last_seen: dict[str, float] = {}
            user_memory_ids = {m.id for m in user_memories}

            for memory in user_memories:
                for elem, role in memory_graph.get_memory_elements(memory.id):
                    if elem.category == "person" and self._is_same_person(elem.name, user_id):
                        continue
                    if elem.category not in ("object", "action", "trait", "place"):
                        continue
                    if role in ("subject", "impression"):
                        continue
                    key = (elem.id, elem.name, elem.category)
                    # 共现次数 + Element 自身 access_count 共同决定兴趣权重
                    counts[key] += 1 + int(getattr(elem, "access_count", 0) or 0)
                    last_seen[elem.id] = max(
                        last_seen.get(elem.id, 0), getattr(memory, "last_accessed", 0) or 0
                    )

            # 如果用户记忆没有可用兴趣元素，降级到全局高访问 Element
            if not counts:
                for elem in getattr(memory_graph, "elements", {}).values():
                    if group_id and elem.group_id != group_id:
                        continue
                    if elem.category in ("object", "action", "trait", "place"):
                        counts[(elem.id, elem.name, elem.category)] += int(
                            getattr(elem, "access_count", 0) or 0
                        )

            total = sum(counts.values())
            if total <= 0:
                total = len(user_memory_ids) or 1

            interests = []
            for (elem_id, elem_name, category), count in counts.items():
                elem = memory_graph.elements.get(elem_id)
                weight = min(1.0, count / total)
                interests.append(
                    UserInterest(
                        element_id=elem_id,
                        element_name=elem_name,
                        category=category,
                        weight=weight,
                        interaction_count=count,
                        access_count=int(getattr(elem, "access_count", 0) or 0),
                        last_interacted=datetime.fromtimestamp(last_seen.get(elem_id, 0))
                        if last_seen.get(elem_id)
                        else datetime.now(),
                    )
                )

            self._interest_cache[cache_key] = interests
            await self._save_interests_to_db(user_id, group_id, interests)

            sorted_interests = sorted(interests, key=lambda x: x.weight, reverse=True)
            return [
                (f"{i.element_name}({i.category})", i.weight)
                for i in sorted_interests[:top_k]
            ]

        except Exception as e:
            logger.error(f"提取用户兴趣失败: {e}", exc_info=True)
            return []

    async def _save_interests_to_db(
        self, user_id: str, group_id: str, interests: list[UserInterest]
    ):
        """兼容旧测试/调用：兴趣不再单独落库。"""
        return None

    async def get_user_interests(self, user_id: str, group_id: str = "") -> list[dict]:
        """获取用户兴趣（API接口）。"""
        interests = await self.extract_user_interests(user_id, group_id, top_k=5)
        return [{"element": name, "weight": weight} for name, weight in interests]

    async def add_taboo_word(
        self, user_id: str, word: str, reason: str = "", group_id: str = ""
    ):
        """添加禁忌词。"""
        try:
            cache_key = (user_id, group_id)
            if cache_key not in self._taboo_words:
                self._taboo_words[cache_key] = []

            for taboo in self._taboo_words[cache_key]:
                if taboo.word == word:
                    logger.debug(f"禁忌词已存在: {word}")
                    return

            taboo = TabooWord(word=word, reason=reason)
            self._taboo_words[cache_key].append(taboo)

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
        """检查内容是否包含禁忌词。"""
        try:
            cache_key = (user_id, group_id)
            if cache_key not in self._taboo_words:
                await self._load_taboo_words(user_id, group_id)

            if cache_key not in self._taboo_words:
                return []

            triggered = []
            for taboo in self._taboo_words[cache_key]:
                if taboo.word in content:
                    triggered.append(taboo.word)
                    taboo.triggered_count += 1
                    await self._update_taboo_trigger_count(
                        user_id, group_id, taboo.word
                    )

                    from ..infrastructure.events import (
                        MemoryEvent,
                        MemoryEventType,
                        get_event_bus,
                    )

                    event = MemoryEvent(
                        event_type=MemoryEventType.TABOO_DETECTED,
                        group_id=group_id,
                        user_id=user_id,
                        data={"word": taboo.word, "content": content[:50]},
                    )
                    await get_event_bus().publish(event)

            return triggered

        except Exception as e:
            logger.error(f"检查禁忌词失败: {e}", exc_info=True)
            return []

    async def _load_taboo_words(self, user_id: str, group_id: str):
        """从数据库加载禁忌词。"""
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
        """更新禁忌词触发次数。"""
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
        """从消息中自动学习禁忌词。"""
        try:
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
            if not any(pattern in message_lower for pattern in rejection_patterns):
                return

            llm_provider = await self.memory_system.get_llm_provider()
            if not llm_provider:
                return

            prompt = f"""从以下用户消息中提取用户不想讨论的话题或关键词（1-3个词）：
消息：{message}
话题："""

            try:
                response = await llm_provider.text_chat(prompt=prompt, context=[])
                topics = response.completion_text.strip()
                if topics:
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
