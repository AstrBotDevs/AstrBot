"""Native main-agent integration for asynchronous subagent workers."""

from __future__ import annotations

import json
from html import escape
from typing import TYPE_CHECKING

from astrbot.core.agent.tool import ToolSet
from astrbot.core.astr_agent_runtime.subagents.caller import AgentCaller
from astrbot.core.astr_agent_runtime.subagents.context import SubAgentContext
from astrbot.core.astr_agent_runtime.subagents.service import SubAgentService
from astrbot.core.astr_agent_runtime.subagents.store import AgentScope
from astrbot.core.astr_agent_runtime.tools.subagent import (
    SUBAGENT_TOOL_NAMES,
    CancelAgentTool,
    GetAgentResultTool,
    ListAgentsTool,
    SendAgentMessageTool,
    SpawnAgentTool,
    WaitAgentTool,
)
from astrbot.core.utils.active_event_registry import active_event_registry

if TYPE_CHECKING:
    from astrbot.core.agent.run_context import ContextWrapper
    from astrbot.core.astr_agent_runtime.context import AstrAgentContext
    from astrbot.core.astr_agent_runtime.runtime import AstrAgentRuntime
    from astrbot.core.platform.astr_message_event import AstrMessageEvent
    from astrbot.core.provider.entities import ProviderRequest
    from astrbot.core.star.context import Context


async def apply_subagents(
    req: ProviderRequest,
    context: Context,
    event: AstrMessageEvent,
    *,
    runtime: AstrAgentRuntime | None = None,
) -> bool:
    """Validate worker wakeups and add native delegation tools to main.

    Args:
        req: Main request after persona and capability selection.
        context: Application services supplying profile configuration and plugin tools.
        event: Incoming message or programmatic wakeup.
        runtime: Native owner supplying configuration storage and delegation services.

    Returns:
        Whether main-agent construction may continue.
    """
    service = runtime.subagents if runtime is not None else None
    config = (
        context.get_config(umo=event.unified_msg_origin)
        .get("agent", {})
        .get("config", {})
        .get("subagents", {})
    )
    enabled = config.get("enabled", False)
    wakeup = event.get_extra("_subagent_wakeup")
    if wakeup is not None:
        if req.conversation is None:
            event.stop_event()
            return False
        scope = AgentScope(
            event.unified_msg_origin,
            req.conversation.cid,
        )
        from astrbot.core.platform.agent_wakeup_event import AgentWakeupEvent

        if not isinstance(event, AgentWakeupEvent) or event.agent_session is None:
            event.stop_event()
            return False
        parent = event.agent_session
        if (
            list(wakeup) != [scope.umo, scope.conversation_id]
            or not isinstance(service, SubAgentService)
            or not enabled
            or active_event_registry.get_background_stop_signal(event).is_set()
            or req.conversation.cid != parent.session_id
        ):
            event.stop_event()
            return False
        if not await service.delivery.consume_wakeup(
            scope, parent, json.dumps(req.contexts, ensure_ascii=False)
        ):
            event.stop_event()
            return False
    if req.func_tool is None:
        req.func_tool = ToolSet()
    for name in SUBAGENT_TOOL_NAMES:
        req.func_tool.remove_tool(name)
    if not enabled or req.conversation is None or runtime is None:
        return True
    manager = context.get_llm_tool_manager()
    for tool_type in (
        SpawnAgentTool,
        ListAgentsTool,
        WaitAgentTool,
        GetAgentResultTool,
        SendAgentMessageTool,
        CancelAgentTool,
    ):
        tool = manager.get_builtin_tool(tool_type)
        if tool.active:
            req.func_tool.add_tool(tool)

    if req.func_tool.get_tool("spawn_agent") is not None:
        configurations = []
        for config_id in config.get("config_ids", []):
            agent_config = await runtime.agent_configs.get(config_id)
            if not agent_config.enabled:
                continue
            if agent_config.runtime not in runtime.subagents.runtimes:
                raise ValueError(f"Agent runtime unavailable: {agent_config.runtime}")
            configurations.append(
                {
                    "config_id": agent_config.config_id,
                    "name": agent_config.name,
                    "description": agent_config.description,
                    "runtime": agent_config.runtime,
                }
            )
        req.system_prompt += (
            "\n<subagent_instructions>\n"
            "Delegate self-contained tasks with spawn_agent. Workers do not inherit "
            "your chat history. Choose a config_id from the catalog, or omit config_id "
            "for a generic native worker. Each agent configuration selects its own runtime and configuration.\n"
            f"<agent_configs>\n{escape(json.dumps(configurations, ensure_ascii=False), quote=False)}\n"
            "</agent_configs>\n</subagent_instructions>\n"
        )

    return True


async def begin_main_agent(
    run_context: ContextWrapper[AstrAgentContext],
    *,
    conversation_id: str | None,
    tools: ToolSet | None,
) -> None:
    """Bind main's conversation ownership without constructing a worker or runner.

    Args:
        run_context: Main execution before its first model step.
        conversation_id: Parent conversation ID from the prepared request.
        tools: Parent tools available at the start of execution.
    """
    original = run_context.context
    if isinstance(original, SubAgentContext) and original.is_subagent:
        return
    from astrbot.core.astr_agent_runtime.runtime import AstrAgentRuntime

    runtime = original._runtime
    if not isinstance(runtime, AstrAgentRuntime):
        return
    service = runtime.subagents
    if not isinstance(service, SubAgentService):
        return
    if (
        not original.context.get_config(umo=original.event.unified_msg_origin)
        .get("agent", {})
        .get("config", {})
        .get("subagents", {})
        .get("enabled", False)
    ):
        return
    if conversation_id is None or original.agent_session is None:
        return
    scope = AgentScope(original.event.unified_msg_origin, conversation_id)
    parent = SubAgentContext(
        context=original.context,
        event=original.event,
        extra=original.extra,
        permissions=original.permissions,
        plugin_tools=original.plugin_tools,
        plugin_skills=original.plugin_skills,
        agent_session=original.agent_session,
        _runtime=runtime,
        subagent_scope=scope,
        delegable_tools=ToolSet(
            tools=[tool for tool in tools.tools if tool.name not in SUBAGENT_TOOL_NAMES]
        )
        if tools
        else ToolSet(),
    )
    run_context.context = parent
    caller = AgentCaller(
        parent.context,
        parent.event,
        scope,
        parent.delegable_tools,
        parent,
        limits=original.context.get_config(umo=scope.umo)
        .get("agent", {})
        .get("config", {})
        .get("subagents", {}),
    )
    service.delivery.callers[scope] = caller
