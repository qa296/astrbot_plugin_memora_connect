"""Memora Connect v2 存储层 - SQLite schema 定义与初始化。
"""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 2

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS memories (
    id            TEXT PRIMARY KEY,
    scope_id      TEXT NOT NULL,
    content       TEXT NOT NULL,
    details       TEXT NOT NULL DEFAULT '',
    emotion       TEXT NOT NULL DEFAULT '',
    participants  TEXT NOT NULL DEFAULT '[]',
    embedding     BLOB,
    strength      REAL NOT NULL DEFAULT 1.0,
    created_at    REAL NOT NULL,
    last_accessed REAL NOT NULL,
    access_count  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_memories_scope_time
    ON memories (scope_id, created_at DESC);

CREATE TABLE IF NOT EXISTS elements (
    id            TEXT PRIMARY KEY,
    scope_id      TEXT NOT NULL,
    name          TEXT NOT NULL,
    category      TEXT NOT NULL,
    created_at    REAL NOT NULL,
    last_accessed REAL NOT NULL,
    access_count  INTEGER NOT NULL DEFAULT 0,
    UNIQUE (scope_id, name)
);
CREATE INDEX IF NOT EXISTS idx_elements_scope ON elements (scope_id);

CREATE TABLE IF NOT EXISTS memory_elements (
    memory_id  TEXT NOT NULL,
    element_id TEXT NOT NULL,
    role       TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (memory_id, element_id)
);
CREATE INDEX IF NOT EXISTS idx_memory_elements_element
    ON memory_elements (element_id);
CREATE INDEX IF NOT EXISTS idx_memory_elements_memory
    ON memory_elements (memory_id);

CREATE TABLE IF NOT EXISTS connections (
    from_element TEXT NOT NULL,
    to_element   TEXT NOT NULL,
    relation     TEXT NOT NULL DEFAULT '',
    updated_at   REAL NOT NULL,
    PRIMARY KEY (from_element, to_element)
);

CREATE TABLE IF NOT EXISTS impressions (
    scope_id   TEXT NOT NULL,
    subject    TEXT NOT NULL,
    score      REAL NOT NULL DEFAULT 0.5,
    summary    TEXT NOT NULL DEFAULT '',
    updated_at REAL NOT NULL,
    PRIMARY KEY (scope_id, subject)
);

CREATE TABLE IF NOT EXISTS sessions (
    id         TEXT PRIMARY KEY,
    scope_id   TEXT NOT NULL,
    topic      TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'ongoing',
    rounds     INTEGER NOT NULL DEFAULT 0,
    summary    TEXT NOT NULL DEFAULT '',
    keywords   TEXT NOT NULL DEFAULT '[]',
    emotion    TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_scope_status
    ON sessions (scope_id, status);

CREATE TABLE IF NOT EXISTS raw_messages (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    scope_id    TEXT NOT NULL,
    content     TEXT NOT NULL,
    sender_id   TEXT NOT NULL DEFAULT '',
    sender_name TEXT NOT NULL DEFAULT '',
    ts          REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_raw_messages_scope
    ON raw_messages (scope_id);
"""


def _try_create_fts(conn: sqlite3.Connection) -> bool:
    """创建 FTS5 trigram 检索表；返回是否可用（缺失时仓储降级 LIKE）。"""
    try:
        conn.execute("DROP TABLE IF EXISTS memories_fts")
        conn.execute(
            """
            CREATE VIRTUAL TABLE memories_fts USING fts5 (
                mem_id UNINDEXED,
                content,
                tokenize='trigram'
            )
            """
        )
        return True
    except sqlite3.Error:
        return False


def has_fts(conn: sqlite3.Connection) -> bool:
    """检测 memories_fts 表是否存在且可查询。"""
    if conn is None:
        return False
    try:
        conn.execute("SELECT 1 FROM memories_fts LIMIT 1")
        return True
    except sqlite3.Error:
        return False


def apply_schema(conn: sqlite3.Connection) -> None:
    """创建全部表/索引/FTS，并写入 schema_version（幂等）。"""
    conn.executescript(SCHEMA_SQL)
    fts_ok = _try_create_fts(conn)
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('fts_enabled', ?)",
        ("1" if fts_ok else "0",),
    )
    conn.commit()
