"""
astrbot.api.platform.qqofficial_webhook
该模块包括了 AstrBot 有关 QQ 机器人官方框架 Webhook 适配器的相关导入
"""

from astrbot.core.platform.sources.qqofficial_webhook.qo_webhook_adapter import (
    botClient as Client,
    QQOfficialWebhookPlatformAdapter as QQOfficialWebhookAdapter,
)

from astrbot.core.platform.sources.qqofficial_webhook.qo_webhook_event import (
    QQOfficialWebhookMessageEvent,
)

from astrbot.core.platform.sources.qqofficial_webhook.qo_webhook_server import (
    QQOfficialWebhook,
)

__all__ = [
    "QQOfficialWebhookAdapter",
    "Client",
    "QQOfficialWebhook",
    "QQOfficialWebhookMessageEvent",
]
