from ...context import PipelineContext
from ..stage import Stage
from typing import Dict, Any, List, AsyncGenerator, Union
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.message.message_event_result import MessageEventResult, CommandResult, EventResultType
from astrbot.core import logger
from astrbot.core.star.star_handler import StarHandlerMetadata
from astrbot.core.star.star import star_map
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
                
                # 判断 handler 是否是类方法（通过装饰器注册的没有 __self__ 属性）
                if hasattr(handler.handler, '__self__'):
                    # 猜测没有通过装饰器去注册
                    try:
                        ret = await handler.handler(event, **params)
                    except TypeError:
                        # 向下兼容
                        ret = await handler.handler(event, self.ctx.plugin_manager.context, **params)
                else:
                    ret = await handler.handler(star_cls_obj, event, **params)
                if ret:
                    assert isinstance(ret, (MessageEventResult, CommandResult)), "如果有返回值，事件监听器的返回值必须是 MessageEventResult 或 CommandResult 类型。"
                    event.stop_event()
                    event.set_result(ret)
                # 执行后续步骤来发送消息
                yield
                event.clear_result() # 清除上一个 handler 的结果
            except Exception as e:
                logger.error(f"Star {handler.handler_full_name} handle error: {e}")