# AstrBot SDK v4 架构与实现文档

## 目录

1. [架构概览](#架构概览)
2. [目录结构](#目录结构)
3. [核心模块详解](#核心模块详解)
   - [协议层 (protocol/)](#协议层-protocol)
   - [运行时层 (runtime/)](#运行时层-runtime)
   - [客户端层 (clients/)](#客户端层-clients)
   - [API 层 (api/)](#api层-api)
   - [核心文件](#核心文件)
4. [五大硬性协议规则](#五大硬性协议规则)
5. [数据流与通信模型](#数据流与通信模型)
6. [扩展机制](#扩展机制)
7. [实现状态](#实现状态)

---

## 架构概览

AstrBot SDK v4 采用分层架构设计，从上到下分为：

```
┌─────────────────────────────────────────────────────┐
│                    用户层 (User Layer)               │
│              插件开发者编写的 Star 类                 │
├─────────────────────────────────────────────────────┤
│                    API 层 (API Layer)                │
│     Star, Context, decorators, filter, events       │
├─────────────────────────────────────────────────────┤
│                 翻译层 (Translation Layer)           │
│     HandlerDispatcher, Loader, LegacyAdapter        │
├─────────────────────────────────────────────────────┤
│                通信层 (Communication Layer)          │
│        Peer, Transport, CapabilityRouter            │
└─────────────────────────────────────────────────────┘
```

### 核心设计原则

1. **协议优先**: 所有通信通过标准化的协议消息
2. **能力抽象**: 通过 Capability 系统暴露核心功能
3. **双向通信**: Plugin ↔ Core 的对称通信模型
4. **向后兼容**: LegacyAdapter 提供 v3 兼容层

---

## 目录结构

```
src-new/astrbot_sdk/
├── __init__.py              # 顶层导出 (Star, Context, decorators, events, errors)
├── __main__.py              # CLI 入口点
├── cli.py                   # Click 命令行工具
├── star.py                  # Star 基类与 Handler 发现
├── context.py               # 运行时 Context 与 CancelToken
├── decorators.py            # 装饰器 @on_command, @on_message, @provide_capability 等
├── events.py                # MessageEvent 事件定义
├── errors.py                # AstrBotError 错误模型与 ErrorCodes 常量
├── compat.py                # 兼容层导出 (LegacyContext, CommandComponent)
├── _legacy_api.py           # Legacy Context, CommandComponent, LegacyConversationManager
│
├── protocol/                # 协议层 (已完成)
│   ├── __init__.py          # 公共入口，导出所有协议类型
│   ├── descriptors.py       # HandlerDescriptor, CapabilityDescriptor
│   │                        # 内置能力 JSON Schema 常量 (16 个能力)
│   ├── messages.py          # 五种协议消息类型
│   └── legacy_adapter.py    # v3 JSON-RPC ↔ v4 协议双向转换
│
├── runtime/                 # 运行时层 (已完成)
│   ├── __init__.py          # 公共入口，导出高级原语
│   ├── peer.py              # 核心通信端点，远程元数据缓存
│   ├── transport.py         # 传输层实现 (Stdio/WebSocket)
│   ├── loader.py            # 插件加载器、环境管理、配置规范化
│   ├── handler_dispatcher.py # Handler 分发器 + CapabilityDispatcher
│   ├── capability_router.py # Capability 路由器，15 个内置能力
│   └── bootstrap.py         # Supervisor/Worker 运行时，WebSocket 服务
│
├── clients/                 # 客户端层 (已完成)
│   ├── __init__.py          # 导出所有客户端
│   ├── _proxy.py            # CapabilityProxy 代理
│   ├── llm.py               # LLM 客户端 (chat/chat_raw/stream_chat)
│   ├── db.py                # 数据库客户端 (get/set/delete/list)
│   ├── memory.py            # 记忆客户端 (search/get/save/delete)
│   └── platform.py          # 平台客户端 (支持 SessionRef)
│
└── api/                     # API 层 - 兼容层
    ├── __init__.py          # 子模块导出
    ├── basic/               # 基础实体与配置
    │   ├── astrbot_config.py
    │   ├── conversation_mgr.py
    │   └── entities.py
    ├── components/          # 组件导出
    │   └── command.py       # CommandComponent 导出
    ├── event/               # 事件相关
    │   ├── astr_message_event.py
    │   ├── astrbot_message.py
    │   ├── event_result.py
    │   ├── event_type.py
    │   ├── filter.py        # filter 命名空间
    │   ├── message_session.py
    │   └── message_type.py
    ├── message/             # 消息链
    │   ├── chain.py
    │   └── components.py
    ├── message_components/  # 消息组件兼容导出
    ├── platform/            # 平台元数据
    │   └── platform_metadata.py
    ├── provider/            # Provider 实体
    │   └── entities.py
    └── star/                # Star 相关
        ├── context.py       # Legacy Context 导出
        └── star.py
```

---

## 核心模块详解

### 协议层 (protocol/)

协议层负责消息格式定义和 legacy 兼容转换，是 v4 新引入的抽象层。

#### `descriptors.py` - 描述符定义

定义了 Handler 和 Capability 的元数据结构，以及内置能力的 JSON Schema 常量。

**核心类型:**

```python
# 权限配置
class Permissions(_DescriptorBase):
    require_admin: bool = False
    level: int = 0

# 会话引用 (新增)
class SessionRef(_DescriptorBase):
    conversation_id: str
    platform: str | None = None
    raw: dict[str, Any] | None = None

# 四种 Trigger 类型 (discriminated union)
class CommandTrigger:
    type: Literal["command"] = "command"
    command: str
    aliases: list[str] = []
    description: str | None = None
    platforms: list[str] = []

class MessageTrigger:
    type: Literal["message"] = "message"
    regex: str | None = None
    keywords: list[str] = []
    platforms: list[str] = []
    message_types: list[str] = []

class EventTrigger:
    type: Literal["event"] = "event"
    event_type: str  # 字符串形式，如 "message"

class ScheduleTrigger:
    type: Literal["schedule"] = "schedule"
    cron: str | None = None
    interval_seconds: int | None = None

# Trigger 联合类型
Trigger = Annotated[
    CommandTrigger | MessageTrigger | EventTrigger | ScheduleTrigger,
    Field(discriminator="type"),
]

# Handler 描述符
class HandlerDescriptor(_DescriptorBase):
    id: str
    trigger: Trigger
    kind: Literal["handler", "hook", "tool", "session"] = "handler"
    contract: str | None = None
    priority: int = 0
    permissions: Permissions

# Capability 描述符
class CapabilityDescriptor(_DescriptorBase):
    name: str
    description: str
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    supports_stream: bool = False
    cancelable: bool = False
```

**内置能力 Schema 常量 (16 个能力):**

```python
# LLM 相关 (3 个)
LLM_CHAT_INPUT_SCHEMA / LLM_CHAT_OUTPUT_SCHEMA
LLM_CHAT_RAW_INPUT_SCHEMA / LLM_CHAT_RAW_OUTPUT_SCHEMA
LLM_STREAM_CHAT_INPUT_SCHEMA / LLM_STREAM_CHAT_OUTPUT_SCHEMA

# Memory 相关 (4 个)
MEMORY_SEARCH_INPUT_SCHEMA / MEMORY_SEARCH_OUTPUT_SCHEMA
MEMORY_SAVE_INPUT_SCHEMA / MEMORY_SAVE_OUTPUT_SCHEMA
MEMORY_GET_INPUT_SCHEMA / MEMORY_GET_OUTPUT_SCHEMA
MEMORY_DELETE_INPUT_SCHEMA / MEMORY_DELETE_OUTPUT_SCHEMA

# DB 相关 (4 个)
DB_GET_INPUT_SCHEMA / DB_GET_OUTPUT_SCHEMA
DB_SET_INPUT_SCHEMA / DB_SET_OUTPUT_SCHEMA
DB_DELETE_INPUT_SCHEMA / DB_DELETE_OUTPUT_SCHEMA
DB_LIST_INPUT_SCHEMA / DB_LIST_OUTPUT_SCHEMA

# Platform 相关 (4 个)
PLATFORM_SEND_INPUT_SCHEMA / PLATFORM_SEND_OUTPUT_SCHEMA
PLATFORM_SEND_IMAGE_INPUT_SCHEMA / PLATFORM_SEND_IMAGE_OUTPUT_SCHEMA
PLATFORM_SEND_CHAIN_INPUT_SCHEMA / PLATFORM_SEND_CHAIN_OUTPUT_SCHEMA
PLATFORM_GET_MEMBERS_INPUT_SCHEMA / PLATFORM_GET_MEMBERS_OUTPUT_SCHEMA

# SessionRef Schema (新增)
SESSION_REF_SCHEMA

# 汇总字典
BUILTIN_CAPABILITY_SCHEMAS: dict[str, dict[str, JSONSchema]]
```

**命名空间规范:**

```python
RESERVED_CAPABILITY_NAMESPACES = ("handler", "system", "internal")
RESERVED_CAPABILITY_PREFIXES = tuple(f"{namespace}." for namespace in RESERVED_CAPABILITY_NAMESPACES)
CAPABILITY_NAME_PATTERN = r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$"
```

---

#### `messages.py` - 协议消息

定义五种协议消息类型，遵循**统一 id 字段**原则。

**消息类型:**

| 类型 | 用途 | 关键字段 |
|------|------|----------|
| `InitializeMessage` | 初始化握手 | `peer`, `handlers`, `provided_capabilities`, `metadata` |
| `InvokeMessage` | 调用 Capability | `capability`, `input`, `stream` |
| `ResultMessage` | 返回结果 | `success`, `output`, `error` |
| `EventMessage` | 流式事件 | `phase` (started/delta/completed/failed) |
| `CancelMessage` | 取消请求 | `reason` |

**核心结构:**

```python
class ErrorPayload(_MessageBase):
    code: str
    message: str
    hint: str = ""
    retryable: bool = False

class PeerInfo(_MessageBase):
    name: str
    role: Literal["plugin", "supervisor", "core"]
    version: str = "4.0"

class InitializeMessage(_MessageBase):
    type: Literal["initialize"] = "initialize"
    id: str
    protocol_version: str = "4.0"
    peer: PeerInfo
    handlers: list[HandlerDescriptor] = []
    provided_capabilities: list[CapabilityDescriptor] = []
    metadata: dict[str, Any] = {}

class InitializeOutput(_MessageBase):
    peer: PeerInfo
    capabilities: list[CapabilityDescriptor] = []
    metadata: dict[str, Any] = {}

class ResultMessage(_MessageBase):
    type: Literal["result"] = "result"
    id: str
    kind: str  # "initialize_result" 或 capability 名称
    success: bool
    output: dict[str, Any] | None = None
    error: ErrorPayload | None = None

class InvokeMessage(_MessageBase):
    type: Literal["invoke"] = "invoke"
    id: str
    capability: str
    input: dict[str, Any] = {}
    stream: bool = False

class EventMessage(_MessageBase):
    type: Literal["event"] = "event"
    id: str
    phase: Literal["started", "delta", "completed", "failed"]
    data: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    error: ErrorPayload | None = None

class CancelMessage(_MessageBase):
    type: Literal["cancel"] = "cancel"
    id: str
    reason: str = "user_cancelled"
```

**核心函数:**

```python
def parse_message(payload: str | bytes | dict) -> ProtocolMessage:
    """解析 JSON 为协议消息对象"""
```

---

#### `legacy_adapter.py` - 协议适配器

实现 v3 JSON-RPC 与 v4 协议的双向转换。

**核心类型:**

```python
class LegacyRequest(_LegacyMessageBase):
    jsonrpc: Literal["2.0"] = "2.0"
    id: str | None = None
    method: str
    params: dict[str, Any] = {}

class LegacySuccessResponse(_LegacyMessageBase):
    jsonrpc: Literal["2.0"] = "2.0"
    id: str | None = None
    result: Any

class LegacyErrorResponse(_LegacyMessageBase):
    jsonrpc: Literal["2.0"] = "2.0"
    id: str | None = None
    error: LegacyErrorData

LegacyMessage = LegacyRequest | LegacySuccessResponse | LegacyErrorResponse
LegacyToV4Message = InitializeMessage | InvokeMessage | CancelMessage | None
```

**核心方法:**

```python
def parse_legacy_message(payload: str | dict) -> LegacyMessage:
    """解析 legacy JSON-RPC 消息"""

def legacy_message_to_v4(legacy: LegacyMessage) -> LegacyToV4Message:
    """Legacy JSON-RPC → v4 Message"""

def initialize_to_legacy_handshake_response(message: InitializeMessage, output: InitializeOutput) -> dict:
    """v4 Initialize → Legacy Response"""

def invoke_to_legacy_request(message: InvokeMessage) -> dict:
    """v4 Invoke → Legacy Request"""

def result_to_legacy_response(message: ResultMessage) -> dict:
    """v4 Result → Legacy Response"""

def event_to_legacy_notification(message: EventMessage) -> dict:
    """v4 Event → Legacy Notification"""

def cancel_to_legacy_request(message: CancelMessage) -> dict:
    """v4 Cancel → Legacy Request"""
```

**转换映射表:**

| 旧版 JSON-RPC | v4 协议消息 |
|---------------|-------------|
| `handshake` | `InitializeMessage` |
| `call_handler` | `InvokeMessage(capability="handler.invoke")` |
| `call_context_function` | `InvokeMessage(capability="internal.legacy.call_context_function")` |
| `handler_stream_start/delta/end` | `EventMessage(phase="started/delta/completed/failed")` |
| `cancel` | `CancelMessage` |

**常量:**

```python
LEGACY_JSONRPC_VERSION = "2.0"
LEGACY_CONTEXT_CAPABILITY = "internal.legacy.call_context_function"
LEGACY_HANDSHAKE_METADATA_KEY = "legacy_handshake_payload"
LEGACY_PLUGIN_KEYS_METADATA_KEY = "legacy_plugin_keys"
LEGACY_ADAPTER_MESSAGE_EVENT = 3
```

---

### 运行时层 (runtime/)

运行时层负责把协议、传输、插件加载和生命周期管理拼成一条完整执行链。

#### `__init__.py` - 模块导出

```python
from .capability_router import CapabilityRouter, StreamExecution
from .handler_dispatcher import HandlerDispatcher
from .peer import Peer
from .transport import (
    MessageHandler,
    StdioTransport,
    Transport,
    WebSocketClientTransport,
    WebSocketServerTransport,
)

__all__ = [
    "CapabilityRouter",
    "HandlerDispatcher",
    "MessageHandler",
    "Peer",
    "StdioTransport",
    "StreamExecution",
    "Transport",
    "WebSocketClientTransport",
    "WebSocketServerTransport",
]
```

**设计说明**: loader/bootstrap 等编排细节保留在子模块中，不作为根级稳定契约。

---

#### `peer.py` - 核心通信端点

实现 Plugin ↔ Core 的对称通信模型。

**核心方法:**

```python
class Peer:
    # 生命周期
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def wait_closed(self) -> None: ...
    async def wait_until_remote_initialized(self, timeout: float = 30.0) -> None: ...

    # 初始化
    async def initialize(self, handlers, metadata, provided_capabilities) -> InitializeOutput: ...

    # Capability 调用
    async def invoke(self, capability, payload, stream=False) -> dict: ...
    async def invoke_stream(self, capability, payload) -> AsyncIterator[EventMessage]: ...

    # 取消
    async def cancel(self, request_id, reason="user_cancelled") -> None: ...

    # Handler 设置
    def set_initialize_handler(self, handler: InitializeHandler): ...
    def set_invoke_handler(self, handler: InvokeHandler): ...
    def set_cancel_handler(self, handler: CancelHandler): ...
```

**远程元数据缓存 (新增):**

```python
# 初始化后可用
remote_peer: PeerInfo                           # 远端身份信息
remote_handlers: list[HandlerDescriptor]        # 远端声明的处理器
remote_provided_capabilities: list[CapabilityDescriptor]  # 远端提供的内置能力
remote_capabilities: list[CapabilityDescriptor] # 远端能力描述符
remote_capability_map: dict[str, CapabilityDescriptor]  # 能力名到描述符的映射
remote_metadata: dict[str, Any]                 # 握手元数据
```

**内部状态:**

```python
self._pending_results: dict[str, asyncio.Future[ResultMessage]]  # 普通调用
self._pending_streams: dict[str, asyncio.Queue]                  # 流式调用
self._inbound_tasks: dict[str, tuple[Task, CancelToken]]         # 入站任务
self._remote_initialized: asyncio.Event                          # 远端初始化状态
self._unusable: bool                                             # 连接是否不可用
```

**错误处理方法:**

```python
async def _fail_connection(self, error: AstrBotError) -> None:
    """统一处理连接失败"""

async def _reject_initialize(self, message, error) -> None:
    """拒绝初始化并标记连接不可用"""
```

---

#### `transport.py` - 传输层实现

抽象传输层，支持多种通信方式。

**类层次:**

```
Transport (ABC)
├── StdioTransport        # 进程间通信 (stdin/stdout)
├── WebSocketServerTransport  # WebSocket 服务端
└── WebSocketClientTransport  # WebSocket 客户端
```

**StdioTransport 特性:**

- 支持作为父进程启动子进程 (`command` 参数)
- 支持直接读写 stdin/stdout
- 自动处理进程生命周期

**WebSocket 特性:**

- 心跳机制 (通过 `heartbeat` 参数配置)
- 单连接限制 (Server 端)
- 自动重连需要外部实现

---

#### `loader.py` - 插件加载器

负责插件发现、环境准备、配置规范化和实例化。

**核心类型:**

```python
@dataclass
class PluginSpec:
    name: str
    plugin_dir: Path
    manifest_path: Path
    requirements_path: Path
    python_version: str
    manifest_data: dict[str, Any]

@dataclass
class LoadedHandler:
    descriptor: HandlerDescriptor
    callable: Any
    owner: Any
    legacy_context: Any | None = None

@dataclass
class LoadedCapability:  # 新增
    descriptor: CapabilityDescriptor
    callable: Any
    owner: Any
    stream_handler: Any | None = None

@dataclass
class LoadedPlugin:
    plugin: PluginSpec
    handlers: list[LoadedHandler]
    capabilities: list[LoadedCapability]  # 新增
    instances: list[Any]
```

**核心函数:**

```python
def discover_plugins(plugins_dir: Path) -> PluginDiscoveryResult:
    """扫描插件目录，发现所有有效插件"""

def load_plugin_spec(plugin_dir: Path) -> PluginSpec:
    """从插件目录加载插件规范"""

def load_plugin(plugin: PluginSpec) -> LoadedPlugin:
    """加载插件，返回 Handler 和 Capability 列表"""

class PluginEnvironmentManager:
    """使用 uv 管理插件虚拟环境"""
    def prepare_environment(self, plugin: PluginSpec) -> Path:
        """准备插件 Python 环境，返回 python 路径"""
```

**配置规范化 (新增):**

```python
def _load_plugin_config(plugin: PluginSpec) -> dict[str, Any]:
    """加载插件配置"""

def _normalize_config_value(value, schema) -> Any:
    """规范化配置值，严格类型检查"""
    # 支持 object, list, dict, int, float, bool, string 类型
    # 排除 bool 伪装成 int 的情况
```

**Legacy 上下文共享 (重要修复):**

```python
# 同一插件共享一个 LegacyContext 实例
shared_legacy_context: LegacyContext | None = None
# 这与旧版 StarManager 行为一致
```

**Handler ID 格式:**

```
{plugin_name}:{module}.{ClassName}.{method_name}
```

---

#### `handler_dispatcher.py` - Handler 分发器

处理 `handler.invoke` Capability 的调用。

```python
class HandlerDispatcher:
    async def invoke(self, message, cancel_token) -> dict[str, Any]:
        """调用指定 Handler"""

    async def cancel(self, request_id: str) -> None:
        """取消正在执行的 Handler"""

    async def _run_handler(self, loaded, event, ctx) -> None:
        """执行 Handler，处理同步/异步/生成器返回值"""

    def _build_args(self, handler, event, ctx) -> list[Any]:
        """根据签名注入 event 和 ctx 参数"""
```

**CapabilityDispatcher (新增):**

```python
class CapabilityDispatcher:
    """与 HandlerDispatcher 并行的 capability 分发器"""

    async def dispatch(self, capability, payload, cancel_token, request_id):
        """分发 capability 调用"""

    # 支持参数注入: Context, CancelToken, payload
    # 支持流式 capability (async generator 或 StreamExecution)
    # 支持取消传播
```

**参数注入规则:**

| 参数名 | 注入值 |
|--------|--------|
| `event` | `MessageEvent` 实例 |
| `ctx` / `context` | `Context` 实例 |
| 类型注解 `MessageEvent` | `MessageEvent` 实例 |
| 类型注解 `Context` | `Context` 实例 |
| 类型注解 `CancelToken` | `CancelToken` 实例 |
| `legacy_args` | 命令参数、regex 捕获组 |

**结果处理:**

| 返回类型 | 处理方式 |
|----------|----------|
| `MessageEventResult` | 调用 `platform.send_chain` |
| `MessageChain` | 调用 `platform.send_chain` |
| `PlainTextResult` | 调用 `event.reply` |
| `dict` 含 "text" 键 | 提取 text 并回复 |

---

#### `capability_router.py` - Capability 路由器

管理和路由 Capability 调用。

```python
class CapabilityRouter:
    def register(self, descriptor, call_handler=None, stream_handler=None, exposed=True):
        """注册 Capability"""

    def unregister(self, name: str) -> bool:
        """注销 Capability"""

    def contains(self, name: str) -> bool:
        """检查能力是否存在"""

    async def execute(self, capability, payload, stream, cancel_token, request_id):
        """执行 Capability 调用"""

@dataclass
class StreamExecution:
    iterator: AsyncIterator[dict[str, Any]]
    finalize: Callable[[list[dict]], dict[str, Any]]
```

**SessionRef 目标解析 (新增):**

```python
def resolve_target(payload: dict) -> dict[str, Any]:
    """从 payload.target 解析会话引用，支持 session 字段和 payload 转换"""
```

**内置 Capabilities (15 个):**

| Capability | 功能 | 流式 |
|------------|------|------|
| `llm.chat` | 对话 (返回文本) | 否 |
| `llm.chat_raw` | 对话 (返回完整响应) | 否 |
| `llm.stream_chat` | 流式对话 | 是 |
| `memory.search` | 搜索记忆 | 否 |
| `memory.get` | 获取记忆 | 否 |
| `memory.save` | 保存记忆 | 否 |
| `memory.delete` | 删除记忆 | 否 |
| `db.get` | 读取 KV | 否 |
| `db.set` | 写入 KV | 否 |
| `db.delete` | 删除 KV | 否 |
| `db.list` | 列出 KV | 否 |
| `platform.send` | 发送消息 | 否 |
| `platform.send_image` | 发送图片 | 否 |
| `platform.send_chain` | 发送消息链 | 否 |
| `platform.get_members` | 获取群成员 | 否 |

---

#### `bootstrap.py` - 运行时启动器

定义三种运行模式。

**运行模式:**

| 模式 | 类 | 用途 |
|------|-----|------|
| Supervisor | `SupervisorRuntime` | 管理多插件，聚合 Handler |
| Worker | `PluginWorkerRuntime` | 单插件进程，处理 Handler 调用 |
| WebSocket | `run_websocket_server()` | 开发调试用 WebSocket 服务 |

```python
class WorkerSession:
    """Supervisor 管理的单插件会话"""
    async def start(self) -> None: ...
    async def invoke_handler(self, handler_id, event_payload, request_id) -> dict: ...
    async def cancel(self, request_id) -> None: ...

class SupervisorRuntime:
    """Supervisor 运行时"""
    async def start(self) -> None:
        # 1. 发现插件
        # 2. 为每个插件启动 Worker 进程
        # 3. 聚合 Handler 并向 Core 初始化

    def _handle_worker_closed(self, worker_name: str) -> None:
        """处理 Worker 连接关闭"""

class PluginWorkerRuntime:
    """Worker 运行时"""
    async def start(self) -> None:
        # 1. 加载插件
        # 2. 创建 Dispatcher
        # 3. 向 Supervisor 初始化

    async def _run_lifecycle(self, method_name: str, ctx) -> None:
        """运行生命周期回调 (on_start/on_stop)"""
```

**连接关闭处理 (新增):**

```python
# WorkerSession 新增 on_closed 回调参数
# 清理逻辑包括：
# - 从 handler_to_worker 移除对应 handlers
# - 从 capability_router 注销 capabilities
# - 从 loaded_plugins 移除
# - 取消 stale requests
```

**Handler 冲突检测 (新增):**

```python
def _register_handler(self, handler_id: str, worker_name: str) -> bool:
    """检测 handler ID 冲突并输出警告"""
```

---

### 客户端层 (clients/)

客户端层提供类型安全的 Capability 调用接口。

#### `_proxy.py` - Capability 代理

```python
class CapabilityProxy:
    async def call(self, name: str, payload: dict) -> dict[str, Any]:
        """普通调用"""

    async def stream(self, name: str, payload: dict) -> AsyncIterator[dict[str, Any]]:
        """流式调用"""

    def _ensure_available(self, name: str, *, stream: bool) -> None:
        """确保能力可用且支持指定调用模式"""
```

**设计要点:**
- 从 `peer.__dict__` 读取 `remote_capability_map` 和 `remote_peer`，避免 `MagicMock` 误判
- 支持 `phase="delta"` 事件的流式响应处理

---

#### `llm.py` - LLM 客户端

```python
class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str

class LLMResponse(BaseModel):
    text: str
    usage: dict[str, Any] | None = None
    finish_reason: str | None = None
    tool_calls: list[dict[str, Any]] = []

class LLMClient:
    async def chat(self, prompt, system=None, history=None, model=None, temperature=None, **kwargs) -> str:
        """简单对话，返回文本"""

    async def chat_raw(self, prompt, **kwargs) -> LLMResponse:
        """完整对话，返回结构化响应"""

    async def stream_chat(self, prompt, system=None, history=None, **kwargs) -> AsyncGenerator[str, None]:
        """流式对话"""
```

**支持参数:**
- `prompt` - 用户输入
- `system` - 系统提示词
- `history` - 对话历史 (`ChatMessage` 列表)
- `model` - 指定模型
- `temperature` - 采样温度 (0-1)
- `**kwargs` - 额外透传参数（如 `image_urls`、`tools`）

---

#### `db.py` - 数据库客户端

```python
class DBClient:
    async def get(self, key: str) -> dict[str, Any] | None: ...
    async def set(self, key: str, value: dict[str, Any]) -> None: ...
    async def delete(self, key: str) -> None: ...
    async def list(self, prefix: str | None = None) -> list[str]: ...
```

**与旧版对比:**
- 旧版：`Context.put_kv_data()`, `Context.get_kv_data()`
- 新版：`ctx.db.set()`, `ctx.db.get()`, `ctx.db.list()`

---

#### `memory.py` - 记忆客户端

```python
class MemoryClient:
    async def search(self, query: str) -> list[dict[str, Any]]: ...
    async def get(self, key: str) -> dict[str, Any] | None: ...
    async def save(self, key: str, value: dict[str, Any] | None = None, **extra) -> None: ...
    async def delete(self, key: str) -> None: ...
```

**与 DBClient 区别:**
- MemoryClient 支持**向量语义搜索**
- 适用于存储用户偏好、对话摘要、AI 推理缓存

---

#### `platform.py` - 平台客户端

```python
class PlatformClient:
    async def send(self, session: str | SessionRef, text: str) -> dict[str, Any]: ...
    async def send_image(self, session: str | SessionRef, image_url: str) -> dict[str, Any]: ...
    async def send_chain(self, session: str | SessionRef, chain: list[dict]) -> dict[str, Any]: ...
    async def get_members(self, session: str | SessionRef) -> list[dict[str, Any]]: ...
```

**SessionRef 支持 (新增):**

```python
def _build_target_payload(self, session: str | SessionRef) -> dict:
    """支持 SessionRef 类型，提取 target 字段"""
```

---

### API 层 (api/)

API 层作为兼容层，通过 thin re-export 方式暴露旧版 API。

#### 兼容层设计

```python
# api/__init__.py
from . import basic, components, event, message, message_components, platform, provider, star

# api/star/context.py - Legacy Context 导出
from ..._legacy_api import LegacyContext as Context

# api/components/command.py - CommandComponent 导出
from ..._legacy_api import CommandComponent

# api/event/filter.py - filter 命名空间
class _FilterNamespace:
    command = staticmethod(command)
    regex = staticmethod(regex)
    permission = staticmethod(permission)
    event_message_type = staticmethod(event_message_type)
    platform_adapter_type = staticmethod(platform_adapter_type)
filter = _FilterNamespace()

# api/message/chain.py - MessageChain 兼容类
class MessageChain:
    def message(self, text) -> "MessageChain": ...
    def at(self, name, qq) -> "MessageChain": ...
    def at_all(self) -> "MessageChain": ...
    def url_image(self, url) -> "MessageChain": ...
    def file_image(self, path) -> "MessageChain": ...
    def base64_image(self, base64_str) -> "MessageChain": ...
    def use_t2i(self, use_t2i) -> "MessageChain": ...
    def to_payload(self) -> list[dict]: ...
    def get_plain_text(self) -> str: ...
    def is_plain_text_only(self) -> bool: ...

# api/message/components.py - 消息组件
class Plain, Image, At, AtAll, Reply, Node, Face, File, Record, Video, ...
ComponentTypes: dict[str, type[BaseMessageComponent]]
```

**不支持的功能 (显式报错):**
- `custom_filter` - 自定义过滤器
- `after_message_sent` - 消息发送后钩子
- `on_astrbot_loaded` / `on_platform_loaded` - 加载钩子
- `on_decorating_result` - 结果装饰钩子
- `on_llm_request` / `on_llm_response` - LLM 钩子
- `command_group` - 命令组

---

### 核心文件

#### 顶层导出 (`__init__.py`)

```python
from .context import Context
from .decorators import on_command, on_event, on_message, on_schedule, provide_capability, require_admin
from .errors import AstrBotError
from .events import MessageEvent
from .star import Star

__all__ = [
    "AstrBotError",
    "Context",
    "MessageEvent",
    "Star",
    "on_command",
    "on_event",
    "on_message",
    "on_schedule",
    "provide_capability",
    "require_admin",
]
```

**设计原则**: 旧版兼容能力由 `astrbot_sdk.api` 与 `astrbot_sdk.compat` 承接。

---

#### `star.py` - Star 基类

```python
class Star:
    __handlers__: tuple[str, ...] = ()

    def __init_subclass__(cls, **kwargs):
        """收集子类的 Handler 方法名到 __handlers__"""

    async def on_start(self, ctx) -> None:
        """生命周期钩子：启动时"""

    async def on_stop(self, ctx) -> None:
        """生命周期钩子：停止时"""

    async def on_error(self, error, event, ctx) -> None:
        """错误处理钩子"""

    @classmethod
    def __astrbot_is_new_star__(cls) -> bool:
        return True  # 新版 Star 返回 True
```

**Handler 发现机制:**

1. `@on_command` 等装饰器在方法上设置 `__astrbot_handler_meta__`
2. `Star.__init_subclass__` 遍历 MRO 收集带 meta 的方法名
3. Loader 读取 `__handlers__` 并构建 `HandlerDescriptor`

---

#### `decorators.py` - 装饰器

```python
# 命令触发
@on_command("hello", aliases=["hi"], description="问候")
def hello_handler(event): ...

# 消息触发
@on_message(regex=r"^ping", keywords=["ping"], platforms=["qq"])
def ping_handler(event): ...

# 事件触发
@on_event("group_join")
def join_handler(event): ...

# 定时触发
@on_schedule(cron="0 9 * * *")  # 或 interval_seconds=60
def scheduled_handler(): ...

# 权限
@on_command("admin")
@require_admin
def admin_handler(event): ...

# 声明能力 (新增)
@provide_capability(
    name="my.custom_action",
    description="自定义操作",
    input_schema={...},
    output_schema={...},
)
async def custom_action(payload, ctx, cancel_token): ...
```

---

#### `context.py` - 运行时 Context

```python
@dataclass(slots=True)
class CancelToken:
    def cancel(self) -> None: ...
    @property
    def cancelled(self) -> bool: ...
    async def wait(self) -> None: ...
    def raise_if_cancelled(self) -> None: ...

class Context:
    def __init__(self, *, peer, plugin_id, cancel_token=None, logger=None):
        proxy = CapabilityProxy(peer)
        self.peer = peer
        self.llm = LLMClient(proxy)
        self.memory = MemoryClient(proxy)
        self.db = DBClient(proxy)
        self.platform = PlatformClient(proxy)
        self.plugin_id = plugin_id
        self.logger = logger or base_logger.bind(plugin_id=plugin_id)
        self.cancel_token = cancel_token or CancelToken()
```

---

#### `events.py` - 事件定义

```python
@dataclass
class PlainTextResult:
    text: str

ReplyHandler = Callable[[str], Awaitable[None]]

class MessageEvent:
    def __init__(self, *, text, user_id, group_id, platform, session_id, raw, context, reply_handler):
        self.text = text
        self.user_id = user_id
        self.group_id = group_id
        self.platform = platform
        self.session_id = session_id or group_id or user_id or ""
        self.raw = raw or {}
        self._reply_handler = reply_handler

    @classmethod
    def from_payload(cls, payload, context=None, reply_handler=None) -> "MessageEvent":
        """从 payload 构造"""

    def to_payload(self) -> dict[str, Any]:
        """序列化为 payload"""

    async def reply(self, text: str) -> None:
        """回复消息 (依赖注入 reply_handler)"""

    def bind_reply_handler(self, reply_handler: ReplyHandler) -> None:
        """绑定回复处理器"""

    def plain_result(self, text: str) -> PlainTextResult:
        """创建纯文本结果"""

    @property
    def session_ref(self) -> SessionRef:
        """获取 SessionRef 对象 (新增)"""
```

---

#### `errors.py` - 错误模型

```python
class ErrorCodes:
    """错误码常量类"""
    # 非重试错误
    LLM_NOT_CONFIGURED = "llm_not_configured"
    CAPABILITY_NOT_FOUND = "capability_not_found"
    PERMISSION_DENIED = "permission_denied"
    LLM_ERROR = "llm_error"
    INVALID_INPUT = "invalid_input"
    CANCELLED = "cancelled"
    PROTOCOL_VERSION_MISMATCH = "protocol_version_mismatch"
    PROTOCOL_ERROR = "protocol_error"
    INTERNAL_ERROR = "internal_error"

    # 可重试错误
    CAPABILITY_TIMEOUT = "capability_timeout"
    NETWORK_ERROR = "network_error"
    LLM_TEMPORARY_ERROR = "llm_temporary_error"

@dataclass
class AstrBotError(Exception):
    code: str
    message: str
    hint: str = ""
    retryable: bool = False

    @classmethod
    def cancelled(cls, message="调用被取消") -> "AstrBotError": ...

    @classmethod
    def capability_not_found(cls, name: str) -> "AstrBotError": ...

    @classmethod
    def invalid_input(cls, message: str) -> "AstrBotError": ...

    @classmethod
    def protocol_version_mismatch(cls, message: str) -> "AstrBotError": ...

    @classmethod
    def protocol_error(cls, message: str) -> "AstrBotError": ...

    @classmethod
    def internal_error(cls, message: str) -> "AstrBotError": ...

    def to_payload(self) -> dict[str, object]: ...

    @classmethod
    def from_payload(cls, payload) -> "AstrBotError": ...
```

---

#### `_legacy_api.py` - 兼容层

```python
class LegacyConversationManager:
    """旧版会话管理器兼容实现"""
    async def new_conversation(self, unified_msg_origin, ...) -> str: ...
    async def switch_conversation(self, unified_msg_origin, conversation_id) -> None: ...
    async def delete_conversation(self, unified_msg_origin, conversation_id) -> None: ...
    async def get_curr_conversation_id(self, unified_msg_origin) -> str | None: ...
    async def get_conversation(self, unified_msg_origin, conversation_id, ...) -> dict | None: ...
    async def get_conversations(self, ...) -> list[dict]: ...
    async def update_conversation(self, unified_msg_origin, conversation_id, ...) -> None: ...
    async def add_message_pair(self, cid, user_message, assistant_message) -> None: ...

class LegacyContext:
    """v3 Context 兼容实现"""
    def __init__(self, plugin_id: str):
        self.plugin_id = plugin_id
        self._runtime_context: NewContext | None = None
        self.conversation_manager = LegacyConversationManager(self)

    def bind_runtime_context(self, runtime_context: NewContext) -> None: ...
    def _register_component(self, *components) -> None: ...
    async def execute_registered_function(self, func_full_name, args) -> Any: ...
    async def call_context_function(self, func_full_name, args) -> dict: ...

    async def llm_generate(self, chat_provider_id, prompt, ...) -> LLMResponse: ...
    async def tool_loop_agent(self, chat_provider_id, prompt, ...) -> LLMResponse: ...
    async def send_message(self, session, message_chain) -> None: ...
    async def put_kv_data(self, key, value) -> None: ...
    async def get_kv_data(self, key, default=None) -> Any: ...
    async def delete_kv_data(self, key) -> None: ...

class LegacyStar(Star):
    """旧版 astrbot.api.star.Star 兼容基类"""
    def __init__(self, context: LegacyContext | None = None, config: Any | None = None): ...
    @classmethod
    def __astrbot_is_new_star__(cls) -> bool:
        return False

class CommandComponent(LegacyStar):
    """v3 插件基类 (LegacyStar 的别名)"""

def register(name=None, author=None, desc=None, version=None, repo=None):
    """旧版插件元数据装饰器兼容入口"""
```

**已废弃方法 (抛出显式迁移错误):**
- `get_filtered_conversations()`
- `get_human_readable_context()`
- `add_llm_tools()`

---

#### `cli.py` - 命令行接口

```python
@click.group()
def cli(): ...

@cli.command()
@click.option("--plugins-dir", default="plugins")
def run(plugins_dir: Path):
    """启动 Supervisor"""
    asyncio.run(run_supervisor(plugins_dir=plugins_dir))

@cli.command(hidden=True)
@click.option("--plugin-dir", required=True)
def worker(plugin_dir: Path):
    """启动 Worker (内部命令)"""
    asyncio.run(run_plugin_worker(plugin_dir=plugin_dir))

@cli.command(hidden=True)
@click.option("--port", default=8765)
@click.option("--host", default="localhost")
@click.option("--path", default="/ws")
def websocket(port: int, host: str, path: str):
    """启动 WebSocket 服务 (调试用)"""
```

---

## 五大硬性协议规则

### 1. 统一 id 字段

**规则**: 所有协议消息必须有 `id` 字段。

```python
class InitializeMessage(_MessageBase):
    type: Literal["initialize"] = "initialize"
    id: str  # 必须有
    ...

class ResultMessage(_MessageBase):
    type: Literal["result"] = "result"
    id: str  # 必须有
    ...
```

### 2. event 仅用于 stream=true

**规则**: `EventMessage` 只在流式调用中使用。

```python
# Peer._handle_result
if queue is not None:  # stream=true 的 pending stream
    await queue.put(AstrBotError.protocol_error("stream=true 调用不应收到 result"))

# Peer._handle_event
if future is not None:  # stream=false 的 pending result
    future.set_exception(AstrBotError.protocol_error("stream=false 调用不应收到 event"))
```

### 3. handler.invoke 用于回调

**规则**: 插件 Handler 调用通过 `handler.invoke` Capability。

```python
# HandlerDispatcher 中
if message.capability != "handler.invoke":
    raise AstrBotError.capability_not_found(message.capability)
```

### 4. cancel 作为 request-stop

**规则**: 取消请求发送 `CancelMessage`，等待终端事件。

```python
async def cancel(self, request_id: str, reason: str = "user_cancelled") -> None:
    await self._send(CancelMessage(id=request_id, reason=reason))

# Worker 收到后
token.cancel()
task.cancel()
```

### 5. initialize 失败处理

**规则**: 初始化失败后连接进入不可用状态并关闭。

```python
async def _reject_initialize(self, message, error):
    await self._send(ResultMessage(id=message.id, kind="initialize_result", success=False, error=...))
    self._unusable = True
    self._remote_initialized.set()
    await self.stop()
```

---

## 数据流与通信模型

### 初始化流程

```
┌────────┐                              ┌────────┐
│  Core  │                              │ Plugin │
└───┬────┘                              └───┬────┘
    │                                       │
    │──── InitializeMessage ───────────────>│
    │   {id, peer, handlers,                │
    │    provided_capabilities, metadata}   │
    │                                       │
    │<─── ResultMessage ────────────────────│
    │   {id, kind="initialize_result",      │
    │    success, output: {peer,            │
    │    capabilities, metadata}}           │
    │                                       │
```

### Capability 调用流程 (普通)

```
┌────────┐                              ┌────────┐
│  Core  │                              │ Plugin │
└───┬────┘                              └───┬────┘
    │                                       │
    │──── InvokeMessage ───────────────────>│
    │   {id, capability, input, stream=false}│
    │                                       │
    │<─── ResultMessage ────────────────────│
    │   {id, success, output/error}         │
    │                                       │
```

### Capability 调用流程 (流式)

```
┌────────┐                              ┌────────┐
│  Core  │                              │ Plugin │
└───┬────┘                              └───┬────┘
    │                                       │
    │──── InvokeMessage ───────────────────>│
    │   {id, capability, input, stream=true}│
    │                                       │
    │<─── EventMessage(phase="started") ────│
    │                                       │
    │<─── EventMessage(phase="delta") ──────│
    │   {data: {...}}                       │
    │<─── EventMessage(phase="delta") ──────│
    │   ...                                 │
    │                                       │
    │<─── EventMessage(phase="completed") ──│
    │   {output: {...}}                     │
    │                                       │
```

### 取消流程

```
┌────────┐                              ┌────────┐
│  Core  │                              │ Plugin │
└───┬────┘                              └───┬────┘
    │                                       │
    │──── CancelMessage ───────────────────>│
    │   {id, reason}                        │
    │                                       │
    │<─── EventMessage(phase="failed") ─────│
    │   {error: {code: "cancelled"}}        │
    │                                       │
```

---

## 扩展机制

### 添加新 Capability

1. 在 `protocol/descriptors.py` 中定义 Schema 常量：

```python
MY_CAPABILITY_INPUT_SCHEMA = {"type": "object", "properties": {...}, "required": [...]}
MY_CAPABILITY_OUTPUT_SCHEMA = {"type": "object", "properties": {...}}
BUILTIN_CAPABILITY_SCHEMAS["my.custom_action"] = {
    "input": MY_CAPABILITY_INPUT_SCHEMA,
    "output": MY_CAPABILITY_OUTPUT_SCHEMA,
}
```

2. 在 `CapabilityRouter._register_builtin_capabilities()` 中注册：

```python
self.register(
    CapabilityDescriptor(
        name="my.custom_action",
        description="自定义操作",
        input_schema=MY_CAPABILITY_INPUT_SCHEMA,
        output_schema=MY_CAPABILITY_OUTPUT_SCHEMA,
        supports_stream=False,
        cancelable=False,
    ),
    call_handler=my_handler,
    exposed=True,
)
```

3. 在 `clients/` 中添加客户端封装（可选）。

### 添加新 Trigger 类型

1. 在 `descriptors.py` 中定义新的 Trigger 类：

```python
class CustomTrigger(_DescriptorBase):
    type: Literal["custom"] = "custom"
    custom_field: str
```

2. 更新 `Trigger` 联合类型：

```python
Trigger = Annotated[
    CommandTrigger | MessageTrigger | EventTrigger | ScheduleTrigger | CustomTrigger,
    Field(discriminator="type"),
]
```

3. 在 `decorators.py` 中添加装饰器：

```python
def on_custom(custom_field: str):
    def decorator(func):
        meta = _get_or_create_meta(func)
        meta.trigger = CustomTrigger(custom_field=custom_field)
        return func
    return decorator
```

### 添加新 Transport

1. 继承 `Transport` 基类：

```python
class MyTransport(Transport):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def send(self, payload: str) -> None: ...
```

2. 在 `runtime/__init__.py` 中导出。

---

## 实现状态

### 已完成模块

| 模块 | 文件 | 状态 | 说明 |
|------|------|------|------|
| **协议层** | `protocol/` | ✅ 完成 | |
| | `descriptors.py` | ✅ | Handler/Capability 描述符 + 16 个内置 Schema 常量 |
| | `messages.py` | ✅ | 5 种消息类型 + parse_message |
| | `legacy_adapter.py` | ✅ | JSON-RPC ↔ v4 双向转换 |
| **运行时层** | `runtime/` | ✅ 完成 | |
| | `peer.py` | ✅ | 对称通信端点 + 取消 + 流式 + 远程元数据缓存 |
| | `transport.py` | ✅ | Stdio + WebSocket Server/Client |
| | `loader.py` | ✅ | 插件发现 + 环境管理 + 配置规范化 + Capability 支持 |
| | `handler_dispatcher.py` | ✅ | Handler 分发 + CapabilityDispatcher + 参数注入增强 |
| | `capability_router.py` | ✅ | 能力路由 + 15 个内置能力 + SessionRef 支持 |
| | `bootstrap.py` | ✅ | Supervisor + Worker + WebSocket + 连接关闭处理 |
| **客户端层** | `clients/` | ✅ 完成 | |
| | `_proxy.py` | ✅ | CapabilityProxy 代理 |
| | `llm.py` | ✅ | LLM 客户端 (chat/chat_raw/stream_chat) |
| | `memory.py` | ✅ | Memory 客户端 (search/get/save/delete) |
| | `db.py` | ✅ | DB 客户端 (get/set/delete/list) |
| | `platform.py` | ✅ | Platform 客户端 (支持 SessionRef) |
| **API 层** | `api/` | ✅ 完成 | 兼容层 |
| | `star/context.py` | ✅ | LegacyContext 导出 |
| | `components/command.py` | ✅ | CommandComponent 导出 |
| | `event/filter.py` | ✅ | filter 命名空间 + 平台/消息类型过滤 |
| | `message/chain.py` | ✅ | MessageChain + to_payload |
| | `message/components.py` | ✅ | 20+ 消息组件类型 |
| | `basic/astrbot_config.py` | ✅ | AstrBotConfig + save_config |
| | `basic/` | ✅ | 基础实体与配置 |
| | `platform/` | ✅ | 平台元数据 |
| | `provider/` | ✅ | Provider 实体 |
| **核心文件** | 根目录 | ✅ 完成 | |
| | `__init__.py` | ✅ | 顶层导出 |
| | `star.py` | ✅ | Star 基类 + Handler 发现 |
| | `context.py` | ✅ | Context + CancelToken |
| | `decorators.py` | ✅ | on_command/on_message/on_event/on_schedule/provide_capability |
| | `events.py` | ✅ | MessageEvent + SessionRef |
| | `errors.py` | ✅ | AstrBotError + ErrorCodes |
| | `_legacy_api.py` | ✅ | LegacyContext + LegacyStar + register + LegacyConversationManager |
| | `cli.py` | ✅ | Click 命令行工具 |
| | `__main__.py` | ✅ | python -m astrbot_sdk 入口 |

### 测试覆盖

测试文件位于 `tests_v4/` 目录，共 **40 个** Python 文件：

```
tests_v4/
├── conftest.py                   # pytest 配置与共享 fixtures
├── helpers.py                    # 测试辅助函数
│
├── # 协议层测试
├── test_protocol_messages.py     # 协议消息模型
├── test_protocol_descriptors.py  # 描述符测试
├── test_protocol_package.py      # 协议包测试
├── test_protocol_legacy_adapter.py # Legacy 适配器测试
├── test_legacy_adapter.py        # LegacyAdapter 运行时测试
│
├── # 运行时层测试
├── test_peer.py                  # Peer 测试
├── test_transport.py             # Transport 测试
├── test_capability_router.py     # CapabilityRouter 测试
├── test_handler_dispatcher.py    # HandlerDispatcher 测试
├── test_loader.py                # 加载器测试
├── test_bootstrap.py             # Bootstrap 测试
├── test_runtime.py               # 运行时测试
├── test_runtime_integration.py   # 运行时集成测试
│
├── # 核心模块测试
├── test_context.py               # Context 测试
├── test_events.py                # 事件测试
├── test_decorators.py            # 装饰器测试
│
├── # API 层测试
├── test_api_modules.py           # API 模块测试
├── test_api_decorators.py        # API 装饰器测试
├── test_api_event_filter.py      # filter 命名空间测试
├── test_api_legacy_context.py    # Legacy Context 测试
├── test_api_message_components.py # 消息组件测试
├── test_api_contract.py          # API 契约测试
│
├── # 客户端层测试
├── test_clients_module.py        # 客户端模块测试
├── test_llm_client.py            # LLM 客户端测试
├── test_memory_client.py         # Memory 客户端测试
├── test_db_client.py             # DB 客户端测试
├── test_platform_client.py       # Platform 客户端测试
├── test_capability_proxy.py      # CapabilityProxy 测试
│
├── # 兼容性迁移测试
├── test_script_migrations.py     # 脚本迁移测试
├── test_supervisor_migration.py  # Supervisor 迁移测试
├── test_legacy_plugin_integration.py # 旧版插件集成测试
├── test_top_level_modules.py     # 顶层模块测试
│
├── # 入口点测试
├── test_entrypoints.py           # 入口点测试
├── test_conftest_fixtures.py     # pytest fixtures 测试
└── __init__.py                   # 包初始化文件
```

---

## 版本兼容性

| 组件 | v3 | v4 |
|------|----|----|
| 插件基类 | `CommandComponent` | `Star` |
| Context | `LegacyContext` | `Context` |
| 装饰器 | `@filter.command` | `@on_command` |
| 协议 | JSON-RPC 2.0 | 自定义协议 |
| 通信 | 单向 | 双向对称 |

**兼容策略**: `LegacyAdapter` 实现协议转换，`CommandComponent` 继承 `Star` 并标记 `__astrbot_is_new_star__ = False`。

**迁移指南:**

```python
# 旧版 (将在未来版本废弃)
from astrbot_sdk.api.event import AstrMessageEvent
from astrbot_sdk.api.star.context import Context

# 新版 (推荐)
from astrbot_sdk.events import MessageEvent
from astrbot_sdk.context import Context
```

**兼容层入口:**

```python
# 通过 astrbot_sdk.api 和 astrbot_sdk.compat 访问旧版 API
from astrbot_sdk.api.star import Context, Star
from astrbot_sdk.compat import LegacyContext, CommandComponent
```
