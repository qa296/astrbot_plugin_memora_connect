import asyncio
import sqlite3
import json
import os
import shutil
import time
import re
from typing import Dict, List, Any, Optional, Tuple, Callable
from datetime import datetime
from dataclasses import dataclass, field
from astrbot.api import logger

try:
    from .resource_management import resource_manager
except ImportError:
    resource_manager = None

@dataclass
class FieldSchema:
    """字段结构定义"""
    name: str
    type: str
    not_null: bool = False
    default_value: Any = None
    primary_key: bool = False
    unique: bool = False
    foreign_key: Optional[str] = None

@dataclass
class TableSchema:
    """表结构定义"""
    name: str
    fields: List[FieldSchema] = field(default_factory=list)
    indexes: List[str] = field(default_factory=list)
    create_sql: str = ""

@dataclass
class DatabaseSchema:
    """数据库结构定义"""
    tables: Dict[str, TableSchema] = field(default_factory=dict)

@dataclass
class FieldChange:
    """字段变化"""
    field_name: str
    old_type: str
    new_type: str
    old_constraints: Dict[str, Any]
    new_constraints: Dict[str, Any]

@dataclass
class TableDiff:
    """表差异"""
    added_fields: List[FieldSchema] = field(default_factory=list)
    removed_fields: List[str] = field(default_factory=list)
    modified_fields: List[FieldChange] = field(default_factory=list)
    added_indexes: List[str] = field(default_factory=list)
    removed_indexes: List[str] = field(default_factory=list)
    
    def has_changes(self) -> bool:
        """检查表是否有变化"""
        return bool(
            self.added_fields or
            self.removed_fields or
            self.modified_fields or
            self.added_indexes or
            self.removed_indexes
        )

@dataclass
class SchemaDiff:
    """结构差异"""
    added_tables: List[str] = field(default_factory=list)
    removed_tables: List[str] = field(default_factory=list)
    modified_tables: Dict[str, TableDiff] = field(default_factory=dict)
    
    def has_changes(self) -> bool:
        """检查是否有变化"""
        return bool(
            self.added_tables or 
            self.removed_tables or 
            self.modified_tables
        )

