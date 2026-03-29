"""传输层抽象模块。

定义 Transport 抽象基类及其实现，负责底层的消息传输。
传输层只关心"发送字符串"和"接收字符串"，不处理协议细节。
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
    await transport.send(json_string)
    await transport.stop()

`Transport` 只处理“字符串发出去 / 字符串收进来”这件事，不做协议解析，也不关心
能力、handler 或迁移适配策略。当前实现包括：

- `StdioTransport`: 子进程或文件对象上的按行文本传输
- `WebSocketServerTransport`: 单连接 WebSocket 服务端
- `WebSocketClientTransport`: WebSocket 客户端

自动重连、消息重放等策略不在这里实现，统一留给更上层编排。
"""

from __future__ import annotations

import asyncio
import sys
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Sequence
from typing import IO, Any

from loguru import logger

MessageHandler = Callable[[str], Awaitable[None]]
STDIO_SUBPROCESS_STREAM_LIMIT = 8 * 1024 * 1024


def _get_aiohttp():
    import aiohttp

    return aiohttp


def _get_web():
    from aiohttp import web

    return web


def _frame_stdio_payload(payload: str) -> bytes:
    body = payload.encode("utf-8")
    return f"{len(body)}\n".encode("ascii") + body


def _parse_stdio_header(raw_header: bytes) -> int:
    header = raw_header.decode("ascii").strip()
    if not header:
        raise ValueError("STDIO frame header is empty")
    try:
        size = int(header)
    except ValueError as exc:
        raise ValueError(f"Invalid STDIO frame header: {header!r}") from exc
    # 拒绝负数 size，防止子进程写入畸形 header 导致 readexactly 行为异常
    if size < 0:
        raise ValueError(f"STDIO frame size must be non-negative: {size}")
    return size


# TODO 一个更好的解决方案？
def _is_windows_access_denied(error: BaseException) -> bool:
    return (
        sys.platform == "win32"
        and isinstance(error, PermissionError)
        and getattr(error, "winerror", None) == 5
    )


