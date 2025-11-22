# Main.py 解耦重构说明

## 重构目标
将原本4094行的main.py解耦成多个职责明确的模块，提高代码可维护性和可读性。

## 重构结果

### 文件结构
```
├── main.py                      # 22行 - 插件注册入口
├── plugin.py                    # 44KB - 插件类（命令处理、事件监听）
├── memory_system.py             # 101KB - 核心记忆系统逻辑
├── memory_graph.py              # 7.9KB - 记忆图数据结构
├── models.py                    # 1.4KB - 数据模型定义
├── config.py                    # 3.4KB - 配置管理
├── batch_memory_extractor.py    # 16KB - 批量记忆提取器
└── [其他已存在的模块...]
```

### 模块职责

#### 1. main.py (入口层)
- 职责：插件注册和导出
- 代码量：22行
- 依赖：plugin.py

#### 2. models.py (数据层)
- 职责：定义核心数据类
- 内容：
  - Concept：概念节点
  - Memory：记忆条目
  - Connection：概念连接
- 依赖：无（仅标准库）

#### 3. config.py (配置层)
- 职责：配置管理
- 内容：
  - MemorySystemConfig：配置数据类
  - MemoryConfigManager：配置管理器
- 依赖：astrbot.api

#### 4. memory_graph.py (数据结构层)
- 职责：记忆图的增删改查
- 内容：
  - MemoryGraph：管理concepts、memories、connections和邻接表
  - 提供图操作方法（添加、删除、更新节点和边）
- 依赖：models.py

#### 5. batch_memory_extractor.py (提取层)
- 职责：通过LLM提取记忆和印象
- 内容：
  - BatchMemoryExtractor：批量记忆提取
  - 对话格式化和JSON解析
  - 回退提取策略
- 依赖：memory_system.py（运行时）

#### 6. memory_system.py (业务逻辑层)
- 职责：核心记忆系统业务逻辑
- 内容：
  - MemorySystem：记忆形成、召回、遗忘、巩固
  - 数据库持久化
  - LLM集成
  - 维护任务调度
- 依赖：models.py, memory_graph.py, config.py, batch_memory_extractor.py等

#### 7. plugin.py (表现层)
- 职责：AstrBot插件接口实现
- 内容：
  - MemoraConnectPlugin：插件主类
  - 命令处理器（/记忆 回忆、状态、印象、图谱等）
  - 事件监听（消息、LLM请求）
  - LLM工具函数（create_memory、recall_memory等）
  - 插件生命周期管理（初始化、终止）
  - API接口方法
- 依赖：memory_system.py及其他辅助模块

## 重构优势

1. **关注点分离**：每个模块职责单一明确
2. **可维护性提升**：从4094行单文件变为多个小文件
3. **可测试性增强**：模块独立，易于单元测试
4. **可扩展性改善**：新功能可以添加新模块，不影响现有代码
5. **代码复用**：核心逻辑可被其他插件复用

## 向后兼容性

- 插件注册信息保持不变
- API接口保持不变
- 数据库格式保持不变
- 配置格式保持不变

## 迁移说明

对于使用此插件的开发者，无需修改任何代码。所有import路径和API保持兼容。
