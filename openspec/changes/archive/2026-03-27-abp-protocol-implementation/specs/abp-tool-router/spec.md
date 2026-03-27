## ADDED Requirements

### Requirement: Tool Listing
主进程 SHALL 支持通过 `tools/list` 获取插件提供的工具列表。

#### Scenario: List Available Tools
- **WHEN** 主进程发送 `tools/list` 请求
- **THEN** 插件返回可用工具定义列表
- **AND** 每个工具包含 name、description、parameters

### Requirement: Tool Calling
主进程 SHALL 支持通过 `tools/call` 调用插件提供的工具。

#### Scenario: Call Tool with Arguments
- **WHEN** 主进程发送 `tools/call` 请求，包含 tool name 和 arguments
- **THEN** 插件执行对应工具
- **AND** 返回工具执行结果（content 数组）

#### Scenario: Tool Not Found
- **WHEN** 请求的工具名称不存在
- **THEN** 插件返回 `-32203` (Tool Not Found) 错误码

#### Scenario: Tool Call Failed
- **WHEN** 工具执行过程中发生错误
- **THEN** 插件返回 `-32204` (Tool Call Failed) 错误码
- **AND** 错误信息包含原因

### Requirement: Tool Result Format
工具调用结果 SHALL 符合标准格式。

#### Scenario: Successful Tool Result
- **WHEN** 工具成功执行
- **THEN** 返回 result，包含 content 数组
- **AND** content 每个元素包含 type 和 text/image/url

### Requirement: Tool Metadata
工具定义 SHALL 包含完整的元数据用于 LLM 函数调用。

#### Scenario: Tool Definition Structure
- **WHEN** 插件声明工具
- **THEN** 必须包含：name (string)、description (string)、parameters (JSON Schema)
- **AND** parameters 必须符合 JSON Schema Draft-07 格式
