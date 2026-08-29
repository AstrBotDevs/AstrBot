from collections.abc import AsyncGenerator

from astrbot.core.agent.llm_types import ProviderRequest
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.star_handler import StarHandlerMetadata

from ..context import PipelineContext
from ..stage import Stage
from .method.agent_request import AgentRequestSubStage
from .method.star_request import StarRequestSubStage


class ProcessStage(Stage):
    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        self.config = ctx.astrbot_config

        # initialize agent sub stage
        self.agent_sub_stage = AgentRequestSubStage()
        await self.agent_sub_stage.initialize(ctx)

        # initialize star request sub stage
        self.star_request_sub_stage = StarRequestSubStage()
        await self.star_request_sub_stage.initialize(ctx)

    async def process(
        self,
        event: AstrMessageEvent,
    ) -> AsyncGenerator[None]:
        """处理事件"""
        activated_handlers: list[StarHandlerMetadata] = event.get_extra(
            "activated_handlers",
        )
        handled_plugin_provider_request = False
        # 有插件 Handler 被激活
        if activated_handlers:
            async for resp in self.star_request_sub_stage.process(event):
                # 生成器返回值处理
                if isinstance(resp, ProviderRequest):
                    # Handler 的 LLM 请求
                    handled_plugin_provider_request = True
                    event.set_extra("provider_request", resp)
                    _t = False
                    async for _ in self.agent_sub_stage.process(event):
                        _t = True
                        yield
                    if not _t:
                        yield
                else:
                    yield
        if handled_plugin_provider_request:
            return

        # 调用 LLM 相关请求
        if not self.ctx.astrbot_config["provider_settings"].get("enable", True):
            return

        if (
            not event._has_send_oper
            and event.get_extra("should_run_llm")
            and not event.call_llm
        ):
            # Skip the default Agent after a handler has already produced output.
            if (
                event.get_result() and not event.is_stopped()
            ) or not event.get_result():
                async for _ in self.agent_sub_stage.process(event):
                    yield
