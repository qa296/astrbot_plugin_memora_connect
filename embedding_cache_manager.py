import asyncio
import json
import sqlite3
import time
import logging
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import numpy as np
from astrbot.api import logger

@dataclass
class EmbeddedMemory:
    """带有嵌入向量的记忆对象"""
    memory_id: str
    content: str
    embedding: List[float]
    concept_id: str
    created_at: float
    last_updated: float
    embedding_version: str = "v1.0"
    metadata: Dict[str, Any] = None

@dataclass
class PrecomputeTask:
    """预计算任务"""
    task_id: str
    memory_ids: List[str]
    priority: int  # 1-5, 5为最高优先级
    created_at: float
    status: str = "pending"  # pending, processing, completed, failed
    progress: int = 0  # 0-100
    error_message: str = ""

class EmbeddingCacheManager:
    """嵌入向量缓存管理器 - 负责预计算、存储和管理记忆的嵌入向量"""
    
    def __init__(self, memory_system, db_path: str):
        self.memory_system = memory_system
        self.db_path = db_path
        self.cache_db_path = db_path.replace(".db", "_embeddings.db")
        self.vector_dimension = None  # 将从第一个嵌入结果中推断
        self.precompute_queue = asyncio.Queue()
        self.is_precomputing = False
        self.precompute_stats = {
            "total_memories": 0,
            "cached_memories": 0,
            "pending_precompute": 0,
            "last_precompute_time": 0,
            "precompute_count": 0,
            "cache_hits": 0,
            "cache_misses": 0
        }
        self.batch_size = 10  # 批量处理大小
        self.max_queue_size = 1000  # 最大队列大小
        
    async def initialize(self):
        """初始化嵌入向量缓存系统"""
        try:
            await self._ensure_cache_database()
            await self._load_precompute_stats()
            logger.info("嵌入向量缓存管理器初始化完成")
        except Exception as e:
            logger.error(f"嵌入向量缓存管理器初始化失败: {e}")
            
    async def _ensure_cache_database(self):
        """确保缓存数据库和表结构存在"""
        try:
            with sqlite3.connect(self.cache_db_path) as conn:
                cursor = conn.cursor()
                
                # 创建嵌入向量表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS memory_embeddings (
                        memory_id TEXT PRIMARY KEY,
                        content TEXT NOT NULL,
                        concept_id TEXT NOT NULL,
                        embedding BLOB NOT NULL,
                        vector_dimension INTEGER NOT NULL,
                        created_at REAL NOT NULL,
                        last_updated REAL NOT NULL,
                        embedding_version TEXT DEFAULT 'v1.0',
                        metadata TEXT DEFAULT '{}'
                    )
                ''')
                
                # 创建预计算任务表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS precompute_tasks (
                        task_id TEXT PRIMARY KEY,
                        memory_ids TEXT NOT NULL,
                        priority INTEGER DEFAULT 1,
                        created_at REAL NOT NULL,
                        status TEXT DEFAULT 'pending',
                        progress INTEGER DEFAULT 0,
                        error_message TEXT DEFAULT '',
                        completed_at REAL DEFAULT 0
                    )
                ''')
                
                # 创建索引
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_concept_embeddings ON memory_embeddings(concept_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_updated_embeddings ON memory_embeddings(last_updated)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_status ON precompute_tasks(status, priority)')
                
                conn.commit()
                
        except Exception as e:
            logger.error(f"创建缓存数据库失败: {e}")
            raise
            
    async def _load_precompute_stats(self):
        """加载预计算统计信息"""
        try:
            with sqlite3.connect(self.cache_db_path) as conn:
                cursor = conn.cursor()
                
                # 统计缓存的记忆数量
                cursor.execute("SELECT COUNT(*) FROM memory_embeddings")
                cached_count = cursor.fetchone()[0]
                
                # 统计待计算的任务数量
                cursor.execute("SELECT COUNT(*) FROM precompute_tasks WHERE status = 'pending'")
                pending_count = cursor.fetchone()[0]
                
                self.precompute_stats["cached_memories"] = cached_count
                self.precompute_stats["pending_precompute"] = pending_count
                
        except Exception as e:
            logger.error(f"加载预计算统计信息失败: {e}")
            
    async def get_embedding(self, memory_id: str, content: str) -> Optional[List[float]]:
        """获取记忆的嵌入向量，优先从缓存读取"""
        try:
            # 首先尝试从缓存获取
            cached_embedding = await self._get_cached_embedding(memory_id)
            if cached_embedding:
                self.precompute_stats["cache_hits"] += 1
                return cached_embedding
                
            # 缓存未命中，实时计算
            self.precompute_stats["cache_misses"] += 1
            embedding = await self._compute_embedding_realtime(content)
            
            if embedding:
                # 异步缓存计算结果
                asyncio.create_task(self._cache_embedding(memory_id, content, embedding))
                
            return embedding
                
        except Exception as e:
            logger.error(f"获取嵌入向量失败: {e}")
            return None
            
    async def _get_cached_embedding(self, memory_id: str) -> Optional[List[float]]:
        """从缓存中获取嵌入向量"""
        try:
            with sqlite3.connect(self.cache_db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT embedding, vector_dimension, metadata 
                    FROM memory_embeddings 
                    WHERE memory_id = ?
                ''', (memory_id,))
                
                row = cursor.fetchone()
                if row:
                    embedding_blob, vector_dim, metadata_json = row
                    embedding = self._deserialize_embedding(embedding_blob, vector_dim)
                    
                    # 设置向量维度（仅在第一次时）
                    if self.vector_dimension is None:
                        self.vector_dimension = vector_dim
                        
                    return embedding
                    
        except Exception as e:
            logger.debug(f"从缓存获取嵌入向量失败: {e}")
            
        return None
        
    async def _compute_embedding_realtime(self, content: str) -> Optional[List[float]]:
        """实时计算嵌入向量"""
        try:
            embedding = await self.memory_system.get_embedding(content)
            if embedding:
                # 设置向量维度
                if self.vector_dimension is None:
                    self.vector_dimension = len(embedding)
                return embedding
        except Exception as e:
            logger.error(f"实时计算嵌入向量失败: {e}")
            
        return None
        
    async def _cache_embedding(self, memory_id: str, content: str, embedding: List[float]):
        """缓存嵌入向量"""
        try:
            if not embedding:
                return
                
            with sqlite3.connect(self.cache_db_path) as conn:
                cursor = conn.cursor()
                
                embedding_blob = self._serialize_embedding(embedding)
                current_time = time.time()
                
                cursor.execute('''
                    INSERT OR REPLACE INTO memory_embeddings 
                    (memory_id, content, concept_id, embedding, vector_dimension, created_at, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    memory_id,
                    content,
                    "",  # concept_id 将在后续更新
                    embedding_blob,
                    len(embedding),
                    current_time,
                    current_time
                ))
                
                conn.commit()
                
                # 更新统计信息
                self.precompute_stats["cached_memories"] += 1
                
        except Exception as e:
            logger.error(f"缓存嵌入向量失败: {e}")
            
    def _serialize_embedding(self, embedding: List[float]) -> bytes:
        """序列化嵌入向量"""
        try:
            # 使用 numpy 序列化为二进制格式
            embedding_array = np.array(embedding, dtype=np.float32)
            return embedding_array.tobytes()
        except Exception as e:
            logger.error(f"序列化嵌入向量失败: {e}")
            # 降级到 JSON 格式
            return json.dumps(embedding).encode('utf-8')
            
    def _deserialize_embedding(self, embedding_blob: bytes, vector_dim: int) -> List[float]:
        """反序列化嵌入向量"""
        try:
            # 首先尝试 numpy 格式
            embedding_array = np.frombuffer(embedding_blob, dtype=np.float32)
            if len(embedding_array) == vector_dim:
                return embedding_array.tolist()
        except Exception:
            pass
            
        try:
            # 降级到 JSON 格式
            embedding_json = embedding_blob.decode('utf-8')
            return json.loads(embedding_json)
        except Exception as e:
            logger.error(f"反序列化嵌入向量失败: {e}")
            return []
            
    async def schedule_precompute_task(self, memory_ids: List[str], priority: int = 1):
        """调度预计算任务"""
        try:
            if not memory_ids:
                return
                
            task_id = f"precompute_{int(time.time() * 1000)}_{len(memory_ids)}"
            
            # 过滤已经缓存的记忆
            uncached_memory_ids = []
            for memory_id in memory_ids:
                if not await self._get_cached_embedding(memory_id):
                    uncached_memory_ids.append(memory_id)
                    
            if not uncached_memory_ids:
                return
                
            # 如果队列已满，移除低优先级任务
            if self.precompute_queue.qsize() >= self.max_queue_size:
                await self._cleanup_low_priority_tasks()
                
            # 创建任务
            task = PrecomputeTask(
                task_id=task_id,
                memory_ids=uncached_memory_ids,
                priority=priority,
                created_at=time.time(),
                status="pending"
            )
            
            # 保存任务到数据库
            await self._save_precompute_task(task)
            
            # 添加到处理队列
            await self.precompute_queue.put(task)
            
            # 更新统计信息
            self.precompute_stats["pending_precompute"] += 1
            
            logger.debug(f"已调度预计算任务: {task_id}, 包含 {len(uncached_memory_ids)} 条记忆")
            
            # 如果没有预计算任务正在运行，启动预计算器
            if not self.is_precomputing:
                asyncio.create_task(self._precompute_worker())
                
        except Exception as e:
            logger.error(f"调度预计算任务失败: {e}")
            
    async def _save_precompute_task(self, task: PrecomputeTask):
        """保存预计算任务到数据库"""
        try:
            with sqlite3.connect(self.cache_db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT OR REPLACE INTO precompute_tasks 
                    (task_id, memory_ids, priority, created_at, status, progress, error_message)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    task.task_id,
                    json.dumps(task.memory_ids),
                    task.priority,
                    task.created_at,
                    task.status,
                    task.progress,
                    task.error_message
                ))
                
                conn.commit()
                
        except Exception as e:
            logger.error(f"保存预计算任务失败: {e}")
            
    async def _cleanup_low_priority_tasks(self):
        """清理低优先级任务"""
        try:
            # 从队列中移除一些低优先级任务
            temp_tasks = []
            removed_count = 0
            
            for _ in range(min(50, self.precompute_queue.qsize())):
                try:
                    task = self.precompute_queue.get_nowait()
                    if task.priority <= 2 and removed_count < 20:  # 移除最多20个低优先级任务
                        removed_count += 1
                        # 标记任务为失败
                        task.status = "failed"
                        task.error_message = "队列清理"
                        await self._save_precompute_task(task)
                    else:
                        temp_tasks.append(task)
                except asyncio.QueueEmpty:
                    break
                    
            # 将剩余任务重新放回队列
            for task in temp_tasks:
                await self.precompute_queue.put(task)
                
            if removed_count > 0:
                logger.debug(f"已清理 {removed_count} 个低优先级任务")
                
        except Exception as e:
            logger.error(f"清理低优先级任务失败: {e}")
            
    async def _precompute_worker(self):
        """预计算工作线程"""
        self.is_precomputing = True
        
        try:
            logger.info("嵌入向量预计算工作线程启动")
            
            while True:
                try:
                    # 从队列获取任务，设置超时以避免无限等待
                    task = await asyncio.wait_for(self.precompute_queue.get(), timeout=30.0)
                    
                    # 处理任务
                    await self._process_precompute_task(task)
                    
                    # 更新任务状态
                    task.status = "completed"
                    task.progress = 100
                    await self._save_precompute_task(task)
                    
                    # 更新统计信息
                    self.precompute_stats["pending_precompute"] -= 1
                    self.precompute_stats["precompute_count"] += 1
                    self.precompute_stats["last_precompute_time"] = time.time()
                    
                except asyncio.TimeoutError:
                    # 队列为空，等待一段时间后退出
                    if self.precompute_queue.empty():
                        break
                except Exception as e:
                    logger.error(f"处理预计算任务失败: {e}")
                    
        finally:
            self.is_precomputing = False
            
    async def _process_precompute_task(self, task: PrecomputeTask):
        """处理单个预计算任务"""
        try:
            task.status = "processing"
            await self._save_precompute_task(task)
            
            total_count = len(task.memory_ids)
            completed_count = 0
            
            logger.info(f"开始处理预计算任务: {task.task_id}, 共 {total_count} 条记忆")
            
            # 批量处理记忆
            for i in range(0, total_count, self.batch_size):
                batch_memory_ids = task.memory_ids[i:i + self.batch_size]
                
                # 获取记忆内容
                memories_data = await self._get_memories_data(batch_memory_ids)
                
                # 批量计算嵌入向量
                batch_results = await self._batch_compute_embeddings(memories_data)
                
                # 批量缓存结果
                await self._batch_cache_embeddings(batch_results)
                
                completed_count += len(batch_memory_ids)
                task.progress = int((completed_count / total_count) * 100)
                
                # 定期更新进度
                if completed_count % (self.batch_size * 5) == 0:
                    await self._save_precompute_task(task)
                    logger.debug(f"预计算任务 {task.task_id} 进度: {task.progress}%")
                    
                # 避免过于频繁的请求
                if i + self.batch_size < total_count:
                    await asyncio.sleep(0.1)
                    
            
        except Exception as e:
            logger.error(f"处理预计算任务失败: {task.task_id}, 错误: {e}")
            task.status = "failed"
            task.error_message = str(e)
            await self._save_precompute_task(task)
            raise
            
    async def _get_memories_data(self, memory_ids: List[str]) -> List[Dict[str, Any]]:
        """获取记忆数据"""
        memories_data = []
        
        for memory_id in memory_ids:
            memory = self.memory_system.memory_graph.memories.get(memory_id)
            if memory:
                memories_data.append({
                    "memory_id": memory_id,
                    "content": memory.content,
                    "concept_id": memory.concept_id
                })
                
        return memories_data
        
    async def _batch_compute_embeddings(self, memories_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """批量计算嵌入向量"""
        results = []
        
        for memory_data in memories_data:
            try:
                embedding = await self._compute_embedding_realtime(memory_data["content"])
                if embedding:
                    results.append({
                        "memory_id": memory_data["memory_id"],
                        "content": memory_data["content"],
                        "concept_id": memory_data["concept_id"],
                        "embedding": embedding
                    })
            except Exception as e:
                logger.warning(f"计算记忆 {memory_data['memory_id']} 的嵌入向量失败: {e}")
                
        return results
        
    async def _batch_cache_embeddings(self, batch_results: List[Dict[str, Any]]):
        """批量缓存嵌入向量"""
        try:
            with sqlite3.connect(self.cache_db_path) as conn:
                cursor = conn.cursor()
                
                current_time = time.time()
                
                for result in batch_results:
                    embedding_blob = self._serialize_embedding(result["embedding"])
                    
                    cursor.execute('''
                        INSERT OR REPLACE INTO memory_embeddings 
                        (memory_id, content, concept_id, embedding, vector_dimension, created_at, last_updated)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        result["memory_id"],
                        result["content"],
                        result["concept_id"],
                        embedding_blob,
                        len(result["embedding"]),
                        current_time,
                        current_time
                    ))
                    
                conn.commit()
                
        except Exception as e:
            logger.error(f"批量缓存嵌入向量失败: {e}")
            
    async def batch_retrieve_embeddings(self, memory_ids: List[str]) -> Dict[str, List[float]]:
        """批量检索嵌入向量"""
        embeddings = {}
        
        try:
            with sqlite3.connect(self.cache_db_path) as conn:
                cursor = conn.cursor()
                
                # 构建查询条件
                placeholders = ",".join(["?" for _ in memory_ids])
                cursor.execute(f'''
                    SELECT memory_id, embedding, vector_dimension 
                    FROM memory_embeddings 
                    WHERE memory_id IN ({placeholders})
                ''', memory_ids)
                
                for row in cursor.fetchall():
                    memory_id, embedding_blob, vector_dim = row
                    embedding = self._deserialize_embedding(embedding_blob, vector_dim)
                    if embedding:
                        embeddings[memory_id] = embedding
                        
        except Exception as e:
            logger.error(f"批量检索嵌入向量失败: {e}")
            
        return embeddings
        
    async def semantic_search(self, query_embedding: List[float], limit: int = 10, 
                           concept_filter: Optional[str] = None) -> List[Tuple[str, float]]:
        """基于嵌入向量的语义搜索"""
        try:
            if not query_embedding:
                return []
                
            with sqlite3.connect(self.cache_db_path) as conn:
                cursor = conn.cursor()
                
                # 构建查询条件
                if concept_filter:
                    cursor.execute('''
                        SELECT memory_id, embedding, vector_dimension 
                        FROM memory_embeddings 
                        WHERE concept_id = ?
                    ''', (concept_filter,))
                else:
                    cursor.execute('''
                        SELECT memory_id, embedding, vector_dimension 
                        FROM memory_embeddings
                    ''')
                    
                results = []
                
                for row in cursor.fetchall():
                    memory_id, embedding_blob, vector_dim = row
                    memory_embedding = self._deserialize_embedding(embedding_blob, vector_dim)
                    
                    if memory_embedding:
                        similarity = self._cosine_similarity(query_embedding, memory_embedding)
                        if similarity > 0.3:  # 相似度阈值
                            results.append((memory_id, similarity))
                            
                # 按相似度排序并返回前N个结果
                results.sort(key=lambda x: x[1], reverse=True)
                return results[:limit]
                
        except Exception as e:
            logger.error(f"语义搜索失败: {e}")
            return []
            
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """计算余弦相似度"""
        try:
            if len(vec1) != len(vec2) or len(vec1) == 0:
                return 0.0
                
            dot_product = sum(a * b for a, b in zip(vec1, vec2))
            magnitude1 = sum(a * a for a in vec1) ** 0.5
            magnitude2 = sum(b * b for b in vec2) ** 0.5
            
            if magnitude1 == 0 or magnitude2 == 0:
                return 0.0
                
            return dot_product / (magnitude1 * magnitude2)
            
        except Exception:
            return 0.0
            
    async def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        try:
            stats = self.precompute_stats.copy()
            
            with sqlite3.connect(self.cache_db_path) as conn:
                cursor = conn.cursor()
                
                # 获取缓存命中率
                total_requests = stats["cache_hits"] + stats["cache_misses"]
                hit_rate = stats["cache_hits"] / total_requests if total_requests > 0 else 0
                
                # 获取平均向量维度
                if self.vector_dimension:
                    stats["vector_dimension"] = self.vector_dimension
                
                stats["cache_hit_rate"] = hit_rate
                stats["total_requests"] = total_requests
                
                # 获取数据库大小
                cursor.execute("SELECT COUNT(*) FROM memory_embeddings WHERE embedding_version = 'v1.0'")
                current_version_count = cursor.fetchone()[0]
                stats["current_version_count"] = current_version_count
                
            return stats
            
        except Exception as e:
            logger.error(f"获取缓存统计信息失败: {e}")
            return self.precompute_stats
            
    async def schedule_initial_precompute(self):
        """调度初始预计算任务"""
        try:
            
            # 获取所有记忆ID
            all_memory_ids = list(self.memory_system.memory_graph.memories.keys())
            
            if not all_memory_ids:
                logger.info("没有记忆需要预计算")
                return
                
            # 分批处理，每批100个记忆
            batch_size = 100
            for i in range(0, len(all_memory_ids), batch_size):
                batch_memory_ids = all_memory_ids[i:i + batch_size]
                
                # 根据索引分配优先级
                priority = 5 if i == 0 else 3  # 第一批高优先级
                
                await self.schedule_precompute_task(batch_memory_ids, priority)
                
                # 避免过于频繁的调度
                if i + batch_size < len(all_memory_ids):
                    await asyncio.sleep(0.1)
                    
 
        except Exception as e:
            logger.error(f"调度初始预计算任务失败: {e}")
            
    async def cleanup_old_embeddings(self, days_old: int = 30):
        """清理旧的嵌入向量"""
        try:
            cutoff_time = time.time() - (days_old * 24 * 3600)
            
            with sqlite3.connect(self.cache_db_path) as conn:
                cursor = conn.cursor()
                
                # 删除旧的嵌入向量
                cursor.execute('''
                    DELETE FROM memory_embeddings 
                    WHERE last_updated < ?
                    AND embedding_version != 'v1.0'
                ''', (cutoff_time,))
                
                deleted_count = cursor.rowcount
                conn.commit()
                
                if deleted_count > 0:
                    logger.info(f"清理了 {deleted_count} 个旧的嵌入向量")
                    
        except Exception as e:
            logger.error(f"清理旧嵌入向量失败: {e}")