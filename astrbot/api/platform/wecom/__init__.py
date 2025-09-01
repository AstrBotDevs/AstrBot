"""
astrbot.api.platform.wecom
该模块包含了 AstrBot 对微信客服平台的适配器
"""

from astrbot.core.platform.sources.wecom.wecom_adapter import (
    WecomPlatformAdapter,
    WecomServer,
)

from astrbot.core.platform.sources.wecom.wecom_event import (
    WecomPlatformEvent as WecomMessageEvent,
)

from astrbot.core.platform.sources.wecom.wecom_kf_message import WeChatKFMessage

from astrbot.core.platform.sources.wecom.wecom_kf import WeChatKF

__all__ = [
    "WecomPlatformAdapter",
    "WecomMessageEvent",
    "WeChatKFMessage",
    "WeChatKF",
    "WecomServer",
]
