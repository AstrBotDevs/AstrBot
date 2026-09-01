import asyncio
import base64
import copy
import logging
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

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
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from astrbot import logger
from astrbot.core.message.components import At, File, Image, Plain, Record, Video
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform import AstrBotMessage, Group, PlatformMetadata
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.send_result import PlatformSendResult
from astrbot.core.platform.sources.qqofficial.qqofficial_chunked_upload import (
    QQOFFICIAL_CHUNKED_UPLOAD_THRESHOLD,
    QQOfficialChunkedUploader,
)
from astrbot.core.utils.error_redaction import safe_error
from astrbot.core.utils.media_utils import MediaResolver, file_uri_to_path, is_file_uri


class APIReturnNoneError(Exception):
    pass


@dataclass(slots=True)
class _QQOfficialMedia:
    """Rich-media values extracted from one outgoing message chain."""

    image_base64: str | None
    image_path: str | None
    record_file_path: str | None
    video_file_source: str | None
    file_source: str | None
    file_name: str | None

    def has_group_or_c2c_media(self) -> bool:
        """Return whether this requires the v2 media upload API."""
        return bool(
            self.image_base64
            or self.record_file_path
            or self.video_file_source
            or self.file_source
        )


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


def _qqofficial_retry(max_attempts: int = 5):
    """Retry decorator for QQ Official API transient errors (HTTP 500/504)"""
    return retry(
        retry=retry_if_exception_type(
            (
                botpy.errors.ServerError,
                botpy.errors.SequenceNumberError,
                OSError,
                asyncio.TimeoutError,
                APIReturnNoneError,
            )
        ),
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )


