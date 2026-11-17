"""
Phase 1 测试：v1 → v2 迁移（构造旧库 fixture，验证 scope 映射、印象记忆分流、
Imprint concept、open_topics 迁移、连接丢弃、幂等与备份）。
"""

import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from conftest import load_plugin_modules  # noqa: E402

mods = load_plugin_modules(["storage.repository", "storage.migrate_v1"])
repo_mod = mods["memora.storage.repository"]
migrate_mod = mods["memora.storage.migrate_v1"]

LEGACY_DDL = """
CREATE TABLE elements (
    id TEXT PRIMARY KEY, name TEXT, category TEXT,
    group_id TEXT DEFAULT '', created_at REAL DEFAULT 0,
    last_accessed REAL DEFAULT 0, access_count INTEGER DEFAULT 0
);
CREATE TABLE concepts (id TEXT PRIMARY KEY, name TEXT, created_at REAL DEFAULT 0);
CREATE TABLE memories (
    id TEXT PRIMARY KEY, group_id TEXT DEFAULT '', content TEXT,
    details TEXT DEFAULT '', emotion TEXT DEFAULT '', strength REAL DEFAULT 1,
    confidence REAL DEFAULT 0.8, created_at REAL DEFAULT 0,
    last_accessed REAL DEFAULT 0, access_count INTEGER DEFAULT 0,
    participants TEXT DEFAULT '', tags TEXT DEFAULT '', concept_id TEXT DEFAULT ''
);
CREATE TABLE element_memories (
    memory_id TEXT, element_id TEXT, role TEXT DEFAULT '', detail TEXT DEFAULT ''
);
CREATE TABLE connections (
    from_element TEXT, to_element TEXT, strength REAL DEFAULT 0, updated_at REAL DEFAULT 0
);
CREATE TABLE open_topics (
    id TEXT PRIMARY KEY, group_id TEXT DEFAULT '', topic TEXT,
    created_at REAL DEFAULT 0, summary TEXT DEFAULT ''
);
"""


