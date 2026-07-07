"""
核心记忆系统
模仿人类海马体功能，处理记忆的形成、提取、遗忘和巩固
"""

import asyncio
import json
import os
import random
import re
import time
from datetime import datetime
from typing import Any

try:
    from astrbot.api import logger
    from astrbot.api.event import AstrMessageEvent
    from astrbot.api.provider import ProviderRequest
    from astrbot.api.star import Context, StarTools

    from ..infrastructure.database import SmartDatabaseMigration
    from ..infrastructure.embedding import EmbeddingCacheManager
    from ..infrastructure.resources import resource_manager
    from .config import MemoryConfigManager
    from .memory_graph import MemoryGraph
    from .models import Concept, Connection, Memory
except ImportError:
    # Fallback for testing without astrbot
    import logging

    logger = logging.getLogger(__name__)
    from config import MemoryConfigManager
    from memory_graph import MemoryGraph
    from models import Concept, Memory

    ProviderRequest = None
    AstrMessageEvent = None
    Context = None
    StarTools = None
    resource_manager = None
    SmartDatabaseMigration = None
    EmbeddingCacheManager = None


class MemorySystem:
    """核心记忆系统，模仿人类海马体功能"""

    @staticmethod
    def filter_memories_by_group(
        memories: list["Memory"], group_id: str = ""
    ) -> list["Memory"]:
        """
        统一的群聊隔离过滤函数

        Args:
            memories: 记忆列表
            group_id: 群组ID，如果为空字符串则获取默认记忆

        Returns:
            过滤后的记忆列表
        """
        if not group_id:
            # 私聊场景：只获取没有group_id的记忆
            return [m for m in memories if not hasattr(m, "group_id") or not m.group_id]
        else:
            # 群聊场景：只获取匹配group_id的记忆
            return [
                m for m in memories if hasattr(m, "group_id") and m.group_id == group_id
            ]

    def __init__(self, context: Context, config=None, data_dir=None):
        self.context = context

        # 初始化配置管理器
        self.config_manager = MemoryConfigManager(config)

        # 检查记忆系统是否启用
        if not self.config_manager.is_memory_system_enabled():
            logger.info("记忆系统已禁用，跳过初始化")
            self.memory_system_enabled = False
            return

        self.memory_system_enabled = True

        # 使用AstrBot标准数据目录
        if data_dir:
            self.db_path = str(data_dir / "memory.db")
        else:
            data_dir = StarTools.get_data_dir() / "memora_connect"
            self.db_path = str(data_dir / "memory.db")

        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        logger.info(f"记忆数据库路径: {self.db_path}")

        self.memory_graph = MemoryGraph()
        self.llm_provider = None
        self.embedding_provider = None
        self.embedding_cache = None  # 嵌入向量缓存管理器

        # 组件引用（由外部注入）
        self.topic_analyzer = None
        self.user_profiling = None

        # 印象系统配置
        self.impression_config = {
            "default_score": 0.5,
            "enable_impression_injection": config.get(
                "enable_impression_injection", True
            ),
            "min_score": 0.0,
            "max_score": 1.0,
        }

        # 配置初始化
        self.memory_config = config or {}

        # 群聊隔离的数据库表前缀映射
        self.group_table_prefixes = {}

        # 日志限制计数器
        self.debug_log_count = 0
        self.debug_log_reset_time = time.time()

        # 优化：缓存和批量操作
        self._save_cache = {}  # 保存缓存 {group_id: pending_changes}
        self._save_locks = {}  # 保存锁 {group_id: asyncio.Lock}
        self._last_save_time = {}  # 最后保存时间 {group_id: timestamp}
        self._pending_save_tasks: dict[str, asyncio.Task] = {}  # 按 group_id 分的待处理保存任务

        # 异步任务生命周期管理 - 新增
        self._managed_tasks = set()  # 管理的异步任务集合
        self._maintenance_task = None  # 维护循环任务
        self._should_stop_maintenance = asyncio.Event()  # 停止维护事件
        self._should_stop_maintenance.clear()  # 初始不停止

    def set_components(self, topic_analyzer, user_profiling):
        """注入组件依赖"""
        self.topic_analyzer = topic_analyzer
        self.user_profiling = user_profiling

    def _create_managed_task(self, coro):
        """创建托管的异步任务，确保任务生命周期被正确管理"""
        if not asyncio.iscoroutine(coro):
            self._debug_log("无法创建任务：传入的不是协程对象", "warning")
            return

        # 使用事件循环管理器创建任务
        task = resource_manager.create_task(coro)
        self._managed_tasks.add(task)

        self._debug_log(
            f"创建新任务: {coro.__name__}。当前任务数: {len(self._managed_tasks)}",
            "debug",
        )

        # 添加任务完成回调，自动清理
        def _task_done_callback(t):
            self._managed_tasks.discard(t)
            if t.exception():
                self._debug_log(f"托管任务异常: {t.exception()}", "error")
            self._debug_log(
                f"任务 {coro.__name__} 完成。当前任务数: {len(self._managed_tasks)}",
                "debug",
            )

        task.add_done_callback(_task_done_callback)
        return task

    async def _cancel_all_managed_tasks(self):
        """取消所有托管的异步任务"""
        if not self._managed_tasks:
            return

        # 取消所有任务
        for task in self._managed_tasks:
            if not task.done():
                task.cancel()

        # 等待所有任务完成或取消
        if self._managed_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._managed_tasks, return_exceptions=True),
                    timeout=5.0,
                )
            except asyncio.TimeoutError:
                # 如果超时，强制清理
                self._managed_tasks.clear()

        self._debug_log("已清理所有托管任务", "debug")

    def _get_group_db_path(self, group_id: str) -> str:
        """获取群聊专用的数据库路径 - 统一使用主数据库，通过逻辑隔离实现群聊分离"""
        # 统一使用主数据库，通过 group_id 字段实现逻辑隔离
        return self.db_path

    def _extract_group_id_from_event(self, event: AstrMessageEvent) -> str:
        """从事件中提取群聊ID"""
        group_id = event.get_group_id()
        return group_id if group_id else ""

    def _record_memory_access_by_ids(self, memory_ids: list[str]) -> int:
        if not memory_ids:
            return 0
        updated = 0
        now = time.time()
        for memory_id in set(memory_ids):
            memory = self.memory_graph.memories.get(memory_id)
            if not memory:
                continue
            memory.access_count = int(memory.access_count or 0) + 1
            memory.last_accessed = now
            updated += 1
        return updated

    def _record_memory_access_by_contents(self, contents: list[str]) -> int:
        if not contents:
            return 0
        content_set = {c for c in contents if c}
        if not content_set:
            return 0
        updated = 0
        now = time.time()
        for memory in self.memory_graph.memories.values():
            if memory.content in content_set:
                memory.access_count = int(memory.access_count or 0) + 1
                memory.last_accessed = now
                updated += 1
        return updated

    def _record_recall_results_accesses(self, results: list[Any]) -> int:
        if not results:
            return 0
        memory_ids = []
        contents = []
        for result in results:
            metadata = getattr(result, "metadata", None)
            memory_id = (
                metadata.get("memory_id") if isinstance(metadata, dict) else None
            )
            if memory_id:
                memory_ids.append(memory_id)
            else:
                memory_content = getattr(result, "memory", None)
                if memory_content:
                    contents.append(memory_content)
        updated = self._record_memory_access_by_ids(memory_ids)
        updated += self._record_memory_access_by_contents(contents)
        return updated

    async def _queue_save_memory_state(self, group_id: str = ""):
        """队列化保存操作，减少频繁的I/O"""
        try:
            # 获取或创建锁
            if group_id not in self._save_locks:
                self._save_locks[group_id] = asyncio.Lock()

            async with self._save_locks[group_id]:
                # 获取最后保存时间
                last_save = self._last_save_time.get(group_id, 0)
                current_time = time.time()

                # 如果距离上次保存时间少于2秒，延迟保存
                if current_time - last_save < 2:
                    # 取消该 group_id 之前的保存任务
                    if group_id in self._pending_save_tasks:
                        old_task = self._pending_save_tasks[group_id]
                        if not old_task.done():
                            old_task.cancel()

                    # 创建新的延迟保存任务
                    self._pending_save_tasks[group_id] = asyncio.create_task(
                        self._delayed_save(group_id, current_time)
                    )
                else:
                    # 立即保存
                    await self.save_memory_state(group_id)
                    self._last_save_time[group_id] = current_time

        except Exception as e:
            self._debug_log(f"队列保存失败: {e}", "warning")

    async def _delayed_save(self, group_id: str, creation_time: float):
        """延迟保存任务"""
        try:
            # 延迟2秒执行
            await asyncio.sleep(2)

            # 检查是否还有新的保存请求
            if self._last_save_time.get(group_id, 0) > creation_time:
                return  # 如果有更新的请求，跳过这次保存

            # 执行实际保存
            await self.save_memory_state(group_id)
            self._last_save_time[group_id] = time.time()

        except asyncio.CancelledError:
            pass  # 任务被取消，正常情况
        except Exception as e:
            self._debug_log(f"延迟保存失败: {e}", "warning")

    def _debug_log(self, message: str, level: str = "debug"):
        """优化的调试日志输出，限制日志频率"""
        current_time = time.time()

        # 每分钟重置计数器
        if current_time - self.debug_log_reset_time > 60:
            self.debug_log_count = 0
            self.debug_log_reset_time = current_time

        # 限制每分钟最多10条调试日志
        if level == "debug" and self.debug_log_count >= 10:
            return

        if level == "debug":
            self.debug_log_count += 1

        # 使用不同的日志级别
        if level == "debug":
            logger.debug(message)
        elif level == "info":
            logger.info(message)
        elif level == "warning":
            logger.warning(message)
        elif level == "error":
            logger.error(message)

    async def initialize(self):
        """初始化记忆系统"""
        # 检查记忆系统是否启用
        if not self.memory_system_enabled:
            self._debug_log("记忆系统已禁用，跳过初始化", "info")
            return

        self._debug_log("开始初始化记忆系统...", "info")

        # 检查默认数据库文件状态
        if os.path.exists(self.db_path):
            file_size = os.path.getsize(self.db_path)
            self._debug_log(f"默认数据库文件存在，大小: {file_size} 字节", "info")
        else:
            self._debug_log("默认数据库文件不存在，将创建新数据库", "info")

        # 测试提供商连接 - 简化为单一日志
        llm_ready = False
        embedding_ready = False

        try:
            llm_provider = await self.get_llm_provider()
            if llm_provider:
                llm_ready = True

            embedding_provider = await self.get_embedding_provider()
            if embedding_provider:
                embedding_ready = True

            self._debug_log(
                f"提供商状态 - LLM: {'已连接' if llm_ready else '未连接'}, 嵌入: {'已连接' if embedding_ready else '未连接'}",
                "info",
            )
        except Exception:
            self._debug_log("提供商连接异常，系统将继续运行", "warning")

        migration = None
        migration_success = False

        # 执行数据库迁移
        try:
            if SmartDatabaseMigration is None:
                raise RuntimeError("SmartDatabaseMigration 不可用")

            migration = SmartDatabaseMigration(self.db_path, self.context)

            # 1. 先执行主数据库迁移
            migration_success = await migration.run_smart_migration()

            if migration_success:
                self._debug_log("主数据库迁移成功", "info")
            else:
                self._debug_log("主数据库迁移失败，记忆系统可能无法正常工作", "error")

        except Exception as e:
            self._debug_log(f"主数据库迁移过程异常: {e}", "error")
            migration_success = False

        # 3. 主数据库迁移成功即可继续初始化；嵌入缓存迁移失败则降级为非语义模式
        if migration_success:
            try:
                # 加载默认数据库（用于私有对话）
                self.load_memory_state()
                asyncio.create_task(self.memory_maintenance_loop())

                # 初始化嵌入向量缓存管理器
                if EmbeddingCacheManager is not None:
                    try:
                        self.embedding_cache = EmbeddingCacheManager(self, self.db_path)
                        await self.embedding_cache.initialize()
                    except Exception as cache_e:
                        self.embedding_cache = None
                        self._debug_log(
                            f"嵌入向量缓存初始化失败，已降级: {cache_e}", "warning"
                        )

                # 调度初始预计算任务
                if self.embedding_cache and self.memory_graph.memories:
                    asyncio.create_task(
                        self.embedding_cache.schedule_initial_precompute()
                    )
                    logger.info(
                        f"已调度 {len(self.memory_graph.memories)} 条记忆的预计算任务"
                    )

                self._debug_log("记忆系统初始化完成", "info")
            except Exception as init_e:
                self._debug_log(f"记忆系统初始化失败: {init_e}", "error")
        else:
            self._debug_log("由于数据库迁移失败，跳过记忆系统初始化", "warning")

    def load_memory_state(self, group_id: str = ""):
        """从数据库加载记忆状态"""
        import os

        db_path = self._get_group_db_path(group_id)

        if not os.path.exists(db_path):
            return

        conn = None
        try:
            conn = resource_manager.get_db_connection(db_path)
            cursor = conn.cursor()

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing_tables = {row[0] for row in cursor.fetchall()}

            has_elements = "elements" in existing_tables

            if has_elements:
                cursor.execute(
                    "SELECT id, name, category, group_id, created_at, last_accessed, access_count FROM elements"
                )
                elements = cursor.fetchall()
                for elem_data in elements:
                    self.memory_graph.add_element(
                        name=elem_data[1],
                        category=elem_data[2],
                        group_id=elem_data[3] or "",
                        element_id=elem_data[0],
                        created_at=elem_data[4],
                        last_accessed=elem_data[5],
                        access_count=elem_data[6],
                    )

                cursor.execute("SELECT element_id, memory_id, role FROM element_memories")
                em_rows = cursor.fetchall()
                for em_data in em_rows:
                    self.memory_graph.link_memory(em_data[0], em_data[1], em_data[2] or "")

            if "concepts" in existing_tables:
                cursor.execute(
                    "SELECT id, name, created_at, last_accessed, access_count FROM concepts"
                )
                concepts = cursor.fetchall()
                for concept_data in concepts:
                    self.memory_graph.add_concept(
                        concept_id=concept_data[0],
                        name=concept_data[1],
                        created_at=concept_data[2],
                        last_accessed=concept_data[3],
                        access_count=concept_data[4],
                    )

            cursor.execute("PRAGMA table_info('memories')")
            memory_columns = [col[1] for col in cursor.fetchall()]
            has_allow_forget = "allow_forget" in memory_columns
            has_concept_id = "concept_id" in memory_columns

            if has_allow_forget and not has_concept_id:
                if group_id:
                    cursor.execute(
                        "SELECT id, content, details, emotion, created_at, last_accessed, access_count, strength, allow_forget FROM memories WHERE group_id = ?",
                        (group_id,),
                    )
                else:
                    cursor.execute(
                        "SELECT id, content, details, emotion, created_at, last_accessed, access_count, strength, allow_forget FROM memories WHERE group_id = '' OR group_id IS NULL"
                    )
                mem_rows = cursor.fetchall()
                for md in mem_rows:
                    allow_forget = True if md[8] is None else bool(md[8])
                    self.memory_graph.add_memory(
                        content=md[1],
                        memory_id=md[0],
                        details=md[2] or "",
                        emotion=md[3] or "",
                        created_at=md[4],
                        last_accessed=md[5],
                        access_count=md[6],
                        strength=md[7],
                        allow_forget=allow_forget,
                        group_id=group_id,
                    )
            elif has_allow_forget:
                if group_id:
                    cursor.execute(
                        "SELECT id, concept_id, content, details, participants, location, emotion, tags, created_at, last_accessed, access_count, strength, allow_forget FROM memories WHERE group_id = ?",
                        (group_id,),
                    )
                else:
                    cursor.execute(
                        "SELECT id, concept_id, content, details, participants, location, emotion, tags, created_at, last_accessed, access_count, strength, allow_forget FROM memories WHERE group_id = '' OR group_id IS NULL"
                    )
                mem_rows = cursor.fetchall()
                for md in mem_rows:
                    allow_forget = True if md[12] is None else bool(md[12])
                    self.memory_graph.add_memory(
                        content=md[2],
                        memory_id=md[0],
                        details=md[3] or "",
                        participants=md[4] or "",
                        location=md[5] or "",
                        emotion=md[6] or "",
                        tags=md[7] or "",
                        created_at=md[8],
                        last_accessed=md[9],
                        access_count=md[10],
                        strength=md[11],
                        allow_forget=allow_forget,
                        group_id=group_id,
                    )
            else:
                if group_id:
                    cursor.execute(
                        "SELECT id, concept_id, content, details, participants, location, emotion, tags, created_at, last_accessed, access_count, strength FROM memories WHERE group_id = ?",
                        (group_id,),
                    )
                else:
                    cursor.execute(
                        "SELECT id, concept_id, content, details, participants, location, emotion, tags, created_at, last_accessed, access_count, strength FROM memories WHERE group_id = '' OR group_id IS NULL"
                    )
                mem_rows = cursor.fetchall()
                for md in mem_rows:
                    self.memory_graph.add_memory(
                        content=md[2],
                        memory_id=md[0],
                        details=md[3] or "",
                        participants=md[4] or "",
                        location=md[5] or "",
                        emotion=md[6] or "",
                        tags=md[7] or "",
                        created_at=md[8],
                        last_accessed=md[9],
                        access_count=md[10],
                        strength=md[11],
                        group_id=group_id,
                    )

            if "connections" in existing_tables:
                cursor.execute("PRAGMA table_info('connections')")
                conn_columns = {col[1] for col in cursor.fetchall()}

                if "from_element" in conn_columns:
                    cursor.execute(
                        "SELECT id, from_element, to_element, strength, last_strengthened FROM connections"
                    )
                else:
                    cursor.execute(
                        "SELECT id, from_concept, to_concept, strength, last_strengthened FROM connections"
                    )
                connections = cursor.fetchall()
                for conn_data in connections:
                    self.memory_graph.add_connection(
                        from_element=conn_data[1],
                        to_element=conn_data[2],
                        strength=conn_data[3],
                        connection_id=conn_data[0],
                        last_strengthened=conn_data[4],
                    )

            elem_count = len(self.memory_graph.elements)
            mem_count = len(self.memory_graph.memories)
            group_info = f" (群: {group_id})" if group_id else ""
            self._debug_log(
                f"记忆系统加载{group_info}，包含 {elem_count} 个元素，{mem_count} 条记忆",
                "debug",
            )

        except Exception as e:
            self._debug_log(f"状态加载异常: {e}", "error")
        finally:
            if conn is not None:
                resource_manager.release_db_connection(db_path, conn)

    async def save_memory_state(self, group_id: str = ""):
        """保存记忆状态到数据库"""
        try:
            db_path = self._get_group_db_path(group_id)
            await self._ensure_database_structure(db_path)
            conn = resource_manager.get_db_connection(db_path)
            cursor = conn.cursor()
            cursor.execute("BEGIN TRANSACTION")

            try:
                for element in self.memory_graph.elements.values():
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO elements
                        (id, name, category, group_id, created_at, last_accessed, access_count)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            element.id,
                            element.name,
                            element.category,
                            element.group_id,
                            element.created_at,
                            element.last_accessed,
                            element.access_count,
                        ),
                    )

                for memory in self.memory_graph.memories.values():
                    cursor.execute("PRAGMA table_info('memories')")
                    mem_cols = {col[1] for col in cursor.fetchall()}
                    if "concept_id" in mem_cols:
                        cursor.execute(
                            """
                            INSERT OR REPLACE INTO memories
                            (id, content, details, emotion, created_at, last_accessed, access_count, strength, allow_forget, group_id, concept_id, participants, location, tags)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', '', '', '')
                        """,
                            (
                                memory.id,
                                memory.content,
                                getattr(memory, 'details', '') or '',
                                getattr(memory, 'emotion', '') or '',
                                memory.created_at,
                                memory.last_accessed,
                                memory.access_count,
                                memory.strength,
                                int(bool(memory.allow_forget)),
                                group_id,
                            ),
                        )
                    else:
                        cursor.execute(
                            """
                            INSERT OR REPLACE INTO memories
                            (id, content, details, emotion, created_at, last_accessed, access_count, strength, allow_forget, group_id)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                            (
                                memory.id,
                                memory.content,
                                getattr(memory, 'details', '') or '',
                                getattr(memory, 'emotion', '') or '',
                                memory.created_at,
                                memory.last_accessed,
                                memory.access_count,
                                memory.strength,
                                int(bool(memory.allow_forget)),
                                group_id,
                            ),
                        )

                cursor.execute("DELETE FROM element_memories")
                for em in self.memory_graph.element_memories:
                    cursor.execute(
                        "INSERT OR REPLACE INTO element_memories (element_id, memory_id, role) VALUES (?, ?, ?)",
                        (em.element_id, em.memory_id, em.role),
                    )

                cursor.execute("PRAGMA table_info('connections')")
                conn_cols = {col[1] for col in cursor.fetchall()}
                from_col = "from_element" if "from_element" in conn_cols else "from_concept"
                to_col = "to_element" if "to_element" in conn_cols else "to_concept"

                existing_connections = set()
                cursor.execute("SELECT id FROM connections")
                for row in cursor.fetchall():
                    existing_connections.add(row[0])

                for conn_obj in self.memory_graph.connections:
                    if conn_obj.id in existing_connections:
                        cursor.execute(
                            f"UPDATE connections SET {from_col}=?, {to_col}=?, strength=?, last_strengthened=? WHERE id=?",
                            (
                                conn_obj.from_element,
                                conn_obj.to_element,
                                conn_obj.strength,
                                conn_obj.last_strengthened,
                                conn_obj.id,
                            ),
                        )
                    else:
                        cursor.execute(
                            f"INSERT INTO connections (id, {from_col}, {to_col}, strength, last_strengthened) VALUES (?, ?, ?, ?, ?)",
                            (
                                conn_obj.id,
                                conn_obj.from_element,
                                conn_obj.to_element,
                                conn_obj.strength,
                                conn_obj.last_strengthened,
                            ),
                        )

                conn.commit()
                resource_manager.release_db_connection(db_path, conn)

                group_info = f" (群: {group_id})" if group_id else ""
                self._debug_log(
                    f"记忆保存完成{group_info}: {len(self.memory_graph.elements)}个元素, {len(self.memory_graph.memories)}条记忆",
                    "debug",
                )

            except Exception as e:
                try:
                    conn.rollback()
                except Exception as rollback_e:
                    self._debug_log(f"回滚失败: {rollback_e}", "error")
                resource_manager.release_db_connection(db_path, conn)
                self._debug_log(f"保存失败: {e}", "error")
                raise

        except Exception as e:
            self._debug_log(f"保存过程异常: {e}", "error")

    async def delete_memory_by_id(self, memory_id: str, group_id: str = "") -> bool:
        conn = None
        try:
            if not memory_id:
                return False

            removed_from_graph = False
            if memory_id in self.memory_graph.memories:
                self.memory_graph.remove_memory(memory_id)
                removed_from_graph = True

            db_path = self._get_group_db_path(group_id)
            await self._ensure_database_structure(db_path)
            conn = resource_manager.get_db_connection(db_path)
            cursor = conn.cursor()

            if group_id:
                cursor.execute(
                    "DELETE FROM memories WHERE id = ? AND group_id = ?",
                    (memory_id, group_id),
                )
            else:
                cursor.execute("DELETE FROM memories WHERE id = ?", (memory_id,))

            deleted_rows = cursor.rowcount
            conn.commit()
            resource_manager.release_db_connection(db_path, conn)
            conn = None  # 已释放

            if self.embedding_cache:
                await self.embedding_cache.delete_embedding(memory_id, group_id)

            return removed_from_graph or deleted_rows > 0
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            self._debug_log(f"删除记忆失败: {e}", "error")
            return False
        finally:
            if conn:
                resource_manager.release_db_connection(db_path, conn)

    async def _ensure_database_structure(self, db_path: str):
        """确保数据库和所需的表结构存在"""
        conn = None
        try:
            conn = resource_manager.get_db_connection(db_path)
            cursor = conn.cursor()

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing_tables = {row[0] for row in cursor.fetchall()}

            has_legacy = "concepts" in existing_tables and "elements" not in existing_tables

            if has_legacy:
                self._migrate_legacy_to_elements(cursor, conn, db_path)
                conn.commit()
                resource_manager.release_db_connection(db_path, conn)
                conn = None  # 已释放，避免 finally 重复释放
                self.memory_graph = MemoryGraph()
                self.load_memory_state("")
                return

            if "elements" not in existing_tables:
                cursor.execute("""
                    CREATE TABLE elements (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        category TEXT NOT NULL,
                        group_id TEXT DEFAULT '',
                        created_at REAL,
                        last_accessed REAL,
                        access_count INTEGER DEFAULT 0
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_elements_category ON elements(category)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_elements_group ON elements(group_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_elements_name ON elements(name)")
                self._debug_log("创建表: elements", "debug")

            if "element_memories" not in existing_tables:
                cursor.execute("""
                    CREATE TABLE element_memories (
                        element_id TEXT NOT NULL,
                        memory_id TEXT NOT NULL,
                        role TEXT DEFAULT '',
                        PRIMARY KEY (element_id, memory_id)
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_em_element ON element_memories(element_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_em_memory ON element_memories(memory_id)")
                self._debug_log("创建表: element_memories", "debug")

            if "concepts" not in existing_tables:
                cursor.execute("""
                    CREATE TABLE concepts (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        created_at REAL,
                        last_accessed REAL,
                        access_count INTEGER DEFAULT 0
                    )
                """)
                self._debug_log("创建表: concepts (兼容)", "debug")

            if "memories" not in existing_tables:
                cursor.execute("""
                    CREATE TABLE memories (
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
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_group_id ON memories(group_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_created_group ON memories(created_at, group_id)")
                self._debug_log("创建表: memories", "debug")
            else:
                cursor.execute("PRAGMA table_info('memories')")
                memory_columns = {col[1] for col in cursor.fetchall()}
                if "allow_forget" not in memory_columns:
                    cursor.execute(
                        "ALTER TABLE memories ADD COLUMN allow_forget INTEGER DEFAULT 1"
                    )
                    cursor.execute(
                        "UPDATE memories SET allow_forget = 1 WHERE allow_forget IS NULL"
                    )

            if "connections" not in existing_tables:
                cursor.execute("""
                    CREATE TABLE connections (
                        id TEXT PRIMARY KEY,
                        from_element TEXT NOT NULL,
                        to_element TEXT NOT NULL,
                        strength REAL DEFAULT 1.0,
                        last_strengthened REAL
                    )
                """)
                self._debug_log("创建表: connections", "debug")

            conn.commit()
            resource_manager.release_db_connection(db_path, conn)
            conn = None  # 已释放，避免 finally 重复释放

        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            self._debug_log(f"确保数据库结构异常: {e}", "error")
            raise
        finally:
            if conn:
                resource_manager.release_db_connection(db_path, conn)

    def _migrate_legacy_to_elements(self, cursor, conn, db_path: str):
        """将旧 concepts/memories/connections 表迁移到 elements 体系"""
        try:
            self._debug_log("开始从旧概念体系迁移到元素体系...", "info")

            backup_path = db_path.replace(".db", "_pre_element_migration_backup.db")
            import shutil
            if not os.path.exists(backup_path):
                shutil.copy2(db_path, backup_path)
                self._debug_log(f"迁移前备份: {backup_path}", "info")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS elements (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    group_id TEXT DEFAULT '',
                    created_at REAL,
                    last_accessed REAL,
                    access_count INTEGER DEFAULT 0
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_elements_category ON elements(category)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_elements_group ON elements(group_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_elements_name ON elements(name)")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS element_memories (
                    element_id TEXT NOT NULL,
                    memory_id TEXT NOT NULL,
                    role TEXT DEFAULT '',
                    PRIMARY KEY (element_id, memory_id)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_em_element ON element_memories(element_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_em_memory ON element_memories(memory_id)")

            cursor.execute("SELECT id, name, created_at, last_accessed, access_count FROM concepts")
            old_concepts = cursor.fetchall()
            concept_to_elements: dict[str, list[str]] = {}

            for concept_data in old_concepts:
                concept_id = concept_data[0]
                concept_name = concept_data[1]
                created_at = concept_data[2]
                last_accessed = concept_data[3]
                access_count = concept_data[4]

                if concept_name.startswith("Imprint:"):
                    parts = concept_name.split(":", 2)
                    person_name = parts[2] if len(parts) >= 3 else concept_name
                    group_id = parts[1] if len(parts) >= 2 else ""
                    elem_id = f"elem_{int(time.time() * 1000)}_{hash(person_name) % 10000}"
                    cursor.execute(
                        "INSERT OR IGNORE INTO elements (id, name, category, group_id, created_at, last_accessed, access_count) VALUES (?, ?, 'person', ?, ?, ?, ?)",
                        (elem_id, person_name, group_id, created_at, last_accessed, access_count),
                    )
                    concept_to_elements[concept_id] = [elem_id]
                else:
                    keywords = [k.strip() for k in concept_name.replace("，", ",").split(",") if k.strip()]
                    elem_ids = []
                    for kw in keywords:
                        category = self._infer_category(kw)
                        cursor.execute("SELECT id FROM elements WHERE name = ? AND category = ?", (kw, category))
                        existing = cursor.fetchone()
                        if existing:
                            elem_ids.append(existing[0])
                        else:
                            elem_id = f"elem_{int(time.time() * 1000)}_{hash(kw) % 10000}"
                            cursor.execute(
                                "INSERT OR IGNORE INTO elements (id, name, category, group_id, created_at, last_accessed, access_count) VALUES (?, ?, ?, '', ?, ?, ?)",
                                (elem_id, kw, category, created_at, last_accessed, access_count),
                            )
                            elem_ids.append(elem_id)
                    concept_to_elements[concept_id] = elem_ids

            cursor.execute("PRAGMA table_info('memories')")
            memory_columns = {col[1] for col in cursor.fetchall()}

            if "concept_id" in memory_columns:
                cursor.execute("SELECT id, concept_id, content, details, participants, location, emotion, tags, created_at, last_accessed, access_count, strength, allow_forget, group_id FROM memories")
            else:
                cursor.execute("SELECT id, content, details, emotion, created_at, last_accessed, access_count, strength, allow_forget, group_id FROM memories")
                return

            old_memories = cursor.fetchall()
            for mem_data in old_memories:
                memory_id = mem_data[0]
                concept_id = mem_data[1]
                participants = mem_data[4]
                location = mem_data[5]
                tags = mem_data[7]

                elem_ids = concept_to_elements.get(concept_id, [])

                for eid in elem_ids:
                    cursor.execute(
                        "INSERT OR IGNORE INTO element_memories (element_id, memory_id, role) VALUES (?, ?, '')",
                        (eid, memory_id),
                    )

                if participants:
                    for p in participants.replace("，", ",").split(","):
                        p = p.strip()
                        if not p:
                            continue
                        cursor.execute("SELECT id FROM elements WHERE name = ? AND category = 'person'", (p,))
                        existing = cursor.fetchone()
                        if existing:
                            eid = existing[0]
                        else:
                            eid = f"elem_{int(time.time() * 1000)}_{hash(p) % 10000}"
                            cursor.execute(
                                "INSERT OR IGNORE INTO elements (id, name, category, group_id, created_at, last_accessed, access_count) VALUES (?, ?, 'person', '', ?, ?, 0)",
                                (eid, p, time.time(), time.time()),
                            )
                        cursor.execute(
                            "INSERT OR IGNORE INTO element_memories (element_id, memory_id, role) VALUES (?, ?, 'subject')",
                            (eid, memory_id),
                        )

                if location:
                    for loc in location.replace("，", ",").split(","):
                        loc = loc.strip()
                        if not loc:
                            continue
                        cursor.execute("SELECT id FROM elements WHERE name = ? AND category = 'place'", (loc,))
                        existing = cursor.fetchone()
                        if existing:
                            eid = existing[0]
                        else:
                            eid = f"elem_{int(time.time() * 1000)}_{hash(loc) % 10000}"
                            cursor.execute(
                                "INSERT OR IGNORE INTO elements (id, name, category, group_id, created_at, last_accessed, access_count) VALUES (?, ?, 'place', '', ?, ?, 0)",
                                (eid, loc, time.time(), time.time()),
                            )
                        cursor.execute(
                            "INSERT OR IGNORE INTO element_memories (element_id, memory_id, role) VALUES (?, ?, 'scene')",
                            (eid, memory_id),
                        )

                if tags:
                    for tag in tags.replace("，", ",").split(","):
                        tag = tag.strip()
                        if not tag:
                            continue
                        category = self._infer_category(tag)
                        cursor.execute(
                            "SELECT id FROM elements WHERE name = ? AND category = ?",
                            (tag, category),
                        )
                        existing = cursor.fetchone()
                        if existing:
                            eid = existing[0]
                        else:
                            eid = f"elem_{int(time.time() * 1000)}_{hash(tag) % 10000}"
                            cursor.execute(
                                "INSERT OR IGNORE INTO elements (id, name, category, group_id, created_at, last_accessed, access_count) VALUES (?, ?, ?, '', ?, ?, 0)",
                                (eid, tag, category, time.time(), time.time()),
                            )
                        cursor.execute(
                            "INSERT OR IGNORE INTO element_memories (element_id, memory_id, role) VALUES (?, ?, 'tag')",
                            (eid, memory_id),
                        )

            if "concept_id" in memory_columns or "participants" in memory_columns or "location" in memory_columns or "tags" in memory_columns:
                try:
                    cols_to_drop = []
                    for col in ["concept_id", "participants", "location", "tags"]:
                        if col in memory_columns:
                            cols_to_drop.append(col)
                    if cols_to_drop:
                        keep_cols = [c for c in memory_columns if c not in cols_to_drop]
                        col_defs = []
                        for col_name in keep_cols:
                            col_defs.append(f'"{col_name}"')
                        cursor.execute(f"CREATE TABLE memories_new AS SELECT {', '.join(col_defs)} FROM memories")
                        cursor.execute("DROP TABLE memories")
                        cursor.execute("ALTER TABLE memories_new RENAME TO memories")
                        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_group_id ON memories(group_id)")
                        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_created_group ON memories(created_at, group_id)")
                except Exception as drop_err:
                    self._debug_log(f"清理旧字段时出错（可忽略）: {drop_err}", "warning")

            try:
                cursor.execute("SELECT id, from_concept, to_concept, strength, last_strengthened FROM connections")
                old_connections = cursor.fetchall()
                for oc in old_connections:
                    conn_id = oc[0]
                    from_c = oc[1]
                    to_c = oc[2]
                    strength = oc[3]
                    last_s = oc[4]
                    from_elems = concept_to_elements.get(from_c, [])
                    to_elems = concept_to_elements.get(to_c, [])
                    for fe in from_elems:
                        for te in to_elems:
                            new_id = f"conn_{fe}_{te}"
                            cursor.execute(
                                "INSERT OR IGNORE INTO connections (id, from_element, to_element, strength, last_strengthened) VALUES (?, ?, ?, ?, ?)",
                                (new_id, fe, te, strength, last_s),
                            )
                cursor.execute("DROP TABLE IF EXISTS connections")
                cursor.execute("""
                    CREATE TABLE connections (
                        id TEXT PRIMARY KEY,
                        from_element TEXT NOT NULL,
                        to_element TEXT NOT NULL,
                        strength REAL DEFAULT 1.0,
                        last_strengthened REAL
                    )
                """)
                for oc in old_connections:
                    from_c = oc[1]
                    to_c = oc[2]
                    strength = oc[3]
                    last_s = oc[4]
                    from_elems = concept_to_elements.get(from_c, [])
                    to_elems = concept_to_elements.get(to_c, [])
                    for fe in from_elems:
                        for te in to_elems:
                            new_id = f"conn_{fe}_{te}"
                            cursor.execute(
                                "INSERT OR IGNORE INTO connections (id, from_element, to_element, strength, last_strengthened) VALUES (?, ?, ?, ?, ?)",
                                (new_id, fe, te, strength, last_s),
                            )
            except Exception as conn_err:
                self._debug_log(f"连接迁移出错（可忽略）: {conn_err}", "warning")

            self._debug_log("旧概念体系迁移到元素体系完成", "info")

        except Exception as e:
            self._debug_log(f"迁移失败: {e}", "error")

    def _infer_category(self, keyword: str) -> str:
        """根据关键词推断元素类型"""
        if not keyword:
            return "trait"
        kw = keyword.strip()

        cursor_for_check = None
        try:
            db_path = self.db_path
            conn_check = resource_manager.get_db_connection(db_path)
            cursor_for_check = conn_check.cursor()
            cursor_for_check.execute(
                "SELECT name FROM elements WHERE category = 'person'"
            )
            known_persons = {row[0] for row in cursor_for_check.fetchall()}
            if kw in known_persons:
                return "person"
        except Exception:
            pass
        finally:
            if cursor_for_check:
                try:
                    resource_manager.release_db_connection(db_path, conn_check)
                except Exception:
                    pass

        return "trait"

    async def process_message_optimized(
        self, event: AstrMessageEvent, group_id: str = ""
    ):
        """优化的消息处理，委托给TopicAnalyzer"""
        try:
            if not self.topic_analyzer:
                return

            message = event.message_str
            if not message or not message.strip():
                return

            sender_id = str(event.get_sender_id() or "")
            sender_name = sender_id  # 默认用ID作为名称
            try:
                nick = getattr(event, "get_sender_name", None)
                if nick:
                    sender_name = str(nick()) or sender_id
            except Exception:
                pass
            umo = getattr(event, "unified_msg_origin", None)

            await self.topic_analyzer.add_message(
                message, sender_id, sender_name, group_id, umo=umo
            )

        except Exception as e:
            self._debug_log(f"优化消息处理失败: {e}", "error")

    async def resolve_memory_generation_persona(
        self, umo: str | None
    ) -> dict[str, Any]:
        """解析记忆生成阶段应使用的人格设定信息。"""
        result = {"source": "", "persona_id": "", "prompt": ""}

        if not self.memory_config.get(
            "enable_persona_injection_in_memory_generation", True
        ):
            return result

        try:
            context = getattr(self, "context", None)
            if not context:
                return result

            persona_manager = getattr(context, "persona_manager", None)
            if not persona_manager:
                return result

            # 1) 优先读取当前会话绑定的人格
            persona_id = ""
            conversation_manager = getattr(context, "conversation_manager", None)
            if umo and conversation_manager:
                curr_cid = await conversation_manager.get_curr_conversation_id(umo)
                if curr_cid:
                    conversation = await conversation_manager.get_conversation(
                        umo, curr_cid
                    )
                    persona_id = str(getattr(conversation, "persona_id", "") or "").strip()

            if persona_id:
                get_persona = getattr(persona_manager, "get_persona", None)
                if get_persona:
                    persona = get_persona(persona_id)
                    if asyncio.iscoroutine(persona):
                        persona = await persona
                    prompt = str(getattr(persona, "system_prompt", "") or "").strip()
                    if prompt:
                        result.update(
                            {
                                "source": "conversation_persona",
                                "persona_id": persona_id,
                                "prompt": prompt,
                            }
                        )
                        return result

            # 2) 回退默认人格(v3)
            get_default = getattr(persona_manager, "get_default_persona_v3", None)
            if get_default:
                default_persona = get_default(umo=umo)
                if asyncio.iscoroutine(default_persona):
                    default_persona = await default_persona
                prompt = ""
                persona_name = ""
                if isinstance(default_persona, dict):
                    prompt = str(default_persona.get("prompt", "") or "").strip()
                    persona_name = str(default_persona.get("name", "") or "").strip()
                else:
                    prompt = str(getattr(default_persona, "prompt", "") or "").strip()
                    persona_name = str(
                        getattr(default_persona, "name", "") or ""
                    ).strip()
                if prompt:
                    result.update(
                        {
                            "source": "default_persona",
                            "persona_id": persona_name,
                            "prompt": prompt,
                        }
                    )

        except Exception as e:
            self._debug_log(f"解析记忆生成人格失败: {e}", "warning")

        return result

    async def build_memory_generation_persona_injection(
        self, umo: str | None, max_chars: int = 1600
    ) -> str:
        """构建记忆生成阶段的人格注入文本。"""
        try:
            persona_data = await self.resolve_memory_generation_persona(umo)
            prompt = str(persona_data.get("prompt", "") or "").strip()
            if not prompt:
                return ""

            if len(prompt) > max_chars:
                prompt = f"{prompt[:max_chars].rstrip()}..."

            return (
                "人格设定\n"
                f"{prompt}\n"
                "请在记忆提取与描述风格上遵循该人格设定，但必须严格基于对话事实，不得编造。"
            )
        except Exception as e:
            self._debug_log(f"构建记忆生成人格注入文本失败: {e}", "warning")
            return ""

    async def _fallback_impression_extraction(
        self, conversation_history: list[dict[str, Any]], group_id: str
    ):
        """基于关键词的简单印象提取（备用方案）"""
        try:
            impression_keywords = {
                "觉得": 0.1,
                "感觉": 0.1,
                "印象": 0.2,
                "人不错": 0.3,
                "挺好的": 0.2,
                "很厉害": 0.3,
                "有点": -0.1,
                "不太行": -0.3,
                "很差": -0.4,
            }

            for msg in conversation_history:
                content = msg.get("content", "")
                sender_name = msg.get("sender_name", "用户")

                # 提取潜在人名
                mentioned_names = self._extract_mentioned_names(content)

                for name in mentioned_names:
                    if name == sender_name or name == "我":
                        continue

                    for keyword, score_delta in impression_keywords.items():
                        if keyword in content:
                            # 找到了一个关于某个人的印象
                            summary = f"感觉 {name} {keyword}"
                            self.record_person_impression(
                                group_id,
                                name,
                                summary,
                                score=None,
                                details=f"来自 {sender_name} 的评价: {content}",
                            )
                            self.adjust_impression_score(group_id, name, score_delta)
                            self._debug_log(
                                f"备用方案提取印象: {name} ({keyword})", "debug"
                            )

        except Exception as e:
            self._debug_log(f"备用印象提取方案失败: {e}", "warning")

    async def get_conversation_history(self, event: AstrMessageEvent) -> list[str]:
        """获取对话历史（兼容旧版本）"""
        try:
            uid = event.unified_msg_origin
            curr_cid = await self.context.conversation_manager.get_curr_conversation_id(
                uid
            )
            if curr_cid:
                conversation = await self.context.conversation_manager.get_conversation(
                    uid, curr_cid
                )
                if conversation and conversation.history:
                    history = json.loads(conversation.history)
                    return [msg.get("content", "") for msg in history[-10:]]  # 最近10条
            return []
        except Exception as e:
            logger.error(f"获取对话历史失败: {e}")
            return []

    async def get_conversation_history_full(
        self, event: AstrMessageEvent
    ) -> list[dict[str, Any]]:
        """获取包含完整信息的对话历史"""
        try:
            uid = event.unified_msg_origin
            curr_cid = await self.context.conversation_manager.get_curr_conversation_id(
                uid
            )
            if curr_cid:
                conversation = await self.context.conversation_manager.get_conversation(
                    uid, curr_cid
                )
                if conversation and conversation.history:
                    history = json.loads(conversation.history)
                    # 添加发送者信息和时间戳
                    full_history = []
                    # 从配置中获取对话历史条数，默认为20条
                    conversation_history_count = self.memory_config.get(
                        "conversation_history_count", 20
                    )
                    for msg in history[
                        -conversation_history_count:
                    ]:  # 使用配置中的条数，避免token过多
                        full_msg = {
                            "role": msg.get("role", "user"),
                            "content": msg.get("content", ""),
                            "sender_name": msg.get("sender_name", "用户"),
                            "timestamp": msg.get("timestamp", time.time()),
                        }
                        full_history.append(full_msg)
                    return full_history
            return []
        except Exception as e:
            logger.error(f"获取完整对话历史失败: {e}")
            return []

    async def recall_memories_full(self, keyword: str) -> list["Memory"]:
        """回忆相关记忆并返回完整的Memory对象"""
        try:
            # 这是一个简化的实现，用于演示目的
            # 在实际应用中，这里应该有更复杂的逻辑来匹配关键词
            related_memories = []
            keyword_lower = keyword.lower()

            for memory in self.memory_graph.memories.values():
                if keyword_lower in memory.content.lower():
                    related_memories.append(memory)

            if related_memories:
                self._record_memory_access_by_ids([m.id for m in related_memories])

            return related_memories

        except Exception as e:
            logger.error(f"回忆记忆失败: {e}")
            return []

    def _cosine_similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """计算余弦相似度"""
        try:
            if len(vec1) != len(vec2):
                return 0.0

            dot_product = sum(a * b for a, b in zip(vec1, vec2))
            magnitude1 = sum(a * a for a in vec1) ** 0.5
            magnitude2 = sum(b * b for b in vec2) ** 0.5

            if magnitude1 == 0 or magnitude2 == 0:
                return 0.0

            return dot_product / (magnitude1 * magnitude2)
        except Exception:
            return 0.0

    async def memory_maintenance_loop(self):
        """记忆维护循环"""
        db_dir = os.path.dirname(self.db_path)

        while True:
            try:
                consolidation_interval = (
                    self.memory_config.get("consolidation_interval_hours", 24) * 3600
                )
                await asyncio.sleep(consolidation_interval)  # 按配置间隔检查

                maintenance_actions = []

                # 处理默认数据库（私有对话）
                if self.memory_config.get("enable_forgetting", True):
                    await self.forget_memories()
                    maintenance_actions.append("遗忘")

                if self.memory_config.get("enable_consolidation", False):
                    await self.consolidate_memories()
                    maintenance_actions.append("整理")

                await self.save_memory_state()
                maintenance_actions.append("保存")

                # 如果启用了群聊隔离，处理所有群聊数据库
                if self.memory_config.get("enable_group_isolation", True):
                    # 扫描群聊数据库文件
                    group_files = []
                    if os.path.exists(db_dir):
                        for filename in os.listdir(db_dir):
                            if filename.startswith(
                                "memory_group_"
                            ) and filename.endswith(".db"):
                                group_id = filename[12:-3]  # 提取群聊ID
                                group_files.append(group_id)

                    # 为每个群聊数据库执行维护
                    for group_id in group_files:
                        try:
                            # 清空当前记忆图，加载群聊数据库
                            self.memory_graph = MemoryGraph()
                            self.load_memory_state(group_id)

                            # 执行群聊的维护操作
                            if self.memory_config.get("enable_forgetting", True):
                                await self.forget_memories()

                            if self.memory_config.get("enable_consolidation", False):
                                await self.consolidate_memories()

                            # 保存群聊数据库
                            await self.save_memory_state(group_id)

                            self._debug_log(f"群聊 {group_id} 维护完成", "debug")

                        except Exception as group_e:
                            self._debug_log(
                                f"群聊 {group_id} 维护失败: {group_e}", "warning"
                            )

                # 简化维护日志输出
                if maintenance_actions:
                    action_text = f"记忆维护完成: {', '.join(maintenance_actions)}"
                    if self.memory_config.get("enable_group_isolation", True):
                        action_text += f" (包含 {len(group_files) if 'group_files' in locals() else 0} 个群聊)"
                    self._debug_log(action_text, "debug")

            except Exception as e:
                self._debug_log(f"记忆维护失败: {e}", "error")

    async def forget_memories(self):
        """遗忘机制"""
        current_time = time.time()
        forget_threshold = self.memory_config.get("forget_threshold_days", 30) * 24 * 3600

        # 降低连接强度
        connections_to_remove = []
        for connection in self.memory_graph.connections:
            if current_time - connection.last_strengthened > forget_threshold:
                connection.strength *= 0.9
                if connection.strength < 0.1:
                    connections_to_remove.append(connection.id)

        # 批量移除连接
        for conn_id in connections_to_remove:
            self.memory_graph.remove_connection(conn_id)

        # 移除不活跃的记忆
        memories_to_remove = []
        for memory in list(self.memory_graph.memories.values()):
            if not memory.allow_forget:
                continue
            if forget_threshold <= 0:
                continue
            last_accessed = memory.last_accessed or memory.created_at or current_time
            time_since = max(0.0, current_time - last_accessed)
            time_factor = time_since / forget_threshold
            access_count = max(0, int(memory.access_count or 0))
            access_factor = 1.0 / (1.0 + access_count)
            decay = min(0.6, time_factor * access_factor * 0.4)
            if decay > 0:
                memory.strength = max(0.0, memory.strength * (1.0 - decay))
            forget_score = time_factor * access_factor
            if time_factor >= 1.0 and memory.strength < 0.12 and forget_score > 0.9:
                memories_to_remove.append(memory.id)

        # 批量移除记忆
        for memory_id in memories_to_remove:
            self.memory_graph.remove_memory(memory_id)

        # 仅在有实际清理时输出日志
        if len(memories_to_remove) > 0 or len(connections_to_remove) > 0:
            self._debug_log(
                f"遗忘完成: 清理{len(memories_to_remove)}条记忆, {len(connections_to_remove)}个连接",
                "info",
            )
        else:
            self._debug_log("遗忘检查完成: 没有需要清理的记忆或连接", "debug")

    async def consolidate_memories(self):
        """Element体系下暂不执行旧式按Concept合并。"""
        self._debug_log("Element体系下跳过旧式记忆整理", "debug")

    async def get_memory_stats(self) -> dict:
        """获取记忆统计信息"""
        return {
            "concepts": len(self.memory_graph.concepts),
            "memories": len(self.memory_graph.memories),
            "connections": len(self.memory_graph.connections),
            "recall_mode": self.memory_config.get("recall_mode", "simple"),
            "llm_provider": self.memory_config.get("llm_provider", ""),
            "embedding_provider": self.memory_config.get("embedding_provider", ""),
            "enable_forgetting": self.memory_config.get("enable_forgetting", True),
            "enable_consolidation": self.memory_config.get("enable_consolidation", False),
        }

    def _parse_allow_forget_value(
        self, value, default: bool | None = True
    ) -> bool | None:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return bool(value)
        text = str(value).strip().lower()
        if not text:
            return default
        for token in [
            "不允许",
            "不可",
            "不能",
            "禁止",
            "false",
            "no",
            "0",
            "否",
            "不要",
        ]:
            if token in text:
                return False
        for token in ["允许", "可以", "true", "yes", "1", "是", "要"]:
            if token in text:
                return True
        return default

    async def resolve_allow_forget(
        self,
        content: str,
        theme: str,
        details: str,
        participants: str,
        location: str,
        emotion: str,
        tags: str,
        initial_allow_forget: bool,
    ) -> bool:
        provider = await self.get_llm_provider()
        if not provider:
            return initial_allow_forget
        initial_label = "允许遗忘" if initial_allow_forget else "不允许遗忘"
        prompt = (
            "请判断以下记忆是否允许遗忘(对于日常习惯，用户相关信息通常不允许遗忘，对于近期安排不长久影响未来的事件，通常允许遗忘)，只回复：允许遗忘/不允许遗忘/无法判断\n"
            f"记忆内容：{content}\n"
            f"主题：{theme}\n"
            f"细节：{details}\n"
            f"参与者：{participants}\n"
            f"地点：{location}\n"
            f"情感：{emotion}\n"
            f"标签：{tags}\n"
            f"当前判断：{initial_label}"
        )
        try:
            response = await provider.text_chat(prompt=prompt, contexts=[])
            text = getattr(response, "completion_text", "") if response else ""
            parsed = self._parse_allow_forget_value(text, None)
            if parsed is None:
                return initial_allow_forget
            return parsed
        except Exception:
            return initial_allow_forget

    async def get_llm_provider(self):
        """使用配置文件指定的提供商 - 添加缓存和日志限制"""
        # 检查是否已经有缓存结果
        if hasattr(self, "_llm_provider_cache"):
            return self._llm_provider_cache

        try:
            provider_id = self.memory_config.get("llm_provider")
            if not provider_id:
                if (
                    not hasattr(self, "_llm_provider_no_config_time")
                    or time.time() - self._llm_provider_no_config_time > 60
                ):  # 每分钟最多记录一次
                    logger.error("插件配置中未指定 'llm_provider'")
                    self._llm_provider_no_config_time = time.time()
                self._llm_provider_cache = None
                return None

            # 1. 尝试通过ID精确查找
            provider = self.context.get_provider_by_id(provider_id)
            if provider:
                self._llm_provider_cache = provider
                return provider

            # 2. 如果ID查找失败，尝试通过名称模糊匹配
            all_providers = self.context.get_all_providers()
            for p in all_providers:
                p_name = getattr(
                    getattr(p, "meta", None), "name", getattr(p, "name", None)
                )
                if p_name and p_name.lower() == provider_id.lower():
                    self._llm_provider_cache = p
                    return p

            if (
                not hasattr(self, "_llm_provider_error_time")
                or time.time() - self._llm_provider_error_time > 60
            ):  # 每分钟最多记录一次
                logger.error(f"无法找到配置的LLM提供商: '{provider_id}'")
                available_ids = [
                    f"ID: {getattr(p, 'id', 'N/A')}, Name: {getattr(p, 'name', 'N/A')}"
                    for p in all_providers
                ]
                logger.error(f"可用提供商: {available_ids}")
                self._llm_provider_error_time = time.time()

            self._llm_provider_cache = None
            return None

        except Exception as e:
            if (
                not hasattr(self, "_llm_provider_exception_time")
                or time.time() - self._llm_provider_exception_time > 60
            ):  # 每分钟最多记录一次
                logger.error(f"获取LLM提供商失败: {e}", exc_info=True)
                self._llm_provider_exception_time = time.time()

            self._llm_provider_cache = None
            return None

    async def get_embedding_provider(self):
        """使用配置文件指定的提供商 - 添加缓存和日志限制"""
        # 检查是否已经有缓存结果
        if hasattr(self, "_embedding_provider_cache"):
            return self._embedding_provider_cache

        try:
            provider_id = self.memory_config.get("embedding_provider", "")

            # 获取所有已注册的嵌入提供商
            if hasattr(self.context, "get_all_embedding_providers"):
                all_providers = self.context.get_all_embedding_providers()
            else:
                # 兼容性回退
                all_providers = self.context.get_all_providers()

            # 精确匹配配置的提供商ID
            for provider in all_providers:
                if hasattr(provider, "id") and provider.id == provider_id:
                    logger.debug(f"成功使用配置指定的嵌入提供商: {provider_id}")
                    self._embedding_provider_cache = provider
                    return provider

            # 如果找不到，尝试通过ID获取
            provider = self.context.get_provider_by_id(provider_id)
            if provider:
                self._embedding_provider_cache = provider
                return provider

            # 最后尝试通过名称匹配
            for provider in all_providers:
                if hasattr(provider, "meta") and hasattr(provider.meta, "name"):
                    if provider.meta.name == provider_id:
                        logger.debug(f"通过名称匹配使用嵌入提供商: {provider_id}")
                        self._embedding_provider_cache = provider
                        return provider

            # 添加日志频率限制，避免刷屏
            if (
                not hasattr(self, "_embedding_provider_error_time")
                or time.time() - self._embedding_provider_error_time > 60
            ):  # 每分钟最多记录一次
                logger.error(f"无法找到配置的嵌入提供商: {provider_id}")
                self._embedding_provider_error_time = time.time()

            self._embedding_provider_cache = None
            return None

        except Exception as e:
            if (
                not hasattr(self, "_embedding_provider_exception_time")
                or time.time() - self._embedding_provider_exception_time > 60
            ):  # 每分钟最多记录一次
                logger.error(f"获取嵌入提供商失败: {e}")
                self._embedding_provider_exception_time = time.time()

            self._embedding_provider_cache = None
            return None

    async def get_embedding(self, text: str) -> list[float]:
        """获取文本的嵌入向量 - 优先使用缓存"""
        # 递归保护：避免嵌入向量获取中的递归调用
        if getattr(self, "_embedding_in_progress", False):
            return []
        self._embedding_in_progress = True
        try:
            # 检查当前回忆模式，如果不是embedding模式，直接返回空列表，避免不必要的嵌入计算
            if self.memory_config.get("recall_mode", "simple") not in ["embedding"]:
                return []

            # 如果启用了嵌入向量缓存，尝试从缓存获取
            if self.embedding_cache:
                # 生成一个临时ID用于缓存查询
                temp_id = f"temp_{hash(text)}"
                cached_embedding = await self.embedding_cache.get_embedding(
                    temp_id, text
                )
                if cached_embedding:
                    return cached_embedding

            # 缓存未命中或未启用，直接计算
            provider = await self.get_embedding_provider()
            if not provider:
                logger.debug("嵌入提供商不可用")
                return []

            # 尝试多种嵌入方法
            methods = ["embedding", "embeddings", "get_embedding", "get_embeddings"]
            for method_name in methods:
                if hasattr(provider, method_name):
                    try:
                        method = getattr(provider, method_name)
                        result = await method(text)
                        if result and isinstance(result, list) and len(result) > 0:
                            return result
                    except Exception as e:
                        logger.debug(f"方法 {method_name} 失败: {e}")
                        continue

            # 尝试使用LLM提供商的嵌入功能
            if hasattr(provider, "text_chat"):
                try:
                    # 构建嵌入请求
                    prompt = f"请将以下文本转换为嵌入向量: {text}"
                    response = await provider.text_chat(
                        prompt=prompt,
                        contexts=[],
                        system_prompt="请将文本转换为数值向量表示",
                    )
                    # 这里假设LLM可能返回嵌入向量
                    if response and hasattr(response, "embedding"):
                        return response.embedding
                except Exception as e:
                    logger.debug(f"LLM嵌入方法失败: {e}")

            logger.debug("所有嵌入方法均失败")
            return []

        except Exception as e:
            logger.error(f"获取嵌入向量失败: {e}")
            return []
        finally:
            self._embedding_in_progress = False

    async def inject_memories_to_context(self, event: AstrMessageEvent) -> str:
        """生成需要注入到上下文的记忆和印象内容

        Args:
            event: 消息事件对象

        Returns:
            str: 生成的上下文内容，如果为空则返回空字符串
        """
        try:
            # [新增] 入口日志，确认是否被调用
            self._debug_log(
                f"开始执行 inject_memories_to_context, 消息: {event.message_str[:20]}...",
                "debug",
            )

            if not self.memory_config.get("enable_enhanced_memory", True):
                return ""

            current_message = event.message_str.strip()
            if not current_message:
                return ""

            # 短消息过滤：避免为过短的消息注入记忆
            # [修改] 缩短长度限制以方便测试
            if len(current_message) < 1:
                return ""

            # 获取群组ID
            group_id = self._extract_group_id_from_event(event)

            impression_context = ""
            if self.impression_config.get("enable_impression_injection", True):
                sender_name = ""
                try:
                    sender_name = event.get_sender_name() or ""
                except Exception:
                    sender_name = ""
                if not sender_name:
                    try:
                        sender_name = str(event.get_sender_id() or "")
                    except Exception:
                        sender_name = ""
                impression_context = await self._inject_impressions_to_context(
                    sender_name, group_id
                )

            # [新增] 注入话题上下文
            topic_context = ""
            if self.topic_analyzer:
                try:
                    sender_id = event.get_sender_id()
                    topic_scope = group_id if group_id else f"private:{sender_id}"

                    # 获取当前活跃会话信息
                    active_sessions = self.topic_analyzer.get_active_sessions(
                        topic_scope
                    )
                    if active_sessions:
                        # 取最近活跃的会话
                        latest = active_sessions[-1]
                        keywords = ", ".join(latest.get("keywords", [])[:5])
                        topic_context = f"【当前话题】\n讨论焦点: {keywords}"
                except Exception as e:
                    self._debug_log(f"获取话题上下文失败: {e}", "warning")

            # [新增] 注入用户画像/亲密度上下文
            profile_context = ""
            if self.user_profiling:
                try:
                    sender_id = event.get_sender_id()
                    # 自用模式：移除亲密度计算，默认为主人/最高权限
                    # 仅保留互动统计，作为数据参考
                    intimacy = await self.user_profiling.calculate_intimacy(
                        sender_id, group_id
                    )
                    if intimacy:
                        profile_context = f"【用户状态】\n身份: 主人\n互动: {intimacy.total_interactions}次"
                except Exception as e:
                    self._debug_log(f"获取用户画像失败: {e}", "warning")

            # 使用增强记忆召回系统获取相关记忆
            from ..memory.memory_recall import EnhancedMemoryRecall

            enhanced_recall = EnhancedMemoryRecall(self)
            results = await enhanced_recall.recall_relevant_memories_for_injection(
                message=current_message, group_id=group_id
            )

            threshold = self.memory_config.get("memory_injection_threshold", 0.2)
            filtered_results = [
                r
                for r in results
                if hasattr(r, "relevance_score") and r.relevance_score >= threshold
            ]

            if filtered_results:
                updated = self._record_recall_results_accesses(filtered_results)
                if updated:
                    await self._queue_save_memory_state(group_id)

            # 调试日志：记录召回详情
            if results:
                scores = [f"{r.relevance_score:.2f}" for r in results]
                self._debug_log(
                    f"记忆召回: {len(results)}条, 分数: {scores}, 阈值: {threshold}",
                    "debug",
                )

            # 组合记忆上下文和印象上下文
            combined_context = ""
            if profile_context:
                combined_context += profile_context + "\n\n"
            if impression_context:
                combined_context += impression_context + "\n\n"
            if topic_context:
                combined_context += topic_context + "\n\n"

            if filtered_results:
                # 使用增强格式化
                memory_context = enhanced_recall.format_memories_for_llm(
                    filtered_results, include_ids=False
                )
                combined_context += memory_context

            if combined_context:
                debug_info = []
                if profile_context:
                    debug_info.append("用户画像")
                if impression_context:
                    debug_info.append("印象")
                if topic_context:
                    debug_info.append("话题")
                if filtered_results:
                    debug_info.append(f"{len(filtered_results)}条记忆")
                self._debug_log(f"生成注入上下文: {'+'.join(debug_info)}", "debug")

            return combined_context

        except Exception as e:
            self._debug_log(f"注入记忆到上下文失败: {e}", "warning")
            return ""

    async def _inject_impressions_to_context(
        self, sender_name: str, group_id: str
    ) -> str:
        """注入印象信息到对话上下文"""
        try:
            if not sender_name:
                return ""

            impression_summary = self.get_person_impression_summary(
                group_id, sender_name
            )
            if impression_summary and impression_summary.get("summary"):
                score = impression_summary.get("score", 0.5)
                score_desc = self._score_to_description(score)
                return f"【人物印象】\n- {sender_name}: {impression_summary['summary']} (好感度: {score_desc})"

            return ""

        except Exception as e:
            self._debug_log(f"注入印象上下文失败: {e}", "warning")
            return ""

    def _extract_mentioned_names(self, message: str) -> list[str]:
        """从消息中提取提到的人名"""
        try:
            # 简单的人名提取，匹配常见的中文名模式
            # 2-4个中文字符，且不是常见词汇
            common_words = {
                "你好",
                "谢谢",
                "再见",
                "好的",
                "是的",
                "不是",
                "可以",
                "不行",
                "知道",
                "不知道",
                "明白",
                "不明白",
            }
            names = set()

            # 匹配2-4个中文字符
            chinese_names = re.findall(r"[\u4e00-\u9fff]{2,4}", message)

            for name in chinese_names:
                if name not in common_words:
                    names.add(name)

            return list(names)

        except Exception as e:
            self._debug_log(f"提取人名失败: {e}", "debug")
            return []

    def _extract_sender_name_from_message(self, message: str) -> str | None:
        """从消息中提取发送者名称"""
        try:
            # 这里可以根据实际情况实现更复杂的逻辑
            # 目前简单返回None，让调用者处理
            return None

        except Exception as e:
            self._debug_log(f"提取发送者名称失败: {e}", "debug")
            return None

    def _score_to_description(self, score: float) -> str:
        """将好感度分数转换为描述性文字"""
        try:
            if score >= 0.8:
                return "很高"
            elif score >= 0.6:
                return "较高"
            elif score >= 0.4:
                return "一般"
            elif score >= 0.2:
                return "较低"
            else:
                return "很低"

        except Exception as e:
            self._debug_log(f"分数描述转换失败: {e}", "debug")
            return "一般"

    def _extract_person_name_from_theme(self, theme: str) -> str | None:
        """从主题中提取人物姓名

        Args:
            theme: 主题字符串，可能包含人物姓名

        Returns:
            str: 提取的人物姓名，无法提取则返回None
        """
        try:
            # 清理主题字符串
            theme = theme.strip()
            if not theme:
                return None

            # 分割主题（可能包含多个关键词）
            parts = theme.split(",")

            # 查找包含人名的部分
            for part in parts:
                part = part.strip()

                # 跳过明显的非人名关键词
                if part in ["印象", "评价", "看法", "感觉", "印象", "人际"]:
                    continue

                # 检查是否是有效的人名（2-4个中文字符）
                if (
                    len(part) >= 2
                    and len(part) <= 4
                    and re.match(r"^[\u4e00-\u9fff]+$", part)
                ):
                    return part

            return None

        except Exception as e:
            self._debug_log(f"从主题提取人名失败: {e}", "debug")
            return None

    async def query_memory(
        self, query: str, event: AstrMessageEvent = None
    ) -> list[str]:
        """记忆查询接口。"""
        return await self.recall_memories(query, event)

    async def recall_memories(
        self, keyword: str, event: AstrMessageEvent = None
    ) -> list[str]:
        """使用Element增强召回接口回忆相关记忆。"""
        try:
            if not keyword or not self.memory_graph.memories:
                return []

            group_id = ""
            if event is not None:
                try:
                    group_id = self._extract_group_id_from_event(event)
                except Exception:
                    group_id = ""

            from ..memory.memory_recall import EnhancedMemoryRecall

            enhanced_recall = EnhancedMemoryRecall(self)
            results = await enhanced_recall.recall_all_relevant_memories(
                query=keyword,
                max_memories=self.memory_config.get("max_injected_memories", 5),
                group_id=group_id,
            )
            return [result.memory for result in results]

        except Exception as e:
            logger.error(f"回忆记忆失败: {e}")
            return []

    async def recall_relevant_memories(self, message: str) -> list[str]:
        """基于消息内容智能召回相关记忆"""
        try:
            if not self.memory_graph.memories:
                return []

            # 使用增强记忆召回系统
            from ..memory.memory_recall import EnhancedMemoryRecall

            enhanced_recall = EnhancedMemoryRecall(self)
            results = await enhanced_recall.recall_all_relevant_memories(
                query=message,
                max_memories=self.memory_config.get("max_injected_memories", 5),
            )

            # 返回记忆内容列表
            return [result.memory for result in results]

        except Exception as e:
            logger.error(f"增强记忆召回失败: {e}")
            return []

    def format_memories_for_context(self, memories: list[str]) -> str:
        """将记忆格式化为适合LLM理解的增强上下文"""
        try:
            if not memories:
                return ""

            # 使用增强格式化
            from ..memory.memory_recall import EnhancedMemoryRecall, MemoryRecallResult

            # 创建增强结果用于格式化
            enhanced_results = []
            for memory in memories:
                enhanced_results.append(
                    MemoryRecallResult(
                        memory=memory,
                        relevance_score=0.8,
                        memory_type="context_injection",
                        concept_id="",
                        metadata={"source": "auto_injection"},
                    )
                )

            enhanced_recall = EnhancedMemoryRecall(self)
            return enhanced_recall.format_memories_for_llm(
                enhanced_results, include_ids=False
            )

        except Exception as e:
            logger.error(f"上下文格式化失败: {e}")
            return ""

    def _find_person_element(self, group_id: str, person_name: str) -> str:
        """查找或创建 person 类型的元素"""
        try:
            for elem in self.memory_graph.elements.values():
                if elem.name == person_name and elem.category == "person":
                    if not group_id or elem.group_id == group_id:
                        return elem.id

            legacy_name = f"Imprint:{group_id}:{person_name}"
            for concept in self.memory_graph.concepts.values():
                if concept.name == legacy_name:
                    eid = self.memory_graph.get_or_create_element(person_name, "person", group_id)
                    return eid

            return self.memory_graph.get_or_create_element(person_name, "person", group_id)
        except Exception as e:
            self._debug_log(f"查找人物元素失败: {e}", "error")
            return ""

    def ensure_person_impression(self, group_id: str, person_name: str) -> str:
        """确保指定群组的人物印象元素存在，返回元素ID"""
        try:
            return self._find_person_element(group_id, person_name)
        except Exception as e:
            self._debug_log(f"确保印象元素失败: {e}", "error")
            return ""

    def record_person_impression(
        self,
        group_id: str,
        person_name: str,
        summary: str,
        score: float | None = None,
        details: str = "",
    ) -> str:
        """记录或更新人物印象"""
        try:
            element_id = self._find_person_element(group_id, person_name)
            if not element_id:
                return ""

            if score is None:
                score = float(self.impression_config["default_score"])

            score = float(score)
            score = max(
                float(self.impression_config["min_score"]),
                min(float(self.impression_config["max_score"]), score),
            )

            memory_id = self.memory_graph.add_memory(
                content=summary,
                details=details,
                emotion="印象",
                strength=score,
                group_id=group_id,
            )

            self.memory_graph.link_memory(element_id, memory_id, "impression")

            self._debug_log(
                f"记录印象: {person_name} (分数: {score}, 群组: {group_id})", "debug"
            )

            return memory_id

        except Exception as e:
            self._debug_log(f"记录印象失败: {e}", "error")
            return ""

    def get_impression_score(self, group_id: str, person_name: str) -> float:
        """获取人物的好感度分数"""
        try:
            element_id = self._find_person_element(group_id, person_name)
            if not element_id:
                return self.impression_config["default_score"]

            impression_memories = self.memory_graph.get_element_memories_with_role(
                element_id, "impression"
            )
            impression_memories = self.filter_memories_by_group(
                impression_memories, group_id
            )

            if not impression_memories:
                legacy_name = f"Imprint:{group_id}:{person_name}"
                for concept in self.memory_graph.concepts.values():
                    if concept.name == legacy_name:
                        all_memories = self.memory_graph.get_element_memories(concept.id)
                        concept_memories = self.filter_memories_by_group(all_memories, group_id)
                        if concept_memories:
                            return max(concept_memories, key=lambda m: m.last_accessed).strength
                return self.impression_config["default_score"]

            latest_memory = max(impression_memories, key=lambda m: m.last_accessed)
            return latest_memory.strength

        except Exception as e:
            self._debug_log(f"获取印象分数失败: {e}", "error")
            return self.impression_config["default_score"]

    def adjust_impression_score(
        self, group_id: str, person_name: str, delta: float
    ) -> float:
        """调整人物的好感度分数"""
        try:
            current_score = self.get_impression_score(group_id, person_name)
            new_score = current_score + delta
            new_score = max(
                self.impression_config["min_score"],
                min(self.impression_config["max_score"], new_score),
            )

            element_id = self._find_person_element(group_id, person_name)

            if element_id:
                impression_memories = self.memory_graph.get_element_memories_with_role(
                    element_id, "impression"
                )
                impression_memories = self.filter_memories_by_group(
                    impression_memories, group_id
                )

                if impression_memories:
                    latest_memory = max(impression_memories, key=lambda m: m.last_accessed)
                    latest_memory.strength = new_score
                    latest_memory.last_accessed = time.time()
                else:
                    summary = f"对{person_name}的印象更新，当前好感度：{new_score:.2f}"
                    self.record_person_impression(
                        group_id, person_name, summary, new_score
                    )
            else:
                summary = f"对{person_name}的印象更新，当前好感度：{new_score:.2f}"
                self.record_person_impression(group_id, person_name, summary, new_score)

            self._debug_log(
                f"调整印象分数: {person_name} {current_score:.2f} -> {new_score:.2f}",
                "debug",
            )

            return new_score

        except Exception as e:
            self._debug_log(f"调整印象分数失败: {e}", "error")
            return self.get_impression_score(group_id, person_name)

    def get_person_impression_summary(
        self, group_id: str, person_name: str
    ) -> dict[str, Any]:
        """获取人物印象摘要信息"""
        try:
            element_id = self._find_person_element(group_id, person_name)

            if not element_id:
                return {
                    "name": person_name,
                    "score": self.impression_config["default_score"],
                    "summary": f"尚未建立对{person_name}的印象",
                    "memory_count": 0,
                    "last_updated": "无",
                }

            impression_memories = self.memory_graph.get_element_memories_with_role(
                element_id, "impression"
            )
            impression_memories = self.filter_memories_by_group(
                impression_memories, group_id
            )

            if not impression_memories:
                legacy_name = f"Imprint:{group_id}:{person_name}"
                for concept in self.memory_graph.concepts.values():
                    if concept.name == legacy_name:
                        all_mem = self.memory_graph.get_element_memories(concept.id)
                        impression_memories = self.filter_memories_by_group(all_mem, group_id)
                        break

            if not impression_memories:
                return {
                    "name": person_name,
                    "score": self.impression_config["default_score"],
                    "summary": f"对{person_name}的印象记录为空",
                    "memory_count": 0,
                    "last_updated": "无",
                }

            latest_memory = max(impression_memories, key=lambda m: m.last_accessed)
            current_score = latest_memory.strength
            summary = latest_memory.content

            try:
                if isinstance(latest_memory.last_accessed, (int, float)):
                    dt = datetime.fromtimestamp(latest_memory.last_accessed)
                    last_updated = dt.strftime("%Y-%m-%d %H:%M:%S")
                elif hasattr(latest_memory.last_accessed, "strftime"):
                    last_updated = latest_memory.last_accessed.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                else:
                    last_updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            except Exception as time_e:
                self._debug_log(f"时间格式化失败: {time_e}", "warning")
                last_updated = "时间格式化失败"

            return {
                "name": person_name,
                "score": current_score,
                "summary": summary,
                "memory_count": len(impression_memories),
                "last_updated": last_updated,
            }

        except Exception as e:
            self._debug_log(f"获取印象摘要失败: {e}", "error")
            return {
                "name": person_name,
                "score": self.impression_config["default_score"],
                "summary": "获取印象信息失败",
                "memory_count": 0,
                "last_updated": "无",
            }

    def get_person_impression_memories(
        self, group_id: str, person_name: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        """获取人物印象相关的记忆列表"""
        try:
            element_id = self._find_person_element(group_id, person_name)

            if not element_id:
                return []

            impression_memories = self.memory_graph.get_element_memories_with_role(
                element_id, "impression"
            )
            impression_memories = self.filter_memories_by_group(
                impression_memories, group_id
            )

            if not impression_memories:
                legacy_name = f"Imprint:{group_id}:{person_name}"
                for concept in self.memory_graph.concepts.values():
                    if concept.name == legacy_name:
                        all_mem = self.memory_graph.get_element_memories(concept.id)
                        impression_memories = self.filter_memories_by_group(all_mem, group_id)
                        break

            impression_memories.sort(key=lambda m: m.last_accessed, reverse=True)
            impression_memories = impression_memories[:limit]

            memories_list = []
            for memory in impression_memories:
                memories_list.append(
                    {
                        "id": memory.id,
                        "content": memory.content,
                        "details": getattr(memory, 'details', '') or "",
                        "score": memory.strength,
                        "created": self._safe_format_datetime(memory.created_at),
                        "last_accessed": self._safe_format_datetime(
                            memory.last_accessed
                        ),
                    }
                )

            return memories_list

        except Exception as e:
            self._debug_log(f"获取印象记忆失败: {e}", "error")
            return []

    def _safe_format_datetime(self, dt_obj) -> str:
        """安全地格式化datetime对象或时间戳"""
        try:
            if isinstance(dt_obj, (int, float)):
                dt = datetime.fromtimestamp(dt_obj)
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            elif hasattr(dt_obj, "strftime"):
                return dt_obj.strftime("%Y-%m-%d %H:%M:%S")
            else:
                return str(dt_obj)
        except Exception as e:
            self._debug_log(f"安全格式化时间失败: {e}", "warning")
            return "未知时间"
