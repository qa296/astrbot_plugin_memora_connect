# 记忆系统改进计划

## 项目概述
基于现有AstrBot记忆插件，实现以下核心功能：
1. 记忆回想内容注入用户输入
2. LLM工具调用优化（非固定回复）
3. 增强主动记忆查询的准确性和相关性

## 详细改进方案

### 1. 记忆回想内容注入机制

#### 当前问题
- 回忆的记忆作为独立回复返回，没有融入对话上下文
- 用户需要主动触发回忆，缺乏主动性

#### 解决方案
- 修改 `on_message` 方法，在消息处理前自动注入相关记忆
- 使用AstrBot的上下文系统增强用户输入
- 实现智能记忆触发机制

#### 具体实现
```python
# 新增方法：inject_memories_to_context
async def inject_memories_to_context(self, event: AstrMessageEvent):
    """将相关记忆注入到对话上下文中"""
    # 1. 分析当前消息内容
    current_message = event.message_str
    
    # 2. 基于消息内容召回相关记忆
    relevant_memories = await self.recall_relevant_memories(current_message)
    
    # 3. 将记忆格式化为上下文提示
    if relevant_memories:
        memory_context = self.format_memories_for_context(relevant_memories)
        
        # 4. 注入到AstrBot的上下文中
        event.context_extra["memory_context"] = memory_context
        
    return event
```

### 2. LLM工具优化

#### 当前问题
- LLM工具返回固定格式的回复
- 打断LLM的自然回复流程

#### 解决方案
- 修改LLM工具返回空值，让LLM继续自然回复
- 使用系统提示词注入记忆内容
- 实现记忆内容的隐式引用

#### 具体实现
```python
# 修改后的LLM工具
@filter.llm_tool(name="create_memory")
async def create_memory_tool(self, event: AstrMessageEvent, content: str, topic: str) -> MessageEventResult:
    """创建记忆但不返回固定回复"""
    try:
        concept_id = self.memory_system.memory_graph.add_concept(topic)
        memory_id = self.memory_system.memory_graph.add_memory(content, concept_id)
        logger.info(f"LLM工具创建记忆：{topic} -> {content}")
        # 返回空值，让LLM继续自然回复
        yield event.plain_result("")
    except Exception as e:
        logger.error(f"LLM工具创建记忆失败：{e}")
        yield event.plain_result("")

@filter.llm_tool(name="recall_memory")
async def recall_memory_tool(self, event: AstrMessageEvent, keyword: str) -> MessageEventResult:
    """查询记忆但不返回固定回复"""
    try:
        memories = await self.memory_system.recall_memories(keyword, event)
        if memories:
            # 将记忆注入系统提示词
            memory_text = "\n".join(memories)
            event.context_extra["recalled_memories"] = memory_text
        yield event.plain_result("")  # 返回空值
    except Exception as e:
        logger.error(f"LLM工具回忆记忆失败：{e}")
        yield event.plain_result("")
```

### 3. 增强记忆查询准确性

#### 当前问题
- 关键词匹配过于简单
- 缺乏语义理解
- 相关性排序不够智能

#### 解决方案
- 实现语义相似度计算
- 添加上下文感知
- 使用LLM进行智能匹配

#### 具体实现
```python
# 新增方法：智能记忆召回
async def recall_relevant_memories(self, message: str, event: AstrMessageEvent) -> List[str]:
    """基于消息内容智能召回相关记忆"""
    # 1. 提取关键词和主题
    keywords = await self.extract_keywords_from_message(message)
    
    # 2. 语义相似度计算
    semantic_memories = await self.semantic_search(message)
    
    # 3. 上下文感知召回
    context_memories = await self.context_aware_recall(message, event)
    
    # 4. 综合排序和去重
    all_memories = semantic_memories + context_memories
    unique_memories = self.deduplicate_and_rank(all_memories)
    
    return unique_memories[:3]  # 返回最相关的3条

# 新增方法：语义搜索
async def semantic_search(self, query: str) -> List[str]:
    """基于语义相似度的记忆搜索"""
    if not self.memory_graph.memories:
        return []
    
    # 使用嵌入向量计算相似度
    query_embedding = await self.get_embedding(query)
    if not query_embedding:
        return []
    
    similarities = []
    for memory in self.memory_graph.memories.values():
        memory_embedding = await self.get_embedding(memory.content)
        if memory_embedding:
            similarity = self._cosine_similarity(query_embedding, memory_embedding)
            similarities.append((memory.content, similarity))
    
    # 按相似度排序
    similarities.sort(key=lambda x: x[1], reverse=True)
    return [content for content, sim in similarities if sim > 0.4]
```

### 4. 记忆注入上下文处理

#### 实现方案
```python
# 新增方法：格式化记忆为上下文
def format_memories_for_context(self, memories: List[str]) -> str:
    """将记忆格式化为适合LLM理解的上下文"""
    if not memories:
        return ""
    
    formatted = "根据之前的对话记忆：\n"
    for i, memory in enumerate(memories, 1):
        formatted += f"{i}. {memory}\n"
    formatted += "\n请基于这些记忆来理解当前对话的上下文。"
    
    return formatted

# 修改 on_message 方法
@filter.event_message_type(filter.EventMessageType.ALL)
async def on_message(self, event: AstrMessageEvent):
    """监听所有消息，注入记忆上下文"""
    # 1. 注入相关记忆到上下文
    await self.memory_system.inject_memories_to_context(event)
    
    # 2. 处理消息形成新记忆
    await self.memory_system.process_message(event)
```

### 5. 配置优化

#### 新增配置项
```json
{
  "auto_inject_memories": {
    "description": "自动注入记忆到上下文",
    "type": "bool",
    "hint": "是否在每次对话时自动将相关记忆注入到LLM上下文中",
    "default": true
  },
  "memory_injection_threshold": {
    "description": "记忆注入阈值",
    "type": "float",
    "hint": "记忆与当前消息的相关度阈值，高于此值的记忆才会被注入",
    "default": 0.5
  },
  "max_injected_memories": {
    "description": "最大注入记忆数",
    "type": "int",
    "hint": "每次对话最多注入多少条相关记忆",
    "default": 3
  }
}
```

## 实施步骤

1. **第一阶段**：实现记忆注入机制
   - 添加 `inject_memories_to_context` 方法
   - 修改 `on_message` 方法

2. **第二阶段**：优化LLM工具
   - 修改 `create_memory_tool` 和 `recall_memory_tool`
   - 实现空值返回机制

3. **第三阶段**：增强查询准确性
   - 实现语义搜索
   - 添加上下文感知召回

4. **第四阶段**：测试和调优
   - 测试各种场景下的记忆注入效果
   - 调整相关度阈值和参数

## 预期效果

1. **用户体验提升**：记忆内容自然融入对话，无需手动触发
2. **回复质量提高**：LLM基于历史记忆提供更连贯的回复
3. **查询准确性增强**：更精准地召回相关记忆
4. **系统智能化**：主动记忆管理，减少用户操作

## 注意事项

1. 保持向后兼容性，不影响现有功能
2. 控制记忆注入的数量，避免上下文过长
3. 处理好记忆的相关性过滤，避免不相关记忆干扰
4. 确保系统性能，避免频繁的数据库查询