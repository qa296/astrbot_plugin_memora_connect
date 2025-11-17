# Memora Connect 主动能力升级 API 文档

## 概述

本次升级为 Memora Connect 记忆插件添加了拟人化主动交互所需的核心能力，主要包括：

1. **实时话题计算引擎** - 动态话题聚类、语义匹配和生命线追踪
2. **用户画像系统** - 亲密度量化、兴趣偏好提取和禁忌词学习
3. **时间维度记忆检索** - 历史今日检测和未闭合话题追踪
4. **事件驱动机制** - 记忆事件总线，支持发布订阅模式
5. **统一API网关** - 标准化、高性能的API接口

---

## 新增模块

### 1. 事件总线 (memory_events.py)

支持的事件类型：

- `memory.triggered` - 当前对话触发历史记忆
- `topic.created` - 新话题被创建
- `topic.resurrected` - 沉默N天的话题被重新激活
- `topic.merged` - 两个话题被合并
- `topic.expired` - 话题过期
- `relationship.shift` - 用户亲密度分数变化超过阈值
- `impression.updated` - 印象被更新
- `memory.analysis_ready` - 每日记忆整理完成
- `anniversary.detected` - 检测到历史今日事件
- `open_topic.found` - 发现未闭合话题
- `taboo.detected` - 检测到禁忌词
- `taboo.added` - 添加新禁忌词

### 2. 话题引擎 (topic_engine.py)

实现动态话题聚类、语义匹配和生命线追踪。

### 3. 用户画像系统 (user_profiling.py)

提供亲密度计算、兴趣提取和禁忌词管理。

### 4. 时间维度记忆系统 (temporal_memory.py)

实现历史今日检测和未闭合话题追踪。

### 5. API网关 (memory_api_gateway.py)

统一封装所有记忆能力，提供标准化API接口。

---

## API 使用指南

所有API都通过 Memora Connect 插件实例调用。假设您已经获取了插件实例：

```python
# 获取 Memora Connect 插件实例
memora_plugin = context.get_registered_star("astrbot_plugin_memora_connect").star_cls
```

### 1. 话题相关API

#### 获取话题相关性

```python
# 获取消息与现有话题的相关性
result = await memora_plugin.get_topic_relevance_api(
    message="今天天气真好",
    group_id="group_123",
    max_results=5
)

# 返回格式：
# [
#     {
#         "topic_id": "abc123",
#         "relevance_score": 0.85,
#         "topic_info": {
#             "keywords": ["天气", "晴天"],
#             "participants": ["user1", "user2"],
#             "depth": 3,
#             "heat": 0.7,
#             "lifetime": 3600.5,
#             "last_active": "2024-01-01T12:00:00"
#         }
#     },
#     ...
# ]
```

### 2. 用户亲密度API

#### 获取单个用户亲密度

```python
# 获取用户亲密度
intimacy = await memora_plugin.get_intimacy_api(
    user_id="user123",
    group_id="group_123"
)

# 返回格式：
# {
#     "user_id": "user123",
#     "group_id": "group_123",
#     "score": 75.5,  # 0-100
#     "sub_scores": {
#         "interaction_frequency": 0.8,  # 互动频度
#         "interaction_depth": 0.7,      # 互动深度
#         "emotional_value": 0.75        # 情感价值
#     },
#     "statistics": {
#         "total_interactions": 50,
#         "last_interaction": "2024-01-01T12:00:00",
#         "first_interaction": "2023-12-01T10:00:00",
#         "days_known": 31
#     }
# }
```

#### 批量获取亲密度

```python
# 批量获取多个用户的亲密度
intimacies = await memora_plugin.batch_get_intimacy_api(
    user_ids=["user1", "user2", "user3"],
    group_id="group_123"
)

# 返回格式：List[Dict]，每个元素与上面相同
```

### 3. 用户兴趣API

```python
# 获取用户的TOP 5兴趣
interests = await memora_plugin.get_user_interests_api(
    user_id="user123",
    group_id="group_123"
)

# 返回格式：
# [
#     {"concept": "游戏", "weight": 0.35},
#     {"concept": "音乐", "weight": 0.28},
#     {"concept": "电影", "weight": 0.20},
#     {"concept": "美食", "weight": 0.10},
#     {"concept": "旅行", "weight": 0.07}
# ]
```

### 4. 禁忌词API

