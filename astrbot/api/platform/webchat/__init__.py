"""
astrbot.api.platform.webchat
该模块包含了 AstrBot 对 WebChat 平台的适配器
"""

from astrbot.core.platform.sources.webchat.webchat_adapter import (
    WebChatAdapter,
    QueueListener,
)

from astrbot.core.platform.sources.webchat.webchat_event import WebChatMessageEvent

from astrbot.core.platform.sources.webchat.webchat_queue_mgr import WebChatQueueMgr

__all__ = [
    "WebChatAdapter",
    "WebChatMessageEvent",
    "WebChatQueueMgr",
    "QueueListener",
]
