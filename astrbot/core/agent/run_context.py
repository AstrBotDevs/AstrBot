from typing import Any, Generic, Literal

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
    run_end_reason: Literal["completed", "error", "cancelled", "max_steps"] | None = (
        None
    )
    """Why execution ended; populated before on_agent_done is called."""
    run_error: str | None = None
    """Error description when execution failed, without retaining a traceback."""
    runner: Any = Field(default=None, repr=False, exclude=True)
    """Active runner, available to lifecycle hooks for steering and cancellation."""


NoContext = ContextWrapper[None]
