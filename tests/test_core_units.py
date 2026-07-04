import asyncio
import importlib.util
import json
import sys
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _load_module(module_name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(module_name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


if "astrbot.api" not in sys.modules:
    import logging
    import types

    astrbot_module = types.ModuleType("astrbot")
    api_module = types.ModuleType("astrbot.api")
    api_module.logger = logging.getLogger("tests.astrbot")
    sys.modules["astrbot"] = astrbot_module
    sys.modules["astrbot.api"] = api_module


models = _load_module("models", "core/models.py")
config_module = _load_module("config_module", "core/config.py")
memory_graph_module = _load_module("memory_graph_module", "core/memory_graph.py")
events_module = _load_module("events_module", "infrastructure/events.py")
formatters = _load_module("formatters_module", "utils/formatters.py")
validators = _load_module("validators_module", "utils/validators.py")

Concept = models.Concept
Connection = models.Connection
Element = models.Element
Memory = models.Memory
MemoryConfigManager = config_module.MemoryConfigManager
MemorySystemConfig = config_module.MemorySystemConfig
MemoryGraph = memory_graph_module.MemoryGraph
MemoryEvent = events_module.MemoryEvent
MemoryEventBus = events_module.MemoryEventBus
MemoryEventType = events_module.MemoryEventType
get_event_bus = events_module.get_event_bus


def test_models_fill_defaults_and_normalize_invalid_values():
    before = time.time()

    element = Element(id="elem_1", name="Alice", category="unknown")
    memory = Memory(id="memory_1", content="hello", allow_forget=None)
    connection = Connection(id="conn_1", from_element="elem_1", to_element="elem_2")
    concept = Concept(id="concept_1", name="legacy")

    assert element.category == "trait"
    assert element.created_at >= before
    assert element.last_accessed >= before
    assert memory.allow_forget is True
    assert memory.created_at >= before
    assert connection.last_strengthened >= before
    assert concept.created_at >= before


def test_memory_config_round_trips_and_manager_updates_state():
    config = MemorySystemConfig.from_dict(
        {
            "enable_memory_system": False,
            "exclude_keywords": ["skip"],
            "topic_trigger_interval_minutes": 9,
            "topic_message_threshold": 3,
            "recent_completed_sessions_count": 2,
        }
    )

    assert config.to_dict() == {
        "enable_memory_system": False,
        "exclude_keywords": ["skip"],
        "topic_trigger_interval_minutes": 9,
        "topic_message_threshold": 3,
        "recent_completed_sessions_count": 2,
    }

    manager = MemoryConfigManager({"enable_memory_system": 0})
    assert manager.is_memory_system_enabled() is False

    manager.set_memory_system_enabled(True)
    assert manager.get_config().enable_memory_system is True

    manager.update_config({"enable_memory_system": False, "exclude_keywords": ["x"]})
    assert manager.get_config_dict()["enable_memory_system"] is False
    assert manager.get_config_dict()["exclude_keywords"] == ["x"]
    assert manager.validate_config() is True

    manager.config.enable_memory_system = "yes"
    assert manager.validate_config() is False


def test_memory_graph_element_memory_and_connection_lifecycle():
    graph = MemoryGraph()

    alice = graph.add_element("Alice", "person", "group-a", element_id="elem_a")
    duplicate = graph.get_or_create_element("Alice", "person", "group-a")
    box = graph.add_element("Box", "object", "group-a", element_id="elem_b")
    other_group_alice = graph.get_or_create_element("Alice", "person", "group-b")
    memory_id = graph.add_memory(
        "Alice bought a box",
        memory_id="memory_1",
        details="at the mall",
        emotion="happy",
        strength=0.8,
        group_id="group-a",
    )

    assert duplicate == alice
    assert other_group_alice != alice
    assert graph.find_element_by_name("Alice", "group-a").id == alice
    assert [e.id for e in graph.find_elements_by_category("person", "group-a")] == [
        alice
    ]
    assert graph.get_all_element_names_by_category("group-a")["person"] == ["Alice"]

    graph.link_memory(alice, memory_id, "subject")
    graph.link_memory(box, memory_id, "object")
    graph.link_memory(alice, memory_id, "actor")

    assert [(e.id, role) for e, role in graph.get_memory_elements(memory_id)] == [
        (alice, "actor"),
        (box, "object"),
    ]
    assert [m.id for m in graph.get_element_memories(alice)] == [memory_id]
    assert [m.id for m in graph.get_element_memories_with_role(alice, "actor")] == [
        memory_id
    ]

    graph.auto_connect_cooccurring_elements(memory_id)
    assert len(graph.connections) == 1
    assert graph.get_neighbors(alice) == [(box, 1.0)]
    assert graph.get_neighbors(box) == [(alice, 1.0)]

    same_connection = graph.add_connection(box, alice, strength=0.5)
    assert same_connection == graph.connections[0].id
    assert graph.connections[0].strength == 1.1
    assert graph.get_neighbors(alice) == [(box, 1.1)]

    assert graph.set_connection_strength(same_connection, 0.25) is True
    assert graph.get_neighbors(alice) == [(box, 0.25)]
    assert graph.set_connection_strength("missing", 0.1) is False

    assert graph.update_memory(memory_id, content="updated", unknown="ignored") is True
    assert graph.memories[memory_id].content == "updated"
    assert not hasattr(graph.memories[memory_id], "unknown")

    assert graph.update_element(alice, name="Alice A.", category="person") is True
    assert graph.elements[alice].name == "Alice A."

    graph.unlink_memory(box, memory_id)
    assert [(e.id, role) for e, role in graph.get_memory_elements(memory_id)] == [
        (alice, "actor")
    ]

    graph.remove_connection(same_connection)
    assert graph.get_neighbors(alice) == []

    graph.remove_memory(memory_id)
    assert memory_id not in graph.memories
    assert graph.get_memory_elements(memory_id) == []

    assert graph.remove_element("missing") is False
    assert graph.remove_element(alice) is True
    assert alice not in graph.elements


def test_memory_graph_legacy_concepts_remove_linked_memories_and_connections():
    graph = MemoryGraph()
    concept_id = graph.add_concept("legacy", concept_id="concept_1")
    other = graph.add_element("Other", "trait", element_id="elem_other")
    memory_id = graph.add_memory("legacy memory", memory_id="memory_legacy")

    graph.link_memory(concept_id, memory_id, "theme")
    connection_id = graph.add_connection(concept_id, other, connection_id="conn_legacy")

    assert graph.remove_concept("missing") is False
    assert graph.remove_concept(concept_id) is True
    assert concept_id not in graph.concepts
    assert memory_id not in graph.memories
    assert all(c.id != connection_id for c in graph.connections)
    assert concept_id not in graph.adjacency_list


def test_formatters_cover_valid_invalid_and_boundary_cases():
    assert formatters.format_timestamp(0) == "1970-01-01 08:00:00"
    assert formatters.format_timestamp("bad") == "未知时间"
    assert formatters.format_memory_summary({"content": "abcdef"}, max_length=3) == "abc..."
    assert formatters.format_memory_summary({}, max_length=3) == ""
    assert formatters.format_score("3.14159", decimals=3) == "3.142"
    assert formatters.format_score("bad") == "0.00"
    assert formatters.format_list_as_string(["a", "b"], separator="|") == "a|b"
    assert "a" in formatters.format_list_as_string(["a", "b", "c"], max_items=2)
    assert formatters.truncate_text("abcdef", max_length=5) == "ab..."
    assert formatters.truncate_text("", max_length=5) == ""
    assert formatters.escape_markdown("*a_[b]") == r"\*a\_\[b\]"

    pretty = formatters.format_dict_pretty({"a": 1}, indent=0)
    assert json.loads(pretty) == {"a": 1}
    assert formatters.format_dict_pretty({("not", "json"): object()}).startswith("{")

    assert formatters.format_duration(0.5) == "500ms"
    assert formatters.format_duration(2) == "2.0s"
    assert formatters.format_duration(120) == "2.0m"
    assert formatters.format_duration(7200) == "2.0h"


def test_validators_cover_acceptance_rejection_and_sanitization():
    assert validators.validate_memory_id("memory_1")
    assert not validators.validate_memory_id("mem_1")
    assert not validators.validate_memory_id(None)

    assert validators.validate_concept_id("concept_1")
    assert not validators.validate_concept_id("elem_1")

    assert validators.validate_group_id(None)
    assert validators.validate_group_id("group")
    assert not validators.validate_group_id(123)

    assert validators.validate_score("0.5") == 0.5
    assert validators.validate_score(5, min_val=1, max_val=10) == 5.0
    assert validators.validate_score(2, min_val=0, max_val=1) is None
    assert validators.validate_score("bad") is None

    assert validators.validate_timestamp(None)
    assert validators.validate_timestamp(1)
    assert not validators.validate_timestamp(0)
    assert not validators.validate_timestamp("now")

    assert validators.sanitize_text(" hello<>世界! ", max_length=8) == "hello世界"
    assert validators.sanitize_text(None) == ""

    assert validators.validate_json_string('{"ok": true}')
    assert not validators.validate_json_string("{bad")


async def _run_event_bus_scenario():
    bus = MemoryEventBus()
    calls = []

    async def async_callback(event):
        calls.append(("async", event.data["value"]))

    def sync_callback(event):
        calls.append(("sync", event.group_id))

    event = MemoryEvent(
        event_type=MemoryEventType.MEMORY_TRIGGERED,
        group_id="group-a",
        user_id="user-a",
        data={"value": 42},
        metadata={"source": "test"},
    )

    assert event.to_dict()["event_type"] == "memory.triggered"
    assert event.to_dict()["group_id"] == "group-a"

    assert bus.subscribe(MemoryEventType.MEMORY_TRIGGERED, async_callback) is True
    assert bus.subscribe(MemoryEventType.MEMORY_TRIGGERED, async_callback) is False
    assert bus.subscribe(MemoryEventType.MEMORY_TRIGGERED, sync_callback) is True

    assert await bus.publish(event, async_mode=False) is True
    assert ("async", 42) in calls
    assert ("sync", "group-a") in calls
    assert bus.get_subscriber_count(MemoryEventType.MEMORY_TRIGGERED) == 2
    assert bus.get_all_subscribers() == {"memory.triggered": 2}
    assert bus.get_event_history(MemoryEventType.MEMORY_TRIGGERED) == [event]

    assert bus.unsubscribe(MemoryEventType.MEMORY_TRIGGERED, async_callback) is True
    assert bus.unsubscribe(MemoryEventType.MEMORY_TRIGGERED, async_callback) is False

    assert await bus.publish(event, async_mode=True) is True
    assert bus._event_queue.qsize() == 1

    await bus.start()
    await asyncio.wait_for(bus._event_queue.join(), timeout=2)
    await bus.stop()
    await bus.stop()

    return bus


def test_event_bus_publish_subscribe_history_and_global_instance():
    bus = asyncio.run(_run_event_bus_scenario())

    assert bus.get_event_history(limit=1)[0].event_type is MemoryEventType.MEMORY_TRIGGERED
    assert get_event_bus() is get_event_bus()
