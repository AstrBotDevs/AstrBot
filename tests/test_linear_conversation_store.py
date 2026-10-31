"""Recovery and reclamation invariants for independent linear conversations."""

import json
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text

from astrbot.core.db.conversation import (
    ContextUnavailableError,
    ConversationConflictError,
)
from astrbot.core.db.po import ConversationEvent, ConversationV3
from astrbot.core.db.sqlite import SQLiteDatabase


@pytest_asyncio.fixture
async def database(tmp_path):
    db = SQLiteDatabase(str(tmp_path / "linear.db"))
    await db.initialize()
    yield db
    await db.engine.dispose()


@pytest.mark.asyncio
async def test_plugin_reclamation_preserves_user_versions_independent_fork_and_receipt(
    database,
):
    store = database.conversation_store
    conv = await store.create(umo="owner", platform_id="p")
    first = (
        await store.append(
            conv.conversation_id,
            [],
            history=[{"role": "user", "content": "original"}],
            origin="plugin",
        )
    )[0]
    plugin = (
        await store.append(
            conv.conversation_id,
            [],
            history=[{"role": "user", "content": "plugin memory"}],
            origin="plugin",
        )
    )[0]
    side = await store.create(
        umo="owner", platform_id="p", source_event_id=plugin.event_id
    )
    user = (
        await store.append(
            conv.conversation_id,
            [],
            history=[{"role": "user", "content": "user edit"}],
            origin="user",
        )
    )[0]
    latest = (
        await store.append(
            conv.conversation_id,
            [],
            history=[{"role": "user", "content": "new plugin"}],
            origin="plugin",
        )
    )[0]
    events = {e.event_id: e for e in await store.events(conv.conversation_id)}
    assert events[plugin.event_id].payload is None
    assert events[user.event_id].payload["origin"] == "user"
    assert events[latest.event_id].payload is not None
    assert await store.get_context_availability(
        conv.conversation_id,
        [
            first.event_id,
            plugin.event_id,
            user.event_id,
            latest.event_id,
            None,
            "absent",
            side.leaf_event_id,
        ],
    ) == {
        first.event_id: "available",
        plugin.event_id: "pruned",
        user.event_id: "available",
        latest.event_id: "available",
        None: "available",
        "absent": "missing",
        side.leaf_event_id: "forbidden",
    }
    async with database.get_db() as session:
        with pytest.raises(ContextUnavailableError):
            await store.project(session, conv, plugin.event_id)
        restored = await store.project(session, conv, user.event_id)
        assert restored.messages == [{"role": "user", "content": "user edit"}]
        assert (
            await session.execute(
                text(
                    "SELECT payload IS NULL FROM conversation_events WHERE event_id=:id"
                ),
                {"id": plugin.event_id},
            )
        ).scalar_one() == 1
    receipt = await store.append(
        conv.conversation_id,
        [
            {
                "event_id": plugin.event_id,
                "type": plugin.type,
                "payload": {"different": "body cannot be verified"},
            }
        ],
    )
    assert receipt[0].payload is None
    with pytest.raises(ConversationConflictError):
        await store.append(
            conv.conversation_id,
            [{"event_id": plugin.event_id, "type": "message.appended", "payload": {}}],
        )
    await store.delete(cid=conv.conversation_id)
    assert (await store.read(side.conversation_id)).messages == [
        {"role": "user", "content": "plugin memory"}
    ]


