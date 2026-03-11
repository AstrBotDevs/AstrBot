import asyncio
import signal
import sys
from pathlib import Path
from typing import IO, Any

from loguru import logger

from .api.context import Context
from .rpc.server import StdioServer, WebSocketServer
from .star_runner import StarRunner
from .stars.star_manager import StarManager
from .supervisor import SupervisorRuntime


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            logger.debug(f"Signal handlers are not supported for {sig}")


def _prepare_stdio_transport(
    stdin: IO[Any] | None,
    stdout: IO[Any] | None,
) -> tuple[IO[Any], IO[Any], IO[Any] | None]:
    if stdin is not None and stdout is not None:
        return stdin, stdout, None

    transport_stdin = stdin or sys.stdin
    transport_stdout = stdout or sys.stdout
    original_stdout = sys.stdout
    sys.stdout = sys.stderr
    return transport_stdin, transport_stdout, original_stdout


async def _wait_for_stdio_shutdown(
    server: StdioServer, stop_event: asyncio.Event
) -> None:
    stop_waiter = asyncio.create_task(stop_event.wait())
    stdio_waiter = asyncio.create_task(server.wait_closed())
    done, pending = await asyncio.wait(
        {stop_waiter, stdio_waiter},
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()
    for task in done:
        if task.cancelled():
            continue
        task.result()


async def run_websocket_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    path: str = "/",
    heartbeat_interval: int = 30,
    plugin_dir: str | Path | None = None,
):
    server = WebSocketServer(
        port=port, host=host, path=path, heartbeat=heartbeat_interval
    )
    runner = StarRunner(server)
    context = Context.default_context(runner=runner)
    star_manager = StarManager(context=context)
    star_manager.discover_star(Path(plugin_dir) if plugin_dir else None)
    await runner.run()

    stop_event = asyncio.Event()
    _install_signal_handlers(stop_event)

    logger.info("Server is running. Press Ctrl+C to stop.")

    try:
        await stop_event.wait()
    finally:
        logger.info("Shutting down...")
        await server.stop()


async def run_supervisor(
    plugins_dir: str | Path = "plugins",
    stdin: IO[Any] | None = None,
    stdout: IO[Any] | None = None,
) -> None:
    transport_stdin, transport_stdout, original_stdout = _prepare_stdio_transport(
        stdin, stdout
    )
    server = StdioServer(stdin=transport_stdin, stdout=transport_stdout)
    supervisor = SupervisorRuntime(
        server=server,
        plugins_dir=Path(plugins_dir),
    )

    try:
        await supervisor.start()
        stop_event = asyncio.Event()
        _install_signal_handlers(stop_event)
        logger.info(f"Plugin supervisor is running with plugins dir: {plugins_dir}")
        await _wait_for_stdio_shutdown(server, stop_event)
    finally:
        logger.info("Shutting down plugin supervisor...")
        await supervisor.stop()
        if original_stdout is not None:
            sys.stdout = original_stdout


async def run_plugin_worker(
    plugin_dir: str | Path,
    stdin: IO[Any] | None = None,
    stdout: IO[Any] | None = None,
) -> None:
    transport_stdin, transport_stdout, original_stdout = _prepare_stdio_transport(
        stdin, stdout
    )
    server = StdioServer(stdin=transport_stdin, stdout=transport_stdout)
    runner = StarRunner(server)
    context = Context.default_context(runner=runner)
    star_manager = StarManager(context=context)
    star_manager.discover_star(Path(plugin_dir))

    try:
        await runner.run()
        stop_event = asyncio.Event()
        _install_signal_handlers(stop_event)
        logger.info(f"Plugin worker is running for: {plugin_dir}")
        await _wait_for_stdio_shutdown(server, stop_event)
    finally:
        logger.info("Shutting down plugin worker...")
        await runner.stop()
        if original_stdout is not None:
            sys.stdout = original_stdout
