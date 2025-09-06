"""
astrbot.api.platform.wechatpadpro
该模块包含了 AstrBot 对 gewechat 的适配器
"""

from astrbot.core.platform.sources.wechatpadpro.wechatpadpro_message_event import (
    WeChatPadProMessageEvent,
)
from astrbot.core.platform.sources.wechatpadpro.wechatpadpro_adapter import (
    WeChatPadProAdapter,
)
from astrbot.core.platform.sources.wechatpadpro.xml_data_parser import (
    GeweDataParser,
)

__all__ = [
    "WeChatPadProAdapter",
    "WeChatPadProMessageEvent",
    "GeweDataParser",
]
