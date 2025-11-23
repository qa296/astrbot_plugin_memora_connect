"""测试记忆图数据结构"""
import pytest
import time
from memory_graph import MemoryGraph
from models import Concept, Memory, Connection


class TestMemoryGraph:
    """测试MemoryGraph类"""
    
    def test_graph_initialization(self):
        """测试图初始化"""
        graph = MemoryGraph()
        assert isinstance(graph.concepts, dict)
        assert isinstance(graph.memories, dict)
        assert isinstance(graph.connections, list)
        assert isinstance(graph.adjacency_list, dict)
        assert len(graph.concepts) == 0
        assert len(graph.memories) == 0
        assert len(graph.connections) == 0
    
    def test_add_concept_with_auto_id(self):
        """测试添加概念（自动生成ID）"""
        graph = MemoryGraph()
        concept_id = graph.add_concept("测试概念")
        
        assert concept_id in graph.concepts
        assert graph.concepts[concept_id].name == "测试概念"
        assert concept_id in graph.adjacency_list
    
    def test_add_concept_with_custom_id(self):
        """测试添加概念（自定义ID）"""
        graph = MemoryGraph()
        concept_id = graph.add_concept("自定义概念", concept_id="custom_c1")
        
        assert concept_id == "custom_c1"
        assert "custom_c1" in graph.concepts
        assert graph.concepts["custom_c1"].name == "自定义概念"
    
    def test_add_concept_with_all_params(self):
        """测试添加概念（所有参数）"""
        graph = MemoryGraph()
        created = time.time() - 1000
        accessed = time.time() - 500
        
        concept_id = graph.add_concept(
            "完整概念",
            concept_id="full_c1",
            created_at=created,
            last_accessed=accessed,
            access_count=10
        )
        
        concept = graph.concepts[concept_id]
        assert concept.name == "完整概念"
        assert concept.created_at == created
        assert concept.last_accessed == accessed
        assert concept.access_count == 10
    
    def test_add_duplicate_concept(self):
        """测试添加重复概念（不会重复添加）"""
        graph = MemoryGraph()
        concept_id = graph.add_concept("重复概念", concept_id="dup_c1")
        concept_id2 = graph.add_concept("重复概念", concept_id="dup_c1")
        
        assert concept_id == concept_id2
        assert len(graph.concepts) == 1
    
    def test_add_memory_with_auto_id(self):
        """测试添加记忆（自动生成ID）"""
        graph = MemoryGraph()
        concept_id = graph.add_concept("概念1")
        memory_id = graph.add_memory("测试记忆", concept_id)
        
        assert memory_id in graph.memories
        assert graph.memories[memory_id].content == "测试记忆"
        assert graph.memories[memory_id].concept_id == concept_id
    
    def test_add_memory_with_all_params(self):
        """测试添加记忆（所有参数）"""
        graph = MemoryGraph()
        concept_id = graph.add_concept("概念2")
        created = time.time() - 2000
        accessed = time.time() - 1000
        
        memory_id = graph.add_memory(
            content="完整记忆",
            concept_id=concept_id,
            memory_id="full_m1",
            details="详细描述",
            participants="用户1,用户2",
            location="北京",
            emotion="开心",
            tags="标签1,标签2",
            created_at=created,
            last_accessed=accessed,
            access_count=5,
            strength=0.9,
            group_id="group1"
        )
        
        memory = graph.memories[memory_id]
        assert memory.content == "完整记忆"
        assert memory.details == "详细描述"
        assert memory.participants == "用户1,用户2"
        assert memory.location == "北京"
        assert memory.emotion == "开心"
        assert memory.tags == "标签1,标签2"
        assert memory.created_at == created
        assert memory.last_accessed == accessed
        assert memory.access_count == 5
        assert memory.strength == 0.9
        assert memory.group_id == "group1"
    
    def test_add_connection_new(self):
        """测试添加新连接"""
        graph = MemoryGraph()
        c1 = graph.add_concept("概念1", concept_id="c1")
        c2 = graph.add_concept("概念2", concept_id="c2")
        
        conn_id = graph.add_connection(c1, c2, strength=0.8)
        
        assert len(graph.connections) == 1
        assert graph.connections[0].from_concept == c1
        assert graph.connections[0].to_concept == c2
        assert graph.connections[0].strength == 0.8
        
        # 检查邻接表
        assert (c2, 0.8) in graph.adjacency_list[c1]
        assert (c1, 0.8) in graph.adjacency_list[c2]
    
    def test_add_connection_duplicate_strengthens(self):
        """测试添加重复连接会加强现有连接"""
        graph = MemoryGraph()
        c1 = graph.add_concept("概念1", concept_id="c1")
        c2 = graph.add_concept("概念2", concept_id="c2")
        
        conn_id1 = graph.add_connection(c1, c2, strength=0.5)
        initial_strength = graph.connections[0].strength
        
        conn_id2 = graph.add_connection(c1, c2, strength=0.3)
        
        # 应该只有一个连接，且强度增加了0.1
        assert len(graph.connections) == 1
        assert graph.connections[0].strength == initial_strength + 0.1
        assert conn_id1 == conn_id2
    
    def test_add_connection_reverse_duplicate(self):
        """测试添加反向重复连接"""
        graph = MemoryGraph()
        c1 = graph.add_concept("概念1", concept_id="c1")
        c2 = graph.add_concept("概念2", concept_id="c2")
        
        conn_id1 = graph.add_connection(c1, c2, strength=0.5)
        initial_strength = graph.connections[0].strength
        
        # 反向添加
        conn_id2 = graph.add_connection(c2, c1, strength=0.3)
        
        # 应该只有一个连接，且强度增加
        assert len(graph.connections) == 1
        assert graph.connections[0].strength == initial_strength + 0.1
    
    def test_remove_connection(self):
        """测试移除连接"""
        graph = MemoryGraph()
        c1 = graph.add_concept("概念1", concept_id="c1")
        c2 = graph.add_concept("概念2", concept_id="c2")
        conn_id = graph.add_connection(c1, c2)
        
        assert len(graph.connections) == 1
        
        graph.remove_connection(conn_id)
        
        assert len(graph.connections) == 0
        # 检查邻接表已更新
        assert len([n for n, s in graph.adjacency_list[c1] if n == c2]) == 0
        assert len([n for n, s in graph.adjacency_list[c2] if n == c1]) == 0
    
    def test_remove_nonexistent_connection(self):
        """测试移除不存在的连接"""
        graph = MemoryGraph()
        # 不应该抛出异常
        graph.remove_connection("nonexistent_conn")
    
    def test_remove_memory(self):
        """测试移除记忆"""
        graph = MemoryGraph()
        concept_id = graph.add_concept("概念1")
        memory_id = graph.add_memory("记忆1", concept_id)
        
        assert memory_id in graph.memories
        
        graph.remove_memory(memory_id)
        
        assert memory_id not in graph.memories
    
    def test_remove_nonexistent_memory(self):
        """测试移除不存在的记忆"""
        graph = MemoryGraph()
        # 不应该抛出异常
        graph.remove_memory("nonexistent_memory")
    
    def test_update_memory_success(self):
        """测试成功更新记忆"""
        graph = MemoryGraph()
        concept_id = graph.add_concept("概念1")
        memory_id = graph.add_memory("原始内容", concept_id)
        
        success = graph.update_memory(
            memory_id,
            content="新内容",
            details="新详情",
            strength=0.7
        )
        
        assert success is True
        memory = graph.memories[memory_id]
        assert memory.content == "新内容"
        assert memory.details == "新详情"
        assert memory.strength == 0.7
    
    def test_update_memory_nonexistent(self):
        """测试更新不存在的记忆"""
        graph = MemoryGraph()
        success = graph.update_memory("nonexistent_memory", content="新内容")
        assert success is False
    
    def test_update_memory_ignored_fields(self):
        """测试更新记忆时忽略不允许的字段"""
        graph = MemoryGraph()
        concept_id = graph.add_concept("概念1")
        memory_id = graph.add_memory("原始内容", concept_id)
        original_memory = graph.memories[memory_id]
        
        # 尝试更新不允许的字段
        success = graph.update_memory(
            memory_id,
            content="新内容",
            invalid_field="应该被忽略"
        )
        
        assert success is True
        assert graph.memories[memory_id].content == "新内容"
        assert not hasattr(graph.memories[memory_id], "invalid_field")
    
    def test_set_connection_strength_success(self):
        """测试成功设置连接强度"""
        graph = MemoryGraph()
        c1 = graph.add_concept("概念1", concept_id="c1")
        c2 = graph.add_concept("概念2", concept_id="c2")
        conn_id = graph.add_connection(c1, c2, strength=0.5)
        
        success = graph.set_connection_strength(conn_id, 0.9)
        
        assert success is True
        assert graph.connections[0].strength == 0.9
        
        # 检查邻接表已更新
        neighbors_c1 = dict(graph.adjacency_list[c1])
        neighbors_c2 = dict(graph.adjacency_list[c2])
        assert neighbors_c1[c2] == 0.9
        assert neighbors_c2[c1] == 0.9
    
    def test_set_connection_strength_nonexistent(self):
        """测试设置不存在的连接强度"""
        graph = MemoryGraph()
        success = graph.set_connection_strength("nonexistent_conn", 0.9)
        assert success is False
    
    def test_remove_concept_success(self):
        """测试成功移除概念"""
        graph = MemoryGraph()
        c1 = graph.add_concept("概念1", concept_id="c1")
        c2 = graph.add_concept("概念2", concept_id="c2")
        
        # 添加记忆和连接
        m1 = graph.add_memory("记忆1", c1)
        conn_id = graph.add_connection(c1, c2)
        
        success = graph.remove_concept(c1)
        
        assert success is True
        assert c1 not in graph.concepts
        assert m1 not in graph.memories
        assert len(graph.connections) == 0
        assert c1 not in graph.adjacency_list
    
    def test_remove_concept_nonexistent(self):
        """测试移除不存在的概念"""
        graph = MemoryGraph()
        success = graph.remove_concept("nonexistent_concept")
        assert success is False
    
    def test_get_neighbors(self):
        """测试获取邻居"""
        graph = MemoryGraph()
        c1 = graph.add_concept("概念1", concept_id="c1")
        c2 = graph.add_concept("概念2", concept_id="c2")
        c3 = graph.add_concept("概念3", concept_id="c3")
        
        graph.add_connection(c1, c2, strength=0.8)
        graph.add_connection(c1, c3, strength=0.6)
        
        neighbors = graph.get_neighbors(c1)
        
        assert len(neighbors) == 2
        assert (c2, 0.8) in neighbors
        assert (c3, 0.6) in neighbors
    
    def test_get_neighbors_no_neighbors(self):
        """测试获取没有邻居的概念"""
        graph = MemoryGraph()
        c1 = graph.add_concept("概念1", concept_id="c1")
        
        neighbors = graph.get_neighbors(c1)
        
        assert len(neighbors) == 0
    
    def test_get_neighbors_nonexistent_concept(self):
        """测试获取不存在概念的邻居"""
        graph = MemoryGraph()
        neighbors = graph.get_neighbors("nonexistent_concept")
        assert len(neighbors) == 0
