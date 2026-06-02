import json
import os
import shlex
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from astrbot.api import FunctionTool
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.computer.computer_client import get_booter
from astrbot.core.utils.astrbot_path import get_astrbot_system_tmp_path

from ..registry import builtin_tool
from .util import check_admin_permission, is_local_runtime, workspace_root

_COMPUTER_RUNTIME_TOOL_CONFIG = {
    "provider_settings.computer_use_runtime": ("local", "sandbox"),
}


def _quote_redirect_path(path: str, *, local_runtime: bool) -> str:
    if local_runtime and os.name == "nt":
        escaped_path = path.replace('"', '""')
    else:
        escaped_path = path.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped_path}"'


def _build_background_output_path(*, local_runtime: bool) -> str:
    file_name = f"astrbot_shell_stdout_{uuid.uuid4().hex[:8]}.log"
    if local_runtime:
        output_dir = Path(get_astrbot_system_tmp_path()) / "shell"
        output_dir.mkdir(parents=True, exist_ok=True)
        return str((output_dir / file_name).resolve(strict=False))
    return f"/tmp/{file_name}"


def _redirect_background_stdout_command(
    command: str,
    *,
    output_path: str,
    local_runtime: bool,
) -> str:
    return f"({command}) > {_quote_redirect_path(output_path, local_runtime=local_runtime)} 2>&1"


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
                    "description": "Run the command in the background. Use the file read tool to read the output later. For long running commands, using this option.",
                    "default": False,
                },
                "timeout": {
                    "type": "integer",
                    "description": "Optional timeout in seconds for the command execution.",
                    "default": 300,
                },
                "env": {
                    "type": "object",
                    "description": "Optional environment variables to set.",
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
        timeout: int | None = 300,
        env: dict[str, Any] | None = None,
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

            env = dict(env or {})
            effective_background = background and not _is_self_detached_command(command)

            stdout_file: str | None = None
            if effective_background:
                local_runtime = is_local_runtime(context)
                stdout_file = _build_background_output_path(
                    local_runtime=local_runtime,
                )
                command = _redirect_background_stdout_command(
                    command,
                    output_path=stdout_file,
                    local_runtime=local_runtime,
                )

            result = await sb.shell.exec(
                command,
                cwd=cwd,
                background=effective_background,
                env=env,
                timeout=timeout or 300,
            )
            if stdout_file:
                result["stdout"] = (
                    f"Command is running in the background. stdout/stderr is being "
                    f"written to `{stdout_file}`. Use astrbot_file_read_tool to read it."
                )
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            detail = str(e) or type(e).__name__
            return f"Error executing command: {detail}"


def _is_self_detached_command(command: str) -> bool:
    lex = shlex.shlex(command, posix=False)
    lex.whitespace_split = True
    lex.commenters = ""
    try:
        tokens = list(lex)
    except ValueError:
        return False
    comment_index = next(
        (index for index, token in enumerate(tokens) if token.startswith("#")),
        None,
    )
    if comment_index is not None:
        tokens = tokens[:comment_index]
    if not tokens:
        return False

    first = tokens[0].lower()
    if first in {"nohup", "setsid", "disown", "start", "start-process"}:
        return True
    return tokens[-1] == "&"
