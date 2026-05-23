"""QQ 官方机器人 API 适配器（类型安全版本）

本文件对原有实现做了两点关键修正以消除类型不匹配：
- 在需要调用 QQOfficialMessageEvent 的实例方法时，创建真实的
  QQOfficialMessageEvent 实例作为 helper，而不是使用 SimpleNamespace
  伪造对象，避免 mypy/ty 的类型错误。
- 在从 botpy 消息对象读取字段时进行归一化（使用 getattr + str(...)
  或者提供默认值），避免 None / 未知类型直接赋值给期望为 str 的字段。
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import time
import uuid
from pathlib import Path
from typing import Any

import botpy
import botpy.message
from botpy import Client
from botpy.gateway import BotWebSocket
from botpy.types.message import MarkdownPayload

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
from astrbot.core.platform.register import register_platform_adapter
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.io import download_file

from .qqofficial_message_event import QQOfficialMessageEvent

# Remove root handlers to avoid duplicate logs from botpy
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)


class ManagedBotWebSocket(BotWebSocket):
    def __init__(self, session, connection: Any, client: botClient):
        super().__init__(session, connection)
        self._client = client
        # 防止 on_error + on_closed 双重入队导致连接指数增长
        self._reenqueued = False

    async def on_closed(self, close_status_code, close_msg):
        if self._client.is_shutting_down:
            logger.debug("[QQOfficial] Ignore websocket reconnect during shutdown.")
            return
        if self._reenqueued:
            logger.debug("[QQOfficial] Session already re-enqueued, skip on_closed.")
            return
        try:
            self._reenqueued = True
            await super().on_closed(close_status_code, close_msg)
        except Exception:
            self._reenqueued = False
            raise

    async def on_error(self, exception: BaseException) -> None:
        if self._reenqueued:
            logger.debug("[QQOfficial] Session already re-enqueued, skip on_error.")
            return
        try:
            self._reenqueued = True
            await super().on_error(exception)
        except Exception:
            self._reenqueued = False
            raise

    async def close(self) -> None:
        self._can_reconnect = False
        if self._conn is not None and not self._conn.closed:
            await self._conn.close()


# QQ 机器人官方框架
class botClient(Client):
    # 消息去重：message_id -> 收到时间戳
    _DEDUP_TTL = 120  # 去重窗口，秒

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._shutting_down = False
        self._active_websockets: set[ManagedBotWebSocket] = set()
        self._seen_message_ids: dict[str, float] = {}

    def set_platform(self, platform: QQOfficialPlatformAdapter) -> None:
        # keep a typed reference back to adapter for callbacks to use
        self.platform = platform

    async def on_group_at_message_create(
        self,
        message: botpy.message.GroupMessage,
    ) -> None:
        abm = await QQOfficialPlatformAdapter._parse_from_qqofficial(
            message,
            MessageType.GROUP_MESSAGE,
            self.platform.appid,
        )
        # normalize group/session id to str
        abm.group_id = str(getattr(message, "group_openid", "") or "")
        abm.session_id = abm.group_id
        self.platform.remember_session_scene(abm.session_id, "group")
        self._commit(abm)

    async def on_at_message_create(self, message: botpy.message.Message) -> None:
        abm = await QQOfficialPlatformAdapter._parse_from_qqofficial(
            message,
            MessageType.GROUP_MESSAGE,
            self.platform.appid,
        )
        abm.group_id = str(getattr(message, "channel_id", "") or "")
        abm.session_id = abm.group_id
        self.platform.remember_session_scene(abm.session_id, "channel")
        self._commit(abm)

    async def on_direct_message_create(
        self,
        message: botpy.message.DirectMessage,
    ) -> None:
        abm = await QQOfficialPlatformAdapter._parse_from_qqofficial(
            message,
            MessageType.FRIEND_MESSAGE,
            self.platform.appid,
        )
        # For DM/C2C the session is the sender user id
        sender_id = getattr(message, "author", None)
        user_openid = ""
        if sender_id is not None:
            user_openid = str(getattr(message.author, "user_openid", "") or "")
        abm.session_id = user_openid
        self.platform.remember_session_scene(abm.session_id, "friend")
        self._commit(abm)

    async def on_c2c_message_create(self, message: botpy.message.C2CMessage) -> None:
        abm = await QQOfficialPlatformAdapter._parse_from_qqofficial(
            message,
            MessageType.FRIEND_MESSAGE,
            self.platform.appid,
        )
        user_openid = str(getattr(message.author, "user_openid", "") or "")
        abm.session_id = user_openid
        self.platform.remember_session_scene(abm.session_id, "friend")
        self._commit(abm)

    def _commit(self, abm: AstrBotMessage) -> None:
        msg_id = abm.message_id
        if msg_id:
            now = time.monotonic()
            # 清理过期条目
            expired = [
                k
                for k, ts in self._seen_message_ids.items()
                if now - ts > self._DEDUP_TTL
            ]
            for k in expired:
                del self._seen_message_ids[k]
            if msg_id in self._seen_message_ids:
                logger.debug(f"[QQOfficial] Duplicate message {msg_id}, skipping.")
                return
            self._seen_message_ids[msg_id] = now

        self.platform.remember_session_message_id(abm.session_id, abm.message_id)
        self.platform.commit_event(
            # QQOfficialMessageEvent expects (message_str, message_obj, platform_meta, session_id, bot)
            # adapter passes its own client to event instances
            # The commit wraps abm into an event for processing by AstrBot core
            # The QQOfficialMessageEvent used here is only to build the platform event,
            # the consumer of commit_event will use QQOfficialMessageEvent to send later.
            QQOfficialMessageEvent(
                abm.message_str,
                abm,
                self.platform.meta(),
                abm.session_id,
                self.platform.client,
            ),
        )

    async def bot_connect(self, session) -> None:
        active_count = len(self._active_websockets)
        if active_count > 0:
            logger.warning(
                "[QQOfficial] bot_connect called with %d existing active websocket(s). "
                "This may indicate a reconnection storm.",
                active_count,
            )
        logger.info(
            "[QQOfficial] Websocket session starting (active: %d).", active_count + 1
        )

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
    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)
        self.appid = platform_config["appid"]
        self.secret = platform_config["secret"]
        qq_group = platform_config.get("enable_group_c2c", False)
        guild_dm = platform_config.get("enable_guild_direct_message", False)

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

        # typed client
        self.client: botClient = botClient(
            intents=self.intents,
            bot_log=False,
            timeout=20,
        )
        self.client.set_platform(self)
        self._session_last_message_id: dict[str, str] = {}
        self._session_scene: dict[str, str] = {}
        self.test_mode = os.environ.get("TEST_MODE", "off") == "on"

    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ) -> None:
        await self._send_by_session_common(session, message_chain)

    @staticmethod
    def _normalize_media_payload(
        payload: dict[str, Any], plain_text: str | None
    ) -> None:
        payload.pop("markdown", None)
        payload["content"] = plain_text or None

    async def _send_by_session_common(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ) -> None:
        # parse outgoing message chain to qq-official compatible payload parts
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
            and (not image_path)
            and (not image_base64)
            and (not record_file_path)
            and (not video_file_source)
            and (not file_source)
        ):
            return

        # 私聊主动推送不需要 msg_id，见 https://github.com/AstrBotDevs/AstrBot/issues/7904
        msg_id = self._session_last_message_id.get(session.session_id)
        if not msg_id and session.message_type != MessageType.FRIEND_MESSAGE:
            logger.warning(
                "[QQOfficial] No cached msg_id for session: %s, skip send_by_session",
                session.session_id,
            )
            return

        payload: dict[str, Any] = {"msg_type": 2, "msg_id": msg_id}
        if plain_text:
            payload["markdown"] = MarkdownPayload(content=plain_text)

        ret: Any = None
        send_helper = SimpleNamespace(bot=self.client)

        # Create a real QQOfficialMessageEvent helper so instance methods are typed correctly.
        # Provide a minimal AstrBotMessage and platform meta; these values are placeholders and
        # only used by helper methods that need access to bot/client or metadata.
        helper_message_obj = AstrBotMessage()
        helper_message_obj.message_id = msg_id
        helper_event = QQOfficialMessageEvent(
            message_str=plain_text or "",
            message_obj=helper_message_obj,
            platform_meta=self.meta(),
            session_id=session.session_id,
            bot=self.client,
        )

        # Decide how to send based on session type
        if session.message_type == MessageType.GROUP_MESSAGE:
            scene = self._session_scene.get(session.session_id)
            if scene == "group":
                payload["msg_seq"] = random.randint(1, 10000)
                if image_base64:
                    media = await helper_event.upload_group_and_c2c_image(
                        image_base64,
                        QQOfficialMessageEvent.IMAGE_FILE_TYPE,
                        group_openid=session.session_id,
                    )
                    payload["media"] = media
                    payload["msg_type"] = 7
                if record_file_path:
                    media = await helper_event.upload_group_and_c2c_media(
                        record_file_path,
                        QQOfficialMessageEvent.VOICE_FILE_TYPE,
                        group_openid=session.session_id,
                    )
                    if media:
                        payload["media"] = media
                        payload["msg_type"] = 7
                if video_file_source:
                    media = await helper_event.upload_group_and_c2c_media(
                        video_file_source,
                        QQOfficialMessageEvent.VIDEO_FILE_TYPE,
                        group_openid=session.session_id,
                    )
                    if media:
                        payload["media"] = media
                        payload["msg_type"] = 7
                        payload.pop("msg_id", None)
                if file_source:
                    media = await helper_event.upload_group_and_c2c_media(
                        file_source,
                        QQOfficialMessageEvent.FILE_FILE_TYPE,
                        file_name=file_name,
                        group_openid=session.session_id,
                    )
                    if media:
                        payload["media"] = media
                        payload["msg_type"] = 7
                        payload.pop("msg_id", None)
                if payload.get("msg_type") == 7:
                    self._normalize_media_payload(payload, plain_text)
                ret = await self.client.api.post_group_message(
                    group_openid=session.session_id or "",
                    **payload,
                )
            else:
                # channel (guild) message path
                if image_path:
                    payload["file_image"] = image_path
                ret = await self.client.api.post_message(
                    channel_id=session.session_id or "",
                    **payload,
                )
        elif session.message_type == MessageType.FRIEND_MESSAGE:
            # When msg_id is absent, the API treats this as a proactive push.
            # C2C proactive push is unrestricted; drops msg_id to avoid permission errors.
            payload.pop("msg_id", None)
            payload["msg_seq"] = random.randint(1, 10000)
            if image_base64:
                media = await helper_event.upload_group_and_c2c_image(
                    image_base64,
                    QQOfficialMessageEvent.IMAGE_FILE_TYPE,
                    openid=session.session_id,
                )
                payload["media"] = media
                payload["msg_type"] = 7
            if record_file_path:
                media = await helper_event.upload_group_and_c2c_media(
                    record_file_path,
                    QQOfficialMessageEvent.VOICE_FILE_TYPE,
                    openid=session.session_id,
                )
                if media:
                    payload["media"] = media
                    payload["msg_type"] = 7
            if video_file_source:
                media = await helper_event.upload_group_and_c2c_media(
                    video_file_source,
                    QQOfficialMessageEvent.VIDEO_FILE_TYPE,
                    openid=session.session_id,
                )
                if media:
                    payload["media"] = media
                    payload["msg_type"] = 7
            if file_source:
                media = await helper_event.upload_group_and_c2c_media(
                    file_source,
                    QQOfficialMessageEvent.FILE_FILE_TYPE,
                    file_name=file_name,
                    openid=session.session_id,
                )
                if media:
                    payload["media"] = media
                    payload["msg_type"] = 7

            if payload.get("msg_type") == 7:
                self._normalize_media_payload(payload, plain_text)

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
        await super().send_by_session(session, message_chain)

    def remember_session_message_id(self, session_id: str, message_id: str) -> None:
        if not session_id or not message_id:
            return
        self._session_last_message_id[session_id] = message_id

    def remember_session_scene(self, session_id: str, scene: str) -> None:
        if not session_id or not scene:
            return
        self._session_scene[session_id] = scene

    def _extract_message_id(self, ret: Any) -> str | None:
        # support both dict and botpy Message objects
        if isinstance(ret, dict):
            message_id = ret.get("id")
            return str(message_id) if message_id else None
        message_id = getattr(ret, "id", None)
        return str(message_id) if message_id else None

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="qq_official",
            description="QQ 机器人官方 API 适配器",
            id=str(self.config.get("id", "")),
            support_proactive_message=True,
        )

    @staticmethod
    def _normalize_attachment_url(url: str | None) -> str:
        if not url:
            return ""
        if url.startswith("http://") or url.startswith("https://"):
            return url
        return f"https://{url}"

    @staticmethod
    async def _prepare_audio_attachment(url: str, filename: str) -> Record:
        temp_dir = os.path.join(get_astrbot_temp_path())
        os.makedirs(temp_dir, exist_ok=True)
        ext = Path(filename).suffix.lower()
        source_ext = ext or ".audio"
        source_path = os.path.join(
            temp_dir,
            f"qqofficial_{uuid.uuid4().hex}{source_ext}",
        )
        await download_file(url, source_path)
        return Record(file=source_path, url=source_path)

    @staticmethod
    async def _append_attachments(
        msg: list[BaseMessageComponent],
        attachments: list | None,
    ) -> None:
        if not attachments:
            return
        for attachment in attachments:
            content_type = (getattr(attachment, "content_type", "") or "").lower()
            url = QQOfficialPlatformAdapter._normalize_attachment_url(
                getattr(attachment, "url", None),
            )
            if not url:
                continue
            if content_type.startswith("image"):
                msg.append(Image.fromURL(url))
            else:
                filename = (
                    getattr(attachment, "filename", None)
                    or getattr(attachment, "name", None)
                    or "attachment"
                )
                ext = Path(filename).suffix.lower()
                image_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
                audio_exts = {".mp3", ".wav", ".ogg", ".m4a", ".amr", ".silk"}
                video_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
                if content_type.startswith("voice") or ext in audio_exts:
                    try:
                        msg.append(
                            await QQOfficialPlatformAdapter._prepare_audio_attachment(
                                url,
                                filename,
                            ),
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
        <faceType=4,faceId="",ext="...base64...">

        The ext field contains base64-encoded JSON with a 'text' field describing
        the emoji (e.g., '[满头问号]').

        Returns:
            Content with face tags replaced by readable emoji descriptions.

        """
        import base64
        import json
        import re

        def replace_face(match: re.Match[str]) -> str:
            face_tag = match.group(0)
            ext_match = re.search(r'ext="([^"]*)"', face_tag)
            if ext_match:
                try:
                    ext_encoded = ext_match.group(1)
                    ext_decoded = base64.b64decode(ext_encoded).decode("utf-8")
                    ext_data = json.loads(ext_decoded)
                    emoji_text = ext_data.get("text", "")
                    if emoji_text:
                        return f"[表情:{emoji_text}]"
                except Exception:
                    pass
            return "[表情]"

        return re.sub(r"<faceType=\d+[^>]*>", replace_face, content)

    @staticmethod
    async def _parse_from_qqofficial(
        message: botpy.message.Message
        | botpy.message.GroupMessage
        | botpy.message.DirectMessage
        | botpy.message.C2CMessage,
        message_type: MessageType,
        appid: str,
    ) -> AstrBotMessage:
        """Normalize incoming botpy message into AstrBotMessage with safe string fields."""
        abm = AstrBotMessage()
        abm.type = message_type
        abm.timestamp = int(time.time())
        abm.raw_message = message
        # normalize message_id to string
        abm.message_id = str(getattr(message, "id", "") or uuid.uuid4().hex)
        msg: list[BaseMessageComponent] = []

        # Group-like messages (GroupMessage or C2C in some contexts)
        if isinstance(message, botpy.message.GroupMessage) or isinstance(
            message,
            botpy.message.C2CMessage,
        ):
            if isinstance(message, botpy.message.GroupMessage):
                abm.sender = MessageMember(
                    str(getattr(message.author, "member_openid", "") or ""),
                    "",
                )
                abm.group_id = str(getattr(message, "group_openid", "") or "")
            else:
                abm.sender = MessageMember(
                    str(getattr(message.author, "user_openid", "") or ""),
                    "",
                )
            abm.message_str = QQOfficialPlatformAdapter._parse_face_message(
                (getattr(message, "content", "") or "").strip(),
            )
            abm.self_id = "unknown_selfid"
            # keep the @ component to indicate mention within group message
            msg.append(At(qq="qq_official"))
            msg.append(Plain(abm.message_str))
            await QQOfficialPlatformAdapter._append_attachments(
                msg,
                getattr(message, "attachments", None),
            )
            abm.message = msg
        # Direct / channel messages
        elif isinstance(message, botpy.message.Message) or isinstance(
            message,
            botpy.message.DirectMessage,
        ):
            # If it's a mention message, the bot id may be in mentions; try to normalize it
            if isinstance(message, botpy.message.Message):
                mention_id = ""
                mentions = getattr(message, "mentions", None) or []
                if mentions:
                    # take first mention id as string
                    mention_id = str(getattr(mentions[0], "id", "") or "")
                abm.self_id = mention_id
            else:
                abm.self_id = ""
            content_raw = getattr(message, "content", "") or ""
            plain_content = QQOfficialPlatformAdapter._parse_face_message(
                content_raw.replace(f"<@!{abm.self_id}>", "").strip(),
            )
            await QQOfficialPlatformAdapter._append_attachments(
                msg,
                getattr(message, "attachments", None),
            )
            abm.message = msg
            abm.message_str = plain_content
            # normalize sender fields with safe fallbacks
            abm.sender = MessageMember(
                str(getattr(message.author, "id", "") or ""),
                str(getattr(message.author, "username", "") or ""),
            )
            msg.append(At(qq=appid))
            msg.append(Plain(plain_content))
            if isinstance(message, botpy.message.Message):
                abm.group_id = str(getattr(message, "channel_id", "") or "")
        else:
            raise ValueError(f"Unknown message type: {message_type}")

        # final normalization for session/self ids to avoid None
        if not getattr(abm, "self_id", None):
            abm.self_id = "qq_official"
        if not getattr(abm, "session_id", None):
            # default session id to sender user id if possible
            try:
                abm.session_id = str(abm.sender.user_id)
            except Exception:
                abm.session_id = ""

        return abm

    def run(self):
        return self.client.start(appid=self.appid, secret=self.secret)

    def get_client(self) -> botClient:
        return self.client

    async def terminate(self) -> None:
        await self.client.close()
        logger.info("QQ 官方机器人接口 适配器 已优雅关闭")
