import json
import shlex
from dataclasses import dataclass, field
from typing import Any

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
_EXPLICIT_BACKGROUND_LAUNCHERS = {"nohup", "setsid", "disown", "start", "start-process"}


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
                    "description": "Whether to run the command in the background. Do not append shell background operators such as `&`; pass the foreground command and use this flag instead.",
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
            prepared_command, effective_background = _prepare_shell_background(
                command,
                background,
            )
            if background and not prepared_command.strip():
                return json.dumps(
                    {
                        "success": False,
                        "stdout": "",
                        "stderr": "error: empty shell command after removing background operator.",
                        "exit_code": 2,
                    },
                    ensure_ascii=False,
                )
            result = await sb.shell.exec(
                prepared_command,
                cwd=cwd,
                background=effective_background,
                env=env,
            )
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            detail = str(e) or type(e).__name__
            return f"Error executing command: {detail}"


def _prepare_shell_background(command: str, background: bool) -> tuple[str, bool]:
    if not background:
        return command, False

    tokens, has_explicit_launcher, has_trailing_amp = _classify_background(command)
    if has_explicit_launcher:
        return command, False
    if has_trailing_amp:
        return " ".join(tokens[:-1]), True
    return command, True


def _classify_background(command: str) -> tuple[list[str], bool, bool]:
    tokens = _command_tokens_before_comment(command)
    if not tokens:
        return tokens, False, False

    has_explicit_launcher = tokens[0].lower() in _EXPLICIT_BACKGROUND_LAUNCHERS
    has_trailing_amp = tokens[-1] == "&"
    return tokens, has_explicit_launcher, has_trailing_amp


def _is_self_detached_command(command: str) -> bool:
    _, has_explicit_launcher, has_trailing_amp = _classify_background(command)
    return has_explicit_launcher or has_trailing_amp


def _command_tokens_before_comment(command: str) -> list[str]:
    lex = shlex.shlex(command, posix=False)
    lex.whitespace_split = True
    lex.commenters = ""
    try:
        tokens = list(lex)
    except ValueError:
        return []
    comment_index = next(
        (index for index, token in enumerate(tokens) if token.startswith("#")),
        None,
    )
    if comment_index is not None:
        tokens = tokens[:comment_index]
    return tokens
