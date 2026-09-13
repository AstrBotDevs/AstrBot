"""Host-side event collection and branch-bound conversation commits."""

import asyncio
import hashlib
import json
import uuid
from collections import Counter, defaultdict, deque
from contextvars import ContextVar
from copy import deepcopy

from sqlalchemy.exc import SQLAlchemyError

from astrbot.core.agent.response import AgentResponse
from astrbot.core.db.conversation import (
    CONTEXT_TYPES,
    ConversationSnapshot,
    persistent_messages,
)
from astrbot.core.sentinels import NOT_GIVEN

active_plugin_id: ContextVar[str | None] = ContextVar(
    "active_conversation_plugin", default=None
)

active_conversation_writer: ContextVar["ConversationEventWriter | None"] = ContextVar(
    "active_conversation_writer", default=None
)


class ConversationPersistenceError(RuntimeError):
    """A journal write failed; provider or tool retries cannot repair it."""


class ConversationEventWriter:
    """Collect runner and plugin events against one conversation revision.

    A runner may retain its own journal. Reuse event IDs when retrying a write,
    and never replay tool side effects to resolve a storage conflict.
    """

    def __init__(self, store, snapshot: ConversationSnapshot):
        self.store = store
        self.cid = snapshot.conversation.conversation_id
        self.umo = snapshot.conversation.umo
        self.head_seq = snapshot.conversation.head_seq
        self.leaf_event_id = snapshot.conversation.leaf_event_id
        self.turn_id: str | None = None
        self.closed = False
        self.turn_result: AgentResponse | None = None
        self._lock = asyncio.Lock()
        self._pending: list[dict] = []
        self._entries = deepcopy(snapshot.entries)
        self._staged_leaf = self.leaf_event_id
        self._excluded_counts: Counter[str] = Counter()
        self.runtime_context = None
        self.request = None

    async def consume(self, response: AgentResponse) -> bool:
        """Collect a runner event before allowing execution to resume.

        Args:
            response: A value yielded by the runner, with optional stable identity.

        Returns:
            Whether the response belongs to persistence rather than display.
        """
        if response.type == "context.updated":
            self.stage_history(
                response.data["messages"],
                reason=response.data.get("reason", "legacy_replace"),
            )
        elif response.type == "turn.started":
            await self.start_turn(
                {"umo": self.umo, **response.data.get("trigger", {})},
                event_id=response.event_id,
            )
        elif response.type == "turn.finished":
            # The host settles the turn after its history-save hook has completed.
            self.turn_result = response
        elif response.type in {
            "request.started",
            "request.finished",
            "tool.started",
            "tool.finished",
            "message.appended",
            "context.rebased",
        }:
            payload = dict(response.data)
            if response.type in {
                "request.started",
                "tool.started",
                "message.appended",
                "context.rebased",
            }:
                payload.setdefault("turn_id", self.turn_id)
            if response.type == "request.started":
                payload.setdefault("context_leaf_event_id", self.leaf_event_id)
            await self.append(
                response.type, payload, event_id=response.event_id, sync_runtime=False
            )
        else:
            return False
        return True

    async def append(
        self,
        event_type: str,
        payload: dict,
        *,
        event_id=None,
        parent_event_id=NOT_GIVEN,
        sync_runtime=True,
    ):
        """Commit one common protocol event without exposing database internals.

        Args:
            event_type: Core or namespaced plugin event type.
            payload: JSON-serializable event data.
            event_id: Stable identity reused for delivery retries.
            parent_event_id: Omit to append to the bound branch; None means root.
            sync_runtime: Apply plugin writes to working context; runner events already did so.

        Returns:
            The acknowledged immutable event.
        """
        if self.closed:
            raise ValueError("The turn writer is closed")
        draft = {
            "type": event_type,
            "payload": payload,
            "event_id": event_id or str(uuid.uuid4()),
        }
        if parent_event_id is not NOT_GIVEN:
            draft["parent_event_id"] = parent_event_id
        async with self._lock:
            context_change = event_type in CONTEXT_TYPES
            drafts = [*self._pending, draft] if context_change else [draft]
            previous_staged_leaf = self._staged_leaf
            try:
                committed = await self.store.append(
                    self.cid,
                    drafts,
                    expected_head=self.head_seq,
                    expected_leaf=self.leaf_event_id,
                )
            except (SQLAlchemyError, ValueError) as exc:
                raise ConversationPersistenceError(
                    "Conversation event was not acknowledged"
                ) from exc
            acknowledged = next(e for e in committed if e.event_id == draft["event_id"])
            if all(e.seq <= self.head_seq for e in committed):
                return acknowledged
            self.head_seq = max(self.head_seq, *(e.seq for e in committed))
            for event in committed:
                if event.type in CONTEXT_TYPES:
                    self.leaf_event_id = event.event_id
            if context_change:
                # Read this immutable tip, even if another writer has since selected a branch.
                async with self.store.db.get_db() as session:
                    from sqlmodel import select

                    from astrbot.core.db.po import ConversationV3

                    conv = (
                        await session.execute(
                            select(ConversationV3).where(
                                ConversationV3.conversation_id == self.cid
                            )
                        )
                    ).scalar_one()
                    snapshot = await self.store.project(
                        session, conv, self.leaf_event_id
                    )
                self._entries = snapshot.entries
                self._pending.clear()
                self._staged_leaf = self.leaf_event_id
                if sync_runtime and self.runtime_context is not None:
                    from astrbot.core.agent.message import Message

                    if event_type == "message.appended" and (
                        parent_event_id is NOT_GIVEN
                        or parent_event_id == previous_staged_leaf
                    ):
                        message = Message.model_validate(deepcopy(payload["message"]))
                        message._no_save = not payload.get("include_in_context", True)
                        self.runtime_context.messages.append(message)
                        if message._no_save:
                            excluded = deepcopy(payload["message"])
                            excluded["_no_save"] = True
                            fingerprint = hashlib.sha256(
                                json.dumps(excluded, sort_keys=True).encode()
                            ).hexdigest()
                            self._excluded_counts[fingerprint] += 1
                    else:
                        leading_system = self.runtime_context.messages[:1]
                        if not leading_system or leading_system[0].role != "system":
                            leading_system = []
                        self.runtime_context.messages = leading_system + [
                            Message.model_validate(m) for m in snapshot.messages
                        ]
                elif sync_runtime and self.request is not None:
                    self.request.contexts = snapshot.messages
            return acknowledged

    async def append_message(
        self,
        message: dict,
        *,
        include_in_context=True,
        event_id=None,
        parent_event_id=NOT_GIVEN,
    ):
        """Persist a message and synchronize the runner's working context.

        Args:
            message: AstrBot message dictionary.
            include_in_context: Whether future projections include the message.
            event_id: Stable delivery ID.
            parent_event_id: Optional explicit branch parent.

        Returns:
            Committed message event.
        """
        return await self.append(
            "message.appended",
            {
                "message": message,
                "turn_id": self.turn_id,
                "include_in_context": include_in_context
                and not message.get("_no_save", False),
            },
            event_id=event_id,
            parent_event_id=parent_event_id,
        )

    async def start_turn(self, trigger: dict, *, event_id=None) -> str:
        """Start this runner's turn once.

        Args:
            trigger: Origin metadata, without request content.
            event_id: Optional host-assigned turn identity.

        Returns:
            Stable turn identity.
        """
        if self.turn_id is not None:
            return self.turn_id
        event = await self.append(
            "turn.started",
            {
                "trigger": trigger,
                "base_leaf_event_id": self.leaf_event_id,
            },
            event_id=event_id,
        )
        self.turn_id = event.event_id
        return self.turn_id

    async def finish_turn(self, status: str) -> None:
        """Record settlement without claiming recovery of external side effects.

        Args:
            status: completed, failed, or cancelled.
        """
        if self.turn_id and not self.closed:
            payload = dict(self.turn_result.data) if self.turn_result else {}
            payload.update(turn_id=self.turn_id, status=status)
            await self.append(
                "turn.finished",
                payload,
                event_id=self.turn_result.event_id if self.turn_result else None,
            )
            self.closed = True
            self._pending.clear()

    def stage_history(self, history: list[dict], *, reason="legacy_replace") -> None:
        """Stage legacy mutations until the existing history-save boundary.

        Args:
            history: Complete working history, including projection exclusions.
            reason: Reason for a replacement, such as compaction.
        """
        excluded_counts = Counter()
        for message in history:
            effective = persistent_messages([message])
            if message.get("role") == "_checkpoint" or effective == [message]:
                continue
            fingerprint = hashlib.sha256(
                json.dumps(message, sort_keys=True).encode()
            ).hexdigest()
            excluded_counts[fingerprint] += 1
            if excluded_counts[fingerprint] <= self._excluded_counts[fingerprint]:
                continue
            identity = str(uuid.uuid4())
            self._pending.append(
                {
                    "event_id": identity,
                    "type": "message.appended",
                    "parent_event_id": self._staged_leaf,
                    "payload": {
                        "turn_id": self.turn_id,
                        "message": deepcopy(message),
                        "include_in_context": False,
                    },
                }
            )
            self._staged_leaf = identity
        self._excluded_counts |= excluded_counts
        history = persistent_messages(history)
        before = [e["message"] for e in self._entries]
        if before == history:
            return
        if history[: len(before)] == before:
            for message in history[len(before) :]:
                identity = str(uuid.uuid4())
                self._pending.append(
                    {
                        "event_id": identity,
                        "type": "message.appended",
                        "parent_event_id": self._staged_leaf,
                        "payload": {
                            "turn_id": self.turn_id,
                            "message": deepcopy(message),
                        },
                    }
                )
                self._entries.append({"id": identity, "message": deepcopy(message)})
                self._staged_leaf = identity
        else:
            identity = str(uuid.uuid4())
            retained_ids = defaultdict(deque)
            for entry in self._entries:
                retained_ids[json.dumps(entry["message"], sort_keys=True)].append(
                    entry["id"]
                )
            self._entries = []
            for message in history:
                matches = retained_ids[json.dumps(message, sort_keys=True)]
                self._entries.append(
                    {
                        "id": matches.popleft() if matches else str(uuid.uuid4()),
                        "message": deepcopy(message),
                    }
                )
            self._pending.append(
                {
                    "event_id": identity,
                    "type": "context.rebased",
                    "parent_event_id": self._staged_leaf,
                    "payload": {
                        "reason": "reset" if not history else reason,
                        "turn_id": self.turn_id,
                        "messages": deepcopy(self._entries),
                    },
                }
            )
            self._staged_leaf = identity

    async def save_history(self, history: list[dict], *, token_usage=None) -> None:
        """Commit staged context at the old save boundary with revision checks.

        Args:
            history: Final legacy working history.
            token_usage: Optional legacy current-context estimate.
        """
        async with self._lock:
            self.stage_history(history)
            drafts = list(self._pending)
            if token_usage is not None:
                drafts.append(
                    {
                        "type": "conversation.updated",
                        "payload": {
                            "changes": {},
                            "token_usage": token_usage,
                        },
                    }
                )
            committed = await self.store.append(
                self.cid,
                drafts,
                expected_head=self.head_seq,
                expected_leaf=self.leaf_event_id,
            )
            for event in committed:
                self.head_seq = event.seq
                if event.type in CONTEXT_TYPES:
                    self.leaf_event_id = event.event_id
            self._staged_leaf = self.leaf_event_id
            self._pending.clear()
            if self.runtime_context is not None:
                from astrbot.core.agent.message import bind_checkpoint_messages

                system = self.runtime_context.messages[:1]
                if not system or system[0].role != "system":
                    system = []
                self.runtime_context.messages = system + bind_checkpoint_messages(
                    deepcopy(history)
                )
            elif self.request is not None:
                self.request.contexts = deepcopy(history)

    def plugin(self, plugin_id: str) -> "PluginConversationEvents":
        """Create a namespace-bound plugin journal facade.

        Args:
            plugin_id: Identity resolved by the plugin loader, not payload data.

        Returns:
            A plugin-specific append/read facade.
        """
        if not plugin_id or any(
            c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-."
            for c in plugin_id
        ):
            raise ValueError("Invalid plugin identity")
        return PluginConversationEvents(self, plugin_id)


