from __future__ import annotations

from datetime import datetime
from typing import Any

from ....errors import AstrBotError
from ....message.session import MessageSession
from ..bridge_base import CapabilityRouterBridgeBase


def _session_payload(session: MessageSession) -> dict[str, str]:
    return {
        "platform_id": str(session.platform_id),
        "message_type": str(session.message_type),
        "session_id": str(session.session_id),
    }


class MessageHistoryCapabilityMixin(CapabilityRouterBridgeBase):
    @staticmethod
    def _typed_session_from_payload(payload: Any) -> MessageSession:
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
            platform_id=platform_id,
            message_type=message_type,
            session_id=session_id,
        )

    @staticmethod
    def _typed_key(session: MessageSession) -> str:
        return (
            f"{str(session.platform_id)}:{str(session.message_type).lower()}:"
            f"{str(session.session_id)}"
        )

    def _message_history_records(self, session: MessageSession) -> list[dict[str, Any]]:
        key = self._typed_key(session)
        records = self._message_history_store.get(key)
        if records is None:
            records = []
            self._message_history_store[key] = records
        return records

    def _next_message_history_id(self) -> int:
        next_id = int(self._message_history_next_id)
        self._message_history_next_id += 1
        return next_id

    def _create_message_history_record(
        self,
        *,
        session: MessageSession,
        sender_payload: dict[str, Any],
        parts_payload: list[dict[str, Any]],
        metadata: dict[str, Any],
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        now = self._now_iso()
        return {
            "id": self._next_message_history_id(),
            "session": _session_payload(session),
            "sender": {
                "sender_id": (
                    str(sender_payload.get("sender_id"))
                    if sender_payload.get("sender_id") is not None
                    else None
                ),
                "sender_name": (
                    str(sender_payload.get("sender_name"))
                    if sender_payload.get("sender_name") is not None
                    else None
                ),
            },
            "parts": [dict(item) for item in parts_payload if isinstance(item, dict)],
            "metadata": dict(metadata),
            "created_at": now,
            "updated_at": now,
            "idempotency_key": idempotency_key,
        }

    @staticmethod
    def _serialize_record(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": int(record.get("id", 0) or 0),
            "session": (
                dict(record.get("session"))
                if isinstance(record.get("session"), dict)
                else {}
            ),
            "sender": (
                dict(record.get("sender"))
                if isinstance(record.get("sender"), dict)
                else {}
            ),
            "parts": (
                [
                    dict(item)
                    for item in record.get("parts", [])
                    if isinstance(item, dict)
                ]
                if isinstance(record.get("parts"), list)
                else []
            ),
            "metadata": (
                dict(record.get("metadata"))
                if isinstance(record.get("metadata"), dict)
                else {}
            ),
            "created_at": record.get("created_at"),
            "updated_at": record.get("updated_at"),
            "idempotency_key": (
                str(record.get("idempotency_key"))
                if record.get("idempotency_key") is not None
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
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session = self._typed_session_from_payload(payload.get("session"))
        raw_limit = self._optional_int(payload.get("limit"))
        limit = 50 if raw_limit is None else raw_limit
        if limit < 1:
            raise AstrBotError.invalid_input("message_history.list requires limit >= 1")
        cursor = payload.get("cursor")
        cursor_id = int(str(cursor)) if cursor not in (None, "") else None
        records = list(reversed(self._message_history_records(session)))
        total = len(records)
        if cursor_id is not None:
            records = [
                record for record in records if int(record.get("id", 0)) < cursor_id
            ]
        page_records = records[:limit]
        next_cursor = (
            str(page_records[-1]["id"])
            if len(records) > limit and page_records
            else None
        )
        return {
            "page": {
                "records": [self._serialize_record(record) for record in page_records],
                "next_cursor": next_cursor,
                "total": total,
            }
        }

    async def _message_history_get_by_id(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session = self._typed_session_from_payload(payload.get("session"))
        record_id = self._optional_int(payload.get("record_id"))
        if record_id is None or record_id < 1:
            raise AstrBotError.invalid_input(
                "message_history.get_by_id requires record_id >= 1"
            )
        record = next(
            (
                item
                for item in self._message_history_records(session)
                if int(item.get("id", 0) or 0) == record_id
            ),
            None,
        )
        return {
            "record": self._serialize_record(record) if record is not None else None
        }

    async def _message_history_append(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session = self._typed_session_from_payload(payload.get("session"))
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
        idempotency_key = (
            str(payload.get("idempotency_key"))
            if payload.get("idempotency_key") is not None
            else None
        )
        records = self._message_history_records(session)
        if idempotency_key:
            existing = next(
                (
                    record
                    for record in records
                    if str(record.get("idempotency_key") or "") == idempotency_key
                ),
                None,
            )
            if existing is not None:
                return {"record": self._serialize_record(existing)}
        record = self._create_message_history_record(
            session=session,
            sender_payload=sender_payload,
            parts_payload=parts_payload,
            metadata=dict(metadata or {}),
            idempotency_key=idempotency_key,
        )
        records.append(record)
        return {"record": self._serialize_record(record)}

    async def _message_history_delete_before(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session = self._typed_session_from_payload(payload.get("session"))
        before = self._parse_boundary(payload.get("before"), "delete_before")
        records = self._message_history_records(session)
        retained: list[dict[str, Any]] = []
        deleted_count = 0
        for record in records:
            created_at = datetime.fromisoformat(str(record.get("created_at")))
            if created_at < before:
                deleted_count += 1
                continue
            retained.append(record)
        self._message_history_store[self._typed_key(session)] = retained
        return {"deleted_count": deleted_count}

    async def _message_history_delete_after(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session = self._typed_session_from_payload(payload.get("session"))
        after = self._parse_boundary(payload.get("after"), "delete_after")
        records = self._message_history_records(session)
        retained: list[dict[str, Any]] = []
        deleted_count = 0
        for record in records:
            created_at = datetime.fromisoformat(str(record.get("created_at")))
            if created_at > after:
                deleted_count += 1
                continue
            retained.append(record)
        self._message_history_store[self._typed_key(session)] = retained
        return {"deleted_count": deleted_count}

    async def _message_history_delete_all(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session = self._typed_session_from_payload(payload.get("session"))
        key = self._typed_key(session)
        deleted_count = len(self._message_history_store.get(key, []))
        self._message_history_store[key] = []
        return {"deleted_count": deleted_count}

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
