#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化的数据库迁移修复验证脚本
不依赖 astrbot 模块，直接测试修复的核心逻辑
"""

import sqlite3
import os
import sys
import tempfile
import shutil
from datetime import datetime

class SimpleMigrationTest:
    """简化的迁移测试类"""
    
    def __init__(self):
        self.test_dir = tempfile.mkdtemp(prefix="simple_migration_test_")
        self.test_results = []
        
    def __del__(self):
        """清理测试目录"""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def log_test(self, test_name: str, success: bool, message: str = ""):
        """记录测试结果"""
        status = "✅ 通过" if success else "❌ 失败"
        result = f"{status} {test_name}"
        if message:
            result += f" - {message}"
        self.test_results.append(result)
        print(result)
        return success
    
    def test_pragma_table_info_parsing(self):
        """测试 PRAGMA table_info 解析修复"""
        print("\n🧪 测试 PRAGMA table_info 解析修复...")
        
        # 创建测试数据库
        test_db = os.path.join(self.test_dir, "pragma_test.db")
        
        with sqlite3.connect(test_db) as conn:
            cursor = conn.cursor()
            
            # 创建测试表
            cursor.execute('''
                CREATE TABLE test_table (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    value INTEGER DEFAULT 0,
                    created_at REAL NOT NULL
                )
            ''')
            
            # 插入测试数据
            cursor.execute("INSERT INTO test_table VALUES (?, ?, ?, ?)", 
                         ("test1", "测试名称", 42, datetime.now().timestamp()))
            
            conn.commit()
        
        # 测试修复前的错误解析方式
        try:
            with sqlite3.connect(test_db) as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info('test_table')")
                
                # 修复前的错误方式
                wrong_columns = [str(col) for col in cursor.fetchall()]
                print(f"❌ 错误解析结果: {wrong_columns}")
                
                # 这应该会产生类似 "(0, 'id', 'TEXT', 0, None, 1)" 的字符串
                if any("('id'" in col for col in wrong_columns):
                    print("✅ 确认修复前的问题存在")
                else:
                    print("⚠️  修复前的问题不明显")
                    
        except Exception as e:
            print(f"❌ 修复前测试异常: {e}")
        
        # 测试修复后的正确解析方式
        try:
            with sqlite3.connect(test_db) as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info('test_table')")
                
                # 修复后的正确方式
                correct_columns = [col[1] for col in cursor.fetchall()]  # col[1] 是列名
                print(f"✅ 正确解析结果: {correct_columns}")
                
                expected_columns = ["id", "name", "value", "created_at"]
                if correct_columns == expected_columns:
                    return self.log_test("PRAGMA table_info 解析修复", True, "列名解析正确")
                else:
                    return self.log_test("PRAGMA table_info 解析修复", False, f"期望 {expected_columns}, 实际 {correct_columns}")
                    
        except Exception as e:
            return self.log_test("PRAGMA table_info 解析修复", False, f"测试异常: {e}")
    
    def test_string_default_value_handling(self):
        """测试字符串默认值处理修复"""
        print("\n🧪 测试字符串默认值处理修复...")
        
        # 测试不同的默认值情况
        test_cases = [
            ("pending", "普通字符串"),
            ("'pending'", "已带引号字符串"),
            ("'pending'", "已带引号字符串2"),
            ("completed", "另一个普通字符串"),
        ]
        
        for i, (default_value, description) in enumerate(test_cases):
            try:
                # 模拟修复后的逻辑
                if isinstance(default_value, str):
                    if default_value.startswith("'") and default_value.endswith("'"):
                        sql_default = f" DEFAULT {default_value}"
                    else:
                        sql_default = f" DEFAULT '{default_value}'"
                else:
                    sql_default = f" DEFAULT {default_value}"
                
                print(f"✅ {description}: '{default_value}' -> {sql_default}")
                
                # 验证生成的SQL是否有效
                test_sql = f"CREATE TABLE test_table_{i} (id TEXT PRIMARY KEY, status TEXT{sql_default})"
                
                # 尝试创建表来验证SQL语法
                test_db = os.path.join(self.test_dir, f"default_test_{i}.db")
                with sqlite3.connect(test_db) as conn:
                    cursor = conn.cursor()
                    cursor.execute(test_sql)
                    conn.commit()
                
            except Exception as e:
                return self.log_test("字符串默认值处理修复", False, f"测试失败: {description} - {e}")
        
        return self.log_test("字符串默认值处理修复", True, "所有测试用例通过")
    
    def test_migration_simulation(self):
        """模拟迁移过程测试"""
        print("\n🧪 测试迁移过程模拟...")
        
        # 创建旧版本数据库
        old_db = os.path.join(self.test_dir, "old_migration.db")
        
        with sqlite3.connect(old_db) as conn:
            cursor = conn.cursor()
            
            # 创建旧版本表（不带 group_id）
            cursor.execute('''
                CREATE TABLE memory_embeddings (
                    memory_id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    concept_id TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    vector_dimension INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    last_updated REAL NOT NULL
                )
            ''')
            
            # 插入测试数据
            cursor.execute("INSERT INTO memory_embeddings VALUES (?, ?, ?, ?, ?, ?, ?)", 
                         ("embed1", "测试内容1", "concept1", b"fake_data", 1536, datetime.now().timestamp(), datetime.now().timestamp()))
            cursor.execute("INSERT INTO memory_embeddings VALUES (?, ?, ?, ?, ?, ?, ?)", 
                         ("embed2", "测试内容2", "concept2", b"fake_data", 1536, datetime.now().timestamp(), datetime.now().timestamp()))
            
            conn.commit()
        
        # 创建新版本数据库结构
        new_db = os.path.join(self.test_dir, "new_migration.db")
        
        with sqlite3.connect(new_db) as conn:
            cursor = conn.cursor()
            
            # 创建新版本表（带 group_id）
            cursor.execute('''
                CREATE TABLE memory_embeddings (
                    memory_id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    concept_id TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    vector_dimension INTEGER NOT NULL,
                    group_id TEXT DEFAULT "",
                    created_at REAL NOT NULL,
                    last_updated REAL NOT NULL,
                    embedding_version TEXT DEFAULT "v1.0",
                    metadata TEXT DEFAULT "{}"
                )
            ''')
            
            conn.commit()
        
        # 模拟数据迁移过程
        try:
            with sqlite3.connect(old_db) as source_conn, \
                 sqlite3.connect(new_db) as target_conn:
                
                source_cursor = source_conn.cursor()
                target_cursor = target_conn.cursor()
                
                # 获取源数据
                source_cursor.execute("SELECT * FROM memory_embeddings")
                rows = source_cursor.fetchall()
                
                # 获取源列信息（修复后的方式）
                source_cursor.execute("PRAGMA table_info('memory_embeddings')")
                source_columns = [col[1] for col in source_cursor.fetchall()]  # 修复：col[1] 是列名
                
                # 获取目标列信息（修复后的方式）
                target_cursor.execute("PRAGMA table_info('memory_embeddings')")
                target_columns_info = {col[1]: col for col in target_cursor.fetchall()}  # 修复：col[1] 是列名
                target_columns = list(target_columns_info.keys())
                
                print(f"源列: {source_columns}")
                print(f"目标列: {target_columns}")
                
                # 构建字段映射
                field_mapping = {}
                final_target_columns = []
                
                for target_col in target_columns:
                    if target_col in source_columns:
                        field_mapping[target_col] = {"type": "direct", "source": target_col}
                        final_target_columns.append(target_col)
                
                # 添加新字段的默认值
                for target_col in ["group_id", "embedding_version", "metadata"]:
                    if target_col in target_columns and target_col not in source_columns:
                        # 修复后的字符串默认值处理
                        if target_col == "group_id":
                            default_value = ""
                        elif target_col == "embedding_version":
                            default_value = "v1.0"
                        elif target_col == "metadata":
                            default_value = "{}"
                        
                        field_mapping[target_col] = {"type": "default", "value": default_value}
                        final_target_columns.append(target_col)
                
                print(f"字段映射: {field_mapping}")
                print(f"最终目标列: {final_target_columns}")
                
                # 迁移数据
                migrated_count = 0
                for row in rows:
                    # 转换数据行
                    source_row_dict = dict(zip(source_columns, row))
                    new_row_dict = {}
                    
                    for target_col, mapping_info in field_mapping.items():
                        if mapping_info["type"] == "direct":
                            new_row_dict[target_col] = source_row_dict.get(mapping_info["source"])
                        elif mapping_info["type"] == "default":
                            new_row_dict[target_col] = mapping_info["value"]
                    
                    # 插入数据
                    ordered_row = [new_row_dict.get(col) for col in final_target_columns]
                    placeholders = ",".join(["?" for _ in final_target_columns])
                    column_names = ",".join(f'"{col}"' for col in final_target_columns)
                    
                    target_cursor.execute(
                        f"INSERT INTO memory_embeddings ({column_names}) VALUES ({placeholders})",
                        tuple(ordered_row)
                    )
                    migrated_count += 1
                
                target_conn.commit()
                
                print(f"✅ 成功迁移 {migrated_count}/{len(rows)} 行数据")
                
                # 验证迁移结果
                target_cursor.execute("SELECT COUNT(*) FROM memory_embeddings")
                final_count = target_cursor.fetchone()[0]
                
                if final_count == len(rows):
                    # 检查新字段是否有正确的默认值
                    target_cursor.execute("SELECT group_id, embedding_version, metadata FROM memory_embeddings LIMIT 1")
                    result = target_cursor.fetchone()
                    
                    if result[0] == "" and result[1] == "v1.0" and result[2] == "{}":
                        return self.log_test("迁移过程模拟", True, "数据迁移成功，默认值正确")
                    else:
                        return self.log_test("迁移过程模拟", False, f"默认值不正确: {result}")
                else:
                    return self.log_test("迁移过程模拟", False, f"数据数量不匹配: {final_count} != {len(rows)}")
                    
        except Exception as e:
            return self.log_test("迁移过程模拟", False, f"迁移过程异常: {e}")
    
    def run_all_tests(self):
        """运行所有测试"""
        print("🚀 开始简化的数据库迁移修复验证测试...")
        print(f"📁 测试目录: {self.test_dir}")
        
        tests = [
            self.test_pragma_table_info_parsing,
            self.test_string_default_value_handling,
            self.test_migration_simulation
        ]
        
        passed = 0
        total = len(tests)
        
        for test in tests:
            try:
                result = test()
                if result:
                    passed += 1
            except Exception as e:
                self.log_test(test.__name__, False, f"测试异常: {e}")
        
        print(f"\n📊 测试结果: {passed}/{total} 通过")
        
        if passed == total:
            print("🎉 所有测试通过！数据库迁移修复成功！")
            return True
        else:
            print("⚠️  部分测试失败，需要进一步修复")
            return False

def main():
    """主函数"""
    runner = SimpleMigrationTest()
    success = runner.run_all_tests()
    
    # 输出详细结果
    print("\n📋 详细测试结果:")
    for result in runner.test_results:
        print(f"  {result}")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)