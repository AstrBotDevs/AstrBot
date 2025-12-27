import asyncio
import base64
import json
import re
import time
import uuid
from typing import Any, cast

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
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
        async def on_msg_event_recv(event: lark.im.v1.P2ImMessageReceiveV1):
            await self.convert_msg(event)

        def do_v2_msg_event(event: lark.im.v1.P2ImMessageReceiveV1):
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

    def _clean_expired_events(self):
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
    ):
        if self.lark_api.im is None:
            logger.error("[Lark] API Client im 模块未初始化，无法发送消息")
            return

        res = await LarkMessageEvent._convert_to_lark(message_chain, self.lark_api)
        wrapped = {
            "zh_cn": {
                "title": "",
                "content": res,
            },
        }

        if session.message_type == MessageType.GROUP_MESSAGE:
            id_type = "chat_id"
            if "%" in session.session_id:
                session.session_id = session.session_id.split("%")[1]
        else:
            id_type = "open_id"

        request = (
            CreateMessageRequest.builder()
            .receive_id_type(id_type)
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(session.session_id)
                .content(json.dumps(wrapped))
                .msg_type("post")
                .uuid(str(uuid.uuid4()))
                .build(),
            )
            .build()
        )

        response = await self.lark_api.im.v1.message.acreate(request)

        if not response.success():
            logger.error(f"发送飞书消息失败({response.code}): {response.msg}")

        await super().send_by_session(session, message_chain)

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="lark",
            description="飞书机器人官方 API 适配器",
            id=cast(str, self.config.get("id")),
            support_streaming_message=False,
        )

    async def convert_msg(self, event: lark.im.v1.P2ImMessageReceiveV1):
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

        if message.message_type == "text":
            message_str_raw = content_json_b.get("text", "")  # 带有 @ 的消息
            at_pattern = r"(@_user_\d+)"  # 可以根据需求修改正则
            # at_users = re.findall(at_pattern, message_str_raw)
            # 拆分文本，去掉AT符号部分
            parts = re.split(at_pattern, message_str_raw)
            for i in range(len(parts)):
                s = parts[i].strip()
                if not s:
                    continue
                if s in at_list:
                    abm.message.append(at_list[s])
                else:
                    abm.message.append(Comp.Plain(parts[i].strip()))
        elif message.message_type == "post":
            _ls = []

            content_ls = content_json_b.get("content", [])
            for comp in content_ls:
                if isinstance(comp, list):
                    _ls.extend(comp)
                elif isinstance(comp, dict):
                    _ls.append(comp)
            content_json_b = _ls
        elif message.message_type == "image":
            content_json_b = [
                {
                    "tag": "img",
                    "image_key": content_json_b.get("image_key"),
                    "style": [],
                },
            ]

        if message.message_type in ("post", "image"):
            for comp in content_json_b:
                if comp.get("tag") == "at":
                    user_id = comp.get("user_id")
                    if user_id in at_list:
                        abm.message.append(at_list[user_id])
                elif comp.get("tag") == "text" and comp.get("text", "").strip():
                    abm.message.append(Comp.Plain(comp["text"].strip()))
                elif comp.get("tag") == "img":
                    image_key = comp.get("image_key")
                    if not image_key:
                        continue

                    request = (
                        GetMessageResourceRequest.builder()
                        .message_id(cast(str, message.message_id))
                        .file_key(image_key)
                        .type("image")
                        .build()
                    )

                    if self.lark_api.im is None:
                        logger.error("[Lark] API Client im 模块未初始化")
                        continue

                    response = await self.lark_api.im.v1.message_resource.aget(request)
                    if not response.success():
                        logger.error(f"无法下载飞书图片: {image_key}")
                        continue

                    if response.file is None:
                        logger.error(f"飞书图片响应中不包含文件流: {image_key}")
                        continue

                    image_bytes = response.file.read()
                    image_base64 = base64.b64encode(image_bytes).decode()
                    abm.message.append(Comp.Image.fromBase64(image_base64))

        for comp in abm.message:
            if isinstance(comp, Comp.Plain):
                abm.message_str += comp.text

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

        logger.debug(abm)
        await self.handle_msg(abm)

    async def handle_msg(self, abm: AstrBotMessage):
        event = LarkMessageEvent(
            message_str=abm.message_str,
            message_obj=abm,
            platform_meta=self.meta(),
            session_id=abm.session_id,
            bot=self.lark_api,
        )

        self._event_queue.put_nowait(event)

    async def handle_webhook_event(self, event_data: dict):
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

    async def run(self):
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

    async def terminate(self):
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
