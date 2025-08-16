# 🧠 memora_connect - 记忆插件

**一个模仿生物海马体，为 AstrBot 赋予长期记忆能力的插件。**

`astrbot_plugin_memora_connect` 不仅仅是一个聊天记录工具，它构建了一个动态的、自组织的记忆网络。通过模拟生物的记忆形成、联想、遗忘和巩固过程，让您的 AstrBot 能够真正“记住”并“理解”过去的对话。

---

## ✨ 核心特性

- **🧠 动态记忆网络**: 所有记忆都存储在一个由“概念节点”和“关系连接”组成的知识图谱中，能够自动发现并连接相关信息。
- **✍️ 智能记忆形成**: 自动从长对话中学习，提炼核心主题，并将其转化为口语化的记忆存入网络。
- **🔍 联想回忆**: 通过 `/recall` 指令，您可以提出一个关键词，插件会像人脑一样，从这个点开始“联想”，激活记忆网络中所有相关的记忆。
- **💧 模拟遗忘**: 为了保持记忆库的高效和准确，长时间不被访问的记忆会像人的记忆一样逐渐“淡忘”。
- **🧩 自动巩固**: 插件会定期整理记忆，将相似的记忆片段融合成一个更完整、更丰富的记忆，实现“温故而知新”。
- **🤖 多模型支持**: 您可以在 `simple`、`llm` 和 `embedding` 三种模式间自由切换，以平衡性能和智能程度。
- **⚙️ 高度可配置**: 插件的核心参数，如记忆灵敏度、遗忘周期等，均可在管理面板中进行调整。
- **💾 持久化存储**: 所有记忆都会被安全地保存，即使 AstrBot 重启，记忆也不会丢失。

---

## 🚀 快速上手

1.  **安装插件**: 在 AstrBot 的插件市场中安装 `astrbot_plugin_memora_connect`。
2.  **（可选）调整配置**: 前往 AstrBot 管理面板 -> 插件管理 -> astrbot_plugin_memora_connect，根据您的需求调整配置项。
3.  **自动记忆**: 插件安装后会自动开始工作。在日常聊天中，长度超过您设定的最小值的非指令消息都会被插件学习。
4.  **回忆记忆**: 当您想回忆某件事时，请使用以下指令：

    ```
    /recall <您想回忆的关键词>
    ```
    或者
    ```
    /回忆 <您- **仓库**: [astrbot_plugin_memora_connect](https://github.com/qa296/astrbot_plugin_memora_connect)
想回忆的关键词>
    ```

    **示例:**
    `/recall 关于项目A的讨论`

---

## ⚙️ 配置指南

插件的所有配置都可以在 AstrBot 的管理面板中进行可视化调整。

### 主要配置

| 配置项 | 描述 | 默认值 |
| :--- | :--- | :--- |
| `model_type` | 选择用于处理记忆的模型。`simple` 性能最高，`embedding` 效果最好。 | `simple` |
| `auto_memory_min_length` | 自动形成记忆的最小消息长度。 | `10` |
| `recall_max_results` | 使用 `/recall` 指令时返回的最大记忆条数。 | `3` |

### 高级配置

| 配置项 | 描述 | 默认值 |
| :--- | :--- | :--- |
| `forgetting_threshold_days` | 记忆开始被遗忘的时间阈值（天）。 | `30` |
| `consolidation_similarity_threshold` | **(simple 模型)** 合并记忆的相似度阈值。 | `0.7` |
| `embedding_similarity_threshold` | **(embedding 模型)** 合并记忆的相似度阈值。 | `0.8` |
| `forgetting_interval_hours` | 执行遗忘检查的定时任务周期（小时）。 | `6` |
| `consolidation_interval_days` | 执行巩固检查的定时任务周期（天）。 | `1` |

---

## 🤝 支持

- **文档**: [AstrBot 官方文档](https://astrbot.app)
- **作者**: qa296
- **仓库**: [astrbot_plugin_memora_connect](https://github.com/qa296/astrbot_plugin_memora_connect)