class Transport(ABC):
    def __init__(self) -> None:
        self._handler: MessageHandler | None = None
        self._closed = asyncio.Event()

    def set_message_handler(self, handler: MessageHandler) -> None:
        """注册收到原始字符串消息后的回调。"""
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
        """等待传输层进入关闭状态。"""
        await self._closed.wait()

    async def _dispatch(self, payload: str) -> None:
        """把收到的原始载荷转交给上层处理器。"""
        if self._handler is not None:
            await self._handler(payload)

    async def _dispatch_safely(self, payload: str, *, source: str) -> None:
        """安全地分发一帧消息：捕获所有非取消异常，避免单帧处理错误拖垮整个读循环。"""
        try:
            await self._dispatch(payload)
        except asyncio.CancelledError:
            # CancelledError 必须放行，否则无法优雅关闭
            raise
        except Exception:
            # 记录异常后继续读下一帧，而不是让读循环崩溃导致整个 transport 不可用
            logger.exception("Dropping inbound transport frame from {}", source)


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
            self._process = await self._start_subprocess_with_retry()
            self._reader_task = asyncio.create_task(self._read_process_loop())
            return

        self._stdin = self._stdin or sys.stdin
        self._stdout = self._stdout or sys.stdout
        self._reader_task = asyncio.create_task(self._read_file_loop())

    async def _start_subprocess_with_retry(self) -> asyncio.subprocess.Process:
        assert self._command is not None  # 类型收窄：start() 已确保非空
        delays = [0.15, 0.35, 0.75]
        last_error: BaseException | None = None
        for attempt, delay in enumerate([0.0, *delays], start=1):
            if delay:
                await asyncio.sleep(delay)
            try:
                return await asyncio.create_subprocess_exec(
                    *self._command,
                    cwd=self._cwd,
                    env=self._env,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=sys.stderr,
                    limit=STDIO_SUBPROCESS_STREAM_LIMIT,
                )
            except Exception as exc:
                last_error = exc
                if not _is_windows_access_denied(exc) or attempt == len(delays) + 1:
                    raise
                logger.warning(
                    "Windows denied access while starting freshly prepared worker "
                    "interpreter, retrying attempt {}/{}: {}",
                    attempt,
                    len(delays) + 1,
                    exc,
                )
        assert last_error is not None
        raise last_error

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
        frame = _frame_stdio_payload(payload)
        if self._process is not None:
            if self._process.stdin is None:
                raise RuntimeError("STDIO subprocess stdin 不可用")
            self._process.stdin.write(frame)
            await self._process.stdin.drain()
            return

        if self._stdout is None:
            raise RuntimeError("STDIO stdout 不可用")

        def _write() -> None:
            assert self._stdout is not None
            binary_stdout = getattr(self._stdout, "buffer", None)
            if binary_stdout is None:
                raise RuntimeError("STDIO stdout 必须提供可写入 bytes 的 buffer")
            binary_stdout.write(frame)
            binary_stdout.flush()

        await asyncio.to_thread(_write)

    async def _read_process_loop(self) -> None:
        """从子进程 stdout 持续读取 STDIO 帧，单帧异常不中断整体读取。"""
        assert self._process is not None
        assert self._process.stdout is not None
        try:
            while True:
                try:
                    raw_header = await self._process.stdout.readline()
                    if not raw_header:
                        break
                    payload_size = _parse_stdio_header(raw_header)
                    raw = await self._process.stdout.readexactly(payload_size)
                    # 使用 _dispatch_safely 而非 _dispatch，确保上层的单帧处理错误不会终结读循环
                    await self._dispatch_safely(
                        raw.decode("utf-8"),
                        source="stdio-process",
                    )
                except asyncio.CancelledError:
                    raise
                except asyncio.IncompleteReadError:
                    # 帧被截断说明子进程已经异常退出，读循环应终止
                    logger.warning("STDIO subprocess frame truncated before completion")
                    break
                except ValueError as exc:
                    # header 格式错误：跳过本帧继续读，因为 stdin/stdout 是流式的无法定位下一帧边界，
                    # 但保留日志便于排查
                    logger.warning("Skipping malformed STDIO subprocess frame: {}", exc)
                    continue
                except UnicodeDecodeError as exc:
                    # UTF-8 解码失败：跳过本帧继续，避免二进制脏数据导致整个连接断开
                    logger.warning(
                        "Skipping STDIO subprocess frame with invalid UTF-8 payload: {}",
                        exc,
                    )
                    continue
        finally:
            self._closed.set()

    async def _read_file_loop(self) -> None:
        """从本地 stdin（file 模式）持续读取 STDIO 帧，单帧异常不中断整体读取。"""
        assert self._stdin is not None
        try:
            while True:
                try:
                    binary_stdin = getattr(self._stdin, "buffer", None)
                    if binary_stdin is None:
                        raise RuntimeError("STDIO stdin 必须提供可读取 bytes 的 buffer")
                    raw_header = await asyncio.to_thread(binary_stdin.readline)
                    if not raw_header:
                        break
                    payload_size = _parse_stdio_header(raw_header)
                    raw = await asyncio.to_thread(binary_stdin.read, payload_size)
                    if len(raw) != payload_size:
                        raise EOFError("STDIO frame truncated before payload completed")
                    await self._dispatch_safely(
                        raw.decode("utf-8"),
                        source="stdio-file",
                    )
                except asyncio.CancelledError:
                    raise
                except EOFError as exc:
                    # 流被截断意味着上游已关闭，读循环应终止
                    logger.warning("{}", exc)
                    break
                except ValueError as exc:
                    # header 格式错误：跳过本帧继续读
                    logger.warning(
                        "Skipping malformed STDIO frame from file input: {}", exc
                    )
                    continue
                except UnicodeDecodeError as exc:
                    # UTF-8 解码失败：跳过本帧继续，保留连接可用
                    logger.warning(
                        "Skipping STDIO file frame with invalid UTF-8 payload: {}",
                        exc,
                    )
                    continue
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
        self._app: Any | None = None
        self._runner: Any | None = None
        self._site: Any | None = None
        self._ws: Any | None = None
        self._write_lock = asyncio.Lock()
        self._connected = asyncio.Event()

    async def start(self) -> None:
        web = _get_web()
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

    async def _handle_socket(self, request) -> Any:
        web = _get_web()
        aiohttp = _get_aiohttp()
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
                    # 文本帧直接分发，无需编解码
                    await self._dispatch_safely(
                        msg.data, source="websocket-server-text"
                    )
                elif msg.type == aiohttp.WSMsgType.BINARY:
                    # 二进制帧需要先尝试 UTF-8 解码；解码失败只跳过本帧，不断开连接
                    try:
                        payload = msg.data.decode("utf-8")
                    except UnicodeDecodeError as exc:
                        logger.warning(
                            "Skipping websocket server binary frame with invalid UTF-8 payload: {}",
                            exc,
                        )
                        continue
                    await self._dispatch_safely(
                        payload,
                        source="websocket-server-binary",
                    )
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
        self._session: Any | None = None
        self._ws: Any | None = None
        self._reader_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        aiohttp = _get_aiohttp()
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
        aiohttp = _get_aiohttp()
        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._dispatch_safely(
                        msg.data, source="websocket-client-text"
                    )
                elif msg.type == aiohttp.WSMsgType.BINARY:
                    # 与 server 端一致：二进制帧解码失败仅跳过本帧，保持连接存活
                    try:
                        payload = msg.data.decode("utf-8")
                    except UnicodeDecodeError as exc:
                        logger.warning(
                            "Skipping websocket client binary frame with invalid UTF-8 payload: {}",
                            exc,
                        )
                        continue
                    await self._dispatch_safely(
                        payload,
                        source="websocket-client-binary",
                    )
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error("websocket client error: {}", self._ws.exception())
                    break
        finally:
            self._closed.set()
