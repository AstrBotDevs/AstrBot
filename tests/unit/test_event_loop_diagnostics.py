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
        diagnostics.WATCHDOG_LOG_PATH_ENV,
        diagnostics.WATCHDOG_LOG_MAX_BYTES_ENV,
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
    assert settings.watchdog_log_max_bytes == diagnostics.DEFAULT_WATCHDOG_LOG_MAX_BYTES


def test_load_event_loop_diagnostic_settings_from_env(monkeypatch):
    """Environment variables override event loop diagnostic settings."""
    _clear_diagnostic_env(monkeypatch)
    monkeypatch.setenv(diagnostics.LAG_MONITOR_ENABLED_ENV, "0")
    monkeypatch.setenv(diagnostics.WATCHDOG_ENABLED_ENV, "yes")
    monkeypatch.setenv(diagnostics.WATCHDOG_TIMEOUT_ENV, "30")
    monkeypatch.setenv(diagnostics.WATCHDOG_LOG_PATH_ENV, "/tmp/astrbot-watchdog.log")
    monkeypatch.setenv(diagnostics.WATCHDOG_LOG_MAX_BYTES_ENV, "2048")

    settings = diagnostics.load_event_loop_diagnostic_settings()

    assert settings.lag_monitor_enabled is False
    assert settings.watchdog_enabled is True
    assert settings.watchdog_timeout == 30
    assert settings.watchdog_log_path.as_posix() == "/tmp/astrbot-watchdog.log"
    assert settings.watchdog_log_max_bytes == 2048


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

    assert any(isinstance(call, tuple) and call[0] == "dump" for call in calls)
    assert calls[-1] == "cancel"


@pytest.mark.asyncio
async def test_faulthandler_watchdog_writes_rotating_log(tmp_path, monkeypatch):
    """The faulthandler watchdog should write to and rotate its log file."""
    log_path = tmp_path / "logs" / "event_loop_watchdog.log"
    log_path.parent.mkdir()
    log_path.write_text("x" * 8, encoding="utf-8")
    calls = []

    class FakeFaultHandler:
        def cancel_dump_traceback_later(self):
            calls.append("cancel")

        def dump_traceback_later(self, timeout, repeat, file):
            calls.append(("dump", timeout, repeat, file.name))
            file.write("watchdog dump\n")
            file.flush()

    fake_faulthandler = FakeFaultHandler()
    monkeypatch.setattr(diagnostics, "faulthandler", fake_faulthandler)

    task = asyncio.create_task(
        diagnostics.faulthandler_event_loop_watchdog(
            timeout=10,
            interval=1,
            dump_path=log_path,
            max_bytes=4,
        )
    )
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    assert log_path.read_text(encoding="utf-8") == "watchdog dump\n"
    assert log_path.with_name("event_loop_watchdog.log.1").read_text(
        encoding="utf-8"
    ) == "x" * 8
    assert any(isinstance(call, tuple) and call[0] == "dump" for call in calls)
