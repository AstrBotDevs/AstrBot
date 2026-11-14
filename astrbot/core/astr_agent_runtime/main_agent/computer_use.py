"""Local and sandbox computer capabilities with their runtime instructions."""

from __future__ import annotations

import os
import platform

from astrbot.core import logger
from astrbot.core.agent.tool import ToolSet
from astrbot.core.astr_agent_runtime.context import (
    AgentContextWrapper,
    AstrAgentContext,
)
from astrbot.core.astr_agent_runtime.tools.computer_tools import (
    AnnotateExecutionTool,
    BrowserBatchExecTool,
    BrowserExecTool,
    CreateSkillCandidateTool,
    CreateSkillPayloadTool,
    CuaKeyboardTypeTool,
    CuaMouseClickTool,
    CuaScreenshotTool,
    EvaluateSkillCandidateTool,
    ExecuteShellTool,
    FileDownloadTool,
    FileEditTool,
    FileReadTool,
    FileUploadTool,
    FileWriteTool,
    GetExecutionHistoryTool,
    GetSkillPayloadTool,
    GrepTool,
    ListSkillCandidatesTool,
    ListSkillReleasesTool,
    LocalExecuteShellTool,
    LocalPythonTool,
    PromoteSkillCandidateTool,
    PythonTool,
    RollbackSkillReleaseTool,
    RunBrowserSkillTool,
    ShellSessionTool,
    SyncSkillReleaseTool,
)
from astrbot.core.astr_agent_runtime.tools.computer_tools.util import (
    LOCAL_NETWORK_POLICY_NOTICE,
    get_local_permission_policy,
)
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.provider.register import llm_tools
from astrbot.core.star.context import Context
from astrbot.core.utils.runtime_env import resolve_windows_shell

from .config import MainAgentBuildConfig
from .workspace import resolve_workspace_path

SANDBOX_MODE_PROMPT = (
    "You have access to a sandboxed environment and can execute shell commands and Python code securely."
    # "Your have extended skills library, such as PDF processing, image generation, data analysis, etc. "
    # "Before handling complex tasks, please retrieve and review the documentation in the in /app/skills/ directory. "
    # "If the current task matches the description of a specific skill, prioritize following the workflow defined by that skill."
    # "Use `ls /app/skills/` to list all available skills. "
    # "Use `cat /app/skills/{skill_name}/SKILL.md` to read the documentation of a specific skill."
    # "SKILL.md might be large, you can read the description first, which is located in the YAML frontmatter of the file."
    # "Use shell commands such as grep, sed, awk to extract relevant information from the documentation as needed.\n"
)


