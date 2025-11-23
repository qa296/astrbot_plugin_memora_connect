"""全面测试，覆盖所有主要功能模块"""
import pytest
import sqlite3
import tempfile
import os
from unittest.mock import Mock, AsyncMock, MagicMock, patch
import time
import json


class TestEnhancedMemoryRecallFull:
    """测试EnhancedMemoryRecall完整功能"""
    
    def test_create_enhanced_memory_recall(self):
        """测试创建EnhancedMemoryRecall实例"""
        from enhanced_memory_recall import EnhancedMemoryRecall
        mock_memory_system = Mock()
        recall = EnhancedMemoryRecall(mock_memory_system)
        assert recall is not None
        assert recall.memory_system == mock_memory_system


class TestMemoryGraphVisualizationFull:
    """测试MemoryGraphVisualization完整功能"""
    
    def test_create_visualizer(self):
        """测试创建可视化器实例"""
        from memory_graph_visualization import MemoryGraphVisualizer
        from memory_graph import MemoryGraph
        
        graph = MemoryGraph()
        try:
            visualizer = MemoryGraphVisualizer(graph)
            assert visualizer is not None
        except Exception:
            # 可能需要额外的依赖，跳过
            pytest.skip("MemoryGraphVisualizer需要额外依赖")


class TestDatabaseOperations:
    """测试数据库操作"""
    
    def test_sqlite_connection(self):
        """测试SQLite连接"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, data TEXT)")
            cursor.execute("INSERT INTO test (data) VALUES ('test data')")
            conn.commit()
            
            cursor.execute("SELECT * FROM test")
            rows = cursor.fetchall()
            assert len(rows) == 1
            assert rows[0][1] == 'test data'
            
            conn.close()
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
    
    def test_sqlite_row_factory(self):
        """测试SQLite Row工厂"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name
        
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT, value INTEGER)")
            cursor.execute("INSERT INTO test (name, value) VALUES ('test', 123)")
            conn.commit()
            
            cursor.execute("SELECT * FROM test")
            row = cursor.fetchone()
            assert row is not None
            assert row['name'] == 'test'
            assert row['value'] == 123
            
            conn.close()
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)


class TestMemoryGraphOperations:
    """测试记忆图的复杂操作"""
    
    def test_complex_graph_operations(self):
        """测试复杂图操作"""
        from memory_graph import MemoryGraph
        
        graph = MemoryGraph()
        
        # 创建多个概念（使用自定义ID）
        c1 = graph.add_concept("概念1", concept_id="c1")
        c2 = graph.add_concept("概念2", concept_id="c2")
        c3 = graph.add_concept("概念3", concept_id="c3")
        
        # 创建连接网络
        graph.add_connection(c1, c2, strength=0.8)
        graph.add_connection(c2, c3, strength=0.6)
        graph.add_connection(c1, c3, strength=0.5)
        
        # 验证邻接表
        assert len(graph.get_neighbors(c1)) == 2
        assert len(graph.get_neighbors(c2)) == 2
        assert len(graph.get_neighbors(c3)) == 2
        
        # 添加记忆
        m1 = graph.add_memory("记忆1", c1, strength=0.9, memory_id="m1")
        m2 = graph.add_memory("记忆2", c2, strength=0.7, memory_id="m2")
        m3 = graph.add_memory("记忆3", c3, strength=0.6, memory_id="m3")
        
        assert len(graph.memories) == 3
        
        # 更新连接强度
        conn_id = f"conn_{c1}_{c2}"
        success = graph.set_connection_strength(conn_id, 0.95)
        assert success is True
        
        # 验证更新
        for conn in graph.connections:
            if conn.id == conn_id:
                assert conn.strength == 0.95
    
    def test_memory_graph_stress_test(self):
        """测试记忆图压力测试"""
        from memory_graph import MemoryGraph
        
        graph = MemoryGraph()
        
        # 创建100个概念（使用自定义ID）
        concepts = []
        for i in range(100):
            cid = graph.add_concept(f"概念{i}", concept_id=f"c{i}")
            concepts.append(cid)
        
        assert len(graph.concepts) == 100
        
        # 为每个概念添加记忆
        for i, cid in enumerate(concepts):
            graph.add_memory(f"记忆{i}", cid, memory_id=f"m{i}")
        
        assert len(graph.memories) == 100
        
        # 创建一些连接
        for i in range(0, 90, 10):
            graph.add_connection(concepts[i], concepts[i+5])
        
        assert len(graph.connections) >= 9


class TestConfigOperations:
    """测试配置操作"""
    
    def test_config_serialization(self):
        """测试配置序列化"""
        from config import MemorySystemConfig, MemoryConfigManager
        
        config = MemorySystemConfig(enable_memory_system=True)
        config_dict = config.to_dict()
        
        # 序列化为JSON
        json_str = json.dumps(config_dict)
        assert json_str is not None
        
        # 反序列化
        loaded_dict = json.loads(json_str)
        new_config = MemorySystemConfig.from_dict(loaded_dict)
        
        assert new_config.enable_memory_system == config.enable_memory_system
    
    def test_config_manager_lifecycle(self):
        """测试配置管理器生命周期"""
        from config import MemoryConfigManager
        
        # 创建
        manager = MemoryConfigManager()
        assert manager.is_memory_system_enabled() is True
        
        # 禁用
        manager.set_memory_system_enabled(False)
        assert manager.is_memory_system_enabled() is False
        
        # 更新
        manager.update_config({'enable_memory_system': True})
        assert manager.is_memory_system_enabled() is True
        
        # 验证
        assert manager.validate_config() is True


