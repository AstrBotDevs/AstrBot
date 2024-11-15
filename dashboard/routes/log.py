import asyncio
from quart import websocket
from quart import Quart
from type.types import Context
from .. import logger
            
class LogRoute:
    def __init__(self, context: Context, app: Quart) -> None:
        self.app = app
        self.context = context
        self.app.add_url_rule('/api/live-log', view_func=self.log, methods=['GET'], websocket=True)

    async def log(self):
        queue = None
        try:
            queue = self.context.log_broker.register()
            while True:
                message = await queue.get()
                await websocket.send(message)
        except asyncio.CancelledError:
            pass
        except BaseException as e:
            logger.error(f"WebSocket 连接错误: {e}")
        finally:
            if queue:
                self.context.log_broker.unregister(queue)