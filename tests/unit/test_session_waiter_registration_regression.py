"""Replacing a waiter must preserve the newer registration (issue #9996)."""

import asyncio

import pytest

from astrbot.core.utils import session_waiter as waiters


@pytest.mark.asyncio
@pytest.mark.parametrize("ending", ["stop", "timeout", "cancel"])
@pytest.mark.parametrize("shared_filter", [False, True])
async def test_old_waiter_cleanup_preserves_replacement(
    monkeypatch, mock_event, ending, shared_filter
):
    """Keep the replacement dispatchable when the previous wait terminates.

    Args:
        monkeypatch: Isolate the module's registration containers.
        mock_event: Message with the shared session origin.
        ending: Completion, timeout, or caller cancellation of the first wait.
        shared_filter: Whether both registrations reuse one filter instance.
    """
    monkeypatch.setattr(waiters, "USER_SESSIONS", {})
    monkeypatch.setattr(waiters, "FILTERS", [])
    old_filter = waiters.DefaultSessionFilter()
    new_filter = old_filter if shared_filter else waiters.DefaultSessionFilter()
    received = []

    @waiters.session_waiter(timeout=60)
    async def handler(controller, event):
        received.append(event)
        controller.stop()

    tasks = []
    registrations = []
    session_id = mock_event.unified_msg_origin
    try:
        old_task = asyncio.create_task(handler(mock_event, session_filter=old_filter))
        tasks.append(old_task)
        # register_wait publishes its registration before its first suspension.
        await asyncio.sleep(0)
        old_waiter = waiters.USER_SESSIONS[session_id]
        registrations.append(old_waiter)

        new_task = asyncio.create_task(handler(mock_event, session_filter=new_filter))
        tasks.append(new_task)
        await asyncio.sleep(0)
        new_waiter = waiters.USER_SESSIONS[session_id]
        registrations.append(new_waiter)
        assert new_waiter is not old_waiter

        if ending == "stop":
            old_waiter.session_controller.stop()
            await old_task
        elif ending == "timeout":
            holding_event = old_waiter.session_controller.current_event
            assert holding_event is not None
            # Exercise the real timeout path without waiting for wall-clock time.
            await old_waiter.session_controller._holding(holding_event, 0)
            with pytest.raises(TimeoutError):
                await old_task
        else:
            old_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await old_task

        assert waiters.USER_SESSIONS.get(session_id) is new_waiter
        assert not new_task.done()
        assert waiters.FILTERS == [new_filter]

        await waiters.SessionWaiter.trigger(session_id, mock_event)
        await new_task
        assert received == [mock_event]
        assert session_id not in waiters.USER_SESSIONS
        assert waiters.FILTERS == []
    finally:
        for waiter in registrations:
            waiter.session_controller.stop()
            if event := waiter.session_controller.current_event:
                event.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.sleep(0)
