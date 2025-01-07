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

class DifyRequestSubStage(Stage):
    
    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        
    async def process(self, event: AstrMessageEvent) -> Union[None, AsyncGenerator[None, None]]:
        req: ProviderRequest = None
        
        provider = self.ctx.plugin_manager.context.get_using_provider()
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
        
        try:
            logger.debug(f"Dify 请求 Payload: {req.__dict__}")
            llm_response = await provider.text_chat(**req.__dict__) # 请求 LLM
            await Metric.upload(llm_tick=1, model_name=provider.get_model(), provider_type=provider.meta().type)

            if llm_response.role == 'assistant':
                # text completion
                event.set_result(MessageEventResult().message(llm_response.completion_text)
                                 .set_result_content_type(ResultContentType.LLM_RESULT))
                yield # rick roll

        except BaseException as e:
            logger.error(traceback.format_exc())
            event.set_result(MessageEventResult().message("AstrBot 请求 Dify 失败：" + str(e)))
            return