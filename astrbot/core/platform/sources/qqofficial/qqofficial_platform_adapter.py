from __future__ import annotations

import asyncio
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
from botpy.connection import ConnectionState
from botpy.gateway import BotWebSocket

from astrbot import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import At, File, Image, Plain, Record, Reply, Video
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


def _set_raw_message_fields(message: Any, data: dict[str, Any]) -> None:
    """Preserve QQ message fields that qq-botpy does not expose.

    Args:
        message: Patched qq-botpy message object.
        data: Raw message payload from QQ.

    Returns:
        None.
    """
    if not isinstance(data, dict):
        data = {}
    message.raw_data = data
    message.message_type = data.get("message_type")
    msg_elements = data.get("msg_elements")
    message.msg_elements = msg_elements if isinstance(msg_elements, list) else []


class PatchedMessage(botpy.message.Message):
    __slots__ = ("raw_data", "message_type", "msg_elements")

    def __init__(
        self,
        api: Any,
        event_id: str | None,
        data: dict[str, Any],
    ) -> None:
        super().__init__(api, event_id, data)  # type: ignore
        _set_raw_message_fields(self, data)


class PatchedDirectMessage(botpy.message.DirectMessage):
    __slots__ = ("raw_data", "message_type", "msg_elements")

    def __init__(
        self,
        api: Any,
        event_id: str | None,
        data: dict[str, Any],
    ) -> None:
        super().__init__(api, event_id, data)  # type: ignore
        _set_raw_message_fields(self, data)


class PatchedC2CMessage(botpy.message.C2CMessage):
    __slots__ = ("raw_data", "message_type", "msg_elements")

    def __init__(
        self,
        api: Any,
        event_id: str | None,
        data: dict[str, Any],
    ) -> None:
        super().__init__(api, event_id, data)  # type: ignore
        _set_raw_message_fields(self, data)


class PatchedGroupMessage(botpy.message.GroupMessage):
    __slots__ = ("raw_data", "message_type", "msg_elements")

    def __init__(
        self,
        api: Any,
        event_id: str | None,
        data: dict[str, Any],
    ) -> None:
        super().__init__(api, event_id, data)  # type: ignore
        _set_raw_message_fields(self, data)

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
    """Register qq-botpy message parsers with QQ quote payload preservation."""

    def build_parser(event_name: str, message_cls: type) -> Any:
        """Build a ConnectionState parser for one QQ message event.

        Args:
            event_name: botpy dispatch event name.
            message_cls: Patched message class used to retain raw fields.

        Returns:
            Parser function bound by qq-botpy's ConnectionState.
        """

        def parse_message(self, payload: dict[str, Any]) -> None:
            qq_message = message_cls(
                self.api,
                payload.get("id", None),
                payload.get("d", {}),
            )
            self._dispatch(event_name, qq_message)

        return parse_message

    parser_specs = {
        "message_create": ("message_create", PatchedMessage),
        "at_message_create": ("at_message_create", PatchedMessage),
        "direct_message_create": ("direct_message_create", PatchedDirectMessage),
        "group_at_message_create": ("group_at_message_create", PatchedGroupMessage),
        "c2c_message_create": ("c2c_message_create", PatchedC2CMessage),
        "group_message_create": ("group_message_create", PatchedGroupMessage),
    }
    for parser_name, (event_name, message_cls) in parser_specs.items():
        setattr(
            ConnectionState,
            f"parse_{parser_name}",
            build_parser(event_name, message_cls),
        )


