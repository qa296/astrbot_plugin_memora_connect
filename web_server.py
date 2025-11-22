import os
import json
import asyncio
from typing import Any, Dict, List, Optional

try:
    from aiohttp import web
except Exception:  # pragma: no cover
    web = None

try:
    from astrbot.api import logger
except Exception:  # pragma: no cover
    import logging
    logger = logging.getLogger(__name__)

from .resource_management import resource_manager
from .web_assets import DEFAULT_INDEX_HTML, DEFAULT_STYLE_CSS, DEFAULT_APP_JS


class MemoryWebServer:
    """
    轻量级 Web 服务，用于浏览与管理记忆图谱。
    提供 REST API + 简单静态页面。可通过配置启用/关闭与端口设置。
    """

    def __init__(self, memory_system: Any, host: str = "127.0.0.1", port: int = 8350, access_token: str = "") -> None:
        if web is None:
            raise RuntimeError("aiohttp 不可用，无法启动 Web 服务")
        self.ms = memory_system
        self.host = host
        self.port = int(port)
        self.access_token = access_token or ""

        self._app = web.Application(middlewares=[self._cors_middleware, self._auth_middleware])
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.BaseSite] = None

        self._setup_routes()

    # ---------------------- lifecycle ----------------------
    async def start(self):
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()
        logger.info(f"Memora Web 已启动: http://{self.host}:{self.port}")

    async def stop(self):
        try:
            if self._runner:
                await self._runner.cleanup()
                logger.info("Memora Web 已停止")
        finally:
            self._runner = None
            self._site = None

    # ---------------------- middlewares ----------------------
    @web.middleware
    async def _cors_middleware(self, request: web.Request, handler):
        if request.method == "OPTIONS":
            resp = web.Response(status=204)
        else:
            resp = await handler(request)
        # CORS headers
        resp.headers["Access-Control-Allow-Origin"] = request.headers.get("Origin", "*")
        resp.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "*, X-Requested-With, Content-Type, Authorization, x-access-token"
        resp.headers["Access-Control-Allow-Credentials"] = "true"
        return resp

    @web.middleware
    async def _auth_middleware(self, request: web.Request, handler):
        # 如果设置了访问令牌，仅保护 /api 前缀
        if self.access_token and request.path.startswith("/api/"):
            token = request.headers.get("x-access-token") or request.query.get("token")
            if token != self.access_token:
                return web.json_response({"error": "unauthorized"}, status=401)
        return await handler(request)

    # ---------------------- routes ----------------------
    def _setup_routes(self) -> None:
        # API
        self._app.add_routes([
            web.get("/api/status", self.api_status),
            web.get("/api/groups", self.api_groups),
            web.get("/api/graph", self.api_graph),

            web.get("/api/concepts", self.api_concepts),
            web.post("/api/concepts", self.api_create_concept),
            web.put("/api/concepts/{concept_id}", self.api_update_concept),
            web.delete("/api/concepts/{concept_id}", self.api_delete_concept),

            web.get("/api/memories", self.api_memories),
            web.post("/api/memories", self.api_create_memory),
            web.put("/api/memories/{memory_id}", self.api_update_memory),
            web.delete("/api/memories/{memory_id}", self.api_delete_memory),

            web.get("/api/connections", self.api_connections),
            web.post("/api/connections", self.api_create_connection),
            web.put("/api/connections/{conn_id}", self.api_update_connection),
            web.delete("/api/connections/{conn_id}", self.api_delete_connection),

            web.get("/api/impressions", self.api_impressions),
            web.post("/api/impressions", self.api_create_impression),
            web.put("/api/impressions/{person}/score", self.api_update_impression_score),
        ])

        # 静态文件
        static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webui")
        self._static_dir = static_dir
        if not os.path.exists(static_dir):
            os.makedirs(static_dir, exist_ok=True)
        # 确保在缺失前端文件时自动写入一份默认的 Web 资源
        self._ensure_default_static_files()
        self._app.router.add_get("/", self.handle_index)
        self._app.router.add_static("/static/", static_dir, show_index=True)

    # ---------------------- helpers ----------------------
    def _ensure_default_static_files(self) -> None:
        """在 webui 目录缺失前端文件时，自动写入一份内置的默认页面与脚本。"""
        try:
            index_path = os.path.join(self._static_dir, "index.html")
            if not os.path.exists(index_path):
                with open(index_path, "w", encoding="utf-8") as f:
                    f.write(DEFAULT_INDEX_HTML)

            style_path = os.path.join(self._static_dir, "style.css")
            if not os.path.exists(style_path):
                with open(style_path, "w", encoding="utf-8") as f:
                    f.write(DEFAULT_STYLE_CSS)

            app_path = os.path.join(self._static_dir, "app.js")
            if not os.path.exists(app_path):
                with open(app_path, "w", encoding="utf-8") as f:
                    f.write(DEFAULT_APP_JS)
        except Exception as e:
            logger.warning(f"初始化 Memora Web 静态文件失败: {e}")

    async def _load_group(self, group_id: str) -> None:
        # 在当前对象上加载/切换内存图数据
        # 注意：此操作会替换内存中的图，和并发消息处理存在竞争，简单版本忽略。
        try:
            self.ms.memory_graph = self.ms.memory_graph.__class__()
            self.ms.load_memory_state(group_id or "")
        except Exception as e:
            logger.warning(f"加载分组数据失败: {e}")

    def _query_all(self, sql: str, params: tuple = ()) -> List[tuple]:
        conn = resource_manager.get_db_connection(self.ms.db_path)
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()
            return rows
        finally:
            resource_manager.release_db_connection(self.ms.db_path, conn)

    def _execute(self, sql: str, params: tuple = ()) -> None:
        conn = resource_manager.get_db_connection(self.ms.db_path)
        try:
            cur = conn.cursor()
            cur.execute("BEGIN TRANSACTION")
            cur.execute(sql, params)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            resource_manager.release_db_connection(self.ms.db_path, conn)

    # ---------------------- handlers ----------------------
    async def handle_index(self, request: web.Request):
        index_path = os.path.join(self._static_dir, "index.html")
        if os.path.exists(index_path):
            return web.FileResponse(index_path)
        return web.Response(text="Memora Web", content_type="text/plain")

    async def api_status(self, request: web.Request):
        cfg = self.ms.memory_config or {}
        web_cfg = cfg.get("web_ui", {})
        return web.json_response({
            "memory_enabled": bool(getattr(self.ms, "memory_system_enabled", True)),
            "db_path": self.ms.db_path,
            "web_enabled": bool(web_cfg.get("enabled", False)),
            "host": request.host,
        })

    async def api_groups(self, request: web.Request):
        rows = self._query_all("SELECT DISTINCT group_id FROM memories WHERE group_id IS NOT NULL")
        groups = sorted({(r[0] or "") for r in rows})
        # 确保包含默认组(私聊/全局)
        if "" not in groups:
            groups = [""] + list(groups)
        return web.json_response({"groups": groups})

    async def api_graph(self, request: web.Request):
        from .memory_graph_visualization import MemoryGraphVisualizer
        group_id = request.query.get("group_id", "")
        layout = request.query.get("layout", "auto")
        try:
            # 直接复用可视化的数据准备逻辑
            viz = MemoryGraphVisualizer(self.ms)
            data = await viz._prepare_graph_data(max_nodes=200, max_edges=800, edge_strength_threshold=0.01, group_id=group_id)
            if data.get("error"):
                return web.json_response({"error": data["error"]}, status=400)
            return web.json_response(data)
        except Exception as e:
            logger.error(f"获取图数据失败: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_concepts(self, request: web.Request):
        group_id = request.query.get("group_id", "")
        if group_id:
            rows = self._query_all(
                "SELECT DISTINCT c.id, c.name FROM concepts c JOIN memories m ON m.concept_id=c.id WHERE m.group_id=?",
                (group_id,),
            )
        else:
            rows = self._query_all(
                "SELECT DISTINCT c.id, c.name FROM concepts c JOIN memories m ON m.concept_id=c.id WHERE (m.group_id='' OR m.group_id IS NULL)"
            )
        concepts = [{"id": r[0], "name": r[1]} for r in rows]
        return web.json_response({"concepts": concepts})

    async def api_create_concept(self, request: web.Request):
        body = await request.json()
        name = (body.get("name") or "").strip()
        group_id = (body.get("group_id") or "").strip()
        if not name:
            return web.json_response({"error": "name required"}, status=400)
        # 通过内存图创建，便于后续操作
        await self._load_group(group_id)
        cid = self.ms.memory_graph.add_concept(name)
        await self.ms._queue_save_memory_state(group_id)
        return web.json_response({"id": cid, "name": name})

    async def api_update_concept(self, request: web.Request):
        concept_id = request.match_info.get("concept_id")
        body = await request.json()
        new_name = (body.get("name") or "").strip()
        group_id = (body.get("group_id") or "").strip()
        if not new_name:
            return web.json_response({"error": "name required"}, status=400)
        await self._load_group(group_id)
        if concept_id in self.ms.memory_graph.concepts:
            self.ms.memory_graph.concepts[concept_id].name = new_name
            await self.ms._queue_save_memory_state(group_id)
            return web.json_response({"ok": True})
        return web.json_response({"error": "concept not found"}, status=404)

    async def api_delete_concept(self, request: web.Request):
        concept_id = request.match_info.get("concept_id")
        group_id = request.query.get("group_id", "")
        await self._load_group(group_id)
        if concept_id in self.ms.memory_graph.concepts:
            self.ms.memory_graph.remove_concept(concept_id)
            await self.ms._queue_save_memory_state(group_id)
            return web.json_response({"ok": True})
        return web.json_response({"error": "not found"}, status=404)

    async def api_memories(self, request: web.Request):
        group_id = request.query.get("group_id", "")
        concept_id = request.query.get("concept_id")
        q = request.query.get("q")
        person = request.query.get("person")

        if person:
            # 人物印象
            try:
                summary = self.ms.get_person_impression_summary(group_id, person)
                memories = self.ms.get_person_impression_memories(group_id, person, limit=50)
                return web.json_response({"summary": summary, "memories": memories})
            except Exception as e:
                return web.json_response({"error": str(e)}, status=500)

        if q:
            # 搜索
            await self._load_group(group_id)
            mems = await self.ms.recall_memories_full(q)
            data = [m.__dict__ for m in mems]
            return web.json_response({"memories": data})

        # 按组/概念列出
        if concept_id:
            rows = self._query_all(
                "SELECT id, concept_id, content, details, participants, location, emotion, tags, created_at, last_accessed, access_count, strength FROM memories WHERE concept_id=? AND (group_id=? OR (?='' AND (group_id='' OR group_id IS NULL))) ORDER BY last_accessed DESC",
                (concept_id, group_id, group_id),
            )
        else:
            if group_id:
                rows = self._query_all(
                    "SELECT id, concept_id, content, details, participants, location, emotion, tags, created_at, last_accessed, access_count, strength FROM memories WHERE group_id=? ORDER BY last_accessed DESC",
                    (group_id,),
                )
            else:
                rows = self._query_all(
                    "SELECT id, concept_id, content, details, participants, location, emotion, tags, created_at, last_accessed, access_count, strength FROM memories WHERE group_id='' OR group_id IS NULL ORDER BY last_accessed DESC"
                )
        memories = [
            {
                "id": r[0],
                "concept_id": r[1],
                "content": r[2],
                "details": r[3] or "",
                "participants": r[4] or "",
                "location": r[5] or "",
                "emotion": r[6] or "",
                "tags": r[7] or "",
                "created_at": r[8],
                "last_accessed": r[9],
                "access_count": r[10],
                "strength": r[11],
            }
            for r in rows
        ]
        return web.json_response({"memories": memories})

    async def api_create_memory(self, request: web.Request):
        body = await request.json()
        group_id = (body.get("group_id") or "").strip()
        concept_id = (body.get("concept_id") or "").strip()
        concept_name = (body.get("concept_name") or "").strip()
        content = (body.get("content") or "").strip()
        if not content:
            return web.json_response({"error": "content required"}, status=400)
        await self._load_group(group_id)
        if not concept_id:
            # 若没有传 id，使用名称新建/获取
            if not concept_name:
                return web.json_response({"error": "concept_id or concept_name required"}, status=400)
            concept_id = self.ms.memory_graph.add_concept(concept_name)
        mem_id = self.ms.memory_graph.add_memory(
            content=content,
            concept_id=concept_id,
            details=(body.get("details") or ""),
            participants=(body.get("participants") or ""),
            location=(body.get("location") or ""),
            emotion=(body.get("emotion") or ""),
            tags=(body.get("tags") or ""),
            strength=float(body.get("strength") or 1.0),
            group_id=group_id,
        )
        await self.ms._queue_save_memory_state(group_id)
        return web.json_response({"id": mem_id})

    async def api_update_memory(self, request: web.Request):
        memory_id = request.match_info.get("memory_id")
        body = await request.json()
        group_id = (body.get("group_id") or "").strip()
        await self._load_group(group_id)
        ok = self.ms.memory_graph.update_memory(
            memory_id,
            content=body.get("content"),
            details=body.get("details"),
            participants=body.get("participants"),
            location=body.get("location"),
            emotion=body.get("emotion"),
            tags=body.get("tags"),
            strength=float(body.get("strength")) if body.get("strength") is not None else None,
            concept_id=body.get("concept_id"),
        )
        if not ok:
            return web.json_response({"error": "not found"}, status=404)
        await self.ms._queue_save_memory_state(group_id)
        return web.json_response({"ok": True})

    async def api_delete_memory(self, request: web.Request):
        memory_id = request.match_info.get("memory_id")
        group_id = request.query.get("group_id", "")
        await self._load_group(group_id)
        if memory_id in self.ms.memory_graph.memories:
            self.ms.memory_graph.remove_memory(memory_id)
            await self.ms._queue_save_memory_state(group_id)
            return web.json_response({"ok": True})
        return web.json_response({"error": "not found"}, status=404)

    async def api_connections(self, request: web.Request):
        group_id = request.query.get("group_id", "")
        # 仅返回当前 group 的概念之间的连接
        if group_id:
            concept_rows = self._query_all("SELECT DISTINCT concept_id FROM memories WHERE group_id=?", (group_id,))
        else:
            concept_rows = self._query_all("SELECT DISTINCT concept_id FROM memories WHERE group_id='' OR group_id IS NULL")
        cids = {r[0] for r in concept_rows}
        rows = self._query_all("SELECT id, from_concept, to_concept, strength, last_strengthened FROM connections")
        result = [
            {
                "id": r[0],
                "from_concept": r[1],
                "to_concept": r[2],
                "strength": r[3],
                "last_strengthened": r[4],
            }
            for r in rows
            if r[1] in cids and r[2] in cids
        ]
        return web.json_response({"connections": result})

    async def api_create_connection(self, request: web.Request):
        body = await request.json()
        group_id = (body.get("group_id") or "").strip()
        from_c = body.get("from_concept")
        to_c = body.get("to_concept")
        strength = float(body.get("strength") or 1.0)
        if not from_c or not to_c:
            return web.json_response({"error": "from_concept and to_concept required"}, status=400)
        await self._load_group(group_id)
        cid = self.ms.memory_graph.add_connection(str(from_c), str(to_c), strength=strength)
        await self.ms._queue_save_memory_state(group_id)
        return web.json_response({"id": cid})

    async def api_update_connection(self, request: web.Request):
        conn_id = request.match_info.get("conn_id")
        body = await request.json()
        group_id = (body.get("group_id") or "").strip()
        strength = body.get("strength")
        if strength is None:
            return web.json_response({"error": "strength required"}, status=400)
        await self._load_group(group_id)
        ok = self.ms.memory_graph.set_connection_strength(conn_id, float(strength))
        if not ok:
            return web.json_response({"error": "not found"}, status=404)
        await self.ms._queue_save_memory_state(group_id)
        return web.json_response({"ok": True})

    async def api_delete_connection(self, request: web.Request):
        conn_id = request.match_info.get("conn_id")
        group_id = request.query.get("group_id", "")
        await self._load_group(group_id)
        self.ms.memory_graph.remove_connection(conn_id)
        await self.ms._queue_save_memory_state(group_id)
        return web.json_response({"ok": True})

    async def api_impressions(self, request: web.Request):
        group_id = request.query.get("group_id", "")
        person = request.query.get("person")
        if person:
            try:
                summary = self.ms.get_person_impression_summary(group_id, person)
                memories = self.ms.get_person_impression_memories(group_id, person, limit=50)
                return web.json_response({"summary": summary, "memories": memories})
            except Exception as e:
                return web.json_response({"error": str(e)}, status=500)
        # 列出当前群的所有 Imprint 概念
        if group_id:
            like_prefix = f"Imprint:{group_id}:"
        else:
            like_prefix = "Imprint::"  # 私聊/全局
        rows = self._query_all("SELECT id, name FROM concepts WHERE name LIKE ?", (f"{like_prefix}%",))
        people = []
        for r in rows:
            name = r[1].split(":")[-1]
            people.append({"concept_id": r[0], "name": name})
        return web.json_response({"people": people})

    async def api_create_impression(self, request: web.Request):
        body = await request.json()
        group_id = (body.get("group_id") or "").strip()
        person = (body.get("person") or "").strip()
        summary = (body.get("summary") or "").strip()
        score = body.get("score")
        details = (body.get("details") or "").strip()
        if not person or not summary:
            return web.json_response({"error": "person and summary required"}, status=400)
        try:
            score_val = float(score) if score is not None else None
        except Exception:
            score_val = None
        _id = self.ms.record_person_impression(group_id, person, summary, score_val, details)
        await self.ms._queue_save_memory_state(group_id)
        return web.json_response({"id": _id, "ok": True})

    async def api_update_impression_score(self, request: web.Request):
        body = await request.json()
        group_id = (body.get("group_id") or "").strip()
        person = request.match_info.get("person")
        delta = body.get("delta")
        try:
            new_score = self.ms.adjust_impression_score(group_id, person, float(delta))
            await self.ms._queue_save_memory_state(group_id)
            return web.json_response({"score": new_score})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=400)
