import asyncio
import json
import subprocess
from dataclasses import dataclass, field

from astrbot.api import FunctionTool
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext

from ..computer_client import get_booter, get_local_booter
from .permissions import check_admin_permission


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
                    "description": "The shell command to execute in the current runtime shell (for example, cmd.exe on Windows). Equal to 'cd {working_dir} && {your_command}'.",
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

    is_local: bool = False

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        command: str,
        background: bool = False,
        env: dict = {},
    ) -> ToolExecResult:
        if permission_error := check_admin_permission(context, "Shell execution"):
            return permission_error

        if background:
            # Background commands still delegate to booter
            if self.is_local:
                sb = get_local_booter()
            else:
                sb = await get_booter(
                    context.context.context,
                    context.context.event.unified_msg_origin,
                )
            try:
                result = await sb.shell.exec(command, background=background, env=env)
                return json.dumps(result)
            except Exception as e:
                return f"Error executing background command: {str(e)}"

        # For foreground sync commands, handle locally with proper encoding
        try:
            loop = asyncio.get_event_loop()

            def run_subprocess():
                proc = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",  # Handle encoding errors gracefully
                )
                stdout, stderr = proc.communicate()
                return {
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": proc.returncode,
                }

            # Run in thread pool to avoid blocking event loop
            result = await loop.run_in_executor(None, run_subprocess)
            return json.dumps(result)

        except Exception as e:
            return json.dumps(
                {
                    "stdout": None,
                    "stderr": f"Error executing command: {str(e)}",
                    "exit_code": -1,
                }
            )