@pytest.mark.asyncio
async def test_unfinished_executions_protect_only_their_required_baseline(database):
    store = database.conversation_store
    conv = await store.create(
        umo="owner", platform_id="p", content=[{"role": "user", "content": "seed"}]
    )
    protected = (
        await store.append(conv.conversation_id, [], history=[], origin="plugin")
    )[0]
    await store.append(
        conv.conversation_id,
        [
            {
                "event_id": "turn",
                "type": "turn.started",
                "payload": {"base_leaf_event_id": protected.event_id},
            },
            {
                "event_id": "request",
                "type": "request.started",
                "payload": {
                    "turn_id": "turn",
                    "context_leaf_event_id": protected.event_id,
                },
            },
        ],
    )
    second = (
        await store.append(
            conv.conversation_id,
            [
                {
                    "type": "context.rebased",
                    "payload": {"reason": "reset", "origin": "plugin", "messages": []},
                }
            ],
        )
    )[0]
    third = (
        await store.append(
            conv.conversation_id,
            [
                {
                    "type": "context.rebased",
                    "payload": {"reason": "reset", "origin": "plugin", "messages": []},
                }
            ],
        )
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
async def test_select_historical_position_creates_two_user_snapshots(database):
    store = database.conversation_store
    conv = await store.create(umo="owner", platform_id="p")
    a, b = await store.append(
        conv.conversation_id,
        [
            {
                "type": "message.appended",
                "payload": {"message": {"role": "user", "content": "a"}},
            },
            {
                "type": "message.appended",
                "payload": {"message": {"role": "assistant", "content": "b"}},
            },
        ],
    )
    state = await store.read(conv.conversation_id)
    await store.select_branch(
        conv.conversation_id,
        a.event_id,
        expected_head=state.conversation.head_seq,
        expected_leaf=b.event_id,
    )
    versions = (await store.events(conv.conversation_id))[-2:]
    assert all(
        e.type == "context.rebased" and e.payload["origin"] == "user" for e in versions
    )
    assert [
        entry["message"]["content"] for entry in versions[0].payload["messages"]
    ] == ["a", "b"]
    assert [
        entry["message"]["content"] for entry in versions[1].payload["messages"]
    ] == ["a"]
    await store.append(
        conv.conversation_id,
        [
            {
                "type": "message.appended",
                "payload": {"message": {"role": "assistant", "content": "c"}},
            }
        ],
    )
    assert [
        m["content"] for m in (await store.read(conv.conversation_id)).messages
    ] == ["a", "c"]
    assert "parent_event_id" not in ConversationEvent.model_fields


@pytest.mark.asyncio
async def test_prune_failure_and_invalid_batch_roll_back_all_changes(database):
    store = database.conversation_store
    conv = await store.create(
        umo="owner", platform_id="p", content=[{"role": "user", "content": "seed"}]
    )
    first = (await store.append(conv.conversation_id, [], history=[], origin="plugin"))[
        0
    ]
    before = await store.events(conv.conversation_id)
    with pytest.raises(ValueError):
        await store.append(
            conv.conversation_id,
            [
                {
                    "type": "context.rebased",
                    "payload": {"reason": "reset", "origin": "plugin", "messages": []},
                },
                {
                    "type": "message.appended",
                    "payload": {"message": {"role": "_checkpoint"}},
                },
            ],
        )
    assert [e.model_dump() for e in await store.events(conv.conversation_id)] == [
        e.model_dump() for e in before
    ]
    assert (
        await store.get_context_availability(conv.conversation_id, [first.event_id])
    )[first.event_id] == "available"


@pytest.mark.asyncio
@pytest.mark.parametrize("broken", [False, True])
async def test_tree_schema_migration_preserves_every_position_and_cross_conversation_fork(
    database, broken
):
    stamp = datetime.now(timezone.utc).isoformat()
    async with database.get_db() as session:
        original = ConversationV3(
            conversation_id="original",
            platform_id="p",
            umo="owner",
            head_seq=4,
            leaf_event_id="b",
        )
        side = ConversationV3(
            conversation_id="side",
            platform_id="p",
            umo="owner",
            head_seq=0,
            leaf_event_id="d",
        )
        session.add_all([original, side])
        await session.flush()
        original_id = original.id
        await session.execute(text("DROP TABLE conversation_events"))
        await session.execute(
            text("""CREATE TABLE conversation_events (
            conversation_ref INTEGER NOT NULL, seq BIGINT NOT NULL,
            event_id VARCHAR NOT NULL UNIQUE, parent_event_id VARCHAR,
            type VARCHAR NOT NULL, version INTEGER NOT NULL, payload JSON NOT NULL,
            created_at DATETIME NOT NULL, PRIMARY KEY(conversation_ref,seq))""")
        )
        for seq, (event_id, parent, content) in enumerate(
            [
                ("a", None, "a"),
                ("b", "a", "b"),
                ("c", "b", "c"),
                ("d", "missing" if broken else "a", "d"),
            ],
            1,
        ):
            await session.execute(
                text("""INSERT INTO conversation_events VALUES
                (:owner,:seq,:id,:parent,'message.appended',1,:payload,:stamp)"""),
                {
                    "owner": original.id,
                    "seq": seq,
                    "id": event_id,
                    "parent": parent,
                    "payload": json.dumps(
                        {"message": {"role": "user", "content": content}}
                    ),
                    "stamp": stamp,
                },
            )
        await session.commit()
    if broken:
        with pytest.raises(ValueError, match="Broken context ancestry"):
            await database.initialize()
        async with database.get_db() as session:
            columns = {
                row[1]
                for row in (
                    await session.execute(
                        text("PRAGMA table_info(conversation_events)")
                    )
                ).all()
            }
            assert "parent_event_id" in columns
            assert (
                await session.execute(text("SELECT count(*) FROM conversation_events"))
            ).scalar_one() == 4
        return
    await database.initialize()
    store = database.conversation_store
    assert [m["content"] for m in (await store.read("original")).messages] == ["a", "b"]
    assert [m["content"] for m in (await store.read("side")).messages] == ["a", "d"]
    async with database.get_db() as session:
        conv = await session.get(ConversationV3, original_id)
        for event_id, expected in {
            "a": ["a"],
            "b": ["a", "b"],
            "c": ["a", "b", "c"],
            "d": ["a", "d"],
        }.items():
            assert [
                m["content"]
                for m in (await store.project(session, conv, event_id)).messages
            ] == expected
        columns = {
            row[1]
            for row in (
                await session.execute(text("PRAGMA table_info(conversation_events)"))
            ).all()
        }
        assert "parent_event_id" not in columns
    await store.delete(cid="original")
    assert [m["content"] for m in (await store.read("side")).messages] == ["a", "d"]


@pytest.mark.asyncio
@pytest.mark.parametrize("display_before", [False, True])
@pytest.mark.parametrize("role", ["user", "assistant"])
async def test_automatic_snapshot_keeps_exact_display_tip_forkable(
    database, display_before, role
):
    store = database.conversation_store
    conv = await store.create(
        umo="owner", platform_id="p", content=[{"role": "user", "content": "seed"}]
    )
    plugin = (
        await store.append(conv.conversation_id, [], history=[], origin="plugin")
    )[0]
    await store.append(
        conv.conversation_id,
        [
            {
                "event_id": "active-turn",
                "type": "turn.started",
                "payload": {"base_leaf_event_id": plugin.event_id},
            }
        ],
    )
    display_content = {"type": "user" if role == "user" else "bot", "message": []}
    if display_before:
        record = await database.insert_platform_message_history(
            "p", "session", display_content, turn_id="active-turn"
        )
    drafts = [
        {
            "type": "message.appended",
            "payload": {"message": {"role": "user", "content": str(i)}},
        }
        for i in range(255)
    ]
    drafts.extend(
        [
            {
                "event_id": "display-tip",
                "type": "message.appended",
                "payload": {
                    "turn_id": "active-turn",
                    "message": {"role": role, "content": "visible"},
                },
            },
            {
                "type": "plugin.test.audit",
                "payload": {
                    "description": "A non-context event separates the tip from its snapshot"
                },
            },
        ]
    )
    committed = await store.append(conv.conversation_id, drafts)
    snapshot = committed[-1]
    assert snapshot.type == "context.rebased"
    assert snapshot.payload["reason"] == "snapshot"
    assert snapshot.payload["source_event_id"] == "display-tip"
    assert (
        await store.get_context_availability(conv.conversation_id, [plugin.event_id])
    )[plugin.event_id] == "available"
    await store.append(
        conv.conversation_id,
        [
            {
                "type": "turn.finished",
                "payload": {"turn_id": "active-turn", "status": "completed"},
            }
        ],
    )
    assert (
        await store.get_context_availability(conv.conversation_id, [plugin.event_id])
    )[plugin.event_id] == "pruned"
    if not display_before:
        record = await database.insert_platform_message_history(
            "p", "session", display_content, turn_id="active-turn"
        )
    linked = await database.get_platform_message_history_by_id(record.id)
    assert linked.context_event_id == snapshot.event_id
    assert (
        await store.get_context_availability(
            conv.conversation_id, [linked.context_event_id]
        )
    )[linked.context_event_id] == "available"
    side = await store.create(
        umo="owner", platform_id="p", source_event_id=linked.context_event_id
    )
    assert (await store.read(side.conversation_id)).messages == (
        await store.read(conv.conversation_id)
    ).messages
