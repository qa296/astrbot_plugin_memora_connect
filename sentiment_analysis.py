"""
情感分析与情感档案管理模块
支持多维度情感模型，自动追踪用户情感类型、强度、趋势
"""
import asyncio
import time
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
from astrbot.api import logger


class EmotionType(Enum):
    """情感类型"""
    POSITIVE = "positive"      # 积极
    NEGATIVE = "negative"      # 消极
    NEUTRAL = "neutral"        # 中性
    MIXED = "mixed"            # 复杂/混合
    EXCITEMENT = "excitement"  # 兴奋
    JOY = "joy"               # 喜悦
    SADNESS = "sadness"       # 悲伤
    ANGER = "anger"           # 愤怒
    FEAR = "fear"             # 恐惧
    SURPRISE = "surprise"     # 惊讶
    DISGUST = "disgust"       # 厌恶
    TRUST = "trust"           # 信任
    ANTICIPATION = "anticipation"  # 期待


@dataclass
class EmotionRecord:
    """单次情感记录"""
    id: str
    user_id: str
    group_id: str
    emotion_type: str           # 情感类型
    intensity: float            # 情感强度 (0-1)
    message_content: str        # 触发消息内容
    context: str                # 上下文
    timestamp: float
    keywords: List[str] = field(default_factory=list)  # 情感关键词
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()


@dataclass
class EmotionProfile:
    """用户情感档案"""
    user_id: str
    group_id: str
    dominant_emotion: str                          # 主导情感类型
    emotion_counts: Dict[str, int]                 # 各类型情感计数
    emotion_intensities: Dict[str, List[float]]    # 各类型情感强度历史
    total_records: int                             # 总记录数
    last_updated: float
    first_record: float
    recent_trend: str                              # 最近趋势: "improving", "declining", "stable"
    triggers: Dict[str, int]                       # 情感触发器（关键词）
    
    def __post_init__(self):
        if not self.last_updated:
            self.last_updated = time.time()
        if not self.first_record:
            self.first_record = time.time()


class SentimentAnalyzer:
    """情感分析器"""
    
    def __init__(self, memory_system):
        self.memory_system = memory_system
        
        # 情感关键词字典
        self.emotion_keywords = {
            EmotionType.JOY.value: ["开心", "高兴", "快乐", "愉快", "喜悦", "哈哈", "😊", "😄", "😃", "🎉", "棒", "好", "赞"],
            EmotionType.SADNESS.value: ["难过", "伤心", "失望", "沮丧", "悲伤", "😢", "😭", "😔", "唉", "哎"],
            EmotionType.ANGER.value: ["生气", "愤怒", "恼火", "火大", "烦", "😡", "😠", "气", "讨厌"],
            EmotionType.FEAR.value: ["害怕", "恐惧", "担心", "焦虑", "紧张", "😨", "😰", "怕"],
            EmotionType.SURPRISE.value: ["惊讶", "吃惊", "震惊", "意外", "哇", "😲", "😮", "天啊"],
            EmotionType.EXCITEMENT.value: ["兴奋", "激动", "期待", "热情", "🔥", "太好了", "牛"],
            EmotionType.DISGUST.value: ["恶心", "讨厌", "反感", "厌恶", "🤮", "呕"],
            EmotionType.TRUST.value: ["信任", "相信", "可靠", "靠谱", "👍"],
            EmotionType.ANTICIPATION.value: ["期待", "希望", "盼望", "等待", "想要"],
        }
        
        # 情感强度修饰词
        self.intensity_modifiers = {
            "非常": 1.5, "特别": 1.5, "超级": 1.8, "太": 1.6, "极其": 1.7,
            "很": 1.3, "挺": 1.1, "有点": 0.7, "稍微": 0.6, "略": 0.5,
            "！": 1.2, "！！": 1.5, "！！！": 1.8
        }
        
    async def analyze_message(self, message: str, user_id: str, group_id: str, context: str = "") -> Optional[EmotionRecord]:
        """分析消息的情感"""
        try:
            # 检测情感类型和强度
            emotion_type, intensity, keywords = await self._detect_emotion(message)
            
            if emotion_type:
                record_id = f"emotion_{user_id}_{int(time.time() * 1000)}"
                record = EmotionRecord(
                    id=record_id,
                    user_id=user_id,
                    group_id=group_id,
                    emotion_type=emotion_type,
                    intensity=intensity,
                    message_content=message[:200],  # 限制长度
                    context=context[:200],
                    timestamp=time.time(),
                    keywords=keywords
                )
                return record
            
            return None
            
        except Exception as e:
            logger.error(f"情感分析失败: {e}", exc_info=True)
            return None
    
    async def _detect_emotion(self, message: str) -> Tuple[Optional[str], float, List[str]]:
        """检测情感类型、强度和关键词"""
        message_lower = message.lower()
        
        # 统计各类型情感的匹配
        emotion_scores = {}
        matched_keywords = {}
        
        for emotion_type, keywords in self.emotion_keywords.items():
            score = 0
            matched = []
            for keyword in keywords:
                if keyword in message:
                    score += 1
                    matched.append(keyword)
            
            if score > 0:
                emotion_scores[emotion_type] = score
                matched_keywords[emotion_type] = matched
        
        if not emotion_scores:
            return None, 0.0, []
        
        # 找到得分最高的情感类型
        dominant_emotion = max(emotion_scores.items(), key=lambda x: x[1])[0]
        
        # 计算基础强度
        base_intensity = min(emotion_scores[dominant_emotion] * 0.3, 0.8)
        
        # 根据修饰词调整强度
        intensity = self._adjust_intensity(message, base_intensity)
        
        return dominant_emotion, intensity, matched_keywords.get(dominant_emotion, [])
    
    def _adjust_intensity(self, message: str, base_intensity: float) -> float:
        """根据修饰词调整情感强度"""
        intensity = base_intensity
        
        for modifier, multiplier in self.intensity_modifiers.items():
            if modifier in message:
                intensity *= multiplier
        
        # 限制在 0-1 范围内
        return min(max(intensity, 0.0), 1.0)


