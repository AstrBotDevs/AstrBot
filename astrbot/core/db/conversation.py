"""Transactional event storage and legacy conversation projections."""

import json
import uuid
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import literal
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import col, delete, select, text, update

from astrbot.core.db.po import (
    ConversationEvent,
    ConversationRead,
    ConversationRevision,
    ConversationV2,
    ConversationV3,
    PlatformMessageHistory,
    WebChatThread,
)
from astrbot.core.sentinels import NOT_GIVEN

CONTEXT_TYPES = {"message.appended", "context.rebased"}
EVENT_TYPES = CONTEXT_TYPES | {
    "conversation.created",
    "conversation.updated",
    "turn.started",
    "turn.finished",
    "request.started",
    "request.finished",
    "tool.started",
    "tool.finished",
}
REBASE_REASONS = {"compaction", "reset", "legacy_replace", "migration", "snapshot"}


class ConversationConflictError(RuntimeError):
    """The conversation changed after a caller read its revision."""


def same_conversation_owner(source: str, target: str) -> bool:
    """Check session ownership for cross-conversation ancestry.

    Args:
        source: Source UMO resolved by the host.
        target: Target UMO resolved by the host.

    Returns:
        Whether the UMOs match or identify WebChat sessions of the same creator.
    """
    if source == target:
        return True
    left, right = source.split(":", 2), target.split(":", 2)
    if (
        len(left) != 3
        or len(right) != 3
        or left[0] != "webchat"
        or right[0] != "webchat"
    ):
        return False
    a, b = left[2].split("!"), right[2].split("!")
    return len(a) == len(b) == 3 and a[0] == b[0] == "webchat" and a[1] == b[1]


def persistent_messages(messages: list[dict]) -> list[dict]:
    """Project working messages while excluding temporary content.

    Args:
        messages: Legacy message dictionaries, including checkpoint markers.

    Returns:
        Detached dictionaries eligible for future model context.
    """
    result = []
    for original in messages:
        if original.get("_no_save") or original.get("role") == "_checkpoint":
            continue
        message = deepcopy(original)
        message.pop("_no_save", None)
        if isinstance(message.get("content"), list):
            message["content"] = [
                {k: v for k, v in part.items() if k != "_no_save"}
                if isinstance(part, dict)
                else part
                for part in message["content"]
                if not isinstance(part, dict) or not part.get("_no_save")
            ]
        result.append(message)
    return result


@dataclass
class ConversationSnapshot:
    """A detached branch projection and its write revision."""

    conversation: ConversationV3
    entries: list[dict] = field(default_factory=list)
    replay_count: int = 0
    replay_bytes: int = 0

    @property
    def messages(self) -> list[dict]:
        """Return a mutable copy without exposing stored payload objects."""
        return deepcopy([entry["message"] for entry in self.entries])


