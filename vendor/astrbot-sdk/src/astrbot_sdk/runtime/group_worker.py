"""Multiplexed Group Worker runtime: host multiple SDK plugins in one Python process.

Incompatible or ``isolation: dedicated`` plugins still spawn their own
subprocess via ``StdioPluginClient`` / ``StdioPluginServer``. Compatible Python
SDK plugins share one OS process over a newline-framed tab-delimited mux:

    <channel_id>\\t<json_line>\\n

The reserved ``__ctrl__`` channel manages plugin channel open/close and graceful
process shutdown without touching the per-plugin JSON-RPC protocol inside each
channel.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import sys
import uuid
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any, BinaryIO

from ..errors import HostUnavailable, RemotePluginError
from ..protocol import MAX_FRAME_BYTES
from .env import runner_env
from .loader import _plugin_namespace
from .stdio_client import StdioPluginClient
from .stdio_server import StdioPluginServer
from .transport import FrameTransport

CTRL_CHANNEL = "__ctrl__"
_MAX_MUX_LINE_BYTES = MAX_FRAME_BYTES + 256


class MuxChannelTransport:
    """Virtual ``FrameTransport`` for one plugin channel over a shared stream."""

    def __init__(
        self,
        channel_id: str,
        *,
        send_frame: Callable[[str, bytes], Awaitable[None]],
        on_close: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        """Initialize a multiplexed channel transport.

        Args:
            channel_id: Unique channel identifier on the shared process stream.
            send_frame: Async callback writing one payload frame for this channel.
            on_close: Optional async callback notifying the peer on local close.
        """
        self.channel_id = channel_id
        self._send_frame = send_frame
        self._on_close = on_close
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._closed = asyncio.Event()
        self._eof_queued = False
        self._close_notified = False

    def feed(self, payload: bytes) -> None:
        """Deliver one incoming frame from the shared demux reader."""
        if not self._closed.is_set():
            self._queue.put_nowait(payload)

    def close_remote(self) -> None:
        """Mark the channel closed after peer EOF or close notification."""
        self._closed.set()
        if not self._eof_queued:
            self._eof_queued = True
            self._queue.put_nowait(None)

    async def read(self) -> bytes | None:
        """Read the next frame payload; ``None`` signals channel close."""
        return await self._queue.get()

    async def write(self, data: bytes) -> None:
        """Write one frame payload onto this channel."""
        if self._closed.is_set():
            raise HostUnavailable(f"mux channel {self.channel_id} is closed")
        await self._send_frame(self.channel_id, data)

    async def close(self) -> None:
        """Close the local side of this channel and notify the peer once."""
        self.close_remote()
        if self._on_close is not None and not self._close_notified:
            self._close_notified = True
            with contextlib.suppress(HostUnavailable, BrokenPipeError, ConnectionError):
                await self._on_close(self.channel_id)

    async def wait_closed(self) -> None:
        """Wait until this channel has been closed by either side."""
        await self._closed.wait()

    @property
    def closed(self) -> bool:
        """Whether this channel has been closed."""
        return self._closed.is_set()


class GroupStdioServer:
    """Serve multiple SDK plugins concurrently over one multiplexed stdio stream."""

    def __init__(
        self,
        *,
        reader: BinaryIO | None = None,
        writer: BinaryIO | None = None,
    ) -> None:
        """Initialize the shared worker server.

        Args:
            reader: Binary input stream. Defaults to process stdin.
            writer: Binary output stream. Defaults to a duplicated private stdout
                fd with ``fd 1`` redirected to stderr once for the whole process.
        """
        self._owns_writer = writer is None
        if writer is None:
            writer = os.fdopen(os.dup(1), "wb", closefd=True)
            os.dup2(2, 1)
            sys.stdout = sys.stderr
        self._reader = reader or sys.stdin.buffer
        self._writer = writer
        self._write_lock = asyncio.Lock()
        self._channels: dict[str, MuxChannelTransport] = {}
        self._channel_roots: dict[str, Path] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._closing = False

    async def _write_mux(self, channel: str, payload: bytes) -> None:
        """Write one ``<channel>\\t<payload>\\n`` line atomically."""
        if not payload.endswith(b"\n"):
            payload = payload + b"\n"
        line = channel.encode("utf-8") + b"\t" + payload
        async with self._write_lock:
            try:
                self._writer.write(line)
                self._writer.flush()
            except (BrokenPipeError, ConnectionError, ValueError, OSError) as exc:
                raise HostUnavailable("group stdio transport is closed") from exc

    async def _send_ctrl(self, payload: Mapping[str, Any]) -> None:
        """Send one control-channel JSON message back to the Host."""
        raw = json.dumps(
            dict(payload),
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        await self._write_mux(CTRL_CHANNEL, raw + b"\n")

    async def _run_plugin(
        self,
        channel: str,
        plugin_root: Path,
        legacy: bool,
        transport: MuxChannelTransport,
    ) -> None:
        """Run one plugin's ``StdioPluginServer`` until shutdown or EOF."""
        try:
            server = StdioPluginServer(
                plugin_root,
                legacy=legacy,
                transport=transport,
            )
            await server.serve()
        except Exception:
            logging.getLogger("astrbot.sdk.group_worker").exception(
                "plugin channel %s (%s) crashed",
                channel,
                plugin_root,
            )
        finally:
            self._channels.pop(channel, None)
            self._channel_roots.pop(channel, None)
            self._tasks.pop(channel, None)
            transport.close_remote()
            if not legacy and plugin_root not in self._channel_roots.values():
                # Drop stale namespace modules so reloading the plugin in the
                # same Group Worker imports updated files from disk cleanly.
                namespace = _plugin_namespace(plugin_root)
                prefix = f"{namespace}."
                for mod_name in [
                    name
                    for name in tuple(sys.modules)
                    if name == namespace or name.startswith(prefix)
                ]:
                    sys.modules.pop(mod_name, None)
            if not self._closing:
                with contextlib.suppress(
                    HostUnavailable,
                    BrokenPipeError,
                    ConnectionError,
                    OSError,
                ):
                    await self._send_ctrl({"op": "closed", "channel": channel})

    async def _handle_ctrl(self, payload: bytes) -> bool:
        """Dispatch one ``__ctrl__`` command; return False to break the loop."""
        try:
            msg = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return True
        if not isinstance(msg, Mapping):
            return True
        op = msg.get("op")
        req_id = msg.get("req_id")
        if op == "shutdown":
            return False
        if op == "close":
            channel = str(msg.get("channel") or "")
            ch_tr = self._channels.get(channel)
            if ch_tr is not None:
                ch_tr.close_remote()
            return True
        if op != "open":
            if req_id is not None:
                await self._send_ctrl(
                    {
                        "op": "error",
                        "req_id": req_id,
                        "message": f"unknown control op: {op!r}",
                    }
                )
            return True

        channel = str(msg.get("channel") or "")
        raw_root = str(msg.get("plugin_root") or "")
        legacy = bool(msg.get("legacy"))
        if not channel or not raw_root:
            if req_id is not None:
                await self._send_ctrl(
                    {
                        "op": "error",
                        "req_id": req_id,
                        "channel": channel,
                        "message": "open requires channel and plugin_root",
                    }
                )
            return True
        if channel in self._channels:
            if req_id is not None:
                await self._send_ctrl(
                    {
                        "op": "error",
                        "req_id": req_id,
                        "channel": channel,
                        "message": f"duplicate channel id: {channel}",
                    }
                )
            return True
        root, is_dir = await asyncio.to_thread(
            lambda p: (r := Path(p).resolve(), r.is_dir()),
            raw_root,
        )
        if not is_dir:
            if req_id is not None:
                await self._send_ctrl(
                    {
                        "op": "error",
                        "req_id": req_id,
                        "channel": channel,
                        "message": f"plugin root does not exist: {root}",
                    }
                )
            return True

        ch_tr = MuxChannelTransport(channel, send_frame=self._write_mux)
        if not legacy and root not in self._channel_roots.values():
            namespace = _plugin_namespace(root)
            prefix = f"{namespace}."
            for mod_name in [
                name
                for name in tuple(sys.modules)
                if name == namespace or name.startswith(prefix)
            ]:
                sys.modules.pop(mod_name, None)
        self._channels[channel] = ch_tr
        self._channel_roots[channel] = root
        self._tasks[channel] = asyncio.create_task(
            self._run_plugin(channel, root, legacy, ch_tr)
        )
        if req_id is not None:
            await self._send_ctrl(
                {"op": "opened", "req_id": req_id, "channel": channel}
            )
        return True

    async def serve(self) -> None:
        """Read multiplexed lines from stdin until shutdown or EOF."""
        try:
            while not self._closing:
                line = await asyncio.to_thread(
                    self._reader.readline,
                    _MAX_MUX_LINE_BYTES,
                )
                if not line:
                    break
                if len(line) >= _MAX_MUX_LINE_BYTES and not line.endswith(b"\n"):
                    break
                ch_bytes, sep, payload = line.partition(b"\t")
                if not sep:
                    continue
                channel = ch_bytes.decode("utf-8", errors="replace")
                if channel == CTRL_CHANNEL:
                    if not await self._handle_ctrl(payload):
                        break
                    continue
                ch_tr = self._channels.get(channel)
                if ch_tr is not None:
                    ch_tr.feed(payload)
        finally:
            self._closing = True
            for ch_tr in list(self._channels.values()):
                ch_tr.close_remote()
            tasks = list(self._tasks.values())
            if tasks:
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*tasks, return_exceptions=True),
                        timeout=5.0,
                    )
                except TimeoutError:
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
            if self._owns_writer:
                with contextlib.suppress(Exception):
                    self._writer.close()


