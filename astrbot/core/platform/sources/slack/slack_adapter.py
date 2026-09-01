import asyncio
import base64
import re
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

import aiohttp
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.web.async_client import AsyncWebClient

from astrbot import logger
from astrbot.core.message.components import *
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform import (
    AstrBotMessage,
    Group,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
)
from astrbot.core.platform.astr_message_event import MessageSession
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.webhook_utils import log_webhook_info

from ...register import register_platform_adapter
from .client import SlackSocketClient, SlackWebhookClient
from .slack_event import SlackMessageEvent

# Slack private-file downloads are capped so large PDFs/zips are neither
# fully buffered nor written as a successful File payload.
_SLACK_FILE_MAX_BYTES = 32 * 1024 * 1024


def _slack_declared_size_exceeds_limit(resp: aiohttp.ClientResponse) -> bool:
    content_length = resp.headers.get("Content-Length")
    if not content_length:
        return False
    try:
        return int(content_length) > _SLACK_FILE_MAX_BYTES
    except ValueError:
        return False


@register_platform_adapter(
    "slack",
    "适用于 Slack 的消息平台适配器，支持 Socket Mode 和 Webhook Mode。",
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
        self.webhook_host = platform_config.get("slack_webhook_host", "127.0.0.1")
        self.webhook_port = platform_config.get("slack_webhook_port", 3000)
        self.webhook_path = platform_config.get(
            "slack_webhook_path",
            "/astrbot-slack-webhook/callback",
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
            id=cast(str, self.config.get("id")),
            support_streaming_message=False,
        )

        # 初始化 Slack Web Client
        self.web_client = AsyncWebClient(token=self.bot_token, logger=logger)
        self.socket_client = None
        self.webhook_client = None

        self.bot_self_id = None

    async def send_by_session(
        self,
        session: MessageSession,
        message_chain: MessageChain,
    ):
        blocks, text = await SlackMessageEvent._parse_slack_blocks(
            message_chain=message_chain,
            web_client=self.web_client,
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

        return await super().send_by_session(session, message_chain)

    async def convert_message(self, event: dict) -> AstrBotMessage:
        logger.debug(f"[slack] RawMessage {event}")

        abm = AstrBotMessage()
        abm.self_id = cast(str, self.bot_self_id)

        user_id = str(event.get("user", "")).strip()
        channel_id = str(event.get("channel", "")).strip()
        abm.sender = MessageMember(user_id=user_id, nickname=user_id)

        if channel_id.startswith("D"):
            abm.type = MessageType.FRIEND_MESSAGE
        else:
            abm.type = MessageType.GROUP_MESSAGE
            abm.group = Group(group_id=channel_id)

        # 设置会话ID
        if abm.type == MessageType.GROUP_MESSAGE:
            abm.session_id = abm.group_id
        else:
            abm.session_id = user_id

        abm.message_id = event.get("client_msg_id", uuid.uuid4().hex)
        abm.timestamp = int(float(event.get("ts", time.time())))

        # 处理消息内容
        message_text = event.get("text", "")
        abm.message_str = message_text
        abm.message = []

        # 优先使用 blocks 字段解析消息
        if event.get("blocks"):
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
                    image = Image(file="")
                    image.set_source_resolver(
                        lambda file_url=file_url: self._resolve_slack_image_source(
                            file_url
                        )
                    )
                    abm.message.append(image)
                else:
                    file_component = File(name=file_name)
                    file_component.set_file_resolver(
                        lambda file_url=file_url, file_name=file_name: (
                            self._resolve_slack_file(
                                file_url,
                                file_name,
                            )
                        )
                    )
                    abm.message.append(file_component)

        abm.raw_message = event
        return abm

    async def _resolve_slack_image_source(self, url: str) -> str | None:
        if not url:
            return None
        file_base64 = await self.get_file_base64(url)
        return f"base64://{file_base64}"

    async def _resolve_slack_file(self, url: str, file_name: str) -> str | None:
        """Download a Slack non-image file to a temp path with Bearer auth.

        Args:
            url: Slack `url_private`. Not stored on File.url.
            file_name: Original filename, used only for the temp suffix.

        Returns:
            Local path on success, or None if the request fails or exceeds
            the 32 MiB cap. Partial files are deleted.
        """
        if not url:
            return None
        temp_dir = Path(get_astrbot_temp_path())
        temp_dir.mkdir(parents=True, exist_ok=True)
        dest_path = temp_dir / f"slack_{uuid.uuid4().hex}{Path(file_name).suffix}"
        completed = False
        try:
            async with self._slack_private_request(url) as resp:
                if resp.status != 200:
                    logger.error(
                        "Failed to download slack file: %s %s",
                        resp.status,
                        await resp.text(),
                    )
                    return None
                if _slack_declared_size_exceeds_limit(resp):
                    logger.warning(
                        "Rejecting Slack file over %s bytes",
                        _SLACK_FILE_MAX_BYTES,
                    )
                    return None
                written = 0
                with dest_path.open("wb") as handle:
                    async for chunk in resp.content.iter_chunked(8192):
                        written += len(chunk)
                        if written > _SLACK_FILE_MAX_BYTES:
                            logger.warning(
                                "Rejecting Slack file over %s bytes",
                                _SLACK_FILE_MAX_BYTES,
                            )
                            return None
                        handle.write(chunk)
                completed = True
                return str(dest_path)
        except Exception:
            logger.exception("Slack file download failed")
            return None
        finally:
            if not completed and dest_path.exists():
                dest_path.unlink(missing_ok=True)

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
                        text_parts = []
                        for section_element in section_elements:
                            element_type = section_element.get("type", "")

                            if element_type == "text":
                                # 普通文本
                                text_parts.append(section_element.get("text", ""))
                            elif element_type == "user":
                                # @用户提及
                                user_id = section_element.get("user_id", "")
                                if user_id:
                                    # 将之前的文本内容先添加到组件中
                                    text_content = "".join(text_parts)
                                    if text_content.strip():
                                        message_components.append(
                                            Plain(text=text_content),
                                        )
                                    text_parts = []
                                    # 添加@提及组件
                                    message_components.append(At(qq=user_id, name=""))
                            elif element_type == "channel":
                                # #频道提及
                                channel_id = section_element.get("channel_id", "")
                                text_parts.append(f"#{channel_id}")
                            elif element_type == "link":
                                # 链接
                                url = section_element.get("url", "")
                                link_text = section_element.get("text", url)
                                text_parts.append(f"[{link_text}]({url})")
                            elif element_type == "emoji":
                                # 表情符号
                                emoji_name = section_element.get("name", "")
                                text_parts.append(f":{emoji_name}:")

                        text_content = "".join(text_parts)

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

    async def _handle_socket_event(self, req: SocketModeRequest) -> None:
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

    @asynccontextmanager
    async def _slack_private_request(
        self, url: str
    ) -> AsyncIterator[aiohttp.ClientResponse]:
        """GET a Slack private file URL with Bearer authentication.

        Args:
            url: Slack `url_private`.

        Yields:
            The HTTP response. The caller must consume the body before
            leaving the context.
        """
        headers = {"Authorization": f"Bearer {self.bot_token}"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                yield resp

    async def get_file_base64(self, url: str) -> str:
        """下载 Slack 文件并返回 Base64 编码的内容"""
        async with self._slack_private_request(url) as resp:
            if resp.status != 200:
                logger.error(
                    "Failed to download slack file: %s %s",
                    resp.status,
                    await resp.text(),
                )
                raise Exception(f"下载文件失败: {resp.status}")
            if _slack_declared_size_exceeds_limit(resp):
                logger.warning(
                    "Rejecting Slack file over %s bytes",
                    _SLACK_FILE_MAX_BYTES,
                )
                raise Exception("下载文件失败: size limit exceeded")
            content = await resp.read()
            if len(content) > _SLACK_FILE_MAX_BYTES:
                logger.warning(
                    "Rejecting Slack file over %s bytes",
                    _SLACK_FILE_MAX_BYTES,
                )
                raise Exception("下载文件失败: size limit exceeded")
            return base64.b64encode(content).decode("utf-8")

    async def run(self) -> None:
        self.bot_self_id = await self.get_bot_user_id()
        logger.info(f"Slack auth test OK. Bot ID: {self.bot_self_id}")

        if self.connection_mode == "socket":
            if not self.app_token:
                raise ValueError("Socket Mode 需要 app_token")

            # 创建 Socket 客户端
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

            # 创建 Webhook 客户端
            self.webhook_client = SlackWebhookClient(
                self.web_client,
                self.signing_secret,
                self.webhook_host,
                self.webhook_port,
                self.webhook_path,
                self._handle_webhook_event,
            )

            # 如果启用统一 webhook 模式，则不启动独立服务器
            webhook_uuid = self.config.get("webhook_uuid")
            if self.unified_webhook_mode and webhook_uuid:
                log_webhook_info(f"{self.meta().id}(Slack)", webhook_uuid)
                # 保持运行状态，等待 shutdown
                await self.webhook_client.shutdown_event.wait()
            else:
                logger.info(
                    f"Slack 适配器 (Webhook Mode) 启动中，监听 {self.webhook_host}:{self.webhook_port}{self.webhook_path}...",
                )
                await self.webhook_client.start()

        else:
            raise ValueError(
                f"不支持的连接模式: {self.connection_mode}，请使用 'socket' 或 'webhook'",
            )

    async def _handle_webhook_event(self, event_data: dict) -> None:
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

    async def webhook_callback(self, request: Any) -> Any:
        """统一 Webhook 回调入口"""
        if self.connection_mode != "webhook" or not self.webhook_client:
            return {"error": "Slack adapter is not in webhook mode"}, 400

        return await self.webhook_client.handle_callback(request)

    async def terminate(self) -> None:
        if self.socket_client:
            await self.socket_client.stop()
        if self.webhook_client:
            await self.webhook_client.stop()
        logger.info("Slack 适配器已被关闭")

    def meta(self) -> PlatformMetadata:
        return self.metadata

    def create_event(self, message: AstrBotMessage) -> SlackMessageEvent:
        """Creates a Slack message event.

        Args:
            message: AstrBot message object to wrap.

        Returns:
            Created Slack message event.
        """
        return SlackMessageEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            web_client=self.web_client,
        )

    async def handle_msg(self, message: AstrBotMessage) -> None:
        self.commit_event(self.create_event(message))

    def unified_webhook(self) -> bool:
        return bool(
            self.config.get("unified_webhook_mode", False)
            and self.config.get("slack_connection_mode", "") == "webhook"
            and self.config.get("webhook_uuid")
        )
