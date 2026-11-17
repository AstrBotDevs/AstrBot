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
from types import SimpleNamespace
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
        status = sink.get_status()
        assert status == {
            "capacity": 2,
            "queued_records": 2,
            "unfinished_records": 3,
            "dropped_records": 498,
            "closed": False,
            "writer_alive": True,
        }
        started = time.monotonic()
        assert not await asyncio.to_thread(sink.drain, 0.02)
        assert time.monotonic() - started < 1
        release.set()
        assert await asyncio.to_thread(sink.drain, 1)
        assert stream.getvalue().startswith("first\nrecord 0\n")
        assert "Skipped 498 console log records" in stream.getvalue()
        assert "record 1\n" in stream.getvalue()
        sink.write("recovered\n")
        assert await asyncio.to_thread(sink.drain, 1)
        assert stream.getvalue().endswith("recovered\n")
    finally:
        failsafe.cancel()
        release.set()
        sink.close()
    assert not sink._thread.is_alive()
    sink.close()
    sink.write("ignored after close\n")
    assert sink._queue.empty()


@pytest.mark.parametrize("timeout", [-1, float("inf"), float("nan")])
def test_invalid_drain_timeout_is_rejected(timeout):
    """Keep the explicit drain API bounded for every accepted argument."""
    sink = BoundedConsoleSink(io.StringIO())
    try:
        with pytest.raises(ValueError, match="finite and nonnegative"):
            sink.drain(timeout)
    finally:
        sink.close()


def test_close_drains_full_queue_before_discarding():
    """Preserve queued records if a temporarily blocked stream recovers in budget."""
    entered = threading.Event()
    release = threading.Event()

    class SlowStream(io.StringIO):
        def write(self, text):
            entered.set()
            release.wait(5)
            return super().write(text)

    stream = SlowStream()
    sink = BoundedConsoleSink(stream, capacity=2)
    sink.write("first\n")
    assert entered.wait(1)
    sink.write("second\n")
    sink.write("third\n")
    recovered = threading.Timer(0.02, release.set)
    recovered.start()
    try:
        sink.close()
        assert stream.getvalue() == "first\nsecond\nthird\n"
        assert sink.get_status()["dropped_records"] == 0
        assert sink.drain(0)
        assert not sink._thread.is_alive()
    finally:
        release.set()
        recovered.cancel()
        sink.close()


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
        assert sink.drain(timeout=1)
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
    with io.TextIOWrapper(
        io.BufferedWriter(raw), encoding="utf-8", newline="\n"
    ) as stream:
        sink = BoundedConsoleSink(stream)
        try:
            sink.write("你好 🌟\none\n")
            sink.write("two\n")
            assert sink.drain(timeout=1)
            assert raw.data.decode("utf-8") == "你好 🌟\none\ntwo\n"
        finally:
            sink.close()
        assert not stream.closed


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16", "iso2022_jp"])
@pytest.mark.parametrize("newline", [None, "\n", "\r\n", "\r"])
def test_console_preserves_text_stream_state(encoding, newline):
    """Match direct writes, including an encoder already used before logging."""
    expected = io.BytesIO()
    actual = io.BytesIO()
    with (
        io.TextIOWrapper(expected, encoding=encoding, newline=newline) as reference,
        io.TextIOWrapper(actual, encoding=encoding, newline=newline) as stream,
    ):
        reference.write("prefix\n")
        reference.flush()
        stream.write("prefix\n")
        stream.flush()
        sink = BoundedConsoleSink(stream)
        try:
            for message in ("日本語\n", "two\r\n", "three\n"):
                reference.write(message)
                reference.flush()
                sink.write(message)
            assert sink.drain(timeout=1)
            assert actual.getvalue() == expected.getvalue()
            assert sink.encoding == stream.encoding
        finally:
            sink.close()


@pytest.mark.parametrize("errors", ["replace", "backslashreplace", "ignore"])
def test_console_preserves_encoding_error_policy(errors):
    """Retain the configured text stream's treatment of unencodable content."""
    data = io.BytesIO()
    with io.TextIOWrapper(
        data, encoding="ascii", errors=errors, newline="\n"
    ) as stream:
        sink = BoundedConsoleSink(stream)
        try:
            sink.write("你好\n")
            assert sink.drain(timeout=1)
            assert data.getvalue() == "你好\n".encode("ascii", errors)
        finally:
            sink.close()


@pytest.mark.parametrize(
    ("native_ansi", "tty"), [(True, True), (False, True), (False, False)]
)
def test_windows_console_adaptation(monkeypatch, native_ansi, tty):
    """Enable VT, convert legacy console colors, and preserve pipe colors."""
    colorama = pytest.importorskip("colorama.ansitowin32")
    monkeypatch.setattr(colorama, "os", SimpleNamespace(name="nt", environ={}))
    monkeypatch.setattr(colorama, "winapi_test", lambda: True)
    enable_vt = MagicMock(return_value=native_ansi)
    monkeypatch.setattr(colorama, "enable_vt_processing", enable_vt)
    monkeypatch.setattr(colorama, "winterm", None)

    class Console(io.StringIO):
        def fileno(self):
            return 17

        def isatty(self):
            return tty

    stream = Console()
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "__stdout__", stream)
    sink = BoundedConsoleSink(stream)
    try:
        sink.write("\x1b[32mgreen\x1b[0m\n")
        assert sink.drain(timeout=1)
        assert stream.getvalue() == (
            "green\n" if tty and not native_ansi else "\x1b[32mgreen\x1b[0m\n"
        )
        enable_vt.assert_called_once_with(17)
    finally:
        sink.close()


