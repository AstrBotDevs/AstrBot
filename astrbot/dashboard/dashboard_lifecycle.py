import asyncio
from astrbot.core import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from .server import AstrBotDashboard
from astrbot.core.db import BaseDatabase

class AstrBotDashBoardLifecycle:
    def __init__(self, db: BaseDatabase):
        self.db = db
        self.logger = logger
        self.dashboard_server = None
        
    async def start(self, core_lifecycle: AstrBotCoreLifecycle):
        core_task = core_lifecycle.start()
        self.dashboard_server = AstrBotDashboard(core_lifecycle, self.db)
        
        task = asyncio.gather(core_task, self.dashboard_server.run())
        
        try:
            await task
        except asyncio.CancelledError:
            logger.info("🌈 正在关闭 AstrBot...")
            await core_lifecycle.stop()