"""Tests for the ws_reverse port probe in the aiocqhttp adapter.

hypercorn sets SO_REUSEADDR unconditionally, so on Windows a second AstrBot
process can bind and listen on a port that is already served without any error.
The adapter now probes the port before starting the server, so a conflict fails
at startup instead of staying silent.
"""

import errno
import logging
import socket
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import astrbot.api  # noqa: F401  # Initialize API before platform adapters.
from astrbot.core.platform.sources.aiocqhttp import aiocqhttp_platform_adapter
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
    AiocqhttpAdapter,
)

# SO_EXCLUSIVEADDRUSE only exists on Windows; -5 is its documented value there
# and stands in on POSIX so the Windows branch stays testable everywhere.
EXCLUSIVE_ADDR_USE = getattr(socket, "SO_EXCLUSIVEADDRUSE", -5)


class _RecordingLogger:
    """Minimal logger that records the messages written by the adapter."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.infos: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def info(self, message: str) -> None:
        self.infos.append(message)

    def warning(self, message: str) -> None:
        pass


class _FakeSocket:
    """Socket double that records options, bind address and close calls."""

    instances: list["_FakeSocket"] = []

    def __init__(self, family: int, type_: int) -> None:
        self.family = family
        self.type = type_
        self.options: list[tuple[int, int, int]] = []
        # Ordered operation log. Real sockets need the option set before bind, and
        # checking only `options` would accept the reverse order.
        self.ops: list[str] = []
        self.bind_args: tuple[str, int] | None = None
        self.closed = False
        self.bind_error: OSError | None = None
        _FakeSocket.instances.append(self)

    def setsockopt(self, level: int, option: int, value: int) -> None:
        self.ops.append("setsockopt")
        self.options.append((level, option, value))

    def bind(self, address: tuple[str, int]) -> None:
        self.ops.append("bind")
        self.bind_args = address
        if self.bind_error is not None:
            raise self.bind_error

    def close(self) -> None:
        self.ops.append("close")
        self.closed = True


def _fake_socket_module() -> SimpleNamespace:
    """Build a socket-module double that hands out recording fake sockets."""
    return SimpleNamespace(
        socket=_FakeSocket,
        AF_INET=socket.AF_INET,
        AF_INET6=socket.AF_INET6,
        SOCK_STREAM=socket.SOCK_STREAM,
        SOL_SOCKET=socket.SOL_SOCKET,
        SO_REUSEADDR=socket.SO_REUSEADDR,
        SO_EXCLUSIVEADDRUSE=EXCLUSIVE_ADDR_USE,
    )


def _make_adapter(host: str, port: int) -> AiocqhttpAdapter:
    """Build an adapter without running the real aiocqhttp constructor."""
    adapter = AiocqhttpAdapter.__new__(AiocqhttpAdapter)
    adapter.host = host
    adapter.port = port
    adapter.bot = SimpleNamespace(run_task=Mock(return_value="run-task-awaitable"))
    adapter.shutdown_trigger_placeholder = Mock()
    return adapter


def _last_fake_socket() -> _FakeSocket:
    """Return the most recently created fake socket."""
    return _FakeSocket.instances[-1]


def test_free_port_starts_server(monkeypatch):
    """The probe passes on a free port and the server coroutine is created."""
    logger = _RecordingLogger()
    monkeypatch.setattr(aiocqhttp_platform_adapter, "logger", logger)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    finally:
        listener.close()
    adapter = _make_adapter("127.0.0.1", port)

    coro = adapter.run()

    assert coro == "run-task-awaitable"
    adapter.bot.run_task.assert_called_once()
    kwargs = adapter.bot.run_task.call_args.kwargs
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == port
    assert logger.errors == []
    assert any(str(port) in message for message in logger.infos)


def test_bound_port_raises_with_port_in_message(monkeypatch):
    """A port that is already listened on fails the start with a clear error."""
    logger = _RecordingLogger()
    monkeypatch.setattr(aiocqhttp_platform_adapter, "logger", logger)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        adapter = _make_adapter("127.0.0.1", port)

        with pytest.raises(OSError):
            adapter.run()
    finally:
        listener.close()

    adapter.bot.run_task.assert_not_called()
    assert len(logger.errors) == 1
    assert "ws_reverse port 127.0.0.1:" in logger.errors[0]
    assert str(port) in logger.errors[0]
    # A listener that accepts connections is reported as a competing server.
    assert "is already served" in logger.errors[0]


def test_silent_holder_gets_the_retry_wording(monkeypatch):
    """An address that is bound but not listening is reported differently."""
    logger = _RecordingLogger()
    monkeypatch.setattr(aiocqhttp_platform_adapter, "logger", logger)
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # Bound but never listening: nothing answers, which is the "still shutting down"
        # case rather than a competing backend.
        holder.bind(("127.0.0.1", 0))
        port = holder.getsockname()[1]
        adapter = _make_adapter("127.0.0.1", port)

        with pytest.raises(OSError):
            adapter.run()
    finally:
        holder.close()

    adapter.bot.run_task.assert_not_called()
    assert len(logger.errors) == 1
    assert str(port) in logger.errors[0]
    assert "does not accept connections" in logger.errors[0]


def test_probe_socket_is_closed_on_success(monkeypatch):
    """The probe socket is closed and never listened on when the bind passes."""
    logger = _RecordingLogger()
    monkeypatch.setattr(aiocqhttp_platform_adapter, "logger", logger)
    _FakeSocket.instances = []
    monkeypatch.setattr(aiocqhttp_platform_adapter, "socket", _fake_socket_module())

    adapter = _make_adapter("127.0.0.1", 47500)
    assert adapter.run() == "run-task-awaitable"

    assert len(_FakeSocket.instances) == 1
    probe = _last_fake_socket()
    assert probe.bind_args == ("127.0.0.1", 47500)
    assert probe.closed is True


def test_probe_socket_is_closed_on_failure(monkeypatch):
    """The probe socket is closed when the bind raises."""
    logger = _RecordingLogger()
    monkeypatch.setattr(aiocqhttp_platform_adapter, "logger", logger)
    _FakeSocket.instances = []
    monkeypatch.setattr(aiocqhttp_platform_adapter, "socket", _fake_socket_module())

    adapter = _make_adapter("127.0.0.1", 47500)

    def _bind_raises(self, address):
        self.bind_args = address
        raise OSError("bind failed")

    monkeypatch.setattr(_FakeSocket, "bind", _bind_raises)
    with pytest.raises(OSError):
        adapter.run()

    assert len(_FakeSocket.instances) == 1
    assert _last_fake_socket().closed is True


def test_windows_uses_exclusive_addruse(monkeypatch):
    """On Windows the probe must use SO_EXCLUSIVEADDRUSE."""
    logger = _RecordingLogger()
    monkeypatch.setattr(aiocqhttp_platform_adapter, "logger", logger)
    _FakeSocket.instances = []
    monkeypatch.setattr(aiocqhttp_platform_adapter, "socket", _fake_socket_module())
    monkeypatch.setattr(sys, "platform", "win32")

    adapter = _make_adapter("127.0.0.1", 47500)
    adapter.run()

    assert _last_fake_socket().options == [
        (socket.SOL_SOCKET, EXCLUSIVE_ADDR_USE, 1),
    ]


def test_posix_uses_reuseaddr(monkeypatch):
    """On POSIX the probe must use SO_REUSEADDR so TIME_WAIT is tolerated."""
    logger = _RecordingLogger()
    monkeypatch.setattr(aiocqhttp_platform_adapter, "logger", logger)
    _FakeSocket.instances = []
    monkeypatch.setattr(aiocqhttp_platform_adapter, "socket", _fake_socket_module())
    monkeypatch.setattr(sys, "platform", "linux")

    adapter = _make_adapter("127.0.0.1", 47500)
    adapter.run()

    assert _last_fake_socket().options == [
        (socket.SOL_SOCKET, socket.SO_REUSEADDR, 1),
    ]


def test_probe_sets_option_before_bind(monkeypatch):
    """The socket option must be set before bind, otherwise a real socket ignores it."""
    logger = _RecordingLogger()
    monkeypatch.setattr(aiocqhttp_platform_adapter, "logger", logger)
    _FakeSocket.instances = []
    monkeypatch.setattr(aiocqhttp_platform_adapter, "socket", _fake_socket_module())
    monkeypatch.setattr(sys, "platform", "linux")

    adapter = _make_adapter("127.0.0.1", 47500)
    adapter.run()

    assert _last_fake_socket().ops == ["setsockopt", "bind", "close"]


def test_ipv6_host_uses_inet6(monkeypatch):
    """A colon in the host selects AF_INET6 for the probe."""
    logger = _RecordingLogger()
    monkeypatch.setattr(aiocqhttp_platform_adapter, "logger", logger)
    _FakeSocket.instances = []
    monkeypatch.setattr(aiocqhttp_platform_adapter, "socket", _fake_socket_module())
    monkeypatch.setattr(sys, "platform", "win32")

    adapter = _make_adapter("::1", 47501)
    adapter.run()

    assert _last_fake_socket().family == socket.AF_INET6
    assert _last_fake_socket().bind_args == ("::1", 47501)


def test_bracketed_ipv6_host_is_normalised(monkeypatch):
    """A "[::1]" host is probed without brackets, matching what hypercorn binds."""
    logger = _RecordingLogger()
    monkeypatch.setattr(aiocqhttp_platform_adapter, "logger", logger)
    _FakeSocket.instances = []
    monkeypatch.setattr(aiocqhttp_platform_adapter, "socket", _fake_socket_module())
    monkeypatch.setattr(sys, "platform", "win32")

    adapter = _make_adapter("[::1]", 47501)
    adapter.run()

    assert _last_fake_socket().family == socket.AF_INET6
    assert _last_fake_socket().bind_args == ("::1", 47501)
    adapter.bot.run_task.assert_called_once()
    assert adapter.bot.run_task.call_args.kwargs["host"] == "::1"


def test_ipv4_host_uses_inet(monkeypatch):
    """A host without a colon keeps AF_INET for the probe."""
    logger = _RecordingLogger()
    monkeypatch.setattr(aiocqhttp_platform_adapter, "logger", logger)
    _FakeSocket.instances = []
    monkeypatch.setattr(aiocqhttp_platform_adapter, "socket", _fake_socket_module())
    monkeypatch.setattr(sys, "platform", "linux")

    adapter = _make_adapter("0.0.0.0", 47500)
    adapter.run()

    assert _last_fake_socket().family == socket.AF_INET


def test_root_handlers_are_preserved(monkeypatch):
    """Starting the adapter must not wipe the global root log handlers."""
    logger = _RecordingLogger()
    monkeypatch.setattr(aiocqhttp_platform_adapter, "logger", logger)
    handler = logging.NullHandler()
    logging.root.addHandler(handler)
    try:
        before = len(logging.root.handlers)
        adapter = _make_adapter("127.0.0.1", 47503)
        monkeypatch.setattr(aiocqhttp_platform_adapter, "socket", _fake_socket_module())

        adapter.run()

        assert len(logging.root.handlers) == before
        assert handler in logging.root.handlers
    finally:
        logging.root.removeHandler(handler)


def test_unresolvable_host_is_not_reported_as_a_port_conflict(monkeypatch):
    """A host problem must not be described as a port that is already in use."""
    logger = _RecordingLogger()
    monkeypatch.setattr(aiocqhttp_platform_adapter, "logger", logger)
    _FakeSocket.instances = []
    monkeypatch.setattr(aiocqhttp_platform_adapter, "socket", _fake_socket_module())

    adapter = _make_adapter("no-such-host.invalid", 47504)

    def _bind_raises(self, address):
        self.bind_args = address
        raise socket.gaierror(errno.ENOENT, "getaddrinfo failed")

    monkeypatch.setattr(_FakeSocket, "bind", _bind_raises)
    with pytest.raises(socket.gaierror):
        adapter.run()

    assert len(logger.errors) == 1
    assert "is already in use" not in logger.errors[0]
    assert "cannot bind ws_reverse address" in logger.errors[0]
    assert "no-such-host.invalid" in logger.errors[0]

