from typing import Union, AsyncGenerator
from ..stage import register_stage, Stage
from ..context import PipelineContext
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core import logger
from astrbot.core.star.star_handler import star_handlers_registry, EventType

@register_stage
class RespondStage(Stage):
    async def initialize(self, ctx: PipelineContext):
        self.ctx = ctx

    async def process(self, event: AstrMessageEvent) -> Union[None, AsyncGenerator[None, None]]:
        result = event.get_result()
        if result is None:
            return

        if len(result.chain) > 0:
            await event.send(result)
            logger.info(f"AstrBot -> {event.get_sender_name()}/{event.get_sender_id()}: {event._outline_chain(result.chain)}")
        
        handlers = star_handlers_registry.get_handlers_by_event_type(EventType.OnAfterMessageSentEvent)
        for handler in handlers:
            # TODO: 如何让这里的 handler 也能使用 LLM 能力。也许需要将 LLMRequestSubStage 提取出来。
            await handler.handler(event)
            
        event.clear_result()