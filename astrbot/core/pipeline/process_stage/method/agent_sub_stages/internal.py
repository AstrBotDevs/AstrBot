"""Route built-in AI input to its runtime and present the resulting turn."""

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import replace

from astrbot import logger
from astrbot.core.agent.input import PlainInput
from astrbot.core.agent.runtime import AgentInput, AgentPermissions, TurnStatus
from astrbot.core.agent_input import (
    collect_plugin_capabilities,
    matches_provider_wake_prefix,
)
from astrbot.core.agent_output import present_turn
from astrbot.core.astr_agent_runtime import AstrAgentRuntime
from astrbot.core.astr_agent_runtime.main_agent import MainAgentBuildConfig
from astrbot.core.astr_agent_runtime.main_session import MainAgentInput
from astrbot.core.llm_error_messages import LLM_ERROR_MESSAGE_EXTRA_KEY
from astrbot.core.message.components import File, Image, Record, Reply, Video
from astrbot.core.message.message_event_result import (
    MessageChain,
    MessageEventResult,
    ResultContentType,
)
from astrbot.core.persona_error_reply import (
    extract_persona_custom_error_message_from_event,
)
from astrbot.core.pipeline.stage import Stage
from astrbot.core.platform.agent_wakeup_event import AgentWakeupEvent
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.speech_output import stream_speech
from astrbot.core.star.session_llm_manager import SessionServiceManager
from astrbot.core.star.star_handler import EventType
from astrbot.core.utils.active_event_registry import active_event_registry

from ....context import PipelineContext, call_event_hook
from ...follow_up import (
    finalize_follow_up_capture,
    prepare_follow_up_capture,
    try_capture_follow_up,
)


async def _prepare_file_attachments(event: AstrMessageEvent) -> None:
    """Download file attachments before acquiring the session lock.

    Args:
        event: Incoming event whose direct and quoted files should be prepared.

    Returns:
        None.
    """
    for component in event.message_obj.message:
        if isinstance(component, File):
            await component.get_file()
        elif isinstance(component, Reply) and component.chain:
            for reply_component in component.chain:
                if isinstance(reply_component, File):
                    await reply_component.get_file()


