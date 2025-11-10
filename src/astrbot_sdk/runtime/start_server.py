import asyncio
import signal
from .rpc.server import WebSocketServer
from .star_runner import StarRunner
from .star_manager import StarManager
from ..runtime.api.context import Context
from ..runtime.api.conversation_mgr import ConversationManager


async def amain():
    server = WebSocketServer(port=8765)
    conversation_manager = ConversationManager()
    context = Context(conversation_manager=conversation_manager)
    runner = StarRunner(server)
    context._inject_rpc_handlers(runner=runner)
    star_manager = StarManager(context=context)
    star_manager.discover_star()
    await runner.run()

    # 设置停止事件
    stop_event = asyncio.Event()

    # 注册信号处理器
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)

    print("Server is running. Press Ctrl+C to stop.")

    try:
        await stop_event.wait()
    finally:
        print("Shutting down...")
        await server.stop()
