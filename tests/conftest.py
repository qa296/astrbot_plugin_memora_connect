"""pytest配置和共享fixtures"""
import pytest
import sqlite3
import tempfile
import os
from unittest.mock import AsyncMock, MagicMock, Mock


@pytest.fixture
def temp_db():
    """创建临时数据库"""
    fd, path = tempfile.mkstemp(suffix='.db')
    yield path
    os.close(fd)
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def mock_llm_provider():
    """模拟LLM提供商"""
    provider = AsyncMock()
    provider.text_chat = AsyncMock()
    return provider


@pytest.fixture
def mock_embedding_provider():
    """模拟嵌入向量提供商"""
    provider = AsyncMock()
    provider.get_embeddings = AsyncMock()
    return provider


@pytest.fixture
def sample_conversation():
    """示例对话"""
    return [
        {
            "role": "user",
            "content": "今天天气不错",
            "sender_name": "张三",
            "timestamp": 1234567890
        },
        {
            "role": "assistant",
            "content": "是的，很适合出游",
            "sender_name": "Bot",
            "timestamp": 1234567891
        },
        {
            "role": "user",
            "content": "我想去公园",
            "sender_name": "张三",
            "timestamp": 1234567892
        }
    ]


@pytest.fixture
def sample_memories():
    """示例记忆数据"""
    return [
        {
            "id": "mem1",
            "concept_id": "c1",
            "content": "今天天气不错",
            "details": "晴天",
            "strength": 0.9,
            "group_id": "group1"
        },
        {
            "id": "mem2",
            "concept_id": "c2",
            "content": "想去公园",
            "details": "周末活动",
            "strength": 0.8,
            "group_id": "group1"
        }
    ]
