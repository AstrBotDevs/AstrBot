from dataclasses import dataclass
from typing import Any, Generic

from typing_extensions import TypeVar

TContext = TypeVar("TContext", default=Any)


@dataclass
class ContextWrapper(Generic[TContext]):
    """A context for running an agent, which can be used to pass additional data or state."""

    context: TContext
    tool_call_timeout: int = 60  # Default tool call timeout in seconds


NoContext = ContextWrapper[None]
