import asyncio
import signal
from .rpc.server import WebSocketServer
from .star_runner import StarRunner
from .star_manager import StarManager
from ..runtime.api.context import Context
from loguru import logger


async def amain(port: int = 8765):
    server = WebSocketServer(port=port)
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
