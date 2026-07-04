import asyncio
import importlib.util
import logging
import sqlite3
import sys
import time
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _ensure_astrbot_stubs():
    if "astrbot" not in sys.modules:
        sys.modules["astrbot"] = types.ModuleType("astrbot")

    api_module = sys.modules.get("astrbot.api")
    if api_module is None:
        api_module = types.ModuleType("astrbot.api")
        sys.modules["astrbot.api"] = api_module
    api_module.logger = logging.getLogger("tests.astrbot")
    setattr(sys.modules["astrbot"], "api", api_module)

    event_module = sys.modules.get("astrbot.api.event")
    if event_module is None:
        event_module = types.ModuleType("astrbot.api.event")
        sys.modules["astrbot.api.event"] = event_module
    event_module.AstrMessageEvent = type("AstrMessageEvent", (), {})

    provider_module = sys.modules.get("astrbot.api.provider")
    if provider_module is None:
        provider_module = types.ModuleType("astrbot.api.provider")
        sys.modules["astrbot.api.provider"] = provider_module
    provider_module.ProviderRequest = type("ProviderRequest", (), {})

    star_module = sys.modules.get("astrbot.api.star")
    if star_module is None:
        star_module = types.ModuleType("astrbot.api.star")
        sys.modules["astrbot.api.star"] = star_module
    star_module.Context = type("Context", (), {})
    star_module.StarTools = type(
        "StarTools",
        (),
        {"get_data_dir": staticmethod(lambda: ROOT / ".test-data")},
    )


def _ensure_package(name: str, path: Path):
    if name in sys.modules:
        return sys.modules[name]
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules[name] = module
    parent_name, _, child_name = name.rpartition(".")
    if parent_name:
        setattr(sys.modules[parent_name], child_name, module)
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


_ensure_astrbot_stubs()
_ensure_package("plugin", ROOT)
_ensure_package("plugin.core", ROOT / "core")
_ensure_package("plugin.infrastructure", ROOT / "infrastructure")
_ensure_package("plugin.memory", ROOT / "memory")

models = _load_module("plugin.core.models", "core/models.py")
resources_module = _load_module("plugin.infrastructure.resources", "infrastructure/resources.py")
database_module = _load_module("plugin.infrastructure.database", "infrastructure/database.py")
memory_graph_module = _load_module("plugin.core.memory_graph", "core/memory_graph.py")
config_module = _load_module("plugin.core.config", "core/config.py")
memory_system_module = _load_module("plugin.core.memory_system", "core/memory_system.py")
recall_module = _load_module("plugin.memory.memory_recall", "memory/memory_recall.py")

MemoryGraph = memory_graph_module.MemoryGraph
MemorySystem = memory_system_module.MemorySystem
EnhancedMemoryRecall = recall_module.EnhancedMemoryRecall
resource_manager = resources_module.resource_manager


def _make_memory_system(tmp_path, config=None):
    base_config = {
        "enable_memory_system": True,
        "recall_mode": "keyword",
        "embedding_provider": "unused-in-tests",
        "enable_associative_recall": True,
        "max_injected_memories": 5,
        "memory_injection_threshold": 0.0,
    }
    if config:
        base_config.update(config)
    return MemorySystem(context=object(), config=base_config, data_dir=tmp_path)


def test_element_memory_links_survive_save_reload(tmp_path):
    async def scenario():
        ms = _make_memory_system(tmp_path)
        now = time.time()

        alice = ms.memory_graph.add_element(
            "Alice",
            "person",
            element_id="elem_alice",
            created_at=now,
            last_accessed=now,
        )
        memory_id = ms.memory_graph.add_memory(
            "Alice likes jasmine tea",
            memory_id="memory_tea",
            details="shared at the cafe",
            strength=0.9,
        )
        ms.memory_graph.link_memory(alice, memory_id, "subject")

        await ms.save_memory_state()
        ms.memory_graph = MemoryGraph()
        ms.load_memory_state()

        assert ms.memory_graph.elements[alice].name == "Alice"
        assert ms.memory_graph.memories[memory_id].content == "Alice likes jasmine tea"
        assert [(e.id, role) for e, role in ms.memory_graph.get_memory_elements(memory_id)] == [
            (alice, "subject")
        ]
        assert [m.id for m in ms.memory_graph.get_element_memories(alice)] == [memory_id]

    try:
        asyncio.run(scenario())
    finally:
        resource_manager.close_db_connections(str(tmp_path / "memory.db"))


