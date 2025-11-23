---
outline: deep
---

# Astrbot 整体运行流程

## 启动 AstrBot

启动 AstrBot 后, 会从 `main.py` 开始执行, 启动阶段的主要流程如下：

1. 检查环境、检查 WebUI 文件，如缺失将自动下载；
2. 加载 WebUI 后端异步任务、加载核心(Core)相关组件

## 核心生命周期

### 启动

在核心生命周期初始化时, 会按顺序初始化以下组件:

1. 供应商管理器(ProviderManager): 用于接入不同的大模型供应商, 提供 LLM 请求接口。
2. 平台管理器(PlatformManager): 用于接入不同的平台, 提供平台请求接口。
3. 知识库管理器(KnowledgeDBManager): 用于内建知识库而不依赖外部的 LLMOps 平台。(这个功能在 v3.5.0 及之前的版本都没有被实装)
4. 会话-对话管理器(ConversationManager): 用于管理不同会话窗口和对话的映射关系。
5. 插件管理器(PluginManager): 用于接入插件。
6. 消息管道调度器(PipelineScheduler): 用于调度消息管道, 处理消息的流转。
7. 事件总线(EventBus): 用于事件的分发和处理。

### 运行

AstrBot 的运行基于事件驱动, 平台适配器上报事件后，事件总线将会将事件交给流水线(PipelineScheduler)进行进一步处理。事件总线的核心结构如下:

```Python
class EventBus:
    """事件总线: 用于处理事件的分发和处理

    维护一个异步队列, 来接受各种消息事件
    """

    def __init__(self, event_queue: Queue, pipeline_scheduler: PipelineScheduler):
        self.event_queue = event_queue  # 事件队列
        self.pipeline_scheduler = pipeline_scheduler  # 管道调度器

    async def dispatch(self):
        """无限循环的调度函数, 从事件队列中获取新的事件, 打印日志并创建一个新的异步任务来执行管道调度器的处理逻辑"""
        while True:
            event: AstrMessageEvent = (
                await self.event_queue.get()
            )  # 从事件队列中获取新的事件
            self._print_event(event)  # 打印日志
            asyncio.create_task(
                self.pipeline_scheduler.execute(event)
            )  # 创建新的异步任务来执行管道调度器的处理逻辑
```

事件总线的核心是一个异步队列和一个无限循环的协程, 它不断地从这个异步队列中拿取新的事件, 并创建新的异步任务将事件交由消息管道调度器进行处理。

### 处理事件

在事件总线中存在事件时， `dispatch`协程便会将这个事件取出, 交由消息管道调度器(PipelineScheduler)进行处理。

消息管道调度器的执行设计为一种『洋葱模型』, 它的特点是:

- 层层嵌套: 每个处理阶段如同洋葱的一层外皮
- 双向流动: 每个请求都会"进入"每一层, 在"返回"时都会经过每一层
- 前置处理与后置处理: 在洋葱模型的每一层中, 都可以在两个时间点进行处理(进入与返回时)

AstrBot 消息管道调度器的『洋葱模型』的实现如下:

```Python
async def _process_stages(self, event: AstrMessageEvent, from_stage=0):
    """依次执行各个阶段"""
    for i in range(from_stage, len(registered_stages)):
        stage = registered_stages[i]  # 获取当前要执行的阶段
        coroutine = stage.process(event)  # 调用阶段的process方法，返回协程或异步生成器

        if isinstance(coroutine, AsyncGenerator):
            # 如果返回的是异步生成器，实现洋葱模型的核心
            async for _ in coroutine:
                # 此处是前置处理完成后的暂停点(yield)，下面开始执行后续阶段
                if event.is_stopped():
                    logger.debug(f"阶段 {stage.__class__.__name__} 已终止事件传播。")
                    break

                # 递归调用，处理所有后续阶段
                await self._process_stages(event, i + 1)

                # 此处是后续所有阶段处理完毕后返回的点，执行后置处理
                if event.is_stopped():
                    logger.debug(f"阶段 {stage.__class__.__name__} 已终止事件传播。")
                    break
        else:
            # 如果返回的是普通协程(不含yield的async函数)，则没有洋葱模型特性
            # 只是简单地等待它执行完成后继续下一个阶段
            await coroutine

            if event.is_stopped():
                logger.debug(f"阶段 {stage.__class__.__name__} 已终止事件传播。")
                break
```

这似乎很难理解, 这里提供一个示例进行解释:

假设目前已经注册了 3 个事件处理阶段 A、B、C, 执行流程如下:

```
A开始
  |
  |--> yield (暂停A)
  |      |
  |      |--> B开始
  |      |      |
  |      |      |--> yield (暂停B)
  |      |      |      |
  |      |      |      |--> C开始
  |      |      |      |      |
  |      |      |      |      |--> C结束
  |      |      |      |
  |      |      |--> B继续执行(yield后的代码)
  |      |      |      |
  |      |      |      |--> B结束
  |      |
  |--> A继续执行(yield后的代码)
  |      |
  |      |--> A结束

A开始 → B开始 → C开始 → C结束 → B结束 → A结束
```
