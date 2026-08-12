import json
import os
import shlex
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic
from typing import Any

from astrbot.api import FunctionTool
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.computer.booters.local import LocalShellComponent
from astrbot.core.computer.computer_client import get_booter
from astrbot.core.utils.astrbot_path import get_astrbot_system_tmp_path

from ..registry import builtin_tool
from .util import (
    check_admin_permission,
    is_local_runtime,
    workspace_root_for_context,
)

_COMPUTER_RUNTIME_TOOL_CONFIG = {
    "provider_settings.computer_use_runtime": ("local", "sandbox"),
}
_LOCAL_RUNTIME_TOOL_CONFIG = {
    "provider_settings.computer_use_runtime": "local",
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
        timeout: int | None = None,
        env: dict[str, Any] | None = None,
        yield_time_ms: int = 10_000,
    ) -> ToolExecResult:
        if permission_error := check_admin_permission(context, "Shell execution"):
            return permission_error

        sb = await get_booter(
            context.context.context,
            context.context.event.unified_msg_origin,
        )
        try:
            cwd: str | None = None
            local_runtime = is_local_runtime(context)
            if local_runtime:
                current_workspace_root = await workspace_root_for_context(context)
                current_workspace_root.mkdir(parents=True, exist_ok=True)
                cwd = str(current_workspace_root)

            env = dict(env or {})
            if local_runtime:
                if not isinstance(sb.shell, LocalShellComponent):
                    return (
                        "Error executing command: local shell component is unavailable."
                    )
                creator_id = context.context.event.get_sender_id()
                if not creator_id:
                    return "Error executing command: sender identity is unavailable."
                started_at = monotonic()
                result = await sb.shell.exec_managed(
                    command,
                    owner_id=context.context.event.unified_msg_origin,
                    creator_id=creator_id,
                    creator_is_admin=context.context.event.role == "admin",
                    sandboxed=False,
                    cwd=cwd,
                    env=env,
                    timeout=timeout,
                    yield_time_ms=0 if background else yield_time_ms,
                )
                elapsed_seconds = monotonic() - started_at
                if result.get("session_closed") and result.get("status") in {
                    "completed",
                    "failed",
                }:
                    message = (
                        f"Command completed with exit code {result['exit_code']} "
                        f"(wall time: {elapsed_seconds:.2f}s)."
                    )
                    output = f"{result['stdout']}{result['stderr']}"
                    return f"{message}\nOutput:\n{output}"
                return json.dumps(result, ensure_ascii=False)

            effective_background = background and not _is_self_detached_command(command)

            stdout_file: str | None = None
            if effective_background:
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


@dataclass
class LocalExecuteShellTool(ExecuteShellTool):
    """Local shell tool that automatically yields long-running commands."""

    description: str = (
        "Execute a command in the shell. If it is still running after "
        "yield_time_ms, the tool returns a managed shell session ID."
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute in the current workspace.",
                },
                "yield_time_ms": {
                    "type": "integer",
                    "description": "Maximum time to wait for completion before returning a managed shell session. This does not stop the process.",
                    "default": 10000,
                    "minimum": 0,
                    "maximum": 30000,
                },
                "timeout": {
                    "type": "integer",
                    "description": "Optional hard process lifetime in seconds. Omit it to allow the managed session to keep running.",
                    "minimum": 1,
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
        yield_time_ms: int = 10_000,
        timeout: int | None = None,
        env: dict[str, Any] | None = None,
    ) -> ToolExecResult:
        """Execute a local command without a background-mode argument.

        Args:
            context: Current agent tool context.
            command: Shell command to execute.
            yield_time_ms: Maximum initial wait before returning a session.
            timeout: Optional hard process lifetime.
            env: Additional environment variables.

        Returns:
            JSON command result or a user-facing error.
        """
        return await super().call(
            context,
            command,
            background=False,
            timeout=timeout,
            env=env,
            yield_time_ms=yield_time_ms,
        )


