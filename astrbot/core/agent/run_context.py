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
    tool_call_timeout: int = 60  # Default tool call timeout in seconds


NoContext = ContextWrapper[None]
