import asyncio
import base64
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


class APIReturnNoneError(Exception):
    pass


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

# URL 上传模式可用性缓存
_url_upload_available: bool | None = None
_media_upload_base_url: str = ""


async def init_url_upload_probe(media_upload_url: str = "") -> None:
    """启动时探测媒体上传地址是否可达，结果缓存。
    应在适配器启动时调用一次。同时清理上次遗留的临时文件。
    """
    global _url_upload_available, _media_upload_base_url

    # 等待 Web Server 启动完成
    await asyncio.sleep(10)

    # 清理上次遗留的临时文件
    temp_dir = os.path.join(os.getcwd(), "data", "media_upload_cache")
    if os.path.isdir(temp_dir):
        try:
            import glob
            stale = glob.glob(os.path.join(temp_dir, "*"))
            for f in stale:
                try:
                    os.unlink(f)
                except OSError:
                    pass
            if stale:
                logger.info(f"[QQOfficial] 清理遗留临时文件: {len(stale)} 个")
        except Exception:
            pass

    if not media_upload_url:
        _url_upload_available = False
        logger.info("[QQOfficial] 未配置 media_upload_url，URL 上传模式不可用，将使用 Base64")
        return

    _media_upload_base_url = media_upload_url.rstrip('/')

    for attempt in range(3):
        _url_upload_available = await QQOfficialMessageEvent._probe_temp_url_reachable(_media_upload_base_url)
        if _url_upload_available:
            break
        if attempt < 2:
            await asyncio.sleep(3)

    if _url_upload_available:
        logger.info(f"[QQOfficial] URL 上传模式已启用 (callback_api_base={_media_upload_base_url})")
    else:
        logger.warning(f"[QQOfficial] callback_api_base 不可达 ({_media_upload_base_url})，回退 Base64 模式")


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
        if record_file_path:
            self.track_temporary_local_file(record_file_path)

        logger.info(
            f"[QQOfficial][DEBUG] _parse_to_qqofficial 返回: "
            f"plain_text={'有' if plain_text else '无'}, "
            f"image_base64={'有' if image_base64 else '无'}, "
            f"image_path={'有' if image_path else '无'}, "
            f"record={'有' if record_file_path else '无'}, "
            f"video_file_source={video_file_source}, "
            f"file_source={file_source}, "
            f"file_name={file_name}"
        )

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

        logger.info(
            f"[QQOfficial][DEBUG] 初始 payload: msg_type={payload.get('msg_type')}, "
            f"has_markdown={payload.get('markdown') is not None}"
        )

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
                    logger.info(f"[QQOfficial][DEBUG] 开始上传文件: {file_source}, file_name={file_name}")
                    media = await self.upload_group_and_c2c_media(
                        file_source,
                        self.FILE_FILE_TYPE,
                        file_name=file_name,
                        group_openid=source.group_openid,
                    )
                    if media:
                        logger.info(f"[QQOfficial][DEBUG] 文件上传成功: media={media}")
                        payload["media"] = media
                        payload["msg_type"] = 7
                        payload.pop("markdown", None)
                        payload["content"] = plain_text or None
                    else:
                        logger.warning(f"[QQOfficial][DEBUG] 文件上传失败, media=None")
                logger.info(
                    f"[QQOfficial][DEBUG] 发送前 payload 状态: msg_type={payload.get('msg_type')}, "
                    f"has_media={payload.get('media') is not None}, "
                    f"has_markdown={payload.get('markdown') is not None}"
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
                    logger.info(f"[QQOfficial][DEBUG] 开始上传文件(C2C): {file_source}, file_name={file_name}")
                    media = await self.upload_group_and_c2c_media(
                        file_source,
                        self.FILE_FILE_TYPE,
                        file_name=file_name,
                        openid=source.author.user_openid,
                    )
                    if media:
                        logger.info(f"[QQOfficial][DEBUG] 文件上传成功(C2C): media={media}")
                        payload["media"] = media
                        payload["msg_type"] = 7
                        payload.pop("markdown", None)
                        payload["content"] = plain_text or None
                        logger.info(
                            f"[QQOfficial][DEBUG] 文件消息 payload: msg_type={payload.get('msg_type')}, "
                            f"has_media=True, file_info={getattr(media, 'file_info', '')[:32]}..."
                        )
                    else:
                        logger.warning(f"[QQOfficial][DEBUG] 文件上传失败(C2C), media=None")
                logger.info(
                    f"[QQOfficial][DEBUG] 发送前 payload 状态(C2C): msg_type={payload.get('msg_type')}, "
                    f"has_media={payload.get('media') is not None}, "
                    f"has_markdown={payload.get('markdown') is not None}"
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
            result = await self.bot.api._http.request(route, json=payload)
            if result is None:
                raise APIReturnNoneError("上传图片API返回None，触发重试")
            return result

        result = await _do_upload()

        if not isinstance(result, dict):
            raise RuntimeError(
                f"Failed to upload image, response is not dict: {result}"
            )

        return Media(
            file_uuid=result["file_uuid"],
            file_info=result["file_info"],
            ttl=result.get("ttl", 0),
        )

    @staticmethod
    async def _probe_temp_url_reachable(base_url: str) -> bool:
        """探测 AstrBot Web Server 是否对外可达（GET 面板根路径）。"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    base_url,
                    timeout=aiohttp.ClientTimeout(total=5),
                    allow_redirects=True,
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False

    @staticmethod
    async def _prepare_temp_file(file_source: str) -> tuple[str | None, str | None]:
        """将本地文件复制到临时目录（UUID 文件名），返回 (temp_path, temp_url)。
        失败返回 (None, None)。
        """
        if not _url_upload_available or not _media_upload_base_url:
            return None, None

        import shutil
        import uuid as _uuid

        ext = os.path.splitext(file_source)[1]
        temp_name = f"{_uuid.uuid4().hex}{ext}"
        temp_dir = os.path.join(os.getcwd(), "data", "media_upload_cache")
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, temp_name)

        try:
            await asyncio.to_thread(shutil.copy2, file_source, temp_path)
        except Exception as e:
            logger.warning(f"[QQOfficial] 创建临时文件失败: {e}")
            return None, None

        url = f"{_media_upload_base_url}/api/media/{temp_name}"
        logger.info(f"[QQOfficial] 临时文件: {temp_path}")
        logger.info(f"[QQOfficial] 下载 URL: {url}")
        return temp_path, url

    @staticmethod
    def _cleanup_temp_file(temp_path: str | None) -> None:
        """删除临时文件。"""
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
                logger.info(f"[QQOfficial] 已清理临时文件: {temp_path}")
            except OSError as e:
                logger.warning(f"[QQOfficial] 清理临时文件失败: {temp_path} ({e})")

    # ── 分片上传 (Chunked Upload) ────────────────────────────────────
    _CHUNKED_MD5_10M_SIZE = 10_002_432  # 约9.54MB，与 QQ API 规范一致
    _CHUNKED_PART_UPLOAD_TIMEOUT = 300.0
    _CHUNKED_PART_UPLOAD_MAX_RETRIES = 2
    _CHUNKED_PART_FINISH_RETRY_INTERVAL = 1.0
    _CHUNKED_PART_FINISH_DEFAULT_TIMEOUT = 120.0
    _CHUNKED_PART_FINISH_MAX_TIMEOUT = 600.0
    _CHUNKED_COMPLETE_MAX_RETRIES = 2
    _CHUNKED_COMPLETE_BASE_DELAY = 2.0
    _CHUNKED_MAX_CONCURRENT_PARTS = 10

    @staticmethod
    def _compute_file_hashes(file_path: str) -> dict:
        """计算文件的 md5, sha1, md5_10m（单次遍历）"""
        file_size = os.path.getsize(file_path)
        md5 = hashlib.md5()
        sha1 = hashlib.sha1()
        md5_10m = hashlib.md5()
        need_10m = file_size > QQOfficialMessageEvent._CHUNKED_MD5_10M_SIZE
        bytes_read = 0
        with open(file_path, "rb") as fh:
            while True:
                chunk = fh.read(65536)
                if not chunk:
                    break
                md5.update(chunk)
                sha1.update(chunk)
                if need_10m:
                    remaining = QQOfficialMessageEvent._CHUNKED_MD5_10M_SIZE - bytes_read
                    if remaining > 0:
                        md5_10m.update(chunk[:remaining])
                bytes_read += len(chunk)
        full_md5 = md5.hexdigest()
        return {
            "md5": full_md5,
            "sha1": sha1.hexdigest(),
            "md5_10m": md5_10m.hexdigest() if need_10m else full_md5,
        }

    @staticmethod
    def _read_file_chunk(file_path: str, offset: int, length: int) -> bytes:
        with open(file_path, "rb") as fh:
            fh.seek(offset)
            data = fh.read(length)
            if len(data) != length:
                raise IOError(f"Short read from {file_path}: expected {length}, got {len(data)}")
            return data

    async def _chunked_upload(
        self,
        file_source: str,
        file_type: int,
        file_name: str,
        **kwargs,
    ) -> Media | None:
        """分片上传：upload_prepare → PUT parts → complete_upload"""
        try:
            file_size = os.path.getsize(file_source)
        except OSError as e:
            logger.error(f"[QQOfficial] 分片上传: 无法读取文件 {file_source}: {e}")
            return None

        # 确定目标 (openid 或 group_openid)
        openid = kwargs.get("openid")
        group_openid = kwargs.get("group_openid")
        if not openid and not group_openid:
            return None

        target_type = "c2c" if openid else "group"
        target_id = openid or group_openid

        logger.info(
            f"[QQOfficial] 分片上传开始: file={file_name}, "
            f"size={file_size / (1024*1024):.1f}MB, type={file_type}, target={target_type}"
        )

        # Step 1: 计算文件哈希
        hashes = await asyncio.get_running_loop().run_in_executor(
            None, self._compute_file_hashes, file_source
        )
        logger.info(f"[QQOfficial] 分片上传: md5={hashes['md5'][:16]}..., sha1={hashes['sha1'][:16]}..., md5_10m={hashes['md5_10m'][:16]}...")
        logger.info(
            f"[QQOfficial] 分片上传 prepare 请求: file_type={file_type}, file_size={file_size}, "
            f"file_name={file_name or 'file'}"
        )

        # Step 2: upload_prepare
        try:
            prepare_payload = {
                "file_type": file_type,
                "file_size": file_size,
                "file_name": file_name or "file",
                "md5": hashes["md5"],
                "sha1": hashes["sha1"],
                "md5_10m": hashes["md5_10m"],
            }
            if openid:
                prepare_route = Route("POST", "/v2/users/{openid}/upload_prepare", openid=openid)
            else:
                prepare_route = Route("POST", "/v2/groups/{group_openid}/upload_prepare", group_openid=group_openid)
            prepare_result = await self.bot.api._http.request(prepare_route, json=prepare_payload)
            if not isinstance(prepare_result, dict):
                logger.error(f"[QQOfficial] upload_prepare 响应格式错误: {prepare_result}")
                return None
        except Exception as e:
            logger.error(f"[QQOfficial] upload_prepare 失败: {e}")
            return None

        upload_id = prepare_result.get("upload_id", "")
        block_size = int(prepare_result.get("block_size", 0))
        parts = prepare_result.get("parts", [])
        if not upload_id or not parts:
            logger.error(f"[QQOfficial] upload_prepare 缺少必要字段: {prepare_result}")
            return None

        # 解析 upload_config
        cfg = prepare_result.get("upload_config", {})
        if isinstance(cfg, dict):
            concurrency = min(int(cfg.get("concurrency", 3)), self._CHUNKED_MAX_CONCURRENT_PARTS)
            retry_timeout_raw = int(cfg.get("retry_timeout", 0))
        else:
            concurrency = min(int(prepare_result.get("concurrency", 3)), self._CHUNKED_MAX_CONCURRENT_PARTS)
            retry_timeout_raw = int(prepare_result.get("retry_timeout", 0))
        retry_timeout = min(
            retry_timeout_raw if retry_timeout_raw > 0 else self._CHUNKED_PART_FINISH_DEFAULT_TIMEOUT,
            self._CHUNKED_PART_FINISH_MAX_TIMEOUT,
        )

        logger.info(
            f"[QQOfficial] 分片上传: upload_id={upload_id}, block_size={block_size / 1024:.0f}KB, "
            f"parts={len(parts)}, concurrency={concurrency}"
        )

        # Step 3: 上传每个分片
        semaphore = asyncio.Semaphore(concurrency)
        completed_parts = 0

        async def _upload_one_part(part: dict):
            nonlocal completed_parts
            part_index = int(part.get("index", 0))
            presigned_url = part.get("presigned_url", "")
            part_block_size = int(part.get("block_size", 0)) or block_size
            offset = (part_index - 1) * block_size
            length = min(part_block_size, file_size - offset)

            if not presigned_url:
                logger.error(f"[QQOfficial] 分片 {part_index} 缺少 presigned_url")
                return

            # 读取分片数据
            data = await asyncio.get_running_loop().run_in_executor(
                None, self._read_file_chunk, file_source, offset, length
            )
            part_md5 = hashlib.md5(data).hexdigest()

            async with semaphore:
                # PUT 到预签名 URL
                last_exc = None
                for attempt in range(self._CHUNKED_PART_UPLOAD_MAX_RETRIES + 1):
                    try:
                        async with aiohttp.ClientSession() as sess:
                            async with sess.put(
                                presigned_url,
                                data=data,
                                headers={"Content-Length": str(len(data))},
                                timeout=aiohttp.ClientTimeout(total=self._CHUNKED_PART_UPLOAD_TIMEOUT),
                            ) as resp:
                                resp.raise_for_status()
                                logger.info(f"[QQOfficial] PUT 分片 {part_index}/{len(parts)}: {resp.status} OK, size={len(data)}")
                                break
                    except Exception as exc:
                        last_exc = exc
                        if attempt < self._CHUNKED_PART_UPLOAD_MAX_RETRIES:
                            delay = 1.0 * (2 ** attempt)
                            logger.warning(f"[QQOfficial] PUT 分片 {part_index} 失败, 重试 {attempt+1}: {exc}")
                            await asyncio.sleep(delay)
                else:
                    logger.error(f"[QQOfficial] PUT 分片 {part_index} 最终失败: {last_exc}")
                    raise RuntimeError(f"Part {part_index} upload failed: {last_exc}")

                # 通知平台分片完成
                # 发送 part 的 block_size（来自 prepare 响应），不是实际数据长度
                part_finish_block_size = int(part.get("block_size", 0)) or block_size
                part_finish_payload = {
                    "upload_id": upload_id,
                    "part_index": part_index,
                    "block_size": part_finish_block_size,
                    "md5": part_md5,
                }
                if openid:
                    finish_route = Route("POST", "/v2/users/{openid}/upload_part_finish", openid=openid)
                else:
                    finish_route = Route("POST", "/v2/groups/{group_openid}/upload_part_finish", group_openid=group_openid)

                logger.info(
                    f"[QQOfficial] part_finish 请求: part={part_index}, block_size={part_finish_block_size}, length={length}, md5={part_md5[:16]}..."
                )
                finish_start = asyncio.get_running_loop().time()
                finish_attempt = 0
                max_finish_retries = 5
                while True:
                    try:
                        await self.bot.api._http.request(finish_route, json=part_finish_payload)
                        break
                    except Exception as exc:
                        err_msg = str(exc)
                        finish_attempt += 1
                        elapsed = asyncio.get_running_loop().time() - finish_start
                        # 40093001 = retryable (平台侧还没收到分片)，其他错误也重试但次数更少
                        if "40093001" in err_msg:
                            if elapsed >= retry_timeout:
                                raise RuntimeError(f"part_finish timeout after {elapsed:.0f}s: {exc}") from exc
                            logger.debug(f"[QQOfficial] part_finish retryable(40093001), attempt {finish_attempt}")
                            await asyncio.sleep(self._CHUNKED_PART_FINISH_RETRY_INTERVAL)
                        else:
                            if finish_attempt >= max_finish_retries:
                                raise RuntimeError(f"part_finish failed after {finish_attempt} attempts: {exc}") from exc
                            delay = 1.0 * (2 ** (finish_attempt - 1))
                            logger.warning(f"[QQOfficial] part_finish 失败, 重试 {finish_attempt}/{max_finish_retries}: {exc}")
                            await asyncio.sleep(delay)

                completed_parts += 1
                logger.info(
                    f"[QQOfficial] 分片 {part_index}/{len(parts)} 完成 "
                    f"({completed_parts}/{len(parts)} done)"
                )

        # 顺序上传所有分片（确保 part_finish 按序完成）
        logger.info(f"[QQOfficial] 分片顺序: {[int(p.get('index', 0)) for p in parts]}")
        for part in parts:
            try:
                await _upload_one_part(part)
            except Exception as e:
                logger.error(f"[QQOfficial] 分片上传失败: {e}")
                return None

        logger.info(f"[QQOfficial] 所有 {len(parts)} 个分片上传完成，调用 complete_upload")

        # Step 4: complete_upload
        complete_payload = {"upload_id": upload_id}
        if openid:
            complete_route = Route("POST", "/v2/users/{openid}/files", openid=openid)
        else:
            complete_route = Route("POST", "/v2/groups/{group_openid}/files", group_openid=group_openid)

        last_exc = None
        for attempt in range(self._CHUNKED_COMPLETE_MAX_RETRIES + 1):
            try:
                complete_result = await self.bot.api._http.request(complete_route, json=complete_payload)
                if isinstance(complete_result, dict):
                    logger.info(
                        f"[QQOfficial] complete_upload 成功: file_info={complete_result.get('file_info', '')[:32]}..., "
                        f"file_uuid={complete_result.get('file_uuid', '')}, ttl={complete_result.get('ttl', 0)}"
                    )
                    return Media(
                        file_uuid=complete_result["file_uuid"],
                        file_info=complete_result["file_info"],
                        ttl=complete_result.get("ttl", 0),
                    )
                logger.error(f"[QQOfficial] complete_upload 响应格式错误: {complete_result}")
                return None
            except Exception as exc:
                last_exc = exc
                if attempt < self._CHUNKED_COMPLETE_MAX_RETRIES:
                    delay = self._CHUNKED_COMPLETE_BASE_DELAY * (2 ** attempt)
                    logger.warning(f"[QQOfficial] complete_upload 失败, 重试: {exc}")
                    await asyncio.sleep(delay)

        logger.error(f"[QQOfficial] complete_upload 最终失败: {last_exc}")
        return None

    async def upload_group_and_c2c_media(
        self,
        file_source: str,
        file_type: int,
        srv_send_msg: bool = False,
        file_name: str | None = None,
        **kwargs,
    ) -> Media | None:
        """上传媒体文件。

        本地视频/文件：分片上传。
        音频/远程 URL：Base64。
        """
        _file_type_name = {1: 'IMAGE', 2: 'VIDEO', 3: 'VOICE', 4: 'FILE'}.get(file_type, f'UNKNOWN({file_type})')
        logger.info(
            f"[QQOfficial][DEBUG] upload_group_and_c2c_media 入口: "
            f"file_source={file_source}, file_type={_file_type_name}, "
            f"file_name={file_name}, is_local={os.path.exists(file_source)}"
        )

        # 本地视频/文件：分片上传
        if os.path.exists(file_source) and file_type in (self.VIDEO_FILE_TYPE, self.FILE_FILE_TYPE):
            result = await self._chunked_upload(file_source, file_type, file_name or "file", **kwargs)
            if result:
                return result
            logger.warning("[QQOfficial] 分片上传失败，回退 Base64")

        # Base64 路径（音频、远程 URL、或分片上传失败回退）
        payload: dict = {"file_type": file_type, "srv_send_msg": srv_send_msg}
        if file_name:
            payload["file_name"] = file_name

        route: Route | None = None
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
            if os.path.exists(file_source):
                async with aiofiles.open(file_source, "rb") as f:
                    file_content = await f.read()
                    payload["file_data"] = base64.b64encode(file_content).decode("utf-8")
            else:
                payload["url"] = file_source

            @_qqofficial_retry()
            async def _do_upload():
                result = await self.bot.api._http.request(route, json=payload)
                if result is None:
                    raise APIReturnNoneError("上传文件API返回None，触发重试")
                return result

            result = await _do_upload()
            if result:
                if not isinstance(result, dict):
                    logger.error(f"上传文件响应格式错误: {result}")
                    return None
                return Media(
                    file_uuid=result["file_uuid"],
                    file_info=result["file_info"],
                    ttl=result.get("ttl", 0),
                )
        except (botpy.errors.ServerError, botpy.errors.SequenceNumberError):
            logger.error(f"上传媒体文件失败，共尝试5次后放弃: {file_source}")
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
                # QQ 视频上限 30MB，大于 28MB 的视频降级为文件发送
                if video_file_source:
                    should_downgrade = False
                    if os.path.exists(video_file_source):
                        # 本地文件：直接读大小
                        file_size_mb = os.path.getsize(video_file_source) / (1024 * 1024)
                        if file_size_mb > 28:
                            should_downgrade = True
                    elif video_file_source.startswith(("http://", "https://")):
                        # 远程 URL：HEAD 请求获取大小
                        try:
                            async with aiohttp.ClientSession() as _sess:
                                async with _sess.head(
                                    video_file_source,
                                    timeout=aiohttp.ClientTimeout(total=10),
                                    allow_redirects=True,
                                ) as _resp:
                                    content_length = _resp.headers.get("Content-Length")
                                    if content_length:
                                        file_size_mb = int(content_length) / (1024 * 1024)
                                        if file_size_mb > 28:
                                            should_downgrade = True
                        except Exception as _e:
                            logger.debug(f"[QQOfficial] HEAD 请求失败，保持视频发送: {_e}")
                    if should_downgrade:
                        logger.info(
                            f"[QQOfficial] 视频文件 {file_size_mb:.1f}MB 超过 28MB 限制，"
                            f"降级为文件发送: {video_file_source}"
                        )
                        file_source = video_file_source
                        if not file_name:
                            # URL 时 basename 可能带查询参数，清理一下
                            _base = os.path.basename(video_file_source.split('?')[0])
                            file_name = _base or "video.mp4"
                        video_file_source = None
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