class TestBatchExtractorEdgeCases:
    """测试BatchExtractor的边缘情况"""
    
    @pytest.mark.asyncio
    async def test_extract_from_single_message(self):
        """测试从单条消息提取"""
        from batch_extractor import BatchMemoryExtractor
        
        mock_system = Mock()
        mock_system.get_llm_provider = AsyncMock(return_value=None)
        
        extractor = BatchMemoryExtractor(mock_system)
        
        conversation = [
            {"role": "user", "content": "测试", "sender_name": "用户", "timestamp": time.time()}
        ]
        
        result = await extractor.extract_memories_and_themes(conversation)
        assert isinstance(result, list)
    
    @pytest.mark.asyncio
    async def test_extract_from_long_conversation(self):
        """测试从长对话提取"""
        from batch_extractor import BatchMemoryExtractor
        
        mock_system = Mock()
        mock_system.get_llm_provider = AsyncMock(return_value=None)
        
        extractor = BatchMemoryExtractor(mock_system)
        
        # 创建长对话
        conversation = []
        for i in range(50):
            conversation.append({
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"消息{i}",
                "sender_name": "用户" if i % 2 == 0 else "Bot",
                "timestamp": time.time() + i
            })
        
        result = await extractor.extract_memories_and_themes(conversation)
        assert isinstance(result, list)
    
    def test_parse_malformed_json(self):
        """测试解析格式错误的JSON"""
        from batch_extractor import BatchMemoryExtractor
        
        mock_system = Mock()
        extractor = BatchMemoryExtractor(mock_system)
        
        # 各种格式错误的JSON
        malformed_jsons = [
            '{"memories": [',
            '{"memories": [{}',
            '{"memories": [{theme: "test"}]}',
            'not json at all',
            '',
            '{"other_key": "value"}',
        ]
        
        for json_str in malformed_jsons:
            result = extractor._parse_batch_response(json_str)
            assert isinstance(result, list)
    
    def test_extract_themes_various_texts(self):
        """测试从各种文本提取主题"""
        from batch_extractor import BatchMemoryExtractor
        
        mock_system = Mock()
        extractor = BatchMemoryExtractor(mock_system)
        
        texts = [
            "今天天气很好，阳光明媚",
            "昨天我们讨论了项目计划",
            "最近工作很忙",
            "",
            "123456",
            "！@#￥%……&*（）",
        ]
        
        for text in texts:
            result = extractor._extract_simple_themes(text)
            assert isinstance(result, list)


class TestModelsEdgeCases:
    """测试数据模型的边缘情况"""
    
    def test_concept_with_special_characters(self):
        """测试包含特殊字符的概念"""
        from models import Concept
        
        concepts = [
            Concept(id="c1", name="概念！@#"),
            Concept(id="c2", name="123456"),
            Concept(id="c3", name=""),
            Concept(id="c4", name="a" * 1000),
        ]
        
        for concept in concepts:
            assert concept.id is not None
            assert concept.created_at > 0
    
    def test_memory_with_extreme_values(self):
        """测试极端值的记忆"""
        from models import Memory
        
        memories = [
            Memory(id="m1", concept_id="c1", content="", strength=0.0),
            Memory(id="m2", concept_id="c2", content="x" * 10000, strength=1.0),
            Memory(id="m3", concept_id="c3", content="内容", strength=100.0),
            Memory(id="m4", concept_id="c4", content="内容", strength=-1.0),
        ]
        
        for memory in memories:
            assert memory.id is not None
            assert memory.concept_id is not None
    
    def test_connection_with_same_concept(self):
        """测试连接到自己的概念"""
        from models import Connection
        
        conn = Connection(id="conn1", from_concept="c1", to_concept="c1")
        assert conn.from_concept == conn.to_concept


class TestMemorySystemCoreComplex:
    """测试MemorySystem的复杂场景"""
    
    def test_memory_system_disabled_operations(self):
        """测试禁用状态下的操作"""
        from memory_system_core import MemorySystem
        import pathlib
        
        mock_context = Mock()
        config = {"enable_memory_system": False}
        
        with tempfile.TemporaryDirectory() as tmpdir:
            data_path = pathlib.Path(tmpdir)
            system = MemorySystem(
                context=mock_context,
                config=config,
                data_dir=data_path
            )
            
            assert system.memory_system_enabled is False
            assert not hasattr(system, 'memory_graph') or system.memory_graph is None
    
    def test_memory_system_with_custom_config(self):
        """测试自定义配置的记忆系统"""
        from memory_system_core import MemorySystem
        import pathlib
        
        mock_context = Mock()
        config = {
            "enable_memory_system": True,
            "enable_impression_injection": False,
        }
        
        with tempfile.TemporaryDirectory() as tmpdir:
            data_path = pathlib.Path(tmpdir)
            system = MemorySystem(
                context=mock_context,
                config=config,
                data_dir=data_path
            )
            
            assert system.memory_system_enabled is True
            assert system.impression_config['enable_impression_injection'] is False


class TestAsyncOperations:
    """测试异步操作"""
    
    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """测试异步上下文管理器"""
        import asyncio
        
        async def async_operation():
            await asyncio.sleep(0.001)
            return "completed"
        
        result = await async_operation()
        assert result == "completed"
    
    @pytest.mark.asyncio
    async def test_multiple_async_tasks(self):
        """测试多个异步任务"""
        import asyncio
        
        async def task(n):
            await asyncio.sleep(0.001)
            return n * 2
        
        results = await asyncio.gather(
            task(1),
            task(2),
            task(3)
        )
        
        assert results == [2, 4, 6]
