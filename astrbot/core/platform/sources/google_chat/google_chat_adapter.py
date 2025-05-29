import asyncio
import uuid
import quart
import astrbot.api.message_components as Comp
from astrbot.api.platform import (
    Platform,
    AstrBotMessage,
    MessageMember,
    MessageType,
    PlatformMetadata,
)
from astrbot.api.event import MessageChain
from astrbot.core.platform.astr_message_event import MessageSesion
from .google_chat_event import GoogleChatMessageEvent
from ...register import register_platform_adapter
from astrbot import logger


class GoogleChatServer:
    def __init__(self, adapter: "GoogleChatPlatformAdapter", config: dict):
        self.adapter = adapter
        self.port = int(config.get("port", 6200))
        self.host = config.get("callback_server_host", "0.0.0.0")
        self.verification_token = config.get("verification_token", "")
        self.server = quart.Quart(__name__)
        self.server.add_url_rule(
            "/astrbot-googlechat/callback", view_func=self.callback, methods=["POST"]
        )
        self.shutdown_event = asyncio.Event()

    async def callback(self):
        data = await quart.request.get_json()
        token = quart.request.headers.get("Authorization")
        if self.verification_token and token != f"Bearer {self.verification_token}":
            logger.warning("Google Chat verification failed")
            return {"success": False}, 403
        await self.adapter.on_event(data)
        return {"success": True}

    async def start_polling(self):
        logger.info(
            f"Google Chat adapter listening on {self.host}:{self.port}"
        )
        await self.server.run_task(
            host=self.host, port=self.port, shutdown_trigger=self.shutdown_trigger
        )

    async def shutdown_trigger(self):
        await self.shutdown_event.wait()

    async def shutdown(self):
        self.shutdown_event.set()


@register_platform_adapter("google_chat", "Google Chat 适配器")
class GoogleChatPlatformAdapter(Platform):
    def __init__(
        self, platform_config: dict, platform_settings: dict, event_queue: asyncio.Queue
    ) -> None:
        super().__init__(event_queue)
        self.config = platform_config
        self.settings = platform_settings
        self.bot_name = platform_config.get("bot_name", "astrbot")
        self.unique_session = platform_settings["unique_session"]
        self.server = GoogleChatServer(self, platform_config)

    async def send_by_session(self, session: MessageSesion, message_chain: MessageChain):
        await GoogleChatMessageEvent._send_chain(session.session_id, message_chain)
        await super().send_by_session(session, message_chain)

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="google_chat", description="Google Chat 适配器", id=self.config.get("id")
        )

    async def on_event(self, payload: dict):
        abm = await self.convert_message(payload)
        if abm:
            await self.handle_msg(abm)

    async def convert_message(self, payload: dict) -> AstrBotMessage | None:
        if payload.get("type") != "MESSAGE":
            return None
        message = payload.get("message", {})
        sender = message.get("sender", {})
        text = message.get("text", "")
        attachments = message.get("attachments", [])

        abm = AstrBotMessage()
        abm.message_id = message.get("name", str(uuid.uuid4()))
        abm.sender = MessageMember(
            user_id=sender.get("name", ""), nickname=sender.get("displayName", "")
        )
        abm.self_id = self.bot_name
        abm.message_str = text
        abm.message = [Comp.Plain(text)] if text else []
        for att in attachments:
            ctype = att.get("contentType", "")
            if isinstance(ctype, str) and ctype.startswith("image/"):
                url = att.get("downloadUri") or att.get("imageUri") or att.get("thumbnailUri")
                if url:
                    abm.message.append(Comp.Image(file=url, url=url))
                    abm.message_str += " [图片]"

        space = payload.get("space", {})
        if space.get("type") == "ROOM":
            abm.type = MessageType.GROUP_MESSAGE
            abm.group_id = space.get("name")
        else:
            abm.type = MessageType.FRIEND_MESSAGE
        abm.session_id = payload.get("responseUrl", self.config.get("webhook_url", ""))
        abm.raw_message = payload
        abm.timestamp = int(payload.get("eventTime", 0)) if isinstance(payload.get("eventTime"), int) else 0
        return abm

    async def handle_msg(self, abm: AstrBotMessage):
        event = GoogleChatMessageEvent(
            message_str=abm.message_str,
            message_obj=abm,
            platform_meta=self.meta(),
            session_id=abm.session_id,
        )
        self.commit_event(event)

    async def run(self):
        await self.server.start_polling()

    async def terminate(self):
        await self.server.shutdown()
        logger.info("Google Chat adapter shutdown")

    def get_client(self):
        return self.server
