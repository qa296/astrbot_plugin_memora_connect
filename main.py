"""
AstrBot 记忆插件 - 模仿人类海马体的记忆系统
基于知识图谱的记忆网络，实现概念节点和关系连接的记忆存储
"""

import asyncio
import json
import sqlite3
import time
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import logging
from dataclasses import dataclass, asdict
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api import AstrBotConfig
import astrbot.api.message_components as Comp

@register("astrbot_plugin_memora_connect", "qa296", "一个模仿人类记忆方式的记忆插件", "v0.1.0", "https://github.com/qa296/astrbot_plugin_memora_connect")
class MemoraConnectPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.memory_system = MemorySystem(context, config)
        asyncio.create_task(self.memory_system.initialize())
        
    @filter.command("记忆")
    async def memory_command(self, event: AstrMessageEvent):
        """记忆相关指令"""
        message = event.message_str.strip()
        if message == "/记忆":
            yield event.plain_result("记忆系统已激活！我可以帮你记住对话中的重要信息。")
        elif message.startswith("/记忆 回忆"):
            keyword = message[5:].strip()
            memories = await self.memory_system.recall_memories(keyword, event)
            if memories:
                yield event.plain_result(f"关于'{keyword}'的记忆：\n" + "\n".join(memories))
            else:
                yield event.plain_result(f"没有找到关于'{keyword}'的记忆")
        elif message.startswith("/记忆 状态"):
            stats = await self.memory_system.get_memory_stats()
            yield event.plain_result(f"记忆系统状态：\n{stats}")
    
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """监听所有消息，形成记忆"""
        await self.memory_system.process_message(event)
    
    async def terminate(self):
        """插件卸载时保存记忆"""
        await self.memory_system.save_memory_state()
        logger.info("记忆系统已保存并关闭")


