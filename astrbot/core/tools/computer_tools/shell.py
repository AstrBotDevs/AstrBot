import json
from dataclasses import dataclass, field

from astrbot.api import FunctionTool
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.computer.computer_client import get_booter

from ..registry import builtin_tool
from .util import check_admin_permission, is_local_runtime, workspace_root

_COMPUTER_RUNTIME_TOOL_CONFIG = {
    "provider_settings.computer_use_runtime": ("local", "sandbox"),
}


@builtin_tool(config=_COMPUTER_RUNTIME_TOOL_CONFIG)
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

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        command: str,
        background: bool = False,
        env: dict = {},
    ) -> ToolExecResult:
        if permission_error := check_admin_permission(context, "Shell execution"):
            return permission_error

        sb = await get_booter(
            context.context.context,
            context.context.event.unified_msg_origin,
        )
        try:
            cwd: str | None = None
            if is_local_runtime(context):
                current_workspace_root = workspace_root(
                    context.context.event.unified_msg_origin
                )
                current_workspace_root.mkdir(parents=True, exist_ok=True)
                cwd = str(current_workspace_root)

            result = await sb.shell.exec(
                command,
                cwd=cwd,
                background=background,
                env=env,
            )
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return f"Error executing command: {str(e)}"
