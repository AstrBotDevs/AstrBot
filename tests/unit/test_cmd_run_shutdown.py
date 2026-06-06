from __future__ import annotations

import asyncio
import signal
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

import astrbot.cli.commands.cmd_run as cmd_run
import astrbot.core as core_module
import astrbot.core.initial_loader as initial_loader_module


@pytest.mark.asyncio
async def test_run_astrbot_stops_gracefully_on_sigterm(monkeypatch):
    set_queue_handler_mock = MagicMock()
    check_dashboard_mock = AsyncMock(return_value=None)
    signal_restore_mock = MagicMock()
    pending_signals: dict[signal.Signals, Callable[[], None]] = {}
    removed_signals: list[signal.Signals] = []
    previous_handlers = {
        signal.SIGINT: object(),
        signal.SIGTERM: object(),
    }

    class FakeLoop:
        def add_signal_handler(self, signum, callback, *args):
            pending_signals[signum] = lambda: callback(*args)

        def remove_signal_handler(self, signum):
            removed_signals.append(signum)
            pending_signals.pop(signum, None)
            return True

    started = asyncio.Event()
    cancelled = asyncio.Event()

    class FakeLoader:
        def __init__(self, db, log_broker):
            self.db = db
            self.log_broker = log_broker

        async def start(self):
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                return

    monkeypatch.setattr(initial_loader_module, "InitialLoader", FakeLoader)
    monkeypatch.setattr(cmd_run, "check_dashboard", check_dashboard_mock)
    fake_loop = FakeLoop()
    monkeypatch.setattr(cmd_run.asyncio, "get_running_loop", lambda: fake_loop)
    monkeypatch.setattr(
        cmd_run.signal, "getsignal", lambda signum: previous_handlers[signum]
    )
    monkeypatch.setattr(cmd_run.signal, "signal", signal_restore_mock)
    monkeypatch.setattr(
        core_module.LogManager, "set_queue_handler", set_queue_handler_mock
    )

    awaitable = asyncio.create_task(cmd_run.run_astrbot(Path("/tmp/astrbot-root")))
    await started.wait()

    assert signal.SIGTERM in pending_signals
    pending_signals[signal.SIGTERM]()

    await awaitable

    assert cancelled.is_set()
    assert set(removed_signals) == {signal.SIGINT, signal.SIGTERM}
    assert signal_restore_mock.call_count == 2
    check_dashboard_mock.assert_awaited_once()
    set_queue_handler_mock.assert_called_once()


@pytest.mark.asyncio
async def test_run_astrbot_suppresses_signal_cancelled_runner(monkeypatch):
    check_dashboard_mock = AsyncMock(return_value=None)
    signal_restore_mock = MagicMock()
    pending_signals: dict[signal.Signals, Callable[[], None]] = {}
    previous_handlers = {
        signal.SIGINT: object(),
        signal.SIGTERM: object(),
    }

    class FakeLoop:
        def add_signal_handler(self, signum, callback, *args):
            pending_signals[signum] = lambda: callback(*args)

        def remove_signal_handler(self, signum):
            pending_signals.pop(signum, None)
            return True

    started = asyncio.Event()

    class FakeLoader:
        def __init__(self, db, log_broker):
            self.db = db
            self.log_broker = log_broker

        async def start(self):
            started.set()
            await asyncio.Event().wait()

    monkeypatch.setattr(initial_loader_module, "InitialLoader", FakeLoader)
    monkeypatch.setattr(cmd_run, "check_dashboard", check_dashboard_mock)
    monkeypatch.setattr(cmd_run.asyncio, "get_running_loop", lambda: FakeLoop())
    monkeypatch.setattr(
        cmd_run.signal, "getsignal", lambda signum: previous_handlers[signum]
    )
    monkeypatch.setattr(cmd_run.signal, "signal", signal_restore_mock)
    monkeypatch.setattr(core_module.LogManager, "set_queue_handler", MagicMock())

    awaitable = asyncio.create_task(cmd_run.run_astrbot(Path("/tmp/astrbot-root")))
    await started.wait()

    pending_signals[signal.SIGTERM]()

    await awaitable

    check_dashboard_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_astrbot_cancels_runner_when_parent_is_cancelled(monkeypatch):
    check_dashboard_mock = AsyncMock(return_value=None)
    signal_restore_mock = MagicMock()
    previous_handlers = {
        signal.SIGINT: object(),
        signal.SIGTERM: object(),
    }

    class FakeLoop:
        def add_signal_handler(self, _signum, _callback, *_args):
            _ = (_signum, _callback, _args)

        def remove_signal_handler(self, _signum):
            _ = _signum
            return True

    started = asyncio.Event()
    cancelled = asyncio.Event()
    shutdown_complete = asyncio.Event()

    class FakeLoader:
        def __init__(self, db, log_broker):
            self.db = db
            self.log_broker = log_broker

        async def start(self):
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise
            finally:
                await asyncio.sleep(0)
                shutdown_complete.set()

    monkeypatch.setattr(initial_loader_module, "InitialLoader", FakeLoader)
    monkeypatch.setattr(cmd_run, "check_dashboard", check_dashboard_mock)
    monkeypatch.setattr(cmd_run.asyncio, "get_running_loop", lambda: FakeLoop())
    monkeypatch.setattr(
        cmd_run.signal, "getsignal", lambda signum: previous_handlers[signum]
    )
    monkeypatch.setattr(cmd_run.signal, "signal", signal_restore_mock)
    monkeypatch.setattr(core_module.LogManager, "set_queue_handler", MagicMock())

    awaitable = asyncio.create_task(cmd_run.run_astrbot(Path("/tmp/astrbot-root")))
    await started.wait()

    awaitable.cancel()

    with pytest.raises(asyncio.CancelledError):
        await awaitable

    assert cancelled.is_set()
    assert shutdown_complete.is_set()
    check_dashboard_mock.assert_awaited_once()
    assert signal_restore_mock.call_count == 2


