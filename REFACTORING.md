# main.py 解耦重构说明

## 概述

本次重构将原本 4093 行的 `main.py` 解耦为多个独立模块，提高了代码的可维护性和可读性。

## 重构内容

### 新增模块

1. **models.py** - 数据模型定义
   - `Concept` - 概念节点数据类
   - `Memory` - 记忆条目数据类
   - `Connection` - 概念连接数据类

2. **config.py** - 配置管理
   - `MemorySystemConfig` - 记忆系统配置类
   - `MemoryConfigManager` - 配置管理器

3. **memory_graph.py** - 记忆图数据结构
   - `MemoryGraph` - 管理概念节点、记忆和连接的图结构
   - 提供添加、删除、更新概念、记忆和连接的方法
   - 维护邻接表以优化图操作

4. **batch_extractor.py** - 批量记忆提取
   - `BatchMemoryExtractor` - 通过 LLM 批量提取记忆和主题
   - 支持从对话历史中提取人物印象
   - 包含回退机制和 JSON 解析容错

5. **memory_system_core.py** - 核心记忆系统
   - `MemorySystem` - 核心记忆系统类（2333行）
   - 实现记忆的形成、提取、遗忘、巩固等功能
   - 支持群聊隔离、异步任务管理、缓存优化

### 优化后的 main.py

重构后的 `main.py` 仅保留 740 行，主要包含：
- `MemoraConnectPlugin` - 插件主类
- 命令处理器（回忆、状态、印象、图谱等）
- 事件监听器和钩子
- 插件 API 接口
- LLM 工具函数

## 代码统计

| 文件 | 行数 | 说明 |
|------|------|------|
| main_old.py | 4093 | 原始文件 |
| **main.py** | **740** | **重构后主文件 (-82%)** |
| models.py | 60 | 数据模型 |
| config.py | 120 | 配置管理 |
| memory_graph.py | 207 | 记忆图结构 |
| batch_extractor.py | 462 | 批量提取器 |
| memory_system_core.py | 2358 | 核心系统 |

## 架构改进

### 解耦前
```
main.py (4093行)
├── MemoraConnectPlugin
├── MemorySystemConfig
├── MemoryConfigManager
├── MemorySystem (2333行)
├── BatchMemoryExtractor
├── MemoryGraph
├── Concept
├── Memory
└── Connection
```

### 解耦后
```
main.py (740行)
└── MemoraConnectPlugin (插件入口)

models.py
├── Concept
├── Memory
└── Connection

config.py
├── MemorySystemConfig
└── MemoryConfigManager

memory_graph.py
└── MemoryGraph

batch_extractor.py
└── BatchMemoryExtractor

memory_system_core.py
└── MemorySystem
```

## 优势

1. **可维护性提升**
   - 职责明确，每个模块专注于特定功能
   - 减少代码耦合，便于独立修改和测试

2. **可读性提升**
   - 文件大小合理，易于阅读和理解
   - 模块化结构清晰，降低认知负担

3. **可扩展性提升**
   - 新功能可以作为独立模块添加
   - 不会影响现有代码结构

4. **团队协作友好**
   - 减少代码冲突的可能性
   - 便于代码审查和版本控制

## 向后兼容

本次重构**完全向后兼容**，所有外部接口保持不变：
- 插件 API 接口不变
- LLM 工具函数不变
- 命令处理器不变
- 配置格式不变

## 迁移指南

如果你有基于旧版本的扩展或修改：

1. **数据模型相关**: 从 `models.py` 导入 `Concept`, `Memory`, `Connection`
2. **配置相关**: 从 `config.py` 导入配置类
3. **记忆图操作**: 从 `memory_graph.py` 导入 `MemoryGraph`
4. **批量提取**: 从 `batch_extractor.py` 导入 `BatchMemoryExtractor`
5. **核心系统**: 从 `memory_system_core.py` 导入 `MemorySystem`

## 测试建议

建议进行以下测试：
- [ ] 插件加载和初始化
- [ ] 记忆创建和保存
- [ ] 记忆召回功能
- [ ] 印象记录和查询
- [ ] 图谱生成
- [ ] LLM 工具调用
- [ ] 群聊隔离功能
- [ ] 异步任务管理
- [ ] 插件终止和资源清理
