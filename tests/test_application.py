"""
Phase 3 测试：application 层（ingest 触发逻辑 / formation 落库 / recall 三策略）。
"""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from conftest import load_plugin_modules  # noqa: E402

mods = load_plugin_modules(
    [
        "storage.repository",
        "application.ingest",
        "application.formation",
        "application.recall",
        "domain.models",
    ]
)
repo_mod = mods["memora.storage.repository"]
ingest_mod = mods["memora.application.ingest"]
formation_mod = mods["memora.application.formation"]
recall_mod = mods["memora.application.recall"]
models = mods["memora.domain.models"]


def _repo(tmp_path):
    return repo_mod.MemoryRepository(str(tmp_path / "t.db"))


class TestIngest:
    def test_blocked_by_exclude_keywords(self, tmp_path):
        repo = _repo(tmp_path)
        try:
            ing = ingest_mod.IngestService(repo, exclude_keywords=["广告", "群发"])
            assert ing.is_blocked("帮我发广告赚钱") is True
            assert ing.is_blocked("今天天气不错") is False
            assert ing.is_blocked("") is False
        finally:
            repo.close()

    def test_threshold_triggers_flush(self, tmp_path):
        repo = _repo(tmp_path)
        try:
            ing = ingest_mod.IngestService(repo, flush_threshold=3)
            assert ing.accept("s1", "一", "u1", "甲", ts=1.0) is False
            assert ing.accept("s1", "二", "u1", "甲", ts=2.0) is False
            assert ing.accept("s1", "三", "u1", "甲", ts=3.0) is True
            assert ing.pending_count("s1") == 3
            # 空内容不计数
            assert ing.accept("s1", "  ", "u1", "甲") is False
        finally:
            repo.close()

    def test_idle_flush_scope(self, tmp_path):
        repo = _repo(tmp_path)
        try:
            ing = ingest_mod.IngestService(repo, idle_seconds=60)
            now = time.time()
            ing.accept("s1", "你好", "u1", "甲", ts=now - 120)
            ing.accept("s2", "在吗", "u2", "乙", ts=now)
            due = ing.scopes_due_flush(now)
            assert "s1" in due and "s2" not in due
            ing.mark_flushed("s1", now)
            assert ing.scopes_due_flush(now) == []
        finally:
            repo.close()


def _canned_analysis(session_id="", status="completed", rounds=2):
    return {
        "sessions": [
            {
                "session_id": session_id,
                "topic": "周末火锅",
                "status": status,
                "new_message_indices": [1, 2],
                "rounds": rounds,
                "keywords": ["火锅", "周末"],
                "emotion": "开心",
                "summary": "大家讨论周末吃火锅" if status == "completed" else "",
                "memory": {
                    "confidence": 0.9,
                    "strength": "high",
                    "details": "周六晚上",
                    "emotion": "期待",
                    "participants": ["张三"],
                    "location": "火锅店",
                    "tags": ["聚餐"],
                    "content": "张三约用户周六去火锅店聚餐",
                },
                "elements": [
                    {"name": "张三", "category": "person", "role": "subject"},
                    {"name": "火锅店", "category": "place", "role": "location"},
                ],
                "relations": [{"from": "张三", "to": "火锅店", "relation": "常去"}],
                "impression": {"person": "张三", "summary": "热情爱组局", "score_delta": 0.1},
            }
        ]
    }


