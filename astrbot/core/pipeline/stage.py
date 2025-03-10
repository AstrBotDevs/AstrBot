from __future__ import annotations
import abc
import inspect
import traceback
from astrbot.api import logger
from typing import List, AsyncGenerator, Union, Awaitable
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from .context import PipelineContext
from astrbot.core.message.message_event_result import MessageEventResult, CommandResult

registered_stages: List[Stage] = []
"""维护了所有已注册的 Stage 实现类"""


def register_stage(cls):
    """一个简单的装饰器，用于注册 pipeline 包下的 Stage 实现类"""
    registered_stages.append(cls())
    return cls


class Stage(abc.ABC):
    """描述一个 Pipeline 的某个阶段"""

    @abc.abstractmethod
    async def initialize(self, ctx: PipelineContext) -> None:
        """初始化阶段"""
        raise NotImplementedError

    @abc.abstractmethod
    async def process(
        self, event: AstrMessageEvent
    ) -> Union[None, AsyncGenerator[None, None]]:
        """处理事件"""
        raise NotImplementedError

    async def _call_handler(
        self,
        ctx: PipelineContext,
        event: AstrMessageEvent,
        handler: Awaitable,
        *args,
        **kwargs,
    ) -> AsyncGenerator[None, None]:
        """调用 Handler。"""
        # 判断 handler 是否是类方法（通过装饰器注册的没有 __self__ 属性）
        ready_to_call = None

        trace_ = None

        try:
            ready_to_call = handler(event, *args, **kwargs)
        except TypeError as _:
            # 向下兼容
            trace_ = traceback.format_exc()
            ready_to_call = handler(event, ctx.plugin_manager.context, *args, **kwargs)

        if isinstance(ready_to_call, AsyncGenerator):
            _has_yielded = False
            try:
                async for ret in ready_to_call:
                    # 如果处理函数是生成器，返回值只能是 MessageEventResult 或者 None（无返回值）
                    _has_yielded = True
                    if isinstance(ret, (MessageEventResult, CommandResult)):
                        event.set_result(ret)
                        yield
                    else:
                        yield ret
                if not _has_yielded:
                    yield
            except Exception as e:
                logger.error(f"Previous Error: {trace_}")
                raise e
        elif inspect.iscoroutine(ready_to_call):
            # 如果只是一个 coroutine
            ret = await ready_to_call
            if isinstance(ret, (MessageEventResult, CommandResult)):
                event.set_result(ret)
                yield
            else:
                yield ret
