"""ComputerToolProvider — decoupled tool injection for computer-use runtimes.

Encapsulates all sandbox / local tool injection logic previously hardcoded in
``astr_main_agent.py``.  The main agent now calls
``provider.get_tools(ctx)`` / ``provider.get_system_prompt_addon(ctx)``
without knowing about specific tool classes.

Tool lists are delegated to booter subclasses via ``get_default_tools()``
and ``get_tools()`` (see ``booters/base.py``), so adding a new booter type
does not require changes here.
"""

from __future__ import annotations

import platform
from typing import TYPE_CHECKING

from astrbot.api import logger
from astrbot.core.tool_provider import ToolProviderContext

if TYPE_CHECKING:
    from astrbot.core.agent.tool import FunctionTool


# ---------------------------------------------------------------------------
# Lazy local-mode tool cache
# ---------------------------------------------------------------------------

_LOCAL_TOOLS_CACHE: list[FunctionTool] | None = None


def _get_local_tools() -> list[FunctionTool]:
    global _LOCAL_TOOLS_CACHE
    if _LOCAL_TOOLS_CACHE is None:
        from astrbot.core.computer.tools import ExecuteShellTool, LocalPythonTool

        _LOCAL_TOOLS_CACHE = [
            ExecuteShellTool(is_local=True),
            LocalPythonTool(),
        ]
    return list(_LOCAL_TOOLS_CACHE)


# ---------------------------------------------------------------------------
# System-prompt helpers
# ---------------------------------------------------------------------------

SANDBOX_MODE_PROMPT = (
    "You have access to a sandboxed environment and can execute "
    "shell commands and Python code securely."
)


def _build_local_mode_prompt() -> str:
    system_name = platform.system() or "Unknown"
    shell_hint = (
        "The runtime shell is Windows Command Prompt (cmd.exe). "
        "Use cmd-compatible commands and do not assume Unix commands like cat/ls/grep are available."
        if system_name.lower() == "windows"
        else "The runtime shell is Unix-like. Use POSIX-compatible shell commands."
    )
    return (
        "You have access to the host local environment and can execute shell commands and Python code. "
        f"Current operating system: {system_name}. "
        f"{shell_hint}"
    )


# ---------------------------------------------------------------------------
# ComputerToolProvider
# ---------------------------------------------------------------------------


class ComputerToolProvider:
    """Provides computer-use tools (local / sandbox) based on session context.

    Sandbox tool lists are delegated to booter subclasses so that each booter
    declares its own capabilities.  ``get_tools`` prefers the precise
    post-boot tool list from a running session; when the sandbox has not yet
    been booted it falls back to the conservative pre-boot default.
    """

    @staticmethod
    def get_all_tools() -> list[FunctionTool]:
        """Return ALL computer-use tools across all runtimes for registration.

        Creates **fresh instances** separate from the runtime caches so that
        setting ``active=False`` on them does not affect runtime behaviour.
        These registration-only instances let the WebUI display and assign
        tools without injecting them into actual LLM requests.

        At request time, ``get_tools(ctx)`` provides the real, active
        instances filtered by runtime.
        """
        from astrbot.core.computer.tools import (
            AnnotateExecutionTool,
            BrowserBatchExecTool,
            BrowserExecTool,
            CreateSkillCandidateTool,
            CreateSkillPayloadTool,
            EvaluateSkillCandidateTool,
            ExecuteShellTool,
            FileDownloadTool,
            FileUploadTool,
            GetExecutionHistoryTool,
            GetSkillPayloadTool,
            ListSkillCandidatesTool,
            ListSkillReleasesTool,
            LocalPythonTool,
            PromoteSkillCandidateTool,
            PythonTool,
            RollbackSkillReleaseTool,
            RunBrowserSkillTool,
            SyncSkillReleaseTool,
        )

        all_tools: list[FunctionTool] = [
            ExecuteShellTool(),
            PythonTool(),
            FileUploadTool(),
            FileDownloadTool(),
            LocalPythonTool(),
            BrowserExecTool(),
            BrowserBatchExecTool(),
            RunBrowserSkillTool(),
            GetExecutionHistoryTool(),
            AnnotateExecutionTool(),
            CreateSkillPayloadTool(),
            GetSkillPayloadTool(),
            CreateSkillCandidateTool(),
            ListSkillCandidatesTool(),
            EvaluateSkillCandidateTool(),
            PromoteSkillCandidateTool(),
            ListSkillReleasesTool(),
            RollbackSkillReleaseTool(),
            SyncSkillReleaseTool(),
        ]

        # De-duplicate by name and mark inactive so they are visible
        # in WebUI but never sent to the LLM via func_list.
        seen: set[str] = set()
        result: list[FunctionTool] = []
        for tool in all_tools:
            if tool.name not in seen:
                tool.active = False
                result.append(tool)
                seen.add(tool.name)
        return result

    def get_tools(self, ctx: ToolProviderContext) -> list[FunctionTool]:
        runtime = ctx.computer_use_runtime
        if runtime == "none":
            return []

        if runtime == "local":
            return _get_local_tools()

        if runtime == "sandbox":
            return self._sandbox_tools(ctx)

        logger.warning("[ComputerToolProvider] Unknown runtime: %s", runtime)
        return []

    def get_system_prompt_addon(self, ctx: ToolProviderContext) -> str:
        runtime = ctx.computer_use_runtime
        if runtime == "none":
            return ""

        if runtime == "local":
            return f"\n{_build_local_mode_prompt()}\n"

        if runtime == "sandbox":
            return self._sandbox_prompt_addon(ctx)

        return ""

    # -- sandbox helpers ----------------------------------------------------

    def _sandbox_tools(self, ctx: ToolProviderContext) -> list[FunctionTool]:
        """Collect tools for sandbox mode.

        Always returns the full (pre-boot default) tool set declared by the
        booter class, regardless of whether the sandbox is already booted.

        This ensures the tool schema sent to the LLM is stable across the
        entire conversation lifecycle (pre-boot and post-boot produce the
        same set), enabling LLM prefix cache hits.  Tools whose underlying
        capability is unavailable at runtime are rejected by the executor
        with a descriptive error message instead of being omitted from the
        schema.
        """
        from astrbot.core.computer.computer_client import get_default_sandbox_tools

        booter_type = ctx.sandbox_cfg.get("booter", "shipyard_neo")

        # Validate shipyard (non-neo) config
        if booter_type == "shipyard":
            ep = ctx.sandbox_cfg.get("shipyard_endpoint", "")
            at = ctx.sandbox_cfg.get("shipyard_access_token", "")
            if not ep or not at:
                logger.error("Shipyard sandbox configuration is incomplete.")
                return []

        # Always return the full tool set for schema stability
        return get_default_sandbox_tools(ctx.sandbox_cfg)

    def _sandbox_prompt_addon(self, ctx: ToolProviderContext) -> str:
        """Build system-prompt addon for sandbox mode."""
        from astrbot.core.computer.computer_client import get_sandbox_prompt_parts

        parts = get_sandbox_prompt_parts(ctx.sandbox_cfg)
        parts.append(f"\n{SANDBOX_MODE_PROMPT}\n")
        return "".join(parts)


def get_all_tools() -> list[FunctionTool]:
    """Module-level entry point for ``FunctionToolManager.register_internal_tools()``.

    Delegates to ``ComputerToolProvider.get_all_tools()`` which collects
    tools from all runtimes (local, sandbox, browser, neo).
    """
    return ComputerToolProvider.get_all_tools()
