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
from astrbot.api.provider import ProviderRequest
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from .database_migration import DatabaseMigration
from .enhanced_memory_display import EnhancedMemoryDisplay
from .embedding_cache_manager import EmbeddingCacheManager
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api import AstrBotConfig
from astrbot.api.star import StarTools
import astrbot.api.message_components as Comp

@register("astrbot_plugin_memora_connect", "qa296", "一个模仿人类记忆方式的记忆插件", "0.2.2", "https://github.com/qa296/astrbot_plugin_memora_connect")
class MemoraConnectPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        data_dir = StarTools.get_data_dir() / "memora_connect"
        self.memory_system = MemorySystem(context, config, data_dir)
        self.memory_display = EnhancedMemoryDisplay(self.memory_system)
        self._initialized = False
        asyncio.create_task(self._async_init())
    
    async def _async_init(self):
        """异步初始化包装器"""
        try:
            logger.info("开始异步初始化记忆系统...")
            await self.memory_system.initialize()
            self._initialized = True
            logger.info("记忆系统异步初始化完成")
        except Exception as e:
            logger.error(f"记忆系统初始化失败: {e}", exc_info=True)
        
    @filter.command_group("记忆")
    def memory(self):
        """记忆管理指令组"""
        pass

    @memory.command("回忆")
    async def memory_recall(self, event: AstrMessageEvent, keyword: str):
        memories = await self.memory_system.recall_memories_full(keyword)
        response = self.memory_display.format_memory_search_result(memories, keyword)
        yield event.plain_result(response)

    @memory.command("状态")
    async def memory_status(self, event: AstrMessageEvent):
        stats = self.memory_display.format_memory_statistics()
        yield event.plain_result(stats)
    
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """监听所有消息，形成记忆并注入相关记忆"""
        if not self._initialized:
            self._debug_log("记忆系统尚未初始化完成，跳过消息处理", "debug")
            return
            
        try:
            # 提取群聊ID，用于群聊隔离
            group_id = self.memory_system._extract_group_id_from_event(event)
            
            # 1. 为当前群聊加载相应的记忆状态（异步优化）
            if group_id and self.memory_system.memory_config.get("enable_group_isolation", True):
                # 清空当前记忆图，重新加载群聊特定的记忆
                self.memory_system.memory_graph = MemoryGraph()
                self.memory_system.load_memory_state(group_id)
            
            # 2. 注入相关记忆到上下文（快速异步操作）
            asyncio.create_task(self.memory_system.inject_memories_to_context(event))
            
            # 3. 消息处理使用异步队列，避免阻塞主流程
            asyncio.create_task(self._process_message_async(event, group_id))
                
        except Exception as e:
            self._debug_log(f"on_message处理错误: {e}", "error")
    
    async def _process_message_async(self, event: AstrMessageEvent, group_id: str):
        """异步消息处理，避免阻塞主流程"""
        try:
            # 使用优化后的单次LLM调用处理消息
            await self.memory_system.process_message_optimized(event, group_id)
            
            # 使用队列化保存，减少I/O操作
            if group_id and self.memory_system.memory_config.get("enable_group_isolation", True):
                await self.memory_system._queue_save_memory_state(group_id)
            else:
                await self.memory_system._queue_save_memory_state("")  # 默认数据库
                
        except Exception as e:
            self._debug_log(f"异步消息处理失败: {e}", "error")

    @filter.on_llm_request()
    async def on_llm_request(self, event: AstrMessageEvent, req: ProviderRequest):
        """处理LLM请求时的记忆召回"""
        try:
            if not self._initialized:
                return
                
            # 获取当前消息内容
            current_message = event.message_str.strip()
            if not current_message:
                return
            
            # 使用增强记忆召回系统
            from .enhanced_memory_recall import EnhancedMemoryRecall
            
            enhanced_recall = EnhancedMemoryRecall(self.memory_system)
            results = await enhanced_recall.recall_all_relevant_memories(
                query=current_message,
                max_memories=self.memory_system.memory_config.get("max_injected_memories", 5)
            )
            
            if results:
                # 格式化记忆为上下文
                memory_context = enhanced_recall.format_memories_for_llm(results)
                
                # 将记忆注入到系统提示中
                if hasattr(req, 'system_prompt'):
                    original_prompt = req.system_prompt or ""
                    if "【相关记忆】" not in original_prompt:
                        req.system_prompt = f"{original_prompt}\n\n{memory_context}"
                        logger.debug(f"已注入 {len(results)} 条记忆到LLM上下文")
                        
        except Exception as e:
            logger.error(f"LLM请求记忆召回失败: {e}", exc_info=True)
    
    async def terminate(self):
        """插件卸载时保存记忆"""
        # 等待待处理的保存任务完成
        if self.memory_system._pending_save_task and not self.memory_system._pending_save_task.done():
            await self.memory_system._pending_save_task
        
        # 保存默认数据库
        await self.memory_system.save_memory_state()
        
        # 如果启用了群聊隔离，保存所有群聊数据库
        if self.memory_system.memory_config.get("enable_group_isolation", True):
            db_dir = os.path.dirname(self.memory_system.db_path)
            if os.path.exists(db_dir):
                for filename in os.listdir(db_dir):
                    if filename.startswith("memory_group_") and filename.endswith(".db"):
                        group_id = filename[12:-3]
                        await self.memory_system.save_memory_state(group_id)
        
        self._debug_log("记忆系统已保存并关闭", "info")

    # ---------- LLM 函数工具 ----------
    @filter.llm_tool(name="create_memory")
    async def create_memory_tool(
        self,
        event: AstrMessageEvent,
        content: str,
        theme: str = None,
        topic: str = None,
        details: str = "",
        participants: str = "",
        location: str = "",
        emotion: str = "",
        tags: str = "",
        confidence = 0.7
    ) -> MessageEventResult:
        """通过LLM调用获取个记忆点和主题

        Args:
            content(string): 需要记录的完整对话内容
            theme(string): 核心关键词，用逗号分隔
            topic(string): 该记忆所属的主题或关键词（向后兼容）
            details(string): 具体细节和背景信息
            participants(string): 涉及的人物，用逗号分隔。特别注意：如果是Bot的发言，请使用"我"作为参与者
            location(string): 相关场景或地点
            emotion(string): 情感色彩，如"开心,兴奋"
            tags(string): 分类标签，如"工作,重要"
            confidence(number): 置信度，0-1之间的数值
        """
        try:
            # 向后兼容性处理：如果提供了topic但没有theme，使用topic作为theme
            actual_theme = theme or topic
            if not actual_theme:
                logger.warning("创建记忆失败：主题为空")
                yield event.plain_result("")
                return
            
            # 参数验证和清理
            if not content:
                logger.warning("创建记忆失败：内容为空")
                yield event.plain_result("")
                return
            
            # 清理特殊字符
            import re
            actual_theme = re.sub(r'[^\w\u4e00-\u9fff,，]', '', str(actual_theme))
            details = str(details).strip()
            participants = str(participants).strip()
            location = str(location).strip()
            emotion = str(emotion).strip()
            tags = str(tags).strip()
            confidence = max(0.0, min(1.0, float(confidence)))
            
            # 创建概念
            concept_id = self.memory_system.memory_graph.add_concept(actual_theme)
            
            # 根据置信度调整记忆强度
            base_strength = 1.0
            adjusted_strength = base_strength * confidence
            
            # 创建丰富记忆
            memory_id = self.memory_system.memory_graph.add_memory(
                content=content,
                concept_id=concept_id,
                details=details,
                participants=participants,
                location=location,
                emotion=emotion,
                tags=tags,
                strength=adjusted_strength
            )
            
            logger.info(f"LLM工具创建丰富记忆：{actual_theme} -> {content} (置信度: {confidence})")
            
            # 返回空字符串让LLM继续其自然回复流程
            yield event.plain_result("")
            
        except Exception as e:
            logger.error(f"LLM工具创建记忆失败：{e}")
            yield event.plain_result("")

    @filter.llm_tool(name="recall_memory")
    async def recall_memory_tool(self, event: AstrMessageEvent, keyword: str) -> MessageEventResult:
        """召回所有相关记忆，包括联想记忆。

        Args:
            keyword(string): 要查询的关键词或内容
        """
        try:
            from .enhanced_memory_recall import EnhancedMemoryRecall
            
            enhanced_recall = EnhancedMemoryRecall(self.memory_system)
            results = await enhanced_recall.recall_all_relevant_memories(
                query=keyword,
                max_memories=8
            )
            
            if results:
                # 生成增强的上下文
                formatted_memories = enhanced_recall.format_memories_for_llm(results)
                yield event.plain_result(formatted_memories)
            else:
                # 返回空字符串让LLM继续其自然回复流程
                yield event.plain_result("")
                  
        except Exception as e:
            logger.error(f"增强记忆召回工具失败：{e}")
            yield event.plain_result("")


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
        self.batch_extractor = BatchMemoryExtractor(self)
        self.embedding_cache = None  # 嵌入向量缓存管理器
        
        # 配置初始化
        config = config or {}
        self.memory_config = {
            "enable_group_isolation": config.get("enable_group_isolation", True),
            "recall_mode": config.get("recall_mode", "llm"),
            "enable_associative_recall": config.get("enable_associative_recall", True),
            "forget_threshold_days": config.get("forget_threshold_days", 30),
            "consolidation_interval_hours": config.get("consolidation_interval_hours", 24),
            "max_memories_per_topic": config.get("max_memories_per_topic", 10),
            "memory_formation_probability": config.get("memory_formation_probability", 0.3),
            "recall_trigger_probability": config.get("recall_trigger_probability", 0.6),
            "enable_forgetting": config.get("enable_forgetting", True),
            "enable_consolidation": config.get("enable_consolidation", True),
            "bimodal_recall": config.get("bimodal_recall", True),
            "llm_provider": config.get("llm_provider", "openai"),
            "llm_system_prompt": config.get("llm_system_prompt", "你是一个记忆总结助手，请将对话内容总结成简洁自然的记忆。"),
            "embedding_provider": config.get("embedding_provider", "openai"),
            "embedding_model": config.get("embedding_model", ""),
            "max_injected_memories": config.get("max_injected_memories", 5),
            "enable_enhanced_memory": config.get("enable_enhanced_memory", True),
            "memory_injection_threshold": config.get("memory_injection_threshold", 0.3)
        }
        
        # 群聊隔离的数据库表前缀映射
        self.group_table_prefixes = {}
        
        # 日志限制计数器
        self.debug_log_count = 0
        self.debug_log_reset_time = time.time()
        
        # 优化：缓存和批量操作
        self._save_cache = {}  # 保存缓存 {group_id: pending_changes}
        self._save_locks = {}  # 保存锁 {group_id: asyncio.Lock}
        self._last_save_time = {}  # 最后保存时间 {group_id: timestamp}
        self._pending_save_task = None  # 待处理的保存任务
        
    def _get_group_db_path(self, group_id: str) -> str:
        """获取群聊专用的数据库路径"""
        if not self.memory_config.get("enable_group_isolation", True) or not group_id:
            return self.db_path
        
        # 为每个群创建独立的数据库文件
        db_dir = os.path.dirname(self.db_path)
        group_db_path = os.path.join(db_dir, f"memory_group_{group_id}.db")
        
        # 确保目录存在
        os.makedirs(os.path.dirname(group_db_path), exist_ok=True)
        
        return group_db_path
    
    def _extract_group_id_from_event(self, event: AstrMessageEvent) -> str:
        """从事件中提取群聊ID"""
        try:
            # 尝试从消息来源中提取群聊信息
            if hasattr(event, 'unified_msg_origin'):
                origin = event.unified_msg_origin
                # 如果是群聊，通常来源格式为 "group:群组ID" 或类似格式
                if isinstance(origin, str) and (origin.startswith('group:') or ':' in origin):
                    parts = origin.split(':')
                    if len(parts) > 1:
                        group_id = parts[1].strip()
                        # 过滤掉通用标识符，只返回实际群聊名称
                        if group_id.lower() not in ['groupmessage', 'group', '']:
                            return group_id
            
            # 尝试从消息对象中获取群聊信息
            if hasattr(event, 'message') and hasattr(event.message, 'group_id'):
                group_id = str(event.message.group_id)
                # 过滤掉通用标识符，只返回实际群聊名称
                if group_id.lower() not in ['groupmessage', 'group', '']:
                    return group_id
                
        except Exception as e:
            self._debug_log(f"提取群聊ID失败: {e}", "debug")
        
        # 如果无法提取到有效的群聊ID，返回空字符串（使用默认数据库）
        return ""
    
    async def _queue_save_memory_state(self, group_id: str = ""):
        """队列化保存操作，减少频繁的I/O"""
        try:
            # 获取或创建锁
            if group_id not in self._save_locks:
                self._save_locks[group_id] = asyncio.Lock()
            
            # 获取最后保存时间
            last_save = self._last_save_time.get(group_id, 0)
            current_time = time.time()
            
            # 如果距离上次保存时间少于2秒，延迟保存
            if current_time - last_save < 2:
                # 取消之前的保存任务
                if self._pending_save_task and not self._pending_save_task.done():
                    self._pending_save_task.cancel()
                
                # 创建新的延迟保存任务
                self._pending_save_task = asyncio.create_task(
                    self._delayed_save(group_id, current_time)
                )
            else:
                # 立即保存
                await self.save_memory_state(group_id)
                self._last_save_time[group_id] = current_time
                
        except Exception as e:
            self._debug_log(f"队列保存失败: {e}", "warning")
    
    async def _delayed_save(self, group_id: str, creation_time: float):
        """延迟保存任务"""
        try:
            # 延迟2秒执行
            await asyncio.sleep(2)
            
            # 检查是否还有新的保存请求
            if self._last_save_time.get(group_id, 0) > creation_time:
                return  # 如果有更新的请求，跳过这次保存
            
            # 执行实际保存
            await self.save_memory_state(group_id)
            self._last_save_time[group_id] = time.time()
            
        except asyncio.CancelledError:
            pass  # 任务被取消，正常情况
        except Exception as e:
            self._debug_log(f"延迟保存失败: {e}", "warning")
    
    def _debug_log(self, message: str, level: str = "debug"):
        """优化的调试日志输出，限制日志频率"""
        current_time = time.time()
        
        # 每分钟重置计数器
        if current_time - self.debug_log_reset_time > 60:
            self.debug_log_count = 0
            self.debug_log_reset_time = current_time
        
        # 限制每分钟最多10条调试日志
        if level == "debug" and self.debug_log_count >= 10:
            return
        
        if level == "debug":
            self.debug_log_count += 1
        
        # 使用不同的日志级别
        if level == "debug":
            logger.debug(message)
        elif level == "info":
            logger.info(message)
        elif level == "warning":
            logger.warning(message)
        elif level == "error":
            logger.error(message)
    
    async def initialize(self):
        """初始化记忆系统"""
        self._debug_log("开始初始化记忆系统...", "info")
        
        # 检查默认数据库文件状态
        if os.path.exists(self.db_path):
            file_size = os.path.getsize(self.db_path)
            self._debug_log(f"默认数据库文件存在，大小: {file_size} 字节", "info")
        else:
            self._debug_log("默认数据库文件不存在，将创建新数据库", "info")
        
        # 测试提供商连接 - 简化为单一日志
        llm_ready = False
        embedding_ready = False
        
        try:
            llm_provider = await self.get_llm_provider()
            if llm_provider:
                llm_ready = True
                
            embedding_provider = await self.get_embedding_provider()
            if embedding_provider:
                embedding_ready = True
                
            self._debug_log(f"提供商状态 - LLM: {'已连接' if llm_ready else '未连接'}, 嵌入: {'已连接' if embedding_ready else '未连接'}", "info")
        except Exception as e:
            self._debug_log("提供商连接异常，系统将继续运行", "warning")
        
        # 执行数据库迁移
        try:
            migration = DatabaseMigration(self.db_path, self.context)
            migration_success = await migration.run_smart_migration()
            
            if migration_success:
                self._debug_log("数据库迁移成功", "info")
                # 加载默认数据库（用于私有对话）
                self.load_memory_state()
                asyncio.create_task(self.memory_maintenance_loop())
                
                # 初始化嵌入向量缓存管理器
                self.embedding_cache = EmbeddingCacheManager(self, self.db_path)
                await self.embedding_cache.initialize()
                
                # 调度初始预计算任务
                if self.memory_graph.memories:
                    asyncio.create_task(self.embedding_cache.schedule_initial_precompute())
                    logger.info(f"已调度 {len(self.memory_graph.memories)} 条记忆的预计算任务")
                
                self._debug_log("记忆系统初始化完成", "info")
            else:
                self._debug_log("数据库迁移失败，记忆系统可能无法正常工作", "error")
                
        except Exception as e:
            self._debug_log(f"数据库迁移过程异常: {e}", "error")
        
    def load_memory_state(self, group_id: str = ""):
        """从数据库加载记忆状态"""
        import sqlite3
        import os
        
        # 获取对应的数据库路径
        db_path = self._get_group_db_path(group_id)
        
        if not os.path.exists(db_path):
            return
            
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                
                # 检查表是否存在
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='concepts'")
                if not cursor.fetchone():
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
                cursor.execute("SELECT id, concept_id, content, details, participants, location, emotion, tags, created_at, last_accessed, access_count, strength FROM memories")
                memories = cursor.fetchall()
                for memory_data in memories:
                    self.memory_graph.add_memory(
                        content=memory_data[2],
                        concept_id=memory_data[1],
                        memory_id=memory_data[0],
                        details=memory_data[3] or "",
                        participants=memory_data[4] or "",
                        location=memory_data[5] or "",
                        emotion=memory_data[6] or "",
                        tags=memory_data[7] or "",
                        created_at=memory_data[8],
                        last_accessed=memory_data[9],
                        access_count=memory_data[10],
                        strength=memory_data[11]
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
                    
            # 仅在成功加载时输出一次统计信息
            group_info = f" (群: {group_id})" if group_id else ""
            self._debug_log(f"记忆系统加载{group_info}，包含 {len(concepts)} 个概念，{len(memories)} 条记忆", "debug")
            
        except sqlite3.Error as e:
            self._debug_log(f"数据库加载失败: {e}", "error")
        except Exception as e:
            self._debug_log(f"状态加载异常: {e}", "error")

    async def save_memory_state(self, group_id: str = ""):
        """保存记忆状态到数据库"""
        import sqlite3
        try:
            # 获取对应的数据库路径
            db_path = self._get_group_db_path(group_id)
            
            # 确保数据库和表存在
            await self._ensure_database_structure(db_path)
            
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                
                # 使用事务确保数据一致性
                cursor.execute("BEGIN TRANSACTION")
                
                try:
                    
                    # 增量更新概念
                    for concept in self.memory_graph.concepts.values():
                        cursor.execute('''
                            INSERT OR REPLACE INTO concepts
                            (id, name, created_at, last_accessed, access_count)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (concept.id, concept.name, concept.created_at, concept.last_accessed, concept.access_count))
                    
                    # 增量更新记忆
                    for memory in self.memory_graph.memories.values():
                        cursor.execute('''
                            INSERT OR REPLACE INTO memories
                            (id, concept_id, content, details, participants,
                            location, emotion, tags, created_at, last_accessed, access_count, strength)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (memory.id, memory.concept_id, memory.content, memory.details,
                             memory.participants, memory.location, memory.emotion, memory.tags,
                             memory.created_at, memory.last_accessed, memory.access_count, memory.strength))
                    
                    # 增量更新连接
                    existing_connections = set()
                    cursor.execute("SELECT id FROM connections")
                    for row in cursor.fetchall():
                        existing_connections.add(row[0])
                    
                    # 更新现有连接
                    for conn in self.memory_graph.connections:
                        if conn.id in existing_connections:
                            cursor.execute('''
                                UPDATE connections
                                SET from_concept=?, to_concept=?, strength=?, last_strengthened=?
                                WHERE id=?
                            ''', (conn.from_concept, conn.to_concept, conn.strength, conn.last_strengthened, conn.id))
                        else:
                            cursor.execute('''
                                INSERT INTO connections (id, from_concept, to_concept, strength, last_strengthened)
                                VALUES (?, ?, ?, ?, ?)
                            ''', (conn.id, conn.from_concept, conn.to_concept, conn.strength, conn.last_strengthened))
                    
                    conn.commit()
                    # 简化的保存完成日志
                    group_info = f" (群: {group_id})" if group_id else ""
                    self._debug_log(f"记忆保存完成{group_info}: {len(self.memory_graph.concepts)}个概念, {len(self.memory_graph.memories)}条记忆", "debug")
                    
                except Exception as e:
                    conn.rollback()
                    self._debug_log(f"保存失败，已回滚: {e}", "error")
                    raise
                    
        except sqlite3.Error as e:
            self._debug_log(f"数据库保存错误: {e}", "error")
        except Exception as e:
            self._debug_log(f"保存过程异常: {e}", "error")
    
    async def _ensure_database_structure(self, db_path: str):
        """确保数据库和所需的表结构存在"""
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                
                # 检查表是否存在
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                existing_tables = {row[0] for row in cursor.fetchall()}
                
                # 创建所需的表（如果不存在）
                if 'concepts' not in existing_tables:
                    cursor.execute('''
                        CREATE TABLE concepts (
                            id TEXT PRIMARY KEY,
                            name TEXT NOT NULL,
                            created_at REAL,
                            last_accessed REAL,
                            access_count INTEGER DEFAULT 0
                        )
                    ''')
                    self._debug_log(f"创建表: concepts", "debug")
                
                if 'memories' not in existing_tables:
                    cursor.execute('''
                        CREATE TABLE memories (
                            id TEXT PRIMARY KEY,
                            concept_id TEXT NOT NULL,
                            content TEXT NOT NULL,
                            details TEXT,
                            participants TEXT,
                            location TEXT,
                            emotion TEXT,
                            tags TEXT,
                            created_at REAL,
                            last_accessed REAL,
                            access_count INTEGER DEFAULT 0,
                            strength REAL DEFAULT 1.0,
                            FOREIGN KEY (concept_id) REFERENCES concepts (id)
                        )
                    ''')
                    self._debug_log(f"创建表: memories", "debug")
                
                if 'connections' not in existing_tables:
                    cursor.execute('''
                        CREATE TABLE connections (
                            id TEXT PRIMARY KEY,
                            from_concept TEXT NOT NULL,
                            to_concept TEXT NOT NULL,
                            strength REAL DEFAULT 1.0,
                            last_strengthened REAL,
                            FOREIGN KEY (from_concept) REFERENCES concepts (id),
                            FOREIGN KEY (to_concept) REFERENCES concepts (id)
                        )
                    ''')
                    self._debug_log(f"创建表: connections", "debug")
                
                conn.commit()
                
        except sqlite3.Error as e:
            self._debug_log(f"创建数据库表结构失败: {e}", "error")
            raise
        except Exception as e:
            self._debug_log(f"确保数据库结构异常: {e}", "error")
            raise
    
    async def process_message(self, event: AstrMessageEvent):
        """处理消息，形成记忆（旧方法，保留兼容性）"""
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
                    
            # 根据回忆模式决定是否触发回忆
            recall_mode = self.memory_config["recall_mode"]
            should_trigger = False
            
            if recall_mode == "simple" or recall_mode == "embedding":
                # 关键词和嵌入模式每次都触发
                should_trigger = True
            elif recall_mode == "llm":
                # LLM模式按概率触发
                trigger_probability = self.memory_config.get("recall_trigger_probability", 0.6)
                should_trigger = random.random() < trigger_probability
            
            if should_trigger:
                recalled = await self.recall_memories("", event)
                if recalled:
                    logger.debug(f"触发了回忆: {recalled[:2]} (模式: {recall_mode})")
                    
        except Exception as e:
            logger.error(f"处理消息时出错: {e}")

    async def process_message_optimized(self, event: AstrMessageEvent, group_id: str = ""):
        """优化的消息处理，使用单次LLM调用"""
        try:
            # 获取完整的对话历史
            full_history = await self.get_conversation_history_full(event)
            if not full_history:
                return
            
            # 获取记忆形成概率
            formation_probability = self.memory_config.get("memory_formation_probability", 0.3)
            
            # 根据概率决定是否提取和创建记忆
            if random.random() > formation_probability:
                return

            # 使用批量提取器，单次LLM调用获取多个记忆
            extracted_memories = await self.batch_extractor.extract_memories_and_themes(full_history)
            
            if not extracted_memories:
                return
            
            # 批量处理提取的记忆
            themes = []
            concept_ids = []  # 存储创建的概念ID
            valid_memories = 0
            
            for memory_data in extracted_memories:
                try:
                    theme = str(memory_data.get("theme", "")).strip()
                    content = str(memory_data.get("content", "")).strip()
                    details = str(memory_data.get("details", "")).strip()
                    participants = str(memory_data.get("participants", "")).strip()
                    location = str(memory_data.get("location", "")).strip()
                    emotion = str(memory_data.get("emotion", "")).strip()
                    tags = str(memory_data.get("tags", "")).strip()
                    confidence = float(memory_data.get("confidence", 0.7))
                    
                    # 验证数据完整性
                    if not theme or not content:
                        continue
                    
                    # 根据置信度调整记忆强度
                    base_strength = 1.0
                    adjusted_strength = base_strength * max(0.0, min(1.0, confidence))
                    
                    # 添加概念和记忆
                    concept_id = self.memory_graph.add_concept(theme)
                    memory_id = self.memory_graph.add_memory(
                        content=content,
                        concept_id=concept_id,
                        details=details,
                        participants=participants,
                        location=location,
                        emotion=emotion,
                        tags=tags,
                        strength=adjusted_strength
                    )
                    
                    themes.append(theme)
                    concept_ids.append(concept_id)
                    valid_memories += 1
                    
                except (KeyError, ValueError, TypeError):
                    continue
            
            # 仅在成功创建记忆时输出一次日志
            if valid_memories > 0:
                group_info = f" (群: {group_id})" if group_id else ""
                self._debug_log(f"批量创建记忆{group_info}: {valid_memories}条", "debug")
            
            # 建立概念之间的连接 - 使用存储的概念ID
            if concept_ids:
                for concept_id in concept_ids:
                    try:
                        self.establish_connections(concept_id, themes)
                    except Exception:
                        continue
            
            # 根据回忆模式决定是否触发回忆
            recall_mode = self.memory_config["recall_mode"]
            should_trigger = False
            
            if recall_mode == "simple" or recall_mode == "embedding":
                # 关键词和嵌入模式每次都触发
                should_trigger = True
            elif recall_mode == "llm":
                # LLM模式按概率触发
                trigger_probability = self.memory_config.get("recall_trigger_probability", 0.6)
                should_trigger = random.random() < trigger_probability
            
            if should_trigger:
                # 修复：使用正确的回忆方法
                if recall_mode == "llm":
                    recalled = await self._recall_llm("", event)
                elif recall_mode == "embedding":
                    recalled = await self._recall_embedding("")
                else:
                    recalled = await self._recall_simple("")
                    
                if recalled:
                    self._debug_log(f"回忆触发: {len(recalled)}条", "debug")
                    
        except Exception as e:
            self._debug_log(f"消息处理失败: {e}", "error")
            # 回退到旧方法
            await self.process_message(event)
    
    async def get_conversation_history(self, event: AstrMessageEvent) -> List[str]:
        """获取对话历史（兼容旧版本）"""
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

    async def get_conversation_history_full(self, event: AstrMessageEvent) -> List[Dict[str, Any]]:
        """获取包含完整信息的对话历史"""
        try:
            uid = event.unified_msg_origin
            curr_cid = await self.context.conversation_manager.get_curr_conversation_id(uid)
            if curr_cid:
                conversation = await self.context.conversation_manager.get_conversation(uid, curr_cid)
                if conversation and conversation.history:
                    history = json.loads(conversation.history)
                    # 添加发送者信息和时间戳
                    full_history = []
                    for msg in history[-20:]:  # 最近20条，避免token过多，等会加配置
                        full_msg = {
                            "role": msg.get("role", "user"),
                            "content": msg.get("content", ""),
                            "sender_name": msg.get("sender_name", "用户"),
                            "timestamp": msg.get("timestamp", time.time())
                        }
                        full_history.append(full_msg)
                    return full_history
            return []
        except Exception as e:
            logger.error(f"获取完整对话历史失败: {e}")
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
2. 每个主题可以包含多个相关关键词，用逗号分隔
3. 返回格式：主题1关键词1,主题1关键词2,主题2关键词1,主题2关键词2
4. 每个关键词2-4个汉字
5. 不要包含解释，只返回主题列表
6. 例如：工作,项目,会议,学习,考试,复习
"""
            
            provider = await self.get_llm_provider()
            if provider:
                response = await provider.text_chat(
                    prompt=prompt,
                    contexts=[],
                    system_prompt="你是一个主题提取助手，请准确提取对话的核心主题。"
                )
                
                themes_text = response.completion_text.strip()
                # 清理和分割主题，支持逗号分隔的多个关键词
                themes = [theme.strip() for theme in themes_text.replace("，", ",").split(",") if theme.strip()]
                return themes[:8]  # 最多返回8个关键词/主题
                
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
            1. 如果记忆内容涉及Bot的发言，请使用第一人称"我"来表述
            2. 如果记忆内容涉及用户的发言，请使用第三人称
            3. 简洁自然
            4. 包含关键信息
            5. 不超过50字
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
        try:
            if concept_id not in self.memory_graph.concepts:
                logger.warning(f"概念ID不存在: {concept_id}")
                return
                
            current_concept = self.memory_graph.concepts[concept_id]
            
            for other_theme in themes:
                if other_theme != current_concept.name:
                    other_concept = None
                    for concept in self.memory_graph.concepts.values():
                        if concept.name == other_theme:
                            other_concept = concept
                            break
                    
                    if other_concept and other_concept.id != concept_id:
                        self.memory_graph.add_connection(concept_id, other_concept.id)
                        
        except Exception as e:
            logger.error(f"建立概念连接时出错: {e}, 概念ID: {concept_id}, 主题: {themes}")
    
    async def recall_memories_full(self, keyword: str) -> List['Memory']:
        """回忆相关记忆并返回完整的Memory对象"""
        try:
            # 这是一个简化的实现，用于演示目的
            # 在实际应用中，这里应该有更复杂的逻辑来匹配关键词
            related_memories = []
            keyword_lower = keyword.lower()

            for memory in self.memory_graph.memories.values():
                if keyword_lower in memory.content.lower():
                    related_memories.append(memory)
            
            return related_memories
                
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
            
            # 增强的关键词匹配，支持多关键词匹配
            related_memories = []
            keyword_lower = keyword.lower()
            
            # 直接概念匹配，支持逗号分隔的多关键词
            for concept in self.memory_graph.concepts.values():
                concept_name_lower = concept.name.lower()
                
                # 检查概念名称是否包含任意关键词
                concept_keywords = concept_name_lower.split(',')
                for concept_keyword in concept_keywords:
                    concept_keyword = concept_keyword.strip()
                    if (keyword_lower in concept_keyword or concept_keyword in keyword_lower or
                        any(kw.strip() in concept_keyword for kw in keyword_lower.split(','))):
                        concept_memories = [m for m in self.memory_graph.memories.values()
                                          if m.concept_id == concept.id]
                        # 按记忆强度排序
                        concept_memories.sort(key=lambda m: m.strength, reverse=True)
                        for memory in concept_memories[:2]:  # 每个概念最多2条
                            if memory.content not in related_memories:
                                related_memories.append(memory.content)
                        break
            
            # 内容关键词匹配
            for memory in self.memory_graph.memories.values():
                if keyword_lower in memory.content.lower():
                    if memory.content not in related_memories:
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
                    self._debug_log("LLM响应中未找到JSON格式", "warning")
                    return [] # 如果没有找到JSON或解析失败
                except json.JSONDecodeError as e:
                    self._debug_log(f"JSON解析失败: {e}, 响应: {completion_text[:200]}...", "error")
                    return [] # JSON解析失败
                except Exception as e:
                    self._debug_log(f"JSON解析异常: {e}", "error")
                    return []
            
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
            
            # 扩散参数，以后加配置文件
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
        db_dir = os.path.dirname(self.db_path)
        
        while True:
            try:
                consolidation_interval = self.memory_config["consolidation_interval_hours"] * 3600
                await asyncio.sleep(consolidation_interval)  # 按配置间隔检查
                
                maintenance_actions = []
                
                # 处理默认数据库（私有对话）
                if self.memory_config["enable_forgetting"]:
                    await self.forget_memories()
                    maintenance_actions.append("遗忘")
                
                if self.memory_config["enable_consolidation"]:
                    await self.consolidate_memories()
                    maintenance_actions.append("整理")
                
                await self.save_memory_state()
                maintenance_actions.append("保存")
                
                # 如果启用了群聊隔离，处理所有群聊数据库
                if self.memory_config.get("enable_group_isolation", True):
                    # 扫描群聊数据库文件
                    group_files = []
                    if os.path.exists(db_dir):
                        for filename in os.listdir(db_dir):
                            if filename.startswith("memory_group_") and filename.endswith(".db"):
                                group_id = filename[12:-3]  # 提取群聊ID
                                group_files.append(group_id)
                    
                    # 为每个群聊数据库执行维护
                    for group_id in group_files:
                        try:
                            # 清空当前记忆图，加载群聊数据库
                            self.memory_graph = MemoryGraph()
                            self.load_memory_state(group_id)
                            
                            # 执行群聊的维护操作
                            if self.memory_config["enable_forgetting"]:
                                await self.forget_memories()
                            
                            if self.memory_config["enable_consolidation"]:
                                await self.consolidate_memories()
                            
                            # 保存群聊数据库
                            await self.save_memory_state(group_id)
                            
                            self._debug_log(f"群聊 {group_id} 维护完成", "debug")
                            
                        except Exception as group_e:
                            self._debug_log(f"群聊 {group_id} 维护失败: {group_e}", "warning")
                
                # 简化维护日志输出
                if maintenance_actions:
                    action_text = f"记忆维护完成: {', '.join(maintenance_actions)}"
                    if self.memory_config.get("enable_group_isolation", True):
                        action_text += f" (包含 {len(group_files) if 'group_files' in locals() else 0} 个群聊)"
                    self._debug_log(action_text, "debug")
                
            except Exception as e:
                self._debug_log(f"记忆维护失败: {e}", "error")
    
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
        
        # 仅在有实际清理时输出日志
        if len(memories_to_remove) > 0 or len(connections_to_remove) > 0:
            self._debug_log(f"遗忘完成: 清理{len(memories_to_remove)}条记忆, {len(connections_to_remove)}个连接", "debug")
    
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
        
        # 仅在有实际合并时输出日志
        if consolidation_count > 0:
            self._debug_log(f"记忆整理完成: 合并{consolidation_count}条相似记忆", "debug")
    
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
    
    async def get_memory_stats(self) -> dict:
        """获取记忆统计信息"""
        return {
            "concepts": len(self.memory_graph.concepts),
            "memories": len(self.memory_graph.memories),
            "connections": len(self.memory_graph.connections),
            "recall_mode": self.memory_config['recall_mode'],
            "llm_provider": self.memory_config['llm_provider'],
            "embedding_provider": self.memory_config['embedding_provider'],
            "enable_forgetting": self.memory_config['enable_forgetting'],
            "enable_consolidation": self.memory_config['enable_consolidation'],
        }

    async def get_llm_provider(self):
        """使用配置文件指定的提供商"""
        try:
            provider_id = self.memory_config.get('llm_provider')
            if not provider_id:
                logger.error("插件配置中未指定 'llm_provider'")
                return None

            # 1. 尝试通过ID精确查找
            provider = self.context.get_provider_by_id(provider_id)
            if provider:
                logger.debug(f"通过ID '{provider_id}' 成功获取LLM提供商")
                return provider

            # 2. 如果ID查找失败，尝试通过名称模糊匹配
            all_providers = self.context.get_all_providers()
            for p in all_providers:
                p_name = getattr(getattr(p, 'meta', None), 'name', getattr(p, 'name', None))
                if p_name and p_name.lower() == provider_id.lower():
                    logger.debug(f"通过名称 '{provider_id}' 成功获取LLM提供商")
                    return p
            
            logger.error(f"无法找到配置的LLM提供商: '{provider_id}'")
            available_ids = [f"ID: {getattr(p, 'id', 'N/A')}, Name: {getattr(p, 'name', 'N/A')}" for p in all_providers]
            logger.error(f"可用提供商: {available_ids}")
            return None
            
        except Exception as e:
            logger.error(f"获取LLM提供商失败: {e}", exc_info=True)
            return None

    async def get_embedding_provider(self):
        """使用配置文件指定的提供商"""
        try:
            provider_id = self.memory_config['embedding_provider']
            
            # 获取所有已注册的提供商
            all_providers = self.context.get_all_providers()
            logger.debug(f"所有可用嵌入提供商: {[getattr(p, 'id', 'unknown') for p in all_providers]}")
            
            # 精确匹配配置的提供商ID
            for provider in all_providers:
                if hasattr(provider, 'id') and provider.id == provider_id:
                    logger.debug(f"成功使用配置指定的嵌入提供商: {provider_id}")
                    return provider
            
            # 如果找不到，尝试通过ID获取
            provider = self.context.get_provider_by_id(provider_id)
            if provider:
                logger.debug(f"通过ID使用嵌入提供商: {provider_id}")
                return provider
            
            # 最后尝试通过名称匹配
            for provider in all_providers:
                if hasattr(provider, 'meta') and hasattr(provider.meta, 'name'):
                    if provider.meta.name == provider_id:
                        logger.debug(f"通过名称匹配使用嵌入提供商: {provider_id}")
                        return provider
            
            logger.error(f"无法找到配置的嵌入提供商: {provider_id}")
            return None
            
        except Exception as e:
            logger.error(f"获取嵌入提供商失败: {e}")
            return None

    async def get_embedding(self, text: str) -> List[float]:
        """获取文本的嵌入向量 - 优先使用缓存"""
        try:
            # 如果启用了嵌入向量缓存，尝试从缓存获取
            if self.embedding_cache:
                # 生成一个临时ID用于缓存查询
                temp_id = f"temp_{hash(text)}"
                cached_embedding = await self.embedding_cache.get_embedding(temp_id, text)
                if cached_embedding:
                    return cached_embedding
            
            # 缓存未命中或未启用，直接计算
            provider = await self.get_embedding_provider()
            if not provider:
                logger.debug("嵌入提供商不可用")
                return []
            
            # 尝试多种嵌入方法
            methods = ['embedding', 'embeddings', 'get_embedding', 'get_embeddings']
            for method_name in methods:
                if hasattr(provider, method_name):
                    try:
                        method = getattr(provider, method_name)
                        result = await method(text)
                        if result and isinstance(result, list) and len(result) > 0:
                            return result
                    except Exception as e:
                        logger.debug(f"方法 {method_name} 失败: {e}")
                        continue
            
            # 尝试使用LLM提供商的嵌入功能
            if hasattr(provider, 'text_chat'):
                try:
                    # 构建嵌入请求
                    prompt = f"请将以下文本转换为嵌入向量: {text}"
                    response = await provider.text_chat(
                        prompt=prompt,
                        contexts=[],
                        system_prompt="请将文本转换为数值向量表示"
                    )
                    # 这里假设LLM可能返回嵌入向量
                    if response and hasattr(response, 'embedding'):
                        return response.embedding
                except Exception as e:
                    logger.debug(f"LLM嵌入方法失败: {e}")
                
            logger.debug("所有嵌入方法均失败")
            return []
                
        except Exception as e:
            logger.error(f"获取嵌入向量失败: {e}")
            return []

    async def inject_memories_to_context(self, event: AstrMessageEvent):
        """将相关记忆注入到对话上下文中"""
        try:
            if not self.memory_config.get("enable_enhanced_memory", True):
                return
            
            current_message = event.message_str.strip()
            if not current_message:
                return
            
            # 避免重复注入：检查是否已经有记忆上下文
            if hasattr(event, 'context_extra') and event.context_extra and 'memory_context' in event.context_extra:
                return
            
            # 短消息过滤：避免为过短的消息注入记忆
            if len(current_message) < 3:
                return
            
            # 使用增强记忆召回系统获取相关记忆
            from .enhanced_memory_recall import EnhancedMemoryRecall
            
            enhanced_recall = EnhancedMemoryRecall(self)
            results = await enhanced_recall.recall_all_relevant_memories(
                query=current_message,
                max_memories=self.memory_config.get("max_injected_memories", 5)
            )
            
            # 过滤低相关性的记忆
            threshold = self.memory_config.get("memory_injection_threshold", 0.3)
            filtered_results = [r for r in results if hasattr(r, 'relevance_score') and r.relevance_score >= threshold]
            
            if filtered_results:
                # 使用增强格式化
                memory_context = enhanced_recall.format_memories_for_llm(filtered_results)
                
                # 注入到AstrBot的上下文中
                if not hasattr(event, 'context_extra'):
                    event.context_extra = {}
                event.context_extra["memory_context"] = memory_context
                
                self._debug_log(f"已注入 {len(filtered_results)} 条记忆到上下文", "debug")
                
        except Exception as e:
            self._debug_log(f"注入记忆到上下文失败: {e}", "warning")

    async def query_memory(self, query: str, event: AstrMessageEvent = None) -> List[str]:
        """记忆查询接口"""
        try:
            if not query:
                return []
                
            # 使用统一的回忆接口
            return await self.recall_memories(query, event)
            
        except Exception as e:
            logger.error(f"记忆查询失败: {e}")
            return []

    async def recall_memories(self, keyword: str, event: AstrMessageEvent = None) -> List[str]:
        """回忆相关记忆，回忆接口"""
        try:
            if not self.memory_graph.memories:
                return []
                
            # 根据配置的回忆模式选择合适的方法
            recall_mode = self.memory_config["recall_mode"]
            
            if recall_mode == "llm":
                return await self._recall_llm(keyword, event)
            elif recall_mode == "embedding":
                return await self._recall_embedding(keyword)
            elif recall_mode == "activation":
                return await self._recall_by_activation(keyword)
            else:
                return await self._recall_simple(keyword)
                
        except Exception as e:
            logger.error(f"回忆记忆失败: {e}")
            return await self._recall_simple(keyword)

    async def recall_relevant_memories(self, message: str) -> List[str]:
        """基于消息内容智能召回相关记忆"""
        try:
            if not self.memory_graph.memories:
                return []
            
            # 使用增强记忆召回系统
            from .enhanced_memory_recall import EnhancedMemoryRecall
            
            enhanced_recall = EnhancedMemoryRecall(self)
            results = await enhanced_recall.recall_all_relevant_memories(
                query=message,
                max_memories=self.memory_config.get("max_injected_memories", 5)
            )
            
            # 返回记忆内容列表
            return [result.memory for result in results]
            
        except Exception as e:
            logger.error(f"增强记忆召回失败: {e}")
            return []

    def format_memories_for_context(self, memories: List[str]) -> str:
        """将记忆格式化为适合LLM理解的增强上下文"""
        try:
            if not memories:
                return ""
            
            # 使用增强格式化
            from .enhanced_memory_recall import EnhancedMemoryRecall, MemoryRecallResult
            
            # 创建增强结果用于格式化
            enhanced_results = []
            for memory in memories:
                enhanced_results.append(MemoryRecallResult(
                    memory=memory,
                    relevance_score=0.8,
                    memory_type='context_injection',
                    concept_id='',
                    metadata={'source': 'auto_injection'}
                ))
            
            enhanced_recall = EnhancedMemoryRecall(self)
            return enhanced_recall.format_memories_for_llm(enhanced_results)
            
        except Exception as e:
            logger.error(f"上下文格式化失败: {e}")
            return ""


class BatchMemoryExtractor:
    """记忆提取器，通过LLM调用获取多个记忆点和主题"""
    
    def __init__(self, memory_system):
        self.memory_system = memory_system
    
    async def extract_memories_and_themes(self, conversation_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        通过LLM调用同时提取主题和记忆内容
        
        Args:
            conversation_history: 包含完整信息的对话历史，每项包含role, content, sender_name, timestamp
            
        Returns:
            包含主题和记忆内容的列表，每项包含theme, memory_content, confidence
        """
        if not conversation_history:
            return []
        
        # 构建包含完整信息的对话历史
        formatted_history = self._format_conversation_history(conversation_history)
        
        prompt = f"""请从以下对话中提取丰富、详细、准确的记忆信息。对话包含完整的发送者信息和时间戳。

对话历史：
{formatted_history}

任务要求：
1. 识别所有有意义的记忆点，包括：
   - 重要事件（高置信度：0.7-1.0）
   - 日常小事（中置信度：0.4-0.7）
   - 有趣细节（低置信度：0.1-0.4）
2. 为每个记忆生成完整信息：
   - 主题（theme）：核心关键词，用逗号分隔
   - 内容（content）：简洁的核心记忆
   - 细节（details）：具体细节和背景，丰富、详细、准确的记忆信息
   - 参与者（participants）：涉及的人物，特别注意：如果发言者是[Bot]，则使用"我"或Bot的身份作为参与者；如果是用户，则使用用户名称
   - 地点（location）：相关场景
   - 情感（emotion）：情感色彩
   - 标签（tags）：分类标签
   - 置信度（confidence）：0-1之间的数值
3. 可以生成多个记忆，包括小事
4. 返回JSON格式

特别注意：
- 请仔细区分[Bot]和用户的发言
- 当[Bot]发言时，在参与者字段使用第一人称"我"而不是"其他用户"
- 确保LLM在后续上下文引用时能准确区分Bot的自我表述与用户的外部输入

返回格式：
{{
  "memories": [
    {{
      "theme": "工作,项目",
      "content": "今天完成了项目演示",
      "details": "丰富、详细、准确的记忆信息",
      "participants": "我,客户,项目经理",
      "location": "会议室",
      "emotion": "兴奋,满意",
      "tags": "重要,成功",
      "confidence": 0.9
    }},
    {{
      "theme": "午餐,同事",
      "content": "丰富、详细、准确的记忆信息",
      "details": "讨论了周末的计划",
      "participants": "我,小王",
      "location": "公司食堂",
      "emotion": "轻松,愉快",
      "tags": "日常,社交",
      "confidence": 0.5
    }}
  ]
}}

要求：
- 捕捉所有有意义的对话内容
- 小事也可以记录，降低置信度即可
- 内容要具体、生动
- 可以生成5-8个记忆
- 只返回JSON
"""

        try:
            provider = await self.memory_system.get_llm_provider()
            if not provider:
                logger.warning("LLM提供商不可用，使用简单提取")
                return await self._fallback_extraction(conversation_history)
            
            try:
                response = await provider.text_chat(
                    prompt=prompt,
                    contexts=[],
                    system_prompt="你是一个专业的记忆提取助手，请准确提取对话中的关键信息。"
                )
                
                # 解析JSON响应
                result = self._parse_batch_response(response.completion_text)
                return result
                
            except Exception as e:
                # 网络错误或LLM服务不可用
                if "upstream" in str(e).lower() or "connection" in str(e).lower():
                    logger.warning(f"LLM服务连接失败，使用简单提取: {e}")
                else:
                    logger.error(f"LLM调用失败: {e}")
                return await self._fallback_extraction(conversation_history)
            
        except Exception as e:
            logger.error(f"批量记忆提取失败: {e}")
            return await self._fallback_extraction(conversation_history)
    
    def _format_conversation_history(self, history: List[Dict[str, Any]]) -> str:
        """格式化对话历史，包含完整信息，并区分Bot和用户发言"""
        formatted_lines = []
        for msg in history:
            content = msg.get('content', '')
            timestamp = msg.get('timestamp', '')
            role = msg.get('role', 'user')
            sender = msg.get('sender_name', '用户')
            
            # 格式化时间戳
            if isinstance(timestamp, (int, float)):
                dt = datetime.fromtimestamp(timestamp)
                time_str = dt.strftime('%m-%d %H:%M')
            else:
                time_str = str(timestamp)
            
            # 根据角色区分Bot和用户消息
            if role == "assistant":
                # Bot消息，标识为"[Bot]"
                formatted_lines.append(f"[{time_str}] [Bot]: {content}") #会改
            else:
                # 用户消息，保持原格式
                formatted_lines.append(f"[{time_str}] {sender}: {content}")
        
        return "\n".join(formatted_lines)
    
    def _parse_batch_response(self, response_text: str) -> List[Dict[str, Any]]:
        """解析批量提取的LLM响应"""
        try:
            # 清理响应文本，处理中文引号和格式问题
            cleaned_text = response_text
            for old, new in [('“', '"'), ('”', '"'), ('‘', "'"), ('’', "'"), ('，', ','), ('：', ':')]:
                cleaned_text = cleaned_text.replace(old, new)
            
            # 尝试多种JSON提取方式
            json_patterns = [
                r'\{[^{}]*"memories"[^{}]*\}',  # 简单JSON对象
                r'\{.*"memories"\s*:\s*\[.*\].*\}',  # 包含memories数组的完整对象
                r'\{.*\}',  # 最宽泛的匹配
            ]
            
            json_str = None
            for pattern in json_patterns:
                matches = re.findall(pattern, cleaned_text, re.DOTALL)
                if matches:
                    json_str = matches[-1]  # 取最后一个匹配
                    break
            
            if not json_str:
                return []
            
            # 修复常见的JSON格式问题
            json_str = re.sub(r',\s*}', '}', json_str)
            json_str = re.sub(r',\s*]', ']', json_str)
            json_str = re.sub(r'([{,]\s*)(\w+):', r'\1"\2":', json_str)  # 修复未加引号的键
            
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError:
                # 更激进的修复，记录错误但不输出过多日志
                json_str = re.sub(r'([{,]\s*)"([^"]*)"\s*:\s*([^",}\]]+)([,\}])', r'\1"\2": "\3"\4', json_str)
                data = json.loads(json_str)
            
            memories = data.get("memories", [])
            if not isinstance(memories, list):
                return []
            
            # 过滤和验证记忆
            filtered_memories = []
            for i, mem in enumerate(memories):
                try:
                    if not isinstance(mem, dict):
                        continue
                    
                    confidence = float(mem.get("confidence", 0.7))
                    theme = str(mem.get("theme", "")).strip()
                    content = str(mem.get("content", "")).strip()
                    details = str(mem.get("details", "")).strip()
                    participants = str(mem.get("participants", "")).strip()
                    location = str(mem.get("location", "")).strip()
                    emotion = str(mem.get("emotion", "")).strip()
                    tags = str(mem.get("tags", "")).strip()
                    
                    # 清理主题中的特殊字符
                    theme = re.sub(r'[^\w\u4e00-\u9fff,，]', '', theme)
                    
                    if theme and content and confidence > 0.3:
                        filtered_memories.append({
                            "theme": theme,
                            "content": content,
                            "details": details,
                            "participants": participants,
                            "location": location,
                            "emotion": emotion,
                            "tags": tags,
                            "confidence": max(0.0, min(1.0, confidence))
                        })
                        
                except (ValueError, TypeError):
                    continue
            
            return filtered_memories
            
        except Exception:
            return []
    
    async def _fallback_extraction(self, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """回退到简单提取模式"""
        if not history:
            return []
        
        # 简单关键词提取
        text = " ".join([msg.get('content', '') for msg in history])
        themes = self._extract_simple_themes(text)
        
        memories = []
        for theme in themes[:3]:
            memory_content = f"我们聊过关于{theme}的事情"
            memories.append({
                "theme": theme,
                "memory_content": memory_content,
                "confidence": 0.5
            })
        
        return memories
    
    def _extract_simple_themes(self, text: str) -> List[str]:
        """简单主题提取"""
        # 提取中文关键词
        words = re.findall(r'\b[\u4e00-\u9fff]{2,4}\b', text)
        word_freq = {}
        
        for word in words:
            if len(word) >= 2 and word not in ["你好", "谢谢", "再见"]:
                word_freq[word] = word_freq.get(word, 0) + 1
        
        # 返回频率最高的关键词
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        return [word for word, freq in sorted_words[:5]]


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
                   details: str = "", participants: str = "", location: str = "",
                   emotion: str = "", tags: str = "", created_at: float = None,
                   last_accessed: float = None, access_count: int = 0,
                   strength: float = 1.0) -> str:
        """添加记忆"""
        if memory_id is None:
            memory_id = f"memory_{int(time.time() * 1000)}"
        
        memory = Memory(
            id=memory_id,
            concept_id=concept_id,
            content=content,
            details=details,
            participants=participants,
            location=location,
            emotion=emotion,
            tags=tags,
            created_at=created_at,
            last_accessed=last_accessed,
            access_count=access_count,
            strength=strength
        )
        self.memories[memory_id] = memory
        
        # 如果启用了嵌入向量缓存，调度预计算任务
        if hasattr(self, 'embedding_cache') and self.embedding_cache:
            asyncio.create_task(self.embedding_cache.schedule_precompute_task([memory_id], priority=3))
        
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
    details: str = ""  # 详细描述
    participants: str = ""  # 参与者
    location: str = ""  # 地点
    emotion: str = ""  # 情感
    tags: str = ""  # 标签
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
