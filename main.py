import asyncio
import json
import time
import random
import sqlite3
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
import os
from dataclasses import dataclass

from astrbot.api.provider import ProviderRequest
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from .database_migration import SmartDatabaseMigration
from .enhanced_memory_display import EnhancedMemoryDisplay
from .embedding_cache_manager import EmbeddingCacheManager
from .enhanced_memory_recall import EnhancedMemoryRecall
from .memory_graph_visualization import MemoryGraphVisualizer
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api import AstrBotConfig
from astrbot.api.star import StarTools
from .resource_management import resource_manager

@register("astrbot_plugin_memora_connect", "qa296", "赋予AI记忆与印象/好感的能力！  模仿生物海马体，通过概念节点与关系连接构建记忆网络，具备记忆形成、提取、遗忘、巩固功能，采用双峰时间分布回顾聊天，打造有记忆能力的智能对话体验。", "0.2.5", "https://github.com/qa296/astrbot_plugin_memora_connect")
class MemoraConnectPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        data_dir = StarTools.get_data_dir() / "memora_connect"
        self.memory_system = MemorySystem(context, config, data_dir)
        self.memory_display = EnhancedMemoryDisplay(self.memory_system)
        self.graph_visualizer = MemoryGraphVisualizer(self.memory_system)
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
        # 检查记忆系统是否启用
        if not self.memory_system.config_manager.is_memory_system_enabled():
            yield event.plain_result("记忆系统已禁用，无法使用回忆功能。")
            return
        memories = await self.memory_system.recall_memories_full(keyword)
        response = self.memory_display.format_memory_search_result(memories, keyword)
        yield event.plain_result(response)

    @memory.command("状态")
    async def memory_status(self, event: AstrMessageEvent):
        # 检查记忆系统是否启用
        if not self.memory_system.config_manager.is_memory_system_enabled():
            yield event.plain_result("记忆系统已禁用，无法查看状态。")
            return
            
        stats = self.memory_display.format_memory_statistics()
        yield event.plain_result(stats)
    @memory.command("印象")
    async def memory_impression(self, event: AstrMessageEvent, name: str):
        """查询人物印象摘要和相关记忆"""
        # 检查记忆系统是否启用
        if not self.memory_system.config_manager.is_memory_system_enabled():
            yield event.plain_result("记忆系统已禁用，无法查询印象。")
            return
            
        try:
            # 获取群组ID
            group_id = self.memory_system._extract_group_id_from_event(event)
            
            # 获取印象摘要
            impression_summary = self.memory_system.get_person_impression_summary(group_id, name)
            
            # 获取印象记忆列表
            impression_memories = self.memory_system.get_person_impression_memories(group_id, name, limit=5)
            
            # 格式化响应
            response_parts = []
            
            # 添加印象摘要
            if impression_summary:
                score = impression_summary.get("score", 0.5)
                score_desc = self.memory_system._score_to_description(score)
                response_parts.append(f"📝 {name} 的印象摘要:")
                response_parts.append(f"   印象: {impression_summary.get('summary', '无')}")
                response_parts.append(f"   好感度: {score_desc} ({score:.2f})")
                response_parts.append(f"   记忆数: {impression_summary.get('memory_count', 0)}")
                response_parts.append(f"   更新时间: {impression_summary.get('last_updated', '无')}")
            else:
                response_parts.append(f"📝 尚未建立对 {name} 的印象")
            
            # 添加相关记忆
            if impression_memories:
                response_parts.append("\n📚 相关记忆:")
                for i, memory in enumerate(impression_memories, 1):
                    response_parts.append(f"   {i}. {memory['content']}")
                    if memory.get('details'):
                        response_parts.append(f"      详情: {memory['details']}")
                    response_parts.append(f"      好感度: {memory['score']:.2f} | 时间: {memory['last_accessed']}")
            else:
                response_parts.append(f"\n📚 暂无关于 {name} 的印象记忆")
            
            # 组合响应
            response = "\n".join(response_parts)
            yield event.plain_result(response)
            
        except Exception as e:
            logger.error(f"查询印象失败: {e}")
            yield event.plain_result(f"查询 {name} 的印象时出现错误")
    
    @memory.command("图谱")
    async def memory_graph(self, event: AstrMessageEvent, layout_style: str = "auto"):
        """生成记忆图谱可视化图片
        
        Args:
            layout_style: 布局风格，可选值：
                - auto: 自适应布局（根据图的复杂度自动选择最适合的布局，默认）
                - force_directed: 力导向布局
                - circular: 圆形布局
                - kamada_kawai: Kamada-Kawai布局
                - spectral: 谱布局
                - community: 社区布局
                - hierarchical: 多层次布局
        """
        # 检查记忆系统是否启用
        if not self.memory_system.config_manager.is_memory_system_enabled():
            yield event.plain_result("记忆系统已禁用，无法生成图谱。")
            return
            
        try:
            # 发送生成中的提示
            yield event.plain_result(f"🔄 正在生成记忆图谱（布局风格: {layout_style}），请稍候...")
            
            # 异步生成图谱图片
            image_path = await self.graph_visualizer.generate_graph_image(layout_style=layout_style)
            
            if image_path:
                # 检查文件是否存在
                if os.path.exists(image_path):
                    # 发送图片消息
                    try:
                        # 尝试使用 AstrBot 的图片发送功能
                        if hasattr(event, 'send_image'):
                            await event.send_image(image_path)
                            yield event.plain_result(f"✅ 记忆图谱已生成！（布局风格: {layout_style}）")
                        else:
                            # 如果不支持直接发送图片，尝试使用其他方法
                            yield event.image_result(image_path)
                    except Exception as img_e:
                        logger.error(f"发送图片失败: {img_e}", exc_info=True)
                        # 如果发送图片失败，发送文件路径
                        yield event.plain_result(f"✅ 记忆图谱已生成！（布局风格: {layout_style}）\n图片路径: {image_path}")
                else:
                    yield event.plain_result("❌ 图谱文件生成失败，请检查权限和磁盘空间。")
            else:
                yield event.plain_result("❌ 记忆图谱生成失败，可能是因为：\n1. 未安装依赖库（networkx, matplotlib）\n2. 记忆数据为空\n3. 系统错误")
                
        except Exception as e:
            logger.error(f"生成记忆图谱失败: {e}", exc_info=True)
            yield event.plain_result(f"❌ 生成记忆图谱时出现错误: {str(e)}")
    
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """监听所有消息，形成记忆并注入相关记忆"""
        if not self._initialized:
            self._debug_log("记忆系统尚未初始化完成，跳过消息处理", "debug")
            return
        # 检查记忆系统是否启用
        if not self.memory_system.config_manager.is_memory_system_enabled():
            return
            
        try:
            # 提取群聊ID，用于群聊隔离
            group_id = event.get_group_id() if event.get_group_id() else ""
            
            # 1. 为当前群聊加载相应的记忆状态（异步优化）
            if group_id and self.memory_system.memory_config.get("enable_group_isolation", True):
                # 清空当前记忆图，重新加载群聊特定的记忆
                self.memory_system.memory_graph = MemoryGraph()
                self.memory_system.load_memory_state(group_id)
            
            # 2. 注入相关记忆到上下文（快速异步操作）
            self.memory_system._create_managed_task(self.memory_system.inject_memories_to_context(event))
            
            # 3. 消息处理使用异步队列，避免阻塞主流程
            self.memory_system._create_managed_task(self._process_message_async(event, group_id))
                
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
        """插件卸载时保存记忆并清理资源"""
        self._debug_log("开始插件终止流程，清理所有资源", "info")
        
        try:
            # 1. 停止维护循环
            if hasattr(self.memory_system, '_should_stop_maintenance'):
                self.memory_system._should_stop_maintenance.set()
            if hasattr(self.memory_system, '_maintenance_task') and self.memory_system._maintenance_task:
                # 等待维护任务正常退出
                try:
                    await asyncio.wait_for(self.memory_system._maintenance_task, timeout=10.0)
                except asyncio.TimeoutError:
                    # 如果超时，取消任务
                    self.memory_system._maintenance_task.cancel()
                    try:
                        await self.memory_system._maintenance_task
                    except asyncio.CancelledError:
                        pass
                        
            # 2. 取消所有托管的异步任务
            if hasattr(self.memory_system, '_managed_tasks'):
                await self.memory_system._cancel_all_managed_tasks()
            
            # 3. 等待待处理的保存任务完成
            if hasattr(self.memory_system, '_pending_save_task') and self.memory_system._pending_save_task and not self.memory_system._pending_save_task.done():
                try:
                    await asyncio.wait_for(self.memory_system._pending_save_task, timeout=5.0)
                except asyncio.TimeoutError:
                    self.memory_system._pending_save_task.cancel()
                    try:
                        await self.memory_system._pending_save_task
                    except asyncio.CancelledError:
                        pass
                    
            # 4. 清理嵌入向量缓存
            if hasattr(self.memory_system, 'embedding_cache') and self.memory_system.embedding_cache:
                try:
                    await self.memory_system.embedding_cache.cleanup()
                except Exception as e:
                    logger.warning(f"清理嵌入向量缓存时出错: {e}")
        
            # 5. 保存记忆状态
            await self.memory_system.save_memory_state()
            
            # 6. 如果启用了群聊隔离，保存所有群聊数据库
            if self.memory_system.memory_config.get("enable_group_isolation", True):
                db_dir = os.path.dirname(self.memory_system.db_path)
                if os.path.exists(db_dir):
                    for filename in os.listdir(db_dir):
                        if filename.startswith("memory_group_") and filename.endswith(".db"):
                            group_id = filename[12:-3]
                            await self.memory_system.save_memory_state(group_id)
            
            # 7. 使用资源管理器清理所有资源
            resource_manager.cleanup()
            
            self._debug_log("记忆系统已保存并安全关闭", "info")
            
        except Exception as e:
            logger.error(f"插件终止过程中发生错误: {e}", exc_info=True)
            
    async def safe_cleanup(self):
        """安全清理方法，用于在 terminate 之外调用的情况"""
        await self.terminate()

    # ---------- 插件API ----------
    async def add_memory_api(self, content: str, theme: str, group_id: str = "", details: str = "", participants: str = "", location: str = "", emotion: str = "", tags: str = "") -> Optional[str]:
        """
        【API】添加一条记忆。
        :param content: 记忆的核心内容。
        :param theme: 记忆的主题或关键词，用逗号分隔。
        :param group_id: 群组ID，如果需要在特定群聊中操作。
        :param details: 记忆的详细信息。
        :param participants: 参与者，用逗号分隔。
        :param location: 相关地点。
        :param emotion: 情感色彩。
        :param tags: 标签，用逗号分隔。
        :return: 成功则返回记忆ID，否则返回None。
        """
        if not self._initialized or not self.memory_system.memory_system_enabled:
            logger.warning("API调用失败：记忆系统未启用或未初始化。")
            return None
        
        try:
            # 切换到正确的群聊上下文
            if group_id and self.memory_system.memory_config.get("enable_group_isolation", True):
                self.memory_system.memory_graph = MemoryGraph()
                self.memory_system.load_memory_state(group_id)

            concept_id = self.memory_system.memory_graph.add_concept(theme)
            memory_id = self.memory_system.memory_graph.add_memory(
                content=content,
                concept_id=concept_id,
                details=details,
                participants=participants,
                location=location,
                emotion=emotion,
                tags=tags,
                group_id=group_id
            )
            
            # 异步保存
            await self.memory_system._queue_save_memory_state(group_id)
            
            logger.info(f"通过API添加记忆成功: {memory_id}")
            return memory_id
        except Exception as e:
            logger.error(f"API add_memory_api 失败: {e}", exc_info=True)
            return None

    async def recall_memories_api(self, keyword: str, group_id: str = "") -> List[Dict[str, Any]]:
        """
        【API】根据关键词回忆相关记忆。
        :param keyword: 要查询的关键词。
        :param group_id: 群组ID，如果需要在特定群聊中操作。
        :return: 记忆对象字典的列表。
        """
        if not self._initialized or not self.memory_system.memory_system_enabled:
            logger.warning("API调用失败：记忆系统未启用或未初始化。")
            return []

        try:
            # 切换到正确的群聊上下文
            if group_id and self.memory_system.memory_config.get("enable_group_isolation", True):
                self.memory_system.memory_graph = MemoryGraph()
                self.memory_system.load_memory_state(group_id)

            memories = await self.memory_system.recall_memories_full(keyword)
            return [memory.__dict__ for memory in memories]
        except Exception as e:
            logger.error(f"API recall_memories_api 失败: {e}", exc_info=True)
            return []

    async def record_impression_api(self, person_name: str, summary: str, score: Optional[float], details: str = "", group_id: str = "") -> bool:
        """
        【API】记录对某个人的印象。
        :param person_name: 人物名称。
        :param summary: 印象摘要。
        :param score: 好感度分数 (0-1)。
        :param details: 详细信息。
        :param group_id: 群组ID。
        :return: 操作是否成功。
        """
        if not self._initialized or not self.memory_system.memory_system_enabled:
            logger.warning("API调用失败：记忆系统未启用或未初始化。")
            return False

        try:
            if group_id and self.memory_system.memory_config.get("enable_group_isolation", True):
                self.memory_system.memory_graph = MemoryGraph()
                self.memory_system.load_memory_state(group_id)

            memory_id = self.memory_system.record_person_impression(group_id, person_name, summary, score, details)
            await self.memory_system._queue_save_memory_state(group_id)
            return bool(memory_id)
