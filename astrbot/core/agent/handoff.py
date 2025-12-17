from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Generic

from typing_extensions import TypedDict, Unpack

from astrbot.core.message.message_event_result import MessageEventResult

from .agent import Agent
from .run_context import TContext
from .tool import FunctionTool, ParametersType


class HandoffInitKwargs(TypedDict, total=False):
    handler: (
        Callable[..., Awaitable[str | None] | AsyncGenerator[MessageEventResult]] | None
    )
    handler_module_path: str | None
    active: bool


class HandoffTool(FunctionTool, Generic[TContext]):
    """Handoff tool for delegating tasks to another agent."""

    def __init__(
        self,
        agent: Agent[TContext],
        parameters: ParametersType | None = None,
        **kwargs: Unpack[HandoffInitKwargs],
    ) -> None:
        self.agent = agent
        super().__init__(
            name=f"transfer_to_{agent.name}",
            parameters=parameters or self.default_parameters(),
            description=agent.instructions or self.default_description(agent.name),
            **kwargs,
        )

    def default_parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "The input to be handed off to another agent. This should be a clear and concise request or task.",
                },
            },
        }

    def default_description(self, agent_name: str | None) -> str:
        agent_name = agent_name or "another"
        return f"Delegate tasks to {self.name} agent to handle the request."
