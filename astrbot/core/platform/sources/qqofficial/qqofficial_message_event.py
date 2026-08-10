import asyncio
import base64
import copy
import hashlib
import logging
import os
import random
from typing import cast

import aiofiles
import aiohttp
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

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import File, Image, Plain, Record, Video
from astrbot.api.platform import AstrBotMessage, PlatformMetadata
from astrbot.core.utils.media_utils import MediaResolver, file_uri_to_path, is_file_uri

# 大文件走 QQ 官方分片上传（inline base64 上传约 10MB 上限，超出返回 413）。
_QQOFFICIAL_CHUNKED_UPLOAD_THRESHOLD = 10 * 1024 * 1024
_QQOFFICIAL_MD5_10M_SIZE = 10_002_432
_QQOFFICIAL_CHUNKED_API_TIMEOUT = 300
_QQOFFICIAL_PART_PUT_TIMEOUT = 300
_QQOFFICIAL_PART_PUT_MAX_RETRIES = 2
_QQOFFICIAL_PART_FINISH_DEFAULT_TIMEOUT = 120.0
_QQOFFICIAL_PART_FINISH_MAX_TIMEOUT = 600.0
_QQOFFICIAL_PART_FINISH_RETRY_INTERVAL = 1.0
_QQOFFICIAL_COMPLETE_MAX_RETRIES = 2
_QQOFFICIAL_BIZ_PART_RETRYABLE = 40093001
_QQOFFICIAL_BIZ_DAILY_LIMIT = 40093002


class QQMediaUploadError(Exception):
    """Raised when a QQ media upload fails; the caller may degrade to text."""


class QQApiError(Exception):
    """QQ API error carrying the platform error code.

    Args:
        code: Platform error code (e.g. 40093001 for retryable part finish).
        message: Human-readable error message from the platform.
        status: HTTP status code.
    """

    def __init__(self, code, message, status):
        self.code = code
        self.message = message
        self.status = status
        super().__init__(f"{message} (code={code}, http={status})")


def _compute_file_hashes(file_path: str) -> dict:
    """Compute md5, sha1 and md5_10m hashes in a single pass.

    md5_10m covers the first 10,002,432 bytes and is used by the platform for
    deduplication; for smaller files it equals the full-file md5.
    """
    md5 = hashlib.md5()
    sha1 = hashlib.sha1()
    md5_10m = hashlib.md5()
    need_10m = os.path.getsize(file_path) > _QQOFFICIAL_MD5_10M_SIZE
    bytes_read = 0

    with open(file_path, "rb") as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            md5.update(chunk)
            sha1.update(chunk)
            if need_10m:
                remaining = _QQOFFICIAL_MD5_10M_SIZE - bytes_read
                if remaining > 0:
                    md5_10m.update(chunk[:remaining])
            bytes_read += len(chunk)

    full_md5 = md5.hexdigest()
    return {
        "md5": full_md5,
        "sha1": sha1.hexdigest(),
        "md5_10m": md5_10m.hexdigest() if need_10m else full_md5,
    }


def _read_file_chunk(file_path: str, offset: int, length: int) -> bytes:
    """Read exactly *length* bytes from *file_path* starting at *offset*.

    Raises:
        IOError: If fewer bytes than expected are read.
    """
    with open(file_path, "rb") as fh:
        fh.seek(offset)
        data = fh.read(length)
        if len(data) != length:
            raise OSError(
                f"Short read from {file_path}: expected {length} bytes at "
                f"offset {offset}, got {len(data)}"
            )
        return data


def _parse_upload_prepare_response(
    raw: dict,
) -> tuple[str, int, list[dict], int, float]:
    """Parse upload_prepare response into upload parameters.

    Args:
        raw: Raw JSON response (may wrap fields under "data").

    Returns:
        Tuple of (upload_id, block_size, parts, concurrency, retry_timeout).

    Raises:
        QQMediaUploadError: If required fields are missing.
    """
    src = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    upload_id = str(src.get("upload_id") or "")
    block_size = int(src.get("block_size") or 0)
    parts = src.get("parts") or src.get("part_list") or []
    if not upload_id or not block_size or not isinstance(parts, list) or not parts:
        raise QQMediaUploadError(
            f"upload_prepare response missing required fields: {str(raw)[:200]}"
        )
    config = src.get("upload_config") or {}
    concurrency = int(config.get("concurrency") or src.get("concurrency") or 1)
    retry_timeout = float(
        config.get("retry_timeout") or src.get("retry_timeout") or 0.0
    )
    return upload_id, block_size, parts, concurrency, retry_timeout


