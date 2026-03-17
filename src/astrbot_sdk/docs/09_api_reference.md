# AstrBot SDK 完整 API 参考

本文档提供 SDK 所有导出类和函数的完整参考，按模块分类。

## 相关文档

### 入门文档
- [README](./README.md)
- [Context API 参考](./01_context_api.md)
- [消息事件与组件](./02_event_and_components.md)
- [装饰器使用指南](./03_decorators.md)

### API 详细文档
#### 核心类
- [Star 类 API](./api/star.md) - 插件基类与生命周期
- [Context 类 API](./api/context.md) - 运行时上下文与能力客户端
- [MessageEvent 类 API](./api/message_event.md) - 消息事件对象

#### 装饰器与过滤器
- [装饰器 API](./api/decorators.md) - 事件触发、限制器、过滤器装饰器

#### 客户端
- [客户端 API](./api/clients.md) - LLM、Memory、DB、Platform 等 12 个客户端

#### 消息处理
- [消息组件 API](./api/message_components.md) - Plain、Image、At、Record、Video、File 等
- [消息结果 API](./api/message_result.md) - MessageChain、MessageBuilder、MessageEventResult

#### 工具与类型
- [工具与辅助类 API](./api/utils.md) - CancelToken、MessageSession、GreedyStr、CommandGroup 等
- [类型定义 API](./api/types.md) - 类型别名、泛型变量、Pydantic 模型

#### 错误处理
- [错误处理 API](./api/errors.md) - AstrBotError、ErrorCodes
