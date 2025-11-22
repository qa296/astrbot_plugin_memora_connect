"""简单的迁移验证测试"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """测试所有模块能否正常导入"""
    print("测试模块导入...")
    
    try:
        from models import Concept, Memory, Connection
        print("✓ models.py 导入成功")
    except Exception as e:
        print(f"✗ models.py 导入失败: {e}")
        return False
    
    try:
        # config.py 依赖 astrbot，在没有astrbot的环境下会失败，这是预期的
        # 我们只检查语法
        import ast
        with open('config.py', 'r') as f:
            ast.parse(f.read())
        print("✓ config.py 语法正确")
    except Exception as e:
        print(f"✗ config.py 语法错误: {e}")
        return False
    
    try:
        # memory_graph.py 依赖 models
        import ast
        with open('memory_graph.py', 'r') as f:
            ast.parse(f.read())
        print("✓ memory_graph.py 语法正确")
    except Exception as e:
        print(f"✗ memory_graph.py 语法错误: {e}")
        return False
    
    try:
        import ast
        with open('batch_memory_extractor.py', 'r') as f:
            ast.parse(f.read())
        print("✓ batch_memory_extractor.py 语法正确")
    except Exception as e:
        print(f"✗ batch_memory_extractor.py 语法错误: {e}")
        return False
    
    try:
        import ast
        with open('memory_system.py', 'r') as f:
            ast.parse(f.read())
        print("✓ memory_system.py 语法正确")
    except Exception as e:
        print(f"✗ memory_system.py 语法错误: {e}")
        return False
    
    try:
        import ast
        with open('plugin.py', 'r') as f:
            ast.parse(f.read())
        print("✓ plugin.py 语法正确")
    except Exception as e:
        print(f"✗ plugin.py 语法错误: {e}")
        return False
    
    try:
        import ast
        with open('main.py', 'r') as f:
            ast.parse(f.read())
        print("✓ main.py 语法正确")
    except Exception as e:
        print(f"✗ main.py 语法错误: {e}")
        return False
    
    return True

def test_data_models():
    """测试数据模型"""
    print("\n测试数据模型...")
    
    try:
        from models import Concept, Memory, Connection
        import time
        
        # 测试Concept
        concept = Concept(id="test_1", name="测试概念")
        assert concept.id == "test_1"
        assert concept.name == "测试概念"
        assert concept.created_at is not None
        assert concept.last_accessed is not None
        print("✓ Concept 模型正常")
        
        # 测试Memory
        memory = Memory(
            id="mem_1",
            concept_id="test_1",
            content="测试记忆"
        )
        assert memory.id == "mem_1"
        assert memory.concept_id == "test_1"
        assert memory.content == "测试记忆"
        assert memory.strength == 1.0
        print("✓ Memory 模型正常")
        
        # 测试Connection
        conn = Connection(
            id="conn_1",
            from_concept="test_1",
            to_concept="test_2"
        )
        assert conn.id == "conn_1"
        assert conn.from_concept == "test_1"
        assert conn.to_concept == "test_2"
        assert conn.strength == 1.0
        print("✓ Connection 模型正常")
        
        return True
    except Exception as e:
        print(f"✗ 数据模型测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_file_structure():
    """测试文件结构"""
    print("\n测试文件结构...")
    
    required_files = [
        'main.py',
        'plugin.py',
        'memory_system.py',
        'memory_graph.py',
        'models.py',
        'config.py',
        'batch_memory_extractor.py'
    ]
    
    all_exist = True
    for filename in required_files:
        if os.path.exists(filename):
            print(f"✓ {filename} 存在")
        else:
            print(f"✗ {filename} 不存在")
            all_exist = False
    
    return all_exist

def main():
    """主测试函数"""
    print("=" * 60)
    print("开始迁移验证测试")
    print("=" * 60)
    
    success = True
    
    # 测试文件结构
    if not test_file_structure():
        success = False
    
    # 测试导入
    if not test_imports():
        success = False
    
    # 测试数据模型
    if not test_data_models():
        success = False
    
    print("\n" + "=" * 60)
    if success:
        print("✓ 所有测试通过！")
        print("=" * 60)
        return 0
    else:
        print("✗ 部分测试失败")
        print("=" * 60)
        return 1

if __name__ == "__main__":
    sys.exit(main())
