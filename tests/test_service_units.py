import asyncio
import importlib.util
import logging
import os
import sqlite3
import sys
import time
import types
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _ensure_astrbot_logger():
    if "astrbot.api" in sys.modules:
        return
    astrbot_module = types.ModuleType("astrbot")
    api_module = types.ModuleType("astrbot.api")
    api_module.logger = logging.getLogger("tests.astrbot")
    sys.modules["astrbot"] = astrbot_module
    sys.modules["astrbot.api"] = api_module


def _ensure_package(name: str, path: Path):
    if name in sys.modules:
        return sys.modules[name]
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules[name] = module
    parent_name, _, child_name = name.rpartition(".")
    if parent_name:
        parent = sys.modules[parent_name]
        setattr(parent, child_name, module)
    return module


def _load_module(module_name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(module_name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    parent_name, _, child_name = module_name.rpartition(".")
    if parent_name and parent_name in sys.modules:
        setattr(sys.modules[parent_name], child_name, module)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


_ensure_astrbot_logger()
_ensure_package("plugin", ROOT)
_ensure_package("plugin.api", ROOT / "api")
_ensure_package("plugin.core", ROOT / "core")
_ensure_package("plugin.infrastructure", ROOT / "infrastructure")
_ensure_package("plugin.intelligence", ROOT / "intelligence")
_ensure_package("plugin.memory", ROOT / "memory")

models = _load_module("plugin.core.models", "core/models.py")
events = _load_module("plugin.infrastructure.events", "infrastructure/events.py")
resources_module = _load_module("plugin.infrastructure.resources", "infrastructure/resources.py")
database_module = _load_module("plugin.infrastructure.database", "infrastructure/database.py")
memory_graph_module = _load_module("plugin.core.memory_graph", "core/memory_graph.py")
gateway_module = _load_module("plugin.api.gateway", "api/gateway.py")
topics_module = _load_module("plugin.intelligence.topics", "intelligence/topics.py")
topic_analyzer_module = _load_module(
    "plugin.intelligence.topic_analyzer", "intelligence/topic_analyzer.py"
)
extractor_module = _load_module("plugin.memory.extractor", "memory/extractor.py")
temporal_module = _load_module("plugin.intelligence.temporal", "intelligence/temporal.py")
profiling_module = _load_module("plugin.intelligence.profiling", "intelligence/profiling.py")
display_module = _load_module("plugin.memory.memory_display", "memory/memory_display.py")
recall_module = _load_module("plugin.memory.memory_recall", "memory/memory_recall.py")

MemoryGraph = memory_graph_module.MemoryGraph
Memory = models.Memory
Element = models.Element


class _FakeResponse:
    def __init__(self, completion_text: str):
        self.completion_text = completion_text


class _FakeProvider:
    def __init__(self, completion_text: str = "", fail: Exception | None = None):
        self.completion_text = completion_text
        self.fail = fail
        self.calls = []

    async def text_chat(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise self.fail
        return _FakeResponse(self.completion_text)


class _FakeExtractorMemorySystem:
    def __init__(self, provider=None):
        self.provider = provider

    async def get_llm_provider(self):
        return self.provider


def test_batch_memory_extractor_parses_formats_and_falls_back():
    extractor = extractor_module.BatchMemoryExtractor(_FakeExtractorMemorySystem())

    assert extractor._safe_load_json('{"a": 1}') == {"a": 1}
    assert extractor._safe_load_json('prefix {"a": 2} suffix') == {"a": 2}
    assert extractor._safe_load_json("no json here") is None

    history = [
        {
            "role": "assistant",
            "content": "I can help.",
            "timestamp": 0,
            "sender_name": "bot",
        },
        {
            "role": "user",
            "content": "Thanks",
            "timestamp": "later",
            "sender_name": "Alice",
        },
    ]
    formatted = extractor._format_conversation_history(history)
    assert "[Bot]: I can help." in formatted
    assert "Alice: Thanks" in formatted

    parsed = extractor._parse_batch_response(
        """
        noise {
          "memories": [
            {
              "theme": "work,project!",
              "content": "finished demo",
              "details": 123,
              "participants": ["Alice"],
              "location": null,
              "emotion": "happy",
              "tags": "work",
              "confidence": "1.2",
              "memory_type": "custom"
            },
            {"theme": "low", "content": "skip", "confidence": 0.2},
            "bad"
          ]
        }
        """
    )
    assert parsed == [
        {
            "theme": "work,project",
            "content": "finished demo",
            "details": "123",
            "participants": "['Alice']",
            "location": "None",
            "emotion": "happy",
            "tags": "work",
            "confidence": 1.0,
            "memory_type": "normal",
        }
    ]

    fallback = asyncio.run(
        extractor._fallback_extraction(
            [
                {"content": "\u9879\u76ee\u8ba1\u5212 \u9879\u76ee\u8ba1\u5212"},
                {"content": "\u9700\u6c42\u8ba8\u8bba"},
            ]
        )
    )
    assert fallback
    assert fallback[0]["confidence"] == 0.5


def test_batch_memory_extractor_uses_provider_and_filters_impressions():
    provider = _FakeProvider(
        """
        {"impressions": [
          {
            "person_name": "Alice",
            "summary": "Helpful",
            "score": "0.8",
            "details": 5,
            "confidence": "0.9"
          },
          {"person_name": "", "summary": "skip"}
        ]}
        """
    )
    extractor = extractor_module.BatchMemoryExtractor(
        _FakeExtractorMemorySystem(provider)
    )

    result = asyncio.run(
        extractor.extract_impressions_from_conversation(
            [{"content": "Alice helped", "sender_name": "Bob"}], "group-a"
        )
    )

    assert result == [
        {
            "person_name": "Alice",
            "summary": "Helpful",
            "score": 0.8,
            "details": "5",
            "confidence": 0.9,
        }
    ]
    assert provider.calls

    no_provider = extractor_module.BatchMemoryExtractor(_FakeExtractorMemorySystem())
    assert (
        asyncio.run(
            no_provider.extract_impressions_from_conversation(
                [{"content": "Alice helped"}], "group-a"
            )
        )
        == []
    )
    assert (
        asyncio.run(no_provider.extract_memories_and_themes([]))
        == []
    )


class _FakeTopicMemorySystem:
    async def get_llm_provider(self):
        return None

    async def get_embedding_provider(self):
        return None


async def _exercise_topic_engine():
    cluster = topics_module.TopicCluster(topic_id="topic-1", keywords={"alpha"})
    assert cluster.calculate_depth() == 0
    now = time.time()
    cluster.add_message("alpha one", "u1", timestamp=now)
    cluster.add_message("alpha two", "u2", timestamp=now)

    assert cluster.calculate_heat() > 0
    assert cluster.calculate_depth() == 1
    as_dict = cluster.to_dict()
    assert as_dict["topic_id"] == "topic-1"
    assert as_dict["message_count"] == 2

    engine = topics_module.TopicEngine(
        _FakeTopicMemorySystem(), similarity_threshold=0.5
    )

    async def keyword_words(message):
        return set(message.split())

    engine._extract_keywords = keyword_words

    await engine.add_message_to_topic("alpha beta", "u1", "group-a")
    assert len(engine.topics["group-a"]) == 1
    topic = next(iter(engine.topics["group-a"].values()))
    created_id = topic.topic_id

    await engine.add_message_to_topic("alpha beta gamma", "u2", "group-a")
    assert engine.topics["group-a"][created_id].message_count == 2
    assert await engine._find_matching_topic({"alpha"}, "missing") is None

    active_timeline = await engine.get_topic_timeline(created_id, "group-a")
    assert active_timeline["status"] == "active"

    relevance = await engine.get_topic_relevance("alpha", "group-a")
    assert relevance and relevance[0][0] == created_id

    merge_a = topics_module.TopicCluster("merge-a", {"shared", "left"})
    merge_b = topics_module.TopicCluster("merge-b", {"shared", "right"})
    merge_a.add_message("left", "u1")
    merge_b.add_message("right", "u2")
    engine.similarity_threshold = 0.3
    engine.topics["merge-group"] = {
        merge_a.topic_id: merge_a,
        merge_b.topic_id: merge_b,
    }
    await engine._try_merge_topics("merge-group")
    assert list(engine.topics["merge-group"]) == ["merge-a"]
    assert engine.topics["merge-group"]["merge-a"].message_count == 2

    expired = topics_module.TopicCluster("expired", {"old"})
    expired.last_active = datetime.now() - timedelta(hours=2)
    engine.topic_expire_hours = 1
    engine.topics["old-group"] = {"expired": expired}
    await engine._cleanup_expired_topics("old-group")
    assert "expired" not in engine.topics["old-group"]
    assert engine.topic_history["old-group"][0].topic_id == "expired"

    expired.last_active = datetime.now() - timedelta(days=10)
    engine.topic_history["old-group"] = [expired]
    resurrected = await engine.find_resurrected_topics(
        "old", "old-group", silence_days=7
    )
    assert resurrected == ["expired"]

    expired_timeline = await engine.get_topic_timeline("expired", "old-group")
    assert expired_timeline["status"] == "expired"
    assert await engine.get_topic_timeline("missing", "old-group") is None

    assert engine.get_all_active_topics("missing") == []
    stats = engine.get_topic_statistics("group-a")
    assert stats["active_topics"] == 1
    assert stats["total_messages"] == 2
    assert engine.get_topic_statistics("missing") == {
        "active_topics": 0,
        "archived_topics": 0,
        "total_messages": 0,
    }


def test_topic_cluster_and_engine_lifecycle():
    asyncio.run(_exercise_topic_engine())


class _FakeTopicAnalyzer:
    def __init__(self):
        self.calls = 0

    def get_active_sessions(self, group_id):
        self.calls += 1
        return [
            {
                "session_id": "s1",
                "topic": "alpha",
                "keywords": ["alpha", "beta"],
                "message_count": 3,
            },
            {
                "session_id": "s2",
                "topic": "gamma",
                "keywords": ["gamma"],
                "message_count": 1,
            },
        ]


class _FakeUserProfiling:
    def __init__(self):
        self.intimacy_calls = 0

    async def get_intimacy(self, user_id, group_id):
        self.intimacy_calls += 1
        return {"user_id": user_id, "score": 88, "group_id": group_id}

    async def get_user_interests(self, user_id, group_id):
        return [{"concept": "shared", "weight": 0.7}]

    async def extract_user_interests(self, user_id, group_id, top_k=10):
        return [("shared", 0.6), (f"{user_id}-only", 0.2)]


class _FakeTemporalMemory:
    async def get_open_topics(self, group_id, days):
        return [{"topic_id": "open-1", "question": "How?", "days": days}]

    async def get_today_anniversaries(self, group_id):
        return [
            temporal_module.AnniversaryMemory(
                memory_id="memory_1",
                content="anniversary",
                event_description="one week ago",
                days_ago=7,
                original_date=datetime(2025, 1, 1),
            )
        ]


class _FakeGatewayMemorySystem:
    def __init__(self):
        self.memory_graph = MemoryGraph()
        person = self.memory_graph.add_element(
            "Alice", "person", "group-a", element_id="elem_alice"
        )
        memory_id = self.memory_graph.add_memory(
            "important",
            memory_id="memory_important",
            created_at=100,
            access_count=10,
            group_id="group-a",
        )
        self.memory_graph.link_memory(person, memory_id, "subject")
        self.memory_graph.add_memory(
            "less important",
            memory_id="memory_less",
            created_at=200,
            access_count=1,
            group_id="other",
        )


async def _exercise_gateway():
    topic_analyzer = _FakeTopicAnalyzer()
    profiling = _FakeUserProfiling()
    gateway = gateway_module.MemoryAPIGateway(
        _FakeGatewayMemorySystem(),
        topic_analyzer,
        profiling,
        _FakeTemporalMemory(),
    )

    relevance = await gateway.get_topic_relevance("message", "group-a", max_results=1)
    assert relevance.success is True
    assert relevance.cached is False
    assert relevance.data == [
        {
            "session_id": "s1",
            "topic": "alpha",
            "keywords": ["alpha", "beta"],
            "message_count": 3,
        }
    ]

    cached_relevance = await gateway.get_topic_relevance("message", "group-a")
    assert cached_relevance.cached is True
    assert topic_analyzer.calls == 1

    intimacy = await gateway.get_intimacy("u1", "group-a")
    assert intimacy.data["score"] == 88
    cached_intimacy = await gateway.get_intimacy("u1", "group-a")
    assert cached_intimacy.cached is True
    assert profiling.intimacy_calls == 1

    batch = await gateway.batch_get_intimacy(["u1", "u2"], "group-a")
    assert [item["user_id"] for item in batch.data] == ["u1", "u2"]

    interests = await gateway.get_user_interests("u1", "group-a")
    assert interests.data == [{"concept": "shared", "weight": 0.7}]
    assert (await gateway.get_user_interests("u1", "group-a")).cached is True

    open_topics = await gateway.get_open_topics("group-a", days=3)
    assert open_topics.data[0]["days"] == 3

    anniversaries = await gateway.get_today_anniversaries("group-a")
    assert anniversaries.data[0]["original_date"] == "2025-01-01T00:00:00"

    connection = await gateway.find_connection("u1", "u2", "group-a")
    assert connection.data["common_topics"] == ["shared"]
    assert connection.data["connection_strength"] == 0.6

    ranking = await gateway.get_memory_importance_ranking("group-a", top_k=5)
    assert ranking.data[0]["memory_id"] == "memory_important"
    assert ranking.data[0]["elements"] == [{"name": "Alice", "category": "person"}]

    health = await gateway.health_check()
    assert health["healthy"] is True
    assert gateway.is_healthy() is True
    assert gateway.get_performance_stats()["total_requests"] >= 8

    gateway.clear_cache()
    assert gateway._l1_cache == {}


def test_api_gateway_formats_caches_and_ranks_results():
    asyncio.run(_exercise_gateway())


class _FakeTemporalMemorySystem:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.memory_graph = MemoryGraph()


class _SharedSqliteConnection:
    def __init__(self, connection):
        self.connection = connection

    def cursor(self):
        return self.connection.cursor()

    def commit(self):
        self.connection.commit()

    def close(self):
        pass


async def _exercise_temporal_system():
    original_connect = sqlite3.connect
    shared_connection = original_connect(":memory:")

    def connect_shared(*args, **kwargs):
        return _SharedSqliteConnection(shared_connection)

    temporal_module.sqlite3.connect = connect_shared
    memory_system = _FakeTemporalMemorySystem()
    recent = time.time() - 7 * 24 * 3600
    try:
        memory_system.memory_graph.add_memory(
            "seven day memory",
            memory_id="memory_7",
            created_at=recent,
            access_count=3,
            group_id="group-a",
        )
        memory_system.memory_graph.add_memory(
            "ignored low access",
            memory_id="memory_low",
            created_at=recent,
            access_count=1,
            group_id="group-a",
        )

        temporal = temporal_module.TemporalMemorySystem.__new__(
            temporal_module.TemporalMemorySystem
        )
        temporal.memory_system = memory_system
        temporal._open_topics = {}
        temporal._anniversary_cache = {}
        temporal._init_database()

        assert await temporal.get_today_anniversaries("group-a") == []
        await temporal.daily_anniversary_scan("group-a")
        anniversaries = await temporal.get_today_anniversaries("group-a")
        assert [a.memory_id for a in anniversaries] == ["memory_7"]
        assert "seven day memory" in anniversaries[0].event_description

        count = shared_connection.execute(
            "select count(*) from anniversary_triggers"
        ).fetchone()[0]
        assert count == 1

        assert temporal._is_open_question("How does this work?") is True
        assert temporal._is_open_question("This is a statement") is False

        await temporal.track_open_question(
            "How does this work?", "user-a", context="ctx", group_id="group-a"
        )
        topics = await temporal.get_open_topics("group-a", days=1)
        assert len(topics) == 1
        assert topics[0]["question"] == "How does this work?"

        await temporal.resolve_open_topic(topics[0]["topic_id"], "group-a")
        assert await temporal.get_open_topics("group-a", days=1) == []

        await temporal.track_open_question(
            "Not a question", "user-a", context="ctx", group_id="group-a"
        )
        assert await temporal.get_open_topics("group-a", days=1) == []
    finally:
        temporal_module.sqlite3.connect = original_connect
        shared_connection.close()


def test_temporal_memory_tracks_open_topics_and_anniversaries():
    asyncio.run(_exercise_temporal_system())


def test_enhanced_memory_display_formats_details_lists_search_and_stats():
    graph = MemoryGraph()
    element_id = graph.add_element("Alice", "person", "group-a", element_id="elem_a")
    memory_id = graph.add_memory(
        "Alice likes tea",
        memory_id="memory_tea",
        details="green tea",
        emotion="calm",
        created_at=100,
        last_accessed=200,
        access_count=2,
        strength=0.6,
        group_id="group-a",
    )
    graph.link_memory(element_id, memory_id, "subject")

    memory_system = types.SimpleNamespace(memory_graph=graph)
    display = display_module.EnhancedMemoryDisplay(memory_system)
    memory = graph.memories[memory_id]

    first, names, details = display._get_element_info(memory)
    assert first == "Alice"
    assert names == ["Alice(person)"]
    assert details == ["Alice[subject]"]

    detailed = display.format_detailed_memory(memory)
    assert "Alice likes tea" in detailed
    assert "green tea" in detailed
    assert "Alice(person)" in detailed

    memory_list = display.format_memory_list([memory])
    assert "Alice likes tea" in memory_list
    assert "0.60" in memory_list
    assert "Alice likes tea" in display.format_memory_search_result([memory], "tea")
    assert "memory_tea" in display._create_memory_card(memory, "Alice", names, 1)
    assert display.format_memory_list([]) == "没有找到相关记忆"

    stats = display.format_memory_statistics()
    assert "memory_tea" not in stats
    assert "1" in stats

    empty_display = display_module.EnhancedMemoryDisplay(
        types.SimpleNamespace(memory_graph=MemoryGraph())
    )
    assert empty_display.format_memory_statistics() == "记忆库为空"


class _FakeEmbeddingCache:
    def __init__(self):
        self.scheduled = []

    async def get_embedding(self, memory_id, content, group_id=""):
        if memory_id == "memory_alice":
            return [1.0, 0.0]
        if memory_id == "memory_tea":
            return [0.0, 1.0]
        return None

    async def _get_cached_embedding(self, memory_id, group_id=""):
        return memory_id == "memory_alice"

    async def schedule_precompute_task(self, memory_ids, priority=1):
        self.scheduled.append((list(memory_ids), priority))

    async def get_cache_stats(self):
        return {"cached_memories": 1, "cache_hit_rate": 50.0}


class _FakeRecallMemorySystem:
    def __init__(self, embedding=False):
        self.memory_graph = MemoryGraph()
        self.memory_config = {
            "recall_mode": "embedding" if embedding else "keyword",
            "enable_associative_recall": True,
            "max_injected_memories": 5,
            "memory_injection_threshold": 0.05,
        }
        self.embedding_cache = _FakeEmbeddingCache() if embedding else None
        self._build_graph()

    def _build_graph(self):
        now = time.time()
        alice = self.memory_graph.add_element(
            "Alice", "person", "group-a", element_id="elem_alice"
        )
        tea = self.memory_graph.add_element(
            "tea", "object", "group-a", element_id="elem_tea"
        )
        other = self.memory_graph.add_element(
            "other", "trait", "other", element_id="elem_other"
        )
        m1 = self.memory_graph.add_memory(
            "Alice drinks green tea",
            memory_id="memory_alice",
            details="sencha",
            created_at=now - 3600,
            last_accessed=now - 60,
            access_count=4,
            strength=0.9,
            group_id="group-a",
        )
        m2 = self.memory_graph.add_memory(
            "Tea store sells cups",
            memory_id="memory_tea",
            details="cups and leaves",
            created_at=now - 1800,
            last_accessed=now - 120,
            access_count=2,
            strength=0.6,
            group_id="group-a",
        )
        m3 = self.memory_graph.add_memory(
            "Other group memory",
            memory_id="memory_other",
            created_at=now - 100,
            last_accessed=now - 10,
            access_count=9,
            strength=1.0,
            group_id="other",
        )
        self.memory_graph.link_memory(alice, m1, "subject")
        self.memory_graph.link_memory(tea, m1, "object")
        self.memory_graph.link_memory(tea, m2, "subject")
        self.memory_graph.link_memory(other, m3, "subject")
        self.memory_graph.add_connection(alice, tea, strength=0.8)
        self.memory_graph.memories[m1].participants = ["bot"]
        self.memory_graph.memories[m2].participants = []

    async def get_embedding_provider(self):
        return object()

    async def get_embedding(self, text):
        return [1.0, 0.0]


async def _exercise_recall_system():
    recall = recall_module.EnhancedMemoryRecall(_FakeRecallMemorySystem())

    assert recall._cosine_similarity([1, 0], [1, 0]) == 1.0
    assert recall._cosine_similarity([1, 0], [0, 0]) == 0.0
    assert recall._extract_keywords("\u9879\u76ee\u8ba1\u5212\u8ba8\u8bba")
    recall._extract_keywords = lambda text: ["alice", "tea"]

    keyword = await recall._keyword_recall(
        "Alice green tea", "group-a", keywords=["alice", "tea"]
    )
    assert keyword[0].memory == "Alice drinks green tea"
    assert keyword[0].metadata["matched_keywords"] == ["alice", "tea"]

    temporal = await recall._temporal_recall("tea", "group-a")
    assert {r.memory for r in temporal} == {
        "Alice drinks green tea",
        "Tea store sells cups",
    }

    strength = await recall._strength_based_recall("tea", "group-a")
    assert strength[0].memory == "Alice drinks green tea"

    associative = await recall._associative_recall("Alice", "group-a")
    assert {r.memory for r in associative} >= {
        "Alice drinks green tea",
        "Tea store sells cups",
    }

    combined = await recall.recall_all_relevant_memories("Alice tea", group_id="group-a")
    assert combined
    assert combined[0].relevance_score >= combined[-1].relevance_score

    duplicate = recall._deduplicate_and_rank(
        [
            recall_module.MemoryRecallResult("same", 0.1, "keyword", "a", {}),
            recall_module.MemoryRecallResult("same", 0.5, "semantic", "a", {}),
        ]
    )
    assert len(duplicate) == 1
    assert duplicate[0].relevance_score == 0.5

    summary = await recall.generate_memory_summary(keyword + associative)
    assert summary
    formatted = recall.format_memories_for_llm(keyword, include_ids=True)
    assert "Alice drinks green tea" in formatted
    assert "memory_alice" in formatted

    filtered = recall._filter_injection_results(
        keyword + associative, ["alice", "tea"], semantic_primary=False
    )
    assert filtered
    injected = await recall.recall_relevant_memories_for_injection(
        "Alice green tea", "group-a"
    )
    assert injected
    assert recall.should_inject_memories(injected)
    assert recall.format_memories_for_injection(injected)
    assert await recall.get_embedding_cache_stats() == {
        "cached_memories": 0,
        "cache_hit_rate": 0.0,
        "total_requests": 0,
        "status": "embedding_cache_not_enabled",
    }
    assert await recall.trigger_precomputation_for_uncached_memories() is False

    semantic_recall = recall_module.EnhancedMemoryRecall(
        _FakeRecallMemorySystem(embedding=True)
    )
    semantic = await semantic_recall._semantic_recall("Alice tea", "group-a")
    assert semantic and semantic[0].memory == "Alice drinks green tea"
    assert await semantic_recall.get_embedding_cache_stats() == {
        "cached_memories": 1,
        "cache_hit_rate": 50.0,
    }
    assert (
        await semantic_recall.trigger_precomputation_for_uncached_memories(
            ["memory_alice", "memory_tea", "missing"]
        )
        is True
    )
    assert semantic_recall.memory_system.embedding_cache.scheduled


def test_enhanced_memory_recall_strategies_and_injection_helpers():
    asyncio.run(_exercise_recall_system())


class _FakeProfilingMemorySystem:
    def __init__(self):
        self.db_path = ":memory:"
        self.memory_graph = MemoryGraph()
        self._build_graph()

    def _build_graph(self):
        now = time.time()
        user = self.memory_graph.add_element(
            "user-a", "person", "group-a", element_id="elem_user"
        )
        action = self.memory_graph.add_element(
            "drawing", "action", "group-a", element_id="elem_draw"
        )
        trait = self.memory_graph.add_element(
            "patient", "trait", "group-a", element_id="elem_patient"
        )
        memory_id = self.memory_graph.add_memory(
            "user-a discussed drawing",
            memory_id="memory_profile",
            details="x" * 80,
            created_at=now - 86400,
            last_accessed=now,
            group_id="group-a",
        )
        self.memory_graph.link_memory(user, memory_id, "subject")
        self.memory_graph.link_memory(action, memory_id, "object")
        self.memory_graph.link_memory(trait, memory_id, "object")

    def get_person_impression_summary(self, group_id, user_id):
        return {"score": 0.8}


async def _exercise_profiling_system():
    score = profiling_module.IntimacyScore(
        user_id="u",
        interaction_frequency=0.5,
        interaction_depth=0.5,
        emotional_value=0.5,
    )
    assert score.calculate_total_score() == 50.0
    assert score.is_cache_valid()
    assert score.to_dict()["sub_scores"]["emotional_value"] == 0.5

    profiling = profiling_module.UserProfilingSystem.__new__(
        profiling_module.UserProfilingSystem
    )
    profiling.memory_system = _FakeProfilingMemorySystem()
    profiling._intimacy_cache = {}
    profiling._interest_cache = {}
    profiling.cache_duration = 3600

    async def no_save_intimacy(saved_score):
        profiling.saved_score = saved_score

    async def no_save_interests(user_id, group_id, interests):
        profiling.saved_interests = (user_id, group_id, interests)

    profiling._save_intimacy_to_db = no_save_intimacy
    profiling._save_interests_to_db = no_save_interests

    calculated = await profiling.calculate_intimacy("user-a", "group-a")
    assert calculated.total_interactions == 1
    assert calculated.emotional_value == 0.8
    assert calculated.total_score > 0
    assert await profiling.get_intimacy("user-a", "group-a")
    assert len(await profiling.batch_get_intimacy(["user-a", "missing"], "group-a")) == 2

    interests = await profiling.extract_user_interests("user-a", "group-a", top_k=5)
    assert interests
    assert interests[0][1] == 0.5
    assert await profiling.get_user_interests("user-a", "group-a")
    assert profiling.saved_interests[0] == "user-a"


def test_user_profiling_scores_and_interests_with_memory_graph():
    asyncio.run(_exercise_profiling_system())


async def _return_value(value):
    return value


async def _exercise_resource_managers():
    pool = resources_module.DatabaseConnectionPool()
    db_path = ":memory:"
    connection = pool.get_connection(db_path)
    connection.execute("create table sample(id integer)")
    pool.release_connection(db_path, connection)
    reused = pool.get_connection(db_path)
    assert reused is connection
    pool.release_connection(db_path, reused)
    with pool.get_connection_context(db_path) as context_connection:
        assert context_connection is connection
    pool.close_connections(db_path)

    loop_manager = resources_module.EventLoopManager()
    assert loop_manager.get_event_loop() is asyncio.get_running_loop()
    task = loop_manager.create_task(_return_value("ok"), name="resource-test")
    assert await task == "ok"

    manager = resources_module.ResourceManager()
    called = []
    manager.register_cleanup_callback(lambda: called.append("cleaned"))
    manager.get_db_connection(db_path)
    manager.close_db_connections(db_path)
    assert called == []


def test_resource_managers_pool_connections_and_tasks():
    asyncio.run(_exercise_resource_managers())


class _ClosableConnection:
    def __init__(self, fail_on_close=False):
        self.fail_on_close = fail_on_close
        self.closed = False
        self.row_factory = None

    def close(self):
        self.closed = True
        if self.fail_on_close:
            raise RuntimeError("close failed")


class _BadLoop:
    def __init__(self, fail_on_close=False):
        self.fail_on_close = fail_on_close
        self.closed = False

    def is_closed(self):
        return self.closed

    def close(self):
        if self.fail_on_close:
            raise RuntimeError("loop close failed")
        self.closed = True


def _fresh_pool(max_connections=1, timeout=0.01):
    pool = object.__new__(resources_module.DatabaseConnectionPool)
    pool.max_connections = max_connections
    pool.timeout = timeout
    pool.connections = {}
    pool.connection_locks = {}
    pool._initialized = True
    return pool


def _fresh_loop_manager():
    loop_manager = object.__new__(resources_module.EventLoopManager)
    loop_manager.main_event_loop = None
    loop_manager.event_loops = {}
    loop_manager._initialized = True
    return loop_manager


def test_resource_pool_and_loop_manager_edge_paths():
    pool = _fresh_pool()

    original_connect = resources_module.sqlite3.connect

    def fail_connect(*args, **kwargs):
        raise RuntimeError("connect failed")

    resources_module.sqlite3.connect = fail_connect
    try:
        try:
            pool.get_connection("broken")
            assert False
        except RuntimeError as exc:
            assert "connect failed" in str(exc)
    finally:
        resources_module.sqlite3.connect = original_connect

    pool.release_connection("missing", _ClosableConnection())
    pool._cleanup_expired_connections("missing")
    pool.close_connections("missing")

    waiting_pool = _fresh_pool(max_connections=1, timeout=0.2)
    waiting_pool.connections["wait"] = [
        resources_module.ConnectionInfo(
            _ClosableConnection(), is_used=True
        ),
        resources_module.ConnectionInfo(
            _ClosableConnection(), is_used=False, thread_id=-1
        ),
    ]
    waiting_pool.connection_locks["wait"] = resources_module.threading.Lock()
    waited = waiting_pool.get_connection("wait")
    assert waited is waiting_pool.connections["wait"][1].connection

    timeout_pool = _fresh_pool(max_connections=1, timeout=0.01)
    timeout_pool.connections["busy"] = [
        resources_module.ConnectionInfo(_ClosableConnection(), is_used=True)
    ]
    timeout_pool.connection_locks["busy"] = resources_module.threading.Lock()
    try:
        timeout_pool.get_connection("busy")
        assert False
    except TimeoutError as exc:
        assert "busy" in str(exc)

    expired_pool = _fresh_pool()
    expired_ok = resources_module.ConnectionInfo(_ClosableConnection())
    expired_ok.last_used = time.time() - 301
    expired_bad = resources_module.ConnectionInfo(
        _ClosableConnection(fail_on_close=True)
    )
    expired_bad.last_used = time.time() - 301
    expired_pool.connections["expired"] = [expired_ok, expired_bad]
    expired_pool.connection_locks["expired"] = resources_module.threading.Lock()
    expired_pool._cleanup_expired_connections("expired")
    assert expired_ok.connection.closed is True
    assert expired_bad in expired_pool.connections["expired"]

    close_pool = _fresh_pool()
    close_pool.connections["close"] = [
        resources_module.ConnectionInfo(_ClosableConnection()),
        resources_module.ConnectionInfo(_ClosableConnection(fail_on_close=True)),
    ]
    close_pool.connection_locks["close"] = resources_module.threading.Lock()
    close_pool.close_connections("close")
    assert close_pool.connections["close"] == []

    all_pool = _fresh_pool()
    all_pool.connections["all"] = [
        resources_module.ConnectionInfo(_ClosableConnection()),
        resources_module.ConnectionInfo(_ClosableConnection(fail_on_close=True)),
    ]
    all_pool.connection_locks["all"] = resources_module.threading.Lock()
    all_pool.close_all_connections()
    assert all_pool.connections["all"] == []

    loop_manager = _fresh_loop_manager()
    main_loop = asyncio.new_event_loop()
    try:
        loop_manager.set_main_event_loop(main_loop)
        assert loop_manager.get_event_loop() is main_loop
    finally:
        loop_manager.main_event_loop = None
        main_loop.close()

    created_loop = loop_manager.get_event_loop()
    assert created_loop in loop_manager.event_loops.values()
    loop_manager.close_all_loops()
    assert created_loop.is_closed()

    bad_task_manager = _fresh_loop_manager()

    class _TaskFailLoop:
        def create_task(self, coro, name=None):
            coro.close()
            raise RuntimeError("task failed")

    bad_task_manager.get_event_loop = lambda: _TaskFailLoop()
    try:
        bad_task_manager.create_task(_return_value("never"))
        assert False
    except RuntimeError as exc:
        assert "task failed" in str(exc)

    close_error_manager = _fresh_loop_manager()
    close_error_manager.event_loops[1] = _BadLoop(fail_on_close=True)
    close_error_manager.main_event_loop = _BadLoop(fail_on_close=True)
    close_error_manager.close_all_loops()


class _FakeResourceDbPool:
    def __init__(self):
        self.connection = object()
        self.closed_all = False
        self.closed_paths = []
        self.released = []

    def get_connection(self, db_path):
        self.last_db_path = db_path
        return self.connection

    def release_connection(self, db_path, connection):
        self.released.append((db_path, connection))

    def close_connections(self, db_path):
        self.closed_paths.append(db_path)

    def close_all_connections(self):
        self.closed_all = True


class _FakeResourceLoopManager:
    def __init__(self):
        self.closed = False
        self.tasks = []
        self.main_loop = None

    def close_all_loops(self):
        self.closed = True

    def create_task(self, coro, name=None):
        coro.close()
        self.tasks.append(name)
        return "fake-task"

    def set_main_event_loop(self, loop):
        self.main_loop = loop


def test_resource_manager_delegates_cleanup_and_contexts():
    manager = object.__new__(resources_module.ResourceManager)
    manager.db_pool = _FakeResourceDbPool()
    manager.event_loop_manager = _FakeResourceLoopManager()
    manager.cleanup_callbacks = []
    manager._initialized = True

    called = []
    manager.register_cleanup_callback(lambda: called.append("ok"))

    def fail_cleanup():
        raise RuntimeError("cleanup failed")

    manager.register_cleanup_callback(fail_cleanup)
    manager.cleanup()
    assert called == ["ok"]
    assert manager.db_pool.closed_all is True
    assert manager.event_loop_manager.closed is True

    connection = manager.get_db_connection("db")
    assert connection is manager.db_pool.connection
    manager.release_db_connection("db", connection)
    assert manager.db_pool.released == [("db", connection)]
    manager.close_db_connections("db")
    assert manager.db_pool.closed_paths == ["db"]

    with manager.get_db_connection_context("context-db") as context_connection:
        assert context_connection is manager.db_pool.connection
    assert manager.db_pool.released[-1] == ("context-db", manager.db_pool.connection)

    assert manager.create_task(_return_value("ok"), name="named") == "fake-task"
    manager.set_main_event_loop("main")
    assert manager.event_loop_manager.main_loop == "main"


def test_database_schema_diff_mapping_and_status_helpers():
    migration = database_module.SmartDatabaseMigration(str(ROOT / "unit_test.db"))

    assert database_module.TableDiff().has_changes() is False
    assert (
        database_module.TableDiff(
            added_fields=[database_module.FieldSchema("name", "TEXT")]
        ).has_changes()
        is True
    )
    assert database_module.SchemaDiff().has_changes() is False

    main_schema = migration._generate_main_memory_schema()
    assert {"elements", "memories", "connections"} <= set(main_schema.tables)

    migration.db_path = str(ROOT / "cache_embeddings.db")
    embedding_schema = migration._generate_target_schema()
    assert {"memory_embeddings", "precompute_tasks"} <= set(embedding_schema.tables)

    current = database_module.DatabaseSchema(
        tables={
            "memories": database_module.TableSchema(
                "memories",
                fields=[database_module.FieldSchema("id", "TEXT", primary_key=True)],
            )
        }
    )
    target = database_module.DatabaseSchema(
        tables={
            "memories": database_module.TableSchema(
                "memories",
                fields=[
                    database_module.FieldSchema("id", "TEXT", primary_key=True),
                    database_module.FieldSchema("content", "TEXT", not_null=True),
                ],
            ),
            "elements": database_module.TableSchema("elements"),
        }
    )
    diff = migration._calculate_schema_diff(current, target)
    assert diff.added_tables == ["elements"]
    assert diff.modified_tables["memories"].added_fields[0].name == "content"

    mapping, final_columns = migration._build_field_mapping(
        ["id"],
        ["id", "content"],
        diff.modified_tables["memories"],
    )
    assert mapping["id"] == {"type": "direct", "source": "id"}
    assert mapping["content"]["type"] == "default"
    assert final_columns == ["id", "content"]
    assert migration._transform_row(("m1",), mapping, ["id"])["id"] == "m1"
    assert migration._get_default_value("TEXT") == ""
    assert migration._get_default_value("INTEGER") == 0
    assert migration._get_default_value("REAL") == 0.0
    assert migration._get_default_value("BOOL") is False
    assert migration._get_default_value("BLOB") is None

    status = migration.get_migration_status()
    assert status["max_retries"] == 3
    migration.fallback_mode = True
    migration.last_error = "boom"
    migration.reset_migration_state()
    assert migration.fallback_mode is False
    assert migration.last_error is None


class _AnalyzerGraph:
    def __init__(self):
        self.memories = []
        self.elements = []
        self.links = []
        self.auto_connected = []

    def get_all_element_names_by_category(self, group_id):
        return {
            "person": ["Alice"],
            "object": ["tea"],
            "place": [],
            "action": [],
            "trait": [],
        }

    def add_memory(self, **kwargs):
        memory_id = f"memory_{len(self.memories) + 1}"
        self.memories.append((memory_id, kwargs))
        return memory_id

    def get_or_create_element(self, name, category, group_id):
        element_id = f"elem_{name}_{category}_{group_id}"
        self.elements.append((element_id, name, category, group_id))
        return element_id

    def link_memory(self, element_id, memory_id, role):
        self.links.append((element_id, memory_id, role))

    def auto_connect_cooccurring_elements(self, memory_id):
        self.auto_connected.append(memory_id)


class _AnalyzerProvider:
    def __init__(self, text):
        self.text = text
        self.calls = []

    async def text_chat(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResponse(self.text)


class _AnalyzerMemorySystem:
    def __init__(self, provider_text):
        self.memory_config = {
            "topic_message_threshold": 2,
            "topic_trigger_interval_minutes": 5,
            "recent_completed_sessions_count": 1,
        }
        self.memory_graph = _AnalyzerGraph()
        self.provider = _AnalyzerProvider(provider_text)
        self.saved_groups = []
        self.impressions = []

    async def get_llm_provider(self):
        return self.provider

    async def build_memory_generation_persona_injection(self, umo):
        return f"persona:{umo}" if umo else ""

    async def _queue_save_memory_state(self, group_id):
        self.saved_groups.append(group_id)

    def record_person_impression(self, group_id, person_name, summary, score, details):
        self.impressions.append((group_id, person_name, summary, score, details))


async def _exercise_topic_analyzer():
    result_json = """
    {
      "sessions": [
        {
          "session_id": "new_1",
          "topic": "Tea chat",
          "new_message_indices": [0, 1, 99],
          "status": "completed",
          "keywords": "tea",
          "subtext": "friendly",
          "emotion": "calm",
          "participants": "Alice",
          "summary": "Talked about tea",
          "memory": {
            "content": "Alice likes green tea",
            "details": "sencha",
            "emotion": "calm",
            "confidence": 1.5
          },
          "elements": [
            {"name": "Alice", "category": "person", "role": "subject"},
            {"name": "sencha", "category": "unknown", "role": "object"},
            "bad"
          ],
          "impression": {
            "person_name": "Alice",
            "summary": "calm tea fan",
            "score": "0.7",
            "details": "likes sencha"
          }
        }
      ]
    }
    """
    memory_system = _AnalyzerMemorySystem(result_json)
    analyzer = topic_analyzer_module.TopicAnalyzer(memory_system)

    assert analyzer._should_trigger("group-a") is False
    await analyzer.add_message("hello", "u1", "Alice", "group-a", umo="u-mo")
    assert analyzer._should_trigger("group-a") is False
    await analyzer.add_message("tea?", "u1", "Alice", "group-a", umo="u-mo")

    assert memory_system.provider.calls
    assert "persona:u-mo" in memory_system.provider.calls[0]["system_prompt"]
    assert "Alice" in memory_system.provider.calls[0]["prompt"]
    assert "tea" in memory_system.provider.calls[0]["prompt"]
    assert memory_system.saved_groups == ["group-a"]

    completed = analyzer.get_completed_sessions("group-a")
    assert completed == [
        {
            "session_id": "session_0001",
            "topic": "Tea chat",
            "summary": "Talked about tea",
            "keywords": ["tea"],
            "message_count": 2,
        }
    ]
    assert analyzer.get_active_sessions("group-a") == []
    assert analyzer.get_statistics("group-a")["completed_sessions"] == 1

    assert memory_system.memory_graph.memories[0][1]["strength"] == 1.0
    assert memory_system.memory_graph.elements[1][2] == "trait"
    assert memory_system.memory_graph.auto_connected == ["memory_1"]
    assert memory_system.impressions == [
        ("group-a", "Alice", "calm tea fan", 0.7, "likes sencha")
    ]

    parsed = analyzer._parse_response('prefix {"sessions": [],} suffix')
    assert parsed == {"sessions": []}
    assert analyzer._parse_response("no json") is None
    assert analyzer._parse_response('{"sessions": {}}') is None

    prompt = analyzer._build_prompt(
        [{"sender_name": "Alice", "content": "tea", "time_str": "now"}],
        "group-a",
        persona_injection="persona block",
    )
    assert "persona block" in prompt
    assert "Alice" in prompt
    assert "tea" in prompt

    provider_none = _AnalyzerMemorySystem(result_json)
    provider_none.provider = None
    analyzer_none = topic_analyzer_module.TopicAnalyzer(provider_none)
    await analyzer_none.add_message("buffer me", "u1", "Alice", "group-b")
    await analyzer_none.add_message("trigger", "u1", "Alice", "group-b")
    assert len(analyzer_none._message_buffers["group-b"]) == 2


def test_topic_analyzer_builds_prompts_parses_results_and_generates_products():
    asyncio.run(_exercise_topic_analyzer())


async def _exercise_topic_analyzer_force_complete():
    """会话达到 max_session_rounds 仍被LLM标记为 ongoing 时，应被系统强制完成。"""
    result_json = """
    {
      "sessions": [
        {
          "session_id": "new_1",
          "topic": "Never ending chat",
          "new_message_indices": [0, 1],
          "status": "ongoing",
          "keywords": "tea",
          "subtext": "friendly",
          "emotion": "calm",
          "participants": "Alice",
          "summary": null,
          "memory": {
            "content": "Alice keeps talking",
            "details": "endless",
            "emotion": "calm",
            "confidence": 0.8
          },
          "elements": [],
          "impression": null
        }
      ]
    }
    """
    memory_system = _AnalyzerMemorySystem(result_json)
    analyzer = topic_analyzer_module.TopicAnalyzer(memory_system)
    # 把强制总结轮次压到1，第一轮分析后就应触发强制完成
    memory_system.memory_config["max_session_rounds"] = 1

    await analyzer.add_message("hello", "u1", "Alice", "group-force")
    await analyzer.add_message("more tea?", "u1", "Alice", "group-force")

    # 会话被LLM标记为 ongoing，但因达到轮次上限应被强制移入 completed
    assert analyzer.get_active_sessions("group-force") == []
    completed = analyzer.get_completed_sessions("group-force")
    assert len(completed) == 1
    assert completed[0]["topic"] == "Never ending chat"
    # 轮次跟踪已随会话一并清理
    assert "session_0001" not in analyzer._session_rounds.get("group-force", {})

    # 把限制设为0等于关闭，会话应保持 ongoing
    memory_system_off = _AnalyzerMemorySystem(result_json)
    analyzer_off = topic_analyzer_module.TopicAnalyzer(memory_system_off)
    memory_system_off.memory_config["max_session_rounds"] = 0
    await analyzer_off.add_message("hello", "u1", "Alice", "group-off")
    await analyzer_off.add_message("more tea?", "u1", "Alice", "group-off")
    assert len(analyzer_off.get_active_sessions("group-off")) == 1
    assert analyzer_off.get_completed_sessions("group-off") == []

    # prompt 在开启限制时应包含轮次提示
    prompt = analyzer._build_prompt(
        [{"sender_name": "Alice", "content": "tea", "time_str": "now"}],
        "group-force",
    )
    assert "硬性轮次上限" in prompt


def test_topic_analyzer_force_completes_overspent_sessions():
    asyncio.run(_exercise_topic_analyzer_force_complete())


async def _exercise_gateway_decorators_and_error_paths():
    monitor = gateway_module.PerformanceMonitor()
    for i in range(101):
        monitor.record_request(f"slow-{i}", 101.0, success=i % 2 == 0)
    stats = monitor.get_stats()
    assert stats["total_requests"] == 101
    assert stats["slow_requests_count"] == 100
    assert stats["error_count"] == 50

    class Decorated:
        def __init__(self):
            self.calls = 0
            self.performance_monitor = gateway_module.PerformanceMonitor()

        @gateway_module.cached(ttl_seconds=60)
        async def cached_value(self, value):
            self.calls += 1
            return {"value": value, "calls": self.calls}

        @gateway_module.performance_monitored
        async def failing(self):
            raise RuntimeError("boom")

    decorated = Decorated()
    first = await decorated.cached_value("x")
    second = await decorated.cached_value("x")
    assert first == second
    assert decorated.calls == 1

    try:
        await decorated.failing()
    except RuntimeError:
        pass
    else:
        raise AssertionError("performance_monitored should re-raise failures")
    assert decorated.performance_monitor.get_stats()["error_count"] == 1

    gateway = gateway_module.MemoryAPIGateway(
        _FakeGatewayMemorySystem(),
        topic_analyzer=types.SimpleNamespace(
            get_active_sessions=lambda group_id: (_ for _ in ()).throw(
                RuntimeError("topic failed")
            )
        ),
        user_profiling=types.SimpleNamespace(
            get_intimacy=lambda user_id, group_id: (_ for _ in ()).throw(
                RuntimeError("not awaited")
            )
        ),
        temporal_memory=_FakeTemporalMemory(),
    )
    relevance = await gateway.get_topic_relevance("bad", "group-a")
    assert relevance.success is False
    assert "topic failed" in relevance.error

    gateway._set_cache("old", {"x": 1})
    gateway._l1_cache["old"] = ({"x": 1}, time.time() - gateway._l1_cache_ttl - 1)
    assert gateway._check_cache("old") is None
    for i in range(1001):
        gateway._set_cache(f"k{i}", i)
    assert len(gateway._l1_cache) <= 1000


def test_gateway_decorators_monitoring_cache_and_errors():
    asyncio.run(_exercise_gateway_decorators_and_error_paths())


async def _exercise_event_bus_edges():
    bus = events.MemoryEventBus()
    event = events.MemoryEvent(events.MemoryEventType.TOPIC_CREATED)
    bus._event_queue = asyncio.Queue(maxsize=1)
    assert await bus.publish(event, async_mode=True) is True
    assert await bus.publish(event, async_mode=True) is False

    async def bad_async(_event):
        raise RuntimeError("async bad")

    def bad_sync(_event):
        raise RuntimeError("sync bad")

    bus.subscribe(events.MemoryEventType.TOPIC_CREATED, bad_async)
    bus.subscribe(events.MemoryEventType.TOPIC_CREATED, bad_sync)
    await bus._process_event(event)

    started = await events.initialize_event_bus()
    assert started._running is True
    await events.shutdown_event_bus()
    assert events._global_event_bus is None
    await events.shutdown_event_bus()


def test_event_bus_queue_full_callback_errors_and_global_lifecycle():
    asyncio.run(_exercise_event_bus_edges())


async def _exercise_temporal_load_and_auto_detect():
    original_connect = sqlite3.connect
    shared_connection = original_connect(":memory:")

    def connect_shared(*args, **kwargs):
        return _SharedSqliteConnection(shared_connection)

    temporal_module.sqlite3.connect = connect_shared
    memory_system = _FakeTemporalMemorySystem()
    try:
        temporal = temporal_module.TemporalMemorySystem.__new__(
            temporal_module.TemporalMemorySystem
        )
        temporal.memory_system = memory_system
        temporal._open_topics = {}
        temporal._anniversary_cache = {}
        temporal._init_database()

        asked_at = time.time() - 3600
        shared_connection.execute(
            """
            insert into open_topics
            (topic_id, question, asker_id, asked_at, context, group_id, resolved)
            values (?, ?, ?, ?, ?, ?, 0)
            """,
            ("loaded", "Loaded?", "user-a", asked_at, "ctx", "load-group"),
        )
        shared_connection.commit()

        loaded = await temporal.get_open_topics("load-group", days=1)
        assert loaded[0]["topic_id"] == "loaded"
        assert loaded[0]["days_ago"] == 0

        await temporal.auto_detect_and_track_questions(
            "First? Second statement.", "user-b", "auto-group"
        )
        auto_topics = await temporal.get_open_topics("auto-group", days=1)
        assert [topic["question"] for topic in auto_topics] == [
            "First? Second statement"
        ]

        assert (
            temporal._generate_anniversary_description(
                types.SimpleNamespace(content="custom memory content"), 12
            )
        )
    finally:
        temporal_module.sqlite3.connect = original_connect
        shared_connection.close()


def test_temporal_memory_loads_from_database_and_auto_detects_questions():
    asyncio.run(_exercise_temporal_load_and_auto_detect())


async def _exercise_profiling_real_db_saves():
    original_connect = sqlite3.connect
    shared_connection = original_connect(":memory:")

    def connect_shared(*args, **kwargs):
        return _SharedSqliteConnection(shared_connection)

    profiling_module.sqlite3.connect = connect_shared
    try:
        profiling = profiling_module.UserProfilingSystem(
            _FakeProfilingMemorySystem()
        )
        score = profiling_module.IntimacyScore(
            user_id="user-a",
            group_id="group-a",
            interaction_frequency=1.0,
            interaction_depth=0.5,
            emotional_value=0.25,
        )
        score.calculate_total_score()
        await profiling._save_intimacy_to_db(score)
        assert shared_connection.execute(
            "select name from sqlite_master where type='table' and name='intimacy_cache'"
        ).fetchone() is None

        interests = [
            profiling_module.UserInterest(
                element_id="elem_draw",
                element_name="drawing",
                category="action",
                weight=0.75,
                interaction_count=3,
            )
        ]
        await profiling._save_interests_to_db("user-a", "group-a", interests)
        assert shared_connection.execute(
            "select name from sqlite_master where type='table' and name='user_interests'"
        ).fetchone() is None

        cached = profiling_module.IntimacyScore(user_id="cached", group_id="g")
        profiling._intimacy_cache[("cached", "g")] = cached
        assert await profiling.calculate_intimacy("cached", "g") is cached
    finally:
        profiling_module.sqlite3.connect = original_connect
        shared_connection.close()


def test_user_profiling_database_saves_and_cache_hit():
    asyncio.run(_exercise_profiling_real_db_saves())
