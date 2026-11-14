"""Recovery and reclamation invariants for independent linear conversations."""

import pytest


@pytest.mark.asyncio
async def test_unfinished_executions_protect_only_their_required_baseline(database):
    store = database.conversation_store
    conv = await store.create(
        umo="owner", platform_id="p", content=[{"role": "user", "content": "seed"}]
    )
    protected = (
        (
            await store.append(conv.conversation_id, [], history=[], origin="plugin")
        ).events
    )[0]
    await store.append(
        conv.conversation_id,
        [
            {
                "event_id": "message",
                "type": "message.appended",
                "payload": {"message": {"role": "user", "content": "active input"}},
            },
            {
                "event_id": "turn",
                "type": "turn.started",
                "payload": {"base_leaf_event_id": "message"},
            },
            {
                "event_id": "request",
                "type": "request.started",
                "payload": {
                    "turn_id": "turn",
                    "context_leaf_event_id": "message",
                },
            },
        ],
    )
    second = (
        (
            await store.append(
                conv.conversation_id,
                [
                    {
                        "type": "context.rebased",
                        "payload": {
                            "reason": "reset",
                            "origin": "plugin",
                            "messages": [],
                        },
                    }
                ],
            )
        ).events
    )[0]
    third = (
        (
            await store.append(
                conv.conversation_id,
                [
                    {
                        "type": "context.rebased",
                        "payload": {
                            "reason": "reset",
                            "origin": "plugin",
                            "messages": [],
                        },
                    }
                ],
            )
        ).events
    )[0]
    assert await store.get_context_availability(
        conv.conversation_id, [protected.event_id, second.event_id, third.event_id]
    ) == {
        protected.event_id: "available",
        second.event_id: "pruned",
        third.event_id: "available",
    }
    await store.append(
        conv.conversation_id,
        [
            {
                "type": "turn.finished",
                "payload": {"turn_id": "turn", "status": "completed"},
            }
        ],
    )
    assert (
        await store.get_context_availability(conv.conversation_id, [protected.event_id])
    )[protected.event_id] == "available"
    await store.append(
        conv.conversation_id,
        [
            {
                "type": "request.finished",
                "payload": {"request_id": "request", "status": "completed"},
            }
        ],
    )
    assert (
        await store.get_context_availability(conv.conversation_id, [protected.event_id])
    )[protected.event_id] == "pruned"
    assert (await store.read(conv.conversation_id)).messages == []


@pytest.mark.asyncio
async def test_context_read_survives_concurrent_baseline_reclamation(
    temp_db, monkeypatch
):
    """Metadata and payloads must come from one view, even if a writer prunes."""
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql import Select

    from astrbot.core.db.po import ConversationV3

    await temp_db.initialize()
    store = temp_db.conversation_store
    conv = await store.create(umo="owner", platform_id="p")
    original = [{"role": "user", "content": "before"}]
    replacement = [{"role": "user", "content": "after"}]
    await store.append(conv.conversation_id, [], history=original, origin="plugin")
    execute = AsyncSession.execute
    replaced = False

    async def interleave(session, statement, *args, **kwargs):
        nonlocal replaced
        result = await execute(session, statement, *args, **kwargs)
        if (
            not replaced
            and isinstance(statement, Select)
            and any(
                column.get("entity") is ConversationV3
                for column in statement.column_descriptions
            )
        ):
            replaced = True
            await store.append(
                conv.conversation_id, [], history=replacement, origin="plugin"
            )
        return result

    with monkeypatch.context() as patch:
        patch.setattr(AsyncSession, "execute", interleave)
        observed = await store.read(conv.conversation_id)
    assert replaced and observed.messages == original
    assert (await store.read(conv.conversation_id)).messages == replacement
