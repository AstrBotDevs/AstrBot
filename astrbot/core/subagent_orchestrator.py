from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

from astrbot import logger
from astrbot.core.agent.agent import Agent
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.provider.func_tool_manager import FunctionToolManager

if TYPE_CHECKING:
    from astrbot.core.persona_mgr import PersonaManager


class SubAgentOrchestrator:
    """Loads subagent definitions from config and registers handoff tools.

    This is intentionally lightweight: it does not execute agents itself.
    Execution happens via HandoffTool in FunctionToolExecutor.
    """

    def __init__(
        self, tool_mgr: FunctionToolManager, persona_mgr: PersonaManager
    ) -> None:
        self._tool_mgr = tool_mgr
        self._persona_mgr = persona_mgr
        self.handoffs: list[HandoffTool] = []

    async def reload_from_config(self, cfg: dict[str, Any]) -> None:
        from astrbot.core.astr_agent_context import AstrAgentContext

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

            persona_id = item.get("persona_id")
            if persona_id is not None:
                persona_id = str(persona_id).strip() or None
            persona_data = self._persona_mgr.get_persona_v3_by_id(persona_id)
            if persona_id and persona_data is None:
                logger.warning(
                    "SubAgent persona %s not found, fallback to inline prompt.",
                    persona_id,
                )

            instructions = str(item.get("system_prompt", "")).strip()
            public_description = str(item.get("public_description", "")).strip()
            provider_id = item.get("provider_id")
            if provider_id is not None:
                provider_id = str(provider_id).strip() or None
            tools = item.get("tools", [])
            begin_dialogs = None

            if persona_data:
                prompt = str(persona_data.get("prompt", "")).strip()
                if prompt:
                    instructions = prompt
                begin_dialogs = copy.deepcopy(
                    persona_data.get("_begin_dialogs_processed")
                )
                tools = persona_data.get("tools")
                if public_description == "" and prompt:
                    public_description = prompt[:120]
            if tools is None:
                tools = None
            elif not isinstance(tools, list):
                tools = []
            else:
                tools = [str(t).strip() for t in tools if str(t).strip()]

            agent = Agent[AstrAgentContext](
                name=name,
                instructions=instructions,
                tools=tools,  # type: ignore
            )
            agent.begin_dialogs = begin_dialogs
            # The tool description should be a short description for the main LLM,
            # while the subagent system prompt can be longer/more specific.
            handoff = HandoffTool(
                agent=agent,
                tool_description=public_description or None,
            )

            # Optional per-subagent chat provider override.
            handoff.provider_id = provider_id

            handoffs.append(handoff)

        for handoff in handoffs:
            logger.info(f"Registered subagent handoff tool: {handoff.name}")

        self.handoffs = handoffs
