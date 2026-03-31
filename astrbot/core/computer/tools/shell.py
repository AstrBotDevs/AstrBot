"""
ExecuteShellTool - shell execution via ComputerBooter system.

This module provides shell execution functionality by delegating to the
ComputerBooter system, which supports both local and remote execution modes.

Behavior:
- When is_local=True, uses LocalBooter with optional local_working_dir.
- When is_local=False, uses remote SandBoxBooter via get_booter.
- Shell execution is handled by the ComputerBooter's shell implementation.
- Returns JSON string describing result to match existing tool contract.
"""

from __future__ import annotations

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
    """
    Shell execution tool using ComputerBooter system.

    Delegates shell execution to ComputerBooter which provides a unified
    interface for both local and remote shell operations.
    """

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
                    "description": "Optional environment variables to set for the shell execution.",
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
        """
        Execute a shell command via ComputerBooter.

        Args:
            context: The agent context wrapper containing event and session info.
            command: The shell command to execute.
            background: Whether to run the command in background mode.
            env: Optional environment variables to set for the execution.

        Returns:
            ToolExecResult containing JSON string with execution result.
        """
        if permission_error := check_admin_permission(context, "Shell execution"):
            return permission_error

        if self.is_local:
            work_dir = context.context.event.get_extra("local_working_dir", "")
            sb = get_local_booter(work_dir=work_dir)
        else:
            sb = await get_booter(
                context.context.context,
                context.context.event.unified_msg_origin,
            )
        try:
            result = await sb.shell.exec(command, background=background, env=env)
            return json.dumps(result)
        except Exception as e:
            return json.dumps({
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Error executing command: {str(e)}",
            })
