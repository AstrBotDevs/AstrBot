import asyncio
import signal
from .rpc.server import WebSocketServer, StdioServer
from .star_runner import StarRunner
from .stars.star_manager import StarManager
from .api.context import Context
from loguru import logger
from typing import IO, Any


async def run_websocket_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    path: str = "/",
    heartbeat_interval: int = 30,
):
    server = WebSocketServer(
        port=port, host=host, path=path, heartbeat=heartbeat_interval
    )
    runner = StarRunner(server)
    context = Context.default_context(runner=runner)
    star_manager = StarManager(context=context)
    star_manager.discover_star()
    await runner.run()

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)

    logger.info("Server is running. Press Ctrl+C to stop.")

    try:
        await stop_event.wait()
    finally:
        logger.info("Shutting down...")
        await server.stop()


async def start_stdio_server(
    stdin: IO[Any] | None = None, stdout: IO[Any] | None = None
):
    """Start a JSON-RPC server over stdio."""
    server = StdioServer(stdin=stdin, stdout=stdout)
    runner = StarRunner(server)
    context = Context.default_context(runner=runner)
    star_manager = StarManager(context=context)
    star_manager.discover_star()
    await runner.run()

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)

    logger.info("Stdio server is running. Press Ctrl+C to stop.")

    try:
        await stop_event.wait()
    finally:
        logger.info("Shutting down...")
        await server.stop()
