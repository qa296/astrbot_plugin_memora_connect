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
            logger.error(f"智能迁移失败: {e}", exc_info=True)
            # 如果发生异常，也尝试回滚
            if 'backup_path' in locals() and os.path.exists(backup_path):
                self._rollback(backup_path)
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
        
        # 记忆表 - 增强版，包含更多详细信息
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
        temp_db_path = self.db_path + ".smart_migration"
        try:
            if os.path.exists(temp_db_path):
                os.remove(temp_db_path)
            
            self._create_new_structure(temp_db_path)
            await self._smart_data_migration(self.db_path, temp_db_path, diff)
            
            # 替换数据库
            os.remove(self.db_path)
            os.rename(temp_db_path, self.db_path)
            
            return True
            
        except Exception as e:
            logger.error(f"智能迁移执行失败: {e}", exc_info=True)
            if os.path.exists(temp_db_path):
                os.remove(temp_db_path)
            return False
    
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
                            sql += f" DEFAULT '{field.default_value}'"
                        else:
                            sql += f" DEFAULT {field.default_value}"
                    fields_sql.append(sql)
                
                create_table_sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(fields_sql)})"
                cursor.execute(create_table_sql)
            
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
    
    async def _migrate_table_data(self, source_cursor, target_cursor,
                                table_name: str, table_diff: TableDiff) -> None:
        """迁移单个表的数据"""
        try:
            source_cursor.execute(f"SELECT * FROM {table_name}")
            rows = source_cursor.fetchall()
            
            if not rows:
                return
            
            source_cursor.execute(f"PRAGMA table_info('{table_name}')")
            source_columns = [str(col) for col in source_cursor.fetchall()]
            
            target_cursor.execute(f"PRAGMA table_info('{table_name}')")
            target_columns_info = {str(col): col for col in target_cursor.fetchall()}
            target_columns = list(target_columns_info.keys())
            
            # 构建字段映射
            field_mapping, final_target_columns = self._build_field_mapping(
                source_columns, target_columns, table_diff
            )
            
            # 迁移数据
            for row in rows:
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
                    except sqlite3.IntegrityError as e:
                        logger.warning(f"插入数据失败 (表: {table_name}): {e}")
            
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
        