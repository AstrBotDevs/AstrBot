"""Runtime-owned coordination for Agent follow-up messages."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol

from astrbot import logger


class FollowUpEvent(Protocol):
    """The event data needed to capture a follow-up message."""

    @property
    def unified_msg_origin(self) -> str:
        """Return the session identity used to scope the active Agent run."""
        ...

    def get_sender_id(self) -> str | None: ...

    def get_message_str(self) -> str: ...

    def get_message_outline(self) -> str: ...


class FollowUpTicket(Protocol):
    """The minimal ticket interface produced by an Agent runner."""

    seq: int
    consumed: bool
    resolved: asyncio.Event


@dataclass(slots=True)
class FollowUpCapture:
    """One request-scoped follow-up capture owned by a coordinator."""

    umo: str
    ticket: FollowUpTicket
    order_seq: int
    monitor_task: asyncio.Task[None]
    target_run_id: str | None = None
    order_key: str | tuple[str, str] | None = None

    def _state_key(self) -> str | tuple[str, str]:
        return self.order_key if self.order_key is not None else self.umo


class FollowUpCoordinator:
    """Track active Agent runs and ordered follow-up captures for one runtime."""

    def __init__(self) -> None:
        self._active_runners: dict[str | tuple[str, str], Any] = {}
        self._order_states: dict[str | tuple[str, str], dict[str, object]] = {}
        self._monitor_tasks: set[asyncio.Task[None]] = set()

    def register_active_runner(
        self,
        umo: str,
        runner: Any,
        *,
        sender_id: str | None = None,
    ) -> None:
        """Make a runner eligible to receive a matching follow-up message."""
        self._active_runners[self._runner_key(umo, sender_id)] = runner

    def unregister_active_runner(
        self,
        umo: str,
        runner: Any,
        *,
        sender_id: str | None = None,
    ) -> None:
        """Remove a runner only when it is still the active one for its key."""
        key = self._runner_key(umo, sender_id)
        if self._active_runners.get(key) is runner:
            self._active_runners.pop(key, None)
        self._release_order_state_if_idle(key)

    @staticmethod
    def _runner_key(umo: str, sender_id: str | None) -> str | tuple[str, str]:
        if sender_id:
            return (umo, sender_id)
        return umo

    def try_capture(self, event: FollowUpEvent) -> FollowUpCapture | None:
        """Capture an inbound message when it belongs to an active Agent run."""
        sender_id = event.get_sender_id()
        if not sender_id:
            return None
        umo = event.unified_msg_origin
        runner = self._active_runners.get((umo, sender_id))
        order_key: str | tuple[str, str] = (umo, sender_id)
        if runner is None:
            runner = self._active_runners.get(umo)
            order_key = umo
        if runner is None:
            return None
        runner_event = getattr(getattr(runner, "run_context", None), "context", None)
        runner_event = getattr(runner_event, "event", None)
        if runner_event is None:
            return None
        active_sender_id = runner_event.get_sender_id()
        if not active_sender_id or active_sender_id != sender_id:
            return None
        if runner_event.get_extra("agent_stop_requested"):
            return None

        ticket = runner.follow_up(message_text=self._event_follow_up_text(event))
        if ticket is None:
            return None
        order_seq = self._allocate_order(order_key)
        monitor_task = asyncio.create_task(
            self._monitor_ticket(order_key, ticket, order_seq),
            name="follow_up_ticket_monitor",
        )
        self._monitor_tasks.add(monitor_task)
        monitor_task.add_done_callback(self._monitor_tasks.discard)
        logger.info(
            "Captured follow-up message for active agent run, umo=%s, order_seq=%s",
            event.unified_msg_origin,
            order_seq,
        )
        runner_message = getattr(runner_event, "message_obj", None)
        runner_message_id = getattr(runner_message, "message_id", None)
        return FollowUpCapture(
            umo=event.unified_msg_origin,
            ticket=ticket,
            order_seq=order_seq,
            monitor_task=monitor_task,
            target_run_id=str(runner_message_id)
            if runner_message_id is not None
            else None,
            order_key=order_key,
        )

    async def prepare_capture(self, capture: FollowUpCapture) -> tuple[bool, bool]:
        """Wait for a captured ticket and reserve its ordered continuation slot."""
        await capture.ticket.resolved.wait()
        if capture.ticket.consumed:
            await self._mark_consumed(capture._state_key(), capture.order_seq)
            return True, False
        await self._activate_and_wait(capture._state_key(), capture.order_seq)
        return False, True

    async def finalize_capture(
        self,
        capture: FollowUpCapture,
        *,
        activated: bool,
        consumed_marked: bool,
    ) -> None:
        """Release all state retained for a completed or abandoned capture."""
        if not capture.monitor_task.done():
            capture.monitor_task.cancel()
            try:
                await capture.monitor_task
            except asyncio.CancelledError:
                pass

        if activated:
            await self._finish(capture._state_key(), capture.order_seq)
        elif not consumed_marked:
            await self._mark_consumed(capture._state_key(), capture.order_seq)

    async def terminate(self) -> None:
        """Cancel pending monitors and discard state held by this runtime."""
        tasks = list(self._monitor_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._monitor_tasks.clear()
        self._active_runners.clear()
        self._order_states.clear()

    @staticmethod
    def _event_follow_up_text(event: FollowUpEvent) -> str:
        text = (event.get_message_str() or "").strip()
        return text or event.get_message_outline().strip()

    def _get_order_state(self, key: str | tuple[str, str]) -> dict[str, object]:
        state = self._order_states.get(key)
        if state is None:
            state = {
                "condition": asyncio.Condition(),
                "statuses": {},
                "next_order": 0,
                "next_turn": 0,
            }
            self._order_states[key] = state
        return state

    def _allocate_order(self, key: str | tuple[str, str]) -> int:
        state = self._get_order_state(key)
        next_order = state["next_order"]
        assert isinstance(next_order, int)
        state["next_order"] = next_order + 1
        statuses = state["statuses"]
        assert isinstance(statuses, dict)
        statuses[next_order] = "pending"
        return next_order

    @staticmethod
    def _advance_turn_locked(state: dict[str, object]) -> None:
        statuses = state["statuses"]
        assert isinstance(statuses, dict)
        next_turn = state["next_turn"]
        assert isinstance(next_turn, int)
        while statuses.get(next_turn) in ("consumed", "finished"):
            statuses.pop(next_turn, None)
            next_turn += 1
        state["next_turn"] = next_turn

    def _release_order_state_if_idle(self, key: str | tuple[str, str]) -> None:
        state = self._order_states.get(key)
        if state is None or self._active_runners.get(key) is not None:
            return
        statuses = state["statuses"]
        assert isinstance(statuses, dict)
        if not statuses:
            self._order_states.pop(key, None)

    async def _mark_consumed(self, key: str | tuple[str, str], sequence: int) -> None:
        state = self._order_states.get(key)
        if state is None:
            return
        condition = state["condition"]
        assert isinstance(condition, asyncio.Condition)
        async with condition:
            statuses = state["statuses"]
            assert isinstance(statuses, dict)
            if sequence in statuses and statuses[sequence] != "finished":
                statuses[sequence] = "consumed"
            self._advance_turn_locked(state)
            condition.notify_all()
        self._release_order_state_if_idle(key)

    async def _activate_and_wait(
        self, key: str | tuple[str, str], sequence: int
    ) -> None:
        state = self._order_states.get(key)
        if state is None:
            return
        condition = state["condition"]
        assert isinstance(condition, asyncio.Condition)
        async with condition:
            statuses = state["statuses"]
            assert isinstance(statuses, dict)
            if sequence in statuses:
                statuses[sequence] = "active"
            while state["next_turn"] != sequence:
                await condition.wait()

    async def _finish(self, key: str | tuple[str, str], sequence: int) -> None:
        state = self._order_states.get(key)
        if state is None:
            return
        condition = state["condition"]
        assert isinstance(condition, asyncio.Condition)
        async with condition:
            statuses = state["statuses"]
            assert isinstance(statuses, dict)
            if sequence in statuses:
                statuses[sequence] = "finished"
            self._advance_turn_locked(state)
            condition.notify_all()
        self._release_order_state_if_idle(key)

    async def _monitor_ticket(
        self,
        key: str | tuple[str, str],
        ticket: FollowUpTicket,
        order_seq: int,
    ) -> None:
        await ticket.resolved.wait()
        if ticket.consumed:
            await self._mark_consumed(key, order_seq)