```python
# 检查内容是否包含禁忌词
result = await memora_plugin.check_taboo_api(
    user_id="user123",
    content="剧透：最后主角死了",
    group_id="group_123"
)

# 返回格式：
# {
#     "has_taboo": True,
#     "taboo_words": ["剧透"]
# }
```

### 5. 未闭合话题API

```python
# 获取最近7天的未闭合话题
open_topics = await memora_plugin.get_open_topics_api(
    group_id="group_123",
    days=7
)

# 返回格式：
# [
#     {
#         "topic_id": "xyz789",
#         "question": "明天一起去爬山吗？",
#         "asker_id": "user123",
#         "asked_at": "2024-01-01T10:00:00",
#         "days_ago": 2,
#         "context": "我们好久没运动了"
#     },
#     ...
# ]
```

### 6. 历史今日API

```python
# 获取今天的历史今日记忆
anniversaries = await memora_plugin.get_today_anniversaries_api(
    group_id="group_123"
)

# 返回格式：
# [
#     {
#         "memory_id": "mem123",
#         "content": "我们一起去了海边玩",
#         "event_description": "在1年前的今天，我们一起去了海边玩",
#         "days_ago": 365,
#         "original_date": "2023-01-01T15:00:00"
#     },
#     ...
# ]
```

### 7. 关系路径API

```python
# 查找两个用户的关系路径（共同兴趣）
connection = await memora_plugin.find_connection_api(
    user_a="user1",
    user_b="user2",
    group_id="group_123"
)

# 返回格式：
# {
#     "common_topics": ["游戏", "动漫"],
#     "connection_strength": 0.65,
#     "user_a_interests": [
#         {"concept": "游戏", "weight": 0.4},
#         {"concept": "动漫", "weight": 0.3},
#         ...
#     ],
#     "user_b_interests": [
#         {"concept": "游戏", "weight": 0.35},
#         {"concept": "动漫", "weight": 0.25},
#         ...
#     ]
# }
```

### 8. 记忆重要性排序API

```python
# 获取最重要的10条记忆
important_memories = await memora_plugin.get_memory_importance_ranking_api(
    group_id="group_123",
    top_k=10
)

# 返回格式：
# [
#     {
#         "memory_id": "mem456",
#         "content": "第一次见面就成为了好朋友",
#         "importance_score": 0.92,
#         "access_count": 15,
#         "participants": "user1, user2",
#         "created_at": "2023-11-01T10:00:00"
#     },
#     ...
# ]
```

### 9. 事件订阅API

```python
# 订阅记忆事件
async def on_topic_resurrected(event):
    """话题复活事件处理器"""
    print(f"话题复活: {event.data['topic_id']}")
    print(f"沉默了: {event.data['silence_days']} 天")

# 订阅
success = await memora_plugin.subscribe_event_api(
    event_type_str="topic.resurrected",
    callback=on_topic_resurrected
)
```

### 10. 健康检查API

```python
# 检查记忆系统健康状态
health = await memora_plugin.health_check_api()

# 返回格式：
# {
#     "healthy": True,
#     "timestamp": "2024-01-01T12:00:00",
#     "components": {
#         "memory_system": True,
#         "topic_engine": True,
#         "user_profiling": True,
#         "temporal_memory": True
#     },
#     "performance": {
#         "total_requests": 1000,
#         "average_latency_ms": 45.2,
#         "error_count": 5,
#         "error_rate": 0.5,
#         "slow_requests_count": 10
#     },
#     "cache_size": 234
# }
```

---

## 主动插件使用示例

### 示例1：基于亲密度的主动问候

```python
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

@register("active_greeting", "author", "基于亲密度的主动问候", "1.0.0")
class ActiveGreetingPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 获取记忆插件
        memora_meta = context.get_registered_star("astrbot_plugin_memora_connect")
        self.memora = memora_meta.star_cls if memora_meta else None
    
    async def should_greet(self, user_id: str, group_id: str) -> bool:
        """判断是否应该主动问候"""
        if not self.memora:
            return False
        
        # 获取亲密度
        intimacy = await self.memora.get_intimacy_api(user_id, group_id)
        if not intimacy:
            return False
        
        # 只对亲密度 > 60 的用户主动问候
        return intimacy["score"] > 60
    
    @filter.command("问候测试")
    async def test_greeting(self, event: AstrMessageEvent):
        """测试主动问候"""
        user_id = event.get_sender_id()
        group_id = event.get_group_id() or ""
        
        should_greet = await self.should_greet(user_id, group_id)
        if should_greet:
            yield event.plain_result("你好呀！很高兴见到你！😊")
        else:
            yield event.plain_result("嗨~")
```

