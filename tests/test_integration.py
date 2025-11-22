"""
集成测试
测试多个模块之间的协作
"""
import unittest
import asyncio
import os
import tempfile
from memory_graph import MemoryGraph
from config import MemoryConfigManager
from models import Concept, Memory, Connection


class TestMemoryGraphIntegration(unittest.TestCase):
    """测试记忆图的集成功能"""
    
    def setUp(self):
        """每个测试前初始化"""
        self.graph = MemoryGraph()
    
    def test_complete_workflow(self):
        """测试完整工作流：创建概念、添加记忆、建立连接"""
        # 创建概念
        concept1_id = self.graph.add_concept("Python编程")
        concept2_id = self.graph.add_concept("机器学习")
        
        # 添加记忆
        memory1_id = self.graph.add_memory(
            "学习了Python基础",
            concept1_id,
            details="变量、函数、类",
            tags="编程,学习"
        )
        memory2_id = self.graph.add_memory(
            "学习了机器学习算法",
            concept2_id,
            details="线性回归、决策树",
            tags="AI,学习"
        )
        
        # 建立连接
        conn_id = self.graph.add_connection(concept1_id, concept2_id, strength=0.8)
        
        # 验证
        self.assertEqual(len(self.graph.concepts), 2)
        self.assertEqual(len(self.graph.memories), 2)
        self.assertEqual(len(self.graph.connections), 1)
        
        # 验证邻居关系
        neighbors = self.graph.get_neighbors(concept1_id)
        self.assertEqual(len(neighbors), 1)
        self.assertIn((concept2_id, 0.8), neighbors)
    
    def test_complex_graph_operations(self):
        """测试复杂图操作：多个概念、记忆和连接"""
        # 创建多个概念
        concepts = []
        for i in range(5):
            concept_id = self.graph.add_concept(f"概念{i}")
            concepts.append(concept_id)
        
        # 为每个概念添加记忆
        for concept_id in concepts:
            self.graph.add_memory(f"关于{concept_id}的记忆", concept_id)
        
        # 建立多个连接
        for i in range(len(concepts) - 1):
            self.graph.add_connection(concepts[i], concepts[i + 1])
        
        # 验证
        self.assertEqual(len(self.graph.concepts), 5)
        self.assertEqual(len(self.graph.memories), 5)
        self.assertEqual(len(self.graph.connections), 4)
    
    def test_memory_update_and_removal(self):
        """测试记忆的更新和删除"""
        concept_id = self.graph.add_concept("测试概念")
        memory_id = self.graph.add_memory("原始记忆", concept_id)
        
        # 更新记忆
        self.graph.update_memory(memory_id, content="更新后的记忆", strength=0.9)
        memory = self.graph.memories[memory_id]
        self.assertEqual(memory.content, "更新后的记忆")
        self.assertEqual(memory.strength, 0.9)
        
        # 删除记忆
        self.graph.remove_memory(memory_id)
        self.assertNotIn(memory_id, self.graph.memories)
    
    def test_connection_strengthening(self):
        """测试连接强化"""
        concept1_id = self.graph.add_concept("概念1")
        concept2_id = self.graph.add_concept("概念2")
        
        # 多次添加相同连接应该强化它
        conn_id1 = self.graph.add_connection(concept1_id, concept2_id, strength=1.0)
        initial_strength = self.graph.connections[0].strength
        
        conn_id2 = self.graph.add_connection(concept1_id, concept2_id, strength=1.0)
        
        # 验证强度增加
        self.assertEqual(len(self.graph.connections), 1)
        self.assertGreater(self.graph.connections[0].strength, initial_strength)
    
    def test_concept_removal_cascade(self):
        """测试删除概念时的级联删除"""
        concept1_id = self.graph.add_concept("主概念")
        concept2_id = self.graph.add_concept("相关概念")
        
        # 添加记忆和连接
        memory_id = self.graph.add_memory("记忆", concept1_id)
        conn_id = self.graph.add_connection(concept1_id, concept2_id)
        
        # 删除概念
        self.graph.remove_concept(concept1_id)
        
        # 验证级联删除
        self.assertNotIn(concept1_id, self.graph.concepts)
        self.assertNotIn(memory_id, self.graph.memories)
        self.assertEqual(len(self.graph.connections), 0)


