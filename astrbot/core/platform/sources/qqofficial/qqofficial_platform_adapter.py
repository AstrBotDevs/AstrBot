from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from typing import Any, cast

import botpy
import botpy.message
from botpy import Client

from astrbot import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import At, File, Image, Plain
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
)
from astrbot.core.message.components import BaseMessageComponent
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.core.utils.number_utils import safe_positive_float

from ...register import register_platform_adapter
from .qqofficial_message_event import QQOfficialMessageEvent

# pyright: reportUnreachable=false

# remove logger handler
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)


# QQ 机器人官方框架
class MessageDeduplicator:
    def __init__(
        self,
        message_id_ttl_seconds: float = 30 * 60,
        content_key_ttl_seconds: float = 3.0,
        cleanup_interval_seconds: float = 1.0,
    ) -> None:
        self._message_id_timestamps: dict[str, float] = {}
        self._content_key_timestamps: dict[str, float] = {}
        self._message_id_ttl_seconds = message_id_ttl_seconds
        self._content_key_ttl_seconds = content_key_ttl_seconds
        self._cleanup_interval_seconds = cleanup_interval_seconds
        self._last_cleanup_at = 0.0
        self._lock = asyncio.Lock()

    def _clean_expired(self, now: float) -> None:
        if (
            self._last_cleanup_at > 0
            and now - self._last_cleanup_at < self._cleanup_interval_seconds
        ):
            return

        expired_message_ids = [
            key
            for key, ts in self._message_id_timestamps.items()
            if now - ts > self._message_id_ttl_seconds
        ]
        for key in expired_message_ids:
            self._message_id_timestamps.pop(key, None)

        expired_content_keys = [
            key
            for key, ts in self._content_key_timestamps.items()
            if now - ts > self._content_key_ttl_seconds
        ]
        for key in expired_content_keys:
            self._content_key_timestamps.pop(key, None)

        self._last_cleanup_at = now

    def _check_and_register_id(self, message_id: str, now: float) -> bool:
        existing_ts = self._message_id_timestamps.get(message_id)
        if existing_ts is not None:
            if now - existing_ts <= self._message_id_ttl_seconds:
                logger.debug(
                    "[QQOfficial] Duplicate message detected (by ID): %s...",
                    message_id[:50],
                )
                return True
            self._message_id_timestamps.pop(message_id, None)

        self._message_id_timestamps[message_id] = now
        return False

    def _build_content_key(self, content: str, sender_id: str) -> str | None:
        if not (content and sender_id):
            return None
        content_hash = hashlib.sha1(content.encode("utf-8")).hexdigest()[:16]
        return f"{sender_id}:{content_hash}"

    def _check_and_register_content_key(self, content_key: str, now: float) -> bool:
        existing_ts = self._content_key_timestamps.get(content_key)
        if existing_ts is not None:
            if now - existing_ts <= self._content_key_ttl_seconds:
                logger.debug(
                    "[QQOfficial] Duplicate message detected (by content): %s",
                    content_key,
                )
                return True
            self._content_key_timestamps.pop(content_key, None)

        self._content_key_timestamps[content_key] = now
        return False

    async def is_duplicate(
        self,
        message_id: str,
        content: str = "",
        sender_id: str = "",
    ) -> bool:
        async with self._lock:
            current_time = time.monotonic()
            self._clean_expired(current_time)

            if self._check_and_register_id(message_id, current_time):
                return True

            content_key = self._build_content_key(content, sender_id)
            if (
                content_key is not None
                and self._check_and_register_content_key(content_key, current_time)
            ):
                # Keep behavior unchanged: content duplicate should not register new message_id.
                self._message_id_timestamps.pop(message_id, None)
                return True

            logger.debug("[QQOfficial] New message registered: %s...", message_id[:50])
            return False


