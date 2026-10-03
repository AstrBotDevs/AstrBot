"""Regression coverage for cleanup with shared session filters."""

import asyncio
from unittest.mock import MagicMock

import pytest

from astrbot.core.platform import AstrMessageEvent
from astrbot.core.utils import session_waiter as waiter_module


@pytest.mark.asyncio
@pytest.mark.parametrize("shared_filter", [False, True])
@pytest.mark.parametrize("completion", ["stop", "timeout", "error", "cancel"])
async def test_cleanup_preserves_other_session_filter_registration(
    monkeypatch: pytest.MonkeyPatch, shared_filter: bool, completion: str
) -> None:
    """Ending one waiter must not remove another session's filter registration."""
    monkeypatch.setattr(waiter_module, "USER_SESSIONS", {})
    monkeypatch.setattr(waiter_module, "FILTERS", [])
    event = MagicMock(spec=AstrMessageEvent)
    event.unified_msg_origin = "test-session"
    other_event = MagicMock(spec=AstrMessageEvent)
    other_event.unified_msg_origin = "other-session"
    old_filter = waiter_module.DefaultSessionFilter()
    new_filter = old_filter if shared_filter else waiter_module.DefaultSessionFilter()
    session_id = old_filter.filter(event)
    other_session_id = new_filter.filter(other_event)
    received: list[AstrMessageEvent] = []

    @waiter_module.session_waiter(timeout=1 if completion == "timeout" else 30)
    async def old_handler(
        controller: waiter_module.SessionController, message: AstrMessageEvent
    ) -> None:
        pytest.fail("The completed handler must not receive new messages")

    @waiter_module.session_waiter(timeout=30)
    async def new_handler(
        controller: waiter_module.SessionController, message: AstrMessageEvent
    ) -> None:
        received.append(message)
        controller.stop()

    registrations: list[asyncio.Task] = []
    controllers: list[waiter_module.SessionController] = []
    try:
        old_task = asyncio.create_task(old_handler(event, old_filter))
        registrations.append(old_task)
        await asyncio.sleep(0)
        old_waiter = waiter_module.USER_SESSIONS[session_id]
        controllers.append(old_waiter.session_controller)

        new_task = asyncio.create_task(new_handler(other_event, new_filter))
        registrations.append(new_task)
        await asyncio.sleep(0)
        replacement = waiter_module.USER_SESSIONS[other_session_id]
        controllers.append(replacement.session_controller)
        assert replacement is not old_waiter

        async with asyncio.timeout(5):
            if completion == "stop":
                old_waiter.session_controller.stop()
                await old_task
            elif completion == "error":
                old_waiter.session_controller.stop(RuntimeError("handler failed"))
                with pytest.raises(RuntimeError, match="handler failed"):
                    await old_task
            elif completion == "cancel":
                old_task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await old_task
            else:
                with pytest.raises(TimeoutError):
                    await old_task

        assert session_id not in waiter_module.USER_SESSIONS
        assert waiter_module.USER_SESSIONS.get(other_session_id) is replacement
        assert waiter_module.FILTERS == [new_filter]
        assert not new_task.done()
        # Dispatch through the filter registry, as the session-control agent does.
        for active_filter in waiter_module.FILTERS:
            await waiter_module.SessionWaiter.trigger(
                active_filter.filter(other_event), other_event
            )
        await asyncio.wait_for(new_task, timeout=5)
        assert received == [other_event]
        assert waiter_module.USER_SESSIONS == {}
        assert waiter_module.FILTERS == []
    finally:
        for task in registrations:
            if not task.done():
                task.cancel()
        await asyncio.gather(*registrations, return_exceptions=True)
        # Drain holding tasks so each parameter case leaves the loop clean.
        holding_tasks = [
            task for controller in controllers for task in controller.tasks
        ]
        for task in holding_tasks:
            task.cancel()
        await asyncio.gather(*holding_tasks, return_exceptions=True)
