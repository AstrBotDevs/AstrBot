import asyncio
import base64
import os
import random
import uuid
from typing import Callable, cast, Optional, Dict, List, Tuple

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
from astrbot.core.utils.io import download_image_by_url
from astrbot.core.utils.tencent_record_helper import wav_to_tencent_silk

# 导入分片上传模块
from .chunked_upload import (
    QQBotHttpClient,
    QQBotHttpClientManager,
    chunked_upload_c2c,
    chunked_upload_group,
    ChunkedUploadProgress,
    UploadDailyLimitExceededError,
    ApiError as ChunkedApiError,
)

# 导入限流器
from .rate_limiter import (
    MessageReplyLimiter,
    check_message_reply_limit,
    record_message_reply,
)

# 导入文件工具
from .file_utils import (
    format_file_size,
    get_max_upload_size,
    get_file_type_name,
)


def _patch_qq_botpy_formdata() -> None:
    """Patch qq-botpy for aiohttp>=3.12 compatibility."""
    try:
        from botpy.http import _FormData

        if not hasattr(_FormData, "_is_processed"):
            setattr(_FormData, "_is_processed", False)
    except Exception:
        logger.debug("[QQOfficial] Skip botpy FormData patch.")


_patch_qq_botpy_formdata()


# ============ 文本分块常量 ============
TEXT_CHUNK_LIMIT = 2000  # QQ 单条消息文本限制
TEXT_CHUNK_OVERLAP = 50  # 分块重叠字符数（避免句子被切断）


def chunk_text(
    text: str, limit: int = TEXT_CHUNK_LIMIT, overlap: int = TEXT_CHUNK_OVERLAP
) -> List[str]:
    """
    将长文本分割为多个小块

    Args:
        text: 原始文本
        limit: 单块最大字符数
        overlap: 块之间重叠字符数

    Returns:
        文本块列表
    """
    if not text or len(text) <= limit:
        return [text] if text else []

    chunks = []
    start = 0

    while start < len(text):
        end = start + limit

        if end >= len(text):
            # 最后一个块
            chunks.append(text[start:])
            break

        # 尝试找到一个合适断点（换行符、句号、逗号等）
        breakpoint = end
        for bp in range(end - 1, max(start, end - 100), -1):
            char = text[bp]
            if char in "\n。.，,；;！!？?":
                breakpoint = bp + 1
                break

        chunk = text[start:breakpoint]
        chunks.append(chunk)

        # 下一个块的起始位置（考虑重叠）
        start = max(breakpoint - overlap, start + 1)

    return chunks


