"""
核心记忆系统
模仿人类海马体功能，处理记忆的形成、提取、遗忘和巩固
"""
import asyncio
import json
import time
import random
import sqlite3
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
import os

try:
    from astrbot.api.provider import ProviderRequest
    from astrbot.api.event import AstrMessageEvent
    from astrbot.api.star import Context
    from astrbot.api import logger
    from astrbot.api.star import StarTools
    from .models import Concept, Memory, Connection
    from .config import MemoryConfigManager
    from .memory_graph import MemoryGraph
    from .batch_extractor import BatchMemoryExtractor
    from .resource_management import resource_manager
    from .database_migration import SmartDatabaseMigration
    from .embedding_cache_manager import EmbeddingCacheManager
except ImportError:
    # Fallback for testing without astrbot
    import logging
    logger = logging.getLogger(__name__)
    from models import Concept, Memory, Connection
    from config import MemoryConfigManager
    from memory_graph import MemoryGraph
    from batch_extractor import BatchMemoryExtractor
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
    def filter_memories_by_group(memories: List['Memory'], group_id: str = "") -> List['Memory']:
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
            return [m for m in memories if not hasattr(m, 'group_id') or not m.group_id]
        else:
            # 群聊场景：只获取匹配group_id的记忆
            return [m for m in memories if hasattr(m, 'group_id') and m.group_id == group_id]
    
    @staticmethod
    def filter_concepts_by_group(concepts: Dict[str, 'Concept'], memories: Dict[str, 'Memory'], group_id: str = "") -> Dict[str, 'Concept']:
        """
        根据群聊隔离过滤概念
        
        Args:
            concepts: 概念字典
            memories: 记忆字典（用于判断概念是否属于指定群组）
            group_id: 群组ID
            
        Returns:
            过滤后的概念字典
        """
        filtered_concepts = {}
        
        for concept_id, concept in concepts.items():
            # 检查该概念下是否有属于指定群组的记忆
            concept_has_group_memory = False
            for memory in memories.values():
                if memory.concept_id == concept_id:
                    if not group_id and (not hasattr(memory, 'group_id') or not memory.group_id):
                        # 私聊场景：概念有无group_id的记忆
                        concept_has_group_memory = True
                        break
                    elif group_id and hasattr(memory, 'group_id') and memory.group_id == group_id:
                        # 群聊场景：概念有匹配group_id的记忆
                        concept_has_group_memory = True
                        break
            
            if concept_has_group_memory:
                filtered_concepts[concept_id] = concept
        
        return filtered_concepts
    
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
        self.batch_extractor = BatchMemoryExtractor(self)
        self.embedding_cache = None  # 嵌入向量缓存管理器
        
        # 组件引用（由外部注入）
        self.topic_engine = None
        self.user_profiling = None
        
        # 印象系统配置
        self.impression_config = {
            "default_score": 0.5,
            "enable_impression_injection": config.get("enable_impression_injection", True),
            "min_score": 0.0,
            "max_score": 1.0
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
        self._pending_save_task = None  # 待处理的保存任务
        
        # 异步任务生命周期管理 - 新增
        self._managed_tasks = set()  # 管理的异步任务集合
        self._maintenance_task = None  # 维护循环任务
        self._should_stop_maintenance = asyncio.Event()  # 停止维护事件
        self._should_stop_maintenance.clear()  # 初始不停止
        
    def set_components(self, topic_engine, user_profiling):
        """注入组件依赖"""
        self.topic_engine = topic_engine
        self.user_profiling = user_profiling

    def _create_managed_task(self, coro):
        """创建托管的异步任务，确保任务生命周期被正确管理"""
        if not asyncio.iscoroutine(coro):
            self._debug_log(f"无法创建任务：传入的不是协程对象", "warning")
            return
        
        # 使用事件循环管理器创建任务
        task = resource_manager.create_task(coro)
        self._managed_tasks.add(task)
        
        self._debug_log(f"创建新任务: {coro.__name__}。当前任务数: {len(self._managed_tasks)}", "debug")
        # 添加任务完成回调，自动清理
        def _task_done_callback(t):
            self._managed_tasks.discard(t)
            if t.exception():
                self._debug_log(f"托管任务异常: {t.exception()}", "error")
            self._debug_log(f"任务 {coro.__name__} 完成。当前任务数: {len(self._managed_tasks)}", "debug")
        
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
                    timeout=5.0
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

    def _record_memory_access_by_ids(self, memory_ids: List[str]) -> int:
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

    def _record_memory_access_by_contents(self, contents: List[str]) -> int:
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

    def _record_recall_results_accesses(self, results: List[Any]) -> int:
        if not results:
            return 0
        memory_ids = []
        contents = []
        for result in results:
            metadata = getattr(result, "metadata", None)
            memory_id = metadata.get("memory_id") if isinstance(metadata, dict) else None
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
            
            # 获取最后保存时间
            last_save = self._last_save_time.get(group_id, 0)
            current_time = time.time()
            
            # 如果距离上次保存时间少于2秒，延迟保存
            if current_time - last_save < 2:
                # 取消之前的保存任务
                if self._pending_save_task and not self._pending_save_task.done():
                    self._pending_save_task.cancel()
                
                # 创建新的延迟保存任务
                self._pending_save_task = asyncio.create_task(
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
                
            self._debug_log(f"提供商状态 - LLM: {'已连接' if llm_ready else '未连接'}, 嵌入: {'已连接' if embedding_ready else '未连接'}", "info")
        except Exception as e:
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
                        self._debug_log(f"嵌入向量缓存初始化失败，已降级: {cache_e}", "warning")
                
                # 调度初始预计算任务
                if self.embedding_cache and self.memory_graph.memories:
                    asyncio.create_task(self.embedding_cache.schedule_initial_precompute())
                    logger.info(f"已调度 {len(self.memory_graph.memories)} 条记忆的预计算任务")
                
                self._debug_log("记忆系统初始化完成", "info")
            except Exception as init_e:
                self._debug_log(f"记忆系统初始化失败: {init_e}", "error")
        else:
            self._debug_log("由于数据库迁移失败，跳过记忆系统初始化", "warning")
        
    def load_memory_state(self, group_id: str = ""):
        """从数据库加载记忆状态"""
        import os
        
        # 获取对应的数据库路径
        db_path = self._get_group_db_path(group_id)
        
        if not os.path.exists(db_path):
            return
            
        conn = None
        try:
            # 使用连接池获取数据库连接
            conn = resource_manager.get_db_connection(db_path)
            cursor = conn.cursor()
            
            # 检查表是否存在
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='concepts'")
            if not cursor.fetchone():
                return
            
            # 加载概念
            cursor.execute("SELECT id, name, created_at, last_accessed, access_count FROM concepts")
            concepts = cursor.fetchall()
            for concept_data in concepts:
                self.memory_graph.add_concept(
                    concept_id=concept_data[0],
                    name=concept_data[1],
                    created_at=concept_data[2],
                    last_accessed=concept_data[3],
                    access_count=concept_data[4]
                )
                
            cursor.execute("PRAGMA table_info('memories')")
            memory_columns = [col[1] for col in cursor.fetchall()]
            has_allow_forget = "allow_forget" in memory_columns

            # 加载记忆 - 支持群聊隔离
            if has_allow_forget:
                if group_id:
                    cursor.execute("SELECT id, concept_id, content, details, participants, location, emotion, tags, created_at, last_accessed, access_count, strength, allow_forget FROM memories WHERE group_id = ?", (group_id,))
                else:
                    cursor.execute("SELECT id, concept_id, content, details, participants, location, emotion, tags, created_at, last_accessed, access_count, strength, allow_forget FROM memories WHERE group_id = '' OR group_id IS NULL")
            else:
                if group_id:
                    cursor.execute("SELECT id, concept_id, content, details, participants, location, emotion, tags, created_at, last_accessed, access_count, strength FROM memories WHERE group_id = ?", (group_id,))
                else:
                    cursor.execute("SELECT id, concept_id, content, details, participants, location, emotion, tags, created_at, last_accessed, access_count, strength FROM memories WHERE group_id = '' OR group_id IS NULL")
            memories = cursor.fetchall()
            for memory_data in memories:
                allow_forget = True
                if has_allow_forget and len(memory_data) > 12:
                    allow_forget = True if memory_data[12] is None else bool(memory_data[12])
                self.memory_graph.add_memory(
                    content=memory_data[2],
                    concept_id=memory_data[1],
                    memory_id=memory_data[0],
                    details=memory_data[3] or "",
                    participants=memory_data[4] or "",
                    location=memory_data[5] or "",
                    emotion=memory_data[6] or "",
                    tags=memory_data[7] or "",
                    created_at=memory_data[8],
                    last_accessed=memory_data[9],
                    access_count=memory_data[10],
                    strength=memory_data[11],
                    allow_forget=allow_forget,
                    group_id=group_id
                )
                
            # 加载连接
            cursor.execute("SELECT id, from_concept, to_concept, strength, last_strengthened FROM connections")
            connections = cursor.fetchall()
            for conn_data in connections:
                self.memory_graph.add_connection(
                    from_concept=conn_data[1],
                    to_concept=conn_data[2],
                    strength=conn_data[3],
                    connection_id=conn_data[0],
                    last_strengthened=conn_data[4]
                )
                
            # 仅在成功加载时输出一次统计信息
            group_info = f" (群: {group_id})" if group_id else ""
            self._debug_log(f"记忆系统加载{group_info}，包含 {len(concepts)} 个概念，{len(memories)} 条记忆", "debug")
            
        except Exception as e:
            self._debug_log(f"状态加载异常: {e}", "error")
        finally:
            if conn is not None:
                resource_manager.release_db_connection(db_path, conn)

    async def save_memory_state(self, group_id: str = ""):
        """保存记忆状态到数据库"""
        try:
            # 获取对应的数据库路径
            db_path = self._get_group_db_path(group_id)
            
            # 确保数据库和表存在
            await self._ensure_database_structure(db_path)
            
            # 使用连接池获取数据库连接
            conn = resource_manager.get_db_connection(db_path)
            cursor = conn.cursor()
            
            # 使用事务确保数据一致性
            cursor.execute("BEGIN TRANSACTION")
            
            try:
                
                # 增量更新概念
                for concept in self.memory_graph.concepts.values():
                    cursor.execute('''
                        INSERT OR REPLACE INTO concepts
                        (id, name, created_at, last_accessed, access_count)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (concept.id, concept.name, concept.created_at, concept.last_accessed, concept.access_count))
                
                # 增量更新记忆
                for memory in self.memory_graph.memories.values():
                    cursor.execute('''
                        INSERT OR REPLACE INTO memories
                        (id, concept_id, content, details, participants,
                        location, emotion, tags, created_at, last_accessed, access_count, strength, allow_forget, group_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (memory.id, memory.concept_id, memory.content, memory.details,
                         memory.participants, memory.location, memory.emotion, memory.tags,
                         memory.created_at, memory.last_accessed, memory.access_count, memory.strength,
                         int(bool(memory.allow_forget)), group_id))
                
                # 增量更新连接
                existing_connections = set()
                cursor.execute("SELECT id FROM connections")
                for row in cursor.fetchall():
                    existing_connections.add(row[0])
                
                # 更新现有连接
                for conn_obj in self.memory_graph.connections:
                    if conn_obj.id in existing_connections:
                        cursor.execute('''
                            UPDATE connections
                            SET from_concept=?, to_concept=?, strength=?, last_strengthened=?
                            WHERE id=?
                        ''', (conn_obj.from_concept, conn_obj.to_concept, conn_obj.strength, conn_obj.last_strengthened, conn_obj.id))
                    else:
                        cursor.execute('''
                            INSERT INTO connections (id, from_concept, to_concept, strength, last_strengthened)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (conn_obj.id, conn_obj.from_concept, conn_obj.to_concept, conn_obj.strength, conn_obj.last_strengthened))
                
                # 提交事务
                conn.commit()
                
                # 释放连接回连接池
                resource_manager.release_db_connection(db_path, conn)
                
                # 简化的保存完成日志
                group_info = f" (群: {group_id})" if group_id else ""
                self._debug_log(f"记忆保存完成{group_info}: {len(self.memory_graph.concepts)}个概念, {len(self.memory_graph.memories)}条记忆", "debug")
                
            except Exception as e:
                try:
                    # 回滚事务
                    conn.rollback()
                except Exception as rollback_e:
                    self._debug_log(f"回滚失败: {rollback_e}", "error")
                # 释放连接回连接池
                resource_manager.release_db_connection(db_path, conn)
                self._debug_log(f"保存失败: {e}", "error")
                raise
                
        except Exception as e:
            self._debug_log(f"保存过程异常: {e}", "error")

    async def delete_memory_by_id(self, memory_id: str, group_id: str = "") -> bool:
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
                    (memory_id, group_id)
                )
            else:
                cursor.execute(
                    "DELETE FROM memories WHERE id = ?",
                    (memory_id,)
                )

            deleted_rows = cursor.rowcount
            conn.commit()
            resource_manager.release_db_connection(db_path, conn)

            if self.embedding_cache:
                await self.embedding_cache.delete_embedding(memory_id, group_id)

            return removed_from_graph or deleted_rows > 0
        except Exception as e:
            self._debug_log(f"删除记忆失败: {e}", "error")
            return False
    
    async def _ensure_database_structure(self, db_path: str):
        """确保数据库和所需的表结构存在"""
        try:
            # 使用连接池获取数据库连接
            conn = resource_manager.get_db_connection(db_path)
            cursor = conn.cursor()
            
            # 检查表是否存在
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing_tables = {row[0] for row in cursor.fetchall()}
            
            # 创建所需的表（如果不存在）
            if 'concepts' not in existing_tables:
                cursor.execute('''
                    CREATE TABLE concepts (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        created_at REAL,
                        last_accessed REAL,
                        access_count INTEGER DEFAULT 0
                    )
                ''')
                self._debug_log(f"创建表: concepts", "debug")
            
            if 'memories' not in existing_tables:
                cursor.execute('''
                    CREATE TABLE memories (
                        id TEXT PRIMARY KEY,
                        concept_id TEXT NOT NULL,
                        content TEXT NOT NULL,
                        details TEXT,
                        participants TEXT,
                        location TEXT,
                        emotion TEXT,
                        tags TEXT,
                        created_at REAL,
                        last_accessed REAL,
                        access_count INTEGER DEFAULT 0,
                        strength REAL DEFAULT 1.0,
                        allow_forget INTEGER DEFAULT 1,
                        group_id TEXT DEFAULT "",
                        FOREIGN KEY (concept_id) REFERENCES concepts (id)
                    )
                ''')
                self._debug_log(f"创建表: memories", "debug")
                
                # 创建群聊隔离相关的索引
                cursor.execute('''
                    CREATE INDEX idx_memories_group_id ON memories(group_id)
                ''')
                cursor.execute('''
                    CREATE INDEX idx_memories_concept_group ON memories(concept_id, group_id)
                ''')
                cursor.execute('''
                    CREATE INDEX idx_memories_created_group ON memories(created_at, group_id)
                ''')
                self._debug_log(f"创建群聊隔离索引", "debug")
            else:
                cursor.execute("PRAGMA table_info('memories')")
                memory_columns = {col[1] for col in cursor.fetchall()}
                if "allow_forget" not in memory_columns:
                    cursor.execute("ALTER TABLE memories ADD COLUMN allow_forget INTEGER DEFAULT 1")
                    cursor.execute("UPDATE memories SET allow_forget = 1 WHERE allow_forget IS NULL")
            
            if 'connections' not in existing_tables:
                cursor.execute('''
                    CREATE TABLE connections (
                        id TEXT PRIMARY KEY,
                        from_concept TEXT NOT NULL,
                        to_concept TEXT NOT NULL,
                        strength REAL DEFAULT 1.0,
                        last_strengthened REAL,
                        FOREIGN KEY (from_concept) REFERENCES concepts (id),
                        FOREIGN KEY (to_concept) REFERENCES concepts (id)
                    )
                ''')
                self._debug_log(f"创建表: connections", "debug")
            
            conn.commit()
            
            # 释放连接回连接池
            resource_manager.release_db_connection(db_path, conn)
                
        except Exception as e:
            self._debug_log(f"确保数据库结构异常: {e}", "error")
            raise
    
    async def process_message(self, event: AstrMessageEvent, group_id: str = ""):
        """处理消息，形成记忆（旧方法，保留兼容性）"""
        try:
            # 获取对话历史
            history = await self.get_conversation_history(event)
            if not history:
                return
                
            # 提取主题和关键词
            themes = await self.extract_themes(history)
            
            # 形成记忆
            for theme in themes:
                memory_content = await self.form_memory(theme, history, event)
                if memory_content:
                    concept_id = self.memory_graph.add_concept(theme)
                    memory_id = self.memory_graph.add_memory(memory_content, concept_id, group_id=group_id)
                    
                    # 建立连接
                    self.establish_connections(concept_id, themes)
                    
            # 根据回忆模式决定是否触发回忆
            recall_mode = self.memory_config["recall_mode"]
            should_trigger = False
            
            if recall_mode == "simple" or recall_mode == "embedding":
                # 关键词和嵌入模式每次都触发
                should_trigger = True
            elif recall_mode == "llm":
                # LLM模式按概率触发
                trigger_probability = self.memory_config.get("recall_trigger_probability", 0.6)
                should_trigger = random.random() < trigger_probability
            
            if should_trigger:
                recalled = await self.recall_memories("", event)
                if recalled:
                    logger.debug(f"触发了回忆: {recalled[:2]} (模式: {recall_mode})")
                    
        except Exception as e:
            logger.error(f"处理消息时出错: {e}")

    async def process_message_optimized(self, event: AstrMessageEvent, group_id: str = ""):
        """优化的消息处理，使用单次LLM调用"""
        try:
            # 获取完整的对话历史
            full_history = await self.get_conversation_history_full(event)
            if not full_history:
                return
            
            # 检查是否启用批量记忆提取
            enable_batch_extraction = self.memory_config.get("enable_batch_memory_extraction", True)
            
            if not enable_batch_extraction:
                # 如果禁用批量记忆提取，则跳过记忆形成
                return

            # 获取记忆形成间隔（对话轮数）
            memory_formation_interval = self.memory_config.get("memory_formation_interval", 15)
            
            # 简单实现：每隔一定轮数形成一次记忆
            # 这里可以根据实际需求实现更复杂的逻辑
            if len(full_history) % memory_formation_interval != 0:
                return

            # 使用批量提取器，单次LLM调用获取多个记忆
            extracted_memories = await self.batch_extractor.extract_memories_and_themes(full_history)
            
            if not extracted_memories:
                return
            
            # 批量处理提取的记忆
            themes = []
            concept_ids = []  # 存储创建的概念ID
            valid_memories = 0
            valid_impressions = 0  # 记录有效印象数量
            
            for memory_data in extracted_memories:
                try:
                    theme = str(memory_data.get("theme", "")).strip()
                    content = str(memory_data.get("content", "")).strip()
                    details = str(memory_data.get("details", "")).strip()
                    participants = str(memory_data.get("participants", "")).strip()
                    location = str(memory_data.get("location", "")).strip()
                    emotion = str(memory_data.get("emotion", "")).strip()
                    tags = str(memory_data.get("tags", "")).strip()
                    confidence = float(memory_data.get("confidence", 0.7))
                    memory_type = str(memory_data.get("memory_type", "normal")).strip().lower()
                    allow_forget = self._parse_allow_forget_value(memory_data.get("allow_forget", True), True)
                    
                    # 验证数据完整性
                    if not theme or not content:
                        continue
                    
                    # 根据置信度调整记忆强度
                    base_strength = 1.0
                    adjusted_strength = base_strength * max(0.0, min(1.0, confidence))
                    
                    # 特殊处理印象记忆
                    if memory_type == "impression":
                        # 从主题中提取人物姓名
                        person_name = self._extract_person_name_from_theme(theme)
                        if person_name:
                            # 使用印象系统记录人物印象
                            impression_score = adjusted_strength  # 使用记忆强度作为印象分数
                            self.record_person_impression(group_id, person_name, content, impression_score, details)
                            valid_impressions += 1
                        else:
                            # 如果无法提取人名，作为普通记忆处理
                            memory_type = "normal"
                    
                    # 处理普通记忆
                    if memory_type == "normal":
                        # 添加概念和记忆
                        concept_id = self.memory_graph.add_concept(theme)
                        memory_id = self.memory_graph.add_memory(
                            content=content,
                            concept_id=concept_id,
                            details=details,
                            participants=participants,
                            location=location,
                            emotion=emotion,
                            tags=tags,
                            strength=adjusted_strength,
                            allow_forget=allow_forget
                        )
                        
                        themes.append(theme)
                        concept_ids.append(concept_id)
                        valid_memories += 1
                    
                except (KeyError, ValueError, TypeError):
                    continue
            
            # 仅在成功创建记忆时输出一次日志
            if valid_memories > 0:
                group_info = f" (群: {group_id})" if group_id else ""
                self._debug_log(f"批量创建记忆{group_info}: {valid_memories}条", "debug")
            
            # 建立概念之间的连接 - 使用存储的概念ID
            if concept_ids:
                for concept_id in concept_ids:
                    try:
                        self.establish_connections(concept_id, themes)
                    except Exception:
                        continue
            
            # 提取人物印象（如果启用）
            if self.impression_config.get("enable_impression_injection", True):
                try:
                    # 检查LLM是否可用
                    llm_provider = await self.get_llm_provider()
                    if llm_provider:
                        extracted_impressions = await self.batch_extractor.extract_impressions_from_conversation(full_history, group_id)
                        
                        if extracted_impressions:
                            valid_impressions = 0
                            for impression_data in extracted_impressions:
                                try:
                                    person_name = impression_data.get("person_name", "").strip()
                                    summary = impression_data.get("summary", "").strip()
                                    score = impression_data.get("score", 0.5)
                                    details = impression_data.get("details", "").strip()
                                    confidence = impression_data.get("confidence", 0.5)
                                    
                                    # 验证数据完整性
                                    if not person_name or not summary:
                                        continue
                                    
                                    # 根据置信度决定是否记录印象
                                    if confidence >= 0.3:  # 置信度阈值
                                        memory_id = self.record_person_impression(
                                            group_id, person_name, summary, score, details
                                        )
                                        if memory_id:
                                            valid_impressions += 1
                                            
                                except (KeyError, ValueError, TypeError):
                                    continue
                            
                            if valid_impressions > 0:
                                self._debug_log(f"提取印象{group_info}: {valid_impressions}条", "debug")
                    else:
                        # LLM不可用时的回退逻辑：基于关键词的简单印象提取
                        await self._fallback_impression_extraction(full_history, group_id)
                            
                except Exception as e:
                    self._debug_log(f"印象提取失败: {e}", "warning")
        except Exception as e:
            self._debug_log(f"优化消息处理失败: {e}", "error")

    async def _fallback_impression_extraction(self, conversation_history: List[Dict[str, Any]], group_id: str):
        """基于关键词的简单印象提取（备用方案）"""
        try:
            impression_keywords = {
                "觉得": 0.1, "感觉": 0.1, "印象": 0.2,
                "人不错": 0.3, "挺好的": 0.2, "很厉害": 0.3,
                "有点": -0.1, "不太行": -0.3, "很差": -0.4
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
                            self.record_person_impression(group_id, name, summary, score=None, details=f"来自 {sender_name} 的评价: {content}")
                            self.adjust_impression_score(group_id, name, score_delta)
                            self._debug_log(f"备用方案提取印象: {name} ({keyword})", "debug")
                            
        except Exception as e:
            self._debug_log(f"备用印象提取方案失败: {e}", "warning")
    
    async def get_conversation_history(self, event: AstrMessageEvent) -> List[str]:
        """获取对话历史（兼容旧版本）"""
        try:
            uid = event.unified_msg_origin
            curr_cid = await self.context.conversation_manager.get_curr_conversation_id(uid)
            if curr_cid:
                conversation = await self.context.conversation_manager.get_conversation(uid, curr_cid)
                if conversation and conversation.history:
                    history = json.loads(conversation.history)
                    return [msg.get("content", "") for msg in history[-10:]]  # 最近10条
            return []
        except Exception as e:
            logger.error(f"获取对话历史失败: {e}")
            return []

    async def get_conversation_history_full(self, event: AstrMessageEvent) -> List[Dict[str, Any]]:
        """获取包含完整信息的对话历史"""
        try:
            uid = event.unified_msg_origin
            curr_cid = await self.context.conversation_manager.get_curr_conversation_id(uid)
            if curr_cid:
                conversation = await self.context.conversation_manager.get_conversation(uid, curr_cid)
                if conversation and conversation.history:
                    history = json.loads(conversation.history)
                    # 添加发送者信息和时间戳
                    full_history = []
                    # 从配置中获取对话历史条数，默认为20条
                    conversation_history_count = self.memory_config.get("conversation_history_count", 20)
                    for msg in history[-conversation_history_count:]:  # 使用配置中的条数，避免token过多
                        full_msg = {
                            "role": msg.get("role", "user"),
                            "content": msg.get("content", ""),
                            "sender_name": msg.get("sender_name", "用户"),
                            "timestamp": msg.get("timestamp", time.time())
                        }
                        full_history.append(full_msg)
                    return full_history
            return []
        except Exception as e:
            logger.error(f"获取完整对话历史失败: {e}")
            return []
    
    async def extract_themes(self, history: List[str]) -> List[str]:
        """从对话历史中提取主题"""
        if not history:
            return []
            
        # 根据配置选择提取方式
        if self.memory_config["recall_mode"] in ["llm", "embedding"]:
            return await self._extract_themes_by_llm(history)
        else:
            return await self._extract_themes_simple(history)
    
    async def _extract_themes_simple(self, history: List[str]) -> List[str]:
        """简单的关键词提取"""
        text = " ".join(str(item) if not isinstance(item, str) else item for item in history)
        keywords = []
        
        # 提取名词和关键词
        words = re.findall(r'\b[\u4e00-\u9fff]{2,4}\b', text)
        word_freq = {}
        for word in words:
            if len(word) >= 2 and word not in ["你好", "谢谢", "再见"]:
                word_freq[word] = word_freq.get(word, 0) + 1
        
        # 返回频率最高的前5个关键词
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        return [str(word) for word, freq in sorted_words[:5]]
    
    async def _extract_themes_by_llm(self, history: List[str]) -> List[str]:
        """使用LLM从对话历史中提取主题"""
        try:
            if not history:
                return []
                
            prompt = f"""请从以下对话中提取3-5个核心主题或关键词。这些主题将用于构建记忆网络。

对话内容：
{" ".join(map(str, history))}

要求：
1. 提取的主题应该是对话的核心内容
2. 每个主题可以包含多个相关关键词，用逗号分隔
3. 返回格式：主题1关键词1,主题1关键词2,主题2关键词1,主题2关键词2
4. 每个关键词2-4个汉字
5. 不要包含解释，只返回主题列表
6. 例如：工作,项目,会议,学习,考试,复习
"""
            
            provider = await self.get_llm_provider()
            if provider:
                response = await provider.text_chat(
                    prompt=prompt,
                    contexts=[],
                    system_prompt="你是一个主题提取助手，请准确提取对话的核心主题。"
                )
                
                themes_text = response.completion_text.strip()
                # 清理和分割主题，支持逗号分隔的多个关键词
                themes = [theme.strip() for theme in themes_text.replace("，", ",").split(",") if theme.strip()]
                return themes[:8]  # 最多返回8个关键词/主题
                
        except Exception as e:
            logger.error(f"LLM主题提取失败: {e}")
            return await self._extract_themes_simple(history)  # 回退到简单模式
    
    async def form_memory(self, theme: str, history: List[str], event: AstrMessageEvent) -> str:
        """形成记忆内容"""
        try:
            # 使用LLM总结记忆
            prompt = f"""请将以下关于"{theme}"的对话总结成一句口语化的记忆，就像亲身经历一样：
            
            对话内容：{" ".join(map(str, history[-3:]))}
            
            要求：
            1. 如果记忆内容涉及Bot的发言，请使用第一人称"我"来表述
            2. 如果记忆内容涉及用户的发言，请使用第三人称
            3. 简洁自然
            4. 包含关键信息
            5. 不超过50字
            """
            
            if self.memory_config["recall_mode"] == "llm":
                provider = await self.get_llm_provider()
                if provider:
                    response = await provider.text_chat(
                        prompt=prompt,
                        contexts=[],
                        system_prompt=self.memory_config["llm_system_prompt"]
                    )
                    return response.completion_text.strip()
            
            # 简单总结
            return f"我记得我们聊过关于{theme}的事情"
                
        except Exception as e:
            logger.error(f"形成记忆失败: {e}")
            return f"关于{theme}的记忆"
    
    def establish_connections(self, concept_id: str, themes: List[str]):
        """建立概念之间的连接"""
        try:
            if concept_id not in self.memory_graph.concepts:
                logger.warning(f"概念ID不存在: {concept_id}")
                return
                
            current_concept = self.memory_graph.concepts[concept_id]
            
            for other_theme in themes:
                if other_theme != current_concept.name:
                    other_concept = None
                    for concept in self.memory_graph.concepts.values():
                        if concept.name == other_theme:
                            other_concept = concept
                            break
                    
                    if other_concept and other_concept.id != concept_id:
                        self.memory_graph.add_connection(concept_id, other_concept.id)
                        
        except Exception as e:
            logger.error(f"建立概念连接时出错: {e}, 概念ID: {concept_id}, 主题: {themes}")
    
    async def recall_memories_full(self, keyword: str) -> List['Memory']:
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

    async def _recall_simple(self, keyword: str) -> List[str]:
        """增强的简单关键词匹配回忆"""
        try:
            if not keyword:
                # 随机回忆，优先选择强度高的记忆
                memories = list(self.memory_graph.memories.values())
                if memories:
                    # 按记忆强度和时间排序
                    memories.sort(key=lambda m: (m.strength, m.last_accessed), reverse=True)
                    selected = memories[:min(3, len(memories))]
                    return [m.content for m in selected]
                return []
            
            # 增强的关键词匹配，支持多关键词匹配
            related_memories = []
            keyword_lower = keyword.lower()
            
            # 直接概念匹配，支持逗号分隔的多关键词
            for concept in self.memory_graph.concepts.values():
                concept_name_lower = concept.name.lower()
                
                # 检查概念名称是否包含任意关键词
                concept_keywords = concept_name_lower.split(',')
                for concept_keyword in concept_keywords:
                    concept_keyword = concept_keyword.strip()
                    if (keyword_lower in concept_keyword or concept_keyword in keyword_lower or
                        any(kw.strip() in concept_keyword for kw in keyword_lower.split(','))):
                        concept_memories = [m for m in self.memory_graph.memories.values()
                                          if m.concept_id == concept.id]
                        # 按记忆强度排序
                        concept_memories.sort(key=lambda m: m.strength, reverse=True)
                        for memory in concept_memories[:2]:  # 每个概念最多2条
                            if memory.content not in related_memories:
                                related_memories.append(memory.content)
                        break
            
            # 内容关键词匹配
            for memory in self.memory_graph.memories.values():
                if keyword_lower in memory.content.lower():
                    if memory.content not in related_memories:
                        related_memories.append(memory.content)
            
            # 去重并限制数量
            seen = set()
            unique_memories = []
            for memory in related_memories:
                if memory not in seen:
                    seen.add(memory)
                    unique_memories.append(memory)
                    if len(unique_memories) >= 5:
                        break
            
            return unique_memories
            
        except Exception as e:
            logger.error(f"简单回忆失败: {e}")
            return []

    async def _recall_llm(self, keyword: str, event: AstrMessageEvent) -> List[str]:
        """LLM智能回忆"""
        try:
            if not self.memory_graph.memories:
                return []
                
            # 获取所有记忆内容
            all_memories = [m.content for m in self.memory_graph.memories.values()]
            
            if not keyword:
                # 随机选择3条记忆
                return random.sample(all_memories, min(3, len(all_memories)))
            
            # 使用LLM进行智能回忆
            prompt = f"""请从以下记忆列表中，找出与用户提问“{keyword}”最相关的3-5条记忆。

记忆列表：
{chr(10).join(f"- {mem}" for mem in all_memories)}

严格按照以下JSON格式返回结果，不要有任何多余的解释：
{{
  "recalled_memories": [
    "记忆1",
    "记忆2",
    ...
  ]
}}

如果找不到任何相关记忆，或记忆列表为空，请返回一个空列表：
{{
  "recalled_memories": []
}}
"""

            provider = await self.get_llm_provider()
            if provider:
                response = await provider.text_chat(
                    prompt=prompt,
                    contexts=[],
                    system_prompt="你是一个记忆检索助手，你的任务是严格按照JSON格式返回检索到的记忆。"
                )
                
                try:
                    # 提取并解析JSON
                    completion_text = response.completion_text.strip()
                    json_match = re.search(r'\{.*\}', completion_text, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(0)
                        data = json.loads(json_str)
                        recalled = data.get("recalled_memories", [])
                        # 确保返回的是列表
                        if isinstance(recalled, list):
                            return recalled[:5]
                    self._debug_log("LLM响应中未找到JSON格式", "warning")
                    return [] # 如果没有找到JSON或解析失败
                except json.JSONDecodeError as e:
                    self._debug_log(f"JSON解析失败: {e}, 响应: {completion_text[:200]}...", "error")
                    return [] # JSON解析失败
                except Exception as e:
                    self._debug_log(f"JSON解析异常: {e}", "error")
                    return []
            
            # LLM不可用，回退到简单模式
            return await self._recall_simple(keyword)
            
        except Exception as e:
            logger.error(f"LLM回忆失败: {e}")
            return await self._recall_simple(keyword)

    async def _recall_embedding(self, keyword: str) -> List[str]:
        """基于嵌入向量的相似度回忆"""
        try:
            if not keyword or not self.memory_graph.memories:
                # 随机回忆
                memories = list(self.memory_graph.memories.values())
                if memories:
                    selected = random.sample(memories, min(3, len(memories)))
                    return [m.content for m in selected]
                return []
            
            # 检查是否配置了嵌入提供商，如果没有直接回退到简单模式
            provider = await self.get_embedding_provider()
            if not provider:
                logger.debug("嵌入提供商不可用，回退到简单模式")
                return await self._recall_simple(keyword)
            
            # 获取关键词的嵌入向量
            keyword_embedding = await self.get_embedding(keyword)
            if not keyword_embedding:
                logger.debug("无法获取关键词嵌入向量，回退到简单模式")
                return await self._recall_simple(keyword)
            
            # 计算与所有记忆的相似度
            memory_similarities = []
            for memory in self.memory_graph.memories.values():
                memory_embedding = await self.get_embedding(memory.content)
                if memory_embedding:
                    similarity = self._cosine_similarity(keyword_embedding, memory_embedding)
                    memory_similarities.append((memory, similarity))
            
            # 按相似度排序
            memory_similarities.sort(key=lambda x: x[1], reverse=True)
            
            # 返回最相似的5条记忆
            return [mem.content for mem, sim in memory_similarities[:5] if sim > 0.3]
            
        except Exception as e:
            logger.error(f"嵌入回忆失败: {e}")
            return await self._recall_simple(keyword)

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
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
    
    async def _get_associative_memories(self, core_memories: List[str]) -> List[str]:
        """基于核心记忆获取联想记忆"""
        try:
            if not core_memories or not self.memory_graph.memories:
                return []
            
            # 找到核心记忆对应的概念节点
            core_concepts = set()
            for memory_content in core_memories:
                for memory in self.memory_graph.memories.values():
                    if memory.content == memory_content:
                        core_concepts.add(memory.concept_id)
                        break
            
            if not core_concepts:
                return []
            
            # 收集与核心概念直接相连的相邻概念
            adjacent_concepts = set()
            for concept_id in core_concepts:
                neighbors = self.memory_graph.get_neighbors(concept_id)
                for neighbor_id, strength in neighbors:
                    if neighbor_id not in core_concepts and strength > 0.3:
                        adjacent_concepts.add(neighbor_id)
            
            # 收集相邻概念下的记忆
            associative_memories = []
            for concept_id in adjacent_concepts:
                concept_memories = [
                    m for m in self.memory_graph.memories.values()
                    if m.concept_id == concept_id
                ]
                
                # 按记忆强度和时间排序
                concept_memories.sort(
                    key=lambda m: (m.strength, m.last_accessed),
                    reverse=True
                )
                
                # 每个相邻概念最多添加1条记忆
                if concept_memories:
                    associative_memories.append(concept_memories[0].content)
            
            return associative_memories
            
        except Exception as e:
            logger.error(f"获取联想记忆失败: {e}")
            return []
    
    def _merge_memories_with_associative(self, core_memories: List[str], associative_memories: List[str]) -> List[str]:
        """合并核心记忆和联想记忆"""
        try:
            # 去重并合并
            all_memories = []
            seen = set()
            
            # 核心记忆在前
            for memory in core_memories:
                if memory not in seen:
                    seen.add(memory)
                    all_memories.append(memory)
            
            # 联想记忆在后
            for memory in associative_memories:
                if memory not in seen:
                    seen.add(memory)
                    all_memories.append(memory)
            
            # 限制总数量
            return all_memories[:5]
            
        except Exception as e:
            logger.error(f"合并记忆失败: {e}")
            return core_memories
    
    async def _recall_by_activation(self, keyword: str) -> List[str]:
        """基于激活扩散的回忆算法"""
        try:
            if not self.memory_graph.concepts or not self.memory_graph.memories:
                return []
            
            # 如果没有关键词，随机回忆
            if not keyword:
                memories = list(self.memory_graph.memories.values())
                if memories:
                    selected = random.sample(memories, min(3, len(memories)))
                    return [m.content for m in selected]
                return []
            
            # 找到初始激活的概念节点
            initial_concepts = []
            for concept in self.memory_graph.concepts.values():
                if keyword.lower() in concept.name.lower():
                    initial_concepts.append(concept)
            
            if not initial_concepts:
                # 如果没有直接匹配，使用简单关键词匹配
                return await self._recall_simple(keyword)
            
            # 激活扩散算法
            activation_map = {}  # concept_id -> activation_energy
            visited = set()
            
            # 初始化激活
            for concept in initial_concepts:
                activation_map[concept.id] = 1.0  # 初始能量为1.0
            
            # 扩散参数，以后加配置文件
            decay_factor = 0.7  # 能量衰减因子
            min_threshold = 0.1  # 最小激活阈值
            max_hops = 3  # 最大扩散步数
            
            # 进行扩散
            for hop in range(max_hops):
                new_activations = {}
                
                for concept_id, energy in activation_map.items():
                    if concept_id in visited:
                        continue
                    
                    # 获取该节点的所有连接
                    related_connections = [
                        conn for conn in self.memory_graph.connections
                        if conn.from_concept == concept_id or conn.to_concept == concept_id
                    ]
                    
                    for conn in related_connections:
                        # 确定相邻节点
                        neighbor_id = conn.to_concept if conn.from_concept == concept_id else conn.from_concept
                        
                        if neighbor_id in self.memory_graph.concepts:
                            # 计算传递的能量
                            transferred_energy = energy * conn.strength * decay_factor
                            
                            if transferred_energy > min_threshold:
                                if neighbor_id not in new_activations:
                                    new_activations[neighbor_id] = 0
                                new_activations[neighbor_id] += transferred_energy
                    
                    visited.add(concept_id)
                
                # 合并新的激活
                for concept_id, energy in new_activations.items():
                    if concept_id not in activation_map:
                        activation_map[concept_id] = 0
                    activation_map[concept_id] += energy
            
            # 收集被激活的概念下的记忆
            activated_memories = []
            adjacent_memories = []
            
            # 获取高激活的核心概念
            core_concepts = [
                concept_id for concept_id, energy in activation_map.items()
                if energy > min_threshold
            ]
            
            # 收集核心概念下的记忆
            for concept_id in core_concepts:
                concept_memories = [
                    m for m in self.memory_graph.memories.values()
                    if m.concept_id == concept_id
                ]
                
                # 按记忆强度和时间排序
                concept_memories.sort(
                    key=lambda m: (m.strength, m.last_accessed),
                    reverse=True
                )
                
                # 添加核心记忆
                for memory in concept_memories[:2]:  # 每个概念最多2条记忆
                    activated_memories.append(memory.content)
            
            # 收集相邻概念的记忆（与核心概念直接相连的概念）
            adjacent_concepts = set()
            for concept_id in core_concepts:
                for conn in self.memory_graph.connections:
                    if conn.from_concept == concept_id:
                        adjacent_concepts.add(conn.to_concept)
                    elif conn.to_concept == concept_id:
                        adjacent_concepts.add(conn.from_concept)
            
            # 收集相邻概念下的记忆
            for adjacent_concept_id in adjacent_concepts:
                if adjacent_concept_id in self.memory_graph.concepts:
                    adjacent_concept_memories = [
                        m for m in self.memory_graph.memories.values()
                        if m.concept_id == adjacent_concept_id
                    ]
                    
                    # 按记忆强度和时间排序
                    adjacent_concept_memories.sort(
                        key=lambda m: (m.strength, m.last_accessed),
                        reverse=True
                    )
                    
                    # 添加相邻记忆
                    for memory in adjacent_concept_memories[:1]:  # 每个相邻概念最多1条记忆
                        adjacent_memories.append(memory.content)
            
            # 合并结果：核心记忆在前，相邻记忆在后
            final_memories = activated_memories + adjacent_memories
            
            # 去重并限制数量
            seen = set()
            unique_memories = []
            for memory in final_memories:
                if memory not in seen:
                    seen.add(memory)
                    unique_memories.append(memory)
                    if len(unique_memories) >= 5:  # 最多返回5条
                        break
            
            return unique_memories
            
        except Exception as e:
            logger.error(f"激活扩散回忆失败: {e}")
            return await self._recall_simple(keyword)
    
    async def memory_maintenance_loop(self):
        """记忆维护循环"""
        db_dir = os.path.dirname(self.db_path)
        
        while True:
            try:
                consolidation_interval = self.memory_config["consolidation_interval_hours"] * 3600
                await asyncio.sleep(consolidation_interval)  # 按配置间隔检查
                
                maintenance_actions = []
                
                # 处理默认数据库（私有对话）
                if self.memory_config["enable_forgetting"]:
                    await self.forget_memories()
                    maintenance_actions.append("遗忘")
                
                if self.memory_config["enable_consolidation"]:
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
                            if filename.startswith("memory_group_") and filename.endswith(".db"):
                                group_id = filename[12:-3]  # 提取群聊ID
                                group_files.append(group_id)
                    
                    # 为每个群聊数据库执行维护
                    for group_id in group_files:
                        try:
                            # 清空当前记忆图，加载群聊数据库
                            self.memory_graph = MemoryGraph()
                            self.load_memory_state(group_id)
                            
                            # 执行群聊的维护操作
                            if self.memory_config["enable_forgetting"]:
                                await self.forget_memories()
                            
                            if self.memory_config["enable_consolidation"]:
                                await self.consolidate_memories()
                            
                            # 保存群聊数据库
                            await self.save_memory_state(group_id)
                            
                            self._debug_log(f"群聊 {group_id} 维护完成", "debug")
                            
                        except Exception as group_e:
                            self._debug_log(f"群聊 {group_id} 维护失败: {group_e}", "warning")
                
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
        forget_threshold = self.memory_config["forget_threshold_days"] * 24 * 3600
        
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
            self._debug_log(f"遗忘完成: 清理{len(memories_to_remove)}条记忆, {len(connections_to_remove)}个连接", "info")
        else:
            self._debug_log("遗忘检查完成: 没有需要清理的记忆或连接", "debug")
    
    async def consolidate_memories(self):
        """记忆整理机制 - 智能合并相似记忆"""
        consolidation_count = 0
        
        for concept in list(self.memory_graph.concepts.values()):
            concept_memories = [m for m in self.memory_graph.memories.values()
                              if m.concept_id == concept.id]
            
            if len(concept_memories) > self.memory_config["max_memories_per_topic"]:
                # 按时间排序，优先合并旧记忆
                concept_memories.sort(key=lambda m: m.created_at)
                
                # 使用更智能的合并策略
                merged_memories = []
                used_indices = set()
                
                for i, memory1 in enumerate(concept_memories):
                    if i in used_indices:
                        continue
                        
                    similar_group = [memory1]
                    used_indices.add(i)
                    
                    # 找到所有相似的记忆
                    for j, memory2 in enumerate(concept_memories):
                        if j not in used_indices and self.are_memories_similar(memory1, memory2):
                            similar_group.append(memory2)
                            used_indices.add(j)
                    
                    # 如果找到相似记忆，合并它们
                    if len(similar_group) > 1:
                        merged_content = await self._merge_memories(similar_group)
                        if merged_content:
                            # 保留最新的记忆ID，更新内容
                            newest_memory = max(similar_group, key=lambda m: m.last_accessed)
                            newest_memory.content = merged_content
                            newest_memory.last_accessed = time.time()
                            consolidation_count += len(similar_group) - 1
                            
                            # 收集需要移除的记忆ID
                            memories_to_remove_in_group = []
                            for mem in similar_group:
                                if mem.id != newest_memory.id:
                                    memories_to_remove_in_group.append(mem.id)
                            
                            # 统一移除
                            for mem_id in memories_to_remove_in_group:
                                self.memory_graph.remove_memory(mem_id)
        
        # 仅在有实际合并时输出日志
        if consolidation_count > 0:
            self._debug_log(f"记忆整理完成: 合并{consolidation_count}条相似记忆", "debug")
    
    async def _merge_memories(self, memories: List['Memory']) -> str:
        """智能合并多条相似记忆"""
        if len(memories) == 1:
            return memories[0].content
        
        # 按时间排序
        memories.sort(key=lambda m: m.created_at)
        
        # 提取关键信息
        contents = [m.content for m in memories]
        
        # 使用LLM进行智能合并（如果可用）
        try:
            if self.memory_config["recall_mode"] == "llm":
                provider = await self.get_llm_provider()
                if provider:
                    prompt = f"""请将以下{len(contents)}条相似记忆合并成一条更完整、更准确的记忆：

{chr(10).join(f"{i+1}. {content}" for i, content in enumerate(contents))}

要求：
1. 保留所有重要信息
2. 去除重复内容
3. 保持简洁自然
4. 不超过100字"""
                    
                    response = await provider.text_chat(
                        prompt=prompt,
                        contexts=[],
                        system_prompt="你是一个记忆整理助手，请准确合并相似记忆。"
                    )
                    
                    merged = response.completion_text.strip()
                    if merged and len(merged) > 10:
                        return merged
        except Exception as e:
            logger.warning(f"LLM合并记忆失败: {e}")
        
        # 简单合并策略
        # 提取共同关键词，合并时间信息
        words_list = [content.split() for content in contents]
        common_words = set(words_list[0])
        for words in words_list[1:]:
            common_words &= set(words)
        
        if common_words:
            key_phrase = " ".join(list(common_words)[:5])
            return f"关于{key_phrase}的多次讨论"
        
        # 默认合并
        return contents[-1]  # 返回最新的记忆
    
    def are_memories_similar(self, mem1, mem2) -> bool:
        """判断两条记忆是否相似"""
        # 简单的相似度判断
        words1 = mem1.content.split()
        words2 = mem2.content.split()
        
        # 防止除零错误
        denominator = max(len(words1), len(words2))
        if denominator == 0:
            return False
        
        common_words = set(words1) & set(words2)
        similarity = len(common_words) / denominator
        return similarity > 0.5
    
    async def get_memory_stats(self) -> dict:
        """获取记忆统计信息"""
        return {
            "concepts": len(self.memory_graph.concepts),
            "memories": len(self.memory_graph.memories),
            "connections": len(self.memory_graph.connections),
            "recall_mode": self.memory_config['recall_mode'],
            "llm_provider": self.memory_config['llm_provider'],
            "embedding_provider": self.memory_config['embedding_provider'],
            "enable_forgetting": self.memory_config['enable_forgetting'],
            "enable_consolidation": self.memory_config['enable_consolidation'],
        }

    def _parse_allow_forget_value(self, value, default: Optional[bool] = True) -> Optional[bool]:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return bool(value)
        text = str(value).strip().lower()
        if not text:
            return default
        for token in ["不允许", "不可", "不能", "禁止", "false", "no", "0", "否", "不要"]:
            if token in text:
                return False
        for token in ["允许", "可以", "true", "yes", "1", "是", "要"]:
            if token in text:
                return True
        return default

    async def resolve_allow_forget(self, content: str, theme: str, details: str, participants: str,
                                   location: str, emotion: str, tags: str, initial_allow_forget: bool) -> bool:
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
        if hasattr(self, '_llm_provider_cache'):
            return self._llm_provider_cache
            
        try:
            provider_id = self.memory_config.get('llm_provider')
            if not provider_id:
                if not hasattr(self, '_llm_provider_no_config_time') or \
                   time.time() - self._llm_provider_no_config_time > 60:  # 每分钟最多记录一次
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
                p_name = getattr(getattr(p, 'meta', None), 'name', getattr(p, 'name', None))
                if p_name and p_name.lower() == provider_id.lower():
                    self._llm_provider_cache = p
                    return p
            
            if not hasattr(self, '_llm_provider_error_time') or \
               time.time() - self._llm_provider_error_time > 60:  # 每分钟最多记录一次
                logger.error(f"无法找到配置的LLM提供商: '{provider_id}'")
                available_ids = [f"ID: {getattr(p, 'id', 'N/A')}, Name: {getattr(p, 'name', 'N/A')}" for p in all_providers]
                logger.error(f"可用提供商: {available_ids}")
                self._llm_provider_error_time = time.time()
            
            self._llm_provider_cache = None
            return None
            
        except Exception as e:
            if not hasattr(self, '_llm_provider_exception_time') or \
               time.time() - self._llm_provider_exception_time > 60:  # 每分钟最多记录一次
                logger.error(f"获取LLM提供商失败: {e}", exc_info=True)
                self._llm_provider_exception_time = time.time()
            
            self._llm_provider_cache = None
            return None

    async def get_embedding_provider(self):
        """使用配置文件指定的提供商 - 添加缓存和日志限制"""
        # 检查是否已经有缓存结果
        if hasattr(self, '_embedding_provider_cache'):
            return self._embedding_provider_cache
            
        try:
            provider_id = self.memory_config['embedding_provider']
            
            # 获取所有已注册的嵌入提供商
            if hasattr(self.context, 'get_all_embedding_providers'):
                all_providers = self.context.get_all_embedding_providers()
            else:
                # 兼容性回退
                all_providers = self.context.get_all_providers()
            
            # 精确匹配配置的提供商ID
            for provider in all_providers:
                if hasattr(provider, 'id') and provider.id == provider_id:
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
                if hasattr(provider, 'meta') and hasattr(provider.meta, 'name'):
                    if provider.meta.name == provider_id:
                        logger.debug(f"通过名称匹配使用嵌入提供商: {provider_id}")
                        self._embedding_provider_cache = provider
                        return provider
            
            # 添加日志频率限制，避免刷屏
            if not hasattr(self, '_embedding_provider_error_time') or \
               time.time() - self._embedding_provider_error_time > 60:  # 每分钟最多记录一次
                logger.error(f"无法找到配置的嵌入提供商: {provider_id}")
                self._embedding_provider_error_time = time.time()
            
            self._embedding_provider_cache = None
            return None
            
        except Exception as e:
            if not hasattr(self, '_embedding_provider_exception_time') or \
               time.time() - self._embedding_provider_exception_time > 60:  # 每分钟最多记录一次
                logger.error(f"获取嵌入提供商失败: {e}")
                self._embedding_provider_exception_time = time.time()
            
            self._embedding_provider_cache = None
            return None

    async def get_embedding(self, text: str) -> List[float]:
        """获取文本的嵌入向量 - 优先使用缓存"""
        # 递归保护：避免嵌入向量获取中的递归调用
        if getattr(self, "_embedding_in_progress", False):
            return []
        self._embedding_in_progress = True
        try:
            # 检查当前回忆模式，如果不是embedding模式，直接返回空列表，避免不必要的嵌入计算
            if self.memory_config["recall_mode"] not in ["embedding"]:
                return []
                
            # 如果启用了嵌入向量缓存，尝试从缓存获取
            if self.embedding_cache:
                # 生成一个临时ID用于缓存查询
                temp_id = f"temp_{hash(text)}"
                cached_embedding = await self.embedding_cache.get_embedding(temp_id, text)
                if cached_embedding:
                    return cached_embedding
            
            # 缓存未命中或未启用，直接计算
            provider = await self.get_embedding_provider()
            if not provider:
                logger.debug("嵌入提供商不可用")
                return []
            
            # 尝试多种嵌入方法
            methods = ['embedding', 'embeddings', 'get_embedding', 'get_embeddings']
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
            if hasattr(provider, 'text_chat'):
                try:
                    # 构建嵌入请求
                    prompt = f"请将以下文本转换为嵌入向量: {text}"
                    response = await provider.text_chat(
                        prompt=prompt,
                        contexts=[],
                        system_prompt="请将文本转换为数值向量表示"
                    )
                    # 这里假设LLM可能返回嵌入向量
                    if response and hasattr(response, 'embedding'):
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
            self._debug_log(f"开始执行 inject_memories_to_context, 消息: {event.message_str[:20]}...", "debug")

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
                impression_context = await self._inject_impressions_to_context(sender_name, group_id)
            
            # [新增] 注入话题上下文
            topic_context = ""
            if self.topic_engine:
                try:
                    sender_id = event.get_sender_id()
                    # 确保使用正确的 scope (与 main.py 保持一致)
                    topic_scope = group_id if group_id else f"private:{sender_id}"
                    
                    # 获取当前最相关的话题
                    topics = await self.topic_engine.get_topic_relevance(current_message, topic_scope, max_results=1)
                    if topics:
                        topic_id, score, info = topics[0]
                        # [修改] 降低阈值以确保话题连贯性
                        if score > 0.3: 
                            keywords = ", ".join(info.get('keywords', [])[:5])
                            heat = info.get('heat', 0)
                            topic_context = f"【当前话题】\n讨论焦点: {keywords}\n热度: {heat:.1f}"
                except Exception as e:
                    self._debug_log(f"获取话题上下文失败: {e}", "warning")

            # [新增] 注入用户画像/亲密度上下文
            profile_context = ""
            if self.user_profiling:
                try:
                    sender_id = event.get_sender_id()
                    # 自用模式：移除亲密度计算，默认为主人/最高权限
                    # 仅保留互动统计，作为数据参考
                    intimacy = await self.user_profiling.calculate_intimacy(sender_id, group_id)
                    if intimacy:
                         profile_context = f"【用户状态】\n身份: 主人\n互动: {intimacy.total_interactions}次"
                except Exception as e:
                    self._debug_log(f"获取用户画像失败: {e}", "warning")

            # 使用增强记忆召回系统获取相关记忆
            from .enhanced_memory_recall import EnhancedMemoryRecall
            
            enhanced_recall = EnhancedMemoryRecall(self)
            results = await enhanced_recall.recall_relevant_memories_for_injection(
                message=current_message,
                group_id=group_id
            )
            
            threshold = self.memory_config.get("memory_injection_threshold", 0.2)
            filtered_results = [r for r in results if hasattr(r, 'relevance_score') and r.relevance_score >= threshold]

            if filtered_results:
                updated = self._record_recall_results_accesses(filtered_results)
                if updated:
                    await self._queue_save_memory_state(group_id)
            
            # 调试日志：记录召回详情
            if results:
                scores = [f"{r.relevance_score:.2f}" for r in results]
                self._debug_log(f"记忆召回: {len(results)}条, 分数: {scores}, 阈值: {threshold}", "debug")
            
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
                memory_context = enhanced_recall.format_memories_for_llm(filtered_results, include_ids=False)
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

    async def _inject_impressions_to_context(self, sender_name: str, group_id: str) -> str:
        """注入印象信息到对话上下文"""
        try:
            if not sender_name:
                return ""

            impression_summary = self.get_person_impression_summary(group_id, sender_name)
            if impression_summary and impression_summary.get("summary"):
                score = impression_summary.get("score", 0.5)
                score_desc = self._score_to_description(score)
                return f"【人物印象】\n- {sender_name}: {impression_summary['summary']} (好感度: {score_desc})"

            return ""
            
        except Exception as e:
            self._debug_log(f"注入印象上下文失败: {e}", "warning")
            return ""

    def _extract_mentioned_names(self, message: str) -> List[str]:
        """从消息中提取提到的人名"""
        try:
            # 简单的人名提取，匹配常见的中文名模式
            # 2-4个中文字符，且不是常见词汇
            common_words = {"你好", "谢谢", "再见", "好的", "是的", "不是", "可以", "不行", "知道", "不知道", "明白", "不明白"}
            names = set()
            
            # 匹配2-4个中文字符
            chinese_names = re.findall(r'[\u4e00-\u9fff]{2,4}', message)
            
            for name in chinese_names:
                if name not in common_words:
                    names.add(name)
            
            return list(names)
            
        except Exception as e:
            self._debug_log(f"提取人名失败: {e}", "debug")
            return []

    def _extract_sender_name_from_message(self, message: str) -> Optional[str]:
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

    def _extract_person_name_from_theme(self, theme: str) -> Optional[str]:
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
            parts = theme.split(',')
            
            # 查找包含人名的部分
            for part in parts:
                part = part.strip()
                
                # 跳过明显的非人名关键词
                if part in ["印象", "评价", "看法", "感觉", "印象", "人际"]:
                    continue
                
                # 检查是否是有效的人名（2-4个中文字符）
                if len(part) >= 2 and len(part) <= 4 and re.match(r'^[\u4e00-\u9fff]+$', part):
                    return part
            
            return None
            
        except Exception as e:
            self._debug_log(f"从主题提取人名失败: {e}", "debug")
            return None

    async def query_memory(self, query: str, event: AstrMessageEvent = None) -> List[str]:
        """记忆查询接口"""
        try:
            if not query:
                return []
                
            # 使用统一的回忆接口
            return await self.recall_memories(query, event)
            
        except Exception as e:
            logger.error(f"记忆查询失败: {e}")
            return []

    async def recall_memories(self, keyword: str, event: AstrMessageEvent = None) -> List[str]:
        """回忆相关记忆，回忆接口"""
        try:
            if not self.memory_graph.memories:
                return []
                
            # 根据配置的回忆模式选择合适的方法
            recall_mode = self.memory_config["recall_mode"]
            
            if recall_mode == "llm":
                return await self._recall_llm(keyword, event)
            elif recall_mode == "embedding":
                return await self._recall_embedding(keyword)
            elif recall_mode == "activation":
                return await self._recall_by_activation(keyword)
            else:
                return await self._recall_simple(keyword)
                
        except Exception as e:
            logger.error(f"回忆记忆失败: {e}")
            return await self._recall_simple(keyword)

    async def recall_relevant_memories(self, message: str) -> List[str]:
        """基于消息内容智能召回相关记忆"""
        try:
            if not self.memory_graph.memories:
                return []
            
            # 使用增强记忆召回系统
            from .enhanced_memory_recall import EnhancedMemoryRecall
            
            enhanced_recall = EnhancedMemoryRecall(self)
            results = await enhanced_recall.recall_all_relevant_memories(
                query=message,
                max_memories=self.memory_config.get("max_injected_memories", 5)
            )
            
            # 返回记忆内容列表
            return [result.memory for result in results]
            
        except Exception as e:
            logger.error(f"增强记忆召回失败: {e}")
            return []

    def format_memories_for_context(self, memories: List[str]) -> str:
        """将记忆格式化为适合LLM理解的增强上下文"""
        try:
            if not memories:
                return ""
            
            # 使用增强格式化
            from .enhanced_memory_recall import EnhancedMemoryRecall, MemoryRecallResult
            
            # 创建增强结果用于格式化
            enhanced_results = []
            for memory in memories:
                enhanced_results.append(MemoryRecallResult(
                    memory=memory,
                    relevance_score=0.8,
                    memory_type='context_injection',
                    concept_id='',
                    metadata={'source': 'auto_injection'}
                ))
            
            enhanced_recall = EnhancedMemoryRecall(self)
            return enhanced_recall.format_memories_for_llm(enhanced_results, include_ids=False)
            
        except Exception as e:
            logger.error(f"上下文格式化失败: {e}")
            return ""
    
    def ensure_person_impression(self, group_id: str, person_name: str) -> str:
        """确保指定群组的人物印象概念存在，返回概念ID
        
        Args:
            group_id: 群组ID，用于跨群隔离
            person_name: 人物名称
            
        Returns:
            str: 概念ID
        """
        try:
            # 构建印象概念名称，格式：Imprint:GROUPID:NAME
            concept_name = f"Imprint:{group_id}:{person_name}"
            
            # 检查是否已存在
            for concept in self.memory_graph.concepts.values():
                if concept.name == concept_name:
                    return concept.id
            
            # 创建新的印象概念
            concept_id = self.memory_graph.add_concept(concept_name)
            self._debug_log(f"创建新印象概念: {concept_name}", "debug")
            
            return concept_id
            
        except Exception as e:
            self._debug_log(f"确保印象概念失败: {e}", "error")
            return ""
    
    def record_person_impression(self, group_id: str, person_name: str, summary: str,
                               score: Optional[float] = None, details: str = "") -> str:
        """记录或更新人物印象
        
        Args:
            group_id: 群组ID
            person_name: 人物名称
            summary: 印象摘要
            score: 好感度分数 (0-1)，默认使用配置的默认值
            details: 详细信息
            
        Returns:
            str: 记忆ID
        """
        try:
            # 确保印象概念存在
            concept_id = self.ensure_person_impression(group_id, person_name)
            if not concept_id:
                return ""
            
            # 使用默认分数或指定分数
            if score is None:
                score = float(self.impression_config["default_score"])
            
            # 确保score是float类型
            score = float(score)
            
            # 限制分数范围
            score = max(float(self.impression_config["min_score"]),
                       min(float(self.impression_config["max_score"]), score))
            
            # 创建印象记忆 - 确保设置正确的group_id
            memory_id = self.memory_graph.add_memory(
                content=summary,
                concept_id=concept_id,
                details=details,
                participants=person_name,
                emotion="印象",
                tags="人际",
                strength=score,
                group_id=group_id
            )
            
            self._debug_log(f"记录印象: {person_name} (分数: {score}, 群组: {group_id})", "debug")
            
            return memory_id
            
        except Exception as e:
            self._debug_log(f"记录印象失败: {e}", "error")
            return ""
    
    def get_impression_score(self, group_id: str, person_name: str) -> float:
        """获取人物的好感度分数
        
        Args:
            group_id: 群组ID
            person_name: 人物名称
            
        Returns:
            float: 好感度分数，未找到返回默认值
        """
        try:
            concept_name = f"Imprint:{group_id}:{person_name}"
            
            # 查找对应的印象概念
            concept_id = None
            for concept in self.memory_graph.concepts.values():
                if concept.name == concept_name:
                    concept_id = concept.id
                    break
            
            if not concept_id:
                return self.impression_config["default_score"]
            
            # 获取该概念下最新的记忆（即最新印象）- 使用群聊隔离过滤
            all_concept_memories = [
                m for m in self.memory_graph.memories.values()
                if m.concept_id == concept_id
            ]
            
            # 应用群聊隔离过滤
            concept_memories = self.filter_memories_by_group(all_concept_memories, group_id)
            
            if not concept_memories:
                return self.impression_config["default_score"]
            
            # 按时间排序，获取最新的印象分数
            latest_memory = max(concept_memories, key=lambda m: m.last_accessed)
            return latest_memory.strength
            
        except Exception as e:
            self._debug_log(f"获取印象分数失败: {e}", "error")
            return self.impression_config["default_score"]
    
    def adjust_impression_score(self, group_id: str, person_name: str, delta: float) -> float:
        """调整人物的好感度分数
        
        Args:
            group_id: 群组ID
            person_name: 人物名称
            delta: 调整增量（可正可负）
            
        Returns:
            float: 调整后的新分数
        """
        try:
            # 获取当前分数
            current_score = self.get_impression_score(group_id, person_name)
            
            # 计算新分数
            new_score = current_score + delta
            new_score = max(self.impression_config["min_score"],
                           min(self.impression_config["max_score"], new_score))
            
            # 获取印象概念
            concept_name = f"Imprint:{group_id}:{person_name}"
            concept_id = None
            for concept in self.memory_graph.concepts.values():
                if concept.name == concept_name:
                    concept_id = concept.id
                    break
            
            if concept_id:
                # 查找现有的印象记忆 - 使用群聊隔离过滤
                all_concept_memories = [
                    m for m in self.memory_graph.memories.values()
                    if m.concept_id == concept_id
                ]
                
                # 应用群聊隔离过滤
                concept_memories = self.filter_memories_by_group(all_concept_memories, group_id)
                
                if concept_memories:
                    # 更新最新一条印象记忆的强度
                    latest_memory = max(concept_memories, key=lambda m: m.last_accessed)
                    latest_memory.strength = new_score
                    latest_memory.last_accessed = time.time()
                    self._debug_log(f"更新现有印象记忆强度: {person_name} -> {new_score:.2f}", "debug")
                else:
                    # 如果没有现有记忆，创建新的
                    summary = f"对{person_name}的印象更新，当前好感度：{new_score:.2f}"
                    self.record_person_impression(group_id, person_name, summary, new_score)
            else:
                # 如果概念不存在，创建新的印象
                summary = f"对{person_name}的印象更新，当前好感度：{new_score:.2f}"
                self.record_person_impression(group_id, person_name, summary, new_score)
            
            self._debug_log(f"调整印象分数: {person_name} {current_score:.2f} -> {new_score:.2f}", "debug")
            
            return new_score
            
        except Exception as e:
            self._debug_log(f"调整印象分数失败: {e}", "error")
            return self.get_impression_score(group_id, person_name)
    
    def get_person_impression_summary(self, group_id: str, person_name: str) -> Dict[str, Any]:
        """获取人物印象摘要信息
        
        Args:
            group_id: 群组ID
            person_name: 人物名称
            
        Returns:
            dict: 包含印象摘要的字典
        """
        try:
            concept_name = f"Imprint:{group_id}:{person_name}"
            
            # 查找对应的印象概念
            concept_id = None
            concept = None
            for c in self.memory_graph.concepts.values():
                if c.name == concept_name:
                    concept_id = c.id
                    concept = c
                    break
            
            if not concept_id or not concept:
                return {
                    "name": person_name,
                    "score": self.impression_config["default_score"],
                    "summary": f"尚未建立对{person_name}的印象",
                    "memory_count": 0,
                    "last_updated": "无"
                }
            
            # 获取该概念下的所有印象记忆 - 使用群聊隔离过滤
            all_impression_memories = [
                m for m in self.memory_graph.memories.values()
                if m.concept_id == concept_id
            ]
            
            # 应用群聊隔离过滤
            impression_memories = self.filter_memories_by_group(all_impression_memories, group_id)
            
            if not impression_memories:
                return {
                    "name": person_name,
                    "score": self.impression_config["default_score"],
                    "summary": f"对{person_name}的印象记录为空",
                    "memory_count": 0,
                    "last_updated": "无"
                }
            
            # 获取最新印象
            latest_memory = max(impression_memories, key=lambda m: m.last_accessed)
            current_score = latest_memory.strength
            
            # 获取印象摘要
            summary = latest_memory.content
            
            # 格式化时间 - 确保last_accessed是datetime对象
            try:
                if isinstance(latest_memory.last_accessed, (int, float)):
                    # 如果是时间戳，转换为datetime
                    dt = datetime.fromtimestamp(latest_memory.last_accessed)
                    last_updated = dt.strftime("%Y-%m-%d %H:%M:%S")
                elif hasattr(latest_memory.last_accessed, 'strftime'):
                    # 如果已经有strftime方法，直接使用
                    last_updated = latest_memory.last_accessed.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    # 其他情况，使用当前时间
                    last_updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            except Exception as time_e:
                self._debug_log(f"时间格式化失败: {time_e}", "warning")
                last_updated = "时间格式化失败"
            
            return {
                "name": person_name,
                "score": current_score,
                "summary": summary,
                "memory_count": len(impression_memories),
                "last_updated": last_updated
            }
            
        except Exception as e:
            self._debug_log(f"获取印象摘要失败: {e}", "error")
            return {
                "name": person_name,
                "score": self.impression_config["default_score"],
                "summary": "获取印象信息失败",
                "memory_count": 0,
                "last_updated": "无"
            }
    
    def get_person_impression_memories(self, group_id: str, person_name: str, limit: int = 5) -> List[Dict[str, Any]]:
        """获取人物印象相关的记忆列表
        
        Args:
            group_id: 群组ID
            person_name: 人物名称
            limit: 返回的记忆数量限制
            
        Returns:
            List[dict]: 记忆列表
        """
        try:
            concept_name = f"Imprint:{group_id}:{person_name}"
            
            # 查找对应的印象概念
            concept_id = None
            for c in self.memory_graph.concepts.values():
                if c.name == concept_name:
                    concept_id = c.id
                    break
            
            if not concept_id:
                return []
            
            # 获取该概念下的所有印象记忆 - 使用群聊隔离过滤
            all_impression_memories = [
                m for m in self.memory_graph.memories.values()
                if m.concept_id == concept_id
            ]
            
            # 应用群聊隔离过滤
            impression_memories = self.filter_memories_by_group(all_impression_memories, group_id)
            
            # 按时间倒序排序
            impression_memories.sort(key=lambda m: m.last_accessed, reverse=True)
            
            # 限制数量
            impression_memories = impression_memories[:limit]
            
            # 转换为字典格式
            memories_list = []
            for memory in impression_memories:
                memories_list.append({
                    "id": memory.id,
                    "content": memory.content,
                    "details": memory.details or "",
                    "score": memory.strength,
                    "created": self._safe_format_datetime(memory.created_at),
                    "last_accessed": self._safe_format_datetime(memory.last_accessed)
                })
            
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
            elif hasattr(dt_obj, 'strftime'):
                return dt_obj.strftime("%Y-%m-%d %H:%M:%S")
            else:
                return str(dt_obj)
        except Exception as e:
            self._debug_log(f"安全格式化时间失败: {e}", "warning")
            return "未知时间"