def test_install_shutdown_signal_handlers_falls_back_and_restores(monkeypatch):
    restored_handlers: list[tuple[signal.Signals, Any]] = []
    installed_handlers: dict[signal.Signals, Callable[[int, object], object]] = {}
    previous_handlers = {
        signal.SIGINT: object(),
        signal.SIGTERM: object(),
    }
    callback = MagicMock()
    scheduled_callbacks: list[tuple[Callable[..., object], tuple[object, ...]]] = []

    class FakeLoop:
        def add_signal_handler(self, _signum, _callback, *_args):
            _ = (_signum, _callback, _args)
            raise NotImplementedError

        def remove_signal_handler(self, _signum):
            _ = _signum
            raise NotImplementedError

        def is_closed(self):
            return False

        def call_soon_threadsafe(self, callback, *args):
            scheduled_callbacks.append((callback, args))

    def fake_signal(signum: signal.Signals, handler: Any) -> object:
        if callable(handler):
            installed_handlers[signum] = cast(Callable[[int, object], object], handler)
        else:
            restored_handlers.append((signum, handler))
        return previous_handlers[signum]

    monkeypatch.setattr(
        cmd_run.signal, "getsignal", lambda signum: previous_handlers[signum]
    )
    monkeypatch.setattr(cmd_run.signal, "signal", fake_signal)

    cleanup = cmd_run._install_shutdown_signal_handlers(cast(Any, FakeLoop()), callback)

    installed_handlers[signal.SIGTERM](signal.SIGTERM, None)
    callback.assert_not_called()
    assert scheduled_callbacks == [(callback, (signal.SIGTERM,))]

    scheduled_callback, scheduled_args = scheduled_callbacks.pop()
    scheduled_callback(*scheduled_args)
    callback.assert_called_once_with(signal.SIGTERM)

    cleanup()

    assert restored_handlers == [
        (signal.SIGINT, previous_handlers[signal.SIGINT]),
        (signal.SIGTERM, previous_handlers[signal.SIGTERM]),
    ]


def test_fallback_signal_handler_ignores_closed_loop(monkeypatch):
    installed_handlers: dict[signal.Signals, Callable[[int, object], object]] = {}
    previous_handlers = {
        signal.SIGINT: object(),
        signal.SIGTERM: object(),
    }
    callback = MagicMock()

    class FakeLoop:
        def add_signal_handler(self, _signum, _callback, *_args):
            _ = (_signum, _callback, _args)
            raise NotImplementedError

        def remove_signal_handler(self, _signum):
            _ = _signum
            raise NotImplementedError

        def is_closed(self):
            return True

        def call_soon_threadsafe(self, _callback, *_args):
            raise AssertionError("closed loop should not schedule callbacks")

    def fake_signal(signum: signal.Signals, handler: Any) -> object:
        if callable(handler):
            installed_handlers[signum] = cast(Callable[[int, object], object], handler)
        return previous_handlers[signum]

    monkeypatch.setattr(
        cmd_run.signal, "getsignal", lambda signum: previous_handlers[signum]
    )
    monkeypatch.setattr(cmd_run.signal, "signal", fake_signal)

    cleanup = cmd_run._install_shutdown_signal_handlers(cast(Any, FakeLoop()), callback)

    installed_handlers[signal.SIGTERM](signal.SIGTERM, None)

    callback.assert_not_called()
    cleanup()