def _legacy_conn(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(LEGACY_DDL)
    return conn


class TestMapScope:
    def test_cases(self):
        assert migrate_mod.map_scope("") == "default"
        assert migrate_mod.map_scope("pm:123") == "u:123"
        assert migrate_mod.map_scope("private:5") == "u:5"
        assert migrate_mod.map_scope("g1") == "g1"
        assert migrate_mod.map_scope("_x") == "x"


class TestDiscover:
    def test_discovers_dbs_skips_embeddings(self, tmp_path):
        (tmp_path / "memory.db").write_bytes(b"")
        (tmp_path / "memory_group_A.db").write_bytes(b"")
        (tmp_path / "memory.db_embeddings").write_bytes(b"")
        found = migrate_mod.discover_v1_dbs(str(tmp_path))
        assert len(found) == 2
        assert any(s == "file:A" for _, s in found)
        assert any(p.endswith("memory.db") for p, _ in found)
        assert not any("embeddings" in p for p, _ in found)


def _populate_main_db(conn: sqlite3.Connection, now: float) -> None:
    conn.executemany(
        "INSERT INTO elements (id, name, category, group_id) VALUES (?,?,?,?)",
        [("e1", "张三", "person", ""), ("e2", "火锅", "object", "")],
    )
    conn.executemany(
        "INSERT INTO concepts (id, name) VALUES (?,?)",
        [("c1", "Imprint:g1:李四"), ("c2", "钓鱼，周末常去")],
    )
    conn.executemany(
        """INSERT INTO memories (id, group_id, content, details, emotion, strength,
               created_at, last_accessed, access_count, participants, tags, concept_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        [
            ("m1", "", "和张三吃了火锅", "", "", 1.0, now, now, 1, "", "", ""),
            ("m2", "", "张三人很靠谱", "", "印象", 0.8, now, now, 0, "", "", ""),
            ("m3", "", "聊到钓鱼", "", "", 0.9, now, now, 0, "", "", "c2"),
        ],
    )
    conn.executemany(
        "INSERT INTO element_memories (memory_id, element_id, role) VALUES (?,?,?)",
        [("m1", "e1", "subject"), ("m1", "e2", ""),
         ("m2", "e1", "impression")],
    )
    conn.execute(
        "INSERT INTO connections (from_element, to_element, strength) VALUES ('e1','e2',1)"
    )
    conn.execute(
        "INSERT INTO open_topics (id, group_id, topic, created_at, summary) VALUES (?,?,?,?,?)",
        ("ot1", "g1", "周末去哪玩", now, "待定"),
    )


class TestMigrate:
    def test_full_migration(self, tmp_path):
        now = time.time()
        main_db = tmp_path / "memory.db"
        conn = _legacy_conn(str(main_db))
        _populate_main_db(conn, now)
        conn.commit()
        conn.close()

        repo = repo_mod.MemoryRepository(str(tmp_path / "memora.db"))
        try:
            stats = migrate_mod.migrate_v1(str(tmp_path), repo)
            assert stats["dbs"] == 1

            # 普通记忆迁移（scope: group_id='' → default），要素链接保留
            m1 = repo.get_memory("m1")
            assert m1 is not None and m1.scope_id == "default"
            links = repo.get_memory_elements("m1")
            names = {e.name for e, _ in links}
            assert names == {"张三", "火锅"}

            # 印象记忆：emotion=印象 + role=impression → impressions 表，不再是记忆
            assert repo.get_memory("m2") is None
            imp = repo.get_impression("default", "张三")
            assert imp is not None and imp.score == 0.8
            assert imp.summary == "张三人很靠谱"

            # concept 链接的记忆仍保留；Imprint concept → person element + 默认印象
            assert repo.get_memory("m3") is not None
            imp2 = repo.get_impression("g1", "李四")
            assert imp2 is not None and imp2.score == 0.5

            # trait concept → element（取主要名）
            trait = [e for e in repo.list_elements("default") if e.name == "钓鱼"]
            assert len(trait) == 1 and trait[0].category == "trait"

            # 旧 connections 丢弃
            assert repo.list_connections("default") == []

            # open_topics → sessions(open_question)
            sessions = repo.list_sessions("g1")
            assert len(sessions) == 1 and sessions[0].status == "open_question"
            assert sessions[0].topic == "周末去哪玩"

            # 备份文件生成 + 幂等标记
            assert (tmp_path / "memory.db.v1_backup").exists()
            assert repo.get_meta("v1_migrated") == "1"

            # 幂等：二次运行不再迁移
            stats2 = migrate_mod.migrate_v1(str(tmp_path), repo)
            assert stats2 == {"dbs": 0, "memories": 0, "impressions": 0, "sessions": 0}
        finally:
            repo.close()

    def test_group_db_scope_from_filename(self, tmp_path):
        now = time.time()
        group_db = tmp_path / "memory_group_G1.db"
        conn = _legacy_conn(str(group_db))
        conn.execute(
            """INSERT INTO memories (id, group_id, content, strength,
                   created_at, last_accessed, participants, tags)
               VALUES ('gm1', 'whatever', '群里的记忆', 1.0, ?, ?, '王五,赵六', '工作')""",
            (now, now),
        )
        conn.commit()
        conn.close()

        repo = repo_mod.MemoryRepository(str(tmp_path / "memora.db"))
        try:
            stats = migrate_mod.migrate_v1(str(tmp_path), repo)
            assert stats["memories"] == 1
            m = repo.get_memory("gm1")
            assert m is not None
            # 文件名优先于列值；participants/tags 合并进 participants
            assert m.scope_id == "G1"
            assert m.participants == ["王五", "赵六", "工作"]
        finally:
            repo.close()

    def test_expired_open_topics_dropped(self, tmp_path):
        now = time.time()
        stale = now - 30 * 86400
        group_db = tmp_path / "memory_group_G9.db"
        conn = _legacy_conn(str(group_db))
        conn.executemany(
            "INSERT INTO open_topics (id, group_id, topic, created_at) VALUES (?,?,?,?)",
            [("old1", "", "过期话题", stale), ("new1", "", "新鲜话题", now)],
        )
        conn.commit()
        conn.close()

        repo = repo_mod.MemoryRepository(str(tmp_path / "memora.db"))
        try:
            stats = migrate_mod.migrate_v1(str(tmp_path), repo, retention_days=7)
            assert stats["sessions"] == 1
            assert repo.list_sessions("G9")[0].topic == "新鲜话题"
        finally:
            repo.close()

    def test_no_v1_dbs_is_noop(self, tmp_path):
        repo = repo_mod.MemoryRepository(str(tmp_path / "memora.db"))
        try:
            stats = migrate_mod.migrate_v1(str(tmp_path), repo)
            assert stats["dbs"] == 0
            assert repo.get_meta("v1_migrated") == "1"
        finally:
            repo.close()
