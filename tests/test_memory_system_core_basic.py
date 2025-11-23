"""测试记忆系统核心基础功能"""
import pytest
import sqlite3
import tempfile
import os
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from models import Concept, Memory, Connection


class TestMemorySystemStaticMethods:
    """测试MemorySystem的静态方法"""
    
    def test_filter_memories_by_group_private_chat(self):
        """测试私聊场景的记忆过滤"""
        from memory_system_core import MemorySystem
        
        memories = [
            Memory(id="m1", concept_id="c1", content="私聊记忆", group_id=""),
            Memory(id="m2", concept_id="c2", content="群聊记忆", group_id="group1"),
            Memory(id="m3", concept_id="c3", content="私聊记忆2"),
        ]
        
        result = MemorySystem.filter_memories_by_group(memories, "")
        
        # 应该只返回没有group_id的记忆
        assert len(result) == 2
        assert all(not m.group_id for m in result)
    
    def test_filter_memories_by_group_group_chat(self):
        """测试群聊场景的记忆过滤"""
        from memory_system_core import MemorySystem
        
        memories = [
            Memory(id="m1", concept_id="c1", content="私聊记忆", group_id=""),
            Memory(id="m2", concept_id="c2", content="群1记忆", group_id="group1"),
            Memory(id="m3", concept_id="c3", content="群2记忆", group_id="group2"),
        ]
        
        result = MemorySystem.filter_memories_by_group(memories, "group1")
        
        # 应该只返回group_id为group1的记忆
        assert len(result) == 1
        assert result[0].group_id == "group1"
    
    def test_filter_concepts_by_group_private_chat(self):
        """测试私聊场景的概念过滤"""
        from memory_system_core import MemorySystem
        
        concepts = {
            "c1": Concept(id="c1", name="概念1"),
            "c2": Concept(id="c2", name="概念2"),
            "c3": Concept(id="c3", name="概念3"),
        }
        
        memories = {
            "m1": Memory(id="m1", concept_id="c1", content="私聊记忆", group_id=""),
            "m2": Memory(id="m2", concept_id="c2", content="群聊记忆", group_id="group1"),
        }
        
        result = MemorySystem.filter_concepts_by_group(concepts, memories, "")
        
        # 应该只返回有私聊记忆的概念
        assert len(result) == 1
        assert "c1" in result
    
    def test_filter_concepts_by_group_group_chat(self):
        """测试群聊场景的概念过滤"""
        from memory_system_core import MemorySystem
        
        concepts = {
            "c1": Concept(id="c1", name="概念1"),
            "c2": Concept(id="c2", name="概念2"),
            "c3": Concept(id="c3", name="概念3"),
        }
        
        memories = {
            "m1": Memory(id="m1", concept_id="c1", content="私聊记忆", group_id=""),
            "m2": Memory(id="m2", concept_id="c2", content="群1记忆", group_id="group1"),
            "m3": Memory(id="m3", concept_id="c3", content="群2记忆", group_id="group2"),
        }
        
        result = MemorySystem.filter_concepts_by_group(concepts, memories, "group1")
        
        # 应该只返回有group1记忆的概念
        assert len(result) == 1
        assert "c2" in result
    
    def test_filter_concepts_by_group_no_matching_memories(self):
        """测试没有匹配记忆的概念过滤"""
        from memory_system_core import MemorySystem
        
        concepts = {
            "c1": Concept(id="c1", name="概念1"),
            "c2": Concept(id="c2", name="概念2"),
        }
        
        memories = {
            "m1": Memory(id="m1", concept_id="c3", content="其他记忆", group_id=""),
        }
        
        result = MemorySystem.filter_concepts_by_group(concepts, memories, "")
        
        # 应该返回空字典
        assert len(result) == 0


class TestMemorySystemInit:
    """测试MemorySystem初始化"""
    
    def test_init_disabled(self):
        """测试禁用时的初始化"""
        from memory_system_core import MemorySystem
        
        mock_context = Mock()
        config = {"enable_memory_system": False}
        
        with tempfile.TemporaryDirectory() as tmpdir:
            system = MemorySystem(
                context=mock_context,
                config=config,
                data_dir=tmpdir
            )
            
            assert system.memory_system_enabled is False
    
    def test_init_enabled(self):
        """测试启用时的初始化"""
        from memory_system_core import MemorySystem
        import pathlib
        
        mock_context = Mock()
        config = {"enable_memory_system": True}
        
        with tempfile.TemporaryDirectory() as tmpdir:
            data_path = pathlib.Path(tmpdir)
            system = MemorySystem(
                context=mock_context,
                config=config,
                data_dir=data_path
            )
            
            assert system.memory_system_enabled is True
            assert system.memory_graph is not None
            assert system.batch_extractor is not None
            assert os.path.exists(os.path.dirname(system.db_path))


