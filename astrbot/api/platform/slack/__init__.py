"""
astrbot.api.platform.slack
该模块包含了 AstrBot 对 Slack 平台的适配器
"""

from astrbot.core.platform.sources.slack.slack_event import (
    SlackMessageEvent,
)

from astrbot.core.platform.sources.slack.slack_adapter import (
    SlackAdapter,
)
from astrbot.core.platform.sources.slack.client import (
    SlackSocketClient,
    SlackWebhookClient,
)

__all__ = [
    "SlackAdapter",
    "SlackSocketClient",
    "SlackMessageEvent",
    "SlackWebhookClient",
]
