"""
记忆图数据结构
管理概念节点、记忆和连接
"""
import time
import asyncio
from typing import Dict, List, Tuple
try:
    from .models import Concept, Memory, Connection
except ImportError:
    from models import Concept, Memory, Connection


class MemoryGraph:
    """记忆图数据结构"""
    
    def __init__(self):
        self.concepts: Dict[str, Concept] = {}
        self.memories: Dict[str, Memory] = {}
        self.connections: List[Connection] = []
        self.adjacency_list: Dict[str, List[Tuple[str, float]]] = {}  # 邻接表优化
        self._concept_counter = 0
        self._memory_counter = 0
        
    def add_concept(self, name: str, concept_id: str = None, created_at: float = None,
                   last_accessed: float = None, access_count: int = 0) -> str:
        """添加概念节点"""
        if concept_id is None:
            self._concept_counter += 1
            concept_id = f"concept_{int(time.time() * 1000)}_{self._concept_counter}"
        
        if concept_id not in self.concepts:
            concept = Concept(
                id=concept_id,
                name=name,
                created_at=created_at,
                last_accessed=last_accessed,
                access_count=access_count
            )
            self.concepts[concept_id] = concept
            if concept_id not in self.adjacency_list:
                self.adjacency_list[concept_id] = []
        
        return concept_id
    
    def add_memory(self, content: str, concept_id: str, memory_id: str = None,
                   details: str = "", participants: str = "", location: str = "",
                   emotion: str = "", tags: str = "", created_at: float = None,
                   last_accessed: float = None, access_count: int = 0,
                   strength: float = 1.0, group_id: str = "") -> str:
        """添加记忆"""
        if memory_id is None:
            self._memory_counter += 1
            memory_id = f"memory_{int(time.time() * 1000)}_{self._memory_counter}"
        
        memory = Memory(
            id=memory_id,
            concept_id=concept_id,
            content=content,
            details=details,
            participants=participants,
            location=location,
            emotion=emotion,
            tags=tags,
            created_at=created_at,
            last_accessed=last_accessed,
            access_count=access_count,
            strength=strength,
            group_id=group_id
        )
        self.memories[memory_id] = memory
        
        # 如果启用了嵌入向量缓存，调度预计算任务
        if hasattr(self, 'embedding_cache') and self.embedding_cache:
            asyncio.create_task(self.embedding_cache.schedule_precompute_task([memory_id], priority=3))
        
        return memory_id
    
    def add_connection(self, from_concept: str, to_concept: str,
                      strength: float = 1.0, connection_id: str = None,
                      last_strengthened: float = None) -> str:
        """添加连接"""
        if connection_id is None:
            connection_id = f"conn_{from_concept}_{to_concept}"
        
        # 检查是否已存在
        for conn in self.connections:
            if (conn.from_concept == from_concept and conn.to_concept == to_concept) or \
               (conn.from_concept == to_concept and conn.to_concept == from_concept):
                conn.strength += 0.1
                conn.last_strengthened = time.time()
                return conn.id
        
        connection = Connection(
            id=connection_id,
            from_concept=from_concept,
            to_concept=to_concept,
            strength=strength,
            last_strengthened=last_strengthened or time.time()
        )
        self.connections.append(connection)
        
        # 更新邻接表
        if from_concept not in self.adjacency_list:
            self.adjacency_list[from_concept] = []
        if to_concept not in self.adjacency_list:
            self.adjacency_list[to_concept] = []
        
        # 添加双向连接
        self.adjacency_list[from_concept].append((to_concept, strength))
        self.adjacency_list[to_concept].append((from_concept, strength))
        
        return connection_id
    
    def remove_connection(self, connection_id: str):
        """移除连接"""
        # 找到要移除的连接
        conn_to_remove = None
        for conn in self.connections:
            if conn.id == connection_id:
                conn_to_remove = conn
                break
        
        if conn_to_remove:
            # 从连接列表中移除
            self.connections = [c for c in self.connections if c.id != connection_id]
            
            # 更新邻接表
            if conn_to_remove.from_concept in self.adjacency_list:
                self.adjacency_list[conn_to_remove.from_concept] = [
                    (neighbor, strength) for neighbor, strength in self.adjacency_list[conn_to_remove.from_concept]
                    if neighbor != conn_to_remove.to_concept
                ]
            
            if conn_to_remove.to_concept in self.adjacency_list:
                self.adjacency_list[conn_to_remove.to_concept] = [
                    (neighbor, strength) for neighbor, strength in self.adjacency_list[conn_to_remove.to_concept]
                    if neighbor != conn_to_remove.from_concept
                ]
    
    def remove_memory(self, memory_id: str):
        """移除记忆"""
        if memory_id in self.memories:
            del self.memories[memory_id]

    def update_memory(self, memory_id: str, **fields) -> bool:
        """更新记忆字段。支持: content, details, participants, location, emotion, tags, strength, concept_id, last_accessed, created_at
        返回是否更新成功"""
        mem = self.memories.get(memory_id)
        if not mem:
            return False
        allowed = {
            "content",
            "details",
            "participants",
            "location",
            "emotion",
            "tags",
            "strength",
            "concept_id",
            "last_accessed",
            "created_at",
        }
        for k, v in fields.items():
            if k in allowed and v is not None:
                setattr(mem, k, v)
        return True

    def set_connection_strength(self, connection_id: str, strength: float) -> bool:
        """设置连接强度并同步更新邻接表"""
        target = None
        for conn in self.connections:
            if conn.id == connection_id:
                target = conn
                break
        if not target:
            return False
        # 更新连接对象
        target.strength = float(strength)
        # 更新邻接表中两端的权重
        if target.from_concept in self.adjacency_list:
            self.adjacency_list[target.from_concept] = [
                (n, float(strength) if n == target.to_concept else s)
                for (n, s) in self.adjacency_list[target.from_concept]
            ]
        if target.to_concept in self.adjacency_list:
            self.adjacency_list[target.to_concept] = [
                (n, float(strength) if n == target.from_concept else s)
                for (n, s) in self.adjacency_list[target.to_concept]
            ]
        return True

    def remove_concept(self, concept_id: str) -> bool:
        """删除概念及其相关记忆与连接，并更新邻接表"""
        if concept_id not in self.concepts:
            return False
        # 移除相关连接
        to_remove = [c.id for c in self.connections if c.from_concept == concept_id or c.to_concept == concept_id]
        for cid in to_remove:
            self.remove_connection(cid)
        # 移除相关记忆
        mem_ids = [m.id for m in self.memories.values() if m.concept_id == concept_id]
        for mid in mem_ids:
            self.remove_memory(mid)
        # 移除概念和邻接表
        if concept_id in self.adjacency_list:
            del self.adjacency_list[concept_id]
        del self.concepts[concept_id]
        return True
    
    def get_neighbors(self, concept_id: str) -> List[Tuple[str, float]]:
        """获取概念节点的邻居及其连接强度"""
        return self.adjacency_list.get(concept_id, [])
