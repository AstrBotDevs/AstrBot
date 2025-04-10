import botpy
import logging
import asyncio
import botpy.message
import botpy.types
import botpy.types.message

from botpy import Client
from astrbot.api.platform import Platform, AstrBotMessage, MessageType, PlatformMetadata
from astrbot.api.event import MessageChain
from astrbot.core.platform.astr_message_event import MessageSesion
from .qo_webhook_event import QQOfficialWebhookMessageEvent
from ...register import register_platform_adapter
from .qo_webhook_server import QQOfficialWebhook
from ..qqofficial.qqofficial_platform_adapter import QQOfficialPlatformAdapter
from astrbot import logger

# remove logger handler
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)


# QQ 机器人官方框架
class botClient(Client):
    def set_platform(self, platform: "QQOfficialWebhookPlatformAdapter"):
        self.platform = platform

    # 收到群消息
    async def on_group_at_message_create(self, message: botpy.message.GroupMessage):
        abm = QQOfficialPlatformAdapter._parse_from_qqofficial(
            message, MessageType.GROUP_MESSAGE
        )
        abm.session_id = (
            abm.sender.user_id if self.platform.unique_session else message.group_openid
        )
        self._commit(abm)

    # 收到频道消息
    async def on_at_message_create(self, message: botpy.message.Message):
        abm = QQOfficialPlatformAdapter._parse_from_qqofficial(
            message, MessageType.GROUP_MESSAGE
        )
        abm.session_id = (
            abm.sender.user_id if self.platform.unique_session else message.channel_id
        )
        self._commit(abm)

    # 收到私聊消息
    async def on_direct_message_create(self, message: botpy.message.DirectMessage):
        abm = QQOfficialPlatformAdapter._parse_from_qqofficial(
            message, MessageType.FRIEND_MESSAGE
        )
        abm.session_id = abm.sender.user_id
        self._commit(abm)

    # 收到 C2C 消息
    async def on_c2c_message_create(self, message: botpy.message.C2CMessage):
        abm = QQOfficialPlatformAdapter._parse_from_qqofficial(
            message, MessageType.FRIEND_MESSAGE
        )
        abm.session_id = abm.sender.user_id
        self._commit(abm)

    def _commit(self, abm: AstrBotMessage):
        self.platform.commit_event(
            QQOfficialWebhookMessageEvent(
                abm.message_str, abm, self.platform.meta(), abm.session_id, self
            )
        )


@register_platform_adapter("qq_official_webhook", "QQ 机器人官方 API 适配器(Webhook)")
class QQOfficialWebhookPlatformAdapter(Platform):
    def __init__(
        self, platform_config: dict, platform_settings: dict, event_queue: asyncio.Queue
    ) -> None:
        super().__init__(event_queue)

        self.config = platform_config

        self.appid = platform_config["appid"]
        self.secret = platform_config["secret"]
        self.unique_session = platform_settings["unique_session"]

        intents = botpy.Intents(
            public_messages=True, public_guild_messages=True, direct_message=True
        )
        self.client = botClient(
            intents=intents,  # 已经无用
            bot_log=False,
            timeout=20,
        )
        self.client.set_platform(self)

    async def send_by_session(
        self, session: MessageSesion, message_chain: MessageChain
    ):
        raise NotImplementedError("QQ 机器人官方 API 适配器不支持 send_by_session")

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="qq_official_webhook",
            description="QQ 机器人官方 API 适配器",
            id=self.config.get("id"),
        )

    async def run(self):
        self.webhook_helper = QQOfficialWebhook(
            self.config, self._event_queue, self.client
        )
        await self.webhook_helper.initialize()
        await self.webhook_helper.start_polling()

    def get_client(self) -> botClient:
        return self.client

    async def terminate(self):
        self.webhook_helper.shutdown_event.set()
        await self.client.close()
        try:
            await self.webhook_helper.server.shutdown()
        except Exception as _:
            pass
        logger.info("QQ 机器人官方 API 适配器已经被优雅地关闭")
