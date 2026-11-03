"""Subagent handoffs, main-agent tool deduplication, and routing instructions."""

from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.agent.tool import ToolSet
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.star.context import Context


def apply_subagents(
    req: ProviderRequest,
    plugin_context: Context,
) -> None:
    """Add handoffs and routing instructions after the main persona's tools.

    Args:
        req: Request with caller-supplied and persona-selected tools.
        plugin_context: Tool, persona, and subagent registries with live global
            routing configuration.
    """
    if not req.conversation:
        return
    tmgr = plugin_context.get_llm_tool_manager()
    # Handoffs belong to the global orchestrator, which the dashboard reloads
    # independently of session pipelines. Read its current global policy per build.
    orch_cfg = plugin_context.get_config().get("subagent_orchestrator", {})
    so = plugin_context.subagent_orchestrator
    if orch_cfg.get("main_enable", False) and so:
        remove_dup = bool(orch_cfg.get("remove_main_duplicate_tools", False))

        assigned_tools: set[str] = set()
        agents = orch_cfg.get("agents", [])
        if isinstance(agents, list):
            for a in agents:
                if not isinstance(a, dict):
                    continue
                if a.get("enabled", True) is False:
                    continue
                persona_tools = None
                pid = a.get("persona_id")
                if pid:
                    persona = plugin_context.persona_manager.get_persona_v3_by_id(pid)
                    if persona is not None:
                        persona_tools = persona.get("tools")
                tools = a.get("tools", [])
                if persona_tools is not None:
                    tools = persona_tools
                if tools is None:
                    assigned_tools.update(
                        [
                            tool.name
                            for tool in tmgr.func_list
                            if not isinstance(tool, HandoffTool)
                        ]
                    )
                    continue
                if not isinstance(tools, list):
                    continue
                for t in tools:
                    name = str(t).strip()
                    if name:
                        assigned_tools.add(name)

        if req.func_tool is None:
            req.func_tool = ToolSet()

        # add subagent handoff tools
        for tool in so.handoffs:
            req.func_tool.add_tool(tool)

        # check duplicates
        if remove_dup:
            handoff_names = {tool.name for tool in so.handoffs}
            for tool_name in assigned_tools:
                if tool_name in handoff_names:
                    continue
                req.func_tool.remove_tool(tool_name)

        router_prompt = orch_cfg.get("router_system_prompt", "").strip()
        if router_prompt:
            req.system_prompt += f"\n{router_prompt}\n"
