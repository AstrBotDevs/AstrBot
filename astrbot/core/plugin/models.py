"""ABP Protocol Data Models"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PluginCapabilities:
    """Plugin capabilities."""

    tools: bool = False
    handlers: bool = False
    events: bool = False
    resources: bool = False


@dataclass
class PluginMetadata:
    """Plugin metadata."""

    display_name: str | None = None
    description: str | None = None
    author: str | None = None
    homepage: str | None = None
    support_platforms: list[str] = field(default_factory=list)
    astrbot_version: str | None = None


@dataclass
class PluginConfig:
    """Plugin configuration."""

    name: str
    version: str = "1.0.0"
    load_mode: str = "in_process"
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    transport: str = "stdio"
    url: str | None = None


@dataclass
class InitializeParams:
    """Initialize request parameters."""

    protocol_version: str
    client_info: dict[str, str]
    capabilities: dict[str, bool]
    plugin_config: dict[str, Any]
    data_dirs: dict[str, str]


@dataclass
class InitializeResult:
    """Initialize response from plugin."""

    protocol_version: str
    server_info: dict[str, str]
    capabilities: PluginCapabilities
    config_schema: dict[str, Any] | None = None
    metadata: PluginMetadata | None = None


@dataclass
class Tool:
    """Tool definition."""

    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolContent:
    """Tool result content."""

    type: str
    text: str | None = None
    image: str | None = None
    url: str | None = None


@dataclass
class ToolResult:
    """Tool call result."""

    content: list[ToolContent] = field(default_factory=list)


@dataclass
class SenderInfo:
    """Message sender info."""

    user_id: str
    nickname: str = ""


@dataclass
class MessageChainItem:
    """Message chain item."""

    type: str
    text: str | None = None


@dataclass
class MessageEvent:
    """Message event."""

    message_id: str
    unified_msg_origin: str
    message_str: str
    sender: SenderInfo
    message_chain: list[MessageChainItem] = field(default_factory=list)


@dataclass
class HandleEventResult:
    """Handle event result."""

    handled: bool
    results: list[MessageChainItem] = field(default_factory=list)
    stop_propagation: bool = False


@dataclass
class EventNotification:
    """Event notification."""

    event_type: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class PluginInfo:
    """Plugin info for listing."""

    name: str
    version: str
    load_mode: str
    capabilities: PluginCapabilities
    metadata: PluginMetadata | None = None
    tools_count: int = 0
