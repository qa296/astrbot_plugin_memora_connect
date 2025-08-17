# AstrBot 记忆插件 (Memora Connect)

一个模仿人类海马体功能的记忆系统插件，基于知识图谱构建记忆网络，实现概念节点和关系连接的智能记忆存储。

## 🧠 功能特性

### 核心记忆机制
- **记忆形成**: 自动从对话中提取主题，形成口语化记忆
- **记忆回忆**: 基于关键词或上下文触发相关记忆
- **记忆遗忘**: 模拟人类遗忘机制，不活跃记忆逐渐淡化
- **记忆整理**: 定期合并相似记忆，保持记忆库精简高效

### 智能特性
- **双峰时间回忆**: 优先回忆"不久前"和"很久以前"的记忆
- **关系网络**: 建立概念间的关联，形成知识图谱
- **自适应强度**: 记忆和连接的强度随使用频率动态调整
- **多模式支持**: 支持simple、LLM、embedding三种回忆模式
- **灵活配置**: 支持自定义LLM和嵌入模型提供商

## 🚀 快速开始

### 安装
1. 将插件放入 `AstrBot/data/plugins/` 目录
2. 重启AstrBot
3. 在WebUI中启用插件

### 基本使用

#### 记忆指令
```
/记忆           - 显示记忆系统状态
/记忆 回忆 [关键词] - 回忆相关记忆
/记忆 状态       - 查看记忆统计信息
```

#### 自动记忆
插件会自动监听对话，智能形成记忆。无需手动操作。

## ⚙️ 配置说明

在WebUI的插件配置页面，可以调整以下参数：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| recall_mode | 回忆模式(simple/llm/embedding) | llm |
| llm_provider | LLM服务提供商 | openai |
| embedding_provider | 嵌入模型服务提供商 | openai |
| embedding_model | 嵌入模型名称(留空使用默认) | "" |
| forget_threshold_days | 遗忘阈值天数 | 30 |
| consolidation_interval_hours | 记忆整理间隔 | 24 |
| max_memories_per_topic | 每主题最大记忆数 | 10 |
| memory_formation_probability | 记忆形成概率 | 0.3 |
| recall_trigger_probability | 回忆触发概率 | 0.2 |
| enable_forgetting | 启用遗忘机制 | true |
| enable_consolidation | 启用记忆整理 | true |
| bimodal_recall | 双峰时间回忆 | true |
| llm_system_prompt | LLM系统提示词 | 你是一个记忆总结助手，请将对话内容总结成简洁自然的记忆。 |

## 🎯 使用示例

### 场景1：日常对话记忆
```
用户: 我今天去了图书馆，看了一本关于人工智能的书
用户: /记忆 回忆 图书馆
机器人: 我记得你说过今天去了图书馆看人工智能的书
```

### 场景2：项目跟踪
```
用户: 我们的项目下周要开始测试了
用户: 明天记得提醒我项目的事情
机器人: 我记得我们的项目下周要开始测试了
```

### 场景3：个人偏好记忆
```
用户: 我喜欢喝美式咖啡，不加糖
用户: /记忆 回忆 咖啡
机器人: 我记得你喜欢喝不加糖的美式咖啡
```

## 🔧 技术架构

### 数据结构
- **Concept(概念)**: 记忆的主题节点
- **Memory(记忆)**: 具体的记忆内容
- **Connection(连接)**: 概念间的关系

### LLM和嵌入模型配置
支持使用AstrBot配置的任何提供商：

#### LLM提供商
- **openai**: OpenAI GPT系列
- **azure**: Azure OpenAI
- **zhipu**: 智谱AI
- **moonshot**: 月之暗面
- **其他**: 任何在AstrBot中配置的提供商

#### 嵌入模型提供商
- **openai**: text-embedding-ada-002, text-embedding-3-small, text-embedding-3-large
- **azure**: 通过Azure配置的嵌入模型
- **zhipu**: 通过智谱配置的嵌入模型
- **其他**: 任何支持嵌入功能的提供商

#### 配置示例
```json
{
  "recall_mode": "llm",
  "llm_provider": "openai",
  "llm_system_prompt": "你是一个记忆总结助手，请将对话内容总结成简洁自然的记忆。"
}
```

```json
{
  "recall_mode": "embedding",
  "embedding_provider": "zhipu",
  "embedding_model": ""
}
```

### 存储机制
- 使用SQLite数据库存储记忆网络
- 支持持久化，重启不丢失
- 定期自动保存和整理

### 回忆算法
1. **关键词匹配**: 基于文本相似度
2. **LLM理解**: 使用配置的大语言模型理解语义
3. **Embedding**: 使用配置的嵌入模型进行高精度匹配

## 📊 记忆统计

插件会记录以下统计信息：
- 概念节点数量
- 记忆条目总数
- 关系连接数量
- 活跃记忆比例
- 当前使用的LLM提供商

## 🎛️ 高级功能

### 双峰时间回忆
系统会优先回忆：
- 最近几小时到一天内的记忆
- 几天前的记忆
- 对"昨天"的记忆关注度较低

### 记忆整理
定期执行：
- 合并相似记忆
- 移除冗余信息
- 优化记忆结构

## 🔍 调试与监控

### 日志查看
插件日志会记录：
- 记忆形成过程
- 回忆触发事件
- 遗忘和整理操作
- 使用的LLM提供商信息

### 手动操作
```
# 查看所有记忆
/记忆 状态

# 回忆特定主题
/记忆 回忆 工作

# 触发记忆整理
/记忆 整理
```

## 🐛 常见问题

### Q: 记忆没有形成？
A: 检查memory_formation_probability配置，确保对话有足够信息量

### Q: 回忆不准确？
A: 尝试切换recall_mode到"llm"或"embedding"模式，并检查llm_provider配置

### Q: 记忆太多导致性能问题？
A: 降低max_memories_per_topic和forget_threshold_days的值

### Q: 如何切换LLM提供商？
A: 在WebUI中修改llm_provider配置，支持openai、azure、zhipu等

MIT License - 详见LICENSE文件
