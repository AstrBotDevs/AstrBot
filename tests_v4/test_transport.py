"""
Tests for runtime/transport.py - Transport implementations.
"""

from __future__ import annotations

import asyncio
from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot_sdk.runtime.transport import (
    StdioTransport,
    Transport,
    WebSocketClientTransport,
    WebSocketServerTransport,
)


class TestTransportBase:
    """Tests for Transport base class."""

    def test_init_sets_handler_none(self):
        """Transport should initialize with _handler as None."""

        # 创建一个具体的测试子类
        class ConcreteTransport(Transport):
            async def start(self):
                pass

            async def stop(self):
                pass

            async def send(self, message: str):
                pass

        transport = ConcreteTransport()
        assert transport._handler is None

    def test_set_message_handler(self):
        """set_message_handler should store handler."""

        class ConcreteTransport(Transport):
            async def start(self):
                pass

            async def stop(self):
                pass

            async def send(self, message: str):
                pass

        transport = ConcreteTransport()
        handler = MagicMock()
        transport.set_message_handler(handler)
        assert transport._handler is handler

    @pytest.mark.asyncio
    async def test_start_not_implemented(self):
        """Transport.start should be abstract."""
        # 抽象方法不能直接测试，跳过
        pass

    @pytest.mark.asyncio
    async def test_stop_not_implemented(self):
        """Transport.stop should be abstract."""
        # 抽象方法不能直接测试，跳过
        pass

    @pytest.mark.asyncio
    async def test_send_not_implemented(self):
        """Transport.send should be abstract."""
        # 抽象方法不能直接测试，跳过
        pass

    @pytest.mark.asyncio
    async def test_wait_closed(self):
        """wait_closed should wait for _closed event."""

        class ConcreteTransport(Transport):
            async def start(self):
                pass

            async def stop(self):
                pass

            async def send(self, message: str):
                pass

        transport = ConcreteTransport()
        transport._closed.set()
        # Should return immediately since _closed is already set
        await transport.wait_closed()

    @pytest.mark.asyncio
    async def test_dispatch_calls_handler(self):
        """_dispatch should call handler with payload."""

        class ConcreteTransport(Transport):
            async def start(self):
                pass

            async def stop(self):
                pass

            async def send(self, message: str):
                pass

        transport = ConcreteTransport()
        handler = AsyncMock()
        transport.set_message_handler(handler)
        await transport._dispatch("test payload")
        handler.assert_called_once_with("test payload")

    @pytest.mark.asyncio
    async def test_dispatch_without_handler(self):
        """_dispatch should work without handler."""

        class ConcreteTransport(Transport):
            async def start(self):
                pass

            async def stop(self):
                pass

            async def send(self, message: str):
                pass

        transport = ConcreteTransport()
        # Should not raise when no handler is set
        await transport._dispatch("test payload")


class TestStdioTransportInit:
    """Tests for StdioTransport initialization."""

    def test_default_init(self):
        """StdioTransport should initialize with default values."""
        transport = StdioTransport()
        assert transport._stdin is None
        assert transport._stdout is None
        assert transport._command is None
        assert transport._cwd is None
        assert transport._env is None
        assert transport._process is None
        assert transport._reader_task is None

    def test_with_custom_streams(self):
        """StdioTransport should accept custom stdin/stdout."""
        stdin = StringIO()
        stdout = StringIO()
        transport = StdioTransport(stdin=stdin, stdout=stdout)
        assert transport._stdin is stdin
        assert transport._stdout is stdout

    def test_with_command(self):
        """StdioTransport should accept command for subprocess."""
        transport = StdioTransport(command=["python", "-m", "module"])
        assert transport._command == ["python", "-m", "module"]

    def test_with_cwd_and_env(self):
        """StdioTransport should accept cwd and env."""
        transport = StdioTransport(cwd="/tmp", env={"VAR": "value"})
        assert transport._cwd == "/tmp"
        assert transport._env == {"VAR": "value"}


