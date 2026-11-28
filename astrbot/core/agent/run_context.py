from typing import Generic, Literal

from pydantic import Field
from pydantic.dataclasses import dataclass

from .message import Message
from .tool import FunctionTool, ToolSet
from .tool import TContext as TContext


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
    tools: ToolSet | None = None
    """The executable tools available to this run."""
    dynamic_tools: bool = False
    """Restrict execution to the current catalog in dynamic tool mode."""
    _sdk_in_use: bool = Field(default=False, init=False, repr=False)
    """Whether an SDK tool loop owns this mutable context."""

    def is_tool_available(self, tool: FunctionTool) -> bool:
        """Check live availability and, in discovery mode, current run membership.

        Args:
            tool: The exact tool instance selected for execution.

        Returns:
            Whether that instance is still available to this run.
        """
        if not tool.is_available():
            return False
        return not self.dynamic_tools or (
            self.tools is not None and self.tools.get_tool(tool.name) is tool
        )


NoContext = ContextWrapper[None]
