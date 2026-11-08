"""Resolved settings for one main-agent build."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from astrbot.core import logger
from astrbot.core.astr_agent_runtime.tools.web_search_tools import (
    normalize_legacy_web_search_config,
)
from astrbot.core.config.agent_runner import resolve_context_compression_config
from astrbot.core.utils.config_number import coerce_int_config


@dataclass(slots=True)
class MainAgentBuildConfig:
    """Settings for one build, resolved from the session before construction."""

    tool_call_timeout: int
    """The timeout (in seconds) for a tool call.
    When the tool call exceeds this time,
    a timeout error as a tool result will be returned.
    """
    tool_schema_mode: str = "full"
    """The tool schema mode, can be 'full' or 'skills-like'."""
    max_steps: int = 128
    """Maximum native model/tool steps before forcing a final response."""
    provider_wake_prefix: str = ""
    """The wake prefix for the provider. If the user message does not start with this prefix,
    the main agent will not be triggered."""
    streaming_response: bool = True
    """Whether to use streaming response."""
    call_request_hook: bool = False
    """Dispatch OnLLMRequestEvent before initializing the runner."""
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
    llm_compress_keep_recent_ratio: float = 0.15
    """Percent of current context tokens to keep as exact recent context during llm_compress strategy."""
    llm_compress_provider_id: str = ""
    """The provider ID for the LLM used in context compression."""
    max_context_length: int = 50
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
    computer_use_runtime: str = "none"
    """The runtime for agent computer use: none, local, or sandbox."""
    sandbox_cfg: dict = field(default_factory=dict)
    add_cron_tools: bool = True
    """This will add cron job management tools to the main agent for proactive cron job execution."""
    provider_settings: dict = field(default_factory=dict)
    fallback_provider_ids: list[str] = field(default_factory=list)
    request_max_retries: int = 5
    timezone: str | None = None
    max_quoted_fallback_images: int = 20
    """Maximum number of images injected from quoted-message fallback extraction."""
    validate_provider_endpoint: bool = False
    """Apply the endpoint blocklist; enabled by the interactive entry point."""
    enable_message_delivery: bool = False
    """Provide the delivery tool when a proactive trigger has a destination."""
    group_message_history_enabled: bool = False

    @classmethod
    def from_config(cls, config: dict) -> MainAgentBuildConfig:
        """Resolve shared build settings from an AstrBot session configuration.

        Args:
            config: Session configuration, before per-run overrides.

        Returns:
            Build settings with an isolated copy of mutable configuration values.
        """
        normalize_legacy_web_search_config(config)
        settings = copy.deepcopy(config.get("provider_settings") or {})
        runner_config = config.get("agent", {}).get("config", {})
        model = runner_config.get("model", {})
        persona = runner_config.get("persona", {})
        misc = runner_config.get("misc", {})
        file_extract = settings.get("file_extract", {})
        tool_schema_mode = misc.get("tool_schema_mode", "full")
        if tool_schema_mode not in ("skills_like", "full"):
            logger.warning(
                "Unsupported tool_schema_mode: %s, fallback to full",
                tool_schema_mode,
            )
            tool_schema_mode = "full"
        return cls(
            tool_call_timeout=misc.get("tool_call_timeout", 120),
            max_steps=coerce_int_config(
                misc.get("max_steps", 128),
                default=128,
                min_value=1,
                field_name="agent.config.misc.max_steps",
            ),
            tool_schema_mode=tool_schema_mode,
            streaming_response=settings.get("streaming_response", True),
            sanitize_context_by_modalities=misc.get(
                "sanitize_context_by_modalities", False
            ),
            kb_agentic_mode=config.get("kb_agentic_mode", False),
            file_extract_enabled=file_extract.get("enable", False),
            file_extract_prov=file_extract.get("provider", "moonshotai"),
            file_extract_msh_api_key=file_extract.get("moonshotai_api_key", ""),
            **resolve_context_compression_config(runner_config.get("compression", {})),
            llm_safety_mode=persona.get("safety_mode", True),
            safety_mode_strategy=persona.get("safety_mode_strategy", "system_prompt"),
            computer_use_runtime=settings.get("computer_use_runtime", "none"),
            sandbox_cfg=settings.get("sandbox", {}),
            add_cron_tools=settings.get("proactive_capability", {}).get(
                "add_cron_tools", True
            ),
            provider_settings=settings,
            fallback_provider_ids=copy.deepcopy(model.get("fallback_provider_ids", [])),
            request_max_retries=model.get("request_max_retries", 5),
            group_message_history_enabled=config.get("provider_ltm_settings", {}).get(
                "group_message_history_enable", False
            ),
            timezone=config.get("timezone"),
            max_quoted_fallback_images=settings.get("max_quoted_fallback_images", 20),
        )