### 示例2：基于话题的主动发起讨论

```python
@register("active_topic", "author", "基于话题的主动讨论", "1.0.0")
class ActiveTopicPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        memora_meta = context.get_registered_star("astrbot_plugin_memora_connect")
        self.memora = memora_meta.star_cls if memora_meta else None
        
        # 订阅话题复活事件
        if self.memora:
            asyncio.create_task(self._subscribe_events())
    
    async def _subscribe_events(self):
        """订阅记忆事件"""
        await self.memora.subscribe_event_api(
            "topic.resurrected",
            self.on_topic_resurrected
        )
    
    async def on_topic_resurrected(self, event):
        """话题复活事件处理"""
        topic_id = event.data.get("topic_id")
        silence_days = event.data.get("silence_days")
        keywords = event.data.get("keywords", [])
        
        # 主动发起讨论
        message = f"我记得我们 {int(silence_days)} 天前聊过关于 {', '.join(keywords)} 的话题，后来怎么样了？"
        
        # 这里需要根据 event.group_id 发送消息
        # 使用 self.context.send_message() 方法
        # ...
```

### 示例3：基于未闭合话题的主动追问

```python
@register("active_followup", "author", "未闭合话题追问", "1.0.0")
class ActiveFollowupPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        memora_meta = context.get_registered_star("astrbot_plugin_memora_connect")
        self.memora = memora_meta.star_cls if memora_meta else None
        
        # 定时检查未闭合话题
        asyncio.create_task(self._periodic_check())
    
    async def _periodic_check(self):
        """定期检查未闭合话题"""
        while True:
            try:
                await asyncio.sleep(3600)  # 每小时检查一次
                
                # 获取未闭合话题
                open_topics = await self.memora.get_open_topics_api(
                    group_id="",  # 这里应该遍历所有群组
                    days=3
                )
                
                for topic in open_topics:
                    if topic["days_ago"] >= 2:  # 超过2天未回答
                        # 主动追问
                        message = f"对了，{topic['question']} 这个问题后来解决了吗？"
                        # 发送消息...
                        
            except Exception as e:
                print(f"定期检查失败: {e}")
```

---

## 性能优化

### 缓存机制

API网关实现了三级缓存：

1. **L1缓存（内存）**: 缓存最近24小时的热门查询，TTL为1小时
2. **L2缓存（数据库）**: 用户画像和亲密度数据持久化缓存
3. **L3缓存（图谱）**: 记忆图谱持久化存储

### 性能监控

所有API调用都会被监控，可通过 `health_check_api()` 查看性能统计：

- 平均响应时间
- 错误率
- 慢请求数量

---

## 注意事项

1. **异步调用**: 所有API都是异步的，必须使用 `await` 关键字
2. **错误处理**: API调用失败时会返回空值或默认值，请做好错误处理
3. **群组隔离**: 大部分API支持 `group_id` 参数，用于群聊隔离
4. **性能考虑**: 避免频繁调用，善用缓存和批量接口
5. **权限控制**: 部分API可能受到隐私合规层的限制

---

## 升级日志

### v0.3.0 (2024-01-01)

**新增功能：**

- ✅ 实时话题计算引擎
- ✅ 用户画像系统（亲密度、兴趣、禁忌词）
- ✅ 时间维度记忆检索（历史今日、未闭合话题）
- ✅ 事件驱动机制（事件总线）
- ✅ 统一API网关
- ✅ 性能监控和健康检查

**性能优化：**

- ✅ 三级缓存架构
- ✅ 批量查询接口
- ✅ 异步事件处理

**数据库变更：**

- 新增表：`taboo_words` - 禁忌词
- 新增表：`user_interests` - 用户兴趣
- 新增表：`intimacy_cache` - 亲密度缓存
- 新增表：`open_topics` - 未闭合话题
- 新增表：`anniversary_triggers` - 历史今日触发记录

---

## 技术支持

如有问题，请在 GitHub 仓库提交 Issue:
https://github.com/qa296/astrbot_plugin_memora_connect

---

**完成时间**: 2024年
**升级版本**: v0.3.0
**兼容性**: AstrBot >= v3.0.0