class InternalAgentSubStage(Stage):
    async def initialize(self, ctx: PipelineContext) -> None:
        """Bind Core's input/output preferences and the application's runtime.

        Args:
            ctx: Pipeline services and this configuration profile.
        """
        self.ctx = ctx
        settings = ctx.astrbot_config["provider_settings"]
        self.streaming_response = settings["streaming_response"]
        self.unsupported_streaming_strategy = settings["unsupported_streaming_strategy"]
        self.show_tool_use = settings.get("show_tool_use_status", True)
        self.show_tool_call_result = settings.get("show_tool_call_result", False)
        self.buffer_intermediate_messages = settings.get(
            "buffer_intermediate_messages", False
        )
        self.show_reasoning = settings.get("display_reasoning_text", False)
        self.main_agent_cfg = MainAgentBuildConfig.from_config(ctx.astrbot_config)
        context = ctx.plugin_manager.context
        runtime = getattr(context, "agent_runtime", None)
        if not isinstance(runtime, AstrAgentRuntime):
            runtime = AstrAgentRuntime(context)
            context.agent_runtime = runtime
        self.runtime = runtime

    async def process(
        self, event: AstrMessageEvent, provider_wake_prefix: str
    ) -> AsyncGenerator[None, None]:
        """Admit a platform input and consume a runtime-owned execution.

        Args:
            event: Current message or ordinary pipeline wakeup.
            provider_wake_prefix: Core's additional AI trigger prefix.

        Yields:
            Pipeline progress after setting a result for platform delivery.
        """
        capture = None
        consumed = activated = typing = False
        turn = None
        is_wakeup = isinstance(event, AgentWakeupEvent)
        target = event.agent_session if isinstance(event, AgentWakeupEvent) else None
        try:
            runtime = self.runtime
            if target is not None:
                service = self.ctx.plugin_manager.context.subagents
                if service is None or target.runtime not in service.runtimes:
                    raise ValueError(
                        f"Target agent runtime unavailable: {target.runtime}"
                    )
                runtime = service.runtimes[target.runtime]
            if (
                is_wakeup
                and active_event_registry.get_background_stop_signal(event).is_set()
            ):
                raise asyncio.CancelledError()
            has_input = bool(event.message_str and event.message_str.strip()) or any(
                isinstance(component, (Image, File, Record, Video, Reply))
                for component in event.message_obj.message
            )
            if not has_input and event.get_extra("provider_request") is None:
                return
            # Explicit session wakeups are queued turns; their sender already tried steering.
            active = (
                self.runtime.active_turn(event.unified_msg_origin)
                if target is None
                else None
            )
            if active is not None:
                selected = await self.runtime.open_session(
                    event.unified_msg_origin,
                    input=AgentInput(event, AgentPermissions.from_event(event)),
                )
                active = selected.active_turn
            capture = try_capture_follow_up(event, active)
            if capture is not None:
                consumed, activated = await prepare_follow_up_capture(capture)
                if consumed:
                    event.set_extra(
                        "_follow_up_captured", {"target_run_id": capture.target_run_id}
                    )
                    return
            if not is_wakeup:
                try:
                    typing = True
                    await event.send_typing()
                except Exception:
                    logger.warning("send_typing failed", exc_info=True)
            if await call_event_hook(event, EventType.OnWaitingLLMRequestEvent):
                return
            if event.get_extra(
                "provider_request"
            ) is None and not matches_provider_wake_prefix(event, provider_wake_prefix):
                return
            await _prepare_file_attachments(event)

            async def admit() -> bool:
                current_config = self.ctx.plugin_manager.context.get_config(
                    umo=event.unified_msg_origin
                )
                return current_config.get("provider_settings", {}).get(
                    "enable", True
                ) and await SessionServiceManager.should_process_llm_request(event)

            if not await admit():
                return
            streaming = self.streaming_response
            if event.get_extra("enable_streaming") is not None:
                streaming = bool(event.get_extra("enable_streaming"))
            show_reasoning = self.show_reasoning
            if event.get_extra("enable_reasoning") is not None:
                show_reasoning = bool(event.get_extra("enable_reasoning"))
            plugin_tools, plugin_skills = collect_plugin_capabilities(
                self.ctx.plugin_manager.context, event
            )
            input = MainAgentInput(
                event=event,
                content=[PlainInput(text=event.message_str)]
                if target is not None
                else None,
                permissions=AgentPermissions.from_event(event),
                plugin_tools=plugin_tools,
                plugin_skills=plugin_skills,
                admit=admit,
                build_config=replace(
                    self.main_agent_cfg,
                    provider_wake_prefix=provider_wake_prefix,
                    streaming_response=streaming,
                    call_request_hook=True,
                    validate_provider_endpoint=True,
                ),
            )
            session = await runtime.open_session(
                event.unified_msg_origin,
                input=input,
                session_id=target.session_id if target is not None else None,
            )
            turn = await session.run_turn(input)
            stream_to_general = (
                self.unsupported_streaming_strategy == "turn_off"
                and not event.platform_meta.support_streaming_message
            )
            chains = present_turn(
                turn,
                streaming=streaming,
                stream_to_general=stream_to_general,
                show_tool_use=self.show_tool_use,
                show_tool_call_result=self.show_tool_call_result,
                show_reasoning=show_reasoning,
                buffer_intermediate_messages=self.buffer_intermediate_messages,
                context=self.ctx.plugin_manager.context,
            )
            live = event.get_extra("action_type") == "live"
            if live:
                provider = (
                    await self.ctx.plugin_manager.context.get_using_tts_provider_async(
                        event.unified_msg_origin
                    )
                )
                chains = stream_speech(chains, provider, event=event)
            if live or streaming and not stream_to_general:
                event.set_result(
                    MessageEventResult()
                    .set_result_content_type(ResultContentType.STREAMING_RESULT)
                    .set_async_stream(chains)
                )
                yield
                result = await turn.result()
                if not live:
                    chain = (
                        MessageChain().message(result.text)
                        if result.text
                        else result.chain or MessageChain()
                    )
                    event.set_result(
                        MessageEventResult(
                            chain=chain.chain,
                            result_content_type=ResultContentType.STREAMING_FINISH,
                        )
                    )
            else:
                async for chain in chains:
                    if chain is None:
                        continue
                    event.set_result(
                        MessageEventResult(
                            chain=chain.chain,
                            result_content_type=ResultContentType.LLM_RESULT,
                        )
                    )
                    yield
                    event.clear_result()
                result = await turn.result()
            if result.status == TurnStatus.CANCELLED and not event.get_extra(
                "agent_user_aborted"
            ):
                raise asyncio.CancelledError(result.error or "")
            if is_wakeup:
                if result.status == TurnStatus.CANCELLED:
                    raise asyncio.CancelledError()
                if result.status == TurnStatus.FAILED:
                    raise RuntimeError(f"Wakeup agent failed: {result.error}")
        except asyncio.CancelledError:
            if turn is not None:
                await turn.cancel()
            raise
        except Exception as exc:
            if is_wakeup:
                raise
            logger.exception("Error occurred while processing agent request")
            error = (
                extract_persona_custom_error_message_from_event(event)
                or event.get_extra(LLM_ERROR_MESSAGE_EXTRA_KEY)
                or f"Error occurred while processing agent request: {exc}"
            )
            await event.send(MessageChain().message(str(error)))
        finally:
            if turn is not None and not turn.done:
                await turn.cancel()
            if typing:
                try:
                    await event.stop_typing()
                except Exception:
                    logger.warning("stop_typing failed", exc_info=True)
            if capture is not None:
                await finalize_follow_up_capture(
                    capture, activated=activated, consumed_marked=consumed
                )
