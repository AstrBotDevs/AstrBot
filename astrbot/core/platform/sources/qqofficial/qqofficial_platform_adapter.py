from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import botpy
import botpy.message
from botpy import Client
from botpy.connection import ConnectionSession, ConnectionState
from botpy.gateway import BotWebSocket
from botpy.robot import Robot, Token

from astrbot import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import At, File, Image, Plain, Record, Video
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
)
from astrbot.core.message.components import BaseMessageComponent
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.core.utils.media_utils import MediaResolver

from ...register import register_platform_adapter
from .qqofficial_message_event import QQOfficialMessageEvent

# remove logger handler
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

_RECONNECT_DELAYS_SECONDS = (1, 2, 5, 10, 30, 60)
_RATE_LIMIT_RECONNECT_DELAY_SECONDS = 60
_MAX_QUICK_DISCONNECTS = 3
_QUICK_DISCONNECT_THRESHOLD_SECONDS = 5
_SESSION_INVALID_CLOSE_CODES = {4006, 4007, 4009}


class QQOfficialGatewayUnavailableError(RuntimeError):
    """Raised when qq-botpy returns unusable gateway metadata."""


class PatchedGroupMessage(botpy.message.GroupMessage):
    class _User:
        def __init__(self, data: dict[str, Any]) -> None:
            self.id = data.get("id", None)
            self.username = data.get("username", None)
            self.bot = data.get("bot", None)
            self.avatar = data.get("avatar", None)
            self.member_openid = data.get("member_openid", None)
            self.user_openid = data.get("user_openid", None)
            self.is_you = data.get("is_you", None)

        def __repr__(self) -> str:
            return str(self.__dict__)


def _ensure_group_message_create_parser() -> None:
    """Register the missing qq-botpy parser for GROUP_MESSAGE_CREATE."""

    if hasattr(ConnectionState, "parse_group_message_create"):
        return

    def parse_group_message_create(self, payload: dict[str, Any]) -> None:
        group_message = PatchedGroupMessage(
            self.api,
            payload.get("id", None),
            payload.get("d", {}),
        )
        logger.debug("[QQOfficial] Received group message: %s", group_message)
        self._dispatch("group_message_create", group_message)

    setattr(ConnectionState, "parse_group_message_create", parse_group_message_create)


class ManagedBotWebSocket(BotWebSocket):
    def __init__(self, session, connection: Any, client: botClient):
        super().__init__(session, connection)
        self._client = client
        self._heartbeat_interval_seconds: float | None = None
        self._last_heartbeat_ack_at = 0.0

    async def on_connected(self, ws) -> None:
        self._client.mark_websocket_connected()
        await super().on_connected(ws)

    async def on_message(self, ws, message) -> None:
        event = None
        try:
            payload = json.loads(message)
            event = payload.get("t")
        except Exception:
            pass

        await super().on_message(ws, message)

        if event in {"READY", "RESUMED"}:
            self._client.reset_reconnect_backoff()

    async def _is_system_event(self, message_event, ws):
        event_op = message_event["op"]
        if event_op == self.WS_HELLO:
            interval_ms = (message_event.get("d") or {}).get("heartbeat_interval")
            if isinstance(interval_ms, int | float) and interval_ms > 0:
                self._heartbeat_interval_seconds = interval_ms / 1000
                logger.info(f"[QQOfficial] Gateway heartbeat interval: {interval_ms}ms")
            return await super()._is_system_event(message_event, ws)
        if event_op == self.WS_HEARTBEAT_ACK:
            self._last_heartbeat_ack_at = time.monotonic()
            return True
        if event_op == self.WS_RECONNECT:
            logger.info("[QQOfficial] Gateway requested reconnect.")
            self._client.schedule_reconnect_delay("server requested reconnect")
            self._connection.add(self._session)
            await ws.close()
            return True
        if event_op == self.WS_INVALID_SESSION:
            can_resume = bool(message_event.get("d"))
            logger.warning(
                f"[QQOfficial] Gateway reported invalid session, can_resume={can_resume}."
            )
            if not can_resume:
                self._session["session_id"] = ""
                self._session["last_seq"] = 0
            self._client.schedule_reconnect_delay("invalid session", custom_delay=3)
            self._connection.add(self._session)
            await ws.close()
            return True
        return await super()._is_system_event(message_event, ws)

    async def _send_heart(self, interval):
        """Send gateway heartbeat using the interval announced by QQ."""

        heartbeat_interval = self._heartbeat_interval_seconds or interval
        logger.info(
            f"[QQOfficial] Heartbeat loop started, interval={heartbeat_interval}s."
        )
        while True:
            payload = {
                "op": self.WS_HEARTBEAT,
                "d": self._session["last_seq"],
            }

            if self._conn is None:
                logger.debug("[QQOfficial] Websocket is closed, stop heartbeat.")
                return
            if self._conn.closed:
                logger.debug("[QQOfficial] Websocket closed, stop heartbeat.")
                return

            await self.send_msg(json.dumps(payload))
            await asyncio.sleep(heartbeat_interval)

    async def on_closed(self, close_status_code, close_msg):
        if self._client.is_shutting_down:
            logger.debug("[QQOfficial] Ignore websocket reconnect during shutdown.")
            return
        rate_limited = close_status_code == 4008
        if close_status_code in _SESSION_INVALID_CLOSE_CODES or (
            isinstance(close_status_code, int) and 4900 <= close_status_code <= 4913
        ):
            self._can_reconnect = False
        self._client.schedule_reconnect_delay(
            f"websocket closed: {close_status_code} {close_msg}",
            rate_limited=rate_limited,
        )
        await super().on_closed(close_status_code, close_msg)

    async def on_error(self, exception: BaseException):
        if not self._client.is_shutting_down:
            self._client.schedule_reconnect_delay(f"websocket error: {exception}")
        await super().on_error(exception)

    async def close(self) -> None:
        self._can_reconnect = False
        if self._conn is not None and not self._conn.closed:
            await self._conn.close()


