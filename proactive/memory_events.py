"""
记忆事件总线系统
提供事件驱动机制，支持主动插件订阅记忆相关事件
"""

import asyncio
from enum import Enum
from typing import Dict, List, Callable, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from astrbot.api import logger


class MemoryEventType(Enum):
    """记忆事件类型枚举"""
    # 记忆触发事件
    MEMORY_TRIGGERED = "memory.triggered"  # 当前对话触发历史记忆
    
    # 话题相关事件
    TOPIC_CREATED = "topic.created"  # 新话题被创建
    TOPIC_RESURRECTED = "topic.resurrected"  # 沉默N天的话题被重新激活
    TOPIC_MERGED = "topic.merged"  # 两个话题被合并
    TOPIC_EXPIRED = "topic.expired"  # 话题过期（长时间未讨论）
    
    # 关系变化事件
    RELATIONSHIP_SHIFT = "relationship.shift"  # 用户亲密度分数变化超过阈值
    IMPRESSION_UPDATED = "impression.updated"  # 印象被更新
    
    # 周期性分析事件
    MEMORY_ANALYSIS_READY = "memory.analysis_ready"  # 每日记忆整理完成
    
    # 特殊事件
    ANNIVERSARY_DETECTED = "anniversary.detected"  # 检测到历史今日事件
    OPEN_TOPIC_FOUND = "open_topic.found"  # 发现未闭合话题
    
    # 禁忌词事件
    TABOO_DETECTED = "taboo.detected"  # 检测到禁忌词
    TABOO_ADDED = "taboo.added"  # 添加新禁忌词


@dataclass
class MemoryEvent:
    """记忆事件数据类"""
    event_type: MemoryEventType
    timestamp: datetime = field(default_factory=datetime.now)
    group_id: str = ""
    user_id: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "group_id": self.group_id,
            "user_id": self.user_id,
            "data": self.data,
            "metadata": self.metadata
        }


