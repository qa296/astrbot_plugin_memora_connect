import asyncio
import sqlite3
import json
import os
import shutil
import time
import re
from typing import Dict, List, Any
from datetime import datetime
from astrbot.api import logger

class DatabaseMigration:
    """智能数据库迁移系统"""
    
    CURRENT_VERSION = "v0.2.0"
    
    def __init__(self, db_path: str, context=None):
        self.db_path = db_path
        self.context = context
        self.backup_dir = os.path.join(os.path.dirname(db_path), "backups")
        
    async def run_migration_if_needed(self):
        """检查并执行数据库迁移"""
        try:
            if not os.path.exists(self.db_path):
                logger.info("数据库不存在，将创建新数据库。")
                return True

            current_version = self._get_database_version()
            if current_version == self.CURRENT_VERSION:
                logger.info("数据库版本匹配，无需迁移。")
                return True

            logger.info(f"检测到数据库版本不匹配 (当前: {current_version}, 目标: {self.CURRENT_VERSION})，启动智能迁移...")
            
            backup_path = self._create_backup()
            logger.info(f"数据库备份已创建于: {backup_path}")
            
            success = await self._perform_migration(current_version, self.CURRENT_VERSION)
            
            if success:
                logger.info("数据库迁移成功完成。")
                return True
            else:
                logger.error("数据库迁移失败，正在从备份中恢复...")
                self._rollback(backup_path)
                logger.error("数据库已回滚，插件功能可能受限。")
                return False
                
        except Exception as e:
            logger.error(f"数据库迁移检查失败: {e}", exc_info=True)
            return False

    def _get_database_version(self) -> str:
        """获取数据库版本"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'")
                if cursor.fetchone():
                    cursor.execute("SELECT version FROM schema_version ORDER BY migrated_at DESC LIMIT 1")
                    result = cursor.fetchone()
                    return result if result else "v0.1.0"
            return "v0.1.0"
        except Exception:
            # 表可能不存在或结构不同，这是需要迁移的信号
            return "v0.1.0"

    def _create_backup(self) -> str:
        """创建数据库备份"""
        os.makedirs(self.backup_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"memory_backup_{self._get_database_version()}_{timestamp}.db"
        backup_path = os.path.join(self.backup_dir, backup_filename)
        shutil.copy2(self.db_path, backup_path)
        return backup_path

    def _rollback(self, backup_path: str):
        """从备份回滚"""
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, self.db_path)

    async def _perform_migration(self, from_version: str, to_version: str) -> bool:
        """执行数据库迁移"""
        if from_version == "v0.1.0" and to_version == "v0.2.0":
            return await self._migrate_v0_1_0_to_v0_2_0()
        logger.warning(f"未找到从 {from_version} 到 {to_version} 的迁移路径。")
        return False

    async def _migrate_v0_1_0_to_v0_2_0(self) -> bool:
        """从v0.1.0迁移到v0.2.0的具体逻辑"""
        try:
            old_schema = self._analyze_db_schema(self.db_path)
            
            # 创建一个临时数据库用于构建新结构
            temp_db_path = self.db_path + ".tmp"
            if os.path.exists(temp_db_path):
                os.remove(temp_db_path)

            self._create_new_schema(temp_db_path)
            
            # 智能数据迁移
            await self._transfer_and_transform_data(self.db_path, temp_db_path, old_schema)

            # 替换旧数据库
            os.remove(self.db_path)
            os.rename(temp_db_path, self.db_path)
            
            # 更新版本号
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO schema_version (version, migrated_at) VALUES (?, ?)",
                    (self.CURRENT_VERSION, time.time())
                )
                conn.commit()

            return True
        except Exception as e:
            logger.error(f"v0.1.0 -> v0.2.0 迁移失败: {e}", exc_info=True)
            return False

    def _analyze_db_schema(self, db_path) -> Dict[str, Any]:
        """分析数据库结构"""
        schema = {"tables": {}}
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            for (table_name,) in cursor.fetchall():
                if table_name.startswith("sqlite_"): continue
                cursor.execute(f"PRAGMA table_info({table_name})")
                schema["tables"][table_name] = [row for row in cursor.fetchall()]
        return schema

    def _create_new_schema(self, db_path):
        """创建v0.2.0的新数据库结构"""
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            # 创建版本表
            cursor.execute("""
                CREATE TABLE schema_version (
                    version TEXT PRIMARY KEY,
                    migrated_at REAL NOT NULL
                )
            """)
            # 创建新表结构 (与main.py中的定义保持一致)
            cursor.execute('''
                CREATE TABLE concepts (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at REAL NOT NULL,
                    last_accessed REAL NOT NULL, access_count INTEGER DEFAULT 0
                )
            ''')
            cursor.execute('''
                CREATE TABLE memories (
                    id TEXT PRIMARY KEY, concept_id TEXT NOT NULL, content TEXT NOT NULL,
                    created_at REAL NOT NULL, last_accessed REAL NOT NULL,
                    access_count INTEGER DEFAULT 0, strength REAL DEFAULT 1.0,
                    FOREIGN KEY (concept_id) REFERENCES concepts (id)
                )
            ''')
            cursor.execute('''
                CREATE TABLE connections (
                    id TEXT PRIMARY KEY, from_concept TEXT NOT NULL, to_concept TEXT NOT NULL,
                    strength REAL DEFAULT 1.0, last_strengthened REAL NOT NULL,
                    FOREIGN KEY (from_concept) REFERENCES concepts (id),
                    FOREIGN KEY (to_concept) REFERENCES concepts (id)
                )
            ''')
            conn.commit()

    async def _transfer_and_transform_data(self, old_db, new_db, old_schema):
        """迁移并转换数据"""
        with sqlite3.connect(old_db) as old_conn, sqlite3.connect(new_db) as new_conn:
            old_cursor = old_conn.cursor()
            new_cursor = new_conn.cursor()

            for table_name, old_columns in old_schema['tables'].items():
                if table_name == 'schema_version': continue
                
                logger.info(f"正在迁移表: {table_name}")
                old_cursor.execute(f"SELECT * FROM {table_name}")
                
                # 假设新旧表结构字段一致，直接插入
                # 在实际场景中，这里会调用LLM进行字段映射
                placeholders = ', '.join(['?'] * len(old_columns))
                insert_sql = f"INSERT INTO {table_name} ({', '.join(old_columns)}) VALUES ({placeholders})"
                
                for row in old_cursor.fetchall():
                    try:
                        new_cursor.execute(insert_sql, row)
                    except sqlite3.IntegrityError as e:
                        logger.warning(f"插入数据失败 (可能已存在): {e} - Row: {row}")

            new_conn.commit()

    async def _get_llm_provider(self):
        """获取LLM服务提供商 (辅助函数)"""
        # 实际实现中会从context获取
        return self.context.get_using_provider() if self.context else None

    async def _get_field_mapping_with_llm(self, old_columns: List[str], new_columns: List[str]) -> Dict[str, str]:
        """使用LLM获取字段映射"""
        provider = await self._get_llm_provider()
        if not provider:
            logger.warning("LLM提供商不可用，使用默认映射。")
            return {col: col for col in old_columns if col in new_columns}

        prompt = f"""
        你是一个数据库迁移助手。请分析以下两个版本的表结构，并提供一个从旧字段到新字段的映射。
        旧表字段: {', '.join(old_columns)}
        新表字段: {', '.join(new_columns)}
        
        请以JSON格式返回映射关系，例如：{{"old_field_1": "new_field_1", "old_field_2": "new_field_2"}}。
        如果某个旧字段在新表中没有对应字段，请不要包含在结果中。
        """
        try:
            response = await provider.text_chat(prompt=prompt, system_prompt="你是一个数据库专家。")
            mapping_str = response.completion_text
            # 从LLM返回的文本中提取JSON
            json_match = re.search(r'\{.*\}', mapping_str, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
        except Exception as e:
            logger.error(f"使用LLM获取字段映射失败: {e}")
        
        # LLM失败后回退
        return {col: col for col in old_columns if col in new_columns}