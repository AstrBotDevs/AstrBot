from . import STAGES_ORDER
from .stage import registered_stages
from .context import PipelineContext
from typing import AsyncGenerator
from astrbot.core.platform import AstrMessageEvent
from astrbot.core import logger


class PipelineScheduler:
    """管道调度器，负责调度各个阶段的执行"""

    def __init__(self, context: PipelineContext):
        registered_stages.sort(
            key=lambda x: STAGES_ORDER.index(x.__class__.__name__)
        )  # 按照顺序排序
        self.ctx = context  # 上下文对象

    async def initialize(self):
        """初始化管道调度器时, 初始化所有阶段"""
        for stage in registered_stages:
            # logger.debug(f"初始化阶段 {stage.__class__ .__name__}")

            await stage.initialize(self.ctx)

    async def _process_stages(self, event: AstrMessageEvent, from_stage=0):
        """依次执行各个阶段

        Args:
            event (AstrMessageEvent): 事件对象
            from_stage (int): 从第几个阶段开始执行, 默认从0开始
        """
        for i in range(from_stage, len(registered_stages)):
            stage = registered_stages[i]  # 获取当前要执行的阶段
            # logger.debug(f"执行阶段 {stage.__class__ .__name__}")
            coroutine = stage.process(
                event
            )  # 调用阶段的process方法, 返回协程或者异步生成器

            if isinstance(coroutine, AsyncGenerator):
                # 如果返回的是异步生成器, 实现洋葱模型的核心
                async for _ in coroutine:
                    # 此处是前置处理完成后的暂停点(yield), 下面开始执行后续阶段
                    if event.is_stopped():
                        logger.debug(
                            f"阶段 {stage.__class__.__name__} 已终止事件传播。"
                        )
                        break

                    # 递归调用, 处理所有后续阶段
                    await self._process_stages(event, i + 1)

                    # 此处是后续所有阶段处理完毕后返回的点, 执行后置处理
                    if event.is_stopped():
                        logger.debug(
                            f"阶段 {stage.__class__.__name__} 已终止事件传播。"
                        )
                        break
            else:
                # 如果返回的是普通协程(不含yield的async函数), 则不进入下一层(基线条件)
                # 简单地等待它执行完成, 然后继续执行下一个阶段
                await coroutine

                if event.is_stopped():
                    logger.debug(f"阶段 {stage.__class__.__name__} 已终止事件传播。")
                    break

    async def execute(self, event: AstrMessageEvent):
        """执行 pipeline

        Args:
            event (AstrMessageEvent): 事件对象
        """
        await self._process_stages(event)

        # 如果没有发送操作, 则发送一个空消息, 以便于后续的处理
        if event.get_platform_name() == "webchat":
            await event.send(None)

        logger.debug("pipeline 执行完毕。")
