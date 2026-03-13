# AstrBot SDK v4 当前架构文档

本文描述仓库 **当前实现**，是 `src-new/astrbot_sdk` / `src-new/astrbot` / `tests_v4` 的唯一主文档。  
`refactor.md` 仅保留历史设计意图和演进说明，不再描述现状。

## 1. 目标与边界

AstrBot SDK v4 当前同时承担两件事：

1. 提供一套原生 v4 插件模型：`Star`、`Context`、`MessageEvent`、capability clients、v4 protocol。
2. 维持旧插件兼容：`astrbot_sdk.api.*`、`astrbot_sdk.compat`、`astrbot.api.*` 以及选定的 `astrbot.core.*` facade 继续可用。

因此，compat 现在不是可忽略的旁路，而是一个受控的长期子系统。当前架构目标是：

- v4 原生 API 仍保持清晰、窄导出、协议优先。
- legacy 兼容逻辑尽量收口到私有边界，而不是扩散到 runtime 主干。
- 兼容导入路径继续可用，但不把旧应用整棵树重新复制进来。
- 文档明确区分“等价兼容”“降级兼容”“仅导入兼容”。

## 2. 当前分层模型

```text
插件作者
  ├─ 原生 v4: astrbot_sdk.{Star, Context, MessageEvent, decorators}
  └─ legacy compat: astrbot_sdk.api.* / astrbot_sdk.compat / astrbot.api.*

高层 API
  ├─ 原生 clients: llm / memory / db / platform
  └─ legacy facade: LegacyContext / LegacyStar / message components / filter namespace

执行边界
  ├─ runtime 主干: loader / bootstrap / handler_dispatcher / capability_router / peer
  ├─ compat 执行边界: _legacy_runtime.py
  ├─ legacy 行为承接: _legacy_api.py
  └─ 会话等待器: _session_waiter.py

协议与传输
  ├─ protocol.messages / protocol.descriptors
  ├─ Peer
  └─ StdioTransport / WebSocket transports
```

### 当前最重要的架构判断

- `astrbot_sdk.__init__` 只导出推荐的 v4 入口。
- `astrbot_sdk.runtime.__init__` 只导出高级运行时原语，不把 loader/bootstrap 等编排细节提升为根级稳定 API。
- `astrbot_sdk.protocol.__init__` 只导出 v4 原生协议模型；legacy JSON-RPC 适配器留在 `protocol.legacy_adapter` 子模块。
- runtime 主干通过 `_legacy_runtime.py` 执行 compat filters / hooks / 生命周期桥接，不直接展开更多 legacy 细节。

## 3. 目录结构

```text
src-new/
├── astrbot_sdk/
│   ├── __init__.py                  # v4 推荐顶层入口
│   ├── context.py                   # Context / CancelToken
│   ├── decorators.py                # on_command / on_message / provide_capability ...
│   ├── events.py                    # MessageEvent / PlainTextResult
│   ├── errors.py                    # AstrBotError / ErrorCodes
│   ├── star.py                      # Star 基类与 handler 收集
│   ├── cli.py                       # astr / astrbot-sdk CLI 入口
│   ├── testing.py                   # 本地开发与测试 harness
│   ├── compat.py                    # 旧顶层兼容重导出
│   ├── _legacy_api.py               # LegacyContext / LegacyStar / CommandComponent
│   ├── _legacy_llm.py               # legacy LLM/tool 兼容辅助
│   ├── _legacy_runtime.py           # compat 执行边界
│   ├── _session_waiter.py           # legacy session_waiter 兼容执行
│   ├── _shared_preferences.py       # 共享偏好兼容辅助
│   │
│   ├── clients/
│   │   ├── _proxy.py                # CapabilityProxy
│   │   ├── llm.py
│   │   ├── memory.py
│   │   ├── db.py                    # 包含 get_many / set_many / watch
│   │   └── platform.py
│   │
│   ├── protocol/
│   │   ├── __init__.py              # 仅导出原生 v4 协议模型
│   │   ├── descriptors.py           # handlers / capabilities / builtin schema registry
│   │   ├── messages.py              # initialize / invoke / result / event / cancel
│   │   └── legacy_adapter.py        # v3 JSON-RPC ↔ v4 适配
│   │
│   ├── runtime/
│   │   ├── __init__.py              # Peer / Transport / CapabilityRouter / HandlerDispatcher
│   │   ├── peer.py
│   │   ├── transport.py
│   │   ├── capability_router.py
│   │   ├── handler_dispatcher.py
│   │   ├── loader.py
│   │   ├── environment_groups.py    # 共享环境规划与分组环境管理
│   │   └── bootstrap.py
│   │
│   └── api/                         # astrbot_sdk.api.* 兼容层
│       ├── basic/
│       ├── components/
│       ├── event/
│       ├── message/
│       ├── platform/
│       ├── provider/
│       └── star/
│
└── astrbot/                         # 旧包名 facade，受控兼容面
    ├── api/
    └── core/
```