class SmartDatabaseMigration:
    """智能数据库迁移系统 - 完全独立版本"""
    
    def __init__(self, db_path: str, context=None):
        self.db_path = db_path
        self.context = context
        self.backup_dir = os.path.join(os.path.dirname(db_path), "backups")
        self.max_retries = 3
        self.retry_delay = 1.0
        self.fallback_mode = False
        self.last_error = None
        
    async def run_smart_migration(self) -> bool:
        """智能迁移主入口 - 无需版本号
        将重迁移的重型同步逻辑放到后台线程，避免阻塞事件循环。
        """
        return await asyncio.to_thread(self.run_smart_migration_sync)
    
    def run_smart_migration_sync(self) -> bool:
        """同步版本的智能迁移主入口（用于在线程中执行）"""
        return self._run_migration_with_retry_sync(self._run_smart_migration_internal_sync)
    
    async def _run_migration_with_retry(self, migration_func) -> bool:
        """带重试机制的迁移执行（保留异步接口以兼容旧代码）"""
        for attempt in range(self.max_retries):
            try:
                logger.info(f"开始数据库迁移 (尝试 {attempt + 1}/{self.max_retries})")
                result = await migration_func()
                if result:
                    logger.info("数据库迁移成功")
                    return True
                else:
                    logger.warning(f"数据库迁移失败 (尝试 {attempt + 1}/{self.max_retries})")
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(self.retry_delay)
                    continue
            except Exception as e:
                self.last_error = str(e)
                logger.error(f"数据库迁移异常 (尝试 {attempt + 1}/{self.max_retries}): {e}", exc_info=True)
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)
                continue
        
        # 所有重试都失败，进入回退模式
        logger.error("所有迁移尝试都失败，进入回退模式")
        return await self._enter_fallback_mode()
    
    def _run_migration_with_retry_sync(self, migration_func: Callable[[], bool]) -> bool:
        """带重试机制的迁移执行（同步版，用于线程中）"""
        for attempt in range(self.max_retries):
            try:
                logger.info(f"开始数据库迁移 (尝试 {attempt + 1}/{self.max_retries})")
                result = migration_func()
                if result:
                    logger.info("数据库迁移成功")
                    return True
                else:
                    logger.warning(f"数据库迁移失败 (尝试 {attempt + 1}/{self.max_retries})")
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay)
                    continue
            except Exception as e:
                self.last_error = str(e)
                logger.error(f"数据库迁移异常 (尝试 {attempt + 1}/{self.max_retries}): {e}", exc_info=True)
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                continue
        
        # 所有重试都失败，进入回退模式
        logger.error("所有迁移尝试都失败，进入回退模式")
        return self._enter_fallback_mode_sync()
    
    async def _run_smart_migration_internal(self) -> bool:
        """智能迁移内部实现（异步版，保留兼容）"""
        try:
            if not os.path.exists(self.db_path):
                logger.info("数据库不存在，将创建新数据库")
                # 创建新数据库时，直接使用新结构，无需迁移
                self._create_new_structure(self.db_path)
                return True
                
            # 1. 分析现有数据库结构
            current_schema = self._analyze_current_schema()
            
            # 2. 生成目标数据库结构
            target_schema = self._generate_target_schema()
            
            # 3. 智能差异检测
            schema_diff = self._calculate_schema_diff(current_schema, target_schema)
            
            if not schema_diff.has_changes():
                logger.info("数据库结构已是最新，无需迁移")
                return True
                
            # 4. 创建备份
            backup_path = self._create_smart_backup()
            logger.info(f"已创建备份: {backup_path}")
            
            # 5. 执行智能迁移
            success = await self._execute_smart_migration(schema_diff)
            
            if success:
                logger.info("智能迁移成功完成")
                return True
            else:
                logger.error("迁移失败，正在回滚...")
                self._rollback(backup_path)
                return False
                
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"智能迁移失败: {e}", exc_info=True)
            # 如果发生异常，也尝试回滚
            if 'backup_path' in locals() and os.path.exists(backup_path):
                self._rollback(backup_path)
            return False
    
    def _run_smart_migration_internal_sync(self) -> bool:
        """智能迁移内部实现（同步版）"""
        try:
            if not os.path.exists(self.db_path):
                logger.info("数据库不存在，将创建新数据库")
                # 创建新数据库时，直接使用新结构，无需迁移
                self._create_new_structure(self.db_path)
                return True
                
            # 1. 分析现有数据库结构
            current_schema = self._analyze_current_schema()
            
            # 2. 生成目标数据库结构
            target_schema = self._generate_target_schema()
            
            # 3. 智能差异检测
            schema_diff = self._calculate_schema_diff(current_schema, target_schema)
            
            if not schema_diff.has_changes():
                logger.info("数据库结构已是最新，无需迁移")
                return True
                
            # 4. 创建备份
            backup_path = self._create_smart_backup()
            logger.info(f"已创建备份: {backup_path}")
            
            # 5. 执行智能迁移
            success = self._execute_smart_migration_sync(schema_diff)
            
            if success:
                logger.info("智能迁移成功完成")
                return True
            else:
                logger.error("迁移失败，正在回滚...")
                self._rollback(backup_path)
                return False
                
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"智能迁移失败: {e}", exc_info=True)
            # 如果发生异常，也尝试回滚
            if 'backup_path' in locals() and os.path.exists(backup_path):
                self._rollback(backup_path)
            return False
    
    async def run_embedding_cache_migration(self) -> bool:
        """专门用于嵌入向量缓存数据库的迁移（异步接口，内部在线程中执行）"""
        return await asyncio.to_thread(self.run_embedding_cache_migration_sync)
    
    def run_embedding_cache_migration_sync(self) -> bool:
        """嵌入向量缓存数据库迁移（同步版）"""
        return self._run_migration_with_retry_sync(self._run_embedding_cache_migration_internal_sync)
    
    async def _run_embedding_cache_migration_internal(self) -> bool:
        """嵌入向量缓存迁移内部实现（异步版，保留兼容）"""
        try:
            if not os.path.exists(self.db_path):
                logger.info("嵌入向量缓存数据库不存在，将创建新数据库")
                # 创建新数据库时，直接使用新结构，无需迁移
                self._create_new_structure(self.db_path)
                return True
            
            logger.info(f"开始嵌入向量缓存数据库迁移: {self.db_path}")
            
            # 1. 分析现有数据库结构
            current_schema = self._analyze_current_schema()
            
            # 2. 生成目标数据库结构
            target_schema = self._generate_embedding_cache_schema()
            
            # 3. 智能差异检测
            schema_diff = self._calculate_schema_diff(current_schema, target_schema)
            
            if not schema_diff.has_changes():
                logger.info("嵌入向量缓存数据库结构已是最新，无需迁移")
                return True
            
            # 4. 创建备份
            backup_path = self._create_smart_backup()
            logger.info(f"已创建备份: {backup_path}")
            
            # 5. 执行智能迁移
            success = await self._execute_smart_migration(schema_diff)
            
            if success:
                logger.info("嵌入向量缓存数据库迁移成功完成")
                return True
            else:
                logger.error("嵌入向量缓存数据库迁移失败，正在回滚...")
                self._rollback(backup_path)
                return False
                
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"嵌入向量缓存数据库迁移失败: {e}", exc_info=True)
            # 如果发生异常，也尝试回滚
            if 'backup_path' in locals() and os.path.exists(backup_path):
                self._rollback(backup_path)
            return False
    
    def _run_embedding_cache_migration_internal_sync(self) -> bool:
        """嵌入向量缓存迁移内部实现（同步版）"""
        try:
            if not os.path.exists(self.db_path):
                logger.info("嵌入向量缓存数据库不存在，将创建新数据库")
                # 创建新数据库时，直接使用新结构，无需迁移
                self._create_new_structure(self.db_path)
                return True
            
            logger.info(f"开始嵌入向量缓存数据库迁移: {self.db_path}")
            
            # 1. 分析现有数据库结构
            current_schema = self._analyze_current_schema()
            
            # 2. 生成目标数据库结构
            target_schema = self._generate_embedding_cache_schema()
            
            # 3. 智能差异检测
            schema_diff = self._calculate_schema_diff(current_schema, target_schema)
            
            if not schema_diff.has_changes():
                logger.info("嵌入向量缓存数据库结构已是最新，无需迁移")
                return True
            
            # 4. 创建备份
            backup_path = self._create_smart_backup()
            logger.info(f"已创建备份: {backup_path}")
            
            # 5. 执行智能迁移
            success = self._execute_smart_migration_sync(schema_diff)
            
            if success:
                logger.info("嵌入向量缓存数据库迁移成功完成")
                return True
            else:
                logger.error("嵌入向量缓存数据库迁移失败，正在回滚...")
                self._rollback(backup_path)
                return False
                
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"嵌入向量缓存数据库迁移失败: {e}", exc_info=True)
            # 如果发生异常，也尝试回滚
            if 'backup_path' in locals() and os.path.exists(backup_path):
                self._rollback(backup_path)
            return False
    
    async def _enter_fallback_mode(self) -> bool:
        """进入回退模式"""
        self.fallback_mode = True
        logger.warning("进入回退模式：尝试创建最小可用数据库结构")
        
        try:
            # 尝试创建最小可用结构
            await self._create_minimal_structure()
            logger.info("回退模式：成功创建最小可用数据库结构")
            return True
        except Exception as e:
            logger.error(f"回退模式失败：无法创建最小数据库结构: {e}")
            return False
    
    def _enter_fallback_mode_sync(self) -> bool:
        """进入回退模式（同步版）"""
        self.fallback_mode = True
        logger.warning("进入回退模式：尝试创建最小可用数据库结构")
        try:
            self._create_minimal_structure_sync()
            logger.info("回退模式：成功创建最小可用数据库结构")
            return True
        except Exception as e:
            logger.error(f"回退模式失败：无法创建最小数据库结构: {e}")
            return False
    
    async def _create_minimal_structure(self) -> None:
        """创建最小可用数据库结构（异步接口，内部为同步实现）"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 判断是否为嵌入向量缓存数据库
            if "_embeddings.db" in self.db_path:
                # 创建最小嵌入向量缓存结构
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS memory_embeddings (
                        memory_id TEXT PRIMARY KEY,
                        content TEXT NOT NULL,
                        concept_id TEXT NOT NULL,
                        embedding BLOB NOT NULL,
                        vector_dimension INTEGER NOT NULL,
                        group_id TEXT DEFAULT "",
                        created_at REAL NOT NULL,
                        last_updated REAL NOT NULL
                    )
                ''')
                
                # 创建基本索引
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_group_embeddings ON memory_embeddings(group_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_concept_embeddings ON memory_embeddings(concept_id)")
                
            else:
                # 创建最小主记忆数据库结构
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS concepts (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        last_accessed REAL NOT NULL,
                        access_count INTEGER DEFAULT 0
                    )
                ''')
                
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS memories (
                        id TEXT PRIMARY KEY,
                        concept_id TEXT NOT NULL,
                        content TEXT NOT NULL,
                        group_id TEXT DEFAULT "",
                        created_at REAL NOT NULL,
                        last_accessed REAL NOT NULL,
                        access_count INTEGER DEFAULT 0,
                        strength REAL DEFAULT 1.0
                    )
                ''')
                
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS connections (
                        id TEXT PRIMARY KEY,
                        from_concept TEXT NOT NULL,
                        to_concept TEXT NOT NULL,
                        strength REAL DEFAULT 1.0,
                        last_strengthened REAL NOT NULL
                    )
                ''')
                
                # 创建基本索引
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_group_id ON memories(group_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_concept_group ON memories(concept_id, group_id)")
            
            conn.commit()
    
    def _create_minimal_structure_sync(self) -> None:
        """创建最小可用数据库结构（同步版）"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 判断是否为嵌入向量缓存数据库
            if "_embeddings.db" in self.db_path:
                # 创建最小嵌入向量缓存结构
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS memory_embeddings (
                        memory_id TEXT PRIMARY KEY,
                        content TEXT NOT NULL,
                        concept_id TEXT NOT NULL,
                        embedding BLOB NOT NULL,
                        vector_dimension INTEGER NOT NULL,
                        group_id TEXT DEFAULT "",
                        created_at REAL NOT NULL,
                        last_updated REAL NOT NULL
                    )
                ''')
                
                # 创建基本索引
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_group_embeddings ON memory_embeddings(group_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_concept_embeddings ON memory_embeddings(concept_id)")
                
            else:
                # 创建最小主记忆数据库结构
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS concepts (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        last_accessed REAL NOT NULL,
                        access_count INTEGER DEFAULT 0
                    )
                ''')
                
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS memories (
                        id TEXT PRIMARY KEY,
                        concept_id TEXT NOT NULL,
                        content TEXT NOT NULL,
                        group_id TEXT DEFAULT "",
                        created_at REAL NOT NULL,
                        last_accessed REAL NOT NULL,
                        access_count INTEGER DEFAULT 0,
                        strength REAL DEFAULT 1.0
                    )
                ''')
                
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS connections (
                        id TEXT PRIMARY KEY,
                        from_concept TEXT NOT NULL,
                        to_concept TEXT NOT NULL,
                        strength REAL DEFAULT 1.0,
                        last_strengthened REAL NOT NULL
                    )
                ''')
                
                # 创建基本索引
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_group_id ON memories(group_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_concept_group ON memories(concept_id, group_id)")
            
            conn.commit()
    
    def get_migration_status(self) -> Dict[str, Any]:
        """获取迁移状态信息"""
        return {
            "fallback_mode": self.fallback_mode,
            "last_error": self.last_error,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
            "database_exists": os.path.exists(self.db_path),
            "backup_dir_exists": os.path.exists(self.backup_dir)
        }
    
    def reset_migration_state(self) -> None:
        """重置迁移状态"""
        self.fallback_mode = False
        self.last_error = None
        logger.info("迁移状态已重置")

    def _analyze_current_schema(self) -> DatabaseSchema:
        """分析当前数据库结构"""
        schema = DatabaseSchema()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 获取所有表
            cursor.execute("""
                SELECT name, sql FROM sqlite_master
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
            """)
            
            for table_name, create_sql in cursor.fetchall():
                table = TableSchema(name=table_name, create_sql=create_sql)
                
                # 分析字段
                cursor.execute(f"PRAGMA table_info('{table_name}')")
                for col in cursor.fetchall():
                    # col结构: (cid, name, type, notnull, dflt_value, pk)
                    field = FieldSchema(
                        name=str(col[1]),
                        type=str(col[2]),
                        not_null=bool(col[3]),
                        default_value=col[4],
                        primary_key=bool(col[5])
                    )
                    table.fields.append(field)
                
                # 分析索引
                cursor.execute(f"PRAGMA index_list('{table_name}')")
                for idx in cursor.fetchall():
                    # idx结构: (seq, name, unique, origin, partial)
                    table.indexes.append(str(idx[1]))
                
                schema.tables[table_name] = table
        
        return schema
    
    def _generate_target_schema(self) -> DatabaseSchema:
        """生成目标数据库结构"""
        schema = DatabaseSchema()
        
        # 判断是否为嵌入向量缓存数据库
        if "_embeddings.db" in self.db_path:
            return self._generate_embedding_cache_schema()
        else:
            return self._generate_main_memory_schema()
    
    def _generate_main_memory_schema(self) -> DatabaseSchema:
        """生成主记忆数据库结构"""
        schema = DatabaseSchema()
        
        # 概念表
        concepts_table = TableSchema(name="concepts")
        concepts_table.fields = [
            FieldSchema(name="id", type="TEXT", primary_key=True),
            FieldSchema(name="name", type="TEXT", not_null=True),
            FieldSchema(name="created_at", type="REAL", not_null=True),
            FieldSchema(name="last_accessed", type="REAL", not_null=True),
            FieldSchema(name="access_count", type="INTEGER", default_value=0)
        ]
        schema.tables["concepts"] = concepts_table
        
        # 记忆表 - 增强版，包含更多详细信息和群聊隔离支持
        memories_table = TableSchema(name="memories")
        memories_table.fields = [
            FieldSchema(name="id", type="TEXT", primary_key=True),
            FieldSchema(name="concept_id", type="TEXT", not_null=True),
            FieldSchema(name="content", type="TEXT", not_null=True),
            FieldSchema(name="details", type="TEXT", default_value=""),
            FieldSchema(name="participants", type="TEXT", default_value=""),
            FieldSchema(name="location", type="TEXT", default_value=""),
            FieldSchema(name="emotion", type="TEXT", default_value=""),
            FieldSchema(name="tags", type="TEXT", default_value=""),
            FieldSchema(name="group_id", type="TEXT", default_value=""),
            FieldSchema(name="created_at", type="REAL", not_null=True),
            FieldSchema(name="last_accessed", type="REAL", not_null=True),
            FieldSchema(name="access_count", type="INTEGER", default_value=0),
            FieldSchema(name="strength", type="REAL", default_value=1.0),
            FieldSchema(name="allow_forget", type="INTEGER", default_value=1)
        ]
        # 添加群聊隔离索引
        memories_table.indexes = [
            "idx_memories_group_id",
            "idx_memories_concept_group",
            "idx_memories_created_group"
        ]
        schema.tables["memories"] = memories_table
        
        # 连接表
        connections_table = TableSchema(name="connections")
        connections_table.fields = [
            FieldSchema(name="id", type="TEXT", primary_key=True),
            FieldSchema(name="from_concept", type="TEXT", not_null=True),
            FieldSchema(name="to_concept", type="TEXT", not_null=True),
            FieldSchema(name="strength", type="REAL", default_value=1.0),
            FieldSchema(name="last_strengthened", type="REAL", not_null=True)
        ]
        schema.tables["connections"] = connections_table
        
        return schema
    
    def _generate_embedding_cache_schema(self) -> DatabaseSchema:
        """生成嵌入向量缓存数据库结构"""
        schema = DatabaseSchema()
        
        # 嵌入向量表 - 支持群聊隔离
        memory_embeddings_table = TableSchema(name="memory_embeddings")
        memory_embeddings_table.fields = [
            FieldSchema(name="memory_id", type="TEXT", primary_key=True),
            FieldSchema(name="content", type="TEXT", not_null=True),
            FieldSchema(name="concept_id", type="TEXT", not_null=True),
            FieldSchema(name="embedding", type="BLOB", not_null=True),
            FieldSchema(name="vector_dimension", type="INTEGER", not_null=True),
            FieldSchema(name="group_id", type="TEXT", default_value=""),
            FieldSchema(name="created_at", type="REAL", not_null=True),
            FieldSchema(name="last_updated", type="REAL", not_null=True),
            FieldSchema(name="embedding_version", type="TEXT", default_value="v1.0"),
            FieldSchema(name="metadata", type="TEXT", default_value="{}")
        ]
        # 添加群聊隔离索引
        memory_embeddings_table.indexes = [
            "idx_concept_embeddings",
            "idx_group_embeddings",
            "idx_concept_group_embeddings",
            "idx_updated_embeddings"
        ]
        schema.tables["memory_embeddings"] = memory_embeddings_table
        
        # 预计算任务表
        precompute_tasks_table = TableSchema(name="precompute_tasks")
        precompute_tasks_table.fields = [
            FieldSchema(name="task_id", type="TEXT", primary_key=True),
            FieldSchema(name="memory_ids", type="TEXT", not_null=True),
            FieldSchema(name="priority", type="INTEGER", default_value=1),
            FieldSchema(name="created_at", type="REAL", not_null=True),
            FieldSchema(name="status", type="TEXT", default_value="pending"),
            FieldSchema(name="progress", type="INTEGER", default_value=0),
            FieldSchema(name="error_message", type="TEXT", default_value=""),
            FieldSchema(name="completed_at", type="REAL", default_value=0)
        ]
        precompute_tasks_table.indexes = [
            "idx_task_status"
        ]
        schema.tables["precompute_tasks"] = precompute_tasks_table
        
        return schema
    
    def _calculate_schema_diff(self, current: DatabaseSchema, 
                             target: DatabaseSchema) -> SchemaDiff:
        """智能计算结构差异"""
        diff = SchemaDiff()
        
        current_tables = set(current.tables.keys())
        target_tables = set(target.tables.keys())
        
        diff.added_tables = list(target_tables - current_tables)
        diff.removed_tables = list(current_tables - target_tables)
        
        for table_name in current_tables & target_tables:
            current_table = current.tables[table_name]
            target_table = target.tables[table_name]
            
            table_diff = self._calculate_table_diff(current_table, target_table)
            if table_diff.has_changes():
                diff.modified_tables[table_name] = table_diff
        
        return diff
    
    def _calculate_table_diff(self, current: TableSchema, 
                            target: TableSchema) -> TableDiff:
        """计算单个表的差异"""
        diff = TableDiff()
        
        current_fields = {f.name: f for f in current.fields}
        target_fields = {f.name: f for f in target.fields}
        
        diff.added_fields = [field for name, field in target_fields.items() if name not in current_fields]
        diff.removed_fields = [name for name in current_fields if name not in target_fields]
        
        for name in set(current_fields.keys()) & set(target_fields.keys()):
            current_field = current_fields[name]
            target_field = target_fields[name]
            
            if (current_field.type.upper() != target_field.type.upper() or
                current_field.not_null != target_field.not_null or
                current_field.primary_key != target_field.primary_key):
                
                change = FieldChange(
                    field_name=name,
                    old_type=current_field.type,
                    new_type=target_field.type,
                    old_constraints={
                        "not_null": current_field.not_null,
                        "primary_key": current_field.primary_key,
                        "default": current_field.default_value
                    },
                    new_constraints={
                        "not_null": target_field.not_null,
                        "primary_key": target_field.primary_key,
                        "default": target_field.default_value
                    }
                )
                diff.modified_fields.append(change)
        
        return diff
    
    def _create_smart_backup(self) -> str:
        """创建智能备份"""
        os.makedirs(self.backup_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"smart_backup_{timestamp}.db"
        backup_path = os.path.join(self.backup_dir, backup_filename)
        shutil.copy2(self.db_path, backup_path)
        return backup_path
    
    async def _execute_smart_migration(self, diff: SchemaDiff) -> bool:
        """执行智能迁移"""
        temp_db_path = self._get_temp_db_path()

        try:
            # 创建临时数据库并迁移数据
            self._create_new_structure(temp_db_path)
            await self._smart_data_migration(self.db_path, temp_db_path, diff)

            # 使用更安全的替换策略：先备份原文件，然后重命名临时文件
            # 这样即使有连接锁定，新文件也能正确创建
            backup_path = self._create_smart_backup()

            # Windows下使用VACUUM INTO策略避免文件锁定问题
            # 直接使用重命名方式，配合更长的重试时间和Windows特定处理
            success = await self._safe_replace_database_async(temp_db_path, backup_path)

            if success:
                return True
            else:
                # 如果替换失败，尝试使用备份恢复
                logger.warning("数据库替换失败，尝试使用备份恢复...")
                return await self._rollback_from_backup_async(backup_path)

        except Exception as e:
            logger.error(f"智能迁移执行失败: {e}", exc_info=True)
            await self._safe_remove_file_async(temp_db_path)
            return False

    async def _safe_replace_database_async(self, temp_db_path: str, backup_path: str) -> bool:
        """安全替换数据库文件（异步版，支持Windows）"""
        import platform

        # Windows需要更长的等待时间
        max_retries = 10 if platform.system() == 'Windows' else 5
        delay = 1.0 if platform.system() == 'Windows' else 0.3

        for attempt in range(max_retries):
            try:
                # 强制关闭所有连接
                if resource_manager:
                    resource_manager.close_db_connections(self.db_path)

                # 尝试删除原文件（Windows下可能失败）
                if os.path.exists(self.db_path):
                    try:
                        os.remove(self.db_path)
                    except PermissionError:
                        # Windows下，如果文件被锁定，尝试重命名为待删除文件
                        if attempt < max_retries - 1:
                            pending_delete = f"{self.db_path}.pending_delete.{attempt}"
                            try:
                                # 先删除旧的待删除文件
                                if os.path.exists(pending_delete):
                                    os.remove(pending_delete)
                                # 将当前文件重命名为待删除
                                os.rename(self.db_path, pending_delete)
                            except Exception:
                                pass  # 忽略错误，继续重试
                        else:
                            raise  # 最后一次尝试仍然失败，抛出异常

                # 重命名临时文件为原文件名
                os.rename(temp_db_path, self.db_path)

                logger.info(f"数据库替换成功 (尝试 {attempt + 1}/{max_retries})")
                return True

            except PermissionError as e:
                logger.debug(f"替换数据库失败 (尝试 {attempt + 1}/{max_retries}): 文件被占用")
                if attempt == max_retries - 1:
                    logger.error(f"数据库替换失败，已达到最大重试次数: {e}")
                    return False
                await asyncio.sleep(delay)

            except Exception as e:
                logger.error(f"数据库替换失败: {e}", exc_info=True)
                return False

        return False

    async def _rollback_from_backup_async(self, backup_path: str) -> bool:
        """从备份回滚数据库（异步版）"""
        import platform

        if not os.path.exists(backup_path):
            logger.error("备份文件不存在，无法回滚")
            return False

        max_retries = 10 if platform.system() == 'Windows' else 5
        delay = 1.0 if platform.system() == 'Windows' else 0.3

        for attempt in range(max_retries):
            try:
                # 强制关闭所有连接
                if resource_manager:
                    resource_manager.close_db_connections(self.db_path)

                # 删除当前损坏的数据库
                if os.path.exists(self.db_path):
                    try:
                        os.remove(self.db_path)
                    except PermissionError:
                        # Windows下处理锁定文件
                        if attempt < max_retries - 1:
                            pending_delete = f"{self.db_path}.pending_delete.{attempt}"
                            try:
                                if os.path.exists(pending_delete):
                                    os.remove(pending_delete)
                                os.rename(self.db_path, pending_delete)
                            except Exception:
                                pass
                        else:
                            raise

                # 从备份恢复
                shutil.copy2(backup_path, self.db_path)
                logger.info(f"已从备份回滚成功 (尝试 {attempt + 1}/{max_retries})")
                return True

            except PermissionError:
                logger.debug(f"回滚失败 (尝试 {attempt + 1}/{max_retries}): 文件被占用")
                if attempt == max_retries - 1:
                    logger.error("从备份回滚失败")
                    return False
                await asyncio.sleep(delay)

            except Exception as e:
                logger.error(f"从备份回滚失败: {e}", exc_info=True)
                return False

        return False

    def _execute_smart_migration_sync(self, diff: SchemaDiff) -> bool:
        """执行智能迁移（同步版）"""
        temp_db_path = self._get_temp_db_path()

        try:
            # 创建临时数据库并迁移数据
            self._create_new_structure(temp_db_path)
            self._smart_data_migration_sync(self.db_path, temp_db_path, diff)

            # 使用更安全的替换策略：先备份原文件，然后重命名临时文件
            # 这样即使有连接锁定，新文件也能正确创建
            backup_path = self._create_smart_backup()

            # Windows下使用VACUUM INTO策略避免文件锁定问题
            # 直接使用重命名方式，配合更长的重试时间和Windows特定处理
            success = self._safe_replace_database_sync(temp_db_path, backup_path)

            if success:
                return True
            else:
                # 如果替换失败，尝试使用备份恢复
                logger.warning("数据库替换失败，尝试使用备份恢复...")
                return self._rollback_from_backup_sync(backup_path)

        except Exception as e:
            logger.error(f"智能迁移执行失败: {e}", exc_info=True)
            self._safe_remove_file(temp_db_path)
            return False

    def _safe_replace_database_sync(self, temp_db_path: str, backup_path: str) -> bool:
        """安全替换数据库文件（同步版，支持Windows）"""
        import platform

        # Windows需要更长的等待时间
        max_retries = 10 if platform.system() == 'Windows' else 5
        delay = 1.0 if platform.system() == 'Windows' else 0.3

        for attempt in range(max_retries):
            try:
                # 强制关闭所有连接
                if resource_manager:
                    resource_manager.close_db_connections(self.db_path)

                # 尝试删除原文件（Windows下可能失败）
                if os.path.exists(self.db_path):
                    try:
                        os.remove(self.db_path)
                    except PermissionError:
                        # Windows下，如果文件被锁定，尝试重命名为待删除文件
                        if attempt < max_retries - 1:
                            pending_delete = f"{self.db_path}.pending_delete.{attempt}"
                            try:
                                # 先删除旧的待删除文件
                                if os.path.exists(pending_delete):
                                    os.remove(pending_delete)
                                # 将当前文件重命名为待删除
                                os.rename(self.db_path, pending_delete)
                            except Exception:
                                pass  # 忽略错误，继续重试
                        else:
                            raise  # 最后一次尝试仍然失败，抛出异常

                # 重命名临时文件为原文件名
                os.rename(temp_db_path, self.db_path)

                logger.info(f"数据库替换成功 (尝试 {attempt + 1}/{max_retries})")
                return True

            except PermissionError as e:
                logger.debug(f"替换数据库失败 (尝试 {attempt + 1}/{max_retries}): 文件被占用")
                if attempt == max_retries - 1:
                    logger.error(f"数据库替换失败，已达到最大重试次数: {e}")
                    return False
                time.sleep(delay)

            except Exception as e:
                logger.error(f"数据库替换失败: {e}", exc_info=True)
                return False

        return False

    def _rollback_from_backup_sync(self, backup_path: str) -> bool:
        """从备份回滚数据库（同步版）"""
        import platform

        if not os.path.exists(backup_path):
            logger.error("备份文件不存在，无法回滚")
            return False

        max_retries = 10 if platform.system() == 'Windows' else 5
        delay = 1.0 if platform.system() == 'Windows' else 0.3

        for attempt in range(max_retries):
            try:
                # 强制关闭所有连接
                if resource_manager:
                    resource_manager.close_db_connections(self.db_path)

                # 删除当前损坏的数据库
                if os.path.exists(self.db_path):
                    try:
                        os.remove(self.db_path)
                    except PermissionError:
                        # Windows下处理锁定文件
                        if attempt < max_retries - 1:
                            pending_delete = f"{self.db_path}.pending_delete.{attempt}"
                            try:
                                if os.path.exists(pending_delete):
                                    os.remove(pending_delete)
                                os.rename(self.db_path, pending_delete)
                            except Exception:
                                pass
                        else:
                            raise

                # 从备份恢复
                shutil.copy2(backup_path, self.db_path)
                logger.info(f"已从备份回滚成功 (尝试 {attempt + 1}/{max_retries})")
                return True

            except PermissionError:
                logger.debug(f"回滚失败 (尝试 {attempt + 1}/{max_retries}): 文件被占用")
                if attempt == max_retries - 1:
                    logger.error("从备份回滚失败")
                    return False
                time.sleep(delay)

            except Exception as e:
                logger.error(f"从备份回滚失败: {e}", exc_info=True)
                return False

        return False

    def _get_temp_db_path(self) -> str:
        base_path = self.db_path + ".smart_migration"
        if not os.path.exists(base_path):
            return base_path
        self._safe_remove_file(base_path)
        if not os.path.exists(base_path):
            return base_path
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{base_path}.{timestamp}"

    def _safe_remove_file(self, file_path: str, retries: int = 5, delay: float = 0.5) -> None:
        if not file_path or not os.path.exists(file_path):
            return
        for attempt in range(retries):
            try:
                if resource_manager:
                    resource_manager.close_db_connections(file_path)
                os.remove(file_path)
                return
            except PermissionError:
                if attempt == retries - 1:
                    try:
                        pending_path = f"{file_path}.pending_delete"
                        if os.path.exists(pending_path):
                            os.remove(pending_path)
                        os.rename(file_path, pending_path)
                        return
                    except Exception:
                        return
                time.sleep(delay)

    async def _safe_remove_file_async(self, file_path: str, retries: int = 5, delay: float = 0.5) -> None:
        if not file_path or not os.path.exists(file_path):
            return
        for attempt in range(retries):
            try:
                if resource_manager:
                    resource_manager.close_db_connections(file_path)
                os.remove(file_path)
                return
            except PermissionError:
                if attempt == retries - 1:
                    try:
                        pending_path = f"{file_path}.pending_delete"
                        if os.path.exists(pending_path):
                            os.remove(pending_path)
                        os.rename(file_path, pending_path)
                        return
                    except Exception:
                        return
                await asyncio.sleep(delay)
    
    def _create_new_structure(self, db_path: str):
        """创建新数据库结构"""
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            target_schema = self._generate_target_schema()
            for table_name, table_schema in target_schema.tables.items():
                fields_sql = []
                for field in table_schema.fields:
                    sql = f'"{field.name}" {field.type}'
                    if field.primary_key:
                        sql += " PRIMARY KEY"
                    if field.not_null:
                        sql += " NOT NULL"
                    if field.default_value is not None:
                        if isinstance(field.default_value, str):
                            # 正确处理字符串默认值，避免重复引号
                            if field.default_value.startswith("'") and field.default_value.endswith("'"):
                                sql += f" DEFAULT {field.default_value}"
                            else:
                                sql += f" DEFAULT '{field.default_value}'"
                        else:
                            sql += f" DEFAULT {field.default_value}"
                    fields_sql.append(sql)
                
                create_table_sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(fields_sql)})"
                cursor.execute(create_table_sql)
                
                # 创建索引
                for index_name in table_schema.indexes:
                    if index_name == "idx_memories_group_id":
                        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_group_id ON memories(group_id)")
                    elif index_name == "idx_memories_concept_group":
                        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_concept_group ON memories(concept_id, group_id)")
                    elif index_name == "idx_memories_created_group":
                        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_created_group ON memories(created_at, group_id)")
                    elif index_name == "idx_concept_embeddings":
                        cursor.execute("CREATE INDEX IF NOT EXISTS idx_concept_embeddings ON memory_embeddings(concept_id)")
                    elif index_name == "idx_group_embeddings":
                        cursor.execute("CREATE INDEX IF NOT EXISTS idx_group_embeddings ON memory_embeddings(group_id)")
                    elif index_name == "idx_concept_group_embeddings":
                        cursor.execute("CREATE INDEX IF NOT EXISTS idx_concept_group_embeddings ON memory_embeddings(concept_id, group_id)")
                    elif index_name == "idx_updated_embeddings":
                        cursor.execute("CREATE INDEX IF NOT EXISTS idx_updated_embeddings ON memory_embeddings(last_updated)")
                    elif index_name == "idx_task_status":
                        cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_status ON precompute_tasks(status, priority)")
            
            conn.commit()
    
    async def _smart_data_migration(self, source_db: str, target_db: str, 
                                  diff: SchemaDiff) -> None:
        """智能数据迁移"""
        with sqlite3.connect(source_db) as source_conn, \
             sqlite3.connect(target_db) as target_conn:
            
            source_cursor = source_conn.cursor()
            target_cursor = target_conn.cursor()
            
            # 迁移未改变和已修改的表
            current_schema = self._analyze_current_schema()
            target_schema = self._generate_target_schema()
            
            for table_name in current_schema.tables:
                if table_name in target_schema.tables:
                    table_diff = diff.modified_tables.get(table_name, TableDiff())
                    await self._migrate_table_data(
                        source_cursor, target_cursor, table_name, table_diff
                    )
            
            target_conn.commit()
    
    def _smart_data_migration_sync(self, source_db: str, target_db: str, 
                                  diff: SchemaDiff) -> None:
        """智能数据迁移（同步版）"""
        with sqlite3.connect(source_db) as source_conn, \
             sqlite3.connect(target_db) as target_conn:
            
            source_cursor = source_conn.cursor()
            target_cursor = target_conn.cursor()
            
            # 迁移未改变和已修改的表
            current_schema = self._analyze_current_schema()
            target_schema = self._generate_target_schema()
            
            for table_name in current_schema.tables:
                if table_name in target_schema.tables:
                    table_diff = diff.modified_tables.get(table_name, TableDiff())
                    self._migrate_table_data_sync(
                        source_cursor, target_cursor, table_name, table_diff
                    )
            
            target_conn.commit()
    
    async def _migrate_table_data(self, source_cursor, target_cursor,
                                table_name: str, table_diff: TableDiff) -> None:
        """迁移单个表的数据"""
        try:
            logger.info(f"开始迁移表 {table_name} 的数据")
            
            source_cursor.execute(f"SELECT * FROM {table_name}")
            rows = source_cursor.fetchall()
            
            if not rows:
                logger.info(f"表 {table_name} 没有数据，跳过迁移")
                return
            
            logger.info(f"表 {table_name} 有 {len(rows)} 行数据需要迁移")
            
            source_cursor.execute(f"PRAGMA table_info('{table_name}')")
            source_columns = [col[1] for col in source_cursor.fetchall()]  # col[1] 是列名
            logger.info(f"表 {table_name} 源列: {source_columns}")
            
            target_cursor.execute(f"PRAGMA table_info('{table_name}')")
            target_columns_info = {col[1]: col for col in target_cursor.fetchall()}
            target_columns = list(target_columns_info.keys())
            logger.info(f"表 {table_name} 目标列: {target_columns}")
            
            # 构建字段映射
            field_mapping, final_target_columns = self._build_field_mapping(
                source_columns, target_columns, table_diff
            )
            logger.info(f"表 {table_name} 字段映射: {field_mapping}")
            logger.info(f"表 {table_name} 最终目标列: {final_target_columns}")
            
            # 迁移数据
            migrated_count = 0
            for i, row in enumerate(rows):
                new_row_dict = self._transform_row(row, field_mapping, source_columns)
                if new_row_dict:
                    # 确保插入顺序与目标列一致
                    ordered_row = [new_row_dict.get(col) for col in final_target_columns]
                    placeholders = ",".join(["?" for _ in final_target_columns])
                    column_names = ",".join(f'"{col}"' for col in final_target_columns)
                    
                    try:
                        target_cursor.execute(
                            f"INSERT INTO {table_name} ({column_names}) VALUES ({placeholders})",
                            tuple(ordered_row)
                        )
                        migrated_count += 1
                    except sqlite3.IntegrityError as e:
                        logger.warning(f"插入数据失败 (表: {table_name}, 行 {i}): {e}")
                    except Exception as e:
                        logger.error(f"插入数据异常 (表: {table_name}, 行 {i}): {e}")
                        
            logger.info(f"表 {table_name} 数据迁移完成，成功迁移 {migrated_count}/{len(rows)} 行")
            
        except Exception as e:
            logger.error(f"迁移表 {table_name} 数据失败: {e}", exc_info=True)

    def _migrate_table_data_sync(self, source_cursor, target_cursor,
                                table_name: str, table_diff: TableDiff) -> None:
        """迁移单个表的数据（同步版）"""
        try:
            logger.info(f"开始迁移表 {table_name} 的数据")
            
            source_cursor.execute(f"SELECT * FROM {table_name}")
            rows = source_cursor.fetchall()
            
            if not rows:
                logger.info(f"表 {table_name} 没有数据，跳过迁移")
                return
            
            logger.info(f"表 {table_name} 有 {len(rows)} 行数据需要迁移")
            
            source_cursor.execute(f"PRAGMA table_info('{table_name}')")
            source_columns = [col[1] for col in source_cursor.fetchall()]  # col[1] 是列名
            logger.info(f"表 {table_name} 源列: {source_columns}")
            
            target_cursor.execute(f"PRAGMA table_info('{table_name}')")
            target_columns_info = {col[1]: col for col in target_cursor.fetchall()}
            target_columns = list(target_columns_info.keys())
            logger.info(f"表 {table_name} 目标列: {target_columns}")
            
            # 构建字段映射
            field_mapping, final_target_columns = self._build_field_mapping(
                source_columns, target_columns, table_diff
            )
            logger.info(f"表 {table_name} 字段映射: {field_mapping}")
            logger.info(f"表 {table_name} 最终目标列: {final_target_columns}")
            
            # 迁移数据
            migrated_count = 0
            for i, row in enumerate(rows):
                new_row_dict = self._transform_row(row, field_mapping, source_columns)
                if new_row_dict:
                    # 确保插入顺序与目标列一致
                    ordered_row = [new_row_dict.get(col) for col in final_target_columns]
                    placeholders = ",".join(["?" for _ in final_target_columns])
                    column_names = ",".join(f'"{col}"' for col in final_target_columns)
                    
                    try:
                        target_cursor.execute(
                            f"INSERT INTO {table_name} ({column_names}) VALUES ({placeholders})",
                            tuple(ordered_row)
                        )
                        migrated_count += 1
                    except sqlite3.IntegrityError as e:
                        logger.warning(f"插入数据失败 (表: {table_name}, 行 {i}): {e}")
                    except Exception as e:
                        logger.error(f"插入数据异常 (表: {table_name}, 行 {i}): {e}")
                        
            logger.info(f"表 {table_name} 数据迁移完成，成功迁移 {migrated_count}/{len(rows)} 行")
            
        except Exception as e:
            logger.error(f"迁移表 {table_name} 数据失败: {e}", exc_info=True)
    
    def _build_field_mapping(self, source_columns: List[str], 
                           target_columns: List[str], 
                           table_diff: TableDiff) -> Tuple[Dict[str, Any], List[str]]:
        """构建字段映射关系"""
        mapping = {}
        final_target_columns = []

        for target_col in target_columns:
            if target_col in source_columns:
                mapping[target_col] = {"type": "direct", "source": target_col}
                final_target_columns.append(target_col)
        
        for added_field in table_diff.added_fields:
            if added_field.name in target_columns:
                default_value = added_field.default_value if added_field.default_value is not None else self._get_default_value(added_field.type)
                mapping[added_field.name] = {"type": "default", "value": default_value}
                final_target_columns.append(added_field.name)
        
        return mapping, final_target_columns
    
    def _get_default_value(self, field_type: str) -> Any:
        """根据字段类型获取默认值"""
        type_lower = field_type.upper()
        if "TEXT" in type_lower or "CHAR" in type_lower: return ""
        if "INT" in type_lower: return 0
        if "REAL" in type_lower or "FLOAT" in type_lower: return 0.0
        if "BOOL" in type_lower: return False
        return None
    
    def _transform_row(self, row: Tuple, field_mapping: Dict[str, Any], 
                      source_columns: List[str]) -> Optional[Dict[str, Any]]:
        """转换单行数据"""
        try:
            source_row_dict = dict(zip(source_columns, row))
            new_row_dict = {}
            
            for target_col, mapping_info in field_mapping.items():
                if mapping_info["type"] == "direct":
                    new_row_dict[target_col] = source_row_dict.get(mapping_info["source"])
                elif mapping_info["type"] == "default":
                    new_row_dict[target_col] = mapping_info["value"]
            
            return new_row_dict
            
        except Exception as e:
            logger.error(f"转换数据行失败: {e}", exc_info=True)
            return None
    
    def _rollback(self, backup_path: str):
        """从备份回滚"""
        if os.path.exists(backup_path):
            try:
                shutil.copy2(backup_path, self.db_path)
                logger.info(f"已从备份 {backup_path} 回滚")
            except Exception as e:
                logger.error(f"回滚失败: {e}")

# 向后兼容的接口
class DatabaseMigration(SmartDatabaseMigration):
    """
    向后兼容的迁移类。
    这个类现在完全依赖于 SmartDatabaseMigration 的迁移逻辑，
    旧的版本号检查和迁移方法已被重写，以确保所有路径都使用新的、更可靠的系统。
    """
    CURRENT_VERSION = "v0.2.0"  # 保持版本号用于识别，但不再用于迁移逻辑
    
    async def run_migration_if_needed(self) -> bool:
        """
        兼容旧的启动接口。
        现在直接调用智能迁移，完全跳过版本号检查。
        """
        logger.info("调用兼容接口 run_migration_if_needed()，将执行迁移。")
        return await self.run_smart_migration() 
        
