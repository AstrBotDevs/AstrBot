"""AstrBot 启动器，负责初始化和启动核心组件和仪表板服务器。

工作流程:
1. 初始化核心生命周期, 传递数据库和日志代理实例到核心生命周期
2. 运行核心生命周期任务和仪表板服务器
"""

import asyncio
import signal
import traceback

from astrbot.core import LogBroker, logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.dashboard.server import AstrBotDashboard

# docker stop 默认 10 秒后发送 SIGKILL，两段超时之和需小于它
STOP_TIMEOUT = 5
DASHBOARD_SHUTDOWN_TIMEOUT = 3


class InitialLoader:
    """AstrBot 启动器，负责初始化和启动核心组件和仪表板服务器。"""

    def __init__(self, db: BaseDatabase, log_broker: LogBroker) -> None:
        self.db = db
        self.logger = logger
        self.log_broker = log_broker
        self.webui_dir: str | None = None

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        main_task = asyncio.current_task()
        # docker stop 发送 SIGTERM，而 PID 1 没有处理器时内核会忽略它。
        # 在初始化之前注册，像 Ctrl+C 一样取消主任务以走优雅退出流程。
        sigterm_installed = False
        if main_task is not None:
            try:
                loop.add_signal_handler(signal.SIGTERM, main_task.cancel)
                sigterm_installed = True
            except (NotImplementedError, RuntimeError):
                # Windows event loops do not support add_signal_handler.
                pass

        try:
            core_lifecycle = AstrBotCoreLifecycle(self.log_broker, self.db)

            try:
                await core_lifecycle.initialize()
            except asyncio.CancelledError:
                logger.info("🌈 Shutting down AstrBot...")
                await self.db.engine.dispose()
                return
            except Exception as e:
                logger.critical(traceback.format_exc())
                logger.critical(f"😭 Failed to initialize AstrBot: {e} !!!")
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
                task = asyncio.ensure_future(core_task)
            try:
                # shield: 收到 SIGTERM/Ctrl+C 时不直接取消 Hypercorn，
                # 而是在下面通过 dashboard_shutdown_event 让它优雅关闭
                await asyncio.shield(task)  # 整个AstrBot在这里运行
            except asyncio.CancelledError:
                logger.info("🌈 Shutting down AstrBot...")
                if sigterm_installed:
                    # 退出过程中忽略重复的 SIGTERM，避免打断 stop()
                    loop.add_signal_handler(signal.SIGTERM, lambda: None)
                stop_task = asyncio.create_task(core_lifecycle.stop())
                try:
                    # 不用 wait_for：它会等待被取消的 stop() 结束，卡住时仍会挂起
                    await asyncio.wait({stop_task}, timeout=STOP_TIMEOUT)
                    if not stop_task.done():
                        logger.error(
                            f"Stopping AstrBot timed out after {STOP_TIMEOUT}s."
                        )
                        stop_task.cancel()
                    elif exc := stop_task.exception():
                        logger.error(
                            "Failed to stop AstrBot: "
                            + "".join(traceback.format_exception(exc))
                        )
                    # stop() 出错或超时时也要关闭 WebUI 并释放数据库
                    core_lifecycle.dashboard_shutdown_event.set()
                    await asyncio.wait({task}, timeout=DASHBOARD_SHUTDOWN_TIMEOUT)
                    if not task.done():
                        task.cancel()
                    elif not task.cancelled() and (exc := task.exception()):
                        logger.error(f"AstrBot exited with an error: {exc!r}")
                finally:
                    await self.db.engine.dispose()
        finally:
            if sigterm_installed:
                loop.remove_signal_handler(signal.SIGTERM)