class MemorySystem:
    """核心记忆系统，模仿人类海马体功能"""
    
    def __init__(self, context: Context, config=None):
        self.context = context
        
        # 确保数据目录存在
        import os
        data_dir = "data/plugins/memora_connect"
        os.makedirs(data_dir, exist_ok=True)
        self.db_path = os.path.join(data_dir, "memory.db")
        
        self.memory_graph = MemoryGraph()
        self.llm_provider = None
        self.embedding_provider = None
        
        # 加载配置
        if config:
            self.memory_config = {
                "recall_mode": config.get("recall_mode", "llm"),
                "forget_threshold_days": config.get("forget_threshold_days", 30),
                "consolidation_interval_hours": config.get("consolidation_interval_hours", 24),
                "max_memories_per_topic": config.get("max_memories_per_topic", 10),
                "memory_formation_probability": config.get("memory_formation_probability", 0.3),
                "recall_trigger_probability": config.get("recall_trigger_probability", 0.2),
                "enable_forgetting": config.get("enable_forgetting", True),
                "enable_consolidation": config.get("enable_consolidation", True),
                "bimodal_recall": config.get("bimodal_recall", True),
                "llm_system_prompt": config.get("llm_system_prompt", "你是一个记忆总结助手，请将对话内容总结成简洁自然的记忆。"),
                "embedding_provider": config.get("embedding_provider", "openai"),
                "embedding_model": config.get("embedding_model", "")
            }
        else:
            self.memory_config = {
                "recall_mode": "llm",
                "forget_threshold_days": 30,
                "consolidation_interval_hours": 24,
                "max_memories_per_topic": 10,
                "memory_formation_probability": 0.3,
                "recall_trigger_probability": 0.2,
                "enable_forgetting": True,
                "enable_consolidation": True,
                "bimodal_recall": True,
                "llm_system_prompt": "你是一个记忆总结助手，请将对话内容总结成简洁自然的记忆。",
                "embedding_provider": "openai",
                "embedding_model": ""
            }
        
    async def initialize(self):
        """初始化记忆系统"""
        await self.load_memory_state()
        asyncio.create_task(self.memory_maintenance_loop())
        
    async def load_memory_state(self):
        """从数据库加载记忆状态"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 创建表结构
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS concepts (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    last_accessed REAL NOT NULL,
                    access_count INTEGER DEFAULT 0
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    concept_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    last_accessed REAL NOT NULL,
                    access_count INTEGER DEFAULT 0,
                    strength REAL DEFAULT 1.0,
                    FOREIGN KEY (concept_id) REFERENCES concepts (id)
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS connections (
                    id TEXT PRIMARY KEY,
                    from_concept TEXT NOT NULL,
                    to_concept TEXT NOT NULL,
                    strength REAL DEFAULT 1.0,
                    last_strengthened REAL NOT NULL,
                    FOREIGN KEY (from_concept) REFERENCES concepts (id),
                    FOREIGN KEY (to_concept) REFERENCES concepts (id)
                )
            ''')
            
            # 加载记忆图
            cursor.execute("SELECT * FROM concepts")
            concepts = cursor.fetchall()
            for concept in concepts:
                self.memory_graph.add_concept(concept[1], concept[0])
                
            cursor.execute("SELECT * FROM memories")
            memories = cursor.fetchall()
            for memory in memories:
                self.memory_graph.add_memory(memory[2], memory[1], memory[0])
                
            cursor.execute("SELECT * FROM connections")
            connections = cursor.fetchall()
            for conn in connections:
                self.memory_graph.add_connection(conn[1], conn[2], conn[3])
                
            conn.close()
            logger.info(f"记忆系统已加载，包含 {len(concepts)} 个概念，{len(memories)} 条记忆")
            
        except Exception as e:
            logger.error(f"加载记忆系统失败: {e}")
            
    async def save_memory_state(self):
        """保存记忆状态到数据库"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 清空现有数据
            cursor.execute("DELETE FROM connections")
            cursor.execute("DELETE FROM memories")
            cursor.execute("DELETE FROM concepts")
            
            # 保存概念
            for concept in self.memory_graph.concepts.values():
                cursor.execute('''
                    INSERT INTO concepts (id, name, created_at, last_accessed, access_count)
                    VALUES (?, ?, ?, ?, ?)
                ''', (concept.id, concept.name, concept.created_at, concept.last_accessed, concept.access_count))
            
            # 保存记忆
            for memory in self.memory_graph.memories.values():
                cursor.execute('''
                    INSERT INTO memories (id, concept_id, content, created_at, last_accessed, access_count, strength)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (memory.id, memory.concept_id, memory.content, memory.created_at, 
                      memory.last_accessed, memory.access_count, memory.strength))
            
            # 保存连接
            for connection in self.memory_graph.connections:
                cursor.execute('''
                    INSERT INTO connections (id, from_concept, to_concept, strength, last_strengthened)
                    VALUES (?, ?, ?, ?, ?)
                ''', (connection.id, connection.from_concept, connection.to_concept, 
                      connection.strength, connection.last_strengthened))
            
            conn.commit()
            conn.close()
            logger.info("记忆状态已保存")
            
        except Exception as e:
            logger.error(f"保存记忆状态失败: {e}")
    
    async def process_message(self, event: AstrMessageEvent):
        """处理消息，形成记忆"""
        try:
            # 获取对话历史
            history = await self.get_conversation_history(event)
            if not history:
                return
                
            # 提取主题和关键词
            themes = await self.extract_themes(history)
            
            # 形成记忆
            for theme in themes:
                memory_content = await self.form_memory(theme, history, event)
                if memory_content:
                    concept_id = self.memory_graph.add_concept(theme)
                    memory_id = self.memory_graph.add_memory(memory_content, concept_id)
                    
                    # 建立连接
                    self.establish_connections(concept_id, themes)
                    
            # 触发回忆
            if random.random() < 0.3:  # 30%概率触发回忆
                recalled = await self.recall_memories("", event)
                if recalled:
                    logger.info(f"触发了回忆: {recalled[:2]}")
                    
        except Exception as e:
            logger.error(f"处理消息时出错: {e}")
    
    async def get_conversation_history(self, event: AstrMessageEvent) -> List[str]:
        """获取对话历史"""
        try:
            uid = event.unified_msg_origin
            curr_cid = await self.context.conversation_manager.get_curr_conversation_id(uid)
            if curr_cid:
                conversation = await self.context.conversation_manager.get_conversation(uid, curr_cid)
                if conversation and conversation.history:
                    history = json.loads(conversation.history)
                    return [msg.get("content", "") for msg in history[-10:]]  # 最近10条
            return []
        except Exception as e:
            logger.error(f"获取对话历史失败: {e}")
            return []
    
    async def extract_themes(self, history: List[str]) -> List[str]:
        """从对话历史中提取主题"""
        if not history:
            return []
            
        # 简单的关键词提取，实际使用LLM会更准确
        text = " ".join(history)
        keywords = []
        
        # 提取名词和关键词
        import re
        words = re.findall(r'\b[\u4e00-\u9fff]{2,4}\b', text)
        word_freq = {}
        for word in words:
            if len(word) >= 2 and word not in ["你好", "谢谢", "再见"]:
                word_freq[word] = word_freq.get(word, 0) + 1
        
        # 返回频率最高的前5个关键词
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        return [word for word, freq in sorted_words[:5]]
    
    async def form_memory(self, theme: str, history: List[str], event: AstrMessageEvent) -> str:
        """形成记忆内容"""
        try:
            # 使用LLM总结记忆
            prompt = f"""请将以下关于"{theme}"的对话总结成一句口语化的记忆，就像亲身经历一样：
            
            对话内容：{" ".join(history[-3:])}
            
            要求：
            1. 用第一人称
            2. 简洁自然
            3. 包含关键信息
            4. 不超过50字
            """
            
            if self.memory_config["recall_mode"] == "llm" and self.context.get_using_provider():
                response = await self.context.get_using_provider().text_chat(
                    prompt=prompt,
                    contexts=[],
                    system_prompt="你是一个记忆总结助手"
                )
                return response.completion_text.strip()
            else:
                # 简单总结
                return f"我记得我们聊过关于{theme}的事情"
                
        except Exception as e:
            logger.error(f"形成记忆失败: {e}")
            return f"关于{theme}的记忆"
    
    def establish_connections(self, concept_id: str, themes: List[str]):
        """建立概念之间的连接"""
        for other_theme in themes:
            if other_theme != self.memory_graph.concepts[concept_id].name:
                other_concept = None
                for concept in self.memory_graph.concepts.values():
                    if concept.name == other_theme:
                        other_concept = concept
                        break
                
                if other_concept:
                    self.memory_graph.add_connection(concept_id, other_concept.id)
    
    async def recall_memories(self, keyword: str, event: AstrMessageEvent) -> List[str]:
        """回忆相关记忆"""
        try:
            if not keyword:
                # 随机回忆
                memories = list(self.memory_graph.memories.values())
                if memories:
                    selected = random.sample(memories, min(3, len(memories)))
                    return [m.content for m in selected]
                return []
            
            # 基于关键词回忆
            related_memories = []
            for concept in self.memory_graph.concepts.values():
                if keyword in concept.name:
                    concept_memories = [m for m in self.memory_graph.memories.values() 
                                      if m.concept_id == concept.id]
                    for memory in concept_memories:
                        related_memories.append(memory.content)
            
            return related_memories[:5]  # 最多返回5条
            
        except Exception as e:
            logger.error(f"回忆记忆失败: {e}")
            return []
    
    async def memory_maintenance_loop(self):
        """记忆维护循环"""
        while True:
            try:
                await asyncio.sleep(3600)  # 每小时检查一次
                
                # 遗忘机制
                await self.forget_memories()
                
                # 记忆整理
                await self.consolidate_memories()
                
                # 保存状态
                await self.save_memory_state()
                
            except Exception as e:
                logger.error(f"记忆维护失败: {e}")
    
    async def forget_memories(self):
        """遗忘机制"""
        current_time = time.time()
        forget_threshold = self.memory_config["forget_threshold_days"] * 24 * 3600
        
        # 降低连接强度
        for connection in self.memory_graph.connections:
            if current_time - connection.last_strengthened > forget_threshold:
                connection.strength *= 0.9
                if connection.strength < 0.1:
                    self.memory_graph.remove_connection(connection.id)
        
        # 移除不活跃的记忆
        for memory in list(self.memory_graph.memories.values()):
            if current_time - memory.last_accessed > forget_threshold:
                memory.strength *= 0.8
                if memory.strength < 0.1:
                    self.memory_graph.remove_memory(memory.id)
    
    async def consolidate_memories(self):
        """记忆整理机制"""
        for concept in self.memory_graph.concepts.values():
            concept_memories = [m for m in self.memory_graph.memories.values() 
                              if m.concept_id == concept.id]
            
            if len(concept_memories) > self.memory_config["max_memories_per_topic"]:
                # 合并相似记忆
                for i in range(len(concept_memories)):
                    for j in range(i+1, len(concept_memories)):
                        if self.are_memories_similar(concept_memories[i], concept_memories[j]):
                            # 保留更丰富的记忆
                            if len(concept_memories[i].content) > len(concept_memories[j].content):
                                self.memory_graph.remove_memory(concept_memories[j].id)
                            else:
                                self.memory_graph.remove_memory(concept_memories[i].id)
                                break
    
    def are_memories_similar(self, mem1, mem2) -> bool:
        """判断两条记忆是否相似"""
        # 简单的相似度判断
        common_words = set(mem1.content.split()) & set(mem2.content.split())
        similarity = len(common_words) / max(len(mem1.content.split()), len(mem2.content.split()))
        return similarity > 0.5
    
    async def get_memory_stats(self) -> str:
        """获取记忆统计信息"""
        return f"""
        概念节点: {len(self.memory_graph.concepts)}
        记忆条目: {len(self.memory_graph.memories)}
        关系连接: {len(self.memory_graph.connections)}
        运行模式: {self.memory_config['recall_mode']}
        嵌入提供商: {self.memory_config['embedding_provider']}
        """

    async def get_embedding_provider(self):
        """获取嵌入模型提供商"""
        try:
            provider_name = self.memory_config['embedding_provider']
            if provider_name == "openai":
                # 使用AstrBot配置的OpenAI提供商
                providers = self.context.get_all_providers()
                for provider in providers:
                    if "openai" in provider.id.lower():
                        return provider
            elif provider_name == "azure":
                # 使用Azure OpenAI
                providers = self.context.get_all_providers()
                for provider in providers:
                    if "azure" in provider.id.lower():
                        return provider
            else:
                # 通过ID获取指定提供商
                return self.context.get_provider_by_id(provider_name)
        except Exception as e:
            logger.error(f"获取嵌入提供商失败: {e}")
            return None

    async def get_embedding(self, text: str) -> List[float]:
        """获取文本的嵌入向量"""
        try:
            provider = await self.get_embedding_provider()
            if not provider:
                return []
            
            # 使用提供商的嵌入功能
            if hasattr(provider, 'embedding'):
                return await provider.embedding(text)
            else:
                logger.warning("提供商不支持嵌入功能")
                return []
                
        except Exception as e:
            logger.error(f"获取嵌入向量失败: {e}")
            return []


class MemoryGraph:
    """记忆图数据结构"""
    
    def __init__(self):
        self.concepts: Dict[str, Concept] = {}
        self.memories: Dict[str, Memory] = {}
        self.connections: List[Connection] = []
        
    def add_concept(self, name: str, concept_id: str = None) -> str:
        """添加概念节点"""
        if concept_id is None:
            concept_id = f"concept_{int(time.time() * 1000)}"
        
        if concept_id not in self.concepts:
            self.concepts[concept_id] = Concept(concept_id, name)
        
        return concept_id
    
    def add_memory(self, content: str, concept_id: str, memory_id: str = None) -> str:
        """添加记忆"""
        if memory_id is None:
            memory_id = f"memory_{int(time.time() * 1000)}"
        
        self.memories[memory_id] = Memory(memory_id, concept_id, content)
        return memory_id
    
    def add_connection(self, from_concept: str, to_concept: str, strength: float = 1.0) -> str:
        """添加连接"""
        connection_id = f"conn_{from_concept}_{to_concept}"
        
        # 检查是否已存在
        for conn in self.connections:
            if (conn.from_concept == from_concept and conn.to_concept == to_concept) or \
               (conn.from_concept == to_concept and conn.to_concept == from_concept):
                conn.strength += 0.1
                conn.last_strengthened = time.time()
                return conn.id
        
        connection = Connection(connection_id, from_concept, to_concept, strength)
        self.connections.append(connection)
        return connection_id
    
    def remove_connection(self, connection_id: str):
        """移除连接"""
        self.connections = [c for c in self.connections if c.id != connection_id]
    
    def remove_memory(self, memory_id: str):
        """移除记忆"""
        if memory_id in self.memories:
            del self.memories[memory_id]


@dataclass
class Concept:
    """概念节点"""
    id: str
    name: str
    created_at: float = None
    last_accessed: float = None
    access_count: int = 0
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()
        if self.last_accessed is None:
            self.last_accessed = time.time()


@dataclass
class Memory:
    """记忆条目"""
    id: str
    concept_id: str
    content: str
    created_at: float = None
    last_accessed: float = None
    access_count: int = 0
    strength: float = 1.0
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()
        if self.last_accessed is None:
            self.last_accessed = time.time()


@dataclass
class Connection:
    """概念之间的连接"""
    id: str
    from_concept: str
    to_concept: str
    strength: float = 1.0
    last_strengthened: float = None
    
    def __post_init__(self):
        if self.last_strengthened is None:
            self.last_strengthened = time.time()