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
    stdin: IO[str] | None = None,
    stdout: IO[str] | None = None,
    env_manager: PluginEnvironmentManager | None = None,
) -> None:
    transport_stdin, transport_stdout, original_stdout = _prepare_stdio_transport(
        stdin,
        stdout,
    )
    transport = StdioTransport(stdin=transport_stdin, stdout=transport_stdout)
    runtime = SupervisorRuntime(
        transport=transport,
        plugins_dir=plugins_dir,
        env_manager=env_manager,
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
    stdin: IO[str] | None = None,
    stdout: IO[str] | None = None,
) -> None:
    if plugin_dir is None and group_metadata is None:
        raise ValueError("plugin_dir or group_metadata is required")
    if plugin_dir is not None and group_metadata is not None:
        raise ValueError("plugin_dir and group_metadata are mutually exclusive")

    transport_stdin, transport_stdout, original_stdout = _prepare_stdio_transport(
        stdin,
        stdout,
    )
    transport = StdioTransport(stdin=transport_stdin, stdout=transport_stdout)
    if group_metadata is not None:
        runtime = GroupWorkerRuntime(
            group_metadata_path=group_metadata,
            transport=transport,
        )
    else:
        # 前置互斥校验已保证单插件模式下 plugin_dir 一定存在；这里显式收窄，
        # 避免把入口层的 Optional 继续传播到单插件运行时。
        assert plugin_dir is not None
        runtime = PluginWorkerRuntime(plugin_dir=plugin_dir, transport=transport)
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
) -> None:
    runtime = PluginWorkerRuntime(
        plugin_dir=plugin_dir or Path.cwd(),
        transport=WebSocketServerTransport(host=host, port=port, path=path),
    )
    try:
        await runtime.start()
        stop_event = asyncio.Event()
        _install_signal_handlers(stop_event)
        await _wait_for_shutdown(runtime.peer, stop_event)
    finally:
        await runtime.stop()