async def serve_group_stdio() -> None:
    """Entrypoint for ``python -m astrbot_sdk.runtime --group-stdio``."""
    await GroupStdioServer().serve()


class MuxPluginClient(StdioPluginClient):
    """Host-side client for one plugin channel inside a shared ``GroupWorkerClient``."""

    def __init__(
        self,
        plugin_root: Path,
        *,
        group_client: GroupWorkerClient,
        channel_id: str,
        transport: MuxChannelTransport,
        on_release: Callable[[], Awaitable[None]] | None = None,
        **kwargs: Any,
    ) -> None:
        """Bind a ``StdioPluginClient`` facade to one channel on a shared worker.

        Args:
            plugin_root: Plugin directory served through this channel.
            group_client: Shared ``GroupWorkerClient`` owning the subprocess.
            channel_id: Channel ID assigned by ``GroupWorkerClient.open_plugin``.
            transport: Multiplexed channel transport for this plugin.
            on_release: Optional callback invoked once when this channel closes.
            **kwargs: Forwarded to ``StdioPluginClient``.
        """
        super().__init__(plugin_root, **kwargs)
        self._group_client = group_client
        self._channel_id = channel_id
        self._mux_transport = transport
        self._on_release = on_release
        self._released = False

    @property
    def pid(self) -> int | None:
        """Return the PID of the underlying shared Group Worker process."""
        return self._group_client.pid

    async def _open_transport(self) -> FrameTransport:
        """Attach to the already-opened multiplexed channel."""
        if self._mux_transport.closed or not self._group_client.is_running:
            raise HostUnavailable("group worker channel is closed")
        return self._mux_transport

    async def _close_transport(self) -> None:
        """Close the channel and notify the owning pool once."""
        try:
            await self._mux_transport.close()
        finally:
            if self._on_release is not None and not self._released:
                self._released = True
                await self._on_release()

    @property
    def is_running(self) -> bool:
        """Whether both the shared Group Worker and this channel are open."""
        return self._group_client.is_running and not self._mux_transport.closed

    async def wait_exited(self) -> int | None:
        """Wait until this channel or the shared Group Worker exits."""
        await self._mux_transport.wait_closed()
        return self._group_client.returncode

    def kill_process(self) -> None:
        """Force-kill the shared Group Worker process when hung."""
        self._group_client.kill()


