"""
记忆系统统一API网关
提供标准化、高性能的API接口供主动插件调用
"""

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime
from functools import wraps
from typing import Any

from astrbot.api import logger


@dataclass
class APIResponse:
    """API响应数据类"""

    success: bool
    data: Any = None
    error: str = ""
    latency_ms: float = 0.0
    cached: bool = False


class PerformanceMonitor:
    """性能监控器"""

    def __init__(self):
        self.request_count = 0
        self.total_latency = 0.0
        self.slow_requests = []  # 记录慢请求
        self.error_count = 0

    def record_request(self, endpoint: str, latency_ms: float, success: bool):
        """记录请求"""
        self.request_count += 1
        self.total_latency += latency_ms

        if not success:
            self.error_count += 1

        # 记录超过100ms的慢请求
        if latency_ms > 100:
            self.slow_requests.append(
                {
                    "endpoint": endpoint,
                    "latency_ms": latency_ms,
                    "timestamp": time.time(),
                }
            )

            # 只保留最近100个
            if len(self.slow_requests) > 100:
                self.slow_requests.pop(0)

    def get_stats(self) -> dict:
        """获取统计信息"""
        avg_latency = (
            self.total_latency / self.request_count if self.request_count > 0 else 0
        )

        return {
            "total_requests": self.request_count,
            "average_latency_ms": round(avg_latency, 2),
            "error_count": self.error_count,
            "error_rate": round(self.error_count / self.request_count * 100, 2)
            if self.request_count > 0
            else 0,
            "slow_requests_count": len(self.slow_requests),
        }


def performance_monitored(func):
    """性能监控装饰器"""

    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        start_time = time.time()
        success = True

        try:
            result = await func(self, *args, **kwargs)
            return result
        except Exception as e:
            success = False
            logger.error(f"API调用失败: {func.__name__}, 错误: {e}", exc_info=True)
            raise
        finally:
            latency_ms = (time.time() - start_time) * 1000
            self.performance_monitor.record_request(func.__name__, latency_ms, success)

    return wrapper


def cached(ttl_seconds: int = 3600):
    """缓存装饰器"""

    def decorator(func):
        cache = {}

        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            # 生成缓存键
            cache_key = f"{func.__name__}_{args}_{kwargs}"

            # 检查缓存
            if cache_key in cache:
                cached_data, cached_time = cache[cache_key]
                if time.time() - cached_time < ttl_seconds:
                    logger.debug(f"缓存命中: {func.__name__}")
                    return cached_data

            # 执行函数
            result = await func(self, *args, **kwargs)

            # 更新缓存
            cache[cache_key] = (result, time.time())

            return result

        return wrapper

    return decorator


