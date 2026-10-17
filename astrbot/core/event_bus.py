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
from collections.abc import Callable

from astrbot.core import logger
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.config import AstrBotConfig
from astrbot.core.pipeline.scheduler import PipelineScheduler
from astrbot.core.platform.message_type import MessageType

from .platform import AstrMessageEvent

UNIQUE_SESSION_ID_BUILDERS: dict[str, Callable[[AstrMessageEvent], str | None]] = {
    "aiocqhttp": lambda e: f"{e.get_sender_id()}_{e.get_group_id()}",
    "slack": lambda e: f"{e.get_sender_id()}_{e.get_group_id()}",
    "dingtalk": lambda e: e.get_sender_id(),
    "qq_official": lambda e: f"{e.get_sender_id()}_{e.get_group_id()}",
    "qq_official_webhook": lambda e: f"{e.get_sender_id()}_{e.get_group_id()}",
    "lark": lambda e: f"{e.get_sender_id()}%{e.get_group_id()}",
    "misskey": lambda e: f"{e.get_session_id()}_{e.get_sender_id()}",
    "matrix": lambda e: f"{e.get_sender_id()}_{e.get_group_id() or e.get_session_id()}",
}


class EventBus:
    """用于处理事件的分发和处理"""

    def __init__(
        self,
        event_queue: Queue,
        pipeline_scheduler_mapping: dict[str, PipelineScheduler],
        astrbot_config_mgr: AstrBotConfigManager,
    ) -> None:
        self.event_queue = event_queue  # 事件队列
        # abconf uuid -> scheduler
        self.pipeline_scheduler_mapping = pipeline_scheduler_mapping
        self.astrbot_config_mgr = astrbot_config_mgr
        # 持有正在执行的 pipeline 任务的强引用, 防止 task 在 pending 状态被 GC 回收
        self._pending_tasks: set[asyncio.Task] = set()

    async def dispatch(self) -> None:
        while True:
            event: AstrMessageEvent = await self.event_queue.get()
            conf_info = self.astrbot_config_mgr.get_conf_info(event.unified_msg_origin)
            conf_id = conf_info["id"]
            conf_name = conf_info.get("name") or conf_id
            self._print_event(event, conf_name)
            scheduler = self.pipeline_scheduler_mapping.get(conf_id)
            if not scheduler:
                logger.error(
                    f"PipelineScheduler not found for id: {conf_id}, event ignored."
                )
                continue
            self._apply_session_isolation(event, scheduler.ctx.astrbot_config)
            task = asyncio.create_task(scheduler.execute(event))
            self._pending_tasks.add(task)
            task.add_done_callback(self._on_task_done)

    def _apply_session_isolation(
        self,
        event: AstrMessageEvent,
        config: AstrBotConfig,
    ) -> None:
        """Finalize the session before pipeline registration and stop lookup.

        Args:
            event: Incoming event whose original UMO was used to select a profile.
            config: Selected profile's configuration controlling session isolation.
        """
        event.set_extra("_session_isolated", False)
        platform_settings = config.get("platform_settings", {})
        if platform_settings.get("unique_session", False) and (
            event.message_obj.type == MessageType.GROUP_MESSAGE
        ):
            builder = UNIQUE_SESSION_ID_BUILDERS.get(event.get_platform_name())
            sid = builder(event) if builder else None
            if sid:
                event.session_id = sid
                event.set_extra("_session_isolated", True)

    def _on_task_done(self, task: asyncio.Task) -> None:
        """pipeline 任务结束回调: 移除强引用并暴露未捕获的异常"""
        self._pending_tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("Pipeline task failed.", exc_info=exc)

    def _print_event(self, event: AstrMessageEvent, conf_name: str) -> None:
        """用于记录事件信息

        Args:
            event (AstrMessageEvent): 事件对象

        """
        log_extra = {
            "category": "user_chat",
            "platform_id": event.get_platform_id(),
            "platform_type": event.get_platform_name(),
        }
        # 如果有发送者名称: [平台名] 发送者名称/发送者ID: 消息概要
        if event.get_sender_name():
            logger.info(
                f"[{conf_name}] [{event.get_platform_id()}({event.get_platform_name()})] {event.get_sender_name()}/{event.get_sender_id()}: {event.get_message_outline()}",
                extra=log_extra,
            )
        # 没有发送者名称: [平台名] 发送者ID: 消息概要
        else:
            logger.info(
                f"[{conf_name}] [{event.get_platform_id()}({event.get_platform_name()})] {event.get_sender_id()}: {event.get_message_outline()}",
                extra=log_extra,
            )
