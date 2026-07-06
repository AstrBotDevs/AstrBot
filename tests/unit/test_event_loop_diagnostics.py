import asyncio

import pytest

from astrbot.core.utils import event_loop_diagnostics as diagnostics


def test_load_event_loop_diagnostic_settings_defaults():
    """Default settings enable lag monitoring and stack dump watchdog."""
    settings = diagnostics.load_event_loop_diagnostic_settings()

    assert settings.lag_monitor_enabled is True
    assert settings.lag_monitor_interval == diagnostics.DEFAULT_LAG_MONITOR_INTERVAL
    assert settings.lag_monitor_threshold == diagnostics.DEFAULT_LAG_MONITOR_THRESHOLD
    assert settings.watchdog_enabled is True
    assert settings.watchdog_interval == diagnostics.DEFAULT_WATCHDOG_INTERVAL
    assert settings.watchdog_timeout == diagnostics.DEFAULT_WATCHDOG_TIMEOUT
    assert settings.watchdog_log_max_bytes == diagnostics.DEFAULT_WATCHDOG_LOG_MAX_BYTES


@pytest.mark.asyncio
async def test_create_event_loop_diagnostic_tasks_defaults():
    """Default diagnostics should create both event loop diagnostic tasks."""
    tasks = diagnostics.create_event_loop_diagnostic_tasks()

    try:
        assert [task.get_name() for task in tasks] == [
            "event_loop_lag_monitor",
            "event_loop_faulthandler_watchdog",
        ]
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


@pytest.mark.asyncio
async def test_faulthandler_watchdog_survives_dump_failure(tmp_path, monkeypatch):
    """The watchdog should keep running after faulthandler arm failures."""
    log_path = tmp_path / "event_loop_watchdog.log"
    armed_again = asyncio.Event()
    calls = []

    class FakeFaultHandler:
        def cancel_dump_traceback_later(self):
            calls.append("cancel")

        def dump_traceback_later(self, timeout, repeat, file):
            calls.append(("dump", timeout, repeat, file.name))
            if len([call for call in calls if isinstance(call, tuple)]) == 1:
                raise RuntimeError("boom")
            armed_again.set()

    fake_faulthandler = FakeFaultHandler()
    monkeypatch.setattr(diagnostics, "faulthandler", fake_faulthandler)

    task = asyncio.create_task(
        diagnostics.faulthandler_event_loop_watchdog(
            timeout=10,
            interval=0.01,
            dump_path=log_path,
        )
    )
    await asyncio.wait_for(armed_again.wait(), timeout=1)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    dump_calls = [call for call in calls if isinstance(call, tuple)]
    assert len(dump_calls) >= 2
