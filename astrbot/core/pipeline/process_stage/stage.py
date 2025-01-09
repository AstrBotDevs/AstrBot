from typing import List, Union, AsyncGenerator
from ..stage import Stage, register_stage
from ..context import PipelineContext
from .method.llm_request import LLMRequestSubStage
from .method.star_request import StarRequestSubStage
from .method.dify_request import DifyRequestSubStage
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.star_handler import StarHandlerMetadata
from astrbot.core.provider.entites import ProviderRequest
from astrbot.core import logger

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
        
        self.dify_request_sub_stage = DifyRequestSubStage()
        await self.dify_request_sub_stage.initialize(ctx)

    async def process(self, event: AstrMessageEvent) -> Union[None, AsyncGenerator[None, None]]:
        '''处理事件
        '''
        activated_handlers: List[StarHandlerMetadata] = event.get_extra("activated_handlers")
        # 有插件 Handler 被激活
        if activated_handlers:
            async for resp in self.star_request_sub_stage.process(event):
                # 生成器返回值处理
                if isinstance(resp, ProviderRequest):
                    # Handler 的 LLM 请求
                    logger.debug(f"llm request -> {resp.prompt}")
                    event.set_extra("provider_request", resp)
                    async for _ in self.llm_request_sub_stage.process(event):
                        yield
                else:
                    yield
        
        # 调用提供商相关请求
        if not self.ctx.astrbot_config['provider_settings'].get('enable', True):
            return
        
        if not event._has_send_oper and event.is_at_or_wake_command:
            if (event.get_result() and not event.get_result().is_stopped()) or not event.get_result():
                provider = self.ctx.plugin_manager.context.get_using_provider()
                match provider.meta().type:
                    case "dify":
                        async for _ in self.dify_request_sub_stage.process(event):
                            yield
                    case _:
                        async for _ in self.llm_request_sub_stage.process(event):
                            yield