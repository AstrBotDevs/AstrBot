'''
Dify 调用 Stage
'''
import traceback
from typing import Union, AsyncGenerator
from ...context import PipelineContext
from ..stage import Stage
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.message.message_event_result import MessageEventResult, ResultContentType
from astrbot.core.message.components import Image
from astrbot.core import logger
from astrbot.core.utils.metrics import Metric
from astrbot.core.provider.entites import ProviderRequest
from astrbot.core.star.star_handler import star_handlers_registry, EventType

class DifyRequestSubStage(Stage):
    
    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        
    async def process(self, event: AstrMessageEvent) -> Union[None, AsyncGenerator[None, None]]:
        req: ProviderRequest = None
        
        provider = self.ctx.plugin_manager.context.get_using_provider()
        
        if not provider:
            return
        
        if provider.meta().type != "dify":
            return
        
        if event.get_extra("provider_request"):
            req = event.get_extra("provider_request")
            assert isinstance(req, ProviderRequest), "provider_request 必须是 ProviderRequest 类型。"
        else:
            req = ProviderRequest(prompt="", image_urls=[])
            if self.ctx.astrbot_config['provider_settings']['wake_prefix']:
                if not event.message_str.startswith(self.ctx.astrbot_config['provider_settings']['wake_prefix']):
                    return
            req.prompt = event.message_str[len(self.ctx.astrbot_config['provider_settings']['wake_prefix']):]
            for comp in event.message_obj.message:
                if isinstance(comp, Image):
                    image_url = comp.url if comp.url else comp.file
                    req.image_urls.append(image_url)
            req.session_id = event.session_id
            event.set_extra("provider_request", req)
            
        if not req.prompt:
            return
        
        req.session_id = event.unified_msg_origin
        
        # 执行请求 LLM 前事件钩子。
        # 装饰 system_prompt 等功能
        handlers = star_handlers_registry.get_handlers_by_event_type(EventType.OnLLMRequestEvent)
        for handler in handlers:
            try:
                await handler.handler(event, req)
            except BaseException:
                logger.error(traceback.format_exc())
            
        try:
            logger.debug(f"Dify 请求 Payload: {req.__dict__}")
            llm_response = await provider.text_chat(**req.__dict__) # 请求 LLM
            await Metric.upload(llm_tick=1, model_name=provider.get_model(), provider_type=provider.meta().type)
            
            # 执行 LLM 响应后的事件。
            handlers = star_handlers_registry.get_handlers_by_event_type(EventType.OnLLMResponseEvent)
            for handler in handlers:
                try:
                    await handler.handler(event, llm_response)
                except BaseException:
                    logger.error(traceback.format_exc())

            if llm_response.role == 'assistant':
                # text completion
                event.set_result(MessageEventResult().message(llm_response.completion_text)
                                 .set_result_content_type(ResultContentType.LLM_RESULT))
                return
            elif llm_response.role == 'err':
                event.set_result(MessageEventResult().message(f"AstrBot 请求失败。\n错误信息: {llm_response.completion_text}"))
                return
            elif llm_response.role == 'tool':
                event.set_result(MessageEventResult().message(f"Dify 暂不支持工具调用。"))
                yield

        except BaseException as e:
            logger.error(traceback.format_exc())
            event.set_result(MessageEventResult().message("AstrBot 请求 Dify 失败：" + str(e)))
            return