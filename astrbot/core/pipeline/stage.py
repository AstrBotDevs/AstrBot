from __future__ import annotations

import abc
from collections.abc import AsyncGenerator, Coroutine
from typing import Any

from astrbot.core.platform.astr_message_event import AstrMessageEvent

from .context import PipelineContext

registered_stages: list[type[Stage]] = []  # 维护了所有已注册的 Stage 实现类类型


def register_stage(cls):
    """一个简单的装饰器，用于注册 pipeline 包下的 Stage 实现类"""
    registered_stages.append(cls)
    return cls


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
    def process(
        self,
        event: AstrMessageEvent,
    ) -> AsyncGenerator[None] | Coroutine[Any, Any, None | AsyncGenerator[None]]:
        """处理事件

        Args:
            event (AstrMessageEvent): 事件对象，包含事件的相关信息
        Returns:
            协程，或在产出时让调度器进入下一阶段的异步生成器。

        """
        raise NotImplementedError
