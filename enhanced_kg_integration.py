"""
知识图谱增强集成模块
将情感分析和关系类型集成到现有记忆系统中
"""

import json
import time
from typing import Dict, List, Optional, Any
from astrbot.api import logger
from .emotion_analyzer import EmotionAnalyzer, EmotionAnalysis
from .relationship_types import (
    RelationshipAnalyzer,
    ConceptAnalyzer,
    RelationshipMetadata,
    ConceptAttributes,
    RelationshipType
)


class EnhancedKGIntegration:
    """增强知识图谱集成器"""
    
    def __init__(self, memory_system):
        self.memory_system = memory_system
        self.emotion_analyzer = EmotionAnalyzer()
        self.relationship_analyzer = RelationshipAnalyzer()
        self.concept_analyzer = ConceptAnalyzer()
        
        # 缓存：存储概念和连接的扩展属性
        self.concept_attributes_cache: Dict[str, ConceptAttributes] = {}
        self.connection_metadata_cache: Dict[str, RelationshipMetadata] = {}
    
    def enhance_memory_with_emotion(
        self,
        content: str,
        emotion_str: str = "",
        context: str = ""
    ) -> Dict[str, Any]:
        """增强记忆的情感信息
        
        Args:
            content: 记忆内容
            emotion_str: 简单情感字符串（向后兼容）
            context: 上下文信息
        
        Returns:
            包含增强情感分析的字典
        """
        try:
            # 如果有简单情感字符串，先转换
            if emotion_str:
                emotion_analysis = EmotionAnalysis.from_simple_emotion(emotion_str)
            else:
                # 使用规则分析情感
                emotion_analysis = self.emotion_analyzer.analyze_emotion_from_text(content, context)
            
            return {
                "emotion_json": emotion_analysis.to_json(),
                "emotion_analysis": emotion_analysis
            }
        except Exception as e:
            logger.error(f"增强情感分析失败: {e}")
            return {
                "emotion_json": "",
                "emotion_analysis": EmotionAnalysis()
            }
    
    def enhance_connection_with_relationship(
        self,
        from_concept_name: str,
        to_concept_name: str,
        strength: float,
        context: str = ""
    ) -> RelationshipMetadata:
        """增强连接的关系类型信息
        
        Args:
            from_concept_name: 源概念名称
            to_concept_name: 目标概念名称
            strength: 连接强度
            context: 上下文信息
        
        Returns:
            关系元数据
        """
        try:
            # 推断关系类型
            relationship_type = self.relationship_analyzer.infer_relationship_type(
                from_concept_name,
                to_concept_name,
                context
            )
            
            # 创建关系元数据
            metadata = self.relationship_analyzer.create_relationship_metadata(
                relationship_type=relationship_type,
                strength=strength,
                description=self.relationship_analyzer.get_relationship_description(
                    relationship_type,
                    from_concept_name,
                    to_concept_name
                )
            )
            
            return metadata
        except Exception as e:
            logger.error(f"增强关系类型失败: {e}")
            return RelationshipMetadata()
    
    def enhance_concept_with_attributes(
        self,
        concept_id: str,
        concept_name: str,
        access_count: int = 0,
        connection_count: int = 0,
        memory_count: int = 0
    ) -> ConceptAttributes:
        """增强概念的属性信息
        
        Args:
            concept_id: 概念ID
            concept_name: 概念名称
            access_count: 访问次数
            connection_count: 连接数
            memory_count: 记忆数
        
        Returns:
            概念属性
        """
        try:
            # 计算重要性
            importance = self.concept_analyzer.calculate_importance(
                access_count,
                connection_count,
                memory_count
            )
            
            # 推断抽象度
            abstraction_level = self.concept_analyzer.infer_abstraction_level(concept_name)
            
            # 确定概念类型
            concept_type = "abstract" if abstraction_level > 0.6 else "concrete"
            
            # 创建概念属性
            attributes = self.concept_analyzer.create_concept_attributes(
                importance=importance,
                abstraction_level=abstraction_level,
                concept_type=concept_type
            )
            
            # 缓存属性
            self.concept_attributes_cache[concept_id] = attributes
            
            return attributes
        except Exception as e:
            logger.error(f"增强概念属性失败: {e}")
            return ConceptAttributes()
    
    def record_user_emotion(
        self,
        user_id: str,
        emotion_analysis: EmotionAnalysis,
        group_id: str = ""
    ):
        """记录用户情感
        
        Args:
            user_id: 用户ID
            emotion_analysis: 情感分析结果
            group_id: 群组ID
        """
        try:
            self.emotion_analyzer.record_emotion(user_id, emotion_analysis, group_id)
        except Exception as e:
            logger.error(f"记录用户情感失败: {e}")
    
    def get_user_emotion_summary(self, user_id: str, group_id: str = "") -> Dict[str, Any]:
        """获取用户情感摘要"""
        try:
            return self.emotion_analyzer.get_user_emotion_summary(user_id, group_id)
        except Exception as e:
            logger.error(f"获取用户情感摘要失败: {e}")
            return {}
    
    def get_concept_attributes(self, concept_id: str) -> Optional[ConceptAttributes]:
        """获取概念属性"""
        return self.concept_attributes_cache.get(concept_id)
    
    def get_connection_metadata(self, connection_id: str) -> Optional[RelationshipMetadata]:
        """获取连接元数据"""
        return self.connection_metadata_cache.get(connection_id)
    
    def save_enhanced_data(self) -> Dict[str, Any]:
        """保存增强数据到字典"""
        try:
            return {
                "emotion_profiles": self.emotion_analyzer.save_profiles_to_dict(),
                "concept_attributes": {
                    concept_id: attr.to_dict()
                    for concept_id, attr in self.concept_attributes_cache.items()
                },
                "connection_metadata": {
                    conn_id: meta.to_dict()
                    for conn_id, meta in self.connection_metadata_cache.items()
                }
            }
        except Exception as e:
            logger.error(f"保存增强数据失败: {e}")
            return {}
    
    def load_enhanced_data(self, data: Dict[str, Any]):
        """从字典加载增强数据"""
        try:
            # 加载情感档案
            if "emotion_profiles" in data:
                self.emotion_analyzer.load_profiles_from_dict(data["emotion_profiles"])
            
            # 加载概念属性
            if "concept_attributes" in data:
                for concept_id, attr_data in data["concept_attributes"].items():
                    self.concept_attributes_cache[concept_id] = ConceptAttributes.from_dict(attr_data)
            
            # 加载连接元数据
            if "connection_metadata" in data:
                for conn_id, meta_data in data["connection_metadata"].items():
                    self.connection_metadata_cache[conn_id] = RelationshipMetadata.from_dict(meta_data)
            
            logger.info("增强数据加载完成")
        except Exception as e:
            logger.error(f"加载增强数据失败: {e}")
    
    async def extract_emotion_with_llm(
        self,
        text: str,
        context: str = ""
    ) -> Optional[EmotionAnalysis]:
        """使用LLM提取情感（高级功能）
        
        Args:
            text: 文本内容
            context: 上下文
        
        Returns:
            情感分析结果
        """
        try:
            # 获取LLM提示词
            prompt_data = self.emotion_analyzer.enhance_emotion_with_llm(text, context)
            prompt = prompt_data["prompt"]
            
            # 调用LLM
            provider = await self.memory_system.get_llm_provider()
            if not provider:
                logger.warning("LLM提供商不可用，使用规则方法")
                return self.emotion_analyzer.analyze_emotion_from_text(text, context)
            
            response = await provider.text_chat(
                prompt=prompt,
                contexts=[],
                system_prompt="你是一个情感分析专家，请严格按照JSON格式返回分析结果。"
            )
            
            # 解析响应
            import re
            completion_text = response.completion_text.strip()
            json_match = re.search(r'\{.*\}', completion_text, re.DOTALL)
            
            if json_match:
                json_str = json_match.group(0)
                data = json.loads(json_str)
                return EmotionAnalysis.from_dict(data)
            else:
                logger.warning("LLM响应中未找到JSON格式，使用规则方法")
                return self.emotion_analyzer.analyze_emotion_from_text(text, context)
        
        except Exception as e:
            logger.error(f"使用LLM提取情感失败: {e}")
            return self.emotion_analyzer.analyze_emotion_from_text(text, context)