## 4. 核心执行链

### 4.1 插件发现与 worker 启动

1. `runtime.loader.discover_plugins()` 扫描插件目录，兼容 `plugin.yaml` 和 legacy `main.py` 插件。
2. `PluginEnvironmentManager.plan()` 基于 `runtime.python` 和 `requirements.txt` 规划共享环境分组。
3. `GroupEnvironmentManager` 负责准备分组环境；worker 仍然保持“一插件一进程”，只是可共享同一个 Python 环境。
4. `load_plugin()` 加载组件，v4 `Star` 直接实例化，legacy 组件复用同一 `LegacyContext`。
5. legacy component 注册通过 `_legacy_runtime` 把 compat hooks / LLM tools / context functions 绑定到共享 `LegacyContext`。
6. `PluginWorkerRuntime` 创建 `Peer`、`HandlerDispatcher`、`CapabilityDispatcher`，初始化后向 supervisor 发送 `initialize`。
7. worker 启动/停止时的 compat lifecycle hooks 统一由 `_legacy_runtime` 执行。

### 4.2 handler.invoke 调用链

1. 上游通过 capability `"handler.invoke"` 调 worker。
2. `HandlerDispatcher` 构造本地 `Context` 和 `MessageEvent`，先尝试把消息路由给 `_session_waiter`。
3. 若命中 legacy compat handler，则由 `_legacy_runtime` 应用 custom filters、结果装饰、发送后 hook、错误 hook。
4. handler 返回值支持：
   - `MessageEventResult`
   - `MessageChain`
   - `PlainTextResult`
   - `str`
   - `{"text": ...}`
5. 发送链路优先使用 `ctx.platform.send_chain()` 或 `event.reply()`。

### 4.3 capability 调用链

1. 插件代码通过 `ctx.llm.*`、`ctx.db.*`、`ctx.memory.*`、`ctx.platform.*` 访问上游能力。
2. clients 通过 `CapabilityProxy` 转成 `Peer.invoke()` / `Peer.invoke_stream()`。
3. supervisor 侧 `CapabilityRouter` 处理内建能力；worker 也可以通过 `@provide_capability()` 暴露插件自定义 capability。
4. 插件自定义 capability 由 `CapabilityDispatcher` 在 worker 内分发执行。

### 4.4 session_waiter

`_session_waiter.py` 提供 legacy `@session_waiter` 的最小可运行兼容实现。  
它不是单纯导入桩，而是按 session 维度把后续消息重新路由给等待中的 compat 回调。

## 5. 协议契约

### 5.1 五条硬规则

1. 所有协议消息统一使用 `id` 关联请求与响应。
2. `EventMessage` 只用于 `stream=true` 的调用。
3. 插件 handler 回调统一走 capability `"handler.invoke"`。
4. `CancelMessage` 表示“请求停止”，调用方仍需等待终止态。
5. `initialize` 失败后连接进入不可用状态。

### 5.2 版本语义

当前实现里必须区分两个概念：

- `protocol_version`：**线协议版本**。当前 wire contract 使用 `"1.0"`。
- `PeerInfo.version`：**软件/实现版本标识**。当前 runtime 常用 `"v4"` 作为软件版本字符串。

二者不是同一个字段，也不应混写成同一含义。

### 5.3 主要消息

- `InitializeMessage`
- `InvokeMessage`
- `ResultMessage`
- `EventMessage`
- `CancelMessage`

`InitializeMessage` 由 `Peer.initialize()` 发起，成功响应是  
`ResultMessage(kind="initialize_result", success=True, output=InitializeOutput(...))`。

## 6. 当前内建 capabilities

当前协议注册表和 `CapabilityRouter` 内建 capability 一致，共 18 个：

| 命名空间 | Capability | 流式 |
|---|---|---|
| `llm` | `llm.chat` | 否 |
| `llm` | `llm.chat_raw` | 否 |
| `llm` | `llm.stream_chat` | 是 |
| `memory` | `memory.search` | 否 |
| `memory` | `memory.save` | 否 |
| `memory` | `memory.get` | 否 |
| `memory` | `memory.delete` | 否 |
| `db` | `db.get` | 否 |
| `db` | `db.set` | 否 |
| `db` | `db.delete` | 否 |
| `db` | `db.list` | 否 |
| `db` | `db.get_many` | 否 |
| `db` | `db.set_many` | 否 |
| `db` | `db.watch` | 是 |
| `platform` | `platform.send` | 否 |
| `platform` | `platform.send_image` | 否 |
| `platform` | `platform.send_chain` | 否 |
| `platform` | `platform.get_members` | 否 |

说明：

- `SessionRef` 是结构化发送目标 schema，不是 capability。
- `internal.*` 与 `handler.*` 命名空间保留给框架内部使用，不属于公开内建 capability 列表。

