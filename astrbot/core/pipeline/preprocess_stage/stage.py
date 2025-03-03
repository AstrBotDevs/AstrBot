import traceback
import asyncio
from typing import Union, AsyncGenerator
from ..stage import Stage, register_stage
from ..context import PipelineContext
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core import logger
from astrbot.core.message.components import Plain, Record, Image


@register_stage
class PreProcessStage(Stage):
    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        self.config = ctx.astrbot_config
        self.plugin_manager = ctx.plugin_manager

        self.stt_settings: dict = self.config.get("provider_stt_settings", {})
        self.platform_settings: dict = self.config.get("platform_settings", {})

    async def process(
        self, event: AstrMessageEvent
    ) -> Union[None, AsyncGenerator[None, None]]:
        """在处理事件之前的预处理"""
        # 路径映射
        if mappings := self.platform_settings.get("path_mapping", []):
            # 支持 Record，Image 消息段的路径映射。
            message_chain = event.get_messages()

            for idx, component in enumerate(message_chain):
                if isinstance(component, (Record, Image)) and component.url:
                    for mapping in mappings:
                        from_, to_ = mapping.split(":")
                        from_ = from_.removesuffix("/")
                        to_ = to_.removesuffix("/")

                        url = component.url.removeprefix("file://")
                        if url.startswith(from_):
                            component.url = url.replace(from_, to_, 1)
                            logger.debug(f"路径映射: {url} -> {component.url}")
                    message_chain[idx] = component

        # STT
        if self.stt_settings.get("enable", False):
            # TODO: 独立
            stt_provider = (
                self.plugin_manager.context.provider_manager.curr_stt_provider_inst
            )
            if stt_provider:
                message_chain = event.get_messages()
                for idx, component in enumerate(message_chain):
                    if isinstance(component, Record) and component.url:
                        path = component.url.removeprefix("file://")
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
                            except FileNotFoundError as e:
                                # napcat workaround
                                logger.warning(e)
                                logger.warning(f"重试中: {i + 1}/{retry}")
                                await asyncio.sleep(0.5)
                                continue
                            except BaseException as e:
                                logger.error(traceback.format_exc())
                                logger.error(f"语音转文本失败: {e}")
                                break