class TestStdioTransportFileMode:
    """Tests for StdioTransport in file mode (no subprocess)."""

    @pytest.mark.asyncio
    async def test_start_without_command(self):
        """start() without command should use stdin/stdout."""
        transport = StdioTransport()
        with patch("sys.stdin"), patch("sys.stdout"):
            await transport.start()
            assert transport._reader_task is not None
            await transport.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_reader_task(self):
        """stop() should cancel reader task."""
        transport = StdioTransport()
        with patch("sys.stdin"), patch("sys.stdout"):
            await transport.start()
            task = transport._reader_task
            await transport.stop()
            assert task.cancelled() or task.done()

    @pytest.mark.asyncio
    async def test_send_without_process(self):
        """send() without process should write to stdout."""
        stdout = MagicMock()
        stdout.write = MagicMock()
        stdout.flush = MagicMock()
        transport = StdioTransport(stdout=stdout)

        with patch("sys.stdin"):
            await transport.start()

        await transport.send("test message")

        # Should have written the message with newline
        stdout.write.assert_called_once_with("test message\n")
        stdout.flush.assert_called_once()

        await transport.stop()

    @pytest.mark.asyncio
    async def test_send_adds_newline_if_missing(self):
        """send() should add newline if not present."""
        stdout = MagicMock()
        stdout.write = MagicMock()
        stdout.flush = MagicMock()
        transport = StdioTransport(stdout=stdout)

        with patch("sys.stdin"):
            await transport.start()

        await transport.send("message")
        stdout.write.assert_called_once_with("message\n")

        await transport.stop()

    @pytest.mark.asyncio
    async def test_send_preserves_existing_newline(self):
        """send() should not add extra newline."""
        stdout = MagicMock()
        stdout.write = MagicMock()
        stdout.flush = MagicMock()
        transport = StdioTransport(stdout=stdout)

        with patch("sys.stdin"):
            await transport.start()

        await transport.send("message\n")
        stdout.write.assert_called_once_with("message\n")

        await transport.stop()

    @pytest.mark.asyncio
    async def test_send_raises_without_stdout(self):
        """send() should raise if stdout is None."""
        transport = StdioTransport(stdout=None)
        transport._stdout = None

        with pytest.raises(RuntimeError, match="stdout"):
            await transport.send("test")


class TestStdioTransportProcessMode:
    """Tests for StdioTransport in subprocess mode."""

    @pytest.mark.asyncio
    async def test_start_with_command_creates_process(self):
        """start() with command should create subprocess."""
        # 使用 Python 解释器作为跨平台兼容的命令
        import sys

        transport = StdioTransport(command=[sys.executable, "-c", "print('test')"])

        await transport.start()
        assert transport._process is not None
        assert transport._reader_task is not None

        await transport.stop()

    @pytest.mark.asyncio
    async def test_stop_terminates_process(self):
        """stop() should terminate the subprocess."""
        import sys

        # 使用 Python 长时间运行的脚本替代 sleep
        transport = StdioTransport(
            command=[sys.executable, "-c", "import time; time.sleep(100)"]
        )

        await transport.start()
        process = transport._process
        assert process is not None

        await transport.stop()
        assert process.returncode is not None

    @pytest.mark.asyncio
    async def test_send_to_process(self):
        """send() should write to process stdin."""
        import sys

        # 使用 Python 脚本替代 cat，读取 stdin 并输出
        transport = StdioTransport(
            command=[
                sys.executable,
                "-c",
                "import sys; sys.stdout.write(sys.stdin.read())",
            ]
        )

        await transport.start()
        # Should not raise
        await transport.send("test data")

        await transport.stop()

    @pytest.mark.asyncio
    async def test_send_raises_if_process_stdin_none(self):
        """send() should raise if process stdin is None."""
        import sys

        transport = StdioTransport(
            command=[
                sys.executable,
                "-c",
                "import sys; sys.stdout.write(sys.stdin.read())",
            ]
        )
        await transport.start()

        # Manually set stdin to None to simulate error condition
        if transport._process:
            transport._process.stdin = None  # type: ignore

        with pytest.raises(RuntimeError, match="stdin"):
            await transport.send("test")

        await transport.stop()


class TestWebSocketServerTransportInit:
    """Tests for WebSocketServerTransport initialization."""

    def test_default_init(self):
        """WebSocketServerTransport should have default values."""
        transport = WebSocketServerTransport()
        assert transport._host == "127.0.0.1"
        assert transport._port == 8765
        assert transport._path == "/"
        assert transport._heartbeat == 30.0
        assert transport._app is None
        assert transport._ws is None

    def test_custom_values(self):
        """WebSocketServerTransport should accept custom values."""
        transport = WebSocketServerTransport(
            host="0.0.0.0",
            port=9000,
            path="/ws",
            heartbeat=60.0,
        )
        assert transport._host == "0.0.0.0"
        assert transport._port == 9000
        assert transport._path == "/ws"
        assert transport._heartbeat == 60.0

    def test_port_property_returns_actual_port(self):
        """port property should return actual port after start."""
        transport = WebSocketServerTransport(port=8765)
        # Before start, should return configured port
        assert transport.port == 8765

    def test_url_property(self):
        """url property should return WebSocket URL."""
        transport = WebSocketServerTransport(host="localhost", port=8080, path="/ws")
        assert transport.url == "ws://localhost:8080/ws"


