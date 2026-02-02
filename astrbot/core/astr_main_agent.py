from __future__ import annotations

import asyncio
import builtins
import copy
import datetime
import json
import os
import zoneinfo
from dataclasses import dataclass, field

from astrbot.api import sp
from astrbot.core import logger
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.agent.message import TextPart
from astrbot.core.agent.tool import ToolSet
from astrbot.core.astr_agent_context import AgentContextWrapper, AstrAgentContext
from astrbot.core.astr_agent_hooks import MAIN_AGENT_HOOKS
from astrbot.core.astr_agent_run_util import AgentRunner
from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
from astrbot.core.astr_main_agent_resources import (
    CHATUI_EXTRA_PROMPT,
    CHATUI_SPECIAL_DEFAULT_PERSONA_PROMPT,
    EXECUTE_SHELL_TOOL,
    FILE_DOWNLOAD_TOOL,
    FILE_UPLOAD_TOOL,
    KNOWLEDGE_BASE_QUERY_TOOL,
    LIVE_MODE_SYSTEM_PROMPT,
    LLM_SAFETY_MODE_SYSTEM_PROMPT,
    LOCAL_EXECUTE_SHELL_TOOL,
    LOCAL_PYTHON_TOOL,
    PYTHON_TOOL,
    SANDBOX_MODE_PROMPT,
    SEND_MESSAGE_TO_USER_TOOL,
    TOOL_CALL_PROMPT,
    TOOL_CALL_PROMPT_SKILLS_LIKE_MODE,
    retrieve_knowledge_base,
)
from astrbot.core.conversation_mgr import Conversation
from astrbot.core.message.components import File, Image, Reply
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider import Provider
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.skills.skill_manager import SkillManager, build_skills_prompt
from astrbot.core.star.context import Context
from astrbot.core.star.star_handler import star_map
from astrbot.core.tools.cron_tools import (
    CREATE_CRON_JOB_TOOL,
    DELETE_CRON_JOB_TOOL,
    LIST_CRON_JOBS_TOOL,
)
from astrbot.core.utils.file_extract import extract_file_moonshotai
from astrbot.core.utils.llm_metadata import LLM_METADATAS


@dataclass(slots=True)
class MainAgentBuildConfig:
    """The main agent build configuration.
    Most of the configs can be found in the cmd_config.json"""

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
    max_context_length: int = -1
    """The maximum number of turns to keep in context. -1 means no limit.
    This enforce max turns before compression"""
    dequeue_context_length: int = 1
    """The number of oldest turns to remove when context length limit is reached."""
    llm_safety_mode: bool = True
    """This will inject healthy and safe system prompt into the main agent,
    to prevent LLM output harmful information"""
    safety_mode_strategy: str = "system_prompt"
    sandbox_cfg: dict = field(default_factory=dict)
    add_cron_tools: bool = True
    """This will add cron job management tools to the main agent for proactive cron job execution."""
    provider_settings: dict = field(default_factory=dict)
    subagent_orchestrator: dict = field(default_factory=dict)
    timezone: str | None = None


@dataclass(slots=True)
class MainAgentBuildResult:
    agent_runner: AgentRunner
    provider_request: ProviderRequest
    provider: Provider


def _select_provider(
    event: AstrMessageEvent, plugin_context: Context
) -> Provider | None:
    """Select chat provider for the event."""
    sel_provider = event.get_extra("selected_provider")
    if sel_provider and isinstance(sel_provider, str):
        provider = plugin_context.get_provider_by_id(sel_provider)
        if not provider:
            logger.error("未找到指定的提供商: %s。", sel_provider)
        if not isinstance(provider, Provider):
            logger.error(
                "选择的提供商类型无效(%s)，跳过 LLM 请求处理。", type(provider)
            )
            return None
        return provider
    try:
        return plugin_context.get_using_provider(umo=event.unified_msg_origin)
    except ValueError as exc:
        logger.error("Error occurred while selecting provider: %s", exc)
        return None


async def _get_session_conv(
    event: AstrMessageEvent, plugin_context: Context
) -> Conversation:
    conv_mgr = plugin_context.conversation_manager
    umo = event.unified_msg_origin
    cid = await conv_mgr.get_curr_conversation_id(umo)
    if not cid:
        cid = await conv_mgr.new_conversation(umo, event.get_platform_id())
    conversation = await conv_mgr.get_conversation(umo, cid)
    if not conversation:
        cid = await conv_mgr.new_conversation(umo, event.get_platform_id())
        conversation = await conv_mgr.get_conversation(umo, cid)
    if not conversation:
        raise RuntimeError("无法创建新的对话。")
    return conversation


