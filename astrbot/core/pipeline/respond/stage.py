import asyncio
from datetime import datetime, timedelta
from collections import defaultdict, deque
from typing import DefaultDict, Deque, List, Union, AsyncGenerator
from ..stage import Stage, register_stage
from ..context import PipelineContext
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core import logger
from astrbot.core.config.astrbot_config import RateLimitStrategy

@register_stage
class RespondStage:
    async def initialize(self, ctx: PipelineContext):
        self.ctx = ctx

    async def process(self, event: AstrMessageEvent) -> Union[None, AsyncGenerator[None, None]]:
        result = event.get_result()
        if result is None:
            return
        
        if len(result.chain) > 0:
            await event.send(result)
            logger.info(f"AstrBot -> {event.get_sender_name()}/{event.get_sender_id()}: {event._outline_chain(result.chain)}")
        