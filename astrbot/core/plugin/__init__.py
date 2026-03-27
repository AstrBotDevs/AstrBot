"""AstrBot Plugin System (ABP)

ABP is the plugin communication protocol for AstrBot, supporting:
- In-process and out-of-process loading modes
- Full plugin lifecycle management
- Tool calling, message handling, event subscriptions
- JSON-RPC 2.0 communication
"""

from .client import PluginClient
from .const import ABP_VERSION, get_error_message
from .manager import PluginManager
from .models import (
    EventNotification,
    HandleEventResult,
    MessageChainItem,
    MessageEvent,
    PluginCapabilities,
    PluginConfig,
    PluginInfo,
    PluginMetadata,
    SenderInfo,
    Tool,
    ToolContent,
    ToolResult,
)
from .transport import HttpTransport, StdioTransport, UnixSocketTransport

__all__ = [
    "ABP_VERSION",
    "EventNotification",
    "HandleEventResult",
    "HttpTransport",
    "MessageChainItem",
    "MessageEvent",
    "PluginCapabilities",
    "PluginClient",
    "PluginConfig",
    "PluginInfo",
    "PluginManager",
    "PluginMetadata",
    "SenderInfo",
    "StdioTransport",
    "Tool",
    "ToolContent",
    "ToolResult",
    "UnixSocketTransport",
    "get_error_message",
]
