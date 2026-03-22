from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from astrbot_sdk.message.components import component_to_payload_sync

from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import PlatformMessageHistory
from astrbot.core.message.components import (
    At,
    AtAll,
    BaseMessageComponent,
    File,
    Forward,
    Image,
    Plain,
    Poke,
    Record,
    Reply,
    Unknown,
    Video,
)
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.message_type import MessageType


@dataclass(frozen=True, slots=True)
class MessageHistorySender:
    sender_id: str | None = None
    sender_name: str | None = None


@dataclass(slots=True)
class MessageHistoryRecord:
    id: int
    session: MessageSession
    sender: MessageHistorySender
    parts: list[BaseMessageComponent] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True, slots=True)
class MessageHistoryPage:
    records: list[MessageHistoryRecord]
    next_cursor: str | None
    total: int | None


def _message_type_key(value: MessageType | str) -> str:
    if isinstance(value, MessageType):
        if value == MessageType.GROUP_MESSAGE:
            return "group"
        if value == MessageType.FRIEND_MESSAGE:
            return "private"
        return "other"
    normalized = str(value).strip().lower()
    if normalized in {"group", "groupmessage", "group_message"}:
        return "group"
    if normalized in {
        "private",
        "friend",
        "friendmessage",
        "privatemessage",
        "friend_message",
        "private_message",
    }:
        return "private"
    if normalized in {"other", "othermessage", "other_message"}:
        return "other"
    raise ValueError(f"Unsupported message type: {value}")


def _message_type_enum(value: str) -> MessageType:
    normalized = _message_type_key(value)
    if normalized == "group":
        return MessageType.GROUP_MESSAGE
    if normalized == "private":
        return MessageType.FRIEND_MESSAGE
    return MessageType.OTHER_MESSAGE


def _session_storage_key(session: MessageSession) -> str:
    # TODO(refactor): persist message_type as a first-class column once the
    # legacy message history model can be migrated without impacting old plugins.
    return f"{_message_type_key(session.message_type)}:{session.session_id}"


def _optional_int_cursor(cursor: str | None) -> int | None:
    if cursor is None:
        return None
    text = str(cursor).strip()
    if not text:
        return None
    return int(text)


def _payload_to_component(payload: Any) -> BaseMessageComponent:
    if not isinstance(payload, dict):
        return Unknown(text=str(payload))

    raw_type = str(payload.get("type", "unknown") or "unknown").lower()
    data = payload.get("data")
    if not isinstance(data, dict):
        data = {}

    if raw_type in {"text", "plain"}:
        return Plain(str(data.get("text", "")), convert=False)
    if raw_type == "image":
        image_data = dict(data)
        image_file = str(image_data.pop("file", "") or image_data.get("url") or "")
        return Image(image_file, **image_data)
    if raw_type == "at":
        qq_value = data.get("qq")
        if str(qq_value).lower() == "all":
            return AtAll()
        return At(qq=str(qq_value or ""), name=str(data.get("name", "")))
    if raw_type == "reply":
        reply_data = dict(data)
        chain_payload = reply_data.get("chain")
        reply_data["chain"] = (
            [_payload_to_component(item) for item in chain_payload]
            if isinstance(chain_payload, list)
            else []
        )
        return Reply(**reply_data)
    if raw_type == "record":
        record_data = dict(data)
        record_file = str(record_data.pop("file", "") or record_data.get("url") or "")
        return Record(record_file, **record_data)
    if raw_type == "video":
        video_data = dict(data)
        video_file = str(video_data.pop("file", "") or "")
        return Video(video_file, **video_data)
    if raw_type == "file":
        file_value = str(data.get("file") or data.get("file_") or data.get("url") or "")
        return File(
            str(data.get("name", "") or "file"),
            file="" if file_value.startswith(("http://", "https://")) else file_value,
            url=file_value if file_value.startswith(("http://", "https://")) else "",
        )
    if raw_type == "poke":
        return Poke(
            poke_type=data.get("type"),
            id=data.get("id"),
            qq=data.get("qq"),
        )
    if raw_type == "forward":
        return Forward(id=str(data.get("id", "")))
    return Unknown(text=str(payload))


