from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from plumbum import local
from plumbum.commands.processes import ProcessExecutionError

from astrbot.api import FunctionTool
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext

from .permissions import check_admin_permission


@dataclass
class ExecuteShellTool(FunctionTool):
    """Stateful shell execution tool based on plumbum.

    Each session maintains its own shell instance, ensuring state isolation
    across different sessions (such as working directory, environment variables, etc.).
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
                    "description": "Optional environment variables to set for the file creation process.",
                    "additionalProperties": {"type": "string"},
                    "default": {},
                },
            },
            "required": ["command"],
        }
    )

    is_local: bool = False
    _session_shells: dict[str, Any] = field(
        default_factory=dict, init=False, repr=False
    )

    def _get_session_shell(self, session_id: str) -> Any:
        """Get or create a shell instance for a specific session.

        Args:
            session_id: The unique session identifier.

        Returns:
            plumbum shell instance for this session.
        """
        import os

        if session_id not in self._session_shells:
            self._session_shells[session_id] = local.cwd(os.getcwd())
        return self._session_shells[session_id]

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        command: str,
        background: bool = False,
        env: dict = {},
    ) -> ToolExecResult:
        if permission_error := check_admin_permission(context, "Shell execution"):
            return permission_error

        try:
            # Get session ID for per-session shell isolation
            session_id = context.context.event.unified_msg_origin
            shell = self._get_session_shell(session_id)

            config = context.context.context.get_config(umo=session_id)
            try:
                timeout = int(
                    config.get("provider_settings", {}).get("tool_call_timeout", 30)
                )
            except (ValueError, TypeError):
                timeout = 30

            # Merge environment variables
            if env:
                full_env = shell.env.copy()
                full_env.update(env)
            else:
                full_env = None

            if background:
                # Background execution: use & to run in background, no waiting
                cmd_line = f"{command} &"
                if full_env:
                    _, stdout, stderr = shell.run(
                        ["/bin/sh", "-c", cmd_line],
                        env=full_env,
                        timeout=timeout,
                    )
                else:
                    _, stdout, stderr = shell.run(
                        ["/bin/sh", "-c", cmd_line],
                        timeout=timeout,
                    )
                result = {
                    "success": True,
                    "background": True,
                    "stdout": stdout,
                    "stderr": stderr,
                }
            else:
                # Foreground execution: wait for command completion
                try:
                    if full_env:
                        exit_code, stdout, stderr = shell.run(
                            ["/bin/sh", "-c", command],
                            env=full_env,
                            timeout=timeout,
                        )
                    else:
                        exit_code, stdout, stderr = shell.run(
                            ["/bin/sh", "-c", command],
                            timeout=timeout,
                        )
                    result = {
                        "success": exit_code == 0,
                        "exit_code": exit_code,
                        "stdout": stdout,
                        "stderr": stderr,
                    }
                except ProcessExecutionError as e:
                    result = {
                        "success": False,
                        "exit_code": e.exit_code,
                        "stdout": e.stdout,
                        "stderr": e.stderr,
                    }
                except Exception as e:
                    result = {
                        "success": False,
                        "exit_code": -1,
                        "stdout": "",
                        "stderr": str(e),
                    }

            return json.dumps(result)

        except Exception as e:
            return f"Error executing command: {e!s}"
