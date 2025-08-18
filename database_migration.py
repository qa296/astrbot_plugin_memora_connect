import asyncio
import sqlite3
import json
import os
import shutil
import time
import re
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from astrbot.api import logger

class DatabaseMigration:
    """智能数据库迁移系统"""
    
    # 当前插件版本
    CURRENT_VERSION = "v0.2.0"
    
    def __init__(self, db_path: str, context=None):
        self.db_path = db_path
        self.context = context
        self.backup_dir = os.path.join(os.path.dirname(db_path), "backups")
        self.migration_log = []
        
    async def check_and_migrate(self) -> bool:
        """检查并执行数据库迁移"""
        try:
            # 检查数据库是否存在
            if not os.path.exists(self.db_path):
                logger.info("数据库不存在，创建新数据库")
                return True
                
            # 获取当前数据库版本
            current_version = self.get_database_version()
            logger.info(f"当前数据库版本: {current_version}")
            logger.info(f"插件版本: {self.CURRENT_VERSION}")
            
            if current_version == self.CURRENT_VERSION:
                logger.info("数据库版本匹配，无需迁移")
                return True
                
            # 版本不匹配，开始迁移
            logger.info("检测到数据库版本不匹配，开始智能迁移...")
            
            # 创建备份
            backup_path = await self.create_backup()
            logger.info(f"已创建数据库备份: {backup_path}")
            
            # 执行迁移
            success = await self.perform_migration(current_version, self.CURRENT_VERSION)
            
            if success:
                logger.info("数据库迁移成功完成")
                return True
            else:
                logger.error("数据库迁移失败，正在回滚...")
                await self.rollback(backup_path)
                return False
                
        except Exception as e:
            logger.error(f"数据库迁移检查失败: {e}")
            return False
    
    def get_database_version(self) -> str:
        """获取数据库版本"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 检查是否存在版本表
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='schema_version'
            """)
            
            if cursor.fetchone():
                cursor.execute("SELECT version FROM schema_version LIMIT 1")
                result = cursor.fetchone()
                conn.close()
                return result[0] if result else "v0.1.0"
            else:
                # 没有版本表，认为是v0.1.0
                conn.close()
                return "v0.1.0"
                
        except Exception as e:
            logger.error(f"获取数据库版本失败: {e}")
            return "v0.1.0"
    
    async def create_backup(self) -> str:
        """创建数据库备份"""
        try:
            os.makedirs(self.backup_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"memory_backup_{timestamp}.db"
            backup_path = os.path.join(self.backup_dir, backup_filename)
            
            shutil.copy2(self.db_path, backup_path)
            
            # 记录备份信息
            backup_info = {
                "original_path": self.db_path,
                "backup_path": backup_path,
                "timestamp": timestamp,
                "version": self.get_database_version()
            }
            
            info_path = os.path.join(self.backup_dir, f"backup_info_{timestamp}.json")
            with open(info_path, 'w', encoding='utf-8') as f:
                json.dump(backup_info, f, ensure_ascii=False, indent=2)
                
            return backup_path
            
        except Exception as e:
            logger.error(f"创建备份失败: {e}")
            raise
    
    async def perform_migration(self, from_version: str, to_version: str) -> bool:
        """执行数据库迁移"""
        try:
            logger.info(f"开始从 {from_version} 迁移到 {to_version}")
            
            # 分析当前数据库结构
            old_schema = self.analyze_current_schema()
            
            # 根据版本差异执行相应迁移
            if from_version == "v0.1.0" and to_version == "v0.2.0":
                return await self.migrate_v0_1_0_to_v0_2_0(old_schema)
            
            # 其他版本迁移逻辑...
            logger.warning(f"未找到从 {from_version} 到 {to_version} 的迁移方案")
            return False
            
        except Exception as e:
            logger.error(f"执行迁移失败: {e}")
            return False
    
    def analyze_current_schema(self) -> Dict[str, Any]:
        """分析当前数据库结构"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            schema = {
                "tables": {},
                "version": self.get_database_version()
            }
            
            # 获取所有表
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            
            for (table_name,) in tables:
                if table_name.startswith("sqlite_"):
                    continue
                    
                # 获取表结构
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = cursor.fetchall()
                
                schema["tables"][table_name] = {
                    "columns": [
                        {
                            "name": col[1],
                            "type": col[2],
                            "notnull": col[3],
                            "default": col[4],
                            "pk": col[5]
                        }
                        for col in columns
                    ]
                }
            
            conn.close()
            return schema
            
        except Exception as e:
            logger.error(f"分析数据库结构失败: {e}")
            return {}
    
    async def migrate_v0_1_0_to_v0_2_0(self, old_schema: Dict[str, Any]) -> bool:
        """从v0.1.0迁移到v0.2.0"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 创建版本表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version TEXT PRIMARY KEY,
                    migrated_at REAL NOT NULL
                )
            """)
            
            # 检查是否需要添加新字段
            tables_to_update = ["concepts", "memories", "connections"]
            
            for table in tables_to_update:
                if table in old_schema["tables"]:
                    # 使用LLM分析字段差异并转换
                    await self.smart_field_conversion(cursor, table, old_schema)
            
            # 更新版本号
            cursor.execute(
                "INSERT OR REPLACE INTO schema_version (version, migrated_at) VALUES (?, ?)",
                (self.CURRENT_VERSION, time.time())
            )
            
            conn.commit()
            conn.close()
            
            logger.info("v0.1.0 -> v0.2.0 迁移完成")
            return True
            
        except Exception as e:
            logger.error(f"v0.1.0 -> v0.2.0 迁移失败: {e}")
            return False
    
    async def smart_field_conversion(self, cursor, table_name: str, old_schema: Dict[str, Any]) -> bool:
        """智能字段转换"""
        try:
            old_columns = {col["name"]: col for col in old_schema["tables"][table_name]["columns"]}
            
            # 定义新版本的字段结构
            new_columns = self.get_new_schema_columns(table_name)
            
            # 找出需要转换的字段
            fields_to_convert = []
            for new_col in new_columns:
                if new_col["name"] not in old_columns:
                    # 新字段，需要添加
                    fields_to_convert.append({
                        "action": "add",
                        "field": new_col
                    })
                elif old_columns[new_col["name"]]["type"] != new_col["type"]:
                    # 类型不匹配，需要转换
                    fields_to_convert.append({
                        "action": "convert",
                        "old_field": old_columns[new_col["name"]],
                        "new_field": new_col
                    })
            
            # 执行转换
            for conversion in fields_to_convert:
                if conversion["action"] == "add":
                    await self.add_field(cursor, table_name, conversion["field"])
                elif conversion["action"] == "convert":
                    await self.convert_field_type(cursor, table_name, conversion)
            
            return True
            
        except Exception as e:
            logger.error(f"智能字段转换失败: {e}")
            return False
    
    def get_new_schema_columns(self, table_name: str) -> List[Dict[str, Any]]:
        """获取新版本的字段结构"""
        schemas = {
            "concepts": [
                {"name": "id", "type": "TEXT", "pk": 1},
                {"name": "name", "type": "TEXT", "notnull": 1},
                {"name": "created_at", "type": "REAL", "notnull": 1},
                {"name": "last_accessed", "type": "REAL", "notnull": 1},
                {"name": "access_count", "type": "INTEGER", "default": 0},
                {"name": "metadata", "type": "TEXT", "default": "{}"}  # 新增字段
            ],
            "memories": [
                {"name": "id", "type": "TEXT", "pk": 1},
                {"name": "concept_id", "type": "TEXT", "notnull": 1},
                {"name": "content", "type": "TEXT", "notnull": 1},
                {"name": "created_at", "type": "REAL", "notnull": 1},
                {"name": "last_accessed", "type": "REAL", "notnull": 1},
                {"name": "access_count", "type": "INTEGER", "default": 0},
                {"name": "strength", "type": "REAL", "default": 1.0},
                {"name": "tags", "type": "TEXT", "default": "[]"}  # 新增字段
            ],
            "connections": [
                {"name": "id", "type": "TEXT", "pk": 1},
                {"name": "from_concept", "type": "TEXT", "notnull": 1},
                {"name": "to_concept", "type": "TEXT", "notnull": 1},
                {"name": "strength", "type": "REAL", "default": 1.0},
                {"name": "last_strengthened", "type": "REAL", "notnull": 1},
                {"name": "relationship_type", "type": "TEXT", "default": "related"}  # 新增字段
            ]
        }
        
        return schemas.get(table_name, [])
    
    async def add_field(self, cursor, table_name: str, field: Dict[str, Any]) -> bool:
        """添加新字段"""
        try:
            sql = f"ALTER TABLE {table_name} ADD COLUMN {field['name']} {field['type']}"
            if "default" in field:
                sql += f" DEFAULT {field['default']}"
            cursor.execute(sql)
            logger.info(f"添加字段 {table_name}.{field['name']} 成功")
            return True
            
        except Exception as e:
            logger.error(f"添加字段失败: {e}")
            return False
    
    async def convert_field_type(self, cursor, table_name: str, conversion: Dict[str, Any]) -> bool:
        """转换字段类型"""
        try:
            old_field = conversion["old_field"]
            new_field = conversion["new_field"]
            
            # 创建临时表
            temp_table = f"{table_name}_temp"
            cursor.execute(f"CREATE TABLE {temp_table} AS SELECT * FROM {table_name}")
            
            # 转换数据
            if old_field["type"] == "TEXT" and new_field["type"] == "REAL":
                # 文本转数字
                cursor.execute(f"""
                    UPDATE {temp_table} 
                    SET {old_field['name']} = CAST({old_field['name']} AS REAL)
                    WHERE {old_field['name']} IS NOT NULL
                """)
            
            # 更多转换逻辑...
            
            # 替换原表
            cursor.execute(f"DROP TABLE {table_name}")
            cursor.execute(f"ALTER TABLE {temp_table} RENAME TO {table_name}")
            
            logger.info(f"转换字段类型 {table_name}.{old_field['name']} 成功")
            return True
            
        except Exception as e:
            logger.error(f"转换字段类型失败: {e}")
            return False
    
    async def rollback(self, backup_path: str) -> bool:
        """回滚到备份"""
        try:
            if os.path.exists(backup_path):
                shutil.copy2(backup_path, self.db_path)
                logger.info(f"已回滚到备份: {backup_path}")
                return True
            else:
                logger.error("备份文件不存在，无法回滚")
                return False
                
        except Exception as e:
            logger.error(f"回滚失败: {e}")
            return False
    
    def get_migration_status(self) -> Dict[str, Any]:
        """获取迁移状态"""
        try:
            current_version = self.get_database_version()
            backup_files = []
            
            if os.path.exists(self.backup_dir):
                backup_files = [f for f in os.listdir(self.backup_dir) if f.startswith("memory_backup_")]
            
            return {
                "current_version": current_version,
                "target_version": self.CURRENT_VERSION,
                "needs_migration": current_version != self.CURRENT_VERSION,
                "backup_count": len(backup_files),
                "backup_dir": self.backup_dir
            }
            
        except Exception as e:
            logger.error(f"获取迁移状态失败: {e}")
            return {}

# 全局迁移实例
migration_instance = None

def get_migration_instance(db_path: str, context=None):
    """获取迁移实例"""
    global migration_instance
    if migration_instance is None:
        migration_instance = DatabaseMigration(db_path, context)
    return migration_instance