class PluginConversationEvents:
    """Plugin context writes and a namespace-bound private event journal."""

    def __init__(self, writer: ConversationEventWriter, plugin_id: str):
        self.writer = writer
        self.prefix = f"plugin.{plugin_id}."

    async def append_message(
        self,
        message: dict,
        *,
        include_in_context=True,
        event_id=None,
        parent_event_id=NOT_GIVEN,
    ):
        """Append a core message and synchronize the current working context.

        Args:
            message: AstrBot message dictionary.
            include_in_context: Whether future projections include the message.
            event_id: Stable delivery identity for retries.
            parent_event_id: Omit for the current branch; None starts a root.

        Returns:
            Committed message event.
        """
        return await self.writer.append_message(
            message,
            include_in_context=include_in_context,
            event_id=event_id,
            parent_event_id=parent_event_id,
        )

    async def append(self, name: str, payload: dict, *, event_id=None):
        """Commit plugin-private JSON data.

        Args:
            name: Plugin-local event name.
            payload: Durable plugin data; do not copy temporary prompt content.
            event_id: Stable delivery identity for retries.

        Returns:
            Committed event.
        """
        if not name or "." in name:
            raise ValueError("Use a local event name without dots")
        return await self.writer.append(self.prefix + name, payload, event_id=event_id)

    async def list(self, name: str, *, after_seq=0, limit=100):
        """Read a bounded page in this conversation and namespace.

        Args:
            name: Plugin-local event name.
            after_seq: Exclusive cursor.
            limit: Maximum event count.

        Returns:
            Stored private events.
        """
        return await self.writer.store.events(
            self.writer.cid,
            event_type=self.prefix + name,
            after_seq=after_seq,
            limit=limit,
        )

    async def latest(self, name: str):
        """Read the most recent private event without scanning history.

        Args:
            name: Plugin-local event name.

        Returns:
            Last event, or None.
        """
        events = await self.writer.store.events(
            self.writer.cid, event_type=self.prefix + name, descending=True, limit=1
        )
        return events[0] if events else None
