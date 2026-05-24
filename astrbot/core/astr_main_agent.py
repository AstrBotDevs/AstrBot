from __future__ import annotations

import asyncio
import copy
import datetime
import inspect
import json
import os
import platform
import zoneinfo
from collections.abc import Awaitable, Coroutine
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from astrbot.core import logger

if TYPE_CHECKING:
    from astrbot.core.conversation_mgr import ConversationManager

from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.agent.mcp_client import MCPTool
from astrbot.core.agent.message import TextPart
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.astr_agent_context import AgentContextWrapper, AstrAgentContext
from astrbot.core.astr_agent_hooks import MAIN_AGENT_HOOKS
from astrbot.core.astr_agent_run_util import AgentRunner
from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
from astrbot.core.astr_main_agent_resources import (
    CHATUI_SPECIAL_DEFAULT_PERSONA_PROMPT,
    LIVE_MODE_SYSTEM_PROMPT,
    LLM_SAFETY_MODE_SYSTEM_PROMPT,
    SANDBOX_MODE_PROMPT,
    TOOL_CALL_PROMPT,
    TOOL_CALL_PROMPT_SKILLS_LIKE_MODE,
)
from astrbot.core.computer import computer_client
from astrbot.core.computer.sandbox_tool_binding import tool_available_in_runtime
from astrbot.core.config.default import GLOBAL_UNIFIED_CONTEXT_UMO, ORIGINAL_UMO_KEY
from astrbot.core.context_memory import (
    build_pinned_memory_system_block,
    load_context_memory_config,
)
from astrbot.core.conversation_mgr import Conversation
from astrbot.core.message.components import File, Image, Record, Reply, Video
from astrbot.core.persona_error_reply import (
    extract_persona_custom_error_message_from_persona,
    set_persona_custom_error_message_on_event,
)
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.prompt_assembly_router import assemble_system_prompt
from astrbot.core.provider import Provider
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.provider.register import llm_tools
from astrbot.core.skills.skill_manager import (
    SkillInfo,
    SkillManager,
    build_skills_prompt,
)
from astrbot.core.star.context import Context
from astrbot.core.star.session_plugin_manager import SessionPluginManager
from astrbot.core.star.star import star_registry
from astrbot.core.star.star_handler import star_map
from astrbot.core.subagent_manager import SubAgentManager
from astrbot.core.subagent_orchestrator import SubAgentOrchestrator
from astrbot.core.tools.computer_tools import (
    CopyFileBetweenSandboxesTool,
    CreateSandboxTool,
    DestroySandboxTool,
    ExecuteShellTool,
    FileDownloadTool,
    FileEditTool,
    FileReadTool,
    FileUploadTool,
    FileWriteTool,
    GetCurrentSandboxTool,
    GrepTool,
    KeepAliveSandboxTool,
    ListSandboxesTool,
    ListSandboxProvidersTool,
    LocalPythonTool,
    PythonTool,
    ReleaseSandboxTool,
    ScreenshotSandboxTool,
    SetSandboxRetentionPolicyTool,
    SwitchSandboxTool,
    TakeoverSandboxTool,
    normalize_umo_for_workspace,
)
from astrbot.core.tools.computer_tools.interactive_shell import (
    InteractiveShellListTool,
    InteractiveShellReadTool,
    InteractiveShellSendTool,
    InteractiveShellStartTool,
    InteractiveShellStopTool,
)
from astrbot.core.tools.cron_tools import FutureTaskTool
from astrbot.core.tools.knowledge_base_tools import (
    KnowledgeBaseQueryTool,
    retrieve_knowledge_base,
)
from astrbot.core.tools.web_search_tools import (
    BaiduWebSearchTool,
    BochaWebSearchTool,
    BraveWebSearchTool,
    MetasoWebSearchTool,
    TavilyExtractWebPageTool,
    TavilyWebSearchTool,
    normalize_legacy_web_search_config,
)
from astrbot.core.utils.astrbot_path import (
    get_astrbot_system_tmp_path,
    get_astrbot_workspaces_path,
)
from astrbot.core.utils.file_extract import extract_file_moonshotai
from astrbot.core.utils.llm_metadata import LLM_METADATAS
from astrbot.core.utils.media_utils import (
    IMAGE_COMPRESS_DEFAULT_MAX_SIZE,
    IMAGE_COMPRESS_DEFAULT_QUALITY,
    compress_image,
)
from astrbot.core.utils.quoted_message.settings import (
    SETTINGS as DEFAULT_QUOTED_MESSAGE_SETTINGS,
)
from astrbot.core.utils.quoted_message.settings import (
    QuotedMessageParserSettings,
)
from astrbot.core.utils.quoted_message_parser import (
    extract_quoted_message_images,
    extract_quoted_message_text,
)
from astrbot.core.utils.string_utils import normalize_and_dedupe_strings

LLM_ERROR_MESSAGE_EXTRA_KEY = "_llm_error_message"
_TITLE_GEN_SYSTEM_PROMPT = (
    "You are a title generator. Return a concise chat title in the user's language. "
    "If no useful title can be generated, return <None>."
)


class _AwaitableNoop:
    def __await__(self):
        if False:
            yield None
        return None


class _AwaitableFactory:
    def __init__(self, factory):
        self._factory = factory

    def __await__(self):
        return self._factory().__await__()


