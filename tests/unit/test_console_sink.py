"""Regression tests for blocked and broken console output."""

import asyncio
import io
import json
import logging
import os
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from astrbot.core.log import LogManager
from astrbot.core.utils.console_sink import BoundedConsoleSink


@pytest.mark.asyncio
async def test_full_console_queue_keeps_event_loop_responsive():
    """Preserve responsiveness under sustained backpressure and report drops."""
    entered = threading.Event()
    release = threading.Event()

    class BlockedStream(io.StringIO):
        def write(self, text):
            entered.set()
            release.wait(5)
            return super().write(text)

    stream = BlockedStream()
    sink = BoundedConsoleSink(stream, capacity=2)
    failsafe = threading.Timer(3, release.set)
    failsafe.daemon = True
    failsafe.start()
    try:
        sink.write("first\n")
        assert await asyncio.to_thread(entered.wait, 1)
        started = time.monotonic()

        async def emit_and_yield():
            for index in range(500):
                sink.write(f"record {index}\n")
            await asyncio.sleep(0)
            return "responsive"

        assert await asyncio.wait_for(emit_and_yield(), 1) == "responsive"
        assert time.monotonic() - started < 1
        assert sink.dropped == 498
        assert sink._queue.qsize() == 2
        release.set()
        await asyncio.wait_for(asyncio.to_thread(sink._queue.join), 1)
        assert stream.getvalue().startswith("first\nrecord 0\n")
        assert "Skipped 498 console log records" in stream.getvalue()
        assert "record 1\n" in stream.getvalue()
        sink.write("recovered\n")
        await asyncio.wait_for(asyncio.to_thread(sink._queue.join), 1)
        assert stream.getvalue().endswith("recovered\n")
    finally:
        failsafe.cancel()
        release.set()
        sink.close()
    assert not sink._thread.is_alive()
    sink.close()
    sink.write("ignored after close\n")
    assert sink._queue.empty()


@pytest.mark.parametrize("failure", ["write", "flush"])
def test_broken_console_does_not_propagate_errors(failure):
    """Keep stream exceptions out of the producer thread."""

    class BrokenStream(io.StringIO):
        def write(self, text):
            if failure == "write":
                raise OSError("broken pipe")
            return super().write(text)

        def flush(self):
            if failure == "flush":
                raise OSError("broken pipe")
            return super().flush()

    sink = BoundedConsoleSink(BrokenStream())
    try:
        sink.write("one\n")
        sink.write("two\n")
        sink._queue.join()
        assert sink._thread.is_alive()
    finally:
        sink.close()
    assert not sink._thread.is_alive()


def test_raw_output_handles_partial_writes_and_unicode():
    """Preserve encoded records when raw output accepts only part of a write."""

    class PartialRawStream(io.RawIOBase):
        def __init__(self):
            self.data = bytearray()

        def writable(self):
            return True

        def write(self, data):
            length = min(3, len(data))
            self.data.extend(data[:length])
            return length

    raw = PartialRawStream()
    with io.TextIOWrapper(io.BufferedWriter(raw), encoding="utf-8") as stream:
        sink = BoundedConsoleSink(stream)
        try:
            sink.write("你好 🌟\none\n")
            sink.write("two\n")
            sink._queue.join()
            assert raw.data.decode("utf-8") == "你好 🌟\none\ntwo\n"
        finally:
            sink.close()
        assert not stream.closed


@pytest.mark.parametrize("capacity", [0, -1])
def test_invalid_capacity_is_rejected(capacity):
    """Never silently create an unbounded queue."""
    with pytest.raises(ValueError, match="positive"):
        BoundedConsoleSink(io.StringIO(), capacity=capacity)


