from typing import Any

from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.platform.astr_message_event import (
    AstrMessageEvent,  # noqa: F401  # re-exported for compat
)
from astrbot.core.star.context import Context


@dataclass
class AstrAgentContext:
    __pydantic_config__ = {"arbitrary_types_allowed": True}

    context: Context
    """The star context instance"""
    event: Any
    """The message event associated with the agent context. Accepts AstrMessageEvent and its proxy views."""
    extra: dict[str, str] = Field(default_factory=dict)
    """Customized extra data."""


AgentContextWrapper = ContextWrapper[AstrAgentContext]