def test_fallback_signal_handler_ignores_call_soon_runtime_error(monkeypatch):
    installed_handlers: dict[signal.Signals, Callable[[int, object], object]] = {}
    previous_handlers = {
        signal.SIGINT: object(),
        signal.SIGTERM: object(),
    }
    callback = MagicMock()

    class FakeLoop:
        def add_signal_handler(self, _signum, _callback, *_args):
            _ = (_signum, _callback, _args)
            raise NotImplementedError

        def remove_signal_handler(self, _signum):
            _ = _signum
            raise NotImplementedError

        def is_closed(self):
            return False

        def call_soon_threadsafe(self, _callback, *_args):
            raise RuntimeError("event loop is closing")

    def fake_signal(signum: signal.Signals, handler: Any) -> object:
        if callable(handler):
            installed_handlers[signum] = cast(Callable[[int, object], object], handler)
        return previous_handlers[signum]

    monkeypatch.setattr(
        cmd_run.signal, "getsignal", lambda signum: previous_handlers[signum]
    )
    monkeypatch.setattr(cmd_run.signal, "signal", fake_signal)

    cleanup = cmd_run._install_shutdown_signal_handlers(cast(Any, FakeLoop()), callback)

    installed_handlers[signal.SIGTERM](signal.SIGTERM, None)

    callback.assert_not_called()
    cleanup()


def test_install_shutdown_signal_handlers_skips_unavailable_signal_api(monkeypatch):
    callback = MagicMock()

    class FakeLoop:
        def add_signal_handler(self, _signum, _callback, *_args):
            _ = (_signum, _callback, _args)
            raise ValueError("signal only works in main thread")

        def remove_signal_handler(self, _signum):
            raise AssertionError("no handlers should be installed")

    monkeypatch.setattr(
        cmd_run.signal,
        "getsignal",
        MagicMock(side_effect=ValueError("signal only works in main thread")),
    )
    monkeypatch.setattr(
        cmd_run.signal,
        "signal",
        MagicMock(side_effect=ValueError("signal only works in main thread")),
    )

    cleanup = cmd_run._install_shutdown_signal_handlers(cast(Any, FakeLoop()), callback)

    cleanup()
    callback.assert_not_called()


def test_cleanup_signal_handlers_skips_none_previous_handler(monkeypatch):
    restored_handlers: list[tuple[signal.Signals, Any]] = []
    callback = MagicMock()

    class FakeLoop:
        def add_signal_handler(self, _signum, _callback, *_args):
            _ = (_signum, _callback, _args)

        def remove_signal_handler(self, _signum):
            _ = _signum
            return True

    def fake_signal(signum: signal.Signals, handler: Any) -> object:
        restored_handlers.append((signum, handler))
        return object()

    monkeypatch.setattr(cmd_run.signal, "getsignal", lambda _signum: None)
    monkeypatch.setattr(cmd_run.signal, "signal", fake_signal)

    cleanup = cmd_run._install_shutdown_signal_handlers(cast(Any, FakeLoop()), callback)

    cleanup()
    assert restored_handlers == []


