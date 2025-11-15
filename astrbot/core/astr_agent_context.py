from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.context import Context


@dataclass(config={"arbitrary_types_allowed": True})
class AstrAgentContext:
    context: Context
    """The star context instance"""
    event: AstrMessageEvent
    """The message event associated with the agent context."""
    extra: dict[str, str] = Field(default_factory=dict)
    """Customized extra data."""


AgentContextWrapper = ContextWrapper[AstrAgentContext]
