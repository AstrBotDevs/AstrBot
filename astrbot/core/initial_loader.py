import asyncio
import traceback
from astrbot.core import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.core import LogBroker
from astrbot.dashboard.server import AstrBotDashboard


class InitialLoader:
    def __init__(self, db: BaseDatabase, log_broker: LogBroker):
        self.db = db
        self.logger = logger
        self.log_broker = log_broker

    async def start(self):
        core_lifecycle = AstrBotCoreLifecycle(self.log_broker, self.db)

        core_task = []
        try:
            await core_lifecycle.initialize()
            core_task = core_lifecycle.start()
        except Exception as e:
            logger.critical(traceback.format_exc())
            logger.critical(f"😭 初始化 AstrBot 失败：{e} !!!")

        self.dashboard_server = AstrBotDashboard(
            core_lifecycle, self.db, core_lifecycle.dashboard_shutdown_event
        )
        task = asyncio.gather(core_task, self.dashboard_server.run())

        try:
            await task
        except asyncio.CancelledError:
            logger.info("🌈 正在关闭 AstrBot...")
            await core_lifecycle.stop()
