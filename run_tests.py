"""
简单的插件功能测试脚本
"""

import asyncio
import os
import sys
from pathlib import Path

# 添加当前目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

from main import MemorySystem, MemoryGraph, Concept, Memory, Connection
from unittest.mock import Mock

async def run_basic_tests():
    """运行基础测试"""
    
    print("🧪 运行记忆插件基础测试")
    print("=" * 40)
    
    # 测试1：记忆图操作
    print("\n1. 测试记忆图操作...")
    graph = MemoryGraph()
    
    # 添加概念
    concept1 = graph.add_concept("测试概念1")
    concept2 = graph.add_concept("测试概念2")
    
    # 添加记忆
    memory1 = graph.add_memory("这是第一条测试记忆", concept1)
    memory2 = graph.add_memory("这是第二条测试记忆", concept2)
    
    # 添加连接
    connection = graph.add_connection(concept1, concept2)
    
    # 验证
    assert len(graph.concepts) == 2, "概念数量不正确"
    assert len(graph.memories) == 2, "记忆数量不正确"
    assert len(graph.connections) == 1, "连接数量不正确"
    
    print("✅ 记忆图操作测试通过")
    
    # 测试2：记忆系统初始化
    print("\n2. 测试记忆系统初始化...")
    
    mock_context = Mock()
    mock_context.get_using_provider.return_value = None
    
    memory_system = MemorySystem(mock_context)
    memory_system.db_path = "test_memory.db"
    
    await memory_system.initialize()
    
    print("✅ 记忆系统初始化测试通过")
    
    # 测试3：主题提取
    print("\n3. 测试主题提取...")
    
    history = [
        "我今天去了图书馆",
        "看了一本关于人工智能的书",
        "人工智能真的很有趣"
    ]
    
    themes = await memory_system.extract_themes(history)
    print(f"提取的主题: {themes}")
    
    assert isinstance(themes, list), "主题提取结果不是列表"
    assert len(themes) > 0, "没有提取到主题"
    
    print("✅ 主题提取测试通过")
    
    # 测试4：记忆相似度判断
    print("\n4. 测试记忆相似度判断...")
    
    mem1 = Memory("1", "c1", "我喜欢喝咖啡")
    mem2 = Memory("2", "c1", "我非常喜欢喝咖啡")
    mem3 = Memory("3", "c1", "今天天气很好")
    
    assert memory_system.are_memories_similar(mem1, mem2) == True, "相似记忆判断错误"
    assert memory_system.are_memories_similar(mem1, mem3) == False, "不相似记忆判断错误"
    
    print("✅ 记忆相似度判断测试通过")
    
    # 测试5：数据库操作
    print("\n5. 测试数据库操作...")
    
    # 添加测试数据
    concept_id = memory_system.memory_graph.add_concept("数据库测试")
    memory_system.memory_graph.add_memory("数据库测试记忆", concept_id)
    
    # 保存
    await memory_system.save_memory_state()
    
    # 验证文件存在
    assert os.path.exists("test_memory.db"), "数据库文件未创建"
    
    # 重新加载
    new_system = MemorySystem(mock_context)
    new_system.db_path = "test_memory.db"
    await new_system.load_memory_state()
    
    assert len(new_system.memory_graph.concepts) > 0, "概念未正确加载"
    assert len(new_system.memory_graph.memories) > 0, "记忆未正确加载"
    
    print("✅ 数据库操作测试通过")
    
    # 清理测试文件
    if os.path.exists("test_memory.db"):
        os.remove("test_memory.db")
    
    print("\n🎉 所有基础测试通过！")


def test_memory_classes():
    """测试记忆类"""
    
    print("\n📋 测试记忆类...")
    
    # 测试概念类
    concept = Concept("test_id", "测试概念")
    assert concept.id == "test_id"
    assert concept.name == "测试概念"
    print("✅ 概念类测试通过")
    
    # 测试记忆类
    memory = Memory("test_id", "concept_id", "测试记忆")
    assert memory.id == "test_id"
    assert memory.concept_id == "concept_id"
    assert memory.content == "测试记忆"
    print("✅ 记忆类测试通过")
    
    # 测试连接类
    connection = Connection("test_id", "from", "to")
    assert connection.id == "test_id"
    assert connection.from_concept == "from"
    assert connection.to_concept == "to"
    print("✅ 连接类测试通过")


async def demonstrate_features():
    """演示插件功能"""
    
    print("\n🎯 功能演示")
    print("=" * 30)
    
    mock_context = Mock()
    mock_context.get_using_provider.return_value = None
    
    memory_system = MemorySystem(mock_context)
    memory_system.db_path = "demo.db"
    
    await memory_system.initialize()
    
    # 演示记忆形成
    print("\n📥 记忆形成演示:")
    concept1 = memory_system.memory_graph.add_concept("编程学习")
    memory_system.memory_graph.add_memory("今天学习了Python的async语法", concept1)
    
    concept2 = memory_system.memory_graph.add_concept("异步编程")
    memory_system.memory_graph.add_memory("异步编程可以提高程序效率", concept2)
    
    concept3 = memory_system.memory_graph.add_concept("AstrBot")
    memory_system.memory_graph.add_memory("AstrBot是一个很好用的聊天机器人框架", concept3)
    
    # 建立连接
    memory_system.memory_graph.add_connection(concept1, concept2)
    memory_system.memory_graph.add_connection(concept2, concept3)
    
    print("已添加3个概念和3条记忆")
    
    # 演示回忆
    print("\n🔍 记忆回忆演示:")
    memories = await memory_system.recall_memories("编程", Mock())
    for memory in memories:
        print(f"  💭 {memory}")
    
    # 演示统计
    print("\n📊 统计信息:")
    stats = await memory_system.get_memory_stats()
    print(stats)
    
    # 保存演示
    await memory_system.save_memory_state()
    print("\n💾 记忆已保存")
    
    # 清理
    import os
    if os.path.exists("demo.db"):
        os.remove("demo.db")


if __name__ == "__main__":
    # 运行测试
    test_memory_classes()
    asyncio.run(run_basic_tests())
    asyncio.run(demonstrate_features())
    
    print("\n🎊 所有测试和演示完成！")
    print("插件已准备就绪，可以部署到AstrBot中使用。")