class TestFormation:
    def _make(self, tmp_path, response_text):
        repo = _repo(tmp_path)
        calls: list[str] = []

        async def ask(prompt: str) -> str:
            calls.append(prompt)
            return response_text

        svc = formation_mod.FormationService(
            repo, ask, max_session_rounds=5, recent_completed_count=5, history_count=24
        )
        return repo, svc, calls

    def test_full_flush_pipeline(self, tmp_path):
        repo, svc, calls = self._make(
            tmp_path, "分析结果如下：\n" + json.dumps(_canned_analysis(), ensure_ascii=False)
        )
        async def run():
            now = time.time()
            repo.append_raw("g1", "周六去吃火锅吗", "u1", "张三", now - 60)
            repo.append_raw("g1", "好啊走起", "u2", "李四", now - 30)
            return await svc.flush_scope("g1", now)

        stats = asyncio.run(run())
        assert stats["messages"] == 2
        assert stats["sessions"] == 1 and stats["memories"] == 1
        assert stats["elements"] == 2 and stats["relations"] == 1
        assert stats["impressions"] == 1

        # 记忆落库：strength=high→0.85，participants 合并
        mems = repo.list_memories("g1")
        assert len(mems) == 1
        assert mems[0].content == "张三约用户周六去火锅店聚餐"
        assert abs(mems[0].strength - 0.85) < 1e-9
        assert set(mems[0].participants) == {"张三"}

        # 会话 completed 落库
        sessions = repo.list_sessions("g1", status="completed")
        assert len(sessions) == 1 and sessions[0].topic == "周末火锅"

        # 要素 + 链接 + 关系
        elems = {e.name: e for e in repo.list_elements("g1")}
        assert set(elems) == {"张三", "火锅店"}
        assert elems["张三"].category == "person"
        links = repo.get_memory_elements(mems[0].id)
        assert {(e.name, r) for e, r in links} == {("张三", "subject"), ("火锅店", "location")}
        conns = repo.list_connections("g1")
        assert len(conns) == 1 and conns[0]["relation"] == "常去"

        # 印象：0.5 + 0.1，summary 覆盖
        imp = repo.get_impression("g1", "张三")
        assert abs(imp.score - 0.6) < 1e-9 and imp.summary == "热情爱组局"

        # 缓冲已清空
        assert repo.count_raw("g1") == 0
        repo.close()

    def test_parse_failure_retries_then_gives_up(self, tmp_path):
        repo, svc, calls = self._make(tmp_path, "这不是 JSON")

        async def run():
            repo.append_raw("g1", "消息", "u1", "甲", 1.0)
            return await svc.flush_scope("g1", time.time())

        stats = asyncio.run(run())
        assert stats.get("error") == "parse_failed"
        assert len(calls) == 2  # 重试一次
        # 失败时不清缓冲（下次再试）
        assert repo.count_raw("g1") == 1
        repo.close()

    def test_ongoing_session_and_force_complete(self, tmp_path):
        payload = _canned_analysis(status="ongoing", rounds=5)
        payload["sessions"][0].pop("memory", None)
        repo, svc, _ = self._make(tmp_path, json.dumps(payload, ensure_ascii=False))

        async def run():
            now = time.time()
            repo.append_raw("g1", "聊啥呢", "u1", "甲", now)
            return await svc.flush_scope("g1", now)

        stats = asyncio.run(run())
        assert "memories" not in stats or stats["memories"] == 0
        sessions = repo.list_sessions("g1")
        assert len(sessions) == 1
        # rounds=5 ≥ max_session_rounds=5 → 强制 completed
        assert sessions[0].status == "completed"
        repo.close()

    def test_completed_session_cannot_revive(self, tmp_path):
        repo, svc, _ = self._make(tmp_path, json.dumps(_canned_analysis(), ensure_ascii=False))
        now = time.time()

        async def run():
            repo.append_raw("g1", "再来一条", "u1", "甲", now)
            return await svc.flush_scope("g1", now)

        asyncio.run(run())
        done_id = repo.list_sessions("g1", status="completed")[0].id

        # 用同一个 session_id 再次提交 → 视为新会话
        repo2_payload = _canned_analysis(session_id=done_id, status="ongoing", rounds=1)
        async def ask2(prompt):
            return json.dumps(repo2_payload, ensure_ascii=False)
        svc2 = formation_mod.FormationService(repo, ask2, max_session_rounds=5)
        async def run2():
            repo.append_raw("g1", "复活吧", "u1", "甲", now + 10)
            return await svc2.flush_scope("g1", now + 10)

        asyncio.run(run2())
        sessions = repo.list_sessions("g1")
        statuses = sorted(s.status for s in sessions)
        assert statuses == ["completed", "ongoing"]
        repo.close()

    def test_relation_with_unknown_names_dropped(self, tmp_path):
        payload = _canned_analysis()
        payload["sessions"][0]["relations"] = [
            {"from": "张三", "to": "路人甲", "relation": "认识"}
        ]
        repo, svc, _ = self._make(tmp_path, json.dumps(payload, ensure_ascii=False))

        async def run():
            repo.append_raw("g1", "聊", "u1", "甲", 1.0)
            return await svc.flush_scope("g1", time.time())

        stats = asyncio.run(run())
        assert stats["relations"] == 0
        assert repo.list_connections("g1") == []
        # 路人甲 不会被凭空创建
        assert {e.name for e in repo.list_elements("g1")} == {"张三", "火锅店"}
        repo.close()


