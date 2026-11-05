"""Behavioral contract for runtime turns, independent of native model execution."""

import asyncio
from types import SimpleNamespace

import pytest

from astrbot.core.agent.input import PlainInput
from astrbot.core.agent.output import PlainOutput
from astrbot.core.agent.runtime import (
    AgentInput,
    AgentPermissions,
    AgentRole,
    AgentSession,
    InputReceipt,
    SessionState,
    TurnResult,
    TurnStatus,
    get_agent_permissions,
)


class RecordingSession(AgentSession):
    def __init__(self):
        super().__init__("conversation", "test:FriendMessage:alice")
        self.entered = asyncio.Queue()
        self.release = asyncio.Event()
        self.saved = []

    async def execute_turn(self, turn):
        await self.entered.put(turn)
        await self.release.wait()
        self.saved.append(turn.id)
        assert turn.input.content is not None
        return TurnResult(content=(PlainOutput(text=turn.input.content[0].text),))

    async def history(self):
        return list(self.saved)


def make_input(text="hello", *, sender="alice", role=AgentRole.MEMBER):
    event = SimpleNamespace(
        unified_msg_origin="test:FriendMessage:alice",
        get_sender_id=lambda: sender,
        plugins_name=None,
    )
    return AgentInput(event, AgentPermissions(role), [PlainInput(text=text)])


@pytest.mark.asyncio
async def test_queued_cancellation_does_not_release_an_earlier_turn():
    session = RecordingSession()
    assert session.state == SessionState.IDLE
    first = await session.run_turn(make_input("first"))
    assert session.state == SessionState.QUEUED
    assert session.pending_turn_count == 1
    await session.entered.get()
    assert session.state == SessionState.RUNNING
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(first.result(), 0.01)
    assert not first.done
    second = await first.follow_up(make_input("second"))
    third = await first.follow_up(make_input("third"))
    assert session.pending_turn_count == 2
    await second.cancel()
    await asyncio.sleep(0)
    assert session.entered.empty()
    session.release.set()
    assert (await first.result()).text == "first"
    assert (await third.result()).text == "third"
    assert (await second.result()).status == TurnStatus.CANCELLED
    assert session.saved == [first.id, third.id]
    assert session.state == SessionState.IDLE
    await session.close()
    assert session.state == SessionState.CLOSED


@pytest.mark.asyncio
async def test_close_cancels_active_and_queued_turns_without_deleting_history():
    session = RecordingSession()
    first = await session.run_turn(make_input())
    await session.entered.get()
    second = await first.follow_up(make_input())
    await session.close()
    assert (await first.result()).status == TurnStatus.CANCELLED
    assert (await second.result()).status == TurnStatus.CANCELLED
    assert not session.saved
    with pytest.raises(ValueError, match="closed"):
        await session.run_turn(make_input())


@pytest.mark.asyncio
async def test_steering_cannot_cross_sender_or_permission_boundaries():
    session = RecordingSession()
    turn = await session.run_turn(make_input())
    await session.entered.get()
    session.steer_turn = lambda target, input: (
        asyncio.get_running_loop().create_future()
    )
    assert turn.steer(make_input(sender="bob")) is None
    assert turn.steer(make_input(role=AgentRole.ADMIN)) is None
    receipt = turn.steer(make_input())
    assert receipt is not None
    receipt.set_result(False)
    session.release.set()
    await turn.result()
    assert turn.steer(make_input()) is None
    await session.close()


def test_permissions_respect_api_key_administrator_ceiling():
    event = SimpleNamespace(role="admin", get_extra=lambda key: False)
    assert not AgentPermissions.from_event(event).is_admin
    event.get_extra = lambda key: None
    assert AgentPermissions.from_event(event).is_admin


@pytest.mark.asyncio
async def test_cancelled_receipt_waiter_cannot_lose_a_committed_input():
    receipt = InputReceipt()

    async def wait():
        return await receipt

    waiter = asyncio.create_task(wait())
    await asyncio.sleep(0)
    waiter.cancel()
    await asyncio.gather(waiter, return_exceptions=True)
    assert not receipt.done()
    receipt.resolve(True)
    assert await receipt


def test_explicit_permissions_override_mutable_event_role():
    context = SimpleNamespace(
        context=SimpleNamespace(
            permissions=AgentPermissions(AgentRole.MEMBER),
            event=SimpleNamespace(role="admin", get_extra=lambda _: None),
        )
    )
    assert not get_agent_permissions(context).is_admin


@pytest.mark.asyncio
async def test_repeated_close_waits_for_cleanup_without_cancelling_it_twice():
    session = RecordingSession()
    cleaning, release_cleanup = asyncio.Event(), asyncio.Event()

    async def execute(turn):
        await session.entered.put(turn)
        try:
            await asyncio.Event().wait()
        finally:
            cleaning.set()
            await release_cleanup.wait()

    session.execute_turn = execute
    turn = await session.run_turn(make_input())
    await session.entered.get()
    first_close = asyncio.create_task(session.close())
    await asyncio.wait_for(cleaning.wait(), 1)
    second_close = asyncio.create_task(session.close())
    await asyncio.sleep(0)
    assert not first_close.done() and not second_close.done()
    release_cleanup.set()
    await asyncio.wait_for(asyncio.gather(first_close, second_close), 1)
    assert (await turn.result()).status == TurnStatus.CANCELLED
