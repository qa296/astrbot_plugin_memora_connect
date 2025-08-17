"""
AstrBot 记忆插件使用示例
"""

import asyncio
import json
from main import MemorySystem, MemoryGraph
from unittest.mock import Mock

async def demonstrate_memory_system():
    """演示记忆系统的基本功能"""
    
    print("🧠 AstrBot 记忆插件演示")
    print("=" * 50)
    
    # 创建模拟上下文
    mock_context = Mock()
    mock_context.get_using_provider.return_value = None
    
    # 初始化记忆系统
    memory_system = MemorySystem(mock_context)
    memory_system.db_path = "demo_memory.db"
    
    await memory_system.initialize()
    
    print("✅ 记忆系统已初始化")
    
    # 演示1：添加概念和记忆
    print("\n📥 添加记忆...")
    concept1 = memory_system.memory_graph.add_concept("Python编程")
    memory1 = memory_system.memory_graph.add_memory(
        "我今天学习了Python的async/await语法，感觉很强大", 
        concept1
    )
    
    concept2 = memory_system.memory_graph.add_concept("异步编程")
    memory2 = memory_system.memory_graph.add_memory(
        "异步编程可以让程序同时处理多个任务", 
        concept2
    )
    
    # 建立连接
    memory_system.memory_graph.add_connection(concept1, concept2)
    
    print(f"✅ 已添加 {len(memory_system.memory_graph.concepts)} 个概念")
    print(f"✅ 已添加 {len(memory_system.memory_graph.memories)} 条记忆")
    print(f"✅ 已添加 {len(memory_system.memory_graph.connections)} 个连接")
    
    # 演示2：回忆记忆
    print("\n🔍 回忆记忆...")
    memories = await memory_system.recall_memories("Python", Mock())
    for memory in memories:
        print(f"💭 {memory}")
    
    # 演示3：查看统计
    print("\n📊 记忆统计:")
    stats = await memory_system.get_memory_stats()
    print(stats)
    
    # 演示4：保存记忆
    await memory_system.save_memory_state()
    print("\n💾 记忆已保存到数据库")
    
    # 演示5：加载记忆
    new_memory_system = MemorySystem(mock_context)
    new_memory_system.db_path = "demo_memory.db"
    await new_memory_system.load_memory_state()
    
    print(f"\n🔄 重新加载后:")
    print(f"概念: {len(new_memory_system.memory_graph.concepts)}")
    print(f"记忆: {len(new_memory_system.memory_graph.memories)}")
    print(f"连接: {len(new_memory_system.memory_graph.connections)}")
    
    # 清理
    import os
    if os.path.exists("demo_memory.db"):
        os.remove("demo_memory.db")


def demonstrate_memory_graph():
    """演示记忆图的基本操作"""
    
    print("\n🕸️ 记忆图演示")
    print("=" * 30)
    
    graph = MemoryGraph()
    
    # 添加概念
    food = graph.add_concept("食物")
    fruit = graph.add_concept("水果")
    apple = graph.add_concept("苹果")
    
    # 添加记忆
    graph.add_memory("我喜欢吃苹果", apple)
    graph.add_memory("水果很健康", fruit)
    graph.add_memory("食物提供能量", food)
    
    # 建立层次关系
    graph.add_connection(apple, fruit)  # 苹果是水果
    graph.add_connection(fruit, food)   # 水果是食物
    
    print("概念节点:")
    for concept in graph.concepts.values():
        print(f"  - {concept.name} ({concept.id})")
    
    print("\n记忆条目:")
    for memory in graph.memories.values():
        concept = graph.concepts[memory.concept_id]
        print(f"  - {concept.name}: {memory.content}")
    
    print("\n关系连接:")
    for conn in graph.connections:
        from_name = graph.concepts[conn.from_concept].name
        to_name = graph.concepts[conn.to_concept].name
        print(f"  - {from_name} ↔ {to_name} (强度: {conn.strength})")


if __name__ == "__main__":
    # 运行演示
    asyncio.run(demonstrate_memory_system())
    demonstrate_memory_graph()