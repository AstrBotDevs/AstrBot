## Why

AstrBot 需要一个统一的插件协议来实现插件的加载、消息处理、工具调用和生命周期管理。当前的 Star 插件系统与核心紧耦合，插件无法独立运行，缺乏标准化接口。ABP 协议将插件系统从核心中解耦，实现插件的零侵入性和跨语言支持。

## What Changes

- **新增 ABP 协议层**：标准化的插件通信协议（JSON-RPC 2.0）
- **新增插件加载器**：支持进程内（`in_process`）和进程外（`out_of_process`）两种模式
- **新增传输层**：Stdio、Unix Socket、HTTP/SSE 三种传输方式
- **新增插件生命周期管理**：初始化、启动、停止、重载、配置更新
- **新增工具调用机制**：标准化的 `tools/list` 和 `tools/call` 接口
- **新增消息处理**：通过 `plugin.handle_event` 处理平台事件
- **新增事件订阅**：插件可订阅 LLM 请求等系统事件
- **Rust 核心实现**：协议核心逻辑在 Rust 运行时（`astrbot/rust/src/`）

## Capabilities

### New Capabilities

- `abp-protocol`: ABP 协议核心 - 握手、消息路由、生命周期管理
- `abp-transport`: ABP 传输层 - Stdio/Unix Socket/HTTP 实现
- `abp-plugin-loader`: ABP 插件加载器 - 进程内/外插件管理
- `abp-tool-router`: ABP 工具路由 - 跨插件工具发现和调用
- `abp-event-system`: ABP 事件系统 - 事件订阅和通知

### Modified Capabilities

- `agent-message` (待定): 如果需要与 Agent 消息流程整合，可能需要调整

## Impact

- **新增目录**：`astrbot/rust/src/abp/` - Rust ABP 核心实现
- **新增 Python 胶水层**：`astrbot/core/plugin/` - Python FFI 胶水代码
- **配置文件变更**：`config.yaml` 中新增 `plugins` 配置项
- **依赖**：`jsonrpc-derive`（Rust）、`jsonrpc-core`（Rust）
