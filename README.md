# astrbot_plugin_memora_connect

一个模仿人类记忆方式的 AstrBot 插件，通过“概念-记忆-连接”机制，让机器人能够形成、回忆和遗忘对话中的信息，就像人类的海马体一样。

## 功能特性

- **对话记忆**：自动将聊天内容提炼为记忆。
- **主题提取**：使用 LLM 或关键词分析提取核心主题。
- **记忆回忆**：支持关键词查询、随机回忆、语义检索。
- **记忆整理**：定期合并相似记忆，避免冗余。
- **遗忘机制**：长时间未使用的记忆会逐渐淡化并被移除。
- **上下文注入**：相关记忆会自动注入对话上下文，增强连贯性。

## 使用方法

### 激活与指令
- `/记忆`  
  激活记忆系统。  
- `/记忆 回忆 <关键词>`  
  查询与关键词相关的记忆。  
- `/记忆 状态`  
  查看记忆系统当前状态。

### LLM 工具接口
- `create_memory(content, topic)`  
  主动将一段对话保存为记忆。  
- `recall_memory(keyword)`  
  查询与关键词相关的记忆并返回到上下文。

## 配置选项

在插件初始化时可设置参数（默认值如下）：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `recall_mode` | `llm` | 回忆模式（`simple` / `llm` / `embedding`） |
| `enable_associative_recall` | `true` | 是否启用联想回忆 |
| `forget_threshold_days` | `30` | 多少天未访问的记忆会被遗忘 |
| `consolidation_interval_hours` | `24` | 记忆整理的时间间隔 |
| `max_memories_per_topic` | `10` | 每个主题的最大记忆数 |
| `memory_formation_every_n` | `5` | 每 N 条消息形成一次记忆 |
| `recall_trigger_probability` | `0.2` | 随机触发回忆的概率 |
| `enable_forgetting` | `true` | 是否启用遗忘机制 |
| `enable_consolidation` | `true` | 是否启用记忆整理 |
| `bimodal_recall` | `true` | 是否启用双模式回忆（主题+语义） |
| `llm_provider` | `openai` | LLM 服务商 |
| `embedding_provider` | `openai` | 向量嵌入服务商 |

## 数据存储

- 插件使用 SQLite 数据库存储记忆，路径默认为：
```

<数据目录>/memora\_connect/memory.db

```
- 数据结构包含：
- **concepts**：概念节点
- **memories**：记忆条目
- **connections**：概念之间的连接关系

## 安装与使用

1. 将插件放入 AstrBot 插件目录。
2. 确保已配置好所需的 LLM 与 Embedding Provider（如 OpenAI）。
3. 启动 AstrBot，插件会自动运行并建立记忆数据库。

## 开发者信息

- 插件名：`astrbot_plugin_memora_connect`  
- 作者：[@qa296](https://github.com/qa296)  
- 版本：`v0.1.0`  
- 仓库：[GitHub](https://github.com/qa296/astrbot_plugin_memora_connect)

---

✨ 通过这个插件，你的 Bot 将拥有“类人记忆”，不仅能记住对话，还能像人一样整理和遗忘信息。
```
