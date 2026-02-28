from __future__ import annotations
from astrbot.core.lang import t

import asyncio
from dataclasses import dataclass

from astrbot import logger
from astrbot.core.agent.runners.tool_loop_agent_runner import FollowUpTicket
from astrbot.core.astr_agent_run_util import AgentRunner
from astrbot.core.platform.astr_message_event import AstrMessageEvent

_ACTIVE_AGENT_RUNNERS: dict[str, AgentRunner] = {}
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
    ticket: FollowUpTicket
    order_seq: int
    monitor_task: asyncio.Task[None]


def _event_follow_up_text(event: AstrMessageEvent) -> str:
    text = (event.get_message_str() or "").strip()
    if text:
        return text
    return event.get_message_outline().strip()


def register_active_runner(umo: str, runner: AgentRunner) -> None:
    _ACTIVE_AGENT_RUNNERS[umo] = runner


def unregister_active_runner(umo: str, runner: AgentRunner) -> None:
    if _ACTIVE_AGENT_RUNNERS.get(umo) is runner:
        _ACTIVE_AGENT_RUNNERS.pop(umo, None)


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

        # Release state only when this UMO has no pending statuses and no active runner.
        if not statuses and _ACTIVE_AGENT_RUNNERS.get(umo) is None:
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

        if not statuses and _ACTIVE_AGENT_RUNNERS.get(umo) is None:
            _FOLLOW_UP_ORDER_STATE.pop(umo, None)


async def _monitor_follow_up_ticket(
    umo: str,
    ticket: FollowUpTicket,
    order_seq: int,
) -> None:
    """Advance consumed slots immediately on resolution to avoid wake-order drift."""
    await ticket.resolved.wait()
    if ticket.consumed:
        await _mark_follow_up_consumed(umo, order_seq)


def try_capture_follow_up(event: AstrMessageEvent) -> FollowUpCapture | None:
    sender_id = event.get_sender_id()
    if not sender_id:
        return None
    runner = _ACTIVE_AGENT_RUNNERS.get(event.unified_msg_origin)
    if not runner:
        return None
    runner_event = getattr(getattr(runner.run_context, "context", None), "event", None)
    if runner_event is None:
        return None
    active_sender_id = runner_event.get_sender_id()
    if not active_sender_id or active_sender_id != sender_id:
        return None

    ticket = runner.follow_up(message_text=_event_follow_up_text(event))
    if not ticket:
        return None
    # Allocate strict order at capture time (arrival order), not at wake time.
    order_seq = _allocate_follow_up_order(event.unified_msg_origin)
    monitor_task = asyncio.create_task(
        _monitor_follow_up_ticket(
            event.unified_msg_origin,
            ticket,
            order_seq,
        )
    )
    logger.info(
        t("msg-12767505", res=event.unified_msg_origin, order_seq=order_seq),
    )
    return FollowUpCapture(
        umo=event.unified_msg_origin,
        ticket=ticket,
        order_seq=order_seq,
        monitor_task=monitor_task,
    )


async def prepare_follow_up_capture(capture: FollowUpCapture) -> tuple[bool, bool]:
    """Return `(consumed_marked, activated)` for internal stage branch handling."""
    await capture.ticket.resolved.wait()
    if capture.ticket.consumed:
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
