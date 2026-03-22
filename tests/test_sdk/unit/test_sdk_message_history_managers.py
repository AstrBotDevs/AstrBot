# ruff: noqa: E402
from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest


def _install_optional_dependency_stubs() -> None:
    def install(name: str, attrs: dict[str, object]) -> None:
        if name in sys.modules:
            return
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module

    install(
        "faiss",
        {
            "read_index": lambda *args, **kwargs: None,
            "write_index": lambda *args, **kwargs: None,
            "IndexFlatL2": type("IndexFlatL2", (), {}),
            "IndexIDMap": type("IndexIDMap", (), {}),
            "normalize_L2": lambda *args, **kwargs: None,
        },
    )
    install("pypdf", {"PdfReader": type("PdfReader", (), {})})
    install(
        "jieba",
        {
            "cut": lambda text, *args, **kwargs: text.split(),
            "lcut": lambda text, *args, **kwargs: text.split(),
        },
    )
    install("rank_bm25", {"BM25Okapi": type("BM25Okapi", (), {})})
    install(
        "aiocqhttp",
        {
            "CQHttp": type("CQHttp", (), {}),
            "Event": type("Event", (), {}),
        },
    )
    install(
        "aiocqhttp.exceptions",
        {"ActionFailed": type("ActionFailed", (Exception,), {})},
    )


_install_optional_dependency_stubs()

from astrbot_sdk.errors import AstrBotError

from astrbot.core.message.components import Plain
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform_message_history_mgr import (
    MessageHistoryPage,
    MessageHistoryRecord,
    MessageHistorySender,
)
from astrbot.core.sdk_bridge.capability_bridge import CoreCapabilityBridge


@dataclass(slots=True)
class _FakeMessageHistoryManager:
    append_calls: list[dict[str, object]]
    list_calls: list[dict[str, object]]
    get_calls: list[dict[str, object]]
    delete_before_calls: list[dict[str, object]]
    delete_after_calls: list[dict[str, object]]
    delete_all_calls: list[MessageSession]
    record: MessageHistoryRecord

    def __init__(self) -> None:
        session = MessageSession(
            platform_name="demo-platform",
            message_type=MessageType.FRIEND_MESSAGE,
            session_id="user-1",
        )
        self.append_calls = []
        self.list_calls = []
        self.get_calls = []
        self.delete_before_calls = []
        self.delete_after_calls = []
        self.delete_all_calls = []
        self.record = MessageHistoryRecord(
            id=7,
            session=session,
            sender=MessageHistorySender(sender_id="sender-1", sender_name="Tester"),
            parts=[Plain("hello history", convert=False)],
            metadata={"trace_id": "trace-1"},
            created_at=datetime(2026, 3, 22, 9, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 3, 22, 9, 1, tzinfo=timezone.utc),
            idempotency_key="idem-1",
        )

    async def append(self, session: MessageSession, **kwargs) -> MessageHistoryRecord:
        self.append_calls.append({"session": session, **kwargs})
        return self.record

    async def list(
        self,
        session: MessageSession,
        *,
        cursor: str | None = None,
        limit: int = 50,
    ) -> MessageHistoryPage:
        self.list_calls.append({"session": session, "cursor": cursor, "limit": limit})
        return MessageHistoryPage(records=[self.record], next_cursor="6", total=3)

    async def get_by_id(
        self,
        session: MessageSession,
        record_id: int,
    ) -> MessageHistoryRecord | None:
        self.get_calls.append({"session": session, "record_id": record_id})
        return self.record if record_id == self.record.id else None

    async def delete_before(self, session: MessageSession, *, before: datetime) -> int:
        self.delete_before_calls.append({"session": session, "before": before})
        return 2

    async def delete_after(self, session: MessageSession, *, after: datetime) -> int:
        self.delete_after_calls.append({"session": session, "after": after})
        return 1

    async def delete_all(self, session: MessageSession) -> int:
        self.delete_all_calls.append(session)
        return 3


