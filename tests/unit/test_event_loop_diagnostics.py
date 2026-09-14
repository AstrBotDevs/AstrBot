import asyncio
import threading

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
async def test_event_loop_watchdog_writes_rotating_log(tmp_path, monkeypatch):
    """The watchdog should write to and rotate its log file."""
    log_path = tmp_path / "logs" / "event_loop_watchdog.log"
    log_path.parent.mkdir()
    log_path.write_text("x" * 8, encoding="utf-8")
    sampled = threading.Event()
    print_stack = diagnostics.traceback.print_stack

    def record_stack(*args, **kwargs):
        print_stack(*args, **kwargs)
        sampled.set()

    monkeypatch.setattr(diagnostics.traceback, "print_stack", record_stack)

    task = asyncio.create_task(
        diagnostics.event_loop_watchdog(
            timeout=0.02,
            interval=0.005,
            dump_path=log_path,
            max_bytes=4,
        )
    )
    try:
        await asyncio.sleep(0)
        # Keep this coroutine on the event-loop stack until the real dump is
        # sampled, instead of assuming the worker runs within a fixed 50ms.
        assert sampled.wait(timeout=5), "Watchdog did not capture a thread stack"
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    log_content = log_path.read_text(encoding="utf-8")
    assert "Event loop stalled for" in log_content
    main_thread_dump = log_content.split("\nThread", 2)[1]
    assert "test_event_loop_diagnostics.py" in main_thread_dump
    assert "test_event_loop_watchdog_writes_rotating_log" in main_thread_dump
    assert (
        log_path.with_name("event_loop_watchdog.log.1").read_text(encoding="utf-8")
        == "x" * 8
    )


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
    try:
        await asyncio.sleep(0)
        # The worker must retry while the event loop is still blocked.
        assert dumped.wait(timeout=5), "Watchdog did not retry the failed dump"
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert attempts >= 2
