import time
import asyncio
import uuid
import aiohttp
import re
import base64
from typing import Awaitable, Any
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.socket_mode.request import SocketModeRequest
from astrbot.api.platform import (
    Platform,
    AstrBotMessage,
    MessageMember,
    MessageType,
    PlatformMetadata,
)
from astrbot.api.event import MessageChain
from .slack_event import SlackMessageEvent
from .client import SlackWebhookClient, SlackSocketClient
from astrbot.api.message_components import *  # noqa: F403
from astrbot.api import logger
from astrbot.core.platform.astr_message_event import MessageSesion
from ...register import register_platform_adapter


@register_platform_adapter(
    "slack", "适用于 Slack 的消息平台适配器，支持 Socket Mode 和 Webhook Mode。"
)
class SlackAdapter(Platform):
    def __init__(
        self, platform_config: dict, platform_settings: dict, event_queue: asyncio.Queue
    ) -> None:
        super().__init__(event_queue)

        self.config = platform_config
        self.settings = platform_settings
        self.unique_session = platform_settings.get("unique_session", False)

        self.bot_token = platform_config.get("bot_token")
        self.app_token = platform_config.get("app_token")
        self.signing_secret = platform_config.get("signing_secret")
        self.connection_mode = platform_config.get("slack_connection_mode", "socket")
        self.webhook_host = platform_config.get("slack_webhook_host", "0.0.0.0")
        self.webhook_port = platform_config.get("slack_webhook_port", 3000)
        self.webhook_path = platform_config.get(
            "slack_webhook_path", "/astrbot-slack-webhook/callback"
        )

        if not self.bot_token:
            raise ValueError("Slack bot_token 是必需的")

        if self.connection_mode == "socket" and not self.app_token:
            raise ValueError("Socket Mode 需要 app_token")

        if self.connection_mode == "webhook" and not self.signing_secret:
            raise ValueError("Webhook Mode 需要 signing_secret")

        self.metadata = PlatformMetadata(
            name="slack",
            description="适用于 Slack 的消息平台适配器，支持 Socket Mode 和 Webhook Mode。",
            id=self.config.get("id"),
        )

        # 初始化 Slack Web Client
        self.web_client = AsyncWebClient(token=self.bot_token, logger=logger)
        self.socket_client = None
        self.webhook_client = None

        self.bot_self_id = None

    async def send_by_session(
        self, session: MessageSesion, message_chain: MessageChain
    ):
        blocks, text = SlackMessageEvent._parse_slack_blocks(
            message_chain=message_chain, web_client=self.web_client
        )

        try:
            if session.message_type == MessageType.GROUP_MESSAGE:
                # 发送到频道
                channel_id = (
                    session.session_id.split("_")[-1]
                    if "_" in session.session_id
                    else session.session_id
                )
                await self.web_client.chat_postMessage(
                    channel=channel_id,
                    text=text,
                    blocks=blocks if blocks else None,
                )
            else:
                # 发送私信
                await self.web_client.chat_postMessage(
                    channel=session.session_id,
                    text=text,
                    blocks=blocks if blocks else None,
                )
        except Exception as e:
            logger.error(f"Slack 发送消息失败: {e}")

        await super().send_by_session(session, message_chain)

    async def convert_message(self, event: dict) -> AstrBotMessage:
        logger.debug(f"[slack] RawMessage {event}")

        abm = AstrBotMessage()
        abm.self_id = self.bot_self_id

        # 获取用户信息
        user_id = event.get("user", "")
        try:
            user_info = await self.web_client.users_info(user=user_id)
            user_data = user_info["user"]
            user_name = user_data.get("real_name") or user_data.get("name", user_id)
        except Exception:
            user_name = user_id

        abm.sender = MessageMember(user_id=user_id, nickname=user_name)

        # 判断消息类型
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
            # 默认作为群组消息处理
            abm.type = MessageType.GROUP_MESSAGE
            abm.group_id = channel_id

        # 设置会话ID
        if self.unique_session and abm.type == MessageType.GROUP_MESSAGE:
            abm.session_id = f"{user_id}_{channel_id}"
        else:
            abm.session_id = (
                channel_id if abm.type == MessageType.GROUP_MESSAGE else user_id
            )

        abm.message_id = event.get("client_msg_id", uuid.uuid4().hex)
        abm.timestamp = int(float(event.get("ts", time.time())))

        # 处理消息内容
        message_text = event.get("text", "")
        abm.message_str = message_text
        abm.message = []

        # 优先使用 blocks 字段解析消息
        if "blocks" in event and event["blocks"]:
            abm.message = self._parse_blocks(event["blocks"])
            # 更新 message_str
            abm.message_str = ""
            for component in abm.message:
                if isinstance(component, Plain):
                    abm.message_str += component.text
        elif message_text:
            # 处理传统的文本消息
            if "<@" in message_text:
                mentions = re.findall(r"<@([^>]+)>", message_text)
                for mention in mentions:
                    try:
                        mentioned_user = await self.web_client.users_info(user=mention)
                        user_data = mentioned_user["user"]
                        user_name = user_data.get("real_name") or user_data.get(
                            "name", mention
                        )
                        abm.message.append(At(qq=mention, name=user_name))
                    except Exception:
                        abm.message.append(At(qq=mention, name=""))

                # 清理消息文本中的@标记
                if clean_text := re.sub(r"<@[^>]+>", "", message_text).strip():
                    abm.message.append(Plain(text=clean_text))
            else:
                abm.message.append(Plain(text=message_text))

        # 处理文件附件
        if "files" in event:
            for file_info in event["files"]:
                file_name = file_info.get("name", "unknown")
                file_url = file_info.get("url_private", "")
                if file_info.get("mimetype", "").startswith("image/"):
                    file_url = await self.get_file_base64(file_url)
                    abm.message.append(Image.fromBase64(base64=file_url))
                else:
                    # TODO: 下载鉴权
                    abm.message.append(
                        File(name=file_name, file=file_url, url=file_url)
                    )

        abm.raw_message = event
        return abm

    def _parse_blocks(self, blocks: list) -> list:
        """解析 Slack blocks 格式的消息内容"""
        message_components = []

        for block in blocks:
            block_type = block.get("type", "")

            if block_type == "rich_text":
                # 处理富文本块
                elements = block.get("elements", [])
                for element in elements:
                    if element.get("type") == "rich_text_section":
                        # 处理富文本段落
                        section_elements = element.get("elements", [])
                        text_content = ""

                        for section_element in section_elements:
                            element_type = section_element.get("type", "")

                            if element_type == "text":
                                # 普通文本
                                text_content += section_element.get("text", "")
                            elif element_type == "user":
                                # @用户提及
                                user_id = section_element.get("user_id", "")
                                if user_id:
                                    # 将之前的文本内容先添加到组件中
                                    if text_content.strip():
                                        message_components.append(
                                            Plain(text=text_content)
                                        )
                                        text_content = ""
                                    # 添加@提及组件
                                    message_components.append(At(qq=user_id, name=""))
                            elif element_type == "channel":
                                # #频道提及
                                channel_id = section_element.get("channel_id", "")
                                text_content += f"#{channel_id}"
                            elif element_type == "link":
                                # 链接
                                url = section_element.get("url", "")
                                link_text = section_element.get("text", url)
                                text_content += f"[{link_text}]({url})"
                            elif element_type == "emoji":
                                # 表情符号
                                emoji_name = section_element.get("name", "")
                                text_content += f":{emoji_name}:"

                        if text_content.strip():
                            message_components.append(Plain(text=text_content))

                    elif element.get("type") == "rich_text_list":
                        # 处理列表
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
                # 处理段落块
                if "text" in block:
                    text_obj = block["text"]
                    if text_obj.get("type") == "mrkdwn":
                        text_content = text_obj.get("text", "")
                        message_components.append(Plain(text=text_content))

        return message_components

    async def _handle_socket_event(self, req: SocketModeRequest):
        """处理 Socket Mode 事件"""
        if req.type == "events_api":
            # 事件 API
            event = req.payload.get("event", {})

            # 忽略机器人自己的消息和消息编辑
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
                else:
                    logger.error(f"Failed to download slack file: {resp.status} {await resp.text()}")
                    raise Exception(f"下载文件失败: {resp.status}")

    async def run(self) -> Awaitable[Any]:
        self.bot_self_id = await self.get_bot_user_id()
        logger.info(f"Slack auth test OK. Bot ID: {self.bot_self_id}")

        if self.connection_mode == "socket":
            if not self.app_token:
                raise ValueError("Socket Mode 需要 app_token")

            # 创建 Socket 客户端
            self.socket_client = SlackSocketClient(
                self.web_client, self.app_token, self._handle_socket_event
            )

            logger.info("Slack 适配器 (Socket Mode) 启动中...")
            await self.socket_client.start()

        elif self.connection_mode == "webhook":
            if not self.signing_secret:
                raise ValueError("Webhook Mode 需要 signing_secret")

            # 创建 Webhook 客户端
            self.webhook_client = SlackWebhookClient(
                self.web_client,
                self.signing_secret,
                self.webhook_host,
                self.webhook_port,
                self.webhook_path,
                self._handle_webhook_event,
            )

            logger.info(
                f"Slack 适配器 (Webhook Mode) 启动中，监听 {self.webhook_host}:{self.webhook_port}{self.webhook_path}..."
            )
            await self.webhook_client.start()

        else:
            raise ValueError(
                f"不支持的连接模式: {self.connection_mode}，请使用 'socket' 或 'webhook'"
            )

    async def _handle_webhook_event(self, event_data: dict):
        """处理 Webhook 事件"""
        event = event_data.get("event", {})

        # 忽略机器人自己的消息和消息编辑
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

    async def terminate(self):
        if self.socket_client:
            await self.socket_client.stop()
        if self.webhook_client:
            await self.webhook_client.stop()
        logger.info("Slack 适配器已被优雅地关闭")

    def meta(self) -> PlatformMetadata:
        return self.metadata

    async def handle_msg(self, message: AstrBotMessage):
        message_event = SlackMessageEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            web_client=self.web_client,
        )

        self.commit_event(message_event)

    def get_client(self):
        return self.web_client