def _build_bridge(
    message_history_manager: _FakeMessageHistoryManager,
) -> CoreCapabilityBridge:
    return CoreCapabilityBridge(
        star_context=SimpleNamespace(
            message_history_manager=message_history_manager,
            persona_manager=object(),
            conversation_manager=object(),
            kb_manager=object(),
        ),
        plugin_bridge=SimpleNamespace(resolve_request_session=lambda _request_id: None),
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_core_bridge_message_history_capabilities_round_trip() -> None:
    manager = _FakeMessageHistoryManager()
    bridge = _build_bridge(manager)

    descriptor_names = {item.name for item in bridge.descriptors()}
    assert "message_history.list" in descriptor_names
    assert "message_history.get_by_id" in descriptor_names
    assert "message_history.append" in descriptor_names
    assert "message_history.delete_before" in descriptor_names
    assert "message_history.delete_after" in descriptor_names
    assert "message_history.delete_all" in descriptor_names

    append_result = await bridge._message_history_append(
        "req-append",
        {
            "session": {
                "platform_id": "demo-platform",
                "message_type": "private",
                "session_id": "user-1",
            },
            "sender": {"sender_id": "sender-1", "sender_name": "Tester"},
            "parts": [{"type": "text", "data": {"text": "hello history"}}],
            "metadata": {"trace_id": "trace-1"},
            "idempotency_key": "idem-1",
        },
        None,
    )
    assert append_result["record"] is not None
    assert append_result["record"]["session"] == {
        "platform_id": "demo-platform",
        "message_type": "private",
        "session_id": "user-1",
    }
    assert append_result["record"]["sender"] == {
        "sender_id": "sender-1",
        "sender_name": "Tester",
    }
    assert append_result["record"]["parts"] == [
        {"type": "text", "data": {"text": "hello history"}}
    ]
    append_call = manager.append_calls[-1]
    append_session = append_call["session"]
    assert isinstance(append_session, MessageSession)
    assert append_session.platform_id == "demo-platform"
    assert append_session.message_type == MessageType.FRIEND_MESSAGE
    assert append_session.session_id == "user-1"

    list_result = await bridge._message_history_list(
        "req-list",
        {
            "session": {
                "platform_id": "demo-platform",
                "message_type": "private",
                "session_id": "user-1",
            },
            "cursor": "10",
            "limit": 1,
        },
        None,
    )
    assert list_result["page"]["next_cursor"] == "6"
    assert list_result["page"]["total"] == 3
    assert manager.list_calls[-1]["cursor"] == "10"
    assert manager.list_calls[-1]["limit"] == 1

    get_result = await bridge._message_history_get_by_id(
        "req-get",
        {
            "session": {
                "platform_id": "demo-platform",
                "message_type": "private",
                "session_id": "user-1",
            },
            "record_id": 7,
        },
        None,
    )
    assert get_result["record"]["id"] == 7
    assert manager.get_calls[-1]["record_id"] == 7

    deleted_before = await bridge._message_history_delete_before(
        "req-delete-before",
        {
            "session": {
                "platform_id": "demo-platform",
                "message_type": "private",
                "session_id": "user-1",
            },
            "before": "2026-03-22T09:30:00+00:00",
        },
        None,
    )
    assert deleted_before == {"deleted_count": 2}
    assert manager.delete_before_calls[-1]["before"] == datetime(
        2026, 3, 22, 9, 30, tzinfo=timezone.utc
    )

    deleted_after = await bridge._message_history_delete_after(
        "req-delete-after",
        {
            "session": {
                "platform_id": "demo-platform",
                "message_type": "private",
                "session_id": "user-1",
            },
            "after": "2026-03-22T08:59:00+00:00",
        },
        None,
    )
    assert deleted_after == {"deleted_count": 1}

    deleted_all = await bridge._message_history_delete_all(
        "req-delete-all",
        {
            "session": {
                "platform_id": "demo-platform",
                "message_type": "private",
                "session_id": "user-1",
            }
        },
        None,
    )
    assert deleted_all == {"deleted_count": 3}
    assert manager.delete_all_calls[-1].session_id == "user-1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_core_bridge_message_history_validates_typed_session_payload() -> None:
    bridge = _build_bridge(_FakeMessageHistoryManager())

    with pytest.raises(AstrBotError, match="require a session object"):
        await bridge._message_history_list(
            "req-1", {"session": "demo:private:user"}, None
        )

    with pytest.raises(AstrBotError, match="requires limit >= 1"):
        await bridge._message_history_list(
            "req-2",
            {
                "session": {
                    "platform_id": "demo-platform",
                    "message_type": "private",
                    "session_id": "user-1",
                },
                "limit": 0,
            },
            None,
        )
