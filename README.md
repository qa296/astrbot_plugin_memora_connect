# AstrBot Memora Connect

<div align="center">

![AstrBot Memora Connect](https://img.shields.io/badge/AstrBot-Memora%20Connect-blue?style=for-the-badge&logo=robot&logoColor=white)
![Version](https://img.shields.io/badge/version-v0.2.3-green?style=for-the-badge)

**模仿人类记忆方式的智能记忆插件**

[功能特性](#功能特性)  • [使用指南](#使用指南) • [配置说明](#配置说明)

</div>

---

## 📖 项目简介

AstrBot Memora Connect 是一个为 AstrBot 设计的高级记忆插件，通过模仿人类海马体的记忆机制，为 AI 助手提供持久化、智能化的记忆能力。该插件能够自动从对话中提取关键信息，形成结构化的记忆网络，并支持多种回忆模式和智能检索。

### 🎯 核心特性

- **🧠 智能记忆形成**：自动从对话中提取关键信息，形成丰富的记忆内容
- **🔍 多模式回忆**：支持简单关键词、LLM 智能和嵌入向量三种回忆模式
- **🌐 知识图谱**：构建概念间的关联网络，支持联想记忆
- **👥 群聊隔离**：不同群聊的记忆可以隔离.
- **👤 印象系统**：记录和管理对人物的好感度和印象
- **⚡ 性能优化**：嵌入向量缓存、批量处理、异步优化
- **🔄 记忆维护**：自动遗忘、记忆整理和合并机制

---

## ✨ 功能特性

### 🧠 记忆系统
- **自动记忆形成**：基于概率自动从对话中提取记忆点
- **丰富记忆内容**：支持参与者、地点、情感、标签等多维度信息
- **记忆强度管理**：模拟人类记忆的强度衰减和强化机制
- **记忆整理合并**：智能合并相似记忆，保持记忆库的简洁性

### 🔍 回忆机制
- **简单模式**：基于关键词匹配的快速回忆
- **LLM 智能模式**：使用大语言模型进行智能语义回忆
- **嵌入向量模式**：基于语义相似度的向量检索
- **联想回忆**：通过知识图谱进行关联记忆检索
- **时间关联**：基于时间维度的记忆召回

### 🌐 知识图谱
- **概念网络**：构建概念间的有向图结构
- **连接强度**：动态调整概念间的关联强度
- **激活扩散**：模拟人脑的激活扩散回忆机制
- **图优化**：邻接表结构，高效的图遍历算法

### 👥 群聊隔离
- **独立存储**：每个群聊使用独立的数据库文件
- **记忆隔离**：群聊间记忆完全隔离，防止信息泄露
- **自动管理**：自动识别群聊 ID，动态切换数据库
- **统一接口**：对上层提供统一的记忆访问接口

### 👤 印象系统
- **人物印象**：记录对人物的好感度和印象摘要
- **动态调整**：支持好感度的动态增减调整
- **印象历史**：维护印象变更的历史记录
- **智能注入**：在对话中自动注入相关人物印象

### ⚡ 性能优化
- **嵌入向量缓存**：预计算并缓存记忆的嵌入向量
- **批量处理**：批量记忆提取和数据库操作
- **异步优化**：非阻塞的异步任务处理
- **队列管理**：智能的任务队列和优先级管理

---

## 🚀 安装指南


### 🔧 插件安装

1. **下载插件**
```bash
git clone https://github.com/qa296/astrbot_plugin_memora_connect.git
cd astrbot_plugin_memora_connect
```

2. **放置插件目录**
```bash
# 将插件目录复制到 AstrBot 的插件目录
cp -r astrbot_plugin_memora_connect /path/to/astrbot/plugins/
```

3. **启用插件**
```bash
# 在 AstrBot 配置中启用插件
# 或通过管理界面启用 Memora Connect 插件
```

4. **验证安装**
```bash
# 启动 AstrBot 并检查插件是否正常加载
# 查看日志确认插件初始化成功
```

---

## 🎮 使用指南

### 💬 基本命令

插件提供了 `/记忆` 命令组，包含以下子命令：

#### 📝 记忆回忆
```bash
/记忆 回忆 [关键词]
```
- **功能**：根据关键词回忆相关记忆
- **参数**：关键词（可选，不提供时随机回忆）
- **示例**：
  ```
  /记忆 回忆 项目
  /记忆 回忆
  ```

#### 📊 记忆状态
```bash
/记忆 状态
```
- **功能**：显示记忆库的统计信息
- **输出**：记忆数量、概念数量、连接数量等

#### 👤 人物印象
```bash
/记忆 印象 [人物名称]
```
- **功能**：查询指定人物的印象摘要和相关记忆
- **参数**：人物名称
- **示例**：
  ```
  /记忆 印象 张三
  ```

### 🤖 LLM 工具

插件为 LLM 提供了以下工具函数：

#### 📝 创建记忆
```javascript
create_memory({
  content: "需要记录的完整对话内容",
  theme: "核心关键词，用逗号分隔",
  details: "具体细节和背景信息",
  participants: "涉及的人物，用逗号分隔",
  location: "相关场景或地点",
  emotion: "情感色彩，如开心,兴奋",
  tags: "分类标签，如工作,重要",
  confidence: 0.7
})
```

#### 🔍 召回记忆
```javascript
recall_memory("要查询的关键词或内容")
```

#### 👤 调整印象
```javascript
adjust_impression({
  person_name: "人物名称",
  delta: 0.1,           // 好感度调整量，可正可负
  reason: "调整原因和详细信息"
})
```

#### 📝 记录印象
```javascript
record_impression({
  person_name: "人物名称",
  summary: "印象摘要描述",
  score: 0.8,           // 好感度分数 (0-1)，可选
  details: "详细信息"
})
```

### 🔄 自动功能

插件在后台自动运行以下功能：

#### 💭 自动记忆形成
- 监听所有对话消息
- 根据配置的概率自动提取记忆
- 支持批量记忆提取，提高效率

#### 🧠 智能记忆注入
- 在 LLM 请求时自动注入相关记忆
- 基于语义相似度选择最相关的记忆
- 支持人物印象的自动注入

#### 🔄 记忆维护
- 定期执行记忆整理和合并
- 自动遗忘不活跃的记忆
- 优化记忆图结构

---

## ⚙️ 配置说明

### 🔧 基本配置

插件通过 `_conf_schema.json` 定义配置参数，支持以下配置项：

#### 🌐 群聊隔离
```json
{
  "enable_group_isolation": {
    "description": "启用群聊隔离",
    "type": "bool",
    "default": true,
    "hint": "是否启用群聊记忆隔离，防止不同群之间的记忆互相泄露"
  }
}
```

#### 🔄 工作模式
```json
{
  "recall_mode": {
    "description": "主要工作模式",
    "type": "string",
    "options": ["simple", "llm", "embedding"],
    "default": "simple",
    "hint": "选择主要的工作模式，simple：最方便，无需配置，效果最差，llm：允许使用llm工作，embedding：embedding和llm配合工作"
  }
}
```

#### 🧠 记忆管理
```json
{
  "forget_threshold_days": {
    "description": "遗忘阈值天数",
    "type": "int",
    "default": 30,
    "hint": "多少天后开始遗忘不活跃的记忆"
  },
  "consolidation_interval_hours": {
    "description": "记忆整理间隔小时",
    "type": "int",
    "default": 24,
    "hint": "多久进行一次记忆整理和合并"
  },
  "max_memories_per_topic": {
    "description": "每个主题最大记忆数",
    "type": "int",
    "default": 10,
    "hint": "单个主题下最多保留多少条记忆"
  }
}
```

#### 📊 概率控制
```json
{
  "memory_formation_probability": {
    "description": "记忆形成概率",
    "type": "float",
    "default": 0.3,
    "hint": "每条消息形成记忆的概率(0-1)"
  },
  "recall_trigger_probability": {
    "description": "回忆触发概率",
    "type": "float",
    "default": 0.6,
    "hint": "对话中触发回忆的概率(0-1)（此选项使用llm）"
  }
}
```

#### 🤖 LLM 配置
```json
{
  "llm_provider": {
    "description": "LLM服务提供商",
    "type": "string",
    "default": "openai",
    "hint": "选择用于记忆形成的LLM服务提供商，将使用AstrBot配置的对应提供商"
  },
  "llm_system_prompt": {
    "description": "LLM系统提示词",
    "type": "text",
    "default": "你是一个记忆总结助手，请将对话内容总结成简洁自然的记忆。",
    "hint": "用于指导LLM形成记忆的系统提示词"
  }
}
```

#### 🔍 嵌入向量配置
```json
{
  "embedding_provider": {
    "description": "嵌入模型服务提供商",
    "type": "string",
    "default": "openai",
    "hint": "选择嵌入模型的服务提供商，将使用AstrBot配置的对应提供商"
  },
  "embedding_model": {
    "description": "嵌入模型名称",
    "type": "string",
    "default": "",
    "hint": "指定要使用的嵌入模型名称，留空将使用提供商的默认模型"
  }
}
```

#### 🚀 高级功能
```json
{
  "enable_associative_recall": {
    "description": "启用联想回忆",
    "type": "bool",
    "default": true,
    "hint": "是否在llm和embedding模式下启用基于知识图谱的联想回忆功能，会智能补充相关记忆"
  },
  "enable_enhanced_memory": {
    "description": "启用增强记忆功能",
    "type": "bool",
    "default": true,
    "hint": "是否启用增强记忆功能，包括增强召回和自动注入相关记忆到LLM上下文"
  },
  "memory_injection_threshold": {
    "description": "记忆注入阈值",
    "type": "float",
    "default": 0.3,
    "hint": "记忆相关性阈值，低于此值的记忆不会被注入(0-1)"
  }
}
```

### 📋 配置示例

#### 🔧 简单配置
```json
{
  "enable_group_isolation": true,
  "recall_mode": "simple",
  "memory_formation_probability": 0.3,
  "enable_forgetting": true,
  "enable_consolidation": true
}
```

#### 🤖 LLM 模式配置
```json
{
  "enable_group_isolation": true,
  "recall_mode": "llm",
  "llm_provider": "openai",
  "llm_system_prompt": "你是一个专业的记忆助手，请准确总结对话中的关键信息。",
  "memory_formation_probability": 0.5,
  "recall_trigger_probability": 0.7,
  "enable_associative_recall": true
}
```

#### 🔍 嵌入向量模式配置
```json
{
  "enable_group_isolation": true,
  "recall_mode": "embedding",
  "embedding_provider": "openai",
  "embedding_model": "text-embedding-ada-002",
  "llm_provider": "openai",
  "memory_formation_probability": 0.4,
  "enable_enhanced_memory": true,
  "memory_injection_threshold": 0.4,
  "max_injected_memories": 5
}
```

---

## 🛠️ 开发说明

### 📁 项目结构

```
astrbot_plugin_memora_connect/
├── main.py                    # 主插件文件
├── metadata.yaml              # 插件元数据
├── requirements.txt           # 依赖包列表
├── _conf_schema.json          # 配置模式定义
├── database_migration.py      # 数据库迁移系统
├── enhanced_memory_display.py # 增强记忆显示
├── enhanced_memory_recall.py  # 增强记忆召回
├── embedding_cache_manager.py # 嵌入向量缓存管理
└── README.md                  # 项目文档
```

### 🏗️ 架构设计

#### 🧠 核心组件

1. **MemorySystem**：核心记忆系统
   - 记忆形成和管理
   - 多种回忆模式
   - 记忆维护机制

2. **MemoryGraph**：记忆图数据结构
   - 概念节点管理
   - 记忆条目存储
   - 连接关系维护

3. **EnhancedMemoryRecall**：增强记忆召回
   - 多维度召回策略
   - 语义相似度计算
   - 记忆排名和去重

4. **EmbeddingCacheManager**：嵌入向量缓存
   - 向量预计算
   - 缓存管理
   - 语义搜索

5. **BatchMemoryExtractor**：批量记忆提取
   - LLM 批量提取
   - 多类型记忆识别
   - 置信度评估

#### 🔄 数据流程

1. **消息处理流程**
   ```
   消息监听 → 群聊识别 → 记忆提取 → 记忆存储 → 关联建立
   ```

2. **记忆召回流程**
   ```
   查询分析 → 多策略召回 → 结果融合 → 排名去重 → 返回结果
   ```

3. **记忆维护流程**
   ```
   定时触发 → 遗忘检查 → 记忆合并 → 连接优化 → 数据保存
   ```

#### 🐛 问题反馈
- 使用 GitHub Issues 报告 bug
- 提供详细的问题描述和复现步骤
- 包含相关的日志信息和环境信息

#### ✨ 功能建议
- 在 GitHub Discussions 中讨论新功能
- 提供详细的功能需求和使用场景
- 考虑功能的通用性和实现复杂度

### 📊 性能优化

#### ⚡ 已实现的优化
- **嵌入向量缓存**：预计算并缓存记忆的嵌入向量
- **批量处理**：批量记忆提取和数据库操作
- **异步优化**：非阻塞的异步任务处理
- **队列管理**：智能的任务队列和优先级管理
- **数据库优化**：增量更新、事务处理、索引优化

#### 🔧 优化建议
- 定期清理旧的嵌入向量缓存
- 根据实际使用情况调整批量处理大小
- 监控内存使用情况，及时调整缓存大小
- 合理配置记忆形成概率，避免过多无用记忆

---

## ❓ 常见问题

### ⚙️ 配置问题

**Q: 如何选择合适的工作模式？**
A: 根据您的需求选择：
- **Simple 模式**：资源占用最少，适合简单使用场景
- **LLM 模式**：需要配置 LLM 服务，适合智能记忆形成
- **Embedding 模式**：需要配置嵌入向量服务，更加强大

**Q: 群聊隔离功能如何工作？**
A: 群聊隔离功能会：
1. 自动识别消息来源的群聊 ID
2. 为每个群聊创建独立的数据库文件
3. 确保不同群聊间的记忆完全隔离
4. 在群聊间切换时自动加载对应的记忆状态

### 🚀 性能问题

### 🧠 功能问题

**Q: 记忆召回结果不准确？**
A: 优化召回效果的方法：
1. 使用 Embedding 模式提高语义理解
2. 启用联想回忆功能扩展相关记忆
3. 调整 `memory_injection_threshold` 阈值
4. 优化 LLM 系统提示词

**Q: 人物印象功能如何使用？**
A: 人物印象功能的使用方法：
1. 在对话中自然提及人物名称
2. LLM 会自动提取人物印象信息
3. 使用 `/记忆 印象 [人物名称]` 查询印象
4. 通过 LLM 工具手动调整印象分数

---

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件。

---

## 📈 版本历史

### v0.2.3 (当前版本)
- ✨ 新增嵌入向量缓存管理
- 🚀 性能优化和异步处理改进
- 🐛 修复群聊隔离的若干问题
- 📚 完善文档和配置说明

### v0.2.2
- 🔧 增强记忆召回系统
- 👥 人物印象功能优化
- 📊 记忆统计功能完善

### v0.2.1
- 🌐 群聊隔离功能
- 🧠 知识图谱连接优化
- 📝 批量记忆提取功能

### v0.2.0
- 🎉 初始版本发布
- 🧠 基础记忆系统
- 🔍 多模式回忆功能

---

<div align="center">

**⭐ 如果这个项目对您有帮助，请考虑给我们一个 Star！**

![Star History](https://img.shields.io/github/stars/qa296/astrbot_plugin_memora_connect?style=social)

</div>
