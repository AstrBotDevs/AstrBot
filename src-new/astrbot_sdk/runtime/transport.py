from __future__ import annotations

import asyncio
import sys
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Sequence
from typing import IO

import aiohttp
from aiohttp import web
from loguru import logger

MessageHandler = Callable[[str], Awaitable[None]]


class Transport(ABC):
    def __init__(self) -> None:
        self._handler: MessageHandler | None = None
        self._closed = asyncio.Event()

    def set_message_handler(self, handler: MessageHandler) -> None:
        self._handler = handler

    @abstractmethod
    async def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def send(self, payload: str) -> None:
        raise NotImplementedError

    async def wait_closed(self) -> None:
        await self._closed.wait()

    async def _dispatch(self, payload: str) -> None:
        if self._handler is not None:
            await self._handler(payload)


class StdioTransport(Transport):
    def __init__(
        self,
        *,
        stdin: IO[str] | None = None,
        stdout: IO[str] | None = None,
        command: Sequence[str] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        super().__init__()
        self._stdin = stdin
        self._stdout = stdout
        self._command = list(command) if command is not None else None
        self._cwd = cwd
        self._env = env
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

        self._stdin = self._stdin or sys.stdin
        self._stdout = self._stdout or sys.stdout
        self._reader_task = asyncio.create_task(self._read_file_loop())

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

    async def send(self, payload: str) -> None:
        line = payload if payload.endswith("\n") else f"{payload}\n"
        if self._process is not None:
            if self._process.stdin is None:
                raise RuntimeError("STDIO subprocess stdin 不可用")
            self._process.stdin.write(line.encode("utf-8"))
            await self._process.stdin.drain()
            return

        if self._stdout is None:
            raise RuntimeError("STDIO stdout 不可用")

        def _write() -> None:
            assert self._stdout is not None
            self._stdout.write(line)
            self._stdout.flush()

        await asyncio.to_thread(_write)

    async def _read_process_loop(self) -> None:
        assert self._process is not None
        assert self._process.stdout is not None
        try:
            while True:
                raw = await self._process.stdout.readline()
                if not raw:
                    break
                await self._dispatch(raw.decode("utf-8").rstrip("\r\n"))
        finally:
            self._closed.set()

    async def _read_file_loop(self) -> None:
        assert self._stdin is not None
        try:
            while True:
                raw = await asyncio.to_thread(self._stdin.readline)
                if not raw:
                    break
                await self._dispatch(raw.rstrip("\r\n"))
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
    ) -> None:
        super().__init__()
        self._host = host
        self._port = port
        self._actual_port: int | None = None
        self._path = path
        self._heartbeat = heartbeat
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
        if self._site._server and getattr(self._site._server, "sockets", None):
            socket = self._site._server.sockets[0]
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

    async def send(self, payload: str) -> None:
        if self._ws is None or self._ws.closed:
            await asyncio.wait_for(self._connected.wait(), timeout=30.0)
        if self._ws is None or self._ws.closed:
            raise RuntimeError("WebSocket 尚未连接")
        async with self._write_lock:
            await self._ws.send_str(payload)

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
                    await self._dispatch(msg.data)
                elif msg.type == aiohttp.WSMsgType.BINARY:
                    await self._dispatch(msg.data.decode("utf-8"))
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


class WebSocketClientTransport(Transport):
    def __init__(
        self,
        *,
        url: str,
        heartbeat: float = 30.0,
    ) -> None:
        super().__init__()
        self._url = url
        self._heartbeat = heartbeat
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

    async def send(self, payload: str) -> None:
        if self._ws is None or self._ws.closed:
            raise RuntimeError("WebSocket client 尚未连接")
        await self._ws.send_str(payload)

    async def _read_loop(self) -> None:
        assert self._ws is not None
        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._dispatch(msg.data)
                elif msg.type == aiohttp.WSMsgType.BINARY:
                    await self._dispatch(msg.data.decode("utf-8"))
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error("websocket client error: {}", self._ws.exception())
                    break
        finally:
            self._closed.set()
