import json
from dataclasses import dataclass, field
from typing import Any

from astrbot.api import FunctionTool
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.computer.computer_client import get_booter
from astrbot.core.tools.computer_tools.util import (
    check_admin_permission,
    is_local_runtime,
    workspace_root,
)
from astrbot.core.tools.registry import builtin_tool

_COMPUTER_RUNTIME_TOOL_CONFIG = {
    "provider_settings.computer_use_runtime": ("local", "sandbox"),
}


@builtin_tool(config=_COMPUTER_RUNTIME_TOOL_CONFIG)
@dataclass
class ExecuteShellTool(FunctionTool):
    name: str = "astrbot_execute_shell"
    description: str = (
        "Execute a command in the persistent shell. "
        "The shell session is maintained across calls within the same conversation, "
        "so ``cd``, ``export``, ``source``, and variable assignments persist naturally."
    )
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
                    "description": "Optional environment variables to set for the command execution.",
                    "additionalProperties": {"type": "string"},
                    "default": {},
                },
            },
            "required": ["command"],
        },
    )

    async def call(  # type: ignore[override]
        self,
        context: ContextWrapper[AstrAgentContext],
        command: str,
        background: bool = False,
        env: dict[str, Any] | None = None,
    ) -> ToolExecResult:
        if permission_error := check_admin_permission(context, "Shell execution"):
            return permission_error

        sb = await get_booter(
            context.context.context,
            context.context.event.unified_msg_origin,
        )
        try:
            # Ensure the workspace directory exists (useful for file operations)
            if is_local_runtime(context):
                workspace_root(
                    context.context.event.unified_msg_origin,
                ).mkdir(parents=True, exist_ok=True)

            resolved_env = dict(env or {})
            kwargs: dict[str, Any] = {
                "background": background,
                "env": resolved_env,
            }
            # Pass session_id for per-UMO persistent shell isolation
            if is_local_runtime(context):
                kwargs["session_id"] = context.context.event.unified_msg_origin

            result = await sb.shell.exec(command, **kwargs)
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return f"Error executing command: {e!s}"
