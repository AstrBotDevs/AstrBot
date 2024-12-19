import time
from typing import Union, AsyncGenerator
from ..stage import register_stage
from ..context import PipelineContext
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core import logger
from astrbot.core.message.components import Plain, Image
from astrbot.core import html_renderer
from astrbot.core.star.star_handler import star_handlers_registry, EventType

@register_stage
class ResultDecorateStage:
    async def initialize(self, ctx: PipelineContext):
        self.ctx = ctx
        self.reply_prefix = ctx.astrbot_config['platform_settings']['reply_prefix']
        self.t2i = ctx.astrbot_config['t2i']

    async def process(self, event: AstrMessageEvent) -> Union[None, AsyncGenerator[None, None]]:
        result = event.get_result()
        if result is None:
            return
        
        handlers = star_handlers_registry.get_handlers_by_event_type(EventType.OnDecoratingResultEvent)
        for handler in handlers:
            # TODO: 如何让这里的 handler 也能使用 LLM 能力。也许需要将 LLMRequestSubStage 提取出来。
            await handler.handler(event)
        
        if len(result.chain) > 0:
            # 回复前缀
            if self.reply_prefix:
                result.chain.insert(0, Plain(self.reply_prefix))
            
            # 文本转图片
            if (result.use_t2i_ is None and self.t2i) or result.use_t2i_:
                plain_str = ""
                for comp in result.chain:
                    if isinstance(comp, Plain):
                        plain_str += "\n\n" + comp.text
                    else:
                        break
                if plain_str and len(plain_str) > 150:
                    render_start = time.time()
                    try:
                        url = await html_renderer.render_t2i(plain_str, return_url=True)
                    except BaseException:
                        logger.error("文本转图片失败，使用文本发送。")
                        return
                    if time.time() - render_start > 3:
                        logger.warning("文本转图片耗时超过了 3 秒，如果觉得很慢可以使用 /t2i 关闭文本转图片模式。")
                    if url:
                        result.chain = [Image.fromURL(url)]