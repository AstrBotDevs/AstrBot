from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import mimetypes
import re
import traceback
import uuid
from collections import deque
from pathlib import Path
from time import time
from typing import Any, cast
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import aiofiles
import aiohttp

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
    register_platform_adapter,
)
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

from .weibo_event import WeiboMessageEvent

DEFAULT_TOKEN_ENDPOINT = "http://open-im.api.weibo.com/open/auth/ws_token"
DEFAULT_WS_ENDPOINT = "wss://open-im.api.weibo.com/ws/stream"
DEFAULT_HEARTBEAT_SEC = 30
DEFAULT_CONNECT_TIMEOUT_SEC = 20
DEFAULT_TEXT_CHUNK_LIMIT = 2000
DEFAULT_RECONNECT_INITIAL_DELAY_SEC = 1
DEFAULT_RECONNECT_MAX_DELAY_SEC = 60
MAX_DEDUP_MESSAGE_IDS = 1000
MAX_INBOUND_IMAGE_BYTES = 10 * 1024 * 1024
MAX_INBOUND_FILE_BYTES = 5 * 1024 * 1024
TOKEN_FETCH_MAX_RETRIES = 2
TOKEN_FETCH_RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
SUPPORTED_IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
}


class WeiboTokenFetchError(RuntimeError):
    """Raised when the token endpoint rejects adapter credentials."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


WEIBO_DEFAULT_CONFIG = {
    "id": "weibo",
    "type": "weibo",
    "enable": False,
    "app_id": "",
    "app_secret": "",
    "token_endpoint": DEFAULT_TOKEN_ENDPOINT,
    "ws_endpoint": DEFAULT_WS_ENDPOINT,
    "dm_policy": "open",
    "allow_from": "",
    "reject_message": "你暂时还没有权限与这个机器人对话。",
    "text_chunk_limit": DEFAULT_TEXT_CHUNK_LIMIT,
    "chunk_mode": "newline",
    "heartbeat_sec": DEFAULT_HEARTBEAT_SEC,
    "connect_timeout_sec": DEFAULT_CONNECT_TIMEOUT_SEC,
    "reconnect_initial_delay_sec": DEFAULT_RECONNECT_INITIAL_DELAY_SEC,
    "reconnect_max_delay_sec": DEFAULT_RECONNECT_MAX_DELAY_SEC,
}

WEIBO_CONFIG_METADATA = {
    "app_id": {
        "description": "微博 App ID",
        "type": "string",
        "hint": "填写私信 @微博龙虾助手 后获取到的 App ID。",
    },
    "app_secret": {
        "description": "微博 App Secret",
        "type": "string",
        "hint": "填写私信 @微博龙虾助手 后获取到的 App Secret。",
    },
    "token_endpoint": {
        "description": "Token 接口地址",
        "type": "string",
        "hint": "用于获取微博 WebSocket Token 的接口地址。",
    },
    "ws_endpoint": {
        "description": "WebSocket 地址",
        "type": "string",
        "hint": "用于收发微博私信的 WebSocket 地址。",
    },
    "dm_policy": {
        "description": "私信策略",
        "type": "string",
        "hint": "`open` 允许所有用户私信，`pairing` 仅允许 `allow_from` 白名单中的用户。",
    },
    "allow_from": {
        "description": "允许发送私信的用户 ID",
        "type": "string",
        "hint": "当 `dm_policy=pairing` 时生效，支持使用逗号或换行分隔多个用户 ID。",
    },
    "reject_message": {
        "description": "拒绝提示语",
        "type": "string",
        "hint": "当用户被私信策略拦截时，自动回复的提示语。",
    },
    "text_chunk_limit": {
        "description": "出站文本分片长度",
        "type": "int",
        "hint": "每个微博出站分片允许的最大字符数。",
    },
    "chunk_mode": {
        "description": "文本分片模式",
        "type": "string",
        "hint": "支持 `newline` 和 `length`；当前 `raw` 会按 `length` 处理。",
    },
    "heartbeat_sec": {
        "description": "心跳间隔（秒）",
        "type": "int",
        "hint": "aiohttp WebSocket 连接使用的心跳间隔。",
    },
    "connect_timeout_sec": {
        "description": "连接超时（秒）",
        "type": "int",
        "hint": "HTTP 与 WebSocket 建连时使用的超时时间。",
    },
    "reconnect_initial_delay_sec": {
        "description": "首次重连延迟（秒）",
        "type": "int",
        "hint": "连接断开后首次尝试重连前等待的秒数。",
    },
    "reconnect_max_delay_sec": {
        "description": "最大重连延迟（秒）",
        "type": "int",
        "hint": "指数退避重连时允许的最大等待秒数。",
    },
}


def _sanitize_filename(filename: str, fallback_stem: str) -> str:
    cleaned = Path(filename).name.strip()
    if not cleaned:
        cleaned = fallback_stem
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", cleaned)
    return cleaned or fallback_stem


def _normalize_allow_from(raw_value: Any) -> set[str]:
    if isinstance(raw_value, list):
        values = [str(item).strip() for item in raw_value]
    else:
        text = str(raw_value or "")
        values = [item.strip() for item in re.split(r"[\n,]", text)]
    return {value for value in values if value}


def _coerce_positive_int(raw_value: Any, default_value: int) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return default_value
    return value if value > 0 else default_value


def _build_ws_url(endpoint: str, app_id: str, token: str) -> str:
    parsed = urlparse(endpoint)
    query_items = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query_items["app_id"] = app_id
    query_items["token"] = token
    return urlunparse(parsed._replace(query=urlencode(query_items)))


def _guess_extension(mime_type: str, default_extension: str) -> str:
    guessed = mimetypes.guess_extension(mime_type or "")
    if guessed:
        return guessed
    return default_extension


def _split_text_by_length(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    return [text[index : index + limit] for index in range(0, len(text), limit)]


def _split_text(text: str, limit: int, mode: str) -> list[str]:
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    normalized_mode = mode.strip().lower()
    if normalized_mode != "newline":
        return _split_text_by_length(text, limit)

    chunks: list[str] = []
    current = ""
    for paragraph in text.splitlines(keepends=True):
        candidate = f"{current}{paragraph}"
        if current and len(candidate) > limit:
            chunks.extend(_split_text_by_length(current.rstrip("\n"), limit))
            current = paragraph
            continue
        current = candidate

    if current:
        chunks.extend(_split_text_by_length(current.rstrip("\n"), limit))

    return [chunk for chunk in chunks if chunk]


@register_platform_adapter(
    "weibo",
    "微博私信适配器",
    default_config_tmpl=WEIBO_DEFAULT_CONFIG,
    adapter_display_name="微博私信",
    logo_path="weibo_logo.svg",
    support_streaming_message=False,
    config_metadata=WEIBO_CONFIG_METADATA,
)
class WeiboPlatformAdapter(Platform):
    """AstrBot adapter for the Weibo DM websocket channel."""

    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)
        self.settings = platform_settings
        self.client_self_id = self.app_id or cast(str, self.config.get("id", "weibo"))
        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._shutdown_event = asyncio.Event()
        self._message_id_queue: deque[str] = deque()
        self._message_id_set: set[str] = set()
        self._inbound_dir = Path(get_astrbot_temp_path()) / "weibo" / "inbound"
        self._inbound_dir.mkdir(parents=True, exist_ok=True)

        if not self.app_id or not self.app_secret:
            raise ValueError("微博适配器需要同时配置 app_id 和 app_secret。")

    @property
    def app_id(self) -> str:
        return str(self.config.get("app_id", "")).strip()

    @property
    def app_secret(self) -> str:
        return str(self.config.get("app_secret", "")).strip()

    @property
    def token_endpoint(self) -> str:
        endpoint = str(
            self.config.get("token_endpoint", DEFAULT_TOKEN_ENDPOINT)
        ).strip()
        return endpoint or DEFAULT_TOKEN_ENDPOINT

    @property
    def ws_endpoint(self) -> str:
        endpoint = str(self.config.get("ws_endpoint", DEFAULT_WS_ENDPOINT)).strip()
        return endpoint or DEFAULT_WS_ENDPOINT

    @property
    def connect_timeout_sec(self) -> int:
        return _coerce_positive_int(
            self.config.get("connect_timeout_sec"),
            DEFAULT_CONNECT_TIMEOUT_SEC,
        )

    @property
    def heartbeat_sec(self) -> int:
        return _coerce_positive_int(
            self.config.get("heartbeat_sec"),
            DEFAULT_HEARTBEAT_SEC,
        )

    @property
    def reconnect_initial_delay_sec(self) -> int:
        return _coerce_positive_int(
            self.config.get("reconnect_initial_delay_sec"),
            DEFAULT_RECONNECT_INITIAL_DELAY_SEC,
        )

    @property
    def reconnect_max_delay_sec(self) -> int:
        return _coerce_positive_int(
            self.config.get("reconnect_max_delay_sec"),
            DEFAULT_RECONNECT_MAX_DELAY_SEC,
        )

    @property
    def text_chunk_limit(self) -> int:
        return _coerce_positive_int(
            self.config.get("text_chunk_limit"),
            DEFAULT_TEXT_CHUNK_LIMIT,
        )

    @property
    def chunk_mode(self) -> str:
        return (
            str(self.config.get("chunk_mode", "newline")).strip().lower() or "newline"
        )

    @property
    def dm_policy(self) -> str:
        return str(self.config.get("dm_policy", "open")).strip().lower() or "open"

    @property
    def allow_from(self) -> set[str]:
        return _normalize_allow_from(self.config.get("allow_from"))

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="weibo",
            description="微博私信适配器",
            id=cast(str, self.config.get("id", "weibo")),
            support_streaming_message=False,
        )

    async def run(self) -> None:
        timeout = aiohttp.ClientTimeout(
            total=None,
            connect=self.connect_timeout_sec,
            sock_connect=self.connect_timeout_sec,
            sock_read=None,
        )
        reconnect_delay = self.reconnect_initial_delay_sec

        async with aiohttp.ClientSession(timeout=timeout) as session:
            self._session = session
            while not self._shutdown_event.is_set():
                try:
                    await self._connect_and_consume()
                    reconnect_delay = self.reconnect_initial_delay_sec
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    trace = traceback.format_exc()
                    self.record_error(str(exc), trace)
                    logger.error(
                        f"[微博] 平台 {self.meta().id} 连接异常：{exc}\n{trace}",
                    )
                finally:
                    await self._close_ws()

                if self._shutdown_event.is_set():
                    break

                logger.warning(
                    "[微博] 平台 %s 将在 %s 秒后重连。",
                    self.meta().id,
                    reconnect_delay,
                )
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=reconnect_delay,
                    )
                    break
                except asyncio.TimeoutError:
                    reconnect_delay = min(
                        reconnect_delay * 2,
                        self.reconnect_max_delay_sec,
                    )

        self._session = None

    async def terminate(self) -> None:
        self._shutdown_event.set()
        await self._close_ws()
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ) -> None:
        await self.send_message_chain(session.session_id, message_chain)
        await super().send_by_session(session, message_chain)

    def get_client(self) -> Any:
        return self._ws

    async def _connect_and_consume(self) -> None:
        if self._session is None:
            raise RuntimeError("微博 HTTP 会话尚未初始化。")

        token = await self._fetch_token()
        ws_url = _build_ws_url(self.ws_endpoint, self.app_id, token)
        logger.info("[微博] 平台 %s 正在连接 %s", self.meta().id, ws_url)

        async with self._session.ws_connect(
            ws_url,
            heartbeat=self.heartbeat_sec,
            autoping=True,
        ) as ws:
            self._ws = ws
            self.clear_errors()
            logger.info("[微博] 平台 %s 已连接。", self.meta().id)

            async for message in ws:
                if self._shutdown_event.is_set():
                    break

                if message.type == aiohttp.WSMsgType.TEXT:
                    await self._handle_text_frame(str(message.data))
                    continue

                if message.type == aiohttp.WSMsgType.ERROR:
                    raise ws.exception() or RuntimeError("微博 WebSocket 连接出错")

                if message.type in {
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.CLOSING,
                }:
                    logger.warning(
                        "[微博] 平台 %s 的 WebSocket 已被服务端关闭。",
                        self.meta().id,
                    )
                    break

            if not self._shutdown_event.is_set() and ws.exception() is not None:
                raise ws.exception() or RuntimeError("微博 WebSocket 异常关闭")

    async def _fetch_token(self) -> str:
        if self._session is None:
            raise RuntimeError("微博 HTTP 会话尚未初始化。")

        payload = {"app_id": self.app_id, "app_secret": self.app_secret}
        delay_sec = 1.0
        last_error: Exception | None = None

        for attempt in range(TOKEN_FETCH_MAX_RETRIES + 1):
            try:
                async with self._session.post(
                    self.token_endpoint, json=payload
                ) as response:
                    if response.status >= 400:
                        body = (await response.text()).strip()
                        message = (
                            f"获取 Token 失败：{response.status} {response.reason}"
                        ).strip()
                        if body:
                            message = f"{message} - {body[:200]}"
                        raise WeiboTokenFetchError(
                            message,
                            retryable=response.status
                            in TOKEN_FETCH_RETRYABLE_STATUS_CODES,
                        )

                    data = await response.json(content_type=None)
                    token = str(
                        ((data or {}).get("data") or {}).get("token", "")
                    ).strip()
                    if not token:
                        raise WeiboTokenFetchError(
                            "Token 接口返回格式错误：缺少 data.token",
                            retryable=False,
                        )
                    return token
            except asyncio.CancelledError:
                raise
            except WeiboTokenFetchError as exc:
                last_error = exc
                if attempt >= TOKEN_FETCH_MAX_RETRIES or not exc.retryable:
                    break
            except Exception as exc:
                last_error = (
                    exc if isinstance(exc, Exception) else RuntimeError(str(exc))
                )
                if attempt >= TOKEN_FETCH_MAX_RETRIES:
                    break

            await asyncio.sleep(delay_sec)
            delay_sec = min(delay_sec * 2, 8.0)

        raise last_error or RuntimeError("获取微博 Token 失败")

    async def _handle_text_frame(self, raw_text: str) -> None:
        text = raw_text.strip()
        if not text or text == "pong" or text == '{"type":"pong"}':
            return

        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            logger.debug("[微博] 忽略非 JSON 帧：%s", text)
            return

        if not isinstance(payload, dict):
            return
        if payload.get("type") != "message":
            logger.debug("[微博] 忽略不支持的帧类型：%s", payload.get("type"))
            return

        await self._handle_inbound_message(payload)

    async def _handle_inbound_message(self, envelope: dict[str, Any]) -> None:
        payload = envelope.get("payload")
        if not isinstance(payload, dict):
            logger.warning("[微博] 收到格式错误的 payload：%s", envelope)
            return

        sender_id = str(payload.get("fromUserId", "")).strip()
        if not sender_id:
            logger.warning("[微博] payload 中缺少 fromUserId：%s", payload)
            return

        message_id = self._resolve_inbound_message_id(payload)
        if self._is_duplicate_message(message_id):
            logger.debug("[微博] 跳过重复消息：%s", message_id)
            return

        if not self._is_sender_allowed(sender_id):
            await self._send_reject_message(sender_id)
            return

        message_obj = await self._build_astrbot_message(envelope, payload, message_id)
        if message_obj is None:
            return

        logger.info(
            "[微博] 平台 %s 收到来自 %s 的私信：%s",
            self.meta().id,
            sender_id,
            message_obj.message_str,
        )
        event = WeiboMessageEvent(
            message_str=message_obj.message_str,
            message_obj=message_obj,
            platform_meta=self.meta(),
            session_id=message_obj.session_id,
            adapter=self,
        )
        self.commit_event(event)

    def _resolve_inbound_message_id(self, payload: dict[str, Any]) -> str:
        explicit_message_id = str(payload.get("messageId", "")).strip()
        if explicit_message_id:
            return explicit_message_id

        digest = hashlib.sha1(
            json.dumps(
                {
                    "fromUserId": payload.get("fromUserId"),
                    "text": payload.get("text"),
                    "timestamp": payload.get("timestamp"),
                    "input": payload.get("input"),
                },
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ).encode("utf-8"),
        ).hexdigest()
        return f"weibo_inbound_{digest[:16]}"

    def _is_duplicate_message(self, message_id: str) -> bool:
        if message_id in self._message_id_set:
            return True

        if len(self._message_id_queue) >= MAX_DEDUP_MESSAGE_IDS:
            oldest = self._message_id_queue.popleft()
            self._message_id_set.discard(oldest)

        self._message_id_queue.append(message_id)
        self._message_id_set.add(message_id)
        return False

    def _is_sender_allowed(self, sender_id: str) -> bool:
        if self.dm_policy == "open":
            return True
        return sender_id in self.allow_from

    async def _write_attachment_buffer(self, saved_path: Path, buffer: bytes) -> None:
        async with aiofiles.open(saved_path, "wb") as file:
            await file.write(buffer)

    async def _send_reject_message(self, sender_id: str) -> None:
        reject_message = str(self.config.get("reject_message", "")).strip()
        if not reject_message:
            return

        try:
            await self._send_text_message(sender_id, reject_message)
        except Exception as exc:
            logger.warning("[微博] 发送拒绝提示给 %s 失败：%s", sender_id, exc)

    async def _build_astrbot_message(
        self,
        envelope: dict[str, Any],
        payload: dict[str, Any],
        message_id: str,
    ) -> AstrBotMessage | None:
        sender_id = str(payload.get("fromUserId", "")).strip()
        components, message_str = await self._build_components(payload)
        if not components:
            return None

        timestamp = payload.get("timestamp")
        if isinstance(timestamp, (int, float)):
            unix_timestamp = (
                int(timestamp / 1000)
                if timestamp > 1_000_000_000_000
                else int(timestamp)
            )
        else:
            unix_timestamp = int(time())

        message = AstrBotMessage()
        message.type = MessageType.FRIEND_MESSAGE
        message.self_id = self.client_self_id
        message.session_id = sender_id
        message.message_id = message_id
        message.sender = MessageMember(user_id=sender_id, nickname=sender_id)
        message.message = components
        message.message_str = message_str
        message.raw_message = envelope
        message.timestamp = unix_timestamp
        return message

    async def _build_components(
        self,
        payload: dict[str, Any],
    ) -> tuple[list[Comp.BaseMessageComponent], str]:
        components: list[Comp.BaseMessageComponent] = []
        outline_parts: list[str] = []
        parsed_input = False

        raw_input = payload.get("input")
        if isinstance(raw_input, list):
            for item in raw_input:
                if not isinstance(item, dict):
                    continue
                if item.get("type") != "message" or item.get("role") != "user":
                    continue
                content = item.get("content")
                if not isinstance(content, list):
                    continue

                parsed_input = True
                for part in content:
                    if not isinstance(part, dict):
                        continue

                    part_type = str(part.get("type", "")).strip()
                    if part_type == "input_text":
                        text = str(part.get("text", ""))
                        if text:
                            components.append(Comp.Plain(text=text))
                            outline_parts.append(text)
                        continue

                    if part_type == "input_image":
                        component, outline = await self._build_attachment_component(
                            part,
                            default_kind="image",
                        )
                    elif part_type == "input_file":
                        component, outline = await self._build_attachment_component(
                            part,
                            default_kind="file",
                        )
                    else:
                        continue

                    if component is not None:
                        components.append(component)
                        outline_parts.append(outline)

        fallback_text = str(payload.get("text", "")).strip()
        if fallback_text and (
            not parsed_input
            or not any(isinstance(component, Comp.Plain) for component in components)
        ):
            components.insert(0, Comp.Plain(text=fallback_text))
            outline_parts.insert(0, fallback_text)

        message_str = "\n".join(part for part in outline_parts if part).strip()
        if not message_str and components:
            message_str = "[附件]"

        return components, message_str

    async def _build_attachment_component(
        self,
        part: dict[str, Any],
        default_kind: str,
    ) -> tuple[Comp.BaseMessageComponent | None, str]:
        source = part.get("source")
        if not isinstance(source, dict):
            return None, ""

        if str(source.get("type", "")).strip() != "base64":
            return None, ""

        mime_type = str(source.get("media_type", "application/octet-stream")).strip()
        encoded_data = str(source.get("data", "")).strip()
        if not encoded_data:
            return None, ""

        try:
            buffer = base64.b64decode(encoded_data, validate=True)
        except Exception as exc:
            logger.warning("[微博] 解码 Base64 附件失败：%s", exc)
            return None, ""

        filename = _sanitize_filename(
            str(part.get("filename", "")),
            fallback_stem=f"{default_kind}_{uuid.uuid4().hex}",
        )
        limit = (
            MAX_INBOUND_IMAGE_BYTES
            if default_kind == "image"
            else MAX_INBOUND_FILE_BYTES
        )
        if len(buffer) > limit:
            logger.warning(
                "[微博] 附件 %s 超过大小限制（%s 字节）。",
                filename,
                len(buffer),
            )
            return None, ""

        suffix = Path(filename).suffix
        if not suffix:
            suffix = _guess_extension(
                mime_type,
                default_extension=".jpg" if default_kind == "image" else ".bin",
            )
            filename = f"{filename}{suffix}"

        saved_path = self._inbound_dir / f"{uuid.uuid4().hex}_{filename}"
        await self._write_attachment_buffer(saved_path, buffer)

        if default_kind == "image" and mime_type in SUPPORTED_IMAGE_MIME_TYPES:
            return Comp.Image.fromFileSystem(str(saved_path)), f"[图片: {filename}]"

        return Comp.File(name=filename, file=str(saved_path)), f"[文件: {filename}]"

    async def send_message_chain(
        self, user_id: str, message_chain: MessageChain
    ) -> None:
        if not user_id:
            raise ValueError("微博发送目标 user_id 不能为空。")

        rendered_text = await self._render_message_chain(message_chain)
        if not rendered_text.strip():
            logger.info("[微博] 跳过发送给 %s 的空消息", user_id)
            return

        await self._send_text_message(user_id, rendered_text)

    async def _render_message_chain(self, message_chain: MessageChain) -> str:
        rendered_parts: list[str] = []

        for component in message_chain.chain:
            if isinstance(component, Comp.Plain):
                rendered_parts.append(component.text)
            elif isinstance(component, Comp.Image):
                label = (
                    Path(component.path).name
                    if getattr(component, "path", None)
                    else "图片"
                )
                rendered_parts.append(f"[图片: {label}]")
            elif isinstance(component, Comp.File):
                file_path = await component.get_file(allow_return_url=True)
                label = component.name or Path(file_path).name or "文件"
                rendered_parts.append(f"[文件: {label}] {file_path}".strip())
            elif isinstance(component, Comp.Record):
                rendered_parts.append("[音频]")
            elif isinstance(component, Comp.Video):
                rendered_parts.append("[视频]")
            elif isinstance(component, Comp.At):
                rendered_parts.append(f"@{component.name}")
            elif isinstance(component, Comp.Reply):
                continue
            elif isinstance(component, Comp.Json):
                rendered_parts.append(json.dumps(component.data, ensure_ascii=False))
            else:
                rendered_parts.append(f"[组件: {component.__class__.__name__}]")

        return "\n".join(part for part in rendered_parts if part).strip()

    async def _send_text_message(self, user_id: str, text: str) -> None:
        chunks = _split_text(text.strip(), self.text_chunk_limit, self.chunk_mode)
        if not chunks:
            return

        outbound_message_id = f"msg_{uuid.uuid4().hex}"
        for index, chunk in enumerate(chunks):
            done = index == len(chunks) - 1
            await self._send_ws_json(
                {
                    "type": "send_message",
                    "payload": {
                        "toUserId": user_id,
                        "text": chunk,
                        "messageId": outbound_message_id,
                        "chunkId": index,
                        "done": done,
                    },
                },
            )

    async def _send_ws_json(self, payload: dict[str, Any]) -> None:
        if self._ws is None or self._ws.closed:
            raise RuntimeError("微博 WebSocket 尚未连接。")
        await self._ws.send_json(
            payload,
            dumps=lambda value: json.dumps(value, ensure_ascii=False),
        )

    async def _close_ws(self) -> None:
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        self._ws = None