async def _maybe_await(value: Awaitable[Any] | Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


_TITLE_GEN_USER_PROMPT_TEMPLATE = (
    "Generate a short title for this user message:\n{user_prompt}"
)


@dataclass(slots=True)
class MainAgentBuildConfig:
    """The main agent build configuration.
    Most of the configs can be found in the cmd_config.json
    """

    tool_call_timeout: int
    """The timeout (in seconds) for a tool call.
    When the tool call exceeds this time,
    a timeout error as a tool result will be returned.
    """
    tool_schema_mode: str = "full"
    """The tool schema mode, can be 'full' or 'skills-like'."""
    provider_wake_prefix: str = ""
    """The wake prefix for the provider. If the user message does not start with this prefix,
    the main agent will not be triggered."""
    streaming_response: bool = True
    """Whether to use streaming response."""
    sanitize_context_by_modalities: bool = False
    """Whether to sanitize the context based on the provider's supported modalities.
    This will remove unsupported message types(e.g. image) from the context to prevent issues."""
    kb_agentic_mode: bool = False
    """Whether to use agentic mode for knowledge base retrieval.
    This will inject the knowledge base query tool into the main agent's toolset to allow dynamic querying."""
    file_extract_enabled: bool = False
    """Whether to enable file content extraction for uploaded files."""
    file_extract_prov: str = "moonshotai"
    """The file extraction provider."""
    file_extract_msh_api_key: str = ""
    """The API key for Moonshot AI file extraction provider."""
    context_limit_reached_strategy: str = "truncate_by_turns"
    """The strategy to handle context length limit reached."""
    llm_compress_instruction: str = ""
    """The instruction for compression in llm_compress strategy."""
    llm_compress_keep_recent: int = 6
    """The number of most recent turns to keep during llm_compress strategy."""
    llm_compress_provider_id: str = ""
    """The provider ID for the LLM used in context compression."""
    llm_compress_use_compact_api: bool = True
    """Whether to prefer provider native context compact API when available."""
    context_token_counter_mode: str = "estimate"
    """Token counting mode used by context compaction."""
    compact_context_after_tool_call: bool = False
    """Whether to run context compaction immediately after tool execution."""
    compact_context_soft_ratio: float = 0.3
    """Soft token budget ratio that can trigger post-tool compaction."""
    compact_context_hard_ratio: float = 0.7
    """Hard token budget ratio that always triggers post-tool compaction."""
    compact_context_min_delta_tokens: int = 0
    """Minimum token increase required before soft-zone post-tool compaction."""
    compact_context_min_delta_turns: int = 0
    """Minimum message increase required before soft-zone post-tool compaction."""
    compact_context_debounce_seconds: int = 0
    """Minimum interval between post-tool compaction checks."""
    max_context_length: int = 30
    """The maximum number of turns to keep in context. -1 means no limit.
    This enforce max turns before compression"""
    dequeue_context_length: int = 10
    """The number of oldest turns to remove when context length limit is reached."""
    fallback_max_context_tokens: int = 128000
    """Fallback max context tokens. When max_context_tokens is 0 and the model is not in LLM_METADATAS, use this value."""
    llm_safety_mode: bool = True
    """This will inject healthy and safe system prompt into the main agent,
    to prevent LLM output harmful information"""
    safety_mode_strategy: str = "system_prompt"
    computer_use_runtime: str = "local"
    """The runtime for agent computer use: none, local, local_sandboxed, or sandbox."""
    sandbox_cfg: dict = field(default_factory=dict)
    add_cron_tools: bool = True
    """This will add cron job management tools to the main agent for proactive cron job execution."""
    provider_settings: dict = field(default_factory=dict)
    subagent_orchestrator: dict = field(default_factory=dict)
    timezone: str | None = None
    max_quoted_fallback_images: int = 20
    """Maximum number of images injected from quoted-message fallback extraction."""
    tool_call_approval: dict = field(default_factory=dict)
    """Tool call approval configuration."""


@dataclass(slots=True)
class MainAgentBuildResult:
    agent_runner: AgentRunner
    provider_request: ProviderRequest
    provider: Provider
    reset_coro: Coroutine | None = None


def _set_llm_error_message(event: AstrMessageEvent, message: str) -> None:
    event.set_extra(LLM_ERROR_MESSAGE_EXTRA_KEY, message)


def _select_provider(
    event: AstrMessageEvent,
    plugin_context: Context,
) -> Provider | None:
    """Select chat provider for the event."""
    sel_provider = event.get_extra("selected_provider")
    if sel_provider and isinstance(sel_provider, str):
        provider = plugin_context.get_provider_by_id(sel_provider)
        if provider is None:
            logger.error("未找到指定的提供商: %s。", sel_provider)
            _set_llm_error_message(
                event,
                f"LLM 请求失败：未找到指定的提供商 `{sel_provider}`。请检查提供商配置或重新选择可用模型。",
            )
            return None
        if not isinstance(provider, Provider):
            logger.error(
                "选择的提供商类型无效(%s)，跳过 LLM 请求处理。",
                type(provider),
            )
            _set_llm_error_message(
                event,
                f"LLM 请求失败：选择的提供商类型无效（{type(provider).__name__}），已跳过本次请求。",
            )
            return None
        return provider
    try:
        return plugin_context.get_using_provider(umo=event.unified_msg_origin)
    except ValueError as exc:
        logger.error("Error occurred while selecting provider: %s", exc)
        _set_llm_error_message(event, f"LLM 请求失败：{exc}")
        return None


async def _get_session_conv(
    event: AstrMessageEvent,
    plugin_context: Context,
) -> Conversation:
    conv_mgr = plugin_context.conversation_manager
    umo = event.unified_msg_origin
    user_name = event.get_sender_name()
    avatar = event.get_sender_avatar()
    cid = await conv_mgr.get_curr_conversation_id(umo)
    if not cid:
        cid = await conv_mgr.new_conversation(umo, event.get_platform_id())
    conversation = await conv_mgr.get_conversation(umo, cid)
    if not conversation:
        cid = await conv_mgr.new_conversation(umo, event.get_platform_id())
        conversation = await conv_mgr.get_conversation(umo, cid)
    if not conversation:
        raise RuntimeError("无法创建新的对话。")
    # 如果已有对话但 user_name 或 avatar 为空，更新它们
    updates: dict[str, Any] = {}
    if getattr(conversation, "user_name", None) is None and user_name:
        updates["user_name"] = user_name
    if getattr(conversation, "avatar", None) is None and avatar:
        updates["avatar"] = avatar
    if updates:
        await _maybe_await(conv_mgr.db.update_conversation(cid, **updates))
        for field, value in updates.items():
            setattr(conversation, field, value)
    return conversation


async def _apply_kb(
    event: AstrMessageEvent,
    req: ProviderRequest,
    plugin_context: Context,
    config: MainAgentBuildConfig,
) -> None:
    if not config.kb_agentic_mode:
        if req.prompt is None or not req.prompt.strip():
            return
        try:
            kb_result = await retrieve_knowledge_base(
                query=req.prompt,
                umo=event.unified_msg_origin,
                context=plugin_context,
            )
            if not kb_result:
                return
            if req.system_prompt is not None:
                req.system_prompt += (
                    f"\n\n[Related Knowledge Base Results]:\n{kb_result}"
                )
        except Exception as exc:  # noqa: BLE001
            logger.error("Error occurred while retrieving knowledge base: %s", exc)
    else:
        if req.func_tool is None:
            req.func_tool = ToolSet()
        req.func_tool.add_tool(
            plugin_context.get_llm_tool_manager().get_builtin_tool(
                KnowledgeBaseQueryTool,
            ),
        )


async def _apply_file_extract(
    event: AstrMessageEvent,
    req: ProviderRequest,
    config: MainAgentBuildConfig,
) -> None:
    file_paths = []
    file_names = []
    for comp in event.message_obj.message:
        if isinstance(comp, File):
            file_paths.append(await comp.get_file())
            file_names.append(comp.name)
        elif isinstance(comp, Reply) and comp.chain:
            for reply_comp in comp.chain:
                if isinstance(reply_comp, File):
                    file_paths.append(await reply_comp.get_file())
                    file_names.append(reply_comp.name)
    if not file_paths:
        return
    if not req.prompt:
        req.prompt = "总结一下文件里面讲了什么？"
    if config.file_extract_prov == "moonshotai":
        if not config.file_extract_msh_api_key:
            logger.error("Moonshot AI API key for file extract is not set")
            return
        file_contents = await asyncio.gather(
            *[
                extract_file_moonshotai(
                    file_path,
                    config.file_extract_msh_api_key,
                )
                for file_path in file_paths
            ],
        )
    else:
        logger.error("Unsupported file extract provider: %s", config.file_extract_prov)
        return

    for file_content, file_name in zip(file_contents, file_names, strict=False):
        req.contexts.append(
            {
                "role": "system",
                "content": (
                    "File Extract Results of user uploaded files:\n"
                    f"{file_content}\nFile Name: {file_name or 'Unknown'}"
                ),
            },
        )


def _apply_prompt_prefix(req: ProviderRequest, cfg: dict) -> None:
    prefix = cfg.get("prompt_prefix")
    if not prefix:
        return
    if "{{prompt}}" in prefix:
        req.prompt = prefix.replace("{{prompt}}", req.prompt)
    else:
        req.prompt = f"{prefix}{req.prompt}"


def _get_workspace_path_for_umo(umo: str) -> Path:
    normalized_umo = normalize_umo_for_workspace(umo)
    return Path(get_astrbot_workspaces_path()) / normalized_umo


def _apply_workspace_extra_prompt(
    event: AstrMessageEvent,
    req: ProviderRequest,
) -> None:
    extra_prompt_path = _get_workspace_path_for_umo(event.unified_msg_origin) / (
        "EXTRA_PROMPT.md"
    )
    if not extra_prompt_path.is_file():
        return

    try:
        extra_prompt = extra_prompt_path.read_text(encoding="utf-8").strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to read workspace extra prompt for umo=%s from %s: %s",
            event.unified_msg_origin,
            extra_prompt_path,
            exc,
        )
        return

    if not extra_prompt:
        return

    req.system_prompt = (
        f"{req.system_prompt or ''}\n"
        "[Workspace Extra Prompt]\n"
        "The following instructions are loaded from the current workspace "
        "`EXTRA_PROMPT.md` file.\n"
        f"{extra_prompt}\n"
    )


