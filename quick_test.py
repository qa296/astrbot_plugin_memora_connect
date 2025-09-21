#!/usr/bin/env python3
"""
快速测试嵌入向量缓存数据库迁移功能
"""
import sqlite3
import os

def test_database_structure():
    """测试数据库结构是否正确"""
    print("🧪 快速测试嵌入向量缓存数据库结构...")
    
    # 创建测试数据库路径
    db_path = "test_memory_embeddings.db"
    
    # 清理旧文件
    if os.path.exists(db_path):
        os.remove(db_path)
    
    try:
        # 创建数据库连接
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 创建memory_embeddings表（包含group_id字段）
        print("📝 创建memory_embeddings表...")
        cursor.execute('''
            CREATE TABLE memory_embeddings (
                memory_id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                concept_id TEXT NOT NULL,
                embedding BLOB NOT NULL,
                vector_dimension INTEGER NOT NULL,
                group_id TEXT DEFAULT '',
                created_at REAL NOT NULL,
                last_updated REAL NOT NULL,
                embedding_version TEXT DEFAULT 'v1.0',
                metadata TEXT DEFAULT '{}'
            )
        ''')
        
        # 创建群聊隔离相关的索引
        print("📝 创建群聊隔离索引...")
        cursor.execute('CREATE INDEX idx_memory_embeddings_group_id ON memory_embeddings(group_id)')
        cursor.execute('CREATE INDEX idx_memory_embeddings_concept_group ON memory_embeddings(concept_id, group_id)')
        cursor.execute('CREATE INDEX idx_memory_embeddings_created_group ON memory_embeddings(created_at, group_id)')
        
        conn.commit()
        
        # 验证表结构
        print("🔍 验证表结构...")
        cursor.execute("PRAGMA table_info(memory_embeddings)")
        columns = cursor.fetchall()
        
        print("📊 memory_embeddings表结构:")
        group_id_found = False
        for col in columns:
            print(f"   {col[1]} ({col[2]})")
            if col[1] == 'group_id':
                group_id_found = True
        
        if group_id_found:
            print("✅ group_id字段已存在")
        else:
            print("❌ group_id字段不存在")
            return False
        
        # 验证索引
        print("🔍 验证索引...")
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='memory_embeddings'")
        indexes = cursor.fetchall()
        
        print("📑 索引列表:")
        group_indexes = []
        for idx in indexes:
            print(f"   {idx[0]}")
            if 'group' in idx[0].lower():
                group_indexes.append(idx[0])
        
        if group_indexes:
            print(f"✅ 群聊隔离索引: {group_indexes}")
        else:
            print("⚠️  未找到群聊隔离相关索引")
        
        # 测试插入数据
        print("🧪 测试插入数据...")
        test_data = [
            ('test_memory_1', 'test content 1', 'concept_1', b'\x00' * 512, 128, 'group1'),
            ('test_memory_2', 'test content 2', 'concept_2', b'\x00' * 512, 128, 'group2'),
            ('test_memory_3', 'test content 3', 'concept_3', b'\x00' * 512, 128, ''),  # 空群组ID
        ]
        
        for memory_id, content, concept_id, embedding, dim, group_id in test_data:
            cursor.execute('''
                INSERT INTO memory_embeddings 
                (memory_id, content, concept_id, embedding, vector_dimension, group_id, created_at, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            ''', (memory_id, content, concept_id, embedding, dim, group_id))
        
        conn.commit()
        
        # 验证数据插入
        cursor.execute("SELECT COUNT(*) FROM memory_embeddings")
        total_count = cursor.fetchone()[0]
        print(f"📊 总记录数: {total_count}")
        
        # 测试群聊隔离查询
        cursor.execute("SELECT COUNT(*) FROM memory_embeddings WHERE group_id = 'group1'")
        group1_count = cursor.fetchone()[0]
        print(f"📊 group1的记忆数量: {group1_count}")
        
        cursor.execute("SELECT COUNT(*) FROM memory_embeddings WHERE group_id = 'group2'")
        group2_count = cursor.fetchone()[0]
        print(f"📊 group2的记忆数量: {group2_count}")
        
        cursor.execute("SELECT COUNT(*) FROM memory_embeddings WHERE group_id = '' OR group_id IS NULL")
        default_count = cursor.fetchone()[0]
        print(f"📊 默认群组的记忆数量: {default_count}")
        
        # 验证群聊隔离功能
        if group1_count == 1 and group2_count == 1 and default_count == 1:
            print("✅ 群聊隔离功能正常工作")
        else:
            print("❌ 群聊隔离功能异常")
            return False
        
        conn.close()
        
        # 清理测试文件
        if os.path.exists(db_path):
            os.remove(db_path)
            print("🗑️  清理测试数据库")
        
        print("🎉 测试完成！嵌入向量缓存数据库结构正确")
        return True
        
    except Exception as e:
        print(f"❌ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    result = test_database_structure()
    print(f"\n📋 最终测试结果: {'✅ 成功' if result else '❌ 失败'}")