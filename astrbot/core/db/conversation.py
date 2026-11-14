"""Transactional event storage and legacy conversation projections."""

import hashlib
import json
import uuid
from collections import Counter, defaultdict, deque
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import insert, literal
from sqlalchemy.orm import aliased
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import col, delete, func, select, text, update

from astrbot.core.db.po import (
    ConversationEvent,
    ConversationRead,
    ConversationRevision,
    ConversationV3,
    PlatformMessageHistory,
)
from astrbot.core.db.webchat_projection import project_webchat_event_links
from astrbot.core.sentinels import NOT_GIVEN
from astrbot.core.utils.event_id import new_event_id

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
EVENT_INSERT_BATCH_ROWS = 100
EVENT_INSERT_BATCH_BYTES = 4 * 1024 * 1024


class ContextUnavailableError(ValueError):
    """The exact historical context has been reclaimed."""


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


def persistent_messages(messages: list[dict], *, detach: bool = True) -> list[dict]:
    """Project working messages while excluding temporary content.

    Args:
        messages: Working message dictionaries with optional temporary content.
        detach: Copy the projected messages. When false, the result may share
            data with the input and is only safe for immediate read-only use.

    Returns:
        Dictionaries eligible for future model context.

    Raises:
        ValueError: A message has an unsupported role.
    """
    result = []
    for message in messages:
        if message.get("role") not in ("system", "user", "assistant", "tool"):
            raise ValueError("Unsupported message role")
        if message.get("_no_save"):
            continue
        content = message.get("content")
        if isinstance(content, list) and any(
            isinstance(part, dict) and "_no_save" in part for part in content
        ):
            message = {
                **message,
                "content": [
                    {k: v for k, v in part.items() if k != "_no_save"}
                    if isinstance(part, dict) and "_no_save" in part
                    else part
                    for part in content
                    if not isinstance(part, dict) or not part.get("_no_save")
                ],
            }
        if "_no_save" in message:
            message = {k: v for k, v in message.items() if k != "_no_save"}
        result.append(deepcopy(message) if detach else message)
    return result


def persistent_entries(entries: list[dict]) -> list[dict]:
    """Project raw baseline entries without changing their message identities.

    Args:
        entries: Stored messages, including runtime exclusion markers.

    Returns:
        Detached entries with temporary messages and parts filtered out.
    """
    return [
        {"id": entry["id"], "message": message}
        for entry in entries
        for message in persistent_messages([entry["message"]])
    ]


