# AstrBot SDK 架构概述文档

> 作者：whatevertogo
> 生成日期：2026-03-19

---

## 目录

1. [项目概述](#项目概述)
2. [核心架构层次](#核心架构层次)
3. [协议层设计](#协议层设计)
4. [运行时架构](#运行时架构)
5. [客户端层设计](#客户端层设计)
6. [插件开发指南](#插件开发指南)
7. [关键设计模式](#关键设计模式)
8. [文档与资源](#文档与资源)

---

## 项目概述

AstrBot SDK 是一个基于 Python 3.12+ 的机器人插件开发框架，采用**进程隔离**和**能力路由**架构，支持插件的动态加载、独立运行和跨进程通信。

### 核心特性

| 特性 | 描述 |
|------|------|
| **进程隔离** | 每个插件运行在独立 Worker 进程，崩溃不影响其他插件 |
| **环境分组** | 多插件可共享同一 Python 虚拟环境，节省资源 |
| **能力路由** | 显式声明的 Capability 系统，支持 JSON Schema 验证 |
| **流式支持** | 原生支持流式 LLM 调用和增量结果返回 |
| **向后兼容** | 完整的旧版 API 兼容层，支持无修改迁移 |
| **协议优先** | 基于 v4 协议的统一通信模型，支持多种传输方式 |

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

## 核心架构层次

```
┌─────────────────────────────────────────────────────────────────┐
│                   用户层 (Plugin Developer)                    │
├─────────────────────────────────────────────────────────────────┤
│  v4 入口:  astrbot_sdk.{Star, Context, MessageEvent}           │
│  装饰器:   on_command, on_message, on_event, on_schedule       │
│           provide_capability, require_admin                     │
│  过滤器:   PlatformFilter, MessageTypeFilter, CustomFilter      │
│  命令组:   CommandGroup, command_group                          │
│  会话:     MessageSession, session_waiter                       │
└────────────────────┬────────────────────────────────────────────┘
                   │
┌──────────────────▼─────────────────────────────────────────────┐
│                 高层 API (High-Level API)                      │
├─────────────────────────────────────────────────────────────────┤
│  能力客户端 (通过 CapabilityProxy 调用):                       │
│    - LLMClient        (llm.chat, llm.chat_raw, llm.stream_chat)│
│    - MemoryClient     (memory.search, memory.save, memory.stats)│
│    - DBClient         (db.get, db.set, db.watch, db.list)      │
│    - PlatformClient   (platform.send, platform.send_image, ...)│
│    - HTTPClient       (http.register_api, http.list_apis)      │
│    - MetadataClient   (metadata.get_plugin, metadata.list_plugins)│
└────────────────────┬────────────────────────────────────────────┘
                   │
┌──────────────────▼─────────────────────────────────────────────┐
│              执行边界 (Execution Boundary)                     │
├─────────────────────────────────────────────────────────────────┤
│  runtime 主干:                                                 │
│    - loader.py              (插件发现、加载、环境管理)         │
│    - bootstrap.py           (Supervisor/Worker 启动)           │
│    - handler_dispatcher.py  (Handler 执行分发、参数注入)       │
│    - capability_dispatcher.py (Capability 调用分发)            │
│    - capability_router.py   (Capability 路由、Schema 验证)     │
│    - peer.py                (协议对等端)                       │
│    - transport.py           (传输抽象)                         │
└────────────────────┬────────────────────────────────────────────┘
                   │
┌──────────────────▼─────────────────────────────────────────────┐
│             协议与传输 (Protocol & Transport)                  │
├─────────────────────────────────────────────────────────────────┤
│  protocol/                                                     │
│    - messages.py          (协议消息模型)                       │
│    - descriptors.py       (Handler/Capability 描述符)          │
│  transport 实现:                                               │
│    - StdioTransport            (标准输入输出)                  │
│    - WebSocketServerTransport  (WebSocket 服务端)              │
│    - WebSocketClientTransport  (WebSocket 客户端)              │
└─────────────────────────────────────────────────────────────────┘
```

### 层次职责

| 层次 | 职责 | 主要模块 |
|------|------|---------|
| **用户层** | 插件开发者 API | `Star`, `Context`, `MessageEvent`, 装饰器, 过滤器 |
| **高层 API** | 类型化的能力客户端 | `clients/{llm, memory, db, platform, http, metadata}` |
| **执行边界** | 插件加载、路由、分发 | `runtime/loader.py`, `runtime/*_dispatcher.py` |
| **协议层** | 消息模型、描述符、JSON Schema | `protocol/` |
| **传输层** | 底层通信抽象 | `runtime/transport.py` |

### 核心设计原则

1. **延迟加载**：`runtime/__init__.py` 使用 `__getattr__` 避免导入时加载重型依赖
2. **插件身份透传**：通过 `caller_plugin_scope()` 上下文管理器将 plugin_id 注入协议层
3. **声明式优先**：所有配置都是数据结构（描述符），便于序列化和跨进程传递
4. **类型安全**：使用 Pydantic 模型和类型注解提供验证和 IDE 支持

---

## 协议层设计

### 消息模型

v4 协议定义了 5 种消息类型：

| 消息类型 | 用途 | 关键字段 |
|---------|------|---------|
| `InitializeMessage` | 握手初始化 | `protocol_version`, `peer`, `handlers`, `provided_capabilities` |
| `InvokeMessage` | 调用能力 | `capability`, `input`, `stream`, `caller_plugin_id` |
| `ResultMessage` | 返回结果 | `success`, `output`, `error`, `kind` |
| `EventMessage` | 流式事件 | `phase` (started/delta/completed/failed), `data` |
| `CancelMessage` | 取消调用 | `reason` |

### 错误模型

`ErrorPayload` 使用字符串 code（而非整数），包含：
- `code`: 错误码（如 "capability_not_found"）
- `message`: 开发者信息
- `hint`: 用户友好提示
- `retryable`: 是否可重试

### 握手流程

```
Worker (Plugin)                 Supervisor (Core)
     |                               |
     |  InitializeMessage             |
     |  (handlers, capabilities)      |
     |----------------------------->|
     |                               |
     |  ResultMessage(kind="init")   |
     |<-----------------------------|
     |                               |
     |  InvokeMessage(handler.invoke)  |
     |<-----------------------------|
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
    "kind": "handler",           # handler | hook | tool | session
    "contract": "message_event", # message_event | schedule
    "priority": 0,
    "permissions": {"require_admin": False, "level": 0},
    "filters": [],
    "param_specs": []
}
```

#### Trigger 类型

| 类型 | 关键字段 | 说明 |
|------|---------|------|
| `CommandTrigger` | command, aliases, platforms | 命令触发 |
| `MessageTrigger` | regex, keywords, platforms | 消息触发（正则/关键词） |
| `EventTrigger` | event_type | 事件触发 |
| `ScheduleTrigger` | cron, interval_seconds | 定时触发 |

### 内置 Capabilities

#### LLM 命名空间

| 能力 | 说明 |
|------|------|
| `llm.chat` | 同步对话，返回文本 |
| `llm.chat_raw` | 同步对话，返回完整响应 |
| `llm.stream_chat` | 流式对话 |

#### Memory 命名空间

| 能力 | 说明 |
|------|------|
| `memory.search` | 语义搜索记忆 |
| `memory.save` | 保存记忆 |
| `memory.save_with_ttl` | 保存带过期时间的记忆 |
| `memory.get` / `get_many` | 读取记忆 |
| `memory.delete` / `delete_many` | 删除记忆 |
| `memory.stats` | 获取统计信息 |

#### DB 命名空间

| 能力 | 说明 |
|------|------|
| `db.get` / `get_many` | 读取 KV |
| `db.set` / `set_many` | 写入 KV |
| `db.delete` | 删除 KV |
| `db.list` | 列出当前插件命名空间内的键（支持前缀过滤） |
| `db.watch` | 订阅当前插件命名空间内的变更（流式） |

#### Message History 命名空间

| 能力 | 说明 |
|------|------|
| `message_history.list` | 分页读取会话消息历史 |
| `message_history.get_by_id` | 按 ID 读取单条消息历史 |
| `message_history.append` | 追加消息历史记录 |
| `message_history.delete_before` | 删除某时间点之前的记录 |
| `message_history.delete_after` | 删除某时间点之后的记录 |
| `message_history.delete_all` | 删除会话内全部消息历史 |

#### Platform 命名空间

| 能力 | 说明 |
|------|------|
| `platform.send` | 发送文本消息 |
| `platform.send_image` | 发送图片 |
| `platform.send_chain` | 发送消息链 |
| `platform.get_members` | 获取群成员 |

#### HTTP 命名空间

| 能力 | 说明 |
|------|------|
| `http.register_api` | 注册 HTTP API 端点，并拦截 `..` 等明显非法路径 |
| `http.unregister_api` | 注销 HTTP API 端点；不传 methods 时移除该 route 的全部方法 |
| `http.list_apis` | 列出已注册的 API |

#### Metadata 命名空间

| 能力 | 说明 |
|------|------|
| `metadata.get_plugin` | 获取单个插件元数据 |
| `metadata.list_plugins` | 列出所有插件元数据 |
| `metadata.get_plugin_config` | 获取当前插件配置 |

#### System 命名空间

| 能力 | 说明 |
|------|------|
| `system.get_data_dir` | 获取插件数据目录 |
| `system.text_to_image` | 文本转图片 |
| `system.html_render` | 渲染 HTML 模板 |
| `system.session_waiter.*` | 会话等待器管理 |
| `system.event.*` | 表情回应、输入状态、流式消息 |

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
  └───────────┘    └───────────┘   └───────────┘
```

### 核心运行时组件

| 组件 | 职责 |
|------|------|
| **SupervisorRuntime** | 管理多个 Worker 进程，聚合所有 handler |
| **WorkerSession** | 管理单个 Worker 进程的生命周期 |
| **PluginWorkerRuntime** | Worker 进程内的插件加载与执行 |
| **HandlerDispatcher** | 将 handler.invoke 请求转成真实 Python 调用 |
| **CapabilityRouter** | 能力注册、发现和执行路由 |

### 参数注入优先级

HandlerDispatcher 支持参数注入，优先级为：

1. **按类型注解注入**（`MessageEvent`, `Context`）
2. **按参数名注入**（`event`, `ctx`, `context`）
3. **从 legacy_args 注入**（命令参数等）

---

## 客户端层设计

### 客户端架构

```
┌─────────────────────────────────────────────────────────────┐
│                    User Plugin                            │
│  ctx.llm.chat() / ctx.memory.save() / ctx.db.set()        │
└────────────┬──────────────────────────────────────────────┘
             │
┌────────────▼──────────────────────────────────────────────┐
│               CapabilityProxy                              │
│  - call(name, payload)      普通调用                       │
│  - stream(name, payload)    流式调用                       │
└────────────┬──────────────────────────────────────────────┘
             │
┌────────────▼──────────────────────────────────────────────┐
│                    Peer                                   │
│  - invoke(capability, payload)                            │
│  - invoke_stream(capability, payload)                      │
└────────────┬──────────────────────────────────────────────┘
             │
┌────────────▼──────────────────────────────────────────────┐
│                 Transport                                 │
│  - send(json_string)                                      │
└─────────────────────────────────────────────────────────────┘
```

### 客户端一览

| 客户端 | 主要方法 | 对应 Capability |
|--------|---------|-----------------|
| `LLMClient` | `chat()`, `chat_raw()`, `stream_chat()` | `llm.*` |
| `MemoryClient` | `search()`, `save()`, `save_with_ttl()`, `get()`, `get_many()`, `delete()`, `delete_many()`, `stats()` | `memory.*` |
| `DBClient` | `get()`, `set()`, `get_many()`, `set_many()`, `delete()`, `list()`, `watch()` | `db.*` |
| `MessageHistoryManagerClient` | `list()`, `get()`, `append()`, `delete_before()`, `delete_after()`, `delete_all()` | `message_history.*` |
| `PlatformClient` | `send()`, `send_image()`, `send_chain()`, `get_members()` | `platform.*` |
| `HTTPClient` | `register_api()`, `unregister_api()`, `list_apis()` | `http.*` |
| `MetadataClient` | `get_plugin()`, `list_plugins()`, `get_current_plugin()`, `get_plugin_config()` | `metadata.*` |

---

## 插件开发指南

### v4 原生插件示例

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
    async def calculate_capability(self, payload: dict, ctx: Context) -> dict:
        x = payload.get("x", 0)
        return {"result": x * 2}
```

### 生命周期钩子

| 钩子 | 说明 |
|------|------|
| `on_start()` | 插件启动时调用 |
| `on_stop()` | 插件停止时调用 |
| `on_error(exc, event, ctx)` | Handler 执行出错时调用 |

### 常用功能速查

#### 1. LLM 对话

```python
# 简单对话
reply = await ctx.llm.chat("你好")

# 带历史对话
from astrbot_sdk.clients.llm import ChatMessage
history = [ChatMessage(role="user", content="我叫小明")]
reply = await ctx.llm.chat("你记得我吗？", history=history)

# 流式对话
async for chunk in ctx.llm.stream_chat("讲个故事"):
    print(chunk, end="")
```

#### 2. 数据持久化

```python
# DB 客户端（精确匹配）
await ctx.db.set("user:123", {"name": "Alice"})
data = await ctx.db.get("user:123")

# Memory 客户端（语义搜索）
await ctx.memory.save("user_pref", {"theme": "dark"})
results = await ctx.memory.search("用户喜欢什么颜色")
```

#### 3. 消息发送

```python
# 简单文本
await ctx.platform.send(event.session_id, "消息内容")

# 图片
await ctx.platform.send_image(event.session_id, "https://example.com/img.jpg")

# 消息链
from astrbot_sdk.message_components import Plain, Image
chain = [Plain("文字"), Image(url="https://example.com/img.jpg")]
await ctx.platform.send_chain(event.session_id, chain)
```

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

## 文档与资源

### 完整文档目录

SDK 文档按学习路径组织，位于 `src/astrbot_sdk/docs/`：

| 级别 | 文档 | 内容 |
|------|------|------|
| **初级** | README.md | 快速开始、核心概念 |
| | 01_context_api.md | Context API 完整参考 |
| | 02_event_and_components.md | MessageEvent 和消息组件 |
| | 03_decorators.md | 装饰器详细说明 |
| | 04_star_lifecycle.md | 插件基类和生命周期 |
| | 05_clients.md | 客户端 API 文档 |
| **中级** | 06_error_handling.md | 错误处理与调试 |
| | 07_advanced_topics.md | 并发、性能优化、安全 |
| | 08_testing_guide.md | 测试指南 |
| **高级** | 09_api_reference.md | 完整 API 索引 |
| | 10_migration_guide.md | 迁移指南 |
| | 11_security_checklist.md | 安全检查清单 |
| | PROJECT_ARCHITECTURE.md | 架构设计文档 |

### 关键文件速查

| 文件 | 核心类/函数 | 说明 |
|------|------------|------|
| `astrbot_sdk/__init__.py` | `Star`, `Context`, `MessageEvent` | 顶层入口 |
| `astrbot_sdk/star.py` | `Star` | v4 原生插件基类 |
| `astrbot_sdk/context.py` | `Context` | 运行时上下文 |
| `astrbot_sdk/decorators.py` | `on_command`, `on_message` | v4 装饰器 |
| `astrbot_sdk/errors.py` | `AstrBotError` | 统一错误模型 |
| `astrbot_sdk/runtime/peer.py` | `Peer` | 协议对等端 |
| `astrbot_sdk/runtime/capability_router.py` | `CapabilityRouter` | Capability 路由 |
| `astrbot_sdk/clients/llm.py` | `LLMClient` | LLM 客户端 |

### 版本信息

- **SDK 版本**: v4.0
- **协议版本**: P0.6
- **Python 要求**: >=3.12
- **推荐版本**: 3.12+

---

> 本文档基于 AstrBot SDK v4 架构文档整理
> 详细内容请查阅 `src/astrbot_sdk/docs/` 目录下的完整文档
