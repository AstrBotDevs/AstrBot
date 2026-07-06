import asyncio

import pytest

from astrbot.core.utils import event_loop_diagnostics as diagnostics


def _clear_diagnostic_env(monkeypatch):
    """Clear event loop diagnostic environment variables.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
    """
    for name in (
        diagnostics.LAG_MONITOR_ENABLED_ENV,
        diagnostics.LAG_MONITOR_INTERVAL_ENV,
        diagnostics.LAG_MONITOR_THRESHOLD_ENV,
        diagnostics.WATCHDOG_ENABLED_ENV,
        diagnostics.WATCHDOG_INTERVAL_ENV,
        diagnostics.WATCHDOG_TIMEOUT_ENV,
    ):
        monkeypatch.delenv(name, raising=False)


def test_load_event_loop_diagnostic_settings_defaults(monkeypatch):
    """Default settings enable low-overhead lag monitoring only."""
    _clear_diagnostic_env(monkeypatch)

    settings = diagnostics.load_event_loop_diagnostic_settings()

    assert settings.lag_monitor_enabled is True
    assert settings.lag_monitor_interval == diagnostics.DEFAULT_LAG_MONITOR_INTERVAL
    assert settings.lag_monitor_threshold == diagnostics.DEFAULT_LAG_MONITOR_THRESHOLD
    assert settings.watchdog_enabled is False


def test_load_event_loop_diagnostic_settings_from_env(monkeypatch):
    """Environment variables override event loop diagnostic settings."""
    _clear_diagnostic_env(monkeypatch)
    monkeypatch.setenv(diagnostics.LAG_MONITOR_ENABLED_ENV, "0")
    monkeypatch.setenv(diagnostics.WATCHDOG_ENABLED_ENV, "yes")
    monkeypatch.setenv(diagnostics.WATCHDOG_TIMEOUT_ENV, "30")

    settings = diagnostics.load_event_loop_diagnostic_settings()

    assert settings.lag_monitor_enabled is False
    assert settings.watchdog_enabled is True
    assert settings.watchdog_timeout == 30


@pytest.mark.asyncio
async def test_create_event_loop_diagnostic_tasks_respects_env(monkeypatch):
    """Disabled lag monitor and watchdog should create no tasks."""
    _clear_diagnostic_env(monkeypatch)
    monkeypatch.setenv(diagnostics.LAG_MONITOR_ENABLED_ENV, "false")
    monkeypatch.setenv(diagnostics.WATCHDOG_ENABLED_ENV, "false")

    tasks = diagnostics.create_event_loop_diagnostic_tasks()

    assert tasks == []


@pytest.mark.asyncio
async def test_create_event_loop_diagnostic_tasks_default_lag_monitor(monkeypatch):
    """Default diagnostics should create only the lag monitor task."""
    _clear_diagnostic_env(monkeypatch)

    tasks = diagnostics.create_event_loop_diagnostic_tasks()

    try:
        assert [task.get_name() for task in tasks] == ["event_loop_lag_monitor"]
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_faulthandler_watchdog_cancels_pending_dump(monkeypatch):
    """The faulthandler watchdog should cancel its pending dump on shutdown."""
    calls = []

    class FakeFaultHandler:
        def is_enabled(self):
            calls.append("is_enabled")
            return False

        def enable(self, file):
            calls.append(("enable", file))

        def cancel_dump_traceback_later(self):
            calls.append("cancel")

        def dump_traceback_later(self, timeout, repeat, file):
            calls.append(("dump", timeout, repeat, file))

    fake_faulthandler = FakeFaultHandler()
    monkeypatch.setattr(diagnostics, "faulthandler", fake_faulthandler)

    task = asyncio.create_task(
        diagnostics.faulthandler_event_loop_watchdog(timeout=10, interval=1)
    )
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    assert "is_enabled" in calls
    assert any(isinstance(call, tuple) and call[0] == "dump" for call in calls)
    assert calls[-1] == "cancel"
