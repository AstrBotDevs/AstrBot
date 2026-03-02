"""AstrBot 启动器，负责初始化和启动核心组件和仪表板服务器。

工作流程:
1. 初始化核心生命周期, 传递数据库和日志代理实例到核心生命周期
2. 运行核心生命周期任务和仪表板服务器
"""
from astrbot.core.lang import t

import asyncio
import traceback

from astrbot.core import LogBroker, logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.dashboard.server import AstrBotDashboard


class InitialLoader:
    """AstrBot 启动器，负责初始化和启动核心组件和仪表板服务器。"""

    def __init__(self, db: BaseDatabase, log_broker: LogBroker) -> None:
        self.db = db
        self.logger = logger
        self.log_broker = log_broker
        self.webui_dir: str | None = None

    async def start(self) -> None:
        core_lifecycle = AstrBotCoreLifecycle(self.log_broker, self.db)

        try:
            await core_lifecycle.initialize()
        except Exception as e:
            logger.critical(t("msg-78b9c276", res=traceback.format_exc()))
            logger.critical(t("msg-58525c23", e=e))
            return

        core_task = core_lifecycle.start()

        webui_dir = self.webui_dir

        self.dashboard_server = AstrBotDashboard(
            core_lifecycle,
            self.db,
            core_lifecycle.dashboard_shutdown_event,
            webui_dir,
        )

        coro = self.dashboard_server.run()
        if coro:
            # 启动核心任务和仪表板服务器
            task = asyncio.gather(core_task, coro)
        else:
            task = core_task
        try:
            await task  # 整个AstrBot在这里运行
        except asyncio.CancelledError:
            logger.info(t("msg-002cc3e8"))
            await core_lifecycle.stop()
