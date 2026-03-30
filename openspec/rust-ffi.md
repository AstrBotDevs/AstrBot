# Rust FFI 接口规范

## 概述

AstrBot 采用 **Rust 核心 + Python 胶水层** 架构。Rust 核心编译为 `_core.so`，通过 FFI 暴露接口供 Python 调用。

**绑定方案**：使用 [PyO3](https://pyo3.rs/)（`rust/src/lib.rs` 导出 `#[pymodule]`），Python 端通过 `ffi` 模块调用。

**禁止使用 `ctypes`** —— 所有 FFI 交互必须通过 PyO3 绑定。

## 核心模块布局

```
astrbot/rust/src/
├── lib.rs              # 入口，导出 #[pymodule]
├── orchestrator.rs     # AstrbotOrchestrator 主协调器
├── abp/                # ABP 协议实现
│   ├── mod.rs
│   ├── protocol.rs      # 握手、消息路由
│   ├── loader.rs        # 插件加载器
│   ├── transport.rs     # Stdio/Unix Socket/HTTP
│   └── error.rs         # ABP 错误码
├── message/            # 消息缓冲（双缓冲区）
│   ├── mod.rs
│   ├── input_buffer.rs
│   └── output_buffer.rs
├── flow_control.rs     # 流控引擎
├── tool_router.rs      # 工具路由（Internal/MCP/Skills）
└── agent.rs            # Agent 协调
```

## FFI 函数签名

### orchestrator.rs

| 函数 | Python 签名 | 返回类型 | 说明 |
|------|-------------|----------|------|
| `get_orchestrator()` | `def get_orchestrator() -> AstrbotOrchestrator` | `AstrbotOrchestrator` | 单例获取 |
| `orchestrator.start()` | `def start(self) -> None` | `None` | 启动核心 |
| `orchestrator.stop()` | `def stop(self) -> None` | `None` | 停止核心 |
| `orchestrator.is_running()` | `def is_running(self) -> bool` | `bool` | 运行状态 |
| `orchestrator.register_star()` | `def register_star(self, name: str, handler: str) -> None` | `None` | 注册 Star |
| `orchestrator.unregister_star()` | `def unregister_star(self, name: str) -> None` | `None` | 注销 Star |
| `orchestrator.list_stars()` | `def list_stars(self) -> list[str]` | `list[str]` | 列出 Stars |
| `orchestrator.record_activity()` | `def record_activity(self) -> None` | `None` | 记录活动 |
| `orchestrator.get_stats()` | `def get_stats(self) -> dict` | `dict[str, Any]` | 获取统计 |
| `orchestrator.set_protocol_connected()` | `def set_protocol_connected(self, protocol: str, connected: bool) -> None` | `None` | 设置协议连接状态 |
| `orchestrator.get_protocol_status()` | `def get_protocol_status(self, protocol: str) -> dict | None` | `dict[str, Any] \| None` | 获取协议状态 |

### abp/protocol.rs（ABP 插件协议）

| 函数 | Python 签名 | 返回类型 | 说明 |
|------|-------------|----------|------|
| `plugin_initialize()` | `def plugin_initialize(config: dict) -> InitializeResult` | `InitializeResult` | 初始化握手 |
| `plugin_start()` | `def plugin_start(self, plugin_id: str) -> None` | `None` | 启动插件 |
| `plugin_stop()` | `def plugin_stop(self, plugin_id: str) -> None` | `None` | 停止插件 |
| `plugin_reload()` | `def plugin_reload(self, plugin_id: str) -> None` | `None` | 重载插件 |
| `plugin_config_update()` | `def plugin_config_update(self, plugin_id: str, config: dict) -> None` | `None` | 更新配置 |

### abp/loader.rs（插件加载器）

| 函数 | Python 签名 | 返回类型 | 说明 |
|------|-------------|----------|------|
| `load_plugin()` | `def load_plugin(self, plugin_config: dict) -> PluginHandle` | `PluginHandle` | 加载插件 |
| `unload_plugin()` | `def unload_plugin(self, plugin_id: str) -> None` | `None` | 卸载插件 |
| `list_loaded_plugins()` | `def list_loaded_plugins(self) -> list[str]` | `list[str]` | 列出已加载 |

### abp/transport.rs（传输层）

| 函数 | Python 签名 | 返回类型 | 说明 |
|------|-------------|----------|------|
| `create_stdio_transport()` | `def create_stdio_transport(cmd: str, args: list[str]) -> Transport` | `Transport` | 创建 stdio 传输 |
| `create_unix_transport()` | `def create_unix_transport(path: str) -> Transport` | `Transport` | 创建 Unix Socket 传输 |
| `create_http_transport()` | `def create_http_transport(url: str) -> Transport` | `Transport` | 创建 HTTP/SSE 传输 |

### message/input_buffer.rs（输入缓冲区）

| 函数 | Python 签名 | 返回类型 | 说明 |
|------|-------------|----------|------|
| `enqueue_message()` | `def enqueue_message(self, event: dict) -> str` | `str` | 入队，返回 message_id |
| `dequeue_messages()` | `def dequeue_messages(self, limit: int) -> list[dict]` | `list[dict]` | 批量出队 |
| `get_queue_depth()` | `def get_queue_depth(self, session_id: str) -> int` | `int` | 获取队列深度 |
| `clear_queue()` | `def clear_queue(self, session_id: str) -> None` | `None` | 清空队列 |

### message/output_buffer.rs（输出缓冲区）

| 函数 | Python 签名 | 返回类型 | 说明 |
|------|-------------|----------|------|
| `enqueue_result()` | `def enqueue_result(self, session_id: str, result: dict) -> str` | `str` | 入队 |
| `dequeue_result()` | `def dequeue_result(self, session_id: str) -> dict \| None` | `dict \| None` | 出队（非阻塞） |
| `set_dispatch_strategy()` | `def set_dispatch_strategy(self, strategy: str) -> None` | `None` | 设置分发策略 |

### flow_control.rs（流控引擎）

| 函数 | Python 签名 | 返回类型 | 说明 |
|------|-------------|----------|------|
| `set_rate_limit()` | `def set_rate_limit(self, requests: int, period: float) -> None` | `None` | 设置限流 |
| `acquire()` | `def acquire(self) -> bool` | `bool` | 获取令牌（非阻塞） |
| `wait_for_token()` | `def wait_for_token(self, timeout: float) -> bool` | `bool` | 等待令牌（阻塞） |

### tool_router.rs（工具路由）

| 函数 | Python 签名 | 返回类型 | 说明 |
|------|-------------|----------|------|
| `register_internal_tool()` | `def register_internal_tool(self, name: str, schema: dict) -> None` | `None` | 注册内部工具 |
| `register_mcp_server()` | `def register_mcp_server(self, name: str, transport: Transport) -> None` | `None` | 注册 MCP 服务器 |
| `route_tool_call()` | `def route_tool_call(self, tool_name: str, arguments: dict) -> ToolResult` | `ToolResult` | 路由工具调用 |
| `list_tools()` | `def list_tools(self) -> list[dict]` | `list[dict]` | 列出所有工具 |

## 类型映射

| Rust 类型 | Python 类型 | 说明 |
|-----------|------------|------|
| `bool` | `bool` | - |
| `i32`, `i64` | `int` | - |
| `f64` | `float` | - |
| `String` | `str` | - |
| `Vec<T>` | `list[T]` | - |
| `HashMap<K,V>` | `dict[K,V]` | - |
| `Option<T>` | `T \| None` | - |
| `Result<T, E>` | 异常或 T | 失败抛 Python 异常 |

## 错误处理

Rust 层返回的错误统一转换为 Python 异常：

| ABP 错误码 | Python 异常 |
|------------|-------------|
| -32200 | `PluginNotFoundError` |
| -32201 | `PluginNotReadyError` |
| -32202 | `PluginCrashedError` |
| -32203 | `ToolNotFoundError` |
| -32204 | `ToolCallFailedError` |
| -32205 | `HandlerNotFoundError` |
| -32206 | `HandlerError` |
| -32207 | `EventSubscribeError` |
| -32208 | `PermissionDeniedError` |
| -32209 | `ConfigError` |
| -32210 | `DependencyMissingError` |
| -32211 | `VersionMismatchError` |
| -32603 | `InternalError` |

## 实现要求

1. **所有函数必须线程安全**（Rust 核心使用 `Arc<Mutex<T>>` 保护共享状态）
2. **异步操作在 Rust 内部完成**，Python 侧得到的是 Future 或直接结果
3. **不得在 FFI 边界传递闭包或函数指针**
4. **版本化接口**：FFI 接口变更时提升 `__version__`，保持向后兼容
5. **文档注释**：Rust 代码使用 `///` 注释，会通过 PyO3 生成 Python docstring

## 相关文件

- [config.yaml](config.yaml) - 项目架构说明（包含 rust_core、internal_package 等 directive）
- [abp.md](abp.md) - ABP 协议规范
- [agent-message.md](agent-message.md) - 消息处理规范
- `openspec/changes/abp-protocol-implementation/` - ABP 实现 change proposal（含详细任务清单）
