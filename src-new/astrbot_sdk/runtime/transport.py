"""传输层抽象模块。

定义 Transport 抽象基类及其实现，负责底层原始载荷的传输。
传输层只关心分帧后的 bytes 或 text frame，不处理协议细节。
传输实现：
    Transport: 抽象基类，定义 start/stop/send/wait_closed 接口
    StdioTransport: 标准输入输出传输
        - 进程模式: 通过 command 参数启动子进程
        - 文件模式: 通过 stdin/stdout 参数指定文件描述符

传输类型：
    Transport: 抽象基类，定义 start/stop/send 接口
    StdioTransport: 标准输入输出传输，支持进程模式和文件模式
    WebSocketServerTransport: WebSocket 服务端传输
        - 单连接限制，支持心跳配置
        - 通过 port 属性获取实际监听端口
        - 自动重连需要外部实现

与旧版对比：
    旧版传输层:
        - 分离的 client/ 和 server/ 目录
        - JSONRPCClient 基类
            - StdioClient: 子进程通信
            - WebSocketClient: WebSocket 客户端
        - JSONRPCServer 基类
            - StdioServer: 标准输入输出
            - WebSocketServer: WebSocket 服务端
        - 每个实现都处理 JSON-RPC 消息序列化

    新版传输层:
        - 统一的 Transport 抽象
        - StdioTransport:
            - 支持启动子进程模式 (command 参数)
            - 支持文件描述符模式 (stdin/stdout 参数)
        - WebSocketServerTransport:
            - 单连接限制
            - 支持心跳配置
        - WebSocketClientTransport:
            - 自动重连需要外部实现
        - 传输层只处理 framed payload，协议由 Peer 层处理

使用示例：
    # 子进程模式
    transport = StdioTransport(
        command=["python", "-m", "my_plugin"],
        cwd="/path/to/plugin",
    )

    # 标准输入输出模式
    transport = StdioTransport(stdin=sys.stdin, stdout=sys.stdout)

    # WebSocket 服务端
    transport = WebSocketServerTransport(host="0.0.0.0", port=8765)

    # WebSocket 客户端
    transport = WebSocketClientTransport(url="ws://localhost:8765")

    # 统一接口
    transport.set_message_handler(my_handler)
    await transport.start()
    await transport.send(encoded_payload)
    await transport.stop()

`Transport` 只处理 framed payload，不做协议解析，也不关心能力、handler 或
legacy 兼容。当前实现包括：

- `StdioTransport`: 子进程或文件对象上的按行或 length-prefixed 传输
- `WebSocketServerTransport`: 单连接 WebSocket 服务端，支持 text/binary frame
- `WebSocketClientTransport`: WebSocket 客户端，支持 text/binary frame

自动重连、消息重放等策略不在这里实现，统一留给更上层编排。
"""

from __future__ import annotations

import asyncio
import io
import struct
import sys
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Sequence
from typing import IO, cast

import aiohttp
from aiohttp import web
from loguru import logger

from ..protocol.wire_codecs import StdioFraming, WebSocketFrameType

MessageHandler = Callable[[bytes], Awaitable[None]]
RawPayload = bytes | str


def _ensure_bytes(payload: RawPayload) -> bytes:
    if isinstance(payload, bytes):
        return payload
    return payload.encode("utf-8")


def _frame_stdio_line_payload(payload: bytes) -> bytes:
    body = payload
    if body.endswith(b"\r\n"):
        body = body[:-2]
    elif body.endswith((b"\n", b"\r")):
        body = body[:-1]
    if b"\n" in body or b"\r" in body:
        raise ValueError("STDIO payload 不允许包含原始换行符")
    return body + b"\n"


