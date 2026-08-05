"""Final assistant-history projection after platform acceptance.

Agent execution records model and tool facts independently.  This module owns
only the user-visible assistant history that is safe to persist after a
platform has accepted the corresponding message submission.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from astrbot import logger
from astrbot.core.agent.history_sanitizer import sanitize_history_for_storage
from astrbot.core.platform.send_result import DeliveryReceipt
from astrbot.core.utils.error_redaction import safe_error


@dataclass(frozen=True, slots=True)
class PendingAssistantHistory:
    """Immutable agent-completion snapshot awaiting a platform receipt."""

    unified_msg_origin: str
    conversation_id: str
    history_snapshot: tuple[Mapping[str, Any], ...]
    token_usage: int | None
    assistant_semantic_output: str
    checkpoint_id: str | None = None
    run_id: str | None = None
    sequence: int = 0
    runtime_metadata: Mapping[str, Any] = MappingProxyType({})


@dataclass(frozen=True, slots=True)
class AssistantHistoryProjection:
    """Safe, local semantic content accepted by the platform."""

    text: str
    message_count: int

    def as_history_message(self) -> dict[str, str]:
        """Return the provider-neutral assistant message persisted in history."""
        return {"role": "assistant", "content": self.text}

    def as_dict(self) -> dict[str, Any]:
        """Return a read-only-event-safe serialization."""
        return {
            "role": "assistant",
            "content": self.text,
            "message_count": self.message_count,
        }


@dataclass(frozen=True, slots=True)
class AssistantHistoryFinalized:
    """Read-only plugin payload emitted after the commit decision."""

    projection: AssistantHistoryProjection | None
    receipt: DeliveryReceipt
    conversation_id: str | None
    run_id: str | None
    history_committed: bool


def make_projection(receipt: DeliveryReceipt) -> AssistantHistoryProjection | None:
    """Build a projection from exactly the accepted local message fragments."""
    if receipt.status not in {"accepted", "partial"}:
        return None
    text = receipt.history_text.strip()
    if not text:
        return None
    return AssistantHistoryProjection(
        text=text,
        message_count=len(receipt.accepted_attempts),
    )


class AssistantHistoryCommitter:
    """Serialize final projections so an older snapshot cannot overwrite newer data."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._latest_sequence_by_conversation: dict[str, int] = {}
        self._sequence = 0

    def next_sequence(self) -> int:
        """Allocate an in-process order token before Agent execution begins."""
        self._sequence += 1
        return self._sequence

    async def commit(
        self,
        conversation_manager,
        pending: PendingAssistantHistory,
        projection: AssistantHistoryProjection | None,
    ) -> bool:
        """Persist a final projection only after a platform acceptance receipt."""
        if projection is None:
            return False

        lock = self._locks.setdefault(pending.conversation_id, asyncio.Lock())
        async with lock:
            previous = self._latest_sequence_by_conversation.get(
                pending.conversation_id,
                0,
            )
            if pending.sequence and pending.sequence < previous:
                logger.info(
                    "Skip stale assistant history projection for conversation %s",
                    pending.conversation_id,
                )
                return False

            history = [_thaw(message) for message in pending.history_snapshot]
            history.append(projection.as_history_message())
            if pending.checkpoint_id:
                history.append(
                    {"role": "_checkpoint", "content": {"id": pending.checkpoint_id}},
                )
            try:
                await conversation_manager.update_conversation(
                    pending.unified_msg_origin,
                    pending.conversation_id,
                    history=sanitize_history_for_storage(history),
                    token_usage=pending.token_usage,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to commit assistant history projection: %s",
                    safe_error("", exc),
                )
                return False
            if pending.sequence:
                self._latest_sequence_by_conversation[pending.conversation_id] = (
                    pending.sequence
                )
            return True


def build_pending_assistant_history(
    *,
    unified_msg_origin: str,
    conversation_id: str,
    history_snapshot: list[dict[str, Any]],
    token_usage: int | None,
    assistant_semantic_output: str,
    checkpoint_id: str | None,
    run_id: str | None,
    sequence: int = 0,
    runtime_metadata: Mapping[str, Any] | None = None,
) -> PendingAssistantHistory:
    """Freeze an agent-completion snapshot without writing conversation storage."""
    return PendingAssistantHistory(
        unified_msg_origin=unified_msg_origin,
        conversation_id=conversation_id,
        history_snapshot=tuple(_freeze(message) for message in history_snapshot),
        token_usage=token_usage,
        assistant_semantic_output=assistant_semantic_output,
        checkpoint_id=checkpoint_id,
        run_id=run_id,
        sequence=sequence,
        runtime_metadata=_freeze(dict(runtime_metadata or {})),
    )


def _freeze(value: Any) -> Any:
    """Recursively freeze event-owned data before it crosses the send boundary."""
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    """Materialize an independent storage payload from a frozen snapshot."""
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value
