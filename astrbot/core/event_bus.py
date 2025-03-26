"""
事件总线, 用于处理事件的分发和处理
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
from astrbot.core.pipeline.scheduler import PipelineScheduler
from astrbot.core import logger
from .platform import AstrMessageEvent


class EventBus:
    """事件总线: 用于处理事件的分发和处理

    维护一个异步队列, 来接受各种消息事件
    """

    def __init__(self, event_queue: Queue, pipeline_scheduler: PipelineScheduler):
        self.event_queue = event_queue  # 事件队列
        self.pipeline_scheduler = pipeline_scheduler  # 管道调度器

    async def dispatch(self):
        """无限循环的调度函数, 从事件队列中获取新的事件, 打印日志并创建一个新的异步任务来执行管道调度器的处理逻辑"""
        while True:
            event: AstrMessageEvent = (
                await self.event_queue.get()
            )  # 从事件队列中获取新的事件
            self._print_event(event)  # 打印日志
            asyncio.create_task(
                self.pipeline_scheduler.execute(event)
            )  # 创建新的异步任务来执行管道调度器的处理逻辑

    def _print_event(self, event: AstrMessageEvent):
        """用于记录事件信息

        Args:
            event (AstrMessageEvent): 事件对象
        """
        # 如果有发送者名称: [平台名] 发送者名称/发送者ID: 消息概要
        if event.get_sender_name():
            logger.info(
                f"[{event.get_platform_name()}] {event.get_sender_name()}/{event.get_sender_id()}: {event.get_message_outline()}"
            )
        # 没有发送者名称: [平台名] 发送者ID: 消息概要
        else:
            logger.info(
                f"[{event.get_platform_name()}] {event.get_sender_id()}: {event.get_message_outline()}"
            )
