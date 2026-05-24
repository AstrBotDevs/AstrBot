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

    Static subagents from config are registered into SubAgentManager so they
    can enjoy unified lifecycle management, shared context, history retention,
    and other advanced features alongside dynamically created subagents.
    """

    def __init__(
        self,
        tool_mgr: FunctionToolManager,
        persona_mgr: PersonaManager,
    ) -> None:
        self._tool_mgr = tool_mgr
        self._persona_mgr = persona_mgr
        self.handoffs: list[HandoffTool] = []
        self.handoff_skills: list[Any] = []

    async def reload_from_config(self, cfg: dict[str, Any]) -> None:
        from astrbot.core.astr_agent_context import AstrAgentContext

        agents = cfg.get("agents", [])
        if not isinstance(agents, list):
            logger.warning("subagent_orchestrator.agents must be a list")
            return

        handoffs: list[HandoffTool] = []
        handoff_skills: list[Any] = []
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
            default_handoff_mode = str(
                item.get("default_handoff_mode", "normal")
            ).strip()
            if default_handoff_mode not in {"normal", "silent"}:
                default_handoff_mode = "normal"
            tools = item.get("tools", [])
            skills = item.get("skills", [])
            begin_dialogs = None

            if persona_data:
                prompt = str(persona_data.get("prompt", "")).strip()
                if prompt:
                    instructions = prompt
                begin_dialogs = copy.deepcopy(
                    persona_data.get("_begin_dialogs_processed"),
                )
                tools = persona_data.get("tools")
                skills = persona_data.get("skills")
                if public_description == "" and prompt:
                    public_description = prompt[:120]
            if tools is None:
                tools = None
            elif not isinstance(tools, list):
                tools = None
            else:
                tools = [str(t).strip() for t in tools if str(t).strip()]
            if skills is None:
                skills = []
            elif not isinstance(skills, list):
                skills = []
            else:
                skills = [str(s).strip() for s in skills if str(s).strip()]
            agent = Agent[AstrAgentContext](
                name=name,
                instructions=instructions,
                tools=tools,
                skills=skills,
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
            handoff.set_default_handoff_mode(default_handoff_mode)

            handoffs.append(handoff)
            handoff_skills.append(skills)

        for handoff in handoffs:
            logger.info(f"Registered subagent handoff tool: {handoff.name}")

        self.handoffs = handoffs
        self.handoff_skills = handoff_skills

    def register_static_subagents_to_manager(self, session_id: str) -> None:
        """Register all static subagents (from config) into SubAgentManager.

        This makes static subagents enjoy the same unified management as
        dynamically created subagents: shared context, history retention,
        lifecycle management, etc.

        Static subagents are always protected from auto-cleanup.
        """

        try:
            from astrbot.core.subagent_manager import SubAgentManager
        except ImportError:
            return

        for handoff, skills in zip(self.handoffs, self.handoff_skills, strict=False):
            try:
                workdir = None
                # Try to get skills from the handoff tool or agent
                agent = handoff.agent
                # The agent.tools may contain skill names; we pass them along
                # SubAgentManager will filter and build skills prompt as needed
                SubAgentManager.register_static_subagent(
                    session_id=session_id,
                    handoff_tool=handoff,
                    skills=skills,
                    workdir=workdir,
                )
                logger.debug(
                    "[SubAgentOrchestrator] Registered static subagent '%s' to SubAgentManager for session %s",
                    agent.name,
                    session_id,
                )
            except Exception as e:
                logger.warning(
                    "[SubAgentOrchestrator] Failed to register static subagent '%s' to manager: %s",
                    getattr(handoff.agent, "name", "unknown"),
                    e,
                )
