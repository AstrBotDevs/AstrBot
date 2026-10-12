from typing import Any, Generic

from pydantic import Field
from pydantic.dataclasses import dataclass
from typing_extensions import TypeVar

from .message import Message

TContext = TypeVar("TContext", default=Any)


@dataclass
class ContextWrapper(Generic[TContext]):
    """A context for running an agent, which can be used to pass additional data or state."""

    context: TContext
    messages: list[Message] = Field(default_factory=list)
    """This field stores the llm message context for the agent run, agent runners will maintain this field automatically."""
    tool_call_timeout: int = 120  # Default tool call timeout in seconds
    modalities: list[str] | None = None
    """Modalities supported by the provider selected for the current agent turn.

    ``None`` means unknown; tools should treat it as supporting all modalities.
    Agent runners maintain this field so tools can branch on the capabilities of
    the provider actually in use without re-resolving the session provider.
    """


NoContext = ContextWrapper[None]
