import abc
from collections.abc import AsyncGenerator, Coroutine
from typing import Any

from astrbot.core.platform.astr_message_event import AstrMessageEvent

from .context import PipelineContext

StageProcessResult = Coroutine[Any, Any, None] | AsyncGenerator[None]


class Stage(abc.ABC):
    """描述一个 Pipeline 的某个阶段"""

    @abc.abstractmethod
    async def initialize(self, ctx: PipelineContext) -> None:
        """初始化阶段

        Args:
            ctx (PipelineContext): 消息管道上下文对象, 包括配置和插件管理器

        """
        raise NotImplementedError

    @abc.abstractmethod
    def process(self, event: AstrMessageEvent) -> StageProcessResult:
        """处理事件

        Args:
            event (AstrMessageEvent): 事件对象，包含事件的相关信息
        Returns:
            Coroutine or async generator. A coroutine finishes the stage without
            entering the onion-model nested stages. An async generator yields
            control so later stages can run before post-processing resumes.

        """
        raise NotImplementedError
