"""运行时模块。

定义 AstrBot SDK 的运行时架构，包括插件加载、能力路由、处理器分发和通信抽象。

架构说明：
    旧版:
        - 目录结构复杂：api/, rpc/, stars/ 等多个子目录
        - 使用 JSON-RPC 2.0 协议进行通信
        - StarManager 负责插件发现和加载
        - StarRunner 负责处理器执行
        - Galaxy 负责虚拟星层管理
        - 传输层分离为 client/server 两套实现

    新版:
        - 目录结构精简：仅 6 个核心文件
        - 使用自描述协议进行通信
        - Peer 统一处理协议层消息收发
        - Transport 抽象传输层，支持多种实现
        - CapabilityRouter 注册和路由能力调用
        - HandlerDispatcher 分发处理器调用
        - SupervisorRuntime 管理多 Worker 会话

核心概念对比：
    旧版概念:
        - StarManager: 插件发现和加载
        - StarRunner: 处理器执行
        - Galaxy: 虚拟星层管理
        - JSONRPCServer/Client: JSON-RPC 通信
        - HandshakeHandler: 握手处理
        - HandlerExecutor: 处理器执行

    新版概念:
        - Peer: 协议对等端，统一处理消息
        - Transport: 传输层抽象
        - CapabilityRouter: 能力路由
        - HandlerDispatcher: 处理器分发
        - SupervisorRuntime: 多 Worker 管理
        - WorkerSession: 单个 Worker 会话
        - PluginWorkerRuntime: 插件 Worker 运行时

通信流程对比：
    旧版 JSON-RPC 流程:
        1. Core -> Plugin: {"method": "handshake", ...}
        2. Plugin -> Core: {"result": {"handlers": [...]}}
        3. Core -> Plugin: {"method": "call_handler", "params": {...}}
        4. Plugin -> Core: {"method": "handler_stream_start", ...}
        5. Plugin -> Core: {"method": "handler_stream_update", ...}
        6. Plugin -> Core: {"method": "handler_stream_end", ...}

    新版协议流程:
        1. Plugin -> Core: {"type": "initialize", "handlers": [...]}
        2. Core -> Plugin: {"type": "result", "kind": "initialize_result", ...}
        3. Core -> Plugin: {"type": "invoke", "capability": "handler.invoke", ...}
        4. Plugin -> Core: {"type": "event", "phase": "started"}
        5. Plugin -> Core: {"type": "event", "phase": "delta", "data": {...}}
        6. Plugin -> Core: {"type": "event", "phase": "completed", "output": {...}}

插件加载对比：
    旧版 StarManager:
        - 通过 plugin.yaml 发现插件
        - 动态导入组件类并实例化
        - 注册到 star_handlers_registry
        - 使用 functools.partial 绑定实例

    新版 loader.py:
        - PluginSpec 描述插件规范
        - PluginEnvironmentManager 管理虚拟环境
        - load_plugin() 加载并解析组件
        - LoadedHandler 封装处理器和描述符
        - 支持新旧 Star 组件兼容

传输层对比：
    旧版传输层:
        - 分离的 client/ 和 server/ 目录
        - JSONRPCClient 基类 + StdioClient/WebSocketClient
        - JSONRPCServer 基类 + StdioServer/WebSocketServer
        - 通过 set_message_handler 设置回调

    新版传输层:
        - 统一的 Transport 抽象基类
        - StdioTransport: 支持进程模式和文件模式
        - WebSocketServerTransport: WebSocket 服务端
        - WebSocketClientTransport: WebSocket 客户端
        - 通过 set_message_handler 设置回调

处理器执行对比：
    旧版 HandlerExecutor:
        - 从 star_handlers_registry 获取处理器
        - 调用 handler(event, **args)
        - 通过 JSON-RPC notification 发送流式结果
        - 无参数注入支持

    新版 HandlerDispatcher:
        - 从 LoadedHandler 映射获取处理器
        - 支持类型注解注入 (MessageEvent, Context)
        - 支持参数名注入 (event, ctx, context)
        - 支持 legacy_args 注入 (命令参数等)
        - 支持 Optional[Type] 类型
        - 统一的错误处理和生命周期回调

能力系统对比：
    旧版:
        - 无显式的能力声明系统
        - 通过 call_context_function 调用核心功能
        - 上下文函数硬编码在核心侧

    新版 CapabilityRouter:
        - CapabilityDescriptor 声明能力
        - JSON Schema 验证输入输出
        - 支持流式能力 (stream_handler)
        - 内置能力：llm.chat, memory.*, db.*, platform.*
        - 支持自定义能力注册

TODO: (架构完善):
    - Transport 缺少 TCP Socket 传输实现
    - Transport 缺少 Unix Domain Socket 传输实现
    - Transport 缺少共享内存传输实现（高性能场景）
    - Peer 缺少消息压缩支持（大数据传输）
    - Peer 缺少消息签名验证（安全通信）
    - CapabilityRouter 缺少能力版本控制
    - CapabilityRouter 缺少能力权限控制
    - CapabilityRouter 缺少能力调用计数/限流
    - HandlerDispatcher 缺少处理器超时控制
    - HandlerDispatcher 缺少处理器重试机制
    - HandlerDispatcher 缺少处理器依赖注入容器
    - loader.py 缺少插件热重载支持
    - loader.py 缺少插件依赖解析
    - loader.py 缺少插件沙箱隔离
    - bootstrap.py 缺少优雅关闭的超时机制
    - bootstrap.py 缺少健康检查端点
    - 缺少分布式部署支持（多节点 Supervisor）
    - 缺少插件状态持久化和恢复

TODO: (功能迁移):
    - 旧版 api/context.py 的功能需要迁移到新版 Context
    - 旧版 api/conversation_mgr.py 的会话管理需要迁移
    - 旧版 stars/filter/ 的过滤器需要评估迁移必要性
    - 旧版 stars/registry/ 的注册表功能已被 loader.py 替代
    - 旧版 galaxy.py 的虚拟星层管理已被 bootstrap.py 替代
"""

from .bootstrap import (
    PluginWorkerRuntime,
    SupervisorRuntime,
    WorkerSession,
    run_plugin_worker,
    run_supervisor,
    run_websocket_server,
)
from .capability_router import CapabilityRouter, StreamExecution
from .handler_dispatcher import HandlerDispatcher
from .loader import (
    LoadedHandler,
    LoadedPlugin,
    PluginDiscoveryResult,
    PluginEnvironmentManager,
    PluginSpec,
    discover_plugins,
    load_plugin,
    load_plugin_spec,
)
from .peer import (
    CancelHandler,
    InitializeHandler,
    InvokeHandler,
    Peer,
)
from .transport import (
    MessageHandler,
    StdioTransport,
    Transport,
    WebSocketClientTransport,
    WebSocketServerTransport,
)

__all__ = [
    "CancelHandler",
    "CapabilityRouter",
    "HandlerDispatcher",
    "InitializeHandler",
    "InvokeHandler",
    "LoadedHandler",
    "LoadedPlugin",
    "MessageHandler",
    "Peer",
    "PluginDiscoveryResult",
    "PluginEnvironmentManager",
    "PluginSpec",
    "PluginWorkerRuntime",
    "StdioTransport",
    "StreamExecution",
    "SupervisorRuntime",
    "Transport",
    "WebSocketClientTransport",
    "WebSocketServerTransport",
    "WorkerSession",
    "discover_plugins",
    "load_plugin",
    "load_plugin_spec",
    "run_plugin_worker",
    "run_supervisor",
    "run_websocket_server",
]
