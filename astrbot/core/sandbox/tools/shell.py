import json
from dataclasses import dataclass, field

from astrbot.api import FunctionTool
from astrbot.api.event import AstrMessageEvent

from ..sandbox_client import SandboxClient


@dataclass
class ExecuteShellTool(FunctionTool):
    name: str = "astrbot_execute_shell"
    description: str = "Execute a command in the shell."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute.",
                },
                "background": {
                    "type": "boolean",
                    "description": "Whether to run the command in the background.",
                    "default": False,
                },
                "env": {
                    "type": "object",
                    "description": "Optional environment variables to set for the file creation process.",
                    "additionalProperties": {"type": "string"},
                    "default": {},
                },
            },
            "required": ["command"],
        }
    )

    async def run(
        self,
        event: AstrMessageEvent,
        command: str,
        background: bool = False,
        env: dict = {},
    ):
        sb = await SandboxClient.get_booter(event.unified_msg_origin)
        try:
            result = await sb.shell.exec(command, background=background, env=env)
            return json.dumps(result)
        except Exception as e:
            return f"Error executing command: {str(e)}"
