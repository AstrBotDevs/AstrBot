from typing import Any

from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.context import Context


@dataclass
class AstrAgentContext:
    __pydantic_config__ = {"arbitrary_types_allowed": True}

    context: Context
    """The star context instance"""
    event: AstrMessageEvent
    """The message event associated with the agent context."""
    extra: dict[str, Any] = Field(default_factory=dict)
    """Customized extra data."""
    trace_span: Any = Field(default=None)
    """Optional custom TraceSpan for subagent tracing. When set, tool calls within
    the agent loop will be recorded to this trace instead of event.trace.
    This prevents concurrent subagent and main agent tool calls from mixing up
    trace records."""


AgentContextWrapper = ContextWrapper[AstrAgentContext]