def reconcile_history(
    entries: list[dict],
    history: list[dict],
    *,
    reason: str = "legacy_replace",
    origin: str = "unknown",
    turn_id: str | None = None,
    temporary_counts: Counter[str] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Convert a working history into context events while retaining message IDs.

    Args:
        entries: Previous context entries with stable message identities.
        history: Complete working messages, including temporary content.
        reason: Reason for replacing existing context.
        origin: Host-attributed source of the change.
        turn_id: Owning turn, if the change belongs to an execution.
        temporary_counts: Optional execution-local counts, updated to avoid
            recording the same temporary content at every staging boundary.

    Returns:
        Context entries and the events needed to reach them. Unchanged entries
        retain their identities; new message bodies are detached from history.

    Raises:
        ValueError: A message has an unsupported role.
    """
    entries = list(entries)
    drafts = []
    known_temporary = temporary_counts if temporary_counts is not None else Counter()
    projected = []
    raw_history = []
    current_temporary = Counter()
    raw_prefix_changed = False
    for message in history:
        effective = persistent_messages([message], detach=False)
        raw_history.append((message, effective[0] if effective else None, False))
        projected.extend(effective)
        if effective == [message]:
            continue
        fingerprint = hashlib.sha256(
            json.dumps(message, sort_keys=True).encode()
        ).hexdigest()
        current_temporary[fingerprint] += 1
        if current_temporary[fingerprint] <= known_temporary[fingerprint]:
            continue
        if effective:
            # A newly changed temporary part on an existing message requires a
            # replacement, not an append that would duplicate its visible part.
            raw_prefix_changed |= len(projected) <= len(entries)
            continue
        raw_history[-1] = (message, None, True)
    # The projection can share data with the plugin until it is staged.
    previous_count = len(entries)
    if (
        not raw_prefix_changed
        and len(projected) >= previous_count
        and all(
            entry["message"] == message for entry, message in zip(entries, projected)
        )
    ):
        position = 0
        for original, message, new_temporary in raw_history:
            if message is not None:
                position += 1
                if position <= previous_count:
                    continue
            elif not new_temporary:
                continue
            identity = new_event_id()
            drafts.append(
                {
                    "event_id": identity,
                    "type": "message.appended",
                    "payload": {
                        "turn_id": turn_id,
                        "message": deepcopy(original),
                    },
                }
            )
            if message is not None:
                entries.append({"id": identity, "message": deepcopy(message)})
    else:
        identity = new_event_id()
        retained_ids = defaultdict(deque)
        for entry in entries:
            retained_ids[json.dumps(entry["message"], sort_keys=True)].append(
                entry["id"]
            )
        entries = []
        raw_entries = []
        for original, message, _ in raw_history:
            matches = (
                retained_ids[json.dumps(message, sort_keys=True)]
                if message is not None
                else None
            )
            message_id = matches.popleft() if matches else new_event_id()
            raw_entries.append({"id": message_id, "message": deepcopy(original)})
            if message is not None:
                entries.append({"id": message_id, "message": deepcopy(message)})
        # A rebase already contains the raw temporary messages; do not also
        # write them as separate message events.
        drafts = [
            {
                "event_id": identity,
                "type": "context.rebased",
                "payload": {
                    "reason": "reset" if not projected else reason,
                    "origin": origin,
                    "turn_id": turn_id,
                    "messages": raw_entries,
                },
            }
        ]
    known_temporary |= current_temporary
    return entries, drafts


@dataclass
class ConversationSnapshot:
    """A detached branch projection and its write revision."""

    conversation: ConversationV3
    revision: ConversationRevision
    entries: list[dict] = field(default_factory=list)
    replay_count: int = 0
    context_seq: int = 0

    @property
    def messages(self) -> list[dict]:
        """Return a mutable copy without exposing stored payload objects."""
        return deepcopy([entry["message"] for entry in self.entries])


@dataclass
class ConversationAppendResult:
    """Acknowledged events and whether they came from an idempotent retry."""

    events: list[ConversationEvent]
    replayed: bool = False


def conversation_revision_columns(owner=ConversationV3.id):
    """Build indexed revision expressions for a metadata or batch query.

    Args:
        owner: SQL expression identifying the owning conversation row.

    Returns:
        Labeled scalar expressions for the event head and latest context identity.
    """
    head = (
        select(ConversationEvent.seq)
        .where(ConversationEvent.conversation_ref == owner)
        .order_by(ConversationEvent.seq.desc())
        .limit(1)
        .correlate_except(ConversationEvent)
        .scalar_subquery()
    )
    leaf = (
        select(ConversationEvent.event_id)
        .where(
            ConversationEvent.conversation_ref == owner,
            text("type IN ('message.appended', 'context.rebased')"),
        )
        .order_by(ConversationEvent.seq.desc())
        .limit(1)
        .correlate_except(ConversationEvent)
        .scalar_subquery()
    )
    return func.coalesce(head, 0).label("head_seq"), leaf.label("leaf_event_id")


class ConversationStore:
    """Store shared conversation events using short SQLite write transactions."""

    def __init__(self, db):
        self.db = db

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
        source_event_id=None,
    ) -> ConversationV3:
        """Create a conversation with an independent optional context snapshot.

        Args:
            umo: Owner session identity.
            platform_id: Platform instance.
            content: Optional initial legacy messages.
            title: Optional title.
            persona_id: Optional persona.
            cid: Optional public identity.
            created_at: Optional migration timestamp.
            updated_at: Optional migration timestamp.
            source_event_id: Authorized historical position to copy.

        Returns:
            Newly committed metadata.
        """
        async with self.db.get_db() as session:
            await session.execute(text("BEGIN IMMEDIATE"))
            inherited = None
            if source_event_id:
                source = (
                    await session.execute(
                        select(ConversationEvent).where(
                            ConversationEvent.event_id == source_event_id
                        )
                    )
                ).scalar_one_or_none()
                owner = (
                    await session.get(ConversationV3, source.conversation_ref)
                    if source
                    else None
                )
                if (
                    not owner
                    or not same_conversation_owner(owner.umo, umo)
                    or source.type not in CONTEXT_TYPES
                ):
                    raise ValueError("The source must be an accessible context event")
                if content is not None:
                    raise ValueError(
                        "Specify initial content or a source event, not both"
                    )
                inherited = await self.project(session, owner, source_event_id)
            conv = ConversationV3(
                conversation_id=cid or str(uuid.uuid4()),
                umo=umo,
                platform_id=platform_id,
                title=title,
                persona_id=persona_id,
                created_at=created_at or datetime.now(timezone.utc),
                updated_at=updated_at or created_at or datetime.now(timezone.utc),
            )
            session.add(conv)
            await session.flush()
            payload = {
                "umo": umo,
                "platform_id": platform_id,
                "title": title,
                "persona_id": persona_id,
            }
            if source_event_id:
                payload["forked_from_event_id"] = source_event_id
            session.add(
                ConversationEvent(
                    conversation_ref=conv.id,
                    seq=1,
                    type="conversation.created",
                    payload=payload,
                )
            )
            if content is not None or inherited is not None:
                # Validate roles, but store the original body only once.
                persistent_messages(content or [], detach=False)
                baseline = ConversationEvent(
                    conversation_ref=conv.id,
                    seq=2,
                    type="context.rebased",
                    payload={
                        "reason": "snapshot" if inherited is not None else "migration",
                        "origin": "user" if inherited is not None else "system",
                        "messages": inherited.entries
                        if inherited is not None
                        else [
                            {"id": new_event_id(), "message": m}
                            for m in deepcopy(content or [])
                        ],
                        **(
                            {"source_event_id": source_event_id}
                            if source_event_id
                            else {}
                        ),
                    },
                )
                session.add(baseline)
            conv.updated_at = updated_at or created_at or conv.updated_at
            flag_modified(conv, "updated_at")
            await session.commit()
            return conv

    async def project(
        self, session, conv: ConversationV3, leaf=NOT_GIVEN, *, revision=None
    ) -> ConversationSnapshot:
        """Restore an exact position from its baseline and indexed linear tail.

        Args:
            session: Active transaction.
            conv: Owning conversation metadata.
            leaf: Optional historical position; None denotes the empty root.
            revision: Optional revision from the same database read transaction.

        Returns:
            Detached messages, revision, and replay event count.

        Raises:
            ContextUnavailableError: The required baseline was reclaimed.
            ValueError: A context position or baseline is missing or invalid.
        """
        conv = ConversationV3(**conv.model_dump())
        if revision is not None and (
            leaf is None or (leaf is NOT_GIVEN and revision.leaf_event_id is None)
        ):
            return ConversationSnapshot(
                conv, ConversationRevision(revision.head_seq, None)
            )
        head, current_leaf = conversation_revision_columns()
        if revision is not None:
            head, current_leaf = (
                literal(revision.head_seq),
                literal(revision.leaf_event_id),
            )
        target_leaf = current_leaf if leaf is NOT_GIVEN else literal(leaf)
        baseline_event = aliased(ConversationEvent)
        baseline_lookup = aliased(ConversationEvent)
        baseline_seq_query = (
            select(baseline_lookup.seq)
            .where(
                baseline_lookup.conversation_ref == ConversationEvent.conversation_ref,
                baseline_lookup.type == "context.rebased",
                baseline_lookup.seq <= ConversationEvent.seq,
            )
            .order_by(baseline_lookup.seq.desc())
            .limit(1)
            .correlate(ConversationEvent)
            .scalar_subquery()
        )
        position = (
            await session.execute(
                select(
                    head.label("head_seq"),
                    ConversationEvent.event_id,
                    ConversationEvent.conversation_ref,
                    ConversationEvent.type,
                    ConversationEvent.seq,
                    baseline_event,
                )
                .select_from(ConversationV3)
                .outerjoin(ConversationEvent, ConversationEvent.event_id == target_leaf)
                .outerjoin(
                    baseline_event,
                    (
                        baseline_event.conversation_ref
                        == ConversationEvent.conversation_ref
                    )
                    & (baseline_event.seq == baseline_seq_query),
                )
                .where(ConversationV3.id == conv.id)
            )
        ).one_or_none()
        if position is None:
            raise ValueError("Conversation not found")
        snapshot = ConversationSnapshot(
            conv, ConversationRevision(position.head_seq, position.event_id)
        )
        if position.event_id is None and (leaf is NOT_GIVEN or leaf is None):
            return snapshot
        if position.conversation_ref != conv.id or position.type not in CONTEXT_TYPES:
            raise ValueError("Missing or inaccessible context leaf")
        target, baseline = position, position[-1]
        snapshot.context_seq = target.seq
        baseline_seq = 0
        if baseline is not None:
            if baseline.payload is None:
                raise ContextUnavailableError("Historical context has been cleared")
            if baseline.version != 1:
                raise ValueError("Unsupported context event version")
            snapshot.entries = persistent_entries(baseline.payload["messages"])
            baseline_seq = baseline.seq
            snapshot.replay_count = 1
        query = (
            select(ConversationEvent)
            .where(
                ConversationEvent.conversation_ref == conv.id,
                ConversationEvent.seq > baseline_seq,
                ConversationEvent.seq <= target.seq,
                col(ConversationEvent.type).in_(CONTEXT_TYPES),
            )
            .order_by(ConversationEvent.seq)
        )
        stream = await session.stream_scalars(query)
        async for event in stream:
            if (
                event.type != "message.appended"
                or event.version != 1
                or event.payload is None
            ):
                raise ValueError("Invalid linear context segment")
            effective = persistent_messages([event.payload["message"]])
            # Older journals contain a separate raw copy marked as excluded.
            # Keep ignoring it so upgrading cannot replay both stored copies.
            if event.payload.get("include_in_context", True) and effective:
                snapshot.entries.append({"id": event.event_id, "message": effective[0]})
            snapshot.replay_count += 1
        return snapshot

    async def get_context_availability(
        self, cid: str, event_ids: list[str | None]
    ) -> dict[str | None, str]:
        """Inspect recovery metadata in bounded batches without loading bodies.

        Args:
            cid: Authorized owning conversation.
            event_ids: Historical positions, including the valid empty root.

        Returns:
            Each position mapped to available, pruned, missing, or forbidden.
        """
        result = {
            event_id: "available" if event_id is None else "missing"
            for event_id in event_ids
        }
        async with self.db.get_db(consistent_read=True) as session:
            conv = (
                await session.execute(
                    select(ConversationV3).where(ConversationV3.conversation_id == cid)
                )
            ).scalar_one_or_none()
            if conv is None:
                return dict.fromkeys(event_ids, "missing")
            ids = list({value for value in event_ids if value is not None})
            baseline = aliased(ConversationEvent)
            lookup = aliased(ConversationEvent)
            baseline_seq = (
                select(lookup.seq)
                .where(
                    lookup.conversation_ref == ConversationEvent.conversation_ref,
                    lookup.type == "context.rebased",
                    lookup.seq <= ConversationEvent.seq,
                )
                .order_by(lookup.seq.desc())
                .limit(1)
                .correlate(ConversationEvent)
                .scalar_subquery()
            )
            for offset in range(0, len(ids), 400):
                rows = (
                    await session.execute(
                        select(
                            ConversationEvent.event_id,
                            ConversationEvent.conversation_ref,
                            ConversationEvent.type,
                            ConversationEvent.version,
                            baseline.version.label("baseline_version"),
                            baseline.payload.is_(None).label("pruned"),
                        )
                        .outerjoin(
                            baseline,
                            (
                                baseline.conversation_ref
                                == ConversationEvent.conversation_ref
                            )
                            & (baseline.seq == baseline_seq),
                        )
                        .where(
                            col(ConversationEvent.event_id).in_(
                                ids[offset : offset + 400]
                            )
                        )
                    )
                ).all()
                for row in rows:
                    if row.conversation_ref != conv.id:
                        result[row.event_id] = "forbidden"
                    elif row.type not in CONTEXT_TYPES or row.version != 1:
                        result[row.event_id] = "missing"
                    elif row.baseline_version is None:
                        result[row.event_id] = "available"
                    elif row.baseline_version != 1:
                        result[row.event_id] = "missing"
                    else:
                        result[row.event_id] = "pruned" if row.pruned else "available"
        return result

    async def restore_context(
        self, conversation: ConversationV3, leaf: str
    ) -> ConversationSnapshot:
        """Restore a confirmed historical position using an owned read session.

        Args:
            conversation: Previously loaded metadata identifying the owner.
            leaf: Exact acknowledged event identity, not the current selected tip.

        Returns:
            Detached context at the requested position.

        Raises:
            ContextUnavailableError: The historical baseline was reclaimed.
            ValueError: The requested leaf does not belong to this conversation.
        """
        async with self.db.get_db(consistent_read=True) as session:
            return await self.project(session, conversation, leaf)

    async def get_metadata(self, cid: str) -> ConversationV3 | None:
        """Read identity and ownership without loading message bodies.

        Args:
            cid: Public conversation identity.

        Returns:
            Detached metadata, or None when the conversation is absent.
        """
        async with self.db.get_db() as session:
            return await session.scalar(
                select(ConversationV3).where(ConversationV3.conversation_id == cid)
            )

    async def read_for_execution(
        self, cid: str
    ) -> tuple[ConversationRead, ConversationSnapshot] | None:
        """Load a request and its writer projection from the same database view.

        Args:
            cid: Public conversation identity.

        Returns:
            Plugin-compatible history and an independent writer snapshot sharing
            one committed revision, or None if the conversation is absent.
        """
        async with self.db.get_db(consistent_read=True) as session:
            token_usage = ConversationEvent.payload["token_usage"].as_integer()
            latest_usage = (
                select(token_usage)
                .where(
                    ConversationEvent.conversation_ref == ConversationV3.id,
                    token_usage.is_not(None),
                )
                .order_by(ConversationEvent.seq.desc())
                .limit(1)
                .correlate(ConversationV3)
            )
            loaded = (
                await session.execute(
                    select(
                        ConversationV3,
                        *conversation_revision_columns(),
                        func.coalesce(
                            latest_usage.where(
                                ConversationEvent.type == "conversation.updated"
                            ).scalar_subquery(),
                            latest_usage.where(
                                ConversationEvent.type == "conversation.created"
                            ).scalar_subquery(),
                            0,
                        ),
                    ).where(ConversationV3.conversation_id == cid)
                )
            ).one_or_none()
            if loaded is None:
                return None
            conv, head, leaf, usage = loaded
            revision = ConversationRevision(head, leaf)
            snapshot = await self.project(session, conv, revision=revision)
            record = ConversationRead(
                inner_conversation_id=conv.id,
                conversation_id=conv.conversation_id,
                platform_id=conv.platform_id,
                user_id=conv.umo,
                title=conv.title,
                persona_id=conv.persona_id,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                token_usage=usage,
                revision=revision,
                content=snapshot.messages,
            )
            return record, snapshot

    async def read(
        self, cid: str, *, include_history: bool = True
    ) -> ConversationSnapshot | None:
        """Read a conversation and its derived revision from one database view.

        Args:
            cid: Public conversation identity.
            include_history: Whether to load message bodies.

        Returns:
            Detached metadata and revision, with context when requested, or None.
        """
        async with self.db.get_db(consistent_read=True) as session:
            row = (
                await session.execute(
                    select(ConversationV3, *conversation_revision_columns()).where(
                        ConversationV3.conversation_id == cid
                    )
                )
            ).one_or_none()
            if row is None:
                return None
            conv, head, leaf = row
            revision = ConversationRevision(head, leaf)
            if include_history:
                return await self.project(session, conv, revision=revision)
            return ConversationSnapshot(conv, revision)

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
        return (await self.read_results(session, [conv], include_history))[0]

    async def read_results(
        self,
        session,
        conversations: Sequence[ConversationV3],
        include_history: bool = True,
    ) -> list[ConversationRead]:
        """Read results in input order and fetch token usage for the batch.

        Args:
            session: Current transaction.
            conversations: Conversation metadata selected by the caller.
            include_history: Whether to project context for each conversation.

        Returns:
            Legacy-compatible fields and their observed revisions.
        """
        if not conversations:
            return []

        # Use one bound parameter even when a page contains entire session groups.
        conversation_ids = func.json_each(
            json.dumps([conv.id for conv in conversations])
        ).table_valued("value")
        token_usage = ConversationEvent.payload["token_usage"].as_integer()
        usage_query = (
            select(token_usage)
            .where(
                ConversationEvent.conversation_ref == conversation_ids.c.value,
                token_usage.is_not(None),
            )
            .order_by(ConversationEvent.seq.desc())
            .limit(1)
            .correlate(conversation_ids)
        )
        # Equality on type lets SQLite seek the metadata index without scanning
        # the context tail. The creation event precedes every update.
        updated_usage = usage_query.where(
            ConversationEvent.type == "conversation.updated"
        ).scalar_subquery()
        created_usage = usage_query.where(
            ConversationEvent.type == "conversation.created"
        ).scalar_subquery()
        usage_rows = await session.execute(
            select(
                conversation_ids.c.value,
                func.coalesce(updated_usage, created_usage, 0),
                *conversation_revision_columns(conversation_ids.c.value),
            )
        )
        usage_by_id = {
            owner: (usage, ConversationRevision(head, leaf))
            for owner, usage, head, leaf in usage_rows
        }
        return [
            ConversationRead(
                inner_conversation_id=conv.id,
                conversation_id=conv.conversation_id,
                platform_id=conv.platform_id,
                user_id=conv.umo,
                title=conv.title,
                persona_id=conv.persona_id,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                token_usage=usage_by_id[conv.id][0],
                revision=usage_by_id[conv.id][1],
                content=(
                    await self.project(session, conv, revision=usage_by_id[conv.id][1])
                ).messages
                if include_history
                else None,
            )
            for conv in conversations
        ]

    async def _validate_event(
        self, session, conv, draft, leaf_event_id, batch_events, batch_finishes
    ) -> None:
        """Validate event shape and references within the active append transaction.

        Args:
            session: Transaction containing any earlier events in this batch.
            conv: Owning conversation metadata.
            draft: Normalized event to validate.
            leaf_event_id: Context position after earlier drafts in this batch.
            batch_events: Already validated events, including unflushed batch rows.
            batch_finishes: Execution settlements already validated in this batch.

        Raises:
            ValueError: Event shape or ownership is invalid.
            ConversationConflictError: A context or execution revision conflicts.
        """
        kind = draft["type"]
        payload = draft.get("payload", {})
        if kind not in EVENT_TYPES and not kind.startswith("plugin."):
            raise ValueError(f"Unknown event type: {kind}")
        if draft.get("version", 1) != 1 or not isinstance(payload, dict):
            raise ValueError("Unsupported event version or payload")
        if kind == "conversation.created":
            raise ValueError("Use create() to create a conversation")
        if "parent_event_id" in draft:
            raise ValueError(
                "Use a complete rebase to continue from historical context"
            )
        if kind == "message.appended":
            message = payload.get("message")
            if not isinstance(message, dict) or not isinstance(
                message.get("role"), str
            ):
                raise ValueError("A message requires a role")
            if message["role"] not in ("system", "user", "assistant", "tool"):
                raise ValueError("Unsupported message role")
            if "include_in_context" in payload:
                raise ValueError("Use message._no_save instead of include_in_context")
        elif kind == "context.rebased":
            if payload.get("origin", "unknown") not in {
                "user",
                "plugin",
                "system",
                "unknown",
            }:
                raise ValueError("Invalid rebase origin")
            if payload.get("reason") not in REBASE_REASONS or not isinstance(
                payload.get("messages"), list
            ):
                raise ValueError("A rebase requires a reason and complete messages")
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
                if not isinstance(message, dict) or "role" not in message:
                    raise ValueError("Invalid rebase message")
                persistent_messages([message], detach=False)
        elif kind == "conversation.updated":
            changes = payload.get("changes", {})
            if set(changes) - {"title", "persona_id"}:
                raise ValueError("Unsupported conversation metadata change")
            for key, value in changes.items():
                if value is not None and not isinstance(value, str):
                    raise ValueError("Metadata must be text or null")
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
            start = batch_events.get(payload.get(key, ""))
            duplicate = False
            if start is None:
                start_event = aliased(ConversationEvent)
                already_finished = (
                    select(ConversationEvent.event_id)
                    .where(
                        ConversationEvent.conversation_ref == conv.id,
                        ConversationEvent.type == kind,
                        ConversationEvent.seq > start_event.seq,
                        func.json_extract(
                            ConversationEvent.payload,
                            literal(f"$.{key}", literal_execute=True),
                        )
                        == payload.get(key, ""),
                    )
                    .correlate(start_event)
                    .exists()
                )
                start = (
                    await session.execute(
                        select(
                            start_event.conversation_ref,
                            start_event.type,
                            start_event.seq,
                            already_finished.label("finished"),
                        ).where(start_event.event_id == payload.get(key, ""))
                    )
                ).one_or_none()
                duplicate = start is not None and start.finished
            if (
                not start
                or start.conversation_ref != conv.id
                or start.type != kind.replace("finished", "started")
            ):
                raise ValueError("Missing matching execution start")
            if kind == "request.finished" and "usage" in payload:
                usage = payload["usage"]
                if not isinstance(usage, dict) or any(
                    type(value) is not int or value < 0 for value in usage.values()
                ):
                    raise ValueError("Token usage must contain nonnegative integers")
                if usage.get("cached_input_tokens", 0) > usage.get("input_tokens", 0):
                    raise ValueError("Cached input tokens are a subset of input tokens")
            # A start created in this batch cannot have a committed finish.
            # Earlier batch finishes remain visible even before rows are flushed.
            if duplicate or (kind, payload[key]) in batch_finishes:
                raise ConversationConflictError("Execution already finished")
            batch_finishes.add((kind, payload[key]))
        elif kind in {"request.started", "tool.started"}:
            turn = batch_events.get(payload.get("turn_id", ""))
            if turn is None:
                turn = (
                    await session.execute(
                        select(
                            ConversationEvent.conversation_ref,
                            ConversationEvent.type,
                        ).where(
                            ConversationEvent.event_id == payload.get("turn_id", "")
                        )
                    )
                ).one_or_none()
            if (
                not turn
                or turn.conversation_ref != conv.id
                or turn.type != "turn.started"
            ):
                raise ValueError("Missing parent turn")
            if (
                kind == "request.started"
                and "input_context" in payload
                and payload.get("context_leaf_event_id") != leaf_event_id
            ):
                raise ConversationConflictError(
                    "Request input is based on a different context"
                )
            if kind == "tool.started" and (
                not isinstance(payload.get("tool_name"), str)
                or not isinstance(payload.get("tool_call_id"), str)
                or not isinstance(payload.get("arguments"), dict)
            ):
                raise ValueError(
                    "A tool execution requires a name, call ID and arguments"
                )

    async def _prune_plugin_context(self, session, conv) -> None:
        """Reclaim superseded plugin bodies while retaining active execution baselines.

        Args:
            session: The append transaction, including its new lifecycle events.
            conv: Conversation with its updated baseline pointer.
        """
        await session.flush()
        # A baseline owns [seq, next rebase). Restrict reference checks to that
        # segment and use the partial indexes instead of scanning execution history.
        # Unary + removes VARCHAR affinity so JSON expression indexes can match
        # the reference value, rather than only their conversation prefix.
        await session.execute(
            text("""UPDATE conversation_events AS old INDEXED BY ix_context_plugin_live
            SET payload=NULL
            WHERE old.conversation_ref=:owner AND old.type='context.rebased'
              AND json_extract(old.payload,'$.origin')='plugin' AND old.payload IS NOT NULL
              AND old.seq < (SELECT seq FROM conversation_events
                  WHERE conversation_ref=:owner AND type='context.rebased'
                  ORDER BY seq DESC LIMIT 1)
              AND NOT EXISTS (
                  SELECT 1 FROM conversation_events AS context
                  JOIN conversation_events AS started INDEXED BY ix_context_turn_started
                    ON started.conversation_ref=:owner AND started.type='turn.started'
                   AND json_extract(started.payload,'$.base_leaf_event_id')=+context.event_id
                  WHERE context.conversation_ref=:owner AND context.seq >= old.seq
                    AND context.seq < (SELECT seq FROM conversation_events
                        WHERE conversation_ref=:owner AND type='context.rebased'
                          AND seq > old.seq ORDER BY seq LIMIT 1)
                    AND NOT EXISTS (
                        SELECT 1 FROM conversation_events AS finished
                        WHERE finished.conversation_ref=:owner AND finished.type='turn.finished'
                          AND json_extract(finished.payload,'$.turn_id')=+started.event_id))
              AND NOT EXISTS (
                  SELECT 1 FROM conversation_events AS context
                  JOIN conversation_events AS started INDEXED BY ix_context_request_started
                    ON started.conversation_ref=:owner AND started.type='request.started'
                   AND json_extract(started.payload,'$.context_leaf_event_id')=+context.event_id
                  WHERE context.conversation_ref=:owner AND context.seq >= old.seq
                    AND context.seq < (SELECT seq FROM conversation_events
                        WHERE conversation_ref=:owner AND type='context.rebased'
                          AND seq > old.seq ORDER BY seq LIMIT 1)
                    AND NOT EXISTS (
                        SELECT 1 FROM conversation_events AS finished
                        WHERE finished.conversation_ref=:owner AND finished.type='request.finished'
                          AND json_extract(finished.payload,'$.request_id')=+started.event_id))
            """),
            {"owner": conv.id},
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
        origin="unknown",
        link_display: bool = True,
    ) -> ConversationAppendResult:
        """Atomically validate and append a batch, optionally committing legacy history.

        Args:
            cid: Public conversation identity.
            drafts: Events with type, payload, and optional stable event ID.
            expected_head: Optional optimistic concurrency revision.
            expected_leaf: Optional expected linear context position.
            history: Optional complete legacy working history to reconcile.
            reason: Reason for a non-append history change.
            origin: Host-attributed source of a legacy context replacement.
            link_display: Maintain display links in the transaction. Hosts without
                display rows can opt out; existing callers retain projection.

        Returns:
            Acknowledged events and whether the complete batch was already stored.

        Raises:
            ConversationConflictError: A stale revision or conflicting ID was supplied.
            ValueError: A payload, reference, or event type is invalid.
        """
        serialized_drafts = [json.dumps(draft, allow_nan=False) for draft in drafts]
        draft_sizes = [len(serialized) for serialized in serialized_drafts]
        drafts = [json.loads(serialized) for serialized in serialized_drafts]
        del serialized_drafts
        async with self.db.get_db() as session:
            await session.execute(text("BEGIN IMMEDIATE"))
            metadata = (
                await session.execute(
                    select(
                        ConversationV3,
                        *conversation_revision_columns(),
                        text("""EXISTS (
                            SELECT 1 FROM conversation_events INDEXED BY ix_context_plugin_live
                            WHERE conversation_ref=conversations_v3.id
                              AND type='context.rebased'
                              AND json_extract(payload,'$.origin')='plugin'
                              AND payload IS NOT NULL
                        ) AS has_plugin_baseline"""),
                    ).where(ConversationV3.conversation_id == cid)
                )
            ).one_or_none()
            if metadata is None:
                raise ValueError("Conversation not found")
            conv, head_seq, leaf_event_id, has_plugin_baseline = metadata
            event_ids = {draft["event_id"] for draft in drafts if draft.get("event_id")}
            existing_by_id: dict[str, ConversationEvent] = {}
            if event_ids:
                # Bind one JSON array so large batches stay within SQLite's parameter limit.
                ids = func.json_each(json.dumps(list(event_ids))).table_valued("value")
                stored_events = await session.scalars(
                    select(ConversationEvent).where(
                        col(ConversationEvent.event_id).in_(select(ids.c.value))
                    )
                )
                existing_by_id = {event.event_id: event for event in stored_events}

            existing = []
            for draft in drafts:
                found = existing_by_id.get(draft.get("event_id"))
                if found is None:
                    continue
                if (
                    found.conversation_ref != conv.id
                    or found.type != draft["type"]
                    or (
                        found.payload is not None
                        and found.payload != draft.get("payload", {})
                    )
                    or found.version != draft.get("version", 1)
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
                    # Older batches could append an automatic snapshot after their drafts.
                    baseline = await session.get(
                        ConversationEvent,
                        (conv.id, max(event.seq for event in existing) + 1),
                    )
                    if (
                        baseline
                        and baseline.type == "context.rebased"
                        and (baseline.payload or {}).get("reason") == "snapshot"
                        and (baseline.payload or {}).get("source_event_id")
                        == context_events[-1].event_id
                    ):
                        existing.append(baseline)
                return ConversationAppendResult(existing, replayed=True)
            if (expected_head is not NOT_GIVEN and head_seq != expected_head) or (
                expected_leaf is not NOT_GIVEN and leaf_event_id != expected_leaf
            ):
                raise ConversationConflictError(
                    "Conversation changed; reload before committing"
                )
            if history is not None:
                snapshot = await self.project(
                    session,
                    conv,
                    revision=ConversationRevision(head_seq, leaf_event_id),
                )
                _, history_drafts = reconcile_history(
                    snapshot.entries, history, reason=reason, origin=origin
                )
                drafts.extend(history_drafts)
            committed = []
            # Validate against earlier batch events without flushing each row.
            metadata_changes: dict[str, str | None] = {}
            rows: list[dict] = []
            batch_bytes = 0
            batch_events: dict[str, ConversationEvent] = {}
            batch_finishes: set[tuple[str, str]] = set()
            for index, draft in enumerate(drafts):
                kind = draft["type"]
                payload = draft.get("payload", {})
                # Legacy history may add drafts after the initial normalization.
                size = (
                    draft_sizes[index]
                    if index < len(draft_sizes)
                    else len(json.dumps(payload))
                )
                if rows and (
                    len(rows) >= EVENT_INSERT_BATCH_ROWS
                    or batch_bytes + size > EVENT_INSERT_BATCH_BYTES
                ):
                    await session.execute(insert(ConversationEvent).values(rows))
                    rows.clear()
                    batch_bytes = 0
                await self._validate_event(
                    session, conv, draft, leaf_event_id, batch_events, batch_finishes
                )
                if kind == "conversation.updated":
                    metadata_changes.update(payload.get("changes", {}))
                head_seq += 1
                event = ConversationEvent(
                    conversation_ref=conv.id,
                    seq=head_seq,
                    event_id=draft.get("event_id") or new_event_id(),
                    type=kind,
                    payload=payload,
                )
                # Payloads are already detached above. Serializing them again via
                # Pydantic would traverse an entire rebase before the JSON bind.
                rows.append(
                    {**event.model_dump(exclude={"payload"}), "payload": payload}
                )
                batch_bytes += size
                batch_events[event.event_id] = event
                committed.append(event)
                if kind in CONTEXT_TYPES:
                    leaf_event_id = event.event_id
                if kind == "context.rebased" and payload.get("origin") == "plugin":
                    has_plugin_baseline = True
            if rows:
                await session.execute(insert(ConversationEvent).values(rows))
            # Execution progress only appends events. Refresh the conversation
            # once at turn settlement, or when its metadata is explicitly edited.
            if metadata_changes or any(
                event.type == "turn.finished" for event in committed
            ):
                for key, value in metadata_changes.items():
                    setattr(conv, key, value)
                conv.updated_at = datetime.now(timezone.utc)
            # Display links are a derived projection, committed with the events.
            if link_display:
                await project_webchat_event_links(session, committed)
            if has_plugin_baseline and any(
                event.type in {"context.rebased", "turn.finished", "request.finished"}
                for event in committed
            ):
                await self._prune_plugin_context(session, conv)
            await session.commit()
            return ConversationAppendResult(committed)

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

    async def read_request_context(self, cid: str, request_id: str) -> dict | None:
        """Restore the provider-facing context captured for a request attempt.

        Args:
            cid: Owning conversation identity.
            request_id: Event ID of the request start.

        Returns:
            Recorded contexts, extra user parts, and completeness, or None for
            an unknown request or a legacy record without a capture.

        Raises:
            ContextUnavailableError: The required historical context was reclaimed.
            ValueError: The stored input references an invalid message range.
        """
        async with self.db.get_db(consistent_read=True) as session:
            row = (
                await session.execute(
                    select(ConversationEvent, ConversationV3)
                    .join(
                        ConversationV3,
                        ConversationV3.id == ConversationEvent.conversation_ref,
                    )
                    .where(
                        ConversationV3.conversation_id == cid,
                        ConversationEvent.event_id == request_id,
                        ConversationEvent.type == "request.started",
                    )
                )
            ).one_or_none()
            if row is None:
                return None
            event, conversation = row
            captured = (event.payload or {}).get("input_context")
            if captured is None:
                return None
            baseline = []
            if any("base_range" in segment for segment in captured["segments"]):
                snapshot = await self.project(
                    session, conversation, event.payload["context_leaf_event_id"]
                )
                baseline = snapshot.messages
            contexts = []
            for segment in captured["segments"]:
                if "base_range" in segment:
                    start, end = segment["base_range"]
                    if not 0 <= start < end <= len(baseline):
                        raise ValueError("Invalid request context range")
                    contexts.extend(baseline[start:end])
                else:
                    contexts.append(segment["message"])
            return {
                "contexts": contexts,
                "extra_user_content_parts": captured["extra_user_content_parts"],
                "complete": captured["complete"],
            }

    async def select_branch(
        self, cid: str, leaf: str | None, *, expected_head, expected_leaf
    ) -> None:
        """Continue at a historical position using independent user snapshots.

        Args:
            cid: Target conversation.
            leaf: Accessible context node or None.
            expected_head: Revision read by the caller.
            expected_leaf: Previously selected tip.
        """
        async with self.db.get_db() as session:
            await session.execute(text("BEGIN IMMEDIATE"))
            conv, head_seq, leaf_event_id = (
                await session.execute(
                    select(ConversationV3, *conversation_revision_columns()).where(
                        ConversationV3.conversation_id == cid
                    )
                )
            ).one()
            if head_seq != expected_head or leaf_event_id != expected_leaf:
                raise ConversationConflictError(
                    "Conversation changed before branch selection"
                )
            snapshot = await self.project(
                session,
                conv,
                leaf,
                revision=ConversationRevision(head_seq, leaf_event_id),
            )
            previous = await self.project(
                session, conv, revision=ConversationRevision(head_seq, leaf_event_id)
            )
            for saved, source in [(previous, leaf_event_id), (snapshot, leaf)]:
                head_seq += 1
                baseline = ConversationEvent(
                    conversation_ref=conv.id,
                    seq=head_seq,
                    type="context.rebased",
                    payload={
                        "reason": "snapshot",
                        "origin": "user",
                        "source_event_id": source,
                        "messages": saved.entries,
                    },
                )
                session.add(baseline)
                if saved is previous and source:
                    await session.execute(
                        update(PlatformMessageHistory)
                        .where(PlatformMessageHistory.context_event_id == source)
                        .values(context_event_id=baseline.event_id)
                    )
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
            conv, head_seq, leaf_event_id = (
                await session.execute(
                    select(ConversationV3, *conversation_revision_columns()).where(
                        ConversationV3.conversation_id == cid
                    )
                )
            ).one()
            if head_seq != expected_head or leaf_event_id != expected_leaf:
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
            source_event_id = turn.payload.get("base_leaf_event_id")
            snapshot = await self.project(
                session,
                conv,
                source_event_id,
                revision=ConversationRevision(head_seq, leaf_event_id),
            )
            previous = await self.project(
                session, conv, revision=ConversationRevision(head_seq, leaf_event_id)
            )
            for saved, source_id in [
                (previous, leaf_event_id),
                (snapshot, source_event_id),
            ]:
                head_seq += 1
                baseline = ConversationEvent(
                    conversation_ref=conv.id,
                    seq=head_seq,
                    type="context.rebased",
                    payload={
                        "reason": "snapshot",
                        "origin": "user",
                        "source_event_id": source_id,
                        "messages": saved.entries,
                    },
                )
                session.add(baseline)
                if saved is previous and source_id:
                    await session.execute(
                        update(PlatformMessageHistory)
                        .where(PlatformMessageHistory.context_event_id == source_id)
                        .values(context_event_id=baseline.event_id)
                    )
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
                turn_id=new_event_id(),
            )
            session.add_all([conv, replacement])
            await session.commit()
            return replacement

    async def delete(self, *, cid=None, umo=None) -> None:
        """Delete conversations; independent forks retain their own contexts.

        Args:
            cid: Optional single public identity.
            umo: Optional owner whose conversations are deleted together.

        Raises:
            ValueError: The conversation selection is invalid.
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
                await session.execute(
                    delete(ConversationEvent).where(
                        col(ConversationEvent.conversation_ref).in_(ids)
                    )
                )
                await session.execute(
                    delete(ConversationV3).where(col(ConversationV3.id).in_(ids))
                )
            await session.commit()
