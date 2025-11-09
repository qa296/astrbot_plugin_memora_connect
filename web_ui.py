import asyncio
import json
import os
from typing import Any, Dict, List, Optional

from aiohttp import web

try:
    from astrbot.api import logger  # type: ignore
except Exception:  # pragma: no cover
    import logging
    logger = logging.getLogger(__name__)


class MemoryWebUI:
    """A lightweight aiohttp-based web UI for Memora Connect.

    Features:
    - Toggleable via plugin config
    - Configurable host/port
    - Interactive graph data endpoint
    - CRUD for memories, concepts and connections
    - Person (impression) focused views
    """

    def __init__(self, memory_system: Any, port: int = 8765, host: str = "127.0.0.1", enabled: bool = True) -> None:
        self.ms = memory_system
        self.port = int(port or 8765)
        self.host = host or "127.0.0.1"
        self.enabled = bool(enabled)
        self.app = web.Application()
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self._setup_routes()

    # ---------------------- setup ----------------------
    def _setup_routes(self) -> None:
        # UI
        self.app.router.add_get("/", self._serve_index)

        # Graph and status
        self.app.router.add_get("/api/status", self._get_status)
        self.app.router.add_get("/api/graph", self._get_graph)

        # Concepts
        self.app.router.add_get("/api/concepts", self._list_concepts)
        self.app.router.add_post("/api/concepts", self._create_concept)
        self.app.router.add_delete("/api/concepts/{concept_id}", self._delete_concept)

        # Memories
        self.app.router.add_get("/api/memories", self._list_memories)
        self.app.router.add_post("/api/memories", self._create_memory)
        self.app.router.add_put("/api/memories/{memory_id}", self._update_memory)
        self.app.router.add_delete("/api/memories/{memory_id}", self._delete_memory)

        # Connections
        self.app.router.add_post("/api/connections", self._create_connection)
        self.app.router.add_put("/api/connections/{conn_id}", self._update_connection)
        self.app.router.add_delete("/api/connections/{conn_id}", self._delete_connection)

        # Persons (impressions)
        self.app.router.add_get("/api/persons", self._list_persons)
        self.app.router.add_get("/api/person/summary", self._person_summary)

    async def start(self) -> bool:
        if not self.enabled:
            logger.info("MemoraConnect Web UI disabled by config")
            return False
        try:
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            self.site = web.TCPSite(self.runner, self.host, self.port)
            await self.site.start()
            logger.info(f"MemoraConnect Web UI started at http://{self.host}:{self.port}")
            return True
        except Exception as e:  # pragma: no cover
            logger.error(f"Failed to start Web UI: {e}")
            return False

    async def stop(self) -> None:
        try:
            if self.site:
                await self.site.stop()
                self.site = None
            if self.runner:
                await self.runner.cleanup()
                self.runner = None
            logger.info("MemoraConnect Web UI stopped")
        except Exception as e:  # pragma: no cover
            logger.warning(f"Error when stopping Web UI: {e}")

    # ---------------------- helpers ----------------------
    def _json(self, data: Any, status: int = 200) -> web.Response:
        return web.json_response(data, status=status, dumps=lambda obj: json.dumps(obj, ensure_ascii=False))

    def _bad_request(self, message: str) -> web.Response:
        return self._json({"ok": False, "error": message}, status=400)

    # ---------------------- UI ----------------------
    async def _serve_index(self, request: web.Request) -> web.Response:
        # Serve the static index.html bundled with the plugin
        base_dir = os.path.dirname(os.path.abspath(__file__))
        index_path = os.path.join(base_dir, "web", "index.html")
        if os.path.exists(index_path):
            try:
                with open(index_path, "r", encoding="utf-8") as f:
                    html = f.read()
                return web.Response(text=html, content_type="text/html")
            except Exception:
                pass
        # Fallback lightweight page
        html = """
        <!doctype html>
        <html lang=\"zh\">
        <head>
          <meta charset=\"utf-8\" />
          <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
          <title>Memora Connect Web UI</title>
        </head>
        <body>
          <h1>Memora Connect Web UI</h1>
          <p>Web 资源未打包，请确认插件目录 /web/index.html 是否存在。</p>
        </body>
        </html>
        """
        return web.Response(text=html, content_type="text/html")

    # ---------------------- status/graph ----------------------
    async def _get_status(self, request: web.Request) -> web.Response:
        stats = await self.ms.get_memory_stats() if hasattr(self.ms, "get_memory_stats") else {}
        return self._json({"ok": True, "stats": stats, "web": {"host": self.host, "port": self.port, "enabled": self.enabled}})

    async def _get_graph(self, request: web.Request) -> web.Response:
        params = request.rel_url.query
        group_id = params.get("group_id", "")
        # Optional person filter (name)
        person = params.get("person")

        graph = getattr(self.ms, "memory_graph", None)
        if not graph or not graph.concepts:
            return self._json({"ok": True, "nodes": [], "edges": []})

        # Filter memories by group
        memories = list(graph.memories.values())
        if hasattr(self.ms, "filter_memories_by_group"):
            memories = self.ms.filter_memories_by_group(memories, group_id)

        # If person filter present, restrict to that imprint concept
        concept_ids_from_memories = set(m.concept_id for m in memories)
        concepts = {cid: c for cid, c in graph.concepts.items() if cid in concept_ids_from_memories}

        if person:
            # Expected imprint concept name format: Imprint:{group_id}:{person}
            imprint_name = f"Imprint:{group_id}:{person}"
            concepts = {cid: c for cid, c in concepts.items() if c.name == imprint_name}
            concept_ids_from_memories = set(concepts.keys())
            memories = [m for m in memories if m.concept_id in concept_ids_from_memories]

        # Build stats per concept
        stats_by_cid: Dict[str, Dict[str, float]] = {}
        for m in memories:
            s = stats_by_cid.setdefault(m.concept_id, {"count": 0, "sum_strength": 0.0, "max_strength": 0.0})
            s["count"] += 1
            s["sum_strength"] += float(m.strength or 0.0)
            if float(m.strength or 0.0) > s["max_strength"]:
                s["max_strength"] = float(m.strength or 0.0)
        for cid, s in stats_by_cid.items():
            cnt = max(1, int(s["count"]))
            s["avg_strength"] = s["sum_strength"] / cnt

        nodes = []
        for cid, c in concepts.items():
            s = stats_by_cid.get(cid, {"count": 0, "avg_strength": 0.0, "max_strength": 0.0})
            nodes.append({
                "id": cid,
                "name": c.name,
                "count": s.get("count", 0),
                "avg_strength": s.get("avg_strength", 0.0),
                "max_strength": s.get("max_strength", 0.0),
            })

        selected_ids = {n["id"] for n in nodes}
        # Filter edges: keep only those between selected concepts
        edges = []
        for e in list(graph.connections):
            if e.from_concept in selected_ids and e.to_concept in selected_ids:
                edges.append({
                    "id": e.id,
                    "from_concept": e.from_concept,
                    "to_concept": e.to_concept,
                    "strength": float(e.strength or 0.0),
                })

        return self._json({"ok": True, "group_id": group_id, "nodes": nodes, "edges": edges})

    # ---------------------- concepts ----------------------
    async def _list_concepts(self, request: web.Request) -> web.Response:
        graph = getattr(self.ms, "memory_graph", None)
        if not graph:
            return self._json({"ok": True, "concepts": []})
        concepts = [
            {"id": c.id, "name": c.name, "created_at": c.created_at, "last_accessed": c.last_accessed, "access_count": c.access_count}
            for c in graph.concepts.values()
        ]
        return self._json({"ok": True, "concepts": concepts})

    async def _create_concept(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            name = str(data.get("name", "")).strip()
            if not name:
                return self._bad_request("缺少 name")
            cid = self.ms.memory_graph.add_concept(name)
            await self.ms._queue_save_memory_state("")
            return self._json({"ok": True, "id": cid})
        except Exception as e:
            logger.error(f"create concept error: {e}")
            return self._bad_request("创建失败")

    async def _delete_concept(self, request: web.Request) -> web.Response:
        concept_id = request.match_info.get("concept_id", "")
        if not concept_id:
            return self._bad_request("缺少概念ID")
        try:
            # Remove memories under this concept first
            mem_ids = [m.id for m in self.ms.memory_graph.memories.values() if m.concept_id == concept_id]
            for mid in mem_ids:
                await self._delete_memory_impl(mid)
            # Remove concept in memory graph
            if concept_id in self.ms.memory_graph.concepts:
                del self.ms.memory_graph.concepts[concept_id]
            # Remove connections that involve this concept
            to_remove = [c.id for c in self.ms.memory_graph.connections if c.from_concept == concept_id or c.to_concept == concept_id]
            for cid in to_remove:
                await self._delete_connection_impl(cid)
            await self.ms._queue_save_memory_state("")
            return self._json({"ok": True})
        except Exception as e:
            logger.error(f"delete concept error: {e}")
            return self._bad_request("删除失败")

    # ---------------------- memories ----------------------
    async def _list_memories(self, request: web.Request) -> web.Response:
        params = request.rel_url.query
        group_id = params.get("group_id", "")
        concept_id = params.get("concept_id")
        graph = getattr(self.ms, "memory_graph", None)
        if not graph:
            return self._json({"ok": True, "memories": []})
        mems = list(graph.memories.values())
        mems = self.ms.filter_memories_by_group(mems, group_id) if hasattr(self.ms, "filter_memories_by_group") else mems
        if concept_id:
            mems = [m for m in mems if m.concept_id == concept_id]
        memories = [
            {
                "id": m.id,
                "concept_id": m.concept_id,
                "content": m.content,
                "details": m.details,
                "participants": m.participants,
                "location": m.location,
                "emotion": m.emotion,
                "tags": m.tags,
                "created_at": m.created_at,
                "last_accessed": m.last_accessed,
                "access_count": m.access_count,
                "strength": float(m.strength or 0.0),
                "group_id": getattr(m, "group_id", ""),
            }
            for m in mems
        ]
        return self._json({"ok": True, "memories": memories})

    async def _create_memory(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            content = str(data.get("content", "")).strip()
            if not content:
                return self._bad_request("缺少 content")
            concept_id = data.get("concept_id")
            concept_name = data.get("concept_name")
            group_id = str(data.get("group_id", ""))

            if not concept_id and concept_name:
                concept_id = self.ms.memory_graph.add_concept(str(concept_name).strip())
            if not concept_id:
                return self._bad_request("缺少 concept_id 或 concept_name")

            details = str(data.get("details", ""))
            participants = str(data.get("participants", ""))
            location = str(data.get("location", ""))
            emotion = str(data.get("emotion", ""))
            tags = str(data.get("tags", ""))
            strength = float(data.get("strength", 1.0))

            mid = self.ms.memory_graph.add_memory(
                content=content,
                concept_id=concept_id,
                details=details,
                participants=participants,
                location=location,
                emotion=emotion,
                tags=tags,
                strength=strength,
                group_id=group_id,
            )
            await self.ms._queue_save_memory_state(group_id)
            return self._json({"ok": True, "id": mid})
        except Exception as e:
            logger.error(f"create memory error: {e}")
            return self._bad_request("创建失败")

    async def _update_memory(self, request: web.Request) -> web.Response:
        memory_id = request.match_info.get("memory_id", "")
        if not memory_id:
            return self._bad_request("缺少记忆ID")
        try:
            data = await request.json()
            m = self.ms.memory_graph.memories.get(memory_id)
            if not m:
                return self._bad_request("记忆不存在")
            # Update fields
            for field in ["content", "details", "participants", "location", "emotion", "tags"]:
                if field in data:
                    setattr(m, field, str(data.get(field, "")))
            if "strength" in data:
                try:
                    m.strength = float(data["strength"])  # type: ignore
                except Exception:
                    pass
            m.last_accessed = m.last_accessed  # keep
            # Persist immediately to DB for stronger consistency
            await self._update_memory_db(m)
            await self.ms._queue_save_memory_state(getattr(m, "group_id", ""))
            return self._json({"ok": True})
        except Exception as e:
            logger.error(f"update memory error: {e}")
            return self._bad_request("更新失败")

    async def _delete_memory(self, request: web.Request) -> web.Response:
        memory_id = request.match_info.get("memory_id", "")
        if not memory_id:
            return self._bad_request("缺少记忆ID")
        try:
            await self._delete_memory_impl(memory_id)
            return self._json({"ok": True})
        except Exception as e:
            logger.error(f"delete memory error: {e}")
            return self._bad_request("删除失败")

    async def _delete_memory_impl(self, memory_id: str) -> None:
        m = self.ms.memory_graph.memories.get(memory_id)
        group_id = getattr(m, "group_id", "") if m else ""
        # Remove from in-memory graph
        self.ms.memory_graph.remove_memory(memory_id)
        # Remove from DB
        try:
            db_path = self.ms._get_group_db_path(group_id)
            conn = self.ms.resource_manager.get_db_connection(db_path) if hasattr(self.ms, "resource_manager") else None
        except Exception:
            conn = None
        # The memory system exposes resource_manager via module-level import; fallback to direct sqlite3 if needed
        if conn is None:
            import sqlite3
            conn = sqlite3.connect(self.ms.db_path)
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            conn.commit()
        finally:
            try:
                # Try release via resource_manager if available
                if hasattr(self.ms, "resource_manager") and hasattr(self.ms.resource_manager, "release_db_connection"):
                    self.ms.resource_manager.release_db_connection(self.ms.db_path, conn)  # type: ignore
                else:
                    conn.close()
            except Exception:
                pass
        await self.ms._queue_save_memory_state(group_id)

    async def _update_memory_db(self, m: Any) -> None:
        group_id = getattr(m, "group_id", "")
        try:
            db_path = self.ms._get_group_db_path(group_id)
            conn = None
            try:
                from .resource_management import resource_manager as rm  # type: ignore
                conn = rm.get_db_connection(db_path)
            except Exception:
                import sqlite3
                conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE memories
                SET content=?, details=?, participants=?, location=?, emotion=?, tags=?, strength=?
                WHERE id=?
                """,
                (
                    m.content,
                    m.details,
                    m.participants,
                    m.location,
                    m.emotion,
                    m.tags,
                    float(m.strength or 0.0),
                    m.id,
                ),
            )
            conn.commit()
        except Exception as e:
            logger.warning(f"Failed to update memory in DB: {e}")
        finally:
            try:
                from .resource_management import resource_manager as rm  # type: ignore
                rm.release_db_connection(db_path, conn)  # type: ignore
            except Exception:
                try:
                    conn.close()  # type: ignore
                except Exception:
                    pass

    # ---------------------- connections ----------------------
    async def _create_connection(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            from_c = str(data.get("from_concept", ""))
            to_c = str(data.get("to_concept", ""))
            if not from_c or not to_c:
                return self._bad_request("缺少 from_concept 或 to_concept")
            strength = float(data.get("strength", 1.0))
            cid = self.ms.memory_graph.add_connection(from_c, to_c, strength=strength)
            await self.ms._queue_save_memory_state("")
            return self._json({"ok": True, "id": cid})
        except Exception as e:
            logger.error(f"create connection error: {e}")
            return self._bad_request("创建失败")

    async def _update_connection(self, request: web.Request) -> web.Response:
        conn_id = request.match_info.get("conn_id", "")
        if not conn_id:
            return self._bad_request("缺少连接ID")
        try:
            data = await request.json()
            strength = data.get("strength")
            if strength is None:
                return self._bad_request("缺少 strength")
            # Find connection and update
            for c in self.ms.memory_graph.connections:
                if c.id == conn_id:
                    try:
                        c.strength = float(strength)  # type: ignore
                    except Exception:
                        pass
                    c.last_strengthened = c.last_strengthened
                    await self._update_connection_db(c)
                    await self.ms._queue_save_memory_state("")
                    return self._json({"ok": True})
            return self._bad_request("连接不存在")
        except Exception as e:
            logger.error(f"update connection error: {e}")
            return self._bad_request("更新失败")

    async def _delete_connection(self, request: web.Request) -> web.Response:
        conn_id = request.match_info.get("conn_id", "")
        if not conn_id:
            return self._bad_request("缺少连接ID")
        try:
            await self._delete_connection_impl(conn_id)
            return self._json({"ok": True})
        except Exception as e:
            logger.error(f"delete connection error: {e}")
            return self._bad_request("删除失败")

    async def _delete_connection_impl(self, conn_id: str) -> None:
        # Remove from memory graph first (will keep adjacency list consistent)
        self.ms.memory_graph.remove_connection(conn_id)
        # Remove from DB
        try:
            from .resource_management import resource_manager as rm  # type: ignore
            db_path = self.ms.db_path
            conn = rm.get_db_connection(db_path)
            cur = conn.cursor()
            cur.execute("DELETE FROM connections WHERE id = ?", (conn_id,))
            conn.commit()
            rm.release_db_connection(db_path, conn)
        except Exception:
            # Fallback to sqlite3
            import sqlite3
            try:
                conn = sqlite3.connect(self.ms.db_path)
                cur = conn.cursor()
                cur.execute("DELETE FROM connections WHERE id = ?", (conn_id,))
                conn.commit()
                conn.close()
            except Exception:
                pass

    async def _update_connection_db(self, c: Any) -> None:
        try:
            from .resource_management import resource_manager as rm  # type: ignore
            db_path = self.ms.db_path
            conn = rm.get_db_connection(db_path)
            cur = conn.cursor()
            cur.execute(
                "UPDATE connections SET strength=?, last_strengthened=? WHERE id=?",
                (float(c.strength or 0.0), float(c.last_strengthened or 0.0), c.id),
            )
            conn.commit()
            rm.release_db_connection(db_path, conn)
        except Exception:
            import sqlite3
            try:
                conn = sqlite3.connect(self.ms.db_path)
                cur = conn.cursor()
                cur.execute(
                    "UPDATE connections SET strength=?, last_strengthened=? WHERE id=?",
                    (float(c.strength or 0.0), float(c.last_strengthened or 0.0), c.id),
                )
                conn.commit()
                conn.close()
            except Exception:
                pass

    # ---------------------- persons (impressions) ----------------------
    async def _list_persons(self, request: web.Request) -> web.Response:
        params = request.rel_url.query
        group_id = params.get("group_id", "")
        graph = getattr(self.ms, "memory_graph", None)
        if not graph:
            return self._json({"ok": True, "persons": []})

        persons: List[Dict[str, Any]] = []
        prefix = f"Imprint:{group_id}:"
        for c in graph.concepts.values():
            if c.name.startswith(prefix):
                name = c.name[len(prefix):]
                try:
                    score = self.ms.get_impression_score(group_id, name)
                except Exception:
                    score = 0.5
                persons.append({"concept_id": c.id, "name": name, "score": score})
        return self._json({"ok": True, "persons": persons})

    async def _person_summary(self, request: web.Request) -> web.Response:
        params = request.rel_url.query
        group_id = params.get("group_id", "")
        name = params.get("name")
        if not name:
            return self._bad_request("缺少 name")
        try:
            summary = self.ms.get_person_impression_summary(group_id, name)
            memories = self.ms.get_person_impression_memories(group_id, name, limit=20)
            return self._json({"ok": True, "summary": summary, "memories": memories})
        except Exception as e:
            logger.error(f"person summary error: {e}")
            return self._bad_request("查询失败")
