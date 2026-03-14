# AstrBot SDK v4 架构分析报告

> 版本：0.1.0
> 生成日期：2026-03-14
> 分析范围：`src-new/astrbot_sdk` 及相关测试

---

## 目录

1. [概述](#1-概述)
2. [优点](#2-优点)
3. [缺点](#3-缺点)
4. [设计理念](#4-设计理念)
5. [核心架构](#5-核心架构)
6. [实现思路](#6-实现思路)
7. [技术亮点](#7-技术亮点)
8. [演进规划](#8-演进规划)
9. [总结](#9-总结)

---

## 1. 概述

AstrBot SDK v4 是一个**插件化机器人框架 SDK**，实现了从旧版 JSON-RPC 协议到新一代 v4 协议的架构重构。其核心特点包括：

- **双层目标**：提供原生 v4 插件模型 + 维持旧版插件兼容
- **协议优先**：设计清晰的 v4 线协议，兼容层作为过渡
- **分层清晰**：插件作者、客户端、运行时、协议层职责明确
- **进程隔离**：Supervisor-Worker 架构，每插件独立进程
- **能力路由**：基于命名空间的 Capability 系统

### 项目结构概览

```
astrbot-sdk/
├── src-new/astrbot_sdk/    # v4 原生实现（主源码）
│   ├── protocol/            # v4 协议层（消息、描述符）
│   ├── runtime/            # 运行时核心（peer、transport、router、loader）
│   ├── clients/            # 能力客户端（llm、memory、db、platform）
│   ├── api/               # 旧 API 兼容层门面
│   ├── _legacy_*.py        # 私有兼容实现（收口边界）
│   └── astrbot/            # 旧包名 facade（受控兼容面）
├── src/                   # 旧版代码（遗留）
├── tests_v4/              # v4 测试套件
├── test_plugin/            # 测试插件示例（old/new 分离）
└── docs/                  # 文档目录
```

---

## 2. 优点

### 2.1 架构设计层面

#### 清晰的分层架构

```
┌─────────────────────────────────────────┐
│   插件作者层        │
│   Star / Context / MessageEvent        │
└─────────────────┬───────────────────┘
                  │
┌─────────────────▼───────────────────┐
│   客户端层       │
│   LLMClient / DBClient / ...        │
│   CapabilityProxy                  │
└─────────────────┬───────────────────┘
                  │
┌─────────────────▼───────────────────┐
│   运行时层  │
│   Peer / Transport                 │
│   CapabilityRouter / HandlerDispatcher│
│   loader / bootstrap               │
└─────────────────┬───────────────────┘
                  │
┌─────────────────▼───────────────────┐
│   协议层      │
│   messages / descriptors           │
│   legacy_adapter                 │
└───────────────────────────────────┘
```

每层职责单一，边界清晰，降低了理解和维护成本。

#### 协议优先的设计

v4 协议层（`protocol/messages.py`、`protocol/descriptors.py`）定义了清晰的线协议契约：

- 5 种消息类型：`InitializeMessage`、`InvokeMessage`、`ResultMessage`、`EventMessage`、`CancelMessage`
- 强类型约束：使用 Pydantic 模型进行严格验证
- 版本协商：支持 `protocol_version` 协商机制
- 流式支持：统一的 `EventMessage` 处理流式调用

这种设计使得协议与实现解耦，便于跨语言实现和协议演进。

#### 窄导出的稳定 API

顶层 `astrbot_sdk.__init__.py` 只导出 7 个核心类：

```python
from .context import Context
from .decorators import (on_command, on_event, on_message,
                        on_schedule, provide_capability, require_admin)
from .errors import AstrBotError
from .events import MessageEvent
from .star import Star
```

这种"最小稳定面"设计减少了 API 变更的影响范围，有利于长期维护。

### 2.2 兼容性设计层面

#### 三级兼容策略

| 级别 | 路径 | 策略 |
|------|------|------|
| 一级 | `astrbot.api.*` | 优先做真实兼容 |
| 二级 | `astrbot.core.*` | 按需补薄 shim |
| 三级 | 旧应用内部系统 | 不做树级复刻 |

这种分层策略避免了"全盘照搬旧架构"的陷阱，只保证真实插件使用的路径可用。

#### 私有边界收口

兼容逻辑集中在 `_legacy_api.py`、`_legacy_runtime.py`、`_legacy_loader.py` 等私有模块：

- `LegacyContext`：旧版上下文适配
- `LegacyRuntimeAdapter`：运行时执行适配
- `SessionWaiterManager`：会话等待机制

这种收口设计让兼容层可被独立演进和最终移除。

### 2.3 运行时设计层面

#### Capability 模式

基于命名空间的能力系统：

```python
# 注册能力
router.register(
    CapabilityDescriptor(
        name="my_plugin.calculate",
        description="执行计算",
        input_schema={"type": "object", ...},
        output_schema={"type": "object", ...},
    ),
    call_handler=my_calculate,
)

# 调用能力
result = await ctx.llm.chat(prompt="hello")
# 实际调用 peer.invoke("llm.chat", {"prompt": "hello"})
```

优势：
- JSON Schema 输入输出验证
- 支持同步和流式两种模式
- 统一的错误处理
- 命名空间避免冲突

#### Peer 模式

统一的对等端抽象，既是客户端也是服务端：

```python
# 作为客户端
peer = Peer(transport, PeerInfo(...))
await peer.start()
output = await peer.initialize(handlers)
result = await peer.invoke("llm.chat", {"prompt": "hello"})

# 作为服务端
peer.set_invoke_handler(my_handler)
await peer.start()
```

优势：
- 双向通信对称
- 统一的初始化握手
- 请求 ID 关联
- 取消传播机制

#### Supervisor-Worker 架构

```
AstrBot Core (Python)
        |
        v
    SupervisorRuntime (管理多插件)
        |
        +-- WorkerSession (插件 A) -- StdioTransport -- PluginWorkerRuntime
        |
        +-- WorkerSession (插件 B) -- StdioTransport -- PluginWorkerRuntime
        |
        +-- WorkerSession (插件 C) -- StdioTransport -- PluginWorkerRuntime
```

优势：
- 进程隔离，单个插件崩溃不影响其他
- 独立 Python 环境，依赖隔离
- 支持 Worker 崩溃检测和清理
- 支持分组 Worker 共享环境

### 2.4 开发体验层面

#### 完整的测试体系

```
tests_v4/
├── test_protocol.py         # 协议模型测试
├── test_peer.py            # Peer 通信测试
├── test_transport.py       # 传输层测试
├── test_loader.py          # 插件加载测试
├── test_capability_router.py # 能力路由测试
├── test_handler_dispatcher.py # 处理器分发测试
├── test_legacy_runtime.py   # Legacy 运行时测试
├── test_legacy_loader.py    # Legacy 加载器测试
├── test_api_*.py           # API 兼容性测试
├── test_new_plugin_integration.py # v4 插件集成测试
├── test_legacy_plugin_integration.py # 旧插件集成测试
└── test_grouped_environment_smoke.py # 分组环境测试
```

#### 本地开发支持

`astrbot_sdk.testing` 提供本地开发 harness：

```python
from astrbot_sdk.testing import PluginHarness, LocalRuntimeConfig

harness = PluginHarness(config=LocalRuntimeConfig(...))
await harness.start()

# 测试插件
result = await harness.invoke_handler("my_command", event)
```

优势：
- 无需启动完整 Core 即可测试
- 复用真实 loader、dispatcher
- 支持交互式开发

---

## 3. 缺点

### 3.1 架构复杂度

#### 兼容层带来的认知负担

虽然兼容逻辑被收口到私有模块，但仍需维护：

- `_legacy_api.py`：600+ 行
- `_legacy_runtime.py`：500+ 行
- `_legacy_loader.py`：400+ 行
- `_session_waiter.py`：300+ 行

对于新开发者来说，理解"为什么要这些文件"需要额外学习成本。

#### 多层抽象的调用链

一个简单的 LLM 调用需要经过：

```
ctx.llm.chat(prompt)
  -> LLMClient.chat()
    -> CapabilityProxy.call("llm.chat")
      -> Peer.invoke("llm.chat")
        -> StdioTransport.send()
          [跨进程]
        -> Peer._handle_invoke()
          -> CapabilityRouter.execute("llm.chat")
            -> Supervisor 提供的实际实现
```

这种多层调用链在调试时需要追踪多个文件。

### 3.2 兼容性限制

#### 降级兼容部分

某些能力只能"降级"实现：

- `command_group`：旧版支持树状命令帮助，新版展平成普通命令名
- legacy handshake 转 v4：只能近似恢复触发信息，原始 payload 保留在 metadata

#### 明确不支持的部分

某些旧功能完全不支持：

- `astrbot.api.agent()`：显式 `NotImplementedError`
- `register_platform_adapter`：不提供
- 旧 LLM hook / plugin hook 的完整执行链：部分实现

### 3.3 测试覆盖的挑战

#### Legacy 插件矩阵维护

`tests_v4/external_plugin_matrix.json` 维护真实插件兼容矩阵：

```json
{
  "plugins": [
    "astrbot_plugin_hapi_connector",
    "astrbot_plugin_endfield"
  ]
}
```

需要持续跟踪外部插件变更，维护成本较高。

#### 集成测试的依赖

真实集成测试需要：
- 克隆外部插件仓库
- 运行完整的 Supervisor-Worker 链路
- 处理网络和进程管理

这些测试执行较慢且容易受环境影响。

### 3.4 文档与代码的漂移

#### `refactor.md` 不再准确

架构文档明确指出：

> `refactor.md` 仅保留历史设计意图和演进说明，不再描述现状。

这意味着：
- 新开发者可能被旧文档误导
- 需要同时阅读 ARCHITECTURE.md 和 refactor.md
- 维护两份文档的成本

#### CLAUDE.md 中的 70+ 条备注

`CLAUDE.md` 记录了大量架构细节和陷阱，例如：

- 2026-03-12: Legacy handshake payloads only contain `event_type` / `handler_full_name` metadata
- 2026-03-13: Keep `astrbot_sdk.runtime` root exports narrow
- 2026-03-14: `test_plugin/old/` and `test_plugin/new/` may contain checked-in `__pycache__` artifacts

这些备注有价值但分散，不利于新人学习。

### 3.5 进程模型的开销

#### 一插件一进程

每个插件独立运行在子进程中，带来：

- 启动延迟：插件数量多时启动时间长
- 资源开销：Python 解释器和依赖的重复加载
- 调试复杂：跨进程调试不如单进程方便

虽然有共享环境分组机制（`environment_groups.py`），但仍然无法完全消除进程开销。

---

## 4. 设计理念

### 4.1 协议优先

> v4 协议层是核心，兼容层是过渡

**体现**：

- `protocol/` 目录独立设计，不依赖旧版代码
- 协议消息使用强类型 Pydantic 模型
- 协议版本协商机制
- `legacy_adapter.py` 作为协议适配层，不污染核心

**好处**：

- 协议可独立演进
- 支持跨语言实现（未来 Go/Rust 版）
- 兼容层可最终移除

### 4.2 分层清晰

> 每层有明确职责，避免耦合

**体现**：

- 插件作者层：`Star`、`Context`、`MessageEvent`
- 客户端层：`LLMClient`、`DBClient` 等
- 运行时层：`Peer`、`Transport`、`CapabilityRouter`
- 协议层：`messages`、`descriptors`

**好处**：

- 各层可独立测试
- 修改影响范围可控
- 新人容易定位问题

### 4.3 窄导出

> 顶层只暴露稳定 API

**体现**：

- `astrbot_sdk.__init__` 只导出 7 个核心类
- `astrbot_sdk.runtime.__init__` 不导出 loader/bootstrap
- `astrbot_sdk.protocol.__init__` 只导出 v4 原生模型

**好处**：

- 减少变更影响面
- 避免"意外公开内部实现"
- 长期兼容性更易保证

### 4.4 私有收口

> 兼容逻辑在私有模块

**体现**：

- `_legacy_api.py`：私有兼容 API
- `_legacy_runtime.py`：私有运行时适配
- `_legacy_loader.py`：私有加载器逻辑

**好处**：

- 兼容层可独立演进
- 不污染主代码库
- 未来可整体移除

### 4.5 受控兼容

> 不是全盘复制旧架构

**体现**：

- 三级兼容策略
- 不支持的路径显式 `NotImplementedError`
- 外部插件矩阵作为真实标准

**好处**：

- 避免维护负担无限增长
- 清晰的兼容边界
- 鼓励迁移到新 API

---

## 5. 核心架构

### 5.1 协议层（Protocol）

#### 消息类型

```python
# 1. InitializeMessage - 初始化握手
{
    "type": "initialize",
    "id": "msg_001",
    "protocol_version": "1.0",
    "peer": {"name": "plugin", "role": "plugin", "version": "v4"},
    "handlers": [...],
    "provided_capabilities": [...],
    "metadata": {}
}

# 2. InvokeMessage - 能力调用
{
    "type": "invoke",
    "id": "msg_002",
    "capability": "llm.chat",
    "input": {"prompt": "hello"},
    "stream": false
}

# 3. ResultMessage - 调用结果
{
    "type": "result",
    "id": "msg_002",
    "success": true,
    "output": {"text": "response"},
    "error": null
}

# 4. EventMessage - 流式事件
{
    "type": "event",
    "id": "msg_003",
    "phase": "delta",  # started/delta/completed/failed
    "data": {},
    "output": {},
    "error": null
}

# 5. CancelMessage - 取消请求
{
    "type": "cancel",
    "id": "msg_003",
    "reason": "user_cancelled"
}
```

#### 版本协商

```python
# PeerInfo.version: 软件版本标识（"v4"）
# protocol_version: 线协议版本（"1.0"）

# 协商过程：
# 1. 发起方发送首选 protocol_version
# 2. 响应方检查支持列表，选择最佳版本
# 3. 双方使用协商后的版本通信
```

#### 描述符系统

```python
# HandlerDescriptor - 处理器描述
@dataclass
class HandlerDescriptor:
    id: str
    trigger: Trigger  # CommandTrigger | MessageTrigger | EventTrigger | ScheduleTrigger
    permissions: Permissions
    metadata: dict[str, Any]

# CapabilityDescriptor - 能力描述
@dataclass
class CapabilityDescriptor:
    name: str              # "llm.chat"
    description: str
    input_schema: dict       # JSON Schema
    output_schema: dict      # JSON Schema
    supports_stream: bool
    cancelable: bool
```

### 5.2 运行时层（Runtime）

#### Peer

核心职责：

```python
class Peer:
    # 握手
    async def initialize(self, handlers, ...) -> InitializeOutput

    # 调用
    async def invoke(self, capability, payload) -> dict
    async def invoke_stream(self, capability, payload) -> AsyncIterator[EventMessage]

    # 取消
    async def cancel(self, request_id, reason)

    # 生命周期
    async def start()
    async def stop()
```

消息处理流程：

```
入站消息:
    ResultMessage -> 唤醒 Future
    EventMessage -> 投递到流式队列
    InitializeMessage -> 调用 initialize_handler
    InvokeMessage -> 创建任务调用 invoke_handler
    CancelMessage -> 取消对应任务

出站消息:
    initialize() -> InitializeMessage
    invoke() -> InvokeMessage(stream=False)
    invoke_stream() -> InvokeMessage(stream=True)
    cancel() -> CancelMessage
```

#### Transport

抽象传输层：

```python
class Transport(ABC):
    @abstractmethod
    async def start()
    @abstractmethod
    async def stop()
    @abstractmethod
    async def send(self, message: str)
    @abstractmethod
    def set_message_handler(self, handler)
```

实现：

- `StdioTransport`：标准输入输出（支持子进程和文件模式）
- `WebSocketServerTransport`：WebSocket 服务端
- `WebSocketClientTransport`：WebSocket 客户端

#### CapabilityRouter

能力注册与执行：

```python
class CapabilityRouter:
    # 注册
    def register(self, descriptor, *, call_handler, stream_handler, finalize)

    # 执行
    async def execute(self, capability, payload, *, stream, cancel_token)

    # 18 个内建能力
    # llm: chat, chat_raw, stream_chat
    # memory: search, save, get, delete
    # db: get, set, delete, list, get_many, set_many, watch
    # platform: send, send_image, send_chain, get_members
```

#### HandlerDispatcher

处理器分发与参数注入：

```python
class HandlerDispatcher:
    async def invoke(self, message, cancel_token):
        # 1. 检查 session_waiter
        # 2. 准备 legacy 运行时（过滤器）
        # 3. 构建参数（类型注入）
        # 4. 执行 handler
        # 5. 处理结果（legacy 结果兼容）
        # 6. 错误处理
```

#### Loader

插件发现与加载：

```python
def discover_plugins(plugins_dir) -> list[PluginSpec]

def load_plugin(spec) -> LoadedPlugin

# PluginSpec
@dataclass
class PluginSpec:
    name: str
    plugin_dir: Path
    manifest_path: Path
    requirements_path: Path
    python_version: str
    manifest_data: dict

# LoadedPlugin
@dataclass
class LoadedPlugin:
    plugin: PluginSpec
    instances: list[Any]
    handlers: list[HandlerWrapper]
```

### 5.3 客户端层（Clients）

```python
class Context:
    llm: LLMClient
    memory: MemoryClient
    db: DBClient
    platform: PlatformClient
    http: HTTPClient
    metadata: MetadataClient
    logger: Logger
    cancel_token: CancelToken
```

每个客户端通过 `CapabilityProxy` 调用对应能力：

```python
class LLMClient:
    async def chat(self, prompt) -> str:
        return await self._proxy.call("llm.chat", {"prompt": prompt})

    async def chat_raw(self, prompt) -> LLMResponse:
        return await self._proxy.call("llm.chat_raw", {"prompt": prompt})

    async def stream_chat(self, prompt) -> AsyncIterator[str]:
        async for event in self._proxy.stream("llm.stream_chat", {"prompt": prompt}):
            yield event["data"]["text"]
```

### 5.4 兼容层（Compat）

#### LegacyContext

旧版上下文适配：

```python
class LegacyContext:
    def __init__(self, new_context: Context):
        self._new_context = new_context
        self.conversation_manager = LegacyConversationManager(self)
        self.llm = ...

    def llm_generate(self, prompt) -> str:
        return self._new_context.llm.chat(prompt)

    def put_kv_data(self, key, value):
        asyncio.create_task(self._new_context.db.set(key, value))

    def get_kv_data(self, key) -> Any:
        return await self._new_context.db.get(key)
```

#### LegacyStar

旧版 Star 基类：

```python
class LegacyStar:
    def __init__(self, context: LegacyContext):
        self.context = context

    # 旧版方法
    async def initialize(self):
        pass

    def register_component(self, component):
        # 通过 _legacy_runtime 注册
        pass
```

#### LegacyRuntimeAdapter

运行时执行适配：

```python
class LegacyWorkerRuntimeBridge:
    async def execute_legacy_handler(self, handler, event):
        # 1. 应用自定义过滤器
        # 2. 执行 handler
        # 3. 结果装饰（on_decorating_result）
        # 4. 发送后 hook（after_message_sent）
        # 5. 错误处理（on_plugin_error）
```

---

## 6. 实现思路

### 6.1 插件发现与加载

#### v4 插件（`plugin.yaml`）

```yaml
name: my_plugin
version: "0.1.0"
description: My awesome plugin
runtime:
  python: "3.12"
components:
  - path: my_plugin/main.py
    entry: MyComponent
permissions:
  - type: admin
    commands: [secure]
```

```python
# my_plugin/main.py
from astrbot_sdk import Star, Context, MessageEvent
from astrbot_sdk.decorators import on_command

class MyComponent(Star):
    @on_command("hello")
    async def hello_cmd(self, event: MessageEvent):
        await event.reply("Hello, world!")
```

#### Legacy 插件（`main.py`）

```python
# main.py
from astrbot_sdk.api.star import Star
from astrbot_sdk.api.event import AstrMessageEvent

class MyOldStar(Star):
    async def initialize(self):
        pass

    @filter.command("old_hello")
    async def old_hello(self, event: AstrMessageEvent):
        await event.reply("Old hello!")
```

发现流程：

```python
def discover_plugins(plugins_dir):
    for subdir in plugins_dir.iterdir():
        # 检查 plugin.yaml
        yaml_path = subdir / "plugin.yaml"
        if yaml_path.exists():
            return load_plugin_spec(subdir)

        # 检查 legacy main.py
        main_path = subdir / "main.py"
        if main_path.exists():
            return synthesize_legacy_spec(subdir)
```

### 6.2 环境管理与分组

```python
class PluginEnvironmentManager:
    def plan(self, plugins: list[PluginSpec]) -> list[EnvironmentGroup]:
        # 基于 runtime.python 和 requirements.txt 分组
        # 依赖兼容性分析
        # 返回共享环境规划

    def prepare_environment(self, spec: PluginSpec):
        # 创建虚拟环境
        # 安装依赖
        # 返回环境路径

class EnvironmentGroup:
    def __init__(self, plugins: list[PluginSpec]):
        self.plugins = plugins
        self.env_path = self._create_shared_env()
        self.lock_path = self._create_lock()

    def lock(self):
        # 获取环境锁

    def unlock(self):
        # 释放环境锁
```

### 6.3 消息处理流程

#### Handler 调用链

```
Core 消息
    ↓
Supervisor.handler_to_worker[handler_id]
    ↓
WorkerSession.invoke_handler(handler_id, event)
    ↓
Peer.invoke("handler.invoke", {handler_id, event})
    ↓
HandlerDispatcher.invoke(message, cancel_token)
    ↓
1. 检查 session_waiter
2. 准备 legacy 运行时（过滤器）
3. 构建参数（类型注入）
4. 执行 handler
5. 处理结果（legacy 结果兼容）
6. 错误处理
```

#### Capability 调用链

```
插件代码调用
    ↓
LLMClient.chat() → CapabilityProxy.call("llm.chat")
    ↓
Peer.invoke("llm.chat", payload)
    ↓
Supervisor.capability_to_worker[capability]
    ↓
WorkerSession.invoke_capability()
    ↓
CapabilityRouter.execute()
    ↓
内建或插件自定义 handler
```

### 6.4 Session Waiter 实现

```python
class SessionWaiterManager:
    def __init__(self):
        self._waiters: dict[str, deque[SessionWaiter]] = defaultdict(deque)

    def register(self, event: MessageEvent) -> SessionWaiter:
        key = self._make_waiter_key(event)
        waiter = SessionWaiter(event)
        self._waiters[key].append(waiter)
        return waiter

    async def dispatch(self, event: MessageEvent):
        key = self._make_waiter_key(event)
        queue = self._waiters.get(key)
        if not queue:
            return

        waiter = queue[0]
        if waiter.match(event):
            await waiter.resume(event)
            queue.popleft()

@dataclass
class SessionWaiter:
    event: MessageEvent
    future: asyncio.Future
    condition: Callable[[MessageEvent], bool]

    async def wait(self, timeout: float):
        return await asyncio.wait_for(self.future, timeout)
```

---

## 7. 技术亮点

### 7.1 取消机制

```python
class CancelToken:
    def __init__(self):
        self._cancelled = asyncio.Event()

    def cancel(self):
        self._cancelled.set()

    def raise_if_cancelled(self):
        if self.cancelled:
            raise asyncio.CancelledError
```

调用链：

```
用户取消
    ↓
peer.cancel(request_id)
    ↓
CancelMessage 发送
    ↓
远端收到 CancelMessage
    ↓
CancelToken.cancel()
    ↓
asyncio.create_task().cancel()
    ↓
asyncio.CancelledError
```

早到取消避免：

```python
async def _handle_invoke(self, message, token, started):
    started.set()
    token.raise_if_cancelled()  # 早到取消检查
    # 执行逻辑...
```

### 7.2 JSON Schema 验证

```python
def _validate_schema(self, schema: dict, payload: dict):
    properties = schema.get("properties", {})
    for field_name in schema.get("required", []):
        if field_name not in payload:
            raise AstrBotError.invalid_input(f"缺少必填字段：{field_name}")
```

能力注册时声明 Schema：

```python
router.register(
    CapabilityDescriptor(
        name="my_plugin.calculate",
        input_schema={
            "type": "object",
            "properties": {
                "x": {"type": "number"},
                "y": {"type": "number"},
            },
            "required": ["x", "y"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "result": {"type": "number"},
            },
        },
    ),
    call_handler=my_calculate,
)
```

### 7.3 流式执行

```python
@dataclass(slots=True)
class StreamExecution:
    iterator: AsyncIterator[dict[str, Any]]
    finalize: FinalizeHandler  # (chunks) -> dict
    collect_chunks: bool = True

# 注册流式能力
async def stream_numbers(request_id, payload, token):
    for i in range(10):
        token.raise_if_cancelled()
        yield {"number": i}

router.register(
    CapabilityDescriptor(
        name="my_plugin.stream",
        supports_stream=True,
        cancelable=True,
    ),
    stream_handler=stream_numbers,
    finalize=lambda chunks: {"count": len(chunks)},
)

# 调用流式能力
async for event in peer.invoke_stream("my_plugin.stream", {}):
    print(event["data"]["number"])
```

### 7.4 参数注入

```python
class HandlerDispatcher:
    async def invoke(self, message, cancel_token):
        handler = self._handlers[message["handler_id"]]
        ctx = Context(peer=..., plugin_id=...)
        event = MessageEvent.from_dict(message["event"])

        # 参数注入
        kwargs = {}
        sig = inspect.signature(handler.method)
        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue
            if param.annotation == Context:
                kwargs[param_name] = ctx
            elif param.annotation == MessageEvent:
                kwargs[param_name] = event
            elif param_name == "cancel_token":
                kwargs[param_name] = cancel_token
            else:
                # 从 event 中获取
                kwargs[param_name] = getattr(event, param_name)

        return await handler.method(**kwargs)
```

### 7.5 传输抽象

```python
class StdioTransport:
    def __init__(self, stdin, stdout):
        self.stdin = stdin
        self.stdout = stdout

    async def start(self):
        self._read_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self):
        while True:
            line = await self.stdin.readline()
            if not line:
                break
            self._message_handler(line.rstrip("\n"))

    async def send(self, message: str):
        self.stdout.write(message + "\n")
        await self.stdout.drain()
```

支持三种模式：

1. **子进程模式**：`PluginWorkerRuntime` 通过子进程的 stdin/stdout 通信
2. **文件模式**：通过临时文件交换消息（测试用）
3. **WebSocket 模式**：网络远程调用

---

## 8. 演进规划

### 8.1 当前规划（来自 ARCHITECTURE.md）

1. **继续收口 runtime 对 compat 的认知**
   - 统一通过 `_legacy_runtime.py` 与 `_legacy_loader.py`
   - 避免直接展开更多 legacy 细节

2. **拆薄 `_legacy_api.py`**
   - 让 `LegacyContext` 更偏向 facade 和 orchestration
   - 减少直接适配逻辑

3. **保持 `src-new/astrbot` 为受控 facade**
   - 不把旧应用整棵树重新复制进来
   - 只覆盖真实插件命中的路径

4. **契约测试保护**
   - capability 注册表契约测试
   - compat hook 执行契约测试
   - facade 导入矩阵契约测试

### 8.2 建议的长期方向

#### 8.2.1 兼容层逐步淘汰

阶段 1（当前）：兼容层完整功能

- 所有旧插件可运行
- 文档明确兼容级别

阶段 2（中期）：兼容层标记 deprecated

- 新项目不再使用旧 API
- 迁移工具完善
- 旧 API 发出警告

阶段 3（长期）：兼容层移除

- 移除 `_legacy_*.py`
- 移除 `src-new/astrbot` facade
- 清理 `astrbot_sdk.api`

#### 8.2.2 协议演进

v4.1：增强能力

- 更细粒度的权限控制
- 插件间直接通信能力
- 热更新支持

v5.0：可能的重大变更

- 二进制协议支持（性能优化）
- 更灵活的流式模型
- 插件依赖管理

#### 8.2.3 运行时优化

当前痛点：一插件一进程的开销

可能优化方向：

1. **共享 Python 进程**：多个插件在同一进程（需要更严格的隔离）
2. **轻量级进程**：使用 uvloop 或其他优化
3. **预加载机制**：常用插件预加载，减少启动延迟

#### 8.2.4 工具链完善

1. **插件脚手架**：

```bash
astrbot-sdk init my_plugin
# 生成项目结构
# 添加示例代码
# 配置 pyproject.toml
```

2. **迁移助手**：

```bash
astrbot-sdk migrate old_plugin
# 自动转换旧 API 到新 API
# 生成迁移报告
```

3. **调试工具**：

```bash
astrbot-sdk debug plugin_dir
# 本地运行插件
# 交互式测试
# 查看调用链
```

### 8.3 文档改进建议

#### 8.3.1 统一文档结构

```
docs/
├── v4/
│   ├── README.md              # v4 总览
│   ├── architecture.md        # 架构说明
│   ├── getting-started.md     # 快速开始
│   ├── api/                  # API 文档
│   │   ├── star.md
│   │   ├── context.md
│   │   ├── events.md
│   │   └── decorators.md
│   ├── runtime/              # 运行时文档
│   │   ├── peer.md
│   │   ├── transport.md
│   │   └── capabilities.md
│   └── migration.md          # 迁移指南
└── legacy/                  # 兼容文档（逐步废弃）
    ├── overview.md
    ├── compatibility.md
    └── migration-guide.md
```

#### 8.3.2 代码示例中心化

创建统一的示例仓库：

```bash
astrbot-sdk-examples/
├── 01-basic-command/         # 基础命令
├── 02-message-filter/        # 消息过滤
├── 03-llm-integration/      # LLM 集成
├── 04-database/             # 数据库使用
├── 05-stream-capability/     # 流式能力
├── 06-session-management/    # 会话管理
└── legacy-examples/          # 旧版示例
```

#### 8.3.3 自动化文档生成

使用工具从 docstring 生成 API 文档：

```bash
# 生成 API 文档
astrbot-sdk docs generate --output docs/api/

# 检查文档覆盖
astrbot-sdk docs check
```

---

## 9. 总结

### 9.1 整体评价

AstrBot SDK v4 是一个**设计良好、架构清晰、兼容性考虑周全**的插件框架。其核心优势在于：

1. **协议优先**：清晰的 v4 协议设计，为长期演进打下基础
2. **分层合理**：插件、客户端、运行时、协议四层职责明确
3. **兼容务实**：三级兼容策略在维护成本和兼容性之间取得平衡
4. **测试完善**：单元测试、集成测试、契约测试覆盖全面
5. **开发友好**：本地开发 harness、CLI 工具、完整文档

主要挑战在于：

1. **复杂度较高**：多层抽象和兼容层带来认知负担
2. **进程开销**：一插件一进程模型的启动和资源成本
3. **维护负担**：兼容层和外部插件矩阵的持续维护
4. **文档漂移**：多份文档和大量 CLAUDE.md 备注不利于学习

### 9.2 适用场景

**非常适合**：

- 需要插件化架构的机器人系统
- 需要进程隔离的高可靠性场景
- 有大量旧插件需要兼容的迁移项目
- 需要 LLM 集成的智能对话系统

**需要权衡**：

- 资源受限的嵌入式环境（进程开销）
- 单机小规模项目（复杂度收益不大）
- 需要极低延迟的场景（跨进程通信）

### 9.3 与竞品对比

| 特性 | AstrBot SDK v4 | Plugin A | Plugin B |
|------|----------------|-----------|----------|
| 协议设计 | 自研 v4 协议 | JSON-RPC 2.0 | HTTP REST |
| 进程模型 | Supervisor-Worker | 单进程 | 单进程 |
| 类型安全 | Pydantic 模型 | 动态类型 | 无验证 |
| 流式支持 | 原生支持 | 不支持 | SSE |
| 兼容性 | 三级兼容策略 | 无 | 无 |
| 测试覆盖 | 完善 | 基础 | 不足 |
| 学习曲线 | 中等 | 低 | 高 |

### 9.4 最终建议

**对于 SDK 维护者**：

1. 继续推进兼容层收口和简化
2. 完善自动化测试和 CI/CD
3. 统一文档结构，减少 CLAUDE.md 依赖
4. 评估进程模型的优化可能性

**对于插件开发者**：

1. 新项目直接使用 v4 API
2. 旧项目逐步迁移到新 API
3. 充分利用本地开发 harness
4. 参考官方示例项目

**对于 Core 开发者**：

1. 理解 v4 协议规范
2. 实现全部 18 个内建 capability
3. 提供可靠的 Supervisor 实现
4. 支持 Worker 进程管理和监控

---

**文档结束**

如有疑问或建议，请参考：
- ARCHITECTURE.md - 当前架构文档
- COMPATIBILITY_MATRIX.md - 兼容矩阵
- CLAUDE.md - 开发者注意事项
- tests_v4/README.md - 测试指南
