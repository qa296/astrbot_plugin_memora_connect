# 记忆工具增强修改计划

## 目标
将现有的`create_memory_tool`从只有两个参数（content, topic）扩展为支持丰富参数的批量记忆提取器格式。

## 当前实现分析
- 当前函数：`create_memory_tool(self, event: AstrMessageEvent, content: str, topic: str)`
- 仅支持：content（内容）和 topic（主题）
- 调用方式：`create_memory(content="...", topic="...")`

## 新的参数结构
基于BatchMemoryExtractor的格式，新的参数应该包括：

### 必需参数
- **content** (str): 需要记录的完整对话内容
- **theme** (str): 该记忆所属的主题或关键词，用逗号分隔

### 可选参数
- **details** (str, 默认=""): 具体细节和背景信息
- **participants** (str, 默认=""): 涉及的人物，用逗号分隔
- **location** (str, 默认=""): 相关场景或地点
- **emotion** (str, 默认=""): 情感色彩，如"开心,兴奋"
- **tags** (str, 默认=""): 分类标签，如"工作,重要"
- **confidence** (float, 默认=0.7): 置信度，0-1之间的数值

## 修改方案

### 1. 函数签名修改
```python
@filter.llm_tool(name="create_memory")
async def create_memory_tool(
    self, 
    event: AstrMessageEvent, 
    content: str, 
    theme: str, 
    details: str = "", 
    participants: str = "", 
    location: str = "", 
    emotion: str = "", 
    tags: str = "", 
    confidence: float = 0.7
) -> MessageEventResult:
```

### 2. 向后兼容性
- 保留原有的`topic`参数作为`theme`的别名
- 在函数内部将`topic`映射到`theme`
- 所有新参数都有默认值，确保不会破坏现有调用

### 3. 实现逻辑更新
- 使用MemoryGraph.add_memory的完整参数
- 添加参数验证和清理
- 支持置信度调整记忆强度

### 4. 文档更新
- 更新函数文档字符串
- 在README.md中添加使用示例
- 更新metadata.yaml中的功能描述

## 实施步骤

1. **修改函数签名** (main.py:113-128)
2. **更新实现逻辑** (main.py:120-128)
3. **添加参数验证** (新增验证逻辑)
4. **更新文档字符串** (main.py:114-119)
5. **测试兼容性** (确保新旧调用都支持)

## 使用示例

### 新用法（丰富参数）
```
/create_memory(
    content="今天完成了项目演示，客户很满意",
    theme="工作,项目,演示",
    details="上午10点在会议室进行了产品演示，展示了新功能",
    participants="我,客户,项目经理",
    location="会议室",
    emotion="兴奋,满意",
    tags="重要,成功",
    confidence=0.9
)
```

### 旧用法（向后兼容）
```
/create_memory(
    content="今天完成了项目演示",
    theme="工作"
)
```

## 技术细节

### 参数处理
- 所有字符串参数自动清理特殊字符
- confidence值限制在0.0-1.0范围
- 空字符串参数会被忽略

### 记忆强度计算
- 基础强度：1.0
- 根据confidence调整：strength = 1.0 * confidence

### 错误处理
- 参数验证失败时返回空字符串
- 记录详细错误日志
- 不影响LLM正常流程