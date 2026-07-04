"""
AstrBot Memora Connect 插件主文件
提供记忆和印象管理功能的主要入口
"""

import asyncio
import os
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, MessageEventResult, filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star, StarTools, register

from .api.gateway import MemoryAPIGateway
from .core.memory_graph import MemoryGraph
from .core.memory_system import MemorySystem

# 导入模块化的组件
from .infrastructure.events import (
    initialize_event_bus,
    shutdown_event_bus,
)
from .infrastructure.resources import resource_manager
from .intelligence.profiling import UserProfilingSystem
from .intelligence.temporal import TemporalMemorySystem
from .intelligence.topic_analyzer import TopicAnalyzer
from .memory.memory_display import EnhancedMemoryDisplay
from .memory.memory_recall import EnhancedMemoryRecall
from .memory.visualization import MemoryGraphVisualizer
from .web.server import MemoryWebServer


@register(
    "astrbot_plugin_memora_connect",
    "qa296",
    "赋予AI记忆与印象/好感的能力！  模仿生物海马体，通过概念节点与关系连接构建记忆网络，具备记忆形成、提取、遗忘、巩固功能，采用双峰时间分布回顾聊天，打造有记忆能力的智能对话体验。",
    "0.4.7",
    "https://github.com/qa296/astrbot_plugin_memora_connect",
)
class MemoraConnectPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        data_dir = StarTools.get_data_dir() / "memora_connect"
        self.memory_system = MemorySystem(context, config, data_dir)
        self.memory_display = EnhancedMemoryDisplay(self.memory_system)
        self.graph_visualizer = MemoryGraphVisualizer(self.memory_system)
        self._initialized = False
        self.web_server = None

        # 新增：主动能力升级模块
        self.event_bus = None
        self.topic_analyzer = None
        self.user_profiling = None
        self.temporal_memory = None
        self.api_gateway = None

        asyncio.create_task(self._async_init())

    def _load_group_context_for_event(self, event: AstrMessageEvent) -> str:
        group_id = event.get_group_id() if event.get_group_id() else ""
        if not self.memory_system.memory_config.get("enable_group_isolation", True):
            return group_id

        def _load_scope(scope_id: str) -> bool:
            self.memory_system.memory_graph = MemoryGraph()
            self.memory_system.load_memory_state(scope_id)
            return bool(self.memory_system.memory_graph.memories)

        if group_id:
            _load_scope(group_id)
            return group_id

        if _load_scope(""):
            return ""

        sender_id = ""
        try:
            sender_id = str(event.get_sender_id() or "")
        except Exception:
            sender_id = ""

        candidates = [
            c for c in [sender_id, f"pm:{sender_id}" if sender_id else ""] if c
        ]
        for scope_id in candidates:
            if _load_scope(scope_id):
                return scope_id

        return ""

    def _debug_log(self, message: str, level: str = "debug"):
        try:
            if level == "debug":
                logger.debug(message)
            elif level == "info":
                logger.info(message)
            elif level == "warning":
                logger.warning(message)
            elif level == "error":
                logger.error(message)
            else:
                logger.info(message)
        except Exception:
            pass

    async def _async_init(self):
        """异步初始化包装器"""
        try:
            # 等待一小段时间，确保所有提供商都已加载完成
            await asyncio.sleep(2)

            logger.info("开始异步初始化记忆系统...")
            await self.memory_system.initialize()

            # 初始化新增模块
            try:

                # 1. 初始化事件总线
                self.event_bus = await initialize_event_bus()

                # 2. 初始化话题分析器
                self.topic_analyzer = TopicAnalyzer(self.memory_system)

                # 3. 初始化用户画像系统
                self.user_profiling = UserProfilingSystem(self.memory_system)

                # 注入组件到记忆系统
                self.memory_system.set_components(
                    self.topic_analyzer, self.user_profiling
                )

                # 4. 初始化时间维度记忆系统
                self.temporal_memory = TemporalMemorySystem(self.memory_system)

                # 5. 初始化API网关
                self.api_gateway = MemoryAPIGateway(
                    self.memory_system,
                    self.topic_analyzer,
                    self.user_profiling,
                    self.temporal_memory,
                )

            except Exception as upgrade_e:
                logger.error(f"主动能力升级模块初始化失败: {upgrade_e}", exc_info=True)

            self._initialized = True

            # 根据配置启动 Web 界面
            try:
                web_cfg = (self.memory_system.memory_config or {}).get(
                    "web_ui", {}
                ) or {}
                if web_cfg.get("enabled", False):
                    host = str(web_cfg.get("host", "127.0.0.1"))
                    port = int(web_cfg.get("port", 8350))
                    token = str(web_cfg.get("access_token", "") or "")
                    self.web_server = MemoryWebServer(
                        self.memory_system, host=host, port=port, access_token=token
                    )
                    await self.web_server.start()
                    logger.info(f"Web 界面已启动: http://{host}:{port}")
            except Exception as _we:
                logger.error(f"启动Web界面失败: {_we}", exc_info=True)
            logger.info("记忆系统异步初始化完成")
        except Exception as e:
            logger.error(f"记忆系统初始化失败: {e}", exc_info=True)

    @filter.command_group("记忆")
    def memory(self):
        """记忆管理指令组"""
        pass

    @memory.command("回忆")
    async def memory_recall(self, event: AstrMessageEvent, keyword: str = ""):
        # 检查记忆系统是否启用
        if not self.memory_system.config_manager.is_memory_system_enabled():
            yield event.plain_result("记忆系统已禁用，无法使用回忆功能。")
            return
        group_id = self._load_group_context_for_event(event)
        memories = await self.memory_system.recall_memories_full(keyword)
        if memories:
            await self.memory_system._queue_save_memory_state(group_id)
        response = self.memory_display.format_memory_search_result(memories, keyword)
        yield event.plain_result(response)

    @memory.command("删除")
    async def memory_delete(self, event: AstrMessageEvent, memory_id: str):
        if not self.memory_system.config_manager.is_memory_system_enabled():
            yield event.plain_result("记忆系统已禁用，无法删除记忆。")
            return

        group_id = self._load_group_context_for_event(event)
        success = await self.memory_system.delete_memory_by_id(memory_id, group_id)
        if success:
            await self.memory_system._queue_save_memory_state(group_id)
            yield event.plain_result(f"✅ 记忆已删除: {memory_id}")
        else:
            yield event.plain_result(f"未找到记忆: {memory_id}")

    @memory.command("状态")
    async def memory_status(self, event: AstrMessageEvent):
        # 检查记忆系统是否启用
        if not self.memory_system.config_manager.is_memory_system_enabled():
            yield event.plain_result("记忆系统已禁用，无法查看状态。")
            return
        scope_id = self._load_group_context_for_event(event)
        stats = self.memory_display.format_memory_statistics()
        if stats == "记忆库为空":
            try:
                from .infrastructure.resources import resource_manager

                conn = resource_manager.get_db_connection(self.memory_system.db_path)
                try:
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='memories'"
                    )
                    if cur.fetchone():
                        cur.execute("SELECT COUNT(*) FROM memories")
                        total = int(cur.fetchone()[0])
                        cur.execute(
                            "SELECT COUNT(*) FROM memories WHERE group_id = ?",
                            (scope_id,),
                        )
                        scope_total = int(cur.fetchone()[0])
                        stats = "\n".join(
                            [
                                stats,
                                f"当前会话ID: {scope_id or '(default)'}",
                                f"数据库总记忆数: {total}",
                                f"当前会话记忆数: {scope_total}",
                                f"数据库路径: {self.memory_system.db_path}",
                            ]
                        )
                finally:
                    resource_manager.release_db_connection(
                        self.memory_system.db_path, conn
                    )
            except Exception:
                pass
        yield event.plain_result(stats)

    @memory.command("印象")
    async def memory_impression(self, event: AstrMessageEvent, name: str):
        """查询人物印象摘要和相关记忆"""
        # 检查记忆系统是否启用
        if not self.memory_system.config_manager.is_memory_system_enabled():
            yield event.plain_result("记忆系统已禁用，无法查询印象。")
            return

        try:
            group_id = self._load_group_context_for_event(event)

            # 获取印象摘要
            impression_summary = self.memory_system.get_person_impression_summary(
                group_id, name
            )

            # 获取印象记忆列表
            impression_memories = self.memory_system.get_person_impression_memories(
                group_id, name, limit=5
            )

            # 格式化响应
            response_parts = []

            # 添加印象摘要
            if impression_summary:
                score = impression_summary.get("score", 0.5)
                score_desc = self.memory_system._score_to_description(score)
                response_parts.append(f"📝 {name} 的印象摘要:")
                response_parts.append(
                    f"   印象: {impression_summary.get('summary', '无')}"
                )
                response_parts.append(f"   好感度: {score_desc} ({score:.2f})")
                response_parts.append(
                    f"   记忆数: {impression_summary.get('memory_count', 0)}"
                )
                response_parts.append(
                    f"   更新时间: {impression_summary.get('last_updated', '无')}"
                )
            else:
                response_parts.append(f"📝 尚未建立对 {name} 的印象")

            # 添加相关记忆
            if impression_memories:
                response_parts.append("\n📚 相关记忆:")
                for i, memory in enumerate(impression_memories, 1):
                    response_parts.append(f"   {i}. {memory['content']}")
                    if memory.get("details"):
                        response_parts.append(f"      详情: {memory['details']}")
                    response_parts.append(
                        f"      好感度: {memory['score']:.2f} | 时间: {memory['last_accessed']}"
                    )
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
            self._load_group_context_for_event(event)
            # 发送生成中的提示
            yield event.plain_result(
                f"🔄 正在生成记忆图谱（布局风格: {layout_style}），请稍候..."
            )

            # 异步生成图谱图片
            image_path = await self.graph_visualizer.generate_graph_image(
                layout_style=layout_style
            )

            if image_path:
                # 检查文件是否存在
                if os.path.exists(image_path):
                    # 发送图片消息
                    try:
                        # 尝试使用 AstrBot 的图片发送功能
                        if hasattr(event, "send_image"):
                            await event.send_image(image_path)
                            yield event.plain_result(
                                f"✅ 记忆图谱已生成！（布局风格: {layout_style}）"
                            )
                        else:
                            # 如果不支持直接发送图片，尝试使用其他方法
                            yield event.image_result(image_path)
                    except Exception as img_e:
                        logger.error(f"发送图片失败: {img_e}", exc_info=True)
                        # 如果发送图片失败，发送文件路径
                        yield event.plain_result(
                            f"✅ 记忆图谱已生成！（布局风格: {layout_style}）\n图片路径: {image_path}"
                        )
                else:
                    yield event.plain_result(
                        "❌ 图谱文件生成失败，请检查权限和磁盘空间。"
                    )
            else:
                yield event.plain_result(
                    "❌ 记忆图谱生成失败，可能是因为：\n1. 未安装依赖库（networkx, matplotlib）\n2. 记忆数据为空\n3. 系统错误"
                )

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
        if not event.is_private_chat() and not getattr(
            event, "is_at_or_wake_command", False
        ):
            return

        try:
            group_id = self._load_group_context_for_event(event)

            # 3. 消息处理使用异步队列，避免阻塞主流程
            self.memory_system._create_managed_task(
                self._process_message_async(event, group_id)
            )

        except Exception as e:
            self._debug_log(f"on_message处理错误: {e}", "error")

    async def _process_message_async(self, event: AstrMessageEvent, group_id: str):
        """异步消息处理，避免阻塞主流程"""
        try:
            message = event.message_str

            # 排除指令消息（以 / ! ！ 开头的消息）
            # 修复话题模块在任何消息下都会触发的问题
            if (
                not message
                or not message.strip()
                or any(
                    message.strip().startswith(prefix) for prefix in ["/", "!", "！"]
                )
            ):
                return

            # 检查配置中的排除关键词
            exclude_keywords = self.memory_system.config_manager.config.exclude_keywords
            if exclude_keywords and any(k in message.strip() for k in exclude_keywords):
                return

            sender_id = event.get_sender_id()

            # 使用优化后的单次LLM调用处理消息
            await self.memory_system.process_message_optimized(event, group_id)

            # === 主动能力升级相关处理 ===
            if self.temporal_memory:
                try:
                    # 未闭合话题检测
                    await self.temporal_memory.auto_detect_and_track_questions(
                        message, sender_id, group_id
                    )
                except Exception as upgrade_e:
                    logger.debug(f"主动能力升级处理失败: {upgrade_e}")

            # 使用队列化保存，减少I/O操作
            if group_id and self.memory_system.memory_config.get(
                "enable_group_isolation", True
            ):
                await self.memory_system._queue_save_memory_state(group_id)
            else:
                await self.memory_system._queue_save_memory_state("")  # 默认数据库

        except Exception as e:
            self._debug_log(f"异步消息处理失败: {e}", "error")

    @filter.on_llm_request(priority=999)
    async def on_llm_request(self, event: AstrMessageEvent, req: ProviderRequest):
        """处理LLM请求时的记忆召回"""
        try:
            logger.info("Memora Connect 拦截到 LLM 请求，准备注入记忆...")
            if not self._initialized:
                logger.warning("Memora Connect 尚未初始化，跳过注入")
                return
            if not event.is_private_chat() and not getattr(
                event, "is_at_or_wake_command", False
            ):
                return

            # 获取当前消息内容
            current_message = event.message_str.strip()
            if not current_message:
                return

            group_id = self._load_group_context_for_event(event)

            # [修改] 统一使用 inject_memories_to_context 获取完整上下文（包含记忆、话题、画像等）
            # 避免重复召回和注入
            full_context = await self.memory_system.inject_memories_to_context(event)
            if full_context and hasattr(req, "system_prompt"):
                # 避免重复注入（简单检查）
                if "【相关记忆】" not in (req.system_prompt or ""):
                    req.system_prompt = f"{req.system_prompt or ''}\n\n{full_context}"
                    logger.debug("已将完整上下文注入到 System Prompt")

        except Exception as e:
            logger.error(f"LLM请求记忆召回失败: {e}", exc_info=True)

    async def terminate(self):
        """插件卸载时保存记忆并清理资源"""
        self._debug_log("开始插件终止流程，清理所有资源", "info")

        try:
            # === 新增：清理主动能力升级模块 ===
            try:
                if self.event_bus:
                    await shutdown_event_bus()
            except Exception as bus_e:
                logger.warning(f"关闭事件总线失败: {bus_e}")

            # 停止 Web 服务
            if hasattr(self, "web_server") and self.web_server:
                try:
                    await self.web_server.stop()
                except Exception as _we:
                    logger.warning(f"停止Web服务失败: {_we}")
            # 1. 停止维护循环
            if hasattr(self.memory_system, "_should_stop_maintenance"):
                self.memory_system._should_stop_maintenance.set()
            if (
                hasattr(self.memory_system, "_maintenance_task")
                and self.memory_system._maintenance_task
            ):
                # 等待维护任务正常退出
                try:
                    await asyncio.wait_for(
                        self.memory_system._maintenance_task, timeout=10.0
                    )
                except asyncio.TimeoutError:
                    # 如果超时，取消任务
                    self.memory_system._maintenance_task.cancel()
                    try:
                        await self.memory_system._maintenance_task
                    except asyncio.CancelledError:
                        pass

            # 2. 取消所有托管的异步任务
            if hasattr(self.memory_system, "_managed_tasks"):
                await self.memory_system._cancel_all_managed_tasks()

            # 3. 等待待处理的保存任务完成
            if (
                hasattr(self.memory_system, "_pending_save_task")
                and self.memory_system._pending_save_task
                and not self.memory_system._pending_save_task.done()
            ):
                try:
                    await asyncio.wait_for(
                        self.memory_system._pending_save_task, timeout=5.0
                    )
                except asyncio.TimeoutError:
                    self.memory_system._pending_save_task.cancel()
                    try:
                        await self.memory_system._pending_save_task
                    except asyncio.CancelledError:
                        pass

            # 4. 清理嵌入向量缓存
            if (
                hasattr(self.memory_system, "embedding_cache")
                and self.memory_system.embedding_cache
            ):
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
                        if filename.startswith("memory_group_") and filename.endswith(
                            ".db"
                        ):
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
    async def add_memory_api(
        self,
        content: str,
        theme: str = "",
        group_id: str = "",
        details: str = "",
        participants: str = "",
        location: str = "",
        emotion: str = "",
        tags: str = "",
        elements: str = "",
    ) -> str | None:
        """【API】添加一条记忆"""
        if not self._initialized or not self.memory_system.memory_system_enabled:
            logger.warning("API调用失败：记忆系统未启用或未初始化。")
            return None

        try:
            if self.memory_system.memory_config.get("enable_group_isolation", True):
                self.memory_system.memory_graph = MemoryGraph()
                self.memory_system.load_memory_state(group_id)

            memory_id = self.memory_system.memory_graph.add_memory(
                content=content,
                details=details,
                emotion=emotion,
                group_id=group_id,
            )

            if elements:
                try:
                    import json
                    elem_list = json.loads(elements) if isinstance(elements, str) else elements
                    if isinstance(elem_list, list):
                        for elem in elem_list:
                            if isinstance(elem, dict):
                                name = str(elem.get("name", "")).strip()
                                category = str(elem.get("category", "trait")).strip()
                                role = str(elem.get("role", "")).strip()
                                if name:
                                    eid = self.memory_system.memory_graph.get_or_create_element(
                                        name, category, group_id
                                    )
                                    self.memory_system.memory_graph.link_memory(eid, memory_id, role)
                        self.memory_system.memory_graph.auto_connect_cooccurring_elements(memory_id)
                except Exception:
                    pass

            if not elements and (participants or location or tags):
                if participants:
                    for p in participants.replace("，", ",").split(","):
                        p = p.strip()
                        if p:
                            eid = self.memory_system.memory_graph.get_or_create_element(p, "person", group_id)
                            self.memory_system.memory_graph.link_memory(eid, memory_id, "subject")
                if location:
                    for loc in location.replace("，", ",").split(","):
                        loc = loc.strip()
                        if loc:
                            eid = self.memory_system.memory_graph.get_or_create_element(loc, "place", group_id)
                            self.memory_system.memory_graph.link_memory(eid, memory_id, "scene")
                if tags:
                    for tag in tags.replace("，", ",").split(","):
                        tag = tag.strip()
                        if tag:
                            eid = self.memory_system.memory_graph.get_or_create_element(tag, "trait", group_id)
                            self.memory_system.memory_graph.link_memory(eid, memory_id, "attribute")
                self.memory_system.memory_graph.auto_connect_cooccurring_elements(memory_id)

            if not elements and not participants and not location and not tags and theme:
                for kw in theme.replace("，", ",").split(","):
                    kw = kw.strip()
                    if kw:
                        eid = self.memory_system.memory_graph.get_or_create_element(kw, "trait", group_id)
                        self.memory_system.memory_graph.link_memory(eid, memory_id, "")
                self.memory_system.memory_graph.auto_connect_cooccurring_elements(memory_id)

            await self.memory_system._queue_save_memory_state(group_id)

            logger.info(f"通过API添加记忆成功: {memory_id}")
            return memory_id
        except Exception as e:
            logger.error(f"API add_memory_api 失败: {e}", exc_info=True)
            return None

    async def recall_memories_api(
        self, keyword: str, group_id: str = ""
    ) -> list[dict[str, Any]]:
        """【API】根据关键词回忆相关记忆"""
        if not self._initialized or not self.memory_system.memory_system_enabled:
            logger.warning("API调用失败：记忆系统未启用或未初始化。")
            return []

        try:
            # 切换到正确的群聊上下文
            if self.memory_system.memory_config.get("enable_group_isolation", True):
                self.memory_system.memory_graph = MemoryGraph()
                self.memory_system.load_memory_state(group_id)

            memories = await self.memory_system.recall_memories_full(keyword)
            if memories:
                await self.memory_system._queue_save_memory_state(group_id)
            return [memory.__dict__ for memory in memories]
        except Exception as e:
            logger.error(f"API recall_memories_api 失败: {e}", exc_info=True)
            return []

    async def record_impression_api(
        self,
        person_name: str,
        summary: str,
        score: float | None,
        details: str = "",
        group_id: str = "",
    ) -> bool:
        """【API】记录对某个人的印象"""
        if not self._initialized or not self.memory_system.memory_system_enabled:
            logger.warning("API调用失败：记忆系统未启用或未初始化。")
            return False

        try:
            if self.memory_system.memory_config.get("enable_group_isolation", True):
                self.memory_system.memory_graph = MemoryGraph()
                self.memory_system.load_memory_state(group_id)

            memory_id = self.memory_system.record_person_impression(
                group_id, person_name, summary, score, details
            )
            await self.memory_system._queue_save_memory_state(group_id)
            return bool(memory_id)
        except Exception as e:
            logger.error(f"API record_impression_api 失败: {e}", exc_info=True)
            return False

    async def get_impression_summary_api(
        self, person_name: str, group_id: str = ""
    ) -> dict[str, Any] | None:
        """【API】获取对某个人的印象摘要"""
        if not self._initialized or not self.memory_system.memory_system_enabled:
            logger.warning("API调用失败：记忆系统未启用或未初始化。")
            return None

        try:
            if self.memory_system.memory_config.get("enable_group_isolation", True):
                self.memory_system.memory_graph = MemoryGraph()
                self.memory_system.load_memory_state(group_id)

            return self.memory_system.get_person_impression_summary(
                group_id, person_name
            )
        except Exception as e:
            logger.error(f"API get_impression_summary_api 失败: {e}", exc_info=True)
            return None

    async def adjust_impression_score_api(
        self, person_name: str, delta: float, group_id: str = ""
    ) -> float | None:
        """【API】调整对某个人的好感度分数"""
        if not self._initialized or not self.memory_system.memory_system_enabled:
            logger.warning("API调用失败：记忆系统未启用或未初始化。")
            return None

        try:
            if self.memory_system.memory_config.get("enable_group_isolation", True):
                self.memory_system.memory_graph = MemoryGraph()
                self.memory_system.load_memory_state(group_id)

            new_score = self.memory_system.adjust_impression_score(
                group_id, person_name, delta
            )
            await self.memory_system._queue_save_memory_state(group_id)
            return new_score
        except Exception as e:
            logger.error(f"API adjust_impression_score_api 失败: {e}", exc_info=True)
            return None

    # ---------- LLM 函数工具 ----------
    @filter.llm_tool(name="create_memory")
    async def create_memory_tool(
        self,
        event: AstrMessageEvent,
        content: str,
        theme: str = None,
        elements: str = "",
        details: str = "",
        emotion: str = "",
        allow_forget: str = None,
        confidence: str = "0.7",
        participants: str = "",
        location: str = "",
        tags: str = "",
    ) -> MessageEventResult:
        """通过LLM调用创建记忆(必须传入完整参数！！！)

        Args:
            content(string): 需要记录的完整对话内容
            theme(string): 核心关键词，用逗号分隔（向后兼容，优先使用elements）
            elements(string): 记忆元素JSON数组，格式如 [{"name":"张三","category":"person","role":"subject"}]，category可选: person/object/place/action/trait
            details(string): 具体细节和背景信息
            emotion(string): 情感色彩
            allow_forget(string): 是否允许遗忘
            confidence(number): 置信度，0-1之间的数值
            participants(string): 涉及的人物，用逗号分隔（向后兼容）
            location(string): 相关场景或地点（向后兼容）
            tags(string): 分类标签（向后兼容）
        """
        try:
            if not content:
                logger.warning("创建记忆失败：内容为空")
                return "创建记忆失败：内容为空"

            parsed_allow_forget = self.memory_system._parse_allow_forget_value(
                allow_forget, None
            )
            if allow_forget is not None and parsed_allow_forget is None:
                return "创建记忆失败：allow_forget参数无效"
            initial_allow_forget = (
                parsed_allow_forget if parsed_allow_forget is not None else True
            )

            try:
                confidence_float = max(0.0, min(1.0, float(confidence)))
            except (ValueError, TypeError):
                confidence_float = 0.7

            group_id = self._load_group_context_for_event(event)
            base_strength = 1.0 * confidence_float

            resolved_allow_forget = await self.memory_system.resolve_allow_forget(
                content=content,
                theme=theme or "",
                details=details,
                participants=participants,
                location=location,
                emotion=emotion,
                tags=tags,
                initial_allow_forget=initial_allow_forget,
            )

            memory_id = self.memory_system.memory_graph.add_memory(
                content=content,
                details=details,
                emotion=emotion,
                strength=base_strength,
                allow_forget=resolved_allow_forget,
                group_id=group_id,
            )

            element_linked = False

            if elements:
                try:
                    import json
                    elem_list = json.loads(elements) if isinstance(elements, str) else elements
                    if isinstance(elem_list, list):
                        for elem in elem_list:
                            if isinstance(elem, dict):
                                name = str(elem.get("name", "")).strip()
                                category = str(elem.get("category", "trait")).strip()
                                role = str(elem.get("role", "")).strip()
                                if name:
                                    from .core.models import CATEGORIES
                                    if category not in CATEGORIES:
                                        category = "trait"
                                    eid = self.memory_system.memory_graph.get_or_create_element(
                                        name, category, group_id
                                    )
                                    self.memory_system.memory_graph.link_memory(eid, memory_id, role)
                                    element_linked = True
                        if element_linked:
                            self.memory_system.memory_graph.auto_connect_cooccurring_elements(memory_id)
                except Exception:
                    pass

            if not element_linked:
                actual_theme = theme or ""
                fallback_parts = []
                if participants:
                    fallback_parts.extend(p.strip() for p in participants.replace("，", ",").split(",") if p.strip())
                if location:
                    fallback_parts.extend(l.strip() for l in location.replace("，", ",").split(",") if l.strip())
                if tags:
                    fallback_parts.extend(t.strip() for t in tags.replace("，", ",").split(",") if t.strip())
                if actual_theme:
                    fallback_parts.extend(k.strip() for k in actual_theme.replace("，", ",").split(",") if k.strip())

                for kw in fallback_parts:
                    eid = self.memory_system.memory_graph.get_or_create_element(kw, "trait", group_id)
                    self.memory_system.memory_graph.link_memory(eid, memory_id, "")
                if fallback_parts:
                    self.memory_system.memory_graph.auto_connect_cooccurring_elements(memory_id)

            await self.memory_system._queue_save_memory_state(group_id)

            logger.info(
                f"LLM工具创建记忆：{content[:30]} (置信度: {confidence})"
            )

            return f"记忆创建成功,内容为:{content}"

        except Exception as e:
            logger.error(f"LLM工具创建记忆失败：{e}")
            await event.send(MessageChain().message("记忆创建失败"))
            return "记忆创建失败"

    @filter.llm_tool(name="recall_memory")
    async def recall_memory_tool(
        self, event: AstrMessageEvent, keyword: str
    ) -> MessageEventResult:
        """召回所有相关记忆，包括联想记忆

        Args:
            keyword(string): 要查询的关键词或内容
        """
        try:
            group_id = self._load_group_context_for_event(event)
            enhanced_recall = EnhancedMemoryRecall(self.memory_system)
            results = await enhanced_recall.recall_all_relevant_memories(
                query=keyword, max_memories=8, group_id=group_id
            )

            if results:
                # 生成增强的上下文
                formatted_memories = enhanced_recall.format_memories_for_llm(
                    results, include_ids=True
                )
                return f"记忆召回结果:{formatted_memories}\n提示：如果记忆已过时允许删除记忆"
            else:
                return "没有相关记忆"

        except Exception as e:
            logger.error(f"增强记忆召回工具失败：{e}")
            await event.send(MessageChain().message("记忆召回失败"))
            return "记忆召回失败"

    @filter.llm_tool(name="delete_memory")
    async def delete_memory_tool(
        self, event: AstrMessageEvent, memory_id: str, reason: str = ""
    ) -> MessageEventResult:
        """删除指定记忆

        Args:
            memory_id(string): 需要删除的记忆ID
            reason(string): 删除原因或说明
        """
        try:
            if not self.memory_system.config_manager.is_memory_system_enabled():
                return "记忆系统已禁用，无法删除记忆"

            group_id = self._load_group_context_for_event(event)
            success = await self.memory_system.delete_memory_by_id(memory_id, group_id)
            if success:
                await self.memory_system._queue_save_memory_state(group_id)
                logger.info(f"LLM工具删除记忆：{memory_id} 原因:{reason}")
                return f"记忆已删除: {memory_id}"

            return f"未找到记忆: {memory_id}"
        except Exception as e:
            logger.error(f"LLM工具删除记忆失败：{e}")
            await event.send(MessageChain().message("删除记忆失败"))
            return "删除记忆失败"

    @filter.llm_tool(name="adjust_impression")
    async def adjust_impression_tool(
        self, event: AstrMessageEvent, person_name: str, delta: str, reason: str = ""
    ) -> MessageEventResult:
        """调整对某人的印象和好感度

        Args:
            person_name(string): 人物名称
            delta(number): 好感度调整量，可正可负
            reason(string): 调整原因和详细信息
        """
        try:
            # 获取群组ID
            group_id = self._load_group_context_for_event(event)

            # 调整印象分数 - 将字符串转换为浮点数
            try:
                delta_float = float(delta)
            except (ValueError, TypeError):
                logger.warning(f"无法将delta '{delta}' 转换为浮点数，使用默认值0.0")
                delta_float = 0.0

            new_score = self.memory_system.adjust_impression_score(
                group_id, person_name, delta_float
            )
            await self.memory_system._queue_save_memory_state(group_id)

            # 记录调整原因
            if reason:
                summary = (
                    f"调整对{person_name}的印象：{reason}，当前好感度：{new_score:.2f}"
                )
                self.memory_system.record_person_impression(
                    group_id, person_name, summary, new_score, reason
                )

            logger.info(
                f"LLM工具调整印象：{person_name} 调整量:{delta} 新分数:{new_score:.2f}"
            )

            return f"调整印象成功，{person_name} 的好感度为 {new_score:.2f}"

        except Exception as e:
            logger.error(f"LLM工具调整印象失败：{e}")
            await event.send(MessageChain().message("调整印象失败"))
            return "调整印象失败"

    @filter.llm_tool(name="record_impression")
    async def record_impression_tool(
        self,
        event: AstrMessageEvent,
        person_name: str,
        summary: str,
        score: str = None,
        details: str = "",
    ) -> MessageEventResult:
        """记录或更新对某人的印象

        Args:
            person_name(string): 人物名称
            summary(string): 印象摘要描述
            score(number): 好感度分数 (0-1)，可选
            details(string): 详细信息和背景
        """
        try:
            # 获取群组ID
            group_id = self._load_group_context_for_event(event)

            # 验证分数范围 - 将字符串转换为浮点数
            score_float = None
            if score is not None:
                try:
                    score_float = max(0.0, min(1.0, float(score)))
                except (ValueError, TypeError):
                    logger.warning(f"无法将score '{score}' 转换为浮点数，使用默认值")
                    score_float = None

            # 记录印象
            memory_id = self.memory_system.record_person_impression(
                group_id, person_name, summary, score_float, details
            )
            await self.memory_system._queue_save_memory_state(group_id)

            if memory_id:
                current_score = self.memory_system.get_impression_score(
                    group_id, person_name
                )
                logger.info(
                    f"LLM工具记录印象：{person_name} 分数:{current_score:.2f} 摘要:{summary[:50]}..."
                )

            return f"记录印象成功，{person_name} 的好感度为 {current_score:.2f}"

        except Exception as e:
            logger.error(f"LLM工具记录印象失败：{e}")
            await event.send(MessageChain().message("记录印象失败"))
            return "记录印象失败"