class GroupWorkerClient:
    """Manage one shared ``--group-stdio`` Python worker hosting multiple plugins."""

    def __init__(
        self,
        *,
        python_executable: Path | str | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float = 10.0,
        start_timeout: float = 180.0,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize a shared Group Worker process handle.

        Args:
            python_executable: Python interpreter for the environment group.
            env: Extra environment variables merged over the scrubbed env.
            timeout: Control shutdown timeout in seconds.
            start_timeout: Maximum time to wait for plugin channel open acks.
            logger: Logger receiving shared worker stderr and diagnostics.
        """
        self.python_executable = str(python_executable or sys.executable)
        self._extra_env = dict(env or {})
        self.timeout = timeout
        self.start_timeout = start_timeout
        self.logger = logger or logging.getLogger("astrbot.group_worker")
        self._process: asyncio.subprocess.Process | None = None
        self._write_lock = asyncio.Lock()
        self._channels: dict[str, MuxChannelTransport] = {}
        self._pending_opens: dict[str, asyncio.Future[None]] = {}
        self._next_channel = 0
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._closing = False
        self._started = False

    @property
    def pid(self) -> int | None:
        """Return the OS PID of the shared Group Worker subprocess."""
        return self._process.pid if self._process is not None else None

    @property
    def returncode(self) -> int | None:
        """Return the process exit code if exited, else ``None``."""
        return self._process.returncode if self._process is not None else None

    @property
    def is_running(self) -> bool:
        """Whether the shared Group Worker subprocess is alive."""
        return self._process is not None and self._process.returncode is None

    @property
    def active_channel_count(self) -> int:
        """Return the number of currently active plugin channels."""
        return len(self._channels)

    async def start(self) -> None:
        """Spawn the ``--group-stdio`` subprocess and start the demux reader."""
        if self._started:
            return
        self._closing = False
        self._process = await asyncio.create_subprocess_exec(
            self.python_executable,
            "-m",
            "astrbot_sdk.runtime",
            "--group-stdio",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=runner_env(self._extra_env),
            limit=_MAX_MUX_LINE_BYTES,
        )
        if self._process.stdin is None or self._process.stdout is None:
            raise HostUnavailable("group worker stdio pipes are unavailable")
        self._started = True
        self._reader_task = asyncio.create_task(self._read_loop())
        if self._process.stderr is not None:
            self._stderr_task = asyncio.create_task(self._read_stderr())

    async def _write_mux(self, channel: str, data: bytes) -> None:
        """Write one multiplexed frame to the shared worker stdin."""
        process = self._process
        if process is None or process.stdin is None or process.stdin.is_closing():
            raise HostUnavailable("group worker transport is closed")
        if not data.endswith(b"\n"):
            data = data + b"\n"
        line = channel.encode("utf-8") + b"\t" + data
        try:
            async with self._write_lock:
                process.stdin.write(line)
                await process.stdin.drain()
        except (BrokenPipeError, ConnectionError, OSError) as exc:
            raise HostUnavailable("group worker transport is closed") from exc

    async def _send_ctrl(self, payload: Mapping[str, Any]) -> None:
        """Write one JSON control message to ``__ctrl__``."""
        raw = json.dumps(
            dict(payload),
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        await self._write_mux(CTRL_CHANNEL, raw + b"\n")

    async def _send_close_channel(self, channel_id: str) -> None:
        """Notify the remote Group Worker that one channel closed locally."""
        self._channels.pop(channel_id, None)
        await self._send_ctrl({"op": "close", "channel": channel_id})

    async def open_plugin(
        self,
        plugin_root: Path,
        *,
        legacy: bool = False,
        on_release: Callable[[], Awaitable[None]] | None = None,
        **client_kwargs: Any,
    ) -> MuxPluginClient:
        """Open a dedicated channel for one plugin inside this Group Worker.

        Args:
            plugin_root: Directory containing the plugin to load.
            legacy: Whether to load via ``compat.v1``.
            on_release: Callback invoked once when the returned client closes.
            **client_kwargs: Extra ``StdioPluginClient`` keyword arguments.

        Returns:
            Bound ``MuxPluginClient`` ready for ``start(...)``.

        Raises:
            HostUnavailable: The Group Worker is not running or closed during open.
            RemotePluginError: The Group Worker rejected the channel open request.
        """
        if not self.is_running:
            raise HostUnavailable("group worker is not running")
        self._next_channel += 1
        channel_id = f"ch-{self._next_channel}"
        req_id = uuid.uuid4().hex
        transport = MuxChannelTransport(
            channel_id,
            send_frame=self._write_mux,
            on_close=self._send_close_channel,
        )
        fut: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._channels[channel_id] = transport
        self._pending_opens[req_id] = fut
        resolved_root = str(await asyncio.to_thread(plugin_root.resolve))
        try:
            await self._send_ctrl(
                {
                    "op": "open",
                    "req_id": req_id,
                    "channel": channel_id,
                    "plugin_root": resolved_root,
                    "legacy": legacy,
                }
            )
            await asyncio.wait_for(fut, timeout=self.start_timeout)
        except Exception:
            self._channels.pop(channel_id, None)
            self._pending_opens.pop(req_id, None)
            transport.close_remote()
            raise
        client_kwargs.setdefault("start_timeout", self.start_timeout)
        client_kwargs.setdefault("timeout", self.timeout)
        client_kwargs.setdefault("logger", self.logger)
        client_kwargs.setdefault("python_executable", self.python_executable)
        client_kwargs.setdefault("env", self._extra_env)
        client_kwargs.setdefault("legacy", legacy)
        return MuxPluginClient(
            plugin_root,
            group_client=self,
            channel_id=channel_id,
            transport=transport,
            on_release=on_release,
            **client_kwargs,
        )

    async def _read_loop(self) -> None:
        """Demultiplex lines from the shared worker stdout into channel queues."""
        stdout = self._process.stdout if self._process is not None else None
        if stdout is None:
            return
        try:
            while line := await stdout.readline():
                ch_bytes, sep, payload = line.partition(b"\t")
                if not sep:
                    continue
                channel = ch_bytes.decode("utf-8", errors="replace")
                if channel == CTRL_CHANNEL:
                    self._handle_ctrl_reply(payload)
                    continue
                ch_tr = self._channels.get(channel)
                if ch_tr is not None:
                    ch_tr.feed(payload)
        except Exception as exc:
            self.logger.debug("GroupWorkerClient read loop error: %s", exc)
        finally:
            for req_id, fut in list(self._pending_opens.items()):
                self._pending_opens.pop(req_id, None)
                if not fut.done():
                    fut.set_exception(HostUnavailable("group worker exited"))
            for ch_tr in list(self._channels.values()):
                ch_tr.close_remote()
            self._channels.clear()

    def _handle_ctrl_reply(self, payload: bytes) -> None:
        """Handle control replies (``opened``, ``closed``, ``error``) from worker."""
        try:
            msg = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        if not isinstance(msg, Mapping):
            return
        op = msg.get("op")
        if op == "opened":
            req_id = str(msg.get("req_id") or "")
            fut = self._pending_opens.pop(req_id, None)
            if fut is not None and not fut.done():
                fut.set_result(None)
        elif op == "error":
            req_id = str(msg.get("req_id") or "")
            fut = self._pending_opens.pop(req_id, None)
            message = str(msg.get("message") or "group worker failed to open channel")
            if fut is not None and not fut.done():
                fut.set_exception(RemotePluginError("PLUGIN_RUNTIME_ERROR", message))
        elif op == "closed":
            channel = str(msg.get("channel") or "")
            ch_tr = self._channels.pop(channel, None)
            if ch_tr is not None:
                ch_tr.close_remote()

    async def _read_stderr(self) -> None:
        """Forward shared worker stderr lines to the Host logger."""
        stderr = self._process.stderr if self._process is not None else None
        if stderr is None:
            return
        while line := await stderr.readline():
            self.logger.debug(
                "Group Worker stderr: %s",
                line.decode("utf-8", errors="replace").rstrip(),
            )

    def kill(self) -> None:
        """Force-kill the shared Group Worker subprocess."""
        process = self._process
        if process is not None and process.returncode is None:
            process.kill()

    async def close(self) -> None:
        """Shut down the shared Group Worker subprocess and cancel reader tasks."""
        if not self._started and self._process is None:
            return
        self._closing = True
        process = self._process
        try:
            if self.is_running:
                with contextlib.suppress(
                    HostUnavailable,
                    BrokenPipeError,
                    ConnectionError,
                    OSError,
                ):
                    await self._send_ctrl({"op": "shutdown"})
            if process is not None and process.stdin is not None:
                if not process.stdin.is_closing():
                    process.stdin.close()
                    with contextlib.suppress(BrokenPipeError, ConnectionError):
                        await process.stdin.wait_closed()
            if process is not None and process.returncode is None:
                try:
                    await asyncio.wait_for(process.wait(), timeout=self.timeout)
                except TimeoutError:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=self.timeout)
                    except TimeoutError:
                        process.kill()
                        await process.wait()
        finally:
            for ch_tr in list(self._channels.values()):
                ch_tr.close_remote()
            self._channels.clear()
            tasks = [t for t in (self._reader_task, self._stderr_task) if t is not None]
            for task in tasks:
                if not task.done():
                    task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            self._reader_task = None
            self._stderr_task = None
            self._process = None
            self._started = False
