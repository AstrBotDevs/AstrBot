from astrbot.api.platform import AstrBotMessage, PlatformMetadata
from botpy import Client
from ..qqofficial.qqofficial_message_event import QQOfficialMessageEvent


class QQOfficialWebhookMessageEvent(QQOfficialMessageEvent):
    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
        bot: Client,
    ):
        super().__init__(message_str, message_obj, platform_meta, session_id, bot)
