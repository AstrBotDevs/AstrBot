"""History actions depend on their own baseline, not on visible message content."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import event

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
        session.add_all(
            [
                ConversationEvent(
                    conversation_ref=conv.id,
                    seq=1,
                    event_id="pruned",
                    type="context.rebased",
                    payload=None,
                    replay_from_event_id="pruned",
                ),
                ConversationEvent(
                    conversation_ref=conv.id,
                    seq=2,
                    event_id="old",
                    type="message.appended",
                    payload={"message": {"role": "assistant", "content": "old"}},
                    replay_from_event_id="pruned",
                ),
                ConversationEvent(
                    conversation_ref=conv.id,
                    seq=3,
                    event_id="kept",
                    type="context.rebased",
                    payload={"messages": []},
                    replay_from_event_id="kept",
                ),
                ConversationEvent(
                    conversation_ref=conv.id,
                    seq=4,
                    event_id="turn-edit",
                    type="turn.started",
                    payload={"base_leaf_event_id": "kept"},
                ),
                ConversationEvent(
                    conversation_ref=conv.id,
                    seq=5,
                    event_id="turn-retry",
                    type="turn.started",
                    payload={"base_leaf_event_id": "old"},
                ),
                ConversationEvent(
                    conversation_ref=conv.id,
                    seq=6,
                    event_id="turn-empty",
                    type="turn.started",
                    payload={"base_leaf_event_id": None},
                ),
                ConversationEvent(
                    conversation_ref=other.id,
                    seq=1,
                    event_id="foreign-turn",
                    type="turn.started",
                    payload={"base_leaf_event_id": None},
                ),
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
async def test_capability_page_batches_metadata_without_projecting(
    service, monkeypatch
):
    rows = [
        {
            "id": i,
            "content": {"type": "bot"},
            "context_event_id": "old",
            "turn_id": "turn-edit",
        }
        for i in range(1000)
    ]
    statements = []
    event.listen(
        service.db.engine.sync_engine,
        "before_cursor_execute",
        lambda conn, cursor, statement, parameters, context, executemany: (
            statements.append(statement)
        ),
    )
    monkeypatch.setattr(
        service.db.conversation_store,
        "project",
        AsyncMock(side_effect=AssertionError("must not replay")),
    )
    await service.add_history_capabilities(rows, "owner", running=False)
    assert len(statements) <= 5
    assert all(row["can_retry"] and not row["can_fork"] for row in rows)
    assert all(row["fork_unavailable_reason"] == "context_pruned" for row in rows)


@pytest.mark.asyncio
async def test_unlinked_history_never_guesses_empty_context():
    service = object.__new__(ChatService)
    rows = [{"content": {"type": "user"}}, {"content": {"type": "bot"}}]
    await service.add_history_capabilities(rows, None, running=False)
    assert not any(
        row["can_edit"] or row["can_fork"] or row["can_retry"] for row in rows
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["edit", "retry", "fork"])
async def test_pruned_context_after_page_load_returns_clear_service_error(action):
    from astrbot.core.db.conversation import ContextUnavailableError
    from astrbot.dashboard.services.chat_service import ChatServiceError

    service = object.__new__(ChatService)
    service.running_convs = {}
    role = "user" if action == "edit" else "bot"
    content = {"type": role, "message": [{"type": "plain", "text": "shown"}]}
    service.db = SimpleNamespace(
        get_platform_session_by_id=AsyncMock(
            return_value=SimpleNamespace(
                session_id="s",
                platform_id="webchat",
                creator="owner",
                is_group=False,
            )
        ),
        get_platform_message_history_by_id=AsyncMock(
            return_value=SimpleNamespace(
                platform_id="webchat",
                user_id="s",
                content=content,
                context_event_id="old",
                turn_id="turn",
            )
        ),
        conversation_store=SimpleNamespace(
            read=AsyncMock(
                return_value=SimpleNamespace(
                    conversation=SimpleNamespace(head_seq=10, leaf_event_id="new")
                )
            ),
            rewind_webchat=AsyncMock(side_effect=ContextUnavailableError("pruned")),
        ),
        get_webchat_thread_by_parent_message_and_text=AsyncMock(return_value=None),
        create_webchat_thread=AsyncMock(
            return_value=SimpleNamespace(thread_id="thread")
        ),
        delete_webchat_thread=AsyncMock(),
    )
    service.conv_mgr = SimpleNamespace(
        get_curr_conversation_id=AsyncMock(return_value="cid"),
        fork_conversation=AsyncMock(side_effect=ContextUnavailableError("pruned")),
    )
    with pytest.raises(ChatServiceError, match="Historical context has been cleared"):
        if action == "fork":
            await service.create_thread(
                "owner",
                {"session_id": "s", "parent_message_id": 1, "selected_text": "shown"},
            )
        elif action == "edit":
            await service.update_message(
                "owner", {"session_id": "s", "message_id": 1, "content": content}
            )
        else:
            await service.prepare_regenerate_message_payload(
                "owner", {"session_id": "s", "message_id": 1}
            )
    if action == "fork":
        service.db.delete_webchat_thread.assert_awaited_once_with("thread")
