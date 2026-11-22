from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Literal

from astrbot.core.agent.runtime import (
    AgentInput,
    AgentPermissions,
    AgentTurn,
    InputReceipt,
)
from astrbot.core.agent_input import extract_plain_steering_text
from astrbot.core.platform.agent_wakeup_event import AgentWakeupEvent
from astrbot.core.platform.astr_message_event import AstrMessageEvent

_OrderSlotStatus = Literal["pending", "deferred", "active", "consumed", "finished"]


@dataclass(slots=True)
class _FollowUpOrderSlot:
    status: _OrderSlotStatus
    event_id: int
    target_run_id: str | None = None


@dataclass(slots=True)
class _FollowUpOrderState:
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)
    # Sequence status map for strict in-order resume after unresolved or deferred inputs.
    slots: dict[int, _FollowUpOrderSlot] = field(default_factory=dict)
    # Stable allocator for arrival order; never decreases for the same UMO state.
    next_order: int = 0
    # The sequence currently allowed to continue main internal flow.
    next_turn: int = 0


_FOLLOW_UP_ORDER_STATE: dict[str, _FollowUpOrderState] = {}
"""UMO-level follow-up order state."""


@dataclass(slots=True)
class FollowUpCapture:
    umo: str
    receipt: InputReceipt | None
    order_seq: int
    monitor_task: asyncio.Task[None] | None
    target_run_id: str | None = None


def _get_follow_up_order_state(umo: str) -> _FollowUpOrderState:
    state = _FOLLOW_UP_ORDER_STATE.get(umo)
    if state is None:
        state = _FollowUpOrderState()
        _FOLLOW_UP_ORDER_STATE[umo] = state
    return state


def _advance_follow_up_turn_locked(state: _FollowUpOrderState) -> None:
    # Skip slots that are already handled, and stop at the first unfinished slot.
    next_turn = state.next_turn
    while True:
        slot = state.slots.get(next_turn)
        if slot is not None and slot.status in ("consumed", "finished"):
            state.slots.pop(next_turn, None)
            next_turn += 1
            continue
        break
    state.next_turn = next_turn


def _allocate_follow_up_order(
    umo: str,
    *,
    status: _OrderSlotStatus,
    event_id: int,
    target_run_id: str | None,
) -> int:
    state = _get_follow_up_order_state(umo)
    seq = state.next_order
    state.next_order = seq + 1
    state.slots[seq] = _FollowUpOrderSlot(
        status=status,
        event_id=event_id,
        target_run_id=target_run_id,
    )
    return seq


async def _complete_follow_up_slot(
    umo: str,
    seq: int,
    final_status: Literal["consumed", "finished"],
) -> None:
    state = _FOLLOW_UP_ORDER_STATE.get(umo)
    if state is None:
        return
    async with state.condition:
        slot = state.slots.get(seq)
        if slot is not None and (
            final_status == "finished" or slot.status != "finished"
        ):
            slot.status = final_status
        _advance_follow_up_turn_locked(state)
        state.condition.notify_all()

        if not state.slots and _FOLLOW_UP_ORDER_STATE.get(umo) is state:
            _FOLLOW_UP_ORDER_STATE.pop(umo, None)


async def _mark_follow_up_consumed(umo: str, seq: int) -> None:
    await _complete_follow_up_slot(umo, seq, "consumed")


async def _activate_and_wait_follow_up_turn(umo: str, seq: int) -> None:
    state = _FOLLOW_UP_ORDER_STATE.get(umo)
    if state is None:
        return
    async with state.condition:
        slot = state.slots.get(seq)
        if slot is None:
            return
        slot.status = "active"

        # Strict ordering: only the head (`next_turn`) can continue.
        while state.next_turn != seq and seq in state.slots:
            await state.condition.wait()


async def _finish_follow_up_turn(umo: str, seq: int) -> None:
    await _complete_follow_up_slot(umo, seq, "finished")


async def _monitor_follow_up_ticket(
    umo: str,
    receipt: InputReceipt,
    order_seq: int,
) -> None:
    """Release captured ordering only after runtime confirms consumption.

    Args:
        umo: Source whose input arrival order is tracked by Core.
        receipt: Runtime-owned durable-consumption acknowledgment.
        order_seq: Core admission order of this input.
    """
    if await receipt:
        await _mark_follow_up_consumed(umo, order_seq)


def _active_turn_event_id(turn: AgentTurn | None) -> int | None:
    if turn is None:
        return None
    turn_input = getattr(turn, "input", None)
    turn_event = getattr(turn_input, "event", None)
    return id(turn_event) if turn_event is not None else None


def _has_pending_session_turns(turn: AgentTurn | None) -> bool:
    if turn is None:
        return False
    session = getattr(turn, "session", None)
    pending_count = getattr(session, "pending_turn_count", 0)
    return isinstance(pending_count, int) and pending_count > 0