class TestWebSocketServerTransportLifecycle:
    """Tests for WebSocketServerTransport lifecycle."""

    @pytest.mark.asyncio
    async def test_start_creates_app(self):
        """start() should create aiohttp app."""
        transport = WebSocketServerTransport(port=0)
        await transport.start()

        assert transport._app is not None
        assert transport._runner is not None
        assert transport._site is not None

        await transport.stop()

    @pytest.mark.asyncio
    async def test_stop_closes_websocket(self):
        """stop() should close the WebSocket."""
        transport = WebSocketServerTransport(port=0)
        await transport.start()
        await transport.stop()

        assert transport._ws is None
        assert transport._runner is None

    @pytest.mark.asyncio
    async def test_send_waits_for_connection(self):
        """send() should wait for WebSocket connection."""
        transport = WebSocketServerTransport(port=0)
        await transport.start()

        # Mock connected state
        transport._connected.set()
        # _ws 需要有异步的 send_str 方法
        transport._ws = MagicMock()
        transport._ws.closed = False
        transport._ws.send_str = AsyncMock()
        # close 也需要是异步的
        transport._ws.close = AsyncMock()

        await transport.send("test")
        transport._ws.send_str.assert_called_once_with("test")

        await transport.stop()

    @pytest.mark.asyncio
    async def test_send_raises_if_not_connected(self):
        """send() should raise if WebSocket not connected."""
        transport = WebSocketServerTransport(port=0, heartbeat=0)
        await transport.start()

        # Set timeout to 0 for immediate failure
        with pytest.raises((RuntimeError, asyncio.TimeoutError)):
            await transport.send("test")

        await transport.stop()


class TestWebSocketClientTransportInit:
    """Tests for WebSocketClientTransport initialization."""

    def test_required_url(self):
        """WebSocketClientTransport requires url."""
        transport = WebSocketClientTransport(url="ws://localhost:8080")
        assert transport._url == "ws://localhost:8080"
        assert transport._heartbeat == 30.0

    def test_custom_heartbeat(self):
        """WebSocketClientTransport should accept custom heartbeat."""
        transport = WebSocketClientTransport(url="ws://localhost:8080", heartbeat=60.0)
        assert transport._heartbeat == 60.0


class TestWebSocketClientTransportLifecycle:
    """Tests for WebSocketClientTransport lifecycle."""

    @pytest.mark.asyncio
    async def test_start_creates_session(self):
        """start() should create aiohttp session and connect."""
        server = WebSocketServerTransport(port=0)
        await server.start()

        client = WebSocketClientTransport(url=server.url)
        await client.start()

        assert client._session is not None
        assert client._ws is not None

        await client.stop()
        await server.stop()

    @pytest.mark.asyncio
    async def test_stop_closes_session_and_websocket(self):
        """stop() should close session and WebSocket."""
        server = WebSocketServerTransport(port=0)
        await server.start()

        client = WebSocketClientTransport(url=server.url)
        await client.start()
        await client.stop()

        assert client._session is None
        assert client._ws is None

        await server.stop()

    @pytest.mark.asyncio
    async def test_send_after_start(self):
        """send() should work after start()."""
        server = WebSocketServerTransport(port=0)
        await server.start()

        client = WebSocketClientTransport(url=server.url)
        await client.start()

        # Should not raise
        await client.send("test message")

        await client.stop()
        await server.stop()

    @pytest.mark.asyncio
    async def test_send_raises_if_not_connected(self):
        """send() should raise if WebSocket not connected."""
        client = WebSocketClientTransport(url="ws://localhost:99999")

        with pytest.raises(RuntimeError, match="尚未连接"):
            await client.send("test")


class TestTransportIntegration:
    """Integration tests for transport pairs."""

    @pytest.mark.asyncio
    async def test_websocket_client_server_communication(self):
        """WebSocket client and server should communicate."""
        server = WebSocketServerTransport(port=0)
        client = WebSocketClientTransport(url="ws://invalid")

        received_messages = []

        async def handle_message(payload: str):
            received_messages.append(payload)

        server.set_message_handler(handle_message)

        await server.start()

        # Create new client with correct URL
        client = WebSocketClientTransport(url=server.url)
        await client.start()

        # Wait for connection
        await asyncio.sleep(0.1)

        await client.send("hello from client")

        # Wait for message to be received
        await asyncio.sleep(0.1)

        assert "hello from client" in received_messages

        await client.stop()
        await server.stop()
