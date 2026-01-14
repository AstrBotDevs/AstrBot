import json
from dataclasses import dataclass, field

from astrbot.api import FunctionTool
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext

from ..sandbox_client import get_booter


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
                    "description": "The bash command to execute. Equal to 'cd {working_dir} && {your_command}'.",
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

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        command: str,
        background: bool = False,
        env: dict = {},
    ) -> ToolExecResult:
        sb = await get_booter(
            context.context.context,
            context.context.event.unified_msg_origin,
        )
        try:
            result = await sb.shell.exec(command, background=background, env=env)
            return json.dumps(result)
        except Exception as e:
            return f"Error executing command: {str(e)}"
