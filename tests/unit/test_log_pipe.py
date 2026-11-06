import locale
import logging
import os

from astrbot.core.utils.log_pipe import LogPipe


class _ListHandler(logging.Handler):
    """Collect forwarded log messages without touching the root logger."""

    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


class _RaisingHandler(logging.Handler):
    """Record every message, then fail the way a broken log sink would."""

    def __init__(self) -> None:
        super().__init__()
        self.seen: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.seen.append(record.getMessage())
        raise RuntimeError("log sink failed")


def _make_pipe(**kwargs):
    """Build a LogPipe wired to an isolated logger plus its captured output."""
    logger = logging.getLogger("astrbot-test-log-pipe")
    logger.propagate = False
    logger.handlers.clear()
    handler = _ListHandler()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    pipe = LogPipe(logging.INFO, logger, identifier="MCP-test", **kwargs)
    return pipe, handler.messages


def test_forwards_non_ascii_utf8_lines():
    """A UTF-8 line with CJK characters must be forwarded, not kill the thread."""
    pipe, messages = _make_pipe()
    # `str.encode` writes UTF-8, the encoding an MCP server launched with
    # PYTHONIOENCODING=utf-8 uses for its stderr.
    os.write(pipe.fileno(), "OCTEN_API_KEY 未设置\n".encode())
    os.write(pipe.fileno(), b"[argo-mcp] ready, waiting for stdin\n")
    pipe.close()
    pipe.join(timeout=5)
    assert not pipe.is_alive(), "drain thread must exit once the pipe is drained"
    assert any("OCTEN_API_KEY 未设置" in line for line in messages)
    assert any("ready, waiting for stdin" in line for line in messages)


def test_decodes_locale_encoded_lines(monkeypatch):
    """A child logging in the host locale (cp936 here) stays readable."""
    monkeypatch.setattr(locale, "getencoding", lambda: "cp936")
    pipe, messages = _make_pipe()
    # GBK multi-byte CJK whose byte pairs are invalid UTF-8: the strict UTF-8
    # pass must raise and hand the raw line to the locale fallback.
    os.write(pipe.fileno(), "OCTEN_API_KEY 未设置\n".encode("gbk"))
    pipe.close()
    pipe.join(timeout=5)
    assert not pipe.is_alive(), "drain thread must exit once the pipe is drained"
    assert any("OCTEN_API_KEY 未设置" in line for line in messages)


def test_decodes_locale_lines_while_parent_runs_in_utf8_mode(monkeypatch):
    """A cp936 child stays readable while the parent runs in UTF-8 mode.

    Under ``PYTHONUTF8=1`` (the default from 3.15 on) the preferred encoding
    reports ``utf-8``, so only ``getencoding`` still names the encoding a
    locale-logging child writes.
    """
    monkeypatch.setattr(
        locale, "getpreferredencoding", lambda do_setlocale=True: "utf-8"
    )
    monkeypatch.setattr(locale, "getencoding", lambda: "cp936")
    pipe, messages = _make_pipe()
    os.write(pipe.fileno(), "OCTEN_API_KEY 未设置\n".encode("gbk"))
    pipe.close()
    pipe.join(timeout=5)
    assert not pipe.is_alive()
    assert any("OCTEN_API_KEY 未设置" in line for line in messages)


def test_replaces_undecodable_bytes_instead_of_dying():
    """Bytes valid in neither UTF-8 nor the locale become replacement chars."""
    pipe, messages = _make_pipe()
    os.write(pipe.fileno(), b"bad \xff\xfe bytes\n")
    pipe.close()
    pipe.join(timeout=5)
    assert not pipe.is_alive()
    assert any("bad " in line for line in messages)


def test_survives_callback_exception():
    """One line whose callback raises must not stop later lines being forwarded."""
    seen: list[str] = []

    def callback(line: str) -> None:
        seen.append(line)
        if line == "boom":
            raise ValueError("callback failed")

    pipe, messages = _make_pipe(callback=callback)
    os.write(pipe.fileno(), b"boom\n")
    os.write(pipe.fileno(), b"after\n")
    pipe.close()
    pipe.join(timeout=5)
    assert not pipe.is_alive()
    assert seen == ["boom", "after"]
    assert any("after" in line for line in messages)


def test_splits_embedded_line_separators_into_separate_lines():
    """Binary readline only splits on ``\\n``; ``\\r`` and ``\\r\\n`` split too."""
    pipe, messages = _make_pipe()
    os.write(pipe.fileno(), b"10%\r50%\r\n100%\n")
    pipe.close()
    pipe.join(timeout=5)
    assert not pipe.is_alive()
    assert messages == ["[MCP-test] 10%", "[MCP-test] 50%", "[MCP-test] 100%"]


def test_forwards_a_final_line_without_separator():
    """Data left in the pipe at EOF is one line even without a separator."""
    pipe, messages = _make_pipe()
    os.write(pipe.fileno(), b"tail without separator")
    pipe.close()
    pipe.join(timeout=5)
    assert not pipe.is_alive()
    assert messages == ["[MCP-test] tail without separator"]


def test_survives_logger_that_always_raises():
    """A sink that raises on every record must not stop later lines either."""
    logger = logging.getLogger("astrbot-test-log-pipe-broken")
    logger.propagate = False
    logger.handlers.clear()
    handler = _RaisingHandler()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    pipe = LogPipe(logging.INFO, logger, identifier="MCP-test")
    os.write(pipe.fileno(), b"boom\n")
    os.write(pipe.fileno(), b"after\n")
    pipe.close()
    pipe.join(timeout=5)
    assert not pipe.is_alive(), "a broken log sink must not end the drain thread"
    assert "[MCP-test] after" in handler.seen
