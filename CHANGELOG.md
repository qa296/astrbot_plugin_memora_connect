## 📈 版本历史

### v0.3.1 (当前版本)
- ✨ 新增「记忆生成人格注入」能力
  - 记忆生成主链路（`TopicAnalyzer`）支持按会话人格注入约束
  - 人格来源优先级：会话 `persona_id` > 默认人格（`get_default_persona_v3`）
  - 新增配置项 `enable_persona_injection_in_memory_generation`（默认开启）

### v0.3.0
- 🚀 架构升级：基于话题的统一LLM调用系统
  - 新增 `TopicAnalyzer` 替代原有的 `TopicEngine` 和 `BatchMemoryExtractor`
  - 一次LLM调用处理多条消息，减少约95%的LLM调用次数
  - 消息带序号发送给LLM，精确对应分析结果
  - 会话completed时自动生成记忆、印象和摘要
  - 支持言外之意（subtext）分析
- ⚙️ 新增配置项：
  - `topic_trigger_interval_minutes`: 触发间隔（默认5分钟，可配置）
  - `topic_message_threshold`: 消息数量阈值（默认12条，可配置）
  - `recent_completed_sessions_count`: 保留的已完成会话数量（默认5个，可配置）
- 🗑️ 移除配置项：
  - `enable_batch_memory_extraction`（已被新系统取代）
  - `memory_formation_interval`（已被新系统取代）
- 🏗️ 内部模块重组：
  - `intelligence/topic_analyzer.py`: 新核心分析器
  - `intelligence/topics.py`: 已废弃（保留文件但不再使用）
  - `memory/extractor.py`: 已废弃（保留文件但不再使用）

### v0.2.6
- 🗺️ 新增记忆图谱可视化命令：/记忆 图谱，支持多种布局
- 🖥️ 新增内置 Web 管理界面，可通过 web_ui 配置启用
- 🧩 新增资源管理器与数据库连接池，提升并发与稳定性
- 🔧 数据库迁移与嵌入缓存迁移增强，带回退策略
- 🤖 LLM 请求的记忆注入和召回进一步优化
- 🐛 修复若干问题，优化传递 LLM 参数等细节

### v0.2.3
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
