from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import time
import uuid
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import quote

import qrcode as qrcode_lib

from astrbot import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import File, Image, Plain, Record, Reply, Video
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
    register_platform_adapter,
)
from astrbot.core import astrbot_config
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

from .weixin_oc_client import WeixinOCClient
from .weixin_oc_event import WeixinOCMessageEvent

if TYPE_CHECKING:  # pragma: no cover - typing-only helper
    pass


@dataclass
class OpenClawLoginSession:
    session_key: str
    qrcode: str
    qrcode_img_content: str
    started_at: float
    status: str = "wait"
    bot_token: str | None = None
    account_id: str | None = None
    base_url: str | None = None
    user_id: str | None = None
    error: str | None = None


@dataclass
class TypingSessionState:
    ticket: str | None = None
    ticket_context_token: str | None = None
    refresh_after: float = 0.0
    keepalive_task: asyncio.Task | None = None
    cancel_task: asyncio.Task | None = None
    owners: set[str] = field(default_factory=set)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


@dataclass
class WeixinOCRecentMessage:
    message_id: str
    sender_id: str
    sender_nickname: str
    timestamp: int
    timestamp_ms: int
    components: list[Any]
    message_str: str
    message_kind: str


@dataclass
class WeixinOCRecentSessionCache:
    messages: deque[WeixinOCRecentMessage]
    updated_at: float


@dataclass
class WeixinOCReplyMeta:
    is_reply: bool = False
    ref_msg: dict[str, Any] | None = None
    reply_kind: str | None = None
    quoted_item_type: int | None = None
    quoted_text: str | None = None
    reply_to: dict[str, Any] = field(default_factory=lambda: {"matched": False})