class MemoryEventBus:
    """
    记忆事件总线
    实现发布-订阅模式，允许插件订阅和接收记忆相关事件
    """
    
    def __init__(self):
        # 事件订阅者字典：{事件类型: [回调函数列表]}
        self._subscribers: Dict[MemoryEventType, List[Callable]] = {}
        
        # 事件历史记录（可选，用于调试）
        self._event_history: List[MemoryEvent] = []
        self._max_history_size = 1000
        
        # 事件队列
        self._event_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        
        # 处理任务
        self._processor_task: Optional[asyncio.Task] = None
        self._running = False
        
        logger.info("记忆事件总线已初始化")
    
    def subscribe(self, event_type: MemoryEventType, callback: Callable) -> bool:
        """
        订阅事件
        
        Args:
            event_type: 事件类型
            callback: 回调函数，签名应为 async def callback(event: MemoryEvent)
            
        Returns:
            bool: 是否订阅成功
        """
        try:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            
            if callback not in self._subscribers[event_type]:
                self._subscribers[event_type].append(callback)
                logger.info(f"订阅事件成功: {event_type.value}, 回调: {callback.__name__}")
                return True
            else:
                logger.warning(f"重复订阅事件: {event_type.value}, 回调: {callback.__name__}")
                return False
                
        except Exception as e:
            logger.error(f"订阅事件失败: {e}", exc_info=True)
            return False
    
    def unsubscribe(self, event_type: MemoryEventType, callback: Callable) -> bool:
        """
        取消订阅事件
        
        Args:
            event_type: 事件类型
            callback: 回调函数
            
        Returns:
            bool: 是否取消成功
        """
        try:
            if event_type in self._subscribers:
                if callback in self._subscribers[event_type]:
                    self._subscribers[event_type].remove(callback)
                    logger.info(f"取消订阅成功: {event_type.value}, 回调: {callback.__name__}")
                    return True
            
            logger.warning(f"取消订阅失败，未找到订阅: {event_type.value}")
            return False
            
        except Exception as e:
            logger.error(f"取消订阅失败: {e}", exc_info=True)
            return False
    
    async def publish(self, event: MemoryEvent, async_mode: bool = True) -> bool:
        """
        发布事件
        
        Args:
            event: 记忆事件
            async_mode: 是否异步处理（True：加入队列异步处理，False：立即处理）
            
        Returns:
            bool: 是否发布成功
        """
        try:
            # 记录事件历史
            self._event_history.append(event)
            if len(self._event_history) > self._max_history_size:
                self._event_history.pop(0)
            
            if async_mode:
                # 异步模式：加入队列
                try:
                    self._event_queue.put_nowait(event)
                    logger.debug(f"事件已加入队列: {event.event_type.value}")
                    return True
                except asyncio.QueueFull:
                    logger.warning(f"事件队列已满，事件被丢弃: {event.event_type.value}")
                    return False
            else:
                # 同步模式：立即处理
                await self._process_event(event)
                return True
                
        except Exception as e:
            logger.error(f"发布事件失败: {e}", exc_info=True)
            return False
    
    async def _process_event(self, event: MemoryEvent):
        """
        处理单个事件，调用所有订阅者
        
        Args:
            event: 记忆事件
        """
        if event.event_type not in self._subscribers:
            return
        
        subscribers = self._subscribers[event.event_type]
        if not subscribers:
            return
        
        logger.debug(f"处理事件: {event.event_type.value}, 订阅者数量: {len(subscribers)}")
        
        # 并发调用所有订阅者
        tasks = []
        for callback in subscribers:
            try:
                if asyncio.iscoroutinefunction(callback):
                    tasks.append(asyncio.create_task(callback(event)))
                else:
                    # 同步函数包装为异步
                    tasks.append(asyncio.create_task(asyncio.to_thread(callback, event)))
            except Exception as e:
                logger.error(f"创建回调任务失败: {callback.__name__}, 错误: {e}")
        
        # 等待所有回调完成
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"事件回调执行失败: {subscribers[i].__name__}, 错误: {result}")
    
    async def start(self):
        """启动事件处理器"""
        if self._running:
            logger.warning("事件总线已经在运行中")
            return
        
        self._running = True
        self._processor_task = asyncio.create_task(self._event_processor_loop())
        logger.info("记忆事件总线处理器已启动")
    
    async def stop(self):
        """停止事件处理器"""
        if not self._running:
            return
        
        self._running = False
        
        # 等待队列清空
        while not self._event_queue.empty():
            try:
                await asyncio.wait_for(self._event_queue.join(), timeout=5.0)
                break
            except asyncio.TimeoutError:
                logger.warning("事件队列清空超时")
                break
        
        # 取消处理任务
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
        
        logger.info("记忆事件总线处理器已停止")
    
    async def _event_processor_loop(self):
        """事件处理循环"""
        logger.info("事件处理循环已启动")
        
        while self._running:
            try:
                # 从队列获取事件，超时1秒
                try:
                    event = await asyncio.wait_for(self._event_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                
                # 处理事件
                try:
                    await self._process_event(event)
                finally:
                    self._event_queue.task_done()
                    
            except asyncio.CancelledError:
                logger.info("事件处理循环被取消")
                break
            except Exception as e:
                logger.error(f"事件处理循环异常: {e}", exc_info=True)
                await asyncio.sleep(1)  # 出错后暂停1秒
        
        logger.info("事件处理循环已退出")
    
    def get_event_history(self, event_type: Optional[MemoryEventType] = None, 
                         limit: int = 100) -> List[MemoryEvent]:
        """
        获取事件历史
        
        Args:
            event_type: 事件类型过滤，None表示获取所有类型
            limit: 返回数量限制
            
        Returns:
            List[MemoryEvent]: 事件列表
        """
        if event_type:
            filtered = [e for e in self._event_history if e.event_type == event_type]
        else:
            filtered = self._event_history
        
        return filtered[-limit:]
    
    def get_subscriber_count(self, event_type: MemoryEventType) -> int:
        """
        获取指定事件类型的订阅者数量
        
        Args:
            event_type: 事件类型
            
        Returns:
            int: 订阅者数量
        """
        return len(self._subscribers.get(event_type, []))
    
    def get_all_subscribers(self) -> Dict[str, int]:
        """
        获取所有订阅统计
        
        Returns:
            Dict[str, int]: {事件类型: 订阅者数量}
        """
        return {
            event_type.value: len(callbacks)
            for event_type, callbacks in self._subscribers.items()
        }


# 全局事件总线实例（单例模式）
_global_event_bus: Optional[MemoryEventBus] = None


def get_event_bus() -> MemoryEventBus:
    """
    获取全局事件总线实例
    
    Returns:
        MemoryEventBus: 全局事件总线
    """
    global _global_event_bus
    if _global_event_bus is None:
        _global_event_bus = MemoryEventBus()
    return _global_event_bus


async def initialize_event_bus():
    """初始化并启动全局事件总线"""
    bus = get_event_bus()
    await bus.start()
    return bus


async def shutdown_event_bus():
    """关闭全局事件总线"""
    global _global_event_bus
    if _global_event_bus:
        await _global_event_bus.stop()
        _global_event_bus = None
