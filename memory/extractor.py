"""
批量记忆提取模块
通过 LLM 从对话中提取记忆点和主题
"""
import json
import re
from datetime import datetime
from typing import Dict, List, Any
try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class BatchMemoryExtractor:
    """记忆提取器，通过LLM调用获取多个记忆点和主题"""
    
    def __init__(self, memory_system):
        self.memory_system = memory_system

    def _safe_load_json(self, text: str):
        try:
            return json.loads(text)
        except Exception:
            match = re.search(r"\{[\s\S]*\}", text)
            if not match:
                return None
            try:
                return json.loads(match.group(0))
            except Exception:
                return None
    
    async def extract_impressions_from_conversation(self, conversation_history: List[Dict[str, Any]], group_id: str) -> List[Dict[str, Any]]:
        """
        从对话中提取人物印象
        
        Args:
            conversation_history: 对话历史
            group_id: 群组ID
            
        Returns:
            人物印象列表
        """
        if not conversation_history:
            return []
        
        formatted_history = self._format_conversation_history(conversation_history)
        
        prompt = f"""请从以下对话中提取人物印象信息。

对话历史：
{formatted_history}

任务要求：
1. 识别对话中涉及的所有人物
2. 提取每个人物的印象描述
3. 为每个印象提供：
   - person_name: 人物姓名
   - summary: 印象摘要
   - score: 好感度分数（0-1）
   - details: 详细描述
   - confidence: 置信度（0-1）

返回格式：
{{
  "impressions": [
    {{
      "person_name": "张三",
      "summary": "友善且乐于助人",
      "score": 0.8,
      "details": "主动提供帮助，态度友好",
      "confidence": 0.9
    }}
  ]
}}

只返回JSON格式
"""

        try:
            provider = await self.memory_system.get_llm_provider()
            if not provider:
                return []
            
            response = await provider.text_chat(
                prompt=prompt,
                contexts=[],
                system_prompt="你是一个人物印象提取助手"
            )
            raw_text = (getattr(response, "completion_text", "") or "").strip()
            if not raw_text:
                return []
            data = self._safe_load_json(raw_text)
            if not isinstance(data, dict):
                return []
            impressions = data.get("impressions", [])
            
            # 过滤有效印象
            valid_impressions = []
            for impression in impressions:
                if impression.get("person_name") and impression.get("summary"):
                    valid_impressions.append({
                        "person_name": str(impression["person_name"]),
                        "summary": str(impression["summary"]),
                        "score": float(impression.get("score", 0.5)),
                        "details": str(impression.get("details", "")),
                        "confidence": float(impression.get("confidence", 0.7))
                    })
            
            return valid_impressions
            
        except Exception as e:
            logger.error(f"提取人物印象失败: {e}")
            return []
    
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
   - 人物印象（对他人评价、看法或互动）
2. 为每个记忆生成完整信息：
   - 主题（theme）：核心关键词，用逗号分隔
   - 内容（content）：简洁的核心记忆
   - 细节（details）：具体细节和背景，丰富、详细、准确的记忆信息
   - 参与者（participants）：涉及的人物，特别注意：如果发言者是[Bot]，则使用"我"或Bot的身份作为参与者；如果是用户，则使用用户名称
   - 地点（location）：相关场景
   - 情感（emotion）：情感色彩
   - 标签（tags）：分类标签
   - 置信度（confidence）：0-1之间的数值
   - 记忆类型（memory_type）："normal"（普通记忆）或"impression"（人物印象）
3. 可以生成多个记忆，包括小事
4. 返回JSON格式

