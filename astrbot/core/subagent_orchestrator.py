from __future__ import annotations

from typing import Any

from astrbot import logger
from astrbot.core.agent.agent import Agent
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.provider.func_tool_manager import FunctionToolManager


class SubAgentOrchestrator:
    """Loads subagent definitions from config and registers handoff tools.

    This is intentionally lightweight: it does not execute agents itself.
    Execution happens via HandoffTool in FunctionToolExecutor.
    """

    def __init__(self, tool_mgr: FunctionToolManager):
        self._tool_mgr = tool_mgr

    def reload_from_config(self, cfg: dict[str, Any]) -> None:
        enabled = bool(cfg.get("main_enable", False))

        if not enabled:
            # Ensure any previous dynamic handoff tools are cleared.
            self._tool_mgr.sync_dynamic_handoff_tools(
                [],
                handler_module_path="core.subagent_orchestrator",
            )
            return

        agents = cfg.get("agents", [])
        if not isinstance(agents, list):
            logger.warning("subagent_orchestrator.agents must be a list")
            return

        handoffs: list[HandoffTool] = []
        for item in agents:
            if not isinstance(item, dict):
                continue
            if not item.get("enabled", True):
                continue

            name = str(item.get("name", "")).strip()
            if not name:
                continue

            instructions = str(item.get("system_prompt", "")).strip()
            public_description = str(item.get("public_description", "")).strip()
            provider_id = item.get("provider_id")
            if provider_id is not None:
                provider_id = str(provider_id).strip() or None
            tools = item.get("tools", [])
            if not isinstance(tools, list):
                tools = []
            tools = [str(t).strip() for t in tools if str(t).strip()]

            agent = Agent[AstrAgentContext](
                name=name,
                instructions=instructions,
                tools=tools,
            )
            # The tool description should be a short description for the main LLM,
            # while the subagent system prompt can be longer/more specific.
            handoff = HandoffTool(
                agent=agent,
                tool_description=public_description or None,
            )

            # Optional per-subagent chat provider override.
            handoff.provider_id = provider_id

            handoffs.append(handoff)

        self._tool_mgr.sync_dynamic_handoff_tools(
            handoffs,
            handler_module_path="core.subagent_orchestrator",
        )

        for handoff in handoffs:
            logger.info(f"Registered subagent handoff tool: {handoff.name}")
