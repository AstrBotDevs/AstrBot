from typing import Generic

from .agent import Agent
from .run_context import TContext
from .tool import FunctionTool


class HandoffTool(FunctionTool, Generic[TContext]):
    """Handoff tool for delegating tasks to another agent."""

    def __init__(
        self,
        agent: Agent[TContext],
        parameters: dict | None = None,
        tool_description: str | None = None,
        **kwargs,
    ) -> None:

        # Avoid passing duplicate `description` to the FunctionTool dataclass.
        # Some call sites (e.g. SubAgentOrchestrator) pass `description` via kwargs
        # to override what the main agent sees, while we also compute a default
        # description here.
        # `tool_description` is the public description shown to the main LLM.
        # Keep a separate kwarg to avoid conflicting with FunctionTool's `description`.
        description = tool_description or self.default_description(agent.name)
        super().__init__(
            name=f"transfer_to_{agent.name}",
            parameters=parameters or self.default_parameters(),
            description=description,
            **kwargs,
        )

        # Optional provider override for this subagent. When set, the handoff
        # execution will use this chat provider id instead of the global/default.
        self.provider_id: str | None = None
        # Note: Must assign after super().__init__() to prevent parent class from overriding this attribute
        self.agent = agent

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
