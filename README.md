# AstrBot Memora Connect

<div align="center">

![Version](https://img.shields.io/badge/version-v0.7.0-green?style=for-the-badge) ![AstrBot](https://img.shields.io/badge/AstrBot-plugin-blue?style=for-the-badge)

**模仿海马体的 AI 记忆插件 — 让聊天机器人拥有持久记忆**

</div>

---

## 项目简介

Memora Connect 为 AstrBot 注入类人记忆能力：LLM 自动从对话中提取记忆、人物、地点与关系，写入单库 SQLite（按聊天气候离），并在每次 LLM 请求前按相关度召回注入。

```
对话 → 空闲/阈值触发 LLM 分析 → 记忆/要素/关系/印象 UPSERT 落库
                                            ↓
LLM 请求 → 关键词 + 图联想 (+语义向量) 三路召回融合 → 注入上下文
```


## 核心能力

| | |
|---|---|
| 🧠 记忆形成 | 空闲 60s 或攒满阈值消息后，一次 LLM 调用批量分析会话，产出记忆、要素、关系、印象 |
| 🔍 三路召回 | 关键词（FTS5 trigram）· 图联想（要素倒排 + 邻接）· 语义向量（可选，需 embedding provider） |
| 🌐 知识图谱 | 要素节点 + 带语义关系的边，每条边由 LLM 提取 |
| 👤 印象系统 | 每人独立好感度评分与摘要，独立于记忆强度 |
| 👥 群聊隔离 | 每群/每私聊独立记忆空间（scope_id），互不干扰 |

## 快速开始

| 命令 | 作用 |
|---|---|
| `/记忆 回忆 [关键词]` | 手动召回相关记忆 |
| `/记忆 状态` | 查看记忆库统计 |
| `/记忆 印象 [人名]` | 查询对某人的印象 |
| `/记忆 图谱 [布局]` | 可视化知识图谱（需可选依赖 matplotlib/networkx） |

LLM 也会自动调用 `create_memory`、`recall_memory`、`delete_memory`、`adjust_impression`、`record_impression` 五个工具。

## 配置要点

- `recall_weight_keyword / semantic / graph`：召回权重，可调、自动归一。
- `group_chat_memory_mode`：群聊记忆收集范围（at_only 仅 @机器人 的消息；all 收全部群消息）。
- `enable_embedding_recall`：开启语义召回（需 AstrBot 可用的 embedding provider）。
- `formation_idle_flush_seconds` / `topic_message_threshold`：会话分析触发时机。
- `memory_injection_threshold`：注入上下文的最低相关度。

全部配置项与默认值见 `_conf_schema.json` 及 WebUI 插件配置页。

---

**⭐ 如果这个项目对您有帮助，请考虑给我们一个 Star！**

![Star History](https://img.shields.io/github/stars/qa296/astrbot_plugin_memora_connect?style=social)

</div>

## QQ群
因为作者并不经常看issue，所以可以通过QQ群来提醒我！
群号：1098607348
