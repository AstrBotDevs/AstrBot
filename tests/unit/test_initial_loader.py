import asyncio
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_initial_loader_stops_core_when_runtime_raises_keyboard_interrupt(
    monkeypatch,
):
    from astrbot.core import initial_loader

    calls = []

    class FakeCoreLifecycle:
        def __init__(self, log_broker, db):
            self.dashboard_shutdown_event = asyncio.Event()

        async def initialize(self):
            calls.append("initialize")

        async def start(self):
            calls.append("start")
            raise KeyboardInterrupt

        async def stop(self):
            calls.append("stop")

    class FakeDashboard:
        def __init__(self, *args, **kwargs):
            pass

        def run(self):
            return None

    monkeypatch.setattr(initial_loader, "AstrBotCoreLifecycle", FakeCoreLifecycle)
    monkeypatch.setattr(initial_loader, "AstrBotDashboard", FakeDashboard)

    loader = initial_loader.InitialLoader(SimpleNamespace(), SimpleNamespace())

    with pytest.raises(KeyboardInterrupt):
        await loader.start()

    assert calls == ["initialize", "start", "stop"]


@pytest.mark.asyncio
async def test_initial_loader_stops_core_when_runtime_task_is_cancelled(monkeypatch):
    from astrbot.core import initial_loader

    calls = []

    class FakeCoreLifecycle:
        def __init__(self, log_broker, db):
            self.dashboard_shutdown_event = asyncio.Event()

        async def initialize(self):
            calls.append("initialize")

        async def start(self):
            calls.append("start")
            raise asyncio.CancelledError

        async def stop(self):
            calls.append("stop")

    class FakeDashboard:
        def __init__(self, *args, **kwargs):
            pass

        def run(self):
            return None

    monkeypatch.setattr(initial_loader, "AstrBotCoreLifecycle", FakeCoreLifecycle)
    monkeypatch.setattr(initial_loader, "AstrBotDashboard", FakeDashboard)

    loader = initial_loader.InitialLoader(SimpleNamespace(), SimpleNamespace())

    await loader.start()

    assert calls == ["initialize", "start", "stop"]
