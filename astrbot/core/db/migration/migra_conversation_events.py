"""One-time conversion of legacy conversation histories and their display links."""

import json
import uuid
from contextlib import nullcontext
from copy import deepcopy
from datetime import datetime, timezone

from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select, text, update

from astrbot.core.db.conversation import (
    CONTEXT_TYPES,
    ConversationStore,
    persistent_messages,
    same_conversation_owner,
)
from astrbot.core.db.po import (
    ConversationEvent,
    ConversationV2,
    ConversationV3,
    PlatformMessageHistory,
    WebChatThread,
)


def linearize_legacy_events(
    conversations: list[dict], events: list[dict]
) -> tuple[list[dict], list[dict]]:
    """Convert tree histories into independent linear segments without losing positions.

    Args:
        conversations: Legacy V3 metadata dictionaries.
        events: Legacy V3 events containing parent_event_id.

    Returns:
        Detached metadata and events, with original event identities preserved.

    Raises:
        ValueError: An ancestor is missing, cyclic, or owned by another user.
    """
    conversations, events = deepcopy(conversations), deepcopy(events)
    by_id = {event["event_id"]: event for event in events}
    owners = {conv["id"]: conv for conv in conversations}
    grouped = {conv["id"]: [] for conv in conversations}
    for event in events:
        if event["conversation_ref"] not in grouped:
            raise ValueError("Event owner is missing during linear migration")
        grouped[event["conversation_ref"]].append(event)
    result = []
    # Complete ancestry reconstruction is confined to one-time migration. Normal
    # requests use the indexed baseline and tail instead.
    for conv in conversations:
        sequence, last, baseline = 0, None, None
        current = conv.get("leaf_event_id")
        pending = sorted(grouped[conv["id"]], key=lambda row: row["seq"])
        pending.append({"type": "_selected_leaf", "event_id": None, "payload": {}})
        for old in pending:
            kind = old["type"]
            sources = []
            if kind == "message.appended" and old.get("parent_event_id") != last:
                sources.append(old.get("parent_event_id"))
            elif kind == "turn.started":
                source = old["payload"].get("base_leaf_event_id")
                source_event = by_id.get(source)
                if source is not None and source_event is None:
                    raise ValueError("Turn base is missing during linear migration")
                if source_event and source_event["conversation_ref"] != conv["id"]:
                    sources.append(source)
            elif kind == "_selected_leaf" and current != last:
                sources.append(current)
            for source in sources:
                path, seen, cursor = [], set(), source
                while cursor is not None:
                    if cursor in seen or cursor not in by_id:
                        raise ValueError(
                            "Broken context ancestry during linear migration"
                        )
                    seen.add(cursor)
                    ancestor = by_id[cursor]
                    owner = owners.get(ancestor["conversation_ref"])
                    if (
                        not owner
                        or not same_conversation_owner(owner["umo"], conv["umo"])
                        or ancestor["type"] not in CONTEXT_TYPES
                    ):
                        raise ValueError(
                            "Inaccessible context ancestor during linear migration"
                        )
                    if ancestor["version"] != 1 or ancestor["payload"] is None:
                        raise ValueError(
                            "Unsupported legacy context during linear migration"
                        )
                    path.append(ancestor)
                    if ancestor["type"] == "context.rebased":
                        break
                    cursor = ancestor.get("parent_event_id")
                entries = []
                for ancestor in reversed(path):
                    if ancestor["type"] == "context.rebased":
                        entries = deepcopy(ancestor["payload"]["messages"])
                    else:
                        effective = persistent_messages(
                            [ancestor["payload"]["message"]]
                        )
                        if (
                            ancestor["payload"].get("include_in_context", True)
                            and effective
                        ):
                            entries.append(
                                {"id": ancestor["event_id"], "message": effective[0]}
                            )
                sequence += 1
                baseline = last = str(uuid.uuid4())
                result.append(
                    {
                        "conversation_ref": conv["id"],
                        "seq": sequence,
                        "event_id": baseline,
                        "replay_from_event_id": baseline,
                        "type": "context.rebased",
                        "version": 1,
                        "payload": {
                            "reason": "migration",
                            "origin": "system",
                            "source_event_id": source,
                            "messages": entries,
                        },
                        "created_at": old.get("created_at")
                        or conv.get("updated_at")
                        or datetime.now(timezone.utc),
                    }
                )
                if kind == "turn.started":
                    old["payload"]["base_leaf_event_id"] = baseline
            if kind == "_selected_leaf":
                continue
            sequence += 1
            event = {
                key: value for key, value in old.items() if key != "parent_event_id"
            }
            event["seq"] = sequence
            if kind == "context.rebased":
                baseline = event["event_id"]
                event["payload"].setdefault("origin", "unknown")
            event["replay_from_event_id"] = baseline if kind in CONTEXT_TYPES else None
            if kind in CONTEXT_TYPES:
                last = event["event_id"]
            result.append(event)
        conv["head_seq"] = sequence
        conv["leaf_event_id"] = last
        conv["replay_from_event_id"] = baseline
    return conversations, result


