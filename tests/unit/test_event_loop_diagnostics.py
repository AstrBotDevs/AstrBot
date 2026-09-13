import asyncio
import io
import threading
import time

import pytest

from astrbot.core.utils import event_loop_diagnostics as diagnostics


def test_load_event_loop_diagnostic_settings_defaults():
    """Default settings enable lag monitoring and the stack dump watchdog."""
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
            "event_loop_watchdog",
        ]
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_event_loop_watchdog_stops_worker_thread():
    """The event loop watchdog should stop its worker thread on shutdown."""
    task = asyncio.create_task(
        diagnostics.event_loop_watchdog(timeout=10, interval=0.01)
    )
    await asyncio.sleep(0.02)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    assert not any(
        thread.name == "event_loop_watchdog" for thread in threading.enumerate()
    )


@pytest.mark.asyncio
async def test_event_loop_watchdog_writes_rotating_log(tmp_path):
    """The watchdog should write to and rotate its log file."""
    # The watchdog must dump the event loop thread's stack while the loop is
    # stalled inside this test. Loaded CI runners can otherwise catch the loop
    # in pytest machinery before the blocking sleep starts or after it ends,
    # so the stall is retried until a dump lands inside this test.
    dump = io.StringIO()
    task = asyncio.create_task(
        diagnostics.event_loop_watchdog(
            timeout=0.02,
            interval=0.005,
            dump_file=dump,
        )
    )
    # Let the watchdog task start and refresh its heartbeat before stalling,
    # so a dump cannot fire before the loop reaches the blocking sleep below.
    await asyncio.sleep(0.05)
    for _ in range(5):
        time.sleep(0.15)  # noqa: ASYNC251 - Intentionally block the event loop.
        await asyncio.sleep(0.02)
        if "test_event_loop_diagnostics.py" in dump.getvalue():
            break
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    dump_content = dump.getvalue()
    assert "Event loop stalled for" in dump_content
    assert "test_event_loop_diagnostics.py" in dump_content

    # Opening an oversized log rotates it aside first. Test the helper
    # directly: going through a live watchdog would make rotation timing
    # depend on thread scheduling.
    log_path = tmp_path / "logs" / "event_loop_watchdog.log"
    log_path.parent.mkdir()
    rotated_path = log_path.with_name("event_loop_watchdog.log.1")
    for _ in range(5):
        if rotated_path.exists():
            rotated_path.unlink()
        log_path.write_text("x" * 8, encoding="utf-8")
        # Virus scanners and similar tools briefly hold freshly written files
        # open on Windows, which makes the rotate below fail with WinError 32.
        time.sleep(0.2)  # noqa: ASYNC251 - Let transient file locks expire.
        with diagnostics._open_watchdog_log_file(log_path, max_bytes=4) as output:
            output.write("new dump\n")
        if rotated_path.exists() and rotated_path.read_text(
            encoding="utf-8"
        ) == "x" * 8:
            break
    assert rotated_path.read_text(encoding="utf-8") == "x" * 8
    assert log_path.read_text(encoding="utf-8") == "new dump\n"


@pytest.mark.asyncio
async def test_event_loop_watchdog_survives_dump_failure(tmp_path, monkeypatch):
    """The watchdog should keep running after stack dump failures."""
    log_path = tmp_path / "event_loop_watchdog.log"
    dumped = threading.Event()
    attempts = 0

    def flaky_open(path, max_bytes):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("boom")
        dumped.set()
        return path.open("a", encoding="utf-8")

    monkeypatch.setattr(diagnostics, "_open_watchdog_log_file", flaky_open)

    task = asyncio.create_task(
        diagnostics.event_loop_watchdog(
            timeout=0.02,
            interval=0.005,
            dump_path=log_path,
        )
    )
    await asyncio.sleep(0)
    time.sleep(0.06)  # noqa: ASYNC251 - Intentionally block the event loop.
    assert dumped.is_set()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    assert attempts >= 2