@register_platform_adapter(
    "weixin_oc",
    "个人微信",
    support_streaming_message=False,
)
class WeixinOCAdapter(Platform):
    SESSION_TIMEOUT_ERRCODE = -14
    IMAGE_ITEM_TYPE = 2
    VOICE_ITEM_TYPE = 3
    FILE_ITEM_TYPE = 4
    VIDEO_ITEM_TYPE = 5
    IMAGE_UPLOAD_TYPE = 1
    VIDEO_UPLOAD_TYPE = 2
    FILE_UPLOAD_TYPE = 3
    RECENT_MESSAGE_CACHE_SIZE = 100
    REPLY_MATCH_WINDOW_MS = 60_000
    RECENT_SESSION_CACHE_TTL_S = 1_800
    MAX_RECENT_MESSAGE_SESSIONS = 500

    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)

        self.settings = platform_settings
        self.base_url = str(
            platform_config.get("weixin_oc_base_url", "https://ilinkai.weixin.qq.com")
        ).rstrip("/")
        self.bot_type = str(platform_config.get("weixin_oc_bot_type", "3"))
        self.qr_poll_interval = max(
            1,
            int(platform_config.get("weixin_oc_qr_poll_interval", 1)),
        )
        self.long_poll_timeout_ms = int(
            platform_config.get("weixin_oc_long_poll_timeout_ms", 35_000),
        )
        self.api_timeout_ms = int(
            platform_config.get("weixin_oc_api_timeout_ms", 15_000),
        )
        self.cdn_base_url = str(
            platform_config.get(
                "weixin_oc_cdn_base_url",
                "https://novac2c.cdn.weixin.qq.com/c2c",
            )
        ).rstrip("/")

        self.metadata = PlatformMetadata(
            name="weixin_oc",
            description="个人微信",
            id=cast(str, self.config.get("id", "weixin_oc")),
            support_streaming_message=False,
        )

        self._shutdown_event = asyncio.Event()
        self._login_session: OpenClawLoginSession | None = None
        self._sync_buf = ""
        self._qr_expired_count = 0
        self._context_tokens: dict[str, str] = {}
        self._context_tokens_dirty = False
        self._typing_states: dict[str, TypingSessionState] = {}
        self._last_inbound_error = ""
        self._recent_message_cache_size = self._get_int_config(
            "weixin_oc_recent_message_cache_size",
            self.RECENT_MESSAGE_CACHE_SIZE,
            1,
        )
        self._recent_session_cache_ttl_s = self._get_int_config(
            "weixin_oc_recent_session_cache_ttl_s",
            self.RECENT_SESSION_CACHE_TTL_S,
            60,
        )
        self._max_recent_message_sessions = self._get_int_config(
            "weixin_oc_max_recent_message_sessions",
            self.MAX_RECENT_MESSAGE_SESSIONS,
            1,
        )
        self._recent_messages: dict[str, WeixinOCRecentSessionCache] = {}
        self._typing_keepalive_interval_s = max(
            1,
            int(platform_config.get("weixin_oc_typing_keepalive_interval", 5)),
        )
        self._typing_ticket_ttl_s = max(
            5,
            int(platform_config.get("weixin_oc_typing_ticket_ttl", 60)),
        )

        self.token = str(platform_config.get("weixin_oc_token", "")).strip() or None
        self.account_id = (
            str(platform_config.get("weixin_oc_account_id", "")).strip() or None
        )
        self._load_account_state()
        self.client = WeixinOCClient(
            adapter_id=self.meta().id,
            base_url=self.base_url,
            cdn_base_url=self.cdn_base_url,
            api_timeout_ms=self.api_timeout_ms,
            token=self.token,
        )

        if self.token:
            logger.info(
                "weixin_oc adapter %s loaded with token from config.",
                self.meta().id,
            )

    def _sync_client_state(self) -> None:
        self.client.base_url = self.base_url
        self.client.cdn_base_url = self.cdn_base_url
        self.client.api_timeout_ms = self.api_timeout_ms
        self.client.token = self.token

    def _get_int_config(
        self,
        key: str,
        default: int,
        minimum: int,
    ) -> int:
        try:
            value = int(self.config.get(key, default))
        except (TypeError, ValueError):
            value = default
        return max(minimum, value)

    def _get_typing_state(self, user_id: str) -> TypingSessionState:
        state = self._typing_states.get(user_id)
        if state is None:
            state = TypingSessionState()
            self._typing_states[user_id] = state
        return state

    def _typing_supported_for(self, user_id: str) -> bool:
        if not self.token:
            return False
        return bool(self._context_tokens.get(user_id))

    async def _cancel_task_safely(
        self,
        task: asyncio.Task | None,
        *,
        log_message: str | None = None,
        log_args: tuple[Any, ...] = (),
    ) -> None:
        if task is None or task.done():
            return

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            if log_message is not None:
                logger.warning(log_message, *log_args, exc_info=True)

    async def _ensure_typing_ticket(
        self,
        user_id: str,
        state: TypingSessionState,
    ) -> str | None:
        now = time.monotonic()
        context_token = self._context_tokens.get(user_id)
        if not context_token:
            return None

        if (
            state.ticket
            and state.ticket_context_token == context_token
            and state.refresh_after > now
        ):
            return state.ticket

        payload = await self.client.get_typing_config(user_id, context_token)
        if not self._is_successful_api_payload(payload):
            logger.warning(
                "weixin_oc(%s): getconfig failed for %s: %s",
                self.meta().id,
                user_id,
                self._format_api_error(payload),
            )
            return None

        ticket = str(payload.get("typing_ticket", "")).strip()
        if not ticket:
            return None

        state.ticket = ticket
        state.ticket_context_token = context_token
        state.refresh_after = time.monotonic() + self._typing_ticket_ttl_s
        return ticket

    async def _send_typing_state(
        self,
        user_id: str,
        ticket: str,
        *,
        cancel: bool,
    ) -> None:
        payload = await self.client.send_typing_state(user_id, ticket, cancel=cancel)
        if not self._is_successful_api_payload(payload):
            raise RuntimeError(
                f"sendtyping failed for {user_id}: {self._format_api_error(payload)}"
            )

    async def _run_typing_keepalive(self, user_id: str) -> None:
        restart_needed = False
        try:
            await self._typing_keepalive_loop(user_id)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            state = self._typing_states.get(user_id)
            if state is not None:
                async with state.lock:
                    state.refresh_after = 0.0
                    restart_needed = (
                        bool(state.owners) and not self._shutdown_event.is_set()
                    )
            logger.warning(
                "weixin_oc(%s): typing keepalive failed for %s: %s",
                self.meta().id,
                user_id,
                e,
            )
        finally:
            state = self._typing_states.get(user_id)
            current_task = asyncio.current_task()
            if state is not None and state.keepalive_task is current_task:
                state.keepalive_task = None

        if not restart_needed:
            return

        await asyncio.sleep(self._typing_keepalive_interval_s)
        state = self._typing_states.get(user_id)
        if state is None or self._shutdown_event.is_set():
            return

        async with state.lock:
            if not state.owners or state.keepalive_task is not None:
                return
            state.keepalive_task = asyncio.create_task(
                self._run_typing_keepalive(user_id)
            )

    async def _typing_keepalive_loop(self, user_id: str) -> None:
        while not self._shutdown_event.is_set():
            await asyncio.sleep(self._typing_keepalive_interval_s)
            state = self._typing_states.get(user_id)
            if state is None:
                return

            async with state.lock:
                if not state.owners:
                    return
                try:
                    ticket = await self._ensure_typing_ticket(user_id, state)
                except Exception as e:
                    state.refresh_after = 0.0
                    logger.warning(
                        "weixin_oc(%s): refresh typing ticket failed for %s: %s",
                        self.meta().id,
                        user_id,
                        e,
                    )
                    continue
                if not ticket:
                    continue
                try:
                    await self._send_typing_state(user_id, ticket, cancel=False)
                except Exception as e:
                    state.refresh_after = 0.0
                    logger.warning(
                        "weixin_oc(%s): typing keepalive send failed for %s: %s",
                        self.meta().id,
                        user_id,
                        e,
                    )

    async def _delayed_cancel_typing(self, user_id: str, ticket: str) -> None:
        await asyncio.sleep(0)
        state = self._typing_states.get(user_id)
        if state is None:
            return

        current_task = asyncio.current_task()
        async with state.lock:
            if state.cancel_task is not current_task:
                return
            if state.owners or state.keepalive_task is not None:
                state.cancel_task = None
                return

        try:
            await self._send_typing_state(user_id, ticket, cancel=True)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(
                "weixin_oc(%s): cancel typing failed for %s: %s",
                self.meta().id,
                user_id,
                e,
            )
        finally:
            state = self._typing_states.get(user_id)
            if state is None:
                return
            async with state.lock:
                if state.cancel_task is current_task:
                    state.cancel_task = None

    async def start_typing(self, user_id: str, owner_id: str) -> None:
        state = self._get_typing_state(user_id)
        cancel_task: asyncio.Task | None = None
        async with state.lock:
            if owner_id in state.owners:
                return
            if not self._typing_supported_for(user_id):
                return
            if state.cancel_task is not None and not state.cancel_task.done():
                cancel_task = state.cancel_task
                cancel_task.cancel()
                state.cancel_task = None
            try:
                ticket = await self._ensure_typing_ticket(user_id, state)
            except Exception as e:
                logger.warning(
                    "weixin_oc(%s): ensure typing ticket failed for %s: %s",
                    self.meta().id,
                    user_id,
                    e,
                )
                return
            if not ticket:
                return

            state.ticket = ticket
            state.owners.add(owner_id)
            if state.keepalive_task is not None and not state.keepalive_task.done():
                return

            try:
                await self._send_typing_state(user_id, ticket, cancel=False)
            except Exception as e:
                state.refresh_after = 0.0
                logger.warning(
                    "weixin_oc(%s): send typing failed for %s: %s",
                    self.meta().id,
                    user_id,
                    e,
                )

            task = asyncio.create_task(self._run_typing_keepalive(user_id))
            state.keepalive_task = task

        if cancel_task is not None:
            await self._cancel_task_safely(
                cancel_task,
                log_message="weixin_oc(%s): ignored error from cancelled typing task",
                log_args=(self.meta().id,),
            )

    async def stop_typing(self, user_id: str, owner_id: str) -> None:
        state = self._typing_states.get(user_id)
        if state is None:
            return

        task: asyncio.Task | None = None
        async with state.lock:
            if owner_id not in state.owners:
                return
            state.owners.remove(owner_id)

            if state.owners:
                return

            task = state.keepalive_task
            state.keepalive_task = None

        await self._cancel_task_safely(
            task,
            log_message="weixin_oc(%s): typing keepalive stop failed for %s",
            log_args=(self.meta().id, user_id),
        )

        async with state.lock:
            if state.owners:
                return
            ticket = state.ticket
            if ticket:
                if state.cancel_task is None or state.cancel_task.done():
                    state.cancel_task = asyncio.create_task(
                        self._delayed_cancel_typing(user_id, ticket)
                    )

    async def _cleanup_typing_tasks(self) -> None:
        tasks: list[asyncio.Task] = []
        cancels: list[tuple[str, str]] = []
        for user_id, state in list(self._typing_states.items()):
            if state.ticket and (
                state.owners
                or state.keepalive_task is not None
                or state.cancel_task is not None
            ):
                cancels.append((user_id, state.ticket))
            state.owners.clear()
            if state.keepalive_task is not None and not state.keepalive_task.done():
                tasks.append(state.keepalive_task)
                state.keepalive_task.cancel()
                state.keepalive_task = None
            if state.cancel_task is not None and not state.cancel_task.done():
                tasks.append(state.cancel_task)
                state.cancel_task.cancel()
                state.cancel_task = None

        for task in tasks:
            await self._cancel_task_safely(
                task,
                log_message="weixin_oc(%s): typing cleanup failed",
                log_args=(self.meta().id,),
            )

        for user_id, ticket in cancels:
            try:
                await self._send_typing_state(user_id, ticket, cancel=True)
            except Exception as e:
                logger.warning(
                    "weixin_oc(%s): typing cleanup cancel failed for %s: %s",
                    self.meta().id,
                    user_id,
                    e,
                )

    def _load_account_state(self) -> None:
        if not self.token:
            token = str(self.config.get("weixin_oc_token", "")).strip()
            if token:
                self.token = token
        if not self.account_id:
            account_id = str(self.config.get("weixin_oc_account_id", "")).strip()
            if account_id:
                self.account_id = account_id
        sync_buf = str(self.config.get("weixin_oc_sync_buf", "")).strip()
        if sync_buf:
            self._sync_buf = sync_buf
        saved_base = str(self.config.get("weixin_oc_base_url", "")).strip()
        if saved_base:
            self.base_url = saved_base.rstrip("/")
        raw_context_tokens = self.config.get("weixin_oc_context_tokens", {})
        if isinstance(raw_context_tokens, dict):
            self._context_tokens = self._normalize_context_tokens(raw_context_tokens)

    def _normalize_context_tokens(
        self, raw_context_tokens: Mapping[object, object]
    ) -> dict[str, str]:
        normalized_context_tokens: dict[str, str] = {}
        for user_id, context_token in raw_context_tokens.items():
            normalized_user_id = str(user_id).strip()
            normalized_context_token = str(context_token).strip()
            if not normalized_user_id or not normalized_context_token:
                continue
            normalized_context_tokens[normalized_user_id] = normalized_context_token
        return normalized_context_tokens

    async def _save_account_state(self) -> None:
        normalized_context_tokens = self._normalize_context_tokens(self._context_tokens)
        self.config["weixin_oc_token"] = self.token or ""
        self.config["weixin_oc_account_id"] = self.account_id or ""
        self.config["weixin_oc_sync_buf"] = self._sync_buf
        self.config["weixin_oc_base_url"] = self.base_url
        self.config["weixin_oc_context_tokens"] = normalized_context_tokens

        for platform in astrbot_config.get("platform", []):
            if not isinstance(platform, dict):
                continue
            if platform.get("id") != self.config.get("id"):
                continue
            if platform.get("type") != self.config.get("type"):
                continue
            platform["weixin_oc_token"] = self.token or ""
            platform["weixin_oc_account_id"] = self.account_id or ""
            platform["weixin_oc_sync_buf"] = self._sync_buf
            platform["weixin_oc_base_url"] = self.base_url
            platform["weixin_oc_context_tokens"] = normalized_context_tokens
            break

        self._sync_client_state()
        astrbot_config.save_config()
        self._context_tokens_dirty = False

    def _is_login_session_valid(
        self, login_session: OpenClawLoginSession | None
    ) -> bool:
        if not login_session:
            return False
        return (time.time() - login_session.started_at) * 1000 < 5 * 60_000

    def _resolve_inbound_media_dir(self) -> Path:
        media_dir = Path(get_astrbot_temp_path())
        media_dir.mkdir(parents=True, exist_ok=True)
        return media_dir

    @staticmethod
    def _normalize_inbound_filename(file_name: str, fallback_name: str) -> str:
        normalized = Path(file_name or "").name.strip()
        return normalized or fallback_name

    def _save_inbound_media(
        self,
        content: bytes,
        *,
        prefix: str,
        file_name: str,
        fallback_suffix: str,
    ) -> Path:
        normalized_name = self._normalize_inbound_filename(
            file_name,
            f"{prefix}{fallback_suffix}",
        )
        stem = Path(normalized_name).stem or prefix
        suffix = Path(normalized_name).suffix or fallback_suffix
        target = (
            self._resolve_inbound_media_dir()
            / f"{prefix}_{uuid.uuid4().hex}_{stem}{suffix}"
        )
        target.write_bytes(content)
        return target

    @staticmethod
    def _build_plain_text_item(text: str) -> dict[str, Any]:
        return {
            "type": 1,
            "text_item": {
                "text": text,
            },
        }

    async def _prepare_media_item(
        self,
        user_id: str,
        media_path: Path,
        upload_media_type: int,
        item_type: int,
        file_name: str,
    ) -> dict[str, Any]:
        raw_bytes = media_path.read_bytes()
        raw_size = len(raw_bytes)
        raw_md5 = hashlib.md5(raw_bytes).hexdigest()
        file_key = uuid.uuid4().hex
        aes_key_hex = uuid.uuid4().bytes.hex()
        ciphertext_size = self.client.aes_padded_size(raw_size)

        payload = await self.client.request_json(
            "POST",
            "ilink/bot/getuploadurl",
            payload={
                "filekey": file_key,
                "media_type": upload_media_type,
                "to_user_id": user_id,
                "rawsize": raw_size,
                "rawfilemd5": raw_md5,
                "filesize": ciphertext_size,
                "no_need_thumb": True,
                "aeskey": aes_key_hex,
                "base_info": {
                    "channel_version": "astrbot",
                },
            },
            token_required=True,
            timeout_ms=self.api_timeout_ms,
        )
        logger.debug(
            "weixin_oc(%s): getuploadurl response user=%s media_type=%s raw_size=%s raw_md5=%s filekey=%s file=%s upload_param_len=%s",
            self.meta().id,
            user_id,
            upload_media_type,
            raw_size,
            raw_md5,
            file_key,
            media_path.name,
            len(str(payload.get("upload_param", ""))),
        )
        upload_param = str(payload.get("upload_param", "")).strip()
        upload_full_url = str(payload.get("upload_full_url", "")).strip()

        encrypted_query_param = await self.client.upload_to_cdn(
            upload_full_url,
            upload_param,
            file_key,
            aes_key_hex,
            media_path,
        )
        logger.debug(
            "weixin_oc(%s): prepared media item type=%s file=%s user=%s mid_size=%s upload_param_len=%s query_len=%s",
            self.meta().id,
            item_type,
            media_path.name,
            user_id,
            ciphertext_size,
            len(upload_param),
            len(encrypted_query_param),
        )

        aes_key_b64 = base64.b64encode(aes_key_hex.encode("utf-8")).decode("utf-8")
        media_payload = {
            "encrypt_query_param": encrypted_query_param,
            "aes_key": aes_key_b64,
            "encrypt_type": 1,
        }

        if item_type == self.IMAGE_ITEM_TYPE:
            return {
                "type": self.IMAGE_ITEM_TYPE,
                "image_item": {
                    "media": media_payload,
                    "mid_size": ciphertext_size,
                },
            }
        if item_type == self.VIDEO_ITEM_TYPE:
            return {
                "type": self.VIDEO_ITEM_TYPE,
                "video_item": {
                    "media": media_payload,
                    "video_size": ciphertext_size,
                },
            }

        file_len = str(raw_size)
        return {
            "type": self.FILE_ITEM_TYPE,
            "file_item": {
                "media": media_payload,
                "file_name": file_name,
                "len": file_len,
            },
        }

    async def _resolve_inbound_media_component(
        self,
        item: dict[str, Any],
    ) -> Image | Video | File | Record | None:
        item_type = int(item.get("type") or 0)

        if item_type == self.IMAGE_ITEM_TYPE:
            image_item = cast(dict[str, Any], item.get("image_item", {}) or {})
            media = cast(dict[str, Any], image_item.get("media", {}) or {})
            encrypted_query_param = str(media.get("encrypt_query_param", "")).strip()
            if not encrypted_query_param:
                return None
            image_aes_key = str(image_item.get("aeskey", "")).strip()
            if image_aes_key:
                aes_key_value = base64.b64encode(bytes.fromhex(image_aes_key)).decode(
                    "utf-8"
                )
            else:
                aes_key_value = str(media.get("aes_key", "")).strip()
            if aes_key_value:
                content = await self.client.download_and_decrypt_media(
                    encrypted_query_param,
                    aes_key_value,
                )
            else:
                content = await self.client.download_cdn_bytes(encrypted_query_param)
            image_path = self._save_inbound_media(
                content,
                prefix="weixin_oc_img",
                file_name="image.jpg",
                fallback_suffix=".jpg",
            )
            return Image.fromFileSystem(str(image_path))

        if item_type == self.VIDEO_ITEM_TYPE:
            video_item = cast(dict[str, Any], item.get("video_item", {}) or {})
            media = cast(dict[str, Any], video_item.get("media", {}) or {})
            encrypted_query_param = str(media.get("encrypt_query_param", "")).strip()
            aes_key_value = str(media.get("aes_key", "")).strip()
            if not encrypted_query_param or not aes_key_value:
                return None
            content = await self.client.download_and_decrypt_media(
                encrypted_query_param,
                aes_key_value,
            )
            video_path = self._save_inbound_media(
                content,
                prefix="weixin_oc_video",
                file_name="video.mp4",
                fallback_suffix=".mp4",
            )
            return Video.fromFileSystem(str(video_path))

        if item_type == self.FILE_ITEM_TYPE:
            file_item = cast(dict[str, Any], item.get("file_item", {}) or {})
            media = cast(dict[str, Any], file_item.get("media", {}) or {})
            encrypted_query_param = str(media.get("encrypt_query_param", "")).strip()
            aes_key_value = str(media.get("aes_key", "")).strip()
            if not encrypted_query_param or not aes_key_value:
                return None
            file_name = self._normalize_inbound_filename(
                str(file_item.get("file_name", "")).strip(),
                "file.bin",
            )
            content = await self.client.download_and_decrypt_media(
                encrypted_query_param,
                aes_key_value,
            )
            file_path = self._save_inbound_media(
                content,
                prefix="weixin_oc_file",
                file_name=file_name,
                fallback_suffix=".bin",
            )
            return File(name=file_name, file=str(file_path))

        if item_type == self.VOICE_ITEM_TYPE:
            voice_item = cast(dict[str, Any], item.get("voice_item", {}) or {})
            media = cast(dict[str, Any], voice_item.get("media", {}) or {})
            encrypted_query_param = str(media.get("encrypt_query_param", "")).strip()
            aes_key_value = str(media.get("aes_key", "")).strip()
            if not encrypted_query_param or not aes_key_value:
                return None
            content = await self.client.download_and_decrypt_media(
                encrypted_query_param,
                aes_key_value,
            )
            voice_path = self._save_inbound_media(
                content,
                prefix="weixin_oc_voice",
                file_name="voice.silk",
                fallback_suffix=".silk",
            )
            return Record.fromFileSystem(str(voice_path))

        return None

    async def _resolve_media_file_path(
        self, segment: Image | Video | File
    ) -> Path | None:
        try:
            if isinstance(segment, File):
                path = await segment.get_file()
            elif isinstance(segment, (Image, Video)):
                path = await segment.convert_to_file_path()
            else:
                path = ""
        except Exception as e:
            logger.warning("weixin_oc(%s): media resolve failed: %s", self.meta().id, e)
            return None

        if not path:
            return None
        media_path = Path(path)
        if not media_path.exists() or not media_path.is_file():
            return None
        return media_path

    async def _send_items_to_session(
        self,
        user_id: str,
        item_list: list[dict[str, Any]],
        *,
        cache_components: list[Any] | None = None,
        cache_message_str: str | None = None,
    ) -> bool:
        if not self.token:
            logger.warning("weixin_oc(%s): missing token, skip send", self.meta().id)
            return False
        if not item_list:
            logger.warning(
                "weixin_oc(%s): empty message payload is ignored",
                self.meta().id,
            )
            return False
        context_token = self._context_tokens.get(user_id)
        if not context_token:
            logger.warning(
                "weixin_oc(%s): context token missing for %s, skip send. You should send one message to refresh context_token.",
                self.meta().id,
                user_id,
            )
            return False
        payload = await self.client.request_json(
            "POST",
            "ilink/bot/sendmessage",
            payload={
                "base_info": {
                    "channel_version": "astrbot",
                },
                "msg": {
                    "from_user_id": "",
                    "to_user_id": user_id,
                    "client_id": uuid.uuid4().hex,
                    "message_type": 2,
                    "message_state": 2,
                    "context_token": context_token,
                    "item_list": item_list,
                },
            },
            token_required=True,
            headers={},
        )
        if not self._is_successful_api_payload(payload):
            logger.warning(
                "weixin_oc(%s): sendmessage failed for %s: %s",
                self.meta().id,
                user_id,
                self._format_api_error(payload),
            )
            return False
        resolved_cache_components = (
            list(cache_components)
            if cache_components is not None
            else self._build_cache_components_from_items(item_list)
        )
        sender_id = str(self.account_id or self.meta().id)
        sent_at_ms = time.time_ns() // 1_000_000
        self._cache_recent_message(
            user_id,
            message_id=uuid.uuid4().hex,
            sender_id=sender_id,
            sender_nickname=sender_id,
            timestamp=sent_at_ms // 1000,
            timestamp_ms=sent_at_ms,
            components=resolved_cache_components,
            message_str=cache_message_str
            if cache_message_str is not None
            else self._message_text_from_item_list(
                item_list,
                include_ref_text=False,
            ),
        )
        return True

    def _build_cache_components_from_items(
        self,
        item_list: list[dict[str, Any]],
    ) -> list[Any]:
        components: list[Any] = []
        for item in item_list:
            item_type = int(item.get("type") or 0)
            if item_type != 1:
                continue
            text = str(item.get("text_item", {}).get("text", "")).strip()
            if text:
                components.append(Plain(text))
        return components

    @staticmethod
    def _is_successful_api_payload(payload: dict[str, Any]) -> bool:
        ret = payload.get("ret", 0)
        errcode = payload.get("errcode", 0)
        return int(ret or 0) == 0 and int(errcode or 0) == 0

    @staticmethod
    def _format_api_error(payload: dict[str, Any]) -> str:
        ret = int(payload.get("ret") or 0)
        errcode = int(payload.get("errcode") or 0)
        errmsg = str(payload.get("errmsg", ""))
        return f"ret={ret}, errcode={errcode}, errmsg={errmsg}"

    @staticmethod
    def _api_errcode(payload: dict[str, Any]) -> int:
        return int(payload.get("errcode") or 0)

    async def _handle_inbound_session_timeout(self) -> None:
        logger.warning(
            "weixin_oc(%s): session timed out, clearing login state and waiting for QR login.",
            self.meta().id,
        )
        self.token = None
        self.account_id = None
        self._sync_buf = ""
        self._context_tokens = {}
        self._context_tokens_dirty = False
        self._login_session = None
        await self._save_account_state()

    async def _send_media_segment(
        self,
        user_id: str,
        segment: Image | Video | File,
        text: str | None = None,
    ) -> bool:
        if not self.token:
            logger.warning(
                "weixin_oc(%s): missing token, skip media send", self.meta().id
            )
            return False
        media_path = await self._resolve_media_file_path(segment)
        if media_path is None:
            logger.warning(
                "weixin_oc(%s): skip media segment, media file not resolvable",
                self.meta().id,
            )
            return False

        item_type = self.IMAGE_ITEM_TYPE
        upload_media_type = self.IMAGE_UPLOAD_TYPE
        if isinstance(segment, Video):
            item_type = self.VIDEO_ITEM_TYPE
            upload_media_type = self.VIDEO_UPLOAD_TYPE
        elif isinstance(segment, File):
            item_type = self.FILE_ITEM_TYPE
            upload_media_type = self.FILE_UPLOAD_TYPE

        file_name = (
            segment.name
            if isinstance(segment, File) and segment.name
            else media_path.name
        )
        try:
            media_item = await self._prepare_media_item(
                user_id,
                media_path,
                upload_media_type,
                item_type,
                file_name,
            )
        except Exception as e:
            logger.error(
                "weixin_oc(%s): prepare media failed: %s",
                self.meta().id,
                e,
                exc_info=True,
            )
            return False

        if text:
            await self._send_items_to_session(
                user_id,
                [self._build_plain_text_item(text)],
                cache_components=[Plain(text)],
                cache_message_str=text,
            )
        return await self._send_items_to_session(
            user_id,
            [media_item],
            cache_components=[segment],
            cache_message_str=self._message_text_from_item_list(
                [media_item],
                include_ref_text=False,
            ),
        )

    async def _start_login_session(self) -> OpenClawLoginSession:
        endpoint = "ilink/bot/get_bot_qrcode"
        params = {"bot_type": self.bot_type}
        logger.info("weixin_oc(%s): request QR code from %s", self.meta().id, endpoint)
        data = await self.client.request_json(
            "GET",
            endpoint,
            params=params,
            token_required=False,
            timeout_ms=15_000,
        )
        qrcode = str(data.get("qrcode", "")).strip()
        qrcode_url = str(data.get("qrcode_img_content", "")).strip()
        if not qrcode or not qrcode_url:
            raise RuntimeError("qrcode response missing qrcode or qrcode_img_content")
        qr_console_url = (
            f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data="
            f"{quote(qrcode_url)}"
        )
        logger.info(
            "weixin_oc(%s): QR session started, qr_link=%s 请使用手机微信扫码登录，二维码有效期 5 分钟，过期后会自动刷新。",
            self.meta().id,
            qr_console_url,
        )
        try:
            qr = qrcode_lib.QRCode(border=1)
            qr.add_data(qrcode_url)
            qr.make(fit=True)
            qr_buffer = io.StringIO()
            qr.print_ascii(out=qr_buffer, tty=False)
            logger.info(
                "weixin_oc(%s): terminal QR code:\n%s",
                self.meta().id,
                qr_buffer.getvalue(),
            )
        except Exception as e:
            logger.warning(
                "weixin_oc(%s): failed to render terminal QR code: %s",
                self.meta().id,
                e,
            )
        login_session = OpenClawLoginSession(
            session_key=str(uuid.uuid4()),
            qrcode=qrcode,
            qrcode_img_content=qrcode_url,
            started_at=time.time(),
        )
        self._login_session = login_session
        self._qr_expired_count = 0
        self._last_inbound_error = ""
        return login_session

    async def _poll_qr_status(self, login_session: OpenClawLoginSession) -> None:
        endpoint = "ilink/bot/get_qrcode_status"
        logger.debug("weixin_oc(%s): poll qrcode status", self.meta().id)
        data = await self.client.request_json(
            "GET",
            endpoint,
            params={"qrcode": login_session.qrcode},
            token_required=False,
            timeout_ms=self.long_poll_timeout_ms,
            headers={"iLink-App-ClientVersion": "1"},
        )
        status = str(data.get("status", "wait")).strip()
        login_session.status = status
        if status == "expired":
            self._qr_expired_count += 1
            if self._qr_expired_count > 3:
                login_session.error = "二维码已过期，超过重试次数，等待下次重试"
                self._login_session = None
                return
            logger.warning(
                "weixin_oc(%s): qr expired, refreshing (%s/%s)",
                self.meta().id,
                self._qr_expired_count,
                3,
            )
            new_session = await self._start_login_session()
            self._login_session = new_session
            return

        if status == "confirmed":
            bot_token = data.get("bot_token")
            account_id = data.get("ilink_bot_id")
            base_url = data.get("baseurl")
            user_id = data.get("ilink_user_id")
            if not bot_token:
                login_session.error = "登录返回成功但未返回 bot_token"
                return
            login_session.bot_token = str(bot_token)
            login_session.account_id = str(account_id) if account_id else None
            login_session.base_url = str(base_url) if base_url else self.base_url
            login_session.user_id = str(user_id) if user_id else None
            self.token = login_session.bot_token
            self.account_id = login_session.account_id
            if login_session.base_url:
                self.base_url = login_session.base_url.rstrip("/")
            await self._save_account_state()

    def _message_text_from_item_list(
        self,
        item_list: list[dict[str, Any]] | None,
        *,
        include_ref_text: bool = False,
    ) -> str:
        if not item_list:
            return ""
        text_parts: list[str] = []
        for item in item_list:
            item_type = int(item.get("type") or 0)
            if item_type == 1:
                text = str(item.get("text_item", {}).get("text", "")).strip()
                if text:
                    text_parts.append(text)
            elif item_type == 2:
                text_parts.append("[图片]")
            elif item_type == 3:
                voice_text = str(item.get("voice_item", {}).get("text", "")).strip()
                if voice_text:
                    text_parts.append(voice_text)
                else:
                    text_parts.append("[语音]")
            elif item_type == 4:
                text_parts.append("[文件]")
            elif item_type == 5:
                text_parts.append("[视频]")
            else:
                if include_ref_text:
                    ref = item.get("ref_msg")
                    if isinstance(ref, dict):
                        ref_item = ref.get("message_item")
                        if isinstance(ref_item, dict):
                            ref_text = str(
                                self._message_text_from_item_list(
                                    [ref_item],
                                    include_ref_text=True,
                                )
                            )
                            if ref_text:
                                text_parts.append(f"[引用:{ref_text}]")
        return "\n".join(text_parts).strip()

    def _item_type_to_kind(self, item_type: int | None) -> str:
        match int(item_type or 0):
            case 1:
                return "text"
            case self.IMAGE_ITEM_TYPE:
                return "image"
            case self.VOICE_ITEM_TYPE:
                return "voice"
            case self.FILE_ITEM_TYPE:
                return "file"
            case self.VIDEO_ITEM_TYPE:
                return "video"
            case _:
                return "unknown"

    def _get_recent_message_cache(
        self,
        session_id: str,
    ) -> deque[WeixinOCRecentMessage]:
        now = time.monotonic()
        self._prune_recent_message_caches(now=now)

        cache_entry = self._recent_messages.get(session_id)
        if cache_entry is None:
            cache_entry = WeixinOCRecentSessionCache(
                messages=deque(maxlen=self._recent_message_cache_size),
                updated_at=now,
            )
            self._recent_messages[session_id] = cache_entry
        else:
            cache_entry.updated_at = now
        return cache_entry.messages

    def _prune_recent_message_caches(self, *, now: float | None = None) -> None:
        if not self._recent_messages:
            return

        current = now if now is not None else time.monotonic()
        expired_session_ids = [
            session_id
            for session_id, cache_entry in self._recent_messages.items()
            if current - cache_entry.updated_at > self._recent_session_cache_ttl_s
        ]
        for session_id in expired_session_ids:
            self._recent_messages.pop(session_id, None)

        overflow = len(self._recent_messages) - self._max_recent_message_sessions
        if overflow <= 0:
            return

        oldest_session_ids = sorted(
            self._recent_messages,
            key=lambda session_id: self._recent_messages[session_id].updated_at,
        )[:overflow]
        for session_id in oldest_session_ids:
            self._recent_messages.pop(session_id, None)

    def _infer_message_kind_from_components(self, components: list[Any]) -> str:
        if not components:
            return "unknown"
        for component in components:
            if isinstance(component, Plain) and component.text.strip():
                return "text"
            if isinstance(component, Image):
                return "image"
            if isinstance(component, Record):
                return "voice"
            if isinstance(component, File):
                return "file"
            if isinstance(component, Video):
                return "video"
        return "unknown"

    def _cache_recent_message(
        self,
        session_id: str,
        *,
        message_id: str,
        sender_id: str,
        sender_nickname: str,
        timestamp: int,
        timestamp_ms: int | None = None,
        components: list[Any],
        message_str: str,
        message_kind: str | None = None,
    ) -> None:
        if not session_id or not message_id:
            return
        resolved_timestamp_ms = (
            timestamp_ms if timestamp_ms is not None else timestamp * 1000
        )
        cache = self._get_recent_message_cache(session_id)
        cache.append(
            WeixinOCRecentMessage(
                message_id=message_id,
                sender_id=sender_id,
                sender_nickname=sender_nickname,
                timestamp=timestamp,
                timestamp_ms=resolved_timestamp_ms,
                components=list(components),
                message_str=message_str,
                message_kind=message_kind
                or self._infer_message_kind_from_components(components),
            )
        )

    def _match_recent_reply(
        self,
        session_id: str,
        *,
        ref_create_time_ms: int | None,
    ) -> tuple[WeixinOCRecentMessage | None, dict[str, Any] | None]:
        if not session_id or ref_create_time_ms is None:
            return None, None

        best_match: WeixinOCRecentMessage | None = None
        best_distance: int | None = None
        self._prune_recent_message_caches()
        cache_entry = self._recent_messages.get(session_id)
        if cache_entry is None:
            return None, None

        for candidate in cache_entry.messages:
            distance = abs(candidate.timestamp_ms - ref_create_time_ms)
            if distance > self.REPLY_MATCH_WINDOW_MS:
                continue
            if best_distance is None or distance < best_distance:
                best_match = candidate
                best_distance = distance

        if best_match is None or best_distance is None:
            return None, None

        confidence = max(
            0.0,
            min(1.0, 1.0 - (best_distance / self.REPLY_MATCH_WINDOW_MS)),
        )
        return best_match, {
            "matched": True,
            "strategy": "nearest-message-by-timestamp",
            "ref_create_time_ms": ref_create_time_ms,
            "matched_message_id": best_match.message_id,
            "matched_kind": best_match.message_kind,
            "distance_ms": best_distance,
            "confidence": round(confidence, 4),
        }

    async def _build_reply_component_from_ref(
        self,
        *,
        session_id: str,
        ref_msg: dict[str, Any],
    ) -> tuple[Reply | None, WeixinOCReplyMeta]:
        metadata = WeixinOCReplyMeta(ref_msg=ref_msg)
        message_item = ref_msg.get("message_item")
        if not isinstance(message_item, dict):
            return None, metadata

        quoted_item_type_raw = message_item.get("type")
        try:
            quoted_item_type = (
                int(quoted_item_type_raw)
                if quoted_item_type_raw not in (None, "")
                else None
            )
        except (TypeError, ValueError):
            quoted_item_type = None
        metadata.quoted_item_type = quoted_item_type
        metadata.reply_kind = self._item_type_to_kind(quoted_item_type)

        ref_create_time_ms_raw = message_item.get("create_time_ms")
        try:
            ref_create_time_ms = (
                int(ref_create_time_ms_raw)
                if ref_create_time_ms_raw not in (None, "")
                else None
            )
        except (TypeError, ValueError):
            ref_create_time_ms = None

        quoted_components: list[Any] = []
        quoted_text = ""
        if quoted_item_type is not None:
            quoted_components = await self._item_list_to_components([message_item])
            quoted_text = self._message_text_from_item_list(
                [message_item],
                include_ref_text=False,
            )

        if quoted_text:
            metadata.quoted_text = quoted_text
            metadata.reply_to = {
                "matched": True,
                "strategy": "direct-ref-msg",
                "matched_kind": metadata.reply_kind,
                "matched_text": quoted_text,
                "confidence": 1.0,
            }

        matched_message = None
        matched_reply_to = None
        if not quoted_text or not quoted_components:
            matched_message, matched_reply_to = self._match_recent_reply(
                session_id,
                ref_create_time_ms=ref_create_time_ms,
            )
            if matched_message is not None:
                quoted_components = list(matched_message.components)
                quoted_text = matched_message.message_str
                metadata.quoted_text = quoted_text or None
                metadata.reply_kind = matched_message.message_kind
                metadata.reply_to = matched_reply_to or {"matched": True}

        if not quoted_text and not quoted_components:
            return None, metadata

        metadata.is_reply = True

        reply_message_id = (
            matched_message.message_id
            if matched_message is not None
            else str(
                message_item.get("message_id")
                or message_item.get("msg_id")
                or f"weixin_oc_ref_{ref_create_time_ms or uuid.uuid4().hex}"
            )
        )
        quoted_sender_id_raw = str(message_item.get("from_user_id") or "unknown")
        reply_sender_id_raw = (
            matched_message.sender_id
            if matched_message is not None
            else quoted_sender_id_raw
        )
        normalized_reply_sender_id = self._normalize_reply_sender_id(
            reply_sender_id_raw
        )
        reply_sender_id = (
            normalized_reply_sender_id
            if normalized_reply_sender_id
            else reply_sender_id_raw
        )
        reply_sender_nickname = (
            matched_message.sender_nickname
            if matched_message is not None
            else quoted_sender_id_raw
        )
        reply_time = (
            matched_message.timestamp
            if matched_message is not None
            else (
                int(ref_create_time_ms / 1000)
                if isinstance(ref_create_time_ms, int)
                else int(time.time())
            )
        )

        return (
            Reply(
                id=reply_message_id,
                chain=quoted_components,
                sender_id=reply_sender_id,
                sender_nickname=reply_sender_nickname,
                time=reply_time,
                message_str=quoted_text,
                text=quoted_text,
            ),
            metadata,
        )

    def _normalize_reply_sender_id(self, sender_id: str) -> str:
        normalized_sender_id = sender_id.strip()
        if not normalized_sender_id:
            return normalized_sender_id
        if self.account_id and normalized_sender_id == str(self.account_id):
            return self.meta().id
        return normalized_sender_id

    async def _item_list_to_components(
        self, item_list: list[dict[str, Any]] | None
    ) -> list[Any]:
        if not item_list:
            return []
        parts: list[Any] = []
        for item in item_list:
            item_type = int(item.get("type") or 0)
            if item_type == 1:
                text = str(item.get("text_item", {}).get("text", "")).strip()
                if text:
                    parts.append(Plain(text))
                continue
            try:
                media_component = await self._resolve_inbound_media_component(item)
            except Exception as e:
                logger.warning(
                    "weixin_oc(%s): resolve inbound media failed: %s",
                    self.meta().id,
                    e,
                )
                media_component = None
            if media_component is not None:
                parts.append(media_component)
        return parts

    async def _handle_inbound_message(self, msg: dict[str, Any]) -> None:
        from_user_id = str(msg.get("from_user_id", "")).strip()
        if not from_user_id:
            logger.debug("weixin_oc: skip message with empty from_user_id.")
            return

        context_token = str(msg.get("context_token", "")).strip()
        if context_token:
            previous_context_token = self._context_tokens.get(from_user_id)
            if previous_context_token != context_token:
                self._context_tokens[from_user_id] = context_token
                self._context_tokens_dirty = True

        item_list = cast(list[dict[str, Any]], msg.get("item_list", []))
        reply_component = None
        reply_metadata = WeixinOCReplyMeta()
        for item in item_list:
            ref_msg = item.get("ref_msg")
            if isinstance(ref_msg, dict):
                (
                    reply_component,
                    reply_metadata,
                ) = await self._build_reply_component_from_ref(
                    session_id=from_user_id,
                    ref_msg=ref_msg,
                )
                break
        cached_components = await self._item_list_to_components(item_list)
        components = list(cached_components)
        if reply_component is not None:
            components.insert(0, reply_component)
        text = self._message_text_from_item_list(item_list, include_ref_text=False)
        message_id = str(msg.get("message_id") or msg.get("msg_id") or uuid.uuid4().hex)
        create_time = msg.get("create_time_ms") or msg.get("create_time")
        create_time_ms: int | None = None
        if isinstance(create_time, (int, float)) and create_time > 1_000_000_000_000:
            create_time_ms = int(create_time)
            ts = int(float(create_time) / 1000)
        elif isinstance(create_time, (int, float)):
            ts = int(create_time)
            create_time_ms = ts * 1000
        else:
            ts = int(time.time())
            create_time_ms = ts * 1000

        abm = AstrBotMessage()
        abm.self_id = self.meta().id
        abm.sender = MessageMember(user_id=from_user_id, nickname=from_user_id)
        abm.type = MessageType.FRIEND_MESSAGE
        abm.session_id = from_user_id
        abm.message_id = message_id
        abm.message = components
        abm.message_str = text
        abm.timestamp = ts
        abm.raw_message = msg
        abm.is_reply = reply_metadata.is_reply
        abm.ref_msg = reply_metadata.ref_msg
        abm.reply_kind = reply_metadata.reply_kind
        abm.quoted_item_type = reply_metadata.quoted_item_type
        abm.quoted_text = reply_metadata.quoted_text
        abm.reply_to = reply_metadata.reply_to

        self._cache_recent_message(
            from_user_id,
            message_id=message_id,
            sender_id=from_user_id,
            sender_nickname=from_user_id,
            timestamp=ts,
            timestamp_ms=create_time_ms,
            components=cached_components,
            message_str=text,
        )

        self.commit_event(
            WeixinOCMessageEvent(
                message_str=text,
                message_obj=abm,
                platform_meta=self.meta(),
                session_id=abm.session_id,
                platform=self,
            )
        )

    async def _poll_inbound_updates(self) -> None:
        data = await self.client.request_json(
            "POST",
            "ilink/bot/getupdates",
            payload={
                "base_info": {
                    "channel_version": "astrbot",
                },
                "get_updates_buf": self._sync_buf,
            },
            token_required=True,
            timeout_ms=self.long_poll_timeout_ms,
        )
        if not self._is_successful_api_payload(data):
            self._last_inbound_error = self._format_api_error(data)
            logger.warning(
                "weixin_oc(%s): getupdates error: %s",
                self.meta().id,
                self._last_inbound_error,
            )
            if self._api_errcode(data) == self.SESSION_TIMEOUT_ERRCODE:
                await self._handle_inbound_session_timeout()
                return
            await asyncio.sleep(5)
            return

        should_save_state = self._context_tokens_dirty
        if data.get("get_updates_buf"):
            self._sync_buf = str(data.get("get_updates_buf"))
            should_save_state = True

        for msg in data.get("msgs", []) if isinstance(data.get("msgs"), list) else []:
            if self._shutdown_event.is_set():
                return
            if not isinstance(msg, dict):
                continue
            await self._handle_inbound_message(msg)
        if should_save_state:
            await self._save_account_state()

    def _message_chain_to_text(self, message_chain: MessageChain) -> str:
        text = ""
        for segment in message_chain.chain:
            if isinstance(segment, Plain):
                text += segment.text
        return text.strip()

    async def _send_to_session(
        self, user_id: str, text: str, _components: list[Any] | None = None
    ) -> bool:
        if not text:
            text = self._message_chain_to_text(MessageChain(_components or []))
        if not text:
            logger.warning(
                "weixin_oc(%s): message without plain text is ignored",
                self.meta().id,
            )
            return False
        return await self._send_items_to_session(
            user_id,
            [self._build_plain_text_item(text)],
        )

    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ) -> None:
        target_user = session.session_id
        pending_text = ""
        has_supported_segment = False
        failed_segments = 0
        for segment in message_chain.chain:
            if isinstance(segment, Plain):
                pending_text += segment.text
                continue

            if isinstance(segment, (Image, Video, File)):
                has_supported_segment = True
                sent = await self._send_media_segment(
                    target_user,
                    segment,
                    text=pending_text.strip() or None,
                )
                if not sent:
                    failed_segments += 1
                pending_text = ""
                continue

            logger.debug(
                "weixin_oc(%s): unsupported outbound segment type %s",
                self.meta().id,
                type(segment).__name__,
            )

        if pending_text:
            has_supported_segment = True
            sent = await self._send_to_session(target_user, pending_text.strip())
            if not sent:
                failed_segments += 1

        if not has_supported_segment:
            logger.warning(
                "weixin_oc(%s): outbound message ignored, no supported segments",
                self.meta().id,
            )
        if failed_segments:
            raise RuntimeError(
                f"weixin_oc({self.meta().id}, target_user={target_user}) "
                f"failed to send {failed_segments} message segment(s)"
            )
        await super().send_by_session(session, message_chain)

    def meta(self) -> PlatformMetadata:
        return self.metadata

    async def run(self) -> None:
        try:
            while not self._shutdown_event.is_set():
                if not self.token:
                    if not self._is_login_session_valid(self._login_session):
                        try:
                            self._login_session = await self._start_login_session()
                            self._qr_expired_count = 0
                        except Exception as e:
                            logger.error(
                                "weixin_oc(%s): start login failed: %s",
                                self.meta().id,
                                e,
                            )
                            await asyncio.sleep(5)
                            continue

                    current_login = self._login_session
                    if current_login is None:
                        continue

                    try:
                        await self._poll_qr_status(current_login)
                    except asyncio.TimeoutError:
                        logger.debug(
                            "weixin_oc(%s): qr status long-poll timeout",
                            self.meta().id,
                        )
                    except Exception as e:
                        logger.error(
                            "weixin_oc(%s): poll qr status failed: %s",
                            self.meta().id,
                            e,
                        )
                        current_login.error = str(e)
                        await asyncio.sleep(2)

                    if self.token:
                        logger.info(
                            "weixin_oc(%s): login confirmed, account=%s",
                            self.meta().id,
                            self.account_id or "",
                        )
                        continue

                    if current_login.error:
                        await asyncio.sleep(2)
                    else:
                        await asyncio.sleep(self.qr_poll_interval)
                    continue

                try:
                    await self._poll_inbound_updates()
                except asyncio.TimeoutError:
                    logger.debug(
                        "weixin_oc(%s): inbound long-poll timeout",
                        self.meta().id,
                    )
                except Exception as e:
                    logger.error(
                        "weixin_oc(%s): poll inbound updates failed, will retry after 5 seconds: %s",
                        self.meta().id,
                        e,
                    )
                    await asyncio.sleep(5)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("weixin_oc(%s): run failed: %s", self.meta().id, e)
        finally:
            await self._cleanup_typing_tasks()
            await self.client.close()

    async def terminate(self) -> None:
        self._shutdown_event.set()
        await self._cleanup_typing_tasks()

    def get_stats(self) -> dict:
        stat = super().get_stats()
        login_session = self._login_session
        stat["weixin_oc"] = {
            "configured": bool(self.token),
            "account_id": self.account_id,
            "base_url": self.base_url,
            "qr_session_key": login_session.session_key if login_session else None,
            "qr_status": login_session.status if login_session else None,
            "qrcode": login_session.qrcode if login_session else None,
            "qrcode_img_content": login_session.qrcode_img_content
            if login_session
            else None,
            "qr_error": login_session.error if login_session else None,
            "sync_buf_len": len(self._sync_buf),
            "last_error": self._last_inbound_error,
        }
        return stat
