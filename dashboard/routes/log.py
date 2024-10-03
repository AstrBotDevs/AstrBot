import asyncio
from quart import websocket
from quart import Quart
from type.types import Context
from .. import logger

class Broker:
    def __init__(self) -> None:
        self.connections = set()
        
    async def send(self, message: str):
        for connection in self.connections:
            try:
                await connection.send(message)
            except Exception as e:
                logger.warning(f"发送日志失败: {e.__str__()}")

            
class LogRoute:
    def __init__(self, context: Context, app: Quart) -> None:
        self.app = app
        self.context = context
        self.broker = Broker()
        self.app.add_url_rule('/api/live-log', view_func=self.log, methods=['GET'], websocket=True)
        
    async def _receive_log_task(self):
        while True:
            message = await self.context._log_queue.get()
            await self.broker.send(message)
            
    async def _get_log_history(self):
        try:
            dq = self.context._log_queue.get_cache()
            ret = ""
            for log in dq:
                log = log.replace("\n", "\n\r")
                ret += log + "\n\r"
            return ret
        except Exception as e:
            logger.warning(f"读取日志历史失败: {e.__str__()}")
            return ""
            
    async def log(self):
        try:
            await websocket.send(await self._get_log_history())
            self.broker.connections.add(websocket)
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            self.broker.connections.remove(websocket)