def test_legacy_concepts_memories_are_migrated_to_elements(tmp_path):
    db_path = tmp_path / "memory.db"
    now = time.time()
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE concepts (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at REAL,
                last_accessed REAL,
                access_count INTEGER DEFAULT 0
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE memories (
                id TEXT PRIMARY KEY,
                concept_id TEXT NOT NULL,
                content TEXT NOT NULL,
                details TEXT DEFAULT '',
                participants TEXT DEFAULT '',
                location TEXT DEFAULT '',
                emotion TEXT DEFAULT '',
                tags TEXT DEFAULT '',
                created_at REAL,
                last_accessed REAL,
                access_count INTEGER DEFAULT 0,
                strength REAL DEFAULT 1.0,
                allow_forget INTEGER DEFAULT 1,
                group_id TEXT DEFAULT ''
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE connections (
                id TEXT PRIMARY KEY,
                from_concept TEXT NOT NULL,
                to_concept TEXT NOT NULL,
                strength REAL DEFAULT 1.0,
                last_strengthened REAL
            )
            """
        )
        cursor.execute(
            "INSERT INTO concepts VALUES (?, ?, ?, ?, ?)",
            ("concept_tea", "tea, calm", now, now, 2),
        )
        cursor.execute(
            """
            INSERT INTO memories
            (id, concept_id, content, details, participants, location, emotion, tags,
             created_at, last_accessed, access_count, strength, allow_forget, group_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "memory_legacy",
                "concept_tea",
                "Alice drank tea at the cafe",
                "legacy details",
                "Alice",
                "Cafe",
                "calm",
                "favorite, ritual",
                now,
                now,
                1,
                0.8,
                1,
                "",
            ),
        )

    async def scenario():
        ms = _make_memory_system(tmp_path)
        await ms._ensure_database_structure(str(db_path))
        ms.memory_graph = MemoryGraph()
        ms.load_memory_state()
        return ms

    try:
        ms = asyncio.run(scenario())
    finally:
        resource_manager.close_db_connections(str(db_path))

    elements_by_name = {element.name: element for element in ms.memory_graph.elements.values()}
    assert {"tea", "calm", "Alice", "Cafe", "favorite", "ritual"} <= set(elements_by_name)
    assert elements_by_name["Alice"].category == "person"
    assert elements_by_name["Cafe"].category == "place"
    assert "memory_legacy" in ms.memory_graph.memories

    linked = {(element.name, role) for element, role in ms.memory_graph.get_memory_elements("memory_legacy")}
    assert ("tea", "") in linked
    assert ("calm", "") in linked
    assert ("Alice", "subject") in linked
    assert ("Cafe", "scene") in linked
    assert ("favorite", "tag") in linked
    assert ("ritual", "tag") in linked

    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info('memories')")}
        assert {"concept_id", "participants", "location", "tags"}.isdisjoint(columns)
        assert conn.execute("SELECT COUNT(*) FROM element_memories").fetchone()[0] >= 6


class _RecallMemorySystem:
    def __init__(self):
        self.memory_graph = MemoryGraph()
        self.memory_config = {"recall_mode": "keyword"}
        self.embedding_cache = None

    async def get_embedding_provider(self):
        return None

    async def get_embedding(self, text):
        return []


def test_enhanced_memory_recall_finds_keyword_temporal_strength_and_associative():
    async def scenario():
        ms = _RecallMemorySystem()
        now = time.time()
        alice = ms.memory_graph.add_element("Alice", "person", element_id="elem_alice")
        bob = ms.memory_graph.add_element("Bob", "person", element_id="elem_bob")
        cafe = ms.memory_graph.add_element("Cafe", "place", element_id="elem_cafe")

        tea_memory = ms.memory_graph.add_memory(
            "Alice likes jasmine tea",
            memory_id="memory_keyword",
            details="Cafe ritual",
            created_at=now - 60,
            last_accessed=now - 60,
            strength=0.95,
        )
        associated_memory = ms.memory_graph.add_memory(
            "Bob recommends oolong",
            memory_id="memory_associated",
            created_at=now - 120,
            last_accessed=now - 120,
            strength=0.7,
        )
        ms.memory_graph.link_memory(alice, tea_memory, "subject")
        ms.memory_graph.link_memory(cafe, tea_memory, "scene")
        ms.memory_graph.link_memory(bob, associated_memory, "subject")
        ms.memory_graph.add_connection(alice, bob, strength=0.9, connection_id="conn_alice_bob")

        recall = EnhancedMemoryRecall(ms)
        keyword = await recall._keyword_recall("Alice jasmine tea")
        temporal = await recall._temporal_recall("anything")
        strength = await recall._strength_based_recall("anything")
        associative = await recall._associative_recall("Alice")
        combined = await recall.recall_all_relevant_memories("Alice jasmine tea", max_memories=10)

        return keyword, temporal, strength, associative, combined

    keyword, temporal, strength, associative, combined = asyncio.run(scenario())

    assert {result.metadata["memory_id"] for result in keyword} >= {"memory_keyword"}
    assert {result.metadata["memory_id"] for result in temporal} >= {
        "memory_keyword",
        "memory_associated",
    }
    assert {result.metadata["memory_id"] for result in strength} >= {
        "memory_keyword",
        "memory_associated",
    }
    assert {result.metadata["memory_id"] for result in associative} >= {
        "memory_keyword",
        "memory_associated",
    }
    assert {result.memory for result in combined} >= {
        "Alice likes jasmine tea",
        "Bob recommends oolong",
    }
