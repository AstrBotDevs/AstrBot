from typing import Generic
from .tool import FunctionTool
from .agent import Agent
from .run_context import TContext


class HandoffTool(FunctionTool, Generic[TContext]):
    """Handoff tool for delegating tasks to another agent."""

    def __init__(
        self, agent: Agent[TContext], parameters: dict | None = None, **kwargs
    ):
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
