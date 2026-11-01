"""Trigger adapters and completion handling for proactive main-agent runs."""

import json
import typing as T
from dataclasses import replace

from astrbot import logger
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runners.base import AgentState
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.astr_main_agent_resources import (
    BACKGROUND_TASK_RESULT_WOKE_SYSTEM_PROMPT,
)
from astrbot.core.cron.events import CronMessageEvent
from astrbot.core.log import log_context
from astrbot.core.platform.astr_message_event import event_context
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.star.context import Context
from astrbot.core.utils.active_event_registry import active_event_registry
from astrbot.core.utils.config_number import coerce_int_config
from astrbot.core.utils.history_saver import persist_agent_history
from astrbot.core.utils.trace import trace_execution


async def wake_cron_agent(
    ctx: Context,
    *,
    message: str,
    session_str: str,
    extras: dict,
    delivery_session_str: str = "",
) -> None:
    """Adapt a scheduled trigger, run its agent, and persist a task summary.

    Args:
        ctx: Session configuration and agent services.
        message: Short trigger message.
        session_str: Conversation to load for the scheduled run.
        extras: Job metadata and the original scheduling payload.
        delivery_session_str: Optional destination enabling proactive delivery.

    Raises:
        RuntimeError: If construction fails or the runner ends in an error state.
    """
    from astrbot.core.astr_main_agent import (
        MainAgentBuildConfig,
        build_main_agent,
    )
    from astrbot.core.astr_main_agent_resources import (
        PROACTIVE_AGENT_CRON_WOKE_SYSTEM_PROMPT,
        PROACTIVE_AGENT_CRON_WOKE_USER_PROMPT,
    )

    try:
        session = (
            session_str
            if isinstance(session_str, MessageSession)
            else MessageSession.from_str(session_str)
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"Invalid session for cron job: {e}")
        return

    cron_event = CronMessageEvent(
        context=ctx,
        session=session,
        message=message,
        extras=extras or {},
        message_type=session.message_type,
    )

    with (
        log_context(cron_event.get_platform_id(), cron_event.get_platform_name()),
        event_context(cron_event),
        trace_execution(cron_event.trace),
    ):
        # judge user's role
        umo = cron_event.unified_msg_origin
        cfg = ctx.get_config(umo=umo)
        enabled_plugins_name = cfg.get("plugin_set", ["*"])
        cron_event.plugins_name = (
            None if enabled_plugins_name == ["*"] else enabled_plugins_name
        )
        cron_payload = extras.get("cron_payload", {}) if extras else {}
        sender_id = cron_payload.get("sender_id")
        admin_ids = cfg.get("admins_id", [])
        if admin_ids:
            cron_event.role = "admin" if sender_id in admin_ids else "member"
        if cron_payload.get("origin", "tool") == "api":
            cron_event.role = "admin"

        agent_max_step = coerce_int_config(
            cfg.get("agent_runner", {})
            .get("config", {})
            .get("misc", {})
            .get("max_steps", 128),
            default=128,
            min_value=1,
            field_name="agent_runner.config.misc.max_steps",
        )
        config = replace(
            MainAgentBuildConfig.from_config(cfg),
            streaming_response=False,
            load_session_history=True,
            enable_message_delivery=bool(delivery_session_str),
        )
        req = ProviderRequest()
        cron_job_str = json.dumps(extras.get("cron_job", {}), ensure_ascii=False)
        req.system_prompt += PROACTIVE_AGENT_CRON_WOKE_SYSTEM_PROMPT
        # Keep per-run metadata after history so it does not invalidate its cache.
        req.prompt = PROACTIVE_AGENT_CRON_WOKE_USER_PROMPT.format(cron_job=cron_job_str)
        result = await build_main_agent(
            event=cron_event, plugin_context=ctx, config=config, req=req
        )
        if not result:
            raise RuntimeError("Failed to build main agent for cron job.")

        runner = result.agent_runner
        async for _ in runner.step_until_done(agent_max_step):
            # agent will send message to user via using tools
            pass
        llm_resp = runner.get_final_llm_resp()
        if runner.state == AgentState.ERROR:
            # The run failed (e.g. malformed function call at max steps) but
            # no exception escapes the runner; without this the job was
            # recorded as completed with last_error=NULL and the user saw
            # only intermediate messages (#9980).
            detail = (
                f": {llm_resp.completion_text}"
                if llm_resp and llm_resp.completion_text
                else ""
            )
            raise RuntimeError(f"Cron agent run ended in ERROR state{detail}")
        cron_meta = extras.get("cron_job", {}) if extras else {}
        summary_note = (
            f"[CronJob] {cron_meta.get('name') or cron_meta.get('id', 'unknown')}: {cron_meta.get('description', '')} "
            f" triggered at {cron_meta.get('run_started_at', 'unknown time')}, "
        )
        if llm_resp and llm_resp.role == "assistant":
            summary_note += (
                f"I finished this job, here is the result: {llm_resp.completion_text}"
            )

        await persist_agent_history(
            ctx.conversation_manager,
            event=cron_event,
            req=req,
            summary_note=summary_note,
        )
        if not llm_resp:
            logger.warning("Cron job agent got no response")
            return