def _apply_local_env_tools(
    req: ProviderRequest,
    plugin_context: Context,
) -> str:
    """Register local computer tools and return their runtime instructions.

    Args:
        req: Request receiving local computer tools.
        plugin_context: Registry providing shared builtin tools.

    Returns:
        Instructions describing the local shell and execution environment.
    """
    if req.func_tool is None:
        req.func_tool = ToolSet()
    tool_mgr = plugin_context.get_llm_tool_manager()
    req.func_tool.add_tool(LocalExecuteShellTool())
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(ShellSessionTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(LocalPythonTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(FileReadTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(FileWriteTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(FileEditTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(GrepTool))
    return f"## Shell and sessions\n{_build_local_mode_prompt()}\n"


def _build_local_mode_prompt() -> str:
    """Describe the host shell and the lifecycle of local command sessions.

    Returns:
        Platform-specific local execution instructions.
    """
    system_name = platform.system() or "Unknown"
    if system_name.lower() != "windows":
        shell_hint = (
            "The runtime shell is Unix-like. Use POSIX-compatible shell commands."
        )
    elif resolve_windows_shell() == "pwsh.exe":
        shell_hint = (
            "The runtime shell is PowerShell 7 (pwsh.exe). "
            "Use PowerShell 7-compatible syntax and cmdlets, and do not "
            "assume a full Unix userland or GNU utilities are available."
        )
    else:
        shell_hint = (
            "The runtime shell is Windows PowerShell 5.1 (powershell.exe). "
            "Use Windows PowerShell 5.1-compatible syntax and cmdlets; do not use "
            "PowerShell 7-only syntax or assume Unix commands like cat/ls/grep are available."
        )
    return (
        "Local computer tools are available subject to your role's file and execution permissions. "
        f"Current operating system: {system_name}. "
        f"{shell_hint} "
        "Local shell commands automatically return a managed session when they "
        "outlive the initial wait. Use `astrbot_shell_session` to list, poll, "
        "write raw text or complete lines to, interrupt, or terminate those sessions. "
        "Use its `write_line` action for line-oriented programs so the session receives "
        "a real line feed. Do not add `&`, `nohup`, or another detachment wrapper for "
        "ordinary long-running commands."
        + (
            " Restricted Windows execution uses AppContainer. "
            "PowerShell starts at Workspace:\\, a PSDrive mapped to the real workspace. "
            "Use relative paths or Workspace:\\ paths with cmdlets; native programs "
            "need relative or actual filesystem paths, not PSDrive paths. "
            "An InitializeDefaultDrives warning can occur because ancestor directories "
            "are inaccessible; it does not imply the workspace command failed. "
            "Access-denied errors on absolute paths can be retried with a workspace-relative "
            "path or astrbot_execute_python. Python/runtime files "
            "are read-only; use the workspace for temporary files and caches. "
            "Network capabilities do not guarantee localhost access, including local "
            "proxy ports. Host proxy environment variables are not inherited. Console "
            "interrupts are unavailable; use session terminate when needed. "
            "Job limits cover CPU time, process count and committed memory; "
            "per-file size and open-handle limits are unavailable. "
            "Missing startup authorization requires restarting AstrBot; tool calls "
            "never request administrator access or retry without isolation."
            if system_name.lower() == "windows"
            else ""
        )
    )


def _apply_sandbox_tools(
    config: MainAgentBuildConfig,
    req: ProviderRequest,
    session_id: str,
) -> str:
    """Register sandbox capabilities and return their runtime instructions.

    Args:
        config: Resolved sandbox settings.
        req: Request receiving the sandbox tool set.
        session_id: Session used to inspect already-booted sandbox capabilities.

    Returns:
        Runtime instructions, or an empty string for incomplete configuration.
    """
    if req.func_tool is None:
        req.func_tool = ToolSet()
    runtime_prompt = ""
    booter = config.sandbox_cfg.get("booter", "shipyard_neo")
    if booter == "shipyard":
        ep = config.sandbox_cfg.get("shipyard_endpoint", "")
        at = config.sandbox_cfg.get("shipyard_access_token", "")
        if not ep or not at:
            logger.error("Shipyard sandbox configuration is incomplete.")
            return ""
        os.environ["SHIPYARD_ENDPOINT"] = ep
        os.environ["SHIPYARD_ACCESS_TOKEN"] = at

    tool_mgr = llm_tools
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(ExecuteShellTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(PythonTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(FileUploadTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(FileDownloadTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(FileReadTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(FileWriteTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(FileEditTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(GrepTool))
    if booter == "shipyard_neo":
        # Neo-specific path rule: filesystem tools operate relative to sandbox
        # workspace root. Do not prepend "/workspace".
        runtime_prompt += (
            "\n## Shipyard Neo File Path Rule\n"
            "When using sandbox filesystem tools (upload/download/read/write/list/delete), "
            "always pass paths relative to the sandbox workspace root. "
            "Example: use `baidu_homepage.png` instead of `/workspace/baidu_homepage.png`.\n"
        )

        runtime_prompt += (
            "\n## Neo Skill Lifecycle Workflow\n"
            "When user asks to create/update a reusable skill in Neo mode, use lifecycle tools instead of directly writing local skill folders.\n"
            "Preferred sequence:\n"
            "1) Use `astrbot_create_skill_payload` to store canonical payload content and get `payload_ref`.\n"
            "2) Use `astrbot_create_skill_candidate` with `skill_key` + `source_execution_ids` (and optional `payload_ref`) to create a candidate.\n"
            "3) Use `astrbot_promote_skill_candidate` to release: `stage=canary` for trial; `stage=stable` for production.\n"
            "For stable release, set `sync_to_local=true` to sync `payload.skill_markdown` into local `SKILL.md`.\n"
            "Do not treat ad-hoc generated files as reusable Neo skills unless they are captured via payload/candidate/release.\n"
            "To update an existing skill, create a new payload/candidate and promote a new release version; avoid patching old local folders directly.\n"
        )

        # Determine sandbox capabilities from an already-booted session.
        # If no session exists yet (first request), capabilities is None
        # and we register all tools conservatively.
        from astrbot.core.astr_agent_runtime.computer.computer_client import (
            session_booter,
        )

        sandbox_capabilities: list[str] | None = None
        existing_booter = session_booter.get(session_id)
        if existing_booter is not None:
            sandbox_capabilities = getattr(existing_booter, "capabilities", None)

        # Browser tools: only register if profile supports browser
        # (or if capabilities are unknown because sandbox hasn't booted yet)
        if sandbox_capabilities is None or "browser" in sandbox_capabilities:
            req.func_tool.add_tool(tool_mgr.get_builtin_tool(BrowserExecTool))
            req.func_tool.add_tool(tool_mgr.get_builtin_tool(BrowserBatchExecTool))
            req.func_tool.add_tool(tool_mgr.get_builtin_tool(RunBrowserSkillTool))

        # Neo-specific tools (always available for shipyard_neo)
        req.func_tool.add_tool(tool_mgr.get_builtin_tool(GetExecutionHistoryTool))
        req.func_tool.add_tool(tool_mgr.get_builtin_tool(AnnotateExecutionTool))
        req.func_tool.add_tool(tool_mgr.get_builtin_tool(CreateSkillPayloadTool))
        req.func_tool.add_tool(tool_mgr.get_builtin_tool(GetSkillPayloadTool))
        req.func_tool.add_tool(tool_mgr.get_builtin_tool(CreateSkillCandidateTool))
        req.func_tool.add_tool(tool_mgr.get_builtin_tool(ListSkillCandidatesTool))
        req.func_tool.add_tool(tool_mgr.get_builtin_tool(EvaluateSkillCandidateTool))
        req.func_tool.add_tool(tool_mgr.get_builtin_tool(PromoteSkillCandidateTool))
        req.func_tool.add_tool(tool_mgr.get_builtin_tool(ListSkillReleasesTool))
        req.func_tool.add_tool(tool_mgr.get_builtin_tool(RollbackSkillReleaseTool))
        req.func_tool.add_tool(tool_mgr.get_builtin_tool(SyncSkillReleaseTool))

    if booter == "cua":
        runtime_prompt += (
            "\n## CUA Desktop Control\n"
            "Use `astrbot_execute_shell` with `background=true` to launch GUI apps. "
            'Use Firefox for browser tasks, for example `firefox "https://example.com"`. '
            "After each visible step, call `astrbot_cua_screenshot` with "
            "`send_to_user=true` and `return_image_to_llm=true` so the user can "
            "monitor progress. When typing, inspect the screenshot first and confirm "
            "the target field is focused and empty or safe to append to. Use "
            "`astrbot_cua_mouse_click` for coordinates and `astrbot_cua_keyboard_type` "
            "for text input; use text=`\\n` for Enter.\n"
        )
        req.func_tool.add_tool(tool_mgr.get_builtin_tool(CuaScreenshotTool))
        req.func_tool.add_tool(tool_mgr.get_builtin_tool(CuaMouseClickTool))
        req.func_tool.add_tool(tool_mgr.get_builtin_tool(CuaKeyboardTypeTool))

    return f"{runtime_prompt}\n## Sandbox\n{SANDBOX_MODE_PROMPT}\n"


async def apply_computer_use(
    req: ProviderRequest,
    plugin_context: Context,
    config: MainAgentBuildConfig,
    agent_context: AstrAgentContext,
) -> None:
    """Register computer tools and append instructions for the selected runtime.

    Args:
        req: Request receiving computer tools and runtime instructions.
        plugin_context: Builtin tool registry.
        config: Local or sandbox runtime settings.
        agent_context: Event and services used to resolve execution permissions.
    """
    runtime_prompt = ""
    if config.computer_use_runtime == "sandbox":
        runtime_prompt = _apply_sandbox_tools(config, req, req.session_id)
    elif config.computer_use_runtime == "local":
        runtime_prompt = _apply_local_env_tools(req, plugin_context)
        local_policy = get_local_permission_policy(
            AgentContextWrapper(context=agent_context)
        )
        if (
            local_policy.allow_execution
            and not local_policy.allow_network
            and LOCAL_NETWORK_POLICY_NOTICE not in (req.system_prompt or "")
        ):
            runtime_prompt += f"\n## Execution policy\n{LOCAL_NETWORK_POLICY_NOTICE}\n"
        runtime_prompt += "\n## Workspace\n" + await get_workspace_instructions(
            agent_context.event, plugin_context, config.computer_use_runtime
        )
    if runtime_prompt:
        req.system_prompt += (
            f'\n<execution_environment runtime="{config.computer_use_runtime}">\n'
            f"{runtime_prompt.strip()}\n"
            "</execution_environment>\n"
        )


async def get_workspace_instructions(
    event: AstrMessageEvent,
    plugin_context: Context,
    runtime: str,
) -> str:
    """Describe local tool paths within the execution environment instructions.

    Args:
        event: Event identifying the current session.
        plugin_context: Workspace services.
        runtime: Selected computer-use runtime.

    Returns:
        Working-directory guidance for local tools, or an empty string.
    """
    if runtime != "local":
        return ""
    workspace_root = await resolve_workspace_path(
        event.unified_msg_origin, plugin_context
    )
    return (
        f"\nCurrent workspace: `{workspace_root}`. "
        "`astrbot_execute_shell` and `astrbot_execute_python` use it as "
        "their working directory. `astrbot_file_read_tool`, "
        "`astrbot_file_write_tool`, `astrbot_file_edit_tool`, and "
        "`astrbot_grep_tool` resolve relative paths from it. Prefer relative "
        "paths within the workspace; do not assume this behavior for other "
        "tools.\n"
    )
