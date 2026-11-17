"""
一次性迁移：v1 多库（memory.db + memory_group_*.db）→ v2 单库 scope 列。

- 群库文件名 → scope；group_id="" → "default"；pm:/private: 前缀 → u:<id>
- 印象型记忆（role='impression' 且 emotion='印象'）转入 impressions，退出普通记忆
- Imprint:{g}:{人名} → person element + 默认印象 0.5；普通 concepts → trait element
- 旧 connections 全部丢弃（无 relation 语义，由后续 LLM 提取重建）
- 迁移前复制源库为 *.v1_backup；完成写 meta.v1_migrated 保证幂等
"""

from __future__ import annotations

import os
import re
import shutil
import sqlite3
import time

from ..domain.models import CATEGORIES, Memory, Session
from .repository import MemoryRepository

GROUP_DB_PREFIX = "memory_group_"
LEGACY_IMPRINT_RE = re.compile(r"^Imprint:(.*?):(.+)$")


def map_scope(raw: str) -> str:
    """旧范围标识 → v2 scope_id。"""
    raw = (raw or "").strip()
    if not raw:
        return "default"
    if raw.startswith("pm:") or raw.startswith("private:"):
        return f"u:{raw.split(':', 1)[1]}"
    return raw.lstrip("_")


def _map_category(category) -> str:
    category = (category or "").strip() if isinstance(category, str) else ""
    return category if category in CATEGORIES else "trait"


def discover_v1_dbs(data_dir: str) -> list[tuple[str, str]]:
    """返回 [(db_path, scope_source)]；scope_source 为 'file:<gid>' 或 'column'。"""
    result: list[tuple[str, str]] = []
    if not os.path.isdir(data_dir):
        return result
    for name in sorted(os.listdir(data_dir)):
        if not name.endswith(".db"):
            continue
        if name.startswith(GROUP_DB_PREFIX):
            gid = name[len(GROUP_DB_PREFIX) : -len(".db")].lstrip("_")
            result.append((os.path.join(data_dir, name), f"file:{gid}"))
        elif name == "memory.db":
            result.append((os.path.join(data_dir, name), "column"))
        elif name.endswith(".db_embeddings"):
            continue
    return result


def _backup(db_path: str) -> None:
    backup = db_path + ".v1_backup"
    if not os.path.exists(backup):
        shutil.copy2(db_path, backup)


