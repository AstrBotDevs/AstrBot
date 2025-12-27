import asyncio
import os
import threading
import uuid
from typing import cast

import aiohttp
import dingtalk_stream
from dingtalk_stream import AckMessage

from astrbot import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import At, Image, Plain
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
)
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.core.utils.io import download_file

from ...register import register_platform_adapter
from .dingtalk_event import DingtalkMessageEvent


class MyEventHandler(dingtalk_stream.EventHandler):
    async def process(self, event: dingtalk_stream.EventMessage):
        print(
            "2",
            event.headers.event_type,
            event.headers.event_id,
            event.headers.event_born_time,
            event.data,
        )
        return AckMessage.STATUS_OK, "OK"


@register_platform_adapter(
    "dingtalk", "钉钉机器人官方 API 适配器", support_streaming_message=False
)
class DingtalkPlatformAdapter(Platform):
    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)

        self.client_id = platform_config["client_id"]
        self.client_secret = platform_config["client_secret"]

        outer_self = self

        class AstrCallbackClient(dingtalk_stream.ChatbotHandler):
            async def process(self, message: dingtalk_stream.CallbackMessage):
                logger.debug(f"dingtalk: {message.data}")
                im = dingtalk_stream.ChatbotMessage.from_dict(message.data)
                abm = await outer_self.convert_msg(im)
                await outer_self.handle_msg(abm)

                return AckMessage.STATUS_OK, "OK"

        self.client = AstrCallbackClient()

        credential = dingtalk_stream.Credential(self.client_id, self.client_secret)
        client = dingtalk_stream.DingTalkStreamClient(credential, logger=logger)
        client.register_all_event_handler(MyEventHandler())
        client.register_callback_handler(
            dingtalk_stream.ChatbotMessage.TOPIC,
            self.client,
        )
        self.client_ = client  # 用于 websockets 的 client
        self._shutdown_event: threading.Event | None = None

    def _id_to_sid(self, dingtalk_id: str | None) -> str:
        if not dingtalk_id:
            return dingtalk_id or "unknown"
        prefix = "$:LWCP_v1:$"
        if dingtalk_id.startswith(prefix):
            return dingtalk_id[len(prefix) :]
        return dingtalk_id or "unknown"

    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ):
        raise NotImplementedError("钉钉机器人适配器不支持 send_by_session")

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="dingtalk",
            description="钉钉机器人官方 API 适配器",
            id=cast(str, self.config.get("id")),
            support_streaming_message=False,
        )

    async def convert_msg(
        self,
        message: dingtalk_stream.ChatbotMessage,
    ) -> AstrBotMessage:
        abm = AstrBotMessage()
        abm.message = []
        abm.message_str = ""
        abm.timestamp = int(cast(int, message.create_at) / 1000)
        abm.type = (
            MessageType.GROUP_MESSAGE
            if message.conversation_type == "2"
            else MessageType.FRIEND_MESSAGE
        )
        abm.sender = MessageMember(
            user_id=self._id_to_sid(message.sender_id),
            nickname=message.sender_nick,
        )
        abm.self_id = self._id_to_sid(message.chatbot_user_id)
        abm.message_id = cast(str, message.message_id)
        abm.raw_message = message

        if abm.type == MessageType.GROUP_MESSAGE:
            # 处理所有被 @ 的用户（包括机器人自己，因 at_users 已包含）
            if message.at_users:
                for user in message.at_users:
                    if id := self._id_to_sid(user.dingtalk_id):
                        abm.message.append(At(qq=id))
            abm.group_id = message.conversation_id
            abm.session_id = abm.group_id
        else:
            abm.session_id = abm.sender.user_id

        message_type: str = cast(str, message.message_type)
        match message_type:
            case "text":
                abm.message_str = message.text.content.strip()
                abm.message.append(Plain(abm.message_str))
            case "richText":
                rtc: dingtalk_stream.RichTextContent = cast(
                    dingtalk_stream.RichTextContent, message.rich_text_content
                )
                contents: list[dict] = cast(list[dict], rtc.rich_text_list)
                for content in contents:
                    plains = ""
                    if "text" in content:
                        plains += content["text"]
                        abm.message.append(Plain(plains))
                    elif "type" in content and content["type"] == "picture":
                        f_path = await self.download_ding_file(
                            content["downloadCode"],
                            cast(str, message.robot_code),
                            "jpg",
                        )
                        abm.message.append(Image.fromFileSystem(f_path))
            case "audio":
                pass

        return abm  # 别忘了返回转换后的消息对象

    async def download_ding_file(
        self,
        download_code: str,
        robot_code: str,
        ext: str,
    ) -> str:
        """下载钉钉文件

        :param access_token: 钉钉机器人的 access_token
        :param download_code: 下载码
        :param robot_code: 机器人码
        :param ext: 文件后缀
        :return: 文件路径
        """
        access_token = await self.get_access_token()
        headers = {
            "x-acs-dingtalk-access-token": access_token,
        }
        payload = {
            "downloadCode": download_code,
            "robotCode": robot_code,
        }
        temp_dir = os.path.join(get_astrbot_data_path(), "temp")
        f_path = os.path.join(temp_dir, f"dingtalk_file_{uuid.uuid4()}.{ext}")
        async with (
            aiohttp.ClientSession() as session,
            session.post(
                "https://api.dingtalk.com/v1.0/robot/messageFiles/download",
                headers=headers,
                json=payload,
            ) as resp,
        ):
            if resp.status != 200:
                logger.error(
                    f"下载钉钉文件失败: {resp.status}, {await resp.text()}",
                )
                return ""
            resp_data = await resp.json()
            download_url = resp_data["data"]["downloadUrl"]
            await download_file(download_url, f_path)
        return f_path

    async def get_access_token(self) -> str:
        payload = {
            "appKey": self.client_id,
            "appSecret": self.client_secret,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.dingtalk.com/v1.0/oauth2/accessToken",
                json=payload,
            ) as resp:
                if resp.status != 200:
                    logger.error(
                        f"获取钉钉机器人 access_token 失败: {resp.status}, {await resp.text()}",
                    )
                    return ""
                return (await resp.json())["data"]["accessToken"]

    async def handle_msg(self, abm: AstrBotMessage):
        event = DingtalkMessageEvent(
            message_str=abm.message_str,
            message_obj=abm,
            platform_meta=self.meta(),
            session_id=abm.session_id,
            client=self.client,
        )

        self._event_queue.put_nowait(event)

    async def run(self):
        # await self.client_.start()
        # 钉钉的 SDK 并没有实现真正的异步，start() 里面有堵塞方法。
        def start_client(loop: asyncio.AbstractEventLoop):
            try:
                self._shutdown_event = threading.Event()
                task = loop.create_task(self.client_.start())
                self._shutdown_event.wait()
                if task.done():
                    task.result()
            except Exception as e:
                if "Graceful shutdown" in str(e):
                    logger.info("钉钉适配器已被关闭")
                    return
                logger.error(f"钉钉机器人启动失败: {e}")

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, start_client, loop)

    async def terminate(self):
        def monkey_patch_close():
            raise KeyboardInterrupt("Graceful shutdown")

        if self.client_.websocket is not None:
            self.client_.open_connection = monkey_patch_close
            await self.client_.websocket.close(code=1000, reason="Graceful shutdown")
        if self._shutdown_event is not None:
            self._shutdown_event.set()

    def get_client(self):
        return self.client
