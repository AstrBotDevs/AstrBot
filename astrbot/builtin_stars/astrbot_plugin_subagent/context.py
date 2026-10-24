from typing import Any
from uuid import uuid4

from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import ToolSet
from astrbot.core.astr_agent_context import AstrAgentContext

from .runtime import SubAgentRuntime


@dataclass
class SubAgentContext(AstrAgentContext):
    """Plugin-owned delegation state layered over the standard Agent context."""

    agent_id: str = Field(default_factory=lambda: uuid4().hex)
    conversation_id: str | None = None
    subagent_runtime: Any = Field(default_factory=SubAgentRuntime)
    delegable_tools: ToolSet = Field(default_factory=ToolSet)


AgentContextWrapper = ContextWrapper[SubAgentContext]
