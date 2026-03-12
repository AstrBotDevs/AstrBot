"""AstrBot SDK 的高级运行时原语。

这里仅暴露相对稳定的运行时构件：协议 `Peer`、传输抽象以及能力/处理器分发器。
大多数插件作者应优先使用顶层 `astrbot_sdk` 或 `astrbot_sdk.api`。
`loader` / `bootstrap` 等编排细节保留在各自子模块中，不作为根级稳定契约。
"""

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
