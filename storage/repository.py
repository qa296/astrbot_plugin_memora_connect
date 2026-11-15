"""
Memora v2 存储仓储层：SQLite 唯一事实源的唯一读写门户。

单连接 + 进程内 RLock 串行化（SQLite 单写者模型），全部方法同步；
应用层用 asyncio.to_thread 调度。FTS5 trigram 缺失时自动降级 LIKE。
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid

from ..domain.models import (
    CATEGORIES,
    Element,
    Impression,
    Memory,
    Session,
)
from . import schema

DEFAULT_IMPRESSION_SCORE = 0.5


def new_id(prefix: str) -> str:
    """生成带前缀的 uuid id。"""
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


class MemoryRepository:
    """Memora v2 记忆仓储（每个插件实例一份，绑定一个数据库文件）。"""

    def __init__(self, db_path: str, *,
                 raw_cap: int = 200,
                 created_at: float | None = None):
        self.db_path = str(db_path)
        self.raw_cap = max(50, int(raw_cap))
        self.fts_enabled = False
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        init_ts = time.time() if created_at is None else created_at
        self._open(init_ts)

    def _open(self, now: float) -> None:
        with self._lock:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.isolation_level = None  # 手动管理事务
            fts_before = schema.has_fts(self._conn)
            schema.apply_schema(self._conn)
            self.fts_enabled = schema.has_fts(self._conn)
            if not fts_before and self.fts_enabled:
                self._rebuild_fts()

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.commit()
                except sqlite3.Error:
                    pass
                self._conn.close()
                self._conn = None

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """在锁内提交写事务。"""
        conn = self._conn
        if conn is None:
            raise RuntimeError("repository closed")
        with self._lock:
            try:
                cur = conn.execute(sql, params)
                conn.commit()
                return cur
            except Exception:
                try:
                    conn.rollback()
                except sqlite3.Error:
                    pass
                raise

    def _query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        """在锁内执行只读查询。"""
        conn = self._conn
        if conn is None:
            raise RuntimeError("repository closed")
        with self._lock:
            return conn.execute(sql, params).fetchall()

    def get_meta(self, key: str, default: str = "") -> str:
        rows = self._query("SELECT value FROM meta WHERE key = ?", (key,))
        return rows[0]["value"] if rows else default

    def set_meta(self, key: str, value: str) -> None:
        self._execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value)
        )

    def delete_meta(self, key: str) -> bool:
        cur = self._execute("DELETE FROM meta WHERE key = ?", (key,))
        return cur.rowcount > 0

    def list_scopes(self) -> list[str]:
        """所有出现过数据的 scope_id（memories/elements/impressions 并集）。"""
        rows = self._query(
            """
            SELECT DISTINCT scope_id FROM memories
            UNION SELECT DISTINCT scope_id FROM elements
            UNION SELECT DISTINCT scope_id FROM impressions
            """
        )
        return [r[0] or "" for r in rows]

    def upsert_memory(self, memory: Memory) -> None:
        self._execute(
            """
            INSERT INTO memories
                (id, scope_id, content, details, emotion, participants,
                 embedding, strength, created_at, last_accessed, access_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                content=excluded.content,
                details=excluded.details,
                emotion=excluded.emotion,
                participants=excluded.participants,
                embedding=excluded.embedding,
                strength=excluded.strength,
                last_accessed=excluded.last_accessed,
                access_count=excluded.access_count
            """,
            (
                memory.id,
                memory.scope_id,
                memory.content,
                memory.details,
                memory.emotion,
                json.dumps(memory.participants, ensure_ascii=False),
                memory.embedding,
                memory.strength,
                memory.created_at,
                memory.last_accessed,
                memory.access_count,
            ),
        )
        self._fts_replace(memory.id, memory.content)

    def delete_memory(self, memory_id: str) -> bool:
        cur = self._execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        self._execute("DELETE FROM memory_elements WHERE memory_id = ?", (memory_id,))
        self._execute("DELETE FROM memories_fts WHERE mem_id = ?", (memory_id,))
        return cur.rowcount > 0

    def get_memory(self, memory_id: str) -> Memory | None:
        rows = self._query("SELECT * FROM memories WHERE id = ?", (memory_id,))
        return self._row_to_memory(rows[0]) if rows else None

    def get_memories_by_ids(self, memory_ids: list[str]) -> list[Memory]:
        """批量按 id 取记忆（保持传入顺序，缺失的跳过）。"""
        ids = [i for i in memory_ids if i]
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        rows = self._query(
            f"SELECT * FROM memories WHERE id IN ({placeholders})", tuple(ids)
        )
        by_id = {r["id"]: self._row_to_memory(r) for r in rows}
        return [by_id[i] for i in ids if i in by_id]

    def list_memories(
        self,
        scope_id: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> list[Memory]:
        rows = self._query(
            """
            SELECT * FROM memories WHERE scope_id = ?
            ORDER BY created_at DESC LIMIT ? OFFSET ?
            """,
            (scope_id, max(0, limit), max(0, offset)),
        )
        return [self._row_to_memory(r) for r in rows]

    def search_memories_by_like(
        self,
        scope_id: str,
        term: str,
        limit: int = 50,
    ) -> list[Memory]:
        rows = self._query(
            """
            SELECT * FROM memories
            WHERE scope_id = ? AND (content LIKE ? OR details LIKE ?)
            ORDER BY created_at DESC LIMIT ?
            """,
            (scope_id, f"%{term}%", f"%{term}%", max(1, limit)),
        )
        return [self._row_to_memory(r) for r in rows]

    def ids_from_fts(self, terms_match: str, scope_id: str, limit: int = 50) -> list[str]:
        """FTS 命中的候选 id（按 rank 排序），跨 scope 由外层过滤。"""
        if not self.fts_enabled or not terms_match:
            return []
        try:
            rows = self._query(
                """
                SELECT f.mem_id AS mem_id
                FROM memories_fts f
                JOIN memories m ON m.id = f.mem_id
                WHERE memories_fts MATCH ? AND m.scope_id = ?
                ORDER BY rank
                LIMIT ?
                """,
                (terms_match, scope_id, max(1, limit)),
            )
        except sqlite3.Error:
            return []
        return [r["mem_id"] for r in rows]

    def touch_memory(self, memory_id: str, now: float) -> None:
        self._execute(
            """
            UPDATE memories
            SET last_accessed = ?, access_count = access_count + 1
            WHERE id = ?
            """,
            (now, memory_id),
        )

    def update_memory_fields(
        self,
        memory_id: str,
        *,
        content: str | None = None,
        details: str | None = None,
        emotion: str | None = None,
        strength: float | None = None,
    ) -> bool:
        sets: list[str] = []
        params: list[object] = []
        if content is not None:
            sets.append("content = ?")
            params.append(content)
        if details is not None:
            sets.append("details = ?")
            params.append(details)
        if emotion is not None:
            sets.append("emotion = ?")
            params.append(emotion)
        if strength is not None:
            sets.append("strength = ?")
            params.append(float(strength))
        if not sets:
            return False
        params.append(memory_id)
        cur = self._execute(
            f"UPDATE memories SET {', '.join(sets)} WHERE id = ?", tuple(params)
        )
        if content is not None and cur.rowcount:
            self._fts_replace(memory_id, content)
        return cur.rowcount > 0

    def count_memories(self, scope_id: str = "") -> int:
        rows = self._query(
            "SELECT COUNT(*) AS n FROM memories WHERE scope_id = ?", (scope_id,)
        )
        return int(rows[0]["n"]) if rows else 0

    def _row_to_memory(self, row: sqlite3.Row) -> Memory:
        try:
            participants = json.loads(row["participants"])
        except (TypeError, ValueError):
            participants = []
        return Memory(
            id=row["id"],
            scope_id=row["scope_id"],
            content=row["content"],
            details=row["details"],
            emotion=row["emotion"],
            participants=participants if isinstance(participants, list) else [],
            embedding=row["embedding"],
            strength=float(row["strength"]),
            created_at=float(row["created_at"]),
            last_accessed=float(row["last_accessed"]),
            access_count=int(row["access_count"]),
        )

    def _fts_replace(self, mem_id: str, content: str) -> None:
        if not self.fts_enabled:
            return
        try:
            self._execute(
                "DELETE FROM memories_fts WHERE mem_id = ?", (mem_id,)
            )
            self._execute(
                "INSERT INTO memories_fts (mem_id, content) VALUES (?, ?)",
                (mem_id, content),
            )
        except sqlite3.Error:
            # FTS 同步失败时静默跳过
            pass

    def _rebuild_fts(self) -> None:
        """从 memories 表重建 FTS 索引（初始化或缺表时）。"""
        if not self.fts_enabled:
            return
        try:
            self._execute("DELETE FROM memories_fts")
            self._execute(
                "INSERT INTO memories_fts (mem_id, content) SELECT id, content FROM memories"
            )
        except sqlite3.Error:
            pass

    def get_or_create_element(
        self,
        scope_id: str,
        name: str,
        category: str,
        now: float,
    ) -> Element:
        name = name.strip()
        if category not in CATEGORIES:
            category = "trait"
        rows = self._query(
            "SELECT * FROM elements WHERE scope_id = ? AND name = ?",
            (scope_id, name),
        )
        if rows:
            row = rows[0]
            if row["category"] != category:
                self._execute(
                    "UPDATE elements SET category = ? WHERE id = ?", (category, row["id"])
                )
            return Element(
                id=row["id"],
                scope_id=scope_id,
                name=name,
                category=category,
                created_at=float(row["created_at"]),
                last_accessed=float(row["last_accessed"]),
                access_count=int(row["access_count"]),
            )
        element = Element(
            id=new_id("elem"),
            scope_id=scope_id,
            name=name,
            category=category,
            created_at=now,
            last_accessed=now,
        )
        self._execute(
            """
            INSERT INTO elements
                (id, scope_id, name, category, created_at, last_accessed, access_count)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (element.id, scope_id, name, category, now, now),
        )
        return element

    def get_element(self, element_id: str) -> Element | None:
        rows = self._query("SELECT * FROM elements WHERE id = ?", (element_id,))
        if not rows:
            return None
        r = rows[0]
        return Element(
            id=r["id"],
            scope_id=r["scope_id"],
            name=r["name"],
            category=r["category"],
            created_at=float(r["created_at"]),
            last_accessed=float(r["last_accessed"]),
            access_count=int(r["access_count"]),
        )

    def list_elements(self, scope_id: str = "") -> list[Element]:
        if scope_id:
            rows = self._query(
                "SELECT * FROM elements WHERE scope_id = ? ORDER BY access_count DESC",
                (scope_id,),
            )
        else:
            rows = self._query("SELECT * FROM elements")
        return [
            Element(
                id=r["id"],
                scope_id=r["scope_id"],
                name=r["name"],
                category=r["category"],
                created_at=float(r["created_at"]),
                last_accessed=float(r["last_accessed"]),
                access_count=int(r["access_count"]),
            )
            for r in rows
        ]

    def rename_element(self, element_id: str, new_name: str) -> bool:
        cur = self._execute(
            "UPDATE elements SET name = ? WHERE id = ?", (new_name.strip(), element_id)
        )
        return cur.rowcount > 0

    def delete_element(self, element_id: str) -> bool:
        cur = self._execute("DELETE FROM elements WHERE id = ?", (element_id,))
        self._execute("DELETE FROM memory_elements WHERE element_id = ?", (element_id,))
        self._execute(
            "DELETE FROM connections WHERE from_element = ? OR to_element = ?",
            (element_id, element_id),
        )
        return cur.rowcount > 0

    def link_memory_element(self, memory_id: str, element_id: str, role: str = "") -> None:
        self._execute(
            """
            INSERT OR REPLACE INTO memory_elements (memory_id, element_id, role)
            VALUES (?, ?, ?)
            """,
            (memory_id, element_id, role),
        )

    def get_memory_elements(self, memory_id: str) -> list[tuple[Element, str]]:
        rows = self._query(
            """
            SELECT e.id, e.scope_id, e.name, e.category, e.created_at,
                   e.last_accessed, e.access_count, me.role
            FROM memory_elements me
            JOIN elements e ON e.id = me.element_id
            WHERE me.memory_id = ?
            """,
            (memory_id,),
        )
        return [
            (
                Element(
                    id=r["id"],
                    scope_id=r["scope_id"],
                    name=r["name"],
                    category=r["category"],
                    created_at=float(r["created_at"]),
                    last_accessed=float(r["last_accessed"]),
                    access_count=int(r["access_count"]),
                ),
                r["role"],
            )
            for r in rows
        ]

    def get_element_memories(self, element_id: str, limit: int = 50) -> list[Memory]:
        rows = self._query(
            """
            SELECT m.* FROM memory_elements me
            JOIN memories m ON m.id = me.memory_id
            WHERE me.element_id = ?
            ORDER BY m.created_at DESC LIMIT ?
            """,
            (element_id, max(1, limit)),
        )
        return [self._row_to_memory(r) for r in rows]

    @staticmethod
    def canonical_edge(a: str, b: str) -> tuple[str, str]:
        return (a, b) if a < b else (b, a)

    def upsert_connection(self, from_element: str, to_element: str,
                          relation: str, now: float) -> None:
        lo, hi = self.canonical_edge(from_element, to_element)
        self._execute(
            """
            INSERT INTO connections (from_element, to_element, relation, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(from_element, to_element) DO UPDATE SET
                relation = excluded.relation,
                updated_at = excluded.updated_at
            """,
            (lo, hi, relation, now),
        )

    def delete_connection(self, from_element: str, to_element: str) -> bool:
        lo, hi = self.canonical_edge(from_element, to_element)
        cur = self._execute(
            "DELETE FROM connections WHERE from_element = ? AND to_element = ?",
            (lo, hi),
        )
        return cur.rowcount > 0

    def list_connections(self, scope_id: str = "") -> list[dict]:
        if scope_id:
            rows = self._query(
                """
                SELECT c.from_element, c.to_element, c.relation, c.updated_at
                FROM connections c
                JOIN elements e ON e.id = c.from_element
                WHERE e.scope_id = ?
                """,
                (scope_id,),
            )
        else:
            rows = self._query(
                "SELECT from_element, to_element, relation, updated_at FROM connections"
            )
        return [
            {
                "from_element": r["from_element"],
                "to_element": r["to_element"],
                "relation": r["relation"],
                "updated_at": float(r["updated_at"]),
            }
            for r in rows
        ]

    def neighbor_elements(self, element_ids: set[str]) -> set[str]:
        """返回与给定元素有一条边相连的新邻居（结果排除输入集合本身）。"""
        if not element_ids:
            return set()
        chunks: list[str] = []
        params: list[object] = list(element_ids)
        placeholders = ",".join("?" for _ in element_ids)
        chunks.append(
            f"SELECT to_element AS n FROM connections WHERE from_element IN ({placeholders})"
        )
        chunks.append(
            f"SELECT from_element AS n FROM connections WHERE to_element IN ({placeholders})"
        )
        sql = " UNION ".join(chunks)
        rows = self._query(sql, tuple(params) + tuple(params))
        neighbors = {r["n"] for r in rows} - set(element_ids)
        return neighbors

    def upsert_impression(
        self,
        scope_id: str,
        subject: str,
        score: float,
        summary: str,
        now: float,
    ) -> None:
        self._execute(
            """
            INSERT INTO impressions (scope_id, subject, score, summary, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(scope_id, subject) DO UPDATE SET
                score = excluded.score,
                summary = CASE WHEN excluded.summary != '' THEN excluded.summary ELSE impressions.summary END,
                updated_at = excluded.updated_at
            """,
            (scope_id, subject, max(0.0, min(1.0, float(score))), summary, now),
        )

    def adjust_impression(self, scope_id: str, subject: str, delta: float,
                          now: float) -> float:
        current = self.get_impression(scope_id, subject)
        base = current.score if current else DEFAULT_IMPRESSION_SCORE
        new_score = max(0.0, min(1.0, base + float(delta)))
        summary = current.summary if current else ""
        self.upsert_impression(scope_id, subject, new_score, summary, now)
        return new_score

    def get_impression(self, scope_id: str, subject: str) -> Impression | None:
        rows = self._query(
            "SELECT * FROM impressions WHERE scope_id = ? AND subject = ?",
            (scope_id, subject),
        )
        if not rows:
            return None
        r = rows[0]
        return Impression(
            scope_id=scope_id,
            subject=subject,
            score=float(r["score"]),
            summary=r["summary"],
            updated_at=float(r["updated_at"]),
        )

    def list_impressions(self, scope_id: str = "") -> list[Impression]:
        params: tuple = ()
        where = ""
        if scope_id:
            where = "WHERE scope_id = ?"
            params = (scope_id,)
        rows = self._query(
            f"SELECT * FROM impressions {where} ORDER BY updated_at DESC", params
        )
        return [
            Impression(
                scope_id=r["scope_id"],
                subject=r["subject"],
                score=float(r["score"]),
                summary=r["summary"],
                updated_at=float(r["updated_at"]),
            )
            for r in rows
        ]

    def upsert_session(self, session: Session) -> None:
        self._execute(
            """
            INSERT INTO sessions
                (id, scope_id, topic, status, rounds, summary, keywords,
                 emotion, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                topic = excluded.topic,
                status = excluded.status,
                rounds = excluded.rounds,
                summary = excluded.summary,
                keywords = excluded.keywords,
                emotion = excluded.emotion,
                updated_at = excluded.updated_at
            """,
            (
                session.id,
                session.scope_id,
                session.topic,
                session.status,
                session.rounds,
                session.summary,
                json.dumps(session.keywords, ensure_ascii=False),
                session.emotion,
                session.created_at,
                session.updated_at,
            ),
        )

    def get_session(self, session_id: str) -> Session | None:
        rows = self._query("SELECT * FROM sessions WHERE id = ?", (session_id,))
        if not rows:
            return None
        r = rows[0]
        try:
            keywords = json.loads(r["keywords"])
        except (TypeError, ValueError):
            keywords = []
        return Session(
            id=r["id"],
            scope_id=r["scope_id"],
            topic=r["topic"],
            status=r["status"],
            rounds=int(r["rounds"]),
            summary=r["summary"],
            keywords=keywords if isinstance(keywords, list) else [],
            emotion=r["emotion"],
            created_at=float(r["created_at"]),
            updated_at=float(r["updated_at"]),
        )

    def list_sessions(
        self,
        scope_id: str,
        status: str | None = None,
        limit: int = 20,
    ) -> list[Session]:
        if status is None:
            rows = self._query(
                """
                SELECT * FROM sessions WHERE scope_id = ?
                ORDER BY updated_at DESC LIMIT ?
                """,
                (scope_id, max(1, limit)),
            )
        else:
            rows = self._query(
                """
                SELECT * FROM sessions WHERE scope_id = ? AND status = ?
                ORDER BY updated_at DESC LIMIT ?
                """,
                (scope_id, status, max(1, limit)),
            )
        sessions = []
        for r in rows:
            try:
                keywords = json.loads(r["keywords"])
            except (TypeError, ValueError):
                keywords = []
            sessions.append(
                Session(
                    id=r["id"],
                    scope_id=r["scope_id"],
                    topic=r["topic"],
                    status=r["status"],
                    rounds=int(r["rounds"]),
                    summary=r["summary"],
                    keywords=keywords if isinstance(keywords, list) else [],
                    emotion=r["emotion"],
                    created_at=float(r["created_at"]),
                    updated_at=float(r["updated_at"]),
                )
            )
        return sessions

    def delete_session(self, session_id: str) -> bool:
        cur = self._execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        return cur.rowcount > 0

    def append_raw(
        self,
        scope_id: str,
        content: str,
        sender_id: str,
        sender_name: str,
        ts: float,
    ) -> int:
        cur = self._execute(
            """
            INSERT INTO raw_messages
                (scope_id, content, sender_id, sender_name, ts)
            VALUES (?, ?, ?, ?, ?)
            """,
            (scope_id, content, sender_id, sender_name, ts),
        )
        self.trim_raw(scope_id, self.raw_cap)
        return int(cur.lastrowid or 0)

    def trim_raw(self, scope_id: str, keep: int) -> None:
        self._execute(
            """
            DELETE FROM raw_messages
            WHERE scope_id = ? AND seq NOT IN (
                SELECT seq FROM raw_messages WHERE scope_id = ?
                ORDER BY seq DESC LIMIT ?
            )
            """,
            (scope_id, scope_id, max(1, keep)),
        )

    def list_raw(self, scope_id: str, limit: int = 200) -> list[dict]:
        rows = self._query(
            """
            SELECT seq, content, sender_id, sender_name, ts
            FROM raw_messages WHERE scope_id = ?
            ORDER BY seq ASC LIMIT ?
            """,
            (scope_id, max(1, limit)),
        )
        return [dict(r) for r in rows]

    def clear_raw(self, scope_id: str) -> None:
        self._execute("DELETE FROM raw_messages WHERE scope_id = ?", (scope_id,))

    def count_raw(self, scope_id: str) -> int:
        rows = self._query(
            "SELECT COUNT(*) AS n FROM raw_messages WHERE scope_id = ?", (scope_id,)
        )
        return int(rows[0]["n"]) if rows else 0

    def stats(self, scope_id: str = "") -> dict:
        params = (scope_id,) if scope_id else ()
        scope_where = "WHERE scope_id = ?" if scope_id else ""
        conn_where = (
            "WHERE from_element IN (SELECT id FROM elements WHERE scope_id = ?)"
            if scope_id
            else ""
        )
        def _count(table: str, where: str, p: tuple) -> int:
            rows = self._query(f"SELECT COUNT(*) AS n FROM {table} {where}", p)
            return int(rows[0]["n"]) if rows else 0
        return {
            "memories": _count("memories", scope_where, params),
            "elements": _count("elements", scope_where, params),
            "connections": _count("connections", conn_where, params),
            "impressions": _count("impressions", scope_where, params),
            "sessions": _count("sessions", scope_where, params),
        }
