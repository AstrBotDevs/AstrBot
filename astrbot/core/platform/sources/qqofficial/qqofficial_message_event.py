import asyncio
import base64
import logging
import os
import random
import uuid
from typing import Callable, cast, Optional, Dict, List, Tuple

import aiofiles
import anyio
import botpy
import botpy.errors
import botpy.interaction
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
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.io import download_image_by_url
from astrbot.core.utils.tencent_record_helper import wav_to_tencent_silk

from ._markdown_media import image_to_markdown_fragment
from .components import QQCButton, QQCKeyboard


def _patch_qq_botpy_formdata() -> None:
    """Patch qq-botpy for aiohttp>=3.12 compatibility."""
    try:
        from botpy.http import _FormData

        if not hasattr(_FormData, "_is_processed"):
            type.__setattr__(_FormData, "_is_processed", False)
    except Exception:
        logger.debug("[QQOfficial] Skip botpy FormData patch.")


_patch_qq_botpy_formdata()

# Retry decorator for QQ Official API transient errors (HTTP 500/504)
_qqofficial_retry = retry(
    retry=retry_if_exception_type(
        (
            botpy.errors.ServerError,
            botpy.errors.SequenceNumberError,
            OSError,
            asyncio.TimeoutError,
        ),
    ),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)


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
    IMAGE_FILE_TYPE = 1
    VIDEO_FILE_TYPE = 2
    VOICE_FILE_TYPE = 3
    FILE_FILE_TYPE = 4
    STREAM_MARKDOWN_NEWLINE_ERROR = "流式消息md分片需要\\n结束"
    # 没有正文但带 keyboard 时的占位（QQ markdown content 不可为空）
    EMPTY_MARKDOWN_PLACEHOLDER = "​"

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
        self._interaction_acked = False
        self._interaction_ack_done = asyncio.Event()
        self._interaction_ack_code: int = 0

    async def ack_interaction(self, code: int = 0) -> None:
        """向 QQ 官方上报按钮交互结果。

        code: 0=成功, 1=操作失败, 2=操作频繁, 3=重复操作, 4=没有权限, 5=仅管理员。

        每个 interaction 只会真正上报一次，重复调用会被忽略。
        非 interaction 事件调用本方法是 no-op。
        """
        if self._interaction_acked:
            logger.debug(f"[QQOfficial] ack_interaction 跳过(已 ack)，请求 code={code}")
            return
        interaction = self.message_obj.raw_message
        if not isinstance(interaction, botpy.interaction.Interaction):
            return
        self._interaction_acked = True
        self._interaction_ack_code = code
        logger.debug(
            f"[QQOfficial] ack_interaction 发送 code={code} id={interaction.id}"
        )
        try:
            await self.bot.api.on_interaction_result(interaction.id, code)
        except Exception as e:
            logger.warning(f"[QQOfficial] interaction ack 失败: {e}")
        finally:
            self._interaction_ack_done.set()

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
                    ret = await self._post_send(stream=stream_payload)
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

    async def _post_send(self, stream: dict | None = None, **kwargs):
        if not self.send_buffer:
            return None
        source = self.message_obj.raw_message
        if not isinstance(
            source,
            botpy.message.Message
            | botpy.message.GroupMessage
            | botpy.message.DirectMessage
            | botpy.message.C2CMessage
            | botpy.interaction.Interaction,
        ):
            logger.warning(f"[QQOfficial] 不支持的消息源类型: {type(source)}")
            return None

        # 先预扫消息链判断是否存在 keyboard / 裸按钮：有的话强制 markdown，
        # 并让 _parse_to_qqofficial 把图片转成 markdown 语法以便共存。
        use_md = getattr(self.send_buffer, "use_markdown_", None)
        has_keyboard_component = any(
            isinstance(seg, (QQCKeyboard, QQCButton)) for seg in self.send_buffer.chain
        )
        if has_keyboard_component and use_md is False:
            logger.warning("[QQOfficial] 检测到 QQC 按钮组件，自动启用 markdown 模式")
            use_md = True
        convert_img = has_keyboard_component and use_md is not False

        (
            plain_text,
            image_source,
            record_file_path,
            video_file_source,
            file_source,
            file_name,
            keyboard_payload,
        ) = await QQOfficialMessageEvent._parse_to_qqofficial(
            self.send_buffer,
            convert_image_to_markdown=convert_img,
        )

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
            and not keyboard_payload
        ):
            return None

        if (
            stream
            and stream.get("state") == 10
            and plain_text
            and (not plain_text.endswith("\n"))
        ):
            plain_text = plain_text + "\n"

        # keyboard 要求 markdown content 非空，补零宽占位
        if keyboard_payload and not plain_text:
            plain_text = self.EMPTY_MARKDOWN_PLACEHOLDER

        is_interaction = isinstance(source, botpy.interaction.Interaction)
        if use_md is False:
            payload: dict = {
                "content": plain_text,
                "msg_type": 0,
            }
        else:
            payload = {
                "markdown": MarkdownPayload(content=plain_text) if plain_text else None,
                "msg_type": 2,
            }
            if keyboard_payload is not None:
                payload["keyboard"] = keyboard_payload

        # 按钮回调用 event_id 换取被动回复配额；其余用 msg_id。
        # message_id 在 _parse_interaction_to_abm 里已经被设为 interaction.event_id，
        # 这里两条分支只是字段名不同。
        if is_interaction:
            payload["event_id"] = self.message_obj.message_id
        else:
            payload["msg_id"] = self.message_obj.message_id

        if not isinstance(
            source,
            botpy.message.Message | botpy.message.DirectMessage,
        ):
            payload["msg_seq"] = random.randint(1, 10000)
        ret = None
        # 若 keyboard 和非 markdown-内联媒体同时存在，媒体路径会把 msg_type 改成 7
        # 并 pop markdown/keyboard。这里预先探测，稍后补发一条带 keyboard 的 markdown 消息。
        media_overrides_keyboard = keyboard_payload is not None and (
            image_base64 or record_file_path or video_file_source or file_source
        )
        if media_overrides_keyboard:
            payload.pop("keyboard", None)

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
                        payload["content"] = plain_text or None
                ret = await self._send_with_stream_newline_fix(
                    send_func=lambda retry_payload: self.bot.api.post_group_message(
                        group_openid=source.group_openid,
                        **retry_payload,
                    ),
                    payload=payload,
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
                        payload["content"] = plain_text or None
                if stream:
                    ret = await self._send_with_stream_newline_fix(
                        send_func=lambda retry_payload: self.post_c2c_message(
                            self.bot,
                            openid=source.author.user_openid,
                            **retry_payload,
                            stream=stream,
                        ),
                        payload=payload,
                        stream=stream,
                    )
                else:
                    ret = await self._send_with_stream_newline_fix(
                        send_func=lambda retry_payload: self.post_c2c_message(
                            self.bot,
                            openid=source.author.user_openid,
                            **retry_payload,
                        ),
                        payload=payload,
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
                ret = await self._send_with_stream_newline_fix(
                    send_func=lambda retry_payload: self.bot.api.post_message(
                        channel_id=source.channel_id,
                        **retry_payload,
                    ),
                    payload=payload,
                    stream=stream,
                )
            case botpy.message.DirectMessage():
                if image_source and os.path.exists(image_source):
                    payload["file_image"] = image_source
                payload.pop("msg_type", None)
                ret = await self._send_with_stream_newline_fix(
                    send_func=lambda retry_payload: self.bot.api.post_dms(
                        guild_id=source.guild_id,
                        **retry_payload,
                    ),
                    payload=payload,
                    stream=stream,
                )

            case botpy.interaction.Interaction():
                # 按钮点击回调的回复：按 chat_type 路由
                # chat_type: 0=频道 / 1=群 / 2=C2C
                #
                # 已知限制：本分支不上传 QQ 富媒体（msg_type=7），因此不支持语音/视频/文件
                if record_file_path or video_file_source or file_source:
                    logger.warning(
                        "[QQOfficial] Interaction 回调暂不支持发送语音/视频/文件，"
                        "本次发送已跳过（chain 中检测到非图片媒体）。"
                    )
                    return None
                chat_type = source.chat_type
                if chat_type == 1 and source.group_openid:
                    ret = await self._send_with_stream_newline_fix(
                        send_func=lambda retry_payload: self.bot.api.post_group_message(
                            group_openid=source.group_openid,  # type: ignore
                            **retry_payload,
                        ),
                        payload=payload,
                        stream=stream,
                    )
                elif chat_type == 2 and source.user_openid:
                    ret = await self._send_with_stream_newline_fix(
                        send_func=lambda retry_payload: self.post_c2c_message(
                            openid=source.user_openid,  # type: ignore
                            **retry_payload,
                        ),
                        payload=payload,
                        stream=stream,
                    )
                elif chat_type == 0 and source.channel_id:
                    # 频道：v1 接口不接受 msg_type / msg_seq / event_id
                    guild_payload = payload.copy()
                    guild_payload.pop("msg_type", None)
                    guild_payload.pop("msg_seq", None)
                    # 频道接口用 msg_id 或 event_id 都可，保留 event_id
                    ret = await self._send_with_stream_newline_fix(
                        send_func=lambda retry_payload: self.bot.api.post_message(
                            channel_id=source.channel_id,  # type: ignore
                            **retry_payload,
                        ),
                        payload=guild_payload,
                        stream=stream,
                    )
                else:
                    logger.warning(
                        "[QQOfficial] interaction 无法路由: chat_type=%s",
                        chat_type,
                    )

            case _:
                pass

        # 非图片媒体抢占了 msg_type=7，补发一条 markdown+keyboard
        if media_overrides_keyboard and keyboard_payload:
            await self._send_keyboard_followup(source, plain_text, keyboard_payload)

        await super().send(self.send_buffer)
        self.send_buffer = None

        # 清理临时文件
        self._cleanup_temp_files()

        return ret

    async def _send_keyboard_followup(
        self,
        source,
        plain_text: str,
        keyboard_payload: dict,
    ) -> None:
        """在媒体消息之后补发一条仅含 markdown+keyboard 的 msg_type=2 消息。"""
        content = plain_text or self.EMPTY_MARKDOWN_PLACEHOLDER
        followup: dict = {
            "markdown": MarkdownPayload(content=content),
            "msg_type": 2,
            "msg_id": self.message_obj.message_id,
            "keyboard": keyboard_payload,
            "msg_seq": random.randint(1, 10000),
        }
        try:
            if isinstance(source, botpy.message.GroupMessage):
                if not source.group_openid:
                    return
                await self.bot.api.post_group_message(
                    group_openid=source.group_openid,
                    **followup,
                )
            elif isinstance(source, botpy.message.C2CMessage):
                await self.post_c2c_message(
                    openid=source.author.user_openid,
                    **followup,
                )
            else:
                logger.debug(
                    "[QQOfficial] 消息源 %s 不支持 keyboard，忽略补发", type(source)
                )
        except Exception as e:
            logger.warning(f"[QQOfficial] keyboard 补发失败: {e}")

    def is_button_interaction(self) -> bool:
        """当前事件是否来自 QQ 消息按钮点击回调。"""
        raw = getattr(self.message_obj, "raw_message", None)
        return isinstance(raw, botpy.interaction.Interaction)

    def get_message_outline(self) -> str:
        """interaction 事件没有消息链，构造按钮摘要供日志使用。"""
        if not self.is_button_interaction():
            return super().get_message_outline()
        button_id = self.get_interaction_button_id() or "?"
        button_data = self.get_interaction_button_data()
        if button_data:
            return f"[Button] id={button_id} data={button_data}"
        return f"[Button] id={button_id}"

    def get_interaction_button_id(self) -> str:
        """获取被点击按钮的 id（`QQCButton.id`）；非交互事件返回空串。"""
        if not self.is_button_interaction():
            return ""
        raw = cast(botpy.interaction.Interaction, self.message_obj.raw_message)
        resolved = getattr(getattr(raw, "data", None), "resolved", None)
        return getattr(resolved, "button_id", "") or ""

    def get_interaction_button_data(self) -> str:
        """获取被点击按钮的 data（`QQCButton.data`）；非交互事件返回空串。"""
        if not self.is_button_interaction():
            return ""
        raw = cast(botpy.interaction.Interaction, self.message_obj.raw_message)
        resolved = getattr(getattr(raw, "data", None), "resolved", None)
        return getattr(resolved, "button_data", "") or ""

    async def _send_with_stream_newline_fix(
        self,
        send_func,
        payload: dict,
        stream: dict | None = None,
    ):
        """发送包装：流式 markdown 分片若因缺失换行被拒，补 `\\n` 重试一次。"""
        try:
            return await send_func(payload)
        except botpy.errors.ServerError as err:
            if stream and self.STREAM_MARKDOWN_NEWLINE_ERROR in str(err):
                retry_payload = payload.copy()
                markdown_payload = retry_payload.get("markdown")
                if isinstance(markdown_payload, dict):
                    md_content = markdown_payload.get("content", "") or ""
                    if md_content and (not md_content.endswith("\n")):
                        retry_payload["markdown"] = {"content": md_content + "\n"}
                content = retry_payload.get("content")
                if content and (not content.endswith("\n")):
                    retry_payload["content"] = content + "\n"
                logger.warning(
                    "[QQOfficial] 流式 markdown 分片换行校验失败,已修正后重试一次｡",
                )
                return await send_func(retry_payload)
            raise

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
            logger.warning("[QQOfficial] post_c2c_message: API 返回 None,跳过本次发送")
            return None
        if not isinstance(result, dict):
            logger.error(f"[QQOfficial] post_c2c_message: 响应不是 dict: {result}")
            return None
        return result

    @staticmethod
    async def _parse_to_qqofficial(
        message: MessageChain,
        convert_image_to_markdown: bool = False,
    ):
        """将 MessageChain 解析为发送 payload 所需要素。

        Args:
            message: 消息链
            convert_image_to_markdown: 若为 True 且图片能注册到文件服务，则将图片
                转成 markdown `![](url)` 语法追加到 plain_text，并跳过 base64 上传；
                这样图片能和 keyboard/markdown 共存于同一条 msg_type=2 消息。

        Returns:
            (plain_text, image_base64, image_file_path, record_file_path,
             video_file_source, file_source, file_name, keyboard_payload)
        """
        plain_text = ""
        image_base64 = None  # only one img supported for msg_type=7 path
        image_file_path = None
        record_file_path = None
        video_file_source = None
        file_source = None
        file_name = None
        keyboard_payload: dict | None = None
        pending_buttons: list[QQCButton] = []
        for i in message.chain:
            if isinstance(i, Plain):
                plain_text += i.text
            elif isinstance(i, QQCKeyboard):
                keyboard_payload = i.to_dict()
            elif isinstance(i, QQCButton):
                pending_buttons.append(i)
            elif isinstance(i, Image):
                # markdown 模式下尽量把图片转成 markdown 语法，以便与 keyboard 共存
                if convert_image_to_markdown:
                    fragment = await image_to_markdown_fragment(i)
                    if fragment is not None:
                        plain_text += fragment
                        continue
                    # 失败时回退到 msg_type=7 路径
                    logger.warning(
                        "[QQOfficial] 图片转 markdown 失败，回退到 msg_type=7；"
                        "若消息链包含 keyboard 则 keyboard 会被丢弃。"
                    )
                if image_base64:
                    continue  # msg_type=7 路径只带第一张
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
                            logger.error("转换音频格式时出错:音频时长不大于0")
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

        # 裸 QQCButton 自动包一层 keyboard（仅当未显式传 QQCKeyboard 时）
        if keyboard_payload is None and pending_buttons:
            keyboard_payload = QQCKeyboard(rows=[pending_buttons]).to_dict()

        return (
            plain_text,
            image_source,
            record_file_path,
            video_file_source,
            file_source,
            file_name,
            keyboard_payload,
        )
