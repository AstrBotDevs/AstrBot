import asyncio
import base64
import re
import time
import uuid
from typing import Any

import aiohttp
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.web.async_client import AsyncWebClient

from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import At, File, Image, Plain
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
)
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.register import register_platform_adapter
from astrbot.core.utils.webhook_utils import log_webhook_info

from .client import SlackSocketClient, SlackWebhookClient
from .session_codec import (
    build_slack_text_fallbacks,
    encode_thread_session_id,
    resolve_target_from_session,
)
from .slack_event import SlackMessageEvent
from .slack_send_utils import send_with_blocks_and_fallback


@register_platform_adapter(
    "slack",
    "适用于 Slack 的消息平台适配器,支持 Socket Mode 和 Webhook Mode｡",
    support_streaming_message=False,
)
class SlackAdapter(Platform):
    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)
        self.settings = platform_settings
        self.bot_token = platform_config.get("bot_token")
        self.app_token = platform_config.get("app_token")
        self.signing_secret = platform_config.get("signing_secret")
        self.connection_mode = platform_config.get("slack_connection_mode", "socket")
        self.unified_webhook_mode = platform_config.get("unified_webhook_mode", False)
        self.webhook_host = platform_config.get("slack_webhook_host", "0.0.0.0")
        self.webhook_port = platform_config.get("slack_webhook_port", 3000)
        self.webhook_path = platform_config.get(
            "slack_webhook_path",
            "/astrbot-slack-webhook/callback",
        )
        if not self.bot_token:
            raise ValueError("Slack bot_token 是必需的")
        if self.connection_mode == "socket" and (not self.app_token):
            raise ValueError("Socket Mode 需要 app_token")
        if self.connection_mode == "webhook" and (not self.signing_secret):
            raise ValueError("Webhook Mode 需要 signing_secret")
        self.metadata = PlatformMetadata(
            name="slack",
            description="适用于 Slack 的消息平台适配器,支持 Socket Mode 和 Webhook Mode｡",
            id=self.config.get("id"),
            support_streaming_message=False,
        )
        self.web_client = AsyncWebClient(token=self.bot_token, logger=logger)
        self.socket_client = None
        self.webhook_client = None
        self.bot_self_id = ""
        self.text_fallbacks = build_slack_text_fallbacks(
            platform_config.get("text_fallbacks")
        )

    async def send_by_session(
        self,
        session: MessageSession,
        message_chain: MessageChain,
    ) -> None:
        channel_id, thread_ts = resolve_target_from_session(
            session_id=session.session_id
        )
        await send_with_blocks_and_fallback(
            web_client=self.web_client,
            channel=channel_id,
            thread_ts=thread_ts,
            message_chain=message_chain,
            fallbacks=self.text_fallbacks,
            parse_blocks=SlackMessageEvent._parse_slack_blocks,
            build_text_fallback=SlackMessageEvent._build_text_fallback_from_chain,
            session_id=session.session_id,
        )
        await super().send_by_session(session, message_chain)

    @staticmethod
    def _unwrap_message_replied_event(event: dict) -> dict:
        """Flatten Slack message_replied envelopes for normal message processing."""
        if event.get("subtype") == "message_replied":
            nested_message = event.get("message")
            if isinstance(nested_message, dict):
                merged = dict(event)
                merged.update(nested_message)
                if not merged.get("channel"):
                    merged["channel"] = event.get("channel", "")
                return merged
        return event

    async def convert_message(self, event: dict) -> AstrBotMessage:
        event = self._unwrap_message_replied_event(event)
        logger.debug(f"[slack] RawMessage {event}")
        abm = AstrBotMessage()
        abm.self_id = self.bot_self_id
        user_id = event.get("user", "")
        try:
            user_info = await self.web_client.users_info(user=user_id)
            user_data = user_info["user"]
            user_name = user_data.get("real_name") or user_data.get("name", user_id)
        except Exception:
            user_name = user_id
        abm.sender = MessageMember(user_id=user_id, nickname=user_name)
        channel_id = event.get("channel", "")
        try:
            channel_info = await self.web_client.conversations_info(channel=channel_id)
            is_im = channel_info["channel"]["is_im"]
            if is_im:
                abm.type = MessageType.FRIEND_MESSAGE
            else:
                abm.type = MessageType.GROUP_MESSAGE
                abm.group_id = channel_id
        except Exception:
            abm.type = MessageType.GROUP_MESSAGE
            abm.group_id = channel_id
        thread_ts = event.get("thread_ts")
        if abm.type == MessageType.GROUP_MESSAGE:
            base_session_id = abm.group_id
        else:
            base_session_id = channel_id or user_id
        abm.session_id = (
            encode_thread_session_id(base_session_id, str(thread_ts))
            if thread_ts
            else base_session_id
        )
        abm.message_id = event.get("client_msg_id", uuid.uuid4().hex)
        abm.timestamp = int(float(event.get("ts", time.time())))
        message_text = event.get("text", "")
        abm.message_str = message_text
        abm.message = []
        if event.get("blocks"):
            abm.message = self._parse_blocks(event["blocks"])
            abm.message_str = ""
            for component in abm.message:
                if isinstance(component, Plain):
                    abm.message_str += component.text
        elif message_text:
            if "<@" in message_text:
                mentions = re.findall("<@([^>]+)>", message_text)
                for mention in mentions:
                    try:
                        mentioned_user = await self.web_client.users_info(user=mention)
                        user_data = mentioned_user["user"]
                        user_name = user_data.get("real_name") or user_data.get(
                            "name",
                            mention,
                        )
                        abm.message.append(At(qq=mention, name=user_name))
                    except Exception:
                        abm.message.append(At(qq=mention, name=""))
                if clean_text := re.sub("<@[^>]+>", "", message_text).strip():
                    abm.message.append(Plain(text=clean_text))
            else:
                abm.message.append(Plain(text=message_text))
        if "files" in event:
            for file_info in event["files"]:
                file_name = file_info.get("name", "unknown")
                file_url = file_info.get("url_private", "")
                if file_info.get("mimetype", "").startswith("image/"):
                    file_url = await self.get_file_base64(file_url)
                    abm.message.append(Image.fromBase64(base64=file_url))
                else:
                    abm.message.append(
                        File(name=file_name, file=file_url, url=file_url),
                    )
        abm.raw_message = event
        return abm

    def _parse_blocks(self, blocks: list) -> list:
        """解析 Slack blocks 格式的消息内容"""
        message_components = []
        for block in blocks:
            block_type = block.get("type", "")
            if block_type == "rich_text":
                elements = block.get("elements", [])
                for element in elements:
                    if element.get("type") == "rich_text_section":
                        section_elements = element.get("elements", [])
                        text_parts = []
                        for section_element in section_elements:
                            element_type = section_element.get("type", "")
                            if element_type == "text":
                                text_parts.append(section_element.get("text", ""))
                            elif element_type == "user":
                                user_id = section_element.get("user_id", "")
                                if user_id:
                                    text_content = "".join(text_parts)
                                    if text_content.strip():
                                        message_components.append(
                                            Plain(text=text_content),
                                        )
                                    text_parts = []
                                    message_components.append(At(qq=user_id, name=""))
                            elif element_type == "channel":
                                channel_id = section_element.get("channel_id", "")
                                text_parts.append(f"#{channel_id}")
                            elif element_type == "link":
                                url = section_element.get("url", "")
                                link_text = section_element.get("text", url)
                                text_parts.append(f"[{link_text}]({url})")
                            elif element_type == "emoji":
                                emoji_name = section_element.get("name", "")
                                text_parts.append(f":{emoji_name}:")
                        text_content = "".join(text_parts)
                        if text_content.strip():
                            message_components.append(Plain(text=text_content))
                    elif element.get("type") == "rich_text_list":
                        list_items = element.get("elements", [])
                        list_text = ""
                        for item in list_items:
                            if item.get("type") == "rich_text_section":
                                item_elements = item.get("elements", [])
                                item_text = ""
                                for item_element in item_elements:
                                    if item_element.get("type") == "text":
                                        item_text += item_element.get("text", "")
                                list_text += f"• {item_text}\n"
                        if list_text.strip():
                            message_components.append(Plain(text=list_text.strip()))
            elif block_type == "section":
                if "text" in block:
                    text_obj = block["text"]
                    if text_obj.get("type") == "mrkdwn":
                        text_content = text_obj.get("text", "")
                        message_components.append(Plain(text=text_content))
        return message_components

    async def _handle_socket_event(self, req: SocketModeRequest) -> None:
        """处理 Socket Mode 事件"""
        if req.type == "events_api":
            event = req.payload.get("event", {})
            if event.get("subtype") in [
                "bot_message",
                "message_changed",
                "message_deleted",
            ]:
                return
            if event.get("bot_id"):
                return
            if event.get("type") in ["message", "app_mention"]:
                abm = await self.convert_message(event)
                if abm:
                    await self.handle_msg(abm)

    async def get_bot_user_id(self):
        auth_info = await self.web_client.auth_test()
        return auth_info.get("user_id")

    async def get_file_base64(self, url: str) -> str:
        """下载 Slack 文件并返回 Base64 编码的内容"""
        headers = {"Authorization": f"Bearer {self.bot_token}"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    content = await resp.read()
                    base64_content = base64.b64encode(content).decode("utf-8")
                    return base64_content
                logger.error(
                    f"Failed to download slack file: {resp.status} {await resp.text()}",
                )
                raise Exception(f"下载文件失败: {resp.status}")

    async def run(self) -> None:
        self.bot_self_id = await self.get_bot_user_id()
        logger.info(f"Slack auth test OK. Bot ID: {self.bot_self_id}")
        if self.connection_mode == "socket":
            if not self.app_token:
                raise ValueError("Socket Mode 需要 app_token")
            self.socket_client = SlackSocketClient(
                self.web_client,
                self.app_token,
                self._handle_socket_event,
            )
            logger.info("Slack 适配器 (Socket Mode) 启动中...")
            await self.socket_client.start()
        elif self.connection_mode == "webhook":
            if not self.signing_secret:
                raise ValueError("Webhook Mode 需要 signing_secret")
            self.webhook_client = SlackWebhookClient(
                self.web_client,
                self.signing_secret,
                self.webhook_host,
                self.webhook_port,
                self.webhook_path,
                self._handle_webhook_event,
            )
            webhook_uuid = self.config.get("webhook_uuid")
            if self.unified_webhook_mode and webhook_uuid:
                log_webhook_info(f"{self.meta().id}(Slack)", webhook_uuid)
                await self.webhook_client.shutdown_event.wait()
            else:
                logger.info(
                    f"Slack 适配器 (Webhook Mode) 启动中,监听 {self.webhook_host}:{self.webhook_port}{self.webhook_path}...",
                )
                await self.webhook_client.start()
        else:
            raise ValueError(
                f"不支持的连接模式: {self.connection_mode},请使用 'socket' 或 'webhook'",
            )

    async def _handle_webhook_event(self, event_data: dict) -> None:
        """处理 Webhook 事件"""
        event = event_data.get("event", {})
        if event.get("subtype") in [
            "bot_message",
            "message_changed",
            "message_deleted",
        ]:
            return
        if event.get("bot_id"):
            return
        if event.get("type") in ["message", "app_mention"]:
            abm = await self.convert_message(event)
            if abm:
                await self.handle_msg(abm)

    async def webhook_callback(self, request: Any) -> Any:
        """统一 Webhook 回调入口"""
        if self.connection_mode != "webhook" or not self.webhook_client:
            return ({"error": "Slack adapter is not in webhook mode"}, 400)
        return await self.webhook_client.handle_callback(request)

    async def terminate(self) -> None:
        if self.socket_client:
            await self.socket_client.stop()
        if self.webhook_client:
            await self.webhook_client.stop()
        logger.info("Slack 适配器已被关闭")

    def meta(self) -> PlatformMetadata:
        return self.metadata

    async def handle_msg(self, message: AstrBotMessage) -> None:
        message_event = SlackMessageEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            web_client=self.web_client,
            text_fallbacks=self.text_fallbacks,
        )
        self.commit_event(message_event)

    def get_client(self):
        return self.web_client

    def unified_webhook(self) -> bool:
        return bool(
            self.config.get("unified_webhook_mode", False)
            and self.config.get("slack_connection_mode", "") == "webhook"
            and self.config.get("webhook_uuid"),
        )
