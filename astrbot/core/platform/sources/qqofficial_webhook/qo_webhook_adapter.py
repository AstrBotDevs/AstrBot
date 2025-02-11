import botpy
import logging
import time
import asyncio
import os

from botpy import BotAPI, BotHttp
from astrbot.api.platform import Platform, AstrBotMessage, MessageMember, MessageType, PlatformMetadata
from astrbot.api.event import MessageChain
from typing import Union, List
from astrbot.api.message_components import Image, Plain, At
from astrbot.core.platform.astr_message_event import MessageSesion
# from .qqofficial_message_event import QQOfficialMessageEvent
from ...register import register_platform_adapter
from astrbot.core.message.components import BaseMessageComponent
from .qo_webhook_server import QQOfficialWebhook

# remove logger handler
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)
        
@register_platform_adapter("qq_official_webhook", "QQ 机器人官方 API 适配器(Webhook)")
class QQOfficialWebhookPlatformAdapter(Platform):

    def __init__(self, platform_config: dict, platform_settings: dict, event_queue: asyncio.Queue) -> None:
        super().__init__(event_queue)
        
        self.config = platform_config
        
        self.appid = platform_config['appid']
        self.secret = platform_config['secret']
        self.unique_session = platform_settings['unique_session']
        qq_group = platform_config['enable_group_c2c']
        guild_dm = platform_config['enable_guild_direct_message']

        if qq_group:
            self.intents = botpy.Intents(
                public_messages=True,
                public_guild_messages=True,
                direct_message=guild_dm
            )
        else:
            self.intents = botpy.Intents(
                public_guild_messages=True,
                direct_message=guild_dm
            )


    async def send_by_session(self, session: MessageSesion, message_chain: MessageChain):
        raise NotImplementedError("QQ 机器人官方 API 适配器不支持 send_by_session")
        
    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            "qq_official_webhook",
            "QQ 机器人官方 API 适配器",
        )

    async def run(self):
        self.webhook_helper = QQOfficialWebhook(
            self.config,
            self._event_queue
        )
        await self.webhook_helper.initialize()
        await self.webhook_helper.start_polling()