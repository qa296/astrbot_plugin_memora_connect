"""
Memora Connect Plugin Page 后端 API。

通过 AstrBot Dashboard 的 Plugin Pages 机制暴露记忆管理 REST API。
前端位于 pages/memora-connect/，使用 window.AstrBotPluginPage bridge SDK 调用，
鉴权由 Dashboard 接管，无需插件自管 token/CORS/端口。
"""

import sqlite3
from typing import Any, List

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

from ..infrastructure.resources import resource_manager

PLUGIN_NAME = "astrbot_plugin_memora_connect"


class MemoryWebAPI:
    """注册到 AstrBot Dashboard 的 Plugin Page 后端 API。

    所有路由以 ``/<PLUGIN_NAME>/`` 为前缀，Dashboard 会把
    ``/api/plug/<PLUGIN_NAME>/<endpoint>`` 转发到对应 handler。
    bridge SDK 的 ``apiGet``/``apiPost`` 只支持 GET/POST，
    因此 PUT/DELETE 操作统一改写为 POST，动作编码进路径
    （如 ``concepts/delete``、``memories/update``）。
    """

    def __init__(self, memory_system: Any, context: "Context") -> None:
        self.ms = memory_system
        self.context = context

    # ------------------------------------------------------------------
    # 注册
    # ------------------------------------------------------------------
    def register(self) -> None:
        """向 Dashboard 注册全部 Web API 路由。"""
        c = self.context
        prefix = f"/{PLUGIN_NAME}"

        # 状态与图
        c.register_web_api(f"{prefix}/status", self.api_status, ["GET"], "记忆系统状态")
        c.register_web_api(f"{prefix}/groups", self.api_groups, ["GET"], "分组列表")
        c.register_web_api(f"{prefix}/graph", self.api_graph, ["GET"], "记忆图谱数据")

        # 概念/元素
        c.register_web_api(f"{prefix}/concepts", self.api_concepts, ["GET"], "概念列表")
        c.register_web_api(f"{prefix}/concepts/create", self.api_create_concept, ["POST"], "创建概念")
        c.register_web_api(f"{prefix}/concepts/update", self.api_update_concept, ["POST"], "更新概念")
        c.register_web_api(f"{prefix}/concepts/delete", self.api_delete_concept, ["POST"], "删除概念")

        # 记忆
        c.register_web_api(f"{prefix}/memories", self.api_memories, ["GET"], "记忆列表/搜索")
        c.register_web_api(f"{prefix}/memories/create", self.api_create_memory, ["POST"], "创建记忆")
        c.register_web_api(f"{prefix}/memories/update", self.api_update_memory, ["POST"], "更新记忆")
        c.register_web_api(f"{prefix}/memories/delete", self.api_delete_memory, ["POST"], "删除记忆")

        # 连接
        c.register_web_api(f"{prefix}/connections", self.api_connections, ["GET"], "连接列表")
        c.register_web_api(f"{prefix}/connections/create", self.api_create_connection, ["POST"], "创建连接")
        c.register_web_api(f"{prefix}/connections/update", self.api_update_connection, ["POST"], "更新连接")
        c.register_web_api(f"{prefix}/connections/delete", self.api_delete_connection, ["POST"], "删除连接")

        # 印象
        c.register_web_api(f"{prefix}/impressions", self.api_impressions, ["GET"], "印象列表")
        c.register_web_api(f"{prefix}/impressions/create", self.api_create_impression, ["POST"], "创建印象")
        c.register_web_api(f"{prefix}/impressions/adjust", self.api_adjust_impression, ["POST"], "调整好感度")

        logger.info("Memora Plugin Page API 已注册到 Dashboard")

    # ------------------------------------------------------------------
    # 辅助方法（从 web/server.py 迁移，不依赖 aiohttp）
    # ------------------------------------------------------------------
    async def _load_group(self, group_id: str) -> None:
        """在当前对象上加载/切换内存图数据。

        注意：此操作会替换内存中的图，和并发消息处理存在竞争，简单版本忽略。
        """
        try:
            self.ms.memory_graph = self.ms.memory_graph.__class__()
            self.ms.load_memory_state(group_id or "")
        except Exception as e:
            logger.warning(f"加载分组数据失败: {e}")

    def _ensure_db_schema(self) -> None:
        conn = resource_manager.get_db_connection(self.ms.db_path)
        try:
            cur = conn.cursor()
            cur.execute('''
                CREATE TABLE IF NOT EXISTS elements (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    group_id TEXT DEFAULT '',
                    created_at REAL,
                    last_accessed REAL,
                    access_count INTEGER DEFAULT 0
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    details TEXT DEFAULT '',
                    emotion TEXT DEFAULT '',
                    created_at REAL,
                    last_accessed REAL,
                    access_count INTEGER DEFAULT 0,
                    strength REAL DEFAULT 1.0,
                    allow_forget INTEGER DEFAULT 1,
                    group_id TEXT DEFAULT ''
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS element_memories (
                    element_id TEXT NOT NULL,
                    memory_id TEXT NOT NULL,
                    role TEXT DEFAULT '',
                    PRIMARY KEY (element_id, memory_id)
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS connections (
                    id TEXT PRIMARY KEY,
                    from_element TEXT NOT NULL,
                    to_element TEXT NOT NULL,
                    strength REAL DEFAULT 1.0,
                    last_strengthened REAL
                )
            ''')
            cur.execute("CREATE INDEX IF NOT EXISTS idx_elements_group ON elements(group_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_memories_group_id ON memories(group_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_em_element ON element_memories(element_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_em_memory ON element_memories(memory_id)")
            conn.commit()
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            logger.warning(f"初始化 Memora Web 数据表失败: {e}")
        finally:
            resource_manager.release_db_connection(self.ms.db_path, conn)

    def _query_all(self, sql: str, params: tuple = ()) -> List[tuple]:
        conn = resource_manager.get_db_connection(self.ms.db_path)
        try:
            cur = conn.cursor()
            try:
                cur.execute(sql, params)
                return cur.fetchall()
            except sqlite3.OperationalError as e:
                if "no such table" in str(e).lower():
                    self._ensure_db_schema()
                    cur.execute(sql, params)
                    return cur.fetchall()
                raise
        finally:
            resource_manager.release_db_connection(self.ms.db_path, conn)

    def _execute(self, sql: str, params: tuple = ()) -> None:
        conn = resource_manager.get_db_connection(self.ms.db_path)
        try:
            cur = conn.cursor()
            try:
                cur.execute("BEGIN TRANSACTION")
                cur.execute(sql, params)
                conn.commit()
            except sqlite3.OperationalError as e:
                if "no such table" in str(e).lower():
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    self._ensure_db_schema()
                    cur.execute("BEGIN TRANSACTION")
                    cur.execute(sql, params)
                    conn.commit()
                else:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    raise
            except Exception:
                conn.rollback()
                raise
        finally:
            resource_manager.release_db_connection(self.ms.db_path, conn)

    # ------------------------------------------------------------------
    # 状态与图
    # ------------------------------------------------------------------
    async def api_status(self):
        return jsonify({
            "memory_enabled": bool(getattr(self.ms, "memory_system_enabled", True)),
            "db_path": self.ms.db_path,
            "web_enabled": True,
        })

    async def api_groups(self):
        rows = self._query_all("SELECT DISTINCT group_id FROM memories WHERE group_id IS NOT NULL")
        groups = sorted({(r[0] or "") for r in rows})
        if "" not in groups:
            groups = [""] + list(groups)
        return jsonify({"groups": groups})

    async def api_graph(self):
        from ..memory.visualization import MemoryGraphVisualizer
        group_id = request.args.get("group_id", "")
        try:
            viz = MemoryGraphVisualizer(self.ms)
            data = await viz._prepare_graph_data(
                max_nodes=200,
                max_edges=800,
                edge_strength_threshold=0.01,
                group_id=group_id,
            )
            if data.get("error"):
                return jsonify({"error": data["error"]}), 400
            return jsonify(data)
        except Exception as e:
            logger.error(f"获取图数据失败: {e}")
            return jsonify({"error": str(e)}), 500

    # ------------------------------------------------------------------
    # 概念/元素
    # ------------------------------------------------------------------
    async def api_concepts(self):
        group_id = request.args.get("group_id", "")
        await self._load_group(group_id)
        elements = []
        for elem in self.ms.memory_graph.elements.values():
            if group_id and elem.group_id != group_id:
                continue
            elements.append({
                "id": elem.id,
                "name": elem.name,
                "category": elem.category,
                "access_count": elem.access_count,
            })
        elements.sort(key=lambda e: (e["category"], e["name"]))
        return jsonify({"concepts": elements})

    async def api_create_concept(self):
        body = await request.get_json()
        name = (body.get("name") or "").strip()
        group_id = (body.get("group_id") or "").strip()
        category = (body.get("category") or "trait").strip()
        if not name:
            return jsonify({"error": "name required"}), 400
        from ..core.models import CATEGORIES
        if category not in CATEGORIES:
            category = "trait"
        await self._load_group(group_id)
        eid = self.ms.memory_graph.get_or_create_element(name, category, group_id)
        await self.ms._queue_save_memory_state(group_id)
        return jsonify({"id": eid, "name": name, "category": category})

    async def api_update_concept(self):
        body = await request.get_json()
        element_id = body.get("id")
        new_name = (body.get("name") or "").strip()
        group_id = (body.get("group_id") or "").strip()
        if not new_name:
            return jsonify({"error": "name required"}), 400
        await self._load_group(group_id)
        elem = self.ms.memory_graph.elements.get(element_id)
        if elem:
            elem.name = new_name
            await self.ms._queue_save_memory_state(group_id)
            return jsonify({"ok": True})
        return jsonify({"error": "element not found"}), 404

    async def api_delete_concept(self):
        body = await request.get_json()
        element_id = body.get("id")
        group_id = (body.get("group_id") or "").strip()
        await self._load_group(group_id)
        if element_id in self.ms.memory_graph.elements:
            self.ms.memory_graph.remove_element(element_id)
            await self.ms._queue_save_memory_state(group_id)
            return jsonify({"ok": True})
        return jsonify({"error": "not found"}), 404

    # ------------------------------------------------------------------
    # 记忆
    # ------------------------------------------------------------------
    async def api_memories(self):
        group_id = request.args.get("group_id", "")
        element_id = request.args.get("element_id") or request.args.get("concept_id")
        q = request.args.get("q")
        person = request.args.get("person")

        if person:
            try:
                summary = self.ms.get_person_impression_summary(group_id, person)
                memories = self.ms.get_person_impression_memories(group_id, person, limit=50)
                return jsonify({"summary": summary, "memories": memories})
            except Exception as e:
                return jsonify({"error": str(e)}), 500

        await self._load_group(group_id)
        if q:
            mems = await self.ms.recall_memories_full(q)
            if mems:
                await self.ms._queue_save_memory_state(group_id)
        elif element_id:
            mems = self.ms.memory_graph.get_element_memories(element_id)
        else:
            mems = list(self.ms.memory_graph.memories.values())

        data = []
        for m in mems:
            if group_id and getattr(m, "group_id", "") != group_id:
                continue
            if not group_id and getattr(m, "group_id", ""):
                continue
            elements = [
                {"id": e.id, "name": e.name, "category": e.category, "role": role}
                for e, role in self.ms.memory_graph.get_memory_elements(m.id)
            ]
            data.append({
                "id": m.id,
                "content": m.content,
                "details": m.details or "",
                "emotion": m.emotion or "",
                "created_at": m.created_at,
                "last_accessed": m.last_accessed,
                "access_count": m.access_count,
                "strength": m.strength,
                "allow_forget": bool(getattr(m, "allow_forget", True)),
                "group_id": getattr(m, "group_id", ""),
                "elements": elements,
                "element_id": elements[0]["id"] if elements else "",
            })
        return jsonify({"memories": data})

    async def api_create_memory(self):
        body = await request.get_json()
        group_id = (body.get("group_id") or "").strip()
        element_name = (body.get("concept_name") or body.get("element_name") or "").strip()
        content = (body.get("content") or "").strip()
        if not content:
            return jsonify({"error": "content required"}), 400
        await self._load_group(group_id)
        mem_id = self.ms.memory_graph.add_memory(
            content=content,
            details=(body.get("details") or ""),
            emotion=(body.get("emotion") or ""),
            strength=float(body.get("strength") or 1.0),
            group_id=group_id,
        )

        # 如果有元素名称，创建/获取对应的 Element 并关联
        if element_name:
            from ..core.models import CATEGORIES
            category = body.get("category", "trait")
            if category not in CATEGORIES:
                category = "trait"
            eid = self.ms.memory_graph.get_or_create_element(
                element_name, category, group_id
            )
            self.ms.memory_graph.link_memory(eid, mem_id, "")

        # 兼容旧字段：将旧 participants/location/tags 转为 trait 元素关联
        for old_field in ["participants", "location", "tags"]:
            val = (body.get(old_field) or "").strip()
            if val:
                for kw in val.replace("，", ",").split(","):
                    kw = kw.strip()
                    if kw:
                        eid = self.ms.memory_graph.get_or_create_element(kw, "trait", group_id)
                        self.ms.memory_graph.link_memory(eid, mem_id, "")

        await self.ms._queue_save_memory_state(group_id)
        return jsonify({"id": mem_id})

    async def api_update_memory(self):
        body = await request.get_json()
        memory_id = body.get("id")
        group_id = (body.get("group_id") or "").strip()
        await self._load_group(group_id)
        ok = self.ms.memory_graph.update_memory(
            memory_id,
            content=body.get("content"),
            details=body.get("details"),
            emotion=body.get("emotion"),
            strength=float(body.get("strength")) if body.get("strength") is not None else None,
        )
        if not ok:
            return jsonify({"error": "not found"}), 404
        await self.ms._queue_save_memory_state(group_id)
        return jsonify({"ok": True})

    async def api_delete_memory(self):
        body = await request.get_json()
        memory_id = body.get("id")
        group_id = (body.get("group_id") or "").strip()
        await self._load_group(group_id)
        ok = await self.ms.delete_memory_by_id(memory_id, group_id)
        if ok:
            await self.ms._queue_save_memory_state(group_id)
            return jsonify({"ok": True})
        return jsonify({"error": "not found"}), 404

    # ------------------------------------------------------------------
    # 连接
    # ------------------------------------------------------------------
    async def api_connections(self):
        group_id = request.args.get("group_id", "")
        await self._load_group(group_id)
        valid_ids = {
            e.id for e in self.ms.memory_graph.elements.values()
            if not group_id or e.group_id == group_id
        }
        result = []
        for conn in self.ms.memory_graph.connections:
            if valid_ids and (conn.from_element not in valid_ids or conn.to_element not in valid_ids):
                continue
            result.append({
                "id": conn.id,
                "from_element": conn.from_element,
                "to_element": conn.to_element,
                "from_concept": conn.from_element,  # 前端兼容字段
                "to_concept": conn.to_element,
                "strength": conn.strength,
                "last_strengthened": conn.last_strengthened,
            })
        return jsonify({"connections": result})

    async def api_create_connection(self):
        body = await request.get_json()
        group_id = (body.get("group_id") or "").strip()
        from_e = body.get("from_element") or body.get("from_concept")
        to_e = body.get("to_element") or body.get("to_concept")
        strength = float(body.get("strength") or 1.0)
        if not from_e or not to_e:
            return jsonify({"error": "from_element and to_element required"}), 400
        await self._load_group(group_id)
        cid = self.ms.memory_graph.add_connection(str(from_e), str(to_e), strength=strength)
        await self.ms._queue_save_memory_state(group_id)
        return jsonify({"id": cid})

    async def api_update_connection(self):
        body = await request.get_json()
        conn_id = body.get("id")
        group_id = (body.get("group_id") or "").strip()
        strength = body.get("strength")
        if strength is None:
            return jsonify({"error": "strength required"}), 400
        await self._load_group(group_id)
        ok = self.ms.memory_graph.set_connection_strength(conn_id, float(strength))
        if not ok:
            return jsonify({"error": "not found"}), 404
        await self.ms._queue_save_memory_state(group_id)
        return jsonify({"ok": True})

    async def api_delete_connection(self):
        body = await request.get_json()
        conn_id = body.get("id")
        group_id = (body.get("group_id") or "").strip()
        await self._load_group(group_id)
        self.ms.memory_graph.remove_connection(conn_id)
        await self.ms._queue_save_memory_state(group_id)
        return jsonify({"ok": True})

    # ------------------------------------------------------------------
    # 印象
    # ------------------------------------------------------------------
    async def api_impressions(self):
        group_id = request.args.get("group_id", "")
        person = request.args.get("person")
        if person:
            try:
                summary = self.ms.get_person_impression_summary(group_id, person)
                memories = self.ms.get_person_impression_memories(group_id, person, limit=50)
                return jsonify({"summary": summary, "memories": memories})
            except Exception as e:
                return jsonify({"error": str(e)}), 500
        await self._load_group(group_id)
        people = []
        for elem in self.ms.memory_graph.elements.values():
            if elem.category != "person":
                continue
            if group_id and elem.group_id != group_id:
                continue
            people.append({"element_id": elem.id, "name": elem.name})
        return jsonify({"people": people})

    async def api_create_impression(self):
        body = await request.get_json()
        group_id = (body.get("group_id") or "").strip()
        person = (body.get("person") or "").strip()
        summary = (body.get("summary") or "").strip()
        score = body.get("score")
        details = (body.get("details") or "").strip()
        if not person or not summary:
            return jsonify({"error": "person and summary required"}), 400
        try:
            score_val = float(score) if score is not None else None
        except Exception:
            score_val = None
        _id = self.ms.record_person_impression(group_id, person, summary, score_val, details)
        await self.ms._queue_save_memory_state(group_id)
        return jsonify({"id": _id, "ok": True})

    async def api_adjust_impression(self):
        body = await request.get_json()
        group_id = (body.get("group_id") or "").strip()
        person = body.get("person")
        delta = body.get("delta")
        try:
            new_score = self.ms.adjust_impression_score(group_id, person, float(delta))
            await self.ms._queue_save_memory_state(group_id)
            return jsonify({"score": new_score})
        except Exception as e:
            return jsonify({"error": str(e)}), 400
