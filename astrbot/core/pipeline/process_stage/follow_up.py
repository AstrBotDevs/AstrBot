from __future__ import annotations

import asyncio
from dataclasses import dataclass

from astrbot.core.agent.runtime import (
    AgentInput,
    AgentPermissions,
    AgentTurn,
    InputReceipt,
)
from astrbot.core.platform.astr_message_event import AstrMessageEvent

_FOLLOW_UP_ORDER_STATE: dict[str, dict[str, object]] = {}
"""UMO-level follow-up order state.

State fields:
- `statuses`: seq -> {"pending"|"active"|"consumed"|"finished"}
- `next_order`: monotonically increasing sequence allocator
- `next_turn`: next sequence allowed to proceed when not consumed
"""


@dataclass(slots=True)
class FollowUpCapture:
    umo: str
    receipt: InputReceipt
    order_seq: int
    monitor_task: asyncio.Task[None]
    target_run_id: str | None = None


def _get_follow_up_order_state(umo: str) -> dict[str, object]:
    state = _FOLLOW_UP_ORDER_STATE.get(umo)
    if state is None:
        state = {
            "condition": asyncio.Condition(),
            # Sequence status map for strict in-order resume after unresolved follow-ups.
            "statuses": {},
            # Stable allocator for arrival order; never decreases for the same UMO state.
            "next_order": 0,
            # The sequence currently allowed to continue main internal flow.
            "next_turn": 0,
        }
        _FOLLOW_UP_ORDER_STATE[umo] = state
    return state


def _advance_follow_up_turn_locked(state: dict[str, object]) -> None:
    # Skip slots that are already handled, and stop at the first unfinished slot.
    statuses = state["statuses"]
    assert isinstance(statuses, dict)
    next_turn = state["next_turn"]
    assert isinstance(next_turn, int)

    while True:
        curr = statuses.get(next_turn)
        if curr in ("consumed", "finished"):
            statuses.pop(next_turn, None)
            next_turn += 1
            continue
        break

    state["next_turn"] = next_turn


def _allocate_follow_up_order(umo: str) -> int:
    state = _get_follow_up_order_state(umo)
    next_order = state["next_order"]
    assert isinstance(next_order, int)
    seq = next_order
    state["next_order"] = seq + 1
    statuses = state["statuses"]
    assert isinstance(statuses, dict)
    statuses[seq] = "pending"
    return seq


async def _mark_follow_up_consumed(umo: str, seq: int) -> None:
    state = _FOLLOW_UP_ORDER_STATE.get(umo)
    if not state:
        return
    condition = state["condition"]
    assert isinstance(condition, asyncio.Condition)
    async with condition:
        statuses = state["statuses"]
        assert isinstance(statuses, dict)
        if seq in statuses and statuses[seq] != "finished":
            statuses[seq] = "consumed"
        _advance_follow_up_turn_locked(state)
        condition.notify_all()

        if not statuses:
            _FOLLOW_UP_ORDER_STATE.pop(umo, None)


async def _activate_and_wait_follow_up_turn(umo: str, seq: int) -> None:
    state = _FOLLOW_UP_ORDER_STATE.get(umo)
    if not state:
        return
    condition = state["condition"]
    assert isinstance(condition, asyncio.Condition)
    async with condition:
        statuses = state["statuses"]
        assert isinstance(statuses, dict)
        if seq in statuses:
            statuses[seq] = "active"

        # Strict ordering: only the head (`next_turn`) can continue.
        while True:
            next_turn = state["next_turn"]
            assert isinstance(next_turn, int)
            if next_turn == seq:
                break
            await condition.wait()


async def _finish_follow_up_turn(umo: str, seq: int) -> None:
    state = _FOLLOW_UP_ORDER_STATE.get(umo)
    if not state:
        return
    condition = state["condition"]
    assert isinstance(condition, asyncio.Condition)
    async with condition:
        statuses = state["statuses"]
        assert isinstance(statuses, dict)
        if seq in statuses:
            statuses[seq] = "finished"
        _advance_follow_up_turn_locked(state)
        condition.notify_all()

        if not statuses:
            _FOLLOW_UP_ORDER_STATE.pop(umo, None)


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


def try_capture_follow_up(
    event: AstrMessageEvent, turn: AgentTurn | None = None
) -> FollowUpCapture | None:
    """Offer input to the exact active turn without inspecting a native runner.

    Args:
        event: Incoming message whose caller identity and role remain explicit.
        turn: Exact active turn of this input's selected conversation.

    Returns:
        A capture to await, or None when this input must open a separate turn.
    """
    if turn is None or event.get_extra("agent_stop_requested"):
        return None
    receipt = turn.steer(
        AgentInput(
            event=event,
            permissions=AgentPermissions.from_event(event),
        )
    )
    if receipt is None:
        return None
    seq = _allocate_follow_up_order(event.unified_msg_origin)
    monitor = asyncio.create_task(
        _monitor_follow_up_ticket(event.unified_msg_origin, receipt, seq)
    )
    return FollowUpCapture(
        umo=event.unified_msg_origin,
        receipt=receipt,
        order_seq=seq,
        monitor_task=monitor,
        target_run_id=turn.id,
    )


async def prepare_follow_up_capture(capture: FollowUpCapture) -> tuple[bool, bool]:
    """Return `(consumed_marked, activated)` for internal stage branch handling."""
    if await capture.receipt:
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
    # Best-effort cancellation: monitor task is auxiliary and should not leak.
    if not capture.monitor_task.done():
        capture.monitor_task.cancel()
        try:
            await capture.monitor_task
        except asyncio.CancelledError:
            pass

    if activated:
        await _finish_follow_up_turn(capture.umo, capture.order_seq)
    elif not consumed_marked:
        await _mark_follow_up_consumed(capture.umo, capture.order_seq)
