import traceback
import asyncio
from typing import Union, AsyncGenerator
from ..stage import Stage, register_stage
from ..context import PipelineContext
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core import logger
from astrbot.core.message.components import Plain, Record

@register_stage
class PreProcessStage(Stage):
    
    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        self.config = ctx.astrbot_config
        self.plugin_manager = ctx.plugin_manager
        
        self.stt_settings: dict = self.config.get('provider_stt_settings', {})
        

    async def process(self, event: AstrMessageEvent) -> Union[None, AsyncGenerator[None, None]]:
        '''在处理事件之前的预处理'''

        if self.stt_settings.get('enable', False):
            # STT 处理
            # TODO: 独立
            stt_provider = self.plugin_manager.context.provider_manager.curr_stt_provider_inst
            if stt_provider:
                message_chain = event.get_messages()
                for idx, component in enumerate(message_chain):
                    if isinstance(component, Record) and component.path:
                        
                        path = component.path
                        
                        retry = 5
                        
                        for i in range(retry):
                            try:
                                result = await stt_provider.get_text(audio_url=path)
                                if result:
                                    logger.info("语音转文本结果: " + result)
                                    message_chain[idx] = Plain(result)
                                    event.message_str += result
                                    event.message_obj.message_str += result
                                break
                            except FileNotFoundError:
                                # napcat workaround
                                logger.warning(f"语音文件不存在: {path}, 重试中: {i + 1}/{retry}")
                                await asyncio.sleep(0.5)
                                continue
                            except BaseException as e:
                                logger.error(traceback.format_exc())
                                logger.error(f"语音转文本失败: {e}")
                                break
