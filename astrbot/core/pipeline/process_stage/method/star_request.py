from ...context import PipelineContext
from ..stage import Stage
from typing import Dict, Any, List, AsyncGenerator, Union
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.message.message_event_result import MessageEventResult, CommandResult
from astrbot.core import logger
from astrbot.core.star.star_handler import StarHandlerMetadata
from astrbot.core.star.star import star_map
import traceback
import inspect
class StarRequestSubStage(Stage):
    
    async def initialize(self, ctx: PipelineContext) -> None:
        self.curr_provider = ctx.plugin_manager.context.get_using_provider()
        self.prompt_prefix = ctx.astrbot_config['provider_settings']['prompt_prefix']
        self.identifier = ctx.astrbot_config['provider_settings']['identifier']
        self.ctx = ctx
        
    async def process(self, event: AstrMessageEvent) -> Union[None, AsyncGenerator[None, None]]:
        activated_handlers: List[StarHandlerMetadata] = event.get_extra("activated_handlers")
        handlers_parsed_params: Dict[str, Dict[str, Any]] = event.get_extra("handlers_parsed_params")
        if not handlers_parsed_params:
            handlers_parsed_params = {}
        for handler in activated_handlers:
            params = handlers_parsed_params.get(handler.handler_full_name, {})
            try:
                if handler.handler_module_str not in star_map:
                    # 孤立无援的 star handler 
                    continue
                star_cls_obj = star_map.get(handler.handler_module_str).star_cls
                
                logger.debug(f"执行 Star Handler {handler.handler_full_name}")
                # 判断 handler 是否是类方法（通过装饰器注册的没有 __self__ 属性）
                ready_to_call = None
                if hasattr(handler.handler, '__self__'):
                    # 猜测没有通过装饰器去注册
                    try:
                        ready_to_call = handler.handler(event, **params)
                    except TypeError:
                        # 向下兼容
                        ready_to_call = handler.handler(event, self.ctx.plugin_manager.context, **params)
                else:
                    ready_to_call = handler.handler(star_cls_obj, event, **params)
                
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
                    elif not event.is_stopped and not event.get_result():
                        continue
                    else:
                        yield
                event.clear_result() # 清除上一个 handler 的结果
            except Exception as e:
                logger.error(traceback.format_exc())
                logger.error(f"Star {handler.handler_full_name} handle error: {e}")
                ret = f":(\n\n在调用插件 {star_map.get(handler.handler_module_str).name} 的处理函数 {handler.handler_name} 时出现异常：{e}"
                event.set_result(MessageEventResult().message(ret))
                yield
                event.clear_result()
                event.stop_event()