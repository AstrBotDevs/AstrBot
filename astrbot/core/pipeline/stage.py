from __future__ import annotations
import abc
import inspect
from typing import List, AsyncGenerator, Union, Awaitable
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from .context import PipelineContext
from astrbot.core.message.message_event_result import MessageEventResult, CommandResult

registered_stages: List[Stage] = []
'''维护了所有已注册的 Stage 实现类'''

def register_stage(cls):
    '''一个简单的装饰器，用于注册 pipeline 包下的 Stage 实现类
    '''
    registered_stages.append(cls())
    return cls
    
class Stage(abc.ABC):
    '''描述一个 Pipeline 的某个阶段
    '''
    
    @abc.abstractmethod
    async def initialize(self, ctx: PipelineContext) -> None:
        '''初始化阶段
        '''
        raise NotImplementedError
    
    @abc.abstractmethod
    async def process(self, event: AstrMessageEvent) -> Union[None, AsyncGenerator[None, None]]:
        '''处理事件
        '''
        raise NotImplementedError
    
    async def _call_handler(
        self, 
        ctx: PipelineContext,
        event: AstrMessageEvent, 
        handler: Awaitable,
        **params
    ) -> AsyncGenerator[None, None]:
        '''调用 Handler。'''
        # 判断 handler 是否是类方法（通过装饰器注册的没有 __self__ 属性）
        ready_to_call = None
        try:
            ready_to_call = handler(event, **params)
        except TypeError as e:
            print(e)
            # 向下兼容
            ready_to_call = handler(event, ctx.plugin_manager.context, **params)
        
        if isinstance(ready_to_call, AsyncGenerator):
            async for mer in ready_to_call:
                # 如果处理函数是生成器，返回值只能是 MessageEventResult 或者 None（无返回值）
                if mer:
                    assert isinstance(mer, (MessageEventResult, CommandResult)), "如果有返回值，必须是 MessageEventResult 或 CommandResult 类型。"
                    event.set_result(mer)
                    yield
                else:
                    if event.get_result():
                        yield
        elif inspect.iscoroutine(ready_to_call):
            # 如果只是一个 coroutine
            ret = await ready_to_call
            if ret:
                # 如果有返回值
                assert isinstance(ret, (MessageEventResult, CommandResult)), "如果有返回值，必须是 MessageEventResult 或 CommandResult 类型。"
                event.set_result(ret)
            # 执行后续步骤来发送消息
            if event.is_stopped() and event.get_result():
                # 插件主动停止事件传播，并且有结果
                event.continue_event()
                yield
                event.clear_result()
                event.stop_event()
                yield
            else:
                yield