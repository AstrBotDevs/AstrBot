"""The single entry point for building a ready-to-run main agent."""

from dataclasses import dataclass

from astrbot.core import logger
from astrbot.core.agent.tool import ToolSet
from astrbot.core.astr_agent_context import AgentContextWrapper, AstrAgentContext
from astrbot.core.astr_agent_hooks import MAIN_AGENT_HOOKS
from astrbot.core.astr_agent_run_util import AgentRunner
from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
from astrbot.core.astr_main_agent_resources import (
    LIVE_MODE_SYSTEM_PROMPT,
    LLM_ERROR_MESSAGE_EXTRA_KEY,
    TOOL_CALL_PROMPT,
    TOOL_CALL_PROMPT_SKILLS_LIKE_MODE,
    decoded_blocked,
)
from astrbot.core.pipeline.context_utils import call_event_hook
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.message_type import MessageType
from astrbot.core.provider import Provider
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.star.context import Context
from astrbot.core.star.star_handler import EventType
from astrbot.core.tools.cron_tools import FutureTaskTool
from astrbot.core.tools.message_tools import (
    GetGroupMessageHistoryTool,
    SendMessageToUserTool,
)
from astrbot.core.utils.astrbot_path import get_astrbot_system_tmp_path
from astrbot.core.utils.image_input import prepare_request_images
from astrbot.core.utils.llm_metadata import LLM_METADATAS

from . import (
    computer_use,
    knowledge_base,
    persona,
    plugins,
    providers,
    request,
    subagent,
    web_search,
    workspace,
)
from .config import MainAgentBuildConfig


@dataclass(slots=True)
class MainAgentBuildResult:
    """An initialized main agent together with its prepared request and provider."""

    agent_runner: AgentRunner
    provider_request: ProviderRequest
    provider: Provider