def _open_source(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info('{table}')").fetchall()]


def _scope_of_row(scope_source: str, raw_gid) -> str:
    if scope_source.startswith("file:"):
        return map_scope(scope_source.split("file:", 1)[1])
    return map_scope(raw_gid)


def _load_old_elements(conn, tables, scope_source, repo: MemoryRepository, now):
    """旧 elements 表 → 新 elements。返回 old_id → (new_element_id, scope)。"""
    mapping: dict[str, tuple[str, str]] = {}
    if "elements" not in tables:
        return mapping
    ecols = _columns(conn, "elements")
    gid_col = "group_id" if "group_id" in ecols else None
    sql = (
        'SELECT id, name, category, "group_id" AS gid FROM elements'
        if gid_col
        else "SELECT id, name, category, '' AS gid FROM elements"
    )
    for r in conn.execute(sql):
        old_id, name = str(r["id"]), str(r["name"] or "").strip()
        if not name:
            continue
        scope = _scope_of_row(scope_source, r["gid"]) if gid_col else _scope_of_row(
            scope_source, ""
        )
        elem = repo.get_or_create_element(
            scope, name, _map_category(r["category"]), now
        )
        mapping[str(old_id)] = (elem.id, scope)
    return mapping


def _load_old_concepts(conn, tables, scope_source, repo: MemoryRepository, now):
    """旧 concepts → person/trait elements；Imprint 型同时写默认印象。"""
    mapping: dict[str, tuple[str, str]] = {}
    if "concepts" not in tables:
        return mapping
    for r in conn.execute("SELECT id, name FROM concepts"):
        concept_id = str(r["id"])
        name = str(r["name"] or "").strip()
        if not name:
            continue
        m = LEGACY_IMPRINT_RE.match(name)
        if m:
            gid, person = m.group(1).strip(), m.group(2).strip()
            scope = map_scope(gid)
            elem = repo.get_or_create_element(scope, person, "person", now)
            if not repo.get_impression(scope, person):
                repo.upsert_impression(scope, person, 0.5, "", now)
            mapping[concept_id] = (elem.id, scope)
            continue
        scope = _scope_of_row(scope_source, "")
        primary = name.split("，")[0].split(",")[0].strip() or name
        elem = repo.get_or_create_element(scope, primary, "trait", now)
        mapping[concept_id] = (elem.id, scope)
    return mapping


def _load_old_memories(conn, tables, scope_source, repo: MemoryRepository, now,
                       element_map, concept_map, stats: dict[str, int]) -> int:
    """迁移 memories；印象型记忆转入 impressions，退出普通记忆存储。"""
    mcols = _columns(conn, "memories")
    count = 0
    has_impression_links = "element_memories" in tables
    for r in conn.execute("SELECT * FROM memories"):
        try:
            mem_id = str(r["id"]).strip()
            content = str(r["content"] or "").strip()
            details = str(r["details"] or "")
            emotion = str(r["emotion"] or "")
            raw_gid = r["group_id"] if "group_id" in mcols else ""
            scope = _scope_of_row(scope_source, raw_gid)
            strength = float(r["strength"] or 1.0)
            created_at = float(r["created_at"] or now)
            last_accessed = float(r["last_accessed"] or created_at)
            access_count = int(r["access_count"] or 0)
        except (KeyError, TypeError, ValueError):
            continue

        participants: list[str] = []
        if "participants" in mcols and r["participants"]:
            participants.extend(
                p.strip()
                for p in str(r["participants"]).replace("，", ",").split(",")
                if p.strip()
            )
        if "tags" in mcols and r["tags"]:
            participants.extend(
                t.strip()
                for t in str(r["tags"]).replace("，", ",").split(",")
                if t.strip() and t.strip() not in participants
            )

        links: list[tuple[str, str]] = []
        if has_impression_links:
            for lr in conn.execute(
                "SELECT element_id, role FROM element_memories WHERE memory_id = ?",
                (mem_id,),
            ):
                target = element_map.get(str(lr["element_id"]))
                if target:
                    links.append((target[0], str(lr["role"] or "")))

        is_impression = emotion == "印象" and any(
            role in ("impression", "subject") for _, role in links
        )
        if is_impression:
            subject = ""
            for elem_id, role in links:
                if role != "subject":
                    continue
                elem = repo.get_element(elem_id)
                if elem:
                    subject = elem.name
                    break
            if not subject:
                for elem_id, role in links:
                    if role == "impression":
                        elem = repo.get_element(elem_id)
                        if elem:
                            subject = elem.name
                            break
            if not subject and participants:
                subject = participants[0]
            if subject:
                repo.upsert_impression(
                    scope, subject, max(0.0, min(1.0, strength)), content, last_accessed
                )
                stats["impressions"] += 1
            continue

        if not content:
            continue

        memory = Memory(
            id=mem_id,
            scope_id=scope,
            content=content,
            details=details,
            emotion=emotion,
            participants=participants,
            strength=max(0.05, min(1.0, strength)),
            created_at=created_at,
            last_accessed=last_accessed,
            access_count=access_count,
        )
        repo.upsert_memory(memory)
        for elem_id, role in links:
            repo.link_memory_element(memory.id, elem_id, role)
        legacy_cid = str(r["concept_id"]) if (
            "concept_id" in mcols and r["concept_id"]
        ) else None
        if legacy_cid and legacy_cid in concept_map:
            repo.link_memory_element(memory.id, concept_map[legacy_cid][0], "")
        count += 1
    return count


def _load_open_topics(conn, tables, scope_source, repo: MemoryRepository, now,
                      retention_days: int, stats: dict[str, int]) -> None:
    """旧 open_topics → v2 sessions(open_question)，过期的直接舍弃。"""
    if "open_topics" not in tables:
        return
    ocols = _columns(conn, "open_topics")
    cutoff_date = now - max(1, retention_days) * 86400
    for r in conn.execute("SELECT * FROM open_topics"):
        try:
            created_at = float(r["created_at"] or 0) or now
        except (TypeError, ValueError):
            created_at = now
        if created_at < cutoff_date:
            continue
        row_id = str(r["id"]) if "id" in ocols and r["id"] is not None else None
        if not row_id:
            continue
        topic = str(r["topic"] or r["question"] or "").strip() or "未闭合话题"
        raw_gid = r["group_id"] if "group_id" in ocols else ""
        scope = _scope_of_row(scope_source, raw_gid)
        summary = ""
        if "summary" in ocols:
            summary = str(r["summary"] or "")
        stats["sessions"] += 1
        repo.upsert_session(
            Session(
                id=f"ot_{row_id}",
                scope_id=scope,
                topic=topic,
                status="open_question",
                summary=summary,
                created_at=created_at,
                updated_at=now,
            )
        )


def migrate_v1(data_dir: str, repo: MemoryRepository,
               retention_days: int = 7) -> dict[str, int]:
    """把 data_dir 下的所有 v1 库迁入 repo。返回统计（dbs/memories/impressions/sessions）。"""
    stats = {"dbs": 0, "memories": 0, "impressions": 0, "sessions": 0}
    if repo.get_meta("v1_migrated"):
        return stats
    now = time.time()
    for db_path, scope_source in discover_v1_dbs(data_dir):
        _backup(db_path)
        conn = _open_source(db_path)
        try:
            tables = _table_names(conn)
            element_map = _load_old_elements(conn, tables, scope_source, repo, now)
            concept_map = _load_old_concepts(conn, tables, scope_source, repo, now)
            if "memories" in tables:
                stats["memories"] += _load_old_memories(
                    conn, tables, scope_source, repo, now,
                    element_map, concept_map, stats,
                )
            _load_open_topics(
                conn, tables, scope_source, repo, now, retention_days, stats
            )
            stats["dbs"] += 1
        finally:
            conn.close()
    repo.set_meta("v1_migrated", "1")
    repo.set_meta("v1_migrated_at", str(int(now)))
    return stats
