"""
测试数据模型
"""
import unittest
import time
from models import Concept, Memory, Connection


class TestConcept(unittest.TestCase):
    """测试 Concept 类"""
    
    def test_concept_creation(self):
        """测试概念创建"""
        concept = Concept(id="test_1", name="测试概念")
        self.assertEqual(concept.id, "test_1")
        self.assertEqual(concept.name, "测试概念")
        self.assertIsNotNone(concept.created_at)
        self.assertIsNotNone(concept.last_accessed)
        self.assertEqual(concept.access_count, 0)
    
    def test_concept_with_custom_times(self):
        """测试带自定义时间的概念"""
        custom_time = 1609459200.0  # 2021-01-01
        concept = Concept(
            id="test_2",
            name="自定义时间概念",
            created_at=custom_time,
            last_accessed=custom_time,
            access_count=5
        )
        self.assertEqual(concept.created_at, custom_time)
        self.assertEqual(concept.last_accessed, custom_time)
        self.assertEqual(concept.access_count, 5)
    
    def test_concept_post_init(self):
        """测试 __post_init__ 方法"""
        concept = Concept(id="test_3", name="测试")
        before = time.time()
        self.assertLessEqual(concept.created_at, before)
        self.assertLessEqual(concept.last_accessed, before)


class TestMemory(unittest.TestCase):
    """测试 Memory 类"""
    
    def test_memory_creation(self):
        """测试记忆创建"""
        memory = Memory(
            id="mem_1",
            concept_id="concept_1",
            content="这是一段记忆"
        )
        self.assertEqual(memory.id, "mem_1")
        self.assertEqual(memory.concept_id, "concept_1")
        self.assertEqual(memory.content, "这是一段记忆")
        self.assertEqual(memory.details, "")
        self.assertEqual(memory.participants, "")
        self.assertEqual(memory.location, "")
        self.assertEqual(memory.emotion, "")
        self.assertEqual(memory.tags, "")
        self.assertEqual(memory.strength, 1.0)
        self.assertEqual(memory.group_id, "")
        self.assertIsNotNone(memory.created_at)
        self.assertIsNotNone(memory.last_accessed)
    
    def test_memory_with_full_details(self):
        """测试带完整详情的记忆"""
        memory = Memory(
            id="mem_2",
            concept_id="concept_2",
            content="完整记忆",
            details="详细描述",
            participants="张三, 李四",
            location="北京",
            emotion="开心",
            tags="标签1, 标签2",
            strength=0.8,
            group_id="group_123",
            access_count=3
        )
        self.assertEqual(memory.details, "详细描述")
        self.assertEqual(memory.participants, "张三, 李四")
        self.assertEqual(memory.location, "北京")
        self.assertEqual(memory.emotion, "开心")
        self.assertEqual(memory.tags, "标签1, 标签2")
        self.assertEqual(memory.strength, 0.8)
        self.assertEqual(memory.group_id, "group_123")
        self.assertEqual(memory.access_count, 3)
    
    def test_memory_post_init(self):
        """测试记忆的 __post_init__ 方法"""
        memory = Memory(id="mem_3", concept_id="concept_3", content="测试")
        before = time.time()
        self.assertLessEqual(memory.created_at, before)
        self.assertLessEqual(memory.last_accessed, before)


class TestConnection(unittest.TestCase):
    """测试 Connection 类"""
    
    def test_connection_creation(self):
        """测试连接创建"""
        conn = Connection(
            id="conn_1",
            from_concept="concept_1",
            to_concept="concept_2"
        )
        self.assertEqual(conn.id, "conn_1")
        self.assertEqual(conn.from_concept, "concept_1")
        self.assertEqual(conn.to_concept, "concept_2")
        self.assertEqual(conn.strength, 1.0)
        self.assertIsNotNone(conn.last_strengthened)
    
    def test_connection_with_custom_strength(self):
        """测试带自定义强度的连接"""
        custom_time = 1609459200.0
        conn = Connection(
            id="conn_2",
            from_concept="concept_3",
            to_concept="concept_4",
            strength=0.5,
            last_strengthened=custom_time
        )
        self.assertEqual(conn.strength, 0.5)
        self.assertEqual(conn.last_strengthened, custom_time)
    
    def test_connection_post_init(self):
        """测试连接的 __post_init__ 方法"""
        conn = Connection(
            id="conn_3",
            from_concept="concept_5",
            to_concept="concept_6"
        )
        before = time.time()
        self.assertLessEqual(conn.last_strengthened, before)


if __name__ == '__main__':
    unittest.main()