特别注意：
- 请仔细区分[Bot]和用户的发言
- 当[Bot]发言时，在参与者字段使用第一人称"我"而不是"其他用户"
- 确保LLM在后续上下文引用时能准确区分Bot的自我表述与用户的外部输入
- 对于人物印象记忆：memory_type设为"impression"，并在theme中包含人物姓名
- 对于普通记忆：memory_type设为"normal"
- 当对话中涉及对他人（非Bot）的评价、看法或互动时，创建印象记忆

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
      "confidence": 0.9,
      "memory_type": "normal"
    }},
    {{
      "theme": "张三,印象",
      "content": "张三很友善且乐于助人",
      "details": "在讨论中主动提供帮助，态度友好",
      "participants": "我,张三",
      "location": "会议室",
      "emotion": "赞赏",
      "tags": "印象,人际",
      "confidence": 0.8,
      "memory_type": "impression"
    }},
    {{
      "theme": "午餐,同事",
      "content": "丰富、详细、准确的记忆信息",
      "details": "讨论了周末的计划",
      "participants": "我,小王",
      "location": "公司食堂",
      "emotion": "轻松,愉快",
      "tags": "日常,社交",
      "confidence": 0.5,
      "memory_type": "normal"
    }}
  ]
}}

要求：
- 捕捉所有有意义的对话内容
- 小事也可以记录，降低置信度即可
- 内容要具体、生动
- 可以生成5-8个记忆
- 特别注意识别人物印象，当涉及对他人评价时创建印象记忆
- 印象记忆的theme应包含人物姓名和"印象"关键词
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
                formatted_lines.append(f"[{time_str}] [Bot]: {content}")
            else:
                # 用户消息，保持原格式
                formatted_lines.append(f"[{time_str}] {sender}: {content}")
        
        return "\n".join(formatted_lines)
    
    def _parse_batch_response(self, response_text: str) -> List[Dict[str, Any]]:
        """解析批量提取的LLM响应"""
        try:
            # 清理响应文本，处理中文引号和格式问题
            cleaned_text = response_text
            for old, new in [('"', '"'), ('"', '"'), (''', "'"), (''', "'"), ('，', ','), ('：', ':')]:
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
                    
                    # 安全地获取每个字段，确保类型正确
                    confidence = 0.7
                    try:
                        confidence_val = mem.get("confidence", 0.7)
                        if isinstance(confidence_val, (int, float)):
                            confidence = float(confidence_val)
                        elif isinstance(confidence_val, str):
                            confidence = float(confidence_val)
                    except (ValueError, TypeError):
                        confidence = 0.7
                    
                    theme = ""
                    try:
                        theme_val = mem.get("theme", "")
                        theme = str(theme_val).strip()
                    except (ValueError, TypeError):
                        theme = ""
                    
                    content = ""
                    try:
                        content_val = mem.get("content", "")
                        content = str(content_val).strip()
                    except (ValueError, TypeError):
                        content = ""
                    
                    details = ""
                    try:
                        details_val = mem.get("details", "")
                        details = str(details_val).strip()
                    except (ValueError, TypeError):
                        details = ""
                    
                    participants = ""
                    try:
                        participants_val = mem.get("participants", "")
                        participants = str(participants_val).strip()
                    except (ValueError, TypeError):
                        participants = ""
                    
                    location = ""
                    try:
                        location_val = mem.get("location", "")
                        location = str(location_val).strip()
                    except (ValueError, TypeError):
                        location = ""
                    
                    emotion = ""
                    try:
                        emotion_val = mem.get("emotion", "")
                        emotion = str(emotion_val).strip()
                    except (ValueError, TypeError):
                        emotion = ""
                    
                    tags = ""
                    try:
                        tags_val = mem.get("tags", "")
                        tags = str(tags_val).strip()
                    except (ValueError, TypeError):
                        tags = ""
                    
                    memory_type = "normal"
                    try:
                        memory_type_val = mem.get("memory_type", "normal")
                        memory_type = str(memory_type_val).strip().lower()
                    except (ValueError, TypeError):
                        memory_type = "normal"
                    
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
                            "confidence": max(0.0, min(1.0, confidence)),
                            "memory_type": memory_type if memory_type in ["normal", "impression"] else "normal"
                        })
                        
                except (ValueError, TypeError, AttributeError):
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
