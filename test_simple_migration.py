#!/usr/bin/env python3
"""
简化的嵌入向量缓存数据库迁移测试脚本
不依赖AstrBot模块，只测试核心数据库逻辑
"""
import asyncio
import os
import sqlite3
import json
import time
from typing import Dict, List, Any
from dataclasses import dataclass

@dataclass
class DatabaseSchema:
    """数据库结构定义"""
    tables: Dict[str, List[Dict[str, Any]]]
    indexes: Dict[str, List[Dict[str, Any]]]

class SimpleDatabaseMigration:
    """简化的数据库迁移类，用于测试"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def _generate_embedding_cache_schema(self) -> DatabaseSchema:
        """生成嵌入向量缓存数据库的目标结构"""
        schema = DatabaseSchema(
            tables={},
            indexes={}
        )
        
        # memory_embeddings 表结构
        schema.tables["memory_embeddings"] = [
            {"name": "memory_id", "type": "TEXT", "primary_key": True},
            {"name": "content", "type": "TEXT", "not_null": True},
            {"name": "concept_id", "type": "TEXT", "not_null": True},
            {"name": "embedding", "type": "BLOB", "not_null": True},
            {"name": "vector_dimension", "type": "INTEGER", "not_null": True},
            {"name": "group_id", "type": "TEXT", "default": "''"},
            {"name": "created_at", "type": "REAL", "not_null": True},
            {"name": "last_updated", "type": "REAL", "not_null": True},
            {"name": "embedding_version", "type": "TEXT", "default": "'v1.0'"},
            {"name": "metadata", "type": "TEXT", "default": "'{}'"}
        ]
        
        # 索引定义
        schema.indexes["memory_embeddings"] = [
            {"name": "idx_memory_embeddings_memory_id", "columns": ["memory_id"], "unique": True},
            {"name": "idx_memory_embeddings_concept_id", "columns": ["concept_id"]},
            {"name": "idx_memory_embeddings_group_id", "columns": ["group_id"]},
            {"name": "idx_memory_embeddings_concept_group", "columns": ["concept_id", "group_id"]},
            {"name": "idx_memory_embeddings_created_at", "columns": ["created_at"]},
            {"name": "idx_memory_embeddings_last_updated", "columns": ["last_updated"]}
        ]
        
        return schema
    
    def _get_current_schema(self, conn: sqlite3.Connection) -> DatabaseSchema:
        """获取当前数据库结构"""
        schema = DatabaseSchema(tables={}, indexes={})
        cursor = conn.cursor()
        
        # 获取表结构
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        
        for table in tables:
            table_name = table[0]
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            
            schema.tables[table_name] = []
            for col in columns:
                schema.tables[table_name].append({
                    "name": col[1],
                    "type": col[2],
                    "not_null": col[3] == 1,
                    "default": col[4],
                    "primary_key": col[5] == 1
                })
        
        # 获取索引信息
        cursor.execute("SELECT name, tbl_name, sql FROM sqlite_master WHERE type='index'")
        indexes = cursor.fetchall()
        
        for idx in indexes:
            index_name, table_name, sql = idx
            if table_name not in schema.indexes:
                schema.indexes[table_name] = []
            
            # 从SQL中提取列名
            if sql:
                columns = []
                if "CREATE INDEX" in sql.upper():
                    # 简单解析列名
                    if "ON" in sql.upper():
                        parts = sql.split("ON")[1].split("(")[1].split(")")[0]
                        columns = [col.strip() for col in parts.split(",")]
                
                schema.indexes[table_name].append({
                    "name": index_name,
                    "columns": columns,
                    "sql": sql
                })
        
        return schema
    
    def _table_needs_migration(self, current_table: List[Dict], target_table: List[Dict]) -> bool:
        """检查表是否需要迁移"""
        current_columns = {col["name"]: col for col in current_table}
        target_columns = {col["name"]: col for col in target_table}
        
        # 检查是否有缺失的列
        for col_name, target_col in target_columns.items():
            if col_name not in current_columns:
                print(f"  📌 发现缺失列: {col_name}")
                return True
            
            current_col = current_columns[col_name]
            
            # 检查列类型
            if current_col["type"].upper() != target_col["type"].upper():
                print(f"  📌 列类型不匹配: {col_name} ({current_col['type']} != {target_col['type']})")
                return True
            
            # 检查NOT NULL约束
            if current_col.get("not_null", False) != target_col.get("not_null", False):
                print(f"  📌 NOT NULL约束不匹配: {col_name}")
                return True
        
        return False
    
    def _add_missing_columns(self, conn: sqlite3.Connection, table_name: str, 
                           current_columns: List[Dict], target_columns: List[Dict]):
        """添加缺失的列"""
        cursor = conn.cursor()
        current_col_names = {col["name"] for col in current_columns}
        
        for target_col in target_columns:
            if target_col["name"] not in current_col_names:
                col_def = f"ALTER TABLE {table_name} ADD COLUMN {target_col['name']} {target_col['type']}"
                
                # 添加默认值
                if "default" in target_col and target_col["default"]:
                    col_def += f" DEFAULT {target_col['default']}"
                
                # 添加NOT NULL约束
                if target_col.get("not_null", False):
                    col_def += " NOT NULL"
                
                print(f"  🔧 执行: {col_def}")
                cursor.execute(col_def)
        
        conn.commit()
    
    def _create_missing_indexes(self, conn: sqlite3.Connection, table_name: str,
                              current_indexes: List[Dict], target_indexes: List[Dict]):
        """创建缺失的索引"""
        cursor = conn.cursor()
        current_index_names = {idx["name"] for idx in current_indexes}
        
        for target_idx in target_indexes:
            if target_idx["name"] not in current_index_names:
                columns = ", ".join(target_idx["columns"])
                unique = "UNIQUE" if target_idx.get("unique", False) else ""
                
                sql = f"CREATE {unique} INDEX {target_idx['name']} ON {table_name} ({columns})"
                print(f"  🔧 执行: {sql}")
                cursor.execute(sql)
        
        conn.commit()
    
    async def run_embedding_cache_migration(self) -> bool:
        """运行嵌入向量缓存数据库迁移"""
        print(f"🚀 开始迁移嵌入向量缓存数据库: {self.db_path}")
        
        try:
            # 确保数据库目录存在
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            
            # 连接数据库
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 获取目标结构
            target_schema = self._generate_embedding_cache_schema()
            print(f"📋 目标结构包含 {len(target_schema.tables)} 个表")
            
            # 获取当前结构
            current_schema = self._get_current_schema(conn)
            print(f"📋 当前结构包含 {len(current_schema.tables)} 个表")
            
            migration_performed = False
            
            # 检查并迁移memory_embeddings表
            if "memory_embeddings" in current_schema.tables:
                print("🔍 检查memory_embeddings表结构...")
                
                current_table = current_schema.tables["memory_embeddings"]
                target_table = target_schema.tables["memory_embeddings"]
                
                if self._table_needs_migration(current_table, target_table):
                    print("📝 memory_embeddings表需要迁移")
                    self._add_missing_columns(conn, "memory_embeddings", current_table, target_table)
                    migration_performed = True
                    print("✅ memory_embeddings表迁移完成")
                else:
                    print("✅ memory_embeddings表结构正确")
                
                # 检查索引
                current_indexes = current_schema.indexes.get("memory_embeddings", [])
                target_indexes = target_schema.indexes.get("memory_embeddings", [])
                
                missing_indexes = [idx for idx in target_indexes 
                                 if idx["name"] not in {curr_idx["name"] for curr_idx in current_indexes}]
                
                if missing_indexes:
                    print("📝 创建缺失的索引...")
                    self._create_missing_indexes(conn, "memory_embeddings", current_indexes, target_indexes)
                    migration_performed = True
                    print("✅ 索引创建完成")
                else:
                    print("✅ 索引结构正确")
            else:
                print("📝 创建memory_embeddings表...")
                
                # 创建表
                columns_def = []
                for col in target_schema.tables["memory_embeddings"]:
                    col_def = f"{col['name']} {col['type']}"
                    
                    if col.get("primary_key", False):
                        col_def += " PRIMARY KEY"
                    
                    if col.get("not_null", False):
                        col_def += " NOT NULL"
                    
                    if "default" in col and col["default"]:
                        col_def += f" DEFAULT {col['default']}"
                    
                    columns_def.append(col_def)
                
                create_sql = f"CREATE TABLE memory_embeddings ({', '.join(columns_def)})"
                cursor.execute(create_sql)
                
                # 创建索引
                for idx in target_schema.indexes["memory_embeddings"]:
                    columns = ", ".join(idx["columns"])
                    unique = "UNIQUE" if idx.get("unique", False) else ""
                    
                    sql = f"CREATE {unique} INDEX {idx['name']} ON memory_embeddings ({columns})"
                    cursor.execute(sql)
                
                conn.commit()
                migration_performed = True
                print("✅ memory_embeddings表创建完成")
            
            conn.close()
            
            if migration_performed:
                print("🎉 嵌入向量缓存数据库迁移完成")
            else:
                print("✅ 嵌入向量缓存数据库结构已是最新")
            
            return True
            
        except Exception as e:
            print(f"❌ 迁移过程中发生错误: {e}")
            import traceback
            traceback.print_exc()
            return False

async def test_embedding_cache_migration():
    """测试嵌入向量缓存数据库迁移"""
    print("🧪 开始测试嵌入向量缓存数据库迁移...")
    
    # 创建测试数据目录
    data_dir = os.path.join(os.getcwd(), 'test_data')
    os.makedirs(data_dir, exist_ok=True)
    db_path = os.path.join(data_dir, 'memory_embeddings.db')
    
    print(f"📁 测试数据库路径: {db_path}")
    
    # 清理旧的测试文件
    if os.path.exists(db_path):
        os.remove(db_path)
        print("🗑️  清理旧的测试数据库")
    
    try:
        # 创建迁移实例
        print("🔧 创建迁移实例...")
        migration = SimpleDatabaseMigration(db_path)
        
        # 执行迁移
        print("⚡ 执行迁移...")
        success = await migration.run_embedding_cache_migration()
        
        if success:
            print("✅ 嵌入向量缓存数据库迁移成功")
            
            # 验证数据库结构
            print("🔍 验证数据库结构...")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # 检查表是否存在
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            print(f"📋 数据库中的表: {[table[0] for table in tables]}")
            
            # 检查memory_embeddings表结构
            cursor.execute("PRAGMA table_info(memory_embeddings)")
            columns = cursor.fetchall()
            print(f"📊 memory_embeddings表结构:")
            for col in columns:
                print(f"   {col[1]} ({col[2]})")
            
            # 检查是否有group_id字段
            has_group_id = any(col[1] == 'group_id' for col in columns)
            if has_group_id:
                print("✅ group_id字段已存在")
            else:
                print("❌ group_id字段不存在")
                return False
            
            # 检查索引
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='memory_embeddings'")
            indexes = cursor.fetchall()
            print(f"📑 索引: {[idx[0] for idx in indexes]}")
            
            # 检查是否有群聊隔离相关的索引
            group_indexes = [idx[0] for idx in indexes if 'group' in idx[0].lower()]
            if group_indexes:
                print(f"✅ 群聊隔离索引: {group_indexes}")
            else:
                print("⚠️  未找到群聊隔离相关索引")
            
            conn.close()
            
            # 测试插入数据
            print("🧪 测试插入数据...")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # 插入测试数据
            test_data = [
                ('test_memory_1', 'test content 1', 'concept_1', 128, 'group1'),
                ('test_memory_2', 'test content 2', 'concept_2', 128, 'group2'),
                ('test_memory_3', 'test content 3', 'concept_3', 128, '')  # 空群组ID
            ]
            
            for memory_id, content, concept_id, dim, group_id in test_data:
                cursor.execute('''
                    INSERT INTO memory_embeddings 
                    (memory_id, content, concept_id, embedding, vector_dimension, group_id, created_at, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                ''', (memory_id, content, concept_id, b'\x00' * dim * 4, dim, group_id))
            
            conn.commit()
            
            # 验证数据插入
            cursor.execute("SELECT COUNT(*) FROM memory_embeddings")
            count = cursor.fetchone()[0]
            print(f"📊 插入的测试数据数量: {count}")
            
            # 验证群聊隔离查询
            cursor.execute("SELECT COUNT(*) FROM memory_embeddings WHERE group_id = 'group1'")
            group1_count = cursor.fetchone()[0]
            print(f"📊 group1的记忆数量: {group1_count}")
            
            cursor.execute("SELECT COUNT(*) FROM memory_embeddings WHERE group_id = '' OR group_id IS NULL")
            default_count = cursor.fetchone()[0]
            print(f"📊 默认群组的记忆数量: {default_count}")
            
            conn.close()
            
            # 清理测试文件
            if os.path.exists(db_path):
                os.remove(db_path)
                print("🗑️  清理测试数据库")
            
            print("🎉 测试完成！嵌入向量缓存数据库迁移功能正常")
            return True
            
        else:
            print("❌ 嵌入向量缓存数据库迁移失败")
            return False
            
    except Exception as e:
        print(f"❌ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    result = asyncio.run(test_embedding_cache_migration())
    print(f"\n📋 最终测试结果: {'✅ 成功' if result else '❌ 失败'}")