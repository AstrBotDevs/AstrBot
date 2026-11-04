"""Main/worker ownership passed through the native AstrBot tool context."""

from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.core.agent.tool import ToolSet
from astrbot.core.astr_agent_runtime.context import AstrAgentContext

from .store import AgentScope


@dataclass
class SubAgentContext(AstrAgentContext):
    """An execution's owner and delegable tools, without a synthetic parent agent ID."""

    subagent_scope: AgentScope | None = None
    delegable_tools: ToolSet = Field(default_factory=ToolSet)
    is_subagent: bool = False