class MemoryAPIGateway:
    """
    记忆系统统一API网关
    封装所有记忆能力为标准化API
    """

    def __init__(self, memory_system, topic_analyzer, user_profiling, temporal_memory):
        """
        初始化API网关

        Args:
            memory_system: 记忆系统
            topic_analyzer: 话题分析器
            user_profiling: 用户画像系统
            temporal_memory: 时间维度记忆系统
        """
        self.memory_system = memory_system
        self.topic_analyzer = topic_analyzer
        self.user_profiling = user_profiling
        self.temporal_memory = temporal_memory

        # 性能监控
        self.performance_monitor = PerformanceMonitor()

        # L1缓存：内存缓存（最近24小时热门查询）
        self._l1_cache: dict[str, tuple[Any, float]] = {}
        self._l1_cache_ttl = 3600  # 1小时

        # 健康状态
        self._is_healthy = True
        self._last_health_check = time.time()

        logger.info("记忆系统API网关已初始化")

    def _check_cache(self, key: str) -> Any | None:
        """检查L1缓存"""
        if key in self._l1_cache:
            data, cached_at = self._l1_cache[key]
            if time.time() - cached_at < self._l1_cache_ttl:
                return data
            else:
                # 过期，删除
                del self._l1_cache[key]
        return None

    def _set_cache(self, key: str, data: Any):
        """设置L1缓存"""
        self._l1_cache[key] = (data, time.time())

        # 限制缓存大小
        if len(self._l1_cache) > 1000:
            # 删除最旧的50%
            sorted_keys = sorted(self._l1_cache.items(), key=lambda x: x[1][1])
            for k, _ in sorted_keys[:500]:
                del self._l1_cache[k]

    @performance_monitored
    async def get_topic_relevance(
        self, message: str, group_id: str = "", max_results: int = 5
    ) -> APIResponse:
        """
        话题语义匹配服务

        Args:
            message: 当前消息
            group_id: 群组ID
            max_results: 最多返回结果数

        Returns:
            APIResponse: {topic_id, score, info}列表
        """
        start_time = time.time()

        try:
            # 检查缓存
            cache_key = f"topic_relevance_{message[:50]}_{group_id}"
            cached = self._check_cache(cache_key)
            if cached:
                return APIResponse(
                    success=True,
                    data=cached,
                    latency_ms=(time.time() - start_time) * 1000,
                    cached=True,
                )

            # 调用话题分析器
            active_sessions = (
                self.topic_analyzer.get_active_sessions(group_id)
                if self.topic_analyzer
                else []
            )

            # 格式化返回
            formatted_results = [
                {
                    "session_id": s.get("session_id"),
                    "topic": s.get("topic"),
                    "keywords": s.get("keywords", []),
                    "message_count": s.get("message_count", 0),
                }
                for s in active_sessions[:max_results]
            ]

            # 缓存结果
            self._set_cache(cache_key, formatted_results)

            return APIResponse(
                success=True,
                data=formatted_results,
                latency_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            logger.error(f"获取话题相关性失败: {e}", exc_info=True)
            return APIResponse(
                success=False,
                error=str(e),
                latency_ms=(time.time() - start_time) * 1000,
            )

    @performance_monitored
    async def get_intimacy(self, user_id: str, group_id: str = "") -> APIResponse:
        """
        获取用户亲密度

        Args:
            user_id: 用户ID
            group_id: 群组ID

        Returns:
            APIResponse: {score: 0-100, sub_scores: {...}}
        """
        start_time = time.time()

        try:
            # 检查缓存
            cache_key = f"intimacy_{user_id}_{group_id}"
            cached = self._check_cache(cache_key)
            if cached:
                return APIResponse(
                    success=True,
                    data=cached,
                    latency_ms=(time.time() - start_time) * 1000,
                    cached=True,
                )

            # 调用用户画像系统
            result = await self.user_profiling.get_intimacy(user_id, group_id)

            # 缓存结果
            self._set_cache(cache_key, result)

            return APIResponse(
                success=True, data=result, latency_ms=(time.time() - start_time) * 1000
            )

        except Exception as e:
            logger.error(f"获取亲密度失败: {e}", exc_info=True)
            return APIResponse(
                success=False,
                error=str(e),
                latency_ms=(time.time() - start_time) * 1000,
            )

    @performance_monitored
    async def batch_get_intimacy(
        self, user_ids: list[str], group_id: str = ""
    ) -> APIResponse:
        """
        批量获取用户亲密度

        Args:
            user_ids: 用户ID列表
            group_id: 群组ID

        Returns:
            APIResponse: [{user_id, score, sub_scores}]列表
        """
        start_time = time.time()

        try:
            results = []

            for user_id in user_ids:
                # 检查缓存
                cache_key = f"intimacy_{user_id}_{group_id}"
                cached = self._check_cache(cache_key)

                if cached:
                    results.append(cached)
                else:
                    # 计算
                    result = await self.user_profiling.get_intimacy(user_id, group_id)
                    results.append(result)
                    # 缓存
                    self._set_cache(cache_key, result)

            return APIResponse(
                success=True, data=results, latency_ms=(time.time() - start_time) * 1000
            )

        except Exception as e:
            logger.error(f"批量获取亲密度失败: {e}", exc_info=True)
            return APIResponse(
                success=False,
                error=str(e),
                latency_ms=(time.time() - start_time) * 1000,
            )

    @performance_monitored
    async def get_user_interests(self, user_id: str, group_id: str = "") -> APIResponse:
        """
        获取用户兴趣偏好

        Args:
            user_id: 用户ID
            group_id: 群组ID

        Returns:
            APIResponse: [{concept, weight}]列表
        """
        start_time = time.time()

        try:
            # 检查缓存
            cache_key = f"interests_{user_id}_{group_id}"
            cached = self._check_cache(cache_key)
            if cached:
                return APIResponse(
                    success=True,
                    data=cached,
                    latency_ms=(time.time() - start_time) * 1000,
                    cached=True,
                )

            # 调用用户画像系统
            result = await self.user_profiling.get_user_interests(user_id, group_id)

            # 缓存结果
            self._set_cache(cache_key, result)

            return APIResponse(
                success=True, data=result, latency_ms=(time.time() - start_time) * 1000
            )

        except Exception as e:
            logger.error(f"获取用户兴趣失败: {e}", exc_info=True)
            return APIResponse(
                success=False,
                error=str(e),
                latency_ms=(time.time() - start_time) * 1000,
            )

    @performance_monitored
    async def get_open_topics(self, group_id: str = "", days: int = 7) -> APIResponse:
        """
        获取未闭合话题

        Args:
            group_id: 群组ID
            days: 查询最近N天

        Returns:
            APIResponse: [{topic_id, question, asker_id, ...}]列表
        """
        start_time = time.time()

        try:
            result = await self.temporal_memory.get_open_topics(group_id, days)

            return APIResponse(
                success=True, data=result, latency_ms=(time.time() - start_time) * 1000
            )

        except Exception as e:
            logger.error(f"获取未闭合话题失败: {e}", exc_info=True)
            return APIResponse(
                success=False,
                error=str(e),
                latency_ms=(time.time() - start_time) * 1000,
            )

    @performance_monitored
    async def get_today_anniversaries(self, group_id: str = "") -> APIResponse:
        """
        获取历史今日记忆

        Args:
            group_id: 群组ID

        Returns:
            APIResponse: [{memory_id, event_description, days_ago, ...}]列表
        """
        start_time = time.time()

        try:
            result = await self.temporal_memory.get_today_anniversaries(group_id)

            # 转换为字典格式
            formatted_result = [
                {
                    "memory_id": ann.memory_id,
                    "content": ann.content,
                    "event_description": ann.event_description,
                    "days_ago": ann.days_ago,
                    "original_date": ann.original_date.isoformat(),
                }
                for ann in result
            ]

            return APIResponse(
                success=True,
                data=formatted_result,
                latency_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            logger.error(f"获取历史今日记忆失败: {e}", exc_info=True)
            return APIResponse(
                success=False,
                error=str(e),
                latency_ms=(time.time() - start_time) * 1000,
            )

    @performance_monitored
    async def find_connection(
        self, user_a: str, user_b: str, group_id: str = ""
    ) -> APIResponse:
        """
        查找两个用户的关系路径（共同兴趣话题）

        Args:
            user_a: 用户A的ID
            user_b: 用户B的ID
            group_id: 群组ID

        Returns:
            APIResponse: {common_topics: [...], connection_strength: float}
        """
        start_time = time.time()

        try:
            # 获取两个用户的兴趣
            interests_a = await self.user_profiling.extract_user_interests(
                user_a, group_id, top_k=10
            )
            interests_b = await self.user_profiling.extract_user_interests(
                user_b, group_id, top_k=10
            )

            # 查找共同话题
            topics_a = set(concept for concept, _ in interests_a)
            topics_b = set(concept for concept, _ in interests_b)
            common_topics = topics_a & topics_b

            # 计算连接强度
            if common_topics:
                # 基于共同话题的权重
                weights_a = {concept: weight for concept, weight in interests_a}
                weights_b = {concept: weight for concept, weight in interests_b}

                connection_strength = sum(
                    (weights_a.get(topic, 0) + weights_b.get(topic, 0)) / 2
                    for topic in common_topics
                )
            else:
                connection_strength = 0.0

            return APIResponse(
                success=True,
                data={
                    "common_topics": list(common_topics),
                    "connection_strength": connection_strength,
                    "user_a_interests": [
                        {"concept": c, "weight": w} for c, w in interests_a[:5]
                    ],
                    "user_b_interests": [
                        {"concept": c, "weight": w} for c, w in interests_b[:5]
                    ],
                },
                latency_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            logger.error(f"查找用户关系路径失败: {e}", exc_info=True)
            return APIResponse(
                success=False,
                error=str(e),
                latency_ms=(time.time() - start_time) * 1000,
            )

    @performance_monitored
    async def get_memory_importance_ranking(
        self, group_id: str = "", top_k: int = 10
    ) -> APIResponse:
        """
        获取记忆重要性排序
        基于度中心性和激活频率

        Args:
            group_id: 群组ID
            top_k: 返回TOP K个记忆

        Returns:
            APIResponse: [{memory_id, content, importance_score, ...}]列表
        """
        start_time = time.time()

        try:
            memory_graph = self.memory_system.memory_graph

            # 计算每个记忆的重要性分数
            memory_scores = []

            for memory in memory_graph.memories.values():
                # 群组过滤
                if group_id and getattr(memory, "group_id", "") != group_id:
                    continue

                # 计算度中心性（记忆关联的概念数量）
                degree = 1  # 至少关联一个概念

                # 计算激活频率分数
                access_score = min(memory.access_count / 10.0, 1.0)

                # 综合得分 = 度中心性 * 0.4 + 激活频率 * 0.6
                importance_score = degree * 0.4 + access_score * 0.6

                memory_scores.append(
                    {
                        "memory_id": memory.id,
                        "content": memory.content,
                        "importance_score": importance_score,
                        "access_count": memory.access_count,
                        "participants": memory.participants or "",
                        "created_at": datetime.fromtimestamp(
                            memory.created_at
                        ).isoformat(),
                    }
                )

            # 排序
            memory_scores.sort(key=lambda x: x["importance_score"], reverse=True)

            return APIResponse(
                success=True,
                data=memory_scores[:top_k],
                latency_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            logger.error(f"获取记忆重要性排序失败: {e}", exc_info=True)
            return APIResponse(
                success=False,
                error=str(e),
                latency_ms=(time.time() - start_time) * 1000,
            )

    async def health_check(self) -> dict:
        """
        健康检查

        Returns:
            Dict: {healthy: bool, components: {...}, performance: {...}}
        """
        try:
            # 检查各个组件
            components = {
                "memory_system": self.memory_system is not None,
                "topic_analyzer": self.topic_analyzer is not None,
                "user_profiling": self.user_profiling is not None,
                "temporal_memory": self.temporal_memory is not None,
            }

            # 性能统计
            performance = self.performance_monitor.get_stats()

            # 综合健康状态
            healthy = all(components.values())

            # 如果平均延迟超过100ms，标记为不健康
            if performance.get("average_latency_ms", 0) > 100:
                healthy = False

            # 如果错误率超过5%，标记为不健康
            if performance.get("error_rate", 0) > 5:
                healthy = False

            self._is_healthy = healthy
            self._last_health_check = time.time()

            return {
                "healthy": healthy,
                "timestamp": datetime.now().isoformat(),
                "components": components,
                "performance": performance,
                "cache_size": len(self._l1_cache),
            }

        except Exception as e:
            logger.error(f"健康检查失败: {e}", exc_info=True)
            return {
                "healthy": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    def is_healthy(self) -> bool:
        """
        快速健康状态检查

        Returns:
            bool: 是否健康
        """
        # 如果距离上次检查超过60秒，重新检查
        if time.time() - self._last_health_check > 60:
            asyncio.create_task(self.health_check())

        return self._is_healthy

    def get_performance_stats(self) -> dict:
        """获取性能统计"""
        return self.performance_monitor.get_stats()

    def clear_cache(self):
        """清空缓存"""
        self._l1_cache.clear()
        logger.info("API网关缓存已清空")
