## ADDED Requirements

### Requirement: tools/list Endpoint
插件通过 `tools/list` 端点暴露可用工具列表。

#### Scenario: List Plugin Tools
- **WHEN** 主进程调用 `tools/list` 方法
- **THEN** 插件返回 `{ "tools": [ToolDef, ...] }`
- **AND** 每个 ToolDef 包含 name、description、parameters（JSON Schema）

#### Scenario: Empty Tools List
- **WHEN** 插件无可用工具
- **THEN** 返回 `{ "tools": [] }`

### Requirement: Tool Schema Validation
注册工具时进行 JSON Schema Draft-07 格式校验。

#### Scenario: Valid Tool Schema
- **WHEN** 工具定义通过 Schema 校验
- **THEN** 工具注册到 `ToolRegistry`
- **AND** 可被 `tools/call` 调用

#### Scenario: Invalid Tool Schema
- **WHEN** 工具定义 Schema 校验失败
- **THEN** 记录警告日志
- **AND** 跳过该工具（不注册）

### Requirement: ToolRegistry
> **架构约束**：核心路由在 Rust FFI（`tool_router.rs`），Python 层仅做聚合

中心化工具注册表，支持跨插件工具发现和调用。

#### Scenario: Register Tool
- **WHEN** 插件调用 `registry.register(plugin_id, tools)`
- **THEN** 工具按 plugin_id 隔离存储
- **AND** 执行 Schema 校验

#### Scenario: Discover All Tools
- **WHEN** 调用 `registry.list_tools()`
- **THEN** 聚合所有插件注册的工具（通过 Rust FFI `list_tools()`）
- **AND** 每个工具标记来源 plugin_id

#### Scenario: Call Tool
- **WHEN** 调用 `registry.call_tool(tool_name, args)`
- **THEN** 转发调用到 Rust FFI `route_tool_call()`
- **AND** 返回执行结果

#### Scenario: Tool Not Found
- **WHEN** 调用不存在的工具
- **THEN** Rust FFI 抛出 `ToolNotFoundError` 错误
- **AND** 错误码 -32203

### Requirement: Cross-Plugin Tool Discovery
聚合多个插件的工具，提供统一发现接口。

#### Scenario: Aggregate Tools from Multiple Plugins
- **WHEN** 多个插件注册了工具
- **THEN** `ToolRegistry` 聚合所有工具
- **AND** 工具名可配置为 `plugin_name/tool_name` 格式避免冲突