def _legacy_content_to_payloads(
    content: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    message_parts = content.get("message")
    if not isinstance(message_parts, list):
        return [], {}
    payloads: list[dict[str, Any]] = []
    for part in message_parts:
        if not isinstance(part, dict):
            continue
        part_type = str(part.get("type", "")).strip().lower()
        if part_type == "plain":
            text = str(part.get("text", ""))
            if text:
                payloads.append({"type": "text", "data": {"text": text}})
            continue
        if part_type == "reply":
            message_id = part.get("message_id")
            if message_id is None:
                continue
            payloads.append(
                {
                    "type": "reply",
                    "data": {
                        "id": str(message_id),
                        "message_str": str(part.get("selected_text", "")),
                        "chain": [],
                    },
                }
            )
            continue
        if part_type not in {"image", "record", "file", "video"}:
            continue
        payload_data: dict[str, Any] = {}
        attachment_id = part.get("attachment_id")
        if attachment_id is not None:
            payload_data["attachment_id"] = str(attachment_id)
        filename = part.get("filename")
        if filename is not None:
            payload_data["filename"] = str(filename)
            if part_type == "file":
                payload_data["name"] = str(filename)
        path_value = part.get("path")
        if path_value not in (None, ""):
            payload_data["path"] = str(path_value)
            payload_data["file"] = str(path_value)
        payloads.append({"type": part_type, "data": payload_data})
    metadata = {key: value for key, value in content.items() if key != "message"}
    return payloads, metadata


def _content_to_parts_and_metadata(
    content: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any], str | None]:
    if not isinstance(content, dict):
        return [], {}, None
    if isinstance(content.get("parts"), list):
        metadata = content.get("metadata")
        idempotency_key = content.get("idempotency_key")
        return (
            [dict(item) for item in content["parts"] if isinstance(item, dict)],
            dict(metadata) if isinstance(metadata, dict) else {},
            str(idempotency_key) if idempotency_key is not None else None,
        )
    payloads, metadata = _legacy_content_to_payloads(content)
    return payloads, metadata, None