class ManagedBotWebSocket(BotWebSocket):
    def __init__(self, session, connection: Any, client: botClient):
        super().__init__(session, connection)
        self._client = client

    async def on_closed(self, close_status_code, close_msg):
        if self._client.is_shutting_down:
            logger.debug("[QQOfficial] Ignore websocket reconnect during shutdown.")
            return
        await super().on_closed(close_status_code, close_msg)

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

    def set_platform(self, platform: QQOfficialPlatformAdapter) -> None:
        self.platform = platform

    @property
    def is_shutting_down(self) -> bool:
        return self._shutting_down or self.is_closed()

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
        self.client = botClient(
            intents=self.intents,
            bot_log=False,
            timeout=20,
        )

        self.client.set_platform(self)

        _ensure_group_message_create_parser()

        self._session_last_message_id: dict[str, str] = {}
        self._session_scene: dict[str, str] = {}
        self._allow_group_proactive_send = True

        self.test_mode = os.environ.get("TEST_MODE", "off") == "on"

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

        has_mention = QQOfficialMessageEvent._has_mention(message_chain)
        use_markdown = (
            has_mention or getattr(message_chain, "use_markdown_", None) is True
        )
        if use_markdown and plain_text:
            payload: dict[str, Any] = {
                "markdown": botpy.types.message.MarkdownPayload(content=plain_text),
                "msg_type": 2,
            }
        else:
            payload = {"content": plain_text, "msg_type": 0}
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
                    QQOfficialMessageEvent._set_media_payload(
                        payload, media, plain_text
                    )
                if record_file_path:
                    media = await QQOfficialMessageEvent.upload_group_and_c2c_media(
                        send_helper,  # type: ignore
                        record_file_path,
                        QQOfficialMessageEvent.VOICE_FILE_TYPE,
                        group_openid=session.session_id,
                    )
                    if media:
                        QQOfficialMessageEvent._set_media_payload(
                            payload, media, plain_text
                        )
                if video_file_source:
                    media = await QQOfficialMessageEvent.upload_group_and_c2c_media(
                        send_helper,  # type: ignore
                        video_file_source,
                        QQOfficialMessageEvent.VIDEO_FILE_TYPE,
                        group_openid=session.session_id,
                    )
                    if media:
                        QQOfficialMessageEvent._set_media_payload(
                            payload, media, plain_text
                        )
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
                        QQOfficialMessageEvent._set_media_payload(
                            payload, media, plain_text
                        )
                        payload.pop("msg_id", None)
                ret = await self.client.api.post_group_message(
                    group_openid=session.session_id,
                    **payload,
                )
            else:
                if image_path:
                    payload["file_image"] = image_path
                payload.pop("msg_type", None)
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
                QQOfficialMessageEvent._set_media_payload(payload, media, plain_text)
            if record_file_path:
                media = await QQOfficialMessageEvent.upload_group_and_c2c_media(
                    send_helper,  # type: ignore
                    record_file_path,
                    QQOfficialMessageEvent.VOICE_FILE_TYPE,
                    openid=session.session_id,
                )
                if media:
                    QQOfficialMessageEvent._set_media_payload(
                        payload, media, plain_text
                    )
            if video_file_source:
                media = await QQOfficialMessageEvent.upload_group_and_c2c_media(
                    send_helper,  # type: ignore
                    video_file_source,
                    QQOfficialMessageEvent.VIDEO_FILE_TYPE,
                    openid=session.session_id,
                )
                if media:
                    QQOfficialMessageEvent._set_media_payload(
                        payload, media, plain_text
                    )
            if file_source:
                media = await QQOfficialMessageEvent.upload_group_and_c2c_media(
                    send_helper,  # type: ignore
                    file_source,
                    QQOfficialMessageEvent.FILE_FILE_TYPE,
                    file_name=file_name,
                    openid=session.session_id,
                )
                if media:
                    QQOfficialMessageEvent._set_media_payload(
                        payload, media, plain_text
                    )

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
            if isinstance(attachment, dict):
                content_type = str(
                    attachment.get("content_type")
                    or attachment.get("contentType")
                    or "",
                ).lower()
                url = QQOfficialPlatformAdapter._normalize_attachment_url(
                    cast(str | None, attachment.get("url"))
                )
                filename = cast(
                    str,
                    attachment.get("filename")
                    or attachment.get("name")
                    or "attachment",
                )
            else:
                content_type = cast(
                    str,
                    getattr(attachment, "content_type", "") or "",
                ).lower()
                url = QQOfficialPlatformAdapter._normalize_attachment_url(
                    cast(str | None, getattr(attachment, "url", None))
                )
                filename = cast(
                    str,
                    getattr(attachment, "filename", None)
                    or getattr(attachment, "name", None)
                    or "attachment",
                )
            if not url:
                continue

            if content_type.startswith("image"):
                msg.append(Image.fromURL(url))
            else:
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
    def _strip_bot_mention_markup(content: str | None, mention_id: str) -> str:
        normalized = content or ""
        for markup in (
            f'<qqbot-at-user id="{mention_id}" />',
            f"<@{mention_id}>",
            f"<@!{mention_id}>",
        ):
            normalized = normalized.replace(markup, "")
        return normalized

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
        message_reference = getattr(message, "message_reference", None)
        quoted_message_id = getattr(message_reference, "message_id", None)
        raw_message_type = getattr(message, "message_type", None)
        try:
            is_quoted_message = int(raw_message_type or 0) == 103
        except (TypeError, ValueError):
            is_quoted_message = False
        msg_elements = getattr(message, "msg_elements", None)
        quoted_message_str = ""
        quoted_element_message_id = ""
        quoted_chain: list[BaseMessageComponent] = []
        if is_quoted_message and isinstance(msg_elements, list) and msg_elements:
            quoted_element = msg_elements[0]
            if isinstance(quoted_element, dict):
                quoted_content = quoted_element.get("content")
                quoted_attachments = quoted_element.get("attachments")
                quoted_element_message_id = str(
                    quoted_element.get("id") or quoted_element.get("message_id") or "",
                )
            else:
                quoted_content = getattr(quoted_element, "content", None)
                quoted_attachments = getattr(quoted_element, "attachments", None)
                quoted_element_message_id = str(
                    getattr(quoted_element, "id", None)
                    or getattr(quoted_element, "message_id", None)
                    or "",
                )

            quoted_message_str = QQOfficialPlatformAdapter._parse_face_message(
                str(quoted_content or "").strip()
            )
            if quoted_message_str:
                quoted_chain.append(Plain(quoted_message_str))
            if isinstance(quoted_attachments, list):
                await QQOfficialPlatformAdapter._append_attachments(
                    quoted_chain,
                    quoted_attachments,
                )
        if quoted_message_id or quoted_element_message_id or quoted_chain:
            msg.append(
                Reply(
                    id=str(quoted_message_id or quoted_element_message_id or ""),
                    chain=quoted_chain,
                    message_str=quoted_message_str,
                    text=quoted_message_str,
                )
            )

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
                    plain_content_raw = (
                        QQOfficialPlatformAdapter._strip_bot_mention_markup(
                            plain_content_raw, mention_id
                        )
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
                QQOfficialPlatformAdapter._strip_bot_mention_markup(
                    message.content, str(abm.self_id)
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

    def run(self):
        return self.client.start(appid=self.appid, secret=self.secret)

    def get_client(self) -> botClient:
        return self.client

    async def terminate(self) -> None:
        await self.client.shutdown()
        logger.info("QQ 官方机器人接口 适配器已被关闭")
