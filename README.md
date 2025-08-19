# astrbot_plugin_memora_connect

一个模仿人类记忆方式的 AstrBot 插件，通过“概念-记忆-连接”机制，让机器人能够形成、回忆和遗忘对话中的信息，就像人类的海马体一样。

## 功能特性

- **丰富对话记忆**：自动将聊天内容提炼为包含**细节、参与者、地点、情感、标签**的丰富记忆。
- **多层置信度**：区分重要事件、日常小事和有趣细节，使记忆系统更具层次感。
- **主题提取**：使用 LLM 或关键词分析提取核心主题。
- **增强记忆召回**：多维度智能召回系统，包括：
  - **语义召回**：基于嵌入向量的语义相似度
  - **关键词召回**：精确和模糊关键词匹配
  - **联想召回**：通过概念网络激活扩散
  - **时间召回**：基于时间相关性的记忆检索
  - **强度召回**：基于记忆强度和访问频率
- **记忆整理**：定期合并相似记忆，避免冗余。
- **遗忘机制**：长时间未使用的记忆会逐渐淡化并被移除。
- **上下文注入**：相关记忆会自动注入对话上下文，增强连贯性。
- **详细记忆展示**：通过指令可以查看记忆的完整信息，包括强度、访问次数等。

## 使用方法

### 激活与指令
- `/记忆`
  激活记忆系统。
- `/记忆 回忆 <关键词>`
  查询与关键词相关的记忆，并以卡片形式展示详细信息。
- `/记忆 状态`
  查看记忆系统当前状态的详细统计。

### LLM 工具接口
- `create_memory(content, topic)`
  主动将一段对话保存为记忆。
- `recall_memory(keyword)`
  查询与关键词相关的记忆并返回到上下文。
- `recall_all_memories(query)`
  使用增强系统召回所有相关记忆，包括联想记忆。

## 配置选项

在插件初始化时可设置参数（默认值如下）：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `recall_mode` | `llm` | 回忆模式（`simple` / `llm` / `embedding`） |
| `enable_associative_recall` | `true` | 是否启用联想回忆 |
| `forget_threshold_days` | `30` | 多少天未访问的记忆会被遗忘 |
| `consolidation_interval_hours` | `24` | 记忆整理的时间间隔 |
| `max_memories_per_topic` | `10` | 每个主题的最大记忆数 |
| `memory_formation_probability` | `0.3` | 形成记忆的概率 |
| `recall_trigger_probability` | `0.6` | 随机触发回忆的概率 |
| `enable_forgetting` | `true` | 是否启用遗忘机制 |
| `enable_consolidation` | `true` | 是否启用记忆整理 |
| `bimodal_recall` | `true` | 是否启用双模式回忆（主题+语义） |
| `llm_provider` | `openai` | LLM 服务商 |
| `embedding_provider` | `openai` | 向量嵌入服务商 |
| `max_injected_memories` | `5` | 注入上下文的最大记忆数 |
| `enable_enhanced_recall` | `true` | 是否启用增强记忆召回系统 |
| `memory_injection_threshold` | `0.3` | 记忆注入的相似度阈值 |
| `auto_inject_memories` | `true` | 是否自动注入相关记忆到上下文 |

## 数据存储

- 插件使用 SQLite 数据库存储记忆，路径默认为：
```
<数据目录>/memora_connect/memory.db
```
- 数据结构包含：
- **concepts**：概念节点
- **memories**：记忆条目（已扩展支持详细信息）
- **connections**：概念之间的连接关系

## 安装与使用

1. 将插件放入 AstrBot 插件目录。
2. 确保已配置好所需的 LLM 与 Embedding Provider（如 OpenAI）。
3. 启动 AstrBot，插件会自动运行并建立记忆数据库。

## 开发者信息

- 插件名：`astrbot_plugin_memora_connect`
- 作者：[@qa296](https://github.com/qa296)
- 版本：`v0.2.0`
- 仓库：[GitHub](https://github.com/qa296/astrbot_plugin_memora_connect)

---

✨ 通过这个插件，你的 Bot 将拥有"类人记忆"，不仅能记住对话，还能像人一样整理和遗忘信息。增强记忆召回系统让记忆更加智能和精准！
