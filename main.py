import time
import json
import random
import re
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict
import numpy as np

from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

@dataclass
class Memory:
    """代表一条具体的记忆"""
    content: str
    timestamp: float = field(default_factory=time.time)

@dataclass
class ConceptNode:
    """代表一个概念节点（主题）"""
    theme: str
    memories: List[Memory] = field(default_factory=list)

@dataclass
class Relationship:
    """代表两个概念节点之间的连接"""
    source_theme: str
    target_theme: str
    strength: float = 1.0

class KnowledgeGraph:
    """管理整个记忆网络，包括所有节点和它们之间的连接"""
    def __init__(self):
        self.nodes: Dict[str, ConceptNode] = {}
        self.relationships: Dict[str, Relationship] = {}

    def get_or_create_node(self, theme: str) -> ConceptNode:
        """获取或创建一个新的概念节点"""
        if theme not in self.nodes:
            self.nodes[theme] = ConceptNode(theme=theme)
        return self.nodes[theme]

    def add_relationship(self, source_theme: str, target_theme: str):
        """在两个主题之间添加或加强关系"""
        if source_theme == target_theme:
            return

        key = tuple(sorted((source_theme, target_theme)))
        key_str = f"{key}-{key}"

        if key_str in self.relationships:
            self.relationships[key_str].strength += 1
        else:
            self.relationships[key_str] = Relationship(source_theme=source_theme, target_theme=target_theme)

    def add_memory(self, theme: str, memory_content: str):
        """向指定主题添加一条记忆"""
        node = self.get_or_create_node(theme)
        node.memories.append(Memory(content=memory_content))

    def save(self, path: str):
        """将知识图谱保存到文件"""
        data = {
            "nodes": {theme: asdict(node) for theme, node in self.nodes.items()},
            "relationships": {key: asdict(rel) for key, rel in self.relationships.items()}
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def load(self, path: str):
        """从文件加载知识图谱"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.nodes = {theme: ConceptNode(**node_data) for theme, node_data in data.get("nodes", {}).items()}
            self.relationships = {key: Relationship(**rel_data) for key, rel_data in data.get("relationships", {}).items()}
        except FileNotFoundError:
            logger.info(f"记忆文件 {path} 未找到，将创建一个新的记忆网络。")
        except Exception as e:
            logger.error(f"加载记忆网络失败: {e}")

# --- 模型接口和实现 ---
from abc import ABC, abstractmethod

class MemoryModel(ABC):
    @abstractmethod
    async def extract_themes(self, text: str) -> List[str]:
        pass

    @abstractmethod
    async def are_memories_similar(self, mem1: Memory, mem2: Memory) -> bool:
        pass

class SimpleModel(MemoryModel):
    """基于简单关键词和文本相似度的模型"""
    async def extract_themes(self, text: str) -> List[str]:
        return list(set(re.split(r'\s+|,|;', text)))

    async def are_memories_similar(self, mem1: Memory, mem2: Memory, threshold: float) -> bool:
        words1 = set(mem1.content.split())
        words2 = set(mem2.content.split())
        if not words1 or not words2:
            return False
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        return (len(intersection) / len(union)) > threshold if union else False

class LLMModel(MemoryModel):
    """基于 LLM 的模型"""
    def __init__(self, context: Context):
        self.llm = context.llm

    async def extract_themes(self, text: str) -> List[str]:
        prompt = f"从以下文本中提取核心主题或关键词，每个不超过5个字，用逗号分隔：\n\n{text}"
        try:
            response = await self.llm.get_resp(prompt)
            return [theme.strip() for theme in response.split(',')]
        except Exception as e:
            logger.error(f"LLM 提取主题失败: {e}")
            return []

    async def are_memories_similar(self, mem1: Memory, mem2: Memory) -> bool:
        prompt = f"判断以下两条记忆是否描述了同一件或非常相似的事情？请回答“是”或“否”。\n\n记忆1: {mem1.content}\n记忆2: {mem2.content}"
        try:
            response = await self.llm.get_resp(prompt)
            return "是" in response
        except Exception as e:
            logger.error(f"LLM 判断相似度失败: {e}")
            return False

class EmbeddingModel(MemoryModel):
    """基于 Embedding 的模型"""
    def __init__(self, context: Context):
        self.embedding = context.embedding
        self.llm = context.llm # 也使用 llm 来提取主题

    async def extract_themes(self, text: str) -> List[str]:
        # 对于 Embedding 模型，我们仍然可以使用 LLM 来提取主题，因为它更擅长这个任务
        prompt = f"从以下文本中提取核心主题或关键词，每个不超过5个字，用逗号分隔：\n\n{text}"
        try:
            response = await self.llm.get_resp(prompt)
            return [theme.strip() for theme in response.split(',')]
        except Exception as e:
            logger.error(f"LLM (in EmbeddingModel) 提取主题失败: {e}")
            return []

    async def are_memories_similar(self, mem1: Memory, mem2: Memory, threshold: float) -> bool:
        try:
            vec1 = await self.embedding.get_embedding(mem1.content)
            vec2 = await self.embedding.get_embedding(mem2.content)
            
            # 计算余弦相似度
            cosine_similarity = np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))
            return cosine_similarity > threshold
        except Exception as e:
            logger.error(f"Embedding 判断相似度失败: {e}")
            return False

from astrbot.api import AstrBotConfig

@register("memora_connect", "qa296", "一个模仿生物海ма体，构建核心记忆系统的插件。", "0.1.0")
class MemoraConnectPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.knowledge_graph = KnowledgeGraph()
        self.db_path = self.context.get_data_path("memora.json")
        self.config = config

        model_type = self.config.get("model_type", "simple")
        if model_type == "llm" and self.context.llm:
            self.model = LLMModel(self.context)
            logger.info("使用 LLM 模型")
        elif model_type == "embedding" and self.context.embedding and self.context.llm:
            self.model = EmbeddingModel(self.context)
            logger.info("使用 Embedding 模型")
        else:
            if model_type != "simple":
                logger.warning(f"模型 '{model_type}' 配置不可用，已回退到 'simple' 模型。")
            self.model = SimpleModel()
            logger.info("使用 Simple 模型")

    async def initialize(self):
        """插件初始化时加载记忆网络"""
        logger.info("Memora Connect 插件开始初始化...")
        self.knowledge_graph.load(self.db_path)
        logger.info(f"数据将保存在: {self.db_path}")

        # 注册定时任务
        forgetting_interval = self.config.get("forgetting_interval_hours", 6)
        consolidation_interval = self.config.get("consolidation_interval_days", 1)
        self.context.scheduler.add_job(self.forget_memories, "interval", hours=forgetting_interval, id="memora_forget")
        self.context.scheduler.add_job(self.consolidate_memories, "interval", days=consolidation_interval, id="memora_consolidate")
        logger.info("Memora Connect 定时任务已注册。")

        logger.info("Memora Connect 插件初始化完成。")

    @filter.on_message()
    async def handle_message(self, event: AstrMessageEvent):
        """处理消息，自动形成记忆"""
        message_str = event.message_str.strip()
        if not message_str or message_str.startswith('/'):
            return
        
        min_length = self.config.get("auto_memory_min_length", 10)
        if len(message_str) > min_length:
            await self.form_memory(message_str)

    @filter.command("recall", "回忆")
    async def recall_command(self, event: AstrMessageEvent):
        """回忆指令，用于查询记忆"""
        query = event.message_str.strip()
        if not query:
            yield event.plain_result("请输入要回忆的关键词。用法: /recall <关键词>")
            return

        max_results = self.config.get("recall_max_results", 3)
        memories = await self.recall_memories(query, max_results=max_results)
        if not memories:
            yield event.plain_result("没有找到相关的记忆。")
            return

        reply = "找到了这些相关的记忆：\n"
        for i, mem in enumerate(memories, 1):
            reply += f"{i}. {mem.content}\n"
        
        yield event.plain_result(reply)

    async def form_memory(self, conversation: str):
        """根据一段对话形成记忆"""
        themes = await self.model.extract_themes(conversation)
        if not themes:
            return

        # 将对话本身作为一条记忆，存入第一个主题
        primary_theme = themes
        self.knowledge_graph.add_memory(primary_theme, conversation)
        logger.info(f"为主题 '{primary_theme}' 添加了新记忆: {conversation}")

        # 在不同主题之间建立关联
        if len(themes) > 1:
            for i in range(len(themes)):
                for j in range(i + 1, len(themes)):
                    self.knowledge_graph.add_relationship(themes[i], themes[j])
                    logger.info(f"更新了主题 '{themes[i]}' 和 '{themes[j]}' 之间的关系")

    async def recall_memories(self, query_text: str, max_results: int) -> List[Memory]:
        """根据查询文本回忆相关记忆"""
        query_themes = await self.model.extract_themes(query_text)
        if not query_themes:
            return []

        activated_themes: Dict[str, float] = {theme: 1.0 for theme in query_themes if theme in self.knowledge_graph.nodes}

        # 简化版的激活扩散
        for _ in range(2): # 扩散两轮
            for rel in self.knowledge_graph.relationships.values():
                if rel.source_theme in activated_themes and rel.target_theme not in activated_themes:
                    activated_themes[rel.target_theme] = activated_themes[rel.source_theme] * rel.strength * 0.5
                elif rel.target_theme in activated_themes and rel.source_theme not in activated_themes:
                    activated_themes[rel.source_theme] = activated_themes[rel.target_theme] * rel.strength * 0.5

        # 提取最相关的记忆
        relevant_memories = []
        for theme, activation_score in sorted(activated_themes.items(), key=lambda item: item, reverse=True):
            if theme in self.knowledge_graph.nodes:
                relevant_memories.extend(self.knowledge_graph.nodes[theme].memories)
        
        return relevant_memories[:max_results]

    async def forget_memories(self):
        """模拟记忆遗忘过程"""
        now = time.time()
        forgetting_threshold_days = self.config.get("forgetting_threshold_days", 30)
        forgetting_threshold_seconds = forgetting_threshold_days * 24 * 60 * 60

        # 遗忘不活跃的记忆和节点
        themes_to_remove = []
        for theme, node in self.knowledge_graph.nodes.items():
            node.memories = [m for m in node.memories if now - m.timestamp < forgetting_threshold_seconds]
            if not node.memories:
                themes_to_remove.append(theme)
        
        for theme in themes_to_remove:
            del self.knowledge_graph.nodes[theme]
            logger.info(f"主题 '{theme}' 因所有记忆被遗忘而被移除")

        # 降低并移除弱连接
        rels_to_remove = []
        for key, rel in self.knowledge_graph.relationships.items():
            # 简化处理：每次调用都降低强度
            rel.strength *= 0.95
            if rel.strength < 0.1:
                rels_to_remove.append(key)

        for key in rels_to_remove:
            del self.knowledge_graph.relationships[key]
            logger.info(f"移除了弱连接: {key}")

    async def consolidate_memories(self):
        """整理和巩固记忆"""
        model_type = self.config.get("model_type", "simple")
        if model_type == "embedding":
            threshold = self.config.get("embedding_similarity_threshold", 0.8)
        else:
            threshold = self.config.get("consolidation_similarity_threshold", 0.7)

        for theme, node in self.knowledge_graph.nodes.items():
            if len(node.memories) < 2:
                continue

            merged_memories = []
            memories_to_skip = set()

            for i in range(len(node.memories)):
                if i in memories_to_skip:
                    continue
                
                current_memory = node.memories[i]
                for j in range(i + 1, len(node.memories)):
                    if j in memories_to_skip:
                        continue

                    other_memory = node.memories[j]
                    if await self.model.are_memories_similar(current_memory, other_memory, threshold=threshold):
                        # 保留信息更丰富（更长）的一条
                        if len(other_memory.content) > len(current_memory.content):
                            current_memory = other_memory
                        memories_to_skip.add(j)
                
                merged_memories.append(current_memory)
            
            if len(merged_memories) < len(node.memories):
                logger.info(f"主题 '{theme}' 下的记忆已从 {len(node.memories)} 条合并为 {len(merged_memories)} 条")
                node.memories = merged_memories

    def get_memories_with_bimodal_distribution(self) -> List[Memory]:
        """使用双峰时间分布来获取记忆"""
        all_memories = [m for node in self.knowledge_graph.nodes.values() for m in node.memories]
        if not all_memories:
            return []

        now = time.time()
        
        # 定义时间窗口（秒）
        one_hour = 3600
        one_day = 24 * one_hour
        
        recent_peak = (now - one_day, now) # 最近一天
        distant_peak = (now - 7 * one_day, now - 3 * one_day) # 3-7天前

        selected_memories = []
        for m in all_memories:
            # 50% 概率选择近期记忆
            if random.random() < 0.5:
                if recent_peak <= m.timestamp <= recent_peak:
                    selected_memories.append(m)
            # 50% 概率选择远期记忆
            else:
                if distant_peak <= m.timestamp <= distant_peak:
                    selected_memories.append(m)
        
        return selected_memories

    async def terminate(self):
        """插件卸载/停用时保存记忆网络"""
        logger.info("Memora Connect 插件开始卸载...")
        self.knowledge_graph.save(self.db_path)
        logger.info("Memora Connect 插件已卸载。")
