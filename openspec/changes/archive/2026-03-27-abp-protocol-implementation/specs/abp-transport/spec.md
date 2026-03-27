## ADDED Requirements

### Requirement: Stdio Transport
插件通过标准输入/输出进行 JSON-RPC 通信。

#### Scenario: Stdio Message Format
- **WHEN** 发送 JSON-RPC 消息
- **THEN** 每条消息为单行 JSON，不包含长度前缀
- **AND** 消息之间以换行符分隔

### Requirement: Unix Socket Transport
进程间通过 Unix Socket 进行通信，使用 Content-Length 协议。

#### Scenario: Unix Socket Message Format
- **WHEN** 发送 JSON-RPC 消息
- **THEN** 消息前添加 `Content-Length: <bytes>\r\n\r\n` 前缀
- **AND** 消息体为 UTF-8 编码的 JSON

#### Scenario: Unix Socket Connection Lifecycle
- **WHEN** 主进程连接插件 Unix Socket
- **THEN** 建立持久连接
- **AND** 双向复用同一连接发送请求/响应

### Requirement: HTTP/SSE Transport
远程插件使用 HTTP 进行请求，SSE 进行服务端推送。

#### Scenario: HTTP Request
- **WHEN** 主进程发送 HTTP 请求到插件
- **THEN** 使用 POST 方法，Content-Type 为 `application/json`
- **AND** 请求体为 JSON-RPC 请求对象

#### Scenario: SSE Event Stream
- **WHEN** 插件需要推送通知
- **THEN** 使用 Server-Sent Events 格式
- **AND** 事件类型为 `plugin.notify`
