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


def test_replaces_undecodable_bytes_instead_of_dying():
    """Bytes that are not valid UTF-8 become replacement chars, not an exception."""
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