class TestMemorySystemDatabase:
    """测试MemorySystem数据库操作"""
    
    @pytest.fixture
    def memory_system(self, temp_db):
        """创建测试用的记忆系统"""
        from memory_system_core import MemorySystem
        import pathlib
        
        mock_context = Mock()
        config = {"enable_memory_system": True}
        
        # 创建临时目录
        tmpdir = os.path.dirname(temp_db)
        data_path = pathlib.Path(tmpdir)
        
        system = MemorySystem(
            context=mock_context,
            config=config,
            data_dir=data_path
        )
        
        # 覆盖db_path为测试数据库
        system.db_path = temp_db
        
        return system
    
    def test_memory_graph_exists(self, memory_system):
        """测试记忆图对象存在"""
        assert memory_system.memory_graph is not None
        assert hasattr(memory_system, 'db_path')
        assert memory_system.db_path is not None


class TestMemorySystemGroupIsolation:
    """测试群聊隔离功能"""
    
    @pytest.fixture
    def memory_system(self, temp_db):
        """创建测试用的记忆系统"""
        from memory_system_core import MemorySystem
        import pathlib
        
        mock_context = Mock()
        config = {"enable_memory_system": True}
        
        tmpdir = os.path.dirname(temp_db)
        data_path = pathlib.Path(tmpdir)
        
        system = MemorySystem(
            context=mock_context,
            config=config,
            data_dir=data_path
        )
        
        system.db_path = temp_db
        
        return system
    
    def test_add_memory_with_group_id(self, memory_system):
        """测试添加带group_id的记忆"""
        concept_id = memory_system.memory_graph.add_concept("群聊概念")
        
        memory_id = memory_system.memory_graph.add_memory(
            content="群聊记忆",
            concept_id=concept_id,
            group_id="group123"
        )
        
        memory = memory_system.memory_graph.memories[memory_id]
        assert memory.group_id == "group123"
    
    def test_filter_memories_by_different_groups_static(self):
        """测试不同群组记忆的过滤（使用静态方法）"""
        from memory_system_core import MemorySystem
        from models import Memory
        
        # 创建测试记忆
        m1 = Memory(id="m1", concept_id="c1", content="群1记忆", group_id="group1")
        m2 = Memory(id="m2", concept_id="c1", content="群2记忆", group_id="group2")
        m3 = Memory(id="m3", concept_id="c1", content="私聊记忆", group_id="")
        
        all_memories = [m1, m2, m3]
        
        # 测试群1过滤
        group1_memories = MemorySystem.filter_memories_by_group(all_memories, "group1")
        assert len(group1_memories) == 1
        assert group1_memories[0].content == "群1记忆"
        
        # 测试私聊过滤
        private_memories = MemorySystem.filter_memories_by_group(all_memories, "")
        assert len(private_memories) == 1
        assert private_memories[0].content == "私聊记忆"


class TestMemorySystemLLMProvider:
    """测试LLM提供商相关功能"""
    
    @pytest.mark.asyncio
    async def test_get_llm_provider_not_set(self, temp_db):
        """测试获取未设置的LLM提供商"""
        from memory_system_core import MemorySystem
        import pathlib
        
        mock_context = Mock()
        config = {"enable_memory_system": True}
        
        tmpdir = os.path.dirname(temp_db)
        data_path = pathlib.Path(tmpdir)
        
        system = MemorySystem(
            context=mock_context,
            config=config,
            data_dir=data_path
        )
        
        provider = await system.get_llm_provider()
        assert provider is None
    
    @pytest.mark.asyncio
    async def test_llm_provider_attribute_exists(self, temp_db):
        """测试llm_provider属性存在"""
        from memory_system_core import MemorySystem
        import pathlib
        
        mock_context = Mock()
        config = {"enable_memory_system": True}
        
        tmpdir = os.path.dirname(temp_db)
        data_path = pathlib.Path(tmpdir)
        
        system = MemorySystem(
            context=mock_context,
            config=config,
            data_dir=data_path
        )
        
        assert hasattr(system, 'llm_provider')
        assert system.llm_provider is None
    
    @pytest.mark.asyncio
    async def test_embedding_provider_attribute_exists(self, temp_db):
        """测试embedding_provider属性存在"""
        from memory_system_core import MemorySystem
        import pathlib
        
        mock_context = Mock()
        config = {"enable_memory_system": True}
        
        tmpdir = os.path.dirname(temp_db)
        data_path = pathlib.Path(tmpdir)
        
        system = MemorySystem(
            context=mock_context,
            config=config,
            data_dir=data_path
        )
        
        assert hasattr(system, 'embedding_provider')
        assert system.embedding_provider is None