def test_regular_close_keeps_standard_streams(monkeypatch):
    """Restrict standard-stream isolation to process shutdown under backpressure."""
    entered = threading.Event()
    release = threading.Event()

    class BlockedStream(io.StringIO):
        def write(self, text):
            entered.set()
            release.wait(5)
            return super().write(text)

    stream = BlockedStream()
    sink = BoundedConsoleSink(stream)
    monkeypatch.setattr(sys, "stdout", stream)
    monkeypatch.setattr(sys, "stderr", stream)
    try:
        sink.write("blocked\n")
        assert entered.wait(1)
        sink.close()
        assert sys.stdout is stream
        assert sys.stderr is stream
        assert sink._thread.is_alive()
    finally:
        release.set()
        sink.close()
    assert not sink._thread.is_alive()


def test_clean_shutdown_keeps_standard_streams(monkeypatch):
    """Leave healthy output available to later atexit callbacks."""
    stream = io.StringIO()
    sink = BoundedConsoleSink(stream)
    monkeypatch.setattr(sys, "stdout", stream)
    monkeypatch.setattr(sys, "stderr", stream)
    sink.write("last record\n")
    sink._shutdown()
    assert not sink._thread.is_alive()
    assert stream.getvalue() == "last record\n"
    assert sys.stdout is stream
    assert sys.stderr is stream


@pytest.mark.parametrize("capacity", [0, -1])
def test_invalid_capacity_is_rejected(capacity):
    """Never silently create an unbounded queue."""
    with pytest.raises(ValueError, match="positive"):
        BoundedConsoleSink(io.StringIO(), capacity=capacity)


@pytest.mark.parametrize("tty", [True, False])
def test_log_level_reconfiguration_reuses_console_writer(monkeypatch, tty):
    """Cover both console sink registration paths without spawning new writers."""
    fake_loguru = MagicMock()
    fake_loguru.add.return_value = 7
    stream = io.StringIO()
    monkeypatch.setattr(stream, "isatty", lambda: tty)
    monkeypatch.setattr(sys, "stdout", stream)
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
        assert all(
            call.kwargs["colorize"] is tty for call in fake_loguru.add.call_args_list
        )
        assert LogManager.get_console_status() == writer.get_status()
    finally:
        if LogManager._console_output is not None:
            LogManager._console_output.close()


def test_unconfigured_console_has_no_status(monkeypatch):
    """Allow diagnostics to run before console setup."""
    monkeypatch.setattr(LogManager, "_console_output", None)
    assert LogManager.get_console_status() is None


@pytest.mark.parametrize("unbuffered", [False, True])
@pytest.mark.parametrize("stderr_alias", [False, True])
@pytest.mark.parametrize("close_first", [False, True])
def test_exit_with_unread_stdout_pipe(unbuffered, stderr_alias, close_first):
    """A blocked daemon must not hold stdout's buffer lock during shutdown."""
    source_path = Path(__file__).parents[2] / "astrbot/core/utils/console_sink.py"
    source = textwrap.dedent(f"""
        import importlib.util
        import os
        import sys
        import asyncio
        import io
        import threading
        import time
        spec = importlib.util.spec_from_file_location('console_sink', {str(source_path)!r})
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        entered = threading.Event()
        completed = threading.Event()
        original = sys.stdout
        raw = getattr(original.buffer, 'raw', original.buffer)
        class ObservedRaw(io.RawIOBase):
            def writable(self):
                return True
            def write(self, data):
                entered.set()
                result = raw.write(data)
                completed.set()
                return result

        observed = ObservedRaw()
        output = observed if {unbuffered!r} else io.BufferedWriter(observed)
        sys.stdout = io.TextIOWrapper(output, encoding=original.encoding,
                                     errors=original.errors, write_through={unbuffered!r})
        if {stderr_alias!r}:
            sys.stderr = sys.stdout
        sink = module.BoundedConsoleSink(sys.stdout, capacity=2)
        sink.write('x' * 1000000)
        assert entered.wait(2), 'writer did not enter raw pipe IO'

        async def probe():
            started = time.monotonic()
            for index in range(500):
                sink.write('record ' + str(index) + '\\n')
            await asyncio.sleep(0)
            assert time.monotonic() - started < 1, 'producer blocked'
        asyncio.run(probe())
        assert sink.dropped == 498
        assert not completed.is_set(), 'pipe write unexpectedly completed'
        if {close_first!r}:
            sink.close()
            assert sys.stdout is sink._original_stream
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
            assert '\\x1b[' not in stream.getvalue()

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
