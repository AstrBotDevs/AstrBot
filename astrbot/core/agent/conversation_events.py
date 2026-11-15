"""Host-side event collection and branch-bound conversation commits."""

import asyncio
import hashlib
import json
from collections import Counter
from copy import deepcopy

from sqlalchemy.exc import SQLAlchemyError

from astrbot.core.agent.response import AgentResponse
from astrbot.core.db.conversation import (
    CONTEXT_TYPES,
    ContextUnavailableError,
    ConversationAppendResult,
    ConversationSnapshot,
    persistent_entries,
    persistent_messages,
    reconcile_history,
)
from astrbot.core.sentinels import NOT_GIVEN
from astrbot.core.utils.event_id import new_event_id


class ConversationPersistenceError(RuntimeError):
    """A journal write failed; provider or tool retries cannot repair it."""


def _message_key(value):
    """Make a JSON value hashable without encoding large message bodies.

    Args:
        value: A JSON-compatible value in a model message.

    Returns:
        A key that preserves JSON types and ignores object key order.
    """
    if isinstance(value, dict):
        return frozenset((key, _message_key(item)) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return tuple(_message_key(item) for item in value)
    return type(value), value


class ConversationEventWriter:
    """Collect runner and plugin events against one conversation revision.

    A runner may retain its own journal. Reuse event IDs when retrying a write,
    and never replay tool side effects to resolve a storage conflict.
    """

    def __init__(
        self, store, snapshot: ConversationSnapshot, *, link_display: bool = True
    ):
        """Bind committed context and the host's display projection policy.

        Args:
            store: Transactional conversation event store.
            snapshot: Detached committed context.
            link_display: Maintain display links; hosts without display rows can
                disable this. Defaults to true for existing API callers.
        """
        self.store = store
        self._link_display = link_display
        self.cid = snapshot.conversation.conversation_id
        self.umo = snapshot.conversation.umo
        self.head_seq = snapshot.revision.head_seq
        self.leaf_event_id = snapshot.revision.leaf_event_id
        self._context_seq = snapshot.context_seq
        self._conversation = snapshot.conversation.model_copy()
        self.turn_id: str | None = None
        self.closed = False
        self.turn_result: AgentResponse | None = None
        self._lock = asyncio.Lock()
        self._pending: list[dict] = []
        self._entries = deepcopy(snapshot.entries)
        self._committed_entries = self._entries
        self._temporary_counts: Counter[str] = Counter()

    def get_messages(self) -> list[dict]:
        """Read a detached view of the current projection, including staged edits.

        Returns:
            Full messages whose mutation cannot alter this writer's state.
        """
        return deepcopy([entry["message"] for entry in self._entries])

    async def consume(self, response: AgentResponse) -> bool:
        """Collect a runner event before allowing execution to resume.

        Args:
            response: A value yielded by the runner, with optional stable identity.

        Returns:
            Whether the response belongs to persistence rather than display.
        """
        if response.type == "context.appended":
            self.stage_messages(response.data["messages"])
        elif response.type == "context.updated":
            self.stage_history(
                response.data["messages"],
                reason=response.data.get("reason", "legacy_replace"),
                origin=response.data.get("origin", "unknown"),
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
            await self.append(response.type, payload, event_id=response.event_id)
        else:
            return False
        return True

    async def append(
        self,
        event_type: str,
        payload: dict,
        *,
        event_id=None,
    ):
        """Commit one common protocol event without exposing database internals.

        Args:
            event_type: Core or namespaced plugin event type.
            payload: JSON-serializable event data.
            event_id: Stable identity reused for delivery retries.

        Returns:
            The acknowledged immutable event.
        """
        if self.closed:
            raise ValueError("The turn writer is closed")
        draft = {
            "type": event_type,
            "payload": payload,
            "event_id": event_id or new_event_id(),
        }
        async with self._lock:
            context_change = event_type in CONTEXT_TYPES
            if event_type == "request.started":
                payload.setdefault("context_leaf_event_id", self.leaf_event_id)
                if "input_context" in payload:
                    payload["context_leaf_event_id"] = self.leaf_event_id
                    payload["input_context"] = self._encode_request_context(
                        payload["input_context"]
                    )
            drafts = [*self._pending, draft] if context_change else [draft]
            checks_context = context_change or event_type in {
                "turn.started",
                "request.started",
                "tool.started",
            }
            try:
                committed = await self.store.append(
                    self.cid,
                    drafts,
                    expected_leaf=self.leaf_event_id if checks_context else NOT_GIVEN,
                    link_display=self._link_display,
                )
            except (SQLAlchemyError, ValueError) as exc:
                raise ConversationPersistenceError(
                    "Conversation event was not acknowledged"
                ) from exc
            acknowledged = next(
                event
                for event in committed.events
                if event.event_id == draft["event_id"]
            )
            previous_context_seq = self._context_seq
            await self._acknowledge(committed)
            if context_change and acknowledged.seq > previous_context_seq:
                # Direct appends bypass staging. Remember their raw temporary
                # bodies too, so a later history save does not record them again.
                messages = (
                    [acknowledged.payload["message"]]
                    if event_type == "message.appended"
                    else [
                        entry["message"] for entry in acknowledged.payload["messages"]
                    ]
                )
                temporary = Counter(
                    hashlib.sha256(
                        json.dumps(message, sort_keys=True).encode()
                    ).hexdigest()
                    for message in messages
                    if persistent_messages([message], detach=False) != [message]
                )
                if event_type == "message.appended":
                    self._temporary_counts.update(temporary)
                else:
                    self._temporary_counts |= temporary
            return acknowledged

    async def _acknowledge(self, result: ConversationAppendResult) -> None:
        """Apply an ACK without replaying history on ordinary append operations.

        Args:
            result: Stored events, including any legacy snapshot returned on retry.

        Raises:
            ContextUnavailableError: An unseen retried context has been reclaimed.
            ValueError: An acknowledged context cannot be projected.
        """
        context_events = sorted(
            (
                event
                for event in result.events
                if event.type in CONTEXT_TYPES and event.seq > self._context_seq
            ),
            key=lambda event: event.seq,
        )
        acknowledged_ids = {event.event_id for event in result.events}
        remaining = [
            draft
            for draft in self._pending
            if draft["event_id"] not in acknowledged_ids
        ]
        replacement = None
        additions = []
        if context_events:
            # A complete rebase supersedes all earlier context in the ACK, including
            # bodies that may have since been reclaimed by plugin retention.
            rebase_index = next(
                (
                    index
                    for index in range(len(context_events) - 1, -1, -1)
                    if context_events[index].type == "context.rebased"
                ),
                None,
            )
            if result.replayed and rebase_index is None:
                # An unseen historical ACK need not follow our local context: other
                # writers may have appended intervening messages. Restore this exact
                # immutable tip, never the conversation's currently selected tip.
                snapshot = await self.store.restore_context(
                    self._conversation, context_events[-1].event_id
                )
                replacement = snapshot.entries
            else:
                for event in context_events[rebase_index or 0 :]:
                    if event.payload is None:
                        raise ContextUnavailableError(
                            "Acknowledged context payload is unavailable"
                        )
                    if event.type == "context.rebased":
                        replacement = persistent_entries(event.payload["messages"])
                    elif event.payload.get("include_in_context", True):
                        effective = persistent_messages([event.payload["message"]])
                        if effective:
                            additions.append(
                                {"id": event.event_id, "message": effective[0]}
                            )

        # Prepare any still-staged projection before confirming the ACK. Staging
        # may have occurred while storage was awaited; only acknowledged drafts
        # are removed. This full reference copy is confined to pending work.
        staged = None
        if remaining and (context_events or len(remaining) != len(self._pending)):
            staged = list(
                self._committed_entries if replacement is None else replacement
            )
            staged.extend(additions)
            for draft in remaining:
                payload = draft["payload"]
                if draft["type"] == "context.rebased":
                    staged = persistent_entries(payload["messages"])
                elif draft["type"] == "message.appended" and payload.get(
                    "include_in_context", True
                ):
                    effective = persistent_messages([payload["message"]])
                    if effective:
                        staged.append(
                            {"id": draft["event_id"], "message": effective[0]}
                        )

        # No await or projection work follows: all committed state moves together.
        if context_events:
            if replacement is not None:
                self._committed_entries = replacement
            self._committed_entries.extend(additions)
            tip = context_events[-1]
            self._context_seq = tip.seq
            self.leaf_event_id = tip.event_id
        if staged is not None:
            self._entries = staged
        elif not remaining:
            self._entries = self._committed_entries
        self._pending = remaining
        self.head_seq = (
            max(self.head_seq, *(event.seq for event in result.events))
            if result.events
            else self.head_seq
        )

    async def append_message(
        self,
        message: dict,
        *,
        event_id=None,
    ):
        """Persist a message without modifying the execution's working context.

        Args:
            message: AstrBot message dictionary.
            event_id: Stable delivery ID.

        Returns:
            Committed message event.
        """
        return await self.append(
            "message.appended",
            {
                "message": message,
                "turn_id": self.turn_id,
            },
            event_id=event_id,
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

    def _encode_request_context(self, input_context: dict) -> dict:
        """Reference unchanged messages in the committed context by position.

        Args:
            input_context: Provider-facing messages with temporary content filtered.

        Returns:
            The request input as ordered ranges and inline messages.
        """
        base_keys = [
            _message_key(entry["message"]) for entry in self._committed_entries
        ]
        positions = {}
        for index, key in enumerate(base_keys):
            positions.setdefault(key, index)
        segments = []
        for message in input_context["contexts"]:
            key = _message_key(message)
            previous_range = segments[-1].get("base_range") if segments else None
            if (
                previous_range is not None
                and previous_range[1] < len(base_keys)
                and base_keys[previous_range[1]] == key
            ):
                previous_range[1] += 1
                continue
            position = positions.get(key)
            if position is None:
                segments.append({"message": message})
            else:
                segments.append({"base_range": [position, position + 1]})
        return {
            "segments": segments,
            "extra_user_content_parts": input_context["extra_user_content_parts"],
            "complete": input_context["complete"],
        }

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
            self._entries = self._committed_entries

    def stage_messages(self, messages: list[dict]) -> None:
        """Stage a framework-owned append without comparing the previous history.

        Args:
            messages: Only new working messages, including temporary content.
        """
        temporary = Counter()
        entries, drafts = reconcile_history(
            [], messages, turn_id=self.turn_id, temporary_counts=temporary
        )
        if entries:
            # Detach the list once when staging begins; message bodies stay shared
            # with the immutable committed projection until a replacement occurs.
            if self._entries is self._committed_entries:
                self._entries = list(self._entries)
            self._entries.extend(entries)
        self._pending.extend(drafts)
        self._temporary_counts.update(temporary)

    def stage_history(
        self, history: list[dict], *, reason="legacy_replace", origin="unknown"
    ) -> None:
        """Stage legacy mutations until the existing history-save boundary.

        Args:
            history: Complete working history, including projection exclusions.
            reason: Reason for a replacement, such as compaction.
            origin: Trusted mutation source: user, plugin, system, or unknown.
        """
        self._entries, drafts = reconcile_history(
            self._entries,
            history,
            reason=reason,
            origin=origin,
            turn_id=self.turn_id,
            temporary_counts=self._temporary_counts,
        )
        self._pending.extend(drafts)

    async def save_history(
        self, history: list[dict], *, token_usage=None, origin="unknown"
    ) -> None:
        """Commit staged context at the old save boundary with revision checks.

        Args:
            history: Final legacy working history.
            token_usage: Optional legacy current-context estimate.
            origin: Trusted source of changes since the latest staged snapshot.
        """
        async with self._lock:
            self.stage_history(history, origin=origin)
            if token_usage is not None:
                payload = {"changes": {}, "token_usage": token_usage}
                if (
                    not self._pending
                    or self._pending[-1]["type"] != "conversation.updated"
                    or self._pending[-1]["payload"] != payload
                ):
                    self._pending.append(
                        {
                            "event_id": new_event_id(),
                            "type": "conversation.updated",
                            "payload": payload,
                        }
                    )
            committed = await self.store.append(
                self.cid,
                list(self._pending),
                expected_leaf=self.leaf_event_id,
                link_display=self._link_display,
            )
            await self._acknowledge(committed)
