import json
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
    description: str = (
        "Execute a command in the shell. "
        "In local_sandboxed runtime, writes are restricted to ~/.astrbot/workspace/<session>."
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute.",
                },
                "cwd": {
                    "type": "string",
                    "description": "Optional working directory for command execution.",
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
        cwd: str | None = None,
        background: bool = False,
        env: dict = {},
    ) -> ToolExecResult:
        if permission_error := check_admin_permission(context, "Shell execution"):
            return permission_error

        event = context.context.event
        cfg = context.context.context.get_config(umo=event.unified_msg_origin)
        runtime = str(
            cfg.get("provider_settings", {}).get("computer_use_runtime", "local")
        )

        if self.is_local:
            sb = get_local_booter(
                event.unified_msg_origin,
                sandboxed=runtime == "local_sandboxed",
            )
        else:
            sb = await get_booter(
                context.context.context,
                event.unified_msg_origin,
            )
        try:
            result = await sb.shell.exec(
                command,
                cwd=cwd,
                background=background,
                env=env,
            )
            return json.dumps(result)
        except Exception as e:
            return f"Error executing command: {str(e)}"