async def build_main_agent(
    *,
    event: AstrMessageEvent,
    plugin_context: Context,
    config: MainAgentBuildConfig,
    provider: Provider | None = None,
    req: ProviderRequest | None = None,
) -> MainAgentBuildResult | None:
    """Build a main agent through the same ordered stages for every trigger.

    Args:
        event: Triggering event, including session identity and permissions.
        plugin_context: Provider, conversation, persona, and tool services.
        config: Resolved session settings. Global subagent policy is read live
            alongside the shared orchestrator.
        provider: Explicit model, or None to select the session's model.
        req: Explicit request, or None to collect input from the event.

    Returns:
        An initialized runner with its request and provider, or None when the
        provider/input is unavailable, validation fails, or a hook stops the run.
    """
    # Resolve the model and prepare content before composing capabilities.
    provider = provider or await providers.select_chat_provider(event, plugin_context)
    if provider is None:
        logger.info("No chat provider is available; skipping the request.")
        if not event.get_extra(LLM_ERROR_MESSAGE_EXTRA_KEY):
            providers.set_llm_error_message(event, "noProvider")
        return None
    prepared = await request.prepare_request(
        event, plugin_context, config, provider, req
    )
    if prepared is None:
        return None
    req = prepared.request

    # Seed caller capabilities before persona selection and subagent deduplication.
    tool_mgr = plugin_context.get_llm_tool_manager()
    if config.enable_message_delivery:
        if req.func_tool is None:
            req.func_tool = ToolSet()
        req.func_tool.add_tool(tool_mgr.get_builtin_tool(SendMessageToUserTool))
    await persona.apply_persona(req, config.provider_settings, plugin_context, event)
    subagent.apply_subagents(req, plugin_context)

    # Add session context before capability instructions.
    request.append_system_reminders(
        event, req, config.provider_settings, config.timezone
    )
    await workspace.apply_workspace_instructions(event, req, plugin_context)
    await knowledge_base.apply_knowledge_base(event, req, plugin_context, config)

    # Session plugin filtering precedes builtins, which have their own settings.
    plugins.filter_tools(event, req)
    search_instructions = web_search.apply_web_search(
        req, plugin_context, config.provider_settings, event
    )
    if config.llm_safety_mode:
        persona.apply_safety_instructions(config, req)
    agent_context = AstrAgentContext(context=plugin_context, event=event)
    await computer_use.apply_computer_use(req, plugin_context, config, agent_context)

    builtin_types = []
    if config.add_cron_tools:
        builtin_types.append(FutureTaskTool)
    if event.platform_meta.support_proactive_message:
        builtin_types.append(SendMessageToUserTool)
    if (
        event.get_message_type() == MessageType.GROUP_MESSAGE
        and config.group_message_history_enabled
    ):
        builtin_types.append(GetGroupMessageHistoryTool)
    if builtin_types:
        if req.func_tool is None:
            req.func_tool = ToolSet()
        for tool_type in builtin_types:
            req.func_tool.add_tool(tool_mgr.get_builtin_tool(tool_type))

    # Final instructions describe the assembled capabilities and output mode.
    if req.func_tool and req.func_tool.tools:
        tool_prompt = (
            TOOL_CALL_PROMPT
            if config.tool_schema_mode == "full"
            else TOOL_CALL_PROMPT_SKILLS_LIKE_MODE
        )
        req.system_prompt += f"\n{tool_prompt}\n"
    if event.get_extra("action_type") == "live":
        req.system_prompt += f"\n{LIVE_MODE_SYSTEM_PROMPT}\n"
    req.system_prompt += search_instructions

    # Final model selection happens after captioning, so only remaining images count.
    fallbacks = providers.resolve_fallback_providers(
        provider, plugin_context, config.fallback_provider_ids
    )
    selected_provider = providers.select_image_provider(provider, req, fallbacks)
    if selected_provider is not provider:
        provider = selected_provider
        req.model = None
        fallbacks = [item for item in fallbacks if item is not provider]
    await prepare_request_images(
        req,
        event,
        max_size=prepared.image_max_size,
        prepared=prepared.images,
        captioned_refs=prepared.captioned_refs,
        supports_image=providers.supports_modality(provider, "image"),
    )

    # Endpoint validation is independent of plugin hook dispatch.
    if config.validate_provider_endpoint:
        api_base = provider.provider_config.get("api_base", "")
        if any(host in api_base for host in decoded_blocked):
            providers.set_llm_error_message(event, "blockedProvider", api_base=api_base)
            logger.error(
                "Provider API base %s was blocked for security reasons", api_base
            )
            return None
    if config.call_request_hook:
        if await call_event_hook(event, EventType.OnLLMRequestEvent, req):
            return None
        # Hooks may add images; preserve the cache from input preparation.
        await prepare_request_images(
            req,
            event,
            max_size=prepared.image_max_size,
            prepared=prepared.images,
            supports_image=providers.supports_modality(provider, "image"),
        )

    # Apply limits per run without mutating the shared provider configuration.
    max_context_tokens = provider.provider_config.get("max_context_tokens", 0)
    if max_context_tokens <= 0:
        model_info = LLM_METADATAS.get(provider.get_model())
        max_context_tokens = (
            model_info["limit"]["context"]
            if model_info
            else config.fallback_max_context_tokens
        )
    agent_runner = AgentRunner()
    read_tool = (
        req.func_tool.get_tool("astrbot_file_read_tool") if req.func_tool else None
    )
    await agent_runner.reset(
        provider=provider,
        request=req,
        run_context=AgentContextWrapper(
            context=agent_context, tool_call_timeout=config.tool_call_timeout
        ),
        tool_executor=FunctionToolExecutor(),
        agent_hooks=MAIN_AGENT_HOOKS,
        streaming=config.streaming_response,
        max_context_tokens=max_context_tokens,
        llm_compress_instruction=config.llm_compress_instruction,
        llm_compress_keep_recent_ratio=config.llm_compress_keep_recent_ratio,
        llm_compress_provider=await providers.resolve_compression_provider(
            config, plugin_context, event
        ),
        truncate_turns=config.dequeue_context_length,
        enforce_max_turns=config.max_context_length,
        tool_schema_mode=config.tool_schema_mode,
        fallback_providers=fallbacks,
        request_max_retries=config.request_max_retries,
        tool_result_overflow_dir=get_astrbot_system_tmp_path() if read_tool else None,
        read_tool=read_tool,
    )
    return MainAgentBuildResult(
        agent_runner=agent_runner, provider_request=req, provider=provider
    )
