from typing import ClassVar

from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runtime import (
    AgentPermissions,
    AgentRuntime,
    AgentSessionRef,
    AgentTurn,
)
from astrbot.core.agent.tool import ToolSet
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.skills.skill_manager import SkillInfo
from astrbot.core.star.context import Context


@dataclass
class AstrAgentContext:
    __pydantic_config__: ClassVar[dict[str, bool]] = {"arbitrary_types_allowed": True}

    context: Context
    """The star context instance"""
    event: AstrMessageEvent
    """The message event associated with the agent context."""
    extra: dict[str, str] = Field(default_factory=dict)
    """Customized extra data."""
    permissions: AgentPermissions | None = None
    """Authorization captured for this input; independent of the session owner."""
    plugin_tools: ToolSet | None = None
    """Core-authorized plugin tools, separate from native runtime capabilities."""
    plugin_skills: list[SkillInfo] | None = None
    """Core-authorized plugin skills available for delegation."""
    agent_session: AgentSessionRef | None = None
    """The current agent's runtime address, retained when it delegates work."""
    _runtime: AgentRuntime | None = None
    """Internal owner used by native delegation tools."""
    send_to_user: bool = True
    """Whether runtime-managed tools may deliver messages to platforms."""
    _output_turn: AgentTurn | None = None
    """Turn collecting prepared tool output, retained across native handoffs."""

    def __post_init__(self) -> None:
        """Resolve legacy SDK callers through the same authorization boundary."""
        if self.permissions is None:
            self.permissions = AgentPermissions.from_event(self.event)


AgentContextWrapper = ContextWrapper[AstrAgentContext]
