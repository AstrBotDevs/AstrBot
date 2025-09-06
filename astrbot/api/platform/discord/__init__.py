"""
astrbot.api.platform.discord
该模块包括了 AstrBot 有关 Discord 平台适配器的相关导入
"""

from astrbot.core.platform.sources.discord.components import (
    DiscordEmbed,  # Discord Embed消息组件
    DiscordButton,  # Discord 引用组件
    DiscordReference,  # Discord 视图组件
    DiscordView,  # Discord 视图组件
)

from astrbot.core.platform.sources.discord.discord_platform_adapter import (
    DiscordPlatformAdapter as DiscordAdapter,
)

from astrbot.core.platform.sources.discord.discord_platform_event import (
    DiscordPlatformEvent as DiscordMessageEvent,
)

__all__ = [
    "DiscordAdapter",
    "DiscordMessageEvent",
    "DiscordEmbed",
    "DiscordButton",
    "DiscordReference",
    "DiscordView",
]
