"""
ExecuteShellTool - subprocess-based shell execution with per-session state.

Replaces previous plumbum-based implementation with a subprocess-based,
per-session state manager that tracks current working directory and
per-session environment variables.

Behavior:
- Each session has its own `cwd` and `env` stored in-memory.
- `cd` commands are interpreted and update the session `cwd`.
  Supports constructs like `cd /path && ls` or `cd rel/path; echo hi`.
- Foreground commands run to completion with a configurable timeout.
- Background commands spawn a subprocess and return immediately with the pid.
- Environment variables passed in `env` are merged with the session env.
- Returns JSON string describing result to match existing tool contract.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from dataclasses import dataclass, field
from typing import Any, cast

from astrbot.api import FunctionTool
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext

from .permissions import check_admin_permission


@dataclass
class ExecuteShellTool(FunctionTool):
    """
    Stateful shell execution tool using subprocess.

    Each agent session keeps its own working directory and environment mapping.
    """

    name: str = "astrbot_execute_shell"
    description: str = "Execute a command in the shell."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute in the current runtime shell (for example, cmd.exe on Windows). Equivalent to running 'cd {working_dir} && {your_command}'.",
                },
                "background": {
                    "type": "boolean",
                    "description": "Whether to run the command in the background.",
                    "default": False,
                },
                "env": {
                    "type": "object",
                    "description": "Optional environment variables to set for the command (merged with session env).",
                    "additionalProperties": {"type": "string"},
                    "default": {},
                },
            },
            "required": ["command"],
        }
    )

    is_local: bool = False
    # session_id -> {"cwd": str, "env": dict}
    _sessions: dict[str, dict[str, Any]] = field(
        default_factory=dict, init=False, repr=False
    )

    def _get_session_state(self, session_id: str) -> dict[str, Any]:
        """
        Initialize or return the per-session state.
        State contains:
          - cwd: current working directory for session
          - env: environment variables dict for session
        """
        if session_id not in self._sessions:
            # start from current process cwd and a copy of os.environ
            self._sessions[session_id] = {
                "cwd": os.getcwd(),
                "env": dict(os.environ),
            }
        return self._sessions[session_id]

    async def call(  # type: ignore[override]
        self, context: ContextWrapper[AstrAgentContext], **kwargs: Any
    ) -> ToolExecResult:
        """
        Execute a shell command for the session.

        Parameters are accepted via kwargs for compatibility with FunctionTool.call:
        - command (str): the shell command to execute
        - background (bool): whether to run in background
        - env (dict): environment variables to merge for this execution
        """
        # Cast the generic ContextWrapper to the concrete AstrAgentContext wrapper so
        # subsequent permission checks and attribute access use the expected type.
        astr_ctx = cast(ContextWrapper[AstrAgentContext], context)

        # Permission check (use the cast wrapper)
        if permission_error := check_admin_permission(astr_ctx, "Shell execution"):
            return permission_error

        # Extract parameters with defaults for backward compatibility
        command: str = kwargs.get("command", "")
        background: bool = bool(kwargs.get("background", False))
        env: dict | None = kwargs.get("env")

        # Resolve session id and session state (use the cast wrapper)
        session_id = astr_ctx.context.event.unified_msg_origin
        state = self._get_session_state(session_id)
        session_cwd = state["cwd"]
        session_env = state["env"].copy()

        # Merge provided env into execution env (do not mutate saved session env)
        if env:
            exec_env = session_env.copy()
            exec_env.update({k: str(v) for k, v in env.items()})
        else:
            exec_env = session_env

        # Determine timeout from config (fall back to 30) — use the cast wrapper's context
        config = astr_ctx.context.context.get_config(umo=session_id)
        try:
            timeout = int(
                config.get("provider_settings", {}).get("tool_call_timeout", 30)
            )
        except (ValueError, TypeError):
            timeout = 30

        # Single atomic try block for overall execution to satisfy anti-nested-try rule.
        try:
            # Quick handling for explicit `cd` constructs that should change session cwd.
            # We support leading cd followed by && or ;: e.g. "cd dir && ls", "cd dir; ls"
            cmd_str = command.strip()

            # Helper to split by shell '&&' or ';' while preserving remainder.
            remainder_cmd = ""
            cd_handled = False
            # Handle forms like: cd <path> && rest OR cd <path>; rest
            for sep in ("&&", ";"):
                if sep in cmd_str:
                    left, right = cmd_str.split(sep, 1)
                    left_strip = left.strip()
                    if left_strip.startswith("cd"):
                        remainder_cmd = right.strip()
                        cd_part = left_strip
                        cd_handled = True
                        break
            else:
                # No separator case, but single 'cd' command or just 'cd /path'
                if cmd_str.startswith("cd"):
                    cd_part = cmd_str
                    remainder_cmd = ""
                    cd_handled = True

            if cd_handled:
                # parse cd argument
                parts = shlex.split(cd_part)
                # cd with no args -> home
                if len(parts) == 1:
                    target = os.path.expanduser("~")
                else:
                    target_raw = parts[1]
                    # expand ~ and variables
                    target_raw = os.path.expanduser(target_raw)
                    target = (
                        target_raw
                        if os.path.isabs(target_raw)
                        else os.path.normpath(os.path.join(session_cwd, target_raw))
                    )

                if not os.path.exists(target) or not os.path.isdir(target):
                    result = {
                        "success": False,
                        "exit_code": -1,
                        "stdout": "",
                        "stderr": f"cd: no such directory: {target}",
                        "cwd": session_cwd,
                    }
                    return json.dumps(result)

                # Update session cwd permanently
                state["cwd"] = target
                session_cwd = target

                # If there is no remaining command, just return success and new cwd
                if not remainder_cmd:
                    result = {
                        "success": True,
                        "exit_code": 0,
                        "stdout": "",
                        "stderr": "",
                        "cwd": session_cwd,
                    }
                    return json.dumps(result)

                # Otherwise we'll execute the remainder using the updated cwd
                # Use the remainder command as the command to run below
                command_to_run = remainder_cmd
            else:
                command_to_run = cmd_str

            # Background execution: spawn process and return pid immediately.
            if background:
                # Start background process; do not wait. Use shell to support pipes/redirects.
                popen = subprocess.Popen(
                    ["/bin/sh", "-c", command_to_run],
                    cwd=session_cwd,
                    env=exec_env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                result = {
                    "success": True,
                    "background": True,
                    "pid": popen.pid,
                    "cwd": session_cwd,
                }
                return json.dumps(result)

            # Foreground execution: run to completion, capture output.
            completed = subprocess.run(
                ["/bin/sh", "-c", command_to_run],
                cwd=session_cwd,
                env=exec_env,
                timeout=timeout,
                capture_output=True,
                text=True,
            )

            exit_code = completed.returncode
            stdout = completed.stdout if completed.stdout is not None else ""
            stderr = completed.stderr if completed.stderr is not None else ""

            result = {
                "success": exit_code == 0,
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr,
                "cwd": session_cwd,
            }
            return json.dumps(result)

        except subprocess.TimeoutExpired as e:
            return json.dumps(
                {
                    "success": False,
                    "exit_code": -1,
                    "stdout": getattr(e, "output", "") or "",
                    "stderr": f"Command timed out after {timeout} seconds",
                    "cwd": session_cwd,
                }
            )
        except Exception as e:
            # Do not silently swallow errors; return an explicit failure payload.
            return json.dumps(
                {
                    "success": False,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": f"Error executing command: {e!s}",
                    "cwd": session_cwd,
                }
            )
