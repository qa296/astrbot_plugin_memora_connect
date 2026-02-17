import asyncio
import sqlite3
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field

from astrbot.api import logger


@dataclass
class ConnectionInfo:
    """连接信息"""

    connection: sqlite3.Connection
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    is_used: bool = False
    thread_id: int = field(default_factory=threading.get_ident)


class DatabaseConnectionPool:
    """数据库连接池管理器 - 单例模式"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, max_connections: int = 20, timeout: float = 30.0):
        if not hasattr(self, "_initialized"):
            self.max_connections = max_connections
            self.timeout = timeout
            self.connections: dict[str, list[ConnectionInfo]] = {}
            self.connection_locks: dict[str, threading.Lock] = {}
            self._initialized = True
            logger.info(f"数据库连接池初始化完成，最大连接数: {max_connections}")

    def get_connection(self, db_path: str) -> sqlite3.Connection:
        """获取数据库连接"""
        if db_path not in self.connections:
            self.connections[db_path] = []
            self.connection_locks[db_path] = threading.Lock()

        lock = self.connection_locks[db_path]

        with lock:
            # 查找可用连接
            available_connections = [
                conn_info
                for conn_info in self.connections[db_path]
                if not conn_info.is_used
                and conn_info.thread_id == threading.get_ident()
            ]

            if available_connections:
                # 使用现有连接
                conn_info = available_connections[0]
                conn_info.is_used = True
                conn_info.last_used = time.time()
                return conn_info.connection

            # 检查是否可以创建新连接
            active_connections = [
                conn_info
                for conn_info in self.connections[db_path]
                if conn_info.is_used
            ]

            if len(active_connections) < self.max_connections:
                # 创建新连接
                try:
                    conn = sqlite3.connect(db_path, check_same_thread=False)
                    conn.row_factory = sqlite3.Row
                    conn_info = ConnectionInfo(
                        connection=conn, thread_id=threading.get_ident(), is_used=True
                    )
                    self.connections[db_path].append(conn_info)
                    logger.debug(f"创建新的数据库连接: {db_path}")
                    return conn
                except Exception as e:
                    logger.error(f"创建数据库连接失败: {e}")
                    raise

            # 等待可用连接
            start_time = time.time()
            while time.time() - start_time < self.timeout:
                # 清理过期连接
                self._cleanup_expired_connections(db_path)

                # 再次检查可用连接
                available_connections = [
                    conn_info
                    for conn_info in self.connections[db_path]
                    if not conn_info.is_used
                ]

                if available_connections:
                    conn_info = available_connections[0]
                    conn_info.is_used = True
                    conn_info.last_used = time.time()
                    conn_info.thread_id = threading.get_ident()
                    logger.debug(f"获取到数据库连接: {db_path}")
                    return conn_info.connection

                # 短暂等待
                time.sleep(0.1)

            # 超时处理
            raise TimeoutError(f"获取数据库连接超时: {db_path}")

    def release_connection(self, db_path: str, connection: sqlite3.Connection):
        """释放数据库连接"""
        if db_path not in self.connections:
            return

        lock = self.connection_locks[db_path]

        with lock:
            for conn_info in self.connections[db_path]:
                if conn_info.connection == connection:
                    conn_info.is_used = False
                    conn_info.last_used = time.time()
                    break

    def _cleanup_expired_connections(self, db_path: str):
        """清理过期连接"""
        if db_path not in self.connections:
            return

        current_time = time.time()
        expired_connections = []

        for conn_info in self.connections[db_path]:
            # 清理5分钟未使用的连接
            if not conn_info.is_used and current_time - conn_info.last_used > 300:
                expired_connections.append(conn_info)

        for conn_info in expired_connections:
            try:
                conn_info.connection.close()
                self.connections[db_path].remove(conn_info)
                logger.debug(f"清理过期数据库连接: {db_path}")
            except Exception as e:
                logger.warning(f"关闭数据库连接失败: {e}")

    def close_connections(self, db_path: str):
        """关闭指定数据库的所有连接"""
        if db_path not in self.connections:
            return

        lock = self.connection_locks[db_path]
        with lock:
            for conn_info in self.connections[db_path]:
                try:
                    conn_info.connection.close()
                except Exception as e:
                    logger.warning(f"关闭数据库连接失败: {e}")
            self.connections[db_path].clear()
            logger.debug(f"已关闭数据库所有连接: {db_path}")

    def close_all_connections(self):
        """关闭所有连接"""
        for db_path, connections in self.connections.items():
            lock = self.connection_locks[db_path]
            with lock:
                for conn_info in connections:
                    try:
                        conn_info.connection.close()
                    except Exception as e:
                        logger.warning(f"关闭数据库连接失败: {e}")
                connections.clear()
        logger.info("所有数据库连接已关闭")

    @contextmanager
    def get_connection_context(self, db_path: str):
        """获取数据库连接上下文管理器"""
        connection = None
        try:
            connection = self.get_connection(db_path)
            yield connection
        finally:
            if connection:
                self.release_connection(db_path, connection)


class EventLoopManager:
    """事件循环管理器 - 单例模式"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self.main_event_loop = None
            self.event_loops: dict[int, asyncio.AbstractEventLoop] = {}
            self._initialized = True
            logger.info("事件循环管理器初始化完成")

    def set_main_event_loop(self, loop: asyncio.AbstractEventLoop):
        """设置主事件循环"""
        self.main_event_loop = loop
        logger.info("设置主事件循环")

    def get_event_loop(self) -> asyncio.AbstractEventLoop:
        """获取当前线程的事件循环"""
        try:
            # 尝试获取当前事件循环
            current_loop = asyncio.get_running_loop()
            return current_loop
        except RuntimeError:
            # 如果没有运行的事件循环，尝试获取主事件循环
            if self.main_event_loop and not self.main_event_loop.is_closed():
                return self.main_event_loop

            # 创建新的事件循环
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                thread_id = threading.get_ident()
                self.event_loops[thread_id] = loop
                logger.debug(f"创建新的事件循环: {thread_id}")
                return loop
            except Exception as e:
                logger.error(f"创建事件循环失败: {e}")
                raise

    def create_task(self, coro, name: str = None) -> asyncio.Task:
        """创建异步任务，确保在正确的事件循环中运行"""
        loop = self.get_event_loop()
        try:
            if name:
                task = loop.create_task(coro, name=name)
            else:
                task = loop.create_task(coro)
            logger.debug(f"创建异步任务: {name or 'unnamed'}")
            return task
        except Exception as e:
            logger.error(f"创建异步任务失败: {e}")
            raise

    def close_all_loops(self):
        """关闭所有事件循环"""
        for thread_id, loop in self.event_loops.items():
            try:
                if not loop.is_closed():
                    loop.close()
                    logger.debug(f"关闭事件循环: {thread_id}")
            except Exception as e:
                logger.warning(f"关闭事件循环失败: {e}")
        self.event_loops.clear()

        if self.main_event_loop and not self.main_event_loop.is_closed():
            try:
                self.main_event_loop.close()
                logger.info("关闭主事件循环")
            except Exception as e:
                logger.warning(f"关闭主事件循环失败: {e}")