class PlatformMessageHistoryManager:
    MessageHistorySender = MessageHistorySender
    MessageHistoryRecord = MessageHistoryRecord
    MessageHistoryPage = MessageHistoryPage

    def __init__(self, db_helper: BaseDatabase) -> None:
        self.db = db_helper

    async def insert(
        self,
        platform_id: str,
        user_id: str,
        content: dict,
        sender_id: str | None = None,
        sender_name: str | None = None,
    ) -> PlatformMessageHistory:
        """Insert a new platform message history record."""
        return await self.db.insert_platform_message_history(
            platform_id=platform_id,
            user_id=user_id,
            content=content,
            sender_id=sender_id,
            sender_name=sender_name,
        )

    async def get(
        self,
        platform_id: str,
        user_id: str,
        page: int = 1,
        page_size: int = 200,
    ) -> list[PlatformMessageHistory]:
        """Get platform message history for a specific user."""
        history = await self.db.get_platform_message_history(
            platform_id=platform_id,
            user_id=user_id,
            page=page,
            page_size=page_size,
        )
        history.reverse()
        return history

    async def delete(
        self, platform_id: str, user_id: str, offset_sec: int = 86400
    ) -> None:
        """Delete platform message history records older than the specified offset."""
        await self.db.delete_platform_message_offset(
            platform_id=platform_id,
            user_id=user_id,
            offset_sec=offset_sec,
        )

    async def append(
        self,
        session: MessageSession,
        *,
        parts: list[BaseMessageComponent],
        sender: MessageHistorySender,
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> MessageHistoryRecord:
        storage_user_id = _session_storage_key(session)
        if idempotency_key:
            # TODO(refactor): move idempotency_key into a dedicated indexed column
            # after the legacy history table is migrated for the new SDK path.
            existing = await self.db.find_platform_message_history_by_idempotency_key(
                platform_id=session.platform_id,
                user_id=storage_user_id,
                idempotency_key=idempotency_key,
            )
            if existing is not None:
                return self._record_from_model(existing)

        content = {
            "parts": [component_to_payload_sync(part) for part in parts],
            "metadata": dict(metadata or {}),
        }
        if idempotency_key is not None:
            content["idempotency_key"] = str(idempotency_key)

        record = await self.db.insert_platform_message_history(
            platform_id=session.platform_id,
            user_id=storage_user_id,
            content=content,
            sender_id=sender.sender_id,
            sender_name=sender.sender_name,
        )
        return self._record_from_model(record)

    async def list(
        self,
        session: MessageSession,
        *,
        cursor: str | None = None,
        limit: int = 50,
    ) -> MessageHistoryPage:
        normalized_limit = max(1, int(limit))
        rows, total = await self.db.list_sdk_platform_message_history(
            platform_id=session.platform_id,
            user_id=_session_storage_key(session),
            cursor_id=_optional_int_cursor(cursor),
            limit=normalized_limit + 1,
            include_total=True,
        )
        has_more = len(rows) > normalized_limit
        page_rows = rows[:normalized_limit]
        records = [self._record_from_model(row) for row in page_rows]
        next_cursor = str(page_rows[-1].id) if has_more and page_rows else None
        return MessageHistoryPage(records=records, next_cursor=next_cursor, total=total)

    async def get_by_id(
        self,
        session: MessageSession,
        record_id: int,
    ) -> MessageHistoryRecord | None:
        record = await self.db.get_platform_message_history_by_id(int(record_id))
        if record is None:
            return None
        if record.platform_id != session.platform_id:
            return None
        if record.user_id != _session_storage_key(session):
            return None
        return self._record_from_model(record)

    async def delete_before(
        self,
        session: MessageSession,
        *,
        before: datetime,
    ) -> int:
        return await self.db.delete_platform_message_before(
            platform_id=session.platform_id,
            user_id=_session_storage_key(session),
            before=before,
        )

    async def delete_after(
        self,
        session: MessageSession,
        *,
        after: datetime,
    ) -> int:
        return await self.db.delete_platform_message_after(
            platform_id=session.platform_id,
            user_id=_session_storage_key(session),
            after=after,
        )

    async def delete_all(self, session: MessageSession) -> int:
        return await self.db.delete_all_platform_message_history(
            platform_id=session.platform_id,
            user_id=_session_storage_key(session),
        )

    def _record_from_model(
        self, record: PlatformMessageHistory
    ) -> MessageHistoryRecord:
        parts_payload, metadata, idempotency_key = _content_to_parts_and_metadata(
            record.content
        )
        return MessageHistoryRecord(
            id=int(record.id or 0),
            session=self._session_from_storage_record(record),
            sender=MessageHistorySender(
                sender_id=str(record.sender_id)
                if record.sender_id is not None
                else None,
                sender_name=(
                    str(record.sender_name) if record.sender_name is not None else None
                ),
            ),
            parts=[_payload_to_component(item) for item in parts_payload],
            metadata=metadata,
            created_at=record.created_at,
            updated_at=record.updated_at,
            idempotency_key=idempotency_key,
        )

    def _session_from_storage_record(
        self, record: PlatformMessageHistory
    ) -> MessageSession:
        raw_user_id = str(record.user_id or "")
        message_type = "private"
        session_id = raw_user_id
        if ":" in raw_user_id:
            maybe_message_type, maybe_session_id = raw_user_id.split(":", 1)
            if maybe_message_type in {"group", "private", "other"} and maybe_session_id:
                message_type = maybe_message_type
                session_id = maybe_session_id
        return MessageSession(
            platform_name=str(record.platform_id),
            message_type=_message_type_enum(message_type),
            session_id=session_id,
        )
