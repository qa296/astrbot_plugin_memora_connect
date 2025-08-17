"""
AstrBot 记忆插件测试用例
"""

import asyncio
import pytest
import sqlite3
import tempfile
import os
from unittest.mock import Mock, AsyncMock
from main import MemorySystem, MemoryGraph, Concept, Memory, Connection


class TestMemorySystem:
    """测试记忆系统核心功能"""
    
    def setup_method(self):
        """测试前设置"""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        
        mock_context = Mock()
        mock_context.get_using_provider.return_value = None
        
        self.memory_system = MemorySystem(mock_context)
        self.memory_system.db_path = self.temp_db.name
        
    def teardown_method(self):
        """测试后清理"""
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)
    
    async def test_memory_formation(self):
        """测试记忆形成"""
        # 模拟消息事件
        mock_event = Mock()
        mock_event.unified_msg_origin = "test_user"
        mock_event.message_str = "我今天去了图书馆，看了一本关于人工智能的书"
        
        # 模拟对话历史
        mock_conversation = Mock()
        mock_conversation.history = json.dumps([
            {"role": "user", "content": "我今天去了图书馆"},
            {"role": "user", "content": "看了一本关于人工智能的书"}
        ])
        
        mock_context = Mock()
        mock_context.conversation_manager.get_curr_conversation_id.return_value = "test_cid"
        mock_context.conversation_manager.get_conversation.return_value = mock_conversation
        
        self.memory_system.context = mock_context
        
        # 测试主题提取
        themes = await self.memory_system.extract_themes(["我今天去了图书馆", "看了一本关于人工智能的书"])
        assert "图书馆" in themes or "人工智能" in themes
        
    async def test_memory_recall(self):
        """测试记忆回忆"""
        # 添加测试记忆
        concept_id = self.memory_system.memory_graph.add_concept("测试主题")
        self.memory_system.memory_graph.add_memory("这是一条测试记忆", concept_id)
        
        # 测试回忆
        memories = await self.memory_system.recall_memories("测试", Mock())
        assert len(memories) > 0
        assert "测试记忆" in memories[0]
    
    def test_memory_graph_operations(self):
        """测试记忆图操作"""
        graph = MemoryGraph()
        
        # 测试添加概念
        concept_id = graph.add_concept("测试概念")
        assert concept_id in graph.concepts
        assert graph.concepts[concept_id].name == "测试概念"
        
        # 测试添加记忆
        memory_id = graph.add_memory("测试记忆内容", concept_id)
        assert memory_id in graph.memories
        assert graph.memories[memory_id].content == "测试记忆内容"
        
        # 测试添加连接
        concept2_id = graph.add_concept("测试概念2")
        conn_id = graph.add_connection(concept_id, concept2_id)
        assert len(graph.connections) == 1
        assert graph.connections[0].strength == 1.0
    
    async def test_database_operations(self):
        """测试数据库操作"""
        # 初始化数据库
        await self.memory_system.initialize()
        
        # 添加测试数据
        concept_id = self.memory_system.memory_graph.add_concept("数据库测试")
        self.memory_system.memory_graph.add_memory("数据库测试记忆", concept_id)
        
        # 保存到数据库
        await self.memory_system.save_memory_state()
        
        # 验证数据已保存
        conn = sqlite3.connect(self.temp_db.name)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM concepts WHERE name = '数据库测试'")
        result = cursor.fetchone()
        assert result is not None
        
        cursor.execute("SELECT * FROM memories WHERE content = '数据库测试记忆'")
        result = cursor.fetchone()
        assert result is not None
        
        conn.close()
    
    async def test_forgetting_mechanism(self):
        """测试遗忘机制"""
        # 添加旧记忆
        old_time = time.time() - 40 * 24 * 3600  # 40天前
        concept_id = self.memory_system.memory_graph.add_concept("旧概念")
        memory = Memory("old_memory", concept_id, "旧记忆")
        memory.created_at = old_time
        memory.last_accessed = old_time
        memory.strength = 0.5
        self.memory_system.memory_graph.memories["old_memory"] = memory
        
        # 执行遗忘
        await self.memory_system.forget_memories()
        
        # 验证记忆被削弱
        assert memory.strength < 0.5
    
    async def test_consolidation_mechanism(self):
        """测试记忆整理机制"""
        # 添加相似记忆
        concept_id = self.memory_system.memory_graph.add_concept("整理测试")
        
        for i in range(15):  # 超过最大限制
            self.memory_system.memory_graph.add_memory(f"相似记忆{i}", concept_id)
        
        # 执行整理
        await self.memory_system.consolidate_memories()
        
        # 验证记忆数量减少
        concept_memories = [m for m in self.memory_system.memory_graph.memories.values() 
                          if m.concept_id == concept_id]
        assert len(concept_memories) <= self.memory_system.memory_config["max_memories_per_topic"]
    
    def test_theme_extraction(self):
        """测试主题提取"""
        history = [
            "我今天去了图书馆",
            "看了一本关于人工智能的书",
            "人工智能真的很有趣"
        ]
        
        # 运行主题提取
        themes = asyncio.run(self.memory_system.extract_themes(history))
        
        # 验证提取结果
        assert isinstance(themes, list)
        assert len(themes) > 0
        assert all(isinstance(theme, str) for theme in themes)


