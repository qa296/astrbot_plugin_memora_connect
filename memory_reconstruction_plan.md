# 记忆插件函数工具重构计划

## 目标
将 `recall_all_memories` 和 `recall_memory` 两个函数工具合并为一个增强的 `recall_memory` 工具，使用完整的增强记忆召回系统。

## 当前状态分析

### 现有函数工具
1. **recall_all_memories_tool** (第149-174行)
   - 功能：使用增强系统召回所有相关记忆，包括联想记忆
   - 参数：query(string) - 要查询的内容
   - 实现：使用EnhancedMemoryRecall.recall_all_relevant_memories()

2. **recall_memory_tool** (第130-147行)
   - 功能：主动查询与关键词相关的记忆
   - 参数：keyword(string) - 要查询的关键词
   - 实现：使用简单的关键词匹配

### 需要移除的内容
- [ ] 移除recall_all_memories_tool函数（第149-174行）
- [ ] 移除recall_memory_tool函数（第130-147行）

### 需要新增的函数
- [ ] 创建新的recall_memory工具，整合增强功能

## 实施步骤

### 步骤1：移除旧的函数工具
删除以下代码段：
- 第130-147行：recall_memory_tool
- 第149-174行：recall_all_memories_tool

### 步骤2：创建新的增强recall_memory工具
在create_memory_tool之后添加新的函数：

```python
@filter.llm_tool(name="recall_memory")
async def recall_memory_tool(self, event: AstrMessageEvent, keyword: str) -> MessageEventResult:
    """使用增强系统召回所有相关记忆，包括联想记忆。
    Args:
        keyword(string): 要查询的关键词或内容
    """
    try:
        from .enhanced_memory_recall import EnhancedMemoryRecall
        
        enhanced_recall = EnhancedMemoryRecall(self.memory_system)
        results = await enhanced_recall.recall_all_relevant_memories(
            query=keyword,
            max_memories=8
        )
        
        if results:
            # 生成增强的上下文
            formatted_memories = enhanced_recall.format_memories_for_llm(results)
            yield event.plain_result(formatted_memories)
        else:
            # 返回空字符串让LLM继续其自然回复流程
            yield event.plain_result("")
            
    except Exception as e:
        logger.error(f"增强记忆召回工具失败：{e}")
        yield event.plain_result("")
```

### 步骤3：验证修改
- [ ] 确保新的recall_memory工具使用EnhancedMemoryRecall
- [ ] 验证参数名称和描述符合新功能
- [ ] 测试工具是否能正常工作

## 技术细节

### 使用的增强功能
- 语义相似度搜索
- 关键词匹配
- 联想记忆召回
- 时间关联召回
- 记忆强度排序
- 多维度相关性评分

### 配置参数
- max_memories: 8 (与原来的recall_all_memories一致)
- 包含所有记忆类型（语义、关键词、联想、时间、强度）

## 回滚计划
如果需要回滚，可以：
1. 恢复被删除的原始函数工具代码
2. 移除新的recall_memory工具
3. 重新添加原始的recall_all_memories_tool和recall_memory_tool

## 测试建议
1. 使用关键词测试新的recall_memory工具
2. 验证联想记忆功能是否正常工作
3. 检查语义搜索是否有效
4. 确认记忆注入功能不受影响