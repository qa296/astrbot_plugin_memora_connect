"""
知识图谱关系类型分类与概念属性管理模块
支持因果、时间、层级、相似等多类型关系自动分类
管理概念的重要性和抽象度属性
"""
import asyncio
import time
import re
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
from astrbot.api import logger


class RelationType(Enum):
    """关系类型"""
    CAUSAL = "causal"          # 因果关系
    TEMPORAL = "temporal"      # 时间关系
    HIERARCHICAL = "hierarchical"  # 层级关系
    SIMILARITY = "similarity"  # 相似关系
    OPPOSITE = "opposite"      # 对立关系
    PART_WHOLE = "part_whole"  # 部分-整体关系
    ATTRIBUTE = "attribute"    # 属性关系
    ASSOCIATED = "associated"  # 关联关系（默认）


class RelationClassifier:
    """关系类型分类器"""
    
    def __init__(self):
        # 关系类型识别关键词
        self.relation_patterns = {
            RelationType.CAUSAL.value: {
                "keywords": ["因为", "所以", "导致", "引起", "造成", "由于", "使得", "导致了"],
                "pattern": r'(因为|由于).*(所以|导致|引起|造成)'
            },
            RelationType.TEMPORAL.value: {
                "keywords": ["之前", "之后", "然后", "接着", "随后", "先", "后", "同时"],
                "pattern": r'(之前|之后|然后|接着|随后|先.*后)'
            },
            RelationType.HIERARCHICAL.value: {
                "keywords": ["属于", "包含", "是一种", "是一个", "分为", "包括", "下属", "上级"],
                "pattern": r'(属于|包含|是一种|是一个|分为|包括)'
            },
            RelationType.SIMILARITY.value: {
                "keywords": ["类似", "相似", "像", "一样", "也是", "同样", "相同", "类似于"],
                "pattern": r'(类似|相似|像|一样|同样|相同)'
            },
            RelationType.OPPOSITE.value: {
                "keywords": ["相反", "对立", "相对", "而不是", "但是", "却", "不同于"],
                "pattern": r'(相反|对立|相对|而不是|不同于)'
            },
            RelationType.PART_WHOLE.value: {
                "keywords": ["的一部分", "组成", "构成", "包含", "含有"],
                "pattern": r'(的一部分|组成|构成|包含|含有)'
            },
            RelationType.ATTRIBUTE.value: {
                "keywords": ["的特征", "的属性", "的性质", "具有", "是", "的"],
                "pattern": r'(的特征|的属性|的性质|具有)'
            }
        }
    
    def classify_relation(self, concept_a: str, concept_b: str, context: str = "") -> str:
        """
        根据概念和上下文分类关系类型
        
        Args:
            concept_a: 概念A
            concept_b: 概念B
            context: 上下文文本
            
        Returns:
            关系类型字符串
        """
        # 如果没有上下文，返回默认关联关系
        if not context:
            return RelationType.ASSOCIATED.value
        
        # 检查各种关系类型模式
        scores = {}
        for relation_type, patterns in self.relation_patterns.items():
            score = 0
            
            # 关键词匹配
            for keyword in patterns["keywords"]:
                if keyword in context:
                    score += 1
            
            # 正则模式匹配
            if "pattern" in patterns:
                if re.search(patterns["pattern"], context):
                    score += 2
            
            if score > 0:
                scores[relation_type] = score
        
        # 返回得分最高的关系类型，如果没有匹配则返回关联关系
        if scores:
            return max(scores.items(), key=lambda x: x[1])[0]
        else:
            return RelationType.ASSOCIATED.value
    
    def get_relation_description(self, relation_type: str) -> str:
        """获取关系类型的中文描述"""
        descriptions = {
            RelationType.CAUSAL.value: "因果关系",
            RelationType.TEMPORAL.value: "时间关系",
            RelationType.HIERARCHICAL.value: "层级关系",
            RelationType.SIMILARITY.value: "相似关系",
            RelationType.OPPOSITE.value: "对立关系",
            RelationType.PART_WHOLE.value: "部分-整体关系",
            RelationType.ATTRIBUTE.value: "属性关系",
            RelationType.ASSOCIATED.value: "关联关系"
        }
        return descriptions.get(relation_type, "关联关系")


