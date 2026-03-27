## ADDED Requirements

### Requirement: Event Subscription
插件 SHALL 支持订阅系统事件。

#### Scenario: Subscribe to Event
- **WHEN** 主进程发送 `plugin.subscribe` 请求，包含 event_type
- **THEN** 插件注册订阅
- **AND** 主进程在事件发生时通知插件

#### Scenario: Unsubscribe from Event
- **WHEN** 主进程发送 `plugin.unsubscribe` 请求
- **THEN** 插件取消订阅
- **AND** 不再接收该类型事件通知

#### Scenario: Event Subscription Failed
- **WHEN** 订阅的事件类型不支持
- **THEN** 插件返回 `-32207` (Event Subscribe Failed) 错误码

### Requirement: Event Notification
插件 SHALL 支持接收和发送事件通知。

#### Scenario: Receive Event Notification
- **WHEN** 主进程有事件发生（llm_request、tool_called 等）
- **THEN** 主进程发送 `plugin.notify` 通知到插件
- **AND** 包含 event_type 和 data

#### Scenario: Send Event from Plugin
- **WHEN** 插件需要通知主进程
- **THEN** 插件发送 `plugin.notify` 到主进程
- **AND** 主进程路由到对应处理器

### Requirement: Supported Event Types
插件 SHALL 支持以下事件类型。

#### Scenario: LLM Request Event
- **WHEN** LLM 开始处理请求
- **THEN** 主进程通知订阅者，包含请求 ID 和 prompt

#### Scenario: Tool Called Event
- **WHEN** 工具被调用
- **THEN** 主进程通知订阅者，包含工具名称和参数

#### Scenario: Message Received Event
- **WHEN** 收到用户消息
- **THEN** 主进程通知订阅者，包含消息内容
