"""Session waiters release their owned timers and handler tasks."""

import asyncio
import logging

import pytest
import pytest_asyncio

from astrbot.core.utils import session_waiter as waiters


@pytest.fixture(autouse=True)
def isolate_waiters(monkeypatch):
    """Keep registrations local to each test."""
    monkeypatch.setattr(waiters, "USER_SESSIONS", {})
    monkeypatch.setattr(waiters, "FILTERS", [])


@pytest_asyncio.fixture
async def owned_tasks():
    """Drain test-owned tasks even when a regression assertion fails."""
    tasks = set()
    yield tasks
    for task in tasks:
        if not task.done():
            task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("future_state", ["pending", "completed", "cancelled"])
@pytest.mark.parametrize("keep_count", [1, 3])
async def test_stop_cancels_all_holders_and_prevents_new_keep(
    owned_tasks, future_state, keep_count
):
    """Stop timers for every future state and reject post-stop extensions.

    Args:
        owned_tasks: Tasks retained for reliable test cleanup.
        future_state: State of the controller future when stop is called.
        keep_count: Number of successive hold periods to create.
    """
    controller = waiters.SessionController()
    for _ in range(keep_count):
        controller.keep(60, reset_timeout=True)
        owned_tasks.update(controller.tasks)
        await asyncio.sleep(0)

    if future_state == "completed":
        controller.future.set_result(None)
    elif future_state == "cancelled":
        controller.future.cancel()
    controller.stop()

    assert all(task.done() or task.cancelling() for task in owned_tasks)
    await asyncio.gather(*owned_tasks, return_exceptions=True)
    assert not controller.tasks

    controller.keep(60, reset_timeout=True)
    owned_tasks.update(controller.tasks)
    assert not controller.tasks


@pytest.mark.asyncio
@pytest.mark.parametrize("ending", ["stop", "cancel", "timeout"])
async def test_registration_drains_holders_and_running_handler(
    owned_tasks, mock_event, ending
):
    """Finish cleanup before returning from a stopped registration.

    Args:
        owned_tasks: Tasks retained for reliable test cleanup.
        mock_event: Input dispatched to the real waiter handler.
        ending: Normal completion, caller cancellation, or timeout.
    """
    entered = asyncio.Event()
    handler_finished = asyncio.Event()

    @waiters.session_waiter(timeout=60)
    async def handler(controller, _event):
        controller.keep(60, reset_timeout=True)
        controller.keep(5)
        owned_tasks.update(controller.tasks)
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            # Cancellation must also wait for asynchronous handler cleanup.
            await asyncio.sleep(0)
            handler_finished.set()

    registration = asyncio.create_task(handler(mock_event))
    owned_tasks.add(registration)
    await asyncio.sleep(0)
    session_id = mock_event.unified_msg_origin
    waiter = waiters.USER_SESSIONS[session_id]
    owned_tasks.update(waiter.session_controller.tasks)
    trigger = asyncio.create_task(waiters.SessionWaiter.trigger(session_id, mock_event))
    owned_tasks.add(trigger)
    await entered.wait()
    assert waiter.curr_task is not None
    owned_tasks.add(waiter.curr_task)

    if ending == "stop":
        waiter.session_controller.stop()
        await registration
    elif ending == "cancel":
        registration.cancel()
        with pytest.raises(asyncio.CancelledError):
            await registration
    else:
        event = waiter.session_controller.current_event
        assert event is not None
        await waiter.session_controller._holding(event, 0)
        with pytest.raises(TimeoutError):
            await registration

    assert handler_finished.is_set()
    assert waiter.curr_task.done()
    assert not waiter.session_controller.tasks
    assert all(
        task.done() for task in owned_tasks if task not in {registration, trigger}
    )
    assert session_id not in waiters.USER_SESSIONS
    assert waiters.FILTERS == []
    await trigger


@pytest.mark.asyncio
async def test_registration_cleanup_is_bounded_for_resistant_handler(
    owned_tasks, mock_event, monkeypatch, caplog
):
    """Retain ownership when a handler suppresses cancellation past cleanup.

    Args:
        owned_tasks: Tasks retained for reliable test cleanup.
        mock_event: Input dispatched to the real waiter handler.
        monkeypatch: Allow the application logger to reach pytest's log capture.
        caplog: Captured warning describing incomplete handler cancellation.
    """
    monkeypatch.setattr(waiters.logger, "propagate", True)
    entered = asyncio.Event()
    cancellation_seen = asyncio.Event()
    release = asyncio.Event()

    @waiters.session_waiter(timeout=60)
    async def handler(_controller, _event):
        entered.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            cancellation_seen.set()
            await release.wait()

    registration = asyncio.create_task(handler(mock_event))
    owned_tasks.add(registration)
    await asyncio.sleep(0)
    session_id = mock_event.unified_msg_origin
    waiter = waiters.USER_SESSIONS[session_id]
    holders = set(waiter.session_controller.tasks)
    owned_tasks.update(holders)
    trigger = asyncio.create_task(waiters.SessionWaiter.trigger(session_id, mock_event))
    owned_tasks.add(trigger)
    await entered.wait()
    handler_task = waiter.curr_task
    assert handler_task is not None
    owned_tasks.add(handler_task)

    try:
        waiter.session_controller.stop()
        done, _ = await asyncio.wait({registration}, timeout=3)
        assert registration in done
        await registration
        assert cancellation_seen.is_set()
        assert waiter.curr_task is handler_task and not handler_task.done()
        assert all(task.done() for task in holders)
        assert not waiter.session_controller.tasks
        assert session_id not in waiters.USER_SESSIONS
        assert waiters.FILTERS == []
        assert (
            waiters.logger.name,
            logging.WARNING,
            "Session waiter cleanup timed out with 1 task(s) still running.",
        ) in caplog.record_tuples
    finally:
        release.set()
    await trigger
