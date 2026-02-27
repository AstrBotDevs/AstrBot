from astrbot.core.lang import t
import asyncio
import json
import threading
import uuid
from pathlib import Path
from typing import Literal, NoReturn, cast

import aiohttp
import dingtalk_stream
from dingtalk_stream import AckMessage

from astrbot import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import At, Image, Plain, Record, Video
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
)
from astrbot.core import sp
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.io import download_file
from astrbot.core.utils.media_utils import (
    convert_audio_format,
    convert_video_format,
    extract_video_cover,
    get_media_duration,
)

from ...register import register_platform_adapter
from .dingtalk_event import DingtalkMessageEvent


class MyEventHandler(dingtalk_stream.EventHandler):
    async def process(self, event: dingtalk_stream.EventMessage):
        print(
            t("msg-c81e728d"),
            event.headers.event_type,
            event.headers.event_id,
            event.headers.event_born_time,
            event.data,
        )
        return AckMessage.STATUS_OK, "OK"


@register_platform_adapter(
    "dingtalk", "钉钉机器人官方 API 适配器", support_streaming_message=True
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
                logger.debug(t("msg-d6371313", res=message.data))
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
    ) -> None:
        robot_code = self.client_id

        if session.message_type == MessageType.GROUP_MESSAGE:
            open_conversation_id = session.session_id
            await self.send_message_chain_to_group(
                open_conversation_id=open_conversation_id,
                robot_code=robot_code,
                message_chain=message_chain,
            )
        else:
            staff_id = await self._get_sender_staff_id(session)
            if not staff_id:
                logger.warning(
                    t("msg-a1c8b5b1"),
                )
                staff_id = session.session_id
            await self.send_message_chain_to_user(
                staff_id=staff_id,
                robot_code=robot_code,
                message_chain=message_chain,
            )

        await super().send_by_session(session, message_chain)

    async def send_with_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ) -> None:
        await self.send_by_session(session, message_chain)

    async def send_with_sesison(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ) -> None:
        # backward typo compatibility
        await self.send_by_session(session, message_chain)

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="dingtalk",
            description="钉钉机器人官方 API 适配器",
            id=cast(str, self.config.get("id")),
            support_streaming_message=True,
            support_proactive_message=True,
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

        await self._remember_sender_binding(message, abm)
        return abm  # 别忘了返回转换后的消息对象

    async def _remember_sender_binding(
        self,
        message: dingtalk_stream.ChatbotMessage,
        abm: AstrBotMessage,
    ) -> None:
        try:
            if abm.type == MessageType.FRIEND_MESSAGE:
                sender_id = abm.sender.user_id
                sender_staff_id = cast(str, message.sender_staff_id or "")
                if sender_staff_id:
                    umo = str(
                        MessageSesion(
                            platform_name=self.meta().id,
                            message_type=abm.type,
                            session_id=sender_id,
                        )
                    )
                    await sp.put_async(
                        "global",
                        umo,
                        "dingtalk_staffid",
                        sender_staff_id,
                    )
        except Exception as e:
            logger.warning(t("msg-2abb842f", e=e))

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
        temp_dir = Path(get_astrbot_temp_path())
        temp_dir.mkdir(parents=True, exist_ok=True)
        f_path = temp_dir / f"dingtalk_{uuid.uuid4()}.{ext}"
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
                    t("msg-46988861", res=resp.status, res_2=await resp.text()),
                )
                return ""
            resp_data = await resp.json()
            download_url = resp_data["data"]["downloadUrl"]
            await download_file(download_url, str(f_path))
        return str(f_path)

    async def get_access_token(self) -> str:
        try:
            access_token = await asyncio.get_event_loop().run_in_executor(
                None,
                self.client_.get_access_token,
            )
            if access_token:
                return access_token
        except Exception as e:
            logger.warning(t("msg-ba9e1288", e=e))

        payload = {"appKey": self.client_id, "appSecret": self.client_secret}
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.dingtalk.com/v1.0/oauth2/accessToken",
                json=payload,
            ) as resp:
                if resp.status != 200:
                    logger.error(
                        t("msg-835b1ce6", res=resp.status, res_2=await resp.text()),
                    )
                    return ""
                data = await resp.json()
                return cast(str, data.get("data", {}).get("accessToken", ""))

    async def _get_sender_staff_id(self, session: MessageSesion) -> str:
        try:
            staff_id = await sp.get_async(
                "global",
                str(session),
                "dingtalk_staffid",
                "",
            )
            return cast(str, staff_id or "")
        except Exception as e:
            logger.warning(t("msg-331fcb1f", e=e))
            return ""

    async def _send_group_message(
        self,
        open_conversation_id: str,
        robot_code: str,
        msg_key: str,
        msg_param: dict,
    ) -> None:
        access_token = await self.get_access_token()
        if not access_token:
            logger.error(t("msg-ba183a34"))
            return

        payload = {
            "msgKey": msg_key,
            "msgParam": json.dumps(msg_param, ensure_ascii=False),
            "openConversationId": open_conversation_id,
            "robotCode": robot_code,
        }
        headers = {
            "Content-Type": "application/json",
            "x-acs-dingtalk-access-token": access_token,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.dingtalk.com/v1.0/robot/groupMessages/send",
                headers=headers,
                json=payload,
            ) as resp:
                if resp.status != 200:
                    logger.error(
                        t("msg-b8aaa69b", res=resp.status, res_2=await resp.text()),
                    )

    async def _send_private_message(
        self,
        staff_id: str,
        robot_code: str,
        msg_key: str,
        msg_param: dict,
    ) -> None:
        access_token = await self.get_access_token()
        if not access_token:
            logger.error(t("msg-cfb35bf5"))
            return

        payload = {
            "robotCode": robot_code,
            "userIds": [staff_id],
            "msgKey": msg_key,
            "msgParam": json.dumps(msg_param, ensure_ascii=False),
        }
        headers = {
            "Content-Type": "application/json",
            "x-acs-dingtalk-access-token": access_token,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend",
                headers=headers,
                json=payload,
            ) as resp:
                if resp.status != 200:
                    logger.error(
                        t("msg-7553c219", res=resp.status, res_2=await resp.text()),
                    )

    def _safe_remove_file(self, file_path: str | None) -> None:
        if not file_path:
            return
        try:
            p = Path(file_path)
            if p.exists() and p.is_file():
                p.unlink()
        except Exception as e:
            logger.warning(t("msg-5ab2d58d", file_path=file_path, e=e))

    async def _prepare_voice_for_dingtalk(self, input_path: str) -> tuple[str, bool]:
        """优先转换为 OGG(Opus)，不可用时回退 AMR。"""
        lower_path = input_path.lower()
        if lower_path.endswith((".amr", ".ogg")):
            return input_path, False

        try:
            converted = await convert_audio_format(input_path, "ogg")
            return converted, converted != input_path
        except Exception as e:
            logger.warning(t("msg-c0c40912", e=e))
            converted = await convert_audio_format(input_path, "amr")
            return converted, converted != input_path

    async def upload_media(self, file_path: str, media_type: str) -> str:
        media_file_path = Path(file_path)
        access_token = await self.get_access_token()
        if not access_token:
            logger.error(t("msg-21c73eca"))
            return ""

        form = aiohttp.FormData()
        form.add_field(
            "media",
            media_file_path.read_bytes(),
            filename=media_file_path.name,
            content_type="application/octet-stream",
        )
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"https://oapi.dingtalk.com/media/upload?access_token={access_token}&type={media_type}",
                data=form,
            ) as resp:
                if resp.status != 200:
                    logger.error(
                        t("msg-24e3054f", res=resp.status, res_2=await resp.text())
                    )
                    return ""
                data = await resp.json()
                if data.get("errcode") != 0:
                    logger.error(t("msg-34d0a11d", data=data))
                    return ""
                return cast(str, data.get("media_id", ""))

    async def upload_image(self, image: Image) -> str:
        image_file_path = await image.convert_to_file_path()
        return await self.upload_media(image_file_path, "image")

    async def _send_message_chain(
        self,
        target_type: Literal["group", "user"],
        target_id: str,
        robot_code: str,
        message_chain: MessageChain,
        at_str: str = "",
    ) -> None:
        async def send_message(msg_key: str, msg_param: dict) -> None:
            if target_type == "group":
                await self._send_group_message(
                    open_conversation_id=target_id,
                    robot_code=robot_code,
                    msg_key=msg_key,
                    msg_param=msg_param,
                )
            else:
                await self._send_private_message(
                    staff_id=target_id,
                    robot_code=robot_code,
                    msg_key=msg_key,
                    msg_param=msg_param,
                )

        for segment in message_chain.chain:
            if isinstance(segment, Plain):
                text = segment.text.strip()
                if not text and not at_str:
                    continue
                await send_message(
                    msg_key="sampleMarkdown",
                    msg_param={
                        "title": "AstrBot",
                        "text": f"{at_str} {text}".strip(),
                    },
                )
            elif isinstance(segment, Image):
                photo_url = segment.file or segment.url or ""
                if photo_url.startswith(("http://", "https://")):
                    pass
                else:
                    photo_url = await self.upload_image(segment)
                if not photo_url:
                    continue
                await send_message(
                    msg_key="sampleImageMsg",
                    msg_param={"photoURL": photo_url},
                )
            elif isinstance(segment, Record):
                converted_audio = None
                try:
                    audio_path = await segment.convert_to_file_path()
                    (
                        audio_path,
                        converted_audio,
                    ) = await self._prepare_voice_for_dingtalk(audio_path)
                    media_id = await self.upload_media(audio_path, "voice")
                    if not media_id:
                        continue
                    duration_ms = await get_media_duration(audio_path)
                    await send_message(
                        msg_key="sampleAudio",
                        msg_param={
                            "mediaId": media_id,
                            "duration": str(duration_ms or 1000),
                        },
                    )
                except Exception as e:
                    logger.warning(t("msg-3b0d4fb5", e=e))
                    continue
                finally:
                    if converted_audio:
                        self._safe_remove_file(audio_path)
            elif isinstance(segment, Video):
                converted_video = False
                cover_path = None
                try:
                    source_video_path = await segment.convert_to_file_path()
                    video_path = source_video_path
                    if not video_path.lower().endswith(".mp4"):
                        video_path = await convert_video_format(video_path, "mp4")
                        converted_video = video_path != source_video_path
                    cover_path = await extract_video_cover(video_path)
                    video_media_id = await self.upload_media(video_path, "file")
                    pic_media_id = await self.upload_media(cover_path, "image")
                    if not video_media_id or not pic_media_id:
                        continue
                    duration_ms = await get_media_duration(video_path)
                    duration_sec = max(1, int((duration_ms or 1000) / 1000))
                    await send_message(
                        msg_key="sampleVideo",
                        msg_param={
                            "duration": str(duration_sec),
                            "videoMediaId": video_media_id,
                            "videoType": "mp4",
                            "picMediaId": pic_media_id,
                        },
                    )
                except Exception as e:
                    logger.warning(t("msg-7187f424", e=e))
                    continue
                finally:
                    self._safe_remove_file(cover_path)
                    if converted_video:
                        self._safe_remove_file(video_path)

    async def send_message_chain_to_group(
        self,
        open_conversation_id: str,
        robot_code: str,
        message_chain: MessageChain,
        at_str: str = "",
    ) -> None:
        await self._send_message_chain(
            target_type="group",
            target_id=open_conversation_id,
            robot_code=robot_code,
            message_chain=message_chain,
            at_str=at_str,
        )

    async def send_message_chain_to_user(
        self,
        staff_id: str,
        robot_code: str,
        message_chain: MessageChain,
        at_str: str = "",
    ) -> None:
        await self._send_message_chain(
            target_type="user",
            target_id=staff_id,
            robot_code=robot_code,
            message_chain=message_chain,
            at_str=at_str,
        )

    async def send_message_chain_with_incoming(
        self,
        incoming_message: dingtalk_stream.ChatbotMessage,
        message_chain: MessageChain,
    ) -> None:
        robot_code = self.client_id

        # at_list: list[str] = []
        sender_id = cast(str, incoming_message.sender_id or "")
        sender_staff_id = cast(str, incoming_message.sender_staff_id or "")
        normalized_sender_id = self._id_to_sid(sender_id)
        # 现在用的发消息接口不支持 at
        # for segment in message_chain.chain:
        #     if isinstance(segment, At):
        #         if (
        #             str(segment.qq) in {sender_id, normalized_sender_id}
        #             and sender_staff_id
        #         ):
        #             at_list.append(f"@{sender_staff_id}")
        #         else:
        #             at_list.append(f"@{segment.qq}")
        # at_str = " ".join(at_list)

        if incoming_message.conversation_type == "2":
            await self.send_message_chain_to_group(
                open_conversation_id=cast(str, incoming_message.conversation_id),
                robot_code=robot_code,
                message_chain=message_chain,
                # at_str=at_str,
            )
        else:
            session = MessageSesion(
                platform_name=self.meta().id,
                message_type=MessageType.FRIEND_MESSAGE,
                session_id=normalized_sender_id,
            )
            staff_id = sender_staff_id or await self._get_sender_staff_id(session)
            if not staff_id:
                logger.error(t("msg-e40cc45f"))
                return
            await self.send_message_chain_to_user(
                staff_id=staff_id,
                robot_code=robot_code,
                message_chain=message_chain,
                # at_str=at_str,
            )

    async def handle_msg(self, abm: AstrBotMessage) -> None:
        event = DingtalkMessageEvent(
            message_str=abm.message_str,
            message_obj=abm,
            platform_meta=self.meta(),
            session_id=abm.session_id,
            client=self.client,
            adapter=self,
        )

        self._event_queue.put_nowait(event)

    async def run(self) -> None:
        # await self.client_.start()
        # 钉钉的 SDK 并没有实现真正的异步，start() 里面有堵塞方法。
        def start_client(loop: asyncio.AbstractEventLoop) -> None:
            try:
                self._shutdown_event = threading.Event()
                task = loop.create_task(self.client_.start())
                self._shutdown_event.wait()
                if task.done():
                    task.result()
            except Exception as e:
                if "Graceful shutdown" in str(e):
                    logger.info(t("msg-be63618a"))
                    return
                logger.error(t("msg-0ab22b13", e=e))

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, start_client, loop)

    async def terminate(self) -> None:
        def monkey_patch_close() -> NoReturn:
            raise KeyboardInterrupt("Graceful shutdown")

        if self.client_.websocket is not None:
            self.client_.open_connection = monkey_patch_close
            await self.client_.websocket.close(code=1000, reason="Graceful shutdown")
        if self._shutdown_event is not None:
            self._shutdown_event.set()

    def get_client(self):
        return self.client
