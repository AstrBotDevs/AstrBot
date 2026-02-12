import asyncio
import logging
from typing import Any, cast

import botpy
import botpy.message
from botpy import Client
from botpy.http import Route

from astrbot import logger
from astrbot.api.event import MessageChain
from astrbot.api.platform import AstrBotMessage, MessageType, Platform, PlatformMetadata
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.core.utils.webhook_utils import log_webhook_info

from ...register import register_platform_adapter
from ..qqofficial.qqofficial_message_event import QQOfficialMessageEvent
from ..qqofficial.qqofficial_platform_adapter import QQOfficialPlatformAdapter
from .qo_webhook_event import QQOfficialWebhookMessageEvent
from .qo_webhook_server import QQOfficialWebhook

# remove logger handler
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)


# QQ 机器人官方框架
class botClient(Client):
    def set_platform(self, platform: "QQOfficialWebhookPlatformAdapter") -> None:
        self.platform = platform

    # 收到群消息
    async def on_group_at_message_create(
        self, message: botpy.message.GroupMessage
    ) -> None:
        abm = QQOfficialPlatformAdapter._parse_from_qqofficial(
            message,
            MessageType.GROUP_MESSAGE,
        )
        abm.group_id = cast(str, message.group_openid)
        abm.session_id = abm.group_id
        self._commit(abm)

    # 收到频道消息
    async def on_at_message_create(self, message: botpy.message.Message) -> None:
        abm = QQOfficialPlatformAdapter._parse_from_qqofficial(
            message,
            MessageType.GROUP_MESSAGE,
        )
        abm.group_id = message.channel_id
        abm.session_id = abm.group_id
        self._commit(abm)

    # 收到私聊消息
    async def on_direct_message_create(
        self, message: botpy.message.DirectMessage
    ) -> None:
        abm = QQOfficialPlatformAdapter._parse_from_qqofficial(
            message,
            MessageType.FRIEND_MESSAGE,
        )
        abm.session_id = abm.sender.user_id
        self._commit(abm)

    # 收到 C2C 消息
    async def on_c2c_message_create(self, message: botpy.message.C2CMessage) -> None:
        abm = QQOfficialPlatformAdapter._parse_from_qqofficial(
            message,
            MessageType.FRIEND_MESSAGE,
        )
        abm.session_id = abm.sender.user_id
        self._commit(abm)

    def _commit(self, abm: AstrBotMessage) -> None:
        self.platform.remember_session_message_id(abm.session_id, abm.message_id)
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
        self._session_last_message_id: dict[str, str] = {}

    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ) -> None:
        (
            plain_text,
            image_base64,
            image_path,
            record_file_path,
        ) = await QQOfficialMessageEvent._parse_to_qqofficial(message_chain)
        if not plain_text and not image_path:
            return

        msg_id = self._session_last_message_id.get(session.session_id)
        if not msg_id:
            logger.warning(
                "[QQOfficialWebhook] No cached msg_id for session: %s, skip send_by_session",
                session.session_id,
            )
            return

        payload: dict[str, Any] = {"content": plain_text, "msg_id": msg_id}
        ret: Any = None
        if session.message_type == MessageType.GROUP_MESSAGE:
            if image_path:
                payload["file_image"] = image_path
            ret = await self.client.api.post_message(
                channel_id=session.session_id,
                **payload,
            )
        elif session.message_type == MessageType.FRIEND_MESSAGE:
            if image_base64 or image_path or record_file_path:
                logger.warning(
                    "[QQOfficialWebhook] send_by_session friend session currently only supports plain text: %s",
                    session.session_id,
                )
            route = Route(
                "POST",
                "/v2/users/{openid}/messages",
                openid=session.session_id,
            )
            ret = await self.client.api._http.request(route, json=payload)
        else:
            logger.warning(
                "[QQOfficialWebhook] Unsupported message type for send_by_session: %s",
                session.message_type,
            )
            return

        sent_message_id = self._extract_message_id(ret)
        if sent_message_id:
            self.remember_session_message_id(session.session_id, sent_message_id)
        await super().send_by_session(session, message_chain)

    def remember_session_message_id(self, session_id: str, message_id: str) -> None:
        if not session_id or not message_id:
            return
        self._session_last_message_id[session_id] = message_id

    def _extract_message_id(self, ret: Any) -> str | None:
        if isinstance(ret, dict):
            message_id = ret.get("id")
            return str(message_id) if message_id else None
        if "id" in ret:
            return ret["id"]
        return None

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="qq_official_webhook",
            description="QQ 机器人官方 API 适配器",
            id=cast(str, self.config.get("id")),
            support_proactive_message=True,
        )

    async def run(self) -> None:
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

    async def terminate(self) -> None:
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
