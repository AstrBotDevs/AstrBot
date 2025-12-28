import asyncio
import logging
from typing import Any, cast

import botpy
import botpy.message
import botpy.types
import botpy.types.message
from botpy import Client

from astrbot import logger
from astrbot.api.event import MessageChain
from astrbot.api.platform import AstrBotMessage, MessageType, Platform, PlatformMetadata
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.core.utils.webhook_utils import log_webhook_info

from ...register import register_platform_adapter
from ..qqofficial.qqofficial_platform_adapter import QQOfficialPlatformAdapter
from .qo_webhook_event import QQOfficialWebhookMessageEvent
from .qo_webhook_server import QQOfficialWebhook

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
            message,
            MessageType.GROUP_MESSAGE,
        )
        abm.group_id = cast(str, message.group_openid)
        abm.session_id = abm.group_id
        self._commit(abm)

    # 收到频道消息
    async def on_at_message_create(self, message: botpy.message.Message):
        abm = QQOfficialPlatformAdapter._parse_from_qqofficial(
            message,
            MessageType.GROUP_MESSAGE,
        )
        abm.group_id = message.channel_id
        abm.session_id = abm.group_id
        self._commit(abm)

    # 收到私聊消息
    async def on_direct_message_create(self, message: botpy.message.DirectMessage):
        abm = QQOfficialPlatformAdapter._parse_from_qqofficial(
            message,
            MessageType.FRIEND_MESSAGE,
        )
        abm.session_id = abm.sender.user_id
        self._commit(abm)

    # 收到 C2C 消息
    async def on_c2c_message_create(self, message: botpy.message.C2CMessage):
        abm = QQOfficialPlatformAdapter._parse_from_qqofficial(
            message,
            MessageType.FRIEND_MESSAGE,
        )
        abm.session_id = abm.sender.user_id
        self._commit(abm)

    def _commit(self, abm: AstrBotMessage):
        self.platform.commit_event(
            QQOfficialWebhookMessageEvent(
                abm.message_str,
                abm,
                self.platform.meta(),
                abm.session_id,
                self,
            ),
        )


@register_platform_adapter("qq_official_webhook", "QQ 机器人官方 API 适配器(Webhook)")
class QQOfficialWebhookPlatformAdapter(Platform):
    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)

        self.appid = platform_config["appid"]
        self.secret = platform_config["secret"]
        self.unified_webhook_mode = platform_config.get("unified_webhook_mode", False)

        intents = botpy.Intents(
            public_messages=True,
            public_guild_messages=True,
            direct_message=True,
        )
        self.client = botClient(
            intents=intents,  # 已经无用
            bot_log=False,
            timeout=20,
        )
        self.client.set_platform(self)
        self.webhook_helper = None

    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ):
        raise NotImplementedError("QQ 机器人官方 API 适配器不支持 send_by_session")

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="qq_official_webhook",
            description="QQ 机器人官方 API 适配器",
            id=cast(str, self.config.get("id")),
        )

    async def run(self):
        self.webhook_helper = QQOfficialWebhook(
            self.config,
            self._event_queue,
            self.client,
        )
        await self.webhook_helper.initialize()

        # 如果启用统一 webhook 模式，则不启动独立服务器
        webhook_uuid = self.config.get("webhook_uuid")
        if self.unified_webhook_mode and webhook_uuid:
            log_webhook_info(f"{self.meta().id}(QQ 官方机器人 Webhook)", webhook_uuid)
            # 保持运行状态，等待 shutdown
            await self.webhook_helper.shutdown_event.wait()
        else:
            await self.webhook_helper.start_polling()

    def get_client(self) -> botClient:
        return self.client

    async def webhook_callback(self, request: Any) -> Any:
        """统一 Webhook 回调入口"""
        if not self.webhook_helper:
            return {"error": "Webhook helper not initialized"}, 500

        # 复用 webhook_helper 的回调处理逻辑
        return await self.webhook_helper.handle_callback(request)

    async def terminate(self):
        if self.webhook_helper:
            self.webhook_helper.shutdown_event.set()
        await self.client.close()
        if self.webhook_helper and not self.unified_webhook_mode:
            try:
                await self.webhook_helper.server.shutdown()
            except Exception as exc:
                logger.warning(
                    f"Exception occurred during QQOfficialWebhook server shutdown: {exc}",
                    exc_info=True,
                )
        logger.info("QQ 机器人官方 API 适配器已经被优雅地关闭")
