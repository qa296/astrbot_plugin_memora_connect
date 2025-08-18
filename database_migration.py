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
        
    async def run_smart_migration(self) -> bool:
        """智能迁移主入口 - 无需版本号"""
        try:
            if not os.path.exists(self.db_path):
                logger.info("数据库不存在，将创建新数据库")
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
            logger.error(f"智能迁移失败: {e}", exc_info=True)
            return False
    
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
                cursor.execute(f"PRAGMA table_info({table_name})")
                for col in cursor.fetchall():
                    field = FieldSchema(
                        name=col[1],
                        type=col[2],
                        not_null=bool(col[3]),
                        default_value=col[4],
                        primary_key=bool(col[5])
                    )
                    table.fields.append(field)
                
                # 分析索引
                cursor.execute(f"PRAGMA index_list({table_name})")
                for idx in cursor.fetchall():
                    table.indexes.append(idx[1])
                
                schema.tables[table_name] = table
        
        return schema
    
    def _generate_target_schema(self) -> DatabaseSchema:
        """生成目标数据库结构"""
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
        
        # 记忆表
        memories_table = TableSchema(name="memories")
        memories_table.fields = [
            FieldSchema(name="id", type="TEXT", primary_key=True),
            FieldSchema(name="concept_id", type="TEXT", not_null=True),
            FieldSchema(name="content", type="TEXT", not_null=True),
            FieldSchema(name="created_at", type="REAL", not_null=True),
            FieldSchema(name="last_accessed", type="REAL", not_null=True),
            FieldSchema(name="access_count", type="INTEGER", default_value=0),
            FieldSchema(name="strength", type="REAL", default_value=1.0)
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
    
    def _calculate_schema_diff(self, current: DatabaseSchema, 
                             target: DatabaseSchema) -> SchemaDiff:
        """智能计算结构差异"""
        diff = SchemaDiff()
        
        # 表级别差异
        current_tables = set(current.tables.keys())
        target_tables = set(target.tables.keys())
        
        diff.added_tables = list(target_tables - current_tables)
        diff.removed_tables = list(current_tables - target_tables)
        
        # 共同表的字段差异
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
        
        # 字段差异
        current_fields = {f.name: f for f in current.fields}
        target_fields = {f.name: f for f in target.fields}
        
        # 新增字段
        for name, field in target_fields.items():
            if name not in current_fields:
                diff.added_fields.append(field)
        
        # 删除字段
        for name, field in current_fields.items():
            if name not in target_fields:
                diff.removed_fields.append(name)
        
        # 修改字段
        for name in set(current_fields.keys()) & set(target_fields.keys()):
            current_field = current_fields[name]
            target_field = target_fields[name]
            
            # 检查字段定义是否相同
            if (current_field.type != target_field.type or
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
        try:
            # 创建临时数据库
            temp_db_path = self.db_path + ".smart_migration"
            if os.path.exists(temp_db_path):
                os.remove(temp_db_path)
            
            # 创建新结构
            self._create_new_structure(temp_db_path)
            
            # 智能数据迁移
            await self._smart_data_migration(self.db_path, temp_db_path, diff)
            
            # 替换数据库
            os.remove(self.db_path)
            os.rename(temp_db_path, self.db_path)
            
            return True
            
        except Exception as e:
            logger.error(f"智能迁移执行失败: {e}", exc_info=True)
            return False
    
    def _create_new_structure(self, db_path: str):
        """创建新数据库结构"""
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # 创建概念表
            cursor.execute('''
                CREATE TABLE concepts (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    last_accessed REAL NOT NULL,
                    access_count INTEGER DEFAULT 0
                )
            ''')
            
            # 创建记忆表
            cursor.execute('''
                CREATE TABLE memories (
                    id TEXT PRIMARY KEY,
                    concept_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    last_accessed REAL NOT NULL,
                    access_count INTEGER DEFAULT 0,
                    strength REAL DEFAULT 1.0,
                    FOREIGN KEY (concept_id) REFERENCES concepts (id)
                )
            ''')
            
            # 创建连接表
            cursor.execute('''
                CREATE TABLE connections (
                    id TEXT PRIMARY KEY,
                    from_concept TEXT NOT NULL,
                    to_concept TEXT NOT NULL,
                    strength REAL DEFAULT 1.0,
                    last_strengthened REAL NOT NULL,
                    FOREIGN KEY (from_concept) REFERENCES concepts (id),
                    FOREIGN KEY (to_concept) REFERENCES concepts (id)
                )
            ''')
            
            conn.commit()
    
    async def _smart_data_migration(self, source_db: str, target_db: str, 
                                  diff: SchemaDiff) -> None:
        """智能数据迁移"""
        with sqlite3.connect(source_db) as source_conn, \
             sqlite3.connect(target_db) as target_conn:
            
            source_cursor = source_conn.cursor()
            target_cursor = target_conn.cursor()
            
            # 处理现有表的数据迁移
            for table_name in diff.modified_tables.keys():
                if table_name not in diff.removed_tables:
                    await self._migrate_table_data(
                        source_cursor, target_cursor, table_name, 
                        diff.modified_tables.get(table_name, TableDiff())
                    )
            
            source_conn.commit()
            target_conn.commit()
    
    async def _migrate_table_data(self, source_cursor, target_cursor,
                                table_name: str, table_diff: TableDiff) -> None:
        """迁移单个表的数据"""
        try:
            # 获取源数据
            source_cursor.execute(f"SELECT * FROM {table_name}")
            rows = source_cursor.fetchall()
            
            if not rows:
                return
            
            # 获取源表结构
            source_cursor.execute(f"PRAGMA table_info({table_name})")
            source_columns = [str(col[1]) for col in source_cursor.fetchall()]
            
            # 获取目标表结构
            target_cursor.execute(f"PRAGMA table_info({table_name})")
            target_columns = [str(col[1]) for col in target_cursor.fetchall()]
            
            # 构建字段映射
            field_mapping = self._build_field_mapping(
                source_columns, target_columns, table_diff
            )
            
            # 迁移数据
            for row in rows:
                new_row = self._transform_row(row, field_mapping, source_columns)
                if new_row:
                    placeholders = ",".join(["?" for _ in new_row])
                    try:
                        column_names = ",".join(str(col) for col in target_columns)
                        target_cursor.execute(
                            f"INSERT INTO {table_name} ({column_names}) VALUES ({placeholders})",
                            new_row
                        )
                    except sqlite3.IntegrityError as e:
                        logger.warning(f"插入数据失败: {e}")
            
        except Exception as e:
            logger.error(f"迁移表 {table_name} 数据失败: {e}")
    
    def _build_field_mapping(self, source_columns: List[str], 
                           target_columns: List[str], 
                           table_diff: TableDiff) -> Dict[str, Any]:
        """构建字段映射关系"""
        mapping = {}
        
        # 直接映射存在的字段
        for target_col in target_columns:
            if target_col in source_columns:
                mapping[target_col] = {"type": "direct", "index": source_columns.index(target_col)}
        
        # 处理新增字段的默认值
        for added_field in table_diff.added_fields:
            if added_field.name in target_columns:
                if added_field.default_value is not None:
                    mapping[added_field.name] = {"type": "default", "value": added_field.default_value}
                else:
                    # 根据类型提供默认值
                    default_value = self._get_default_value(added_field.type)
                    mapping[added_field.name] = {"type": "default", "value": default_value}
        
        return mapping
    
    def _get_default_value(self, field_type: str) -> Any:
        """根据字段类型获取默认值"""
        type_lower = field_type.upper()
        
        if "TEXT" in type_lower or "VARCHAR" in type_lower or "CHAR" in type_lower:
            return ""
        elif "INTEGER" in type_lower or "INT" in type_lower:
            return 0
        elif "REAL" in type_lower or "FLOAT" in type_lower or "DOUBLE" in type_lower:
            return 0.0
        elif "BOOLEAN" in type_lower or "BOOL" in type_lower:
            return False
        else:
            return None
    
    def _transform_row(self, row: Tuple, field_mapping: Dict[str, Any], 
                      source_columns: List[str]) -> Optional[Tuple]:
        """转换单行数据"""
        try:
            new_row = []
            target_columns = list(field_mapping.keys())
            
            for target_col in target_columns:
                mapping = field_mapping[target_col]
                
                if mapping["type"] == "direct":
                    new_row.append(row[mapping["index"]])
                elif mapping["type"] == "default":
                    new_row.append(mapping["value"])
                else:
                    new_row.append(None)
            
            return tuple(new_row)
            
        except Exception as e:
            logger.error(f"转换数据行失败: {e}")
            return None
    
    def _rollback(self, backup_path: str):
        """从备份回滚"""
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, self.db_path)
            logger.info(f"已从备份 {backup_path} 回滚")

# 向后兼容的接口
class DatabaseMigration(SmartDatabaseMigration):
    """向后兼容的迁移类"""
    CURRENT_VERSION = "v0.2.0"
    
    async def run_migration_if_needed(self) -> bool:
        """兼容旧接口 - 完全跳过版本号检查"""
        return await self.run_smart_migration()
        
    def _get_database_version(self) -> str:
        """重写版本号获取 - 始终返回需要迁移的状态"""
        return "legacy"
        
    async def _migrate_v0_1_0_to_v0_2_0(self) -> bool:
        """重写旧版本迁移 - 直接调用智能迁移"""
        return await self.run_smart_migration()