class TestRecall:
    def _prepare(self, repo):
        now = time.time()
        m1 = models.Memory(id="m1", scope_id="g1", content="我们上周去了火锅店吃大餐",
                           created_at=now, last_accessed=now)
        m2 = models.Memory(id="m2", scope_id="g1", content="小明说喜欢看电影",
                           created_at=now, last_accessed=now)
        for m in (m1, m2):
            repo.upsert_memory(m)
        elem_hotpot = repo.get_or_create_element("g1", "火锅店", "place", now)
        elem_movie = repo.get_or_create_element("g1", "电影", "action", now)
        elem_person = repo.get_or_create_element("g1", "小明", "person", now)
        repo.link_memory_element("m1", elem_hotpot.id, "location")
        repo.link_memory_element("m2", elem_movie.id, "object")
        repo.link_memory_element("m2", elem_person.id, "subject")
        repo.upsert_connection(elem_person.id, elem_hotpot.id, "常去", now)
        return now, elem_hotpot, elem_movie, elem_person

    def test_keyword_recall_via_fts(self, tmp_path):
        repo = _repo(tmp_path)
        try:
            now, *_ = self._prepare(repo)
            svc = recall_mod.RecallService(repo, weights={"kw": 1.0, "emb": 0, "graph": 0},
                                           threshold=0.1, max_injected=5)
            fused = asyncio.run(svc.recall("g1", "火锅店那次真开心", now))
            assert [c.memory.id for c in fused] == ["m1"]
        finally:
            repo.close()

    def test_graph_recall_direct_and_neighbor(self, tmp_path):
        repo = _repo(tmp_path)
        try:
            now, hotpot, _movie, person = self._prepare(repo)
            svc = recall_mod.RecallService(repo, weights={"kw": 0, "emb": 0, "graph": 1.0},
                                           threshold=0.1, max_injected=5)
            # 提及 小明 → 直挂 m2(1.0)；邻居 火锅店 → m1(0.5)
            fused = asyncio.run(svc.recall("g1", "小明最近怎么样", now))
            scores = {c.memory.id: c.graph_score for c in fused}
            assert scores.get("m2") == 1.0
            assert scores.get("m1") == 0.5
        finally:
            repo.close()

    def test_threshold_filters_all(self, tmp_path):
        repo = _repo(tmp_path)
        try:
            now, *_ = self._prepare(repo)
            svc = recall_mod.RecallService(repo, weights={"kw": 1.0}, threshold=0.99)
            assert asyncio.run(svc.recall("g1", "完全不相关的天文话题", now)) == []
        finally:
            repo.close()

    def test_injection_assembly(self, tmp_path):
        repo = _repo(tmp_path)
        try:
            now, *_ = self._prepare(repo)
            repo.upsert_impression("g1", "小明", 0.8, "话痨但靠谱", now)
            repo.upsert_session(models.Session(id="s1", scope_id="g1", topic="周末计划",
                                               status="ongoing", created_at=now, updated_at=now))
            svc = recall_mod.RecallService(repo, weights={"kw": 1.0}, threshold=0.05)
            text = asyncio.run(svc.build_injection("g1", "火锅店", "张三", now))
            assert "【人物印象】" in text and "话痨但靠谱" in text and "很高" in text
            assert "【当前话题】周末计划" in text
            assert "【相关记忆】" in text and "火锅店" in text
        finally:
            repo.close()