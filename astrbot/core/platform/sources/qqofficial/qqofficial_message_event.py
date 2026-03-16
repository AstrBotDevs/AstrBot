import asyncio
import base64
import os
import random
import uuid
from typing import cast

import aiofiles
import botpy
import botpy.errors
import botpy.message
import botpy.types
import botpy.types.message
from botpy import Client
from botpy.http import Route
from botpy.types import message
from botpy.types.message import MarkdownPayload, Media

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import File, Image, Plain, Record, Video
from astrbot.api.platform import AstrBotMessage, PlatformMetadata
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.io import download_image_by_url, file_to_base64
from astrbot.core.utils.tencent_record_helper import wav_to_tencent_silk


def _patch_qq_botpy_formdata() -> None:
    """Patch qq-botpy for aiohttp>=3.12 compatibility.

    qq-botpy 1.2.1 defines botpy.http._FormData._gen_form_data() and expects
    aiohttp.FormData to have a private flag named _is_processed, which is no
    longer present in newer aiohttp versions.
    """

    try:
        from botpy.http import _FormData  # type: ignore

        if not hasattr(_FormData, "_is_processed"):
            setattr(_FormData, "_is_processed", False)
    except Exception:
        logger.debug("[QQOfficial] Skip botpy FormData patch.")


_patch_qq_botpy_formdata()