class ResourceManager:
    """资源管理器 - 单例模式"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self.db_pool = DatabaseConnectionPool()
            self.event_loop_manager = EventLoopManager()
            self.cleanup_callbacks: list[Callable] = []
            self._initialized = True
            logger.info("资源管理器初始化完成")

    def register_cleanup_callback(self, callback: Callable):
        """注册清理回调"""
        self.cleanup_callbacks.append(callback)
        logger.debug("注册清理回调")

    def cleanup(self):
        """清理所有资源"""
        logger.info("开始清理资源")

        # 执行清理回调
        for callback in self.cleanup_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"执行清理回调失败: {e}")

        # 清理数据库连接
        self.db_pool.close_all_connections()

        # 清理事件循环
        self.event_loop_manager.close_all_loops()

        logger.info("资源清理完成")

    def get_db_connection(self, db_path: str) -> sqlite3.Connection:
        """获取数据库连接"""
        return self.db_pool.get_connection(db_path)

    def release_db_connection(self, db_path: str, connection: sqlite3.Connection):
        """释放数据库连接"""
        self.db_pool.release_connection(db_path, connection)

    def close_db_connections(self, db_path: str):
        """关闭指定数据库的所有连接"""
        self.db_pool.close_connections(db_path)

    @contextmanager
    def get_db_connection_context(self, db_path: str):
        """获取数据库连接上下文管理器"""
        connection = None
        try:
            connection = self.get_db_connection(db_path)
            yield connection
        finally:
            if connection:
                self.release_db_connection(db_path, connection)

    def create_task(self, coro, name: str = None) -> asyncio.Task:
        """创建异步任务"""
        return self.event_loop_manager.create_task(coro, name)

    def set_main_event_loop(self, loop: asyncio.AbstractEventLoop):
        """设置主事件循环"""
        self.event_loop_manager.set_main_event_loop(loop)


# 全局资源管理器实例
resource_manager = ResourceManager()
