import asyncio
import json
import time
import random
import sqlite3
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import os
import shutil
from dataclasses import dataclass, asdict
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from .database_migration import DatabaseMigration
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api import AstrBotConfig
from astrbot.api.star import StarTools
import astrbot.api.message_components as Comp

@register("astrbot_plugin_memora_connect", "qa296", "一个模仿人类记忆方式的记忆插件", "v0.1.0", "https://github.com/qa296/astrbot_plugin_memora_connect")
class MemoraConnectPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        data_dir = StarTools.get_data_dir() / "memora_connect"
        self.memory_system = MemorySystem(context, config, data_dir)
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
        """监听所有消息，形成记忆并注入相关记忆"""
        try:
            # 1. 注入相关记忆到上下文
            await self.memory_system.inject_memories_to_context(event)
            
            # 2. 处理消息形成新记忆
            await self.memory_system.process_message(event)
        except Exception as e:
            logger.error(f"on_message处理错误: {e}", exc_info=True)
    
    async def terminate(self):
        """插件卸载时保存记忆"""
        await self.memory_system.save_memory_state()
        logger.info("记忆系统已保存并关闭")

    # ---------- LLM 函数工具 ----------
    @filter.llm_tool(name="create_memory")
    async def create_memory_tool(self, event: AstrMessageEvent, content: str, topic: str) -> MessageEventResult:
        """主动把一段对话内容记为记忆。
        Args:
            content(string): 需要记录的完整对话内容
            topic(string): 该记忆所属的主题或关键词
        """
        try:
            concept_id = self.memory_system.memory_graph.add_concept(topic)
            memory_id = self.memory_system.memory_graph.add_memory(content, concept_id)
            logger.info(f"LLM 工具创建记忆：{topic} -> {content}")
            # 让LLM生成自然回复，不返回固定内容
            yield event.plain_result(None)  # 返回None让LLM继续其自然回复流程
        except Exception as e:
            logger.error(f"LLM 工具创建记忆失败：{e}")
            yield event.plain_result(None)

    @filter.llm_tool(name="recall_memory")
    async def recall_memory_tool(self, event: AstrMessageEvent, keyword: str) -> MessageEventResult:
        """主动查询与关键词相关的记忆。
        Args:
            keyword(string): 要查询的关键词
        """
        try:
            memories = await self.memory_system.recall_memories(keyword, event)
            if memories:
                # 构建自然语言回复，让LLM基于记忆内容继续对话
                memory_context = "根据我们之前的对话记忆：\n" + "\n".join(f"• {mem}" for mem in memories)
                yield event.plain_result(memory_context)
            else:
                # 让LLM自然回复没有找到相关记忆
                yield event.plain_result(None)
        except Exception as e:
            logger.error(f"LLM 工具回忆记忆失败：{e}")
            yield event.plain_result(None)