class EmotionProfileManager:
    """情感档案管理器"""
    
    def __init__(self, memory_system):
        self.memory_system = memory_system
        self.analyzer = SentimentAnalyzer(memory_system)
        
    async def record_emotion(self, message: str, user_id: str, group_id: str, context: str = "") -> Optional[EmotionRecord]:
        """记录用户情感"""
        try:
            # 分析情感
            record = await self.analyzer.analyze_message(message, user_id, group_id, context)
            
            if record:
                # 保存到数据库
                await self._save_emotion_record(record)
                
                # 更新情感档案
                await self._update_emotion_profile(record)
                
                logger.debug(f"记录用户 {user_id} 情感: {record.emotion_type} (强度: {record.intensity:.2f})")
                
                return record
            
            return None
            
        except Exception as e:
            logger.error(f"记录情感失败: {e}", exc_info=True)
            return None
    
    async def _save_emotion_record(self, record: EmotionRecord):
        """保存情感记录到数据库"""
        try:
            conn = await self.memory_system._get_db_connection()
            cursor = conn.cursor()
            
            # 确保表存在
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS emotion_records (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    emotion_type TEXT NOT NULL,
                    intensity REAL NOT NULL,
                    message_content TEXT,
                    context TEXT,
                    keywords TEXT,
                    timestamp REAL NOT NULL
                )
            """)
            
            # 插入记录
            cursor.execute("""
                INSERT OR REPLACE INTO emotion_records
                (id, user_id, group_id, emotion_type, intensity, message_content, context, keywords, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.id,
                record.user_id,
                record.group_id,
                record.emotion_type,
                record.intensity,
                record.message_content,
                record.context,
                ",".join(record.keywords),
                record.timestamp
            ))
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"保存情感记录失败: {e}", exc_info=True)
    
    async def _update_emotion_profile(self, record: EmotionRecord):
        """更新用户情感档案"""
        try:
            conn = await self.memory_system._get_db_connection()
            cursor = conn.cursor()
            
            # 确保表存在
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS emotion_profiles (
                    user_id TEXT,
                    group_id TEXT,
                    dominant_emotion TEXT,
                    emotion_counts TEXT,
                    emotion_intensities TEXT,
                    total_records INTEGER,
                    last_updated REAL,
                    first_record REAL,
                    recent_trend TEXT,
                    triggers TEXT,
                    PRIMARY KEY (user_id, group_id)
                )
            """)
            
            # 获取现有档案
            cursor.execute("""
                SELECT emotion_counts, emotion_intensities, total_records, first_record, triggers
                FROM emotion_profiles
                WHERE user_id = ? AND group_id = ?
            """, (record.user_id, record.group_id))
            
            row = cursor.fetchone()
            
            if row:
                # 更新现有档案
                import json
                emotion_counts = json.loads(row[0])
                emotion_intensities = json.loads(row[1])
                total_records = row[2]
                first_record = row[3]
                triggers = json.loads(row[4])
            else:
                # 创建新档案
                emotion_counts = {}
                emotion_intensities = {}
                total_records = 0
                first_record = record.timestamp
                triggers = {}
            
            # 更新计数和强度
            emotion_counts[record.emotion_type] = emotion_counts.get(record.emotion_type, 0) + 1
            
            if record.emotion_type not in emotion_intensities:
                emotion_intensities[record.emotion_type] = []
            emotion_intensities[record.emotion_type].append(record.intensity)
            
            # 只保留最近100条记录
            if len(emotion_intensities[record.emotion_type]) > 100:
                emotion_intensities[record.emotion_type] = emotion_intensities[record.emotion_type][-100:]
            
            total_records += 1
            
            # 更新触发器
            for keyword in record.keywords:
                triggers[keyword] = triggers.get(keyword, 0) + 1
            
            # 计算主导情感
            dominant_emotion = max(emotion_counts.items(), key=lambda x: x[1])[0] if emotion_counts else "neutral"
            
            # 计算趋势
            recent_trend = self._calculate_trend(emotion_intensities, record.emotion_type)
            
            # 保存档案
            import json
            cursor.execute("""
                INSERT OR REPLACE INTO emotion_profiles
                (user_id, group_id, dominant_emotion, emotion_counts, emotion_intensities,
                 total_records, last_updated, first_record, recent_trend, triggers)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.user_id,
                record.group_id,
                dominant_emotion,
                json.dumps(emotion_counts, ensure_ascii=False),
                json.dumps(emotion_intensities, ensure_ascii=False),
                total_records,
                record.timestamp,
                first_record,
                recent_trend,
                json.dumps(triggers, ensure_ascii=False)
            ))
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"更新情感档案失败: {e}", exc_info=True)
    
    def _calculate_trend(self, emotion_intensities: Dict[str, List[float]], emotion_type: str) -> str:
        """计算情感趋势"""
        if emotion_type not in emotion_intensities:
            return "stable"
        
        intensities = emotion_intensities[emotion_type]
        if len(intensities) < 5:
            return "stable"
        
        # 比较最近5条和之前5条的平均值
        recent = intensities[-5:]
        previous = intensities[-10:-5] if len(intensities) >= 10 else intensities[:5]
        
        recent_avg = sum(recent) / len(recent)
        previous_avg = sum(previous) / len(previous)
        
        diff = recent_avg - previous_avg
        
        if diff > 0.1:
            return "intensifying"  # 增强
        elif diff < -0.1:
            return "declining"     # 减弱
        else:
            return "stable"        # 稳定
    
    async def get_emotion_profile(self, user_id: str, group_id: str) -> Optional[EmotionProfile]:
        """获取用户情感档案"""
        try:
            conn = await self.memory_system._get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT dominant_emotion, emotion_counts, emotion_intensities,
                       total_records, last_updated, first_record, recent_trend, triggers
                FROM emotion_profiles
                WHERE user_id = ? AND group_id = ?
            """, (user_id, group_id))
            
            row = cursor.fetchone()
            
            if row:
                import json
                profile = EmotionProfile(
                    user_id=user_id,
                    group_id=group_id,
                    dominant_emotion=row[0],
                    emotion_counts=json.loads(row[1]),
                    emotion_intensities=json.loads(row[2]),
                    total_records=row[3],
                    last_updated=row[4],
                    first_record=row[5],
                    recent_trend=row[6],
                    triggers=json.loads(row[7])
                )
                return profile
            
            return None
            
        except Exception as e:
            logger.error(f"获取情感档案失败: {e}", exc_info=True)
            return None
    
    async def get_recent_emotion_records(self, user_id: str, group_id: str, limit: int = 10) -> List[EmotionRecord]:
        """获取用户最近的情感记录"""
        try:
            conn = await self.memory_system._get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, user_id, group_id, emotion_type, intensity,
                       message_content, context, keywords, timestamp
                FROM emotion_records
                WHERE user_id = ? AND group_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (user_id, group_id, limit))
            
            records = []
            for row in cursor.fetchall():
                record = EmotionRecord(
                    id=row[0],
                    user_id=row[1],
                    group_id=row[2],
                    emotion_type=row[3],
                    intensity=row[4],
                    message_content=row[5],
                    context=row[6],
                    keywords=row[7].split(",") if row[7] else [],
                    timestamp=row[8]
                )
                records.append(record)
            
            return records
            
        except Exception as e:
            logger.error(f"获取情感记录失败: {e}", exc_info=True)
            return []
    
    def format_emotion_profile(self, profile: EmotionProfile, recent_records: List[EmotionRecord]) -> str:
        """格式化情感档案为可读文本"""
        lines = []
        
        # 基本信息
        days_active = (profile.last_updated - profile.first_record) / 86400
        lines.append(f"📊 情感档案")
        lines.append(f"   用户: {profile.user_id}")
        lines.append(f"   总记录数: {profile.total_records}")
        lines.append(f"   活跃天数: {days_active:.1f} 天")
        lines.append("")
        
        # 主导情感
        emotion_emoji = {
            "joy": "😊", "sadness": "😢", "anger": "😠", "fear": "😨",
            "surprise": "😲", "excitement": "🎉", "disgust": "🤮",
            "trust": "👍", "anticipation": "⏳", "positive": "✨",
            "negative": "😔", "neutral": "😐", "mixed": "🎭"
        }
        emoji = emotion_emoji.get(profile.dominant_emotion, "")
        lines.append(f"🎯 主导情感: {emoji} {profile.dominant_emotion}")
        lines.append("")
        
        # 情感分布
        lines.append("📈 情感分布:")
        total = sum(profile.emotion_counts.values())
        for emotion, count in sorted(profile.emotion_counts.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / total * 100) if total > 0 else 0
            emoji = emotion_emoji.get(emotion, "")
            lines.append(f"   {emoji} {emotion}: {count} 次 ({percentage:.1f}%)")
        lines.append("")
        
        # 情感趋势
        trend_emoji = {
            "intensifying": "📈",
            "declining": "📉",
            "stable": "➡️"
        }
        trend_text = {
            "intensifying": "增强",
            "declining": "减弱",
            "stable": "稳定"
        }
        lines.append(f"{trend_emoji.get(profile.recent_trend, '➡️')} 最近趋势: {trend_text.get(profile.recent_trend, '稳定')}")
        lines.append("")
        
        # 情感触发器
        if profile.triggers:
            lines.append("🔥 情感触发器（Top 5）:")
            top_triggers = sorted(profile.triggers.items(), key=lambda x: x[1], reverse=True)[:5]
            for keyword, count in top_triggers:
                lines.append(f"   • {keyword}: {count} 次")
            lines.append("")
        
        # 最近记录
        if recent_records:
            lines.append("📝 最近记录:")
            for i, record in enumerate(recent_records[:5], 1):
                dt = datetime.fromtimestamp(record.timestamp)
                time_str = dt.strftime('%m-%d %H:%M')
                emoji = emotion_emoji.get(record.emotion_type, "")
                intensity_bar = "█" * int(record.intensity * 10)
                lines.append(f"   {i}. [{time_str}] {emoji} {record.emotion_type}")
                lines.append(f"      强度: {intensity_bar} {record.intensity:.2f}")
                if record.message_content:
                    content = record.message_content[:50] + "..." if len(record.message_content) > 50 else record.message_content
                    lines.append(f"      内容: {content}")
        
        return "\n".join(lines)
