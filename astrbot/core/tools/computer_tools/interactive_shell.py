"""
Interactive shell tools for AstrBot Agent.

Provides tools for LLM to interact with long-running shell processes
that require multi-turn bidirectional communication.

Tools:
- astrbot_inta_shell_start: Start an interactive shell session
- astrbot_inta_shell_send: Send input to a session
- astrbot_inta_shell_read: Read output from a session
- astrbot_inta_shell_stop: Stop a session
- astrbot_inta_shell_list: List active sessions
"""

from __future__ import annotations

import asyncio
import json
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


def _session_to_dict(session) -> dict[str, Any]:
    """Convert InteractiveSession to a JSON-serializable dict."""
    return {
        "session_id": session.session_id,
        "command": session.command,
        "pid": session.pid,
        "state": session.state.value,
        "exit_code": session.exit_code,
        "error_message": session.error_message,
        "created_at": session.created_at,
        "last_activity": session.last_activity,
    }


# =============================================================================
# Tool 1: astrbot_inta_shell_start
# =============================================================================


@builtin_tool(config=_COMPUTER_RUNTIME_TOOL_CONFIG)
@dataclass
class InteractiveShellStartTool(FunctionTool):
    name: str = "astrbot_inta_shell_start"
    description: str = (
        "Start an interactive shell session with a long-running command. "
        "Use this for programs that require multi-turn interaction "
        "(e.g., npm init, python REPL, git add -p, interactive installers). "
        "Returns a session_id that must be used for subsequent send/read/stop operations. "
        "Note: This tool does NOT support full TTY programs like vim or nano."
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": (
                        "The interactive command to start. "
                        "For programs with non-interactive alternatives, prefer those instead "
                        "(e.g., use 'npm init -y' instead of 'npm init' when possible)."
                    ),
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
        env: dict[str, Any] | None = None,
    ) -> ToolExecResult:
        if permission_error := check_admin_permission(
            context, "Interactive shell start"
        ):
            return permission_error

        sb = await get_booter(
            context.context.context,
            context.context.event.unified_msg_origin,
        )

        ish = sb.interactive_shell
        if ish is None:
            return json.dumps(
                {
                    "success": False,
                    "error": "Interactive shell is not supported by the current runtime.",
                },
                ensure_ascii=False,
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
            session = await ish.start(command, cwd=cwd, env=env)

            # Give the process a moment to produce initial output
            await asyncio.sleep(0.3)
            initial_output = await ish.read(session.session_id, timeout=2.0)

            result = {
                "success": True,
                "session": _session_to_dict(session),
                "initial_output": initial_output,
                "hint": (
                    "Session started. Use astrbot_inta_shell_send/astrbot_inta_shell_read "
                    "to interact, or astrbot_inta_shell_stop to terminate."
                ),
            }
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps(
                {
                    "success": False,
                    "error": f"Failed to start interactive shell: {e}",
                },
                ensure_ascii=False,
            )


# =============================================================================
# Tool 2: astrbot_inta_shell_send
# =============================================================================


@builtin_tool(config=_COMPUTER_RUNTIME_TOOL_CONFIG)
@dataclass
class InteractiveShellSendTool(FunctionTool):
    name: str = "astrbot_inta_shell_send"
    description: str = (
        "Send input to an active interactive shell session. "
        "A newline is automatically appended if not present. "
        "Use this to respond to prompts from interactive programs."
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "The session ID returned by astrbot_inta_shell_start.",
                },
                "input": {
                    "type": "string",
                    "description": (
                        "The text to send to the interactive program. "
                        "For prompts asking for confirmation, common responses are: "
                        "'y' (yes), 'n' (no), '' (accept default/empty), "
                        "or specific values like package names, versions, etc."
                    ),
                },
                "send_eof": {
                    "type": "boolean",
                    "description": (
                        "If true, close stdin after sending (signals end-of-input). "
                        "Useful when the program expects input to end before processing."
                    ),
                    "default": False,
                },
            },
            "required": ["session_id", "input"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        session_id: str,
        input: str,
        send_eof: bool = False,
    ) -> ToolExecResult:
        if permission_error := check_admin_permission(
            context, "Interactive shell send"
        ):
            return permission_error

        sb = await get_booter(
            context.context.context,
            context.context.event.unified_msg_origin,
        )

        ish = sb.interactive_shell
        if ish is None:
            return json.dumps(
                {"success": False, "error": "Interactive shell not available."},
                ensure_ascii=False,
            )

        try:
            await ish.send(session_id, input, send_eof=send_eof)
            return json.dumps(
                {"success": True, "message": "Input sent successfully."},
                ensure_ascii=False,
            )
        except ValueError as e:
            return json.dumps(
                {"success": False, "error": f"Session not found: {e}"},
                ensure_ascii=False,
            )
        except Exception as e:
            return json.dumps(
                {"success": False, "error": f"Failed to send input: {e}"},
                ensure_ascii=False,
            )


# =============================================================================
# Tool 3: astrbot_inta_shell_read
# =============================================================================


