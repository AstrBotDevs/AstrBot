"""Host-side event collection and branch-bound conversation commits."""

import asyncio
import uuid
from collections import Counter
from copy import deepcopy

from sqlalchemy.exc import SQLAlchemyError

from astrbot.core.agent.response import AgentResponse
from astrbot.core.db.conversation import (
    CONTEXT_TYPES,
    ConversationSnapshot,
    reconcile_history,
)
from astrbot.core.sentinels import NOT_GIVEN


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
        self._committed_entries = tuple(self._entries)
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
            "event_id": event_id or str(uuid.uuid4()),
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
                self._committed_entries = tuple(self._entries)
                self._pending.clear()
            return acknowledged

    async def append_message(
        self,
        message: dict,
        *,
        include_in_context=True,
        event_id=None,
    ):
        """Persist a message without modifying the execution's working context.

        Args:
            message: AstrBot message dictionary.
            include_in_context: Whether future projections include the message.
            event_id: Stable delivery ID.

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
            excluded_counts=self._excluded_counts,
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
                expected_leaf=self.leaf_event_id,
            )
            for event in committed:
                self.head_seq = event.seq
                if event.type in CONTEXT_TYPES:
                    self.leaf_event_id = event.event_id
            self._pending.clear()
            self._committed_entries = tuple(self._entries)
            if self.runtime_context is not None:
                from astrbot.core.agent.message import load_messages

                system = self.runtime_context.messages[:1]
                if not system or system[0].role != "system":
                    system = []
                self.runtime_context.messages = system + load_messages(
                    deepcopy(history)
                )
            elif self.request is not None:
                self.request.contexts = deepcopy(history)
