import asyncio
from astrbot.core import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from .server import AstrBotDashboard
from astrbot.core.db import BaseDatabase
from astrbot.core import LogBroker
class AstrBotDashBoardLifecycle:
    def __init__(self, db: BaseDatabase, log_broker: LogBroker):
        self.db = db
        self.logger = logger
        self.log_broker = log_broker
        self.dashboard_server = None
        
    async def start(self):
        core_lifecycle = AstrBotCoreLifecycle(self.log_broker, self.db)
        await core_lifecycle.initialize()
        core_task = core_lifecycle.start()
        self.dashboard_server = AstrBotDashboard(core_lifecycle, self.db)
        task = asyncio.gather(core_task, self.dashboard_server.run())
        
        try:
            await task
        except asyncio.CancelledError:
            logger.info("🌈 正在关闭 AstrBot...")
            await core_lifecycle.stop()