class botClient(Client):
    def set_platform(self, platform: QQOfficialPlatformAdapter) -> None:
        self.platform = platform

    def _get_sender_id(self, message) -> str:
        """Extract sender ID from different message types.

        The precedence order is aligned with `_parse_from_qqofficial` to ensure
        consistent deduplication and event fingerprinting:
        1. author.user_openid
        2. author.member_openid
        3. author.id
        """
        if hasattr(message, "author") and hasattr(message.author, "user_openid"):
            return str(message.author.user_openid)
        if hasattr(message, "author") and hasattr(message.author, "member_openid"):
            return str(message.author.member_openid)
        if hasattr(message, "author") and hasattr(message.author, "id"):
            return str(message.author.id)
        return ""

    def _extract_dedup_key(self, message) -> tuple[str, str]:
        sender_id = self._get_sender_id(message)
        content = getattr(message, "content", "") or ""
        return sender_id, content

    async def _should_drop_message(self, message) -> bool:
        sender_id, content = self._extract_dedup_key(message)
        return await self.platform._is_duplicate_message(message.id, content, sender_id)

    # 收到群消息
    async def on_group_at_message_create(
        self, message: botpy.message.GroupMessage
    ) -> None:
        if await self._should_drop_message(message):
            return
        abm = QQOfficialPlatformAdapter._parse_from_qqofficial(
            message,
            MessageType.GROUP_MESSAGE,
        )
        abm.group_id = cast(str, message.group_openid)
        abm.session_id = abm.group_id
        self._commit(abm)

    # 收到频道消息
    async def on_at_message_create(self, message: botpy.message.Message) -> None:
        if await self._should_drop_message(message):
            return
        abm = QQOfficialPlatformAdapter._parse_from_qqofficial(
            message,
            MessageType.GROUP_MESSAGE,
        )
        abm.group_id = message.channel_id
        abm.session_id = abm.group_id
        self._commit(abm)

    # 收到私聊消息
    async def on_direct_message_create(
        self, message: botpy.message.DirectMessage
    ) -> None:
        if await self._should_drop_message(message):
            return
        abm = QQOfficialPlatformAdapter._parse_from_qqofficial(
            message,
            MessageType.FRIEND_MESSAGE,
        )
        abm.session_id = abm.sender.user_id
        self._commit(abm)

    # 收到 C2C 消息
    async def on_c2c_message_create(self, message: botpy.message.C2CMessage) -> None:
        if await self._should_drop_message(message):
            return
        abm = QQOfficialPlatformAdapter._parse_from_qqofficial(
            message,
            MessageType.FRIEND_MESSAGE,
        )
        abm.session_id = abm.sender.user_id
        self._commit(abm)

    def _commit(self, abm: AstrBotMessage) -> None:
        self.platform.commit_event(
            QQOfficialMessageEvent(
                abm.message_str,
                abm,
                self.platform.meta(),
                abm.session_id,
                self.platform.client,
            ),
        )


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

        self.test_mode = os.environ.get("TEST_MODE", "off") == "on"

        message_id_ttl_seconds = safe_positive_float(
            platform_config.get("dedup_message_id_ttl_seconds"),
            30 * 60,
        )
        content_key_ttl_seconds = safe_positive_float(
            platform_config.get("dedup_content_key_ttl_seconds"),
            3.0,
        )
        cleanup_interval_seconds = safe_positive_float(
            platform_config.get("dedup_cleanup_interval_seconds"),
            1.0,
        )

        self._deduplicator = MessageDeduplicator(
            message_id_ttl_seconds=message_id_ttl_seconds,
            content_key_ttl_seconds=content_key_ttl_seconds,
            cleanup_interval_seconds=cleanup_interval_seconds,
        )

    async def _is_duplicate_message(
        self, message_id: str, content: str = "", sender_id: str = ""
    ) -> bool:
        return await self._deduplicator.is_duplicate(message_id, content, sender_id)

    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ) -> None:
        raise NotImplementedError("QQ 机器人官方 API 适配器不支持 send_by_session")

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="qq_official",
            description="QQ 机器人官方 API 适配器",
            id=cast(str, self.config.get("id")),
            support_proactive_message=False,
        )

    @staticmethod
    def _normalize_attachment_url(url: str | None) -> str:
        if not url:
            return ""
        if url.startswith("http://") or url.startswith("https://"):
            return url
        return f"https://{url}"

    @staticmethod
    def _append_attachments(
        msg: list[BaseMessageComponent],
        attachments: list | None,
    ) -> None:
        if not attachments:
            return

        for attachment in attachments:
            content_type = cast(str, getattr(attachment, "content_type", "") or "")
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
                msg.append(File(name=filename, file=url, url=url))

    @staticmethod
    def _parse_from_qqofficial(
        message: botpy.message.Message
        | botpy.message.GroupMessage
        | botpy.message.DirectMessage
        | botpy.message.C2CMessage,
        message_type: MessageType,
    ):
        abm = AstrBotMessage()
        abm.type = message_type
        abm.timestamp = int(time.time())
        abm.raw_message = message
        abm.message_id = message.id
        # abm.tag = "qq_official"
        msg: list[BaseMessageComponent] = []
        message = cast(Any, message)

        if isinstance(message, botpy.message.GroupMessage) or isinstance(
            message,
            botpy.message.C2CMessage,
        ):
            if isinstance(message, botpy.message.GroupMessage):
                abm.sender = MessageMember(message.author.member_openid, "")
                abm.group_id = message.group_openid
            else:
                abm.sender = MessageMember(message.author.user_openid, "")
            abm.message_str = message.content.strip()
            abm.self_id = "unknown_selfid"
            msg.append(At(qq="qq_official"))
            msg.append(Plain(abm.message_str))
            QQOfficialPlatformAdapter._append_attachments(msg, message.attachments)
            abm.message = msg

        elif isinstance(message, botpy.message.Message) or isinstance(
            message,
            botpy.message.DirectMessage,
        ):
            if isinstance(message, botpy.message.Message):
                abm.self_id = str(message.mentions[0].id)
            else:
                abm.self_id = ""

            plain_content = message.content.replace(
                "<@!" + str(abm.self_id) + ">",
                "",
            ).strip()

            QQOfficialPlatformAdapter._append_attachments(msg, message.attachments)
            abm.message = msg
            abm.message_str = plain_content
            sender_user_id = cast(
                str,
                getattr(message.author, "user_openid", None)
                or getattr(message.author, "id", ""),
            )
            abm.sender = MessageMember(
                sender_user_id,
                str(message.author.username),
            )
            msg.append(At(qq="qq_official"))
            msg.append(Plain(plain_content))

            if isinstance(message, botpy.message.Message):
                abm.group_id = message.channel_id
        else:
            raise ValueError(f"Unknown message type: {message_type}")
        abm.self_id = "qq_official"
        return abm

    def run(self):
        return self.client.start(appid=self.appid, secret=self.secret)

    def get_client(self) -> botClient:
        return self.client

    async def terminate(self) -> None:
        await self.client.close()
        logger.info("QQ 官方机器人接口 适配器已被优雅地关闭")