async def migrate_conversations(store: ConversationStore, *, session=None) -> None:
    """Atomically migrate legacy rows and WebChat links, then drop the old table.

    Args:
        store: Runtime store used to verify migrated context before committing.
        session: Optional import transaction; the caller owns its commit.
    """
    owns_transaction = session is None
    async with (
        store.db.AsyncSessionLocal() if owns_transaction else nullcontext(session)
    ) as session:
        if owns_transaction:
            await session.execute(text("BEGIN IMMEDIATE"))
        columns = {
            row[1]
            for row in (
                await session.execute(text("PRAGMA table_info(conversation_events)"))
            ).all()
        }
        if "parent_event_id" in columns:
            old_conversations = [
                dict(row)
                for row in (
                    await session.execute(text("SELECT * FROM conversations_v3"))
                ).mappings()
            ]
            old_events = [
                dict(row)
                for row in (
                    await session.execute(text("SELECT * FROM conversation_events"))
                ).mappings()
            ]
            for event in old_events:
                event["payload"] = (
                    json.loads(event["payload"])
                    if isinstance(event["payload"], str)
                    else event["payload"]
                )
            migrated_conversations, migrated_events = linearize_legacy_events(
                old_conversations, old_events
            )
            await session.execute(
                text("""CREATE TABLE conversation_events_linear (
                conversation_ref INTEGER NOT NULL REFERENCES conversations_v3(id),
                seq BIGINT NOT NULL CHECK(seq > 0), event_id VARCHAR NOT NULL UNIQUE,
                replay_from_event_id VARCHAR, type VARCHAR NOT NULL,
                version INTEGER NOT NULL CHECK(version > 0), payload JSON,
                created_at DATETIME NOT NULL, PRIMARY KEY(conversation_ref, seq))""")
            )
            if migrated_events:
                await session.execute(
                    text("""INSERT INTO conversation_events_linear
                    (conversation_ref,seq,event_id,replay_from_event_id,type,version,payload,created_at)
                    VALUES (:conversation_ref,:seq,:event_id,:replay_from_event_id,:type,:version,:payload,:created_at)"""),
                    [
                        {
                            **event,
                            "payload": json.dumps(event["payload"], ensure_ascii=False)
                            if event["payload"] is not None
                            else None,
                        }
                        for event in migrated_events
                    ],
                )
            await session.execute(text("DROP TABLE conversation_events"))
            await session.execute(
                text(
                    "ALTER TABLE conversation_events_linear RENAME TO conversation_events"
                )
            )
            await session.execute(
                text(
                    "CREATE INDEX ix_conversation_events_type_seq ON conversation_events(conversation_ref,type,seq)"
                )
            )
            await session.execute(
                text(
                    "CREATE INDEX ix_conversation_events_baseline ON conversation_events(replay_from_event_id)"
                )
            )
            for conv in migrated_conversations:
                await session.execute(
                    text("""UPDATE conversations_v3 SET head_seq=:head_seq,
                    leaf_event_id=:leaf_event_id,replay_from_event_id=:replay_from_event_id WHERE id=:id"""),
                    conv,
                )
        # Partial indexes contain only live plugin baselines and lifecycle
        # references, so cleanup need not inspect historical event payloads.
        await session.execute(
            text("""CREATE INDEX IF NOT EXISTS ix_context_plugin_live
            ON conversation_events(conversation_ref,seq)
            WHERE type='context.rebased' AND json_extract(payload,'$.origin')='plugin'
                AND payload IS NOT NULL""")
        )
        await session.execute(
            text("""CREATE INDEX IF NOT EXISTS ix_context_snapshot_source
            ON conversation_events(conversation_ref,json_extract(payload,'$.source_event_id'))
            WHERE type='context.rebased' AND json_extract(payload,'$.reason')='snapshot'
                AND json_extract(payload,'$.origin')='system'""")
        )
        for kind, field_name in [
            ("turn.started", "base_leaf_event_id"),
            ("request.started", "context_leaf_event_id"),
            ("turn.finished", "turn_id"),
            ("request.finished", "request_id"),
        ]:
            index_name = "ix_context_" + kind.replace(".", "_")
            await session.execute(
                text(f"""CREATE INDEX IF NOT EXISTS {index_name}
                ON conversation_events(conversation_ref,json_extract(payload,'$.{field_name}'))
                WHERE type='{kind}'""")
            )
        exists = (
            await session.execute(
                text(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='conversations'"
                )
            )
        ).first()
        if not exists:
            if owns_transaction:
                await session.commit()
            return
        columns = {
            r[1]
            for r in (
                await session.execute(text("PRAGMA table_info(conversations)"))
            ).all()
        }
        if "token_usage" not in columns:
            await session.execute(
                text(
                    "ALTER TABLE conversations ADD COLUMN token_usage INTEGER NOT NULL DEFAULT 0"
                )
            )
        rows = await session.stream_scalars(
            select(ConversationV2)
            .order_by(ConversationV2.inner_conversation_id)
            .execution_options(yield_per=32)
        )
        async for old in rows:
            if (
                await session.execute(
                    select(ConversationV3.id).where(
                        ConversationV3.conversation_id == old.conversation_id
                    )
                )
            ).first():
                raise ValueError(
                    "Both V2 and V3 contain this conversation; refusing an ambiguous migration"
                )
            conv = ConversationV3(
                conversation_id=old.conversation_id,
                platform_id=old.platform_id,
                umo=old.user_id,
                title=old.title,
                persona_id=old.persona_id,
                created_at=old.created_at,
                updated_at=old.updated_at,
                head_seq=1,
            )
            session.add(conv)
            await session.flush()
            session.add(
                ConversationEvent(
                    conversation_ref=conv.id,
                    seq=1,
                    type="conversation.created",
                    created_at=old.created_at,
                    payload={
                        "platform_id": old.platform_id,
                        "umo": old.user_id,
                        "title": old.title,
                        "persona_id": old.persona_id,
                        "token_usage": old.token_usage,
                    },
                )
            )
            pending = []
            groups = []
            for message in old.content or []:
                if message.get("role") == "_checkpoint":
                    marker = message.get("content", {})
                    groups.append(
                        (
                            pending,
                            marker.get("id") if isinstance(marker, dict) else None,
                        )
                    )
                    pending = []
                else:
                    pending.append(message)
            if pending:
                groups.append((pending, None))
            entries = []
            for messages, checkpoint in groups:
                turn_id = str(uuid.uuid4())
                conv.head_seq += 1
                session.add(
                    ConversationEvent(
                        conversation_ref=conv.id,
                        seq=conv.head_seq,
                        event_id=turn_id,
                        type="turn.started",
                        created_at=old.created_at,
                        payload={
                            "trigger": {"kind": "migration"},
                            "base_leaf_event_id": conv.leaf_event_id,
                        },
                    )
                )
                first_user = None
                for message in messages:
                    effective = persistent_messages([message])
                    conv.head_seq += 1
                    event = ConversationEvent(
                        conversation_ref=conv.id,
                        seq=conv.head_seq,
                        replay_from_event_id=conv.replay_from_event_id,
                        type="message.appended",
                        created_at=old.created_at,
                        payload={
                            "turn_id": turn_id,
                            "message": message,
                            "include_in_context": bool(effective),
                        },
                    )
                    session.add(event)
                    conv.leaf_event_id = event.event_id
                    if effective:
                        entries.append({"id": event.event_id, "message": effective[0]})
                    if (
                        first_user is None
                        and effective
                        and message.get("role") == "user"
                    ):
                        first_user = event.event_id
                if checkpoint:
                    # Copied side histories may reuse checkpoint IDs. Scope by display session.
                    display_id = old.user_id.rsplit("!", 1)[-1]
                    records = (
                        (
                            await session.execute(
                                select(PlatformMessageHistory).where(
                                    PlatformMessageHistory.turn_id == checkpoint,
                                    PlatformMessageHistory.user_id == display_id,
                                )
                            )
                        )
                        .scalars()
                        .all()
                    )
                    for record in records:
                        record.turn_id = turn_id
                        record.context_event_id = (
                            first_user
                            if record.content.get("type") == "user"
                            else conv.leaf_event_id
                        )
                        session.add(record)
                        if record.content.get("type") == "bot":
                            await session.execute(
                                update(WebChatThread)
                                .where(WebChatThread.parent_message_id == record.id)
                                .values(base_event_id=conv.leaf_event_id)
                            )
                conv.head_seq += 1
                session.add(
                    ConversationEvent(
                        conversation_ref=conv.id,
                        seq=conv.head_seq,
                        type="turn.finished",
                        created_at=old.updated_at,
                        payload={
                            "turn_id": turn_id,
                            "status": "completed",
                            "migrated": True,
                        },
                    )
                )
            conv.head_seq += 1
            baseline = ConversationEvent(
                conversation_ref=conv.id,
                seq=conv.head_seq,
                replay_from_event_id=conv.replay_from_event_id,
                type="context.rebased",
                created_at=old.updated_at,
                payload={
                    "reason": "migration",
                    "origin": "system",
                    "messages": entries,
                },
            )
            baseline.replay_from_event_id = baseline.event_id
            session.add(baseline)
            conv.leaf_event_id = conv.replay_from_event_id = baseline.event_id
            conv.updated_at = old.updated_at
            flag_modified(conv, "updated_at")
            session.add(conv)
            await session.flush()
            restored = await store.project(session, conv)
            expected = persistent_messages(
                [m for m in old.content or [] if m.get("role") != "_checkpoint"]
            )
            if restored.messages != expected:
                raise ValueError("Conversation migration verification failed")
        await rows.close()
        await session.flush()
        await session.execute(text("DROP TABLE conversations"))
        if owns_transaction:
            await session.commit()
