#!/usr/bin/env python3
"""
数据库结构验证工具
用于验证群聊记忆隔离相关的数据库表结构是否正确
"""

import os
import sqlite3
import sys
from typing import Dict, List, Tuple, Any

def get_database_path(data_dir: str = None) -> Tuple[str, str]:
    """
    获取数据库路径
    
    Args:
        data_dir: 数据目录路径，如果为None则使用默认路径
        
    Returns:
        Tuple[str, str]: (主数据库路径, 嵌入向量缓存数据库路径)
    """
    if data_dir is None:
        # 使用默认数据目录
        current_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(current_dir, "data", "memora_connect")
    
    main_db_path = os.path.join(data_dir, "memory.db")
    embedding_cache_db_path = os.path.join(data_dir, "embedding_cache.db")
    
    return main_db_path, embedding_cache_db_path

def check_table_structure(conn: sqlite3.Connection, table_name: str) -> Dict[str, Any]:
    """
    检查表结构
    
    Args:
        conn: 数据库连接
        table_name: 表名
        
    Returns:
        Dict[str, Any]: 表结构信息
    """
    try:
        cursor = conn.cursor()
        
        # 获取表结构
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()
        
        # 获取索引信息
        cursor.execute(f"PRAGMA index_list({table_name})")
        indexes = cursor.fetchall()
        
        # 获取外键信息
        cursor.execute(f"PRAGMA foreign_key_list({table_name})")
        foreign_keys = cursor.fetchall()
        
        return {
            "table_name": table_name,
            "columns": columns,
            "indexes": indexes,
            "foreign_keys": foreign_keys,
            "exists": True
        }
        
    except sqlite3.OperationalError as e:
        if f"no such table: {table_name}" in str(e):
            return {
                "table_name": table_name,
                "exists": False,
                "error": str(e)
            }
        else:
            return {
                "table_name": table_name,
                "exists": False,
                "error": f"查询表结构时出错: {e}"
            }

def verify_main_database_structure(db_path: str) -> Dict[str, Any]:
    """
    验证主数据库结构
    
    Args:
        db_path: 主数据库路径
        
    Returns:
        Dict[str, Any]: 验证结果
    """
    result = {
        "database_path": db_path,
        "database_exists": os.path.exists(db_path),
        "tables": {},
        "issues": [],
        "summary": ""
    }
    
    if not result["database_exists"]:
        result["summary"] = "主数据库文件不存在"
        return result
    
    try:
        conn = sqlite3.connect(db_path)
        
        # 需要检查的表
        required_tables = ["concepts", "memories", "connections"]
        
        for table_name in required_tables:
            table_info = check_table_structure(conn, table_name)
            result["tables"][table_name] = table_info
            
            if not table_info["exists"]:
                result["issues"].append(f"表 {table_name} 不存在")
                continue
            
            # 检查特定表的字段
            if table_name == "memories":
                # 检查memories表是否有group_id字段
                columns = [col[1] for col in table_info["columns"]]
                if "group_id" not in columns:
                    result["issues"].append("memories表缺少group_id字段")
                else:
                    # 检查group_id字段的定义
                    for col in table_info["columns"]:
                        if col[1] == "group_id":
                            if col[2].upper() != "TEXT":
                                result["issues"].append(f"group_id字段类型应为TEXT，当前为{col[2]}")
                            break
                
                # 检查群聊隔离相关的索引
                index_names = [idx[1] for idx in table_info["indexes"]]
                required_indexes = ["idx_memories_group_id", "idx_memories_concept_group", "idx_memories_created_group"]
                for req_index in required_indexes:
                    if req_index not in index_names:
                        result["issues"].append(f"缺少索引: {req_index}")
        
        conn.close()
        
        # 生成总结
        if not result["issues"]:
            result["summary"] = "主数据库结构验证通过"
        else:
            result["summary"] = f"主数据库结构发现问题: {len(result['issues'])}个问题"
            
    except Exception as e:
        result["summary"] = f"验证主数据库结构时出错: {e}"
        result["issues"].append(f"数据库连接错误: {e}")
    
    return result