# QQ 机器人官方框架
class botClient(Client):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._shutting_down = False
        self._active_websockets: set[ManagedBotWebSocket] = set()
        self._next_connect_at = 0.0
        self._reconnect_attempts = 0
        self._last_connect_at = 0.0
        self._quick_disconnect_count = 0

    def set_platform(self, platform: QQOfficialPlatformAdapter) -> None:
        self.platform = platform

    @property
    def is_shutting_down(self) -> bool:
        return self._shutting_down or self.is_closed()

    async def _bot_login(self, token: Token) -> None:
        logger.info("[QQOfficial] 登录机器人账号中...")

        user = await self.http.login(token)
        self._ws_ap = await self.api.get_ws_url()
        session_limit = (
            self._ws_ap.get("session_start_limit")
            if isinstance(self._ws_ap, dict)
            else None
        )
        max_concurrency = (
            session_limit.get("max_concurrency")
            if isinstance(session_limit, dict)
            else None
        )
        if not isinstance(max_concurrency, int):
            raise QQOfficialGatewayUnavailableError(
                "gateway metadata unavailable during qq_official startup"
            )

        self._connection = ConnectionSession(
            max_async=max_concurrency,
            connect=self.bot_connect,
            dispatch=self.ws_dispatch,
            loop=self.loop,
            api=self.api,
        )
        self._connection.state.robot = Robot(user)

    def mark_websocket_connected(self) -> None:
        self._last_connect_at = time.monotonic()

    def reset_reconnect_backoff(self) -> None:
        if self._reconnect_attempts or self._quick_disconnect_count:
            logger.info("[QQOfficial] Websocket session resumed, reset backoff.")
        self._next_connect_at = 0.0
        self._reconnect_attempts = 0
        self._quick_disconnect_count = 0

    def schedule_reconnect_delay(
        self,
        reason: str,
        *,
        custom_delay: float | None = None,
        rate_limited: bool = False,
    ) -> None:
        """Schedule the next websocket connection attempt.

        Args:
            reason: Human-readable reason for logging.
            custom_delay: Explicit reconnect delay in seconds.
            rate_limited: Whether QQ reported gateway rate limiting.
        """

        if self.is_shutting_down:
            return

        delay = custom_delay
        if delay is None and rate_limited:
            delay = _RATE_LIMIT_RECONNECT_DELAY_SECONDS
        if delay is None:
            if self._last_connect_at:
                duration = time.monotonic() - self._last_connect_at
                if duration < _QUICK_DISCONNECT_THRESHOLD_SECONDS:
                    self._quick_disconnect_count += 1
                else:
                    self._quick_disconnect_count = 0
                if self._quick_disconnect_count >= _MAX_QUICK_DISCONNECTS:
                    delay = _RATE_LIMIT_RECONNECT_DELAY_SECONDS
                    self._quick_disconnect_count = 0
                    logger.warning(
                        "[QQOfficial] Too many quick disconnects; delaying reconnect."
                    )
            if delay is None:
                idx = min(
                    self._reconnect_attempts,
                    len(_RECONNECT_DELAYS_SECONDS) - 1,
                )
                delay = _RECONNECT_DELAYS_SECONDS[idx]
                self._reconnect_attempts += 1

        self._next_connect_at = max(self._next_connect_at, time.monotonic() + delay)
        logger.info(f"[QQOfficial] Reconnect scheduled in {delay}s, reason: {reason}")

    async def wait_for_reconnect_delay(self) -> None:
        delay = self._next_connect_at - time.monotonic()
        if delay <= 0:
            return
        logger.info(f"[QQOfficial] Waiting {delay:.1f}s before reconnect.")
        await asyncio.sleep(delay)

    # 收到群消息
    async def on_group_at_message_create(
        self, message: botpy.message.GroupMessage
    ) -> None:
        abm = await QQOfficialPlatformAdapter._parse_from_qqofficial(
            message,
            MessageType.GROUP_MESSAGE,
            force_group_mention=True,
        )
        abm.group_id = cast(str, message.group_openid)
        abm.session_id = abm.group_id
        self.platform.remember_session_scene(abm.session_id, "group")
        self._commit(abm)

    async def on_group_message_create(
        self, message: botpy.message.GroupMessage
    ) -> None:
        abm = await QQOfficialPlatformAdapter._parse_from_qqofficial(
            message,
            MessageType.GROUP_MESSAGE,
        )
        abm.group_id = cast(str, message.group_openid)
        abm.session_id = abm.group_id
        self.platform.remember_session_scene(abm.session_id, "group")
        self._commit(abm)

    # 收到频道消息
    async def on_at_message_create(self, message: botpy.message.Message) -> None:
        abm = await QQOfficialPlatformAdapter._parse_from_qqofficial(
            message,
            MessageType.GROUP_MESSAGE,
        )
        abm.group_id = message.channel_id
        abm.session_id = abm.group_id
        self.platform.remember_session_scene(abm.session_id, "channel")
        self._commit(abm)

    # 收到私聊消息
    async def on_direct_message_create(
        self, message: botpy.message.DirectMessage
    ) -> None:
        abm = await QQOfficialPlatformAdapter._parse_from_qqofficial(
            message,
            MessageType.FRIEND_MESSAGE,
        )
        abm.session_id = abm.sender.user_id
        self.platform.remember_session_scene(abm.session_id, "friend")
        self._commit(abm)

    # 收到 C2C 消息
    async def on_c2c_message_create(self, message: botpy.message.C2CMessage) -> None:
        abm = await QQOfficialPlatformAdapter._parse_from_qqofficial(
            message,
            MessageType.FRIEND_MESSAGE,
        )
        abm.session_id = abm.sender.user_id
        self.platform.remember_session_scene(abm.session_id, "friend")
        self._commit(abm)

    def _commit(self, abm: AstrBotMessage) -> None:
        self.platform.remember_session_message_id(abm.session_id, abm.message_id)
        self.platform.commit_event(self.platform.create_event(abm))

    async def bot_connect(self, session) -> None:
        await self.wait_for_reconnect_delay()
        if self.is_shutting_down:
            return
        logger.info("[QQOfficial] Websocket session starting.")

        websocket = ManagedBotWebSocket(session, self._connection, self)
        self._active_websockets.add(websocket)
        try:
            await websocket.ws_connect()
        except Exception as e:
            if not self.is_shutting_down:
                await websocket.on_error(e)
        finally:
            self._active_websockets.discard(websocket)

    async def shutdown(self) -> None:
        if self.is_shutting_down:
            return

        self._shutting_down = True
        await asyncio.gather(
            *(websocket.close() for websocket in list(self._active_websockets)),
            return_exceptions=True,
        )
        await self.close()


