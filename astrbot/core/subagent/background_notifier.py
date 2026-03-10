from __future__ import annotations

import json
import typing as T

from astrbot import logger
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import ToolSet
from astrbot.core.cron.events import CronMessageEvent
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.provider.entites import ProviderRequest
from astrbot.core.utils.history_saver import persist_agent_history

if T.TYPE_CHECKING:
    from astrbot.core.astr_agent_context import AstrAgentContext


async def wake_main_agent_for_background_result(
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
    from astrbot.core.astr_main_agent import (
        MainAgentBuildConfig,
        _get_session_conv,
        build_main_agent,
    )
    from astrbot.core.astr_main_agent_resources import (
        BACKGROUND_TASK_RESULT_WOKE_SYSTEM_PROMPT,
        SEND_MESSAGE_TO_USER_TOOL,
    )

    event = run_context.context.event
    ctx = run_context.context.context

    task_result = {
        "task_id": task_id,
        "tool_name": tool_name,
        "result": result_text or "",
        "tool_args": tool_args,
    }
    if extra_result_fields:
        task_result.update(extra_result_fields)
    extras = {"background_task_result": task_result}

    session = MessageSession.from_str(event.unified_msg_origin)
    cron_event = CronMessageEvent(
        context=ctx,
        session=session,
        message=note,
        extras=extras,
        message_type=session.message_type,
    )
    cron_event.role = event.role
    cfg = ctx.get_config(umo=event.unified_msg_origin)
    provider_settings = cfg.get("provider_settings", {})
    config = MainAgentBuildConfig.from_provider_settings(
        provider_settings,
        cfg=cfg,
        # Background tasks use a longer timeout and disable local computer use
        # by default – these overrides preserve the original behaviour.
        tool_call_timeout=max(
            int(provider_settings.get("tool_call_timeout", 0) or 0),
            900,
        ),
        computer_use_runtime=str(provider_settings.get("computer_use_runtime", "none")),
    )

    req = ProviderRequest()
    conv = await _get_session_conv(event=cron_event, plugin_context=ctx)
    req.conversation = conv
    context = json.loads(conv.history)
    if context:
        req.contexts = context
        context_dump = req._print_friendly_context()
        req.contexts = []
        req.system_prompt += f"\n\nBelow is your and the user's previous conversation history:\n{context_dump}"

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
    if not req.func_tool:
        req.func_tool = ToolSet()
    req.func_tool.add_tool(SEND_MESSAGE_TO_USER_TOOL)

    result = await build_main_agent(
        event=cron_event, plugin_context=ctx, config=config, req=req
    )
    if not result:
        logger.error("Failed to build main agent for background task %s.", tool_name)
        return

    runner = result.agent_runner
    async for _ in runner.step_until_done(30):
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