def test_log_level_reconfiguration_reuses_console_writer(monkeypatch):
    """Cover both console sink registration paths without spawning new writers."""
    fake_loguru = MagicMock()
    fake_loguru.add.return_value = 7
    monkeypatch.setattr("astrbot.core.log._loguru", fake_loguru)
    monkeypatch.setattr(LogManager, "_configured", False)
    monkeypatch.setattr(LogManager, "_console_output", None)
    monkeypatch.setattr(LogManager, "_console_sink_id", None)
    monkeypatch.setattr(LogManager, "_file_sink_id", None)
    monkeypatch.setattr(LogManager, "_plugin_logger_names", set())
    monkeypatch.setattr(LogManager, "_plugin_level_overrides", {})
    try:
        LogManager._setup_loguru()
        writer = LogManager._console_output
        for level in ("INFO", "WARNING", "DEBUG"):
            LogManager.configure_logger(
                logging.Logger("console-test"), {"log_level": level}
            )
        assert [call.args[0] for call in fake_loguru.add.call_args_list] == [writer] * 4
        assert writer._thread.is_alive()
        assert LogManager._console_output is writer
    finally:
        if LogManager._console_output is not None:
            LogManager._console_output.close()


@pytest.mark.parametrize("unbuffered", [False, True])
def test_exit_with_unread_stdout_pipe(unbuffered):
    """A blocked daemon must not hold stdout's buffer lock during shutdown."""
    source_path = Path(__file__).parents[2] / "astrbot/core/utils/console_sink.py"
    source = textwrap.dedent(f"""
        import importlib.util
        import os
        import sys
        import time
        spec = importlib.util.spec_from_file_location('console_sink', {str(source_path)!r})
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sink = module.BoundedConsoleSink(sys.stdout, capacity=2)
        for _ in range(10):
            sink.write('x' * 1000000)
        time.sleep(0.2)
        os.write(2, b'ready\\n')
    """)
    command = [sys.executable]
    if unbuffered:
        command.append("-u")
    process = subprocess.Popen(
        [*command, "-c", source], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    try:
        assert process.wait(timeout=5) == 0
        assert process.stderr.read() == b"ready\n"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        process.stdout.close()
        process.stderr.close()


def test_blocked_console_preserves_file_and_dashboard_logs(tmp_path):
    """Exercise actual Loguru registration, level changes, and independent sinks."""
    source = textwrap.dedent("""
        import asyncio
        import io
        import json
        import sys
        import threading
        import time
        from pathlib import Path
        from astrbot.core.log import LogBroker, LogManager, _loguru
        from astrbot.core.utils.console_sink import BoundedConsoleSink

        entered = threading.Event()
        release = threading.Event()
        class BlockedStream(io.StringIO):
            def write(self, text):
                entered.set()
                release.wait(5)
                return super().write(text)

        async def main():
            _loguru.remove()
            LogManager._console_output.close()
            LogManager._configured = False
            LogManager._console_sink_id = None
            stream = BlockedStream()
            LogManager._console_output = BoundedConsoleSink(stream, capacity=2)
            log = LogManager.GetLogger('console-regression')
            broker = LogBroker()
            LogManager.set_queue_handler(log, broker)
            config = {'log_level': 'INFO', 'log_file': {'enable': True, 'path': sys.argv[1]}}
            LogManager.configure_logger(log, config)
            failsafe = threading.Timer(3, release.set)
            failsafe.daemon = True
            failsafe.start()
            try:
                log.info('initial record')
                assert await asyncio.to_thread(entered.wait, 1)
                started = time.monotonic()
                LogManager.configure_logger(log, config)
                log.debug('filtered debug record')
                for index in range(100):
                    log.info('regression record %s', index)
                await asyncio.sleep(0)
                elapsed = time.monotonic() - started
                assert elapsed < 1, elapsed
                assert LogManager._console_output.dropped > 0
                _loguru.remove(LogManager._file_sink_id)
                text = Path(sys.argv[1]).read_text(encoding='utf-8')
                assert 'initial record' in text
                assert all('regression record ' + str(i) + '\\n' in text for i in range(100))
                assert 'filtered debug record' not in text
                assert len(broker.log_cache) == 101
                print(json.dumps({'heartbeat_seconds': elapsed, 'file_records': 101, 'dashboard_records': len(broker.log_cache)}))
            finally:
                failsafe.cancel()
                release.set()
                _loguru.remove()
                LogManager._console_output.close()

        asyncio.run(main())
    """)
    root = Path(__file__).parents[2]
    env = {**os.environ, "ASTRBOT_ROOT": str(tmp_path), "PYTHONPATH": str(root)}
    result = subprocess.run(
        [sys.executable, "-c", source, str(tmp_path / "console-regression.log")],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.splitlines()[-1])
    assert report["file_records"] == report["dashboard_records"] == 101