def verify_embedding_cache_database_structure(db_path: str) -> Dict[str, Any]:
    """
    验证嵌入向量缓存数据库结构
    
    Args:
        db_path: 嵌入向量缓存数据库路径
        
    Returns:
        Dict[str, Any]: 验证结果
    """
    result = {
        "database_path": db_path,
        "database_exists": os.path.exists(db_path),
        "tables": {},
        "issues": [],
        "summary": ""
    }
    
    if not result["database_exists"]:
        result["summary"] = "嵌入向量缓存数据库文件不存在"
        return result
    
    try:
        conn = sqlite3.connect(db_path)
        
        # 需要检查的表
        required_tables = ["memory_embeddings"]
        
        for table_name in required_tables:
            table_info = check_table_structure(conn, table_name)
            result["tables"][table_name] = table_info
            
            if not table_info["exists"]:
                result["issues"].append(f"表 {table_name} 不存在")
                continue
            
            # 检查memory_embeddings表的字段
            if table_name == "memory_embeddings":
                columns = [col[1] for col in table_info["columns"]]
                required_columns = ["memory_id", "embedding", "group_id", "created_at", "last_accessed"]
                
                for req_col in required_columns:
                    if req_col not in columns:
                        result["issues"].append(f"memory_embeddings表缺少{req_col}字段")
                
                # 检查group_id字段的定义
                if "group_id" in columns:
                    for col in table_info["columns"]:
                        if col[1] == "group_id":
                            if col[2].upper() != "TEXT":
                                result["issues"].append(f"group_id字段类型应为TEXT，当前为{col[2]}")
                            break
                
                # 检查群聊隔离相关的索引
                index_names = [idx[1] for idx in table_info["indexes"]]
                required_indexes = ["idx_embeddings_group_id", "idx_embeddings_memory_group", "idx_embeddings_created_group"]
                for req_index in required_indexes:
                    if req_index not in index_names:
                        result["issues"].append(f"缺少索引: {req_index}")
        
        conn.close()
        
        # 生成总结
        if not result["issues"]:
            result["summary"] = "嵌入向量缓存数据库结构验证通过"
        else:
            result["summary"] = f"嵌入向量缓存数据库结构发现问题: {len(result['issues'])}个问题"
            
    except Exception as e:
        result["summary"] = f"验证嵌入向量缓存数据库结构时出错: {e}"
        result["issues"].append(f"数据库连接错误: {e}")
    
    return result

def print_verification_result(result: Dict[str, Any], title: str):
    """
    打印验证结果
    
    Args:
        result: 验证结果字典
        title: 标题
    """
    print(f"\n{'='*60}")
    print(f"{title}")
    print(f"{'='*60}")
    print(f"数据库路径: {result['database_path']}")
    print(f"数据库存在: {'是' if result['database_exists'] else '否'}")
    print(f"总结: {result['summary']}")
    
    if result['tables']:
        print(f"\n表结构:")
        for table_name, table_info in result['tables'].items():
            print(f"  - {table_name}: {'存在' if table_info['exists'] else '不存在'}")
            if table_info['exists'] and table_info['columns']:
                print(f"    字段: {', '.join([col[1] for col in table_info['columns']])}")
                if table_info['indexes']:
                    print(f"    索引: {', '.join([idx[1] for idx in table_info['indexes']])}")
    
    if result['issues']:
        print(f"\n发现的问题:")
        for i, issue in enumerate(result['issues'], 1):
            print(f"  {i}. {issue}")
    else:
        print(f"\n✅ 未发现问题")

def main():
    """主函数"""
    print("数据库结构验证工具")
    print("验证群聊记忆隔离相关的数据库表结构")
    
    # 获取数据库路径
    main_db_path, embedding_cache_db_path = get_database_path()
    
    # 验证主数据库结构
    main_result = verify_main_database_structure(main_db_path)
    print_verification_result(main_result, "主数据库结构验证")
    
    # 验证嵌入向量缓存数据库结构
    embedding_result = verify_embedding_cache_database_structure(embedding_cache_db_path)
    print_verification_result(embedding_result, "嵌入向量缓存数据库结构验证")
    
    # 总体评估
    print(f"\n{'='*60}")
    print("总体评估")
    print(f"{'='*60}")
    
    total_issues = len(main_result['issues']) + len(embedding_result['issues'])
    
    if total_issues == 0:
        print("✅ 所有数据库结构验证通过！群聊记忆隔离功能应该可以正常工作。")
        return 0
    else:
        print(f"❌ 发现 {total_issues} 个问题，需要修复后才能正常使用群聊记忆隔离功能。")
        return 1

if __name__ == "__main__":
    sys.exit(main())