_QQOFFICIAL_SEND_API_ERRORS = (
    botpy.errors.ForbiddenError,
    botpy.errors.MethodNotAllowedError,
    botpy.errors.NotFoundError,
    botpy.errors.SequenceNumberError,
    botpy.errors.ServerError,
)


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
        self._bot = bot
        self.send_buffer = None

    async def get_group(self, group_id: str | None = None, **kwargs) -> Group | None:
        """Get QQ group or guild-channel information for this event.

        QQ group metadata is restricted to allowlisted bots. When the API is
        unavailable, the basic group object attached to the incoming message is
        returned so callers can still rely on the group identifier.

        Args:
            group_id: Optional QQ group OpenID or guild channel ID. Defaults to
                the current message group identifier.
            **kwargs: Reserved for compatibility with the base event API.

        Returns:
            Available group information, or ``None`` for a private event without
            an explicit group identifier.
        """
        del kwargs
        target_id = group_id or self.message_obj.group_id
        if not target_id:
            return None

        group = Group.from_inbound(self.message_obj.group, target_id)
        source = self.message_obj.raw_message

        if isinstance(source, botpy.message.GroupMessage):
            try:
                route = Route(
                    "GET",
                    "/v2/groups/{group_openid}/info",
                    group_openid=target_id,
                )
                payload = await self._bot.api._http.request(route)
                if not isinstance(payload, dict):
                    logger.warning(
                        "[QQOfficial] Group info API returned an invalid response for %s",
                        target_id,
                    )
                    return group

                group.group_name = payload.get("group_name") or group.group_name
                member_count = payload.get(
                    "group_member_num",
                    payload.get("member_count"),
                )
                if member_count is not None:
                    try:
                        group.member_count = int(member_count)
                    except TypeError, ValueError:
                        logger.warning(
                            "[QQOfficial] Group info API returned an invalid member_count for %s",
                            target_id,
                        )
            except Exception as exc:
                logger.warning(
                    "[QQOfficial] Failed to get group info for %s: %s",
                    target_id,
                    safe_error("", exc),
                )
            return group

        if isinstance(source, botpy.message.Message):
            try:
                channel = await self._bot.api.get_channel(target_id)
                if not isinstance(channel, dict):
                    logger.warning(
                        "[QQOfficial] Channel API returned an invalid response for %s",
                        target_id,
                    )
                    return group

                group.group_name = channel.get("name") or group.group_name
                guild_id = channel.get("guild_id") or getattr(source, "guild_id", None)
                if guild_id:
                    guild = await self._bot.api.get_guild(str(guild_id))
                    if isinstance(guild, dict):
                        group.group_avatar = guild.get("icon") or group.group_avatar
                        group.group_owner = guild.get("owner_id") or group.group_owner
                        member_count = guild.get("member_count")
                        if member_count is not None:
                            try:
                                group.member_count = int(member_count)
                            except TypeError, ValueError:
                                logger.warning(
                                    "[QQOfficial] Guild API returned an invalid member_count for %s",
                                    guild_id,
                                )
            except Exception as exc:
                logger.warning(
                    "[QQOfficial] Failed to get channel info for %s: %s",
                    target_id,
                    safe_error("", exc),
                )
            return group

        return group

    async def send(self, message: MessageChain) -> PlatformSendResult | None:
        self.send_buffer = message
        return await self._post_send()

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
                    # Non-C2C output is sent at the end. Keep an owned copy
                    # because some stream generators reuse their chain object.
                    self._append_stream_delta(chain)
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

                # Keep an owned copy: a reused stream delta must not mutate
                # previously buffered text.
                self._append_stream_delta(chain)

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

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"发送流式消息时出错: {e}", exc_info=True)
            # 避免累计内容在异常后被整包重复发送：仅清理缓存，不做非流式整包兜底
            # 如需兜底，应该只发送未发送 delta（后续可继续优化）
            self.send_buffer = None
            return self._streaming_send_result(status="unknown")

        if isinstance(ret, PlatformSendResult):
            return ret
        return self._streaming_send_result(status="skipped")

    def _streaming_send_result(
        self,
        *,
        status: Literal["unknown", "skipped"],
    ) -> PlatformSendResult:
        """Build a receipt when no final QQ response object is available."""
        platform_meta = getattr(self, "platform_meta", None)
        route_identity = getattr(self, "route_identity", None)
        return PlatformSendResult(
            platform_id=getattr(platform_meta, "id", ""),
            success=False,
            target=getattr(route_identity, "target_id", ""),
            status=status,
            error_message=(
                "QQ streaming outcome unknown" if status == "unknown" else None
            ),
        )

    def _append_stream_delta(self, chain: MessageChain) -> None:
        """Append a stream delta without retaining caller-owned components.

        Some stream generators mutate and yield the same ``MessageChain`` more
        than once. Holding that chain by reference corrupts the accumulated
        response (most visibly by losing its leading text).
        """
        if not self.send_buffer:
            self.send_buffer = MessageChain(
                use_t2i_=chain.use_t2i_,
                use_markdown_=chain.use_markdown_,
                type=chain.type,
            )
        for component in chain.chain:
            if isinstance(component, Plain):
                self.send_buffer.chain.append(Plain(text=component.text))
            else:
                self.send_buffer.chain.append(copy.deepcopy(component))

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

    @staticmethod
    def _split_message_chain_by_media(message: MessageChain) -> list[MessageChain]:
        chunks: list[MessageChain] = []
        current_chain = []
        current_has_media = False

        for component in message.chain:
            is_media = isinstance(component, Image | Record | Video | File)
            if is_media and current_has_media:
                chunks.append(
                    MessageChain(
                        chain=current_chain,
                        use_t2i_=message.use_t2i_,
                        type=message.type,
                    )
                )
                current_chain = []
                current_has_media = False

            current_chain.append(component)
            current_has_media = current_has_media or is_media

        if current_chain or not message.chain:
            chunks.append(
                MessageChain(
                    chain=current_chain,
                    use_t2i_=message.use_t2i_,
                    type=message.type,
                )
            )

        return chunks

    async def _post_send(self, stream: dict | None = None):
        if not self.send_buffer:
            return None

        message_chains = self._split_message_chain_by_media(self.send_buffer)
        stream_for_chain = stream if len(message_chains) == 1 else None

        ret = None
        for message_chain in message_chains:
            ret = await self._post_send_one(message_chain, stream_for_chain)

        self.send_buffer = None

        return ret

    def _build_base_payload(self, plain_text: str, source: object) -> dict:
        """Build the common QQ payload before route-specific media handling."""
        if getattr(self.send_buffer, "use_markdown_", None) is False:
            payload: dict = {
                "content": plain_text,
                "msg_type": 0,
                "msg_id": self.message_obj.message_id,
            }
        else:
            payload = {
                "markdown": MarkdownPayload(content=plain_text) if plain_text else None,
                "msg_type": 2,
                "msg_id": self.message_obj.message_id,
            }
        if not isinstance(source, botpy.message.Message | botpy.message.DirectMessage):
            payload["msg_seq"] = random.randint(1, 10000)
        return payload

    @staticmethod
    def _media_upload_target(source: object) -> dict[str, str] | None:
        """Select the v2 upload target for group and C2C messages."""
        if isinstance(source, botpy.message.GroupMessage):
            if not source.group_openid:
                logger.error("[QQOfficial] GroupMessage 缺少 group_openid")
                return None
            return {"group_openid": source.group_openid}
        if isinstance(source, botpy.message.C2CMessage):
            return {"openid": source.author.user_openid}
        return None

    @staticmethod
    def _write_media_payload(payload: dict, media: Media, plain_text: str) -> None:
        """Make an uploaded v2 media item the message payload body."""
        payload["media"] = media
        payload["msg_type"] = 7
        payload.pop("markdown", None)
        payload["content"] = plain_text or None

    async def _apply_group_or_c2c_media(
        self,
        payload: dict,
        plain_text: str,
        media: _QQOfficialMedia,
        upload_target: dict[str, str],
    ) -> None:
        """Upload rich media in the established image-to-file priority order."""
        if media.image_base64:
            if group_openid := upload_target.get("group_openid"):
                uploaded = await self.upload_group_and_c2c_image(
                    media.image_base64,
                    self.IMAGE_FILE_TYPE,
                    group_openid=group_openid,
                )
            else:
                uploaded = await self.upload_group_and_c2c_image(
                    media.image_base64,
                    self.IMAGE_FILE_TYPE,
                    openid=upload_target["openid"],
                )
            self._write_media_payload(payload, uploaded, plain_text)

        for source, file_type, file_name in (
            (media.record_file_path, self.VOICE_FILE_TYPE, None),
            (media.video_file_source, self.VIDEO_FILE_TYPE, None),
            (media.file_source, self.FILE_FILE_TYPE, media.file_name),
        ):
            if not source:
                continue
            if group_openid := upload_target.get("group_openid"):
                uploaded = await self.upload_group_and_c2c_media(
                    source,
                    file_type,
                    file_name=file_name,
                    group_openid=group_openid,
                )
            else:
                uploaded = await self.upload_group_and_c2c_media(
                    source,
                    file_type,
                    file_name=file_name,
                    openid=upload_target["openid"],
                )
            if uploaded:
                self._write_media_payload(payload, uploaded, plain_text)

    async def _send_c2c_payload(
        self,
        openid: str,
        payload: dict,
        plain_text: str,
        stream: dict | None,
    ):
        """Send a C2C payload, passing stream data only to the v2 stream API."""
        if stream:

            async def send_func(retry_payload: dict):
                return await self.post_c2c_message(
                    openid=openid,
                    **retry_payload,
                    stream=stream,
                )
        else:

            async def send_func(retry_payload: dict):
                return await self.post_c2c_message(
                    openid=openid,
                    **retry_payload,
                )

        return await self._send_with_markdown_fallback(
            send_func=send_func,
            payload=payload,
            plain_text=plain_text,
            stream=stream,
        )

    async def _post_send_one(
        self,
        message_to_send: MessageChain,
        stream: dict | None = None,
    ):
        if not message_to_send:
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

        plain_text, *media_values = await QQOfficialMessageEvent._parse_to_qqofficial(
            message_to_send
        )
        media = _QQOfficialMedia(*media_values)
        if media.record_file_path:
            self.track_temporary_local_file(media.record_file_path)
        if (
            not plain_text
            and not media.image_path
            and not media.has_group_or_c2c_media()
        ):
            return None

        if stream and media.has_group_or_c2c_media():
            logger.debug("[QQOfficial] 检测到富媒体，降级为非流式发送。")
            stream = None
        if (
            stream
            and stream.get("state") == 10
            and plain_text
            and not plain_text.endswith("\n")
        ):
            plain_text += "\n"

        payload = self._build_base_payload(plain_text, source)
        if isinstance(source, botpy.message.GroupMessage | botpy.message.C2CMessage):
            upload_target = self._media_upload_target(source)
            if upload_target is None:
                return None
            await self._apply_group_or_c2c_media(
                payload,
                plain_text,
                media,
                upload_target,
            )
            if isinstance(source, botpy.message.GroupMessage):
                group_openid = upload_target["group_openid"]
                ret = await self._send_with_markdown_fallback(
                    send_func=lambda retry_payload: self._bot.api.post_group_message(
                        group_openid=group_openid,
                        **retry_payload,
                    ),
                    payload=payload,
                    plain_text=plain_text,
                    stream=stream,
                )
            else:
                ret = await self._send_c2c_payload(
                    source.author.user_openid,
                    payload,
                    plain_text,
                    stream,
                )
                logger.debug(f"Message sent to C2C: {ret}")
        elif isinstance(source, botpy.message.Message):
            if media.image_path:
                payload["file_image"] = media.image_path
            payload.pop("msg_type", None)
            ret = await self._send_with_markdown_fallback(
                send_func=lambda retry_payload: self._bot.api.post_message(
                    channel_id=source.channel_id,
                    **retry_payload,
                ),
                payload=payload,
                plain_text=plain_text,
                stream=stream,
            )
        else:
            if media.image_path:
                payload["file_image"] = media.image_path
            payload.pop("msg_type", None)
            ret = await self._send_with_markdown_fallback(
                send_func=lambda retry_payload: self._bot.api.post_dms(
                    guild_id=source.guild_id,
                    **retry_payload,
                ),
                payload=payload,
                plain_text=plain_text,
                stream=stream,
            )

        send_result = await super().send(message_to_send)
        if not isinstance(send_result, PlatformSendResult):
            return send_result
        message_id = self._extract_response_message_id(ret)
        if message_id is not None:
            send_result.message_id = str(message_id)
        return send_result

    async def _send_with_markdown_fallback(
        self,
        send_func,
        payload: dict,
        plain_text: str,
        stream: dict | None = None,
    ):
        try:
            return await send_func(payload)
        except _QQOFFICIAL_SEND_API_ERRORS as err:
            logger.info("[QQOfficial] 回复消息失败: %s, 尝试使用主动发送接口。", err)
            if payload.get("msg_id"):
                fallback_payload = payload.copy()
                fallback_payload.pop("msg_id", None)
                try:
                    ret = await send_func(fallback_payload)
                    logger.info("[QQOfficial] 使用主动发送接口发送成功。")
                    return ret
                except _QQOFFICIAL_SEND_API_ERRORS as fallback_err:
                    err = fallback_err
                    payload = fallback_payload

            if not isinstance(err, botpy.errors.ServerError):
                raise

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

        @_qqofficial_retry()
        async def _do_upload():
            if "openid" in kwargs:
                payload["openid"] = kwargs["openid"]
                route = Route(
                    "POST", "/v2/users/{openid}/files", openid=kwargs["openid"]
                )
            elif "group_openid" in kwargs:
                payload["group_openid"] = kwargs["group_openid"]
                route = Route(
                    "POST",
                    "/v2/groups/{group_openid}/files",
                    group_openid=kwargs["group_openid"],
                )
            else:
                raise ValueError("Invalid upload parameters")

            result = await self._bot.api._http.request(route, json=payload)
            if result is None:
                err_msg = "上传图片API返回None，触发重试"
                raise APIReturnNoneError(err_msg)
            return result

        try:
            result = await _do_upload()
        except APIReturnNoneError:
            logger.warning(f"上传图片API返回None，共尝试5次后放弃: {payload}")
            raise

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
    ) -> Media:
        """Upload media to a QQ group or C2C session.

        Args:
            file_source: Local file path or remote URL to upload.
            file_type: QQ media type identifier.
            srv_send_msg: Whether QQ should send the media immediately.
            file_name: Optional display name for the uploaded file.
            **kwargs: Recipient identifier as ``openid`` or ``group_openid``.

        Returns:
            Metadata for the uploaded media.

        Raises:
            ValueError: No supported recipient identifier was provided.
            Exception: The upload request fails or returns an invalid response.
        """
        local_file = Path(file_source)
        if (
            local_file.is_file()
            and local_file.stat().st_size > QQOFFICIAL_CHUNKED_UPLOAD_THRESHOLD
        ):
            openid = kwargs.get("openid")
            group_openid = None if openid else kwargs.get("group_openid")
            if not openid and not isinstance(group_openid, str):
                raise ValueError("Invalid upload parameters")
            uploader = QQOfficialChunkedUploader(self._bot.api._http)
            if openid:
                return await uploader.upload_c2c(
                    file_path=local_file,
                    file_type=file_type,
                    file_name=file_name or local_file.name,
                    user_openid=openid,
                    srv_send_msg=srv_send_msg,
                )
            assert isinstance(group_openid, str)
            return await uploader.upload_group(
                file_path=local_file,
                file_type=file_type,
                file_name=file_name or local_file.name,
                group_openid=group_openid,
                srv_send_msg=srv_send_msg,
            )

        # 构建基础payload
        payload: dict = {"file_type": file_type, "srv_send_msg": srv_send_msg}
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
            raise ValueError("Invalid upload parameters")

        @_qqofficial_retry()
        async def _do_upload():
            result = await self._bot.api._http.request(route, json=payload)
            if result is None:
                err_msg = "上传文件API返回None，触发重试"
                raise APIReturnNoneError(err_msg)
            return result

        try:
            result = await _do_upload()
        except APIReturnNoneError:
            logger.warning("Media upload API returned None after 5 attempts.")
            raise
        except botpy.errors.ServerError, botpy.errors.SequenceNumberError:
            logger.error("Media upload failed after 5 attempts.")
            raise
        except Exception as exc:
            logger.error("Media upload request failed: %s", safe_error("", exc))
            raise

        if not isinstance(result, dict):
            raise RuntimeError("Failed to upload media: invalid response.")

        return Media(
            file_uuid=result["file_uuid"],
            file_info=result["file_info"],
            ttl=result.get("ttl", 0),
        )

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
    ) -> message.Message | None:
        payload = locals()
        payload.pop("self", None)
        if payload.get("msg_id") is None:
            payload.pop("msg_id", None)
        # QQ API does not accept stream.id=None; remove it when not yet assigned
        if "stream" in payload and payload["stream"] is not None:
            stream_data = dict(payload["stream"])
            if stream_data.get("id") is None:
                stream_data.pop("id", None)
            payload["stream"] = stream_data
        route = Route("POST", "/v2/users/{openid}/messages", openid=openid)

        retry_times = 3

        @_qqofficial_retry(retry_times)
        async def _do_request():
            result = await self._bot.api._http.request(route, json=payload)
            if result is None:
                err_msg = "发送消息API返回None，触发重试"
                raise APIReturnNoneError(err_msg)
            return result

        result = None
        try:
            result = await _do_request()
        except APIReturnNoneError:
            logger.warning(
                f"[QQOfficial] post_c2c_message: 发送消息失败，API 返回 None，共尝试{retry_times}次后放弃"
            )
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
                if not i.file:
                    raise ValueError("Unsupported image file format")
                image_is_local = is_file_uri(i.file)
                if not image_is_local:
                    try:
                        image_is_local = os.path.exists(i.file)
                    except OSError:
                        image_is_local = False
                resolver = MediaResolver(i.file, media_type="image")
                if image_is_local:
                    async with resolver.as_path() as resolved:
                        image_file_path = str(resolved.path.resolve())
                        image_base64 = resolved.to_base64()
                else:
                    image_base64 = await resolver.to_base64()
            elif isinstance(i, Record):
                record_ref = i.url or i.file
                if record_ref:
                    try:
                        record_file_path = await MediaResolver(
                            record_ref,
                            media_type="audio",
                            default_suffix=".wav",
                        ).to_path(
                            target_format="tencent_silk",
                        )
                    except Exception as e:
                        logger.error(f"处理语音时出错: {e}")
                        record_file_path = None
            elif isinstance(i, Video) and not video_file_source:
                if is_file_uri(i.file):
                    video_file_source = file_uri_to_path(i.file)
                else:
                    video_file_source = i.file
            elif isinstance(i, File) and not file_source:
                file_name = i.name
                if i.file_:
                    file_path = i.file_
                    if is_file_uri(file_path):
                        file_path = file_uri_to_path(file_path)
                    file_source = file_path
                elif i.url:
                    file_source = i.url
            elif isinstance(i, At):
                qq_id = getattr(i, "qq", "")
                if qq_id and qq_id != "all":
                    plain_text += f"<@{qq_id}>"
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
