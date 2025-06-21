from __future__ import annotations
import abc
import inspect
import traceback
from astrbot.api import logger
from typing import List, AsyncGenerator, Union, Awaitable
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from .context import PipelineContext
from astrbot.core.message.message_event_result import MessageEventResult, CommandResult

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

    async def _call_handler(
        self,
        ctx: PipelineContext,
        event: AstrMessageEvent,
        handler: Awaitable,
        *args,
        **kwargs,
    ) -> AsyncGenerator[None, None]:
        """执行事件处理函数并处理其返回结果

        该方法负责调用处理函数并处理不同类型的返回值。它支持两种类型的处理函数:
        1. 异步生成器: 实现洋葱模型，每次yield都会将控制权交回上层
        2. 协程: 执行一次并处理返回值

        Args:
            ctx (PipelineContext): 消息管道上下文对象
            event (AstrMessageEvent): 待处理的事件对象
            handler (Awaitable): 事件处理函数
            *args: 传递给handler的位置参数
            **kwargs: 传递给handler的关键字参数

        Returns:
            AsyncGenerator[None, None]: 异步生成器，用于在管道中传递控制流
        """
        ready_to_call = None  # 一个协程或者异步生成器(async def)

        trace_ = None

        try:
            ready_to_call = handler(event, *args, **kwargs)
        except TypeError as _:
            # 向下兼容
            trace_ = traceback.format_exc()
            # 以前的handler会额外传入一个参数, 但是context对象实际上在插件实例中有一份
            ready_to_call = handler(event, ctx.plugin_manager.context, *args, **kwargs)

        if isinstance(ready_to_call, AsyncGenerator):
            # 如果是一个异步生成器, 进入洋葱模型
            _has_yielded = False  # 是否返回过值
            try:
                async for ret in ready_to_call:
                    # 这里逐步执行异步生成器, 对于每个yield返回的ret, 执行下面的代码
                    # 返回值只能是 MessageEventResult 或者 None（无返回值）
                    _has_yielded = True
                    if isinstance(ret, (MessageEventResult, CommandResult)):
                        # 如果返回值是 MessageEventResult, 设置结果并继续
                        event.set_result(ret)
                        yield  # 传递控制权给上一层的process函数
                    else:
                        # 如果返回值是 None, 则不设置结果并继续
                        # 继续执行后续阶段
                        yield ret  # 传递控制权给上一层的process函数
                if not _has_yielded:
                    # 如果这个异步生成器没有执行到yield分支
                    yield
            except Exception as e:
                logger.error(f"Previous Error: {trace_}")
                raise e
        elif inspect.iscoroutine(ready_to_call):
            # 如果只是一个协程, 直接执行
            ret = await ready_to_call
            if isinstance(ret, (MessageEventResult, CommandResult)):
                event.set_result(ret)
                yield  # 传递控制权给上一层的process函数
            else:
                yield ret  # 传递控制权给上一层的process函数
