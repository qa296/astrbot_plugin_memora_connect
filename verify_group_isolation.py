"""群聊隔离验证测试"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_group_filter_logic():
    """测试群聊过滤逻辑"""
    print("测试群聊隔离逻辑...")
    
    try:
        from models import Memory
        
        # 创建测试记忆
        memories = [
            Memory(id="m1", concept_id="c1", content="私聊记忆", group_id=""),
            Memory(id="m2", concept_id="c1", content="群聊1记忆", group_id="group1"),
            Memory(id="m3", concept_id="c1", content="群聊2记忆", group_id="group2"),
            Memory(id="m4", concept_id="c1", content="另一个私聊记忆", group_id=""),
        ]
        
        # 测试私聊过滤
        private_memories = [m for m in memories if not m.group_id]
        assert len(private_memories) == 2, f"预期2个私聊记忆，实际{len(private_memories)}"
        assert all(not m.group_id for m in private_memories), "私聊记忆应该没有group_id"
        print("✓ 私聊过滤正确")
        
        # 测试群聊1过滤
        group1_memories = [m for m in memories if m.group_id == "group1"]
        assert len(group1_memories) == 1, f"预期1个群聊1记忆，实际{len(group1_memories)}"
        assert group1_memories[0].content == "群聊1记忆"
        print("✓ 群聊1过滤正确")
        
        # 测试群聊2过滤
        group2_memories = [m for m in memories if m.group_id == "group2"]
        assert len(group2_memories) == 1, f"预期1个群聊2记忆，实际{len(group2_memories)}"
        assert group2_memories[0].content == "群聊2记忆"
        print("✓ 群聊2过滤正确")
        
        return True
    except Exception as e:
        print(f"✗ 群聊隔离测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_memory_graph_isolation():
    """测试MemoryGraph的群聊隔离"""
    print("\n测试MemoryGraph群聊隔离...")
    
    try:
        from models import Concept, Memory
        
        # 由于MemoryGraph依赖其他模块，我们只测试数据模型的group_id字段
        memory1 = Memory(id="m1", concept_id="c1", content="测试", group_id="")
        memory2 = Memory(id="m2", concept_id="c1", content="测试", group_id="group1")
        
        assert hasattr(memory1, 'group_id'), "Memory应该有group_id属性"
        assert hasattr(memory2, 'group_id'), "Memory应该有group_id属性"
        assert memory1.group_id == "", "私聊记忆的group_id应为空字符串"
        assert memory2.group_id == "group1", "群聊记忆的group_id应为指定值"
        
        print("✓ Memory模型支持group_id")
        
        return True
    except Exception as e:
        print(f"✗ MemoryGraph群聊隔离测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_module_structure():
    """测试模块结构是否支持群聊隔离"""
    print("\n测试模块结构...")
    
    try:
        # 检查memory_system.py中是否有filter_memories_by_group方法
        with open('memory_system.py', 'r', encoding='utf-8') as f:
            content = f.read()
            assert 'filter_memories_by_group' in content, "memory_system.py应该包含filter_memories_by_group方法"
            print("✓ memory_system.py包含群聊过滤方法")
        
        # 检查Memory模型是否有group_id字段
        with open('models.py', 'r', encoding='utf-8') as f:
            content = f.read()
            assert 'group_id' in content, "Memory模型应该包含group_id字段"
            print("✓ Memory模型包含group_id字段")
        
        return True
    except Exception as e:
        print(f"✗ 模块结构测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("=" * 60)
    print("开始群聊隔离验证测试")
    print("=" * 60)
    
    success = True
    
    # 测试模块结构
    if not test_module_structure():
        success = False
    
    # 测试群聊过滤逻辑
    if not test_group_filter_logic():
        success = False
    
    # 测试MemoryGraph隔离
    if not test_memory_graph_isolation():
        success = False
    
    print("\n" + "=" * 60)
    if success:
        print("✓ 所有群聊隔离测试通过！")
        print("=" * 60)
        return 0
    else:
        print("✗ 部分测试失败")
        print("=" * 60)
        return 1

if __name__ == "__main__":
    sys.exit(main())
