"""事件总线, 用于处理事件的分发和处理
事件总线是一个异步队列, 用于接收各种消息事件, 并将其发送到Scheduler调度器进行处理
其中包含了一个无限循环的调度函数, 用于从事件队列中获取新的事件, 并创建一个新的异步任务来执行管道调度器的处理逻辑

class:
    EventBus: 事件总线, 用于处理事件的分发和处理

工作流程:
1. 维护一个异步队列, 来接受各种消息事件
2. 无限循环的调度函数, 从事件队列中获取新的事件, 打印日志并创建一个新的异步任务来执行管道调度器的处理逻辑
"""

import asyncio
from asyncio import Queue

from astrbot.core import logger
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.pipeline.scheduler import PipelineScheduler
from astrbot.core.background_tool.manager import BackgroundToolManager
from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import MessageChain

from .platform import AstrMessageEvent


class EventBus:
    """用于处理事件的分发和处理"""

    def __init__(
        self,
        event_queue: Queue,
        pipeline_scheduler_mapping: dict[str, PipelineScheduler],
        astrbot_config_mgr: AstrBotConfigManager,
    ):
        self.event_queue = event_queue  # 事件队列
        # abconf uuid -> scheduler
        self.pipeline_scheduler_mapping = pipeline_scheduler_mapping
        self.astrbot_config_mgr = astrbot_config_mgr

    async def dispatch(self):
        while True:
            event: AstrMessageEvent = await self.event_queue.get()
            conf_info = self.astrbot_config_mgr.get_conf_info(event.unified_msg_origin)
            self._print_event(event, conf_info["name"])

            # 设置中断标记，用于打断正在执行的wait_tool_result
            try:
                manager = BackgroundToolManager()
                session_id = event.unified_msg_origin
                manager.set_interrupt_flag(session_id)

                # 检查是否有正在运行的后台任务，如果有则注入状态信息
                running_tasks_status = manager.get_running_tasks_status(session_id)
                if running_tasks_status:
                    # 将后台任务状态信息注入到event对象中
                    event.background_tasks_status = running_tasks_status
                    logger.info(
                        f"[EventBus] Injected background tasks status for session {session_id}"
                    )
            except Exception as e:
                logger.error(f"[EventBus] Failed to set interrupt flag: {e}")

            # 将待处理的后台任务通知注入到event中，供AI处理
            await self._inject_notifications(event)

            scheduler = self.pipeline_scheduler_mapping.get(conf_info["id"])
            if not scheduler:
                logger.error(
                    f"PipelineScheduler not found for id: {conf_info['id']}, event ignored."
                )
                continue
            asyncio.create_task(scheduler.execute(event))

    def _print_event(self, event: AstrMessageEvent, conf_name: str):
        """用于记录事件信息

        Args:
            event (AstrMessageEvent): 事件对象

        """
        event.trace.record("event_dispatch", config_name=conf_name)
        # 如果有发送者名称: [平台名] 发送者名称/发送者ID: 消息概要
        if event.get_sender_name():
            logger.info(
                f"[{conf_name}] [{event.get_platform_id()}({event.get_platform_name()})] {event.get_sender_name()}/{event.get_sender_id()}: {event.get_message_outline()}",
            )
        # 没有发送者名称: [平台名] 发送者ID: 消息概要
        else:
            logger.info(
                f"[{conf_name}] [{event.get_platform_id()}({event.get_platform_name()})] {event.get_sender_id()}: {event.get_message_outline()}",
            )

    async def _inject_notifications(self, event: AstrMessageEvent):
        """将待处理的后台任务通知注入到event对象中，供AI处理"""
        try:
            manager = BackgroundToolManager()
            session_id = event.unified_msg_origin

            # 获取待发送通知
            notifications = manager.get_pending_notifications(session_id)

            if not notifications:
                return

            logger.info(
                f"[EventBus] Found {len(notifications)} pending notifications for session {session_id}"
            )

            # 将通知注入到event对象中，让AI处理
            event.pending_notifications = notifications
            logger.info(
                f"[EventBus] Injected {len(notifications)} notifications into event for AI processing"
            )
        except Exception as e:
            logger.error(f"[EventBus] Error injecting notifications: {e}")
