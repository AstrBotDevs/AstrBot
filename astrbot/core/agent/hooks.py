from dataclasses import dataclass
from .run_context import RunContext, TContext
from typing import Generic


@dataclass
class BaseAgentRunHooks(Generic[TContext]):
    async def on_agent_start(self, run_context: RunContext[TContext]): ...
    async def on_agent_step(self, run_context: RunContext[TContext]): ...
    async def on_agent_done(self, run_context: RunContext[TContext]): ...
