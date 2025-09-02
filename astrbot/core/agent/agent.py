from dataclasses import dataclass
from .tool import FunctionTool
from typing import Generic
from .run_context import TContext
from .hooks import BaseAgentRunHooks


@dataclass
class Agent(Generic[TContext]):
    name: str
    instructions: str | None = None
    tools: list[str, FunctionTool] | None = None
    run_hooks: BaseAgentRunHooks[TContext] | None = None
