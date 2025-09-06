"""
astrbot.api.platform.weixin_official_account
该模块包含了 AstrBot 对 微信公众号 平台的适配器
"""

from astrbot.core.platform.sources.weixin_official_account.weixin_offacc_adapter import (
    WeixinOfficialAccountPlatformAdapter as WeixinOfficialAccountAdapter,
    WecomServer,
)
from astrbot.core.platform.sources.weixin_official_account.weixin_offacc_event import (
    WeixinOfficialAccountPlatformEvent,
)

__all__ = [
    "WeixinOfficialAccountAdapter",
    "WecomServer",
    "WeixinOfficialAccountPlatformEvent",
]
