import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, cast

# 尝试导入 numpy，如果失败则使用 None 标记
try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    np = None
    HAS_NUMPY = False

# 尝试导入 astrbot.api.logger，如果失败则使用标准 logging
try:
    from astrbot.api import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

from .database import SmartDatabaseMigration
from .resources import resource_manager


@dataclass
class EmbeddedMemory:
    """带有嵌入向量的记忆对象"""

    memory_id: str
    content: str
    embedding: list[float]
    concept_id: str
    created_at: float
    last_updated: float
    embedding_version: str = "v1.0"
    metadata: dict[str, Any] | None = field(default_factory=dict)


@dataclass
class PrecomputeTask:
    """预计算任务"""

    task_id: str
    memory_ids: list[str]
    priority: int  # 1-5, 5为最高优先级
    created_at: float
    status: str = "pending"  # pending, processing, completed, failed
    progress: int = 0  # 0-100
    error_message: str = ""


class EmbeddingCacheManager:
    """嵌入向量缓存管理器 - 负责预计算、存储和管理记忆的嵌入向量"""

    def __init__(self, memory_system: Any, db_path: str):
        self.memory_system: Any = memory_system
        self.db_path: str = db_path
        self.cache_db_path: str = db_path.replace(".db", "_embeddings.db")
        self.vector_dimension: int | None = None  # 将从第一个嵌入结果中推断
        self.precompute_queue: asyncio.Queue[PrecomputeTask] = asyncio.Queue(
            maxsize=1000
        )  # 限制队列大小，防止内存溢出
        self.is_precomputing: bool = False
        self.precompute_stats: dict[str, int | float] = {
            "total_memories": 0,
            "cached_memories": 0,
            "pending_precompute": 0,
            "last_precompute_time": 0.0,
            "precompute_count": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "cache_hit_rate": 0.0,
        }
        self.batch_size: int = 10  # 批量处理大小
        self.max_queue_size: int = 1000  # 最大队列大小

        # 生命周期管理 - 新增
        self._worker_task: asyncio.Task[None] | None = None
        self._should_stop_worker: asyncio.Event = asyncio.Event()
        self._should_stop_worker.clear()  # 初始不停止

    async def initialize(self):
        """初始化嵌入向量缓存系统"""
        try:
            # 在初始化缓存数据库之前，先执行数据库迁移
            await self._run_database_migration()

            await self._ensure_cache_database()
            await self._load_precompute_stats()
            logger.info("嵌入向量缓存管理器初始化完成")
        except Exception as e:
            logger.error(f"嵌入向量缓存管理器初始化失败: {e}")

    async def _ensure_cache_database(self):
        """确保缓存数据库和表结构存在"""
        try:
            # 使用连接池获取数据库连接
            conn = resource_manager.get_db_connection(self.cache_db_path)
            cursor = conn.cursor()

            # 创建嵌入向量表（支持群聊隔离）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memory_embeddings (
                    memory_id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    concept_id TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    vector_dimension INTEGER NOT NULL,
                    group_id TEXT DEFAULT '',
                    created_at REAL NOT NULL,
                    last_updated REAL NOT NULL,
                    embedding_version TEXT DEFAULT 'v1.0',
                    metadata TEXT DEFAULT '{}'
                )
            """)

            # 创建预计算任务表
            cursor.execute("""
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
            """)

            # 创建索引（支持群聊隔离）
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_concept_embeddings ON memory_embeddings(concept_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_group_embeddings ON memory_embeddings(group_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_concept_group_embeddings ON memory_embeddings(concept_id, group_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_updated_embeddings ON memory_embeddings(last_updated)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_task_status ON precompute_tasks(status, priority)"
            )

            conn.commit()

            # 释放连接回连接池
            resource_manager.release_db_connection(self.cache_db_path, conn)

        except Exception as e:
            logger.error(f"创建缓存数据库失败: {e}")
            raise

    async def _run_database_migration(self):
        """运行嵌入向量缓存数据库的迁移"""
        try:
            logger.info(f"开始嵌入向量缓存数据库迁移: {self.cache_db_path}")

            # 创建数据库迁移实例
            migration = SmartDatabaseMigration(self.cache_db_path)

            # 执行嵌入向量缓存数据库迁移
            success = await migration.run_embedding_cache_migration()

            if success:
                logger.info("嵌入向量缓存数据库迁移成功完成")
            else:
                logger.error("嵌入向量缓存数据库迁移失败")
                raise RuntimeError("嵌入向量缓存数据库迁移失败")

        except Exception as e:
            logger.error(f"运行数据库迁移时发生错误: {e}")
            raise

    async def _load_precompute_stats(self):
        """加载预计算统计信息"""
        try:
            # 使用连接池获取数据库连接
            conn = resource_manager.get_db_connection(self.cache_db_path)
            cursor = conn.cursor()

            # 统计缓存的记忆数量
            cursor.execute("SELECT COUNT(*) FROM memory_embeddings")
            cached_count = cursor.fetchone()[0]

            # 统计待计算的任务数量
            cursor.execute(
                "SELECT COUNT(*) FROM precompute_tasks WHERE status = 'pending'"
            )
            pending_count = cursor.fetchone()[0]

            self.precompute_stats["cached_memories"] = cached_count
            self.precompute_stats["pending_precompute"] = pending_count

            # 释放连接回连接池
            resource_manager.release_db_connection(self.cache_db_path, conn)

        except Exception as e:
            logger.error(f"加载预计算统计信息失败: {e}")

    async def get_embedding(
        self, memory_id: str, content: str, group_id: str = ""
    ) -> list[float] | None:
        """获取记忆的嵌入向量，优先从缓存读取（支持群聊隔离）"""
        try:
            # 首先尝试从缓存获取（传递群聊ID）
            cached_embedding = await self._get_cached_embedding(memory_id, group_id)
            if cached_embedding:
                self.precompute_stats["cache_hits"] += 1
                return cached_embedding

            # 缓存未命中，实时计算
            self.precompute_stats["cache_misses"] += 1
            embedding = await self._compute_embedding_realtime(content)

            if embedding:
                # 异步缓存计算结果（包含群聊ID）
                asyncio.create_task(
                    self._cache_embedding(memory_id, content, embedding, group_id)
                )

            return embedding

        except Exception as e:
            logger.error(f"获取嵌入向量失败: {e}")
            return None

    async def _get_cached_embedding(
        self, memory_id: str, group_id: str = ""
    ) -> list[float] | None:
        """从缓存中获取嵌入向量（支持群聊隔离）"""
        try:
            # 使用连接池获取数据库连接
            conn = resource_manager.get_db_connection(self.cache_db_path)
            cursor = conn.cursor()

            # 构建查询条件（支持群聊隔离）
            if group_id:
                cursor.execute(
                    """
                    SELECT embedding, vector_dimension, metadata
                    FROM memory_embeddings
                    WHERE memory_id = ? AND group_id = ?
                """,
                    (memory_id, group_id),
                )
            else:
                cursor.execute(
                    """
                    SELECT embedding, vector_dimension, metadata
                    FROM memory_embeddings
                    WHERE memory_id = ?
                """,
                    (memory_id,),
                )

            row = cursor.fetchone()
            if row:
                embedding_blob, vector_dim, _metadata_json = row
                embedding = self._deserialize_embedding(embedding_blob, vector_dim)

                # 设置向量维度（仅在第一次时）
                if self.vector_dimension is None:
                    self.vector_dimension = vector_dim

                # 释放连接回连接池
                resource_manager.release_db_connection(self.cache_db_path, conn)
                return embedding

            # 释放连接回连接池
            resource_manager.release_db_connection(self.cache_db_path, conn)

        except Exception as e:
            logger.debug(f"从缓存获取嵌入向量失败: {e}")

        return None

    async def _compute_embedding_realtime(self, content: str) -> list[float] | None:
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

    async def _cache_embedding(
        self, memory_id: str, content: str, embedding: list[float], group_id: str = ""
    ):
        """缓存嵌入向量（支持群聊隔离）"""
        try:
            if not embedding:
                return

            # 使用连接池获取数据库连接
            conn = resource_manager.get_db_connection(self.cache_db_path)
            cursor = conn.cursor()

            embedding_blob = self._serialize_embedding(embedding)
            current_time = time.time()

            cursor.execute(
                """
                INSERT OR REPLACE INTO memory_embeddings
                (memory_id, content, concept_id, embedding, vector_dimension, group_id, created_at, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    memory_id,
                    content,
                    "",  # concept_id 将在后续更新
                    embedding_blob,
                    len(embedding),
                    group_id,
                    current_time,
                    current_time,
                ),
            )

            conn.commit()

            # 释放连接回连接池
            resource_manager.release_db_connection(self.cache_db_path, conn)

            # 更新统计信息
            self.precompute_stats["cached_memories"] += 1

        except Exception as e:
            logger.error(f"缓存嵌入向量失败: {e}")

    def _serialize_embedding(self, embedding: list[float]) -> bytes:
        """序列化嵌入向量"""
        try:
            if HAS_NUMPY and np:
                # 使用 numpy 序列化为二进制格式
                embedding_array = np.array(embedding, dtype=np.float32)
                return embedding_array.tobytes()
            else:
                # 降级到 JSON 格式
                return json.dumps(embedding).encode("utf-8")
        except Exception as e:
            logger.error(f"序列化嵌入向量失败: {e}")
            # 降级到 JSON 格式
            return json.dumps(embedding).encode("utf-8")

    def _deserialize_embedding(
        self, embedding_blob: bytes, vector_dim: int
    ) -> list[float] | None:
        """反序列化嵌入向量"""
        try:
            # 首先尝试 numpy 格式
            if isinstance(embedding_blob, str):
                # 如果意外传入字符串，尝试转换为字节
                try:
                    embedding_blob = embedding_blob.encode("utf-8")
                except UnicodeEncodeError as e:
                    logger.debug(f"字符串编码失败: {e}")
                    return None

            # 检查是否为有效的二进制数据
            if not isinstance(embedding_blob, (bytes, bytearray)):
                logger.debug(f"不支持的嵌入向量数据类型: {type(embedding_blob)}")
                return None

            if HAS_NUMPY and np:
                try:
                    embedding_array = np.frombuffer(embedding_blob, dtype=np.float32)
                    if len(embedding_array) == vector_dim:
                        return embedding_array.tolist()
                except (ValueError, TypeError, BufferError) as e:
                    logger.debug(f"numpy反序列化失败: {e}")
                    pass

        except Exception as e:
            logger.debug(f"numpy格式处理失败: {e}")

        try:
            # 降级到 JSON 格式
            if isinstance(embedding_blob, bytes):
                try:
                    embedding_json = embedding_blob.decode("utf-8")
                except UnicodeDecodeError as e:
                    logger.debug(f"UTF-8解码失败: {e}")
                    # 尝试其他编码
                    try:
                        embedding_json = embedding_blob.decode("latin-1")
                    except UnicodeDecodeError:
                        logger.debug("所有编码尝试都失败")
                        return None
            else:
                embedding_json = str(embedding_blob)

            try:
                result = json.loads(embedding_json)
                if isinstance(result, list) and len(result) == vector_dim:
                    return cast(list[float], result)
                else:
                    logger.debug(
                        f"反序列化的嵌入向量格式不正确: {type(result)}, 长度: {len(result) if isinstance(result, list) else 'N/A'}"
                    )
                    return None
            except json.JSONDecodeError as e:
                logger.debug(f"JSON解析失败: {e}")
                return None

        except Exception as e:
            logger.error(f"反序列化嵌入向量失败: {e}")
            return None

    async def schedule_precompute_task(
        self, memory_ids: list[str], priority: int = 1, group_id: str = ""
    ):
        """调度预计算任务（支持群聊隔离）"""
        try:
            if not memory_ids:
                return

            task_id = f"precompute_{int(time.time() * 1000)}_{len(memory_ids)}"

            # 过滤已经缓存的记忆（传递群聊ID）
            uncached_memory_ids: list[str] = []
            for memory_id in memory_ids:
                if not await self._get_cached_embedding(memory_id, group_id):
                    uncached_memory_ids.append(memory_id)

            if not uncached_memory_ids:
                return

            # 如果队列已满，移除低优先级任务
            if self.precompute_queue.full():
                await self._cleanup_low_priority_tasks()

            # 创建任务（存储群聊ID）
            task = PrecomputeTask(
                task_id=task_id,
                memory_ids=uncached_memory_ids,
                priority=priority,
                created_at=time.time(),
                status="pending",
            )
            # 将群聊ID存储在任务的error_message字段中（临时方案）
            task.error_message = f"group_id:{group_id}"

            # 保存任务到数据库
            await self._save_precompute_task(task)

            # 添加到处理队列，使用非阻塞方式避免死锁
            try:
                self.precompute_queue.put_nowait(task)
            except asyncio.QueueFull:
                logger.warning("预计算队列已满，丢弃任务")
                return

            # 更新统计信息
            self.precompute_stats["pending_precompute"] += 1

            logger.debug(
                f"已调度预计算任务: {task_id}, 包含 {len(uncached_memory_ids)} 条记忆"
            )

            # 如果没有预计算任务正在运行，启动预计算器
            if not self.is_precomputing:
                self._worker_task = cast(
                    asyncio.Task[None],
                    resource_manager.create_task(self._precompute_worker()),
                )

        except Exception as e:
            logger.error(f"调度预计算任务失败: {e}")

    async def _save_precompute_task(self, task: PrecomputeTask):
        """保存预计算任务到数据库"""
        try:
            # 使用连接池获取数据库连接
            conn = resource_manager.get_db_connection(self.cache_db_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT OR REPLACE INTO precompute_tasks
                (task_id, memory_ids, priority, created_at, status, progress, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    task.task_id,
                    json.dumps(task.memory_ids),
                    task.priority,
                    task.created_at,
                    task.status,
                    task.progress,
                    task.error_message,
                ),
            )

            conn.commit()

            # 释放连接回连接池
            resource_manager.release_db_connection(self.cache_db_path, conn)

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
                    if (
                        task.priority <= 2 and removed_count < 20
                    ):  # 移除最多20个低优先级任务
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
        """预计算工作线程 - 支持优雅退出"""
        self.is_precomputing = True

        try:
            logger.info("嵌入向量预计算工作线程启动")

            # 工作循环，支持优雅退出
            while not self._should_stop_worker.is_set():
                try:
                    # 使用较短的等待时间，以便及时响应停止信号
                    try:
                        task = await asyncio.wait_for(
                            self.precompute_queue.get(), timeout=5.0
                        )
                    except asyncio.TimeoutError:
                        # 队列为空，检查是否需要退出
                        if self._should_stop_worker.is_set():
                            break
                        continue

                    # 处理任务
                    try:
                        await self._process_precompute_task(task)

                        # 更新任务状态
                        task.status = "completed"
                        task.progress = 100
                        await self._save_precompute_task(task)

                        # 更新统计信息
                        self.precompute_stats["pending_precompute"] -= 1
                        self.precompute_stats["precompute_count"] += 1
                        self.precompute_stats["last_precompute_time"] = time.time()

                    except Exception as e:
                        logger.error(f"处理预计算任务失败: {e}")
                        # 标记任务为失败
                        task.status = "failed"
                        task.error_message = str(e)
                        await self._save_precompute_task(task)

                    # 检查停止信号后再处理下一个任务
                    if self._should_stop_worker.is_set():
                        break

                except asyncio.CancelledError:
                    # 任务被取消，正常退出
                    logger.info("预计算工作线程被取消，准备退出")
                    break
                except Exception as e:
                    logger.error(f"预计算工作线程发生异常: {e}")
                    # 短暂等待后继续
                    try:
                        await asyncio.sleep(1)
                        if self._should_stop_worker.is_set():
                            break
                    except asyncio.CancelledError:
                        break

        finally:
            self.is_precomputing = False
            logger.info("嵌入向量预计算工作线程已停止")

    async def _process_precompute_task(self, task: PrecomputeTask):
        """处理单个预计算任务"""
        try:
            task.status = "processing"
            await self._save_precompute_task(task)

            total_count = len(task.memory_ids)
            completed_count = 0

            # 批量处理记忆
            for i in range(0, total_count, self.batch_size):
                batch_memory_ids = task.memory_ids[i : i + self.batch_size]

                # 获取记忆内容
                memories_data = await self._get_memories_data(batch_memory_ids)

                # 批量计算嵌入向量
                batch_results = await self._batch_compute_embeddings(memories_data)

                # 批量缓存结果（传递群聊ID）
                # 从任务中提取群聊ID
                group_id = ""
                if task.error_message and task.error_message.startswith("group_id:"):
                    group_id = task.error_message.replace("group_id:", "")

                await self._batch_cache_embeddings(batch_results, group_id)

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

    async def _get_memories_data(self, memory_ids: list[str]) -> list[dict[str, Any]]:
        """获取记忆数据"""
        memories_data: list[dict[str, Any]] = []

        for memory_id in memory_ids:
            memory = self.memory_system.memory_graph.memories.get(memory_id)
            if memory:
                memories_data.append(
                    {
                        "memory_id": memory_id,
                        "content": memory.content,
                        "concept_id": memory.concept_id,
                        "group_id": getattr(memory, "group_id", ""),  # 确保传递group_id
                    }
                )

        return memories_data

    async def _batch_compute_embeddings(
        self, memories_data: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """批量计算嵌入向量"""
        results: list[dict[str, Any]] = []

        for memory_data in memories_data:
            try:
                embedding = await self._compute_embedding_realtime(
                    memory_data["content"]
                )
                if embedding:
                    results.append(
                        {
                            "memory_id": memory_data["memory_id"],
                            "content": memory_data["content"],
                            "concept_id": memory_data["concept_id"],
                            "embedding": embedding,
                        }
                    )
            except Exception as e:
                logger.warning(
                    f"计算记忆 {memory_data['memory_id']} 的嵌入向量失败: {e}"
                )

        return results

    async def _batch_cache_embeddings(
        self, batch_results: list[dict[str, Any]], group_id: str = ""
    ):
        """批量缓存嵌入向量（支持群聊隔离）"""
        try:
            # 使用连接池获取数据库连接
            conn = resource_manager.get_db_connection(self.cache_db_path)
            cursor = conn.cursor()

            current_time = time.time()

            for result in batch_results:
                embedding_blob = self._serialize_embedding(result["embedding"])

                cursor.execute(
                    """
                    INSERT OR REPLACE INTO memory_embeddings
                    (memory_id, content, concept_id, embedding, vector_dimension, group_id, created_at, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        result["memory_id"],
                        result["content"],
                        result["concept_id"],
                        embedding_blob,
                        len(result["embedding"]),
                        group_id,
                        current_time,
                        current_time,
                    ),
                )

            conn.commit()

            # 释放连接回连接池
            resource_manager.release_db_connection(self.cache_db_path, conn)

        except Exception as e:
            logger.error(f"批量缓存嵌入向量失败: {e}")

    async def batch_retrieve_embeddings(
        self, memory_ids: list[str], group_id: str = ""
    ) -> dict[str, list[float]]:
        """批量检索嵌入向量（支持群聊隔离）"""
        embeddings: dict[str, list[float]] = {}

        try:
            # 使用连接池获取数据库连接
            conn = resource_manager.get_db_connection(self.cache_db_path)
            cursor = conn.cursor()

            # 构建查询条件（支持群聊隔离）
            placeholders = ",".join(["?" for _ in memory_ids])
            if group_id:
                cursor.execute(
                    f"""
                    SELECT memory_id, embedding, vector_dimension
                    FROM memory_embeddings
                    WHERE memory_id IN ({placeholders}) AND group_id = ?
                """,
                    memory_ids + [group_id],
                )
            else:
                cursor.execute(
                    f"""
                    SELECT memory_id, embedding, vector_dimension
                    FROM memory_embeddings
                    WHERE memory_id IN ({placeholders})
                """,
                    memory_ids,
                )

            for row in cursor.fetchall():
                memory_id, embedding_blob, vector_dim = row
                embedding = self._deserialize_embedding(embedding_blob, vector_dim)
                if embedding:
                    embeddings[memory_id] = embedding

            # 释放连接回连接池
            resource_manager.release_db_connection(self.cache_db_path, conn)

        except Exception as e:
            logger.error(f"批量检索嵌入向量失败: {e}")

        return embeddings

    async def semantic_search(
        self,
        query_embedding: list[float],
        limit: int = 10,
        concept_filter: str | None = None,
        group_id: str = "",
    ) -> list[tuple[str, float]]:
        """基于嵌入向量的语义搜索（支持群聊隔离）"""
        try:
            if not query_embedding:
                return []

            # 使用连接池获取数据库连接
            conn = resource_manager.get_db_connection(self.cache_db_path)
            cursor = conn.cursor()

            # 构建查询条件（支持群聊隔离）
            if concept_filter and group_id:
                cursor.execute(
                    """
                    SELECT memory_id, embedding, vector_dimension
                    FROM memory_embeddings
                    WHERE concept_id = ? AND group_id = ?
                """,
                    (concept_filter, group_id),
                )
            elif concept_filter:
                cursor.execute(
                    """
                    SELECT memory_id, embedding, vector_dimension
                    FROM memory_embeddings
                    WHERE concept_id = ?
                """,
                    (concept_filter,),
                )
            elif group_id:
                cursor.execute(
                    """
                    SELECT memory_id, embedding, vector_dimension
                    FROM memory_embeddings
                    WHERE group_id = ?
                """,
                    (group_id,),
                )
            else:
                cursor.execute("""
                    SELECT memory_id, embedding, vector_dimension
                    FROM memory_embeddings
                """)

            results: list[tuple[str, float]] = []

            for row in cursor.fetchall():
                memory_id, embedding_blob, vector_dim = row
                memory_embedding = self._deserialize_embedding(
                    embedding_blob, vector_dim
                )

                if memory_embedding:
                    similarity = self._cosine_similarity(
                        query_embedding, memory_embedding
                    )
                    if similarity > 0.3:  # 相似度阈值
                        results.append((memory_id, similarity))

            # 释放连接回连接池
            resource_manager.release_db_connection(self.cache_db_path, conn)

            # 按相似度排序并返回前N个结果
            results.sort(key=lambda x: x[1], reverse=True)
            return results[:limit]

        except Exception as e:
            logger.error(f"语义搜索失败: {e}")
            return []

    def _cosine_similarity(self, vec1: list[float], vec2: list[float]) -> float:
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

    async def get_cache_stats(self) -> dict[str, Any]:
        """获取缓存统计信息"""
        try:
            stats = self.precompute_stats.copy()

            # 使用连接池获取数据库连接
            conn = resource_manager.get_db_connection(self.cache_db_path)
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
            cursor.execute(
                "SELECT COUNT(*) FROM memory_embeddings WHERE embedding_version = 'v1.0'"
            )
            current_version_count = cursor.fetchone()[0]
            stats["current_version_count"] = current_version_count

            # 释放连接回连接池
            resource_manager.release_db_connection(self.cache_db_path, conn)

            return stats

        except Exception as e:
            logger.error(f"获取缓存统计信息失败: {e}")
            return self.precompute_stats

    async def schedule_initial_precompute(self):
        """调度初始预计算任务"""
        try:
            # 获取所有记忆ID，按群聊分组处理以确保群聊隔离
            all_memories = list(
                cast(dict[str, Any], self.memory_system.memory_graph.memories).values()
            )

            if not all_memories:
                logger.info("没有记忆需要预计算")
                return

            # 按群聊ID分组记忆
            group_memories: dict[str, list[str]] = {}
            for memory in all_memories:
                group_id = getattr(memory, "group_id", "")
                if group_id not in group_memories:
                    group_memories[group_id] = []
                group_memories[group_id].append(memory.id)

            # 分批处理，每批100个记忆，按群聊分组
            for group_id, memory_ids in group_memories.items():
                batch_size = 100
                for i in range(0, len(memory_ids), batch_size):
                    batch_memory_ids = memory_ids[i : i + batch_size]

                    # 根据索引分配优先级
                    priority = 5 if i == 0 else 3  # 第一批高优先级

                    # 传递群聊ID以确保群聊隔离
                    await self.schedule_precompute_task(
                        batch_memory_ids, priority, group_id
                    )

                    # 避免过于频繁的调度
                    if i + batch_size < len(memory_ids):
                        await asyncio.sleep(0.1)

        except Exception as e:
            logger.error(f"调度初始预计算任务失败: {e}")

    async def cleanup_old_embeddings(self, days_old: int = 30):
        """清理旧的嵌入向量"""
        try:
            cutoff_time = time.time() - (days_old * 24 * 3600)

            # 使用连接池获取数据库连接
            conn = resource_manager.get_db_connection(self.cache_db_path)
            cursor = conn.cursor()

            # 删除旧的嵌入向量
            cursor.execute(
                """
                DELETE FROM memory_embeddings
                WHERE last_updated < ?
                AND embedding_version != 'v1.0'
            """,
                (cutoff_time,),
            )

            deleted_count = cursor.rowcount
            conn.commit()

            # 释放连接回连接池
            resource_manager.release_db_connection(self.cache_db_path, conn)

            if deleted_count > 0:
                logger.info(f"清理了 {deleted_count} 个旧的嵌入向量")

        except Exception as e:
            logger.error(f"清理旧嵌入向量失败: {e}")

    async def delete_embedding(self, memory_id: str, group_id: str = "") -> bool:
        """删除指定记忆的嵌入向量"""
        try:
            if not memory_id:
                return False

            conn = resource_manager.get_db_connection(self.cache_db_path)
            cursor = conn.cursor()

            if group_id:
                cursor.execute(
                    "DELETE FROM memory_embeddings WHERE memory_id = ? AND group_id = ?",
                    (memory_id, group_id),
                )
            else:
                cursor.execute(
                    "DELETE FROM memory_embeddings WHERE memory_id = ?", (memory_id,)
                )

            deleted = cursor.rowcount
            conn.commit()
            resource_manager.release_db_connection(self.cache_db_path, conn)

            if deleted and self.precompute_stats.get("cached_memories", 0) > 0:
                self.precompute_stats["cached_memories"] = max(
                    0, self.precompute_stats["cached_memories"] - deleted
                )

            return deleted > 0
        except Exception as e:
            logger.error(f"删除嵌入向量失败: {e}")
            return False

    async def cleanup(self):
        """清理资源，支持优雅退出"""
        try:
            logger.info("开始清理嵌入向量缓存管理器资源")

            # 1. 停止工作线程
            if hasattr(self, "_should_stop_worker"):
                self._should_stop_worker.set()

            if hasattr(self, "_worker_task") and self._worker_task:
                try:
                    # 等待工作线程正常退出
                    await asyncio.wait_for(self._worker_task, timeout=10.0)
                except asyncio.TimeoutError:
                    # 如果超时，强制取消
                    self._worker_task.cancel()
                    try:
                        await self._worker_task
                    except asyncio.CancelledError:
                        pass

            # 2. 清空队列
            if hasattr(self, "precompute_queue"):
                while not self.precompute_queue.empty():
                    try:
                        self.precompute_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break

            logger.info("嵌入向量缓存管理器资源已清理完成")

        except Exception as e:
            logger.error(f"清理嵌入向量缓存管理器时发生错误: {e}", exc_info=True)

    def get_queue_status(self) -> dict[str, int | bool]:
        """获取队列状态信息"""
        return {
            "queue_size": self.precompute_queue.qsize(),
            "max_queue_size": self.max_queue_size,
            "is_precomputing": self.is_precomputing,
            "pending_precompute": int(
                self.precompute_stats.get("pending_precompute", 0)
            ),
        }
