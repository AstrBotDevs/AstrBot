"""Native main-agent integration for asynchronous subagent workers."""

from __future__ import annotations

import json
from html import escape
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from astrbot.core.agent.tool import ToolSet
from astrbot.core.astr_agent_runtime.tools.subagent import (
    SUBAGENT_TOOL_NAMES,
    CancelAgentTool,
    GetAgentResultTool,
    ListAgentsTool,
    SendAgentMessageTool,
    SpawnAgentTool,
    WaitAgentTool,
)
from astrbot.core.subagents.caller import AgentCaller
from astrbot.core.subagents.context import SubAgentContext
from astrbot.core.subagents.service import SubAgentService
from astrbot.core.subagents.store import AgentScope
from astrbot.core.utils.active_event_registry import active_event_registry

if TYPE_CHECKING:
    from astrbot.core.agent.run_context import ContextWrapper
    from astrbot.core.astr_agent_runtime.context import AstrAgentContext
    from astrbot.core.platform.astr_message_event import AstrMessageEvent
    from astrbot.core.provider.entities import ProviderRequest
    from astrbot.core.star.context import Context


class ExpertDefinition(BaseModel):
    """Expert configuration shared by the native API and template loader."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    enabled: StrictBool = True
    public_description: str = ""
    persona_id: str | None = None
    provider_id: str | None = None
    system_prompt: str = ""
    tools: list[str] | None = Field(default_factory=list)

    @field_validator("persona_id", "provider_id")
    @classmethod
    def normalize_optional_id(cls, value: str | None) -> str | None:
        """Return the selected ID, treating an empty selector as unset.

        Args:
            value: Configured persona or provider ID.

        Returns:
            The nonempty ID, or None.
        """
        return value or None


async def initialize_subagents(context: Context) -> None:
    """Register fixed controls and recover persisted workers after startup.

    Args:
        context: Initialized application services and target platform adapters.
    """
    if context.subagents is not None:
        await context.subagents.start(context)


async def apply_subagents(
    req: ProviderRequest, context: Context, event: AstrMessageEvent
) -> bool:
    """Validate worker wakeups and add native delegation tools to main.

    Args:
        req: Main request after persona and capability selection.
        context: Application services holding the global subagent configuration.
        event: Incoming message or programmatic wakeup.

    Returns:
        Whether main-agent construction may continue.
    """
    service = context.subagents
    config = context.get_config().get("subagent_orchestrator", {})
    enabled = config.get("main_enable", False)
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
    if not enabled or req.conversation is None:
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
        experts = []
        for item in config.get("agents", []):
            if not isinstance(item, dict) or not item.get("enabled", True):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            description = str(item.get("public_description", "")).strip()
            if not description and item.get("persona_id"):
                persona = context.persona_manager.get_persona_v3_by_id(
                    item["persona_id"]
                )
                if persona:
                    description = str(persona.get("prompt", "")).strip()[:120]
            experts.append({"name": name, "description": description})
        providers = [
            {"id": provider.provider_config["id"], "model": provider.get_model()}
            for provider in context.get_all_providers()
        ]
        req.system_prompt += (
            "\n<subagent_instructions>\n"
            "Delegate self-contained tasks with spawn_agent. Workers do not inherit "
            "your chat history. Select an expert by its template name below, or omit "
            "template for a generic worker. Expert instructions apply only to that worker.\n"
            f"<subagent_experts>\n{escape(json.dumps(experts, ensure_ascii=False), quote=False)}\n"
            "</subagent_experts>\n"
            "Optional provider_id overrides must use a configured ID from this catalog; "
            "omit it to use the expert's provider or the current conversation provider.\n"
            f"<subagent_providers>\n{escape(json.dumps(providers, ensure_ascii=False), quote=False)}\n"
            "</subagent_providers>\n"
            "Available agent runtimes: "
            + ", ".join(
                service.runtimes
                if isinstance(service, SubAgentService)
                else ["astrbot"]
            )
            + ". Omit runtime to use astrbot.\n"
            "</subagent_instructions>\n"
        )

    return True


async def begin_main_agent(run_context: ContextWrapper[AstrAgentContext]) -> None:
    """Bind main's conversation ownership without constructing a worker or runner.

    Args:
        run_context: Main execution before its first model step.
    """
    original = run_context.context
    if isinstance(original, SubAgentContext) and original.is_subagent:
        return
    service = original.context.subagents
    if not isinstance(service, SubAgentService) or run_context.runner is None:
        return
    if (
        not original.context.get_config()
        .get("subagent_orchestrator", {})
        .get("main_enable", False)
    ):
        return
    conversation = run_context.runner.req.conversation
    if conversation is None or original.agent_session is None:
        return
    scope = AgentScope(original.event.unified_msg_origin, conversation.cid)
    tools = run_context.runner.req.func_tool
    parent = SubAgentContext(
        context=original.context,
        event=original.event,
        extra=original.extra,
        permissions=original.permissions,
        plugin_tools=original.plugin_tools,
        plugin_skills=original.plugin_skills,
        agent_session=original.agent_session,
        subagent_scope=scope,
        delegable_tools=ToolSet(
            tools=[tool for tool in tools.tools if tool.name not in SUBAGENT_TOOL_NAMES]
        )
        if tools
        else ToolSet(),
    )
    run_context.context = parent
    caller = AgentCaller(
        parent.context, parent.event, scope, parent.delegable_tools, parent
    )
    service.delivery.callers[scope] = caller
