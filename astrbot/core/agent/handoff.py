from .tool import FunctionTool


class Handoff(FunctionTool):
    """Handoff tool for delegating tasks to another agent."""

    def __init__(
        self, name: str, description: str | None = None, parameters: dict | None = None
    ):
        super().__init__(
            name=name,
            parameters=parameters or self.default_parameters(),
            description=description or self.default_description(name),
        )

    def default_parameters(self) -> dict:
        return {
            "input": {
                "type": "string",
                "description": "The input to be handed off to another agent. This should be a clear and concise request or task.",
            },
        }

    def default_description(self, agent_name: str | None) -> str:
        agent_name = agent_name or "another"
        return f"Delegate tasks to {self.name} agent to handle the request."
