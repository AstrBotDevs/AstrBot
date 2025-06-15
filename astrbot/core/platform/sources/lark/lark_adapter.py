import base64
import asyncio
import json
import re
import uuid
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
from .lark_event import LarkMessageEvent
from ...register import register_platform_adapter
from astrbot import logger
import lark_oapi as lark
from lark_oapi.api.im.v1 import *


@register_platform_adapter("lark", "飞书机器人官方 API 适配器")
class LarkPlatformAdapter(Platform):
    def __init__(
        self, platform_config: dict, platform_settings: dict, event_queue: asyncio.Queue
    ) -> None:
        super().__init__(event_queue)

        self.config = platform_config

        self.unique_session = platform_settings["unique_session"]

        self.appid = platform_config["app_id"]
        self.appsecret = platform_config["app_secret"]
        self.domain = platform_config.get("domain", lark.FEISHU_DOMAIN)
        self.bot_name = platform_config.get("lark_bot_name", "astrbot")

        if not self.bot_name:
            logger.warning("未设置飞书机器人名称，@ 机器人可能得不到回复。")

        async def on_msg_event_recv(event: lark.im.v1.P2ImMessageReceiveV1):
            await self.convert_msg(event)

        def do_v2_msg_event(event: lark.im.v1.P2ImMessageReceiveV1):
            asyncio.create_task(on_msg_event_recv(event))

        self.event_handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(do_v2_msg_event)
            .build()
        )

        self.client = lark.ws.Client(
            app_id=self.appid,
            app_secret=self.appsecret,
            log_level=lark.LogLevel.ERROR,
            domain=self.domain,
            event_handler=self.event_handler,
        )

        self.lark_api = (
            lark.Client.builder().app_id(self.appid).app_secret(self.appsecret).build()
        )

    async def send_by_session(
        self, session: MessageSesion, message_chain: MessageChain
    ):
        res = await LarkMessageEvent._convert_to_lark(message_chain, self.lark_api)
        wrapped = {
            "zh_cn": {
                "title": "",
                "content": res,
            }
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
                .build()
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
            id=self.config.get("id"),
        )

    async def _send_thinking_message(self, message_id: str) -> tuple[bool, str]:
        """发送临时消息

        Args:
            message_id: 原始消息ID

        Returns:
            tuple[bool, str]: (是否成功, 临时消息ID)
        """
        temp_message = {
            "config": {"wide_screen_mode": True},
            "elements": [
                {
                    "tag": "div",
                    "text": {"content": "让我想一想哦🤔🤔...", "tag": "lark_md"},
                }
            ],
        }

        request = (
            ReplyMessageRequest.builder()
            .message_id(message_id)
            .request_body(
                ReplyMessageRequestBody.builder()
                .content(json.dumps(temp_message))
                .msg_type("interactive")
                .uuid(str(uuid.uuid4()))
                .reply_in_thread(False)
                .build()
            )
            .build()
        )

        response = await self.lark_api.im.v1.message.areply(request)
        if not response.success():
            logger.error(f"发送 thinking 消息失败({response.code}): {response.msg}")
            return False, ""

        return True, response.data.message_id

    async def convert_msg(self, event: lark.im.v1.P2ImMessageReceiveV1):
        message = event.event.message
        abm = AstrBotMessage()
        abm.timestamp = int(message.create_time) / 1000
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
        is_at_bot = False  # 标记是否@了机器人
        if message.mentions:
            for m in message.mentions:
                at_list[m.key] = Comp.At(qq=m.id.open_id, name=m.name)
                if m.name == self.bot_name:
                    abm.self_id = m.id.open_id
                    is_at_bot = True  # 标记@了机器人

        content_json_b = json.loads(message.content)

        if message.message_type == "text":
            message_str_raw = content_json_b["text"]  # 带有 @ 的消息
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
                {"tag": "img", "image_key": content_json_b["image_key"], "style": []}
            ]

        if message.message_type in ("post", "image"):
            for comp in content_json_b:
                if comp["tag"] == "at":
                    abm.message.append(at_list[comp["user_id"]])
                elif comp["tag"] == "text" and comp["text"].strip():
                    abm.message.append(Comp.Plain(comp["text"].strip()))
                elif comp["tag"] == "img":
                    image_key = comp["image_key"]
                    request = (
                        GetMessageResourceRequest.builder()
                        .message_id(message.message_id)
                        .file_key(image_key)
                        .type("image")
                        .build()
                    )
                    response = await self.lark_api.im.v1.message_resource.aget(request)
                    if not response.success():
                        logger.error(f"无法下载飞书图片: {image_key}")
                    image_bytes = response.file.read()
                    image_base64 = base64.b64encode(image_bytes).decode()
                    abm.message.append(Comp.Image.fromBase64(image_base64))

        for comp in abm.message:
            if isinstance(comp, Comp.Plain):
                abm.message_str += comp.text
        abm.message_id = message.message_id
        abm.raw_message = message
        abm.sender = MessageMember(
            user_id=event.event.sender.sender_id.open_id,
            nickname=event.event.sender.sender_id.open_id[:8],
        )
        # 独立会话
        if not self.unique_session:
            if abm.type == MessageType.GROUP_MESSAGE:
                abm.session_id = abm.group_id
            else:
                abm.session_id = abm.sender.user_id
        else:
            if abm.type == MessageType.GROUP_MESSAGE:
                abm.session_id = f"{abm.sender.user_id}%{abm.group_id}"  # 也保留群组id
            else:
                abm.session_id = abm.sender.user_id

        logger.debug(abm)

        # 创建事件对象
        event = LarkMessageEvent(
            message_str=abm.message_str,
            message_obj=abm,
            platform_meta=self.meta(),
            session_id=abm.session_id,
            bot=self.lark_api,
        )

        # 只有在私聊消息或者群聊中@了机器人的消息才发送 thinking 消息
        if abm.type == MessageType.FRIEND_MESSAGE or is_at_bot:
            success, thinking_message_id = await self._send_thinking_message(
                message.message_id
            )
            if success:
                event.thinking_message_id = thinking_message_id

        self._event_queue.put_nowait(event)

    async def handle_msg(self, abm: AstrBotMessage):
        event = LarkMessageEvent(
            message_str=abm.message_str,
            message_obj=abm,
            platform_meta=self.meta(),
            session_id=abm.session_id,
            bot=self.lark_api,
        )
        self._event_queue.put_nowait(event)

    async def run(self):
        # self.client.start()
        await self.client._connect()

    async def terminate(self):
        await self.client._disconnect()
        logger.info("飞书(Lark) 适配器已被优雅地关闭")

    def get_client(self) -> lark.Client:
        return self.client
