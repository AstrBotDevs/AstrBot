from dataclasses import dataclass
from typing import Any

from .hooks import BaseAgentRunHooks
from .tool import FunctionTool


@dataclass
class Agent[TContext]:
    name: str
    instructions: str | None = None
    tools: list[str | FunctionTool] | None = None
    run_hooks: BaseAgentRunHooks[TContext] | None = None
    begin_dialogs: list[Any] | None = None
