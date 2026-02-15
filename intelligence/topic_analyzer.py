"""
基于话题的统一LLM调用分析器
通过积累消息后一次性LLM调用完成话题分析、记忆生成和印象提取
"""
import json
import re
import time
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


@dataclass
class Session:
    """会话数据类"""
    session_id: str
    topic: str
    messages: List[Dict] = field(default_factory=list)
    status: str = "ongoing"  # "ongoing" | "completed"
    keywords: List[str] = field(default_factory=list)
    subtext: str = ""
    emotion: str = ""
    participants: List[str] = field(default_factory=list)
    summary: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    last_active: datetime = field(default_factory=datetime.now)


class TopicAnalyzer:
    """
    基于话题的统一LLM调用分析器
    替代原有的 TopicEngine 和 BatchMemoryExtractor
    """

    def __init__(self, memory_system):
        self.memory_system = memory_system

        # 消息缓冲区：{group_id: [messages]}
        self._message_buffers: Dict[str, List[Dict]] = defaultdict(list)

        # 上次分析时间：{group_id: timestamp}
        self._last_analysis_time: Dict[str, float] = defaultdict(float)

        # 活跃会话：{group_id: {session_id: Session}}
        self._active_sessions: Dict[str, Dict[str, Session]] = defaultdict(dict)

        # 已完成会话摘要：{group_id: [Session]}
        self._completed_sessions: Dict[str, List[Session]] = defaultdict(list)

        # 会话ID计数器
        self._session_counter: int = 0

        logger.info("TopicAnalyzer 已初始化")

    def _get_config_value(self, key: str, default):
        """从配置中获取值"""
        return self.memory_system.memory_config.get(key, default)

    @property
    def trigger_interval_seconds(self) -> int:
        minutes = self._get_config_value("topic_trigger_interval_minutes", 5)
        return minutes * 60

    @property
    def message_threshold(self) -> int:
        return self._get_config_value("topic_message_threshold", 12)

    @property
    def max_completed_sessions(self) -> int:
        return self._get_config_value("recent_completed_sessions_count", 5)

    def _next_session_id(self) -> str:
        self._session_counter += 1
        return f"session_{self._session_counter:04d}"

    async def add_message(self, message: str, sender_id: str, sender_name: str, group_id: str):
        """
        添加消息到缓冲区，检查是否需要触发分析

        Args:
            message: 消息内容
            sender_id: 发送者ID
            sender_name: 发送者名称
            group_id: 群组/会话ID
        """
        msg = {
            "content": message,
            "sender_id": sender_id,
            "sender_name": sender_name,
            "timestamp": time.time(),
            "time_str": datetime.now().strftime("%m-%d %H:%M")
        }
        self._message_buffers[group_id].append(msg)

        if self._should_trigger(group_id):
            await self._run_analysis(group_id)

    def _should_trigger(self, group_id: str) -> bool:
        """检查是否满足触发条件"""
        buf = self._message_buffers.get(group_id, [])
        if not buf:
            return False

        # 数量触发
        if len(buf) >= self.message_threshold:
            return True

        # 时间触发
        last_time = self._last_analysis_time.get(group_id, 0)
        if last_time > 0 and (time.time() - last_time) >= self.trigger_interval_seconds:
            return True

        return False

    async def _run_analysis(self, group_id: str):
        """执行一次话题分析"""
        buf = self._message_buffers.get(group_id, [])
        if not buf:
            return

        # 取出缓冲区消息并清空
        messages = list(buf)
        self._message_buffers[group_id] = []
        self._last_analysis_time[group_id] = time.time()

        # 构建LLM输入
        prompt = self._build_prompt(messages, group_id)

        # 调用LLM
        try:
            provider = await self.memory_system.get_llm_provider()
            if not provider:
                logger.warning("LLM提供商不可用，跳过话题分析")
                # 把消息放回缓冲区
                self._message_buffers[group_id] = messages + self._message_buffers[group_id]
                return

            response = await provider.text_chat(
                prompt=prompt,
                contexts=[],
                system_prompt="你是一个对话分析助手，负责将对话消息分配到不同的话题会话中，并提取记忆和印象。只返回JSON格式。"
            )

            raw_text = (getattr(response, "completion_text", "") or "").strip()
            if not raw_text:
                logger.warning("LLM返回空响应")
                return

            # 解析结果
            result = self._parse_response(raw_text)
            if not result:
                logger.warning("LLM响应解析失败")
                return

            # 处理分析结果
            await self._process_result(result, messages, group_id)

        except Exception as e:
            logger.error(f"话题分析失败: {e}", exc_info=True)
            # 把消息放回缓冲区
            self._message_buffers[group_id] = messages + self._message_buffers[group_id]

    def _build_prompt(self, messages: List[Dict], group_id: str) -> str:
        """构建LLM分析的完整prompt"""
        parts = []

        # 1. 新消息（带序号）
        parts.append("新消息:")
        for i, msg in enumerate(messages):
            sender = msg.get("sender_name", "未知")
            content = msg.get("content", "")
            time_str = msg.get("time_str", "")
            parts.append(f"[{i}] [{time_str}] {sender}: {content}")

        # 2. 未完成会话
        active = self._active_sessions.get(group_id, {})
        if active:
            parts.append("\n未完成会话（完整消息历史）:")
            for sid, session in active.items():
                parts.append(f"\n会话 {sid}:")
                parts.append(f"话题: {session.topic}")
                parts.append(f"关键词: {', '.join(session.keywords)}")
                parts.append("消息:")
                for m in session.messages:
                    parts.append(f"  [{m.get('time_str', '')}] {m.get('sender_name', '未知')}: {m.get('content', '')}")

        # 3. 最近完成会话摘要
        completed = self._completed_sessions.get(group_id, [])
        if completed:
            recent = completed[-self.max_completed_sessions:]
            parts.append("\n最近完成会话摘要:")
            for session in recent:
                parts.append(f"- 会话 {session.session_id}: {session.topic} - {session.summary or '无摘要'}")

        # 4. 任务要求
        parts.append("""
请分析以上新消息，将其分配到合适的会话中。

要求：
1. 判断每条新消息属于哪个会话（延续已有会话或创建新会话）
2. 如果延续已有会话，使用已有的session_id；如果是新会话，使用"new_N"格式（N从1开始）
3. 分析每个会话的言外之意（subtext）
4. 判断会话状态：ongoing（进行中）或 completed（已结束）
5. 为每个会话生成记忆内容
6. 如果涉及对人物的评价或互动，生成印象
7. 对completed的会话生成摘要

返回JSON格式：
{
  "sessions": [
    {
      "session_id": "session_0001或new_1",
      "topic": "话题名称",
      "new_message_indices": [0, 1, 2],
      "status": "ongoing或completed",
      "keywords": ["关键词1", "关键词2"],
      "subtext": "言外之意分析",
      "emotion": "情感色彩",
      "participants": ["参与者1"],
      "summary": "仅completed时需要，会话摘要",
      "memory": {
        "content": "记忆核心内容",
        "details": "详细信息，包含言外之意分析",
        "participants": "参与者",
        "location": "地点",
        "emotion": "情感",
        "tags": "标签",
        "confidence": 0.8
      },
      "impression": {
        "person_name": "人物名称",
        "summary": "印象摘要",
        "score": 0.7,
        "details": "详细描述"
      }
    }
  ]
}

注意：
- impression字段可选，仅在涉及对人物评价时生成
- memory字段必须为每个会话生成
- new_message_indices中的数字对应新消息的序号
- 每条新消息必须被分配到某个会话中
- 只返回JSON，不要其他内容
""")
        return "\n".join(parts)

    def _parse_response(self, raw_text: str) -> Optional[Dict]:
        """解析LLM返回的JSON"""
        try:
            # 清理中文标点
            cleaned = raw_text
            for old, new in [('\u201c', '"'), ('\u201d', '"'), ('\u2018', "'"), ('\u2019', "'"), ('\uff0c', ','), ('\uff1a', ':')]:
                cleaned = cleaned.replace(old, new)

            # 提取JSON
            match = re.search(r'\{[\s\S]*\}', cleaned)
            if not match:
                return None

            json_str = match.group(0)
            # 修复常见格式问题
            json_str = re.sub(r',\s*}', '}', json_str)
            json_str = re.sub(r',\s*]', ']', json_str)

            data = json.loads(json_str)
            if "sessions" not in data or not isinstance(data["sessions"], list):
                return None
            return data

        except (json.JSONDecodeError, Exception) as e:
            logger.debug(f"JSON解析失败: {e}")
            return None

    async def _process_result(self, result: Dict, messages: List[Dict], group_id: str):
        """处理LLM分析结果，更新会话状态并生成衍生产物"""
        sessions_data = result.get("sessions", [])

        for s_data in sessions_data:
            try:
                session_id = str(s_data.get("session_id", ""))
                topic = str(s_data.get("topic", "")).strip()
                indices = s_data.get("new_message_indices", [])
                status = str(s_data.get("status", "ongoing")).strip().lower()
                keywords = s_data.get("keywords", [])
                subtext = str(s_data.get("subtext", "")).strip()
                emotion = str(s_data.get("emotion", "")).strip()
                participants = s_data.get("participants", [])
                summary = s_data.get("summary")

                if not topic:
                    continue

                # 收集本次分配到此会话的消息
                new_msgs = []
                for idx in indices:
                    if isinstance(idx, int) and 0 <= idx < len(messages):
                        new_msgs.append(messages[idx])

                # 判断是延续已有会话还是新建
                is_new = session_id.startswith("new_") or session_id not in self._active_sessions.get(group_id, {})

                if is_new:
                    # 创建新会话
                    real_id = self._next_session_id()
                    session = Session(
                        session_id=real_id,
                        topic=topic,
                        messages=new_msgs,
                        status=status,
                        keywords=keywords if isinstance(keywords, list) else [keywords],
                        subtext=subtext,
                        emotion=emotion,
                        participants=participants if isinstance(participants, list) else [participants],
                        summary=str(summary) if summary else None
                    )
                    self._active_sessions[group_id][real_id] = session
                    logger.info(f"创建新会话: {real_id}, 话题: {topic}")
                else:
                    # 延续已有会话
                    session = self._active_sessions[group_id][session_id]
                    session.messages.extend(new_msgs)
                    session.last_active = datetime.now()
                    session.status = status
                    if keywords:
                        session.keywords = list(set(session.keywords + (keywords if isinstance(keywords, list) else [keywords])))
                    if subtext:
                        session.subtext = subtext
                    if emotion:
                        session.emotion = emotion
                    if participants:
                        new_p = participants if isinstance(participants, list) else [participants]
                        session.participants = list(set(session.participants + new_p))
                    if summary:
                        session.summary = str(summary)
                    logger.debug(f"更新会话: {session_id}, 话题: {topic}")

                # 生成衍生产物
                await self._generate_products(s_data, session if not is_new else self._active_sessions[group_id].get(real_id if is_new else session_id), group_id)

                # 如果会话已完成，移到已完成列表
                if status == "completed":
                    sid = real_id if is_new else session_id
                    completed_session = self._active_sessions[group_id].pop(sid, None)
                    if completed_session:
                        self._completed_sessions[group_id].append(completed_session)
                        # 限制已完成会话数量
                        max_count = self.max_completed_sessions * 2
                        if len(self._completed_sessions[group_id]) > max_count:
                            self._completed_sessions[group_id] = self._completed_sessions[group_id][-max_count:]
                        logger.info(f"会话完成: {sid}, 话题: {topic}")

            except Exception as e:
                logger.error(f"处理会话数据失败: {e}", exc_info=True)
                continue

        # 保存记忆状态
        await self.memory_system._queue_save_memory_state(group_id)

    async def _generate_products(self, s_data: Dict, session: Session, group_id: str):
        """生成衍生产物：记忆和印象"""
        if not session:
            return

        # 1. 生成记忆
        memory_data = s_data.get("memory")
        if memory_data and isinstance(memory_data, dict):
            try:
                content = str(memory_data.get("content", "")).strip()
                details = str(memory_data.get("details", "")).strip()
                m_participants = str(memory_data.get("participants", "")).strip()
                location = str(memory_data.get("location", "")).strip()
                m_emotion = str(memory_data.get("emotion", "")).strip()
                tags = str(memory_data.get("tags", "")).strip()
                confidence = float(memory_data.get("confidence", 0.7))

                if content:
                    theme = ", ".join(session.keywords) if session.keywords else session.topic
                    # 清理主题中的特殊字符
                    theme = re.sub(r'[^\w\u4e00-\u9fff,，\s]', '', theme)

                    concept_id = self.memory_system.memory_graph.add_concept(theme)
                    self.memory_system.memory_graph.add_memory(
                        content=content,
                        concept_id=concept_id,
                        details=details,
                        participants=m_participants,
                        location=location,
                        emotion=m_emotion,
                        tags=tags,
                        strength=max(0.0, min(1.0, confidence)),
                        group_id=group_id
                    )
                    logger.debug(f"生成记忆: {content[:30]}...")
            except Exception as e:
                logger.error(f"生成记忆失败: {e}", exc_info=True)

        # 2. 生成印象
        impression_data = s_data.get("impression")
        if impression_data and isinstance(impression_data, dict):
            try:
                person_name = str(impression_data.get("person_name", "")).strip()
                i_summary = str(impression_data.get("summary", "")).strip()
                score = impression_data.get("score")
                i_details = str(impression_data.get("details", "")).strip()

                if person_name and i_summary:
                    score_float = None
                    if score is not None:
                        try:
                            score_float = max(0.0, min(1.0, float(score)))
                        except (ValueError, TypeError):
                            score_float = None

                    self.memory_system.record_person_impression(
                        group_id, person_name, i_summary, score_float, i_details
                    )
                    logger.debug(f"生成印象: {person_name} - {i_summary[:30]}...")
            except Exception as e:
                logger.error(f"生成印象失败: {e}", exc_info=True)

    # --- 公开查询接口 ---

    def get_active_sessions(self, group_id: str) -> List[Dict]:
        """获取所有活跃会话"""
        sessions = self._active_sessions.get(group_id, {})
        result = []
        for session in sessions.values():
            result.append({
                "session_id": session.session_id,
                "topic": session.topic,
                "status": session.status,
                "keywords": session.keywords,
                "subtext": session.subtext,
                "emotion": session.emotion,
                "participants": session.participants,
                "message_count": len(session.messages),
                "created_at": session.created_at.isoformat(),
                "last_active": session.last_active.isoformat()
            })
        return result

    def get_completed_sessions(self, group_id: str) -> List[Dict]:
        """获取已完成会话"""
        sessions = self._completed_sessions.get(group_id, [])
        return [
            {
                "session_id": s.session_id,
                "topic": s.topic,
                "summary": s.summary,
                "keywords": s.keywords,
                "message_count": len(s.messages)
            }
            for s in sessions[-self.max_completed_sessions:]
        ]

    def get_statistics(self, group_id: str) -> Dict:
        """获取统计信息"""
        active = self._active_sessions.get(group_id, {})
        completed = self._completed_sessions.get(group_id, [])
        buffered = len(self._message_buffers.get(group_id, []))
        return {
            "active_sessions": len(active),
            "completed_sessions": len(completed),
            "buffered_messages": buffered,
            "total_messages": sum(len(s.messages) for s in active.values()) + sum(len(s.messages) for s in completed)
        }
