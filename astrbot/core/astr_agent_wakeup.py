"""Run a programmatically triggered main-agent turn for a target session."""

import asyncio
from dataclasses import replace

from astrbot import logger
from astrbot.core.agent.runners.base import AgentState
from astrbot.core.log import log_context
from astrbot.core.platform.agent_wakeup_event import AgentWakeupEvent, WakeupSource
from astrbot.core.platform.astr_message_event import event_context
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.star.context import Context
from astrbot.core.utils.active_event_registry import active_event_registry
from astrbot.core.utils.config_number import coerce_int_config
from astrbot.core.utils.history_saver import persist_agent_history
from astrbot.core.utils.session_lock import session_lock_manager
from astrbot.core.utils.trace import trace_execution


async def wake_main_agent(
    ctx: Context,
    *,
    session_str: str,
    user_prompt: str,
    source: WakeupSource,
    source_id: str | None = None,
    role: str = "member",
    stop_signal: asyncio.Event | None = None,
) -> None:
    """Append a triggered user turn to the current conversation and run its agent.

    Args:
        ctx: Session configuration and agent services.
        session_str: UMO whose current conversation supplies the existing context.
        user_prompt: Trigger instructions and data, exclusively for this user turn.
        source: Trigger mechanism, independent of the target session's platform.
        source_id: Cron job ID, background task ID, or invoking plugin ID.
        role: Initiating caller's resolved permission role.
        stop_signal: Optional cancellation signal shared with a background task.

    Raises:
        RuntimeError: If construction or execution fails.
        ValueError: If the source, target session, or stored history is invalid.
    """
    from astrbot.core.astr_main_agent import MainAgentBuildConfig, build_main_agent

    if stop_signal is not None and stop_signal.is_set():
        return
    session = MessageSession.from_str(session_str)
    metadata = PlatformMetadata(
        id=session.platform_id,
        name="internal",
        description="Agent wakeup target without an active platform adapter",
        support_proactive_message=False,
        support_streaming_message=False,
    )
    platform = ctx.get_platform_inst(session.platform_id)
    if platform is not None:
        platform_metadata = platform.meta()
        if isinstance(platform_metadata, PlatformMetadata):
            metadata = platform_metadata
    event = AgentWakeupEvent(
        context=ctx,
        session=session,
        platform_meta=metadata,
        prompt=user_prompt,
        source=source,
        source_id=source_id,
        role=role,
    )
    if stop_signal is not None:
        event.set_extra("_background_stop_signal", stop_signal)
    stop_signal = active_event_registry.get_background_stop_signal(event)

    with (
        log_context(event.get_platform_id(), event.get_platform_name()),
        event_context(event),
        trace_execution(event.trace),
    ):
        # Share the ordinary-message lock so a concurrent turn cannot replace history.
        async with session_lock_manager.acquire_lock(event.unified_msg_origin):
            if stop_signal.is_set():
                return
            cfg = ctx.get_config(umo=event.unified_msg_origin)
            enabled_plugins = cfg.get("plugin_set", ["*"])
            event.plugins_name = None if enabled_plugins == ["*"] else enabled_plugins
            config = replace(
                MainAgentBuildConfig.from_config(cfg),
                load_session_history=True,
                call_request_hook=True,
                validate_provider_endpoint=True,
            )
            req = ProviderRequest(prompt=user_prompt)
            result = await build_main_agent(
                event=event, plugin_context=ctx, config=config, req=req
            )
            if stop_signal.is_set() or event.is_stopped():
                return
            if result is None:
                raise RuntimeError("Failed to build main agent for wakeup.")
            runner = result.agent_runner
            active_event_registry.register_agent_stop_callback(
                event, lambda: runner.request_stop()
            )
            max_steps = coerce_int_config(
                cfg.get("agent_runner", {})
                .get("config", {})
                .get("misc", {})
                .get("max_steps", 128),
                default=128,
                min_value=1,
                field_name="agent_runner.config.misc.max_steps",
            )
            async for _ in runner.step_until_done(max_steps):
                if stop_signal.is_set():
                    runner.request_stop()
                    return
            if stop_signal.is_set() or event.is_stopped():
                return
            response = runner.get_final_llm_resp()
            if runner.state == AgentState.ERROR:
                detail = f": {response.completion_text}" if response else ""
                raise RuntimeError(f"Wakeup agent run ended in ERROR state{detail}")
            await persist_agent_history(
                ctx.conversation_manager, event=event, req=req, response=response
            )
            if response is None:
                logger.warning("Main-agent wakeup completed without a final response.")
            elif not event._has_send_oper:
                logger.debug(
                    "Main-agent wakeup completed without user delivery; "
                    "the result was saved to conversation history."
                )