class APIReturnNoneError(Exception):
    pass


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
                    # 非 C2C 场景：直接累积，最后统一发（拷贝 delta，避免引用丢首字）
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

                # 累积内容（拷贝，避免上游复用 MessageChain 改写 buffer）
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

        except Exception as e:
            logger.error(f"发送流式消息时出错: {e}", exc_info=True)
            # 避免累计内容在异常后被整包重复发送：仅清理缓存，不做非流式整包兜底
            # 如需兜底，应该只发送未发送 delta（后续可继续优化）
            self.send_buffer = None

        return None

    def _append_stream_delta(self, chain: MessageChain) -> None:
        """Append stream delta into an owned buffer (copy components).

        Holding the yielded MessageChain by reference drops leading characters
        when upstream reuses/mutates the same chain between yields. Non-Plain
        components are deep-copied for the same reason.
        """
        if not self.send_buffer:
            self.send_buffer = MessageChain(
                use_t2i_=chain.use_t2i_,
                use_markdown_=chain.use_markdown_,
                type=chain.type,
            )
        for comp in chain.chain:
            if isinstance(comp, Plain):
                # Preserve original text value (do not coerce falsy with `or ""`).
                self.send_buffer.chain.append(Plain(text=comp.text))
            else:
                self.send_buffer.chain.append(copy.deepcopy(comp))

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

        (
            plain_text,
            image_base64,
            image_path,
            record_file_path,
            video_file_source,
            file_source,
            file_name,
        ) = await QQOfficialMessageEvent._parse_to_qqofficial(message_to_send)

        # C2C 流式仅用于文本分片，富媒体时降级为普通发送，避免平台侧流式校验报错。
        if stream and (
            image_base64 or record_file_path or video_file_source or file_source
        ):
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

        # 根据消息链的 use_markdown_ 标记决定发送模式
        use_md = getattr(self.send_buffer, "use_markdown_", None)
        if use_md is False:
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

        ret = None

        match source:
            case botpy.message.GroupMessage():
                if not source.group_openid:
                    logger.error("[QQOfficial] GroupMessage 缺少 group_openid")
                    return None

                try:
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
                except QQMediaUploadError as e:
                    logger.error("[QQOfficial] 媒体上传失败，降级为纯文本发送: %s", e)
                    plain_text = self._degrade_media_payload_to_text(
                        payload, plain_text, e, stream
                    )
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
                try:
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
                except QQMediaUploadError as e:
                    logger.error("[QQOfficial] 媒体上传失败，降级为纯文本发送: %s", e)
                    plain_text = self._degrade_media_payload_to_text(
                        payload, plain_text, e, stream
                    )
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

        await super().send(message_to_send)

        return ret

    @staticmethod
    def _degrade_media_payload_to_text(
        payload: dict,
        plain_text: str,
        error: Exception,
        stream: dict | None = None,
    ) -> str:
        """Convert a media payload into a plain-text payload when upload fails.

        If the chain carries no text, a short explanation is used so the user
        still receives a reply instead of nothing.
        """
        if not plain_text:
            plain_text = (
                f"文件已生成，但发送到 QQ 失败：{error}。"
                "文件仍保存在服务器上，可联系管理员获取。"
            )
        payload.pop("markdown", None)
        payload.pop("media", None)
        payload["msg_type"] = 0
        payload["content"] = plain_text or None
        if stream:
            content = cast(str, payload.get("content") or "")
            if content and not content.endswith("\n"):
                payload["content"] = content + "\n"
        return plain_text

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

            # 纯文本兜底：markdown 或媒体消息发送失败时降级为 msg_type=0 纯文本。
            # 覆盖长任务超过被动回复有效期、以及 40034011 无效 markdown content 等场景。
            if plain_text and (payload.get("markdown") or payload.get("media")):
                content_payload = payload.copy()
                content_payload.pop("markdown", None)
                content_payload.pop("media", None)
                content_payload["content"] = plain_text
                content_payload["msg_type"] = 0
                if stream:
                    content_value = cast(str, content_payload.get("content") or "")
                    if content_value and not content_value.endswith("\n"):
                        content_payload["content"] = content_value + "\n"
                try:
                    ret = await send_func(content_payload)
                    logger.info("[QQOfficial] 主动发送接口（纯文本）发送成功。")
                    return ret
                except _QQOFFICIAL_SEND_API_ERRORS as content_err:
                    err = content_err
                    payload = content_payload

            # 媒体消息发送失败且无文本时，发送失败说明，避免用户收不到任何回复。
            if not plain_text and (
                payload.get("media") or payload.get("msg_type") == 7
            ):
                explanation = (
                    f"文件已生成，但发送到 QQ 失败：{err}。"
                    "文件仍保存在服务器上，可联系管理员获取。"
                )
                content_payload = payload.copy()
                content_payload.pop("markdown", None)
                content_payload.pop("media", None)
                content_payload["content"] = explanation
                content_payload["msg_type"] = 0
                if stream:
                    content_value = cast(str, content_payload.get("content") or "")
                    if content_value and not content_value.endswith("\n"):
                        content_payload["content"] = content_value + "\n"
                try:
                    ret = await send_func(content_payload)
                    logger.info("[QQOfficial] 媒体发送失败，已发送文本说明。")
                    return ret
                except _QQOFFICIAL_SEND_API_ERRORS as content_err:
                    err = content_err
                    payload = content_payload

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

            result = await self.bot.api._http.request(route, json=payload)
            if result is None:
                err_msg = "上传图片API返回None，触发重试"
                raise APIReturnNoneError(err_msg)
            return result

        try:
            result = await _do_upload()
        except APIReturnNoneError:
            logger.warning(f"上传图片API返回None，共尝试5次后放弃: {payload}")
            raise QQMediaUploadError("上传图片失败：API 返回 None") from None
        except Exception as e:
            logger.error(f"上传图片失败: {e}")
            raise QQMediaUploadError(f"上传图片失败：{e}") from e

        if not isinstance(result, dict):
            raise QQMediaUploadError(f"上传图片响应格式错误: {result}")

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
        """Upload a media file, using the chunked flow for large local files.

        Args:
            file_source: Local file path or public URL.
            file_type: QQ media type (1=image, 2=video, 3=voice, 4=file).
            srv_send_msg: Whether to send the message during upload.
            file_name: File name reported to the platform.
            **kwargs: Must contain either ``openid`` or ``group_openid``.

        Returns:
            The uploaded Media object, or None when the destination is invalid.

        Raises:
            QQMediaUploadError: If the upload fails.
        """
        # 大文件（>10MB）走分片上传，避免 inline base64 触发 413 Request Entity Too Large。
        if (
            os.path.exists(file_source)
            and os.path.getsize(file_source) > _QQOFFICIAL_CHUNKED_UPLOAD_THRESHOLD
        ):
            logger.info(
                "[QQOfficial] 文件超过 %dMB，使用分片上传: %s",
                _QQOFFICIAL_CHUNKED_UPLOAD_THRESHOLD // (1024 * 1024),
                file_source,
            )
            return await self._chunked_upload_media(
                file_source,
                file_type,
                file_name=file_name or os.path.basename(file_source),
                openid=kwargs.get("openid"),
                group_openid=kwargs.get("group_openid"),
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
            return None

        @_qqofficial_retry()
        async def _do_upload():
            result = await self.bot.api._http.request(route, json=payload)
            if result is None:
                err_msg = "上传文件API返回None，触发重试"
                raise APIReturnNoneError(err_msg)
            return result

        try:
            result = await _do_upload()
        except APIReturnNoneError:
            logger.warning(f"上传文件API返回None，共尝试5次后放弃: {file_source}")
            raise QQMediaUploadError("上传文件失败：API 返回 None") from None
        except Exception as e:
            logger.error(f"上传媒体文件失败: {file_source}: {e}")
            raise QQMediaUploadError(f"上传文件失败：{e}") from e

        if not isinstance(result, dict):
            raise QQMediaUploadError(f"上传文件响应格式错误: {result}")
        if not result.get("file_info"):
            raise QQMediaUploadError(f"上传文件响应缺少 file_info: {result}")

        return Media(
            file_uuid=result["file_uuid"],
            file_info=result["file_info"],
            ttl=result.get("ttl", 0),
        )

    async def _qq_api_request(
        self, method: str, path: str, body: dict, retries: int = 3
    ) -> dict:
        """Perform a QQ API request with bot auth headers.

        Args:
            method: HTTP method.
            path: API path with path parameters already substituted.
            body: JSON request body.
            retries: Number of attempts for transport errors.

        Returns:
            Parsed JSON response (dict).

        Raises:
            QQApiError: On non-2xx responses, carrying the platform error code.
            QQMediaUploadError: On non-JSON responses or transport failures.
        """
        http = self.bot.api._http
        url = Route(method, path).url
        last_exc = None
        for attempt in range(retries):
            try:
                async with http._session.request(
                    method,
                    url,
                    headers=http._headers,
                    json=body,
                    timeout=aiohttp.ClientTimeout(
                        total=_QQOFFICIAL_CHUNKED_API_TIMEOUT
                    ),
                ) as resp:
                    try:
                        raw = await resp.json(content_type=None)
                    except ValueError:
                        text = (await resp.text(errors="ignore"))[:300]
                        raise QQMediaUploadError(
                            f"QQ API {path} 返回非 JSON: {text}"
                        ) from None
                    if not isinstance(raw, dict):
                        raise QQMediaUploadError(
                            f"QQ API {path} 返回非 JSON: {str(raw)[:200]}"
                        )
                    if resp.status < 400:
                        return raw
                    raise QQApiError(raw.get("code"), raw.get("message"), resp.status)
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
                last_exc = e
                if attempt < retries - 1:
                    await asyncio.sleep(min(2**attempt, 8))
        raise QQMediaUploadError(f"QQ API {method} {path} 网络错误: {last_exc}")

    async def _chunked_upload_media(
        self,
        file_source: str,
        file_type: int,
        file_name: str,
        openid: str | None = None,
        group_openid: str | None = None,
    ) -> Media:
        """Upload a large local file via the QQ chunked upload flow.

        Flow: upload_prepare -> PUT parts -> upload_part_finish -> /files(upload_id).

        Args:
            file_source: Local path of the file to upload.
            file_type: QQ media type.
            file_name: File name reported to the platform.
            openid: C2C user openid.
            group_openid: Group openid.

        Returns:
            The uploaded Media object ready for msg_type=7.

        Raises:
            QQMediaUploadError: If any step of the chunked upload fails.
        """
        if not (openid or group_openid):
            raise QQMediaUploadError("分片上传缺少 openid/group_openid")

        loop = asyncio.get_running_loop()
        file_size = os.path.getsize(file_source)
        try:
            hashes = await loop.run_in_executor(None, _compute_file_hashes, file_source)
        except OSError as e:
            raise QQMediaUploadError(f"读取文件失败: {file_source}: {e}") from e

        base = f"/v2/users/{openid}" if openid else f"/v2/groups/{group_openid}"
        receiver_field = (
            {"openid": openid} if openid else {"group_openid": group_openid}
        )
        prepare_body = {
            "file_type": file_type,
            "file_name": file_name or os.path.basename(file_source),
            "file_size": file_size,
            "md5": hashes["md5"],
            "sha1": hashes["sha1"],
            "md5_10m": hashes["md5_10m"],
            **receiver_field,
        }
        logger.info(
            "[QQOfficial] 分片上传开始: file=%s size=%dMB type=%d",
            file_name,
            file_size // (1024 * 1024),
            file_type,
        )

        try:
            prepare = await self._qq_api_request(
                "POST", f"{base}/upload_prepare", prepare_body
            )
            upload_id, block_size, parts, concurrency, retry_timeout = (
                _parse_upload_prepare_response(prepare)
            )
        except QQApiError as e:
            if e.code == _QQOFFICIAL_BIZ_DAILY_LIMIT:
                raise QQMediaUploadError(
                    "上传失败：今日上传配额已达上限（40093002），请明天再试。"
                ) from e
            raise QQMediaUploadError(f"upload_prepare 失败: {e}") from e

        logger.info(
            "[QQOfficial] upload_prepare: upload_id=%s block_size=%d parts=%d",
            upload_id,
            block_size,
            len(parts),
        )
        sem = asyncio.Semaphore(max(1, min(concurrency, 4)))
        total_parts = len(parts)

        async def upload_part(part: dict) -> None:
            async with sem:
                await self._upload_one_part(
                    base,
                    receiver_field,
                    upload_id,
                    block_size,
                    file_source,
                    file_size,
                    part,
                    retry_timeout,
                    total_parts,
                )

        await asyncio.gather(*(upload_part(p) for p in parts))

        complete = await self._qq_api_request(
            "POST",
            f"{base}/files",
            {"upload_id": upload_id, **receiver_field},
            retries=_QQOFFICIAL_COMPLETE_MAX_RETRIES + 1,
        )
        if not isinstance(complete, dict) or not complete.get("file_info"):
            raise QQMediaUploadError(
                f"分片上传合并失败，响应缺少 file_info: {str(complete)[:200]}"
            )
        logger.info("[QQOfficial] 分片上传完成: %s", file_name)
        media = Media(file_info=complete["file_info"])
        if complete.get("file_uuid"):
            media["file_uuid"] = complete["file_uuid"]
        if complete.get("ttl"):
            media["ttl"] = complete["ttl"]
        return media

    async def _upload_one_part(
        self,
        base: str,
        receiver_field: dict,
        upload_id: str,
        block_size: int,
        file_source: str,
        file_size: int,
        part: dict,
        retry_timeout: float,
        total_parts: int,
    ) -> None:
        """PUT one part to its presigned URL, then acknowledge via part_finish."""
        part_index = int(part.get("part_index") or part.get("index") or 0)
        presigned_url = str(part.get("presigned_url") or part.get("url") or "")
        if not presigned_url:
            raise QQMediaUploadError(
                f"upload_prepare 分片缺少 presigned_url: {str(part)[:200]}"
            )
        part_block_size = int(part.get("block_size") or block_size)
        offset = (part_index - 1) * block_size
        length = min(part_block_size, file_size - offset)

        data = await asyncio.get_running_loop().run_in_executor(
            None, _read_file_chunk, file_source, offset, length
        )
        md5_hex = hashlib.md5(data).hexdigest()

        await self._put_part_with_retry(presigned_url, data, part_index, total_parts)
        await self._part_finish_with_retry(
            base,
            receiver_field,
            upload_id,
            part_index,
            length,
            md5_hex,
            retry_timeout,
        )

    async def _put_part_with_retry(
        self,
        url: str,
        data: bytes,
        part_index: int,
        total_parts: int,
    ) -> None:
        """PUT part bytes to a presigned COS URL with retry."""
        session = self.bot.api._http._session
        last_exc = None
        for attempt in range(_QQOFFICIAL_PART_PUT_MAX_RETRIES + 1):
            try:
                async with session.put(
                    url,
                    data=data,
                    headers={"Content-Length": str(len(data))},
                    timeout=aiohttp.ClientTimeout(total=_QQOFFICIAL_PART_PUT_TIMEOUT),
                ) as resp:
                    if 200 <= resp.status < 300:
                        return
                    body = (await resp.text(errors="ignore"))[:200]
                    last_exc = RuntimeError(f"COS PUT {resp.status}: {body}")
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
                last_exc = e
            if attempt < _QQOFFICIAL_PART_PUT_MAX_RETRIES:
                await asyncio.sleep(1.0 * (2**attempt))
        raise QQMediaUploadError(
            f"分片 {part_index}/{total_parts} 上传失败: {last_exc}"
        )

    async def _part_finish_with_retry(
        self,
        base: str,
        receiver_field: dict,
        upload_id: str,
        part_index: int,
        block_size: int,
        md5: str,
        retry_timeout: float,
    ) -> None:
        """Acknowledge a finished part, retrying on biz_code 40093001."""
        body = {
            "upload_id": upload_id,
            "part_index": part_index,
            "block_size": block_size,
            "md5": md5,
            **receiver_field,
        }
        timeout = (
            _QQOFFICIAL_PART_FINISH_DEFAULT_TIMEOUT
            if not retry_timeout
            else min(retry_timeout, _QQOFFICIAL_PART_FINISH_MAX_TIMEOUT)
        )
        loop = asyncio.get_running_loop()
        start = loop.time()
        while True:
            try:
                await self._qq_api_request("POST", f"{base}/upload_part_finish", body)
                return
            except QQApiError as e:
                if e.code != _QQOFFICIAL_BIZ_PART_RETRYABLE:
                    raise QQMediaUploadError(f"upload_part_finish 失败: {e}") from e
                if loop.time() - start >= timeout:
                    raise QQMediaUploadError(
                        f"upload_part_finish 重试超时（{timeout:.0f}s）: {e}"
                    ) from e
                await asyncio.sleep(_QQOFFICIAL_PART_FINISH_RETRY_INTERVAL)
            except QQMediaUploadError:
                raise

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
            result = await self.bot.api._http.request(route, json=payload)
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
