"""Final assistant-history projection after platform acceptance.

Agent execution records model and tool facts independently.  This module owns
only the user-visible assistant history that is safe to persist after a
platform has accepted the corresponding message submission.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from astrbot import logger
from astrbot.core.agent.history_sanitizer import sanitize_history_for_storage
from astrbot.core.conversation_mgr import load_sanitized_history
from astrbot.core.platform.send_result import DeliveryReceipt
from astrbot.core.utils.error_redaction import safe_error

_HISTORY_RECEIPT_LIMIT = 256


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
    base_history: tuple[Mapping[str, Any], ...] | None = None
    unit_start: int | None = None
    expected_total: int | None = None


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
        self._structure_receipts: OrderedDict[str, tuple[tuple[Any, ...], ...]] = (
            OrderedDict()
        )
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
            token_usage = pending.token_usage
            if pending.base_history is not None:
                history, token_usage = await _merge_concurrent_history(
                    conversation_manager,
                    pending,
                    history,
                    token_usage,
                    self._structure_receipts,
                )
            try:
                await conversation_manager.update_conversation(
                    pending.unified_msg_origin,
                    pending.conversation_id,
                    history=sanitize_history_for_storage(history),
                    token_usage=token_usage,
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
            _remember_structure_receipt(
                self._structure_receipts,
                pending.conversation_id,
                history,
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
    base_history: Sequence[Mapping[str, Any]] | None = None,
    unit_start: int | None = None,
    expected_total: int | None = None,
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
        base_history=(
            tuple(_freeze(message) for message in base_history)
            if base_history is not None
            else None
        ),
        unit_start=unit_start,
        expected_total=expected_total,
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


def _history_struct_summary(
    history: Sequence[Mapping[str, Any]],
) -> tuple[tuple[Any, ...], ...]:
    """Return a bounded, text-free fingerprint of history structure."""
    summary: list[tuple[Any, ...]] = []
    for message in history:
        role = message.get("role")
        content = message.get("content")
        if isinstance(content, str):
            content_len = len(content)
        elif isinstance(content, list):
            content_len = len(content)
        else:
            content_len = 0
        summary.append(
            (
                role,
                content_len,
                bool(message.get("tool_calls")),
                role == "_checkpoint",
            )
        )
    return tuple(summary)


def _remember_structure_receipt(
    receipts: OrderedDict[str, tuple[tuple[Any, ...], ...]],
    conversation_id: str,
    history: Sequence[Mapping[str, Any]],
) -> None:
    receipts[conversation_id] = _history_struct_summary(history)
    receipts.move_to_end(conversation_id)
    while len(receipts) > _HISTORY_RECEIPT_LIMIT:
        receipts.popitem(last=False)


def _histories_equal(
    left: Sequence[Mapping[str, Any]],
    right: Sequence[Mapping[str, Any]],
) -> bool:
    return _history_struct_summary(left) == _history_struct_summary(right) and len(
        left
    ) == len(right)


async def _merge_concurrent_history(
    conversation_manager,
    pending: PendingAssistantHistory,
    new_history: list[dict[str, Any]],
    token_usage: int | None,
    receipts: OrderedDict[str, tuple[tuple[Any, ...], ...]],
) -> tuple[list[dict[str, Any]], int | None]:
    """Merge another sender's complete turns into this request's snapshot."""
    base_history = [_thaw(message) for message in pending.base_history or ()]
    unit_start = pending.unit_start
    expected_total = pending.expected_total
    if (
        unit_start is None
        or expected_total is None
        or unit_start < 0
        or unit_start >= len(new_history)
        or len(new_history) != expected_total
        or new_history[unit_start].get("role") != "user"
    ):
        return new_history, token_usage

    latest_history = await _load_latest_history(
        conversation_manager,
        pending.unified_msg_origin,
        pending.conversation_id,
    )
    if latest_history is None:
        return new_history, token_usage
    if _histories_equal(latest_history, base_history):
        return new_history, token_usage

    receipt = receipts.get(pending.conversation_id)
    if receipt is None or receipt != _history_struct_summary(latest_history):
        return new_history, token_usage

    current_unit = new_history[unit_start:]
    if _is_prefix(latest_history, base_history):
        merged = new_history[:unit_start] + latest_history[len(base_history) :]
        merged.extend(current_unit)
        extra_turns = len(latest_history) > len(base_history)
        return merged, 0 if extra_turns else token_usage
    merged = list(latest_history)
    merged.extend(current_unit)
    return merged, 0


def _is_prefix(
    latest: Sequence[Mapping[str, Any]],
    base: Sequence[Mapping[str, Any]],
) -> bool:
    if len(latest) < len(base):
        return False
    return _histories_equal(latest[: len(base)], base)


async def _load_latest_history(
    conversation_manager,
    unified_msg_origin: str,
    conversation_id: str,
) -> list[dict[str, Any]] | None:
    getter = getattr(conversation_manager, "get_conversation", None)
    if not callable(getter):
        return None
    try:
        conversation = await getter(unified_msg_origin, conversation_id)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to reload conversation history for merge: %s",
            safe_error("", exc),
        )
        return None
    if conversation is None:
        return None
    history = getattr(conversation, "history", None)
    if isinstance(history, list):
        return [dict(item) if isinstance(item, Mapping) else item for item in history]
    if isinstance(history, str):
        return load_sanitized_history(history)
    return None


def _thaw(value: Any) -> Any:
    """Materialize an independent storage payload from a frozen snapshot."""
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value