async def _apply_kb(
    event: AstrMessageEvent,
    req: ProviderRequest,
    plugin_context: Context,
    config: MainAgentBuildConfig,
) -> None:
    if not config.kb_agentic_mode:
        if req.prompt is None:
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
        req.func_tool.add_tool(KNOWLEDGE_BASE_QUERY_TOOL)


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
            ]
        )
    else:
        logger.error("Unsupported file extract provider: %s", config.file_extract_prov)
        return

    for file_content, file_name in zip(file_contents, file_names):
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


def _apply_local_env_tools(req: ProviderRequest) -> None:
    if req.func_tool is None:
        req.func_tool = ToolSet()
    req.func_tool.add_tool(LOCAL_EXECUTE_SHELL_TOOL)
    req.func_tool.add_tool(LOCAL_PYTHON_TOOL)


async def _ensure_persona_and_skills(
    req: ProviderRequest,
    cfg: dict,
    plugin_context: Context,
    event: AstrMessageEvent,
) -> None:
    """Ensure persona and skills are applied to the request's system prompt or user prompt."""
    if not req.conversation:
        return

    # get persona ID
    persona_id = (
        await sp.get_async(
            scope="umo",
            scope_id=event.unified_msg_origin,
            key="session_service_config",
            default={},
        )
    ).get("persona_id")

    if not persona_id:
        persona_id = req.conversation.persona_id or cfg.get("default_personality")
        if persona_id is None or persona_id != "[%None]":
            default_persona = plugin_context.persona_manager.selected_default_persona_v3
            if default_persona:
                persona_id = default_persona["name"]
                if event.get_platform_name() == "webchat":
                    persona_id = "_chatui_default_"
                    req.system_prompt += CHATUI_SPECIAL_DEFAULT_PERSONA_PROMPT

    persona = next(
        builtins.filter(
            lambda persona: persona["name"] == persona_id,
            plugin_context.persona_manager.personas_v3,
        ),
        None,
    )
    if persona:
        # Inject persona system prompt
        if prompt := persona["prompt"]:
            req.system_prompt += f"\n# Persona Instructions\n\n{prompt}\n"
        if begin_dialogs := copy.deepcopy(persona.get("_begin_dialogs_processed")):
            req.contexts[:0] = begin_dialogs

    # Inject skills prompt
    skills_cfg = cfg.get("skills", {})
    sandbox_cfg = cfg.get("sandbox", {})
    skill_manager = SkillManager()
    runtime = skills_cfg.get("runtime", "local")
    skills = skill_manager.list_skills(active_only=True, runtime=runtime)

    if runtime == "sandbox" and not sandbox_cfg.get("enable", False):
        logger.warning(
            "Skills runtime is set to sandbox, but sandbox mode is disabled, will skip skills prompt injection.",
        )
        req.system_prompt += (
            "\n[Background: User added some skills, and skills runtime is set to sandbox, "
            "but sandbox mode is disabled. So skills will be unavailable.]\n"
        )
    elif skills:
        if persona and persona.get("skills") is not None:
            if not persona["skills"]:
                skills = []
            else:
                allowed = set(persona["skills"])
                skills = [skill for skill in skills if skill.name in allowed]
        if skills:
            req.system_prompt += f"\n{build_skills_prompt(skills)}\n"

        runtime = skills_cfg.get("runtime", "local")
        sandbox_enabled = sandbox_cfg.get("enable", False)
        if runtime == "local" and not sandbox_enabled:
            _apply_local_env_tools(req)

    tmgr = plugin_context.get_llm_tool_manager()

    # sub agents integration
    orch_cfg = plugin_context.get_config().get("subagent_orchestrator", {})
    so = plugin_context.subagent_orchestrator
    if orch_cfg.get("main_enable", False) and so:
        remove_dup = bool(orch_cfg.get("remove_main_duplicate_tools", False))

        assigned_tools: set[str] = set()
        agents = orch_cfg.get("agents", [])
        if isinstance(agents, list):
            for a in agents:
                if not isinstance(a, dict):
                    continue
                if a.get("enabled", True) is False:
                    continue
                persona_tools = None
                pid = a.get("persona_id")
                if pid:
                    persona_tools = next(
                        (
                            p.get("tools")
                            for p in plugin_context.persona_manager.personas_v3
                            if p["name"] == pid
                        ),
                        None,
                    )
                tools = a.get("tools", [])
                if persona_tools is not None:
                    tools = persona_tools
                if tools is None:
                    assigned_tools.update(
                        [
                            tool.name
                            for tool in tmgr.func_list
                            if not isinstance(tool, HandoffTool)
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
            toolset = ToolSet()
        else:
            toolset = req.func_tool

        # add subagent handoff tools
        for tool in so.handoffs:
            toolset.add_tool(tool)

        # check duplicates
        if remove_dup:
            names = toolset.names()
            for tool_name in assigned_tools:
                if tool_name in names:
                    toolset.remove_tool(tool_name)

        req.func_tool = toolset

        router_prompt = (
            plugin_context.get_config()
            .get("subagent_orchestrator", {})
            .get("router_system_prompt", "")
        ).strip()
        if router_prompt:
            req.system_prompt += f"\n{router_prompt}\n"
        return

    # inject toolset in the persona
    if (persona and persona.get("tools") is None) or not persona:
        toolset = tmgr.get_full_tool_set()
        for tool in list(toolset):
            if not tool.active:
                toolset.remove_tool(tool.name)
    else:
        toolset = ToolSet()
        if persona["tools"]:
            for tool_name in persona["tools"]:
                tool = tmgr.get_func(tool_name)
                if tool and tool.active:
                    toolset.add_tool(tool)
    if not req.func_tool:
        req.func_tool = toolset
    else:
        req.func_tool.merge(toolset)
    try:
        event.trace.record(
            "sel_persona", persona_id=persona_id, persona_toolset=toolset.names()
        )
    except Exception:
        pass
    logger.debug("Tool set for persona %s: %s", persona_id, toolset.names())


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


async def _ensure_img_caption(
    req: ProviderRequest,
    cfg: dict,
    plugin_context: Context,
    image_caption_provider: str,
) -> None:
    try:
        caption = await _request_img_caption(
            image_caption_provider,
            cfg,
            req.image_urls,
            plugin_context,
        )
        if caption:
            req.extra_user_content_parts.append(
                TextPart(text=f"<image_caption>{caption}</image_caption>")
            )
            req.image_urls = []
    except Exception as exc:  # noqa: BLE001
        logger.error("处理图片描述失败: %s", exc)


async def _process_quote_message(
    event: AstrMessageEvent,
    req: ProviderRequest,
    img_cap_prov_id: str,
    plugin_context: Context,
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
    message_str = quote.message_str or "[Empty Text]"
    content_parts.append(f"{sender_info}{message_str}")

    image_seg = None
    if quote.chain:
        for comp in quote.chain:
            if isinstance(comp, Image):
                image_seg = comp
                break

    if image_seg:
        try:
            prov = None
            if img_cap_prov_id:
                prov = plugin_context.get_provider_by_id(img_cap_prov_id)
            if prov is None:
                prov = plugin_context.get_using_provider(event.unified_msg_origin)

            if prov and isinstance(prov, Provider):
                llm_resp = await prov.text_chat(
                    prompt="Please describe the image content.",
                    image_urls=[await image_seg.convert_to_file_path()],
                )
                if llm_resp.completion_text:
                    content_parts.append(
                        f"[Image Caption in quoted message]: {llm_resp.completion_text}"
                    )
            else:
                logger.warning("No provider found for image captioning in quote.")
        except BaseException as exc:
            logger.error("处理引用图片失败: %s", exc)

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


async def _decorate_llm_request(
    event: AstrMessageEvent,
    req: ProviderRequest,
    plugin_context: Context,
    config: MainAgentBuildConfig,
) -> None:
    cfg = config.provider_settings or plugin_context.get_config(
        umo=event.unified_msg_origin
    ).get("provider_settings", {})

    _apply_prompt_prefix(req, cfg)

    if req.conversation:
        await _ensure_persona_and_skills(req, cfg, plugin_context, event)

        img_cap_prov_id: str = cfg.get("default_image_caption_provider_id") or ""
        if img_cap_prov_id and req.image_urls:
            await _ensure_img_caption(
                req,
                cfg,
                plugin_context,
                img_cap_prov_id,
            )

    img_cap_prov_id = cfg.get("default_image_caption_provider_id") or ""
    await _process_quote_message(
        event,
        req,
        img_cap_prov_id,
        plugin_context,
    )

    tz = config.timezone
    if tz is None:
        tz = plugin_context.get_config().get("timezone")
    _append_system_reminders(event, req, cfg, tz)


def _modalities_fix(provider: Provider, req: ProviderRequest) -> None:
    if req.image_urls:
        provider_cfg = provider.provider_config.get("modalities", ["image"])
        if "image" not in provider_cfg:
            logger.debug(
                "Provider %s does not support image, using placeholder.", provider
            )
            image_count = len(req.image_urls)
            placeholder = " ".join(["[图片]"] * image_count)
            if req.prompt:
                req.prompt = f"{placeholder} {req.prompt}"
            else:
                req.prompt = placeholder
            req.image_urls = []
    if req.func_tool:
        provider_cfg = provider.provider_config.get("modalities", ["tool_use"])
        if "tool_use" not in provider_cfg:
            logger.debug(
                "Provider %s does not support tool_use, clearing tools.", provider
            )
            req.func_tool = None


def _sanitize_context_by_modalities(
    config: MainAgentBuildConfig,
    provider: Provider,
    req: ProviderRequest,
) -> None:
    if not config.sanitize_context_by_modalities:
        return
    if not isinstance(req.contexts, list) or not req.contexts:
        return
    modalities = provider.provider_config.get("modalities", None)
    if not modalities or not isinstance(modalities, list):
        return
    supports_image = bool("image" in modalities)
    supports_tool_use = bool("tool_use" in modalities)
    if supports_image and supports_tool_use:
        return

    sanitized_contexts: list[dict] = []
    removed_image_blocks = 0
    removed_tool_messages = 0
    removed_tool_calls = 0

    for msg in req.contexts:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        if not role:
            continue

        new_msg = msg
        if not supports_tool_use:
            if role == "tool":
                removed_tool_messages += 1
                continue
            if role == "assistant" and "tool_calls" in new_msg:
                if "tool_calls" in new_msg:
                    removed_tool_calls += 1
                new_msg.pop("tool_calls", None)
                new_msg.pop("tool_call_id", None)

        if not supports_image:
            content = new_msg.get("content")
            if isinstance(content, list):
                filtered_parts: list = []
                removed_any_image = False
                for part in content:
                    if isinstance(part, dict):
                        part_type = str(part.get("type", "")).lower()
                        if part_type in {"image_url", "image"}:
                            removed_any_image = True
                            removed_image_blocks += 1
                            continue
                    filtered_parts.append(part)
                if removed_any_image:
                    new_msg["content"] = filtered_parts

        if role == "assistant":
            content = new_msg.get("content")
            has_tool_calls = bool(new_msg.get("tool_calls"))
            if not has_tool_calls:
                if not content:
                    continue
                if isinstance(content, str) and not content.strip():
                    continue

        sanitized_contexts.append(new_msg)

    if removed_image_blocks or removed_tool_messages or removed_tool_calls:
        logger.debug(
            "sanitize_context_by_modalities applied: "
            "removed_image_blocks=%s, removed_tool_messages=%s, removed_tool_calls=%s",
            removed_image_blocks,
            removed_tool_messages,
            removed_tool_calls,
        )
    req.contexts = sanitized_contexts


def _plugin_tool_fix(event: AstrMessageEvent, req: ProviderRequest) -> None:
    """根据事件中的插件设置，过滤请求中的工具列表。

    注意：没有 handler_module_path 的工具（如 MCP 工具）会被保留，
    因为它们不属于任何插件，不应被插件过滤逻辑影响。
    """
    if event.plugins_name is not None and req.func_tool:
        new_tool_set = ToolSet()
        for tool in req.func_tool.tools:
            mp = tool.handler_module_path
            if not mp:
                # 保留没有 handler_module_path 的工具（如 MCP 工具）
                new_tool_set.add_tool(tool)
                continue
            plugin = star_map.get(mp)
            if not plugin:
                continue
            if plugin.name in event.plugins_name or plugin.reserved:
                new_tool_set.add_tool(tool)
        req.func_tool = new_tool_set


async def _handle_webchat(
    event: AstrMessageEvent, req: ProviderRequest, prov: Provider
) -> None:
    from astrbot.core import db_helper

    chatui_session_id = event.session_id.split("!")[-1]
    user_prompt = req.prompt
    session = await db_helper.get_platform_session_by_id(chatui_session_id)

    if not user_prompt or not chatui_session_id or not session or session.display_name:
        return

    llm_resp = await prov.text_chat(
        system_prompt=(
            "You are a conversation title generator. "
            "Generate a concise title in the same language as the user’s input, "
            "no more than 10 words, capturing only the core topic."
            "If the input is a greeting, small talk, or has no clear topic, "
            "(e.g., “hi”, “hello”, “haha”), return <None>. "
            "Output only the title itself or <None>, with no explanations."
        ),
        prompt=f"Generate a concise title for the following user query:\n{user_prompt}",
    )
    if llm_resp and llm_resp.completion_text:
        title = llm_resp.completion_text.strip()
        if not title or "<None>" in title:
            return
        logger.info(
            "Generated chatui title for session %s: %s", chatui_session_id, title
        )
        await db_helper.update_platform_session(
            session_id=chatui_session_id,
            display_name=title,
        )


def _apply_llm_safety_mode(config: MainAgentBuildConfig, req: ProviderRequest) -> None:
    if config.safety_mode_strategy == "system_prompt":
        req.system_prompt = (
            f"{LLM_SAFETY_MODE_SYSTEM_PROMPT}\n\n{req.system_prompt or ''}"
        )
    else:
        logger.warning(
            "Unsupported llm_safety_mode strategy: %s.",
            config.safety_mode_strategy,
        )


def _apply_sandbox_tools(
    config: MainAgentBuildConfig, req: ProviderRequest, session_id: str
) -> None:
    if req.func_tool is None:
        req.func_tool = ToolSet()
    if config.sandbox_cfg.get("booter") == "shipyard":
        ep = config.sandbox_cfg.get("shipyard_endpoint", "")
        at = config.sandbox_cfg.get("shipyard_access_token", "")
        if not ep or not at:
            logger.error("Shipyard sandbox configuration is incomplete.")
            return
        os.environ["SHIPYARD_ENDPOINT"] = ep
        os.environ["SHIPYARD_ACCESS_TOKEN"] = at
    req.func_tool.add_tool(EXECUTE_SHELL_TOOL)
    req.func_tool.add_tool(PYTHON_TOOL)
    req.func_tool.add_tool(FILE_UPLOAD_TOOL)
    req.func_tool.add_tool(FILE_DOWNLOAD_TOOL)
    req.system_prompt += f"\n{SANDBOX_MODE_PROMPT}\n"


def _proactive_cron_job_tools(req: ProviderRequest) -> None:
    if req.func_tool is None:
        req.func_tool = ToolSet()
    req.func_tool.add_tool(CREATE_CRON_JOB_TOOL)
    req.func_tool.add_tool(DELETE_CRON_JOB_TOOL)
    req.func_tool.add_tool(LIST_CRON_JOBS_TOOL)


def _get_compress_provider(
    config: MainAgentBuildConfig, plugin_context: Context
) -> Provider | None:
    if not config.llm_compress_provider_id:
        return None
    if config.context_limit_reached_strategy != "llm_compress":
        return None
    provider = plugin_context.get_provider_by_id(config.llm_compress_provider_id)
    if provider is None:
        logger.warning(
            "未找到指定的上下文压缩模型 %s，将跳过压缩。",
            config.llm_compress_provider_id,
        )
        return None
    if not isinstance(provider, Provider):
        logger.warning(
            "指定的上下文压缩模型 %s 不是对话模型，将跳过压缩。",
            config.llm_compress_provider_id,
        )
        return None
    return provider


async def build_main_agent(
    *,
    event: AstrMessageEvent,
    plugin_context: Context,
    config: MainAgentBuildConfig,
    provider: Provider | None = None,
    req: ProviderRequest | None = None,
) -> MainAgentBuildResult | None:
    """构建主对话代理（Main Agent），并且自动 reset。"""
    provider = provider or _select_provider(event, plugin_context)
    if provider is None:
        logger.info("未找到任何对话模型（提供商），跳过 LLM 请求处理。")
        return None

    if req is None:
        if event.get_extra("provider_request"):
            req = event.get_extra("provider_request")
            assert isinstance(req, ProviderRequest), (
                "provider_request 必须是 ProviderRequest 类型。"
            )
            if req.conversation:
                req.contexts = json.loads(req.conversation.history)
        else:
            req = ProviderRequest()
            req.prompt = ""
            req.image_urls = []
            if sel_model := event.get_extra("selected_model"):
                req.model = sel_model
            if config.provider_wake_prefix and not event.message_str.startswith(
                config.provider_wake_prefix
            ):
                return None

            req.prompt = event.message_str[len(config.provider_wake_prefix) :]
            for comp in event.message_obj.message:
                if isinstance(comp, Image):
                    image_path = await comp.convert_to_file_path()
                    req.image_urls.append(image_path)
                    req.extra_user_content_parts.append(
                        TextPart(text=f"[Image Attachment: path {image_path}]")
                    )
                elif isinstance(comp, File):
                    file_path = await comp.get_file()
                    file_name = comp.name or os.path.basename(file_path)
                    req.extra_user_content_parts.append(
                        TextPart(
                            text=f"[File Attachment: name {file_name}, path {file_path}]"
                        )
                    )

            conversation = await _get_session_conv(event, plugin_context)
            req.conversation = conversation
            req.contexts = json.loads(conversation.history)
            event.set_extra("provider_request", req)

    if isinstance(req.contexts, str):
        req.contexts = json.loads(req.contexts)

    if config.file_extract_enabled:
        try:
            await _apply_file_extract(event, req, config)
        except Exception as exc:  # noqa: BLE001
            logger.error("Error occurred while applying file extract: %s", exc)

    if not req.prompt and not req.image_urls:
        if not event.get_group_id() and req.extra_user_content_parts:
            req.prompt = "<attachment>"
        else:
            return None

    await _decorate_llm_request(event, req, plugin_context, config)

    await _apply_kb(event, req, plugin_context, config)

    if not req.session_id:
        req.session_id = event.unified_msg_origin

    _modalities_fix(provider, req)
    _plugin_tool_fix(event, req)
    _sanitize_context_by_modalities(config, provider, req)

    if config.llm_safety_mode:
        _apply_llm_safety_mode(config, req)

    if config.sandbox_cfg.get("enable", False):
        _apply_sandbox_tools(config, req, req.session_id)

    agent_runner = AgentRunner()
    astr_agent_ctx = AstrAgentContext(
        context=plugin_context,
        event=event,
    )

    if config.add_cron_tools:
        _proactive_cron_job_tools(req)

    if event.platform_meta.support_proactive_message:
        if req.func_tool is None:
            req.func_tool = ToolSet()
        req.func_tool.add_tool(SEND_MESSAGE_TO_USER_TOOL)

    if provider.provider_config.get("max_context_tokens", 0) <= 0:
        model = provider.get_model()
        if model_info := LLM_METADATAS.get(model):
            provider.provider_config["max_context_tokens"] = model_info["limit"][
                "context"
            ]

    if event.get_platform_name() == "webchat":
        asyncio.create_task(_handle_webchat(event, req, provider))
        req.system_prompt += f"\n{CHATUI_EXTRA_PROMPT}\n"

    if req.func_tool and req.func_tool.tools:
        tool_prompt = (
            TOOL_CALL_PROMPT
            if config.tool_schema_mode == "full"
            else TOOL_CALL_PROMPT_SKILLS_LIKE_MODE
        )
        req.system_prompt += f"\n{tool_prompt}\n"

    action_type = event.get_extra("action_type")
    if action_type == "live":
        req.system_prompt += f"\n{LIVE_MODE_SYSTEM_PROMPT}\n"

    await agent_runner.reset(
        provider=provider,
        request=req,
        run_context=AgentContextWrapper(
            context=astr_agent_ctx,
            tool_call_timeout=config.tool_call_timeout,
        ),
        tool_executor=FunctionToolExecutor(),
        agent_hooks=MAIN_AGENT_HOOKS,
        streaming=config.streaming_response,
        llm_compress_instruction=config.llm_compress_instruction,
        llm_compress_keep_recent=config.llm_compress_keep_recent,
        llm_compress_provider=_get_compress_provider(config, plugin_context),
        truncate_turns=config.dequeue_context_length,
        enforce_max_turns=config.max_context_length,
        tool_schema_mode=config.tool_schema_mode,
    )

    return MainAgentBuildResult(
        agent_runner=agent_runner,
        provider_request=req,
        provider=provider,
    )
