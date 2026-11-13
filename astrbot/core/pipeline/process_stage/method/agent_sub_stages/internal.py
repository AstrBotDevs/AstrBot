"""Route registered AI input to its runtime and present the resulting turn."""

import asyncio
from collections.abc import AsyncGenerator
from copy import deepcopy
from functools import partial

from astrbot import logger
from astrbot.core.agent.input import PlainInput
from astrbot.core.agent.runtime import AgentInput, AgentPermissions, TurnStatus
from astrbot.core.agent_input import (
    admit_agent_input,
    prepare_agent_input,
)
from astrbot.core.agent_output import present_turn
from astrbot.core.agent_output_content import chain_from_content
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
from astrbot.core.utils.active_event_registry import active_event_registry

from ....context import PipelineContext
from ...follow_up import (
    finalize_follow_up_capture,
    prepare_follow_up_capture,
    try_capture_follow_up,
)


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
            agent_config = self.ctx.astrbot_config.get("agent", {})
            runtime_name = (
                target.runtime
                if target is not None
                else agent_config.get("runtime", "astrbot")
            )
            runtime = self.ctx.agent_runtimes.get(runtime_name)
            if runtime is None:
                raise RuntimeError(f"Agent runtime unavailable: {runtime_name}")
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
                runtime.active_turn(event.unified_msg_origin)
                if target is None
                else None
            )
            if active is not None:
                selected = await runtime.open_session(
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
            streaming = self.streaming_response
            if event.get_extra("enable_streaming") is not None:
                streaming = bool(event.get_extra("enable_streaming"))
            input = await prepare_agent_input(
                self.ctx.plugin_manager.context,
                event,
                provider_wake_prefix=provider_wake_prefix,
                streaming=streaming,
                content=[PlainInput(text=event.message_str)]
                if target is not None
                else None,
            )
            if input is None:
                return
            # Waiting hooks may override this event's presentation preference.
            if event.get_extra("enable_streaming") is not None:
                streaming = bool(event.get_extra("enable_streaming"))
            input.streaming = streaming
            show_reasoning = self.show_reasoning
            if event.get_extra("enable_reasoning") is not None:
                show_reasoning = bool(event.get_extra("enable_reasoning"))
            session = await runtime.open_session(
                event.unified_msg_origin,
                input=input,
                session_id=target.session_id if target is not None else None,
                options={"config": deepcopy(agent_config.get("config", {}))}
                if target is None
                else None,
            )
            session.runtime_name = runtime_name
            turn = await session.run_turn(
                input,
                admit=partial(
                    admit_agent_input, self.ctx.plugin_manager.context, input
                ),
            )
            active_event_registry.register_agent_stop_callback(event, turn.request_stop)
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
                        else chain_from_content(result.content)
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
                raise asyncio.CancelledError(
                    result.error.message if result.error else ""
                )
            if is_wakeup:
                if result.status == TurnStatus.CANCELLED:
                    raise asyncio.CancelledError()
                if result.status == TurnStatus.FAILED:
                    raise RuntimeError(
                        f"Wakeup agent failed: {result.error.message if result.error else 'unknown error'}"
                    )
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
            if turn is not None:
                active_event_registry.unregister_agent_stop_callback(
                    event, turn.request_stop
                )
                if not turn.done:
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
