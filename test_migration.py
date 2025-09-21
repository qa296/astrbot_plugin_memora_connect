#!/usr/bin/env python3
"""
测试嵌入向量缓存数据库迁移的简单脚本
"""
import asyncio
import os
import sqlite3
from database_migration import SmartDatabaseMigration

class MockContext:
    """模拟的Context对象"""
    def get_config(self):
        return {}

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
        migration = SmartDatabaseMigration(db_path, MockContext())
        
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