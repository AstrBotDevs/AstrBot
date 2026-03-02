from __future__ import annotations
from astrbot.core.lang import t

from typing import Any

from astrbot import logger
from astrbot.core.agent.agent import Agent
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.persona_mgr import PersonaManager
from astrbot.core.provider.func_tool_manager import FunctionToolManager


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
            logger.warning(t("msg-5d950986"))
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
            persona_data = None
            if persona_id:
                try:
                    persona_data = await self._persona_mgr.get_persona(persona_id)
                except StopIteration:
                    logger.warning(
                        t("msg-4867eefb", persona_id=persona_id),
                    )

            instructions = str(item.get("system_prompt", "")).strip()
            public_description = str(item.get("public_description", "")).strip()
            provider_id = item.get("provider_id")
            if provider_id is not None:
                provider_id = str(provider_id).strip() or None
            tools = item.get("tools", [])
            begin_dialogs = None

            if persona_data:
                instructions = persona_data.system_prompt or instructions
                begin_dialogs = persona_data.begin_dialogs
                tools = persona_data.tools
                if public_description == "" and persona_data.system_prompt:
                    public_description = persona_data.system_prompt[:120]
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
            logger.info(t("msg-f425c9f0", res=handoff.name))

        self.handoffs = handoffs
