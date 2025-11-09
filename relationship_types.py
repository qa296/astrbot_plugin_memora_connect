"""
关系类型模块
定义和管理知识图谱中的不同关系类型
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from enum import Enum
import json
from astrbot.api import logger


class RelationshipType(Enum):
    """关系类型枚举"""
    CAUSAL = "causal"  # 因果关系
    TEMPORAL = "temporal"  # 时间关系
    HIERARCHICAL = "hierarchical"  # 层级关系
    SIMILARITY = "similarity"  # 相似关系
    OPPOSITION = "opposition"  # 对立关系
    ASSOCIATIVE = "associative"  # 联想关系（默认）
    PART_WHOLE = "part_whole"  # 部分-整体关系
    ATTRIBUTE = "attribute"  # 属性关系


class DirectionalityType(Enum):
    """方向性类型"""
    UNIDIRECTIONAL = "unidirectional"  # 单向
    BIDIRECTIONAL = "bidirectional"  # 双向


class StrengthLevel(Enum):
    """强度等级"""
    STRONG = "strong"  # 强关联 (0.7-1.0)
    MEDIUM = "medium"  # 中关联 (0.4-0.7)
    WEAK = "weak"  # 弱关联 (0.1-0.4)


@dataclass
class ConceptAttributes:
    """概念属性扩展"""
    importance: float = 0.5  # 重要性 (0-1)
    abstraction_level: float = 0.5  # 抽象度 (0=具体, 1=抽象)
    usage_frequency: float = 0.0  # 使用频率
    category: str = ""  # 类别
    concept_type: str = "concrete"  # 概念类型 (abstract, concrete)
    tags: List[str] = field(default_factory=list)  # 标签
    metadata: Dict[str, Any] = field(default_factory=dict)  # 元数据
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)
    
    def to_json(self) -> str:
        """转换为JSON"""
        return json.dumps(self.to_dict(), ensure_ascii=False)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConceptAttributes':
        """从字典创建"""
        return cls(
            importance=float(data.get("importance", 0.5)),
            abstraction_level=float(data.get("abstraction_level", 0.5)),
            usage_frequency=float(data.get("usage_frequency", 0.0)),
            category=data.get("category", ""),
            concept_type=data.get("concept_type", "concrete"),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {})
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> Optional['ConceptAttributes']:
        """从JSON创建"""
        try:
            data = json.loads(json_str)
            return cls.from_dict(data)
        except Exception as e:
            logger.error(f"解析概念属性JSON失败: {e}")
            return None


@dataclass
class RelationshipMetadata:
    """关系元数据"""
    relationship_type: str = "associative"  # 关系类型
    directionality: str = "bidirectional"  # 方向性
    strength_level: str = "medium"  # 强度等级
    confidence: float = 0.7  # 置信度
    description: str = ""  # 关系描述
    evidence: List[str] = field(default_factory=list)  # 证据（记忆ID）
    created_by: str = "system"  # 创建者（system, user, llm）
    metadata: Dict[str, Any] = field(default_factory=dict)  # 额外元数据
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)
    
    def to_json(self) -> str:
        """转换为JSON"""
        return json.dumps(self.to_dict(), ensure_ascii=False)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RelationshipMetadata':
        """从字典创建"""
        return cls(
            relationship_type=data.get("relationship_type", "associative"),
            directionality=data.get("directionality", "bidirectional"),
            strength_level=data.get("strength_level", "medium"),
            confidence=float(data.get("confidence", 0.7)),
            description=data.get("description", ""),
            evidence=data.get("evidence", []),
            created_by=data.get("created_by", "system"),
            metadata=data.get("metadata", {})
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> Optional['RelationshipMetadata']:
        """从JSON创建"""
        try:
            data = json.loads(json_str)
            return cls.from_dict(data)
        except Exception as e:
            logger.error(f"解析关系元数据JSON失败: {e}")
            return None


class RelationshipAnalyzer:
    """关系分析器"""
    
    def __init__(self):
        pass
    
    @staticmethod
    def classify_strength(strength: float) -> str:
        """根据强度值分类强度等级"""
        if strength >= 0.7:
            return StrengthLevel.STRONG.value
        elif strength >= 0.4:
            return StrengthLevel.MEDIUM.value
        else:
            return StrengthLevel.WEAK.value
    
    @staticmethod
    def infer_relationship_type(concept1_name: str, concept2_name: str, context: str = "") -> str:
        """推断关系类型（简单规则）"""
        # 简单的关键词匹配来推断关系类型
        context_lower = context.lower()
        name1_lower = concept1_name.lower()
        name2_lower = concept2_name.lower()
        
        # 因果关系
        if any(keyword in context_lower for keyword in ["因为", "所以", "导致", "引起", "造成"]):
            return RelationshipType.CAUSAL.value
        
        # 时间关系
        if any(keyword in context_lower for keyword in ["之前", "之后", "然后", "接着", "先", "后"]):
            return RelationshipType.TEMPORAL.value
        
        # 层级关系
        if any(keyword in context_lower for keyword in ["属于", "包含", "是一种", "的一部分"]):
            return RelationshipType.HIERARCHICAL.value
        
        # 相似关系
        if any(keyword in context_lower for keyword in ["类似", "相似", "像", "一样", "也是"]):
            return RelationshipType.SIMILARITY.value
        
        # 对立关系
        if any(keyword in context_lower for keyword in ["相反", "对立", "但是", "然而", "不同于"]):
            return RelationshipType.OPPOSITION.value
        
        # 部分-整体
        if any(keyword in context_lower for keyword in ["的部分", "组成", "包括"]):
            return RelationshipType.PART_WHOLE.value
        
        # 属性关系
        if any(keyword in context_lower for keyword in ["特点", "特征", "属性", "是", "具有"]):
            return RelationshipType.ATTRIBUTE.value
        
        # 默认为联想关系
        return RelationshipType.ASSOCIATIVE.value
    
    @staticmethod
    def create_relationship_metadata(
        relationship_type: str = "associative",
        strength: float = 0.5,
        directionality: str = "bidirectional",
        description: str = "",
        confidence: float = 0.7
    ) -> RelationshipMetadata:
        """创建关系元数据"""
        strength_level = RelationshipAnalyzer.classify_strength(strength)
        
        return RelationshipMetadata(
            relationship_type=relationship_type,
            directionality=directionality,
            strength_level=strength_level,
            confidence=confidence,
            description=description
        )
    
    @staticmethod
    def get_relationship_description(relationship_type: str, concept1: str, concept2: str) -> str:
        """获取关系的描述性文本"""
        descriptions = {
            "causal": f"{concept1} 导致/影响 {concept2}",
            "temporal": f"{concept1} 在时间上关联 {concept2}",
            "hierarchical": f"{concept1} 和 {concept2} 存在层级关系",
            "similarity": f"{concept1} 与 {concept2} 相似",
            "opposition": f"{concept1} 与 {concept2} 对立",
            "associative": f"{concept1} 和 {concept2} 相关联",
            "part_whole": f"{concept1} 是 {concept2} 的一部分",
            "attribute": f"{concept1} 是 {concept2} 的属性"
        }
        return descriptions.get(relationship_type, f"{concept1} 关联 {concept2}")
    
    @staticmethod
    def suggest_exploration_paths(
        relationship_type: str,
        current_concept: str
    ) -> List[str]:
        """根据关系类型建议探索路径"""
        suggestions = {
            "causal": [
                f"探索 {current_concept} 的原因",
                f"探索 {current_concept} 的结果",
                "寻找因果链"
            ],
            "temporal": [
                f"查看 {current_concept} 之前发生的事",
                f"查看 {current_concept} 之后发生的事",
                "构建时间线"
            ],
            "hierarchical": [
                f"查看 {current_concept} 的上级概念",
                f"查看 {current_concept} 的下级概念",
                "探索概念树"
            ],
            "similarity": [
                f"寻找与 {current_concept} 相似的概念",
                "发现概念聚类",
                "探索相似模式"
            ],
            "opposition": [
                f"查看与 {current_concept} 对立的概念",
                "分析对比关系",
                "探索矛盾点"
            ],
            "associative": [
                f"探索 {current_concept} 的关联概念",
                "发现潜在联系",
                "扩散式探索"
            ]
        }
        return suggestions.get(relationship_type, [f"探索 {current_concept} 的相关概念"])


class ConceptAnalyzer:
    """概念分析器"""
    
    @staticmethod
    def infer_abstraction_level(concept_name: str, examples: List[str] = None) -> float:
        """推断概念的抽象程度"""
        # 简单规则：长度越短，越可能是抽象概念
        base_score = max(0.0, min(1.0, 1.0 - len(concept_name) / 20.0))
        
        # 如果有具体实例，降低抽象度
        if examples and len(examples) > 0:
            base_score *= 0.7
        
        # 抽象概念关键词
        abstract_keywords = ["概念", "理论", "思想", "主义", "观念", "原则", "精神"]
        if any(keyword in concept_name for keyword in abstract_keywords):
            base_score += 0.2
        
        # 具体概念关键词
        concrete_keywords = ["物品", "东西", "事物", "人", "地方", "时间"]
        if any(keyword in concept_name for keyword in concrete_keywords):
            base_score -= 0.2
        
        return max(0.0, min(1.0, base_score))
    
    @staticmethod
    def calculate_importance(
        access_count: int,
        connection_count: int,
        memory_count: int,
        recency: float = 1.0
    ) -> float:
        """计算概念重要性"""
        # 综合访问次数、连接数、记忆数和时效性
        access_score = min(access_count / 10.0, 1.0) * 0.3
        connection_score = min(connection_count / 5.0, 1.0) * 0.3
        memory_score = min(memory_count / 10.0, 1.0) * 0.3
        recency_score = recency * 0.1
        
        return min(access_score + connection_score + memory_score + recency_score, 1.0)
    
    @staticmethod
    def create_concept_attributes(
        importance: float = 0.5,
        abstraction_level: float = 0.5,
        category: str = "",
        concept_type: str = "concrete"
    ) -> ConceptAttributes:
        """创建概念属性"""
        return ConceptAttributes(
            importance=importance,
            abstraction_level=abstraction_level,
            category=category,
            concept_type=concept_type
        )