@builtin_tool(config=_COMPUTER_RUNTIME_TOOL_CONFIG)
@dataclass
class InteractiveShellReadTool(FunctionTool):
    name: str = "astrbot_inta_shell_read"
    description: str = (
        "Read output from an active interactive shell session. "
        "Waits up to the specified timeout for output to become available. "
        "If the program is waiting for input, the output will typically show the prompt."
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "The session ID returned by astrbot_inta_shell_start.",
                },
                "timeout": {
                    "type": "number",
                    "description": (
                        "Maximum seconds to wait for output. "
                        "Increase this for slow programs. "
                        "Decrease for quick-response programs."
                    ),
                    "default": 5.0,
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters to read. Use to limit large outputs.",
                    "default": 4096,
                },
            },
            "required": ["session_id"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        session_id: str,
        timeout: float = 5.0,
        max_chars: int = 4096,
    ) -> ToolExecResult:
        if permission_error := check_admin_permission(
            context, "Interactive shell read"
        ):
            return permission_error

        sb = await get_booter(
            context.context.context,
            context.context.event.unified_msg_origin,
        )

        ish = sb.interactive_shell
        if ish is None:
            return json.dumps(
                {"success": False, "error": "Interactive shell not available."},
                ensure_ascii=False,
            )

        try:
            output = await ish.read(session_id, timeout=timeout, max_chars=max_chars)

            # Also get current session state
            session = await ish.get_session(session_id)
            state_info = _session_to_dict(session) if session else None

            result = {
                "success": True,
                "output": output,
                "session": state_info,
                "hint": (
                    "Analyze the output to determine if the program is: "
                    "(1) waiting for input (shows a prompt), "
                    "(2) still processing (no prompt yet), or "
                    "(3) has finished (exited)."
                ),
            }
            return json.dumps(result, ensure_ascii=False)
        except ValueError as e:
            return json.dumps(
                {"success": False, "error": f"Session not found: {e}"},
                ensure_ascii=False,
            )
        except Exception as e:
            return json.dumps(
                {"success": False, "error": f"Failed to read output: {e}"},
                ensure_ascii=False,
            )


# =============================================================================
# Tool 4: astrbot_inta_shell_stop
# =============================================================================


@builtin_tool(config=_COMPUTER_RUNTIME_TOOL_CONFIG)
@dataclass
class InteractiveShellStopTool(FunctionTool):
    name: str = "astrbot_inta_shell_stop"
    description: str = (
        "Terminate an interactive shell session. "
        "Always call this when done with a session to free resources. "
        "By default, sends Ctrl+C first for graceful shutdown, then kills if needed."
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "The session ID to terminate.",
                },
                "force": {
                    "type": "boolean",
                    "description": (
                        "If true, kill immediately without sending Ctrl+C first. "
                        "Use only when the session is completely unresponsive."
                    ),
                    "default": False,
                },
            },
            "required": ["session_id"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        session_id: str,
        force: bool = False,
    ) -> ToolExecResult:
        if permission_error := check_admin_permission(
            context, "Interactive shell stop"
        ):
            return permission_error

        sb = await get_booter(
            context.context.context,
            context.context.event.unified_msg_origin,
        )

        ish = sb.interactive_shell
        if ish is None:
            return json.dumps(
                {"success": False, "error": "Interactive shell not available."},
                ensure_ascii=False,
            )

        try:
            session = await ish.terminate(session_id, graceful=not force)
            return json.dumps(
                {
                    "success": True,
                    "session": _session_to_dict(session),
                    "message": "Session terminated.",
                },
                ensure_ascii=False,
            )
        except ValueError as e:
            return json.dumps(
                {"success": False, "error": f"Session not found: {e}"},
                ensure_ascii=False,
            )
        except Exception as e:
            return json.dumps(
                {"success": False, "error": f"Failed to terminate session: {e}"},
                ensure_ascii=False,
            )


# =============================================================================
# Tool 5: astrbot_inta_shell_list
# =============================================================================


@builtin_tool(config=_COMPUTER_RUNTIME_TOOL_CONFIG)
@dataclass
class InteractiveShellListTool(FunctionTool):
    name: str = "astrbot_inta_shell_list"
    description: str = (
        "List all active interactive shell sessions. "
        "Use this to check which sessions are still running or need cleanup."
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {},
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
    ) -> ToolExecResult:
        if permission_error := check_admin_permission(
            context, "Interactive shell list"
        ):
            return permission_error

        sb = await get_booter(
            context.context.context,
            context.context.event.unified_msg_origin,
        )

        ish = sb.interactive_shell
        if ish is None:
            return json.dumps(
                {
                    "success": True,
                    "sessions": [],
                    "message": "Interactive shell is not available in this runtime.",
                },
                ensure_ascii=False,
            )

        try:
            sessions = await ish.list_sessions()
            return json.dumps(
                {
                    "success": True,
                    "sessions": [_session_to_dict(s) for s in sessions],
                    "count": len(sessions),
                },
                ensure_ascii=False,
            )
        except Exception as e:
            return json.dumps(
                {"success": False, "error": f"Failed to list sessions: {e}"},
                ensure_ascii=False,
            )
