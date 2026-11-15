"""
Memora Connect 插件主文件（薄装配层）。

只做装配、事件门控、scope 解析与 AstrBot API 适配；
所有 @filter.* 处理器必须留在本模块（AstrBot 按模块绑定 handler）。
"""

import asyncio
import json
import os
import time

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, MessageEventResult, filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.core.agent.message import TextPart

from .application.formation import FormationService
from .application.ingest import IngestService
from .application.recall import RecallService
from .domain.models import CATEGORIES, Memory, score_verbal
from .memory.visualization import generate_graph_image, prepare_graph_data
from .storage.migrate_v1 import migrate_v1
from .storage.repository import MemoryRepository, new_id
from .web.api import MemoryWebAPI

_COMMAND_PREFIXES = ("/", "!", "！")


@register(
    "astrbot_plugin_memora_connect",
    "qa296",
    "赋予AI模仿人类的记忆和印象能力。从对话自动沉淀记忆、人物与关系图谱，请求时按相关度召回注入，好感度独立追踪",
    "0.6.0",
    "https://github.com/qa296/astrbot_plugin_memora_connect",
)
class MemoraConnectPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.cfg = config
        data_dir = StarTools.get_data_dir() / "memora_connect"
        os.makedirs(data_dir, exist_ok=True)
        self.data_dir = str(data_dir)

        self.repo = MemoryRepository(str(data_dir / "memora.db"))
        migrate_v1(str(data_dir), self.repo)

        self.ingest = IngestService(
            self.repo,
            exclude_keywords=list(config.get("exclude_keywords") or []),
            flush_threshold=int(config.get("topic_message_threshold", 20)),
            idle_seconds=float(config.get("formation_idle_flush_seconds", 60)),
        )
        self.formation = FormationService(
            self.repo,
            self._ask_llm,
            max_session_rounds=int(config.get("max_session_rounds", 5)),
            recent_completed_count=int(
                config.get("recent_completed_sessions_count", 5)
            ),
            history_count=int(config.get("conversation_history_count", 24)),
            persona_fn=self._persona_text,
        )
        self.recall = RecallService(
            self.repo,
            weights={
                "kw": float(config.get("recall_weight_keyword", 0.2)),
                "emb": float(config.get("recall_weight_semantic", 0.6)),
                "graph": float(config.get("recall_weight_graph", 0.2)),
            },
            threshold=float(config.get("memory_injection_threshold", 0.3)),
            max_injected=int(config.get("max_injected_memories", 5)),
            half_life_hours=float(config.get("recency_half_life_hours", 72)),
            enable_embedding=bool(config.get("enable_embedding_recall", False)),
            embed_fn=self._get_embedding,
        )

        self._flush_locks: dict[str, asyncio.Lock] = {}
        self._background_tasks: set[asyncio.Task] = []
        self._stopping = False
        self._sweeper_task = asyncio.create_task(self._sweeper_loop())

        try:
            self.web_api = MemoryWebAPI(self.repo, context)
            self.web_api.register()
        except Exception as e:
            self.web_api = None
            logger.error(f"注册 Plugin Page API 失败: {e}", exc_info=True)

        logger.info(f"Memora Connect v2 就绪：{self.repo.db_path}")

    def _get_provider(self, provider_id: str):
        try:
            if provider_id:
                provider = self.context.get_provider_by_id(provider_id)
                if provider:
                    return provider
                for p in self.context.get_all_providers():
                    name = getattr(getattr(p, "meta", None), "name", None) or getattr(
                        p, "name", None
                    )
                    if name and str(name).lower() == provider_id.lower():
                        return p
                return None
            return self.context.get_using_provider()
        except Exception:
            return None

    async def _ask_llm(self, prompt: str) -> str:
        provider = self._get_provider(str(self.cfg.get("llm_provider", "") or ""))
        if provider is None:
            raise RuntimeError("无可用 LLM 提供商（检查 llm_provider 配置）")
        response = await provider.text_chat(prompt=prompt, contexts=[])
        return getattr(response, "completion_text", "") or ""

    async def _get_embedding(self, text: str) -> list[float]:
        provider = self._get_provider(str(self.cfg.get("embedding_provider", "") or ""))
        if provider is None:
            return []
        for method_name in ("embedding", "embeddings", "get_embedding", "get_embeddings"):
            method = getattr(provider, method_name, None)
            if method is None:
                continue
            try:
                result = await method(text)
                if isinstance(result, list) and result:
                    return result
            except Exception:
                continue
        return []

    def _persona_text(self) -> str:
        if not self.cfg.get("enable_persona_injection_in_memory_generation", True):
            return ""
        try:
            pm = self.context.persona_manager
            persona = pm.get_default_persona_v3()
            if persona is None:
                return ""
            return str(getattr(persona, "system_prompt", "") or "")
        except Exception:
            return ""

    def resolve_scope(self, event: AstrMessageEvent) -> str:
        """群聊=群号；私聊隔离=u:{sender_id}；私聊共享=default。"""
        group_id = event.get_group_id() or ""
        if group_id:
            return str(group_id)
        if not self.cfg.get("enable_group_isolation", True):
            return "default"
        return f"u:{event.get_sender_id() or ''}"

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._background_tasks = [t for t in self._background_tasks if not t.done()]
        self._background_tasks.append(task)

    def _flush_lock(self, scope_id: str) -> asyncio.Lock:
        lock = self._flush_locks.get(scope_id)
        if lock is None:
            lock = asyncio.Lock()
            self._flush_locks[scope_id] = lock
        return lock

    async def _flush(self, scope_id: str) -> None:
        async with self._flush_lock(scope_id):
            if self.repo.count_raw(scope_id) == 0:
                return
            try:
                stats = await self.formation.flush_scope(scope_id, time.time())
                logger.info(f"记忆整理完成 scope={scope_id}: {stats}")
            except Exception as e:
                logger.warning(f"记忆整理失败 scope={scope_id}: {e}")
            finally:
                self.ingest.mark_flushed(scope_id)

    async def _sweeper_loop(self) -> None:
        """空闲触发：沉默超过阈值的 scope 定期 flush。"""
        try:
            while not self._stopping:
                await asyncio.sleep(10)
                try:
                    for scope in self.ingest.scopes_due_flush():
                        self._spawn(self._flush(scope))
                except Exception as e:
                    logger.warning(f"空闲整理调度失败: {e}")
        except asyncio.CancelledError:
            pass

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        if not self.cfg.get("enable_memory_system", True):
            return
        if not event.is_private_chat() and not getattr(
            event, "is_at_or_wake_command", False
        ):
            return
        message = (event.message_str or "").strip()
        if not message or message.startswith(_COMMAND_PREFIXES):
            return
        if self.ingest.is_blocked(message):
            return

        scope = self.resolve_scope(event)
        try:
            should_flush = self.ingest.accept(
                scope,
                message,
                str(event.get_sender_id() or ""),
                str(getattr(event, "get_sender_name", lambda: "")() or ""),
            )
            if should_flush:
                self._spawn(self._flush(scope))
        except Exception as e:
            logger.warning(f"消息入站失败: {e}")

    @filter.on_llm_request(priority=999)
    async def on_llm_request(self, event: AstrMessageEvent, req: ProviderRequest):
        if not self.cfg.get("enable_memory_system", True):
            return
        if not event.is_private_chat() and not getattr(
            event, "is_at_or_wake_command", False
        ):
            return
        query = (event.message_str or "").strip()
        if not query:
            return
        try:
            scope = self.resolve_scope(event)
            sender_name = str(getattr(event, "get_sender_name", lambda: "")() or "")
            injection = await self.recall.build_injection(
                scope, query, sender_name, time.time()
            )
            if injection and not any(
                "【相关记忆】" in getattr(p, "text", "")
                for p in req.extra_user_content_parts
            ):
                req.extra_user_content_parts.append(
                    TextPart(text=injection).mark_as_temp()
                )
        except Exception as e:
            logger.error(f"LLM请求记忆召回失败: {e}", exc_info=True)

    async def terminate(self):
        self._stopping = True
        for task in list(self._background_tasks):
            task.cancel()
        if self._sweeper_task:
            self._sweeper_task.cancel()
            try:
                await self._sweeper_task
            except asyncio.CancelledError:
                pass
        try:
            self.repo.close()
        except Exception:
            pass
        logger.info("Memora Connect v2 已安全关闭")

    async def safe_cleanup(self):
        await self.terminate()

    @filter.command_group("记忆")
    def memory(self):
        """记忆管理指令组"""
        pass

    @memory.command("回忆")
    async def memory_recall(self, event: AstrMessageEvent, keyword: str = ""):
        if not self.cfg.get("enable_memory_system", True):
            yield event.plain_result("记忆系统已禁用。")
            return
        scope = self.resolve_scope(event)
        if not keyword:
            mems = self.repo.list_memories(scope, limit=10)
        else:
            fused = await self.recall.recall(scope, keyword, time.time())
            mems = [c.memory for c in fused]
        if not mems:
            yield event.plain_result("没有找到相关记忆。")
            return
        lines = ["🔍 找到以下记忆："]
        for i, m in enumerate(mems[:10], 1):
            date = time.strftime("%Y-%m-%d", time.localtime(m.created_at))
            detail = f" —— {m.details}" if m.details else ""
            lines.append(f"{i}. ({date}) {m.content}{detail} [ID:{m.id[:8]}]")
        yield event.plain_result("\n".join(lines))

    @memory.command("删除")
    async def memory_delete(self, event: AstrMessageEvent, memory_id: str):
        if not self.cfg.get("enable_memory_system", True):
            yield event.plain_result("记忆系统已禁用。")
            return
        scope = self.resolve_scope(event)
        mem = self.repo.get_memory(memory_id.strip())
        if mem is None or mem.scope_id != scope:
            yield event.plain_result(f"未找到记忆: {memory_id}")
            return
        self.repo.delete_memory(mem.id)
        yield event.plain_result(f"✅ 记忆已删除: {mem.content[:30]}")

    @memory.command("状态")
    async def memory_status(self, event: AstrMessageEvent):
        if not self.cfg.get("enable_memory_system", True):
            yield event.plain_result("记忆系统已禁用。")
            return
        scope = self.resolve_scope(event)
        stats = self.repo.stats(scope)
        yield event.plain_result(
            "\n".join(
                [
                    "📊 记忆系统状态 (Memora Connect v2)",
                    f"当前空间: {scope or 'default'}",
                    f"记忆数量: {stats['memories']}",
                    f"要素数量: {stats['elements']}",
                    f"关系数量: {stats['connections']}",
                    f"印象数量: {stats['impressions']}",
                    f"话题数量: {stats['sessions']}",
                    f"数据库: {self.repo.db_path}",
                ]
            )
        )

    @memory.command("印象")
    async def memory_impression(self, event: AstrMessageEvent, name: str):
        if not self.cfg.get("enable_memory_system", True):
            yield event.plain_result("记忆系统已禁用。")
            return
        scope = self.resolve_scope(event)
        imp = self.repo.get_impression(scope, name.strip())
        parts = [f"📝 {name} 的印象摘要:"]
        if imp is not None:
            parts.append(f"   印象: {imp.summary or '无'}")
            parts.append(f"   好感度: {score_verbal(imp.score)} ({imp.score:.2f})")
            parts.append(
                f"   更新时间: {time.strftime('%Y-%m-%d %H:%M', time.localtime(imp.updated_at))}"
            )
        else:
            parts.append(f"   尚未建立对 {name} 的印象")
        elem = next(
            (e for e in self.repo.list_elements(scope) if e.name == name.strip()), None
        )
        related = self.repo.get_element_memories(elem.id, limit=5) if elem else []
        if related:
            parts.append("\n📚 相关记忆:")
            for i, m in enumerate(related, 1):
                parts.append(f"   {i}. {m.content}")
        else:
            parts.append(f"\n📚 暂无关于 {name} 的相关记忆")
        yield event.plain_result("\n".join(parts))

    @memory.command("图谱")
    async def memory_graph(self, event: AstrMessageEvent, layout_style: str = "auto"):
        """生成记忆图谱可视化图片

        Args:
            layout_style(string): 布局风格，可选 auto/force_directed/circular/kamada_kawai/spectral/community/hierarchical
        """
        if not self.cfg.get("enable_memory_system", True):
            yield event.plain_result("记忆系统已禁用。")
            return
        scope = self.resolve_scope(event)
        yield event.plain_result(f"🔄 正在生成记忆图谱（布局风格: {layout_style}），请稍候...")
        try:
            image_path = await generate_graph_image(
                self.repo, scope, os.path.join(self.data_dir, "graphs"), layout_style
            )
        except Exception as e:
            logger.error(f"生成记忆图谱失败: {e}", exc_info=True)
            image_path = None
        if image_path:
            try:
                if hasattr(event, "send_image"):
                    await event.send_image(image_path)
                    yield event.plain_result("✅ 记忆图谱已生成！")
                else:
                    yield event.image_result(image_path)
            except Exception as e:
                logger.error(f"发送图片失败: {e}")
                yield event.plain_result(f"✅ 图谱已生成：{image_path}")
        else:
            yield event.plain_result(
                "❌ 图谱生成失败：记忆数据为空，或未安装 networkx/matplotlib。"
            )

    async def add_memory_api(self, content: str, theme: str = "", group_id: str = "",
                             details: str = "", participants: str = "",
                             location: str = "", emotion: str = "", tags: str = "",
                             elements: str = "") -> str | None:
        scope = group_id or "default"
        if not content:
            return None
        now = time.time()
        memory = Memory(id=new_id("mem"), scope_id=scope, content=content,
                        details=details, emotion=emotion, created_at=now,
                        last_accessed=now)
        self.repo.upsert_memory(memory)
        names: list[tuple[str, str]] = []
        if elements:
            try:
                parsed = json.loads(elements) if isinstance(elements, str) else elements
                for el in parsed if isinstance(parsed, list) else []:
                    if isinstance(el, dict) and str(el.get("name", "")).strip():
                        cat = str(el.get("category", "trait")).strip()
                        names.append((str(el["name"]).strip(),
                                      cat if cat in CATEGORIES else "trait"))
            except Exception:
                pass
        if not names:
            for raw, cat in ((participants, "person"), (location, "place"),
                             (tags, "trait"), (theme, "trait")):
                names.extend((p.strip(), cat) for p in (raw or "").replace("，", ",").split(",")
                             if p.strip())
        for name, cat in names:
            elem = self.repo.get_or_create_element(scope, name, cat, now)
            self.repo.link_memory_element(memory.id, elem.id, "")
        return memory.id

    async def recall_memories_api(self, keyword: str, group_id: str = "") -> list:
        scope = group_id or "default"
        fused = await self.recall.recall(scope, keyword, time.time())
        return [c.memory.__dict__ for c in fused]

    async def record_impression_api(self, person_name: str, summary: str,
                                    score: float | None, details: str = "",
                                    group_id: str = "") -> bool:
        scope = group_id or "default"
        if not person_name or not summary:
            return False
        current = self.repo.get_impression(scope, person_name)
        new_score = max(0.0, min(1.0, float(score))) if score is not None else (
            current.score if current else 0.5
        )
        self.repo.upsert_impression(scope, person_name, new_score, summary, time.time())
        return True

    async def get_impression_summary_api(self, person_name: str,
                                         group_id: str = "") -> dict | None:
        imp = self.repo.get_impression(group_id or "default", person_name)
        if imp is None:
            return None
        return {"score": imp.score, "summary": imp.summary,
                "last_updated": imp.updated_at}

    async def adjust_impression_score_api(self, person_name: str, delta: float,
                                          group_id: str = "") -> float | None:
        return self.repo.adjust_impression(
            group_id or "default", person_name, float(delta), time.time()
        )

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
            theme(string): 核心关键词，用逗号分隔（优先使用elements）
            elements(string): 记忆元素JSON数组，格式如 [{"name":"张三","category":"person","role":"subject"}]，category可选: person/object/place/action/trait
            details(string): 具体细节和背景信息
            emotion(string): 情感色彩
            allow_forget(string): 是否允许遗忘
            confidence(number): 置信度，0-1之间的数值
            participants(string): 涉及的人物，用逗号分隔
            location(string): 相关场景或地点
            tags(string): 分类标签
        """
        if not content or not content.strip():
            return "创建记忆失败：内容为空"
        scope = self.resolve_scope(event)
        try:
            confidence_float = max(0.0, min(1.0, float(confidence)))
        except (ValueError, TypeError):
            confidence_float = 0.7
        memory_id = await self.add_memory_api(
            content=content.strip(),
            theme=theme or "",
            group_id=scope,
            details=details,
            participants=participants,
            location=location,
            emotion=emotion,
            tags=tags,
            elements=elements,
        )
        if memory_id:
            self.repo.update_memory_fields(memory_id, strength=confidence_float)
            return f"记忆创建成功,内容为:{content}"
        return "记忆创建失败"

    @filter.llm_tool(name="recall_memory")
    async def recall_memory_tool(
        self, event: AstrMessageEvent, keyword: str
    ) -> MessageEventResult:
        """召回所有相关记忆，包括联想记忆

        Args:
            keyword(string): 要查询的关键词或内容
        """
        if not keyword or not keyword.strip():
            return "没有相关记忆"
        scope = self.resolve_scope(event)
        try:
            fused = await self.recall.recall(scope, keyword.strip(), time.time())
        except Exception as e:
            logger.error(f"记忆召回工具失败：{e}")
            return "记忆召回失败"
        if not fused:
            return "没有相关记忆"
        lines = ["记忆召回结果:"]
        for i, cand in enumerate(fused, 1):
            m = cand.memory
            date = time.strftime("%Y-%m-%d", time.localtime(m.created_at))
            lines.append(f"{i}. [ID:{m.id}] ({date}) {m.content}")
        lines.append("提示：如果记忆已过时允许删除记忆")
        return "\n".join(lines)

    @filter.llm_tool(name="delete_memory")
    async def delete_memory_tool(
        self, event: AstrMessageEvent, memory_id: str, reason: str = ""
    ) -> MessageEventResult:
        """删除指定记忆

        Args:
            memory_id(string): 需要删除的记忆ID
            reason(string): 删除原因或说明
        """
        scope = self.resolve_scope(event)
        mem = self.repo.get_memory(memory_id.strip())
        if mem is None or mem.scope_id != scope:
            return f"未找到记忆: {memory_id}"
        self.repo.delete_memory(mem.id)
        logger.info(f"LLM工具删除记忆：{mem.id} 原因:{reason}")
        return f"记忆已删除: {mem.id}"

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
            delta_float = float(delta)
        except (ValueError, TypeError):
            return "调整印象失败：delta 参数无效"
        scope = self.resolve_scope(event)
        new_score = self.repo.adjust_impression(scope, person_name.strip(), delta_float, time.time())
        if reason:
            self.repo.upsert_impression(
                scope, person_name.strip(), new_score,
                f"调整对{person_name}的印象：{reason}", time.time()
            )
        return f"调整印象成功，{person_name} 的好感度为 {new_score:.2f}"

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
        if not person_name.strip() or not summary.strip():
            return "记录印象失败：参数不完整"
        scope = self.resolve_scope(event)
        score_float = None
        if score is not None:
            try:
                score_float = max(0.0, min(1.0, float(score)))
            except (ValueError, TypeError):
                score_float = None
        current = self.repo.get_impression(scope, person_name.strip())
        final_score = score_float if score_float is not None else (
            current.score if current else 0.5
        )
        text = summary.strip()
        if details.strip():
            text = f"{text}（{details.strip()}）"
        self.repo.upsert_impression(scope, person_name.strip(), final_score, text, time.time())
        self.repo.get_or_create_element(scope, person_name.strip(), "person", time.time())
        return f"记录印象成功，{person_name} 的好感度为 {final_score:.2f}"