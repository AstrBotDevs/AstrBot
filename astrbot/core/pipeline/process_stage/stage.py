import asyncio
from collections.abc import AsyncGenerator
from contextlib import aclosing

from astrbot.core.chatui import ViewResult, resolve_view, view_store
from astrbot.core.message.components import Json, UIInteraction
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.pipeline.context import PipelineContext
from astrbot.core.pipeline.stage import Stage, register_stage
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.star.star_handler import StarHandlerMetadata
from astrbot.core.utils.session_waiter import FILTERS, USER_SESSIONS, SessionWaiter

from .method.agent_request import AgentRequestSubStage
from .method.star_request import StarRequestSubStage


@register_stage
class ProcessStage(Stage):
    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        self.plugin_manager = ctx.plugin_manager
        self.sdk_plugin_bridge = getattr(
            ctx.plugin_manager.context,
            "sdk_plugin_bridge",
            None,
        )

        # initialize agent sub stage
        self.agent_sub_stage = AgentRequestSubStage()
        await self.agent_sub_stage.initialize(ctx)

        # initialize star request sub stage
        self.star_request_sub_stage = StarRequestSubStage()
        await self.star_request_sub_stage.initialize(ctx)

    async def process(
        self,
        event: AstrMessageEvent,
    ) -> AsyncGenerator[None, None]:
        """处理事件"""
        # Dispatch after access/safety checks and preprocessing, before plugins.
        for session_filter in (
            ()
            if isinstance(event.get_ui_interaction(), UIInteraction)
            else tuple(FILTERS)
        ):
            session_id = session_filter.filter(event)
            session = USER_SESSIONS.get(session_id)
            if session and not session.session_controller.future.done():
                await SessionWaiter.trigger(session_id, event)
                event.stop_event()
                return

        activated_handlers: list[StarHandlerMetadata] = event.get_extra(
            "activated_handlers",
        )
        interaction = event.get_ui_interaction()
        if isinstance(interaction, UIInteraction):
            update = None
            request = None
            deadline = asyncio.get_running_loop().time() + 120
            try:
                resolve_view(
                    event.get_extra("ui_plugin_module"),
                    interaction.view.name,
                    interaction.view.version,
                )
                if not activated_handlers:
                    raise ValueError("No UI action handler was activated.")
                async with aclosing(
                    self.star_request_sub_stage.process(event)
                ) as results:
                    while True:
                        try:
                            result = await asyncio.wait_for(
                                anext(results),
                                timeout=max(
                                    0, deadline - asyncio.get_running_loop().time()
                                ),
                            )
                        except StopAsyncIteration:
                            break
                        if isinstance(result, ViewResult):
                            if update is not None:
                                raise ValueError(
                                    "Only one view update is permitted per action."
                                )
                            update = result.data
                        elif isinstance(result, ProviderRequest):
                            if request is not None or result.conversation is not None:
                                raise ValueError(
                                    "Only one request in the current conversation is permitted."
                                )
                            request = result
                        else:
                            yield
                error = event.get_extra("ui_action_error")
            except Exception:
                error = {
                    "code": "ACTION_FAILED",
                    "message": "The plugin action failed or timed out.",
                }
            receipt = await asyncio.to_thread(
                view_store.finish,
                interaction.view.id,
                interaction.interaction_id,
                update,
                error,
            )
            await event.send(
                MessageChain(chain=[Json(receipt)], type="ui_action_result")
            )
            event.set_extra("ui_action_acknowledged", True)
            if request is not None and not error:
                await asyncio.to_thread(view_store.get, interaction.view.id)
                event.set_extra("provider_request", request)
                async with aclosing(self.agent_sub_stage.process(event)) as responses:
                    async for _ in responses:
                        yield
            return
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
                        yield None
                else:
                    yield None

        if self.sdk_plugin_bridge is not None and not event.is_stopped():
            sdk_result = await self.sdk_plugin_bridge.dispatch_message(event)
            if sdk_result.sent_message or sdk_result.stopped:
                yield None

        # 调用 LLM 相关请求
        if not self.ctx.astrbot_config["provider_settings"].get("enable", True):
            return

        should_call_llm = (
            self.sdk_plugin_bridge.get_effective_should_call_llm(event)
            if self.sdk_plugin_bridge is not None
            and hasattr(self.sdk_plugin_bridge, "get_effective_should_call_llm")
            else not event.call_llm
        )
        effective_result = (
            self.sdk_plugin_bridge.get_effective_result(event)
            if self.sdk_plugin_bridge is not None
            and hasattr(self.sdk_plugin_bridge, "get_effective_result")
            else event.get_result()
        )
        if not event._has_send_oper and event.is_at_or_wake_command and should_call_llm:
            # 是否有过发送操作 and 是否是被 @ 或者通过唤醒前缀
            if (effective_result and not event.is_stopped()) or not effective_result:
                async with aclosing(self.agent_sub_stage.process(event)) as responses:
                    async for _ in responses:
                        yield None