class QQOfficialMessageEvent(AstrMessageEvent):
    MARKDOWN_NOT_ALLOWED_ERROR = "不允许发送原生 markdown"
    IMAGE_FILE_TYPE = 1
    VIDEO_FILE_TYPE = 2
    VOICE_FILE_TYPE = 3
    FILE_FILE_TYPE = 4
    STREAM_MARKDOWN_NEWLINE_ERROR = "流式消息md分片需要\\n结束"

    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
        bot: Client,
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.bot = bot
        self.send_buffer = None

    async def send(self, message: MessageChain) -> None:
        self.send_buffer = message
        await self._post_send()

    async def send_streaming(self, generator, use_fallback: bool = False):
        """流式输出仅支持消息列表私聊（C2C），其他消息源退化为普通发送"""
        # 先标记事件层“已执行发送操作”，避免异常路径遗漏
        await super().send_streaming(generator, use_fallback)
        # QQ C2C 流式协议：开始/中间分片使用 state=1，结束分片使用 state=10
        stream_payload = {"state": 1, "id": None, "index": 0, "reset": False}
        last_edit_time = 0  # 上次发送分片的时间
        throttle_interval = 1  # 分片间最短间隔 (秒)
        ret = None
        source = (
            self.message_obj.raw_message
        )  # 提前获取，避免 generator 为空时 NameError
        try:
            async for chain in generator:
                source = self.message_obj.raw_message

                if not isinstance(source, botpy.message.C2CMessage):
                    # 非 C2C 场景：直接累积，最后统一发
                    if not self.send_buffer:
                        self.send_buffer = chain
                    else:
                        self.send_buffer.chain.extend(chain.chain)
                    continue

                # ---- C2C 流式场景 ----

                # tool_call break 信号：工具开始执行，先把已有 buffer 以 state=10 结束当前流式段
                if chain.type == "break":
                    if self.send_buffer:
                        stream_payload["state"] = 10
                        ret = await self._post_send(stream=stream_payload)
                        ret_id = self._extract_response_message_id(ret)
                        if ret_id is not None:
                            stream_payload["id"] = ret_id
                    # 重置 stream_payload，为下一段流式做准备
                    stream_payload = {
                        "state": 1,
                        "id": None,
                        "index": 0,
                        "reset": False,
                    }
                    last_edit_time = 0
                    continue

                # 累积内容
                if not self.send_buffer:
                    self.send_buffer = chain
                else:
                    self.send_buffer.chain.extend(chain.chain)

                # 节流：按时间间隔发送中间分片
                current_time = asyncio.get_running_loop().time()
                if current_time - last_edit_time >= throttle_interval:
                    ret = cast(
                        message.Message,
                        await self._post_send(stream=stream_payload),
                    )
                    stream_payload["index"] += 1
                    ret_id = self._extract_response_message_id(ret)
                    if ret_id is not None:
                        stream_payload["id"] = ret_id
                    last_edit_time = asyncio.get_running_loop().time()
                    self.send_buffer = None  # 清空已发送的分片，避免下次重复发送旧内容

            if isinstance(source, botpy.message.C2CMessage):
                # 结束流式对话，发送 buffer 中剩余内容
                stream_payload["state"] = 10
                ret = await self._post_send(stream=stream_payload)
            else:
                ret = await self._post_send()

        except Exception as e:
            logger.error(f"发送流式消息时出错: {e}", exc_info=True)
            # 避免累计内容在异常后被整包重复发送：仅清理缓存，不做非流式整包兜底
            # 如需兜底，应该只发送未发送 delta（后续可继续优化）
            self.send_buffer = None

        return None

    @staticmethod
    def _extract_response_message_id(ret) -> str | None:
        """兼容 qq-botpy 返回 Message 对象或 dict 两种形态。"""
        if ret is None:
            return None
        if isinstance(ret, dict):
            ret_id = ret.get("id")
            return str(ret_id) if ret_id is not None else None
        ret_id = getattr(ret, "id", None)
        return str(ret_id) if ret_id is not None else None

    async def _post_send(self, stream: dict | None = None):
        if not self.send_buffer:
            return None

        source = self.message_obj.raw_message

        if not isinstance(
            source,
            botpy.message.Message
            | botpy.message.GroupMessage
            | botpy.message.DirectMessage
            | botpy.message.C2CMessage,
        ):
            logger.warning(f"[QQOfficial] 不支持的消息源类型: {type(source)}")
            return None

        (
            plain_text,
            image_base64,
            image_path,
            record_file_path,
            video_file_source,
            file_source,
            file_name,
        ) = await QQOfficialMessageEvent._parse_to_qqofficial(self.send_buffer)

        # C2C 流式仅用于文本分片，富媒体时降级为普通发送，避免平台侧流式校验报错。
        if stream and (image_base64 or record_file_path):
            logger.debug("[QQOfficial] 检测到富媒体，降级为非流式发送。")
            stream = None

        if (
            not plain_text
            and not image_base64
            and not image_path
            and not record_file_path
            and not video_file_source
            and not file_source
        ):
            return None

        # QQ C2C 流式 API 说明：
        # - 开始/中间分片（state=1）：增量追加内容，不需要 \n（加了会导致强制换行）
        # - 最终分片（state=10）：结束流，content 必须以 \n 结尾（QQ API 要求）
        if (
            stream
            and stream.get("state") == 10
            and plain_text
            and not plain_text.endswith("\n")
        ):
            plain_text = plain_text + "\n"

        payload: dict = {
            # "content": plain_text,
            "markdown": MarkdownPayload(content=plain_text) if plain_text else None,
            "msg_type": 2,
            "msg_id": self.message_obj.message_id,
        }

        if not isinstance(source, botpy.message.Message | botpy.message.DirectMessage):
            payload["msg_seq"] = random.randint(1, 10000)

        ret = None

        match source:
            case botpy.message.GroupMessage():
                if not source.group_openid:
                    logger.error("[QQOfficial] GroupMessage 缺少 group_openid")
                    return None

                if image_base64:
                    media = await self.upload_group_and_c2c_image(
                        image_base64,
                        self.IMAGE_FILE_TYPE,
                        group_openid=source.group_openid,
                    )
                    payload["media"] = media
                    payload["msg_type"] = 7
                    payload.pop("markdown", None)
                    payload["content"] = plain_text or None
                if record_file_path:  # group record msg
                    media = await self.upload_group_and_c2c_media(
                        record_file_path,
                        self.VOICE_FILE_TYPE,
                        group_openid=source.group_openid,
                    )
                    if media:
                        payload["media"] = media
                        payload["msg_type"] = 7
                        payload.pop("markdown", None)
                        payload["content"] = plain_text or None
                if video_file_source:
                    media = await self.upload_group_and_c2c_media(
                        video_file_source,
                        self.VIDEO_FILE_TYPE,
                        group_openid=source.group_openid,
                    )
                    if media:
                        payload["media"] = media
                        payload["msg_type"] = 7
                        payload.pop("markdown", None)
                        payload["content"] = plain_text or None
                if file_source:
                    media = await self.upload_group_and_c2c_media(
                        file_source,
                        self.FILE_FILE_TYPE,
                        file_name=file_name,
                        group_openid=source.group_openid,
                    )
                    if media:
                        payload["media"] = media
                        payload["msg_type"] = 7
                        payload.pop("markdown", None)
                        payload["content"] = plain_text or None
                ret = await self._send_with_markdown_fallback(
                    send_func=lambda retry_payload: self.bot.api.post_group_message(
                        group_openid=source.group_openid,  # type: ignore
                        **retry_payload,
                    ),
                    payload=payload,
                    plain_text=plain_text,
                    stream=stream,
                )

            case botpy.message.C2CMessage():
                if image_base64:
                    media = await self.upload_group_and_c2c_image(
                        image_base64,
                        self.IMAGE_FILE_TYPE,
                        openid=source.author.user_openid,
                    )
                    payload["media"] = media
                    payload["msg_type"] = 7
                    payload.pop("markdown", None)
                    payload["content"] = plain_text or None
                if record_file_path:  # c2c record
                    media = await self.upload_group_and_c2c_media(
                        record_file_path,
                        self.VOICE_FILE_TYPE,
                        openid=source.author.user_openid,
                    )
                    if media:
                        payload["media"] = media
                        payload["msg_type"] = 7
                        payload.pop("markdown", None)
                        payload["content"] = plain_text or None
                if video_file_source:
                    media = await self.upload_group_and_c2c_media(
                        video_file_source,
                        self.VIDEO_FILE_TYPE,
                        openid=source.author.user_openid,
                    )
                    if media:
                        payload["media"] = media
                        payload["msg_type"] = 7
                        payload.pop("markdown", None)
                        payload["content"] = plain_text or None
                if file_source:
                    media = await self.upload_group_and_c2c_media(
                        file_source,
                        self.FILE_FILE_TYPE,
                        file_name=file_name,
                        openid=source.author.user_openid,
                    )
                    if media:
                        payload["media"] = media
                        payload["msg_type"] = 7
                        payload.pop("markdown", None)
                        payload["content"] = plain_text or None
                if stream:
                    ret = await self._send_with_markdown_fallback(
                        send_func=lambda retry_payload: self.post_c2c_message(
                            openid=source.author.user_openid,
                            **retry_payload,
                            stream=stream,
                        ),
                        payload=payload,
                        plain_text=plain_text,
                        stream=stream,
                    )
                else:
                    ret = await self._send_with_markdown_fallback(
                        send_func=lambda retry_payload: self.post_c2c_message(
                            openid=source.author.user_openid,
                            **retry_payload,
                        ),
                        payload=payload,
                        plain_text=plain_text,
                        stream=stream,
                    )
                logger.debug(f"Message sent to C2C: {ret}")

            case botpy.message.Message():
                if image_path:
                    payload["file_image"] = image_path
                # Guild text-channel send API (/channels/{channel_id}/messages) does not use v2 msg_type.
                payload.pop("msg_type", None)
                ret = await self._send_with_markdown_fallback(
                    send_func=lambda retry_payload: self.bot.api.post_message(
                        channel_id=source.channel_id,
                        **retry_payload,
                    ),
                    payload=payload,
                    plain_text=plain_text,
                    stream=stream,
                )

            case botpy.message.DirectMessage():
                if image_path:
                    payload["file_image"] = image_path
                # Guild DM send API (/dms/{guild_id}/messages) does not use v2 msg_type.
                payload.pop("msg_type", None)
                ret = await self._send_with_markdown_fallback(
                    send_func=lambda retry_payload: self.bot.api.post_dms(
                        guild_id=source.guild_id,
                        **retry_payload,
                    ),
                    payload=payload,
                    plain_text=plain_text,
                    stream=stream,
                )

            case _:
                pass

        await super().send(self.send_buffer)

        self.send_buffer = None

        return ret

    async def _send_with_markdown_fallback(
        self,
        send_func,
        payload: dict,
        plain_text: str,
        stream: dict | None = None,
    ):
        try:
            return await send_func(payload)
        except botpy.errors.ServerError as err:
            # QQ 流式 markdown 分片校验：内容必须以换行结尾。
            # 某些边界场景服务端仍可能判定失败，这里做一次修正重试。
            if stream and self.STREAM_MARKDOWN_NEWLINE_ERROR in str(err):
                retry_payload = payload.copy()

                markdown_payload = retry_payload.get("markdown")
                if isinstance(markdown_payload, dict):
                    md_content = cast(str, markdown_payload.get("content", "") or "")
                    if md_content and not md_content.endswith("\n"):
                        retry_payload["markdown"] = {"content": md_content + "\n"}

                content = cast(str | None, retry_payload.get("content"))
                if content and not content.endswith("\n"):
                    retry_payload["content"] = content + "\n"

                logger.warning(
                    "[QQOfficial] 流式 markdown 分片换行校验失败，已修正后重试一次。"
                )
                return await send_func(retry_payload)

            if (
                self.MARKDOWN_NOT_ALLOWED_ERROR not in str(err)
                or not payload.get("markdown")
                or not plain_text
            ):
                raise

            logger.warning(
                "[QQOfficial] markdown 发送被拒绝，回退到 content 模式重试。"
            )
            fallback_payload = payload.copy()
            fallback_payload.pop("markdown", None)
            fallback_payload["content"] = plain_text
            if fallback_payload.get("msg_type") == 2:
                fallback_payload["msg_type"] = 0
            if stream:
                fallback_content = cast(str, fallback_payload.get("content") or "")
                if fallback_content and not fallback_content.endswith("\n"):
                    fallback_payload["content"] = fallback_content + "\n"
            return await send_func(fallback_payload)

    async def upload_group_and_c2c_image(
        self,
        image_base64: str,
        file_type: int,
        **kwargs,
    ) -> botpy.types.message.Media:
        payload = {
            "file_data": image_base64,
            "file_type": file_type,
            "srv_send_msg": False,
        }

        result = None
        if "openid" in kwargs:
            payload["openid"] = kwargs["openid"]
            route = Route("POST", "/v2/users/{openid}/files", openid=kwargs["openid"])
            result = await self.bot.api._http.request(route, json=payload)
        elif "group_openid" in kwargs:
            payload["group_openid"] = kwargs["group_openid"]
            route = Route(
                "POST",
                "/v2/groups/{group_openid}/files",
                group_openid=kwargs["group_openid"],
            )
            result = await self.bot.api._http.request(route, json=payload)
        else:
            raise ValueError("Invalid upload parameters")

        if not isinstance(result, dict):
            raise RuntimeError(
                f"Failed to upload image, response is not dict: {result}"
            )

        return Media(
            file_uuid=result["file_uuid"],
            file_info=result["file_info"],
            ttl=result.get("ttl", 0),
        )

    async def upload_group_and_c2c_media(
        self,
        file_source: str,
        file_type: int,
        srv_send_msg: bool = False,
        file_name: str | None = None,
        **kwargs,
    ) -> Media | None:
        """上传媒体文件"""
        # 构建基础payload
        payload = {"file_type": file_type, "srv_send_msg": srv_send_msg}
        if file_name:
            payload["file_name"] = file_name

        # 处理文件数据
        if os.path.exists(file_source):
            # 读取本地文件
            async with aiofiles.open(file_source, "rb") as f:
                file_content = await f.read()
                # use base64 encode
                payload["file_data"] = base64.b64encode(file_content).decode("utf-8")
        else:
            # 使用URL
            payload["url"] = file_source

        # 添加接收者信息和确定路由
        if "openid" in kwargs:
            payload["openid"] = kwargs["openid"]
            route = Route("POST", "/v2/users/{openid}/files", openid=kwargs["openid"])
        elif "group_openid" in kwargs:
            payload["group_openid"] = kwargs["group_openid"]
            route = Route(
                "POST",
                "/v2/groups/{group_openid}/files",
                group_openid=kwargs["group_openid"],
            )
        else:
            return None

        try:
            # 使用底层HTTP请求
            result = await self.bot.api._http.request(route, json=payload)

            if result:
                if not isinstance(result, dict):
                    logger.error(f"上传文件响应格式错误: {result}")
                    return None

                return Media(
                    file_uuid=result["file_uuid"],
                    file_info=result["file_info"],
                    ttl=result.get("ttl", 0),
                )
        except Exception as e:
            logger.error(f"上传请求错误: {e}")

        return None

    async def post_c2c_message(
        self,
        openid: str,
        msg_type: int = 0,
        content: str | None = None,
        embed: message.Embed | None = None,
        ark: message.Ark | None = None,
        message_reference: message.Reference | None = None,
        media: message.Media | None = None,
        msg_id: str | None = None,
        msg_seq: int | None = 1,
        event_id: str | None = None,
        markdown: message.MarkdownPayload | None = None,
        keyboard: message.Keyboard | None = None,
        stream: dict | None = None,
    ) -> message.Message:
        payload = locals()
        payload.pop("self", None)
        # QQ API does not accept stream.id=None; remove it when not yet assigned
        if "stream" in payload and payload["stream"] is not None:
            stream_data = dict(payload["stream"])
            if stream_data.get("id") is None:
                stream_data.pop("id", None)
            payload["stream"] = stream_data
        route = Route("POST", "/v2/users/{openid}/messages", openid=openid)
        result = await self.bot.api._http.request(route, json=payload)

        if result is None:
            logger.warning("[QQOfficial] post_c2c_message: API 返回 None，跳过本次发送")
            return None
        if not isinstance(result, dict):
            logger.error(f"[QQOfficial] post_c2c_message: 响应不是 dict: {result}")
            return None

        return message.Message(**result)

    @staticmethod
    async def _parse_to_qqofficial(message: MessageChain):
        plain_text = ""
        image_base64 = None  # only one img supported
        image_file_path = None
        record_file_path = None
        video_file_source = None
        file_source = None
        file_name = None
        for i in message.chain:
            if isinstance(i, Plain):
                plain_text += i.text
            elif isinstance(i, Image) and not image_base64:
                if i.file and i.file.startswith("file:///"):
                    image_base64 = file_to_base64(i.file[8:])
                    image_file_path = i.file[8:]
                elif i.file and i.file.startswith("http"):
                    image_file_path = await download_image_by_url(i.file)
                    image_base64 = file_to_base64(image_file_path)
                elif i.file and i.file.startswith("base64://"):
                    image_base64 = i.file
                elif i.file:
                    image_base64 = file_to_base64(i.file)
                else:
                    raise ValueError("Unsupported image file format")
                image_base64 = image_base64.removeprefix("base64://")
            elif isinstance(i, Record):
                if i.file:
                    record_wav_path = await i.convert_to_file_path()  # wav 路径
                    temp_dir = get_astrbot_temp_path()
                    record_tecent_silk_path = os.path.join(
                        temp_dir,
                        f"qqofficial_{uuid.uuid4()}.silk",
                    )
                    try:
                        duration = await wav_to_tencent_silk(
                            record_wav_path,
                            record_tecent_silk_path,
                        )
                        if duration > 0:
                            record_file_path = record_tecent_silk_path
                        else:
                            record_file_path = None
                            logger.error("转换音频格式时出错：音频时长不大于0")
                    except Exception as e:
                        logger.error(f"处理语音时出错: {e}")
                        record_file_path = None
            elif isinstance(i, Video) and not video_file_source:
                if i.file.startswith("file:///"):
                    video_file_source = i.file[8:]
                else:
                    video_file_source = i.file
            elif isinstance(i, File) and not file_source:
                file_name = i.name
                if i.file_:
                    file_path = i.file_
                    if file_path.startswith("file:///"):
                        file_path = file_path[8:]
                    elif file_path.startswith("file://"):
                        file_path = file_path[7:]
                    file_source = file_path
                elif i.url:
                    file_source = i.url
            else:
                logger.debug(f"qq_official 忽略 {i.type}")
        return (
            plain_text,
            image_base64,
            image_file_path,
            record_file_path,
            video_file_source,
            file_source,
            file_name,
        )
