"""旧版 ``astrbot.api.all`` 兼容入口。"""

from loguru import logger

from astrbot.api import AstrBotConfig, html_renderer, llm_tool, sp
from astrbot.api.event import (
    AstrBotMessage,
    AstrMessageEvent,
    EventResultType,
    Group,
    MessageChain,
    MessageEventResult,
    MessageMember,
    MessageType,
)
from astrbot.api.event.filter import (
    EventMessageType,
    EventMessageTypeFilter,
    PlatformAdapterType,
    PlatformAdapterTypeFilter,
    command,
    command_group,
    event_message_type,
    platform_adapter_type,
    regex,
)
from astrbot.api.platform import PlatformMetadata
from astrbot.api.provider import (
    LLMResponse,
    Provider,
    ProviderMetaData,
    ProviderRequest,
    ProviderType,
    STTProvider,
)
from astrbot.api.star import Context, Star, register
from astrbot.api.message_components import *  # noqa: F403

__all__ = [
    "AstrBotConfig",
    "AstrBotMessage",
    "AstrMessageEvent",
    "Context",
    "EventMessageType",
    "EventMessageTypeFilter",
    "EventResultType",
    "Group",
    "LLMResponse",
    "MessageChain",
    "MessageEventResult",
    "MessageMember",
    "MessageType",
    "PlatformAdapterType",
    "PlatformAdapterTypeFilter",
    "PlatformMetadata",
    "Provider",
    "ProviderMetaData",
    "ProviderRequest",
    "ProviderType",
    "STTProvider",
    "Star",
    "command",
    "command_group",
    "event_message_type",
    "html_renderer",
    "llm_tool",
    "logger",
    "platform_adapter_type",
    "regex",
    "register",
    "sp",
]
