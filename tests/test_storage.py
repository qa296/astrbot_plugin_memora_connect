"""
Phase 1 测试：schema + repository（真实 SQLite，临时目录）。
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from conftest import load_plugin_modules  # noqa: E402

mods = load_plugin_modules(
    ["storage.schema", "storage.repository", "domain.models", "domain.scoring"]
)
models = mods["memora.domain.models"]
repo_mod = mods["memora.storage.repository"]
Memory = models.Memory
Session = models.Session


def _memory(mid, scope="s1", content="内容", **kw):
    kw.setdefault("created_at", kw.pop("now", time.time()))
    kw.setdefault("last_accessed", kw["created_at"])
    return Memory(id=mid, scope_id=scope, content=content, **kw)


class TestMemoryCrud:
    def test_upsert_and_get(self, tmp_path):
        repo = repo_mod.MemoryRepository(str(tmp_path / "t.db"))
        try:
            repo.upsert_memory(_memory("m1", content="我昨天去吃了火锅"))
            m = repo.get_memory("m1")
            assert m is not None
            assert m.scope_id == "s1"
            assert m.participants == []
            assert m.strength == 1.0
        finally:
            repo.close()

    def test_upsert_updates_in_place(self, tmp_path):
        repo = repo_mod.MemoryRepository(str(tmp_path / "t.db"))
        try:
            repo.upsert_memory(_memory("m1", content="旧", created_at=1.0))
            m = _memory("m1", content="新", created_at=2.0)
            repo.upsert_memory(m)
            m2 = repo.get_memory("m1")
            assert m2.content == "新"
            # 更新不重置创建时间
            assert m2.created_at == 1.0
        finally:
            repo.close()

    def test_hard_delete(self, tmp_path):
        repo = repo_mod.MemoryRepository(str(tmp_path / "t.db"))
        try:
            repo.upsert_memory(_memory("m1"))
            assert repo.delete_memory("m1") is True
            assert repo.get_memory("m1") is None
            assert repo.delete_memory("m1") is False
        finally:
            repo.close()

    def test_scope_isolation(self, tmp_path):
        repo = repo_mod.MemoryRepository(str(tmp_path / "t.db"))
        try:
            repo.upsert_memory(_memory("m1", scope="A", content="私密"))
            repo.upsert_memory(_memory("m2", scope="B", content="火锅"))
            assert repo.search_memories_by_like("B", "火锅")[0].id == "m2"
            assert repo.search_memories_by_like("A", "火锅") == []
            assert repo.ids_from_fts('"火锅"', "A") == []
        finally:
            repo.close()

    def test_fts_and_like(self, tmp_path):
        repo = repo_mod.MemoryRepository(str(tmp_path / "t.db"))
        try:
            repo.upsert_memory(_memory("m1", content="我们一起去了电影院"))
            assert repo.fts_enabled is True
            assert repo.ids_from_fts('"电影院"', "s1") == ["m1"]
            assert repo.search_memories_by_like("s1", "电影院")[0].id == "m1"
            # 2 字词 trigram 覆盖不到，LIKE 兜底必须生效
            assert repo.search_memories_by_like("s1", "电影")[0].id == "m1"
        finally:
            repo.close()

    def test_touch_and_update_fields(self, tmp_path):
        repo = repo_mod.MemoryRepository(str(tmp_path / "t.db"))
        try:
            repo.upsert_memory(_memory("m1", content="原"))
            repo.touch_memory("m1", now=999.0)
            m = repo.get_memory("m1")
            assert m.last_accessed == 999.0 and m.access_count == 1
            assert repo.update_memory_fields("m1", content="改", strength=0.5) is True
            m = repo.get_memory("m1")
            assert m.content == "改" and m.strength == 0.5
            assert repo.update_memory_fields("nope", content="x") is False
        finally:
            repo.close()


class TestElementsAndConnections:
    def test_get_or_create_idempotent(self, tmp_path):
        repo = repo_mod.MemoryRepository(str(tmp_path / "t.db"))
        try:
            e1 = repo.get_or_create_element("s1", "张三", "person", 1.0)
            e2 = repo.get_or_create_element("s1", "张三", "person", 2.0)
            e3 = repo.get_or_create_element("s2", "张三", "person", 3.0)
            assert e1.id == e2.id
            assert e3.id != e1.id
            assert e2.category == "person"
        finally:
            repo.close()

    def test_rename_delete_element(self, tmp_path):
        repo = repo_mod.MemoryRepository(str(tmp_path / "t.db"))
        try:
            e = repo.get_or_create_element("s1", "旧名", "person", 1.0)
            assert repo.rename_element(e.id, "新名") is True
            assert repo.get_element(e.id).name == "新名"
            assert repo.delete_element(e.id) is True
            assert repo.get_element(e.id) is None
        finally:
            repo.close()

    def test_link_and_query_memories(self, tmp_path):
        repo = repo_mod.MemoryRepository(str(tmp_path / "t.db"))
        try:
            repo.upsert_memory(_memory("m1", content="和张三吃饭"))
            e = repo.get_or_create_element("s1", "张三", "person", 1.0)
            repo.link_memory_element("m1", e.id, "subject")
            links = repo.get_memory_elements("m1")
            assert links[0][0].id == e.id and links[0][1] == "subject"
            mems = repo.get_element_memories(e.id)
            assert [m.id for m in mems] == ["m1"]
        finally:
            repo.close()

    def test_connection_canonical_and_removal(self, tmp_path):
        repo = repo_mod.MemoryRepository(str(tmp_path / "t.db"))
        try:
            a = repo.get_or_create_element("s1", "阿", "person", 1.0)
            b = repo.get_or_create_element("s1", "彪", "person", 1.0)
            repo.upsert_connection(a.id, b.id, "同学", 1.0)
            repo.upsert_connection(b.id, a.id, "同事", 2.0)  # 反向写入 = 覆盖同一条边
            conns = repo.list_connections("s1")
            assert len(conns) == 1
            # 规范序 (a,b) 存储，后写的关系描述胜出
            assert conns[0]["relation"] == "同事"
            assert repo.delete_connection(b.id, a.id) is True
            assert repo.list_connections("s1") == []
        finally:
            repo.close()

    def test_neighbors_excludes_self(self, tmp_path):
        repo = repo_mod.MemoryRepository(str(tmp_path / "t.db"))
        try:
            a = repo.get_or_create_element("s1", "阿", "person", 1.0)
            b = repo.get_or_create_element("s1", "彪", "person", 1.0)
            c = repo.get_or_create_element("s1", "蔡", "person", 1.0)
            repo.upsert_connection(a.id, b.id, "朋友", 1.0)
            repo.upsert_connection(c.id, a.id, "亲戚", 1.0)
            assert repo.neighbor_elements({a.id}) == {b.id, c.id}
        finally:
            repo.close()


class TestImpressions:
    def test_upsert_clamps_and_keeps_summary(self, tmp_path):
        repo = repo_mod.MemoryRepository(str(tmp_path / "t.db"))
        try:
            repo.upsert_impression("s1", "张三", 2.5, "很好", 1.0)
            imp = repo.get_impression("s1", "张三")
            assert imp.score == 1.0
            # 空 summary 不覆盖旧值
            repo.upsert_impression("s1", "张三", 0.3, "", 2.0)
            imp = repo.get_impression("s1", "张三")
            assert imp.score == 0.3 and imp.summary == "很好"
        finally:
            repo.close()

    def test_adjust_clamps(self, tmp_path):
        repo = repo_mod.MemoryRepository(str(tmp_path / "t.db"))
        try:
            repo.upsert_impression("s1", "张三", 0.5, "初识", 1.0)
            assert repo.adjust_impression("s1", "张三", -1.0, 2.0) == 0.0
            assert repo.adjust_impression("s1", "张三", 5.0, 3.0) == 1.0
        finally:
            repo.close()

    def test_list_and_stats(self, tmp_path):
        repo = repo_mod.MemoryRepository(str(tmp_path / "t.db"))
        try:
            repo.upsert_impression("s1", "张三", 0.8, "a", 1.0)
            repo.upsert_impression("s2", "李四", 0.4, "b", 1.0)
            assert {i.subject for i in repo.list_impressions("s1")} == {"张三"}
            assert len(repo.list_impressions()) == 2
        finally:
            repo.close()


class TestSessions:
    def test_upsert_preserves_created_at(self, tmp_path):
        repo = repo_mod.MemoryRepository(str(tmp_path / "t.db"))
        try:
            s = Session(id="s_1", scope_id="s1", topic="旅行计划", status="ongoing",
                        rounds=2, keywords=["旅行"], created_at=1.0, updated_at=1.0)
            repo.upsert_session(s)
            s.topic = "假期旅行计划"
            s.rounds = 3
            s.created_at = 999.0
            repo.upsert_session(s)
            got = repo.get_session("s_1")
            assert got.topic == "假期旅行计划" and got.rounds == 3
            assert got.created_at == 1.0
            assert got.keywords == ["旅行"]
        finally:
            repo.close()

    def test_list_by_status(self, tmp_path):
        repo = repo_mod.MemoryRepository(str(tmp_path / "t.db"))
        try:
            now = time.time()
            repo.upsert_session(Session(id="a", scope_id="s1", topic="t1",
                                        status="open_question", created_at=now, updated_at=now))
            repo.upsert_session(Session(id="b", scope_id="s1", topic="t2",
                                        status="completed", created_at=now, updated_at=now))
            assert {s.id for s in repo.list_sessions("s1")} == {"a", "b"}
            assert {s.id for s in repo.list_sessions("s1", status="completed")} == {"b"}
            assert repo.delete_session("b") is True
            assert repo.list_sessions("s1", status="completed") == []
        finally:
            repo.close()


class TestRawBuffer:
    def test_append_list_trim_clear(self, tmp_path):
        repo = repo_mod.MemoryRepository(str(tmp_path / "t.db"))
        try:
            for i in range(5):
                repo.append_raw("s1", f"消息{i}", f"u{i}", f"用户{i}", 1000.0 + i)
            rows = repo.list_raw("s1")
            assert [r["content"] for r in rows] == [f"消息{i}" for i in range(5)]
            repo.trim_raw("s1", 3)
            rows = repo.list_raw("s1")
            assert [r["content"] for r in rows] == ["消息2", "消息3", "消息4"]
            assert rows[0]["sender_name"] == "用户2"
            repo.clear_raw("s1")
            assert repo.list_raw("s1") == []
        finally:
            repo.close()


class TestMetaAndStats:
    def test_meta_roundtrip(self, tmp_path):
        repo = repo_mod.MemoryRepository(str(tmp_path / "t.db"))
        try:
            repo.set_meta("k1", "1")
            assert repo.get_meta("k1") == "1"
            assert repo.get_meta("missing", "d") == "d"
            repo.delete_meta("k1")
            assert repo.get_meta("k1") == ""
        finally:
            repo.close()

    def test_stats_counts_by_scope(self, tmp_path):
        repo = repo_mod.MemoryRepository(str(tmp_path / "t.db"))
        try:
            now = time.time()
            for i in range(2):
                repo.upsert_memory(_memory(f"m{i}", content=f"c{i}",
                                           created_at=now + i, last_accessed=now + i))
            repo.upsert_memory(_memory("mx", scope="other"))
            repo.upsert_impression("s1", "张三", 0.8, "a", now)
            repo.upsert_session(Session(id="s", scope_id="s1", topic="t",
                                        created_at=now, updated_at=now))
            e1 = repo.get_or_create_element("s1", "张三", "person", now)
            e2 = repo.get_or_create_element("s1", "李四", "person", now)
            repo.upsert_connection(e1.id, e2.id, "朋友", now)
            st = repo.stats("s1")
            assert st == {"memories": 2, "elements": 2, "connections": 1,
                          "impressions": 1, "sessions": 1}
            assert repo.stats()["memories"] == 3
        finally:
            repo.close()
