from typing import List, Union, AsyncGenerator
from ..stage import Stage, register_stage
from ..context import PipelineContext
from .method.llm_request import LLMRequestSubStage
from .method.star_request import StarRequestSubStage
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.star_handler import StarHandlerMetadata

@register_stage
class ProcessStage(Stage):
    
    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        self.config = ctx.astrbot_config
        self.plugin_manager = ctx.plugin_manager
        self.llm_request_sub_stage = LLMRequestSubStage()
        await self.llm_request_sub_stage.initialize(ctx)
        
        self.star_request_sub_stage = StarRequestSubStage()
        await self.star_request_sub_stage.initialize(ctx)

    async def process(self, event: AstrMessageEvent) -> Union[None, AsyncGenerator[None, None]]:
        '''处理事件
        '''
        activated_handlers: List[StarHandlerMetadata] = event.get_extra("activated_handlers")
        
        if activated_handlers:
            async for _ in self.star_request_sub_stage.process(event):
                yield

        if self.ctx.astrbot_config['provider_settings'].get('enable', True):
            if not event._has_send_oper:
                '''当没有发送操作'''
                if (event.get_result() and not event.get_result().is_stopped()) or not event.get_result():
                    async for _ in self.llm_request_sub_stage.process(event):
                        yield