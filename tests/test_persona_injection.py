import asyncio
import importlib.util
from pathlib import Path

_TOPIC_ANALYZER_PATH = (
    Path(__file__).resolve().parent.parent / "intelligence" / "topic_analyzer.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "topic_analyzer_module", _TOPIC_ANALYZER_PATH
)
_MODULE = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(_MODULE)
TopicAnalyzer = _MODULE.TopicAnalyzer


class _FakeResponse:
    def __init__(self, completion_text: str):
        self.completion_text = completion_text


class _FakeProvider:
    def __init__(self):
        self.last_system_prompt = ""
        self.last_prompt = ""

    async def text_chat(self, prompt, contexts, system_prompt):
        self.last_prompt = prompt
        self.last_system_prompt = system_prompt
        return _FakeResponse(
            """
            {
              "sessions": [
                {
                  "session_id": "new_1",
                  "topic": "测试",
                  "new_message_indices": [0],
                  "status": "ongoing",
                  "keywords": ["测试"],
                  "subtext": "",
                  "emotion": "",
                  "participants": ["用户A"],
                  "memory": {
                    "content": "记忆内容",
                    "details": "",
                    "participants": "用户A",
                    "location": "",
                    "emotion": "",
                    "tags": "",
                    "confidence": 0.8
                  }
                }
              ]
            }
            """
        )


class _FakeGraph:
    def add_concept(self, theme):
        return f"concept:{theme}"

    def add_memory(self, **kwargs):
        return "memory:1"


class _FakeMemorySystem:
    def __init__(self, enable_persona_injection=True):
        self.memory_config = {
            "topic_message_threshold": 1,
            "topic_trigger_interval_minutes": 5,
            "recent_completed_sessions_count": 5,
            "enable_persona_injection_in_memory_generation": enable_persona_injection,
        }
        self.provider = _FakeProvider()
        self.memory_graph = _FakeGraph()
        self.saved_group_id = None

    async def get_llm_provider(self):
        return self.provider

    async def build_memory_generation_persona_injection(self, umo):
        if not self.memory_config.get(
            "enable_persona_injection_in_memory_generation", True
        ):
            return ""
        return f"【人格设定（记忆生成约束）】\n来自{umo}的人格"

    async def _queue_save_memory_state(self, group_id):
        self.saved_group_id = group_id

    def record_person_impression(self, group_id, person_name, summary, score, details):
        return "impression:1"


def test_topic_analyzer_injects_persona_into_system_prompt():
    ms = _FakeMemorySystem(enable_persona_injection=True)
    analyzer = TopicAnalyzer(ms)

    asyncio.run(analyzer.add_message("你好", "u1", "用户A", "g1", umo="umo-1"))

    assert "人格设定（记忆生成约束）" in ms.provider.last_system_prompt
    assert "umo-1" in ms.provider.last_system_prompt
    assert ms.saved_group_id == "g1"


def test_topic_analyzer_skips_persona_injection_when_disabled():
    ms = _FakeMemorySystem(enable_persona_injection=False)
    analyzer = TopicAnalyzer(ms)

    asyncio.run(analyzer.add_message("你好", "u1", "用户A", "g1", umo="umo-2"))

    assert "人格设定（记忆生成约束）" not in ms.provider.last_system_prompt
    assert ms.saved_group_id == "g1"