class ConversationStore:
    """Store shared conversation events using short SQLite write transactions."""

    def __init__(self, db):
        self.db = db

    async def migrate(self, *, session=None) -> None:
        """Atomically migrate legacy rows and WebChat links, then drop the old table.

        Args:
            session: Optional import transaction; the caller owns its commit.
        """
        owns_transaction = session is None
        async with (
            self.db.AsyncSessionLocal() if owns_transaction else nullcontext(session)
        ) as session:
            if owns_transaction:
                await session.execute(text("BEGIN IMMEDIATE"))
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
                            parent_event_id=conv.leaf_event_id,
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
                            entries.append(
                                {"id": event.event_id, "message": effective[0]}
                            )
                        if first_user is None and message.get("role") == "user":
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
                    parent_event_id=conv.leaf_event_id,
                    type="context.rebased",
                    created_at=old.updated_at,
                    payload={"reason": "migration", "messages": entries},
                )
                session.add(baseline)
                conv.leaf_event_id = conv.replay_from_event_id = baseline.event_id
                conv.updated_at = old.updated_at
                flag_modified(conv, "updated_at")
                session.add(conv)
                await session.flush()
                restored = await self.project(session, conv)
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

    async def create(
        self,
        *,
        umo: str,
        platform_id: str,
        content=None,
        title=None,
        persona_id=None,
        cid=None,
        created_at=None,
        updated_at=None,
        parent_event_id=None,
    ) -> ConversationV3:
        """Create a conversation, optionally inheriting an authorized branch.

        Args:
            umo: Owner session identity.
            platform_id: Platform instance.
            content: Optional initial legacy messages.
            title: Optional title.
            persona_id: Optional persona.
            cid: Optional caller-supplied public identity.
            created_at: Optional migration timestamp.
            updated_at: Optional migration timestamp.
            parent_event_id: Existing context node owned by the same UMO.

        Returns:
            Newly committed metadata.
        """
        async with self.db.get_db() as session:
            await session.execute(text("BEGIN IMMEDIATE"))
            baseline_id = None
            if parent_event_id:
                parent = (
                    await session.execute(
                        select(ConversationEvent).where(
                            ConversationEvent.event_id == parent_event_id
                        )
                    )
                ).scalar_one_or_none()
                owner = (
                    await session.get(ConversationV3, parent.conversation_ref)
                    if parent
                    else None
                )
                if (
                    not owner
                    or not same_conversation_owner(owner.umo, umo)
                    or parent.type not in CONTEXT_TYPES
                ):
                    raise ValueError("The parent must be an accessible context event")
                inherited = await self.project(session, owner, parent_event_id)
                baseline_id = inherited.conversation.replay_from_event_id
            conv = ConversationV3(
                conversation_id=cid or str(uuid.uuid4()),
                umo=umo,
                platform_id=platform_id,
                title=title,
                persona_id=persona_id,
                created_at=created_at or datetime.now(timezone.utc),
                updated_at=updated_at or created_at or datetime.now(timezone.utc),
                leaf_event_id=parent_event_id,
                replay_from_event_id=baseline_id,
                head_seq=1,
            )
            session.add(conv)
            await session.flush()
            payload = {
                "umo": umo,
                "platform_id": platform_id,
                "title": title,
                "persona_id": persona_id,
            }
            if parent_event_id:
                payload["forked_from_event_id"] = parent_event_id
            session.add(
                ConversationEvent(
                    conversation_ref=conv.id,
                    seq=1,
                    type="conversation.created",
                    payload=payload,
                )
            )
            if content:
                for message in content:
                    if message.get("role") != "_checkpoint" and persistent_messages(
                        [message]
                    ) != [message]:
                        conv.head_seq += 1
                        excluded = ConversationEvent(
                            conversation_ref=conv.id,
                            seq=conv.head_seq,
                            parent_event_id=conv.leaf_event_id,
                            type="message.appended",
                            payload={
                                "message": deepcopy(message),
                                "include_in_context": False,
                            },
                        )
                        session.add(excluded)
                        conv.leaf_event_id = excluded.event_id
                conv.head_seq += 1
                baseline = ConversationEvent(
                    conversation_ref=conv.id,
                    seq=conv.head_seq,
                    parent_event_id=conv.leaf_event_id,
                    type="context.rebased",
                    payload={
                        "reason": "migration",
                        "messages": [
                            {"id": str(uuid.uuid4()), "message": m}
                            for m in persistent_messages(content)
                        ],
                    },
                )
                session.add(baseline)
                conv.leaf_event_id = conv.replay_from_event_id = baseline.event_id
            conv.updated_at = updated_at or created_at or conv.updated_at
            flag_modified(conv, "updated_at")
            await session.commit()
            return conv

    async def project(
        self, session, conv: ConversationV3, leaf=NOT_GIVEN
    ) -> ConversationSnapshot:
        """Read only the selected ancestry, stopping at a self-contained rebase.

        Args:
            session: Active read or write transaction.
            conv: Metadata defining the selected branch.
            leaf: Optional alternate branch tip; None selects an empty branch.

        Returns:
            Detached effective entries and replay cost.

        Raises:
            ValueError: The branch is broken or uses an unsupported schema.
        """
        conv = ConversationV3(**conv.model_dump())
        if leaf is not NOT_GIVEN:
            conv.leaf_event_id = leaf
        snapshot = ConversationSnapshot(conv)
        conv.replay_from_event_id = None
        if conv.leaf_event_id is None:
            return snapshot
        events = ConversationEvent.__table__
        path = (
            select(
                events.c.event_id,
                events.c.parent_event_id,
                events.c.type,
                events.c.version,
                events.c.payload,
                literal(0).label("depth"),
            )
            .where(events.c.event_id == conv.leaf_event_id)
            .cte("context_path", recursive=True)
        )
        path = path.union_all(
            select(
                events.c.event_id,
                events.c.parent_event_id,
                events.c.type,
                events.c.version,
                events.c.payload,
                (path.c.depth + 1).label("depth"),
            )
            .join(path, events.c.event_id == path.c.parent_event_id)
            .where(path.c.type != "context.rebased")
        )
        stream = await session.stream(select(path).order_by(path.c.depth.desc()))
        previous = None
        async for row in stream.mappings():
            if row["version"] != 1 or row["type"] not in CONTEXT_TYPES:
                raise ValueError("Unsupported context event or version")
            if row["type"] == "context.rebased":
                snapshot.entries = deepcopy(row["payload"]["messages"])
                conv.replay_from_event_id = row["event_id"]
            else:
                if row["parent_event_id"] != previous:
                    raise ValueError("Broken context ancestry")
                effective = persistent_messages([row["payload"]["message"]])
                if row["payload"].get("include_in_context", True) and effective:
                    snapshot.entries.append(
                        {
                            "id": row["event_id"],
                            "message": effective[0],
                        }
                    )
            previous = row["event_id"]
            snapshot.replay_count += 1
            # Count only the tail: a large baseline must not trigger another snapshot.
            if row["type"] != "context.rebased":
                snapshot.replay_bytes += len(
                    json.dumps(row["payload"], ensure_ascii=False).encode()
                )
        if previous != conv.leaf_event_id:
            raise ValueError("Missing context leaf")
        return snapshot

    async def read(self, cid: str) -> ConversationSnapshot | None:
        """Read an initialized conversation by its public ID.

        Args:
            cid: Public conversation identity.

        Returns:
            Detached snapshot, or None when absent.
        """
        async with self.db.get_db() as session:
            conv = (
                await session.execute(
                    select(ConversationV3).where(ConversationV3.conversation_id == cid)
                )
            ).scalar_one_or_none()
            if conv:
                return await self.project(session, conv)
        return None

    async def read_result(
        self, session, conv: ConversationV3, include_history=True
    ) -> ConversationRead:
        """Read context and its revision into an explicit detached result.

        Args:
            session: Current transaction.
            conv: V3 metadata.
            include_history: Whether to project context.

        Returns:
            Legacy-compatible fields and the revision used to project them.
        """
        usage = (
            await session.execute(
                select(ConversationEvent.payload)
                .where(
                    ConversationEvent.conversation_ref == conv.id,
                    col(ConversationEvent.type).in_(
                        ["conversation.created", "conversation.updated"]
                    ),
                    ConversationEvent.payload["token_usage"].as_integer().is_not(None),
                )
                .order_by(ConversationEvent.seq.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return ConversationRead(
            inner_conversation_id=conv.id,
            conversation_id=conv.conversation_id,
            platform_id=conv.platform_id,
            user_id=conv.umo,
            title=conv.title,
            persona_id=conv.persona_id,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            token_usage=(usage or {}).get("token_usage", 0),
            revision=ConversationRevision(conv.head_seq, conv.leaf_event_id),
            content=(await self.project(session, conv)).messages
            if include_history
            else None,
        )

    async def append(
        self,
        cid: str,
        drafts: list[dict],
        *,
        expected_head=NOT_GIVEN,
        expected_leaf=NOT_GIVEN,
        history=None,
        reason="legacy_replace",
    ) -> list[ConversationEvent]:
        """Atomically validate and append a batch, optionally committing legacy history.

        Args:
            cid: Public conversation identity.
            drafts: Events with type, payload and optional stable event ID/parent.
            expected_head: Optional optimistic concurrency revision.
            expected_leaf: Optional expected selected branch.
            history: Optional complete legacy working history to reconcile.
            reason: Reason for a non-append history change.

        Returns:
            Committed events, including previously committed identical retries.

        Raises:
            ConversationConflictError: A stale revision or conflicting ID was supplied.
            ValueError: A payload, reference, or event type is invalid.
        """
        drafts = json.loads(json.dumps(drafts, allow_nan=False))
        async with self.db.get_db() as session:
            await session.execute(text("BEGIN IMMEDIATE"))
            conv = (
                await session.execute(
                    select(ConversationV3).where(ConversationV3.conversation_id == cid)
                )
            ).scalar_one_or_none()
            if conv is None:
                raise ValueError("Conversation not found")
            existing = []
            for draft in drafts:
                found = (
                    await session.execute(
                        select(ConversationEvent).where(
                            ConversationEvent.event_id == draft.get("event_id", "")
                        )
                    )
                ).scalar_one_or_none()
                if found:
                    if (
                        found.conversation_ref != conv.id
                        or found.type != draft["type"]
                        or found.payload != draft.get("payload", {})
                        or found.version != draft.get("version", 1)
                        or (
                            "parent_event_id" in draft
                            and found.parent_event_id != draft["parent_event_id"]
                        )
                    ):
                        raise ConversationConflictError(
                            "Event ID already has different content"
                        )
                    existing.append(found)
            if existing:
                if len(existing) != len(drafts) or history is not None:
                    raise ConversationConflictError(
                        "Cannot partially replay a committed batch"
                    )
                context_events = [
                    event for event in existing if event.type in CONTEXT_TYPES
                ]
                if context_events:
                    baseline = await session.get(
                        ConversationEvent,
                        (conv.id, max(event.seq for event in existing) + 1),
                    )
                    if (
                        baseline
                        and baseline.type == "context.rebased"
                        and baseline.payload.get("reason") == "snapshot"
                        and baseline.parent_event_id == context_events[-1].event_id
                    ):
                        existing.append(baseline)
                return existing
            if (expected_head is not NOT_GIVEN and conv.head_seq != expected_head) or (
                expected_leaf is not NOT_GIVEN and conv.leaf_event_id != expected_leaf
            ):
                raise ConversationConflictError(
                    "Conversation changed; reload before committing"
                )
            snapshot = None
            if history is not None:
                for message in history:
                    if message.get("role") != "_checkpoint" and persistent_messages(
                        [message]
                    ) != [message]:
                        drafts.append(
                            {
                                "type": "message.appended",
                                "payload": {
                                    "message": deepcopy(message),
                                    "include_in_context": False,
                                },
                            }
                        )
                history = persistent_messages(history)
                snapshot = await self.project(session, conv)
                before = snapshot.messages
                if history != before:
                    if len(history) >= len(before) and history[: len(before)] == before:
                        drafts.extend(
                            {"type": "message.appended", "payload": {"message": m}}
                            for m in history[len(before) :]
                        )
                    else:
                        drafts.append(
                            {
                                "type": "context.rebased",
                                "payload": {
                                    "reason": "reset" if not history else reason,
                                    "messages": [
                                        {"id": str(uuid.uuid4()), "message": m}
                                        for m in history
                                    ],
                                },
                            }
                        )
            committed = []
            for draft in drafts:
                kind = draft["type"]
                payload = draft.get("payload", {})
                if kind not in EVENT_TYPES and not kind.startswith("plugin."):
                    raise ValueError(f"Unknown event type: {kind}")
                if draft.get("version", 1) != 1 or not isinstance(payload, dict):
                    raise ValueError("Unsupported event version or payload")
                if kind == "conversation.created":
                    raise ValueError("Use create() to create a conversation")
                parent_id = (
                    draft.get("parent_event_id", conv.leaf_event_id)
                    if kind in CONTEXT_TYPES
                    else None
                )
                if (
                    kind not in CONTEXT_TYPES
                    and draft.get("parent_event_id") is not None
                ):
                    raise ValueError("Only context events have context parents")
                if parent_id:
                    parent = (
                        await session.execute(
                            select(ConversationEvent).where(
                                ConversationEvent.event_id == parent_id
                            )
                        )
                    ).scalar_one_or_none()
                    owner = (
                        await session.get(ConversationV3, parent.conversation_ref)
                        if parent
                        else None
                    )
                    if (
                        not owner
                        or not same_conversation_owner(owner.umo, conv.umo)
                        or parent.type not in CONTEXT_TYPES
                    ):
                        raise ValueError("Parent must be an accessible context event")
                if kind == "message.appended":
                    message = payload.get("message")
                    if not isinstance(message, dict) or not isinstance(
                        message.get("role"), str
                    ):
                        raise ValueError("A message requires a role")
                    if message["role"] == "_checkpoint":
                        raise ValueError("Checkpoint markers are not model messages")
                    if not isinstance(payload.get("include_in_context", True), bool):
                        raise ValueError("include_in_context must be boolean")
                elif kind == "context.rebased":
                    if payload.get("reason") not in REBASE_REASONS or not isinstance(
                        payload.get("messages"), list
                    ):
                        raise ValueError(
                            "A rebase requires a reason and complete messages"
                        )
                    ids = set()
                    for entry in payload["messages"]:
                        if (
                            not isinstance(entry, dict)
                            or not isinstance(entry.get("id"), str)
                            or entry["id"] in ids
                        ):
                            raise ValueError("Rebase message identities must be unique")
                        ids.add(entry["id"])
                        message = entry.get("message")
                        if (
                            not isinstance(message, dict)
                            or "role" not in message
                            or persistent_messages([message]) != [message]
                        ):
                            raise ValueError("Invalid or temporary rebase message")
                elif kind == "conversation.updated":
                    changes = payload.get("changes", {})
                    if set(changes) - {"title", "persona_id"}:
                        raise ValueError("Unsupported conversation metadata change")
                    for key, value in changes.items():
                        if value is not None and not isinstance(value, str):
                            raise ValueError("Metadata must be text or null")
                        setattr(conv, key, value)
                elif kind in {"turn.finished", "request.finished", "tool.finished"}:
                    if payload.get("status") not in {
                        "completed",
                        "failed",
                        "cancelled",
                    }:
                        raise ValueError("Invalid execution status")
                    key = {
                        "turn.finished": "turn_id",
                        "request.finished": "request_id",
                        "tool.finished": "execution_id",
                    }[kind]
                    start = (
                        await session.execute(
                            select(ConversationEvent).where(
                                ConversationEvent.event_id == payload.get(key, "")
                            )
                        )
                    ).scalar_one_or_none()
                    if (
                        not start
                        or start.conversation_ref != conv.id
                        or start.type != kind.replace("finished", "started")
                    ):
                        raise ValueError("Missing matching execution start")
                    if kind == "request.finished" and "usage" in payload:
                        usage = payload["usage"]
                        if not isinstance(usage, dict) or any(
                            type(value) is not int or value < 0
                            for value in usage.values()
                        ):
                            raise ValueError(
                                "Token usage must contain nonnegative integers"
                            )
                        if usage.get("cached_input_tokens", 0) > usage.get(
                            "input_tokens", 0
                        ):
                            raise ValueError(
                                "Cached input tokens are a subset of input tokens"
                            )
                    duplicate = (
                        await session.execute(
                            select(ConversationEvent.event_id)
                            .where(
                                ConversationEvent.conversation_ref == conv.id,
                                ConversationEvent.type == kind,
                                ConversationEvent.seq > start.seq,
                                ConversationEvent.payload[key].as_string()
                                == payload[key],
                            )
                            .limit(1)
                        )
                    ).first()
                    if duplicate:
                        raise ConversationConflictError("Execution already finished")
                elif kind in {"request.started", "tool.started"}:
                    turn = (
                        await session.execute(
                            select(ConversationEvent).where(
                                ConversationEvent.event_id == payload.get("turn_id", "")
                            )
                        )
                    ).scalar_one_or_none()
                    if (
                        not turn
                        or turn.conversation_ref != conv.id
                        or turn.type != "turn.started"
                    ):
                        raise ValueError("Missing parent turn")
                    if kind == "tool.started" and (
                        not isinstance(payload.get("tool_name"), str)
                        or not isinstance(payload.get("tool_call_id"), str)
                        or not isinstance(payload.get("arguments"), dict)
                    ):
                        raise ValueError(
                            "A tool execution requires a name, call ID and arguments"
                        )
                conv.head_seq += 1
                event = ConversationEvent(
                    conversation_ref=conv.id,
                    seq=conv.head_seq,
                    event_id=draft.get("event_id") or str(uuid.uuid4()),
                    parent_event_id=parent_id,
                    type=kind,
                    payload=payload,
                )
                session.add(event)
                await session.flush()
                if kind in CONTEXT_TYPES and payload.get("turn_id"):
                    role = (
                        payload["message"].get("role")
                        if kind == "message.appended"
                        else payload["messages"][-1]["message"].get("role")
                        if payload["messages"]
                        else None
                    )
                    if role in {"user", "assistant"}:
                        query = update(PlatformMessageHistory).where(
                            PlatformMessageHistory.turn_id == payload["turn_id"],
                            PlatformMessageHistory.content["type"].as_string()
                            == ("user" if role == "user" else "bot"),
                        )
                        if role == "user":
                            query = query.where(
                                PlatformMessageHistory.context_event_id.is_(None)
                            )
                        await session.execute(
                            query.values(context_event_id=event.event_id)
                        )
                committed.append(event)
                if kind in CONTEXT_TYPES:
                    conv.leaf_event_id = event.event_id
                    conv.replay_from_event_id = (
                        event.event_id if kind == "context.rebased" else None
                    )
            if committed:
                # Snapshots bound replay cost without changing model-visible messages.
                if any(e.type in CONTEXT_TYPES for e in committed):
                    snapshot = await self.project(session, conv)
                    conv.replay_from_event_id = (
                        snapshot.conversation.replay_from_event_id
                    )
                    if snapshot.replay_count > 256 or (
                        snapshot.replay_count > 1
                        and snapshot.replay_bytes > 4 * 1024 * 1024
                    ):
                        conv.head_seq += 1
                        baseline = ConversationEvent(
                            conversation_ref=conv.id,
                            seq=conv.head_seq,
                            type="context.rebased",
                            parent_event_id=conv.leaf_event_id,
                            payload={
                                "reason": "snapshot",
                                "messages": snapshot.entries,
                            },
                        )
                        session.add(baseline)
                        conv.leaf_event_id = conv.replay_from_event_id = (
                            baseline.event_id
                        )
                        committed.append(baseline)
                conv.updated_at = datetime.now(timezone.utc)
                session.add(conv)
            await session.commit()
            return committed

    async def events(
        self,
        cid: str,
        *,
        after_seq=0,
        before_seq=None,
        event_type=None,
        limit=100,
        max_bytes=4 * 1024 * 1024,
        descending=False,
    ) -> list[ConversationEvent]:
        """Read an indexed event page without loading the conversation projection.

        Args:
            cid: Public conversation identity.
            after_seq: Exclusive lower cursor.
            before_seq: Optional exclusive upper cursor.
            event_type: Optional exact event type.
            limit: Maximum events, from 1 to 1000.
            max_bytes: Soft byte budget; one oversized event is returned alone.
            descending: Whether to read newest first.

        Returns:
            Detached events; continue using the last returned seq.
        """
        if not 1 <= limit <= 1000 or max_bytes <= 0:
            raise ValueError("Invalid event page budget")
        async with self.db.get_db() as session:
            query = (
                select(ConversationEvent)
                .join(
                    ConversationV3,
                    ConversationV3.id == ConversationEvent.conversation_ref,
                )
                .where(
                    ConversationV3.conversation_id == cid,
                    ConversationEvent.seq > after_seq,
                )
            )
            if before_seq is not None:
                query = query.where(ConversationEvent.seq < before_seq)
            if event_type is not None:
                query = query.where(ConversationEvent.type == event_type)
            query = query.order_by(
                ConversationEvent.seq.desc()
                if descending
                else ConversationEvent.seq.asc()
            ).limit(limit)
            result, size = [], 0
            stream = await session.stream_scalars(query.execution_options(yield_per=1))
            try:
                async for event in stream:
                    weight = len(json.dumps(event.payload, ensure_ascii=False).encode())
                    if result and size + weight > max_bytes:
                        break
                    result.append(ConversationEvent(**deepcopy(event.model_dump())))
                    size += weight
            finally:
                await stream.close()
            return result

    async def select_branch(
        self, cid: str, leaf: str | None, *, expected_head, expected_leaf
    ) -> None:
        """Select an existing branch atomically without appending an event.

        Args:
            cid: Target conversation.
            leaf: Accessible context node or None.
            expected_head: Revision read by the caller.
            expected_leaf: Previously selected tip.
        """
        async with self.db.get_db() as session:
            await session.execute(text("BEGIN IMMEDIATE"))
            conv = (
                await session.execute(
                    select(ConversationV3).where(ConversationV3.conversation_id == cid)
                )
            ).scalar_one()
            if conv.head_seq != expected_head or conv.leaf_event_id != expected_leaf:
                raise ConversationConflictError(
                    "Conversation changed before branch selection"
                )
            if leaf:
                target = (
                    await session.execute(
                        select(ConversationEvent).where(
                            ConversationEvent.event_id == leaf
                        )
                    )
                ).scalar_one_or_none()
                owner = (
                    await session.get(ConversationV3, target.conversation_ref)
                    if target
                    else None
                )
                if (
                    not owner
                    or not same_conversation_owner(owner.umo, conv.umo)
                    or target.type not in CONTEXT_TYPES
                ):
                    raise ValueError("Branch is not accessible")
            snapshot = await self.project(session, conv, leaf)
            conv.leaf_event_id = leaf
            conv.replay_from_event_id = snapshot.conversation.replay_from_event_id
            conv.updated_at = datetime.now(timezone.utc)
            session.add(conv)
            await session.commit()

    async def rewind_webchat(
        self, cid: str, message_id: int, *, expected_head, expected_leaf, content=None
    ) -> PlatformMessageHistory:
        """Fork an edited/retried turn and atomically update its display projection.

        Args:
            cid: Conversation already authorized by the WebChat service.
            message_id: Active user or assistant display record.
            expected_head: Metadata revision read by the service.
            expected_leaf: Selected tip read by the service.
            content: Optional edited user display content.

        Returns:
            New user display record for the replacement turn.
        """
        async with self.db.get_db() as session:
            await session.execute(text("BEGIN IMMEDIATE"))
            conv = (
                await session.execute(
                    select(ConversationV3).where(ConversationV3.conversation_id == cid)
                )
            ).scalar_one()
            if conv.head_seq != expected_head or conv.leaf_event_id != expected_leaf:
                raise ConversationConflictError("Conversation changed before editing")
            target = await session.get(PlatformMessageHistory, message_id)
            if not target or not target.is_active or not target.turn_id:
                raise ValueError("Message is not an active linked turn")
            source = (
                await session.execute(
                    select(PlatformMessageHistory)
                    .where(
                        PlatformMessageHistory.turn_id == target.turn_id,
                        PlatformMessageHistory.platform_id == target.platform_id,
                        PlatformMessageHistory.user_id == target.user_id,
                        PlatformMessageHistory.content["type"].as_string() == "user",
                    )
                    .order_by(PlatformMessageHistory.id)
                    .limit(1)
                )
            ).scalar_one_or_none()
            turn = (
                await session.execute(
                    select(ConversationEvent).where(
                        ConversationEvent.event_id == target.turn_id,
                        ConversationEvent.type == "turn.started",
                        ConversationEvent.conversation_ref == conv.id,
                    )
                )
            ).scalar_one_or_none()
            if source is None or turn is None:
                raise ValueError("The original user turn is unavailable")
            parent = turn.payload.get("base_leaf_event_id")
            snapshot = await self.project(session, conv, parent)
            conv.leaf_event_id = parent
            conv.replay_from_event_id = snapshot.conversation.replay_from_event_id
            conv.updated_at = datetime.now(timezone.utc)
            # Old display records remain available to existing side threads.
            await session.execute(
                update(PlatformMessageHistory)
                .where(
                    PlatformMessageHistory.platform_id == source.platform_id,
                    PlatformMessageHistory.user_id == source.user_id,
                    PlatformMessageHistory.id >= source.id,
                )
                .values(is_active=False)
            )
            replacement = PlatformMessageHistory(
                platform_id=source.platform_id,
                user_id=source.user_id,
                sender_id=source.sender_id,
                sender_name=source.sender_name,
                content=deepcopy(content if content is not None else source.content),
                turn_id=str(uuid.uuid4()),
            )
            session.add_all([conv, replacement])
            await session.commit()
            return replacement

    async def delete(self, *, cid=None, umo=None) -> None:
        """Delete selected conversations only when no surviving branch references them.

        Args:
            cid: Optional single public identity.
            umo: Optional owner whose conversations are deleted together.

        Raises:
            ValueError: A surviving conversation depends on the selected history.
        """
        async with self.db.get_db() as session:
            await session.execute(text("BEGIN IMMEDIATE"))
            query = (
                select(ConversationV3.id).where(ConversationV3.conversation_id == cid)
                if cid
                else select(ConversationV3.id).where(ConversationV3.umo == umo)
            )
            ids = list((await session.execute(query)).scalars())
            if ids:
                owned = select(ConversationEvent.event_id).where(
                    col(ConversationEvent.conversation_ref).in_(ids)
                )
                child = (
                    await session.execute(
                        select(ConversationEvent.event_id)
                        .where(
                            ~col(ConversationEvent.conversation_ref).in_(ids),
                            col(ConversationEvent.parent_event_id).in_(owned),
                        )
                        .limit(1)
                    )
                ).first()
                leaf = (
                    await session.execute(
                        select(ConversationV3.id)
                        .where(
                            ~col(ConversationV3.id).in_(ids),
                            col(ConversationV3.leaf_event_id).in_(owned),
                        )
                        .limit(1)
                    )
                ).first()
                if child or leaf:
                    raise ValueError("Conversation is referenced by another branch")
                await session.execute(
                    delete(ConversationEvent).where(
                        col(ConversationEvent.conversation_ref).in_(ids)
                    )
                )
                await session.execute(
                    delete(ConversationV3).where(col(ConversationV3.id).in_(ids))
                )
            await session.commit()