@pytest.mark.asyncio
async def test_initial_loader_shutdowns_logs_on_initialize_failure(monkeypatch):
    shutdown_mock = AsyncMock(return_value=None)
    lifecycle_instances: list[MagicMock] = []

    class FakeLifecycle:
        def __init__(self, log_broker, db):
            _ = (log_broker, db)
            lifecycle = MagicMock()
            lifecycle.initialize = AsyncMock(side_effect=RuntimeError("boom"))
            lifecycle.stop = AsyncMock()
            lifecycle.start = AsyncMock()
            lifecycle.dashboard_shutdown_event = asyncio.Event()
            lifecycle.astrbot_config = MagicMock()
            lifecycle_instances.append(lifecycle)
            self.__dict__.update(lifecycle.__dict__)

    monkeypatch.setattr(initial_loader_module, "AstrBotCoreLifecycle", FakeLifecycle)
    monkeypatch.setattr(initial_loader_module.LogManager, "shutdown", shutdown_mock)

    loader = initial_loader_module.InitialLoader(MagicMock(), MagicMock())

    await loader.start()

    assert len(lifecycle_instances) == 1
    lifecycle_instances[0].stop.assert_not_awaited()
    shutdown_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_initial_loader_handles_cancellation_during_initialize(monkeypatch):
    shutdown_mock = AsyncMock(return_value=None)
    initialize_started = asyncio.Event()
    lifecycle_instances: list[MagicMock] = []

    class FakeLifecycle:
        def __init__(self, log_broker, db):
            _ = (log_broker, db)
            lifecycle = MagicMock()

            async def initialize():
                initialize_started.set()
                await asyncio.Event().wait()

            lifecycle.initialize = AsyncMock(side_effect=initialize)
            lifecycle.stop = AsyncMock()
            lifecycle.start = AsyncMock()
            lifecycle.dashboard_shutdown_event = asyncio.Event()
            lifecycle.astrbot_config = MagicMock()
            lifecycle_instances.append(lifecycle)
            self.__dict__.update(lifecycle.__dict__)

    monkeypatch.setattr(initial_loader_module, "AstrBotCoreLifecycle", FakeLifecycle)
    monkeypatch.setattr(initial_loader_module.LogManager, "shutdown", shutdown_mock)

    loader = initial_loader_module.InitialLoader(MagicMock(), MagicMock())
    task = asyncio.create_task(loader.start())
    await initialize_started.wait()

    task.cancel()
    await task

    assert len(lifecycle_instances) == 1
    lifecycle_instances[0].stop.assert_not_awaited()
    shutdown_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_initial_loader_stops_core_on_runtime_exception(monkeypatch):
    shutdown_mock = AsyncMock(return_value=None)
    lifecycle_instances: list[MagicMock] = []

    class FakeLifecycle:
        def __init__(self, log_broker, db):
            _ = (log_broker, db)
            lifecycle = MagicMock()
            lifecycle.initialize = AsyncMock(return_value=None)
            lifecycle.stop = AsyncMock()
            lifecycle.start = AsyncMock(side_effect=RuntimeError("run boom"))
            lifecycle.dashboard_shutdown_event = asyncio.Event()
            lifecycle.astrbot_config = MagicMock()
            lifecycle_instances.append(lifecycle)
            self.__dict__.update(lifecycle.__dict__)

    class FakeDashboard:
        def __init__(self, *args, **kwargs):
            _ = (args, kwargs)

        def run(self):
            return None

    monkeypatch.setattr(initial_loader_module, "AstrBotCoreLifecycle", FakeLifecycle)
    monkeypatch.setattr(initial_loader_module, "AstrBotDashboard", FakeDashboard)
    monkeypatch.setattr(initial_loader_module.LogManager, "shutdown", shutdown_mock)

    loader = initial_loader_module.InitialLoader(MagicMock(), MagicMock())

    with pytest.raises(RuntimeError, match="run boom"):
        await loader.start()

    assert len(lifecycle_instances) == 1
    lifecycle_instances[0].stop.assert_awaited_once()
    shutdown_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_initial_loader_preserves_runtime_error_if_stop_fails(monkeypatch):
    shutdown_mock = AsyncMock(return_value=None)
    lifecycle_instances: list[MagicMock] = []

    class FakeLifecycle:
        def __init__(self, log_broker, db):
            _ = (log_broker, db)
            lifecycle = MagicMock()
            lifecycle.initialize = AsyncMock(return_value=None)
            lifecycle.stop = AsyncMock(side_effect=RuntimeError("stop boom"))
            lifecycle.start = AsyncMock(side_effect=RuntimeError("run boom"))
            lifecycle.dashboard_shutdown_event = asyncio.Event()
            lifecycle.astrbot_config = MagicMock()
            lifecycle_instances.append(lifecycle)
            self.__dict__.update(lifecycle.__dict__)

    class FakeDashboard:
        def __init__(self, *args, **kwargs):
            _ = (args, kwargs)

        def run(self):
            return None

    monkeypatch.setattr(initial_loader_module, "AstrBotCoreLifecycle", FakeLifecycle)
    monkeypatch.setattr(initial_loader_module, "AstrBotDashboard", FakeDashboard)
    monkeypatch.setattr(initial_loader_module.LogManager, "shutdown", shutdown_mock)

    loader = initial_loader_module.InitialLoader(MagicMock(), MagicMock())

    with pytest.raises(RuntimeError, match="run boom"):
        await loader.start()

    assert len(lifecycle_instances) == 1
    lifecycle_instances[0].stop.assert_awaited_once()
    shutdown_mock.assert_awaited_once()
