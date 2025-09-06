"""
astrbot.api.platform.lark
该模块包括了 AstrBot 飞书平台适配器的相关导入
"""

from astrbot.core.platform.sources.lark.lark_adapter import (
    LarkPlatformAdapter as LarkAdapter,
)

from astrbot.core.platform.sources.lark.lark_event import LarkMessageEvent

__all__ = [
    "LarkAdapter",
    "LarkMessageEvent",
]
