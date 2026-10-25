from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from astrbot import logger
from astrbot.core.agent.agent import Agent
from astrbot.core.provider.func_tool_manager import FunctionToolManager

from .runtime import SubAgentScheduler
from .store import SubAgentStore
from .tools import SubAgentTemplate

if TYPE_CHECKING:
    from astrbot.core.db import BaseDatabase
    from astrbot.core.persona_mgr import PersonaManager


class ExpertDefinition(BaseModel):
    """Editable expert settings shared by the plugin form and template loader."""

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
        """Treat empty selector values as an unset override.

        Args:
            value: Selected identifier, if any.

        Returns:
            Nonempty identifier or None.
        """
        return value or None


class SubAgentOrchestrator:
    """Load expert templates used by the single spawn_agent tool.

    Owns shared scheduling and optional persistent conversation runtimes.
    FunctionToolExecutor runs the selected template.
    """

    def __init__(
        self,
        tool_mgr: FunctionToolManager,
        persona_mgr: PersonaManager,
        db: BaseDatabase | None = None,
    ) -> None:
        self._tool_mgr = tool_mgr
        self._persona_mgr = persona_mgr
        self.templates: list[SubAgentTemplate] = []
        self.scheduler = SubAgentScheduler()
        self.store = SubAgentStore(db) if db is not None else None

    async def reload_from_config(self, cfg: dict[str, Any]) -> None:
        from .context import SubAgentContext as AstrAgentContext

        agents = cfg.get("agents", [])
        if not isinstance(agents, list):
            logger.warning("subagent_orchestrator.agents must be a list")
            return

        templates: list[SubAgentTemplate] = []
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
            template = SubAgentTemplate(
                agent=agent,
                description=public_description,
                provider_id=provider_id,
            )
            templates.append(template)

        for template in templates:
            logger.info("Loaded subagent template: %s", template.agent.name)

        self.templates = templates
