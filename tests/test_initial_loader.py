import asyncio
import os
import signal
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core import initial_loader


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signal handling only")
@pytest.mark.asyncio
async def test_sigterm_triggers_graceful_shutdown_once(monkeypatch):
    running = asyncio.Event()

    async def run_forever():
        running.set()
        await asyncio.Event().wait()

    lifecycle = MagicMock()
    lifecycle.initialize = AsyncMock()
    lifecycle.start = MagicMock(side_effect=run_forever)

    async def stop():
        # A second SIGTERM during shutdown must not start another shutdown.
        os.kill(os.getpid(), signal.SIGTERM)
        await asyncio.sleep(0.05)

    lifecycle.stop = AsyncMock(side_effect=stop)
    monkeypatch.setattr(
        initial_loader, "AstrBotCoreLifecycle", MagicMock(return_value=lifecycle)
    )
    dashboard = MagicMock()
    dashboard.run.return_value = run_forever()
    monkeypatch.setattr(
        initial_loader, "AstrBotDashboard", MagicMock(return_value=dashboard)
    )

    loader = initial_loader.InitialLoader(MagicMock(), MagicMock())
    start_task = asyncio.create_task(loader.start())
    await asyncio.wait_for(running.wait(), 1)

    os.kill(os.getpid(), signal.SIGTERM)
    await asyncio.wait_for(start_task, 1)

    lifecycle.stop.assert_awaited_once()
    assert not start_task.cancelled()
