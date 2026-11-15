"""
Phase 4 薄集成测试：main.py 装配（stub context/config/event）。

覆盖：插件构造、scope 解析、on_message → ingest → formation flush 全链路、
on_llm_request 注入、terminate 清理。
"""

import asyncio
import json
import sys
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from conftest import load_plugin_modules  # noqa: E402

mods = load_plugin_modules(["main"])
main_mod = mods["memora.main"]
MemoraConnectPlugin = main_mod.MemoraConnectPlugin


class FakeProvider:
    def __init__(self, reply: str = "ok"):
        self.reply = reply

    async def text_chat(self, prompt, contexts=None, **kw):
        self.last_prompt = prompt
        return types.SimpleNamespace(completion_text=self.reply)


class FakeContext:
    def __init__(self, reply: str = "ok"):
        self.provider = FakeProvider(reply)
        self.registered_routes = []

    def register_web_api(self, path, handler, methods, desc):
        self.registered_routes.append(path)

    def get_provider_by_id(self, pid):
        return None

    def get_all_providers(self):
        return []

    def get_using_provider(self):
        return self.provider


class FakeEvent:
    def __init__(self, text, group_id="g1", sender_id="u1", sender_name="张三",
                 private=False, at=True):
        self.message_str = text
        self._gid = group_id
        self._sid = sender_id
        self._name = sender_name
        self._private = private
        self._at = at

    def get_group_id(self):
        return self._gid

    def get_sender_id(self):
        return self._sid

    def get_sender_name(self):
        return self._name

    def is_private_chat(self):
        return self._private

    @property
    def is_at_or_wake_command(self):
        return self._at

    def plain_result(self, text):
        return ("plain", text)

    async def send_image(self, path):
        return True


class FakeReq:
    def __init__(self):
        self.extra_user_content_parts = []


def _build(tmp_path, reply="ok", **cfg_overrides):
    # StarTools.get_data_dir 指向临时目录
    star_mod = sys.modules["astrbot.api.star"]
    star_mod.StarTools.get_data_dir = staticmethod(lambda: tmp_path)
    cfg = {
        "enable_memory_system": True,
        "enable_group_isolation": True,
        "topic_message_threshold": 2,
        "formation_idle_flush_seconds": 60,
        "llm_provider": "",
        "exclude_keywords": [],
    }
    cfg.update(cfg_overrides)
    context = FakeContext(reply)
    plugin = MemoraConnectPlugin(context, cfg)
    return plugin, context


async def _drain(plugin):
    for _ in range(50):
        pending = [t for t in plugin._background_tasks if not t.done()]
        if not pending:
            break
        await asyncio.gather(*pending)


def test_scope_resolution(tmp_path):
    async def run():
        plugin, _ = _build(tmp_path)
        try:
            assert plugin.resolve_scope(FakeEvent("x", group_id="123")) == "123"
            assert plugin.resolve_scope(FakeEvent("x", group_id="", sender_id="u9",
                                                  private=True)) == "u:u9"
            plugin.cfg["enable_group_isolation"] = False
            assert plugin.resolve_scope(FakeEvent("x", group_id="", sender_id="u9",
                                                  private=True)) == "default"
        finally:
            await plugin.terminate()

    asyncio.run(run())


def test_message_to_memory_pipeline(tmp_path):
    reply = json.dumps(
        {
            "sessions": [
                {
                    "session_id": "",
                    "topic": "测试话题",
                    "status": "completed",
                    "rounds": 1,
                    "memory": {"content": "用户喜欢在群里聊火锅", "confidence": 0.9,
                               "strength": "normal"},
                    "elements": [{"name": "火锅", "category": "object", "role": "object"}],
                    "relations": [],
                    "impression": {"person": "张三", "summary": "爱吃火锅", "score_delta": 0.1},
                }
            ]
        },
        ensure_ascii=False,
    )

    async def run():
        plugin, context = _build(tmp_path, reply=reply)
        try:
            ev1 = FakeEvent("今晚吃火锅去吗", group_id="g1")
            ev2 = FakeEvent("走走走 嗨吃", group_id="g1")
            await plugin.on_message(ev1)
            # 阈值=2：第二条消息触发 flush
            await plugin.on_message(ev2)
            await _drain(plugin)

            mems = plugin.repo.list_memories("g1")
            assert len(mems) == 1
            assert mems[0].content == "用户喜欢在群里聊火锅"
            assert plugin.repo.get_impression("g1", "张三") is not None
            assert context.provider.last_prompt and "新消息" in context.provider.last_prompt
        finally:
            await plugin.terminate()

    asyncio.run(run())


def test_message_filters(tmp_path):
    async def run():
        plugin, _ = _build(tmp_path, exclude_keywords=["广告"])
        try:
            # 指令前缀跳过
            await plugin.on_message(FakeEvent("/help"))
            await plugin.on_message(FakeEvent("!hi"))
            await plugin.on_message(FakeEvent("！签到"))
            assert plugin.repo.count_raw("g1") == 0
            # 排除关键词跳过
            await plugin.on_message(FakeEvent("这是广告内容"))
            assert plugin.repo.count_raw("g1") == 0
            # 正常入站
            await plugin.on_message(FakeEvent("正常聊天"))
            assert plugin.repo.count_raw("g1") == 1
        finally:
            await plugin.terminate()

    asyncio.run(run())


def test_llm_request_injection(tmp_path):
    async def run():
        plugin, _ = _build(tmp_path)
        try:
            mem_id = await plugin.add_memory_api("张三和老王是同学", group_id="g1")
            elem = plugin.repo.get_or_create_element("g1", "老王", "person", time.time())
            plugin.repo.link_memory_element(mem_id, elem.id, "subject")
            plugin.repo.upsert_impression("g1", "老王", 0.7, "靠谱", time.time())

            req = FakeReq()
            # 群聊需 @bot 才进入记忆管线
            await plugin.on_llm_request(FakeEvent("老王是谁", group_id="g1", at=True), req)
            texts = [getattr(p, "text", "") for p in req.extra_user_content_parts]
            assert any("【相关记忆】" in t for t in texts)
            assert any("老王" in t and "靠谱" in t for t in texts)

            # 不重复注入
            await plugin.on_llm_request(FakeEvent("老王是谁", group_id="g1", at=True), req)
            assert len(req.extra_user_content_parts) == 1
        finally:
            await plugin.terminate()

    asyncio.run(run())


def test_private_scope_isolated(tmp_path):
    async def run():
        plugin, _ = _build(tmp_path)
        try:
            await plugin.add_memory_api("私房话", group_id="u:u5")
            assert plugin.repo.stats("u:u5")["memories"] == 1
            assert plugin.repo.stats("g1")["memories"] == 0
        finally:
            await plugin.terminate()

    asyncio.run(run())


def test_terminate_closes_repo(tmp_path):
    async def run():
        plugin, _ = _build(tmp_path)
        sweeper = plugin._sweeper_task
        await plugin.terminate()
        assert sweeper.cancelled() or sweeper.done()
        try:
            plugin.repo.count_raw("g1")
            raise AssertionError("repo 应已关闭")
        except RuntimeError:
            pass

    asyncio.run(run())