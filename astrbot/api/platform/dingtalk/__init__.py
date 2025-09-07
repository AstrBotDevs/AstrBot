"""
astrbot.api.platform.dingtalk
该模块包含了 AstrBot 有关 钉钉 平台适配器的相关
"""

from astrbot.core.platform.sources.dingtalk.dingtalk_event import DingtalkMessageEvent

from astrbot.core.platform.sources.dingtalk.dingtalk_adapter import (
    DingtalkPlatformAdapter as DingtalkAdapter,
)

__all__ = [
    "DingtalkAdapter",
    "DingtalkMessageEvent",
]