class TestMemoryGraph:
    """测试记忆图数据结构"""
    
    def test_concept_creation(self):
        """测试概念创建"""
        concept = Concept("test_id", "测试概念")
        assert concept.id == "test_id"
        assert concept.name == "测试概念"
        assert concept.created_at is not None
        assert concept.last_accessed is not None
    
    def test_memory_creation(self):
        """测试记忆创建"""
        memory = Memory("test_id", "concept_id", "测试记忆")
        assert memory.id == "test_id"
        assert memory.concept_id == "concept_id"
        assert memory.content == "测试记忆"
        assert memory.created_at is not None
    
    def test_connection_creation(self):
        """测试连接创建"""
        connection = Connection("test_id", "from", "to")
        assert connection.id == "test_id"
        assert connection.from_concept == "from"
        assert connection.to_concept == "to"
        assert connection.strength == 1.0
    
    def test_memory_similarity(self):
        """测试记忆相似度判断"""
        mem1 = Memory("1", "c1", "我喜欢喝咖啡")
        mem2 = Memory("2", "c1", "我非常喜欢喝咖啡")
        
        memory_system = MemorySystem(Mock())
        assert memory_system.are_memories_similar(mem1, mem2) == True
        
        mem3 = Memory("3", "c1", "今天天气很好")
        assert memory_system.are_memories_similar(mem1, mem3) == False


class TestIntegration:
    """集成测试"""
    
    async def test_full_memory_lifecycle(self):
        """测试完整的记忆生命周期"""
        # 创建临时数据库
        temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        temp_db.close()
        
        try:
            # 初始化系统
            mock_context = Mock()
            memory_system = MemorySystem(mock_context)
            memory_system.db_path = temp_db.name
            
            await memory_system.initialize()
            
            # 模拟对话
            mock_event = Mock()
            mock_event.unified_msg_origin = "test_user"
            mock_event.message_str = "今天学习了Python编程，感觉很有趣"
            
            mock_conversation = Mock()
            mock_conversation.history = json.dumps([
                {"role": "user", "content": "今天学习了Python"},
                {"role": "user", "content": "感觉编程很有趣"}
            ])
            
            mock_context.conversation_manager.get_curr_conversation_id.return_value = "test_cid"
            mock_context.conversation_manager.get_conversation.return_value = mock_conversation
            
            # 处理消息
            await memory_system.process_message(mock_event)
            
            # 验证记忆形成
            assert len(memory_system.memory_graph.concepts) > 0
            assert len(memory_system.memory_graph.memories) > 0
            
            # 测试回忆
            memories = await memory_system.recall_memories("Python", mock_event)
            assert len(memories) > 0
            
            # 保存状态
            await memory_system.save_memory_state()
            
            # 验证数据库
            conn = sqlite3.connect(temp_db.name)
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM concepts")
            concept_count = cursor.fetchone()[0]
            assert concept_count > 0
            
            cursor.execute("SELECT COUNT(*) FROM memories")
            memory_count = cursor.fetchone()[0]
            assert memory_count > 0
            
            conn.close()
            
        finally:
            if os.path.exists(temp_db.name):
                os.unlink(temp_db.name)


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])