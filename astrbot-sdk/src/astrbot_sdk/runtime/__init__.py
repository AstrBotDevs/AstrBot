"""AstrBot SDK runtime public exports.

本模块提供运行时核心组件的公共导出，包括：
- CapabilityRouter: 能力路由器，处理能力调用的分发和路由
- HandlerDispatcher: 事件处理器分发器，将事件分发到注册的 handler
- Peer: 与 AstrBot 核心通信的对等端抽象
- Transport 系列: 进程间通信传输层实现（stdio/websocket）

延迟加载策略：
为避免导入时触发 websocket/aiohttp 等重型依赖，采用 __getattr__ 实现按需加载。
这样轻量级导入（如仅使用类型提示）不会产生不必要的依赖开销。
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
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


def __getattr__(name: str) -> Any:
    if name in {"CapabilityRouter", "StreamExecution"}:
        module = import_module(".capability_router", __name__)
        return getattr(module, name)
    if name == "HandlerDispatcher":
        module = import_module(".handler_dispatcher", __name__)
        return getattr(module, name)
    if name == "Peer":
        module = import_module(".peer", __name__)
        return getattr(module, name)
    if name in {
        "MessageHandler",
        "StdioTransport",
        "Transport",
        "WebSocketClientTransport",
        "WebSocketServerTransport",
    }:
        module = import_module(".transport", __name__)
        return getattr(module, name)
    raise AttributeError(name)
