from __future__ import annotations

from datetime import datetime
from typing import Any

from astrbot_sdk.errors import AstrBotError
from astrbot_sdk.message.components import component_to_payload_sync

from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform_message_history_mgr import MessageHistorySender

from ._host import CapabilityMixinHost


def _core_message_type_from_sdk(value: str) -> MessageType:
    normalized = str(value).strip().lower()
    if normalized == "group":
        return MessageType.GROUP_MESSAGE
    if normalized == "private":
        return MessageType.FRIEND_MESSAGE
    if normalized == "other":
        return MessageType.OTHER_MESSAGE
    raise AstrBotError.invalid_input(
        f"Unsupported message history message_type: {value}"
    )


def _sdk_message_type_from_core(value: MessageType | str) -> str:
    if isinstance(value, MessageType):
        if value == MessageType.GROUP_MESSAGE:
            return "group"
        if value == MessageType.FRIEND_MESSAGE:
            return "private"
        return "other"
    return str(value).strip().lower()


class MessageHistoryCapabilityMixin(CapabilityMixinHost):
    @staticmethod
    def _typed_message_history_session(payload: Any) -> MessageSession:
        if not isinstance(payload, dict):
            raise AstrBotError.invalid_input(
                "message_history capabilities require a session object"
            )
        platform_id = str(payload.get("platform_id", "")).strip()
        message_type = str(payload.get("message_type", "")).strip()
        session_id = str(payload.get("session_id", "")).strip()
        if not platform_id or not message_type or not session_id:
            raise AstrBotError.invalid_input(
                "message_history session requires platform_id, message_type, and session_id"
            )
        return MessageSession(
            platform_name=platform_id,
            message_type=_core_message_type_from_sdk(message_type),
            session_id=session_id,
        )

    @staticmethod
    def _serialize_session(session: MessageSession) -> dict[str, str]:
        return {
            "platform_id": str(session.platform_id),
            "message_type": _sdk_message_type_from_core(session.message_type),
            "session_id": str(session.session_id),
        }

    def _serialize_message_history_record(self, record: Any) -> dict[str, Any] | None:
        if record is None:
            return None
        session = getattr(record, "session", None)
        sender = getattr(record, "sender", None)
        parts = getattr(record, "parts", None)
        return {
            "id": int(getattr(record, "id", 0) or 0),
            "session": (
                self._serialize_session(session)
                if isinstance(session, MessageSession)
                else {}
            ),
            "sender": {
                "sender_id": (
                    str(getattr(sender, "sender_id", ""))
                    if getattr(sender, "sender_id", None) is not None
                    else None
                ),
                "sender_name": (
                    str(getattr(sender, "sender_name", ""))
                    if getattr(sender, "sender_name", None) is not None
                    else None
                ),
            },
            "parts": (
                [component_to_payload_sync(part) for part in parts]
                if isinstance(parts, list)
                else []
            ),
            "metadata": (
                dict(getattr(record, "metadata", {}))
                if isinstance(getattr(record, "metadata", None), dict)
                else {}
            ),
            "created_at": self._to_iso_datetime(getattr(record, "created_at", None)),
            "updated_at": self._to_iso_datetime(getattr(record, "updated_at", None)),
            "idempotency_key": (
                str(getattr(record, "idempotency_key", ""))
                if getattr(record, "idempotency_key", None) is not None
                else None
            ),
        }

    @staticmethod
    def _parse_boundary(raw_value: Any, field_name: str) -> datetime:
        text = str(raw_value or "").strip()
        if not text:
            raise AstrBotError.invalid_input(
                f"message_history.{field_name} requires {field_name}"
            )
        try:
            return datetime.fromisoformat(text)
        except ValueError as exc:
            raise AstrBotError.invalid_input(
                f"message_history.{field_name} requires an ISO datetime string"
            ) from exc

    async def _message_history_list(
        self,
        _request_id: str,
        payload: dict[str, object],
        _token,
    ) -> dict[str, object]:
        session = self._typed_message_history_session(payload.get("session"))
        raw_limit = self._optional_int(payload.get("limit"))
        limit = 50 if raw_limit is None else raw_limit
        if limit < 1:
            raise AstrBotError.invalid_input("message_history.list requires limit >= 1")
        page = await self._star_context.message_history_manager.list(
            session,
            cursor=(
                str(payload.get("cursor"))
                if payload.get("cursor") is not None
                else None
            ),
            limit=limit,
        )
        return {
            "page": {
                "records": [
                    item
                    for item in (
                        self._serialize_message_history_record(record)
                        for record in page.records
                    )
                    if item is not None
                ],
                "next_cursor": page.next_cursor,
                "total": page.total,
            }
        }

    async def _message_history_get_by_id(
        self,
        _request_id: str,
        payload: dict[str, object],
        _token,
    ) -> dict[str, object]:
        session = self._typed_message_history_session(payload.get("session"))
        record_id = self._optional_int(payload.get("record_id"))
        if record_id is None or record_id < 1:
            raise AstrBotError.invalid_input(
                "message_history.get_by_id requires record_id >= 1"
            )
        record = await self._star_context.message_history_manager.get_by_id(
            session,
            record_id,
        )
        return {"record": self._serialize_message_history_record(record)}

    async def _message_history_append(
        self,
        _request_id: str,
        payload: dict[str, object],
        _token,
    ) -> dict[str, object]:
        session = self._typed_message_history_session(payload.get("session"))
        sender_payload = payload.get("sender")
        if not isinstance(sender_payload, dict):
            raise AstrBotError.invalid_input(
                "message_history.append requires sender object"
            )
        parts_payload = payload.get("parts")
        if not isinstance(parts_payload, list) or any(
            not isinstance(item, dict) for item in parts_payload
        ):
            raise AstrBotError.invalid_input(
                "message_history.append requires parts array"
            )
        metadata = payload.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            raise AstrBotError.invalid_input(
                "message_history.append requires metadata object when provided"
            )
        record = await self._star_context.message_history_manager.append(
            session,
            parts=self._build_core_message_chain(parts_payload).chain,
            sender=MessageHistorySender(
                sender_id=(
                    str(sender_payload.get("sender_id"))
                    if sender_payload.get("sender_id") is not None
                    else None
                ),
                sender_name=(
                    str(sender_payload.get("sender_name"))
                    if sender_payload.get("sender_name") is not None
                    else None
                ),
            ),
            metadata=dict(metadata or {}),
            idempotency_key=(
                str(payload.get("idempotency_key"))
                if payload.get("idempotency_key") is not None
                else None
            ),
        )
        return {"record": self._serialize_message_history_record(record)}

    async def _message_history_delete_before(
        self,
        _request_id: str,
        payload: dict[str, object],
        _token,
    ) -> dict[str, object]:
        session = self._typed_message_history_session(payload.get("session"))
        deleted_count = await self._star_context.message_history_manager.delete_before(
            session,
            before=self._parse_boundary(payload.get("before"), "delete_before"),
        )
        return {"deleted_count": int(deleted_count)}

    async def _message_history_delete_after(
        self,
        _request_id: str,
        payload: dict[str, object],
        _token,
    ) -> dict[str, object]:
        session = self._typed_message_history_session(payload.get("session"))
        deleted_count = await self._star_context.message_history_manager.delete_after(
            session,
            after=self._parse_boundary(payload.get("after"), "delete_after"),
        )
        return {"deleted_count": int(deleted_count)}

    async def _message_history_delete_all(
        self,
        _request_id: str,
        payload: dict[str, object],
        _token,
    ) -> dict[str, object]:
        session = self._typed_message_history_session(payload.get("session"))
        deleted_count = await self._star_context.message_history_manager.delete_all(
            session
        )
        return {"deleted_count": int(deleted_count)}

    def _register_message_history_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("message_history.list", "List message history"),
            call_handler=self._message_history_list,
        )
        self.register(
            self._builtin_descriptor(
                "message_history.get_by_id",
                "Get message history by id",
            ),
            call_handler=self._message_history_get_by_id,
        )
        self.register(
            self._builtin_descriptor(
                "message_history.append", "Append message history"
            ),
            call_handler=self._message_history_append,
        )
        self.register(
            self._builtin_descriptor(
                "message_history.delete_before",
                "Delete message history before timestamp",
            ),
            call_handler=self._message_history_delete_before,
        )
        self.register(
            self._builtin_descriptor(
                "message_history.delete_after",
                "Delete message history after timestamp",
            ),
            call_handler=self._message_history_delete_after,
        )
        self.register(
            self._builtin_descriptor(
                "message_history.delete_all",
                "Delete all message history in session",
            ),
            call_handler=self._message_history_delete_all,
        )