def _has_blocking_order_slot(
    state: _FollowUpOrderState,
    *,
    active_turn_id: str | None,
    active_event_id: int | None,
) -> bool:
    """Return whether an earlier queued turn must precede any new input."""
    for slot in state.slots.values():
        if slot.status in ("consumed", "finished"):
            continue
        # Once a queued event becomes the active turn itself, it no longer blocks
        # subsequent plain-text inputs from steering that active turn.
        if active_event_id is not None and slot.event_id == active_event_id:
            continue
        # Pending steering tickets targeting the same active turn execute in FIFO
        # order within that turn and do not block later plain-text steering.
        if (
            slot.status == "pending"
            and active_turn_id is not None
            and slot.target_run_id == active_turn_id
        ):
            continue
        return True
    return False


def _create_deferred_capture(
    umo: str,
    event: AstrMessageEvent,
    *,
    target_run_id: str | None,
) -> FollowUpCapture:
    seq = _allocate_follow_up_order(
        umo,
        status="deferred",
        event_id=id(event),
        target_run_id=target_run_id,
    )
    return FollowUpCapture(
        umo=umo,
        receipt=None,
        order_seq=seq,
        monitor_task=None,
        target_run_id=target_run_id,
    )


def _is_event_stopped(event: AstrMessageEvent) -> bool:
    is_stopped = getattr(event, "is_stopped", None)
    if callable(is_stopped) and is_stopped():
        return True
    get_extra = getattr(event, "get_extra", None)
    return bool(callable(get_extra) and get_extra("agent_stop_requested"))


def try_capture_follow_up(
    event: AstrMessageEvent, turn: AgentTurn | None = None
) -> FollowUpCapture | None:
    """Offer plain-text input to the active turn, or reserve arrival order if deferred.

    Media attachments, quoted replies, and structured inputs cannot be collapsed to
    plain-text steering and must run as separate turns. When such a turn is deferred
    behind an active run, an ordering barrier prevents later plain-text inputs from
    steering ahead of it.

    Args:
        event: Incoming message whose caller identity and role remain explicit.
        turn: Exact active turn of this input's selected conversation.

    Returns:
        A capture to await (for steering or ordering), or None when this input can
        open a separate turn immediately without ordering coordination.
    """
    if _is_event_stopped(event):
        return None
    if isinstance(event, AgentWakeupEvent) and event.agent_session is not None:
        return None

    umo = event.unified_msg_origin
    active_turn_id = turn.id if turn is not None else None
    active_event_id = _active_turn_event_id(turn)
    state = _FOLLOW_UP_ORDER_STATE.get(umo)
    blocked = (
        state is not None
        and _has_blocking_order_slot(
            state,
            active_turn_id=active_turn_id,
            active_event_id=active_event_id,
        )
    ) or _has_pending_session_turns(turn)

    if turn is None:
        if not blocked:
            return None
        return _create_deferred_capture(umo, event, target_run_id=None)

    if not blocked and extract_plain_steering_text(event) is not None:
        receipt = turn.steer(
            AgentInput(
                event=event,
                permissions=AgentPermissions.from_event(event),
            )
        )
        if receipt is not None:
            seq = _allocate_follow_up_order(
                umo,
                status="pending",
                event_id=id(event),
                target_run_id=turn.id,
            )
            monitor = asyncio.create_task(_monitor_follow_up_ticket(umo, receipt, seq))
            return FollowUpCapture(
                umo=umo,
                receipt=receipt,
                order_seq=seq,
                monitor_task=monitor,
                target_run_id=turn.id,
            )

    return _create_deferred_capture(umo, event, target_run_id=turn.id)


async def prepare_follow_up_capture(capture: FollowUpCapture) -> tuple[bool, bool]:
    """Return `(consumed_marked, activated)` for internal stage branch handling."""
    if capture.receipt is not None and await capture.receipt:
        await _mark_follow_up_consumed(capture.umo, capture.order_seq)
        return True, False
    await _activate_and_wait_follow_up_turn(capture.umo, capture.order_seq)
    return False, True


async def finalize_follow_up_capture(
    capture: FollowUpCapture,
    *,
    activated: bool,
    consumed_marked: bool,
) -> None:
    try:
        # Best-effort cancellation: monitor task is auxiliary and should not leak.
        if capture.monitor_task is not None and not capture.monitor_task.done():
            capture.monitor_task.cancel()
            try:
                await capture.monitor_task
            except asyncio.CancelledError:
                pass
    finally:
        if activated:
            await _finish_follow_up_turn(capture.umo, capture.order_seq)
        elif not consumed_marked:
            await _mark_follow_up_consumed(capture.umo, capture.order_seq)
