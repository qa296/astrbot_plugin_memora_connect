"""
Plugin Pages 后端 API。前端 pages/memora-connect/ 未改动，本文件保证：
路由与响应 JSON 形状与 v1 兼容（group_id 即 scope_id，"" 视为 default）。
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

try:
    from astrbot.api import logger
    from astrbot.api.star import Context
except ImportError:  # 测试环境降级
    import logging

    logger = logging.getLogger(__name__)
    Context = None

try:
    from quart import jsonify, request
except ImportError:  # pragma: no cover - AstrBot 运行时一定有 quart
    jsonify = None
    request = None

from ..domain.models import CATEGORIES, Memory
from ..domain.models import score_verbal
from ..memory.visualization import prepare_graph_data
from ..storage.repository import MemoryRepository, new_id

PLUGIN_NAME = "astrbot_plugin_memora_connect"


def _scope_of(group_id: str) -> str:
    """Web 参数 group_id → scope_id（v1 的空串即默认空间）。"""
    return (group_id or "").strip() or "default"


class MemoryWebAPI:
    """注册到 AstrBot Dashboard 的 Plugin Page 后端 API。

    路由以 ``/<PLUGIN_NAME>/`` 为前缀；bridge SDK 只支持 GET/POST，
    因此 PUT/DELETE 操作统一改写为 POST，动作编码进路径（如 memories/update）。
    """

    def __init__(self, repo: MemoryRepository, context: "Context") -> None:
        self.repo = repo
        self.context = context

    def register(self) -> None:
        """向 Dashboard 注册全部 Web API 路由。"""
        c = self.context
        prefix = f"/{PLUGIN_NAME}"

        c.register_web_api(f"{prefix}/status", self.api_status, ["GET"], "记忆系统状态")
        c.register_web_api(f"{prefix}/groups", self.api_groups, ["GET"], "分组列表")
        c.register_web_api(f"{prefix}/graph", self.api_graph, ["GET"], "记忆图谱数据")

        c.register_web_api(f"{prefix}/concepts", self.api_concepts, ["GET"], "概念列表")
        c.register_web_api(f"{prefix}/concepts/create", self.api_create_concept, ["POST"], "创建概念")
        c.register_web_api(f"{prefix}/concepts/update", self.api_update_concept, ["POST"], "更新概念")
        c.register_web_api(f"{prefix}/concepts/delete", self.api_delete_concept, ["POST"], "删除概念")

        c.register_web_api(f"{prefix}/memories", self.api_memories, ["GET"], "记忆列表/搜索")
        c.register_web_api(f"{prefix}/memories/create", self.api_create_memory, ["POST"], "创建记忆")
        c.register_web_api(f"{prefix}/memories/update", self.api_update_memory, ["POST"], "更新记忆")
        c.register_web_api(f"{prefix}/memories/delete", self.api_delete_memory, ["POST"], "删除记忆")

        c.register_web_api(f"{prefix}/connections", self.api_connections, ["GET"], "连接列表")
        c.register_web_api(f"{prefix}/connections/create", self.api_create_connection, ["POST"], "创建连接")
        c.register_web_api(f"{prefix}/connections/update", self.api_update_connection, ["POST"], "更新连接")
        c.register_web_api(f"{prefix}/connections/delete", self.api_delete_connection, ["POST"], "删除连接")

        c.register_web_api(f"{prefix}/impressions", self.api_impressions, ["GET"], "印象列表")
        c.register_web_api(f"{prefix}/impressions/create", self.api_create_impression, ["POST"], "创建印象")
        c.register_web_api(f"{prefix}/impressions/adjust", self.api_adjust_impression, ["POST"], "调整好感度")

        logger.info("Memora Plugin Page API 已注册到 Dashboard")

    async def api_status(self):
        return jsonify(
            {
                "memory_enabled": True,
                "db_path": self.repo.db_path,
                "web_enabled": True,
            }
        )

    async def api_groups(self):
        groups = sorted({s for s in self.repo.list_scopes() if s})
        if "default" not in groups:
            groups = ["default"] + groups
        return jsonify({"groups": groups})

    async def api_graph(self):
        group_id = request.args.get("group_id", "")
        scope = _scope_of(group_id)
        try:
            data = await asyncio.to_thread(prepare_graph_data, self.repo, scope)
            if data.get("error"):
                return jsonify({"error": data["error"]}), 400
            return jsonify(data)
        except Exception as e:
            logger.error(f"获取图数据失败: {e}")
            return jsonify({"error": str(e)}), 500

    async def api_concepts(self):
        group_id = request.args.get("group_id", "")
        scope = _scope_of(group_id)
        concepts = [
            {
                "id": e.id,
                "name": e.name,
                "category": e.category,
                "access_count": e.access_count,
            }
            for e in self.repo.list_elements(scope)
        ]
        concepts.sort(key=lambda e: (e["category"], e["name"]))
        return jsonify({"concepts": concepts})

    async def api_create_concept(self):
        body = await request.get_json()
        name = (body.get("name") or "").strip()
        scope = _scope_of(body.get("group_id"))
        category = (body.get("category") or "trait").strip()
        if not name:
            return jsonify({"error": "name required"}), 400
        if category not in CATEGORIES:
            category = "trait"
        elem = self.repo.get_or_create_element(scope, name, category, time.time())
        return jsonify({"id": elem.id, "name": name, "category": category})

    async def api_update_concept(self):
        body = await request.get_json()
        element_id = body.get("id")
        new_name = (body.get("name") or "").strip()
        if not new_name:
            return jsonify({"error": "name required"}), 400
        if self.repo.rename_element(element_id, new_name):
            return jsonify({"ok": True})
        return jsonify({"error": "element not found"}), 404

    async def api_delete_concept(self):
        body = await request.get_json()
        element_id = body.get("id")
        if self.repo.delete_element(element_id):
            return jsonify({"ok": True})
        return jsonify({"error": "not found"}), 404

    def _memory_dict(self, m) -> dict:
        elements = [
            {"id": e.id, "name": e.name, "category": e.category, "role": role}
            for e, role in self.repo.get_memory_elements(m.id)
        ]
        return {
            "id": m.id,
            "content": m.content,
            "details": m.details or "",
            "emotion": m.emotion or "",
            "created_at": m.created_at,
            "last_accessed": m.last_accessed,
            "access_count": m.access_count,
            "strength": m.strength,
            "allow_forget": True,
            "group_id": m.scope_id,
            "elements": elements,
            "element_id": elements[0]["id"] if elements else "",
        }

    async def api_memories(self):
        group_id = request.args.get("group_id", "")
        element_id = request.args.get("element_id") or request.args.get("concept_id")
        q = request.args.get("q")
        person = request.args.get("person")
        scope = _scope_of(group_id)

        if person:
            return self._person_payload(scope, person)

        if element_id:
            mems = self.repo.get_element_memories(element_id, limit=100)
        elif q:
            ids: list[str] = []
            from ..domain.scoring import fts_match_clause, short_terms

            clause = fts_match_clause(q)
            if clause:
                ids.extend(self.repo.ids_from_fts(clause, scope))
            for term in short_terms(q):
                ids.extend(
                    m.id for m in self.repo.search_memories_by_like(scope, term, limit=20)
                )
            seen: set[str] = set()
            ids = [i for i in ids if not (i in seen or seen.add(i))][:50]
            mems = self.repo.get_memories_by_ids(ids)
        else:
            mems = self.repo.list_memories(scope, limit=200)

        for m in mems:
            self.repo.touch_memory(m.id, time.time())
        return jsonify({"memories": [self._memory_dict(m) for m in mems]})

    def _person_payload(self, scope: str, person: str):
        imp = self.repo.get_impression(scope, person)
        summary = None
        if imp is not None:
            summary = {
                "name": person,
                "score": imp.score,
                "summary": imp.summary or "暂无详细印象",
                "memory_count": 0,
                "last_updated": time.strftime(
                    "%Y-%m-%d %H:%M", time.localtime(imp.updated_at)
                ),
            }
        elem = None
        for e in self.repo.list_elements(scope):
            if e.name == person:
                elem = e
                break
        memories = []
        if elem is not None:
            for m in self.repo.get_element_memories(elem.id, limit=50):
                memories.append(
                    {
                        "content": m.content,
                        "details": m.details or "",
                        "score": m.strength,
                        "last_accessed": time.strftime(
                            "%Y-%m-%d %H:%M", time.localtime(m.last_accessed)
                        ),
                    }
                )
        return jsonify({"summary": summary, "memories": memories})

    async def api_create_memory(self):
        body = await request.get_json()
        scope = _scope_of(body.get("group_id"))
        content = (body.get("content") or "").strip()
        if not content:
            return jsonify({"error": "content required"}), 400
        now = time.time()
        memory = Memory(
            id=new_id("mem"),
            scope_id=scope,
            content=content,
            details=(body.get("details") or ""),
            emotion=(body.get("emotion") or ""),
            strength=max(0.05, min(1.0, float(body.get("strength") or 1.0))),
            created_at=now,
            last_accessed=now,
        )
        self.repo.upsert_memory(memory)

        element_name = (body.get("concept_name") or body.get("element_name") or "").strip()
        if element_name:
            category = body.get("category", "trait")
            if category not in CATEGORIES:
                category = "trait"
            elem = self.repo.get_or_create_element(scope, element_name, category, now)
            self.repo.link_memory_element(memory.id, elem.id, "")
        for old_field in ["participants", "location", "tags"]:
            val = (body.get(old_field) or "").strip()
            if val:
                for kw in val.replace("，", ",").split(","):
                    kw = kw.strip()
                    if kw:
                        elem = self.repo.get_or_create_element(scope, kw, "trait", now)
                        self.repo.link_memory_element(memory.id, elem.id, "")
        return jsonify({"id": memory.id})

    async def api_update_memory(self):
        body = await request.get_json()
        memory_id = body.get("id")
        strength = body.get("strength")
        ok = self.repo.update_memory_fields(
            memory_id,
            content=body.get("content"),
            details=body.get("details"),
            emotion=body.get("emotion"),
            strength=float(strength) if strength is not None else None,
        )
        if not ok:
            return jsonify({"error": "not found"}), 404
        return jsonify({"ok": True})

    async def api_delete_memory(self):
        body = await request.get_json()
        memory_id = body.get("id")
        if self.repo.delete_memory(memory_id):
            return jsonify({"ok": True})
        return jsonify({"error": "not found"}), 404

    @staticmethod
    def _conn_id(from_e: str, to_e: str) -> str:
        return f"{from_e}|{to_e}"

    @staticmethod
    def _parse_conn_id(conn_id: str) -> tuple[str, str] | None:
        parts = (conn_id or "").split("|")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            return None
        return parts[0], parts[1]

    async def api_connections(self):
        group_id = request.args.get("group_id", "")
        scope = _scope_of(group_id)
        result = []
        for conn in self.repo.list_connections(scope):
            cid = self._conn_id(conn["from_element"], conn["to_element"])
            result.append(
                {
                    "id": cid,
                    "from_element": conn["from_element"],
                    "to_element": conn["to_element"],
                    "from_concept": conn["from_element"],
                    "to_concept": conn["to_element"],
                    "strength": 1.0,
                    "last_strengthened": conn.get("updated_at", 0.0),
                    "relation": conn.get("relation", ""),
                }
            )
        return jsonify({"connections": result})

    async def api_create_connection(self):
        body = await request.get_json()
        scope = _scope_of(body.get("group_id"))
        from_e = body.get("from_element") or body.get("from_concept")
        to_e = body.get("to_element") or body.get("to_concept")
        relation = (body.get("relation") or "").strip()
        if not from_e or not to_e:
            return jsonify({"error": "from_element and to_element required"}), 400
        # 允许按名称创建（前端旧字段传名称）
        src = self.repo.get_or_create_element(scope, str(from_e), "trait", time.time())
        dst = self.repo.get_or_create_element(scope, str(to_e), "trait", time.time())
        self.repo.upsert_connection(src.id, dst.id, relation or "关联", time.time())
        return jsonify({"id": self._conn_id(src.id, dst.id)})

    async def api_update_connection(self):
        body = await request.get_json()
        parsed = self._parse_conn_id(body.get("id") or "")
        if not parsed:
            return jsonify({"error": "not found"}), 404
        # v2 连接无强度概念；若传了 relation 则更新关系描述，strength 参数忽略
        relation = (body.get("relation") or "").strip()
        if relation:
            self.repo.upsert_connection(parsed[0], parsed[1], relation, time.time())
            return jsonify({"ok": True})
        strength = body.get("strength")
        if strength is None:
            return jsonify({"error": "strength required"}), 400
        return jsonify({"ok": True})  # 兼容旧字段：强度无语义，静默接受

    async def api_delete_connection(self):
        body = await request.get_json()
        parsed = self._parse_conn_id(body.get("id") or "")
        if not parsed:
            return jsonify({"error": "not found"}), 404
        self.repo.delete_connection(parsed[0], parsed[1])
        return jsonify({"ok": True})

    async def api_impressions(self):
        group_id = request.args.get("group_id", "")
        person = request.args.get("person")
        scope = _scope_of(group_id)
        if person:
            return self._person_payload(scope, person)
        people = [
            {"element_id": e.id, "name": e.name}
            for e in self.repo.list_elements(scope)
            if e.category == "person"
        ]
        return jsonify({"people": people})

    async def api_create_impression(self):
        body = await request.get_json()
        scope = _scope_of(body.get("group_id"))
        person = (body.get("person") or "").strip()
        summary = (body.get("summary") or "").strip()
        if not person or not summary:
            return jsonify({"error": "person and summary required"}), 400
        score_raw = body.get("score")
        try:
            score = max(0.0, min(1.0, float(score_raw))) if score_raw is not None else None
        except (TypeError, ValueError):
            score = None
        current = self.repo.get_impression(scope, person)
        if score is None:
            score = current.score if current else 0.5
        now = time.time()
        self.repo.upsert_impression(scope, person, score, summary, now)
        # 人名同时登记为 person 要素，图谱/人物下拉可见
        self.repo.get_or_create_element(scope, person, "person", now)
        return jsonify({"id": new_id("imp"), "ok": True})

    async def api_adjust_impression(self):
        body = await request.get_json()
        scope = _scope_of(body.get("group_id"))
        person = body.get("person")
        delta = body.get("delta")
        try:
            new_score = self.repo.adjust_impression(scope, str(person), float(delta), time.time())
            return jsonify({"score": new_score, "score_desc": score_verbal(new_score)})
        except Exception as e:
            return jsonify({"error": str(e)}), 400