# 插件注册与能力注册数据流

> 作者：whatevertogo
> 生成日期：2026-03-24

---

## 目录

1. [概述](#概述)
2. [核心架构](#核心架构)
3. [插件注册流程](#插件注册流程)
4. [能力注册流程](#能力注册流程)
5. [能力调用流程](#能力调用流程)
6. [CapabilityRouter 机制](#capabilityrouter-机制)
7. [关键数据结构](#关键数据结构)
8. [时序图](#时序图)

---

## 概述

AstrBot SDK v4 采用**进程隔离**和**能力路由**架构：

- **进程隔离**: 每个插件运行在独立 Worker 进程，崩溃不影响其他插件
- **能力路由**: Supervisor 统一管理所有能力的注册、发现和调用
- **协议通信**: 通过 v4 协议进行跨进程通信（支持 Stdio/WebSocket）

### 核心组件

| 组件 | 位置 | 职责 |
|------|------|------|
| `SupervisorRuntime` | 主进程 | 管理多个 Worker 进程，聚合所有 handler 和 capability |
| `WorkerSession` | 主进程 | 封装单个 Worker 进程的生命周期和通信 |
| `PluginWorkerRuntime` | Worker 进程 | 插件加载与执行 |
| `HandlerDispatcher` | Worker 进程 | Handler 请求转成真实 Python 调用 |
| `CapabilityDispatcher` | Worker 进程 | Capability 调用分发 |
| `CapabilityRouter` | 主进程 | 能力注册、发现和执行路由 |

---

## 核心架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         AstrBot Core                            │
│                     (调用能力/发送消息)                          │
└────────────────────────────┬────────────────────────────────────┘
                             │ invoke/call
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    SupervisorRuntime (主进程)                    │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              CapabilityRouter                              │  │
│  │  _registrations: {capability_name: registration}         │  │
│  │  handler_to_worker: {handler_id: WorkerSession}          │  │
│  │  capability_to_worker: {capability_name: WorkerSession}  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                     │
│  WorkerSession A ◄────────────► WorkerSession B ◄───────────► ...  │
└──────────────┬──────────────────────────────┬───────────────────┘
               │ stdio/ws                      │ stdio/ws
               ▼                              ▼
┌──────────────────────────┐      ┌──────────────────────────┐
│   Worker 进程 A          │      │   Worker 进程 B          │
│  ┌────────────────────┐  │      │  ┌────────────────────┐  │
│  │ PluginWorkerRuntime│  │      │  │ PluginWorkerRuntime│  │
│  │                    │  │      │  │                    │  │
│  │  HandlerDispatcher │  │      │  │  HandlerDispatcher │  │
│  │  CapabilityDispatcher│     │  │  CapabilityDispatcher│  │
│  │                    │  │      │  │                    │  │
│  │  loaded.handlers   │  │      │  │  loaded.handlers   │  │
│  │  loaded.capabilities│     │  │  loaded.capabilities│  │
│  └────────────────────┘  │      │  └────────────────────┘  │
└──────────┬─────────────────┘      └──────────┬─────────────────┘
           │                                    │
           ▼                                    ▼
┌──────────────────────────┐      ┌──────────────────────────┐
│   Plugin A (Star)        │      │   Plugin B (Star)        │
│                          │      │                          │
│  @on_command             │      │  @on_command             │
│  @on_message             │      │  @on_message             │
│  @provide_capability     │      │  @provide_capability     │
│  @llm_tool               │      │  @llm_tool               │
│  @on_schedule            │      │  @on_schedule            │
│  @http_api               │      │  @http_api               │
└──────────────────────────┘      └──────────────────────────┘
```

---

## 插件注册流程

### 阶段一：插件发现 (Supervisor 侧)

```
SupervisorRuntime.start()
  │
  ▼
discover_plugins(plugins_dir)
  │
  ├─► 遍历 plugins 目录下的子目录
  │     │
  │     ├─► 检查 plugin.yaml 是否存在
  │     │
  │     ├─► load_plugin_spec(entry)
  │     │     ├─ 读取 plugin.yaml
  │     │     ├─ 解析 manifest_data
  │     │     │   (name, author, version, components, runtime.python)
  │     │     └─ 返回 PluginSpec
  │     │
  │     ├─► validate_plugin_spec(plugin)
  │     │     └─ 验证必要字段 (name, components)
  │     │
  │     └─► 添加到 PluginDiscoveryResult.plugins
  │
  ▼
env_manager.plan(discovery.plugins)
  │
  ├─► 按依赖兼容性分组
  │
  └─► 生成 EnvironmentGroups
```

**关键数据结构**:

```python
@dataclass
class PluginSpec:
    """插件规范"""
    name: str                    # 插件名称
    plugin_dir: Path            # 插件目录
    manifest_path: Path         # plugin.yaml 路径
    requirements_path: Path     # requirements.txt 路径
    python_version: str         # Python 版本要求
    manifest_data: dict         # 原始 manifest 数据

@dataclass
class PluginDiscoveryResult:
    """发现结果"""
    plugins: list[PluginSpec]           # 成功发现的插件
    skipped_plugins: list[PluginSpec]   # 跳过的插件
    issues: list[str]                   # 问题列表
```

### 阶段二：插件加载 (Worker 侧)

```
PluginWorkerRuntime.__init__(plugin_dir)
  │
  ▼
load_plugin_spec(plugin_dir)
  │
  ▼
load_plugin(plugin)
  │
  ├─► 将插件目录添加到 sys.path
  │
  ├─► _plugin_component_classes(plugin)
  │     │
  │     ├─ 读取 components 列表 (如 ["main:MyPlugin"])
  │     │
  │     └─ import_string(class_path)
  │         └─ 动态导入组件类
  │
  ├─► 遍历每个组件类:
  │     │
  │     ├─► instance = component_cls()  # 无参实例化
  │     │
  │     ├─► _iter_discoverable_names(instance)
  │     │     └─ 扫描所有公共方法
  │     │
  │     ├─► _resolve_handler_candidate(method)
  │     │     └─ 解析 @on_command, @on_message, @on_event 等装饰器
  │     │         → 生成 LoadedHandler
  │     │
  │     ├─► _resolve_capability_candidate(method)
  │     │     └─ 解析 @provide_capability 装饰器
  │     │         → 生成 LoadedCapability
  │     │
  │     ├─► _resolve_llm_tool_candidate(method)
  │     │     └─ 解析 @llm_tool 装饰器
  │     │         → 生成 LoadedLLMTool
  │     │
  │     └─► _iter_agent_candidates(method)
  │           └─ 解析 @agent 装饰器
  │               → 生成 LoadedAgent
  │
  ▼
返回 LoadedPlugin
  │
  ▼
创建 HandlerDispatcher(handlers)
创建 CapabilityDispatcher(capabilities)
```

**关键数据结构**:

```python
@dataclass
class LoadedPlugin:
    """加载后的插件"""
    plugin: PluginSpec                      # 插件规范
    handlers: list[LoadedHandler]           # 处理器列表
    capabilities: list[LoadedCapability]    # 能力列表
    llm_tools: list[LoadedLLMTool]          # LLM 工具列表
    agents: list[LoadedAgent]               # Agent 列表
    instances: list[Any]                    # 组件实例列表

@dataclass
class LoadedHandler:
    """加载后的处理器"""
    descriptor: HandlerDescriptor           # 描述符
    callable: Callable                      # 可调用方法
    owner: Any                              # 所属实例
    plugin_id: str                          # 插件 ID
    local_filters: list                     # 过滤器
    limiter: Optional[RateLimiter]          # 限流器
    conversation: Optional[ConversationConfig]  # 会话配置

@dataclass
class LoadedCapability:
    """加载后的能力"""
    descriptor: CapabilityDescriptor        # 描述符
    callable: Callable                      # 可调用方法
    owner: Any                              # 所属实例
    plugin_id: str                          # 插件 ID
```

---

## 能力注册流程

### 插件中声明能力

```python
from astrbot_sdk import Star, Context
from astrbot_sdk.decorators import provide_capability

class MyPlugin(Star):
    @provide_capability(
        name="my_plugin.calculate",
        description="执行数学计算",
        input_schema={
            "type": "object",
            "properties": {
                "x": {"type": "number"},
                "y": {"type": "number"}
            },
            "required": ["x", "y"]
        },
        output_schema={
            "type": "object",
            "properties": {
                "result": {"type": "number"}
            },
            "required": ["result"]
        }
    )
    async def calculate(self, payload: dict, ctx: Context) -> dict:
        x = payload.get("x", 0)
        y = payload.get("y", 0)
        return {"result": x + y}
```

### 握手注册流程

```
Worker 侧                                    Supervisor 侧
    │                                             │
    │  PluginWorkerRuntime.start()                │
    │         │                                   │
    │         ▼                                   │
    │  peer.initialize(                           │
    │      handlers=[handler.descriptor...],      │
    │      provided_capabilities=[cap.desc...],   │
    │      metadata={...}                         │
    │  )                                          │
    │         │                                   │
    │         ▼                                   │
    │  构建 InitializeMessage                     │
    │         │                                   │
    │         ├─────────────────────────────────► │
    │         │  InitializeMessage                │
    │         │                                   │
    │         │                        WorkerSession._handle_initialize()
    │         │                                   │
    │         │                        ├─ 解析 remote_handlers
    │         │                        │  └─ handler_to_worker[id] = session
    │         │                        │
    │         │                        ├─ 解析 remote_provided_capabilities
    │         │                        │  └─ _register_plugin_capability()
    │         │                        │       │
    │         │                        │       ├─ 检查命名冲突
    │         │                        │       │   ├─ 保留命名空间 (handler/system/internal)
    │         │                        │       │   │   → 跳过并警告
    │         │                        │       │   └─ 普通冲突
    │         │                        │       │       → 添加插件前缀 (如 plugin.echo)
    │         │                        │       │
    │         │                        │       └─ CapabilityRouter.register()
    │         │                        │           ├─ _registrations[name] = registration
    │         │                        │           └─ capability_to_worker[name] = session
    │         │                        │
    │         │                        └─ 构建 InitializeOutput
    │         │                                   │
    │         ◄─────────────────────────────────┤
    │         │  ResultMessage(kind="init")      │
    │         │  + InitializeOutput              │
    │         │                                   │
    │         ▼                                   │
    │  握手完成，插件就绪                          │
```

### 冲突处理规则

| 场景 | 处理方式 |
|------|---------|
| 保留命名空间冲突 (`handler.*`, `system.*`, `internal.*`) | 跳过注册，输出警告日志 |
| 普通命名冲突 | 自动添加插件名前缀，如 `demo.echo` → `my_plugin.demo.echo` |
| 无冲突 | 直接注册 |

---

## 能力调用流程

### 从 Core 到 Plugin

```
AstrBot Core
    │
    │  调用能力 (如 llm.chat, platform.send, 或插件能力)
    │
    ▼
SupervisorRuntime._handle_upstream_invoke(message, cancel_token)
    │
    ▼
CapabilityRouter.execute(capability, payload, stream, cancel_token, request_id)
    │
    ├─► 查找 _registrations[capability]
    │
    ├─► 验证 input_schema (JSON Schema)
    │
    └─► 调用注册的处理器
        │
        ▼
_make_plugin_capability_caller(session, capability_name)
    │
    ▼
WorkerSession.invoke_capability(capability_name, payload, request_id)
    │
    ▼
peer.invoke(capability_name, payload, request_id)
    │
    │  构建 InvokeMessage
    │
    ▼
发送到 Worker 进程
```

### Worker 侧执行

```
Worker 进程收到 InvokeMessage
    │
    ▼
PluginWorkerRuntime._handle_invoke(message, cancel_token)
    │
    ▼
CapabilityDispatcher.invoke(message, cancel_token)
    │
    ├─► 查找 _capabilities[capability]
    │
    ├─► 构建 Context
    │     Context(
    │         peer=peer,
    │         plugin_id=plugin_id,
    │         request_id=request_id,
    │         cancel_token=cancel_token
    │     )
    │
    ├─► 绑定 logger (caller_plugin_scope)
    │
    └─► _run_capability(loaded, payload, ctx, cancel_token, stream)
        │
        ├─► _build_args()  # 参数注入
        │     │
        │     ├─ 按类型注入: Context, CancelToken, dict
        │     │
        │     └─ 按参数名注入: ctx, context, payload, ...
        │
        ├─► result = loaded.callable(*args)  # 执行用户方法
        │
        └─► _normalize_output(result)  # 标准化输出
```

### 返回结果

```
Worker 侧                                    Supervisor 侧
    │                                             │
    │  执行完成，返回结果                          │
    │         │                                   │
    │         ▼                                   │
    │  构建 ResultMessage                         │
    │         │                                   │
    │         ├─────────────────────────────────► │
    │         │  ResultMessage                    │
    │         │  {success: true, output: {...}}   │
    │         │                                   │
    │         │                        CapabilityRouter 处理结果
    │         │                                   │
    │         │                        ├─ 验证 output_schema
    │         │                        │
    │         │                        └─ 返回给调用方
    │         │                                   │
```

---

## CapabilityRouter 机制

### 核心职责

1. **能力注册表**: 维护所有可用能力的描述符和处理器
2. **Schema 验证**: 输入/输出的 JSON Schema 验证
3. **路由转发**: 将调用转发到对应的 Worker 进程
4. **冲突处理**: 能力名称冲突时的自动重命名

### 注册表结构

```python
@dataclass
class _CapabilityRegistration:
    """能力注册项"""
    descriptor: CapabilityDescriptor    # 能力描述符
    call_handler: Callable              # 同步调用处理器
    stream_handler: Optional[Callable]  # 流式调用处理器
    finalize: Optional[Callable]        # 清理函数
    exposed: bool                       # 是否对外暴露

class CapabilityRouter:
    # 能力注册表
    _registrations: dict[str, _CapabilityRegistration]

    # Handler 到 Worker 的映射
    handler_to_worker: dict[str, WorkerSession]

    # Capability 到 Worker 的映射
    capability_to_worker: dict[str, WorkerSession]
```

### 内置能力命名空间

| 命名空间 | 能力示例 | 说明 |
|---------|---------|------|
| `llm.*` | `llm.chat`, `llm.stream_chat` | LLM 对话 |
| `memory.*` | `memory.search`, `memory.save` | 记忆存储 |
| `db.*` | `db.get`, `db.set`, `db.watch` | KV 存储 |
| `platform.*` | `platform.send`, `platform.send_image` | 消息发送 |
| `provider.*` | `provider.get_using`, `provider.list_all` | Provider 管理 |
| `metadata.*` | `metadata.get_plugin`, `metadata.list_plugins` | 插件元数据 |
| `http.*` | `http.register_api`, `http.list_apis` | HTTP API |
| `system.*` | `system.get_data_dir`, `system.text_to_image` | 系统功能 |
| `message_history.*` | `message_history.list`, `message_history.append` | 消息历史 |

### Schema 验证流程

```
CapabilityRouter.execute()
    │
    ├─► 获取 _registrations[capability]
    │
    ├─► 输入验证
    │     │
    │     └─ validate(descriptor.input_schema, payload)
    │         ├─ 检查 required 字段
    │         ├─ 检查类型匹配
    │         └─ 失败返回 ErrorPayload
    │
    ├─► 执行调用
    │     │
    │     └─ call_handler(payload, cancel_token, request_id)
    │
    └─► 输出验证
          │
          └─ validate(descriptor.output_schema, result)
              ├─ 检查 required 字段
              ├─ 检查类型匹配
              └─ 失败返回 ErrorPayload
```

---

## 关键数据结构

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
    "kind": "handler",           # handler | hook | tool | session
    "contract": "message_event", # message_event | schedule
    "priority": 0,
    "permissions": {"require_admin": false, "level": 0},
    "filters": [],
    "param_specs": []
}
```

#### CapabilityDescriptor

```python
{
    "name": "my_plugin.calculate",
    "description": "执行数学计算",
    "input_schema": {
        "type": "object",
        "properties": {
            "x": {"type": "number"},
            "y": {"type": "number"}
        },
        "required": ["x", "y"]
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "result": {"type": "number"}
        },
        "required": ["result"]
    },
    "streaming": false
}
```

### 协议消息模型

| 消息类型 | 用途 | 关键字段 |
|---------|------|---------|
| `InitializeMessage` | 握手初始化 | `protocol_version`, `peer`, `handlers`, `provided_capabilities` |
| `InvokeMessage` | 调用能力 | `capability`, `input`, `stream`, `caller_plugin_id` |
| `ResultMessage` | 返回结果 | `success`, `output`, `error`, `kind` |
| `EventMessage` | 流式事件 | `phase` (started/delta/completed/failed), `data` |
| `CancelMessage` | 取消调用 | `reason` |

---

## 时序图

### 完整生命周期时序图

```
┌─────────┐     ┌────────────┐     ┌──────────────┐     ┌────────────────┐
│  Core   │     │ Supervisor │     │ WorkerSession│     │ Worker Runtime │
└────┬────┘     └─────┬──────┘     └──────┬───────┘     └───────┬────────┘
     │                │                   │                     │
     │                │  start()          │                     │
     │                ├──────────────────►│                     │
     │                │                   │  启动 Worker 进程    │
     │                │                   ├────────────────────►│
     │                │                   │                     │
     │                │                   │     load_plugin()   │
     │                │                   │                     ├──────┐
     │                │                   │                     │      │ 解析装饰器
     │                │                   │                     │      │ 加载组件
     │                │                   │                     │◄─────┘
     │                │                   │                     │
     │                │                   │  InitializeMessage  │
     │                │                   │◄────────────────────┤
     │                │                   │                     │
     │                │  _handle_initialize()                   │
     │                ├──────────────────►│                     │
     │                │                   │                     │
     │                │                   │  注册 handlers      │
     │                │                   │  注册 capabilities  │
     │                │                   │                     │
     │                │                   │  ResultMessage      │
     │                │                   ├────────────────────►│
     │                │                   │                     │
     │                │                   │     握手完成        │
     │                │                   │                     │
     │  调用能力       │                   │                     │
     ├───────────────►│                   │                     │
     │                │                   │                     │
     │                │  execute()        │                     │
     │                ├──────────────────►│                     │
     │                │                   │                     │
     │                │                   │  InvokeMessage      │
     │                │                   ├────────────────────►│
     │                │                   │                     │
     │                │                   │                     │  执行用户方法
     │                │                   │                     ├──────┐
     │                │                   │                     │      │
     │                │                   │                     │◄─────┘
     │                │                   │                     │
     │                │                   │  ResultMessage      │
     │                │                   │◄────────────────────┤
     │                │                   │                     │
     │  返回结果       │                   │                     │
     │◄───────────────┤                   │                     │
     │                │                   │                     │
```

---

## 附录

### 相关文件

| 文件 | 说明 |
|------|------|
| `astrbot-sdk/src/astrbot_sdk/runtime/loader.py` | 插件发现与加载 |
| `astrbot-sdk/src/astrbot_sdk/runtime/bootstrap.py` | Supervisor/Worker 启动 |
| `astrbot-sdk/src/astrbot_sdk/runtime/capability_router.py` | 能力路由 |
| `astrbot-sdk/src/astrbot_sdk/runtime/capability_dispatcher.py` | 能力分发 |
| `astrbot-sdk/src/astrbot_sdk/runtime/handler_dispatcher.py` | Handler 分发 |
| `astrbot-sdk/src/astrbot_sdk/runtime/peer.py` | 协议对等端 |
| `astrbot-sdk/src/astrbot_sdk/protocol/messages.py` | 协议消息模型 |
| `astrbot-sdk/src/astrbot_sdk/protocol/descriptors.py` | 描述符模型 |
| `astrbot-sdk/src/astrbot_sdk/decorators.py` | 装饰器定义 |

### 版本信息

- **SDK 版本**: v4.0
- **协议版本**: P0.6
- **Python 要求**: >=3.12
