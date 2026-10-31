from collections.abc import AsyncGenerator
from contextlib import aclosing

from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.star.star_handler import StarHandlerMetadata
from astrbot.core.utils.session_waiter import FILTERS, USER_SESSIONS, SessionWaiter

from ..context import PipelineContext
from ..stage import Stage, register_stage
from .method.agent_request import AgentRequestSubStage
from .method.star_request import StarRequestSubStage


@register_stage
class ProcessStage(Stage):
    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        self.config = ctx.astrbot_config
        self.plugin_manager = ctx.plugin_manager

        # initialize agent sub stage
        self.agent_sub_stage = AgentRequestSubStage()
        await self.agent_sub_stage.initialize(ctx)

        # initialize star request sub stage
        self.star_request_sub_stage = StarRequestSubStage()
        await self.star_request_sub_stage.initialize(ctx)

    async def process(
        self,
        event: AstrMessageEvent,
    ) -> None | AsyncGenerator[None, None]:
        """处理事件"""
        # Dispatch after access/safety checks and preprocessing, before plugins.
        for session_filter in tuple(FILTERS):
            session_id = session_filter.filter(event)
            session = USER_SESSIONS.get(session_id)
            if session and not session.session_controller.future.done():
                await SessionWaiter.trigger(session_id, event)
                event.stop_event()
                return

        activated_handlers: list[StarHandlerMetadata] = event.get_extra(
            "activated_handlers",
        )
        # 有插件 Handler 被激活
        if activated_handlers:
            async for resp in self.star_request_sub_stage.process(event):
                # 生成器返回值处理
                if isinstance(resp, ProviderRequest):
                    # Handler 的 LLM 请求
                    event.set_extra("provider_request", resp)
                    _t = False
                    async with aclosing(
                        self.agent_sub_stage.process(event)
                    ) as responses:
                        async for _ in responses:
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
                event.get_result() and not event.is_stopped()
            ) or not event.get_result():
                async with aclosing(self.agent_sub_stage.process(event)) as responses:
                    async for _ in responses:
                        yield