class ConceptAttributeManager:
    """概念属性管理器"""
    
    def __init__(self, memory_system):
        self.memory_system = memory_system
    
    def calculate_importance(self, concept_id: str) -> float:
        """
        计算概念的重要性
        基于：访问频率、连接数量、记忆数量
        
        Returns:
            重要性分数 (0-1)
        """
        try:
            memory_graph = self.memory_system.memory_graph
            
            if concept_id not in memory_graph.concepts:
                return 0.0
            
            concept = memory_graph.concepts[concept_id]
            
            # 1. 访问频率分数 (0-0.4)
            access_score = min(concept.access_count / 100.0, 0.4)
            
            # 2. 连接数量分数 (0-0.3)
            neighbors = memory_graph.get_neighbors(concept_id)
            connection_score = min(len(neighbors) / 20.0, 0.3)
            
            # 3. 记忆数量分数 (0-0.3)
            memory_count = sum(1 for m in memory_graph.memories.values() if m.concept_id == concept_id)
            memory_score = min(memory_count / 10.0, 0.3)
            
            # 总重要性
            importance = access_score + connection_score + memory_score
            
            return min(importance, 1.0)
            
        except Exception as e:
            logger.error(f"计算概念重要性失败: {e}", exc_info=True)
            return 0.0
    
    def calculate_abstractness(self, concept_name: str, concept_id: str) -> float:
        """
        计算概念的抽象度
        基于：概念名称长度、连接的子概念数量
        
        Returns:
            抽象度分数 (0-1)，越高越抽象
        """
        try:
            memory_graph = self.memory_system.memory_graph
            
            # 1. 基于概念名称的抽象度判断 (0-0.5)
            # 单字或双字的概念通常更抽象
            name_length = len(concept_name)
            if name_length <= 2:
                name_score = 0.5
            elif name_length <= 4:
                name_score = 0.3
            else:
                name_score = 0.1
            
            # 2. 基于下级概念数量的抽象度 (0-0.5)
            # 如果有很多子概念连接，说明更抽象
            if concept_id not in memory_graph.concepts:
                return name_score
            
            # 统计层级关系中作为父概念的次数
            parent_count = 0
            for conn in memory_graph.connections:
                # 检查是否有关系类型属性
                if hasattr(conn, 'relation_type') and conn.relation_type == RelationType.HIERARCHICAL.value:
                    if conn.from_concept == concept_id:
                        parent_count += 1
            
            hierarchy_score = min(parent_count / 10.0, 0.5)
            
            abstractness = name_score + hierarchy_score
            
            return min(abstractness, 1.0)
            
        except Exception as e:
            logger.error(f"计算概念抽象度失败: {e}", exc_info=True)
            return 0.0
    
    async def update_concept_attributes(self, concept_id: str):
        """更新概念的重要性和抽象度属性"""
        try:
            memory_graph = self.memory_system.memory_graph
            
            if concept_id not in memory_graph.concepts:
                return
            
            concept = memory_graph.concepts[concept_id]
            
            # 计算属性
            importance = self.calculate_importance(concept_id)
            abstractness = self.calculate_abstractness(concept.name, concept_id)
            
            # 更新概念属性
            if not hasattr(concept, 'importance'):
                concept.importance = importance
            else:
                concept.importance = importance
            
            if not hasattr(concept, 'abstractness'):
                concept.abstractness = abstractness
            else:
                concept.abstractness = abstractness
            
            # 保存到数据库
            await self._save_concept_attributes(concept_id, importance, abstractness)
            
            logger.debug(f"更新概念属性: {concept.name} - 重要性: {importance:.2f}, 抽象度: {abstractness:.2f}")
            
        except Exception as e:
            logger.error(f"更新概念属性失败: {e}", exc_info=True)
    
    async def _save_concept_attributes(self, concept_id: str, importance: float, abstractness: float):
        """保存概念属性到数据库"""
        try:
            conn = await self.memory_system._get_db_connection()
            cursor = conn.cursor()
            
            # 检查 concepts 表是否有 importance 和 abstractness 列
            cursor.execute("PRAGMA table_info(concepts)")
            columns = [col[1] for col in cursor.fetchall()]
            
            # 如果列不存在，添加列
            if "importance" not in columns:
                cursor.execute("ALTER TABLE concepts ADD COLUMN importance REAL DEFAULT 0.0")
            if "abstractness" not in columns:
                cursor.execute("ALTER TABLE concepts ADD COLUMN abstractness REAL DEFAULT 0.0")
            
            # 更新概念属性
            cursor.execute("""
                UPDATE concepts
                SET importance = ?, abstractness = ?
                WHERE id = ?
            """, (importance, abstractness, concept_id))
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"保存概念属性失败: {e}", exc_info=True)
    
    async def get_concept_attributes(self, concept_id: str) -> Dict[str, Any]:
        """获取概念的属性"""
        try:
            conn = await self.memory_system._get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT importance, abstractness
                FROM concepts
                WHERE id = ?
            """, (concept_id,))
            
            row = cursor.fetchone()
            
            if row:
                return {
                    "importance": row[0] if row[0] is not None else 0.0,
                    "abstractness": row[1] if row[1] is not None else 0.0
                }
            
            return {"importance": 0.0, "abstractness": 0.0}
            
        except Exception as e:
            logger.error(f"获取概念属性失败: {e}", exc_info=True)
            return {"importance": 0.0, "abstractness": 0.0}


class RelationExplorer:
    """关系探索器 - 用于探索概念网络"""
    
    def __init__(self, memory_system):
        self.memory_system = memory_system
        self.classifier = RelationClassifier()
        self.attribute_manager = ConceptAttributeManager(memory_system)
    
    async def explore_concept_network(self, concept_name: str, max_depth: int = 2) -> Dict[str, Any]:
        """
        探索概念网络
        
        Args:
            concept_name: 概念名称
            max_depth: 最大探索深度
            
        Returns:
            包含概念属性、连接关系等信息的字典
        """
        try:
            memory_graph = self.memory_system.memory_graph
            
            # 查找概念
            concept = None
            concept_id = None
            for cid, c in memory_graph.concepts.items():
                if c.name == concept_name:
                    concept = c
                    concept_id = cid
                    break
            
            if not concept:
                return {
                    "found": False,
                    "message": f"未找到概念: {concept_name}"
                }
            
            # 获取概念属性
            attributes = await self.attribute_manager.get_concept_attributes(concept_id)
            
            # 获取相关记忆数量
            memory_count = sum(1 for m in memory_graph.memories.values() if m.concept_id == concept_id)
            
            # 获取连接关系
            connections = []
            visited = set([concept_id])
            
            await self._explore_connections(concept_id, connections, visited, depth=0, max_depth=max_depth)
            
            # 按关系类型分组
            relations_by_type = {}
            for conn_info in connections:
                rel_type = conn_info["relation_type"]
                if rel_type not in relations_by_type:
                    relations_by_type[rel_type] = []
                relations_by_type[rel_type].append(conn_info)
            
            return {
                "found": True,
                "concept": {
                    "id": concept_id,
                    "name": concept.name,
                    "importance": attributes.get("importance", 0.0),
                    "abstractness": attributes.get("abstractness", 0.0),
                    "access_count": concept.access_count,
                    "memory_count": memory_count
                },
                "total_connections": len(connections),
                "relations_by_type": relations_by_type,
                "connections": connections
            }
            
        except Exception as e:
            logger.error(f"探索概念网络失败: {e}", exc_info=True)
            return {
                "found": False,
                "error": str(e)
            }
    
    async def _explore_connections(self, concept_id: str, connections: List[Dict], visited: set, depth: int, max_depth: int):
        """递归探索概念连接"""
        if depth >= max_depth:
            return
        
        memory_graph = self.memory_system.memory_graph
        neighbors = memory_graph.get_neighbors(concept_id)
        
        for neighbor_id, strength in neighbors:
            if neighbor_id in visited:
                continue
            
            visited.add(neighbor_id)
            
            # 获取连接信息
            neighbor_concept = memory_graph.concepts.get(neighbor_id)
            if not neighbor_concept:
                continue
            
            # 查找连接对象
            conn = None
            relation_type = RelationType.ASSOCIATED.value
            for c in memory_graph.connections:
                if (c.from_concept == concept_id and c.to_concept == neighbor_id) or \
                   (c.from_concept == neighbor_id and c.to_concept == concept_id):
                    conn = c
                    if hasattr(c, 'relation_type'):
                        relation_type = c.relation_type
                    break
            
            # 获取邻居属性
            neighbor_attrs = await self.attribute_manager.get_concept_attributes(neighbor_id)
            
            connections.append({
                "from_concept": memory_graph.concepts[concept_id].name,
                "to_concept": neighbor_concept.name,
                "relation_type": relation_type,
                "relation_desc": self.classifier.get_relation_description(relation_type),
                "strength": strength,
                "depth": depth + 1,
                "target_importance": neighbor_attrs.get("importance", 0.0),
                "target_abstractness": neighbor_attrs.get("abstractness", 0.0)
            })
            
            # 如果还没达到最大深度，继续探索
            if depth + 1 < max_depth:
                await self._explore_connections(neighbor_id, connections, visited, depth + 1, max_depth)
    
    def format_network_exploration(self, result: Dict[str, Any]) -> str:
        """格式化网络探索结果为可读文本"""
        if not result.get("found"):
            return result.get("message", "探索失败")
        
        lines = []
        
        # 概念基本信息
        concept = result["concept"]
        lines.append(f"🔍 概念网络探索: {concept['name']}")
        lines.append("")
        lines.append(f"📊 概念属性:")
        lines.append(f"   • 重要性: {'⭐' * int(concept['importance'] * 5)} {concept['importance']:.2f}")
        lines.append(f"   • 抽象度: {'🔼' * int(concept['abstractness'] * 5)} {concept['abstractness']:.2f}")
        lines.append(f"   • 访问次数: {concept['access_count']}")
        lines.append(f"   • 相关记忆: {concept['memory_count']} 条")
        lines.append("")
        
        # 关系统计
        lines.append(f"🌐 网络连接: 共 {result['total_connections']} 个连接")
        lines.append("")
        
        # 按关系类型展示
        relations_by_type = result.get("relations_by_type", {})
        if relations_by_type:
            lines.append("📋 关系分类:")
            for rel_type, conns in sorted(relations_by_type.items(), key=lambda x: len(x[1]), reverse=True):
                classifier = RelationClassifier()
                rel_desc = classifier.get_relation_description(rel_type)
                lines.append(f"   • {rel_desc} ({rel_type}): {len(conns)} 个")
            lines.append("")
        
        # 详细连接列表（展示前10个）
        connections = result.get("connections", [])
        if connections:
            lines.append("🔗 主要连接:")
            # 按强度排序
            sorted_conns = sorted(connections, key=lambda x: x["strength"], reverse=True)[:10]
            for i, conn in enumerate(sorted_conns, 1):
                strength_bar = "█" * int(conn["strength"] * 10)
                depth_indent = "  " * conn["depth"]
                lines.append(f"{depth_indent}{i}. {conn['from_concept']} → {conn['to_concept']}")
                lines.append(f"{depth_indent}   类型: {conn['relation_desc']}")
                lines.append(f"{depth_indent}   强度: {strength_bar} {conn['strength']:.2f}")
                if conn.get("target_importance", 0) > 0:
                    lines.append(f"{depth_indent}   目标重要性: {conn['target_importance']:.2f}")
        
        return "\n".join(lines)
