from .aiocqhttp.aiocqhttp_platform_adapter import AiocqhttpAdapter
from .qqofficial.qqofficial_platform_adapter import QQOfficialPlatformAdapter
from .qqofficial_webhook.qo_webhook_adapter import QQOfficialWebhookPlatformAdapter
from .gewechat.gewechat_platform_adapter import GewechatPlatformAdapter
from .telegram.tg_adapter import TelegramPlatformAdapter
from .webchat.webchat_adapter import WebChatAdapter
from .wecom.wecom_adapter import WecomPlatformAdapter
from .lark.lark_adapter import LarkPlatformAdapter

__all__ = [
    "AiocqhttpAdapter",
    "QQOfficialPlatformAdapter",
    "QQOfficialWebhookPlatformAdapter",
    "GewechatPlatformAdapter",
    "TelegramPlatformAdapter",
    "WebChatAdapter",
    "WecomPlatformAdapter",
    "LarkPlatformAdapter",
]
