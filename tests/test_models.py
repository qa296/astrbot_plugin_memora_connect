"""测试数据模型"""
import pytest
import time
from models import Concept, Memory, Connection


class TestConcept:
    """测试Concept类"""
    
    def test_concept_creation_with_defaults(self):
        """测试使用默认值创建概念"""
        concept = Concept(id="c1", name="测试概念")
        assert concept.id == "c1"
        assert concept.name == "测试概念"
        assert concept.created_at is not None
        assert concept.last_accessed is not None
        assert concept.access_count == 0
    
    def test_concept_creation_with_custom_values(self):
        """测试使用自定义值创建概念"""
        created = time.time() - 1000
        accessed = time.time() - 500
        concept = Concept(
            id="c2",
            name="自定义概念",
            created_at=created,
            last_accessed=accessed,
            access_count=5
        )
        assert concept.id == "c2"
        assert concept.name == "自定义概念"
        assert concept.created_at == created
        assert concept.last_accessed == accessed
        assert concept.access_count == 5
    
    def test_concept_post_init_creates_timestamps(self):
        """测试__post_init__自动创建时间戳"""
        before = time.time()
        concept = Concept(id="c3", name="时间戳测试")
        after = time.time()
        
        assert before <= concept.created_at <= after
        assert before <= concept.last_accessed <= after


class TestMemory:
    """测试Memory类"""
    
    def test_memory_creation_with_minimal_params(self):
        """测试使用最小参数创建记忆"""
        memory = Memory(id="m1", concept_id="c1", content="测试记忆")
        assert memory.id == "m1"
        assert memory.concept_id == "c1"
        assert memory.content == "测试记忆"
        assert memory.details == ""
        assert memory.participants == ""
        assert memory.location == ""
        assert memory.emotion == ""
        assert memory.tags == ""
        assert memory.strength == 1.0
        assert memory.group_id == ""
        assert memory.created_at is not None
        assert memory.last_accessed is not None
        assert memory.access_count == 0
    
    def test_memory_creation_with_all_params(self):
        """测试使用所有参数创建记忆"""
        created = time.time() - 2000
        accessed = time.time() - 1000
        memory = Memory(
            id="m2",
            concept_id="c2",
            content="完整记忆",
            details="详细描述",
            participants="用户1,用户2",
            location="北京",
            emotion="开心",
            tags="标签1,标签2",
            created_at=created,
            last_accessed=accessed,
            access_count=10,
            strength=0.8,
            group_id="group1"
        )
        assert memory.id == "m2"
        assert memory.concept_id == "c2"
        assert memory.content == "完整记忆"
        assert memory.details == "详细描述"
        assert memory.participants == "用户1,用户2"
        assert memory.location == "北京"
        assert memory.emotion == "开心"
        assert memory.tags == "标签1,标签2"
        assert memory.created_at == created
        assert memory.last_accessed == accessed
        assert memory.access_count == 10
        assert memory.strength == 0.8
        assert memory.group_id == "group1"
    
    def test_memory_post_init_creates_timestamps(self):
        """测试__post_init__自动创建时间戳"""
        before = time.time()
        memory = Memory(id="m3", concept_id="c3", content="时间戳测试")
        after = time.time()
        
        assert before <= memory.created_at <= after
        assert before <= memory.last_accessed <= after


class TestConnection:
    """测试Connection类"""
    
    def test_connection_creation_with_defaults(self):
        """测试使用默认值创建连接"""
        connection = Connection(
            id="conn1",
            from_concept="c1",
            to_concept="c2"
        )
        assert connection.id == "conn1"
        assert connection.from_concept == "c1"
        assert connection.to_concept == "c2"
        assert connection.strength == 1.0
        assert connection.last_strengthened is not None
    
    def test_connection_creation_with_custom_values(self):
        """测试使用自定义值创建连接"""
        strengthened = time.time() - 3000
        connection = Connection(
            id="conn2",
            from_concept="c3",
            to_concept="c4",
            strength=0.5,
            last_strengthened=strengthened
        )
        assert connection.id == "conn2"
        assert connection.from_concept == "c3"
        assert connection.to_concept == "c4"
        assert connection.strength == 0.5
        assert connection.last_strengthened == strengthened
    
    def test_connection_post_init_creates_timestamp(self):
        """测试__post_init__自动创建时间戳"""
        before = time.time()
        connection = Connection(
            id="conn3",
            from_concept="c5",
            to_concept="c6"
        )
        after = time.time()
        
        assert before <= connection.last_strengthened <= after
