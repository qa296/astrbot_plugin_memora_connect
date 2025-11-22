"""
测试记忆图数据结构
"""
import unittest
import time
from memory_graph import MemoryGraph
from models import Concept, Memory, Connection


class TestMemoryGraph(unittest.TestCase):
    """测试 MemoryGraph 类"""
    
    def setUp(self):
        """每个测试前初始化记忆图"""
        self.graph = MemoryGraph()
    
    def test_graph_initialization(self):
        """测试记忆图初始化"""
        self.assertIsInstance(self.graph.concepts, dict)
        self.assertIsInstance(self.graph.memories, dict)
        self.assertIsInstance(self.graph.connections, list)
        self.assertIsInstance(self.graph.adjacency_list, dict)
        self.assertEqual(len(self.graph.concepts), 0)
        self.assertEqual(len(self.graph.memories), 0)
        self.assertEqual(len(self.graph.connections), 0)
    
    def test_add_concept(self):
        """测试添加概念"""
        concept_id = self.graph.add_concept("测试概念")
        self.assertIn(concept_id, self.graph.concepts)
        self.assertEqual(self.graph.concepts[concept_id].name, "测试概念")
        self.assertIn(concept_id, self.graph.adjacency_list)
    
    def test_add_concept_with_id(self):
        """测试添加带指定ID的概念"""
        concept_id = self.graph.add_concept("测试", concept_id="custom_id")
        self.assertEqual(concept_id, "custom_id")
        self.assertIn("custom_id", self.graph.concepts)
    
    def test_add_concept_with_times(self):
        """测试添加带时间参数的概念"""
        custom_time = 1609459200.0
        concept_id = self.graph.add_concept(
            "测试",
            created_at=custom_time,
            last_accessed=custom_time,
            access_count=5
        )
        concept = self.graph.concepts[concept_id]
        self.assertEqual(concept.created_at, custom_time)
        self.assertEqual(concept.last_accessed, custom_time)
        self.assertEqual(concept.access_count, 5)
    
    def test_add_duplicate_concept(self):
        """测试添加重复概念"""
        concept_id = self.graph.add_concept("测试", concept_id="dup_id")
        concept_id2 = self.graph.add_concept("测试2", concept_id="dup_id")
        self.assertEqual(len(self.graph.concepts), 1)
        self.assertEqual(self.graph.concepts["dup_id"].name, "测试")
    
    def test_add_memory(self):
        """测试添加记忆"""
        concept_id = self.graph.add_concept("测试概念")
        memory_id = self.graph.add_memory("这是记忆内容", concept_id)
        self.assertIn(memory_id, self.graph.memories)
        self.assertEqual(self.graph.memories[memory_id].content, "这是记忆内容")
        self.assertEqual(self.graph.memories[memory_id].concept_id, concept_id)
    
    def test_add_memory_with_details(self):
        """测试添加带详细信息的记忆"""
        concept_id = self.graph.add_concept("测试")
        memory_id = self.graph.add_memory(
            "记忆",
            concept_id,
            memory_id="mem_custom",
            details="详细信息",
            participants="张三",
            location="北京",
            emotion="开心",
            tags="标签1",
            strength=0.8,
            group_id="group_1",
            access_count=3
        )
        memory = self.graph.memories[memory_id]
        self.assertEqual(memory.id, "mem_custom")
        self.assertEqual(memory.details, "详细信息")
        self.assertEqual(memory.participants, "张三")
        self.assertEqual(memory.location, "北京")
        self.assertEqual(memory.emotion, "开心")
        self.assertEqual(memory.tags, "标签1")
        self.assertEqual(memory.strength, 0.8)
        self.assertEqual(memory.group_id, "group_1")
        self.assertEqual(memory.access_count, 3)
    
    def test_add_connection(self):
        """测试添加连接"""
        concept1_id = self.graph.add_concept("概念1")
        concept2_id = self.graph.add_concept("概念2")
        conn_id = self.graph.add_connection(concept1_id, concept2_id)
        
        self.assertEqual(len(self.graph.connections), 1)
        self.assertEqual(self.graph.connections[0].from_concept, concept1_id)
        self.assertEqual(self.graph.connections[0].to_concept, concept2_id)
        self.assertIn((concept2_id, 1.0), self.graph.adjacency_list[concept1_id])
        self.assertIn((concept1_id, 1.0), self.graph.adjacency_list[concept2_id])
    
    def test_add_connection_with_strength(self):
        """测试添加带强度的连接"""
        concept1_id = self.graph.add_concept("概念1")
        concept2_id = self.graph.add_concept("概念2")
        custom_time = 1609459200.0
        conn_id = self.graph.add_connection(
            concept1_id,
            concept2_id,
            strength=0.5,
            connection_id="custom_conn",
            last_strengthened=custom_time
        )
        
        conn = self.graph.connections[0]
        self.assertEqual(conn.id, "custom_conn")
        self.assertEqual(conn.strength, 0.5)
        self.assertEqual(conn.last_strengthened, custom_time)
    
    def test_add_duplicate_connection(self):
        """测试添加重复连接（应增强现有连接）"""
        concept1_id = self.graph.add_concept("概念1")
        concept2_id = self.graph.add_concept("概念2")
        
        conn_id1 = self.graph.add_connection(concept1_id, concept2_id, strength=1.0)
        initial_strength = self.graph.connections[0].strength
        
        conn_id2 = self.graph.add_connection(concept1_id, concept2_id, strength=1.0)
        
        self.assertEqual(len(self.graph.connections), 1)
        self.assertGreater(self.graph.connections[0].strength, initial_strength)
    
    def test_add_reverse_connection(self):
        """测试添加反向连接（应增强现有连接）"""
        concept1_id = self.graph.add_concept("概念1")
        concept2_id = self.graph.add_concept("概念2")
        
        self.graph.add_connection(concept1_id, concept2_id)
        initial_strength = self.graph.connections[0].strength
        
        self.graph.add_connection(concept2_id, concept1_id)
        
        self.assertEqual(len(self.graph.connections), 1)
        self.assertGreater(self.graph.connections[0].strength, initial_strength)
    
    def test_remove_connection(self):
        """测试移除连接"""
        concept1_id = self.graph.add_concept("概念1")
        concept2_id = self.graph.add_concept("概念2")
        conn_id = self.graph.add_connection(concept1_id, concept2_id)
        
        self.assertEqual(len(self.graph.connections), 1)
        
        self.graph.remove_connection(conn_id)
        
        self.assertEqual(len(self.graph.connections), 0)
        # 检查邻接表是否也更新了
        self.assertEqual(len(self.graph.adjacency_list[concept1_id]), 0)
        self.assertEqual(len(self.graph.adjacency_list[concept2_id]), 0)
    
    def test_remove_nonexistent_connection(self):
        """测试移除不存在的连接"""
        self.graph.remove_connection("nonexistent")
        self.assertEqual(len(self.graph.connections), 0)
    
    def test_remove_memory(self):
        """测试移除记忆"""
        concept_id = self.graph.add_concept("测试")
        memory_id = self.graph.add_memory("记忆", concept_id)
        
        self.assertIn(memory_id, self.graph.memories)
        
        self.graph.remove_memory(memory_id)
        
        self.assertNotIn(memory_id, self.graph.memories)
    
    def test_remove_nonexistent_memory(self):
        """测试移除不存在的记忆"""
        self.graph.remove_memory("nonexistent")
        self.assertEqual(len(self.graph.memories), 0)
    
    def test_update_memory(self):
        """测试更新记忆"""
        concept_id = self.graph.add_concept("测试")
        memory_id = self.graph.add_memory("原始内容", concept_id)
        
        success = self.graph.update_memory(
            memory_id,
            content="新内容",
            details="新详情",
            strength=0.5
        )
        
        self.assertTrue(success)
        memory = self.graph.memories[memory_id]
        self.assertEqual(memory.content, "新内容")
        self.assertEqual(memory.details, "新详情")
        self.assertEqual(memory.strength, 0.5)
    
    def test_update_nonexistent_memory(self):
        """测试更新不存在的记忆"""
        success = self.graph.update_memory("nonexistent", content="新内容")
        self.assertFalse(success)
    
    def test_update_memory_with_none_values(self):
        """测试使用 None 值更新记忆（应忽略）"""
        concept_id = self.graph.add_concept("测试")
        memory_id = self.graph.add_memory("原始内容", concept_id, details="原始详情")
        
        self.graph.update_memory(memory_id, content=None, details="新详情")
        
        memory = self.graph.memories[memory_id]
        self.assertEqual(memory.content, "原始内容")  # 未改变
        self.assertEqual(memory.details, "新详情")  # 已改变
    
    def test_set_connection_strength(self):
        """测试设置连接强度"""
        concept1_id = self.graph.add_concept("概念1")
        concept2_id = self.graph.add_concept("概念2")
        conn_id = self.graph.add_connection(concept1_id, concept2_id)
        
        success = self.graph.set_connection_strength(conn_id, 0.7)
        
        self.assertTrue(success)
        self.assertEqual(self.graph.connections[0].strength, 0.7)
        # 检查邻接表是否也更新
        neighbors1 = self.graph.adjacency_list[concept1_id]
        neighbors2 = self.graph.adjacency_list[concept2_id]
        self.assertIn((concept2_id, 0.7), neighbors1)
        self.assertIn((concept1_id, 0.7), neighbors2)
    
    def test_set_nonexistent_connection_strength(self):
        """测试设置不存在的连接强度"""
        success = self.graph.set_connection_strength("nonexistent", 0.5)
        self.assertFalse(success)
    
    def test_remove_concept(self):
        """测试删除概念及其相关数据"""
        concept1_id = self.graph.add_concept("概念1")
        concept2_id = self.graph.add_concept("概念2")
        memory_id = self.graph.add_memory("记忆", concept1_id)
        conn_id = self.graph.add_connection(concept1_id, concept2_id)
        
        success = self.graph.remove_concept(concept1_id)
        
        self.assertTrue(success)
        self.assertNotIn(concept1_id, self.graph.concepts)
        self.assertNotIn(memory_id, self.graph.memories)
        self.assertEqual(len(self.graph.connections), 0)
        self.assertNotIn(concept1_id, self.graph.adjacency_list)
    
    def test_remove_nonexistent_concept(self):
        """测试删除不存在的概念"""
        success = self.graph.remove_concept("nonexistent")
        self.assertFalse(success)
    
    def test_get_neighbors(self):
        """测试获取邻居节点"""
        concept1_id = self.graph.add_concept("概念1")
        concept2_id = self.graph.add_concept("概念2")
        concept3_id = self.graph.add_concept("概念3")
        
        self.graph.add_connection(concept1_id, concept2_id, strength=0.8)
        self.graph.add_connection(concept1_id, concept3_id, strength=0.6)
        
        neighbors = self.graph.get_neighbors(concept1_id)
        
        self.assertEqual(len(neighbors), 2)
        self.assertIn((concept2_id, 0.8), neighbors)
        self.assertIn((concept3_id, 0.6), neighbors)
    
    def test_get_neighbors_nonexistent(self):
        """测试获取不存在节点的邻居"""
        neighbors = self.graph.get_neighbors("nonexistent")
        self.assertEqual(neighbors, [])
    
    def test_add_connection_creates_adjacency_list_entries(self):
        """测试添加连接时创建邻接表条目"""
        # 手动创建概念但不初始化邻接表
        concept1 = Concept(id="c1", name="概念1")
        concept2 = Concept(id="c2", name="概念2")
        self.graph.concepts["c1"] = concept1
        self.graph.concepts["c2"] = concept2
        
        # 添加连接应该创建邻接表条目
        self.graph.add_connection("c1", "c2")
        
        self.assertIn("c1", self.graph.adjacency_list)
        self.assertIn("c2", self.graph.adjacency_list)
    
    def test_add_memory_without_embedding_cache(self):
        """测试不带嵌入缓存的记忆添加"""
        # 确保没有嵌入缓存
        self.assertFalse(hasattr(self.graph, 'embedding_cache'))
        
        concept_id = self.graph.add_concept("测试")
        memory_id = self.graph.add_memory("记忆", concept_id)
        
        # 验证记忆已添加
        self.assertIn(memory_id, self.graph.memories)


if __name__ == '__main__':
    unittest.main()
