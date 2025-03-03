from astrbot.core.platform import (
    AstrMessageEvent,
    Platform,
    AstrBotMessage,
    MessageMember,
    MessageType,
    PlatformMetadata,
)

from astrbot.core.platform.register import register_platform_adapter
from astrbot.core.message.components import *

from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import AiocqhttpAdapter
from astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter import QQOfficialPlatformAdapter
from astrbot.core.platform.sources.qqofficial_webhook.qo_webhook_adapter import QQOfficialWebhookPlatformAdapter
from astrbot.core.platform.sources.gewechat.gewechat_platform_adapter import GewechatPlatformAdapter
from astrbot.core.platform.sources.telegram.tg_adapter import TelegramPlatformAdapter
from astrbot.core.platform.sources.webchat.webchat_adapter import WebChatAdapter
from astrbot.core.platform.sources.wecom.wecom_adapter import WecomPlatformAdapter
from astrbot.core.platform.sources.lark.lark_adapter import LarkPlatformAdapter

__all__ = [
    "AstrMessageEvent",
    "Platform",
    "AstrBotMessage",
    "MessageMember",
    "MessageType",
    "PlatformMetadata",
    "register_platform_adapter",
    "AiocqhttpAdapter",
    "QQOfficialPlatformAdapter",
    "QQOfficialWebhookPlatformAdapter",
    "GewechatPlatformAdapter",
    "TelegramPlatformAdapter",
    "WebChatAdapter",
    "WecomPlatformAdapter",
    "LarkPlatformAdapter",
]