class QQOfficialMessageEvent(AstrMessageEvent):
    MARKDOWN_NOT_ALLOWED_ERROR = "不允许发送原生 markdown"
    IMAGE_FILE_TYPE = 1
    VIDEO_FILE_TYPE = 2
    VOICE_FILE_TYPE = 3
    FILE_FILE_TYPE = 4
    STREAM_MARKDOWN_NEWLINE_ERROR = "流式消息md片段需要\\n结束"

    # 分片上传阈值：超过此大小使用分片上传
    CHUNKED_UPLOAD_THRESHOLD = 1024 * 1024  # 1MB

    # 消息回复限制配置
    MESSAGE_REPLY_LIMIT = 4
    MESSAGE_REPLY_TTL_MS = 60 * 60 * 1000  # 1小时

    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
        bot: Client,
        appid: str = "",
        secret: str = "",
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.bot = bot
        self.send_buffer = None

        # 凭据配置
        self.appid = appid
        self.secret = secret

        # 分片上传 HTTP 客户端（延迟初始化）
        self._http_client: Optional[QQBotHttpClient] = None

        # 限流器实例
        self._rate_limiter = MessageReplyLimiter()

        # 临时文件跟踪（用于清理）
        self._temp_files: list[str] = []

        # 媒体上传失败的兜底 URL
        self._upload_failed_media: Dict[str, str] = {}

    def set_credentials(self, appid: str, secret: str) -> None:
        """设置 QQ Bot 凭据（用于分片上传）"""
        self.appid = appid
        self.secret = secret

    def _cleanup_temp_files(self) -> None:
        """清理临时文件"""
        if not self._temp_files:
            return

        cleaned = 0
        for temp_file in self._temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    cleaned += 1
                    logger.debug(f"[QQOfficial] Cleaned temp file: {temp_file}")
            except Exception as e:
                logger.warning(
                    f"[QQOfficial] Failed to clean temp file {temp_file}: {e}"
                )

        if cleaned > 0:
            logger.debug(
                f"[QQOfficial] Cleaned {cleaned}/{len(self._temp_files)} temp files"
            )

        self._temp_files.clear()

    async def _get_http_client(self) -> QQBotHttpClient:
        """
        获取分片上传 HTTP 客户端

        使用全局管理器按 appId 隔离客户端，实现多机器人共享 Token 缓存。
        同一 appId 的多个实例会共享同一个 HTTP 客户端和 Token。
        """
        if self._http_client is None:
            if not self.appid or not self.secret:
                raise RuntimeError("QQ Bot 凭据未配置 (缺少 appid 或 secret)")
            # 使用全局管理器获取客户端（按 appId 隔离）
            self._http_client = await QQBotHttpClientManager.get_client(
                self.appid, self.secret
            )
        return self._http_client

    def _check_reply_limit(
        self, msg_id: str
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        检查消息回复是否受到限流

        Returns:
            Tuple[是否使用被动回复, 降级原因, 提示信息]
        """
        if not msg_id:
            return (False, "no_msg_id", "无消息ID，使用主动消息")

        limit_check = check_message_reply_limit(msg_id)

        if not limit_check.allowed:
            if limit_check.should_fallback_to_proactive:
                return (False, limit_check.fallback_reason, limit_check.message)

        return (True, None, None)

    def _should_use_passive_reply(self, source) -> Tuple[bool, Optional[str]]:
        """
        判断是否应该使用被动回复

        Args:
            source: 消息源对象

        Returns:
            Tuple[是否使用被动回复, 降级原因]
        """
        msg_id = self.message_obj.message_id

        # 频道消息和私信不支持被动回复
        if isinstance(source, (botpy.message.Message, botpy.message.DirectMessage)):
            return (False, "channel_dm_no_passive")

        # 检查限流
        use_passive, reason, hint = self._check_reply_limit(msg_id)

        if not use_passive and hint:
            logger.warning(f"[QQOfficial] {hint}")

        return (use_passive, reason)

    async def send(self, message: MessageChain) -> None:
        self.send_buffer = message
        await self._post_send()

    async def send_streaming(self, generator, use_fallback: bool = False):
        """流式输出仅支持消息列表私聊（C2C），其他消息源退化为普通发送"""
        await super().send_streaming(generator, use_fallback)
        stream_payload = {"state": 1, "id": None, "index": 0, "reset": False}
        last_edit_time = 0
        throttle_interval = 1
        ret = None

        # 记录初始消息源类型（用于流式结束时的判断）
        original_source = self.message_obj.raw_message
        is_c2c_source = isinstance(original_source, botpy.message.C2CMessage)

        try:
            async for chain in generator:
                source = self.message_obj.raw_message

                if not isinstance(source, botpy.message.C2CMessage):
                    # 非 C2C 消息，累积到 send_buffer
                    if not self.send_buffer:
                        self.send_buffer = chain
                    else:
                        self.send_buffer.chain.extend(chain.chain)
                    continue

                if chain.type == "break":
                    if self.send_buffer:
                        stream_payload["state"] = 10
                        ret = await self._post_send(stream=stream_payload)
                        ret_id = self._extract_response_message_id(ret)
                        if ret_id is not None:
                            stream_payload["id"] = ret_id
                    stream_payload = {
                        "state": 1,
                        "id": None,
                        "index": 0,
                        "reset": False,
                    }
                    last_edit_time = 0
                    continue

                if not self.send_buffer:
                    self.send_buffer = chain
                else:
                    self.send_buffer.chain.extend(chain.chain)

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
                    self.send_buffer = None

            # 流式消息结束处理
            if self.send_buffer:
                # 使用初始消息源类型判断，而非生成器最后一个元素
                if is_c2c_source:
                    stream_payload["state"] = 10
                    ret = await self._post_send(stream=stream_payload)
                else:
                    # 非 C2C 消息，直接发送累积的消息
                    ret = await self._post_send()

        except Exception as e:
            logger.error(f"发送流式消息时出错: {e}", exc_info=True)
            self.send_buffer = None

        # 清理临时文件
        self._cleanup_temp_files()

        return ret

    @staticmethod
    def _extract_response_message_id(ret) -> str | None:
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

        # ========== P0-2 & P0-3: 消息限流检查和自动降级 ==========
        msg_id = self.message_obj.message_id
        use_passive, fallback_reason = self._should_use_passive_reply(source)

        if not use_passive:
            # 降级为主动消息，移除 msg_id
            effective_msg_id = None
            logger.info(f"[QQOfficial] 消息回复降级为主动消息，原因: {fallback_reason}")
        else:
            effective_msg_id = msg_id

        # ========== 解析消息内容 ==========
        (
            plain_text,
            image_source,
            record_file_path,
            video_file_source,
            file_source,
            file_name,
        ) = await QQOfficialMessageEvent._parse_to_qqofficial(self.send_buffer)

        # C2C 流式仅用于文本分片，富媒体时降级为普通发送
        if stream and (
            image_source or record_file_path or video_file_source or file_source
        ):
            logger.debug("[QQOfficial] 检测到富媒体，降级为非流式发送。")
            stream = None

        if (
            not plain_text
            and not image_source
            and not record_file_path
            and not video_file_source
            and not file_source
        ):
            return None

        if (
            stream
            and stream.get("state") == 10
            and plain_text
            and not plain_text.endswith("\n")
        ):
            plain_text = plain_text + "\n"

        # ========== P1-2: 长文本分块处理 ==========
        # 检查是否需要分块
        needs_chunking = len(plain_text) > TEXT_CHUNK_LIMIT if plain_text else False
        text_chunks = []

        if needs_chunking and not stream:
            text_chunks = chunk_text(plain_text)
            logger.info(
                f"[QQOfficial] 文本长度 {len(plain_text)} 超过限制，将分 {len(text_chunks)} 块发送"
            )

        # 构建 payload（使用 effective_msg_id 而不是直接使用 message_id）
        payload: dict = {
            "markdown": MarkdownPayload(content=plain_text) if plain_text else None,
            "msg_type": 2,
            "msg_id": effective_msg_id,  # P0-3: 使用可能降级后的 msg_id
        }

        if not isinstance(source, botpy.message.Message | botpy.message.DirectMessage):
            payload["msg_seq"] = random.randint(1, 10000)

        ret = None

        # ========== P1-1 & P1-3 & P1-4: 媒体处理增强 ==========
        # 媒体上传失败标记
        media_upload_failed = False
        upload_error_hint = None



        match source:
            case botpy.message.GroupMessage():
                if not source.group_openid:
                    logger.error("[QQOfficial] GroupMessage 缺少 group_openid")
                    return None

                if image_source:
                    media = await self._upload_image_enhanced(
                        image_source,
                        self.IMAGE_FILE_TYPE,
                        group_openid=source.group_openid,
                    )
                    if media:
                        payload["media"] = media
                        payload["msg_type"] = 7
                        payload.pop("markdown", None)
                        # P1-3: 保留文本内容，不要删除
                        payload["content"] = plain_text if plain_text else None
                    else:
                        # P1-1: 媒体上传失败标记
                        media_upload_failed = True
                        upload_error_hint = "图片"

                if record_file_path and not media_upload_failed:
                    media = await self._upload_media_enhanced(
                        record_file_path,
                        self.VOICE_FILE_TYPE,
                        group_openid=source.group_openid,
                    )
                    if media:
                        payload["media"] = media
                        payload["msg_type"] = 7
                        payload.pop("markdown", None)
                        payload["content"] = plain_text if plain_text else None
                    else:
                        media_upload_failed = True
                        if not upload_error_hint:
                            upload_error_hint = "语音"

                if video_file_source and not media_upload_failed:
                    media = await self._upload_media_enhanced(
                        video_file_source,
                        self.VIDEO_FILE_TYPE,
                        group_openid=source.group_openid,
                    )
                    if media:
                        payload["media"] = media
                        payload["msg_type"] = 7
                        payload.pop("markdown", None)
                        payload["content"] = plain_text if plain_text else None
                        payload.pop("msg_id", None)  # 视频消息不需要 msg_id
                    else:
                        media_upload_failed = True
                        if not upload_error_hint:
                            upload_error_hint = "视频"

                if file_source and not media_upload_failed:
                    media = await self._upload_media_enhanced(
                        file_source,
                        self.FILE_FILE_TYPE,
                        file_name=file_name,
                        group_openid=source.group_openid,
                    )
                    if media:
                        payload["media"] = media
                        payload["msg_type"] = 7
                        payload.pop("markdown", None)
                        payload["content"] = plain_text if plain_text else None
                        payload.pop("msg_id", None)  # 文件消息不需要 msg_id
                    else:
                        media_upload_failed = True
                        if not upload_error_hint:
                            upload_error_hint = "文件"

                # P1-1: 如果有文本内容且媒体上传失败，添加提示
                if media_upload_failed and plain_text:
                    hint = f"[提示: {upload_error_hint}发送失败]"
                    if not plain_text.endswith(hint):
                        payload["content"] = plain_text + "\n" + hint
                        payload["msg_type"] = 0
                        payload.pop("markdown", None)

                ret = await self._send_with_markdown_fallback(
                    send_func=lambda retry_payload: self.bot.api.post_group_message(
                        group_openid=source.group_openid,
                        **retry_payload,
                    ),
                    payload=payload,
                    plain_text=plain_text,
                    stream=stream,
                )

                # P0-2: 记录消息回复（如果使用了被动回复）
                if use_passive and effective_msg_id:
                    record_message_reply(effective_msg_id)

            case botpy.message.C2CMessage():
                if image_source:
                    media = await self._upload_image_enhanced(
                        image_source,
                        self.IMAGE_FILE_TYPE,
                        openid=source.author.user_openid,
                    )
                    if media:
                        payload["media"] = media
                        payload["msg_type"] = 7
                        payload.pop("markdown", None)
                        # P1-3: 保留文本内容
                        payload["content"] = plain_text if plain_text else None
                    else:
                        media_upload_failed = True
                        upload_error_hint = "图片"

                if record_file_path and not media_upload_failed:
                    media = await self._upload_media_enhanced(
                        record_file_path,
                        self.VOICE_FILE_TYPE,
                        openid=source.author.user_openid,
                    )
                    if media:
                        payload["media"] = media
                        payload["msg_type"] = 7
                        payload.pop("markdown", None)
                        payload["content"] = plain_text if plain_text else None
                    else:
                        media_upload_failed = True
                        if not upload_error_hint:
                            upload_error_hint = "语音"

                if video_file_source and not media_upload_failed:
                    media = await self._upload_media_enhanced(
                        video_file_source,
                        self.VIDEO_FILE_TYPE,
                        openid=source.author.user_openid,
                    )
                    if media:
                        payload["media"] = media
                        payload["msg_type"] = 7
                        payload.pop("markdown", None)
                        payload["content"] = plain_text if plain_text else None
                    else:
                        media_upload_failed = True
                        if not upload_error_hint:
                            upload_error_hint = "视频"

                if file_source and not media_upload_failed:
                    media = await self._upload_media_enhanced(
                        file_source,
                        self.FILE_FILE_TYPE,
                        file_name=file_name,
                        openid=source.author.user_openid,
                    )
                    if media:
                        payload["media"] = media
                        payload["msg_type"] = 7
                        payload.pop("markdown", None)
                        payload["content"] = plain_text if plain_text else None
                    else:
                        media_upload_failed = True
                        if not upload_error_hint:
                            upload_error_hint = "文件"

                # P1-1: 如果有文本内容且媒体上传失败，添加提示
                if media_upload_failed and plain_text:
                    hint = f"[提示: {upload_error_hint}发送失败]"
                    if not plain_text.endswith(hint):
                        payload["content"] = plain_text + "\n" + hint
                        payload["msg_type"] = 0
                        payload.pop("markdown", None)

                # P1-2: 分块发送（如果有多个文本块）
                if text_chunks and len(text_chunks) > 1:
                    logger.info(f"[QQOfficial] 开始分块发送 {len(text_chunks)} 条消息")
                    for i, chunk_text in enumerate(text_chunks):
                        chunk_payload = payload.copy()
                        chunk_payload["msg_id"] = effective_msg_id if i == 0 else None
                        chunk_payload["markdown"] = MarkdownPayload(content=chunk_text)
                        chunk_payload["content"] = chunk_text
                        chunk_payload["msg_type"] = 2

                        try:
                            ret = await self._send_with_markdown_fallback(
                                send_func=lambda p: self.post_c2c_message(
                                    openid=source.author.user_openid,
                                    **p,
                                ),
                                payload=chunk_payload,
                                plain_text=chunk_text,
                                stream=None,
                            )
                            logger.debug(
                                f"[QQOfficial] 块 {i + 1}/{len(text_chunks)} 发送成功"
                            )

                            # 记录被动回复
                            if i == 0 and use_passive and effective_msg_id:
                                record_message_reply(effective_msg_id)

                            # 避免发送过快
                            if i < len(text_chunks) - 1:
                                await asyncio.sleep(0.5)
                        except Exception as e:
                            logger.error(f"[QQOfficial] 块 {i + 1} 发送失败: {e}")
                            # 继续发送其他块

                    self.send_buffer = None
                    return ret
                elif stream:
                    ret = await self._send_with_markdown_fallback(
                        send_func=lambda retry_payload: self.post_c2c_message(
                            self.bot,
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
                            self.bot,
                            openid=source.author.user_openid,
                            **retry_payload,
                        ),
                        payload=payload,
                        plain_text=plain_text,
                        stream=stream,
                    )

                # P0-2: 记录消息回复（如果使用了被动回复）
                if use_passive and effective_msg_id:
                    record_message_reply(effective_msg_id)

                logger.debug(f"Message sent to C2C: {ret}")

            case botpy.message.Message():
                if image_source and os.path.exists(image_source):
                    payload["file_image"] = image_source
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
                if image_source and os.path.exists(image_source):
                    payload["file_image"] = image_source
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

        # 清理临时文件
        self._cleanup_temp_files()

        return ret

    async def _upload_image_enhanced(
        self,
        image_source: str,
        file_type: int,
        **kwargs,
    ) -> botpy.types.message.Media | None:
        """
        增强版图片上传：根据文件大小自动选择 base64 直传或分片上传
        P1-4: 完善 URL 下载的错误处理
        """
        # 判断文件大小
        file_path = None
        file_size = 0
        download_error = None

        try:
            if os.path.exists(image_source):
                file_path = image_source
                file_size = os.path.getsize(file_path)
            elif image_source.startswith("http"):
                # P1-4: URL 图片：先下载，增加错误处理
                try:
                    file_path = await download_image_by_url(image_source)
                    if file_path and os.path.exists(file_path):
                        file_size = os.path.getsize(file_path)
                    else:
                        download_error = "下载图片失败"
                        logger.error(f"[QQOfficial] 下载图片失败: {image_source}")
                except Exception as e:
                    download_error = f"下载图片出错: {str(e)}"
                    logger.error(f"[QQOfficial] 下载图片异常: {e}")
            elif image_source.startswith("base64://"):
                # Base64 数据，保存为临时文件
                try:
                    b64_data = image_source[9:]
                    temp_dir = get_astrbot_temp_path()
                    temp_path = os.path.join(
                        temp_dir, f"qqofficial_{uuid.uuid4().hex}.png"
                    )
                    with open(temp_path, "wb") as f:
                        f.write(base64.b64decode(b64_data))
                    file_path = temp_path
                    self._temp_files.append(temp_path)
                    file_size = os.path.getsize(file_path)
                except Exception as e:
                    download_error = f"解析 Base64 图片失败: {str(e)}"
                    logger.error(f"[QQOfficial] 解析 Base64 图片异常: {e}")
            else:
                download_error = f"不支持的图片来源: {image_source[:50]}..."
                logger.warning(f"[QQOfficial] {download_error}")

            # 如果下载失败但有 URL，记录用于兜底
            if download_error and image_source.startswith("http"):
                self._upload_failed_media["image"] = image_source
                logger.debug(
                    f"[QQOfficial] 保存图片 URL 用于兜底: {image_source[:50]}..."
                )
        except Exception as e:
            logger.error(f"[QQOfficial] 处理图片文件时出错: {e}")
            return None

        # 检查文件大小限制
        max_size = get_max_upload_size(file_type)
        if file_size > max_size:
            type_name = get_file_type_name(file_type)
            size_mb = file_size / (1024 * 1024)
            limit_mb = max_size / (1024 * 1024)
            logger.error(
                f"[QQOfficial] {type_name}过大（{size_mb:.1f}MB），超过{limit_mb:.0f}MB限制"
            )
            return None

        # 始终使用分片上传（与 openclaw-qqbot 行为一致）
        # openclaw-qqbot 不使用 base64 上传，所有图片都通过分片上传
        if file_path and os.path.exists(file_path):
            return await self._chunked_upload(
                file_path,
                file_type,
                openid=kwargs.get("openid"),
                group_openid=kwargs.get("group_openid"),
                on_progress=kwargs.get("on_progress"),
            )
        else:
            logger.error(
                f"[QQOfficial] 图片文件不存在: {image_source[:50] if image_source else 'None'}..."
            )
            return None

    async def _upload_media_enhanced(
        self,
        file_source: str,
        file_type: int,
        srv_send_msg: bool = False,
        file_name: str | None = None,
        **kwargs,
    ) -> Media | None:
        """
        增强版媒体上传：始终使用分片上传（与 openclaw-qqbot 行为一致）
        """
        file_path = None
        file_size = 0

        if os.path.exists(file_source):
            file_path = file_source
            file_size = os.path.getsize(file_path)
        else:
            # URL 或其他来源 - 记录用于兜底
            if file_source.startswith("http"):
                self._upload_failed_media[f"media_{file_type}"] = file_source
            file_size = 0

        # 检查文件大小限制
        max_size = get_max_upload_size(file_type)
        if file_size > max_size:
            type_name = get_file_type_name(file_type)
            size_mb = file_size / (1024 * 1024)
            limit_mb = max_size / (1024 * 1024)
            logger.error(
                f"[QQOfficial] {type_name}过大（{size_mb:.1f}MB），超过{limit_mb:.0f}MB限制"
            )
            return None

        # 始终使用分片上传（与 openclaw-qqbot 行为一致）
        if file_path:
            return await self._chunked_upload(
                file_path,
                file_type,
                openid=kwargs.get("openid"),
                group_openid=kwargs.get("group_openid"),
                on_progress=kwargs.get("on_progress"),
            )
        else:
            logger.error(f"[QQOfficial] 媒体文件不存在: {file_source}")
            return None

    async def _chunked_upload(
        self,
        file_path: str,
        file_type: int,
        openid: Optional[str] = None,
        group_openid: Optional[str] = None,
        on_progress: Optional[Callable[[ChunkedUploadProgress], None]] = None,
    ) -> Media | None:
        """
        分片上传（大文件）

        Args:
            file_path: 文件路径
            file_type: 文件类型（1=图片, 2=视频, 3=语音, 4=文件）
            openid: 用户 openid（C2C 目标）
            group_openid: 群 openid（Group 目标）
            on_progress: 进度回调函数

        Returns:
            Media 对象，失败返回 None
        """

        # 创建默认进度回调（类似 TypeScript 版本的日志）
        def default_progress_callback(progress: ChunkedUploadProgress) -> None:
            file_type_name = get_file_type_name(file_type)
            logger.debug(
                f"[QQOfficial] chunked upload progress: "
                f"{progress.completed_parts}/{progress.total_parts} parts, "
                f"{format_file_size(progress.uploaded_bytes)}/{format_file_size(progress.total_bytes)}"
            )

        # 使用传入的回调或默认回调
        progress_callback = (
            on_progress if on_progress is not None else default_progress_callback
        )

        try:
            http_client = await self._get_http_client()
            log_prefix = "[QQOfficial:chunked]"
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)

            # 判断目标是 C2C 还是 Group
            if openid:
                logger.info(
                    f"{log_prefix} Starting C2C chunked upload: "
                    f"file={file_name}, size={format_file_size(file_size)}, type={file_type}"
                )
                result = await chunked_upload_c2c(
                    http_client,
                    openid,
                    file_path,
                    file_type,
                    on_progress=progress_callback,
                    log_prefix=log_prefix,
                )
            elif group_openid:
                logger.info(
                    f"{log_prefix} Starting group chunked upload: "
                    f"file={file_name}, size={format_file_size(file_size)}, type={file_type}"
                )
                result = await chunked_upload_group(
                    http_client,
                    group_openid,
                    file_path,
                    file_type,
                    on_progress=progress_callback,
                    log_prefix=log_prefix,
                )
            else:
                raise ValueError(
                    "Invalid upload parameters: must provide openid or group_openid"
                )

            return Media(
                file_uuid=result.file_uuid,
                file_info=result.file_info,
                ttl=result.ttl,
            )

        except UploadDailyLimitExceededError as e:
            # P1-1: 每日上传限额超限
            logger.error(f"[QQOfficial] 每日上传限额超限: {e}")
            return None
        except ChunkedApiError as e:
            # P1-1: API 错误处理
            logger.error(f"[QQOfficial] 分片上传 API 错误: {e}")
            return None
        except Exception as e:
            logger.error(f"[QQOfficial] 分片上传失败: {e}", exc_info=True)
            return None

    async def _base64_upload(
        self,
        file_source: str,
        file_type: int,
        srv_send_msg: bool = False,
        file_name: str | None = None,
        **kwargs,
    ) -> Media | None:
        """
        Base64 直传（小文件）- 使用自定义 HTTP 客户端确保超时配置

        使用 QQBotHttpClient 的 base64_upload 方法，该方法配置了 120 秒超时，
        相比 botpy 默认超时更适合文件上传场景。
        """
        # 处理文件数据
        file_data = None
        if os.path.exists(file_source):
            try:
                async with aiofiles.open(file_source, "rb") as f:
                    file_content = await f.read()
                    file_data = base64.b64encode(file_content).decode("utf-8")
            except Exception as e:
                logger.error(f"[QQOfficial] 读取文件失败: {e}")
                return None
        elif file_source.startswith("http"):
            # 对于 URL，使用 botpy 的方式（因为 URL 上传不需要 base64 编码）
            pass  # 降级到原有逻辑
        else:
            logger.error(f"[QQOfficial] 不支持的图片来源: {file_source[:50]}...")
            return None

        # 如果是 URL，降级到原有逻辑
        if file_data is None:
            payload = {"file_type": file_type, "srv_send_msg": srv_send_msg}
            if file_name:
                payload["file_name"] = file_name
            payload["url"] = file_source

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
                return None

            try:
                result = await self.bot.api._http.request(route, json=payload)
                if result and isinstance(result, dict):
                    return Media(
                        file_uuid=result["file_uuid"],
                        file_info=result["file_info"],
                        ttl=result.get("ttl", 0),
                    )
            except Exception as e:
                logger.error(f"[QQOfficial] URL上传请求错误: {e}")
            return None

        # 使用自定义 HTTP 客户端上传
        try:
            http_client = await self._get_http_client()

            if "openid" in kwargs:
                result = await http_client.base64_upload(
                    file_type=file_type,
                    file_data=file_data,
                    file_name=file_name,
                    srv_send_msg=srv_send_msg,
                    target_type="c2c",
                    target_id=kwargs["openid"],
                )
            elif "group_openid" in kwargs:
                result = await http_client.base64_upload(
                    file_type=file_type,
                    file_data=file_data,
                    file_name=file_name,
                    srv_send_msg=srv_send_msg,
                    target_type="group",
                    target_id=kwargs["group_openid"],
                )
            else:
                return None

            return Media(
                file_uuid=result.file_uuid,
                file_info=result.file_info,
                ttl=result.ttl,
            )
        except ChunkedApiError as e:
            logger.error(f"[QQOfficial] Base64上传 API 错误: {e}")
        except Exception as e:
            logger.error(f"[QQOfficial] Base64上传失败: {e}", exc_info=True)

        return None

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

    @staticmethod
    async def upload_group_and_c2c_image(
        send_helper,
        image_source: str,
        file_type: int,
        **kwargs,
    ) -> botpy.types.message.Media:
        """兼容旧接口：上传图片

        Args:
            send_helper: 发送辅助对象（包含 bot 属性）
            image_source: 图片来源，可以是文件路径、URL 或 base64:// 数据
        """
        bot = getattr(send_helper, "bot", send_helper)
        event = QQOfficialMessageEvent.__new__(QQOfficialMessageEvent)
        event.bot = bot
        event._http_client = None
        event._temp_files = []
        event._upload_failed_media = {}
        appid = getattr(bot, "_appid", "") or getattr(bot, "appid", "")
        secret = getattr(bot, "_secret", "") or getattr(bot, "secret", "")
        event.appid = appid
        event.secret = secret
        return await event._upload_image_enhanced(
            image_source,
            file_type,
            **kwargs,
        )

    @staticmethod
    async def upload_group_and_c2c_media(
        send_helper,
        file_source: str,
        file_type: int,
        srv_send_msg: bool = False,
        file_name: str | None = None,
        **kwargs,
    ) -> Media | None:
        """兼容旧接口：上传媒体"""
        bot = getattr(send_helper, "bot", send_helper)
        event = QQOfficialMessageEvent.__new__(QQOfficialMessageEvent)
        event.bot = bot
        event._http_client = None
        event._temp_files = []
        event._upload_failed_media = {}
        appid = getattr(bot, "_appid", "") or getattr(bot, "appid", "")
        secret = getattr(bot, "_secret", "") or getattr(bot, "secret", "")
        event.appid = appid
        event.secret = secret
        return await event._upload_media_enhanced(
            file_source,
            file_type,
            srv_send_msg,
            file_name,
            **kwargs,
        )

    @staticmethod
    async def post_c2c_message(
        send_helper,
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
        bot = getattr(send_helper, "bot", send_helper)
        payload = {
            "msg_type": msg_type,
            "content": content,
            "embed": embed,
            "ark": ark,
            "message_reference": message_reference,
            "media": media,
            "msg_id": msg_id,
            "msg_seq": msg_seq,
            "event_id": event_id,
            "markdown": markdown,
            "keyboard": keyboard,
        }
        if "stream" in payload and payload["stream"] is not None:
            stream_data = dict(payload["stream"])
            if stream_data.get("id") is None:
                stream_data.pop("id", None)
            payload["stream"] = stream_data
        route = Route("POST", "/v2/users/{openid}/messages", openid=openid)
        result = await bot.api._http.request(route, json=payload)

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
        image_source = None  # 图片来源（路径或 URL）
        record_file_path = None
        video_file_source = None
        file_source = None
        file_name = None

        for i in message.chain:
            if isinstance(i, Plain):
                plain_text += i.text
            elif isinstance(i, Image) and not image_source:
                if i.file and i.file.startswith("file:///"):
                    image_source = i.file[8:]
                elif i.file and i.file.startswith("http"):
                    image_source = i.file  # P1-4: 保留 URL 供后续处理
                elif i.file and i.file.startswith("base64://"):
                    # Base64 数据，保存为临时文件
                    b64_data = i.file[9:]
                    temp_dir = get_astrbot_temp_path()
                    temp_path = os.path.join(
                        temp_dir, f"qqofficial_{uuid.uuid4().hex}.png"
                    )
                    try:
                        with open(temp_path, "wb") as f:
                            f.write(base64.b64decode(b64_data))
                        image_source = temp_path
                    except Exception as e:
                        logger.error(f"[QQOfficial] 保存 Base64 图片失败: {e}")
                        image_source = i.file  # 保留原始数据
                elif i.file:
                    image_source = i.file
                else:
                    raise ValueError("Unsupported image file format")

            elif isinstance(i, Record):
                if i.file:
                    record_wav_path = await i.convert_to_file_path()
                    temp_dir = get_astrbot_temp_path()
                    record_silk_path = os.path.join(
                        temp_dir,
                        f"qqofficial_{uuid.uuid4()}.silk",
                    )
                    try:
                        duration = await wav_to_tencent_silk(
                            record_wav_path,
                            record_silk_path,
                        )
                        if duration > 0:
                            record_file_path = record_silk_path
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
            image_source,
            record_file_path,
            video_file_source,
            file_source,
            file_name,
        )