## 7. 兼容层现状

### 7.1 等价或接近等价的兼容面

以下兼容面当前是实际可运行的，不只是 import stub：

- `astrbot_sdk.api.*` 常用导入路径
- `astrbot_sdk.compat`
- `astrbot.api.*` 以及选定的 `astrbot.core.*` facade
- `LegacyContext` / `LegacyStar` / `CommandComponent`
- `filter.command` / `regex` / `permission`
- `event_message_type` / `platform_adapter_type`
- 常用 compat hooks：
  - `after_message_sent`
  - `on_astrbot_loaded`
  - `on_platform_loaded`
  - `on_decorating_result`
  - `on_llm_request`
  - `on_llm_response`
  - `on_waiting_llm_request`
  - `on_using_llm_tool`
  - `on_llm_tool_respond`
  - `on_plugin_error`
  - `on_plugin_loaded`
  - `on_plugin_unloaded`
- message components 兼容导出、别名构造和常用工厂
- `session_waiter`
- 旧插件共享单一 `LegacyContext`

### 7.2 降级兼容

这些能力可以运行，但不保证与历史实现完全等价：

- `command_group`：当前会展平成普通命令名，不复刻旧的树状命令帮助与多层执行链。
- legacy JSON-RPC handshake 转 v4 handler 描述时，只能近似恢复旧触发信息，原始 payload 会保留在 metadata 里。
- `astrbot.core.*` 的深层 facade 只覆盖受支持的导入路径，不等于整个旧应用树。
- `tool_loop_agent()` 当前是 compat local tool loop，并非完整复刻旧应用内部 agent 体系。

### 7.3 仅导入兼容或明确不支持

以下路径或能力要么只有导入兼容，要么明确不实现旧语义：

- `astrbot.api.agent()`：显式 `NotImplementedError`
- `astrbot.core.provider.provider` 中的 provider 基类与 embeddings/rerank 方法：导入可用，但方法是 stub
- 没有可映射执行链路的旧 `filter.*` helper：显式 `NotImplementedError`

兼容原则是“尽量保留可运行的旧插件路径”，不是“重新实现整个旧 AstrBot 应用”。

## 8. 对插件作者的导入建议

### 推荐的新代码

```python
from astrbot_sdk import Star, Context, MessageEvent
from astrbot_sdk.decorators import on_command, on_message, provide_capability
```

### 仍受支持的旧代码

```python
from astrbot_sdk.api.event import AstrMessageEvent
from astrbot_sdk.api.star.context import Context
from astrbot_sdk.api.event.filter import filter
```

### 旧包名 facade

```python
from astrbot.api.star import Star
from astrbot.core.utils.session_waiter import session_waiter
```

只有在需要兼容现有旧插件时才应继续使用这些路径；新插件应直接使用 v4 顶层入口。

## 9. 本地开发与测试

当前仓库已经提供一条受控的本地开发路径：

- CLI：`astr dev --local` 与 `astrbot-sdk dev --local`
- 稳定测试入口：`astrbot_sdk.testing`

`astrbot_sdk.testing` 当前公开的稳定面包括：

- `PluginHarness`
- `LocalRuntimeConfig`
- `MockPeer`
- `MockCapabilityRouter`
- `InMemoryDB`
- `InMemoryMemory`
- `StdoutPlatformSink`
- `RecordedSend`

设计约束：

- 本地 harness 复用真实的 `load_plugin()`、`HandlerDispatcher`、`CapabilityDispatcher`、`_legacy_runtime.py` 与 `_session_waiter.py`
- `dev --local` 使用进程内 mock core，而不是重新发明一套并行 runtime
- 同一次 `interactive` 会话会复用同一个 dispatcher / waiter manager / in-memory db / in-memory memory
- `astrbot_sdk.testing` 是插件测试依赖的公开 API，minor 版本内保持兼容稳定

## 10. 测试与维护约定

- 当前主测试目录是 `tests_v4/`，覆盖 protocol、runtime、clients、compat facade、legacy plugin integration、top-level imports 与 integration flows。
- 文档维护规则：
  - capability 集合变化时，同时更新本文档与对应测试。
  - compat 支持级别变化时，同时更新本文档、`CLAUDE.md` / `AGENTS.md` 备注以及相关契约测试。
  - `refactor.md` 不再承载现状；出现冲突时，一律以本文档和代码/测试为准。

## 11. 当前建议的后续演进方向

1. 继续把 runtime 对 compat 的认知收口到 `_legacy_runtime.py`。
2. 继续拆薄 `_legacy_api.py`，让 `LegacyContext` 更偏向 facade 和 orchestration。
3. 保持 `src-new/astrbot` 为受控 facade，不要把旧应用整棵树重新复制进来。
4. 用契约测试保护 capability 注册表、compat hook 执行和 facade 导入矩阵，避免文档再次漂移。
