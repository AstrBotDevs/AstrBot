import asyncio
import json
import threading
import time
import uuid
from collections.abc import Awaitable, Callable
from concurrent.futures import CancelledError as FutureCancelledError
from pathlib import Path
from typing import Literal, NoReturn, cast

import aiohttp
import dingtalk_stream
from dingtalk_stream import AckMessage
from dingtalk_stream.frames import Headers

from astrbot import logger
from astrbot.core.message.components import At, File, Image, Plain, Record, Video
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
)
from astrbot.core.platform.astr_message_event import MessageSession
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
from .provisioning import provision_dingtalk_registration

DINGTALK_RECONNECT_INITIAL_DELAY = 10
DINGTALK_RECONNECT_MAX_DELAY = 300
DINGTALK_RECONNECT_STABLE_SECONDS = 300
_DINGTALK_HTTP_TIMEOUT = aiohttp.ClientTimeout(total=30, connect=10, sock_read=30)


def _dingtalk_reconnect_delay(retry_count: int) -> int:
    safe_retry_count = max(retry_count, 1)
    return min(
        DINGTALK_RECONNECT_INITIAL_DELAY * 2 ** (safe_retry_count - 1),
        DINGTALK_RECONNECT_MAX_DELAY,
    )


@register_platform_adapter(
    "dingtalk",
    "钉钉机器人官方 API 适配器",
    support_streaming_message=True,
    provisioner=provision_dingtalk_registration,
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

        class AstrCallbackClient:
            def __init__(self) -> None:
                self.dingtalk_client: dingtalk_stream.DingTalkStreamClient | None = None

            def pre_start(self) -> None:
                return

            async def process(
                self, message: dingtalk_stream.CallbackMessage
            ) -> tuple[int, str]:
                logger.debug(f"dingtalk: {message.data}")
                im = dingtalk_stream.ChatbotMessage.from_dict(message.data)
                abm = await outer_self.convert_msg(im)
                await outer_self.handle_msg(abm)
                return AckMessage.STATUS_OK, "OK"

            async def raw_process(
                self, message: dingtalk_stream.CallbackMessage
            ) -> AckMessage:
                code, text = await self.process(message)
                ack_message = AckMessage()
                ack_message.code = code
                ack_message.headers.message_id = message.headers.message_id
                setattr(
                    ack_message.headers,
                    "content_type",
                    Headers.CONTENT_TYPE_APPLICATION_JSON,
                )
                ack_message.data = {"response": text}
                return ack_message

        self.client = AstrCallbackClient()

        credential = dingtalk_stream.Credential(self.client_id, self.client_secret)
        client = dingtalk_stream.DingTalkStreamClient(credential, logger=logger)
        client.register_callback_handler(
            dingtalk_stream.ChatbotMessage.TOPIC,
            cast(dingtalk_stream.CallbackHandler, self.client),
        )
        self.client_ = client  # 用于 websockets 的 client
        self._shutdown_event = threading.Event()
        self._terminated_event = threading.Event()

    def _id_to_sid(self, dingtalk_id: str | None) -> str:
        if not dingtalk_id:
            return dingtalk_id or "unknown"
        prefix = "$:LWCP_v1:$"
        if dingtalk_id.startswith(prefix):
            return dingtalk_id[len(prefix) :]
        return dingtalk_id or "unknown"

    async def send_by_session(
        self,
        session: MessageSession,
        message_chain: MessageChain,
    ):
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
                    "钉钉私聊会话缺少 staff_id 映射，回退使用 session_id 作为 userId 发送",
                )
                staff_id = session.session_id
            await self.send_message_chain_to_user(
                staff_id=staff_id,
                robot_code=robot_code,
                message_chain=message_chain,
            )

        return await super().send_by_session(session, message_chain)

    async def send_with_session(
        self,
        session: MessageSession,
        message_chain: MessageChain,
    ) -> None:
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
        setattr(abm, "temporary_file_paths", [])
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

        leading_at_is_self = False
        if abm.type == MessageType.GROUP_MESSAGE:
            # 处理所有被 @ 的用户（包括机器人自己，因 at_users 已包含）
            if message.at_users:
                for index, user in enumerate(message.at_users):
                    if user_id := self._id_to_sid(user.dingtalk_id):
                        abm.message.append(At(qq=user_id))
                        if (
                            index == 0
                            and user_id != "unknown"
                            and abm.self_id != "unknown"
                            and user_id == abm.self_id
                            and bool(getattr(message, "is_in_at_list", False))
                        ):
                            leading_at_is_self = True
            abm.group_id = message.conversation_id
            if abm.group:
                abm.group.group_name = getattr(message, "conversation_title", None)
            abm.session_id = abm.group_id
        else:
            abm.session_id = abm.sender.user_id

        message_type: str = cast(str, message.message_type)
        robot_code = cast(str, message.robot_code or "")
        raw_content = cast(dict, message.extensions.get("content") or {})
        if not isinstance(raw_content, dict):
            raw_content = {}

        def _track_temp_path(path: str) -> str:
            temp_paths = cast(list[str], getattr(abm, "temporary_file_paths", []))
            if path and path not in temp_paths:
                temp_paths.append(path)
            return path

        async def _download_media_lazily(
            download_code: str,
            file_ext: str,
        ) -> str | None:
            f_path = await self.download_ding_file(
                download_code,
                robot_code,
                file_ext,
            )
            if not f_path:
                return None
            return _track_temp_path(f_path)

        await self._convert_message_content(
            message=message,
            abm=abm,
            message_type=message_type,
            robot_code=robot_code,
            raw_content=raw_content,
            leading_at_is_self=leading_at_is_self,
            download_media=_download_media_lazily,
        )

        await self._remember_sender_binding(message, abm)
        return abm  # 别忘了返回转换后的消息对象

    async def _convert_message_content(
        self,
        *,
        message: dingtalk_stream.ChatbotMessage,
        abm: AstrBotMessage,
        message_type: str,
        robot_code: str,
        raw_content: dict,
        leading_at_is_self: bool,
        download_media: Callable[[str, str], Awaitable[str | None]],
    ) -> None:
        match message_type:
            case "text":
                abm.message_str = message.text.content.strip()
                abm.message.append(Plain(abm.message_str))
            case "picture":
                if not robot_code:
                    logger.error("钉钉图片消息解析失败: 回调中缺少 robotCode")
                    return
                image_content = cast(
                    dingtalk_stream.ImageContent | None,
                    message.image_content,
                )
                download_code = cast(
                    str, (image_content.download_code if image_content else "") or ""
                )
                if not download_code:
                    logger.warning("钉钉图片消息缺少 downloadCode，已跳过")
                else:
                    image = Image(file="")
                    image.set_source_resolver(
                        lambda download_code=download_code: download_media(
                            download_code, "jpg"
                        )
                    )
                    abm.message.append(image)
            case "richText":
                rtc: dingtalk_stream.RichTextContent = cast(
                    dingtalk_stream.RichTextContent, message.rich_text_content
                )
                contents: list[dict] = cast(list[dict], rtc.rich_text_list)
                plain_parts: list[str] = []
                for index, content in enumerate(contents):
                    if "text" in content:
                        plain_text = cast(str, content.get("text") or "")
                        if plain_text:
                            # HarmonyOS repeats the leading bot mention as a text
                            # segment even though at_users already represents it.
                            if (
                                index == 0
                                and leading_at_is_self
                                and plain_text.lstrip().startswith("@")
                            ):
                                mention_parts = plain_text.lstrip().split(maxsplit=1)
                                if len(mention_parts) == 1:
                                    continue
                                # Keep content that shares the rich-text segment
                                # with the duplicated bot mention so commands
                                # remain parseable.
                                plain_text = mention_parts[1]
                            plain_parts.append(plain_text)
                            abm.message.append(Plain(plain_text))
                    elif "type" in content and content["type"] == "picture":
                        download_code = cast(str, content.get("downloadCode") or "")
                        if not download_code:
                            logger.warning(
                                "钉钉富文本图片消息缺少 downloadCode，已跳过"
                            )
                            continue
                        if not robot_code:
                            logger.error(
                                "钉钉富文本图片消息解析失败: 回调中缺少 robotCode"
                            )
                            continue
                        image = Image(file="")
                        image.set_source_resolver(
                            lambda download_code=download_code: download_media(
                                download_code, "jpg"
                            )
                        )
                        abm.message.append(image)
                abm.message_str = "".join(plain_parts).strip()
            case "audio" | "voice":
                download_code = cast(str, raw_content.get("downloadCode") or "")
                if not download_code:
                    logger.warning("钉钉语音消息缺少 downloadCode，已跳过")
                elif not robot_code:
                    logger.error("钉钉语音消息解析失败: 回调中缺少 robotCode")
                else:
                    voice_ext = cast(str, raw_content.get("fileExtension") or "")
                    if not voice_ext:
                        voice_ext = "amr"
                    voice_ext = voice_ext.lstrip(".")
                    record = Record(file="")
                    record.set_source_resolver(
                        lambda download_code=download_code, voice_ext=voice_ext: (
                            download_media(download_code, voice_ext)
                        )
                    )
                    abm.message.append(record)
            case "file":
                download_code = cast(str, raw_content.get("downloadCode") or "")
                if not download_code:
                    logger.warning("钉钉文件消息缺少 downloadCode，已跳过")
                elif not robot_code:
                    logger.error("钉钉文件消息解析失败: 回调中缺少 robotCode")
                else:
                    file_name = cast(str, raw_content.get("fileName") or "")
                    file_name_missing = not file_name
                    file_ext = Path(file_name).suffix.lstrip(".") if file_name else ""
                    if not file_ext:
                        file_ext = cast(str, raw_content.get("fileExtension") or "")
                    if not file_ext:
                        file_ext = "file"
                    if not file_name:
                        file_name = f"dingtalk_file.{file_ext}"
                    file_component = File(name=file_name)

                    async def _resolve_file_path(
                        *,
                        download_code: str = download_code,
                        file_ext: str = file_ext,
                        file_name_missing: bool = file_name_missing,
                    ) -> str | None:
                        resolved_path = await download_media(download_code, file_ext)
                        if resolved_path and file_name_missing:
                            file_component.name = Path(resolved_path).name
                        return resolved_path

                    file_component.set_file_resolver(_resolve_file_path)
                    abm.message.append(file_component)

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
                        MessageSession(
                            platform_name=self.meta().id,
                            message_type=abm.type,
                            session_id=sender_id,
                        )
                    )
                    await self.preferences.put_async(
                        "global",
                        umo,
                        "dingtalk_staffid",
                        sender_staff_id,
                    )
        except Exception as e:
            logger.warning(f"保存钉钉会话映射失败: {e}")

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
            aiohttp.ClientSession(timeout=_DINGTALK_HTTP_TIMEOUT) as session,
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
            download_url = cast(
                str,
                (
                    resp_data.get("downloadUrl")
                    or resp_data.get("data", {}).get("downloadUrl")
                    or ""
                ),
            )
            if not download_url:
                logger.error(f"下载钉钉文件失败: 未找到 downloadUrl, 响应: {resp_data}")
                return ""
            await download_file(download_url, str(f_path))
        return str(f_path)

    async def get_access_token(self) -> str:
        try:
            access_token = await asyncio.get_running_loop().run_in_executor(
                None,
                self.client_.get_access_token,
            )
            if access_token:
                return access_token
        except Exception as e:
            logger.warning(f"通过 dingtalk_stream 获取 access_token 失败: {e}")

        payload = {"appKey": self.client_id, "appSecret": self.client_secret}
        async with aiohttp.ClientSession(timeout=_DINGTALK_HTTP_TIMEOUT) as session:
            async with session.post(
                "https://api.dingtalk.com/v1.0/oauth2/accessToken",
                json=payload,
            ) as resp:
                if resp.status != 200:
                    logger.error(
                        f"获取钉钉机器人 access_token 失败: {resp.status}, {await resp.text()}",
                    )
                    return ""
                data = await resp.json()
                return cast(str, data.get("data", {}).get("accessToken", ""))

    async def _get_sender_staff_id(self, session: MessageSession) -> str:
        try:
            staff_id = await self.preferences.get_async(
                "global",
                str(session),
                "dingtalk_staffid",
                "",
            )
            return cast(str, staff_id or "")
        except Exception as e:
            logger.warning(f"读取钉钉 staff_id 映射失败: {e}")
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
            logger.error("钉钉群消息发送失败: access_token 为空")
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
        async with aiohttp.ClientSession(timeout=_DINGTALK_HTTP_TIMEOUT) as session:
            async with session.post(
                "https://api.dingtalk.com/v1.0/robot/groupMessages/send",
                headers=headers,
                json=payload,
            ) as resp:
                if resp.status != 200:
                    logger.error(
                        f"钉钉群消息发送失败: {resp.status}, {await resp.text()}",
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
            logger.error("钉钉私聊消息发送失败: access_token 为空")
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
        async with aiohttp.ClientSession(timeout=_DINGTALK_HTTP_TIMEOUT) as session:
            async with session.post(
                "https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend",
                headers=headers,
                json=payload,
            ) as resp:
                if resp.status != 200:
                    logger.error(
                        f"钉钉私聊消息发送失败: {resp.status}, {await resp.text()}",
                    )

    def _safe_remove_file(self, file_path: str | None) -> None:
        if not file_path:
            return
        try:
            p = Path(file_path)
            if p.exists() and p.is_file():
                p.unlink()
        except Exception as e:
            logger.warning(f"清理临时文件失败: {file_path}, {e}")

    async def _prepare_voice_for_dingtalk(self, input_path: str) -> tuple[str, bool]:
        """优先转换为 OGG(Opus)，不可用时回退 AMR。"""
        lower_path = input_path.lower()
        if lower_path.endswith((".amr", ".ogg")):
            return input_path, False

        try:
            converted = await convert_audio_format(input_path, "ogg")
            return converted, converted != input_path
        except Exception as e:
            logger.warning(f"钉钉语音转 OGG 失败，回退 AMR: {e}")
            converted = await convert_audio_format(input_path, "amr")
            return converted, converted != input_path

    async def upload_media(self, file_path: str, media_type: str) -> str:
        media_file_path = Path(file_path)
        access_token = await self.get_access_token()
        if not access_token:
            logger.error("钉钉媒体上传失败: access_token 为空")
            return ""

        form = aiohttp.FormData()
        form.add_field(
            "media",
            media_file_path.read_bytes(),
            filename=media_file_path.name,
            content_type="application/octet-stream",
        )
        async with aiohttp.ClientSession(timeout=_DINGTALK_HTTP_TIMEOUT) as session:
            async with session.post(
                f"https://oapi.dingtalk.com/media/upload?access_token={access_token}&type={media_type}",
                data=form,
            ) as resp:
                if resp.status != 200:
                    logger.error(
                        f"钉钉媒体上传失败: {resp.status}, {await resp.text()}"
                    )
                    return ""
                data = await resp.json()
                if data.get("errcode") != 0:
                    logger.error(f"钉钉媒体上传失败: {data}")
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
                text = f"{at_str} {text}".strip()
                if message_chain.use_markdown_ is False:
                    await send_message(
                        msg_key="sampleText",
                        msg_param={"content": text},
                    )
                else:
                    await send_message(
                        msg_key="sampleMarkdown",
                        msg_param={"title": "AstrBot", "text": text},
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
                audio_path = ""
                converted_audio = False
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
                    logger.warning(f"钉钉语音发送失败: {e}")
                    continue
                finally:
                    if converted_audio:
                        self._safe_remove_file(audio_path)
            elif isinstance(segment, Video):
                converted_video = False
                cover_path = None
                video_path = ""
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
                    logger.warning(f"钉钉视频发送失败: {e}")
                    continue
                finally:
                    self._safe_remove_file(cover_path)
                    if converted_video:
                        self._safe_remove_file(video_path)
            elif isinstance(segment, File):
                try:
                    file_path = await segment.get_file()
                    if not file_path:
                        logger.warning("钉钉文件发送失败: 无法解析文件路径")
                        continue
                    media_id = await self.upload_media(file_path, "file")
                    if not media_id:
                        continue
                    file_name = segment.name or Path(file_path).name
                    file_type = Path(file_name).suffix.lstrip(".")
                    await send_message(
                        msg_key="sampleFile",
                        msg_param={
                            "mediaId": media_id,
                            "fileName": file_name,
                            "fileType": file_type,
                        },
                    )
                except Exception as e:
                    logger.warning(f"钉钉文件发送失败: {e}")
                    continue

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
            session = MessageSession(
                platform_name=self.meta().id,
                message_type=MessageType.FRIEND_MESSAGE,
                session_id=normalized_sender_id,
            )
            staff_id = sender_staff_id or await self._get_sender_staff_id(session)
            if not staff_id:
                logger.error("钉钉私聊回复失败: 缺少 sender_staff_id")
                return
            await self.send_message_chain_to_user(
                staff_id=staff_id,
                robot_code=robot_code,
                message_chain=message_chain,
                # at_str=at_str,
            )

    def create_event(self, message: AstrBotMessage) -> DingtalkMessageEvent:
        """Creates a Dingtalk message event.

        Args:
            message: AstrBot message object to wrap.

        Returns:
            Created Dingtalk message event.
        """
        return DingtalkMessageEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            client=self.client,
            adapter=self,
        )

    async def handle_msg(self, abm: AstrBotMessage) -> None:
        self.commit_event(self.create_event(abm))

    async def run(self) -> None:
        # await self.client_.start()
        # 钉钉的 SDK 并没有实现真正的异步，start() 里面有堵塞方法。
        # SDK 内部已有 while True 重连循环，但需要监控 task 状态，
        # 如果 task 意外退出则重新启动。

        def start_client(loop: asyncio.AbstractEventLoop) -> None:
            retry_count = 0

            def handle_retry(error_msg: str, run_seconds: float) -> None:
                nonlocal retry_count
                logger.error(error_msg)
                if run_seconds >= DINGTALK_RECONNECT_STABLE_SECONDS:
                    retry_count = 0
                retry_count += 1
                delay = _dingtalk_reconnect_delay(retry_count)
                logger.info(
                    f"钉钉适配器将在 {delay} 秒后重连 (第 {retry_count} 次)...",
                )
                self._terminated_event.wait(delay)

            while not self._terminated_event.is_set():
                task = None
                should_cancel_task = False
                start_time = time.monotonic()
                try:
                    self._shutdown_event.clear()
                    if self._terminated_event.is_set():
                        return
                    task = asyncio.run_coroutine_threadsafe(self.client_.start(), loop)
                    # 当 task 完成时唤醒线程（无论是正常退出还是异常退出）
                    task.add_done_callback(lambda _: self._shutdown_event.set())
                    if self._terminated_event.is_set():
                        should_cancel_task = True
                        self._shutdown_event.set()
                    self._shutdown_event.wait()
                    if self._terminated_event.is_set():
                        return
                    if task.done():
                        try:
                            exc = task.exception()
                        except asyncio.CancelledError, FutureCancelledError:
                            logger.info("钉钉适配器 task 已取消")
                            return
                        if exc:
                            if "Graceful shutdown" in str(exc):
                                logger.info("钉钉适配器已被关闭")
                                return
                            should_cancel_task = True
                            handle_retry(
                                f"钉钉 SDK task 异常退出: {exc}",
                                time.monotonic() - start_time,
                            )
                            continue
                    # task 仍在运行，shutdown_event 被设置（正常关闭）
                    return
                except Exception as e:
                    if "Graceful shutdown" in str(e):
                        logger.info("钉钉适配器已被关闭")
                        return
                    should_cancel_task = True
                    handle_retry(
                        f"钉钉机器人启动失败: {e}",
                        time.monotonic() - start_time,
                    )
                    continue
                finally:
                    # 仅在重试/失败路径取消 task，正常关闭不取消
                    if task is not None and not task.done() and should_cancel_task:
                        task.cancel()

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, start_client, loop)

    async def terminate(self) -> None:
        def monkey_patch_close() -> NoReturn:
            raise KeyboardInterrupt("Graceful shutdown")

        self._terminated_event.set()
        self._shutdown_event.set()
        if self.client_.websocket is not None:
            self.client_.open_connection = monkey_patch_close
            await self.client_.websocket.close(code=1000, reason="Graceful shutdown")
