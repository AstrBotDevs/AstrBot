"""启动引导入口。

对外提供三个顶层启动函数：

- ``run_supervisor``: 启动 Supervisor 进程
- ``run_plugin_worker``: 启动单插件或组 Worker 进程
- ``run_websocket_server``: 以 WebSocket 方式启动 Worker

运行时核心类分布在同目录的子模块：

- ``runtime.supervisor``: ``SupervisorRuntime`` / ``WorkerSession``
- ``runtime.worker``: ``PluginWorkerRuntime`` / ``GroupWorkerRuntime``
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import IO

from ..protocol.wire_codecs import make_protocol_codec
from .loader import PluginEnvironmentManager
from .supervisor import (
    SupervisorRuntime,
    WorkerSession,
    _install_signal_handlers,
    _prepare_stdio_transport,
    _sdk_source_dir,
    _wait_for_shutdown,
)
from .transport import StdioTransport, WebSocketServerTransport
from .worker import GroupWorkerRuntime, PluginWorkerRuntime

__all__ = [
    "GroupWorkerRuntime",
    "PluginWorkerRuntime",
    "SupervisorRuntime",
    "WorkerSession",
    "_install_signal_handlers",
    "_prepare_stdio_transport",
    "_sdk_source_dir",
    "_wait_for_shutdown",
    "run_supervisor",
    "run_plugin_worker",
    "run_websocket_server",
]


async def run_supervisor(
    *,
    plugins_dir: Path = Path("plugins"),
    stdin: IO[str] | IO[bytes] | None = None,
    stdout: IO[str] | IO[bytes] | None = None,
    env_manager: PluginEnvironmentManager | None = None,
    wire_codec: str = "json",
) -> None:
    codec = make_protocol_codec(wire_codec)
    transport_stdin, transport_stdout, original_stdout = _prepare_stdio_transport(
        stdin,
        stdout,
        binary=codec.stdio_framing == "length_prefixed",
    )
    transport = StdioTransport(
        stdin=transport_stdin,
        stdout=transport_stdout,
        framing=codec.stdio_framing,
    )
    runtime = SupervisorRuntime(
        transport=transport,
        plugins_dir=plugins_dir,
        env_manager=env_manager,
        codec=codec,
    )

    try:
        await runtime.start()
        stop_event = asyncio.Event()
        _install_signal_handlers(stop_event)
        await _wait_for_shutdown(runtime.peer, stop_event)
    finally:
        await runtime.stop()
        if original_stdout is not None:
            sys.stdout = original_stdout


async def run_plugin_worker(
    *,
    plugin_dir: Path | None = None,
    group_metadata: Path | None = None,
    stdin: IO[str] | IO[bytes] | None = None,
    stdout: IO[str] | IO[bytes] | None = None,
    wire_codec: str = "json",
) -> None:
    if plugin_dir is None and group_metadata is None:
        raise ValueError("plugin_dir or group_metadata is required")
    if plugin_dir is not None and group_metadata is not None:
        raise ValueError("plugin_dir and group_metadata are mutually exclusive")

    codec = make_protocol_codec(wire_codec)
    transport_stdin, transport_stdout, original_stdout = _prepare_stdio_transport(
        stdin,
        stdout,
        binary=codec.stdio_framing == "length_prefixed",
    )
    transport = StdioTransport(
        stdin=transport_stdin,
        stdout=transport_stdout,
        framing=codec.stdio_framing,
    )
    if group_metadata is not None:
        runtime = GroupWorkerRuntime(
            group_metadata_path=group_metadata,
            transport=transport,
            codec=codec,
        )
    else:
        assert plugin_dir is not None
        runtime = PluginWorkerRuntime(
            plugin_dir=plugin_dir,
            transport=transport,
            codec=codec,
        )
    try:
        await runtime.start()
        stop_event = asyncio.Event()
        _install_signal_handlers(stop_event)
        await _wait_for_shutdown(runtime.peer, stop_event)
    finally:
        await runtime.stop()
        if original_stdout is not None:
            sys.stdout = original_stdout


async def run_websocket_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    path: str = "/",
    plugin_dir: Path | None = None,
    wire_codec: str = "json",
) -> None:
    codec = make_protocol_codec(wire_codec)
    runtime = PluginWorkerRuntime(
        plugin_dir=plugin_dir or Path.cwd(),
        transport=WebSocketServerTransport(
            host=host,
            port=port,
            path=path,
            frame_type=codec.websocket_frame_type,
        ),
        codec=codec,
    )
    try:
        await runtime.start()
        stop_event = asyncio.Event()
        _install_signal_handlers(stop_event)
        await _wait_for_shutdown(runtime.peer, stop_event)
    finally:
        await runtime.stop()
