import asyncio
from quart import websocket
from quart import Quart
from core.config.astrbot_config import AstrBotConfig
from core import logger, LogBroker
from .route import Route, Response
            
class LogRoute(Route):
    def __init__(self, config: AstrBotConfig, app: Quart, log_broker: LogBroker) -> None:
        super().__init__(config, app)
        self.log_broker = log_broker
        self.app.add_url_rule('/api/live-log', view_func=self.log, methods=['GET'], websocket=True)

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