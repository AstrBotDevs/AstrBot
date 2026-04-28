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
    if _uses_explicit_background_launcher(command):
        return command, False

    stripped_command = _strip_plain_trailing_background_operator(command)
    if stripped_command is not None:
        return stripped_command, True
    return command, True


def _uses_explicit_background_launcher(command: str) -> bool:
    tokens = _command_tokens_before_comment(command)
    if not tokens:
        return False
    return tokens[0].lower() in {"nohup", "setsid", "disown", "start", "start-process"}


def _is_self_detached_command(command: str) -> bool:
    tokens = _command_tokens_before_comment(command)
    if not tokens:
        return False

    if _uses_explicit_background_launcher(command):
        return True
    return tokens[-1] == "&"


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


def _strip_plain_trailing_background_operator(command: str) -> str | None:
    effective_end = _command_effective_end(command)
    tail = command[:effective_end].rstrip()
    if not tail.endswith("&"):
        return None
    if not _is_unquoted_char_at(tail, len(tail) - 1):
        return None

    stripped = tail[:-1].rstrip()
    return stripped if stripped != tail else None


def _command_effective_end(command: str) -> int:
    quote: str | None = None
    escaped = False
    for index, char in enumerate(command):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote != "'":
            escaped = True
            continue
        if char in {"'", '"'}:
            if quote is None:
                quote = char
            elif quote == char:
                quote = None
            continue
        if (
            char == "#"
            and quote is None
            and (index == 0 or command[index - 1].isspace())
        ):
            return index
    return len(command)


def _is_unquoted_char_at(command: str, target_index: int) -> bool:
    quote: str | None = None
    escaped = False
    for index, char in enumerate(command):
        if index == target_index:
            return quote is None and not escaped
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote != "'":
            escaped = True
            continue
        if char in {"'", '"'}:
            if quote is None:
                quote = char
            elif quote == char:
                quote = None
    return False
