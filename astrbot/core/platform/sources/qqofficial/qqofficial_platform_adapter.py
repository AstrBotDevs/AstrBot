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
from botpy.connection import ConnectionState

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
from astrbot.core.platform.register import register_platform_adapter
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.io import download_file

from .qqofficial_message_event import QQOfficialMessageEvent

# Remove root handlers to avoid duplicate logs from botpy
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
        super().__init__(api, event_id, data)
        _set_raw_message_fields(self, data)


class PatchedDirectMessage(botpy.message.DirectMessage):
    __slots__ = ("raw_data", "message_type", "msg_elements")

    def __init__(
        self,
        api: Any,
        event_id: str | None,
        data: dict[str, Any],
    ) -> None:
        super().__init__(api, event_id, data)
        _set_raw_message_fields(self, data)


class PatchedC2CMessage(botpy.message.C2CMessage):
    __slots__ = ("raw_data", "message_type", "msg_elements")

    def __init__(
        self,
        api: Any,
        event_id: str | None,
        data: dict[str, Any],
    ) -> None:
        super().__init__(api, event_id, data)
        _set_raw_message_fields(self, data)


class PatchedGroupMessage(botpy.message.GroupMessage):
    __slots__ = ("raw_data", "message_type", "msg_elements")

    def __init__(
        self,
        api: Any,
        event_id: str | None,
        data: dict[str, Any],
    ) -> None:
        super().__init__(api, event_id, data)
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


class botClient(Client):
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
            force_group_mention=True,
        )
        # normalize group/session id to str
        abm.group_id = str(getattr(message, "group_openid", "") or "")
        abm.session_id = abm.group_id
        self.platform.remember_session_scene(abm.session_id, "group")
        self._commit(abm)

    async def on_group_message_create(
        self,
        message: botpy.message.GroupMessage,
    ) -> None:
        abm = await QQOfficialPlatformAdapter._parse_from_qqofficial(
            message,
            MessageType.GROUP_MESSAGE,
        )
        abm.group_id = str(getattr(message, "group_openid", "") or "")
        abm.session_id = abm.group_id
        self.platform.remember_session_scene(abm.session_id, "group")
        self._commit(abm)

    async def on_at_message_create(self, message: botpy.message.Message) -> None:
        abm = await QQOfficialPlatformAdapter._parse_from_qqofficial(
            message,
            MessageType.GROUP_MESSAGE,
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
        )
        user_openid = str(getattr(message.author, "user_openid", "") or "")
        abm.session_id = user_openid
        self.platform.remember_session_scene(abm.session_id, "friend")
        self._commit(abm)

    def _commit(self, abm: AstrBotMessage) -> None:
        self.platform.remember_session_message_id(abm.session_id, abm.message_id)
        self.platform.commit_event(self.platform.create_event(abm))


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
        _ensure_group_message_create_parser()
        self._session_last_message_id: dict[str, str] = {}
        self._session_scene: dict[str, str] = {}
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

        msg_id = self._session_last_message_id.get(session.session_id)
        scene = self._session_scene.get(session.session_id)
        group_proactive_send = (
            session.message_type == MessageType.GROUP_MESSAGE and scene == "group"
        )
        if (
            not msg_id
            and session.message_type != MessageType.FRIEND_MESSAGE
            and not group_proactive_send
        ):
            logger.warning(
                "[QQOfficial] No cached msg_id for session: %s, skip send_by_session",
                session.session_id,
            )
            return

        payload: dict[str, Any] = {"content": plain_text}
        if msg_id and not group_proactive_send:
            payload["msg_id"] = msg_id
        ret: Any | None = None

        # Create a real QQOfficialMessageEvent helper so instance methods are typed correctly.
        # Provide a minimal AstrBotMessage and platform meta; these values are placeholders and
        # only used by helper methods that need access to bot/client or metadata.
        helper_message_obj = AstrBotMessage()
        helper_message_obj.type = session.message_type
        helper_message_obj.message_id = msg_id or ""
        helper_event = QQOfficialMessageEvent(
            message_str=plain_text or "",
            message_obj=helper_message_obj,
            platform_meta=self.meta(),
            session_id=session.session_id,
            bot=self.client,
        )

        # Decide how to send based on session type
        if session.message_type == MessageType.GROUP_MESSAGE:
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
            # c2c / direct message
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
            ret = await helper_event.post_c2c_message(
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

    def create_event(self, message: AstrBotMessage) -> QQOfficialMessageEvent:
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
            if isinstance(attachment, dict):
                content_type = str(
                    attachment.get("content_type")
                    or attachment.get("contentType")
                    or "",
                ).lower()
                attachment_url = attachment.get("url")
                url = QQOfficialPlatformAdapter._normalize_attachment_url(
                    str(attachment_url) if attachment_url else None,
                )
                filename = str(
                    attachment.get("filename")
                    or attachment.get("name")
                    or "attachment",
                )
            else:
                content_type = str(
                    getattr(attachment, "content_type", "") or "",
                ).lower()
                attachment_url = getattr(attachment, "url", None)
                url = QQOfficialPlatformAdapter._normalize_attachment_url(
                    str(attachment_url) if attachment_url else None,
                )
                filename = str(
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
        force_group_mention: bool = False,
    ) -> AstrBotMessage:
        """Normalize incoming botpy message into AstrBotMessage with safe string fields."""
        abm = AstrBotMessage()
        abm.type = message_type
        abm.timestamp = int(time.time())
        abm.raw_message = message
        # normalize message_id to string
        abm.message_id = str(getattr(message, "id", "") or uuid.uuid4().hex)
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

        # Group-like messages (GroupMessage or C2C in some contexts)
        if isinstance(message, botpy.message.GroupMessage) or isinstance(
            message,
            botpy.message.C2CMessage,
        ):
            if isinstance(message, botpy.message.GroupMessage):
                abm.sender = MessageMember(
                    str(getattr(message.author, "member_openid", "") or ""),
                    str(getattr(message.author, "username", "") or ""),
                )
                abm.group_id = str(getattr(message, "group_openid", "") or "")
                bot_mentions = [
                    mention
                    for mention in (getattr(message, "mentions", None) or [])
                    if getattr(mention, "is_you", False) is True
                    and getattr(mention, "id", None) is not None
                ]
                bot_mention_ids = [
                    str(getattr(mention, "id")) for mention in bot_mentions
                ]
                group_mentioned = bool(bot_mention_ids) or force_group_mention
                plain_content = str(getattr(message, "content", "") or "")
                for mention_id in bot_mention_ids:
                    plain_content = plain_content.replace(
                        f"<@{mention_id}>",
                        "",
                    ).replace(
                        f"<@!{mention_id}>",
                        "",
                    )
                abm.message_str = QQOfficialPlatformAdapter._parse_face_message(
                    plain_content.strip(),
                )
                abm.self_id = bot_mention_ids[0] if bot_mention_ids else "qq_official"
                if group_mentioned:
                    mention_name = (
                        str(getattr(bot_mentions[0], "username", "") or "")
                        if bot_mentions
                        else ""
                    )
                    msg.append(At(qq=abm.self_id, name=mention_name))
            else:
                abm.sender = MessageMember(
                    str(getattr(message.author, "user_openid", "") or ""),
                    "",
                )
                abm.message_str = QQOfficialPlatformAdapter._parse_face_message(
                    str(getattr(message, "content", "") or "").strip(),
                )
                abm.self_id = "unknown_selfid"
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
            msg.append(At(qq="qq_official"))
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
