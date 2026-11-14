"""History actions depend on their own baseline, not on visible message content."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from astrbot.core.db.po import ConversationEvent, ConversationV3
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.dashboard.services.chat_service import ChatService


@pytest_asyncio.fixture
async def service(tmp_path):
    db = SQLiteDatabase(str(tmp_path / "capabilities.db"))
    await db.initialize()
    async with db.get_db() as session:
        conv = ConversationV3(conversation_id="cid", umo="owner", platform_id="webchat")
        other = ConversationV3(
            conversation_id="foreign", umo="other", platform_id="webchat"
        )
        session.add_all([conv, other])
        await session.flush()
        rows = [
            (conv.id, "pruned", "context.rebased", None),
            (
                conv.id,
                "old",
                "message.appended",
                {"message": {"role": "assistant", "content": "old"}},
            ),
            (conv.id, "kept", "context.rebased", {"messages": []}),
            (
                conv.id,
                "turn-edit",
                "turn.started",
                {"base_leaf_event_id": "kept"},
            ),
            (
                conv.id,
                "turn-retry",
                "turn.started",
                {"base_leaf_event_id": "old"},
            ),
            (conv.id, "turn-empty", "turn.started", {"base_leaf_event_id": None}),
            (
                other.id,
                "foreign-turn",
                "turn.started",
                {"base_leaf_event_id": None},
            ),
        ]
        session.add_all(
            [
                ConversationEvent(
                    conversation_ref=owner,
                    seq=seq,
                    event_id=identity,
                    type=kind,
                    payload=payload,
                )
                for seq, (owner, identity, kind, payload) in enumerate(rows, 1)
            ]
        )
        await session.commit()
    service = object.__new__(ChatService)
    service.db = db
    service.conv_mgr = SimpleNamespace(
        get_curr_conversation_id=AsyncMock(return_value="cid")
    )
    yield service
    await db.engine.dispose()


@pytest.mark.asyncio
async def test_capabilities_use_distinct_operation_targets_and_preserve_guards(service):
    rows = [
        {
            "id": 1,
            "content": {"type": "user"},
            "context_event_id": "old",
            "turn_id": "turn-edit",
        },
        {
            "id": 2,
            "content": {"type": "bot"},
            "context_event_id": "kept",
            "turn_id": "turn-retry",
        },
        {"id": 3, "content": {"type": "user"}, "turn_id": "turn-empty"},
        {"id": 4, "content": {"type": "user"}, "turn_id": "foreign-turn"},
        {
            "id": 5,
            "content": {"type": "user"},
            "turn_id": "turn-edit",
            "is_active": False,
        },
    ]
    await service.add_history_capabilities(rows, "owner", running=False)
    assert rows[0]["can_edit"] is True
    assert rows[0]["can_fork"] is False
    assert rows[1]["can_fork"] is True
    assert rows[1]["can_retry"] is False
    assert rows[1]["retry_unavailable_reason"] == "context_pruned"
    assert rows[2]["can_edit"] is True
    assert rows[3]["edit_unavailable_reason"] == "context_unavailable"
    assert rows[4]["edit_unavailable_reason"] == "inactive_message"
    await service.add_history_capabilities(rows, "owner", running=True)
    assert rows[0]["edit_unavailable_reason"] == "run_active"
    assert rows[1]["can_fork"] is True


@pytest.mark.asyncio
async def test_unlinked_history_never_guesses_empty_context():
    service = object.__new__(ChatService)
    rows = [{"content": {"type": "user"}}, {"content": {"type": "bot"}}]
    await service.add_history_capabilities(rows, None, running=False)
    assert not any(
        row["can_edit"] or row["can_fork"] or row["can_retry"] for row in rows
    )
