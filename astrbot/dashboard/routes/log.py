import asyncio
from quart import websocket
from astrbot.core import logger, LogBroker
from .route import Route, RouteContext


class LogRoute(Route):
    def __init__(self, context: RouteContext, log_broker: LogBroker) -> None:
        super().__init__(context)
        self.log_broker = log_broker
        self.app.add_url_rule(
            "/api/live-log", view_func=self.log, methods=["GET"], websocket=True
        )

    async def log(self):
        queue = None
        try:
            queue = self.log_broker.register()
            while True:
                message = await queue.get()
                await websocket.send(message)
        except asyncio.CancelledError:
            pass
        except BaseException as e:
            logger.error(f"WebSocket 连接错误: {e}")
        finally:
            if queue:
                self.log_broker.unregister(queue)
