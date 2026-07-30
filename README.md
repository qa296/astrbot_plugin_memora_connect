# AstrBot Memora Connect

<div align="center">

![Version](https://img.shields.io/badge/version-v0.5.2-green?style=for-the-badge) ![AstrBot](https://img.shields.io/badge/AstrBot-plugin-blue?style=for-the-badge)

**模仿海马体的 AI 记忆插件 — 让聊天机器人拥有持久记忆**

</div>

---

## 项目简介

Memora Connect 为 AstrBot 注入类人记忆能力：自动从对话中提取知识图谱节点（人、物、地点...），构建关联网络，并按需召回。记忆会衰减、巩固、联想。

```
对话 → 提取元素 → 构建图谱 → 持久化存储
                                   ↓
LLM 请求 → 多策略召回 → 注入上下文 → 有记忆的对话
```

## 核心能力

| | |
|---|---|
| 🧠 记忆形成 | 自动从对话提取结构化记忆，含情感、强度、参与者 |
| 🔍 五路召回 | 语义向量 · 关键词 · 图联想 · 时间加权 · 强度排序 |
| 🌐 知识图谱 | Element 节点网络（人物/物品/场所/行为/特征），联想扩散 |
| 👤 印象系统 | 对每个人的好感度追踪，自动注入对话上下文 |
| 🔄 记忆维护 | 强度衰减、自动遗忘、定期巩固、相似合并 |
| 👥 群聊隔离 | 每群独立记忆空间，互不干扰 |

## 快速开始

| 命令 | 作用 |
|---|---|
| `/记忆 回忆 [关键词]` | 召回相关记忆 |
| `/记忆 状态` | 查看记忆库统计 |
| `/记忆 印象 [人名]` | 查询对某人的印象 |
| `/记忆 图谱` | 可视化知识图谱 |

LLM 也可以自动调用 `create_memory`、`recall_memory`、`adjust_impression` 等工具。

## 设计理念

> **记忆是联想、衰减、重构的**

该系统借鉴 hippocampal 记忆理论：记忆经历 **编码**（提取）→ **巩固**（存储）→ **回忆**（检索）三阶段。与常规 RAG 不同，我们构建了一个带权知识图谱 —— 每次对话更新实体间的关联强度，使其回忆更像人类的"触类旁通"。

## 项目状态

当前处于 **v0.5.2 beta** — 核心功能稳定，正在从旧架构向新知识图谱迁移

---

**⭐ 如果这个项目对您有帮助，请考虑给我们一个 Star！**

![Star History](https://img.shields.io/github/stars/qa296/astrbot_plugin_memora_connect?style=social)

</div>

## QQ群
因为作者并不经常看issue，所以可以通过QQ群来提醒我！
群号：1098607348
