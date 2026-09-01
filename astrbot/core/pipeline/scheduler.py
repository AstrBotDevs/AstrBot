from collections.abc import AsyncGenerator, Awaitable
from time import time
from typing import Protocol, cast

from astrbot import logger
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.astr_message_event import AstrMessageEvent

from .bootstrap import builtin_stage_classes
from .context import PipelineContext
from .stage import Stage


class _EmptyCompletionEvent(Protocol):
    """An adapter event that accepts an empty completion signal."""

    def send(self, message: MessageChain | None) -> Awaitable[object]: ...


class PipelineScheduler:
    """管道调度器，负责调度各个阶段的执行"""

    _PIPELINE_SLOW_LOG_THRESHOLD_S = 1.0

    def __init__(self, context: PipelineContext) -> None:
        self.ctx = context  # 上下文对象
        self.stage_classes = builtin_stage_classes()
        self.stages: list[Stage] = []  # 存储阶段实例

    async def initialize(self) -> None:
        """初始化管道调度器时, 初始化所有阶段"""
        for stage_cls in self.stage_classes:
            stage_instance = stage_cls()  # 创建实例
            await stage_instance.initialize(self.ctx)
            self.stages.append(stage_instance)

    async def _process_stages(self, event: AstrMessageEvent, from_stage=0) -> None:
        """依次执行各个阶段

        Args:
            event (AstrMessageEvent): 事件对象
            from_stage (int): 从第几个阶段开始执行, 默认从0开始

        """
        for i in range(from_stage, len(self.stages)):
            stage = self.stages[i]  # 获取当前要执行的阶段
            # logger.debug(f"执行阶段 {stage.__class__.__name__}")
            coroutine = stage.process(
                event,
            )  # 调用阶段的process方法, 返回协程或者异步生成器

            if isinstance(coroutine, AsyncGenerator):
                # 如果返回的是异步生成器, 实现洋葱模型的核心
                agen = cast(AsyncGenerator[None], coroutine)
                async for _ in agen:
                    # 此处是前置处理完成后的暂停点(yield), 下面开始执行后续阶段
                    if event.is_stopped():
                        logger.debug(
                            f"阶段 {stage.__class__.__name__} 已终止事件传播。",
                        )
                        break

                    # 递归调用, 处理所有后续阶段
                    await self._process_stages(event, i + 1)

                    # 此处是后续所有阶段处理完毕后返回的点, 执行后置处理
                    if event.is_stopped():
                        logger.debug(
                            f"阶段 {stage.__class__.__name__} 已终止事件传播。",
                        )
                        break
            else:
                # 如果返回的是普通协程(不含yield的async函数), 则不进入下一层(基线条件)
                # 简单地等待它执行完成, 然后继续执行下一个阶段
                await coroutine

                if event.is_stopped():
                    logger.debug(f"阶段 {stage.__class__.__name__} 已终止事件传播。")
                    break

    async def execute(self, event: AstrMessageEvent) -> None:
        """执行 pipeline

        Args:
            event (AstrMessageEvent): 事件对象

        """
        self.ctx.execution_context.active_event_registry.register(event)
        started_at = time()
        try:
            await self._process_stages(event)

            # 发送一个空消息, 以便于后续的处理
            if event.requires_empty_completion and not event.get_extra(
                "skip_empty_completion"
            ):
                # Only adapters whose send implementation accepts ``None`` set this
                # flag. The base event contract deliberately remains message-only.
                # Coalesced fragments skip this so WebChat does not emit ``end``
                # before the later flush event replies.
                await cast(_EmptyCompletionEvent, event).send(None)

            elapsed = time() - started_at
            if elapsed >= self._PIPELINE_SLOW_LOG_THRESHOLD_S:
                logger.info(
                    "pipeline completed in %.2fs. platform=%s session=%s message=%s",
                    elapsed,
                    event.get_platform_id(),
                    event.unified_msg_origin,
                    event.get_message_outline(),
                )
            else:
                logger.debug("pipeline execution completed.")
        finally:
            event.cleanup_temporary_local_files()
            self.ctx.execution_context.active_event_registry.unregister(event)
