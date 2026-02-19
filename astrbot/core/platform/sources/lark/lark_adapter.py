import asyncio
import base64
import json
import re
import time
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    GetMessageRequest,
    GetMessageResourceRequest,
)
from lark_oapi.api.im.v1.processor import P2ImMessageReceiveV1Processor

import astrbot.api.message_components as Comp
from astrbot import logger
from astrbot.api.event import MessageChain
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
)
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.webhook_utils import log_webhook_info

from ...register import register_platform_adapter
from .lark_event import LarkMessageEvent
from .server import LarkWebhookServer


@register_platform_adapter(
    "lark", "飞书机器人官方 API 适配器", support_streaming_message=False
)
class LarkPlatformAdapter(Platform):
    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)

        self.appid = platform_config["app_id"]
        self.appsecret = platform_config["app_secret"]
        self.domain = platform_config.get("domain", lark.FEISHU_DOMAIN)
        self.bot_name = platform_config.get("lark_bot_name", "astrbot")

        # socket or webhook
        self.connection_mode = platform_config.get("lark_connection_mode", "socket")

        if not self.bot_name:
            logger.warning("未设置飞书机器人名称，@ 机器人可能得不到回复。")

        # 初始化 WebSocket 长连接相关配置
        async def on_msg_event_recv(event: lark.im.v1.P2ImMessageReceiveV1) -> None:
            await self.convert_msg(event)

        def do_v2_msg_event(event: lark.im.v1.P2ImMessageReceiveV1) -> None:
            asyncio.create_task(on_msg_event_recv(event))

        self.event_handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(do_v2_msg_event)
            .build()
        )

        self.do_v2_msg_event = do_v2_msg_event

        self.client = lark.ws.Client(
            app_id=self.appid,
            app_secret=self.appsecret,
            log_level=lark.LogLevel.ERROR,
            domain=self.domain,
            event_handler=self.event_handler,
        )

        self.lark_api = (
            lark.Client.builder()
            .app_id(self.appid)
            .app_secret(self.appsecret)
            .log_level(lark.LogLevel.ERROR)
            .domain(self.domain)
            .build()
        )

        self.webhook_server = None
        if self.connection_mode == "webhook":
            self.webhook_server = LarkWebhookServer(platform_config, event_queue)
            self.webhook_server.set_callback(self.handle_webhook_event)

        self.event_id_timestamps: dict[str, float] = {}

    async def _download_message_resource(
        self,
        *,
        message_id: str,
        file_key: str,
        resource_type: str,
    ) -> bytes | None:
        if self.lark_api.im is None:
            logger.error("[Lark] API Client im 模块未初始化")
            return None

        request = (
            GetMessageResourceRequest.builder()
            .message_id(message_id)
            .file_key(file_key)
            .type(resource_type)
            .build()
        )
        response = await self.lark_api.im.v1.message_resource.aget(request)
        if not response.success():
            logger.error(
                f"[Lark] 下载消息资源失败 type={resource_type}, key={file_key}, "
                f"code={response.code}, msg={response.msg}",
            )
            return None

        if response.file is None:
            logger.error(f"[Lark] 消息资源响应中不包含文件流: {file_key}")
            return None

        return response.file.read()

    @staticmethod
    def _build_message_str_from_components(
        components: list[Comp.BaseMessageComponent],
    ) -> str:
        parts: list[str] = []
        for comp in components:
            if isinstance(comp, Comp.Plain):
                text = comp.text.strip()
                if text:
                    parts.append(text)
            elif isinstance(comp, Comp.At):
                name = str(comp.name or comp.qq or "").strip()
                if name:
                    parts.append(f"@{name}")
            elif isinstance(comp, Comp.Image):
                parts.append("[image]")
            elif isinstance(comp, Comp.File):
                parts.append(str(comp.name or "[file]"))
            elif isinstance(comp, Comp.Record):
                parts.append("[audio]")
            elif isinstance(comp, Comp.Video):
                parts.append("[video]")

        return " ".join(parts).strip()

    @staticmethod
    def _parse_post_content(content: dict[str, Any]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for item in content.get("content", []):
            if isinstance(item, list):
                for comp in item:
                    if isinstance(comp, dict):
                        result.append(comp)
            elif isinstance(item, dict):
                result.append(item)
        return result

    @staticmethod
    def _build_at_map(mentions: list[Any] | None) -> dict[str, Comp.At]:
        at_map: dict[str, Comp.At] = {}
        if not mentions:
            return at_map

        for mention in mentions:
            key = getattr(mention, "key", None)
            if not key:
                continue

            mention_id = getattr(mention, "id", None)
            open_id = ""
            if mention_id is not None:
                if hasattr(mention_id, "open_id"):
                    open_id = getattr(mention_id, "open_id", "") or ""
                else:
                    open_id = str(mention_id)

            mention_name = str(getattr(mention, "name", "") or "")
            at_map[key] = Comp.At(qq=open_id, name=mention_name)

        return at_map

    async def _parse_message_components(
        self,
        *,
        message_id: str | None,
        message_type: str,
        content: dict[str, Any],
        at_map: dict[str, Comp.At],
    ) -> list[Comp.BaseMessageComponent]:
        components: list[Comp.BaseMessageComponent] = []

        if message_type == "text":
            message_str_raw = str(content.get("text", ""))
            at_pattern = r"(@_user_\d+)"
            parts = re.split(at_pattern, message_str_raw)
            for part in parts:
                segment = part.strip()
                if not segment:
                    continue
                if segment in at_map:
                    components.append(at_map[segment])
                else:
                    components.append(Comp.Plain(segment))
            return components

        if message_type in ("post", "image"):
            if message_type == "image":
                comp_list = [
                    {
                        "tag": "img",
                        "image_key": content.get("image_key"),
                    },
                ]
            else:
                comp_list = self._parse_post_content(content)

            for comp in comp_list:
                tag = comp.get("tag")
                if tag == "at":
                    user_key = str(comp.get("user_id", ""))
                    if user_key in at_map:
                        components.append(at_map[user_key])
                elif tag == "text":
                    text = str(comp.get("text", "")).strip()
                    if text:
                        components.append(Comp.Plain(text))
                elif tag == "a":
                    text = str(comp.get("text", "")).strip()
                    href = str(comp.get("href", "")).strip()
                    if text and href:
                        components.append(Comp.Plain(f"{text}({href})"))
                    elif text:
                        components.append(Comp.Plain(text))
                elif tag == "img":
                    image_key = str(comp.get("image_key", "")).strip()
                    if not image_key:
                        continue
                    if not message_id:
                        logger.error("[Lark] 图片消息缺少 message_id")
                        continue
                    image_bytes = await self._download_message_resource(
                        message_id=message_id,
                        file_key=image_key,
                        resource_type="image",
                    )
                    if image_bytes is None:
                        continue
                    image_base64 = base64.b64encode(image_bytes).decode()
                    components.append(Comp.Image.fromBase64(image_base64))
                elif tag == "media":
                    file_key = str(comp.get("file_key", "")).strip()
                    file_name = (
                        str(comp.get("file_name", "")).strip() or "lark_media.mp4"
                    )
                    if not file_key:
                        continue
                    if not message_id:
                        logger.error("[Lark] 富文本视频消息缺少 message_id")
                        continue
                    file_path = await self._download_file_resource_to_temp(
                        message_id=message_id,
                        file_key=file_key,
                        message_type="post_media",
                        file_name=file_name,
                        default_suffix=".mp4",
                    )
                    if file_path:
                        components.append(Comp.Video(file=file_path, path=file_path))

            return components

        if message_type == "file":
            file_key = str(content.get("file_key", "")).strip()
            file_name = str(content.get("file_name", "")).strip() or "lark_file"
            if not message_id:
                logger.error("[Lark] 文件消息缺少 message_id")
                return components
            if not file_key:
                logger.error("[Lark] 文件消息缺少 file_key")
                return components
            file_path = await self._download_file_resource_to_temp(
                message_id=message_id,
                file_key=file_key,
                message_type="file",
                file_name=file_name,
            )
            if file_path:
                components.append(Comp.File(name=file_name, file=file_path))
            return components

        if message_type == "audio":
            file_key = str(content.get("file_key", "")).strip()
            if not message_id:
                logger.error("[Lark] 音频消息缺少 message_id")
                return components
            if not file_key:
                logger.error("[Lark] 音频消息缺少 file_key")
                return components
            file_path = await self._download_file_resource_to_temp(
                message_id=message_id,
                file_key=file_key,
                message_type="audio",
                default_suffix=".opus",
            )
            if file_path:
                components.append(Comp.Record(file=file_path, url=file_path))
            return components

        if message_type == "media":
            file_key = str(content.get("file_key", "")).strip()
            file_name = str(content.get("file_name", "")).strip() or "lark_media.mp4"
            if not message_id:
                logger.error("[Lark] 视频消息缺少 message_id")
                return components
            if not file_key:
                logger.error("[Lark] 视频消息缺少 file_key")
                return components
            file_path = await self._download_file_resource_to_temp(
                message_id=message_id,
                file_key=file_key,
                message_type="media",
                file_name=file_name,
                default_suffix=".mp4",
            )
            if file_path:
                components.append(Comp.Video(file=file_path, path=file_path))
            return components

        return components

    async def _build_reply_from_parent_id(
        self,
        parent_message_id: str,
    ) -> Comp.Reply | None:
        if self.lark_api.im is None:
            logger.error("[Lark] API Client im 模块未初始化")
            return None

        request = GetMessageRequest.builder().message_id(parent_message_id).build()
        response = await self.lark_api.im.v1.message.aget(request)
        if not response.success():
            logger.error(
                f"[Lark] 获取引用消息失败 id={parent_message_id}, "
                f"code={response.code}, msg={response.msg}",
            )
            return None

        if response.data is None or not response.data.items:
            logger.error(
                f"[Lark] 引用消息响应为空 id={parent_message_id}",
            )
            return None

        parent_message = response.data.items[0]
        quoted_message_id = parent_message.message_id or parent_message_id
        quoted_sender_id = (
            parent_message.sender.id
            if parent_message.sender and parent_message.sender.id
            else "unknown"
        )
        quoted_time_raw = parent_message.create_time or 0
        quoted_time = (
            quoted_time_raw // 1000
            if isinstance(quoted_time_raw, int) and quoted_time_raw > 10**11
            else quoted_time_raw
        )
        quoted_content = (
            parent_message.body.content if parent_message.body else ""
        ) or ""
        quoted_type = parent_message.msg_type or ""
        quoted_content_json: dict[str, Any] = {}
        if quoted_content:
            try:
                parsed = json.loads(quoted_content)
                if isinstance(parsed, dict):
                    quoted_content_json = parsed
            except json.JSONDecodeError:
                logger.warning(
                    f"[Lark] 解析引用消息内容失败 id={quoted_message_id}",
                )

        quoted_at_map = self._build_at_map(parent_message.mentions)
        quoted_chain = await self._parse_message_components(
            message_id=quoted_message_id,
            message_type=quoted_type,
            content=quoted_content_json,
            at_map=quoted_at_map,
        )
        quoted_text = self._build_message_str_from_components(quoted_chain)
        sender_nickname = (
            quoted_sender_id[:8] if quoted_sender_id != "unknown" else "unknown"
        )

        return Comp.Reply(
            id=quoted_message_id,
            chain=quoted_chain,
            sender_id=quoted_sender_id,
            sender_nickname=sender_nickname,
            time=quoted_time,
            message_str=quoted_text,
            text=quoted_text,
        )

    async def _download_file_resource_to_temp(
        self,
        *,
        message_id: str,
        file_key: str,
        message_type: str,
        file_name: str = "",
        default_suffix: str = ".bin",
    ) -> str | None:
        file_bytes = await self._download_message_resource(
            message_id=message_id,
            file_key=file_key,
            resource_type="file",
        )
        if file_bytes is None:
            return None

        suffix = Path(file_name).suffix if file_name else default_suffix
        temp_dir = Path(get_astrbot_temp_path())
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = (
            temp_dir / f"lark_{message_type}_{file_name}_{uuid4().hex[:4]}{suffix}"
        )
        temp_path.write_bytes(file_bytes)
        return str(temp_path.resolve())

    def _clean_expired_events(self) -> None:
        """清理超过 30 分钟的事件记录"""
        current_time = time.time()
        expired_keys = [
            event_id
            for event_id, timestamp in self.event_id_timestamps.items()
            if current_time - timestamp > 1800
        ]
        for event_id in expired_keys:
            del self.event_id_timestamps[event_id]

    def _is_duplicate_event(self, event_id: str) -> bool:
        """检查事件是否重复

        Args:
            event_id: 事件ID

        Returns:
            True 表示重复事件，False 表示新事件
        """
        self._clean_expired_events()
        if event_id in self.event_id_timestamps:
            return True
        self.event_id_timestamps[event_id] = time.time()
        return False

    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ) -> None:
        if session.message_type == MessageType.GROUP_MESSAGE:
            id_type = "chat_id"
            receive_id = session.session_id
            if "%" in receive_id:
                receive_id = receive_id.split("%")[1]
        else:
            id_type = "open_id"
            receive_id = session.session_id

        # 复用 LarkMessageEvent 中的通用发送逻辑
        await LarkMessageEvent.send_message_chain(
            message_chain,
            self.lark_api,
            receive_id=receive_id,
            receive_id_type=id_type,
        )

        await super().send_by_session(session, message_chain)

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="lark",
            description="飞书机器人官方 API 适配器",
            id=cast(str, self.config.get("id")),
            support_streaming_message=False,
        )

    async def convert_msg(self, event: lark.im.v1.P2ImMessageReceiveV1) -> None:
        if event.event is None:
            logger.debug("[Lark] 收到空事件(event.event is None)")
            return
        message = event.event.message
        if message is None:
            logger.debug("[Lark] 事件中没有消息体(message is None)")
            return

        abm = AstrBotMessage()

        if message.create_time:
            abm.timestamp = int(message.create_time) // 1000
        else:
            abm.timestamp = int(time.time())
        abm.message = []
        abm.type = (
            MessageType.GROUP_MESSAGE
            if message.chat_type == "group"
            else MessageType.FRIEND_MESSAGE
        )
        if message.chat_type == "group":
            abm.group_id = message.chat_id
        abm.self_id = self.bot_name
        abm.message_str = ""

        at_list = {}
        if message.parent_id:
            reply_seg = await self._build_reply_from_parent_id(message.parent_id)
            if reply_seg:
                abm.message.append(reply_seg)

        if message.mentions:
            for m in message.mentions:
                if m.id is None:
                    continue
                # 飞书 open_id 可能是 None，这里做个防护
                open_id = m.id.open_id if m.id.open_id else ""
                at_list[m.key] = Comp.At(qq=open_id, name=m.name)

                if m.name == self.bot_name:
                    if m.id.open_id is not None:
                        abm.self_id = m.id.open_id

        if message.content is None:
            logger.warning("[Lark] 消息内容为空")
            return

        try:
            content_json_b = json.loads(message.content)
        except json.JSONDecodeError:
            logger.error(f"[Lark] 解析消息内容失败: {message.content}")
            return

        if not isinstance(content_json_b, dict):
            logger.error(f"[Lark] 消息内容不是 JSON Object: {message.content}")
            return

        logger.debug(f"[Lark] 解析消息内容: {content_json_b}")
        parsed_components = await self._parse_message_components(
            message_id=message.message_id,
            message_type=message.message_type or "unknown",
            content=content_json_b,
            at_map=at_list,
        )
        abm.message.extend(parsed_components)
        abm.message_str = self._build_message_str_from_components(parsed_components)

        if message.message_id is None:
            logger.error("[Lark] 消息缺少 message_id")
            return

        if (
            event.event.sender is None
            or event.event.sender.sender_id is None
            or event.event.sender.sender_id.open_id is None
        ):
            logger.error("[Lark] 消息发送者信息不完整")
            return

        abm.message_id = message.message_id
        abm.raw_message = message
        abm.sender = MessageMember(
            user_id=event.event.sender.sender_id.open_id,
            nickname=event.event.sender.sender_id.open_id[:8],
        )
        if abm.type == MessageType.GROUP_MESSAGE:
            abm.session_id = abm.group_id
        else:
            abm.session_id = abm.sender.user_id

        await self.handle_msg(abm)

    async def handle_msg(self, abm: AstrBotMessage) -> None:
        event = LarkMessageEvent(
            message_str=abm.message_str,
            message_obj=abm,
            platform_meta=self.meta(),
            session_id=abm.session_id,
            bot=self.lark_api,
        )

        self._event_queue.put_nowait(event)

    async def handle_webhook_event(self, event_data: dict) -> None:
        """处理 Webhook 事件

        Args:
            event_data: Webhook 事件数据
        """
        try:
            header = event_data.get("header", {})
            event_id = header.get("event_id", "")
            if event_id and self._is_duplicate_event(event_id):
                logger.debug(f"[Lark Webhook] 跳过重复事件: {event_id}")
                return
            event_type = header.get("event_type", "")
            if event_type == "im.message.receive_v1":
                processor = P2ImMessageReceiveV1Processor(self.do_v2_msg_event)
                data = (processor.type())(event_data)
                processor.do(data)
            else:
                logger.debug(f"[Lark Webhook] 未处理的事件类型: {event_type}")
        except Exception as e:
            logger.error(f"[Lark Webhook] 处理事件失败: {e}", exc_info=True)

    async def run(self) -> None:
        if self.connection_mode == "webhook":
            # Webhook 模式
            if self.webhook_server is None:
                logger.error("[Lark] Webhook 模式已启用，但 webhook_server 未初始化")
                return

            webhook_uuid = self.config.get("webhook_uuid")
            if webhook_uuid:
                log_webhook_info(f"{self.meta().id}(飞书 Webhook)", webhook_uuid)
            else:
                logger.warning("[Lark] Webhook 模式已启用，但未配置 webhook_uuid")
        else:
            # 长连接模式
            await self.client._connect()

    async def webhook_callback(self, request: Any) -> Any:
        """统一 Webhook 回调入口"""
        if not self.webhook_server:
            return {"error": "Webhook server not initialized"}, 500

        return await self.webhook_server.handle_callback(request)

    async def terminate(self) -> None:
        if self.connection_mode == "socket":
            await self.client._disconnect()
        logger.info("飞书(Lark) 适配器已关闭")

    def get_client(self) -> lark.ws.Client:
        return self.client

    def unified_webhook(self) -> bool:
        return bool(
            self.config.get("lark_connection_mode", "") == "webhook"
            and self.config.get("webhook_uuid")
        )
