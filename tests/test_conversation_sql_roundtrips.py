"""Round-trip budgets and correctness of combined conversation queries."""

import asyncio

import pytest
from sqlalchemy import event
from sqlmodel import select

from astrbot.core.agent.conversation_events import ConversationEventWriter
from astrbot.core.db.conversation import ConversationConflictError
from astrbot.core.db.po import ProviderStat


@pytest.fixture
def statements(database):
    """Collect executed SQL for the test's initialized database."""
    captured = []

    def record(_conn, _cursor, statement, _params, _context, _many):
        captured.append(statement)

    engine = database.engine.sync_engine
    event.listen(engine, "before_cursor_execute", record)
    try:
        yield captured
    finally:
        event.remove(engine, "before_cursor_execute", record)


@pytest.mark.asyncio
@pytest.mark.parametrize("latest_usage", [None, 0, 42])
async def test_execution_load_preserves_usage_and_history_in_three_selects(
    database, statements, latest_usage
):
    store = database.conversation_store
    conv = await store.create(
        umo="owner", platform_id="p", content=[{"role": "user", "content": "seed"}]
    )
    await database.update_conversation(conv.conversation_id, token_usage=123)
    await store.append(
        conv.conversation_id,
        [
            {"type": "conversation.updated", "payload": {"token_usage": latest_usage}},
            {
                "type": "message.appended",
                "payload": {"message": {"role": "assistant", "content": "tail"}},
            },
        ],
    )
    statements.clear()
    record, snapshot = await store.read_for_execution(conv.conversation_id)
    assert sum(sql.startswith("SELECT") for sql in statements) == 3
    assert record.token_usage == (123 if latest_usage is None else latest_usage)
    assert (
        record.content
        == snapshot.messages
        == [
            {"role": "user", "content": "seed"},
            {"role": "assistant", "content": "tail"},
        ]
    )
    record.content[0]["content"] = "plugin edit"
    assert snapshot.messages[0]["content"] == "seed"


@pytest.mark.asyncio
async def test_provider_stat_returns_persisted_defaults_without_readback(
    database, statements
):
    statements.clear()
    record = await database.insert_provider_stat(
        umo="owner", provider_id="p", stats={"token_usage": {"output": 7}}
    )
    assert not any(sql.startswith("SELECT") for sql in statements)
    assert record.id is not None and record.created_at is not None
    async with database.get_db() as session:
        stored = await session.scalar(
            select(ProviderStat).where(ProviderStat.id == record.id)
        )
    assert stored.token_output == record.token_output == 7
    assert stored.created_at.replace(tzinfo=None) == record.created_at.replace(
        tzinfo=None
    )


@pytest.mark.asyncio
async def test_im_writer_skips_display_queries_for_append_and_save(
    database, statements
):
    store = database.conversation_store
    conv = await store.create(umo="owner", platform_id="p")
    writer = ConversationEventWriter(
        store, await store.read(conv.conversation_id), link_display=False
    )
    await writer.start_turn({"kind": "im_wake"})
    statements.clear()
    await writer.append_message({"role": "user", "content": "question"})
    expected = [
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": "answer"},
    ]
    await writer.save_history(expected)
    assert not any(
        "platform_message_history" in sql or "pg_advisory" in sql for sql in statements
    )
    assert (await store.read(conv.conversation_id)).messages == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["turn", "request", "tool"])
async def test_combined_finish_check_rejects_concurrent_duplicate_and_allows_retry(
    database, kind
):
    store = database.conversation_store
    conv = await store.create(umo="owner", platform_id="p")
    await store.append(
        conv.conversation_id,
        [
            {"type": "turn.started", "event_id": "turn", "payload": {}},
            {
                "type": "request.started",
                "event_id": "request",
                "payload": {"turn_id": "turn"},
            },
            {
                "type": "tool.started",
                "event_id": "tool",
                "payload": {
                    "turn_id": "turn",
                    "tool_name": "test",
                    "tool_call_id": "call",
                    "arguments": {},
                },
            },
        ],
    )
    key = {"turn": "turn_id", "request": "request_id", "tool": "execution_id"}[kind]
    drafts = [
        {
            "type": f"{kind}.finished",
            "event_id": f"finish-{i}",
            "payload": {key: kind, "status": "completed"},
        }
        for i in range(2)
    ]
    results = await asyncio.gather(
        *(store.append(conv.conversation_id, [draft]) for draft in drafts),
        return_exceptions=True,
    )
    assert sum(isinstance(result, ConversationConflictError) for result in results) == 1
    winner = next(
        i for i, result in enumerate(results) if not isinstance(result, Exception)
    )
    assert (await store.append(conv.conversation_id, [drafts[winner]])).replayed
    assert (
        len(await store.events(conv.conversation_id, event_type=f"{kind}.finished"))
        == 1
    )
