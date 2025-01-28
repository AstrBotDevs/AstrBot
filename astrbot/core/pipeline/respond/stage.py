import random
import asyncio
from typing import Union, AsyncGenerator
from ..stage import register_stage, Stage
from ..context import PipelineContext
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core import logger
from astrbot.core.star.star_handler import star_handlers_registry, EventType

@register_stage
class RespondStage(Stage):
    async def initialize(self, ctx: PipelineContext):
        self.ctx = ctx
        
        # 分段回复
        self.enable_seg: bool = ctx.astrbot_config['platform_settings']['segmented_reply']['enable']
        self.only_llm_result = ctx.astrbot_config['platform_settings']['segmented_reply']['only_llm_result']
        interval_str: str = ctx.astrbot_config['platform_settings']['segmented_reply']['interval']
        interval_str_ls = interval_str.replace(" ", "").split(",")
        try:
            self.interval = [float(t) for t in interval_str_ls]
        except BaseException as e:
            logger.error(f'解析分段回复的间隔时间失败。{e}')
            self.interval = [1.5, 3.5]
        logger.info(f"分段回复间隔时间：{self.interval}")


    async def process(self, event: AstrMessageEvent) -> Union[None, AsyncGenerator[None, None]]:
        result = event.get_result()
        if result is None:
            return

        if len(result.chain) > 0:
            await event._pre_send()
            
            if self.enable_seg and ((self.only_llm_result and result.is_llm_result()) or not self.only_llm_result):
                # 分段回复
                for comp in result.chain:
                    await event.send(MessageChain([comp]))
                    await asyncio.sleep(random.uniform(self.interval[0], self.interval[1]))
            else:
                await event.send(result)
            await event._post_send()
            logger.info(f"AstrBot -> {event.get_sender_name()}/{event.get_sender_id()}: {event._outline_chain(result.chain)}")
        
        handlers = star_handlers_registry.get_handlers_by_event_type(EventType.OnAfterMessageSentEvent)
        for handler in handlers:
            # TODO: 如何让这里的 handler 也能使用 LLM 能力。也许需要将 LLMRequestSubStage 提取出来。
            await handler.handler(event)
            
        event.clear_result()