async def wake_background_agent(
    run_context: ContextWrapper[AstrAgentContext],
    *,
    task_id: str,
    tool_name: str,
    result_text: str,
    tool_args: dict[str, T.Any],
    note: str,
    summary_name: str,
    extra_result_fields: dict[str, T.Any] | None = None,
) -> None:
    """Wake a main agent to handle the completion of a background tool or handoff.

    Args:
        run_context: Original execution context, including its shared stop signal.
        task_id: Background task identifier.
        tool_name: Completed tool's name.
        result_text: Tool result to deliver to the agent.
        tool_args: Arguments used by the completed task.
        note: Short trigger message.
        summary_name: Name included in the persisted task summary.
        extra_result_fields: Optional metadata for a background handoff.
    """
    from astrbot.core.astr_main_agent import (
        MainAgentBuildConfig,
        build_main_agent,
    )

    event = run_context.context.event
    stop_signal = active_event_registry.get_background_stop_signal(event)
    if stop_signal.is_set():
        return
    ctx = run_context.context.context

    task_result = {
        "task_id": task_id,
        "tool_name": tool_name,
        "result": result_text or "",
        "tool_args": tool_args,
    }
    if extra_result_fields:
        task_result.update(extra_result_fields)
    extras = {
        "background_task_result": task_result,
        "_background_stop_signal": stop_signal,
    }

    session = MessageSession.from_str(event.unified_msg_origin)
    cron_event = CronMessageEvent(
        context=ctx,
        session=session,
        message=note,
        extras=extras,
        message_type=session.message_type,
    )
    cron_event.role = event.role
    cfg = ctx.get_config(umo=event.unified_msg_origin) or {}
    provider_settings = cfg.get("provider_settings") or {}
    agent_max_step = coerce_int_config(
        cfg.get("agent_runner", {})
        .get("config", {})
        .get("misc", {})
        .get("max_steps", 128),
        default=128,
        min_value=1,
        field_name="agent_runner.config.misc.max_steps",
    )
    config = replace(
        MainAgentBuildConfig.from_config(cfg),
        tool_call_timeout=run_context.tool_call_timeout,
        # Preserve the background entry point's legacy streaming setting.
        streaming_response=provider_settings.get("stream", False),
        load_session_history=True,
        enable_message_delivery=True,
    )

    req = ProviderRequest()
    bg = json.dumps(extras["background_task_result"], ensure_ascii=False)
    req.system_prompt += BACKGROUND_TASK_RESULT_WOKE_SYSTEM_PROMPT.format(
        background_task_result=bg
    )
    req.prompt = (
        "Proceed according to your system instructions. "
        "Output using same language as previous conversation. "
        "If you need to deliver the result to the user immediately, "
        "you MUST use `send_message_to_user` tool to send the message directly to the user, "
        "otherwise the user will not see the result. "
        "After completing your task, summarize and output your actions and results. "
    )
    result = await build_main_agent(
        event=cron_event, plugin_context=ctx, config=config, req=req
    )
    if stop_signal.is_set():
        return
    if not result:
        logger.error(f"Failed to build main agent for background task {tool_name}.")
        return

    runner = result.agent_runner
    async for _ in runner.step_until_done(agent_max_step):
        # agent will send message to user via using tools
        pass
    llm_resp = runner.get_final_llm_resp()
    task_meta = extras.get("background_task_result", {})
    summary_note = (
        f"[BackgroundTask] {summary_name} "
        f"(task_id={task_meta.get('task_id', task_id)}) finished. "
        f"Result: {task_meta.get('result') or result_text or 'no content'}"
    )
    if llm_resp and llm_resp.completion_text:
        summary_note += (
            f"I finished the task, here is the result: {llm_resp.completion_text}"
        )
    await persist_agent_history(
        ctx.conversation_manager,
        event=cron_event,
        req=req,
        summary_note=summary_note,
    )
    if not llm_resp:
        logger.warning("background task agent got no response")
        return
    # Set once anything reaches this session, e.g. via send_message_to_user.
    if not cron_event._has_send_oper:
        logger.warning(
            f"Background task {tool_name} (task_id={task_id}) finished, but "
            "nothing was sent to the user. The result was only saved to the "
            "conversation history."
        )
