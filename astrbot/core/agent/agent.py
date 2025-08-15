from dataclasses import dataclass
from .tool import ToolSet

@dataclass
class Agent:
    name: str
    instructions: str | None = None
    tools: ToolSet | None = None
