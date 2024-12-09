from typing import List, Union, AsyncGenerator
from ..stage import Stage, register_stage
from ..context import PipelineContext
from .method.llm_request import LLMRequestSubStage
from .method.star_request import StarRequestSubStage
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.message.message_event_result import MessageEventResult, CommandResult, EventResultType
from astrbot.core import logger
from astrbot.core.star.star_handler import StarHandlerMetadata
from astrbot.core.message.components import *
from astrbot.core import html_renderer

@register_stage
class ProcessStage(Stage):
    
    async def initialize(self, ctx: PipelineContext) -> None:
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
        
        if not activated_handlers:
            async for _ in self.llm_request_sub_stage.process(event):
                yield
        else:
            async for _ in self.star_request_sub_stage.process(event):
                yield
    