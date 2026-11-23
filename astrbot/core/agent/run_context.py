from typing import Generic, Literal

from pydantic import Field
from pydantic.dataclasses import dataclass

from .message import Message
from .tool import TContext as TContext
from .tool import ToolSet


@dataclass
class ContextWrapper(Generic[TContext]):  # noqa: UP046 - The shared TypeVar default requires Python 3.12 compatibility.
    """A context for running an agent, which can be used to pass additional data or state."""

    context: TContext
    messages: list[Message] = Field(default_factory=list)
    """This field stores the llm message context for the agent run, agent runners will maintain this field automatically."""
    tool_call_timeout: int = 120  # Default tool call timeout in seconds
    run_end_reason: Literal["completed", "error", "cancelled", "max_steps"] | None = (
        None
    )
    """Why execution ended; populated before on_agent_done is called."""
    run_error: str | None = None
    """Error description when execution failed, without retaining a traceback."""
    tools: ToolSet | None = None
    """The executable tools available to this run."""


NoContext = ContextWrapper[None]