def _apply_local_env_tools(req: ProviderRequest, plugin_context: Context) -> None:
    if req.func_tool is None:
        req.func_tool = ToolSet()
    tool_mgr = plugin_context.get_llm_tool_manager()
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(ExecuteShellTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(LocalPythonTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(FileReadTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(FileWriteTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(FileEditTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(GrepTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(InteractiveShellStartTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(InteractiveShellStopTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(InteractiveShellSendTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(InteractiveShellReadTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(InteractiveShellListTool))
    req.system_prompt = f"{req.system_prompt or ''}\n{_build_local_mode_prompt()}\n"


def _build_local_mode_prompt() -> str:
    system_name = platform.system() or "Unknown"
    shell_hint = (
        "The runtime shell is Windows Command Prompt (cmd.exe). "
        "Use cmd-compatible commands and do not assume Unix commands like cat/ls/grep are available."
        if system_name.lower() == "windows"
        else "The runtime shell is Unix-like. Use POSIX-compatible shell commands."
    )
    lines = [
        "You have access to the host local environment and can execute shell commands and Python code.",
        f"Current operating system: {system_name}.",
        shell_hint,
        "",
        "You can write and modify the EXTRA_PROMPT.md file in the current workspace",
        "to customize your own system prompt instructions. This file will be automatically",
        "loaded and applied to your system prompt in subsequent conversations.",
        "",
        "When installing skills, unless explicitly specified otherwise, prefer installing",
        "them to the workspace/skills directory for better isolation and portability.",
    ]
    return " ".join(lines)


def _filter_skills_for_current_config(
    skills: list[SkillInfo],
    cfg: dict,
    session_disabled: set[str] | None = None,
) -> list[SkillInfo]:
    plugin_set = cfg.get("plugin_set", ["*"])
    allowed_plugins = (
        None
        if not isinstance(plugin_set, list) or "*" in plugin_set
        else {str(name) for name in plugin_set}
    )
    plugin_by_root_dir = {
        metadata.root_dir_name: metadata
        for metadata in star_registry
        if metadata.root_dir_name
    }
    filtered: list[SkillInfo] = []
    for skill in skills:
        if skill.source_type != "plugin":
            filtered.append(skill)
            continue

        plugin = plugin_by_root_dir.get(skill.plugin_name)
        if not plugin or not plugin.activated:
            continue
        if plugin.reserved:
            filtered.append(skill)
            continue
        if session_disabled and plugin.name in session_disabled:
            continue
        if allowed_plugins is None:
            filtered.append(skill)
            continue
        if plugin.name is not None and plugin.name in allowed_plugins:
            filtered.append(skill)
    return filtered


def _tool_available_for_current_runtime(tool: FunctionTool, cfg: dict) -> bool:
    runtime = str(cfg.get("computer_use_runtime", "local"))
    return tool_available_in_runtime(tool, runtime)


def _filter_tools_for_current_config(
    toolset: ToolSet, cfg: dict, session_id: str
) -> ToolSet:
    filtered = ToolSet()
    for tool in toolset:
        if _tool_available_for_current_runtime(tool, cfg):
            filtered.add_tool(tool)
    return filtered


def _filter_provider_runtime_tools(req: ProviderRequest, cfg: dict | None) -> None:
    if req.func_tool is None or cfg is None:
        return
    session_id = req.session_id or ""
    req.func_tool = _filter_tools_for_current_config(req.func_tool, cfg, session_id)


async def _ensure_persona_and_skills(
    req: ProviderRequest,
    cfg: dict,
    plugin_context: Context,
    event: AstrMessageEvent,
) -> None:
    """Ensure persona and skills are applied to the request's system prompt or user prompt."""
    if not req.conversation:
        return

    from astrbot.core import sp

    session_id = event.unified_msg_origin
    session_plugin_config = await sp.get_async(
        scope="umo",
        scope_id=session_id,
        key="session_plugin_config",
        default={},
    )
    set(session_plugin_config.get(session_id, {}).get("disabled_plugins", []))

    (
        persona_id,
        persona,
        _,
        use_webchat_special_default,
    ) = await plugin_context.persona_manager.resolve_selected_persona(
        umo=event.unified_msg_origin,
        conversation_persona_id=req.conversation.persona_id,
        platform_name=event.get_platform_name(),
        provider_settings=cfg,
    )

    set_persona_custom_error_message_on_event(
        event,
        extract_persona_custom_error_message_from_persona(persona),
    )

    # Ensure system_prompt is a string before any +=
    if req.system_prompt is None:
        req.system_prompt = ""
    session_id = event.unified_msg_origin

    if persona:
        # Inject persona system prompt
        if prompt := persona["prompt"]:
            req.system_prompt += f"\n# Persona Instructions\n\n{prompt}\n"
        if begin_dialogs := copy.deepcopy(persona.get("_begin_dialogs_processed")):
            req.contexts[:0] = begin_dialogs
    elif use_webchat_special_default:
        req.system_prompt += CHATUI_SPECIAL_DEFAULT_PERSONA_PROMPT

    # Inject skills prompt
    runtime = cfg.get("computer_use_runtime", "local")
    skill_manager = SkillManager()
    current_provider = computer_client.get_current_sandbox_provider_id(session_id)
    skills = skill_manager.list_skills(
        active_only=True,
        runtime=runtime,
        provider_id=current_provider,
    )
    skills = _filter_skills_for_current_config(skills, cfg)

    if skills:
        if persona and persona.get("skills") is not None:
            if not persona["skills"]:
                skills = []
            else:
                allowed = set(persona["skills"])
                skills = [skill for skill in skills if skill.name in allowed]
        if skills:
            req.system_prompt += f"\n{build_skills_prompt(skills)}\n"
            if runtime == "none":
                req.system_prompt += (
                    "User has not enabled the Computer Use feature. "
                    "You cannot use shell or Python to perform skills. "
                    "If you need to use these capabilities, ask the user to enable Computer Use in the AstrBot WebUI -> Config."
                )
    tmgr = plugin_context.get_llm_tool_manager()

    # inject toolset in the persona
    if (persona and persona.get("tools") is None) or not persona:
        persona_toolset = tmgr.get_full_tool_set()
        persona_toolset = _filter_tools_for_current_config(
            persona_toolset, cfg, session_id
        )
        for tool in list(persona_toolset):
            if not tool.active:
                persona_toolset.remove_tool(tool.name)
    else:
        persona_toolset = ToolSet()
        if persona["tools"]:
            for tool_name in persona["tools"]:
                tool = tmgr.get_func(tool_name)
                if (
                    tool
                    and tool.active
                    and _tool_available_for_current_runtime(tool, cfg)
                ):
                    persona_toolset.add_tool(tool)
    if not req.func_tool:
        req.func_tool = persona_toolset
    else:
        req.func_tool.merge(persona_toolset)

    # sub agents integration
    orch_cfg = plugin_context.get_config().get("subagent_orchestrator", {})
    so = plugin_context.subagent_orchestrator
    if orch_cfg.get("main_enable", False) and so:
        remove_dup = bool(orch_cfg.get("remove_main_duplicate_tools", False))

        assigned_tools: set[str] = set()
        agents = orch_cfg.get("agents", [])

        # 1. 提取白名单（归一化 subagents 名称）
        sub_agents_cfg = (persona or {}).get("subagents")
        normalized_subagents = (
            {str(name).strip() for name in sub_agents_cfg if str(name).strip()}
            if sub_agents_cfg is not None
            else None
        )

        # 2. 过滤 agents（使用归一化后的名称）
        if normalized_subagents is not None:
            agents = [
                agent
                for agent in agents
                if isinstance(agent, dict)
                and str(agent.get("name", "")).strip() in normalized_subagents
            ]
        if isinstance(agents, list):
            for a in agents:
                if not isinstance(a, dict):
                    continue
                if a.get("enabled", True) is False:
                    continue
                persona_tools = None
                persona_tools_configured = False
                pid = a.get("persona_id")
                if pid:
                    persona = plugin_context.persona_manager.get_persona_v3_by_id(pid)
                    if persona is not None:
                        persona_tools = persona.get("tools")
                        persona_tools_configured = "tools" in persona
                tools = a.get("tools", [])
                if persona_tools_configured:
                    tools = persona_tools
                if tools is None:
                    assigned_tools.update(
                        [
                            tool.name
                            for tool in tmgr.func_list
                            if not isinstance(tool, HandoffTool)
                            and _tool_available_for_current_runtime(tool, cfg)
                        ]
                    )
                    continue
                if not isinstance(tools, list):
                    continue
                for t in tools:
                    name = str(t).strip()
                    if name:
                        assigned_tools.add(name)

        if req.func_tool is None:
            req.func_tool = ToolSet()

        # add subagent handoff tools
        # 如果 normalized_subagents 为 None 则默认放行所有 handoffs,空集合禁用所有handoffs
        if normalized_subagents is None:
            # 不配置 subagents 时，默认放行所有 handoffs
            for tool in so.handoffs:
                req.func_tool.add_tool(tool)
        else:
            # 只允许指向归一化白名单中的 subagents 的 handoff
            for tool in so.handoffs:
                agent = getattr(tool, "agent", None)
                agent_name = getattr(agent, "name", None) if agent else None
                if agent_name is not None:
                    name_norm = str(agent_name).strip()
                    if name_norm and name_norm in normalized_subagents:
                        req.func_tool.add_tool(tool)

        # add subagent manager tools
        await _apply_subagent_manager_tools(plugin_context.get_config(), req, event, so)

        # check duplicates
        if remove_dup:
            handoff_names = {tool.name for tool in so.handoffs}
            for tool_name in assigned_tools:
                if tool_name in handoff_names:
                    continue
                req.func_tool.remove_tool(tool_name)

        router_prompt = (
            plugin_context.get_config()
            .get("subagent_orchestrator", {})
            .get("router_system_prompt", "")
        ).strip()

        if router_prompt:
            dynamic_cfg = orch_cfg.get(
                "dynamic_agents", {}
            )  # 未启用dynamic时才注入router_prompt，否则由subagent_manager注入
            if not dynamic_cfg.get("enabled", False):
                req.system_prompt += f"\n{router_prompt}\n"

    try:
        persona_span = event.trace.child("sel_persona", span_type="pipeline_stage")
        persona_span.set_input(
            persona_id=persona_id,
            persona_toolset=persona_toolset.names(),
        )
        persona_span.finish()
    except Exception:
        pass


async def _request_img_caption(
    provider_id: str,
    cfg: dict,
    image_urls: list[str],
    plugin_context: Context,
) -> str:
    prov = plugin_context.get_provider_by_id(provider_id)
    if prov is None:
        raise ValueError(
            f"Cannot get image caption because provider `{provider_id}` is not exist.",
        )
    if not isinstance(prov, Provider):
        raise ValueError(
            f"Cannot get image caption because provider `{provider_id}` is not a valid Provider, it is {type(prov)}.",
        )

    img_cap_prompt = cfg.get(
        "image_caption_prompt",
        "Please describe the image.",
    )
    logger.debug("Processing image caption with provider: %s", provider_id)
    llm_resp = await prov.text_chat(
        prompt=img_cap_prompt,
        image_urls=image_urls,
    )
    return llm_resp.completion_text


_PRE_CAPTION_RESULT_KEY = "_pre_caption_result"


async def pre_caption_images(
    event: AstrMessageEvent,
    plugin_context: Context,
    cfg: dict,
) -> None:
    """在 session lock 外提前完成图片描述，结果写入 event extra。

    由 pipeline 在获取 session lock 之前调用，避免图片描述慢速 LLM
    调用占用 session lock，阻塞后续消息处理。
    """
    img_cap_prov_id: str = cfg.get("default_image_caption_provider_id") or ""
    if not img_cap_prov_id:
        return

    image_components = [
        comp for comp in event.message_obj.message if isinstance(comp, Image)
    ]
    if not image_components:
        return

    try:
        image_urls = []
        for comp in image_components:
            path = await comp.convert_to_file_path()
            compressed = await _compress_image_for_provider(path, cfg)
            if _is_generated_compressed_image_path(path, compressed):
                event.track_temporary_local_file(compressed)
            image_urls.append(compressed)

        caption = await _request_img_caption(
            img_cap_prov_id,
            cfg,
            image_urls,
            plugin_context,
        )
        event.set_extra(_PRE_CAPTION_RESULT_KEY, caption or "")
    except Exception as exc:  # noqa: BLE001
        logger.error("预处理图片描述失败: %s", exc, exc_info=True)
        event.set_extra(_PRE_CAPTION_RESULT_KEY, None)


async def _ensure_img_caption(
    event: AstrMessageEvent,
    req: ProviderRequest,
    cfg: dict,
    plugin_context: Context,
    image_caption_provider: str,
) -> None:
    if event.get_extra("_skip_img_caption"):
        return

    pre_caption = event.get_extra(_PRE_CAPTION_RESULT_KEY)
    if pre_caption:
        req.extra_user_content_parts.append(
            TextPart(text=f"<image_caption>{pre_caption}</image_caption>")
        )
        req.image_urls = []
        return

    try:
        compressed_urls = []
        for url in req.image_urls:
            compressed_url = await _compress_image_for_provider(url, cfg)
            compressed_urls.append(compressed_url)
            if _is_generated_compressed_image_path(url, compressed_url):
                event.track_temporary_local_file(compressed_url)
        caption = await _request_img_caption(
            image_caption_provider,
            cfg,
            compressed_urls,
            plugin_context,
        )
        if caption:
            req.extra_user_content_parts.append(
                TextPart(text=f"<image_caption>{caption}</image_caption>"),
            )
            req.image_urls = []
    except Exception as exc:  # noqa: BLE001
        logger.error("处理图片描述失败: %s", exc)
        req.extra_user_content_parts.append(TextPart(text="[Image Captioning Failed]"))
    finally:
        req.image_urls = []


def _append_quoted_image_attachment(req: ProviderRequest, image_path: str) -> None:
    req.extra_user_content_parts.append(
        TextPart(text=f"[Image Attachment in quoted message: path {image_path}]"),
    )


def _append_audio_attachment(req: ProviderRequest, audio_path: str) -> None:
    req.extra_user_content_parts.append(
        TextPart(text=f"[Audio Attachment: path {audio_path}]"),
    )


def _append_quoted_audio_attachment(req: ProviderRequest, audio_path: str) -> None:
    req.extra_user_content_parts.append(
        TextPart(text=f"[Audio Attachment in quoted message: path {audio_path}]"),
    )


async def _resolve_image_component_ref(comp: Image) -> str:
    image_ref = (getattr(comp, "url", "") or "").strip()
    if image_ref:
        return image_ref

    image_ref = (getattr(comp, "file", "") or "").strip()
    if image_ref:
        return image_ref

    image_ref = (getattr(comp, "path", "") or "").strip()
    if image_ref:
        return image_ref

    return await comp.convert_to_file_path()


async def _append_video_attachment(
    req: ProviderRequest,
    comp: Video,
    *,
    quoted: bool = False,
) -> None:
    try:
        video_path = await comp.convert_to_file_path()
    except Exception as exc:  # noqa: BLE001
        if quoted:
            logger.error("Error processing quoted video attachment: %s", exc)
        else:
            logger.error("Error processing video attachment: %s", exc)
        return

    video_name = os.path.basename(video_path) or "video"
    if quoted:
        text = (
            "[Video Attachment in quoted message: "
            f"name {video_name}, path {video_path}]"
        )
    else:
        text = f"[Video Attachment: name {video_name}, path {video_path}]"
    req.extra_user_content_parts.append(TextPart(text=text))


def _get_quoted_message_parser_settings(
    provider_settings: dict[str, object] | None,
) -> QuotedMessageParserSettings:
    if not isinstance(provider_settings, dict):
        return DEFAULT_QUOTED_MESSAGE_SETTINGS
    overrides = provider_settings.get("quoted_message_parser")
    if not isinstance(overrides, dict):
        return DEFAULT_QUOTED_MESSAGE_SETTINGS
    return DEFAULT_QUOTED_MESSAGE_SETTINGS.with_overrides(overrides)


def _get_image_compress_args(
    provider_settings: dict[str, object] | None,
) -> tuple[bool, int, int]:
    if not isinstance(provider_settings, dict):
        return True, IMAGE_COMPRESS_DEFAULT_MAX_SIZE, IMAGE_COMPRESS_DEFAULT_QUALITY

    enabled = provider_settings.get("image_compress_enabled", True)
    if not isinstance(enabled, bool):
        enabled = True

    raw_options = provider_settings.get("image_compress_options")
    if isinstance(raw_options, dict):
        options = dict(raw_options.items())
    else:
        options = {}

    max_size = options.get("max_size", IMAGE_COMPRESS_DEFAULT_MAX_SIZE)
    if not isinstance(max_size, int):
        max_size = IMAGE_COMPRESS_DEFAULT_MAX_SIZE
    max_size = max(max_size, 1)

    quality = options.get("quality", IMAGE_COMPRESS_DEFAULT_QUALITY)
    if not isinstance(quality, int):
        quality = IMAGE_COMPRESS_DEFAULT_QUALITY
    quality = min(max(quality, 1), 100)

    return enabled, max_size, quality


async def _compress_image_for_provider(
    url_or_path: str,
    provider_settings: dict[str, object] | None,
) -> str:
    try:
        enabled, max_size, quality = _get_image_compress_args(provider_settings)
        if not enabled:
            return url_or_path
        return await compress_image(url_or_path, max_size=max_size, quality=quality)
    except Exception as exc:  # noqa: BLE001
        logger.error("Image compression failed: %s", exc)
        return url_or_path


def _is_generated_compressed_image_path(
    original_path: str,
    compressed_path: str | None,
) -> bool:
    if not compressed_path or compressed_path == original_path:
        return False
    if compressed_path.startswith("http") or compressed_path.startswith("data:image"):
        return False
    return os.path.exists(compressed_path)


def _provider_supports_images(provider: object | None) -> bool:
    if provider is None:
        return False

    provider_config = getattr(provider, "provider_config", None)
    if not isinstance(provider_config, dict):
        return False

    modalities = provider_config.get("modalities")
    if modalities is None:
        return False
    if isinstance(modalities, str):
        return "image" in {part.strip() for part in modalities.split(",") if part}
    if not isinstance(modalities, (list, tuple, set)):
        return False
    return "image" in {str(part).strip() for part in modalities if str(part).strip()}


def _resolve_quoted_image_caption_mode(
    provider_settings: dict[str, object] | None,
) -> str:
    if not isinstance(provider_settings, dict):
        return "auto"

    mode = provider_settings.get("quoted_image_caption_mode", "auto")
    if not isinstance(mode, str):
        return "auto"

    normalized = mode.strip().lower()
    if normalized in {"auto", "always", "never"}:
        return normalized
    return "auto"


def _should_caption_quoted_images(
    event: AstrMessageEvent,
    plugin_context: Context,
    provider_settings: dict[str, object] | None,
) -> bool:
    mode = _resolve_quoted_image_caption_mode(provider_settings)
    if mode == "always":
        return True
    if mode == "never":
        return False

    active_provider = _select_provider(event, plugin_context)
    return not _provider_supports_images(active_provider)


async def _process_quote_message(
    event: AstrMessageEvent,
    req: ProviderRequest,
    img_cap_prov_id: str,
    plugin_context: Context,
    provider_settings: dict[str, object] | None = None,
    quoted_message_settings: QuotedMessageParserSettings = DEFAULT_QUOTED_MESSAGE_SETTINGS,
    config: MainAgentBuildConfig | None = None,
) -> None:
    quote = None
    for comp in event.message_obj.message:
        if isinstance(comp, Reply):
            quote = comp
            break
    if not quote:
        return

    content_parts = []
    sender_info = f"({quote.sender_nickname}): " if quote.sender_nickname else ""
    message_str = (
        await extract_quoted_message_text(
            event,
            quote,
            settings=quoted_message_settings,
        )
        or quote.message_str
        or "[Empty Text]"
    )
    content_parts.append(f"{sender_info}{message_str}")

    image_seg = None
    if quote.chain:
        for comp in quote.chain:
            if isinstance(comp, Image):
                image_seg = comp
                break

    if image_seg and _should_caption_quoted_images(
        event, plugin_context, provider_settings
    ):
        try:
            prov = None
            path = None
            compress_path = None
            if img_cap_prov_id:
                prov = plugin_context.get_provider_by_id(img_cap_prov_id)
            if prov is None:
                prov = plugin_context.get_using_provider(event.unified_msg_origin)

            if prov and isinstance(prov, Provider):
                path = await image_seg.convert_to_file_path()
                compress_path = await _compress_image_for_provider(
                    path,
                    config.provider_settings if config else None,
                )
                if path and _is_generated_compressed_image_path(path, compress_path):
                    event.track_temporary_local_file(compress_path)
                cfg = (
                    config.provider_settings if config else None
                ) or plugin_context.get_config(umo=event.unified_msg_origin).get(
                    "provider_settings", {}
                )
                img_cap_prompt = (
                    cfg.get("image_caption_prompt") or "Please describe the image."
                )
                llm_resp = await prov.text_chat(
                    prompt=img_cap_prompt,
                    image_urls=[compress_path],
                )
                if llm_resp.completion_text:
                    content_parts.append(
                        f"[Image Caption in quoted message]: {llm_resp.completion_text}",
                    )
            else:
                logger.warning("No provider found for image captioning in quote.")
        except BaseException as exc:
            logger.error("处理引用图片失败: %s", exc)
        finally:
            if (
                compress_path
                and compress_path != path
                and await asyncio.to_thread(os.path.exists, compress_path)
            ):
                try:
                    await asyncio.to_thread(os.remove, compress_path)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Fail to remove temporary compressed image: %s", exc)

    quoted_content = "\n".join(content_parts)
    quoted_text = f"<Quoted Message>\n{quoted_content}\n</Quoted Message>"
    req.extra_user_content_parts.append(TextPart(text=quoted_text))


def _append_system_reminders(
    event: AstrMessageEvent,
    req: ProviderRequest,
    cfg: dict,
    timezone: str | None,
) -> None:
    system_parts: list[str] = []
    if cfg.get("identifier"):
        user_id = event.message_obj.sender.user_id
        user_nickname = event.message_obj.sender.nickname
        system_parts.append(f"User ID: {user_id}, Nickname: {user_nickname}")

    if cfg.get("group_name_display") and event.message_obj.group_id:
        if not event.message_obj.group:
            logger.error(
                "Group name display enabled but group object is None. Group ID: %s",
                event.message_obj.group_id,
            )
        else:
            group_name = event.message_obj.group.group_name
            if group_name:
                system_parts.append(f"Group name: {group_name}")

    if cfg.get("datetime_system_prompt"):
        current_time = None
        if timezone:
            try:
                now = datetime.datetime.now(zoneinfo.ZoneInfo(timezone))
                current_time = now.strftime("%Y-%m-%d %H:%M (%Z)")
            except Exception as exc:  # noqa: BLE001
                logger.error("时区设置错误: %s, 使用本地时区", exc)
        if not current_time:
            current_time = (
                datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M (%Z)")
            )
        system_parts.append(f"Current datetime: {current_time}")

    if system_parts:
        system_content = (
            "<system_reminder>" + "\n".join(system_parts) + "</system_reminder>"
        )
        req.extra_user_content_parts.append(TextPart(text=system_content))


def _inject_context_memory(
    event: AstrMessageEvent,
    req: ProviderRequest,
    cfg: dict,
) -> None:
    """Inject manually pinned top-level memories into system prompt.

    Vector retrieval enhancement is intentionally deferred to a follow-up PR.
    This function only handles manually configured pinned memories.
    """
    if not isinstance(cfg, dict):
        return
    cm_cfg = load_context_memory_config(cfg)
    memory_block = build_pinned_memory_system_block(cm_cfg)
    retrieved_facts = event.get_extra("retrieved_long_term_facts")
    summarized_history = event.get_extra("compacted_history_summary")
    req.system_prompt = assemble_system_prompt(
        base_system_prompt=req.system_prompt or "",
        retrieved_long_term_facts=retrieved_facts
        if isinstance(retrieved_facts, list)
        else None,
        summarized_history=summarized_history
        if isinstance(summarized_history, str)
        else "",
        pinned_memory_block=memory_block,
    )


async def _decorate_llm_request(
    event: AstrMessageEvent,
    req: ProviderRequest,
    plugin_context: Context,
    config: MainAgentBuildConfig,
) -> None:
    cfg = config.provider_settings or plugin_context.get_config(
        umo=event.unified_msg_origin,
    ).get("provider_settings", {})

    _apply_prompt_prefix(req, cfg)

    if req.conversation:
        await _ensure_persona_and_skills(req, cfg, plugin_context, event)

        img_cap_prov_id: str = cfg.get("default_image_caption_provider_id") or ""
        if img_cap_prov_id and req.image_urls:
            await _ensure_img_caption(
                event,
                req,
                cfg,
                plugin_context,
                img_cap_prov_id,
            )

    img_cap_prov_id = cfg.get("default_image_caption_provider_id") or ""
    quoted_message_settings = _get_quoted_message_parser_settings(cfg)
    await _process_quote_message(
        event,
        req,
        img_cap_prov_id,
        plugin_context,
        cfg,
        quoted_message_settings,
        config,
    )

    tz = config.timezone
    if tz is None:
        tz = plugin_context.get_config().get("timezone")
    _append_system_reminders(event, req, cfg, tz)
    _inject_context_memory(event, req, cfg)


def _plugin_tool_fix(
    event: AstrMessageEvent, req: ProviderRequest, cfg: dict | None = None
) -> _AwaitableNoop | Awaitable[None]:
    """根据事件中的插件设置，过滤请求中的工具列表。

    注意：没有 handler_module_path 的工具（如 MCP 工具）会被保留，
    因为它们不属于任何插件，不应被插件过滤逻辑影响。
    """
    if not req.func_tool:
        return _AwaitableNoop()
    if cfg is not None:
        session_id = req.session_id or event.unified_msg_origin
        req.func_tool = _filter_tools_for_current_config(req.func_tool, cfg, session_id)

    async def _apply_plugin_filters() -> None:
        if not req.func_tool:
            return
        session_id = event.unified_msg_origin
        session_plugin_config = await SessionPluginManager.get_session_plugin_config(
            session_id
        )
        session_disabled = set(session_plugin_config.get("disabled_plugins", []))

        global_whitelist = event.plugins_name  # None 表示全部允许

        new_tool_set = ToolSet()
        for tool in req.func_tool.tools:
            if isinstance(tool, MCPTool):
                # 保留 MCP 工具
                new_tool_set.add_tool(tool)
                continue
            mp = tool.handler_module_path
            if not mp:
                # 没有 plugin 归属信息的工具（如 subagent transfer_to_*）
                # 不应受到会话插件过滤影响。
                new_tool_set.add_tool(tool)
                continue
            plugin = star_map.get(mp)
            if not plugin:
                # 无法解析插件归属时，保守保留工具，避免误过滤。
                new_tool_set.add_tool(tool)
                continue
            if plugin.reserved:
                new_tool_set.add_tool(tool)
                continue
            # 全局白名单过滤
            if global_whitelist is not None and plugin.name not in global_whitelist:
                continue
            # 会话级禁用过滤
            if plugin.name in session_disabled:
                continue
            new_tool_set.add_tool(tool)
        req.func_tool = new_tool_set

    return _AwaitableFactory(_apply_plugin_filters)


async def _handle_webchat(
    event: AstrMessageEvent,
    req: ProviderRequest,
    prov: Provider,
) -> None:
    from astrbot.core import db_helper

    chatui_session_id = event.session_id.split("!")[-1]
    user_prompt = req.prompt
    session = await db_helper.get_platform_session_by_id(chatui_session_id)

    if not user_prompt or not chatui_session_id or not session or session.display_name:
        return

    try:
        llm_resp = await prov.text_chat(
            system_prompt=_TITLE_GEN_SYSTEM_PROMPT,
            prompt=_TITLE_GEN_USER_PROMPT_TEMPLATE.format(user_prompt=user_prompt),
        )
        if llm_resp and llm_resp.completion_text:
            title = llm_resp.completion_text.strip()
            # 精确匹配 <None>，避免误过滤合法标题
            if not title or title.lower() in ("<none>", "none"):
                return
            logger.info(
                "Generated chatui title for session %s: %s",
                chatui_session_id,
                title,
            )
            await db_helper.update_platform_session(
                session_id=chatui_session_id,
                display_name=title,
            )
    except Exception as e:
        logger.exception("Failed to generate chatui title: %s", e)


async def _handle_conversation_title(
    event: AstrMessageEvent,
    req: ProviderRequest,
    prov: Provider,
    conv_mgr: ConversationManager,
) -> None:
    """为非 WebChat 平台生成会话标题。

    使用 Conversation.title 存储标题。
    """
    try:  # 全局异常捕获，防止后台任务静默失败
        user_prompt = req.prompt
        umo = event.unified_msg_origin

        # 获取当前会话 ID
        cid = await _maybe_await(conv_mgr.get_curr_conversation_id(umo))
        if not cid or not user_prompt:
            return

        # 获取会话对象，检查是否已有标题
        conversation = await _maybe_await(conv_mgr.get_conversation(umo, cid))
        if not conversation:
            return

        # 如果已有标题，跳过生成
        if conversation.title:
            return

        try:
            llm_resp = await prov.text_chat(
                system_prompt=_TITLE_GEN_SYSTEM_PROMPT,
                prompt=_TITLE_GEN_USER_PROMPT_TEMPLATE.format(user_prompt=user_prompt),
            )
        except Exception as e:
            logger.exception(
                "Failed to generate conversation title for %s: %s",
                umo,
                e,
            )
            return

        if llm_resp and llm_resp.completion_text:
            title = llm_resp.completion_text.strip()
            # 精确匹配 <None>，避免误过滤合法标题
            if not title or title.lower() in ("<none>", "none"):
                return

            # 防止竞态条件：更新前再次检查标题是否已存在
            conversation = await _maybe_await(conv_mgr.get_conversation(umo, cid))
            if conversation and conversation.title:
                logger.debug(
                    "Conversation title already set for %s, skipping update", umo
                )
                return

            logger.info("Generated conversation title for %s: %s", umo, title)
            await _maybe_await(
                conv_mgr.update_conversation(
                    unified_msg_origin=umo,
                    conversation_id=cid,
                    title=title,
                )
            )
    except Exception as e:
        # 捕获所有未预期的异常，防止后台任务静默失败
        logger.exception(
            "Unexpected error in conversation title generation for %s: %s",
            event.unified_msg_origin,
            e,
        )


def _apply_llm_safety_mode(config: MainAgentBuildConfig, req: ProviderRequest) -> None:
    if config.safety_mode_strategy == "system_prompt":
        req.system_prompt = f"{LLM_SAFETY_MODE_SYSTEM_PROMPT}\n\n{req.system_prompt}"
    else:
        logger.warning(
            "Unsupported llm_safety_mode strategy: %s.",
            config.safety_mode_strategy,
        )


async def _apply_subagent_manager_tools(
    cfg: dict,
    req: ProviderRequest,
    event: AstrMessageEvent,
    so: SubAgentOrchestrator,
) -> None:
    """Apply SubAgent tools and system prompt

    When enabled:
    1. Inject subagent capability prompt into system prompt
    2. Register SubAgent management tools
    3. Register session's transfer_to_xxx tools
    """
    orch_cfg = cfg.get("subagent_orchestrator", {})

    if not orch_cfg.get("main_enable", False):
        return

    if req.func_tool is None:
        req.func_tool = ToolSet()

    try:
        from astrbot.core.subagent_tools import (
            BROADCAST_SHARED_CONTEXT_TOOL,
            CREATE_SUBAGENT_TOOL,
            LIST_SUBAGENTS_TOOL,
            MANAGE_SUBAGENT_PROTECTION_TOOL,
            REMOVE_SUBAGENT_TOOL,
            VIEW_SHARED_CONTEXT_TOOL,
            WAIT_FOR_SUBAGENT_TOOL,
        )

        # Configure SubAgentManager with settings from subagent_orchestrator
        dynamic_cfg = orch_cfg.get("dynamic_agents", {})
        enable_dynamic = dynamic_cfg.get("enabled", False)
        history_enabled = orch_cfg.get("history_enabled", True)
        shared_context_enabled = orch_cfg.get("shared_context_enabled", False)
        SubAgentManager.configure(
            max_subagent_count=dynamic_cfg.get("max_dynamic_subagent_count", 3),
            auto_cleanup_per_turn=dynamic_cfg.get("auto_cleanup_per_turn", True),
            shared_context_enabled=shared_context_enabled,
            shared_context_maxlen=orch_cfg.get("shared_context_maxlen", 300),
            subagent_history_maxlen=orch_cfg.get("subagent_history_maxlen", 300),
            tools_blacklist=dynamic_cfg.get("tools_blacklist", None),
            tools_inherent=dynamic_cfg.get("tools_inherent", None),
            execution_timeout=orch_cfg.get("execution_timeout", 1200),
            history_enabled=history_enabled,
            rule_prompt=dynamic_cfg.get("rule_prompt", ""),
            time_prompt_enabled=orch_cfg.get("time_prompt_enabled", True),
            timezone=cfg.get("timezone", None),
        )

        # Enable subagent history and shared context if configured
        SubAgentManager.set_history_enabled(event.unified_msg_origin, history_enabled)
        SubAgentManager.set_shared_context_enabled(
            event.unified_msg_origin, shared_context_enabled
        )

        session_id = event.unified_msg_origin
        # Register static subagents from config into SubAgentManager for unified management
        so.register_static_subagents_to_manager(session_id)

        # Register dynamic subagent management tools (only when dynamic creation is enabled)
        # Always register `wait_for_subagent` for better background task running
        req.func_tool.add_tool(WAIT_FOR_SUBAGENT_TOOL)
        if enable_dynamic:
            req.func_tool.add_tool(CREATE_SUBAGENT_TOOL)
            req.func_tool.add_tool(REMOVE_SUBAGENT_TOOL)
            req.func_tool.add_tool(LIST_SUBAGENTS_TOOL)
            # if SubAgentManager.is_history_enabled():   #
            #     req.func_tool.add_tool(RESET_SUBAGENT_TOOL)
            if SubAgentManager.is_auto_cleanup_per_turn():
                req.func_tool.add_tool(MANAGE_SUBAGENT_PROTECTION_TOOL)
            if SubAgentManager.is_shared_context_enabled():
                req.func_tool.add_tool(VIEW_SHARED_CONTEXT_TOOL)
                req.func_tool.add_tool(BROADCAST_SHARED_CONTEXT_TOOL)

            # Inject subagent capability system prompt for dynamic creation
            task_router_prompt = SubAgentManager.build_task_router_prompt(session_id)
            req.system_prompt = f"{req.system_prompt or ''}\n{task_router_prompt}\n"

        # Register dynamically created handoff tools
        dynamic_handoffs = SubAgentManager.get_handoff_tools_for_session(session_id)
        for handoff in dynamic_handoffs:
            req.func_tool.add_tool(handoff)
    except ImportError as e:
        logger.warning(f"[SubAgent] Cannot import module: {e}")


def _apply_sandbox_tools(
    config: MainAgentBuildConfig,
    req: ProviderRequest,
) -> None:
    if req.func_tool is None:
        req.func_tool = ToolSet()
    if req.system_prompt is None:
        req.system_prompt = ""
    tool_mgr = llm_tools
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(ExecuteShellTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(ListSandboxesTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(ListSandboxProvidersTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(GetCurrentSandboxTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(CreateSandboxTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(SwitchSandboxTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(KeepAliveSandboxTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(ReleaseSandboxTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(SetSandboxRetentionPolicyTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(TakeoverSandboxTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(DestroySandboxTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(ScreenshotSandboxTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(CopyFileBetweenSandboxesTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(PythonTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(FileUploadTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(FileDownloadTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(FileReadTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(FileWriteTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(FileEditTool))
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(GrepTool))
    req.system_prompt = f"{req.system_prompt or ''}\n{SANDBOX_MODE_PROMPT}\n"


def _proactive_cron_job_tools(req: ProviderRequest, plugin_context: Context) -> None:
    if req.func_tool is None:
        req.func_tool = ToolSet()
    tool_mgr = plugin_context.get_llm_tool_manager()
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(FutureTaskTool))


async def _apply_web_search_tools(
    event: AstrMessageEvent,
    req: ProviderRequest,
    plugin_context: Context,
) -> None:
    cfg = plugin_context.get_config(umo=event.unified_msg_origin)
    normalize_legacy_web_search_config(cfg)
    prov_settings = cfg.get("provider_settings", {})

    if not prov_settings.get("web_search", False):
        return

    if req.func_tool is None:
        req.func_tool = ToolSet()

    tool_mgr = plugin_context.get_llm_tool_manager()
    provider = prov_settings.get("websearch_provider", "tavily")
    if provider == "tavily":
        req.func_tool.add_tool(tool_mgr.get_builtin_tool(TavilyWebSearchTool))
        req.func_tool.add_tool(tool_mgr.get_builtin_tool(TavilyExtractWebPageTool))
    elif provider == "bocha":
        req.func_tool.add_tool(tool_mgr.get_builtin_tool(BochaWebSearchTool))
    elif provider == "brave":
        req.func_tool.add_tool(tool_mgr.get_builtin_tool(BraveWebSearchTool))
    elif provider == "baidu_ai_search":
        req.func_tool.add_tool(tool_mgr.get_builtin_tool(BaiduWebSearchTool))
    elif provider == "metaso":
        req.func_tool.add_tool(tool_mgr.get_builtin_tool(MetasoWebSearchTool))


def _get_compress_provider(
    config: MainAgentBuildConfig,
    plugin_context: Context,
    event: AstrMessageEvent | None = None,
) -> Provider | None:
    if config.context_limit_reached_strategy != "llm_compress":
        return None
    if config.llm_compress_provider_id:
        provider = plugin_context.get_provider_by_id(config.llm_compress_provider_id)
        if provider and isinstance(provider, Provider):
            return provider
        logger.warning(
            "指定的上下文压缩模型 %s 不可用",
            config.llm_compress_provider_id,
        )
    return None


def _get_fallback_chat_providers(
    provider: Provider,
    plugin_context: Context,
    provider_settings: dict,
) -> list[Provider]:
    fallback_ids = provider_settings.get("fallback_chat_models", [])
    if not isinstance(fallback_ids, list):
        logger.warning(
            "fallback_chat_models setting is not a list, skip fallback providers.",
        )
        return []

    fallback_providers: list[Provider] = []
    for provider_id in fallback_ids:
        try:
            fallback_provider = plugin_context.get_provider_by_id(str(provider_id))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to resolve fallback provider %s: %s", provider_id, exc
            )
            continue
        if fallback_provider and isinstance(fallback_provider, Provider):
            fallback_providers.append(fallback_provider)
    return fallback_providers


def _apply_global_context_info(event: AstrMessageEvent, req: ProviderRequest) -> None:
    if event.unified_msg_origin != GLOBAL_UNIFIED_CONTEXT_UMO:
        return

    original_umo = event.get_extra(ORIGINAL_UMO_KEY)
    if not original_umo:
        return

    try:
        parts = str(original_umo).split(":", 2)
        if len(parts) != 3:
            logger.warning(
                "Original UMO format is invalid (expected 3 parts): %s",
                original_umo,
            )
            return

        platform_id, message_type, session_id = parts
        context_info = (
            f"[Context: Platform={platform_id}, Type={message_type}, "
            f"Session={session_id}]"
        )
        req.prompt = f"{context_info} {req.prompt or ''}".strip()
    except Exception as e:
        logger.warning("Failed to parse original UMO for global context: %s", e)


def _provider_supports_modality(provider: Provider, modality: str) -> bool:
    modalities = provider.provider_config.get("modalities", None)
    return isinstance(modalities, list) and modality in modalities


def _modalities_fix(provider: Provider, req: ProviderRequest) -> None:
    modalities = provider.provider_config.get("modalities", None)
    if not isinstance(modalities, list) or not modalities:
        return
    if req.image_urls and "image" not in modalities:
        req.image_urls = []
        req.prompt = f"{req.prompt or ''}\n[图片]".strip()
    if req.func_tool and "tool_use" not in modalities:
        req.func_tool = None


def _sanitize_context_by_modalities(
    config: MainAgentBuildConfig,
    provider: Provider,
    req: ProviderRequest,
) -> None:
    if not config.sanitize_context_by_modalities:
        return
    modalities = provider.provider_config.get("modalities", None)
    if not isinstance(modalities, list) or not modalities:
        return

    supports_tool = "tool_use" in modalities
    supports_image = "image" in modalities
    sanitized_contexts = []
    for item in req.contexts or []:
        if not isinstance(item, dict):
            sanitized_contexts.append(item)
            continue
        if not supports_tool and item.get("role") == "tool":
            continue
        copied = copy.deepcopy(item)
        if not supports_tool:
            copied.pop("tool_calls", None)
        content = copied.get("content")
        if not supports_image and isinstance(content, list):
            copied["content"] = [
                part
                for part in content
                if not (isinstance(part, dict) and part.get("type") == "image_url")
            ]
        sanitized_contexts.append(copied)
    req.contexts = sanitized_contexts


def _select_image_chat_provider(
    provider: Provider,
    req: ProviderRequest,
    fallback_providers: list[Provider],
) -> Provider:
    if not req.image_urls or _provider_supports_modality(provider, "image"):
        return provider

    provider_id = provider.provider_config.get("id", "<unknown>")
    for fallback_provider in fallback_providers:
        if not _provider_supports_modality(fallback_provider, "image"):
            continue
        fallback_id = fallback_provider.provider_config.get("id", "<unknown>")
        logger.warning(
            "Chat provider %s does not support image input, switching this request to fallback provider %s.",
            provider_id,
            fallback_id,
        )
        return fallback_provider

    logger.warning(
        "Chat provider %s does not support image input and no image-capable fallback provider is available.",
        provider_id,
    )
    return provider


async def build_main_agent(
    *,
    event: AstrMessageEvent,
    plugin_context: Context,
    config: MainAgentBuildConfig,
    provider: Provider | None = None,
    req: ProviderRequest | None = None,
    apply_reset: bool = True,
) -> MainAgentBuildResult | None:
    """构建主对话代理（Main Agent），并且自动 reset。

    If apply_reset is False, will not call reset on the agent runner.
    """
    logger.debug(f"req received in build_main_agent: {req}")
    provider = provider or _select_provider(event, plugin_context)
    if provider is None:
        logger.info("未找到任何对话模型（提供商），跳过 LLM 请求处理。")
        if not event.get_extra(LLM_ERROR_MESSAGE_EXTRA_KEY):
            _set_llm_error_message(
                event,
                "LLM 请求失败：未找到任何可用的对话模型（提供商）。请先在 WebUI 中配置并启用可用模型。",
            )
        return None

    if req is None:
        if event.get_extra("provider_request"):
            logger.debug("Using existing provider_request from event extras.")
            req = event.get_extra("provider_request")
            assert isinstance(req, ProviderRequest), (
                "provider_request 必须是 ProviderRequest 类型。"
            )
            if req.conversation:
                req.contexts = json.loads(req.conversation.history)
            for comp in event.message_obj.message:
                if isinstance(comp, Image):
                    req.image_urls.append(await _resolve_image_component_ref(comp))
                elif isinstance(comp, File):
                    file_path = await comp.get_file()
                    file_name = comp.name or os.path.basename(file_path)
                    req.extra_user_content_parts.append(
                        TextPart(
                            text=f"[File Attachment: name {file_name}, path {file_path}]"
                        )
                    )
        else:
            req = ProviderRequest()
            req.prompt = ""
            req.image_urls = []
            req.audio_urls = []
            if sel_model := event.get_extra("selected_model"):
                req.model = sel_model
            if config.provider_wake_prefix and not event.message_str.startswith(
                config.provider_wake_prefix,
            ):
                return None

            req.prompt = event.message_str[len(config.provider_wake_prefix) :]

            conversation = await _get_session_conv(event, plugin_context)
            req.conversation = conversation
            req.contexts = json.loads(conversation.history)
            event.set_extra("provider_request", req)

        # media files attachments (always process, regardless of req source)
        for comp in event.message_obj.message:
            if isinstance(comp, Image):
                path = await comp.convert_to_file_path()
                image_path = await _compress_image_for_provider(
                    path,
                    config.provider_settings,
                )
                if _is_generated_compressed_image_path(path, image_path):
                    event.track_temporary_local_file(image_path)
                image_ref = await _resolve_image_component_ref(comp)
                req.image_urls.append(image_ref if image_path == path else image_path)
                req.extra_user_content_parts.append(
                    TextPart(text=f"[Image Attachment: path {image_ref}]")
                )
            elif isinstance(comp, Record):
                audio_path = await comp.convert_to_file_path()
                req.audio_urls.append(audio_path)
                _append_audio_attachment(req, audio_path)
            elif isinstance(comp, File):
                file_path = await comp.get_file()
                file_name = comp.name or os.path.basename(file_path)
                req.extra_user_content_parts.append(
                    TextPart(
                        text=f"[File Attachment: name {file_name}, path {file_path}]"
                    )
                )
            elif isinstance(comp, Video):
                await _append_video_attachment(req, comp)
        # quoted message attachments
        reply_comps = [
            comp for comp in event.message_obj.message if isinstance(comp, Reply)
        ]
        quoted_message_settings = _get_quoted_message_parser_settings(
            config.provider_settings
        )
        cfg = config.provider_settings or plugin_context.get_config(
            umo=event.unified_msg_origin
        ).get("provider_settings", {})
        img_cap_prov_id = cfg.get("default_image_caption_provider_id") or ""
        fallback_quoted_image_count = 0
        for comp in reply_comps:
            has_embedded_image = False
            if comp.chain:
                for reply_comp in comp.chain:
                    if isinstance(reply_comp, Image):
                        has_embedded_image = True
                        path = await reply_comp.convert_to_file_path()
                        image_path = await _compress_image_for_provider(
                            path,
                            config.provider_settings,
                        )
                        if _is_generated_compressed_image_path(path, image_path):
                            event.track_temporary_local_file(image_path)
                        if not img_cap_prov_id:
                            req.image_urls.append(image_path)
                        _append_quoted_image_attachment(req, image_path)
                    elif isinstance(reply_comp, Record):
                        audio_path = await reply_comp.convert_to_file_path()
                        req.audio_urls.append(audio_path)
                        _append_quoted_audio_attachment(req, audio_path)
                    elif isinstance(reply_comp, File):
                        file_path = await reply_comp.get_file()
                        file_name = reply_comp.name or os.path.basename(file_path)
                        req.extra_user_content_parts.append(
                            TextPart(
                                text=(
                                    f"[File Attachment in quoted message: "
                                    f"name {file_name}, path {file_path}]"
                                )
                            )
                        )
                    elif isinstance(reply_comp, Video):
                        await _append_video_attachment(req, reply_comp, quoted=True)

            # Fallback quoted image extraction for reply-id-only payloads, or when
            # embedded reply chain only contains placeholders (e.g. [Forward Message], [Image]).
            if not has_embedded_image:
                try:
                    fallback_images = normalize_and_dedupe_strings(
                        await extract_quoted_message_images(
                            event,
                            comp,
                            settings=quoted_message_settings,
                        )
                    )
                    remaining_limit = max(
                        config.max_quoted_fallback_images - fallback_quoted_image_count,
                        0,
                    )
                    if remaining_limit <= 0 and fallback_images:
                        logger.warning(
                            "Skip quoted fallback images due to limit=%d for umo=%s",
                            config.max_quoted_fallback_images,
                            event.unified_msg_origin,
                        )
                        continue
                    if len(fallback_images) > remaining_limit:
                        logger.warning(
                            "Truncate quoted fallback images for umo=%s, reply_id=%s from %d to %d",
                            event.unified_msg_origin,
                            getattr(comp, "id", None),
                            len(fallback_images),
                            remaining_limit,
                        )
                        fallback_images = fallback_images[:remaining_limit]
                    for image_ref in fallback_images:
                        if image_ref in req.image_urls:
                            continue
                        if not img_cap_prov_id:
                            req.image_urls.append(image_ref)
                        fallback_quoted_image_count += 1
                        _append_quoted_image_attachment(req, image_ref)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Failed to resolve fallback quoted images for umo=%s, reply_id=%s: %s",
                        event.unified_msg_origin,
                        getattr(comp, "id", None),
                        exc,
                        exc_info=True,
                    )

    if isinstance(req.contexts, str):
        req.contexts = json.loads(req.contexts)
    thread_selected_text = event.get_extra("thread_selected_text")
    if isinstance(thread_selected_text, str) and thread_selected_text.strip():
        req.extra_user_content_parts.append(
            TextPart(
                text=(
                    "The user is asking in a side thread about this selected "
                    "excerpt from the previous assistant answer:\n"
                    f"<selected_excerpt>{thread_selected_text.strip()}</selected_excerpt>"
                ),
            ),
        )
    req.image_urls = normalize_and_dedupe_strings(req.image_urls)
    req.audio_urls = normalize_and_dedupe_strings(req.audio_urls)

    # Apply global context information if enabled
    _apply_global_context_info(event, req)

    if config.file_extract_enabled:
        try:
            await _apply_file_extract(event, req, config)
        except Exception as exc:  # noqa: BLE001
            logger.error("Error occurred while applying file extract: %s", exc)

    if not req.prompt and not req.image_urls and not req.audio_urls:
        if not event.get_group_id() and req.extra_user_content_parts:
            req.prompt = "<attachment>"
        else:
            return None

    await _decorate_llm_request(event, req, plugin_context, config)

    await _apply_kb(event, req, plugin_context, config)

    if not req.session_id:
        req.session_id = event.unified_msg_origin

    await _plugin_tool_fix(event, req, config.provider_settings)
    await _apply_web_search_tools(event, req, plugin_context)

    if config.llm_safety_mode:
        _apply_llm_safety_mode(config, req)

    if config.computer_use_runtime == "sandbox":
        _apply_sandbox_tools(config, req)
    elif config.computer_use_runtime == "local":
        _apply_local_env_tools(req, plugin_context)

    agent_runner = AgentRunner()
    astr_agent_ctx = AstrAgentContext(
        context=plugin_context, event=event, extra={"main_agent_runner": agent_runner}
    )

    if config.add_cron_tools:
        _proactive_cron_job_tools(req, plugin_context)

    if event.platform_meta.support_proactive_message:
        if req.func_tool is None:
            req.func_tool = ToolSet()
        req.func_tool.add_tool(
            plugin_context.get_llm_tool_manager().get_builtin_tool(
                "send_message_to_user",
            ),
        )

    fallback_providers = _get_fallback_chat_providers(
        provider, plugin_context, config.provider_settings
    )
    selected_provider = _select_image_chat_provider(provider, req, fallback_providers)
    if selected_provider is not provider:
        provider = selected_provider
        if req.model:
            req.model = None
        fallback_providers = [p for p in fallback_providers if p is not provider]

    if provider.provider_config.get("max_context_tokens", 0) <= 0:
        model = provider.get_model()
        if model_info := LLM_METADATAS.get(model):
            provider.provider_config["max_context_tokens"] = model_info["limit"][
                "context"
            ]
        else:
            # fallback: default to configured fallback value
            provider.provider_config["max_context_tokens"] = (
                config.fallback_max_context_tokens
            )

    _sanitize_context_by_modalities(config, provider, req)

    if event.get_platform_name() == "webchat":
        asyncio.create_task(_handle_webchat(event, req, provider))
    else:
        # 为其他平台生成会话标题（使用 Conversation.title）
        asyncio.create_task(
            _handle_conversation_title(
                event, req, provider, plugin_context.conversation_manager
            )
        )

    if req.func_tool and req.func_tool.tools:
        if config.tool_schema_mode == "skills_like":
            tool_prompt = TOOL_CALL_PROMPT_SKILLS_LIKE_MODE
        elif config.tool_schema_mode in ("tool_search", "auto"):
            # tool_search/auto prompt is injected by the runner AFTER mode resolution
            # in reset(). Injecting here would double-inject or inject for auto→full fallback.
            tool_prompt = TOOL_CALL_PROMPT
        else:
            tool_prompt = TOOL_CALL_PROMPT
        req.system_prompt += f"\n{tool_prompt}\n"

    action_type = event.get_extra("action_type")
    if action_type == "live":
        req.system_prompt += f"\n{LIVE_MODE_SYSTEM_PROMPT}\n"

    reset_coro = agent_runner.reset(
        provider=provider,
        request=req,
        run_context=AgentContextWrapper(
            context=astr_agent_ctx,
            tool_call_timeout=config.tool_call_timeout,
            tool_call_approval=config.tool_call_approval,
        ),
        tool_executor=FunctionToolExecutor(),
        agent_hooks=MAIN_AGENT_HOOKS,
        streaming=config.streaming_response,
        llm_compress_instruction=config.llm_compress_instruction,
        llm_compress_keep_recent=config.llm_compress_keep_recent,
        llm_compress_provider=_get_compress_provider(config, plugin_context, event),
        llm_compress_use_compact_api=config.llm_compress_use_compact_api,
        truncate_turns=config.dequeue_context_length,
        token_counter_mode=config.context_token_counter_mode,
        token_counter_model=provider.get_model() if provider else None,
        compact_context_after_tool_call=config.compact_context_after_tool_call,
        compact_context_soft_ratio=config.compact_context_soft_ratio,
        compact_context_hard_ratio=config.compact_context_hard_ratio,
        compact_context_min_delta_tokens=config.compact_context_min_delta_tokens,
        compact_context_min_delta_turns=config.compact_context_min_delta_turns,
        compact_context_debounce_seconds=config.compact_context_debounce_seconds,
        tool_schema_mode=config.tool_schema_mode,
        fallback_providers=fallback_providers,
        tool_result_overflow_dir=(
            get_astrbot_system_tmp_path()
            if req.func_tool and req.func_tool.get_tool("astrbot_file_read_tool")
            else None
        ),
        read_tool=(
            req.func_tool.get_tool("astrbot_file_read_tool") if req.func_tool else None
        ),
        tool_search_config=config.provider_settings.get("tool_search", {}),
    )

    if apply_reset:
        await reset_coro

    return MainAgentBuildResult(
        agent_runner=agent_runner,
        provider_request=req,
        provider=provider,
        reset_coro=reset_coro if not apply_reset else None,
    )


apply_sandbox_tools = _apply_sandbox_tools
