"""
记忆图数据结构
管理元素节点、记忆、元素-记忆关联和连接
"""

import asyncio
import time

try:
    from .models import Concept, Connection, Element, ElementMemory, Memory
except ImportError:
    from models import Concept, Connection, Element, ElementMemory, Memory


class MemoryGraph:
    """记忆图数据结构"""

    def __init__(self):
        self.elements: dict[str, Element] = {}
        self.memories: dict[str, Memory] = {}
        self.connections: list[Connection] = []
        self.element_memories: list[ElementMemory] = []
        self.adjacency_list: dict[str, list[tuple[str, float]]] = {}

        self.concepts: dict[str, Concept] = {}

    # ================================================================
    # Element 操作
    # ================================================================

    def add_element(
        self,
        name: str,
        category: str,
        group_id: str = "",
        element_id: str = None,
        created_at: float = None,
        last_accessed: float = None,
        access_count: int = 0,
    ) -> str:
        if element_id is None:
            element_id = f"elem_{int(time.time() * 1000)}"

        if element_id not in self.elements:
            element = Element(
                id=element_id,
                name=name,
                category=category,
                group_id=group_id,
                created_at=created_at,
                last_accessed=last_accessed,
                access_count=access_count,
            )
            self.elements[element_id] = element
            if element_id not in self.adjacency_list:
                self.adjacency_list[element_id] = []

        return element_id

    def get_or_create_element(
        self,
        name: str,
        category: str,
        group_id: str = "",
    ) -> str:
        for elem in self.elements.values():
            if elem.name == name and elem.category == category and elem.group_id == group_id:
                return elem.id
        return self.add_element(name, category, group_id)

    def find_element_by_name(self, name: str, group_id: str = "") -> Element | None:
        for elem in self.elements.values():
            if elem.name == name and elem.group_id == group_id:
                return elem
        return None

    def find_elements_by_category(self, category: str, group_id: str = "") -> list[Element]:
        results = []
        for elem in self.elements.values():
            if elem.category == category:
                if not group_id or elem.group_id == group_id:
                    results.append(elem)
        return results

    def get_all_element_names_by_category(self, group_id: str = "") -> dict[str, list[str]]:
        result: dict[str, list[str]] = {
            "person": [],
            "object": [],
            "place": [],
            "action": [],
            "trait": [],
        }
        for elem in self.elements.values():
            if not group_id or elem.group_id == group_id:
                cat = elem.category
                if cat in result and elem.name not in result[cat]:
                    result[cat].append(elem.name)
        return result

    def remove_element(self, element_id: str) -> bool:
        if element_id not in self.elements:
            return False

        to_remove = [
            c.id
            for c in self.connections
            if c.from_element == element_id or c.to_element == element_id
        ]
        for cid in to_remove:
            self.remove_connection(cid)

        self.element_memories = [
            em for em in self.element_memories if em.element_id != element_id
        ]

        if element_id in self.adjacency_list:
            del self.adjacency_list[element_id]
        del self.elements[element_id]
        return True

    def update_element(self, element_id: str, **fields) -> bool:
        elem = self.elements.get(element_id)
        if not elem:
            return False
        allowed = {"name", "category", "last_accessed", "access_count", "group_id"}
        for k, v in fields.items():
            if k in allowed and v is not None:
                setattr(elem, k, v)
        return True

    # ================================================================
    # ElementMemory 操作
    # ================================================================

    def link_memory(self, element_id: str, memory_id: str, role: str = ""):
        for em in self.element_memories:
            if em.element_id == element_id and em.memory_id == memory_id:
                if role:
                    em.role = role
                return
        self.element_memories.append(
            ElementMemory(element_id=element_id, memory_id=memory_id, role=role)
        )

    def unlink_memory(self, element_id: str, memory_id: str):
        self.element_memories = [
            em
            for em in self.element_memories
            if not (em.element_id == element_id and em.memory_id == memory_id)
        ]

    def unlink_all_for_memory(self, memory_id: str):
        self.element_memories = [
            em for em in self.element_memories if em.memory_id != memory_id
        ]

    def get_memory_elements(self, memory_id: str) -> list[tuple[Element, str]]:
        results = []
        for em in self.element_memories:
            if em.memory_id == memory_id:
                elem = self.elements.get(em.element_id)
                if elem:
                    results.append((elem, em.role))
        return results

    def get_element_memories(self, element_id: str) -> list[Memory]:
        memory_ids = [
            em.memory_id
            for em in self.element_memories
            if em.element_id == element_id
        ]
        results = []
        for mid in memory_ids:
            mem = self.memories.get(mid)
            if mem:
                results.append(mem)
        return results

    def get_element_memories_with_role(self, element_id: str, role: str) -> list[Memory]:
        memory_ids = [
            em.memory_id
            for em in self.element_memories
            if em.element_id == element_id and em.role == role
        ]
        results = []
        for mid in memory_ids:
            mem = self.memories.get(mid)
            if mem:
                results.append(mem)
        return results

    # ================================================================
    # 自动连接：同一条记忆关联的元素两两建 Connection
    # ================================================================

    def auto_connect_cooccurring_elements(self, memory_id: str):
        elements_data = self.get_memory_elements(memory_id)
        element_ids = [elem.id for elem, _ in elements_data]

        for i in range(len(element_ids)):
            for j in range(i + 1, len(element_ids)):
                self.add_connection(element_ids[i], element_ids[j])

    # ================================================================
    # Memory 操作
    # ================================================================

    def add_memory(
        self,
        content: str,
        memory_id: str = None,
        details: str = "",
        emotion: str = "",
        created_at: float = None,
        last_accessed: float = None,
        access_count: int = 0,
        strength: float = 1.0,
        allow_forget: bool = True,
        group_id: str = "",
        concept_id: str = "",
        participants: str = "",
        location: str = "",
        tags: str = "",
    ) -> str:
        if memory_id is None:
            memory_id = f"memory_{int(time.time() * 1000)}"

        memory = Memory(
            id=memory_id,
            content=content,
            details=details,
            emotion=emotion,
            created_at=created_at,
            last_accessed=last_accessed,
            access_count=access_count,
            strength=strength,
            allow_forget=allow_forget,
            group_id=group_id,
        )
        self.memories[memory_id] = memory

        if hasattr(self, "embedding_cache") and self.embedding_cache:
            asyncio.create_task(
                self.embedding_cache.schedule_precompute_task([memory_id], priority=3)
            )

        return memory_id

    def remove_memory(self, memory_id: str):
        if memory_id in self.memories:
            del self.memories[memory_id]
        self.unlink_all_for_memory(memory_id)

    def update_memory(self, memory_id: str, **fields) -> bool:
        mem = self.memories.get(memory_id)
        if not mem:
            return False
        allowed = {
            "content",
            "details",
            "emotion",
            "strength",
            "last_accessed",
            "created_at",
            "allow_forget",
        }
        for k, v in fields.items():
            if k in allowed and v is not None:
                setattr(mem, k, v)
        return True

    # ================================================================
    # Connection 操作
    # ================================================================

    def add_connection(
        self,
        from_element: str,
        to_element: str,
        strength: float = 1.0,
        connection_id: str = None,
        last_strengthened: float = None,
    ) -> str:
        if connection_id is None:
            connection_id = f"conn_{from_element}_{to_element}"

        for conn in self.connections:
            if (
                conn.from_element == from_element and conn.to_element == to_element
            ) or (conn.from_element == to_element and conn.to_element == from_element):
                conn.strength += 0.1
                conn.last_strengthened = time.time()
                self._sync_adjacency(conn)
                return conn.id

        connection = Connection(
            id=connection_id,
            from_element=from_element,
            to_element=to_element,
            strength=strength,
            last_strengthened=last_strengthened or time.time(),
        )
        self.connections.append(connection)

        if from_element not in self.adjacency_list:
            self.adjacency_list[from_element] = []
        if to_element not in self.adjacency_list:
            self.adjacency_list[to_element] = []

        self.adjacency_list[from_element].append((to_element, strength))
        self.adjacency_list[to_element].append((from_element, strength))

        return connection_id

    def remove_connection(self, connection_id: str):
        conn_to_remove = None
        for conn in self.connections:
            if conn.id == connection_id:
                conn_to_remove = conn
                break

        if conn_to_remove:
            self.connections = [c for c in self.connections if c.id != connection_id]

            if conn_to_remove.from_element in self.adjacency_list:
                self.adjacency_list[conn_to_remove.from_element] = [
                    (neighbor, s)
                    for neighbor, s in self.adjacency_list[conn_to_remove.from_element]
                    if neighbor != conn_to_remove.to_element
                ]

            if conn_to_remove.to_element in self.adjacency_list:
                self.adjacency_list[conn_to_remove.to_element] = [
                    (neighbor, s)
                    for neighbor, s in self.adjacency_list[conn_to_remove.to_element]
                    if neighbor != conn_to_remove.from_element
                ]

    def set_connection_strength(self, connection_id: str, strength: float) -> bool:
        target = None
        for conn in self.connections:
            if conn.id == connection_id:
                target = conn
                break
        if not target:
            return False
        target.strength = float(strength)
        self._sync_adjacency(target)
        return True

    def get_neighbors(self, element_id: str) -> list[tuple[str, float]]:
        return self.adjacency_list.get(element_id, [])

    def _sync_adjacency(self, conn: Connection):
        if conn.from_element in self.adjacency_list:
            self.adjacency_list[conn.from_element] = [
                (n, float(conn.strength) if n == conn.to_element else s)
                for (n, s) in self.adjacency_list[conn.from_element]
            ]
        if conn.to_element in self.adjacency_list:
            self.adjacency_list[conn.to_element] = [
                (n, float(conn.strength) if n == conn.from_element else s)
                for (n, s) in self.adjacency_list[conn.to_element]
            ]

    # ================================================================
    # Concept 兼容层（旧代码过渡用）
    # ================================================================

    def add_concept(
        self,
        name: str,
        concept_id: str = None,
        created_at: float = None,
        last_accessed: float = None,
        access_count: int = 0,
    ) -> str:
        if concept_id is None:
            concept_id = f"concept_{int(time.time() * 1000)}"

        if concept_id not in self.concepts:
            concept = Concept(
                id=concept_id,
                name=name,
                created_at=created_at,
                last_accessed=last_accessed,
                access_count=access_count,
            )
            self.concepts[concept_id] = concept
            if concept_id not in self.adjacency_list:
                self.adjacency_list[concept_id] = []

        return concept_id

    def remove_concept(self, concept_id: str) -> bool:
        if concept_id not in self.concepts:
            return False
        to_remove = [
            c.id
            for c in self.connections
            if c.from_element == concept_id or c.to_element == concept_id
        ]
        for cid in to_remove:
            self.remove_connection(cid)
        concept_mem_ids = []
        for em in self.element_memories:
            if em.element_id == concept_id:
                concept_mem_ids.append(em.memory_id)
        for mid in concept_mem_ids:
            self.remove_memory(mid)
        if concept_id in self.adjacency_list:
            del self.adjacency_list[concept_id]
        del self.concepts[concept_id]
        return True
