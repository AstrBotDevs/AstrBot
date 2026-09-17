import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.utils import session_waiter as sw


@pytest.fixture(autouse=True)
def _clean_registry():
    sw.USER_SESSIONS.clear()
    sw.FILTERS.clear()
    yield
    sw.USER_SESSIONS.clear()
    sw.FILTERS.clear()


def _waiter(session_id: str) -> sw.SessionWaiter:
    waiter = sw.SessionWaiter(sw.DefaultSessionFilter(), session_id, False)
    sw.FILTERS.append(waiter.session_filter)
    return waiter


async def _finish(waiter: sw.SessionWaiter) -> None:
    """Stop the waiter and let its keep-alive task exit."""
    waiter.session_controller.stop()
    event = waiter.session_controller.current_event
    if event is not None:
        event.set()
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_finished_waiter_keeps_newer_registration_for_same_session():
    old, new = _waiter("same"), _waiter("same")
    handler = AsyncMock()

    task_old = asyncio.create_task(old.register_wait(handler, timeout=10))
    await asyncio.sleep(0)
    task_new = asyncio.create_task(new.register_wait(handler, timeout=10))
    await asyncio.sleep(0)
    assert sw.USER_SESSIONS["same"] is new

    await _finish(old)
    await task_old

    # The newer waiter must still be registered and reachable.
    assert sw.USER_SESSIONS["same"] is new
    assert not new.session_controller.future.done()

    event = MagicMock()
    event.get_messages.return_value = []
    await sw.SessionWaiter.trigger("same", event)
    handler.assert_awaited_once()
    assert handler.await_args.args[0] is new.session_controller

    await _finish(new)
    await task_new
    assert "same" not in sw.USER_SESSIONS


@pytest.mark.asyncio
async def test_finished_waiter_removes_its_own_registration():
    waiter = _waiter("solo")
    task = asyncio.create_task(waiter.register_wait(AsyncMock(), timeout=10))
    await asyncio.sleep(0)
    assert sw.USER_SESSIONS["solo"] is waiter

    await _finish(waiter)
    await task
    assert "solo" not in sw.USER_SESSIONS
    assert waiter.session_filter not in sw.FILTERS