@builtin_tool(config=_LOCAL_RUNTIME_TOOL_CONFIG)
@dataclass
class ShellSessionTool(FunctionTool):
    """Manage shell sessions created by the local shell execution tool."""

    name: str = "astrbot_shell_session"
    description: str = (
        "List, poll, write raw text or complete lines to, interrupt, or terminate "
        "managed shell sessions. "
        "Sessions are isolated to the current conversation and sender. "
        "Administrators can manage all sessions in the conversation."
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "list",
                        "poll",
                        "write",
                        "write_line",
                        "interrupt",
                        "terminate",
                    ],
                    "description": "Session operation to perform.",
                },
                "session_id": {
                    "type": "string",
                    "description": "Required for every action except list.",
                },
                "chars": {
                    "type": "string",
                    "description": (
                        "Text sent verbatim by write. For write_line, provide one "
                        "line without a line ending; a real LF is appended automatically."
                    ),
                    "default": "",
                },
                "cursor": {
                    "type": "integer",
                    "description": "Optional byte cursor for poll. Omit to continue from the last returned output.",
                    "minimum": 0,
                },
                "yield_time_ms": {
                    "type": "integer",
                    "description": "Maximum time poll or interrupt waits for output or exit.",
                    "default": 5000,
                    "minimum": 0,
                    "maximum": 30000,
                },
                "max_output_chars": {
                    "type": "integer",
                    "description": "Maximum output bytes returned by poll, interrupt, or terminate.",
                    "default": 10000,
                    "minimum": 1,
                    "maximum": 100000,
                },
            },
            "required": ["action"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        action: str,
        session_id: str | None = None,
        chars: str = "",
        cursor: int | None = None,
        yield_time_ms: int = 5_000,
        max_output_chars: int = 10_000,
    ) -> ToolExecResult:
        """Perform an identity-scoped local shell session operation.

        Args:
            context: Current agent tool context.
            action: Session operation to perform.
            session_id: Managed session identifier, except for list.
            chars: Text written verbatim for write or with a trailing LF for write_line.
            cursor: Optional output byte cursor.
            yield_time_ms: Maximum wait for output or process exit.
            max_output_chars: Maximum output bytes to return.

        Returns:
            JSON session operation result or a user-facing error.
        """
        if permission_error := check_admin_permission(
            context,
            "Shell session management",
        ):
            return permission_error
        if not is_local_runtime(context):
            return "Error managing shell session: only local runtime is supported."

        try:
            sb = await get_booter(
                context.context.context,
                context.context.event.unified_msg_origin,
            )
            if not isinstance(sb.shell, LocalShellComponent):
                return "Error managing shell session: local shell component is unavailable."

            owner_id = context.context.event.unified_msg_origin
            requester_id = context.context.event.get_sender_id()
            if not requester_id:
                return "Error managing shell session: sender identity is unavailable."
            requester_is_admin = context.context.event.role == "admin"
            if action == "list":
                result = await sb.shell.list_sessions(
                    owner_id=owner_id,
                    requester_id=requester_id,
                    requester_is_admin=requester_is_admin,
                )
            else:
                if not session_id:
                    return (
                        "Error managing shell session: session_id is required "
                        f"when action={action}."
                    )
                if action == "poll":
                    result = await sb.shell.poll_session(
                        owner_id=owner_id,
                        requester_id=requester_id,
                        requester_is_admin=requester_is_admin,
                        session_id=session_id,
                        cursor=cursor,
                        yield_time_ms=yield_time_ms,
                        max_output_chars=max_output_chars,
                    )
                elif action in {"write", "write_line"}:
                    result = await sb.shell.write_session(
                        owner_id=owner_id,
                        requester_id=requester_id,
                        requester_is_admin=requester_is_admin,
                        session_id=session_id,
                        chars=f"{chars}\n" if action == "write_line" else chars,
                    )
                elif action == "interrupt":
                    result = await sb.shell.interrupt_session(
                        owner_id=owner_id,
                        requester_id=requester_id,
                        requester_is_admin=requester_is_admin,
                        session_id=session_id,
                        yield_time_ms=yield_time_ms,
                        max_output_chars=max_output_chars,
                    )
                elif action == "terminate":
                    result = await sb.shell.terminate_session(
                        owner_id=owner_id,
                        requester_id=requester_id,
                        requester_is_admin=requester_is_admin,
                        session_id=session_id,
                        max_output_chars=max_output_chars,
                    )
                else:
                    return f"Error managing shell session: unsupported action {action}."
            return json.dumps(result, ensure_ascii=False)
        except Exception as exc:
            detail = str(exc) or type(exc).__name__
            return f"Error managing shell session: {detail}"


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
