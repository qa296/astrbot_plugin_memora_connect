"""
情感分析模块
提供多维度情感分析、情感档案管理、情感模式识别等功能
"""

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from astrbot.api import logger


@dataclass
class EmotionAnalysis:
    """多维度情感分析数据结构"""
    primary_emotion: str = ""  # 主要情感（喜、怒、哀、乐、惊、恐、爱、恶）
    emotion_intensity: float = 0.5  # 情感强度 (0-1)
    emotion_duration: str = "transient"  # 情感持续时间（transient, short-term, long-term）
    emotion_source: str = ""  # 情感来源/触发器
    complex_emotions: List[str] = field(default_factory=list)  # 复合情感
    confidence: float = 0.7  # 置信度 (0-1)
    timestamp: float = field(default_factory=lambda: time.time())  # 时间戳
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)
    
    def to_json(self) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EmotionAnalysis':
        """从字典创建"""
        return cls(
            primary_emotion=data.get("primary_emotion", ""),
            emotion_intensity=float(data.get("emotion_intensity", 0.5)),
            emotion_duration=data.get("emotion_duration", "transient"),
            emotion_source=data.get("emotion_source", ""),
            complex_emotions=data.get("complex_emotions", []),
            confidence=float(data.get("confidence", 0.7)),
            timestamp=float(data.get("timestamp", time.time()))
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> Optional['EmotionAnalysis']:
        """从JSON字符串创建"""
        try:
            data = json.loads(json_str)
            return cls.from_dict(data)
        except Exception as e:
            logger.error(f"解析情感JSON失败: {e}")
            return None
    
    @classmethod
    def from_simple_emotion(cls, emotion_str: str) -> 'EmotionAnalysis':
        """从简单的情感字符串创建（向后兼容）"""
        if not emotion_str:
            return cls()
        
        # 解析逗号分隔的情感
        emotions = [e.strip() for e in emotion_str.split(',') if e.strip()]
        if not emotions:
            return cls()
        
        # 第一个作为主要情感，其余作为复合情感
        primary = emotions[0]
        complex = emotions[1:] if len(emotions) > 1 else []
        
        return cls(
            primary_emotion=primary,
            complex_emotions=complex,
            emotion_intensity=0.5,
            confidence=0.7
        )


@dataclass
class EmotionProfile:
    """用户情感档案"""
    user_id: str  # 用户ID
    group_id: str = ""  # 群组ID（用于群聊隔离）
    emotion_timeline: List[EmotionAnalysis] = field(default_factory=list)  # 情感时间线
    emotion_triggers: Dict[str, int] = field(default_factory=dict)  # 情感触发器统计
    dominant_emotions: Dict[str, float] = field(default_factory=dict)  # 主导情感分布
    last_updated: float = field(default_factory=lambda: time.time())
    
    def add_emotion_record(self, emotion: EmotionAnalysis):
        """添加情感记录"""
        self.emotion_timeline.append(emotion)
        
        # 更新情感触发器统计
        if emotion.emotion_source:
            self.emotion_triggers[emotion.emotion_source] = \
                self.emotion_triggers.get(emotion.emotion_source, 0) + 1
        
        # 更新主导情感分布
        if emotion.primary_emotion:
            current_score = self.dominant_emotions.get(emotion.primary_emotion, 0.0)
            self.dominant_emotions[emotion.primary_emotion] = \
                current_score + emotion.emotion_intensity * emotion.confidence
        
        # 限制时间线长度（保留最近100条）
        if len(self.emotion_timeline) > 100:
            self.emotion_timeline = self.emotion_timeline[-100:]
        
        self.last_updated = time.time()
    
    def get_recent_emotions(self, limit: int = 10) -> List[EmotionAnalysis]:
        """获取最近的情感记录"""
        return self.emotion_timeline[-limit:]
    
    def get_emotion_trend(self) -> Dict[str, Any]:
        """获取情感趋势分析"""
        if not self.emotion_timeline:
            return {
                "trend": "neutral",
                "average_intensity": 0.5,
                "dominant_emotion": None,
                "emotion_variability": 0.0
            }
        
        recent_emotions = self.emotion_timeline[-20:]  # 分析最近20条
        
        # 计算平均强度
        avg_intensity = sum(e.emotion_intensity for e in recent_emotions) / len(recent_emotions)
        
        # 找出主导情感
        emotion_counts = {}
        for e in recent_emotions:
            if e.primary_emotion:
                emotion_counts[e.primary_emotion] = emotion_counts.get(e.primary_emotion, 0) + 1
        
        dominant = max(emotion_counts.items(), key=lambda x: x[1])[0] if emotion_counts else None
        
        # 计算情感变化性（标准差）
        if len(recent_emotions) > 1:
            mean_intensity = avg_intensity
            variance = sum((e.emotion_intensity - mean_intensity) ** 2 for e in recent_emotions) / len(recent_emotions)
            variability = variance ** 0.5
        else:
            variability = 0.0
        
        return {
            "trend": "positive" if avg_intensity > 0.6 else "negative" if avg_intensity < 0.4 else "neutral",
            "average_intensity": avg_intensity,
            "dominant_emotion": dominant,
            "emotion_variability": variability
        }
    
    def identify_emotion_patterns(self) -> List[Dict[str, Any]]:
        """识别情感模式"""
        patterns = []
        
        if not self.emotion_timeline:
            return patterns
        
        # 模式1: 周期性情感
        emotion_sequence = [e.primary_emotion for e in self.emotion_timeline if e.primary_emotion]
        if len(emotion_sequence) > 5:
            # 简单的模式检测：连续出现的情感
            consecutive_count = 1
            for i in range(1, len(emotion_sequence)):
                if emotion_sequence[i] == emotion_sequence[i-1]:
                    consecutive_count += 1
                    if consecutive_count >= 3:
                        patterns.append({
                            "type": "consecutive",
                            "emotion": emotion_sequence[i],
                            "count": consecutive_count,
                            "description": f"连续{consecutive_count}次出现{emotion_sequence[i]}情感"
                        })
                        consecutive_count = 1
                else:
                    consecutive_count = 1
        
        # 模式2: 情感触发器
        if self.emotion_triggers:
            top_triggers = sorted(self.emotion_triggers.items(), key=lambda x: x[1], reverse=True)[:3]
            for trigger, count in top_triggers:
                patterns.append({
                    "type": "trigger",
                    "trigger": trigger,
                    "count": count,
                    "description": f"{trigger}触发了{count}次情感反应"
                })
        
        return patterns
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "user_id": self.user_id,
            "group_id": self.group_id,
            "emotion_timeline": [e.to_dict() for e in self.emotion_timeline],
            "emotion_triggers": self.emotion_triggers,
            "dominant_emotions": self.dominant_emotions,
            "last_updated": self.last_updated
        }
    
    def to_json(self) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EmotionProfile':
        """从字典创建"""
        timeline = [EmotionAnalysis.from_dict(e) for e in data.get("emotion_timeline", [])]
        return cls(
            user_id=data.get("user_id", ""),
            group_id=data.get("group_id", ""),
            emotion_timeline=timeline,
            emotion_triggers=data.get("emotion_triggers", {}),
            dominant_emotions=data.get("dominant_emotions", {}),
            last_updated=float(data.get("last_updated", time.time()))
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> Optional['EmotionProfile']:
        """从JSON字符串创建"""
        try:
            data = json.loads(json_str)
            return cls.from_dict(data)
        except Exception as e:
            logger.error(f"解析情感档案JSON失败: {e}")
            return None


class EmotionAnalyzer:
    """情感分析器"""
    
    # 基础情感映射
    BASIC_EMOTIONS = {
        "喜": ["高兴", "开心", "快乐", "愉快", "欢乐", "兴奋", "满足"],
        "怒": ["生气", "愤怒", "恼怒", "暴怒", "气愤", "不满"],
        "哀": ["悲伤", "难过", "伤心", "忧伤", "哀伤", "失落", "沮丧"],
        "乐": ["愉悦", "舒适", "惬意", "享受", "满意"],
        "惊": ["惊讶", "震惊", "吃惊", "意外", "惊奇"],
        "恐": ["害怕", "恐惧", "担心", "焦虑", "紧张", "不安"],
        "爱": ["喜爱", "爱慕", "喜欢", "钟爱", "爱护"],
        "恶": ["厌恶", "讨厌", "嫌恶", "反感", "排斥"]
    }
    
    def __init__(self):
        self.emotion_profiles: Dict[str, EmotionProfile] = {}
    
    def analyze_emotion_from_text(self, text: str, context: Optional[str] = None) -> EmotionAnalysis:
        """从文本中分析情感（规则基础方法）"""
        if not text:
            return EmotionAnalysis()
        
        detected_emotions = []
        emotion_scores = {}
        
        # 简单的关键词匹配
        for basic_emotion, keywords in self.BASIC_EMOTIONS.items():
            for keyword in keywords:
                if keyword in text:
                    detected_emotions.append(basic_emotion)
                    emotion_scores[basic_emotion] = emotion_scores.get(basic_emotion, 0) + 1
        
        if not detected_emotions:
            return EmotionAnalysis(primary_emotion="中性", confidence=0.5)
        
        # 找出最主要的情感
        primary = max(emotion_scores.items(), key=lambda x: x[1])[0]
        
        # 其他情感作为复合情感
        complex = [e for e in detected_emotions if e != primary]
        
        # 计算强度（基于出现次数）
        intensity = min(emotion_scores[primary] * 0.2, 1.0)
        
        return EmotionAnalysis(
            primary_emotion=primary,
            emotion_intensity=intensity,
            complex_emotions=list(set(complex)),
            emotion_source=context or "",
            confidence=0.6
        )
    
    def get_or_create_profile(self, user_id: str, group_id: str = "") -> EmotionProfile:
        """获取或创建用户情感档案"""
        key = f"{group_id}:{user_id}"
        if key not in self.emotion_profiles:
            self.emotion_profiles[key] = EmotionProfile(user_id=user_id, group_id=group_id)
        return self.emotion_profiles[key]
    
    def record_emotion(self, user_id: str, emotion: EmotionAnalysis, group_id: str = ""):
        """记录用户情感"""
        profile = self.get_or_create_profile(user_id, group_id)
        profile.add_emotion_record(emotion)
    
    def get_user_emotion_summary(self, user_id: str, group_id: str = "") -> Dict[str, Any]:
        """获取用户情感摘要"""
        profile = self.get_or_create_profile(user_id, group_id)
        trend = profile.get_emotion_trend()
        patterns = profile.identify_emotion_patterns()
        
        return {
            "user_id": user_id,
            "group_id": group_id,
            "emotion_trend": trend,
            "emotion_patterns": patterns,
            "top_triggers": sorted(
                profile.emotion_triggers.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5],
            "dominant_emotions": sorted(
                profile.dominant_emotions.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5],
            "recent_emotions": [e.to_dict() for e in profile.get_recent_emotions(5)]
        }
    
    def enhance_emotion_with_llm(self, text: str, context: Optional[str] = None) -> Dict[str, Any]:
        """使用LLM增强情感分析（返回提示词和预期格式）"""
        prompt = f"""请分析以下文本的情感信息，提供多维度的情感分析。

文本：{text}

{f'上下文：{context}' if context else ''}

请分析并返回以下信息：
1. 主要情感（从"喜、怒、哀、乐、惊、恐、爱、恶、中性"中选择）
2. 情感强度（0-1之间的数值，0表示无情感，1表示极强）
3. 情感持续时间（transient=瞬时、short-term=短期、long-term=长期）
4. 情感来源/触发器（是什么引发了这种情感）
5. 复合情感（如果存在多种情感，列出）
6. 置信度（0-1之间的数值）

返回JSON格式：
{{
  "primary_emotion": "喜",
  "emotion_intensity": 0.8,
  "emotion_duration": "short-term",
  "emotion_source": "完成了重要工作",
  "complex_emotions": ["满足", "兴奋"],
  "confidence": 0.9
}}
"""
        return {
            "prompt": prompt,
            "expected_format": "JSON with EmotionAnalysis fields"
        }
    
    def save_profiles_to_dict(self) -> Dict[str, Any]:
        """保存所有档案到字典"""
        return {
            key: profile.to_dict()
            for key, profile in self.emotion_profiles.items()
        }
    
    def load_profiles_from_dict(self, data: Dict[str, Any]):
        """从字典加载档案"""
        self.emotion_profiles = {
            key: EmotionProfile.from_dict(profile_data)
            for key, profile_data in data.items()
        }
