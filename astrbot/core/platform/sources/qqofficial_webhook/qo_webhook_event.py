import botpy
import botpy.message
import botpy.types
import botpy.types.message
from astrbot.core.utils.io import file_to_base64, download_image_by_url
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.platform import AstrBotMessage, PlatformMetadata
from astrbot.api.message_components import Plain, Image, Reply
from botpy import Client
from botpy.http import Route
from astrbot.api import logger
from ..qqofficial.qqofficial_message_event import QQOfficialMessageEvent


class QQOfficialWebhookMessageEvent(QQOfficialMessageEvent):
    def __init__(self, message_str: str, message_obj: AstrBotMessage, platform_meta: PlatformMetadata, session_id: str, bot: Client):
        super().__init__(message_str, message_obj, platform_meta, session_id, bot)
    