class MemorySystem:
    """核心记忆系统，模仿人类海马体功能"""
    
    def __init__(self, context: Context, config=None, data_dir=None):
        self.context = context
        
        # 使用AstrBot标准数据目录
        if data_dir:
            self.db_path = str(data_dir / "memory.db")
        else:
            data_dir = StarTools.get_data_dir() / "memora_connect"
            self.db_path = str(data_dir / "memory.db")
        
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        logger.info(f"记忆数据库路径: {self.db_path}")
        
        self.memory_graph = MemoryGraph()
        self.llm_provider = None
        self.embedding_provider = None
        
        # 简化配置初始化
        config = config or {}
        self.memory_config = {
            "recall_mode": config.get("recall_mode", "llm"),
            "enable_associative_recall": config.get("enable_associative_recall", True),
            "forget_threshold_days": config.get("forget_threshold_days", 30),
            "consolidation_interval_hours": config.get("consolidation_interval_hours", 24),
            "max_memories_per_topic": config.get("max_memories_per_topic", 10),
            "memory_formation_every_n": config.get("memory_formation_every_n", 5),
            "recall_trigger_probability": config.get("recall_trigger_probability", 0.2),
            "enable_forgetting": config.get("enable_forgetting", True),
            "enable_consolidation": config.get("enable_consolidation", True),
            "bimodal_recall": config.get("bimodal_recall", True),
            "llm_provider": config.get("llm_provider", "openai"),
            "llm_system_prompt": config.get("llm_system_prompt", "你是一个记忆总结助手，请将对话内容总结成简洁自然的记忆。"),
            "embedding_provider": config.get("embedding_provider", "openai"),
            "embedding_model": config.get("embedding_model", "")
        }
        
    async def initialize(self):
        """初始化记忆系统"""
        migration = DatabaseMigration(self.db_path, self.context)
        migration_success = await migration.run_smart_migration()

        if migration_success:
            self.load_memory_state()
            asyncio.create_task(self.memory_maintenance_loop())
        else:
            logger.error("数据库迁移失败，记忆系统可能无法正常工作。")
        
    def load_memory_state(self):
        """从数据库加载记忆状态"""
        import sqlite3
        import os
        
        if not os.path.exists(self.db_path):
            logger.info("数据库文件不存在，跳过加载")
            return
            
        try:
            logger.info(f"正在加载记忆数据库: {self.db_path}")
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 检查表是否存在
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='concepts'")
                if not cursor.fetchone():
                    logger.info("数据库表不存在，跳过加载")
                    return
                
                # 加载概念
                cursor.execute("SELECT id, name, created_at, last_accessed, access_count FROM concepts")
                concepts = cursor.fetchall()
                for concept_data in concepts:
                    self.memory_graph.add_concept(
                        concept_id=concept_data[0],
                        name=concept_data[1],
                        created_at=concept_data[2],
                        last_accessed=concept_data[3],
                        access_count=concept_data[4]
                    )
                    
                # 加载记忆
                cursor.execute("SELECT id, concept_id, content, created_at, last_accessed, access_count, strength FROM memories")
                memories = cursor.fetchall()
                for memory_data in memories:
                    self.memory_graph.add_memory(
                        content=memory_data[2],
                        concept_id=memory_data[1],
                        memory_id=memory_data[0],
                        created_at=memory_data[3],
                        last_accessed=memory_data[4],
                        access_count=memory_data[5],
                        strength=memory_data[6]
                    )
                    
                # 加载连接
                cursor.execute("SELECT id, from_concept, to_concept, strength, last_strengthened FROM connections")
                connections = cursor.fetchall()
                for conn_data in connections:
                    self.memory_graph.add_connection(
                        from_concept=conn_data[1],
                        to_concept=conn_data[2],
                        strength=conn_data[3],
                        connection_id=conn_data[0],
                        last_strengthened=conn_data[4]
                    )
                    
            logger.info(f"记忆系统已加载，包含 {len(concepts)} 个概念，{len(memories)} 条记忆")
            
        except sqlite3.Error as e:
            logger.error(f"加载记忆数据库失败: {e}")
        except Exception as e:
            logger.error(f"加载记忆状态时发生未知错误: {e}")

    def _create_database_schema(self):
        """创建初始数据库表结构"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # 确保在创建时就写入版本信息
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version TEXT PRIMARY KEY,
                    migrated_at REAL NOT NULL
                )
            """)
            cursor.execute(
                "INSERT OR REPLACE INTO schema_version (version, migrated_at) VALUES (?, ?)",
                (DatabaseMigration.CURRENT_VERSION, time.time())
            )
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS concepts (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at REAL NOT NULL,
                    last_accessed REAL NOT NULL, access_count INTEGER DEFAULT 0
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY, concept_id TEXT NOT NULL, content TEXT NOT NULL,
                    created_at REAL NOT NULL, last_accessed REAL NOT NULL,
                    access_count INTEGER DEFAULT 0, strength REAL DEFAULT 1.0,
                    FOREIGN KEY (concept_id) REFERENCES concepts (id)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS connections (
                    id TEXT PRIMARY KEY, from_concept TEXT NOT NULL, to_concept TEXT NOT NULL,
                    strength REAL DEFAULT 1.0, last_strengthened REAL NOT NULL,
                    FOREIGN KEY (from_concept) REFERENCES concepts (id),
                    FOREIGN KEY (to_concept) REFERENCES concepts (id)
                )
            ''')
            conn.commit()
            
    def save_memory_state(self):
        """保存记忆状态到数据库"""
        import sqlite3
        try:
            logger.info(f"正在保存记忆到数据库: {self.db_path}")
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 使用事务确保数据一致性
                cursor.execute("BEGIN TRANSACTION")
                
                try:
                    # 清空现有数据
                    cursor.execute("DELETE FROM connections")
                    cursor.execute("DELETE FROM memories")
                    cursor.execute("DELETE FROM concepts")
                    
                    # 批量保存概念
                    concept_data = [
                        (c.id, c.name, c.created_at, c.last_accessed, c.access_count)
                        for c in self.memory_graph.concepts.values()
                    ]
                    if concept_data:
                        cursor.executemany('''
                            INSERT INTO concepts (id, name, created_at, last_accessed, access_count)
                            VALUES (?, ?, ?, ?, ?)
                        ''', concept_data)
                    
                    # 批量保存记忆
                    memory_data = [
                        (m.id, m.concept_id, m.content, m.created_at, m.last_accessed, m.access_count, m.strength)
                        for m in self.memory_graph.memories.values()
                    ]
                    if memory_data:
                        cursor.executemany('''
                            INSERT INTO memories (id, concept_id, content, created_at, last_accessed, access_count, strength)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', memory_data)
                    
                    # 批量保存连接
                    connection_data = [
                        (c.id, c.from_concept, c.to_concept, c.strength, c.last_strengthened)
                        for c in self.memory_graph.connections
                    ]
                    if connection_data:
                        cursor.executemany('''
                            INSERT INTO connections (id, from_concept, to_concept, strength, last_strengthened)
                            VALUES (?, ?, ?, ?, ?)
                        ''', connection_data)
                    
                    conn.commit()
                    logger.info(f"记忆状态已保存: {len(concept_data)}个概念, {len(memory_data)}条记忆, {len(connection_data)}个连接")
                    
                except Exception as e:
                    conn.rollback()
                    logger.error(f"保存记忆状态失败，已回滚: {e}")
                    raise
                    
        except sqlite3.Error as e:
            logger.error(f"数据库错误导致保存失败: {e}")
        except Exception as e:
            logger.error(f"保存记忆状态时发生未知错误: {e}")
    
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
            
        # 根据配置选择提取方式
        if self.memory_config["recall_mode"] in ["llm", "embedding"]:
            return await self._extract_themes_by_llm(history)
        else:
            return await self._extract_themes_simple(history)
    
    async def _extract_themes_simple(self, history: List[str]) -> List[str]:
        """简单的关键词提取"""
        text = " ".join(str(item) if not isinstance(item, str) else item for item in history)
        keywords = []
        
        # 提取名词和关键词
        words = re.findall(r'\b[\u4e00-\u9fff]{2,4}\b', text)
        word_freq = {}
        for word in words:
            if len(word) >= 2 and word not in ["你好", "谢谢", "再见"]:
                word_freq[word] = word_freq.get(word, 0) + 1
        
        # 返回频率最高的前5个关键词
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        return [str(word) for word, freq in sorted_words[:5]]
    
    async def _extract_themes_by_llm(self, history: List[str]) -> List[str]:
        """使用LLM从对话历史中提取主题"""
        try:
            if not history:
                return []
                
            prompt = f"""请从以下对话中提取3-5个核心主题或关键词。这些主题将用于构建记忆网络。

对话内容：
{" ".join(map(str, history))}

要求：
1. 提取的主题应该是对话的核心内容
2. 每个主题2-4个汉字
3. 返回格式：主题1,主题2,主题3
4. 不要包含解释，只返回主题列表
"""
            
            provider = await self.get_llm_provider()
            if provider:
                response = await provider.text_chat(
                    prompt=prompt,
                    contexts=[],
                    system_prompt="你是一个主题提取助手，请准确提取对话的核心主题。"
                )
                
                themes_text = response.completion_text.strip()
                # 清理和分割主题
                themes = [theme.strip() for theme in themes_text.replace("，", ",").split(",") if theme.strip()]
                return themes[:5]  # 最多返回5个主题
                
        except Exception as e:
            logger.error(f"LLM主题提取失败: {e}")
            return await self._extract_themes_simple(history)  # 回退到简单模式
    
    async def form_memory(self, theme: str, history: List[str], event: AstrMessageEvent) -> str:
        """形成记忆内容"""
        try:
            # 使用LLM总结记忆
            prompt = f"""请将以下关于"{theme}"的对话总结成一句口语化的记忆，就像亲身经历一样：
            
            对话内容：{" ".join(map(str, history[-3:]))}
            
            要求：
            1. 用第三人称
            2. 简洁自然
            3. 包含关键信息
            4. 不超过50字
            """
            
            if self.memory_config["recall_mode"] == "llm":
                provider = await self.get_llm_provider()
                if provider:
                    response = await provider.text_chat(
                        prompt=prompt,
                        contexts=[],
                        system_prompt=self.memory_config["llm_system_prompt"]
                    )
                    return response.completion_text.strip()
            
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
            recall_mode = self.memory_config["recall_mode"]
            enable_associative = self.memory_config.get("enable_associative_recall", True)
            
            if recall_mode == "simple":
                return await self._recall_simple(keyword)
            elif recall_mode == "llm":
                core_memories = await self._recall_llm(keyword, event)
                if enable_associative and core_memories:
                    associative_memories = await self._get_associative_memories(core_memories)
                    return self._merge_memories_with_associative(core_memories, associative_memories)
                return core_memories
            elif recall_mode == "embedding":
                core_memories = await self._recall_embedding(keyword)
                if enable_associative and core_memories:
                    associative_memories = await self._get_associative_memories(core_memories)
                    return self._merge_memories_with_associative(core_memories, associative_memories)
                return core_memories
            else:
                logger.warning(f"未知的回忆模式: {recall_mode}，使用simple模式")
                return await self._recall_simple(keyword)
                
        except Exception as e:
            logger.error(f"回忆记忆失败: {e}")
            return []

    async def _recall_simple(self, keyword: str) -> List[str]:
        """增强的简单关键词匹配回忆"""
        try:
            if not keyword:
                # 随机回忆，优先选择强度高的记忆
                memories = list(self.memory_graph.memories.values())
                if memories:
                    # 按记忆强度和时间排序
                    memories.sort(key=lambda m: (m.strength, m.last_accessed), reverse=True)
                    selected = memories[:min(3, len(memories))]
                    return [m.content for m in selected]
                return []
            
            # 增强的关键词匹配
            related_memories = []
            keyword_lower = keyword.lower()
            
            # 直接概念匹配
            for concept in self.memory_graph.concepts.values():
                concept_name_lower = concept.name.lower()
                if keyword_lower in concept_name_lower or concept_name_lower in keyword_lower:
                    concept_memories = [m for m in self.memory_graph.memories.values()
                                      if m.concept_id == concept.id]
                    # 按记忆强度排序
                    concept_memories.sort(key=lambda m: m.strength, reverse=True)
                    for memory in concept_memories[:2]:  # 每个概念最多2条
                        related_memories.append(memory.content)
            
            # 内容关键词匹配
            for memory in self.memory_graph.memories.values():
                if keyword_lower in memory.content.lower():
                    related_memories.append(memory.content)
            
            # 去重并限制数量
            seen = set()
            unique_memories = []
            for memory in related_memories:
                if memory not in seen:
                    seen.add(memory)
                    unique_memories.append(memory)
                    if len(unique_memories) >= 5:
                        break
            
            return unique_memories
            
        except Exception as e:
            logger.error(f"简单回忆失败: {e}")
            return []

    async def _recall_llm(self, keyword: str, event: AstrMessageEvent) -> List[str]:
        """LLM智能回忆"""
        try:
            if not self.memory_graph.memories:
                return []
                
            # 获取所有记忆内容
            all_memories = [m.content for m in self.memory_graph.memories.values()]
            
            if not keyword:
                # 随机选择3条记忆
                return random.sample(all_memories, min(3, len(all_memories)))
            
            # 使用LLM进行智能回忆
            prompt = f"""请从以下记忆列表中，找出与用户提问“{keyword}”最相关的3-5条记忆。

记忆列表：
{chr(10).join(f"- {mem}" for mem in all_memories)}

严格按照以下JSON格式返回结果，不要有任何多余的解释：
{{
  "recalled_memories": [
    "记忆1",
    "记忆2",
    ...
  ]
}}

如果找不到任何相关记忆，或记忆列表为空，请返回一个空列表：
{{
  "recalled_memories": []
}}
"""

            provider = await self.get_llm_provider()
            if provider:
                response = await provider.text_chat(
                    prompt=prompt,
                    contexts=[],
                    system_prompt="你是一个记忆检索助手，你的任务是严格按照JSON格式返回检索到的记忆。"
                )
                
                try:
                    # 提取并解析JSON
                    completion_text = response.completion_text.strip()
                    json_match = re.search(r'\{.*\}', completion_text, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(0)
                        data = json.loads(json_str)
                        recalled = data.get("recalled_memories", [])
                        # 确保返回的是列表
                        if isinstance(recalled, list):
                            return recalled[:5]
                    return [] # 如果没有找到JSON或解析失败
                except json.JSONDecodeError:
                    logger.error("LLM返回的不是有效的JSON格式")
                    return [] # JSON解析失败
            
            # LLM不可用，回退到简单模式
            return await self._recall_simple(keyword)
            
        except Exception as e:
            logger.error(f"LLM回忆失败: {e}")
            return await self._recall_simple(keyword)

    async def _recall_embedding(self, keyword: str) -> List[str]:
        """基于嵌入向量的相似度回忆"""
        try:
            if not keyword or not self.memory_graph.memories:
                # 随机回忆
                memories = list(self.memory_graph.memories.values())
                if memories:
                    selected = random.sample(memories, min(3, len(memories)))
                    return [m.content for m in selected]
                return []
            
            # 获取关键词的嵌入向量
            keyword_embedding = await self.get_embedding(keyword)
            if not keyword_embedding:
                logger.warning("无法获取关键词嵌入向量，回退到简单模式")
                return await self._recall_simple(keyword)
            
            # 计算与所有记忆的相似度
            memory_similarities = []
            for memory in self.memory_graph.memories.values():
                memory_embedding = await self.get_embedding(memory.content)
                if memory_embedding:
                    similarity = self._cosine_similarity(keyword_embedding, memory_embedding)
                    memory_similarities.append((memory, similarity))
            
            # 按相似度排序
            memory_similarities.sort(key=lambda x: x[1], reverse=True)
            
            # 返回最相似的5条记忆
            return [mem.content for mem, sim in memory_similarities[:5] if sim > 0.3]
            
        except Exception as e:
            logger.error(f"嵌入回忆失败: {e}")
            return await self._recall_simple(keyword)

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """计算余弦相似度"""
        try:
            if len(vec1) != len(vec2):
                return 0.0
            
            dot_product = sum(a * b for a, b in zip(vec1, vec2))
            magnitude1 = sum(a * a for a in vec1) ** 0.5
            magnitude2 = sum(b * b for b in vec2) ** 0.5
            
            if magnitude1 == 0 or magnitude2 == 0:
                return 0.0
            
            return dot_product / (magnitude1 * magnitude2)
        except Exception:
            return 0.0
    
    async def _get_associative_memories(self, core_memories: List[str]) -> List[str]:
        """基于核心记忆获取联想记忆"""
        try:
            if not core_memories or not self.memory_graph.memories:
                return []
            
            # 找到核心记忆对应的概念节点
            core_concepts = set()
            for memory_content in core_memories:
                for memory in self.memory_graph.memories.values():
                    if memory.content == memory_content:
                        core_concepts.add(memory.concept_id)
                        break
            
            if not core_concepts:
                return []
            
            # 收集与核心概念直接相连的相邻概念
            adjacent_concepts = set()
            for concept_id in core_concepts:
                neighbors = self.memory_graph.get_neighbors(concept_id)
                for neighbor_id, strength in neighbors:
                    if neighbor_id not in core_concepts and strength > 0.3:
                        adjacent_concepts.add(neighbor_id)
            
            # 收集相邻概念下的记忆
            associative_memories = []
            for concept_id in adjacent_concepts:
                concept_memories = [
                    m for m in self.memory_graph.memories.values()
                    if m.concept_id == concept_id
                ]
                
                # 按记忆强度和时间排序
                concept_memories.sort(
                    key=lambda m: (m.strength, m.last_accessed),
                    reverse=True
                )
                
                # 每个相邻概念最多添加1条记忆
                if concept_memories:
                    associative_memories.append(concept_memories[0].content)
            
            return associative_memories
            
        except Exception as e:
            logger.error(f"获取联想记忆失败: {e}")
            return []
    
    def _merge_memories_with_associative(self, core_memories: List[str], associative_memories: List[str]) -> List[str]:
        """合并核心记忆和联想记忆"""
        try:
            # 去重并合并
            all_memories = []
            seen = set()
            
            # 核心记忆在前
            for memory in core_memories:
                if memory not in seen:
                    seen.add(memory)
                    all_memories.append(memory)
            
            # 联想记忆在后
            for memory in associative_memories:
                if memory not in seen:
                    seen.add(memory)
                    all_memories.append(memory)
            
            # 限制总数量
            return all_memories[:5]
            
        except Exception as e:
            logger.error(f"合并记忆失败: {e}")
            return core_memories
    
    async def _recall_by_activation(self, keyword: str) -> List[str]:
        """基于激活扩散的回忆算法"""
        try:
            if not self.memory_graph.concepts or not self.memory_graph.memories:
                return []
            
            # 如果没有关键词，随机回忆
            if not keyword:
                memories = list(self.memory_graph.memories.values())
                if memories:
                    selected = random.sample(memories, min(3, len(memories)))
                    return [m.content for m in selected]
                return []
            
            # 找到初始激活的概念节点
            initial_concepts = []
            for concept in self.memory_graph.concepts.values():
                if keyword.lower() in concept.name.lower():
                    initial_concepts.append(concept)
            
            if not initial_concepts:
                # 如果没有直接匹配，使用简单关键词匹配
                return await self._recall_simple(keyword)
            
            # 激活扩散算法
            activation_map = {}  # concept_id -> activation_energy
            visited = set()
            
            # 初始化激活
            for concept in initial_concepts:
                activation_map[concept.id] = 1.0  # 初始能量为1.0
            
            # 扩散参数
            decay_factor = 0.7  # 能量衰减因子
            min_threshold = 0.1  # 最小激活阈值
            max_hops = 3  # 最大扩散步数
            
            # 进行扩散
            for hop in range(max_hops):
                new_activations = {}
                
                for concept_id, energy in activation_map.items():
                    if concept_id in visited:
                        continue
                    
                    # 获取该节点的所有连接
                    related_connections = [
                        conn for conn in self.memory_graph.connections
                        if conn.from_concept == concept_id or conn.to_concept == concept_id
                    ]
                    
                    for conn in related_connections:
                        # 确定相邻节点
                        neighbor_id = conn.to_concept if conn.from_concept == concept_id else conn.from_concept
                        
                        if neighbor_id in self.memory_graph.concepts:
                            # 计算传递的能量
                            transferred_energy = energy * conn.strength * decay_factor
                            
                            if transferred_energy > min_threshold:
                                if neighbor_id not in new_activations:
                                    new_activations[neighbor_id] = 0
                                new_activations[neighbor_id] += transferred_energy
                    
                    visited.add(concept_id)
                
                # 合并新的激活
                for concept_id, energy in new_activations.items():
                    if concept_id not in activation_map:
                        activation_map[concept_id] = 0
                    activation_map[concept_id] += energy
            
            # 收集被激活的概念下的记忆
            activated_memories = []
            adjacent_memories = []
            
            # 获取高激活的核心概念
            core_concepts = [
                concept_id for concept_id, energy in activation_map.items()
                if energy > min_threshold
            ]
            
            # 收集核心概念下的记忆
            for concept_id in core_concepts:
                concept_memories = [
                    m for m in self.memory_graph.memories.values()
                    if m.concept_id == concept_id
                ]
                
                # 按记忆强度和时间排序
                concept_memories.sort(
                    key=lambda m: (m.strength, m.last_accessed),
                    reverse=True
                )
                
                # 添加核心记忆
                for memory in concept_memories[:2]:  # 每个概念最多2条记忆
                    activated_memories.append(memory.content)
            
            # 收集相邻概念的记忆（与核心概念直接相连的概念）
            adjacent_concepts = set()
            for concept_id in core_concepts:
                for conn in self.memory_graph.connections:
                    if conn.from_concept == concept_id:
                        adjacent_concepts.add(conn.to_concept)
                    elif conn.to_concept == concept_id:
                        adjacent_concepts.add(conn.from_concept)
            
            # 收集相邻概念下的记忆
            for adjacent_concept_id in adjacent_concepts:
                if adjacent_concept_id in self.memory_graph.concepts:
                    adjacent_concept_memories = [
                        m for m in self.memory_graph.memories.values()
                        if m.concept_id == adjacent_concept_id
                    ]
                    
                    # 按记忆强度和时间排序
                    adjacent_concept_memories.sort(
                        key=lambda m: (m.strength, m.last_accessed),
                        reverse=True
                    )
                    
                    # 添加相邻记忆
                    for memory in adjacent_concept_memories[:1]:  # 每个相邻概念最多1条记忆
                        adjacent_memories.append(memory.content)
            
            # 合并结果：核心记忆在前，相邻记忆在后
            final_memories = activated_memories + adjacent_memories
            
            # 去重并限制数量
            seen = set()
            unique_memories = []
            for memory in final_memories:
                if memory not in seen:
                    seen.add(memory)
                    unique_memories.append(memory)
                    if len(unique_memories) >= 5:  # 最多返回5条
                        break
            
            return unique_memories
            
        except Exception as e:
            logger.error(f"激活扩散回忆失败: {e}")
            return await self._recall_simple(keyword)
    
    async def memory_maintenance_loop(self):
        """记忆维护循环"""
        while True:
            try:
                consolidation_interval = self.memory_config["consolidation_interval_hours"] * 3600
                await asyncio.sleep(consolidation_interval)  # 按配置间隔检查
                
                # 遗忘机制
                if self.memory_config["enable_forgetting"]:
                    await self.forget_memories()
                
                # 记忆整理
                if self.memory_config["enable_consolidation"]:
                    await self.consolidate_memories()
                
                # 保存状态
                self.save_memory_state()
                
                logger.info("记忆维护完成")
                
            except Exception as e:
                logger.error(f"记忆维护失败: {e}")
    
    async def forget_memories(self):
        """遗忘机制"""
        current_time = time.time()
        forget_threshold = self.memory_config["forget_threshold_days"] * 24 * 3600
        
        # 降低连接强度
        connections_to_remove = []
        for connection in self.memory_graph.connections:
            if current_time - connection.last_strengthened > forget_threshold:
                connection.strength *= 0.9
                if connection.strength < 0.1:
                    connections_to_remove.append(connection.id)
        
        # 批量移除连接
        for conn_id in connections_to_remove:
            self.memory_graph.remove_connection(conn_id)
        
        # 移除不活跃的记忆
        memories_to_remove = []
        for memory in list(self.memory_graph.memories.values()):
            if current_time - memory.last_accessed > forget_threshold:
                memory.strength *= 0.8
                if memory.strength < 0.1:
                    memories_to_remove.append(memory.id)
        
        # 批量移除记忆
        for memory_id in memories_to_remove:
            self.memory_graph.remove_memory(memory_id)
        
        logger.info(f"遗忘机制：移除{len(memories_to_remove)}条记忆，{len(connections_to_remove)}个连接")
    
    async def consolidate_memories(self):
        """记忆整理机制 - 智能合并相似记忆"""
        consolidation_count = 0
        
        for concept in list(self.memory_graph.concepts.values()):
            concept_memories = [m for m in self.memory_graph.memories.values()
                              if m.concept_id == concept.id]
            
            if len(concept_memories) > self.memory_config["max_memories_per_topic"]:
                # 按时间排序，优先合并旧记忆
                concept_memories.sort(key=lambda m: m.created_at)
                
                # 使用更智能的合并策略
                merged_memories = []
                used_indices = set()
                
                for i, memory1 in enumerate(concept_memories):
                    if i in used_indices:
                        continue
                        
                    similar_group = [memory1]
                    used_indices.add(i)
                    
                    # 找到所有相似的记忆
                    for j, memory2 in enumerate(concept_memories):
                        if j not in used_indices and self.are_memories_similar(memory1, memory2):
                            similar_group.append(memory2)
                            used_indices.add(j)
                    
                    # 如果找到相似记忆，合并它们
                    if len(similar_group) > 1:
                        merged_content = await self._merge_memories(similar_group)
                        if merged_content:
                            # 保留最新的记忆ID，更新内容
                            newest_memory = max(similar_group, key=lambda m: m.last_accessed)
                            newest_memory.content = merged_content
                            newest_memory.last_accessed = time.time()
                            consolidation_count += len(similar_group) - 1
                            
                            # 收集需要移除的记忆ID
                            memories_to_remove_in_group = []
                            for mem in similar_group:
                                if mem.id != newest_memory.id:
                                    memories_to_remove_in_group.append(mem.id)
                            
                            # 统一移除
                            for mem_id in memories_to_remove_in_group:
                                self.memory_graph.remove_memory(mem_id)
        
        if consolidation_count > 0:
            logger.info(f"记忆整理：合并了{consolidation_count}条相似记忆")
    
    async def _merge_memories(self, memories: List['Memory']) -> str:
        """智能合并多条相似记忆"""
        if len(memories) == 1:
            return memories[0].content
        
        # 按时间排序
        memories.sort(key=lambda m: m.created_at)
        
        # 提取关键信息
        contents = [m.content for m in memories]
        
        # 使用LLM进行智能合并（如果可用）
        try:
            if self.memory_config["recall_mode"] == "llm":
                provider = await self.get_llm_provider()
                if provider:
                    prompt = f"""请将以下{len(contents)}条相似记忆合并成一条更完整、更准确的记忆：

{chr(10).join(f"{i+1}. {content}" for i, content in enumerate(contents))}

要求：
1. 保留所有重要信息
2. 去除重复内容
3. 保持简洁自然
4. 不超过100字"""
                    
                    response = await provider.text_chat(
                        prompt=prompt,
                        contexts=[],
                        system_prompt="你是一个记忆整理助手，请准确合并相似记忆。"
                    )
                    
                    merged = response.completion_text.strip()
                    if merged and len(merged) > 10:
                        return merged
        except Exception as e:
            logger.warning(f"LLM合并记忆失败: {e}")
        
        # 简单合并策略
        # 提取共同关键词，合并时间信息
        words_list = [content.split() for content in contents]
        common_words = set(words_list[0])
        for words in words_list[1:]:
            common_words &= set(words)
        
        if common_words:
            key_phrase = " ".join(list(common_words)[:5])
            return f"关于{key_phrase}的多次讨论"
        
        # 默认合并
        return contents[-1]  # 返回最新的记忆
    
    def are_memories_similar(self, mem1, mem2) -> bool:
        """判断两条记忆是否相似"""
        # 简单的相似度判断
        words1 = mem1.content.split()
        words2 = mem2.content.split()
        
        # 防止除零错误
        denominator = max(len(words1), len(words2))
        if denominator == 0:
            return False
        
        common_words = set(words1) & set(words2)
        similarity = len(common_words) / denominator
        return similarity > 0.5
    
    async def get_memory_stats(self) -> str:
        """获取记忆统计信息"""
        return f"""
记忆系统状态：
- 概念节点: {len(self.memory_graph.concepts)}
- 记忆条目: {len(self.memory_graph.memories)}
- 关系连接: {len(self.memory_graph.connections)}
- 回忆模式: {self.memory_config['recall_mode']}
- LLM提供商: {self.memory_config['llm_provider']}
- 嵌入提供商: {self.memory_config['embedding_provider']}
- 遗忘机制: {'启用' if self.memory_config['enable_forgetting'] else '禁用'}
- 记忆整理: {'启用' if self.memory_config['enable_consolidation'] else '禁用'}
"""

    def _find_provider_by_keywords(self, keywords: list, capability_check=None):
        """根据关键词查找提供商，优先完全匹配"""
        providers = self.context.get_all_providers()
        
        # 优先完全匹配
        for provider in providers:
            provider_name = str(getattr(provider, 'name', '')).lower()
            if provider_name in keywords:
                if capability_check is None or capability_check(provider):
                    return provider

        # 然后再进行模糊匹配
        for provider in providers:
            provider_name = str(getattr(provider, 'name', '')).lower()
            for keyword in keywords:
                if keyword in provider_name:
                    if capability_check is None or capability_check(provider):
                        return provider
        
        return None

    async def get_llm_provider(self):
        """获取LLM服务提供商"""
        try:
            provider_name = self.memory_config['llm_provider'].lower()
            keywords_map = {
                "openai": ["openai"],
                "azure": ["azure"],
                "zhipu": ["zhipu", "glm"],
                "moonshot": ["moonshot", "kimi"],
                "anthropic": ["anthropic", "claude"],
                "google": ["google", "gemini"]
            }
            
            keywords = keywords_map.get(provider_name, [provider_name])
            provider = self._find_provider_by_keywords(keywords, lambda p: hasattr(p, 'text_chat'))
            
            if provider:
                return provider
            
            # 通过ID获取指定提供商
            try:
                provider = self.context.get_provider_by_id(provider_name)
                if provider and hasattr(provider, 'text_chat'):
                    return provider
            except Exception as e:
                logger.debug(f"通过ID获取提供商失败: {e}")
                
            # 回退到当前使用的提供商
            fallback_provider = self.context.get_using_provider()
            if fallback_provider:
                logger.info(f"使用回退LLM提供商: {getattr(fallback_provider, 'name', 'unknown')}")
            return fallback_provider
        except Exception as e:
            logger.error(f"获取LLM提供商失败: {e}")
            return None

    async def get_embedding_provider(self):
        """获取嵌入模型提供商"""
        try:
            provider_name = self.memory_config['embedding_provider'].lower()
            keywords_map = {
                "openai": ["openai"],
                "azure": ["azure"],
                "zhipu": ["zhipu", "glm"],
                "google": ["google", "gemini"]
            }
            
            keywords = keywords_map.get(provider_name, [provider_name])
            return self._find_provider_by_keywords(keywords)
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

    async def inject_memories_to_context(self, event: AstrMessageEvent):
        """将相关记忆注入到对话上下文中"""
        try:
            if not self.memory_config.get("auto_inject_memories", True):
                return
            
            current_message = event.message_str.strip()
            if not current_message:
                return
            
            # 获取相关记忆
            relevant_memories = await self.recall_relevant_memories(current_message)
            
            if relevant_memories:
                # 格式化记忆为上下文提示
                memory_context = self.format_memories_for_context(relevant_memories)
                
                # 注入到AstrBot的上下文中
                if not hasattr(event, 'context_extra'):
                    event.context_extra = {}
                event.context_extra["memory_context"] = memory_context
                
                logger.info(f"已注入 {len(relevant_memories)} 条相关记忆到上下文")
                
        except Exception as e:
            logger.error(f"注入记忆到上下文失败: {e}")

    async def recall_relevant_memories(self, message: str) -> List[str]:
        """基于消息内容智能召回相关记忆"""
        try:
            if not self.memory_graph.memories:
                return []
            
            # 使用多种召回策略
            memories = []
            
            # 1. 语义搜索
            semantic_memories = await self.semantic_search(message)
            memories.extend(semantic_memories)
            
            # 2. 关键词匹配
            keyword_memories = await self.keyword_based_recall(message)
            memories.extend(keyword_memories)
            
            # 3. 去重和排序
            seen = set()
            unique_memories = []
            for memory in memories:
                if memory not in seen:
                    seen.add(memory)
                    unique_memories.append(memory)
                    if len(unique_memories) >= self.memory_config.get("max_injected_memories", 3):
                        break
            
            return unique_memories
            
        except Exception as e:
            logger.error(f"智能召回记忆失败: {e}")
            return []

    async def semantic_search(self, query: str) -> List[str]:
        """基于语义相似度的记忆搜索"""
        try:
            if not query or not self.memory_graph.memories:
                return []
            
            # 获取查询的嵌入向量
            query_embedding = await self.get_embedding(query)
            if not query_embedding:
                return []
            
            similarities = []
            threshold = self.memory_config.get("memory_injection_threshold", 0.5)
            
            for memory in self.memory_graph.memories.values():
                memory_embedding = await self.get_embedding(memory.content)
                if memory_embedding:
                    similarity = self._cosine_similarity(query_embedding, memory_embedding)
                    if similarity > threshold:
                        similarities.append((memory.content, similarity))
            
            # 按相似度排序
            similarities.sort(key=lambda x: x[1], reverse=True)
            return [content for content, sim in similarities]
            
        except Exception as e:
            logger.error(f"语义搜索失败: {e}")
            return []

    async def keyword_based_recall(self, message: str) -> List[str]:
        """基于关键词的记忆召回"""
        try:
            # 提取关键词
            keywords = self.extract_keywords_from_text(message)
            
            relevant_memories = []
            for keyword in keywords:
                memories = await self._recall_simple(keyword)
                relevant_memories.extend(memories)
            
            return relevant_memories
            
        except Exception as e:
            logger.error(f"关键词召回失败: {e}")
            return []

    def extract_keywords_from_text(self, text: str) -> List[str]:
        """从文本中提取关键词"""
        try:
            # 提取中文关键词
            words = re.findall(r'\b[\u4e00-\u9fff]{2,4}\b', text)
            
            # 过滤常用词
            stop_words = {"你好", "谢谢", "再见", "请问", "可以", "这个", "那个"}
            keywords = [word for word in words if word not in stop_words and len(word) >= 2]
            
            # 返回前5个关键词
            return keywords[:5]
            
        except Exception as e:
            logger.error(f"提取关键词失败: {e}")
            return []

    def format_memories_for_context(self, memories: List[str]) -> str:
        """将记忆格式化为适合LLM理解的上下文"""
        if not memories:
            return ""
        
        formatted = "【记忆提示】根据我们之前的对话记忆：\n"
        for i, memory in enumerate(memories, 1):
            formatted += f"• {memory}\n"
        formatted += "【当前对话】"
        
        return formatted


class MemoryGraph:
    """记忆图数据结构"""
    
    def __init__(self):
        self.concepts: Dict[str, Concept] = {}
        self.memories: Dict[str, Memory] = {}
        self.connections: List[Connection] = []
        self.adjacency_list: Dict[str, List[Tuple[str, float]]] = {}  # 邻接表优化
        
    def add_concept(self, name: str, concept_id: str = None, created_at: float = None,
                   last_accessed: float = None, access_count: int = 0) -> str:
        """添加概念节点"""
        if concept_id is None:
            concept_id = f"concept_{int(time.time() * 1000)}"
        
        if concept_id not in self.concepts:
            concept = Concept(
                id=concept_id,
                name=name,
                created_at=created_at,
                last_accessed=last_accessed,
                access_count=access_count
            )
            self.concepts[concept_id] = concept
            if concept_id not in self.adjacency_list:
                self.adjacency_list[concept_id] = []
        
        return concept_id
    
    def add_memory(self, content: str, concept_id: str, memory_id: str = None,
                   created_at: float = None, last_accessed: float = None,
                   access_count: int = 0, strength: float = 1.0) -> str:
        """添加记忆"""
        if memory_id is None:
            memory_id = f"memory_{int(time.time() * 1000)}"
        
        memory = Memory(
            id=memory_id,
            concept_id=concept_id,
            content=content,
            created_at=created_at,
            last_accessed=last_accessed,
            access_count=access_count,
            strength=strength
        )
        self.memories[memory_id] = memory
        return memory_id
    
    def add_connection(self, from_concept: str, to_concept: str,
                      strength: float = 1.0, connection_id: str = None,
                      last_strengthened: float = None) -> str:
        """添加连接"""
        if connection_id is None:
            connection_id = f"conn_{from_concept}_{to_concept}"
        
        # 检查是否已存在
        for conn in self.connections:
            if (conn.from_concept == from_concept and conn.to_concept == to_concept) or \
               (conn.from_concept == to_concept and conn.to_concept == from_concept):
                conn.strength += 0.1
                conn.last_strengthened = time.time()
                return conn.id
        
        connection = Connection(
            id=connection_id,
            from_concept=from_concept,
            to_concept=to_concept,
            strength=strength,
            last_strengthened=last_strengthened or time.time()
        )
        self.connections.append(connection)
        
        # 更新邻接表
        if from_concept not in self.adjacency_list:
            self.adjacency_list[from_concept] = []
        if to_concept not in self.adjacency_list:
            self.adjacency_list[to_concept] = []
        
        # 添加双向连接
        self.adjacency_list[from_concept].append((to_concept, strength))
        self.adjacency_list[to_concept].append((from_concept, strength))
        
        return connection_id
    
    def remove_connection(self, connection_id: str):
        """移除连接"""
        # 找到要移除的连接
        conn_to_remove = None
        for conn in self.connections:
            if conn.id == connection_id:
                conn_to_remove = conn
                break
        
        if conn_to_remove:
            # 从连接列表中移除
            self.connections = [c for c in self.connections if c.id != connection_id]
            
            # 更新邻接表
            if conn_to_remove.from_concept in self.adjacency_list:
                self.adjacency_list[conn_to_remove.from_concept] = [
                    (neighbor, strength) for neighbor, strength in self.adjacency_list[conn_to_remove.from_concept]
                    if neighbor != conn_to_remove.to_concept
                ]
            
            if conn_to_remove.to_concept in self.adjacency_list:
                self.adjacency_list[conn_to_remove.to_concept] = [
                    (neighbor, strength) for neighbor, strength in self.adjacency_list[conn_to_remove.to_concept]
                    if neighbor != conn_to_remove.from_concept
                ]
    
    def remove_memory(self, memory_id: str):
        """移除记忆"""
        if memory_id in self.memories:
            del self.memories[memory_id]
    
    def get_neighbors(self, concept_id: str) -> List[Tuple[str, float]]:
        """获取概念节点的邻居及其连接强度"""
        return self.adjacency_list.get(concept_id, [])


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