# AstrBot SDK 项目完整架构分析文档

> 作者：whatevertogo
> 更新时间：2026-03-14

---

## ⚠️ 兼容层弃用通知

**兼容层已标记为 deprecated，将在下个大版本移除。**

- 旧插件请使用 **AstrBot 主程序** 运行（主程序有完整的 `StarManager` 支持）
- 新插件请使用 `astrbot_sdk` 顶层入口
- 导入兼容层会触发 `DeprecationWarning`

**待移除的文件/目录**：
- `src-new/astrbot_sdk/_legacy_*.py` - 所有 legacy 私有模块
- `src-new/astrbot_sdk/api/` - 旧版 API 兼容层（已移除）
- `src-new/astrbot_sdk/compat.py` - 顶层兼容入口
- `src-new/astrbot_sdk/protocol/legacy_adapter.py` - JSON-RPC 适配器
- `src-new/astrbot/` - 旧包名别名（已移除）
- `test_plugin/old/` - 旧插件示例
- `tests_v4/test_legacy*.py` - legacy 相关测试

---

## 目录

1. [项目概述](#项目概述)
2. [目录结构](#目录结构)
3. [核心架构层次](#核心架构层次)
4. [协议层设计](#协议层设计)
5. [运行时架构](#运行时架构)
6. [客户端层设计](#客户端层设计)
7. [新旧架构对比](#新旧架构对比)
8. [插件开发指南](#插件开发指南)
9. [关键设计模式](#关键设计模式)

---

## 项目概述

AstrBot SDK 是一个基于 Python 3.12+ 的机器人插件开发框架，采用**进程隔离**和**能力路由**架构，支持插件的动态加载、独立运行和跨进程通信。

### 核心特性

| 特性 | 描述 |
|------|------|
| 进程隔离 | 每个插件运行在独立 Worker 进程，崩溃不影响其他插件 |
| 环境分组 | 多插件可共享同一 Python 虚拟环境，节省资源 |
| 能力路由 | 显式声明的 Capability 系统，支持 JSON Schema 验证 |
| 流式支持 | 原生支持流式 LLM 调用和增量结果返回 |
| 向后兼容 | 完整的旧版 API 兼容层，支持无修改迁移 |
| 协议优先 | 基于 v4 协议的统一通信模型，支持多种传输方式 |

### 技术栈

- **Python**: 3.12+
- **异步框架**: asyncio
- **Web 框架**: aiohttp
- **数据验证**: pydantic
- **日志**: loguru
- **配置**: pyyaml
- **LLM**: openai, anthropic, google-genai
- **包管理**: uv (环境分组)

---

## 目录结构

```
astrbot-sdk/
├── src/                           # 旧版实现 (已停止更新)
│   └── astrbot_sdk/               # 旧版 SDK
├── src-new/                       # 新版 v4 实现 (当前活跃)
│   └── astrbot_sdk/               # v4 SDK 主包
│       ├── __init__.py             # 顶层公共 API
│       ├── __main__.py            # CLI 入口点
│       ├── star.py                 # v4 原生插件基类
│       ├── context.py              # 运行时上下文
│       ├── decorators.py           # v4 原生装饰器
│       ├── events.py               # v4 原生事件对象
│       ├── errors.py               # 统一错误模型
│       ├── cli.py                  # 命令行工具
│       ├── testing.py              # 测试辅助模块
│       ├── _invocation_context.py  # 调用上下文管理
│       │
│       ├── clients/                # 能力客户端层
│       │   ├── __init__.py
│       │   ├── _proxy.py          # CapabilityProxy 能力代理
│       │   ├── llm.py             # LLM 客户端
│       │   ├── memory.py          # 记忆存储客户端
│       │   ├── db.py              # KV 存储客户端
│       │   ├── platform.py        # 平台消息客户端
│       │   ├── http.py            # HTTP 注册客户端
│       │   └── metadata.py        # 插件元数据客户端
│       │
│       ├── protocol/               # 协议层
│       │   ├── __init__.py
│       │   ├── messages.py        # v4 协议消息模型
│       │   └── descriptors.py     # Handler/Capability 描述符
│       │
│       └── runtime/                # 运行时层
│           ├── __init__.py
│           ├── peer.py            # 协议对等端
│           ├── transport.py       # 传输抽象与实现
│           ├── handler_dispatcher.py  # Handler 执行分发
│           ├── capability_router.py   # Capability 路由
│           ├── loader.py          # 插件加载
│           ├── bootstrap.py       # 启动引导
│           ├── worker.py          # Worker 运行时
│           ├── supervisor.py      # Supervisor 运行时
│           └── environment_groups.py  # 环境分组管理
│
├── tests_v4/                     # v4 测试套件
│   ├── unit/                    # 单元测试
│   ├── integration/             # 集成测试
│   └── external_plugin_matrix.json  # 外部插件兼容矩阵
│
├── test_plugin/                   # 测试插件样本
│   ├── new/                     # v4 原生插件示例
│   │   ├── plugin.yaml
│   │   └── commands/
│   │       └── hello.py
│   │
│   └── old/                     # 旧版兼容插件示例 (deprecated)
│       ├── plugin.yaml
│       └── main.py
│
├── examples/                      # 示例插件
│   └── hello_plugin/            # 入门示例
│       ├── plugin.yaml
│       ├── main.py
│       └── README.md
│
├── astrBot/                      # 参考 AstrBot 应用
│
├── pyproject.toml               # 项目配置
├── ARCHITECTURE.md             # 架构文档
├── refactor.md                 # 重构历史
├── PROJECT_ARCHITECTURE.md     # 本文档
└── run_tests.py               # 测试入口
```

---

## 核心架构层次

```
┌─────────────────────────────────────────────────────────────────┐
│                   用户层 (Plugin Developer)                    │
├─────────────────────────────────────────────────────────────────┤
│  v4 入口:  astrbot_sdk.{Star, Context, MessageEvent}           │
│  装饰器:   on_command, on_message, on_event, provide_capability│
└────────────────────┬────────────────────────────────────────────┘
                   │
┌──────────────────▼─────────────────────────────────────────────┐
│                 高层 API (High-Level API)                      │
├─────────────────────────────────────────────────────────────────┤
│  能力客户端:                                                   │
│    - LLMClient        (llm.chat, llm.chat_raw, llm.stream_chat)│
│    - MemoryClient     (memory.save, memory.search, ...)        │
│    - DBClient         (db.get, db.set, db.watch, ...)          │
│    - PlatformClient   (platform.send, platform.send_image, ...)│
│    - HTTPClient       (http.register_api, http.list_apis)      │
│    - MetadataClient   (metadata.get_plugin, ...)               │
└────────────────────┬────────────────────────────────────────────┘
                   │
┌──────────────────▼─────────────────────────────────────────────┐
│              执行边界 (Execution Boundary)                     │
├─────────────────────────────────────────────────────────────────┤
│  runtime 主干:                                                 │
│    - loader.py        (插件发现、加载)                         │
│    - bootstrap.py     (Supervisor/Worker 启动)                 │
│    - handler_dispatcher.py  (Handler 执行分发)                 │
│    - capability_router.py   (Capability 路由)                  │
│    - peer.py          (协议对等端)                             │
│    - transport.py     (传输抽象)                               │
│    - supervisor.py    (Supervisor 运行时)                      │
│    - worker.py        (Worker 运行时)                          │
└────────────────────┬────────────────────────────────────────────┘
                   │
┌──────────────────▼─────────────────────────────────────────────┐
│             协议与传输 (Protocol & Transport)                  │
├─────────────────────────────────────────────────────────────────┤
│  protocol/                                                     │
│    - messages.py       (协议消息模型)                          │
│    - descriptors.py    (Handler/Capability 描述符)             │
│  transport 实现:                                               │
│    - StdioTransport            (标准输入输出)                  │
│    - WebSocketServerTransport  (WebSocket 服务端)              │
│    - WebSocketClientTransport  (WebSocket 客户端)              │
└─────────────────────────────────────────────────────────────────┘
```

### 层次职责

| 层次 | 职责 | 主要模块 |
|------|------|---------|
| 用户层 | 插件开发者 API | `Star`, `Context`, `MessageEvent`, 装饰器 |
| 高层 API | 类型化的能力客户端 | `clients/{llm, memory, db, platform, http, metadata}` |
| 执行边界 | 插件加载、路由、分发 | `runtime/loader.py`, `runtime/supervisor.py` |
| 协议层 | 消息模型、描述符 | `protocol/` |
| 传输层 | 底层通信抽象 | `runtime/transport.py` |

---

## 协议层设计

### 消息模型

v4 协议定义了 5 种消息类型：

| 消息类型 | 用途 | 关键字段 |
|---------|------|---------|
| `InitializeMessage` | 握手初始化 | `protocol_version`, `peer`, `handlers`, `provided_capabilities` |
| `InvokeMessage` | 调用能力 | `capability`, `input`, `stream` |
| `ResultMessage` | 返回结果 | `success`, `output`, `error` |
| `EventMessage` | 流式事件 | `phase` (started/delta/completed/failed), `data` |
| `CancelMessage` | 取消调用 | `reason` |

### 握手流程

```
Worker (Plugin)                 Supervisor (Core)
     |                               |
     |  InitializeMessage             |
     |----------------------------->|
     |                               | 创建 CapabilityRouter
     |                               | 注册 handler.invoke
     |                               |
     |  ResultMessage(kind="init")   |
     |<-----------------------------|
     |                               | 等待 handler.invoke 调用
     |                               | 执行 CapabilityRouter.execute()
     |                               |
     |  InvokeMessage(handler.invoke)  |
     |<-----------------------------|
     |  HandlerDispatcher.invoke()    |
     |  执行用户 handler             |
     |                               |
     |  ResultMessage(output)         |
     |----------------------------->|
```

### 描述符模型

#### HandlerDescriptor

```python
{
    "id": "plugin.module:handler_name",
    "trigger": {
        "type": "command",
        "command": "hello",
        "aliases": ["hi"],
        "description": "打招呼命令"
    },
    "priority": 0,
    "permissions": {
        "require_admin": False,
        "level": 0
    }
}
```

#### CapabilityDescriptor

```python
{
    "name": "llm.chat",
    "description": "发送对话请求，返回文本",
    "input_schema": {
        "type": "object",
        "properties": {
            "prompt": {"type": "string"}
        },
        "required": ["prompt"]
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "text": {"type": "string"}
        },
        "required": ["text"]
    },
    "supports_stream": False,
    "cancelable": False
}
```

### 内置 Capabilities (28个)

| 命名空间 | 能力 | 说明 |
|----------|------|------|
| `llm` | `chat` | 同步对话，返回文本 |
| `llm` | `chat_raw` | 同步对话，返回完整响应 |
| `llm` | `stream_chat` | 流式对话 |
| `memory` | `search` | 搜索记忆 |
| `memory` | `save` | 保存记忆 |
| `memory` | `save_with_ttl` | 保存带过期时间的记忆 |
| `memory` | `get` | 读取单条记忆 |
| `memory` | `get_many` | 批量获取记忆 |
| `memory` | `delete` | 删除记忆 |
| `memory` | `delete_many` | 批量删除记忆 |
| `memory` | `stats` | 获取记忆统计信息 |
| `db` | `get` | 读取 KV |
| `db` | `set` | 写入 KV |
| `db` | `delete` | 删除 KV |
| `db` | `list` | 列出 KV 键 |
| `db` | `get_many` | 批量读取 KV |
| `db` | `set_many` | 批量写入 KV |
| `db` | `watch` | 订阅 KV 变更 |
| `platform` | `send` | 发送消息 |
| `platform` | `send_image` | 发送图片 |
| `platform` | `send_chain` | 发送消息链 |
| `platform` | `get_members` | 获取群成员 |
| `http` | `register_api` | 注册 HTTP API 端点 |
| `http` | `unregister_api` | 注销 HTTP API 端点 |
| `http` | `list_apis` | 列出已注册的 API |
| `metadata` | `get_plugin` | 获取单个插件元数据 |
| `metadata` | `list_plugins` | 列出所有插件元数据 |
| `metadata` | `get_plugin_config` | 获取当前插件配置 |

---

## 运行时架构

### 组件关系图

```
                    ┌──────────────┐
                    │  AstrBot   │
                    │    Core    │
                    └──────┬─────┘
                           │
                    ┌──────▼─────┐
                    │ Supervisor  │
                    │  Runtime   │
                    └──────┬─────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
  ┌─────▼─────┐    ┌─────▼─────┐   ┌─────▼─────┐
  │   Peer     │    │   Peer     │   │   Peer     │
  │  (stdio)   │    │  (stdio)   │   │  (stdio)   │
  └─────┬─────┘    └─────┬─────┘   └─────┬─────┘
        │                  │                  │
  ┌─────▼─────┐    ┌─────▼─────┐   ┌─────▼─────┐
  │  Worker    │    │  Worker    │   │  Worker    │
  │  Runtime   │    │  Runtime   │   │  Runtime   │
  └─────┬─────┘    └─────┬─────┘   └─────┬─────┘
        │                  │                  │
  ┌─────▼─────┐    ┌─────▼─────┐   ┌─────▼─────┐
  │  Plugin A  │    │  Plugin B  │   │  Plugin C  │
  │  (v4/old) │    │  (v4/old) │   │  (v4/old) │
  └───────────┘    └───────────┘   └───────────┘
```

### SupervisorRuntime

职责：管理多个 Worker 进程，聚合所有 handler

```python
class SupervisorRuntime:
    def __init__(self, *, transport, plugins_dir, env_manager):
        self.transport = transport              # 与 Core 的传输层
        self.plugins_dir = plugins_dir          # 插件目录
        self.capability_router = CapabilityRouter()  # 能力路由器
        self.peer = Peer(...)                 # 与 Core 的对等端
        self.worker_sessions = {}             # Worker 会话映射
        self.handler_to_worker = {}           # Handler → Worker 映射

    async def start(self):
        # 1. 发现所有插件
        discovery = discover_plugins(self.plugins_dir)

        # 2. 规划环境分组
        plan_result = self.env_manager.plan(discovery.plugins)

        # 3. 为每个分组启动 Worker
        for group in plan_result.groups:
            session = WorkerSession(group=group, ...)
            await session.start()
            self.worker_sessions[group.id] = session

        # 4. 聚合所有 handler 和 capability
        await self.peer.initialize(
            handlers=[...],
            provided_capabilities=self.capability_router.descriptors()
        )
```

### WorkerSession

职责：管理单个 Worker 进程的生命周期

```python
class WorkerSession:
    def __init__(self, *, group, env_manager, capability_router):
        self.group = group                   # 环境分组
        self.peer = Peer(...)                # 与 Worker 的对等端
        self.capability_router = capability_router
        self.handlers = []                   # Worker 注册的 handlers
        self.provided_capabilities = []       # Worker 提供的 capabilities

    async def start(self):
        # 启动 Worker 子进程
        python_path = self.env_manager.prepare_group_environment(self.group)
        transport = StdioTransport(
            command=[python_path, "-m", "astrbot_sdk", "worker", "--group-metadata", ...]
        )
        self.peer = Peer(transport=transport, ...)

        # 等待 Worker 初始化完成
        await self.peer.start()
        await self.peer.wait_until_remote_initialized()

        # 获取 Worker 的注册信息
        self.handlers = list(self.peer.remote_handlers)
        self.provided_capabilities = list(self.peer.remote_provided_capabilities)

    async def invoke_capability(self, capability_name, payload, *, request_id):
        # 转发能力调用到 Worker
        return await self.peer.invoke(capability_name, payload, request_id=request_id)
```

### PluginWorkerRuntime

职责：Worker 进程内的插件加载与执行

```python
class PluginWorkerRuntime:
    def __init__(self, *, plugin_dir, transport):
        self.plugin = load_plugin_spec(plugin_dir)
        self.loaded_plugin = load_plugin(self.plugin)
        self.peer = Peer(transport=transport, ...)
        self.dispatcher = HandlerDispatcher(...)
        self.capability_dispatcher = CapabilityDispatcher(...)

    async def start(self):
        # 1. 向 Supervisor 注册 handlers 和 capabilities
        await self.peer.initialize(
            handlers=[h.descriptor for h in self.loaded_plugin.handlers],
            provided_capabilities=[c.descriptor for c in self.loaded_plugin.capabilities]
        )

        # 2. 执行 on_start 生命周期
        await self._run_lifecycle("on_start")

        # 3. 设置消息处理器
        self.peer.set_invoke_handler(self._handle_invoke)
        self.peer.set_cancel_handler(self._handle_cancel)

    async def _handle_invoke(self, message, cancel_token):
        if message.capability == "handler.invoke":
            return await self.dispatcher.invoke(message, cancel_token)
        return await self.capability_dispatcher.invoke(message, cancel_token)
```

### HandlerDispatcher

职责：将 handler.invoke 请求转成真实 Python 调用

```python
class HandlerDispatcher:
    def __init__(self, *, plugin_id, peer, handlers):
        self._handlers = {item.descriptor.id: item for item in handlers}
        self._peer = peer
        self._active = {}  # request_id → (task, cancel_token)

    async def invoke(self, message, cancel_token):
        # 1. 查找 handler
        loaded = self._handlers[message.input["handler_id"]]

        # 2. 创建上下文
        ctx = Context(peer=self._peer, plugin_id=plugin_id, cancel_token=cancel_token)
        event = MessageEvent.from_payload(message.input["event"], context=ctx)

        # 3. 构建参数 (支持类型注解注入)
        args = self._build_args(loaded.callable, event, ctx)

        # 4. 执行 handler
        result = loaded.callable(*args)

        # 5. 处理返回值
        await self._consume_result(result, event, ctx)
```

**参数注入优先级**:
1. 按类型注解注入（`MessageEvent`, `Context`）
2. 按参数名注入（`event`, `ctx`, `context`）
3. 从 legacy_args 注入（命令参数等）

### CapabilityRouter

职责：能力注册、发现和执行路由

```python
class CapabilityRouter:
    def __init__(self):
        self._registrations = {}  # capability_name → registration
        self.db_store = {}        # 内置 KV 存储
        self.memory_store = {}    # 内置记忆存储
        self._register_builtin_capabilities()

    def register(self, descriptor, *, call_handler, stream_handler, finalize):
        """注册能力"""
        self._registrations[descriptor.name] = _CapabilityRegistration(
            descriptor=descriptor,
            call_handler=call_handler,
            stream_handler=stream_handler,
            finalize=finalize
        )

    async def execute(self, capability, payload, *, stream, cancel_token, request_id):
        """执行能力调用"""
        registration = self._registrations[capability]

        if stream:
            # 流式调用
            raw_execution = registration.stream_handler(request_id, payload, cancel_token)
            return StreamExecution(iterator=raw_execution, finalize=finalize)
        else:
            # 同步调用
            output = await registration.call_handler(request_id, payload, cancel_token)
            return output
```

### 环境分组管理

```python
class EnvironmentPlanner:
    def plan(self, plugins):
        """根据 Python 版本和依赖兼容性分组"""
        # 1. 按版本分组
        # 2. 按依赖兼容性合并
        # 3. 生成分组元数据
        return EnvironmentPlanResult(groups=[...])

class GroupEnvironmentManager:
    def prepare(self, group):
        """准备分组虚拟环境"""
        # 1. 生成 lock/source/metadata 工件
        # 2. 必要时重建虚拟环境
        # 3. 返回 Python 解释器路径
        return venv_python_path
```

---

## 客户端层设计

### 客户端架构

```
┌─────────────────────────────────────────────────────────────┐
│                    User Plugin                            │
├─────────────────────────────────────────────────────────────┤
│  ctx.llm.chat()                                         │
│  ctx.memory.save()                                      │
│  ctx.db.set()                                           │
│  ctx.platform.send()                                     │
└────────────┬──────────────────────────────────────────────┘
             │
┌────────────▼──────────────────────────────────────────────┐
│               CapabilityProxy                              │
│  - call(name, payload)                                   │
│  - stream(name, payload)                                 │
└────────────┬──────────────────────────────────────────────┘
             │
┌────────────▼──────────────────────────────────────────────┐
│                    Peer                                 │
│  - invoke(capability, payload, stream=False)              │
│  - invoke_stream(capability, payload)                      │
└────────────┬──────────────────────────────────────────────┘
             │
┌────────────▼──────────────────────────────────────────────┐
│                 Transport                                │
│  - send(json_string)                                     │
└─────────────────────────────────────────────────────────────┘
```

### CapabilityProxy

职责：封装 Peer 的能力调用接口

```python
class CapabilityProxy:
    def __init__(self, peer):
        self._peer = peer

    async def call(self, name, payload):
        """普通能力调用"""
        # 1. 检查能力是否可用
        descriptor = self._peer.remote_capability_map.get(name)
        if descriptor is None:
            raise AstrBotError.capability_not_found(name)

        # 2. 调用 Peer.invoke
        return await self._peer.invoke(name, payload, stream=False)

    async def stream(self, name, payload):
        """流式能力调用"""
        # 1. 检查流式支持
        descriptor = self._peer.remote_capability_map.get(name)
        if not descriptor.supports_stream:
            raise AstrBotError.invalid_input(f"{name} 不支持 stream")

        # 2. 调用 Peer.invoke_stream
        event_stream = await self._peer.invoke_stream(name, payload)
        async for event in event_stream:
            if event.phase == "delta":
                yield event.data
```

### LLMClient

```python
class LLMClient:
    def __init__(self, proxy: CapabilityProxy):
        self._proxy = proxy

    async def chat(self, prompt, *, system=None, history=None, **kwargs) -> str:
        """发送聊天请求，返回文本"""
        output = await self._proxy.call("llm.chat", {
            "prompt": prompt,
            "system": system,
            "history": self._serialize_history(history),
            **kwargs
        })
        return output["text"]

    async def chat_raw(self, prompt, **kwargs) -> LLMResponse:
        """发送聊天请求，返回完整响应"""
        output = await self._proxy.call("llm.chat_raw", {"prompt": prompt, **kwargs})
        return LLMResponse.model_validate(output)

    async def stream_chat(self, prompt, **kwargs) -> AsyncGenerator[str]:
        """流式聊天"""
        async for delta in self._proxy.stream("llm.stream_chat", {"prompt": prompt, **kwargs}):
            yield delta["text"]
```

### 其他客户端

| 客户端 | 主要方法 | 对应 Capability |
|--------|---------|-----------------|
| `MemoryClient` | `search()`, `save()`, `save_with_ttl()`, `get()`, `get_many()`, `delete()`, `delete_many()`, `stats()` | `memory.*` |
| `DBClient` | `get()`, `set()`, `delete()`, `list()`, `get_many()`, `set_many()`, `watch()` | `db.*` |
| `PlatformClient` | `send()`, `send_image()`, `send_chain()`, `get_members()` | `platform.*` |
| `HTTPClient` | `register_api()`, `unregister_api()`, `list_apis()` | `http.*` |
| `MetadataClient` | `get_plugin()`, `list_plugins()`, `get_current_plugin()`, `get_plugin_config()` | `metadata.*` |

---

## 新旧架构对比

### 协议对比

| 特性 | 旧版 JSON-RPC | 新版 v4 协议 |
|------|---------------|--------------|
| 消息格式 | `{"jsonrpc": "2.0", ...}` | `{"type": "invoke", ...}` |
| 方法区分 | `method` 字段 | `type` 字段 |
| 错误码 | 整数 (`-32000`) | 字符串 (`"internal_error"`) |
| 流式支持 | 独立 notification 方法 | 统一 `EventMessage` phase |
| 握手 | `handshake` method | `InitializeMessage` type |
| 能力声明 | 隐式（method 名称） | 显式 `CapabilityDescriptor` |

### 运行时对比

| 特性 | 旧版 | 新版 |
|------|------|------|
| Peer 抽象 | 分离 `JSONRPCClient/Server` | 统一 `Peer` |
| Handler 分发 | 直接调用 `handler(event)` | `HandlerDispatcher` 参数注入 |
| 能力路由 | 无显式路由 | `CapabilityRouter` |
| 环境管理 | 无 | `PluginEnvironmentManager` 分组 |
| 传输层 | 每个实现处理 JSON-RPC | 传输层只处理字符串 |

### 代码对比

#### 旧版 Handler

```python
from astrbot.api.star import Star
from astrbot.api.event import AstrMessageEvent

class MyPlugin(Star):
    @command_handler("hello", aliases=["hi"])
    def hello_handler(self, event: AstrMessageEvent):
        reply = self.call_context_function("llm_generate", prompt=event.message_plain)
        event.reply(reply)
```

#### 新版 Handler

```python
from astrbot_sdk import Star, Context, MessageEvent
from astrbot_sdk.decorators import on_command

class MyPlugin(Star):
    @on_command("hello", aliases=["hi"])
    async def hello(self, event: MessageEvent, ctx: Context) -> None:
        reply = await ctx.llm.chat(event.text)
        await event.reply(reply)
```

---

## 新旧架构对比

---

## 插件开发指南

### v4 原生插件

#### plugin.yaml

```yaml
_schema_version: 2
name: my_plugin
author: your_name
version: 1.0.0
runtime:
  python: "3.12"
components:
  - class: main:MyPlugin
```

#### main.py

```python
from astrbot_sdk import Star, Context, MessageEvent
from astrbot_sdk.decorators import on_command, on_message, provide_capability

class MyPlugin(Star):
    # 命令处理器
    @on_command("hello", aliases=["hi"])
    async def hello(self, event: MessageEvent, ctx: Context) -> None:
        await event.reply(f"你好，{event.user_id}！")

    # 消息处理器
    @on_message(keywords=["帮助"])
    async def help(self, event: MessageEvent, ctx: Context) -> None:
        await event.reply("可用命令：hello, help")

    # 提供能力
    @provide_capability(
        "my_plugin.calculate",
        description="执行计算",
        input_schema={
            "type": "object",
            "properties": {"x": {"type": "number"}},
            "required": ["x"]
        },
        output_schema={
            "type": "object",
            "properties": {"result": {"type": "number"}},
            "required": ["result"]
        }
    )
    async def calculate_capability(
        self,
        payload: dict,
        ctx: Context
    ) -> dict:
        x = payload.get("x", 0)
        return {"result": x * 2}
```

### 旧版兼容插件

#### plugin.yaml

```yaml
name: my_old_plugin
version: 1.0.0
components:
  - class: main:MyOldPlugin
```

#### main.py

```python
from astrbot.api.star import Star
from astrbot.api.event import AstrMessageEvent

class MyOldPlugin(Star):
    # 旧版装饰器仍然支持
    @command_handler("old_hello")
    def old_hello_handler(self, event: AstrMessageEvent):
        # 旧版 API 调用
        reply = self.call_context_function("llm_generate", prompt="你好")
        event.reply(reply)

    # 生命周期钩子
    async def on_start(self):
        self.put_kv_data("started", True)

    async def on_stop(self):
        self.put_kv_data("started", False)
```

### 生命周期钩子

| 钩子 | 说明 |
|------|------|
| `on_start()` | 插件启动时调用 |
| `on_stop()` | 插件停止时调用 |
| `on_error(exc, event, ctx)` | Handler 执行出错时调用 |

---

## 关键设计模式

### 1. 协议优先模式

- 所有跨进程通信都通过 v4 协议
- 传输层只处理字符串，协议由 Peer 层处理
- 支持多种传输方式（Stdio, WebSocket）

### 2. 能力路由模式

- 显式声明 Capability 和输入/输出 Schema
- 通过 CapabilityRouter 统一路由
- 支持同步和流式两种调用模式
- 冲突处理：保留命名空间冲突直接跳过，非保留命名空间冲突自动添加插件名前缀

### 3. 环境分组模式

- 多插件可共享同一 Python 虚拟环境
- 按版本和依赖兼容性自动分组
- 节省资源，加快启动速度

### 4. 参数注入模式

- HandlerDispatcher 支持类型注解注入
- 优先级：类型注解 > 参数名 > legacy_args
- 支持可选类型 `Optional[Type]`

### 5. 取消传播模式

- CancelToken 统一取消机制
- 跨进程取消通过 CancelMessage
- 早到取消避免竞态条件

### 6. 插件隔离模式

- 每个插件运行在独立 Worker 进程
- 崩溃不影响其他插件
- 支持 GroupWorkerRuntime 共享环境

### 7. 热重载模式

- `dev --watch` 支持文件变更检测
- 按插件目录清理 `sys.modules` 缓存
- 确保代码变更后正确重载

---

## 附录：关键文件速查

| 文件 | 核心类/函数 | 说明 |
|------|------------|------|
| `src-new/astrbot_sdk/__init__.py` | `Star`, `Context`, `MessageEvent` | 顶层入口 |
| `src-new/astrbot_sdk/star.py` | `Star` | v4 原生插件基类 |
| `src-new/astrbot_sdk/context.py` | `Context` | 运行时上下文 |
| `src-new/astrbot_sdk/decorators.py` | `on_command`, `on_message`, `provide_capability` | v4 装饰器 |
| `src-new/astrbot_sdk/errors.py` | `AstrBotError` | 统一错误模型 |
| `src-new/astrbot_sdk/cli.py` | CLI 命令 | 命令行工具 |
| `src-new/astrbot_sdk/testing.py` | `PluginHarness`, `MockContext` | 测试辅助 |
| `src-new/astrbot_sdk/runtime/peer.py` | `Peer` | 协议对等端 |
| `src-new/astrbot_sdk/runtime/supervisor.py` | `SupervisorRuntime` | Supervisor 运行时 |
| `src-new/astrbot_sdk/runtime/worker.py` | `PluginWorkerRuntime` | Worker 运行时 |
| `src-new/astrbot_sdk/runtime/loader.py` | `load_plugin()`, `_ResolvedComponent` | 插件加载 |
| `src-new/astrbot_sdk/runtime/handler_dispatcher.py` | `HandlerDispatcher` | Handler 执行分发 |
| `src-new/astrbot_sdk/runtime/capability_router.py` | `CapabilityRouter` | Capability 路由 |
| `src-new/astrbot_sdk/runtime/environment_groups.py` | `EnvironmentGroup` | 环境分组 |
| `src-new/astrbot_sdk/protocol/messages.py` | `InitializeMessage`, `InvokeMessage` | 协议消息 |
| `src-new/astrbot_sdk/protocol/descriptors.py` | `HandlerDescriptor`, `CapabilityDescriptor` | 描述符 |
| `src-new/astrbot_sdk/clients/_proxy.py` | `CapabilityProxy` | 能力代理 |
| `src-new/astrbot_sdk/clients/llm.py` | `LLMClient` | LLM 客户端 |
| `src-new/astrbot_sdk/clients/memory.py` | `MemoryClient` | 记忆客户端 |
| `src-new/astrbot_sdk/clients/db.py` | `DBClient` | 数据库客户端 |
| `src-new/astrbot_sdk/clients/platform.py` | `PlatformClient` | 平台客户端 |
| `src-new/astrbot_sdk/clients/http.py` | `HTTPClient` | HTTP 客户端 |
| `src-new/astrbot_sdk/clients/metadata.py` | `MetadataClient`, `PluginMetadata` | 元数据客户端 |
| `examples/hello_plugin/` | - | 入门示例插件 |

---

## 更新日志

### 2026-03-14 (v2)
- 添加兼容层弃用通知
- 更新目录结构，移除已删除的 `api/` 和 `astrbot/` 目录
- 更新内置 Capabilities 列表至 28 个（新增 memory 扩展方法、http、metadata）
- 更新客户端方法表，补充完整方法列表
- 移除兼容层设计章节（已弃用）
- 更新关键文件速查表
- 添加热重载模式说明

### 2026-03-14
- 添加环境分组详细说明
- 完善 CapabilityRouter 内置能力列表
- 添加客户端层架构图
- 补充新旧代码对比示例

### 2026-03-13
- 初始版本
- 完成整体架构分析
- 新旧对比整理

---

> 本文档基于 AstrBot SDK 当前版本 (`refact1/refactsome`) 整理
> 如有疑问请查阅源代码或提交 Issue
