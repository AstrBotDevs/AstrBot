"""AstrBot 启动器,负责初始化和启动核心组件和仪表板服务器｡

工作流程:
1. 初始化核心生命周期, 传递数据库和日志代理实例到核心生命周期
2. 运行核心生命周期任务和仪表板服务器
"""

import asyncio
import traceback
from typing import cast

from astrbot.core import LogBroker, logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.dashboard.server import AstrBotDashboard


class InitialLoader:
    """AstrBot 启动器,负责初始化和启动核心组件和仪表板服务器｡"""

    def __init__(self, db: BaseDatabase, log_broker: LogBroker) -> None:
        self.db = db
        self.logger = logger
        self.log_broker = log_broker
        self.webui_dir: str | None = None

    async def start(self) -> None:
        core_lifecycle = AstrBotCoreLifecycle(self.log_broker, self.db)

        try:
            await core_lifecycle.initialize_core()
        except Exception as e:
            logger.critical(traceback.format_exc())
            logger.critical(f"😭 初始化 AstrBot 失败:{e} !!!")
            return

        core_lifecycle.runtime_bootstrap_task = asyncio.create_task(
            core_lifecycle.bootstrap_runtime(),
        )

        core_task = core_lifecycle.start()
        shutdown_event = core_lifecycle.dashboard_shutdown_event
        if shutdown_event is None:
            raise RuntimeError("initialize_core must set dashboard_shutdown_event")
        shutdown_event = cast(asyncio.Event, shutdown_event)

        webui_dir = self.webui_dir

        self.dashboard_server = AstrBotDashboard(
            core_lifecycle,
            self.db,
            shutdown_event,
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
            logger.info("🌈 正在关闭 AstrBot...")
            await core_lifecycle.stop()
        except Exception:
            await core_lifecycle.stop()
            raise
