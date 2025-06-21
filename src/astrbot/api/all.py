from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot import logger
from astrbot.core import html_renderer
from astrbot.core.star.register import register_llm_tool as llm_tool

# event
from astrbot.core.message.message_event_result import (
    MessageEventResult,
    MessageChain,
    CommandResult,
    EventResultType,
)

# star register
from astrbot.core.star.register import (
    register_command as command,
    register_command_group as command_group,
    register_event_message_type as event_message_type,
    register_regex as regex,
    register_platform_adapter_type as platform_adapter_type,
)
from astrbot.core.star.filter.event_message_type import (
    EventMessageTypeFilter,
    EventMessageType,
)
from astrbot.core.star.filter.platform_adapter_type import (
    PlatformAdapterTypeFilter,
    PlatformAdapterType,
)
from astrbot.core.star.register import (
    register_star as register,  # 注册插件（Star）
)
from astrbot.core.star import Context, Star
from astrbot.core.star.config import *  # 过时 跳过检查 # noqa: F401,F403


# provider
from astrbot.core.provider import Provider, Personality, ProviderMetaData

# platform
from astrbot.core.platform import (
    AstrMessageEvent,
    Platform,
    AstrBotMessage,
    MessageMember,
    MessageType,
    PlatformMetadata,
)

from astrbot.core.platform.register import register_platform_adapter

from .message_components import (
    ComponentType,
    BaseMessageComponent,
    Plain,
    Face,
    Record,
    Video,
    At,
    AtAll,
    RPS,
    Dice,
    Shake,
    Anonymous,
    Share,
    Contact,
    Location,
    Music,
    Image,
    Reply,
    RedBag,
    Poke,
    Forward,
    Node,
    Nodes,
    Xml,
    Json,
    CardImage,
    TTS,
    Unknown,
    File,
    WechatEmoji,
    ComponentTypes
)

__all__ = [
    "AstrBotConfig",
    "logger",
    "html_renderer",
    "llm_tool",
    "MessageEventResult",
    "MessageChain",
    "CommandResult",
    "EventResultType",
    "AstrMessageEvent",
    "command",
    "command_group",
    "event_message_type",
    "regex",
    "platform_adapter_type",
    "EventMessageTypeFilter",
    "EventMessageType",
    "PlatformAdapterTypeFilter",
    "PlatformAdapterType",
    "register",
    "Context",
    "Star",
    "Provider",
    "Personality",
    "ProviderMetaData",
    "Platform",
    "AstrBotMessage",
    "MessageMember",
    "MessageType",
    "PlatformMetadata",
    "register_platform_adapter",
    # from .message_components import *
    "ComponentType",
    "BaseMessageComponent",
    "Plain",
    "Face",
    "Record",
    "Video",
    "At",
    "AtAll",
    "RPS",
    "Dice",
    "Shake",
    "Anonymous",
    "Share",
    "Contact",
    "Location",
    "Music",
    "Image",
    "Reply",
    "RedBag",
    "Poke",
    "Forward",
    "Node",
    "Nodes",
    "Xml",
    "Json",
    "CardImage",
    "TTS",
    "Unknown",
    "File",
    "WechatEmoji",
    "ComponentTypes",

]