def _frame_stdio_length_prefixed_payload(payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + payload


def _write_stdio_payload(stream: IO[str] | IO[bytes], payload: bytes) -> None:
    if hasattr(stream, "buffer"):
        stream.buffer.write(payload)  # type: ignore[attr-defined]
        stream.flush()  # type: ignore[call-arg]
        return
    if isinstance(stream, io.TextIOBase):
        text_stream = cast(IO[str], stream)
        text_stream.write(payload.decode("utf-8"))
        text_stream.flush()
        return
    binary_stream = cast(IO[bytes], stream)
    binary_stream.write(payload)
    binary_stream.flush()


class Transport(ABC):
    def __init__(self) -> None:
        self._handler: MessageHandler | None = None
        self._closed = asyncio.Event()

    def set_message_handler(self, handler: MessageHandler) -> None:
        """注册收到原始字符串消息后的回调。"""
        self._handler = handler

    def configure_for_codec(self, codec) -> None:
        """Allow transports to align framing or frame type with the selected codec."""
        return None

    @abstractmethod
    async def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def send(self, payload: RawPayload) -> None:
        raise NotImplementedError

    async def wait_closed(self) -> None:
        """等待传输层进入关闭状态。"""
        await self._closed.wait()

    async def _dispatch(self, payload: bytes) -> None:
        """把收到的原始载荷转交给上层处理器。"""
        if self._handler is not None:
            await self._handler(payload)


class StdioTransport(Transport):
    def __init__(
        self,
        *,
        stdin: IO[str] | IO[bytes] | None = None,
        stdout: IO[str] | IO[bytes] | None = None,
        command: Sequence[str] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        framing: StdioFraming = "line",
    ) -> None:
        super().__init__()
        self._stdin = stdin
        self._stdout = stdout
        self._command = list(command) if command is not None else None
        self._cwd = cwd
        self._env = env
        self._framing = framing
        self._process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._closed.clear()
        if self._command is not None:
            self._process = await asyncio.create_subprocess_exec(
                *self._command,
                cwd=self._cwd,
                env=self._env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=sys.stderr,
            )
            self._reader_task = asyncio.create_task(self._read_process_loop())
            return

        if self._framing == "length_prefixed":
            self._stdin = self._stdin or sys.stdin.buffer
            self._stdout = self._stdout or sys.stdout.buffer
        else:
            self._stdin = self._stdin or sys.stdin
            self._stdout = self._stdout or sys.stdout
        self._reader_task = asyncio.create_task(self._read_file_loop())

    def configure_for_codec(self, codec) -> None:
        self._framing = codec.stdio_framing

    async def stop(self) -> None:
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        if self._process is not None:
            if self._process.returncode is None:
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    self._process.kill()
                    await self._process.wait()
            self._process = None
        self._closed.set()

    async def send(self, payload: RawPayload) -> None:
        encoded = _ensure_bytes(payload)
        if self._framing == "line":
            framed = _frame_stdio_line_payload(encoded)
        else:
            framed = _frame_stdio_length_prefixed_payload(encoded)
        if self._process is not None:
            if self._process.stdin is None:
                raise RuntimeError("STDIO subprocess stdin 不可用")
            self._process.stdin.write(framed)
            await self._process.stdin.drain()
            return

        if self._stdout is None:
            raise RuntimeError("STDIO stdout 不可用")

        def _write() -> None:
            assert self._stdout is not None
            _write_stdio_payload(self._stdout, framed)

        await asyncio.to_thread(_write)

    async def _read_process_loop(self) -> None:
        assert self._process is not None
        assert self._process.stdout is not None
        try:
            while True:
                if self._framing == "line":
                    raw = await self._process.stdout.readline()
                    if not raw:
                        break
                    await self._dispatch(raw.rstrip(b"\r\n"))
                    continue
                header = await self._process.stdout.readexactly(4)
                length = struct.unpack(">I", header)[0]
                payload = await self._process.stdout.readexactly(length)
                await self._dispatch(payload)
        except asyncio.IncompleteReadError:
            pass
        finally:
            self._closed.set()

    async def _read_file_loop(self) -> None:
        assert self._stdin is not None
        try:
            while True:
                if self._framing == "line":
                    raw = await asyncio.to_thread(self._stdin.readline)
                    if not raw:
                        break
                    if isinstance(raw, bytes):
                        await self._dispatch(raw.rstrip(b"\r\n"))
                    else:
                        await self._dispatch(raw.rstrip("\r\n").encode("utf-8"))
                    continue
                header = await asyncio.to_thread(self._stdin.read, 4)
                if not header:
                    break
                if isinstance(header, str):
                    raise RuntimeError("length_prefixed STDIO 需要二进制 stdin")
                if len(header) < 4:
                    break
                length = struct.unpack(">I", header)[0]
                payload = await asyncio.to_thread(self._stdin.read, length)
                if isinstance(payload, str):
                    raise RuntimeError("length_prefixed STDIO 需要二进制 stdin")
                if len(payload) < length:
                    break
                await self._dispatch(payload)
        finally:
            self._closed.set()


class WebSocketServerTransport(Transport):
    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
        path: str = "/",
        heartbeat: float = 30.0,
        frame_type: WebSocketFrameType = "text",
    ) -> None:
        super().__init__()
        self._host = host
        self._port = port
        self._actual_port: int | None = None
        self._path = path
        self._heartbeat = heartbeat
        self._frame_type = frame_type
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._ws: web.WebSocketResponse | None = None
        self._write_lock = asyncio.Lock()
        self._connected = asyncio.Event()

    async def start(self) -> None:
        self._closed.clear()
        self._connected.clear()
        self._app = web.Application()
        self._app.router.add_get(self._path, self._handle_socket)
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self._host, self._port)
        await self._site.start()
        server = getattr(self._site, "_server", None)
        sockets = getattr(server, "sockets", None)
        if sockets:
            socket = sockets[0]
            self._actual_port = socket.getsockname()[1]

    async def stop(self) -> None:
        self._connected.clear()
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        if self._site is not None:
            await self._site.stop()
            self._site = None
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
        self._closed.set()

    async def send(self, payload: RawPayload) -> None:
        if self._ws is None or self._ws.closed:
            await asyncio.wait_for(self._connected.wait(), timeout=30.0)
        if self._ws is None or self._ws.closed:
            raise RuntimeError("WebSocket 尚未连接")
        async with self._write_lock:
            encoded = _ensure_bytes(payload)
            if self._frame_type == "text":
                await self._ws.send_str(encoded.decode("utf-8"))
            else:
                await self._ws.send_bytes(encoded)

    async def _handle_socket(self, request: web.Request) -> web.WebSocketResponse:
        if self._ws is not None and not self._ws.closed:
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            await ws.close(code=1008, message=b"only one websocket connection allowed")
            return ws

        ws = web.WebSocketResponse(
            heartbeat=self._heartbeat if self._heartbeat > 0 else None
        )
        await ws.prepare(request)
        self._ws = ws
        self._connected.set()
        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._dispatch(msg.data.encode("utf-8"))
                elif msg.type == aiohttp.WSMsgType.BINARY:
                    await self._dispatch(msg.data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error("websocket server error: {}", ws.exception())
                    break
        finally:
            self._connected.clear()
            self._closed.set()
            self._ws = None
        return ws

    @property
    def port(self) -> int:
        return self._actual_port or self._port

    @property
    def url(self) -> str:
        return f"ws://{self._host}:{self.port}{self._path}"

    def configure_for_codec(self, codec) -> None:
        self._frame_type = codec.websocket_frame_type


class WebSocketClientTransport(Transport):
    def __init__(
        self,
        *,
        url: str,
        heartbeat: float = 30.0,
        frame_type: WebSocketFrameType = "text",
    ) -> None:
        super().__init__()
        self._url = url
        self._heartbeat = heartbeat
        self._frame_type = frame_type
        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._reader_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._closed.clear()
        self._session = aiohttp.ClientSession()
        self._ws = await self._session.ws_connect(
            self._url,
            heartbeat=self._heartbeat if self._heartbeat > 0 else None,
        )
        self._reader_task = asyncio.create_task(self._read_loop())

    async def stop(self) -> None:
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        if self._session is not None:
            await self._session.close()
        self._ws = None
        self._session = None
        self._closed.set()

    async def send(self, payload: RawPayload) -> None:
        if self._ws is None or self._ws.closed:
            raise RuntimeError("WebSocket client 尚未连接")
        encoded = _ensure_bytes(payload)
        if self._frame_type == "text":
            await self._ws.send_str(encoded.decode("utf-8"))
        else:
            await self._ws.send_bytes(encoded)

    async def _read_loop(self) -> None:
        assert self._ws is not None
        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._dispatch(msg.data.encode("utf-8"))
                elif msg.type == aiohttp.WSMsgType.BINARY:
                    await self._dispatch(msg.data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error("websocket client error: {}", self._ws.exception())
                    break
        finally:
            self._closed.set()

    def configure_for_codec(self, codec) -> None:
        self._frame_type = codec.websocket_frame_type