@register_platform_adapter("qq_official", "QQ 机器人官方 API 适配器")
class QQOfficialPlatformAdapter(Platform):
    STARTUP_RETRY_DELAYS_SECONDS = (5, 10, 30, 60)

    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)

        self.appid = platform_config["appid"]
        self.secret = platform_config["secret"]
        qq_group = platform_config["enable_group_c2c"]
        guild_dm = platform_config["enable_guild_direct_message"]

        if qq_group:
            self.intents = botpy.Intents(
                public_messages=True,
                public_guild_messages=True,
                direct_message=guild_dm,
            )
        else:
            self.intents = botpy.Intents(
                public_guild_messages=True,
                direct_message=guild_dm,
            )
        self._shutdown_event = asyncio.Event()
        self._startup_retry_attempts = 0
        self.client = self._create_client()

        _ensure_group_message_create_parser()

        self._session_last_message_id: dict[str, str] = {}
        self._session_scene: dict[str, str] = {}
        self._allow_group_proactive_send = True

        self.test_mode = os.environ.get("TEST_MODE", "off") == "on"

    def _create_client(self) -> botClient:
        client = botClient(
            intents=self.intents,
            bot_log=False,
            timeout=20,
        )
        client.set_platform(self)
        return client

    @staticmethod
    def _should_retry_startup_error(error: Exception) -> bool:
        if isinstance(
            error,
            (
                asyncio.TimeoutError,
                ConnectionError,
                OSError,
                QQOfficialGatewayUnavailableError,
            ),
        ):
            return True
        if isinstance(error, botpy.errors.ServerError):
            error_msg = str(error)
            return any(
                marker in error_msg
                for marker in ("100017", "频率限制", "Too many requests")
            )
        return False

    def _next_startup_retry_delay(self, error: Exception | None = None) -> int:
        if isinstance(error, botpy.errors.ServerError):
            error_msg = str(error)
            if any(
                marker in error_msg
                for marker in ("100017", "频率限制", "Too many requests")
            ):
                return _RATE_LIMIT_RECONNECT_DELAY_SECONDS

        idx = min(
            self._startup_retry_attempts,
            len(self.STARTUP_RETRY_DELAYS_SECONDS) - 1,
        )
        self._startup_retry_attempts += 1
        return self.STARTUP_RETRY_DELAYS_SECONDS[idx]

    async def _restart_client(self) -> None:
        try:
            await self.client.shutdown()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"[QQOfficial] Close client failed during recovery: {e}")
        self.client = self._create_client()

    async def _sleep_until_retry_or_shutdown(self, delay: float) -> bool:
        try:
            await asyncio.wait_for(self._shutdown_event.wait(), timeout=delay)
            return False
        except asyncio.TimeoutError:
            return True

    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ) -> None:
        await self._send_by_session_common(session, message_chain)

    async def _send_by_session_common(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ) -> None:
        message_chains = QQOfficialMessageEvent._split_message_chain_by_media(
            message_chain
        )
        if len(message_chains) > 1:
            for split_message_chain in message_chains:
                await self._send_by_session_common(session, split_message_chain)
            return

        (
            plain_text,
            image_base64,
            image_path,
            record_file_path,
            video_file_source,
            file_source,
            file_name,
        ) = await QQOfficialMessageEvent._parse_to_qqofficial(message_chain)
        if (
            not plain_text
            and not image_path
            and not image_base64
            and not record_file_path
            and not video_file_source
            and not file_source
        ):
            return

        # 主动推送不需要 msg_id，见 https://github.com/AstrBotDevs/AstrBot/issues/7904
        msg_id = self._session_last_message_id.get(session.session_id)
        scene = self._session_scene.get(session.session_id)
        allow_group_proactive_send = (
            session.message_type == MessageType.GROUP_MESSAGE
            and scene == "group"
            and getattr(self, "_allow_group_proactive_send", False)
        )
        if (
            not msg_id
            and session.message_type != MessageType.FRIEND_MESSAGE
            and not allow_group_proactive_send
        ):
            logger.warning(
                "[QQOfficial] No cached msg_id for session: %s, skip send_by_session",
                session.session_id,
            )
            return

        payload: dict[str, Any] = {"content": plain_text}
        if msg_id and not allow_group_proactive_send:
            payload["msg_id"] = msg_id
        ret: Any = None
        send_helper = SimpleNamespace(bot=self.client)

        if session.message_type == MessageType.GROUP_MESSAGE:
            if scene == "group":
                payload["msg_seq"] = random.randint(1, 10000)
                if image_base64:
                    media = await QQOfficialMessageEvent.upload_group_and_c2c_image(
                        send_helper,  # type: ignore
                        image_base64,
                        QQOfficialMessageEvent.IMAGE_FILE_TYPE,
                        group_openid=session.session_id,
                    )
                    payload["media"] = media
                    payload["msg_type"] = 7
                if record_file_path:
                    media = await QQOfficialMessageEvent.upload_group_and_c2c_media(
                        send_helper,  # type: ignore
                        record_file_path,
                        QQOfficialMessageEvent.VOICE_FILE_TYPE,
                        group_openid=session.session_id,
                    )
                    if media:
                        payload["media"] = media
                        payload["msg_type"] = 7
                if video_file_source:
                    media = await QQOfficialMessageEvent.upload_group_and_c2c_media(
                        send_helper,  # type: ignore
                        video_file_source,
                        QQOfficialMessageEvent.VIDEO_FILE_TYPE,
                        group_openid=session.session_id,
                    )
                    if media:
                        payload["media"] = media
                        payload["msg_type"] = 7
                        payload.pop("msg_id", None)
                if file_source:
                    media = await QQOfficialMessageEvent.upload_group_and_c2c_media(
                        send_helper,  # type: ignore
                        file_source,
                        QQOfficialMessageEvent.FILE_FILE_TYPE,
                        file_name=file_name,
                        group_openid=session.session_id,
                    )
                    if media:
                        payload["media"] = media
                        payload["msg_type"] = 7
                        payload.pop("msg_id", None)
                ret = await self.client.api.post_group_message(
                    group_openid=session.session_id,
                    **payload,
                )
            else:
                if image_path:
                    payload["file_image"] = image_path
                ret = await self.client.api.post_message(
                    channel_id=session.session_id,
                    **payload,
                )

        elif session.message_type == MessageType.FRIEND_MESSAGE:
            # 参考 https://bot.q.qq.com/wiki/develop/pythonsdk/api/message/post_message.html
            # msg_id 缺失时认为是主动推送，而似乎至少在私聊上主动推送是没有被限制的，这里直接移除 msg_id 可以避免越权或 msg_id 不可用的bug
            payload.pop("msg_id", None)
            payload["msg_seq"] = random.randint(1, 10000)
            if image_base64:
                media = await QQOfficialMessageEvent.upload_group_and_c2c_image(
                    send_helper,  # type: ignore
                    image_base64,
                    QQOfficialMessageEvent.IMAGE_FILE_TYPE,
                    openid=session.session_id,
                )
                payload["media"] = media
                payload["msg_type"] = 7
            if record_file_path:
                media = await QQOfficialMessageEvent.upload_group_and_c2c_media(
                    send_helper,  # type: ignore
                    record_file_path,
                    QQOfficialMessageEvent.VOICE_FILE_TYPE,
                    openid=session.session_id,
                )
                if media:
                    payload["media"] = media
                    payload["msg_type"] = 7
            if video_file_source:
                media = await QQOfficialMessageEvent.upload_group_and_c2c_media(
                    send_helper,  # type: ignore
                    video_file_source,
                    QQOfficialMessageEvent.VIDEO_FILE_TYPE,
                    openid=session.session_id,
                )
                if media:
                    payload["media"] = media
                    payload["msg_type"] = 7
            if file_source:
                media = await QQOfficialMessageEvent.upload_group_and_c2c_media(
                    send_helper,  # type: ignore
                    file_source,
                    QQOfficialMessageEvent.FILE_FILE_TYPE,
                    file_name=file_name,
                    openid=session.session_id,
                )
                if media:
                    payload["media"] = media
                    payload["msg_type"] = 7

            ret = await QQOfficialMessageEvent.post_c2c_message(
                send_helper,  # type: ignore
                openid=session.session_id,
                **payload,
            )
        else:
            logger.warning(
                "[QQOfficial] Unsupported message type for send_by_session: %s",
                session.message_type,
            )
            return

        sent_message_id = self._extract_message_id(ret)
        if sent_message_id:
            self.remember_session_message_id(session.session_id, sent_message_id)
        await Platform.send_by_session(self, session, message_chain)

    def remember_session_message_id(self, session_id: str, message_id: str) -> None:
        if not session_id or not message_id:
            return
        self._session_last_message_id[session_id] = message_id

    def remember_session_scene(self, session_id: str, scene: str) -> None:
        if not session_id or not scene:
            return
        self._session_scene[session_id] = scene

    def _extract_message_id(self, ret: Any) -> str | None:
        if isinstance(ret, dict):
            message_id = ret.get("id")
            return str(message_id) if message_id else None
        message_id = getattr(ret, "id", None)
        if message_id:
            return str(message_id)
        return None

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="qq_official",
            description="QQ 机器人官方 API 适配器",
            id=cast(str, self.config.get("id")),
            support_proactive_message=True,
        )

    def create_event(self, message: AstrBotMessage) -> QQOfficialMessageEvent:
        """Creates a QQ Official message event.

        Args:
            message: AstrBot message object to wrap.

        Returns:
            Created QQ Official message event.
        """
        return QQOfficialMessageEvent(
            message.message_str,
            message,
            self.meta(),
            message.session_id,
            self.client,
        )

    @staticmethod
    def _normalize_attachment_url(url: str | None) -> str:
        if not url:
            return ""
        if url.startswith("http://") or url.startswith("https://"):
            return url
        return f"https://{url}"

    @staticmethod
    async def _prepare_audio_attachment(
        url: str,
        filename: str,
    ) -> Record:
        ext = Path(filename).suffix.lower()
        source_ext = ext or ".audio"
        path_wav = await MediaResolver(
            url,
            media_type="audio",
            default_suffix=source_ext,
        ).to_path(target_format="wav")

        return Record(file=path_wav, url=path_wav)

    @staticmethod
    async def _append_attachments(
        msg: list[BaseMessageComponent],
        attachments: list | None,
    ) -> None:
        if not attachments:
            return

        for attachment in attachments:
            content_type = cast(
                str,
                getattr(attachment, "content_type", "") or "",
            ).lower()
            url = QQOfficialPlatformAdapter._normalize_attachment_url(
                cast(str | None, getattr(attachment, "url", None))
            )
            if not url:
                continue

            if content_type.startswith("image"):
                msg.append(Image.fromURL(url))
            else:
                filename = cast(
                    str,
                    getattr(attachment, "filename", None)
                    or getattr(attachment, "name", None)
                    or "attachment",
                )
                ext = Path(filename).suffix.lower()
                image_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
                audio_exts = {
                    ".mp3",
                    ".wav",
                    ".ogg",
                    ".m4a",
                    ".amr",
                    ".silk",
                }
                video_exts = {
                    ".mp4",
                    ".mov",
                    ".avi",
                    ".mkv",
                    ".webm",
                }

                if content_type.startswith("voice") or ext in audio_exts:
                    try:
                        msg.append(
                            await QQOfficialPlatformAdapter._prepare_audio_attachment(
                                url,
                                filename,
                            )
                        )
                    except Exception as e:
                        logger.warning(
                            "[QQOfficial] Failed to prepare audio attachment %s: %s",
                            url,
                            e,
                        )
                        msg.append(Record.fromURL(url))
                elif content_type.startswith("video") or ext in video_exts:
                    msg.append(Video.fromURL(url))
                elif content_type.startswith("image") or ext in image_exts:
                    msg.append(Image.fromURL(url))
                else:
                    msg.append(File(name=filename, file=url, url=url))

    @staticmethod
    def _parse_face_message(content: str) -> str:
        """Parse QQ official face message format and convert to readable text.

        QQ official face message format:
        <faceType=4,faceId="",ext="eyJ0ZXh0IjoiW+a7oeWktOmXruWPt10ifQ==">

        The ext field contains base64-encoded JSON with a 'text' field
        describing the emoji (e.g., '[满头问号]').

        Args:
            content: The message content that may contain face tags.

        Returns:
            Content with face tags replaced by readable emoji descriptions.
        """
        import base64
        import json
        import re

        def replace_face(match):
            face_tag = match.group(0)
            # Extract ext field from the face tag
            ext_match = re.search(r'ext="([^"]*)"', face_tag)
            if ext_match:
                try:
                    ext_encoded = ext_match.group(1)
                    # Decode base64 and parse JSON
                    ext_decoded = base64.b64decode(ext_encoded).decode("utf-8")
                    ext_data = json.loads(ext_decoded)
                    emoji_text = ext_data.get("text", "")
                    if emoji_text:
                        return f"[表情:{emoji_text}]"
                except Exception:
                    pass
            # Fallback if parsing fails
            return "[表情]"

        # Match face tags: <faceType=...>
        return re.sub(r"<faceType=\d+[^>]*>", replace_face, content)

    @staticmethod
    async def _parse_from_qqofficial(
        message: botpy.message.Message
        | botpy.message.GroupMessage
        | botpy.message.DirectMessage
        | botpy.message.C2CMessage,
        message_type: MessageType,
        force_group_mention: bool = False,
    ) -> AstrBotMessage:
        abm = AstrBotMessage()
        abm.type = message_type
        abm.timestamp = int(time.time())
        abm.raw_message = message
        abm.message_id = message.id
        # abm.tag = "qq_official"
        msg: list[BaseMessageComponent] = []

        if isinstance(message, botpy.message.GroupMessage) or isinstance(
            message,
            botpy.message.C2CMessage,
        ):
            if isinstance(message, botpy.message.GroupMessage):
                abm.sender = MessageMember(
                    message.author.member_openid,
                    getattr(message.author, "username", "") or "",
                )
                abm.group_id = message.group_openid
                bot_mentions = [
                    mention
                    for mention in (getattr(message, "mentions", None) or [])
                    if getattr(mention, "is_you", False) is True
                    and getattr(mention, "id", None) is not None
                ]
                bot_mention_ids = [str(mention.id) for mention in bot_mentions]
                group_mentioned = bool(bot_mention_ids) or force_group_mention
                plain_content_raw = message.content or ""
                for mention_id in bot_mention_ids:
                    plain_content_raw = plain_content_raw.replace(
                        f"<@{mention_id}>",
                        "",
                    ).replace(
                        f"<@!{mention_id}>",
                        "",
                    )
                abm.message_str = QQOfficialPlatformAdapter._parse_face_message(
                    plain_content_raw.strip()
                )
                abm.self_id = bot_mention_ids[0] if bot_mention_ids else "qq_official"
                if group_mentioned:
                    mention_name = (
                        getattr(bot_mentions[0], "username", "") if bot_mentions else ""
                    )
                    msg.append(At(qq=abm.self_id, name=mention_name))
            else:
                abm.sender = MessageMember(
                    message.author.user_openid,
                    getattr(message.author, "username", "") or "",
                )
                abm.message_str = QQOfficialPlatformAdapter._parse_face_message(
                    (message.content or "").strip()
                )
                abm.self_id = "unknown_selfid"
                msg.append(At(qq="qq_official"))
            msg.append(Plain(abm.message_str))
            await QQOfficialPlatformAdapter._append_attachments(
                msg, message.attachments
            )
            abm.message = msg

        elif isinstance(message, botpy.message.Message) or isinstance(
            message,
            botpy.message.DirectMessage,
        ):
            if isinstance(message, botpy.message.Message):
                abm.self_id = str(message.mentions[0].id)
            else:
                abm.self_id = ""

            plain_content = QQOfficialPlatformAdapter._parse_face_message(
                message.content.replace(
                    "<@!" + str(abm.self_id) + ">",
                    "",
                ).strip()
            )

            await QQOfficialPlatformAdapter._append_attachments(
                msg, message.attachments
            )
            abm.message = msg
            abm.message_str = plain_content
            abm.sender = MessageMember(
                str(message.author.id),
                str(message.author.username),
            )
            msg.append(At(qq="qq_official"))
            msg.append(Plain(plain_content))

            if isinstance(message, botpy.message.Message):
                abm.group_id = message.channel_id
        else:
            raise ValueError(f"Unknown message type: {message_type}")
        if not abm.self_id:
            abm.self_id = "qq_official"
        return abm

    async def run(self) -> None:
        while not self._shutdown_event.is_set():
            try:
                await self.client.start(appid=self.appid, secret=self.secret)
                self._startup_retry_attempts = 0
                if self._shutdown_event.is_set():
                    break
                logger.warning(
                    f"[QQOfficial] Client stopped unexpectedly, restarting in "
                    f"{self.STARTUP_RETRY_DELAYS_SECONDS[0]}s."
                )
                await self._restart_client()
                if not await self._sleep_until_retry_or_shutdown(
                    self.STARTUP_RETRY_DELAYS_SECONDS[0]
                ):
                    break
            except asyncio.CancelledError:
                raise
            except Exception as e:
                if self._shutdown_event.is_set():
                    break
                if not self._should_retry_startup_error(e):
                    raise
                delay = self._next_startup_retry_delay(e)
                logger.warning(
                    f"[QQOfficial] Startup failed, retrying in {delay}s: {e}"
                )
                await self._restart_client()
                if not await self._sleep_until_retry_or_shutdown(delay):
                    break

    def get_client(self) -> botClient:
        return self.client

    async def terminate(self) -> None:
        self._shutdown_event.set()
        await self.client.shutdown()
        logger.info("QQ 官方机器人接口 适配器已被关闭")
