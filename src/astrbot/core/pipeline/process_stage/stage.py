from typing import List, Union, AsyncGenerator
from ..stage import Stage, register_stage
from ..context import PipelineContext
from .method.llm_request import LLMRequestSubStage
from .method.star_request import StarRequestSubStage
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.star_handler import StarHandlerMetadata
from astrbot.core.provider.entities import ProviderRequest
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

    async def process(
        self, event: AstrMessageEvent
    ) -> Union[None, AsyncGenerator[None, None]]:
        """处理事件"""
        activated_handlers: List[StarHandlerMetadata] = event.get_extra(
            "activated_handlers"
        )
        # 有插件 Handler 被激活
        if activated_handlers:
            async for resp in self.star_request_sub_stage.process(event):
                # 生成器返回值处理
                if isinstance(resp, ProviderRequest):
                    # Handler 的 LLM 请求
                    event.set_extra("provider_request", resp)
                    _t = False
                    async for _ in self.llm_request_sub_stage.process(event):
                        _t = True
                        yield
                    if not _t:
                        yield
                else:
                    yield

        # 调用 LLM 相关请求
        if not self.ctx.astrbot_config["provider_settings"].get("enable", True):
            return

        if (
            not event._has_send_oper
            and event.is_at_or_wake_command
            and not event.call_llm
        ):
            # 是否有过发送操作 and 是否是被 @ 或者通过唤醒前缀
            if (
                event.get_result() and not event.get_result().is_stopped()
            ) or not event.get_result():
                # 事件没有终止传播
                provider = self.ctx.plugin_manager.context.get_using_provider()

                if not provider:
                    logger.info("未找到可用的 LLM 提供商，请先前往配置服务提供商。")
                    return

                async for _ in self.llm_request_sub_stage.process(event):
                    yield
