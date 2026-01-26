from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from astrbot import logger
from astrbot.core.agent.agent import Agent
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.provider.func_tool_manager import FunctionToolManager


@dataclass(frozen=True)
class SubAgentConfig:
    """Runtime representation of a configured subagent."""

    name: str
    instructions: str
    tools: list[str]
    enabled: bool = True


class SubAgentOrchestrator:
    """Loads subagent definitions from config and registers handoff tools.

    This is intentionally lightweight: it does not execute agents itself.
    Execution happens via HandoffTool in FunctionToolExecutor.
    """

    def __init__(self, tool_mgr: FunctionToolManager):
        self._tool_mgr = tool_mgr
        self._registered_handoff_names: set[str] = set()

    def reload_from_config(self, provider_settings: dict[str, Any]) -> None:
        cfg = provider_settings.get("subagent_orchestrator", {})
        enabled = bool(cfg.get("main_enable", False))

        # Remove previously registered dynamic handoff tools.
        if self._registered_handoff_names:
            for name in list(self._registered_handoff_names):
                try:
                    self._tool_mgr.remove_func(name)
                except Exception:
                    # remove_func is best-effort; keep going.
                    pass
            self._registered_handoff_names.clear()

        if not enabled:
            return

        agents = cfg.get("agents", [])
        if not isinstance(agents, list):
            logger.warning("subagent_orchestrator.agents must be a list")
            return

        for item in agents:
            if not isinstance(item, dict):
                continue
            if not item.get("enabled", True):
                continue

            name = str(item.get("name", "")).strip()
            if not name:
                continue

            instructions = str(item.get("description", "")).strip()
            tools = item.get("tools", [])
            if not isinstance(tools, list):
                tools = []
            tools = [str(t).strip() for t in tools if str(t).strip()]

            agent = Agent[AstrAgentContext](
                name=name,
                instructions=instructions,
                tools=tools,
            )
            handoff = HandoffTool(agent=agent)

            # Mark as dynamic so we can replace/remove later.
            handoff.handler_module_path = "core.subagent_orchestrator"

            # Register tool (replaces if same name exists).
            self._tool_mgr.add_func(
                name=handoff.name,
                func_args=[
                    {
                        "type": "string",
                        "name": "input",
                        "description": "Task input delegated from the main agent.",
                    }
                ],
                desc=handoff.description,
                handler=handoff.handler,
            )

            # NOTE: add_func wraps handler into a FunctionTool; we want the actual HandoffTool.
            # Therefore, directly append the HandoffTool to func_list (and remove any wrapper).
            self._tool_mgr.remove_func(handoff.name)
            self._tool_mgr.func_list.append(handoff)

            self._registered_handoff_names.add(handoff.name)
            logger.info(f"Registered subagent handoff tool: {handoff.name}")
