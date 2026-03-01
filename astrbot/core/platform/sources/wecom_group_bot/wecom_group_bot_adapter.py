"""企业微信消息推送机器人（原群机器人）适配器"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import Image, Plain
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
)
from astrbot.core.platform.astr_message_event import MessageSesion

from ...register import register_platform_adapter
from .wecom_group_bot_client import WecomGroupBotClient
from .wecom_group_bot_event import WecomGroupBotEvent
from .wecom_group_bot_parser import WecomGroupBotParser
from .wecom_group_bot_server import WecomGroupBotServer


@register_platform_adapter(
    "wecom_group_bot",
    "企业微信消息推送机器人（原群机器人）适配器",
    default_config_tmpl={
        "token": "your_token",
        "encoding_aes_key": "your_encoding_aes_key",
        "port": 6200,
        "callback_server_host": "0.0.0.0",
        "callback_path": "/webhook/wecom-group-bot",
        "callback_format": "xml",
        "receive_id": "",
        "wecomaibot_init_respond_text": "💭 思考中...",
        "wecomaibot_friend_message_welcome_text": "",
    },
)
class WecomGroupBotAdapter(Platform):
    """将企业微信消息推送机器人接入 AstrBot"""

    def __init__(self, platform_config: dict, platform_settings: dict, event_queue: asyncio.Queue) -> None:
        super().__init__(event_queue)
        self.config = platform_config
        self.settings = platform_settings

        self.token = self.config["token"]
        self.encoding_aes_key = self.config["encoding_aes_key"]
        self.host = self.config.get("callback_server_host", "0.0.0.0")
        self.port = int(self.config.get("port", 0) or 0)
        self.callback_path = self.config.get("callback_path", "/webhook/wecom-group-bot")
        self.receive_id = self.config.get("receive_id", "")
        self.callback_format = self.config.get("callback_format", "xml")
        self.initial_respond_text = self.config.get(
            "wecomaibot_init_respond_text",
            "💭 思考中...",
        )
        self.friend_message_welcome_text = self.config.get(
            "wecomaibot_friend_message_welcome_text",
            "",
        )

        self.metadata = PlatformMetadata(
            name="wecom_group_bot",
            description="企业微信消息推送机器人（原群机器人）适配器",
            id=self.config.get("id", "wecom_group_bot"),
        )

        self.parser = WecomGroupBotParser(self.callback_format)
        self.client = WecomGroupBotClient()
        self.server = WecomGroupBotServer(
            host=self.host,
            port=self.port,
            token=self.token,
            encoding_aes_key=self.encoding_aes_key,
            receive_id=self.receive_id,
            parser=self.parser,
            message_handler=self._handle_incoming_message,
            callback_path=self.callback_path,
        )

    async def _handle_incoming_message(self, message_data: dict[str, Any], metadata: dict[str, str]):
        if not message_data:
            logger.warning("收到空的企业微信消息推送机器人（原群机器人）消息，忽略")
            return

        await self._maybe_send_auto_reply(message_data)

        abm = await self.convert_message(message_data, metadata)
        if abm:
            await self.handle_msg(abm)

    async def convert_message(self, payload: dict[str, Any], metadata: dict[str, str]) -> AstrBotMessage | None:
        msgtype = str(payload.get("msgtype") or payload.get("msg_type") or "").lower()
        if not msgtype:
            logger.warning("无法识别的企业微信消息推送机器人（原群机器人）消息: %s", payload)
            return None

        sender_data = payload.get("from", {}) or {}
        user_id = sender_data.get("userid") or sender_data.get("user_id") or "unknown"
        nickname = sender_data.get("name") or sender_data.get("alias") or user_id
        chat_id = payload.get("chatid") or payload.get("chat_id") or user_id
        message_id = payload.get("msgid") or uuid.uuid4().hex

        abm = AstrBotMessage()
        abm.self_id = payload.get("webhook_url", self.metadata.id)
        abm.sender = MessageMember(user_id=user_id, nickname=nickname)
        abm.session_id = chat_id
        abm.message_id = message_id
        abm.timestamp = int(time.time())
        abm.raw_message = {"payload": payload, "metadata": metadata}
        abm.type = (
            MessageType.GROUP_MESSAGE
            if str(payload.get("chattype") or "").lower() == "group"
            else MessageType.FRIEND_MESSAGE
        )

        message_components, message_str = await self._build_message_components(msgtype, payload)
        abm.message = message_components or [Plain(message_str or "")]
        abm.message_str = message_str or ""

        return abm

    async def _build_message_components(
        self,
        msgtype: str,
        payload: dict[str, Any],
    ) -> tuple[list, str]:
        components: list = []
        message_str = ""

        if msgtype == "text":
            content = str(payload.get("text", {}).get("content", "")).strip()
            message_str = content
            components.append(Plain(content))
        elif msgtype == "image":
            image_url = payload.get("image", {}).get("image_url") or payload.get("image", {}).get("url")
            message_str = "[图片]"
            if image_url:
                components.append(Image(file=image_url, url=image_url))
        elif msgtype == "mixed":
            items = payload.get("mixed_message", {}).get("msg_item", [])
            texts: list[str] = []
            for item in items:
                item_type = str(item.get("msg_type", "")).lower()
                if item_type == "text":
                    text_content = item.get("text", {}).get("content", "")
                    texts.append(text_content)
                    components.append(Plain(text_content))
                elif item_type == "image":
                    image_url = item.get("image", {}).get("image_url")
                    if image_url:
                        components.append(Image(file=image_url, url=image_url))
            message_str = " ".join(texts)
        elif msgtype == "event":
            event_type = payload.get("event", {}).get("event_type")
            message_str = f"[事件] {event_type}" if event_type else "[事件]"
            components.append(Plain(message_str))
        elif msgtype == "attachment":
            callback_id = payload.get("attachment", {}).get("callback_id")
            message_str = f"[按钮回调] {callback_id or ''}".strip()
            components.append(Plain(message_str))
        else:
            message_str = f"[{msgtype}]"
            components.append(Plain(message_str))

        return components, message_str

    async def send_by_session(self, session: MessageSesion, message_chain: MessageChain):
        logger.info("WeCom 群机器人 send_by_session: %s -> %s", session.session_id, message_chain)
        await super().send_by_session(session, message_chain)

    async def _maybe_send_auto_reply(self, payload: dict[str, Any]) -> None:
        webhook_url = payload.get("webhook_url") or payload.get("response_url")
        chat_id = payload.get("chatid") or payload.get("chat_id")
        msgtype = str(payload.get("msgtype") or payload.get("msg_type") or "").lower()

        if not webhook_url or not chat_id:
            return

        try:
            if msgtype in {"text", "image", "mixed"} and self.initial_respond_text:
                await self.client.send_plain_message(
                    webhook_url,
                    chat_id,
                    Plain(self.initial_respond_text),
                )
            elif (
                msgtype == "event"
                and (payload.get("event") or {}).get("event_type") == "enter_chat"
                and self.friend_message_welcome_text
            ):
                await self.client.send_plain_message(
                    webhook_url,
                    chat_id,
                    Plain(self.friend_message_welcome_text),
                )
        except Exception as exc:  # pragma: no cover - defensive log
            logger.error("企业微信消息推送机器人（原群机器人）自动回复失败: %s", exc)

    def meta(self) -> PlatformMetadata:
        return self.metadata

    async def run(self):
        await self.server.start()

    async def terminate(self):
        await self.server.stop()

    async def handle_msg(self, message: AstrBotMessage):
        event = WecomGroupBotEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            client=self.client,
        )
        self.commit_event(event)
