from dataclasses import dataclass
from typing import Generic

from .hooks import BaseAgentRunHooks
from .run_context import TContext
from .tool import FunctionTool


@dataclass
class Agent(Generic[TContext]):
    name: str
    instructions: str | None = None
    tools: list[str | FunctionTool] | None = None
    run_hooks: BaseAgentRunHooks[TContext] | None = None