class TestConfigIntegration(unittest.TestCase):
    """测试配置管理的集成功能"""
    
    def test_config_lifecycle(self):
        """测试配置的完整生命周期"""
        # 创建配置管理器
        manager = MemoryConfigManager()
        self.assertTrue(manager.is_memory_system_enabled())
        
        # 更新配置
        manager.update_config({"enable_memory_system": False})
        self.assertFalse(manager.is_memory_system_enabled())
        
        # 获取配置字典
        config_dict = manager.get_config_dict()
        self.assertEqual(config_dict["enable_memory_system"], False)
        
        # 验证配置
        self.assertTrue(manager.validate_config())
    
    def test_config_with_graph(self):
        """测试配置与记忆图的协作"""
        manager = MemoryConfigManager({"enable_memory_system": True})
        graph = MemoryGraph()
        
        if manager.is_memory_system_enabled():
            concept_id = graph.add_concept("测试")
            self.assertIn(concept_id, graph.concepts)
        
        # 禁用后不应该影响已有数据
        manager.set_memory_system_enabled(False)
        self.assertIn(concept_id, graph.concepts)


class TestDataModelIntegration(unittest.TestCase):
    """测试数据模型的集成"""
    
    def test_concept_memory_relationship(self):
        """测试概念和记忆的关系"""
        graph = MemoryGraph()
        
        # 创建概念
        concept = Concept(id="c1", name="测试概念")
        graph.concepts[concept.id] = concept
        
        # 创建关联记忆
        memory = Memory(id="m1", concept_id=concept.id, content="相关记忆")
        graph.memories[memory.id] = memory
        
        # 验证关系
        self.assertEqual(memory.concept_id, concept.id)
        concept_memories = [m for m in graph.memories.values() if m.concept_id == concept.id]
        self.assertEqual(len(concept_memories), 1)
    
    def test_connection_bidirectional(self):
        """测试连接的双向性"""
        graph = MemoryGraph()
        
        c1_id = graph.add_concept("概念1")
        c2_id = graph.add_concept("概念2")
        
        graph.add_connection(c1_id, c2_id)
        
        # 验证双向连接
        neighbors_c1 = graph.get_neighbors(c1_id)
        neighbors_c2 = graph.get_neighbors(c2_id)
        
        self.assertIn(c2_id, [n[0] for n in neighbors_c1])
        self.assertIn(c1_id, [n[0] for n in neighbors_c2])


class TestMemoryGraphPerformance(unittest.TestCase):
    """测试记忆图的性能"""
    
    def test_large_graph_creation(self):
        """测试创建大型图"""
        graph = MemoryGraph()
        
        # 创建100个概念
        concepts = []
        for i in range(100):
            concept_id = graph.add_concept(f"概念{i}")
            concepts.append(concept_id)
        
        # 为每个概念添加记忆
        for concept_id in concepts:
            graph.add_memory(f"记忆内容{concept_id}", concept_id)
        
        # 建立连接
        for i in range(0, len(concepts) - 1, 2):
            graph.add_connection(concepts[i], concepts[i + 1])
        
        self.assertEqual(len(graph.concepts), 100)
        self.assertEqual(len(graph.memories), 100)
        self.assertGreater(len(graph.connections), 0)
    
    def test_neighbor_lookup_performance(self):
        """测试邻居查找性能"""
        graph = MemoryGraph()
        
        # 创建星型结构
        center_id = graph.add_concept("中心")
        for i in range(50):
            outer_id = graph.add_concept(f"外围{i}")
            graph.add_connection(center_id, outer_id)
        
        # 查找邻居应该很快
        neighbors = graph.get_neighbors(center_id)
        self.assertEqual(len(neighbors), 50)


if __name__ == '__main__':
    unittest.main()
