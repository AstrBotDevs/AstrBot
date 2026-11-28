import asyncio
import os
import signal
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core import initial_loader

pytestmark = [
    pytest.mark.skipif(sys.platform == "win32", reason="POSIX signal handling only"),
    pytest.mark.asyncio,
]


def _setup(monkeypatch, stop_side_effect=None):
    """Builds an InitialLoader with a mocked lifecycle and a fake dashboard.

    The fake dashboard behaves like Hypercorn's ``serve``: it runs until the
    shutdown event is set and records whether it was cancelled instead.
    """
    running = asyncio.Event()
    state = {"dashboard_cancelled": False, "dashboard_closed": False}

    lifecycle = MagicMock()
    lifecycle.initialize = AsyncMock()
    lifecycle.dashboard_shutdown_event = asyncio.Event()

    core_stopped = asyncio.Event()

    async def core_start():
        running.set()
        await core_stopped.wait()

    lifecycle.start = MagicMock(side_effect=core_start)

    async def stop():
        # stop() ends the core tasks and then lets the WebUI shut down.
        core_stopped.set()
        lifecycle.dashboard_shutdown_event.set()

    lifecycle.stop = AsyncMock(side_effect=stop_side_effect or stop)
    monkeypatch.setattr(
        initial_loader, "AstrBotCoreLifecycle", MagicMock(return_value=lifecycle)
    )

    async def serve():
        try:
            await lifecycle.dashboard_shutdown_event.wait()
            state["dashboard_closed"] = True
        except asyncio.CancelledError:
            state["dashboard_cancelled"] = True
            raise

    dashboard = MagicMock()
    dashboard.run.side_effect = serve
    monkeypatch.setattr(
        initial_loader, "AstrBotDashboard", MagicMock(return_value=dashboard)
    )

    db = MagicMock()
    db.engine.dispose = AsyncMock()
    loader = initial_loader.InitialLoader(db, MagicMock())
    return loader.start, lifecycle, db, running, state


async def _sigterm_while_running(start, running):
    start_task = asyncio.create_task(start())
    await asyncio.wait_for(running.wait(), 1)
    os.kill(os.getpid(), signal.SIGTERM)
    await asyncio.wait_for(start_task, 5)
    assert not start_task.cancelled()


async def test_sigterm_shuts_down_dashboard_gracefully(monkeypatch):
    start, lifecycle, db, running, state = _setup(monkeypatch)
    await _sigterm_while_running(start, running)

    lifecycle.stop.assert_awaited_once()
    assert state == {"dashboard_cancelled": False, "dashboard_closed": True}
    db.engine.dispose.assert_awaited()


async def test_repeated_sigterm_does_not_interrupt_stop(monkeypatch):
    async def stop():
        os.kill(os.getpid(), signal.SIGTERM)
        await asyncio.sleep(0.05)

    start, lifecycle, db, running, state = _setup(monkeypatch, stop)
    await _sigterm_while_running(start, running)

    lifecycle.stop.assert_awaited_once()
    assert state["dashboard_closed"]
    db.engine.dispose.assert_awaited()


async def test_db_disposed_when_stop_raises(monkeypatch):
    async def stop():
        raise RuntimeError("provider terminate failed")

    start, _, db, running, state = _setup(monkeypatch, stop)
    await _sigterm_while_running(start, running)

    assert state["dashboard_closed"]
    db.engine.dispose.assert_awaited()


async def test_db_disposed_when_stop_hangs(monkeypatch):
    monkeypatch.setattr(initial_loader, "STOP_TIMEOUT", 0.1)
    monkeypatch.setattr(initial_loader, "DASHBOARD_SHUTDOWN_TIMEOUT", 0.1)

    async def stop():
        # A teardown that ignores cancellation, like a stuck platform adapter.
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            await asyncio.sleep(0.5)

    start, _, db, running, state = _setup(monkeypatch, stop)
    await _sigterm_while_running(start, running)

    assert state["dashboard_closed"]
    db.engine.dispose.assert_awaited()


async def test_sigterm_during_initialize_disposes_db(monkeypatch):
    start, lifecycle, db, _, _ = _setup(monkeypatch)
    initializing = asyncio.Event()

    async def initialize():
        initializing.set()
        await asyncio.Event().wait()

    lifecycle.initialize.side_effect = initialize
    start_task = asyncio.create_task(start())
    await asyncio.wait_for(initializing.wait(), 1)
    os.kill(os.getpid(), signal.SIGTERM)
    await asyncio.wait_for(start_task, 1)

    lifecycle.stop.assert_not_called()
    db.engine.dispose.assert_awaited_once()
