"""Regression tests for terminating captured follow-up turns."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from astrbot.core.agent.runners.tool_loop_agent_runner import FollowUpTicket
from astrbot.core.pipeline.process_stage import follow_up


class StubEvent:
    """Minimal event accepted by the follow-up capture registry."""

    unified_msg_origin = "Perrin:FriendMessage:1"
    message_obj = SimpleNamespace(message_id="incoming")

    def get_sender_id(self) -> str:
        return "1"

    def get_message_str(self) -> str:
        return "queued follow-up"

    def get_message_outline(self) -> str:
        return "queued follow-up"

    def get_extra(self, _key: str):
        return None


class StubRunner:
    """Runner that leaves follow-up tickets unresolved until termination."""

    def __init__(self, event: StubEvent):
        self.run_context = SimpleNamespace(context=SimpleNamespace(event=event))
        self.request_stop = Mock()
        self.tickets: list[FollowUpTicket] = []

    def follow_up(self, *, message_text: str) -> FollowUpTicket:
        ticket = FollowUpTicket(seq=len(self.tickets), text=message_text)
        self.tickets.append(ticket)
        return ticket


@pytest.fixture(autouse=True)
def clean_follow_up_globals():
    follow_up._ACTIVE_AGENT_RUNNERS.clear()
    follow_up._FOLLOW_UP_ORDER_STATE.clear()
    yield
    follow_up._ACTIVE_AGENT_RUNNERS.clear()
    follow_up._FOLLOW_UP_ORDER_STATE.clear()


@pytest.mark.asyncio
async def test_termination_wakes_and_discards_unresolved_capture():
    event = StubEvent()
    runner = StubRunner(event)
    follow_up.register_active_runner(event.unified_msg_origin, runner)
    capture = follow_up.try_capture_follow_up(event)
    assert capture is not None
    waiter = asyncio.create_task(follow_up.prepare_follow_up_capture(capture))
    await asyncio.sleep(0)

    assert await follow_up.terminate_follow_up_session(event.unified_msg_origin) == 1
    assert await asyncio.wait_for(waiter, timeout=0.2) == (True, False)
    await follow_up.finalize_follow_up_capture(
        capture,
        activated=False,
        consumed_marked=True,
    )


@pytest.mark.asyncio
async def test_termination_releases_turn_waiting_behind_earlier_capture():
    event = StubEvent()
    runner = StubRunner(event)
    follow_up.register_active_runner(event.unified_msg_origin, runner)
    first = follow_up.try_capture_follow_up(event)
    second = follow_up.try_capture_follow_up(event)
    assert first is not None and second is not None
    second.ticket.resolved.set()
    waiter = asyncio.create_task(follow_up.prepare_follow_up_capture(second))
    await asyncio.sleep(0)

    assert await follow_up.terminate_follow_up_session(event.unified_msg_origin) == 2
    assert await asyncio.wait_for(waiter, timeout=0.2) == (True, False)
    for capture in (first, second):
        await follow_up.finalize_follow_up_capture(
            capture,
            activated=False,
            consumed_marked=True,
        )


@pytest.mark.asyncio
async def test_unresolved_capture_times_out(monkeypatch):
    monkeypatch.setattr(follow_up, "FOLLOW_UP_WAIT_TIMEOUT_SECONDS", 0.01)
    event = StubEvent()
    runner = StubRunner(event)
    follow_up.register_active_runner(event.unified_msg_origin, runner)
    capture = follow_up.try_capture_follow_up(event)
    assert capture is not None

    assert await follow_up.prepare_follow_up_capture(capture) == (True, False)
    await follow_up.finalize_follow_up_capture(
        capture,
        activated=False,
        consumed_marked=True,
    )
