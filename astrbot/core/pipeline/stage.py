from __future__ import annotations
import abc
from typing import List, AsyncGenerator, Union
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from .context import PipelineContext

registered_stages: List[Stage] = []  # 维护了所有已注册的 Stage 实现类


def register_stage(cls):
    """一个简单的装饰器，用于注册 pipeline 包下的 Stage 实现类"""
    registered_stages.append(cls())
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
    async def process(
        self, event: AstrMessageEvent
    ) -> Union[None, AsyncGenerator[None, None]]:
        """处理事件

        Args:
            event (AstrMessageEvent): 事件对象，包含事件的相关信息
        Returns:
            Union[None, AsyncGenerator[None, None]]: 处理结果，可能是 None 或者异步生成器, 如果为 None 则表示不需要继续处理, 如果为异步生成器则表示需要继续处理(进入下一个阶段)
        """
        raise NotImplementedError
