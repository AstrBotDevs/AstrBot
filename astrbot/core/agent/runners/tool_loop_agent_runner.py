import asyncio
import copy
import hashlib
import json
import sys
import time
import traceback
import typing as T
import uuid
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import dataclass, field, replace
from typing import override

import anyio
from mcp.types import (
    BlobResourceContents,
    CallToolResult,
    EmbeddedResource,
    ImageContent,
    TextContent,
    TextResourceContents,
)
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from astrbot import logger
from astrbot.core.agent.context.config import ContextConfig
from astrbot.core.agent.context.manager import ContextManager
from astrbot.core.agent.context.token_counter import EstimateTokenCounter
from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.message import (
    AssistantMessageSegment,
    ImageURLPart,
    Message,
    TextPart,
    ThinkPart,
    ToolCallMessageSegment,
    bind_checkpoint_messages,
)
from astrbot.core.agent.response import AgentResponseData, AgentStats
from astrbot.core.agent.run_context import ContextWrapper, TContext
from astrbot.core.agent.runners.base import AgentResponse, AgentState, BaseAgentRunner
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.agent.tool_executor import BaseFunctionToolExecutor
from astrbot.core.agent.tool_image_cache import tool_image_cache
from astrbot.core.exceptions import EmptyModelOutputError
from astrbot.core.message.components import Json
from astrbot.core.message.message_event_result import (
    MessageChain,
)
from astrbot.core.persona_error_reply import (
    extract_persona_custom_error_message_from_event,
)
from astrbot.core.provider.entities import (
    LLMResponse,
    ProviderRequest,
    ToolCallsResult,
)
from astrbot.core.provider.modalities import (
    log_context_sanitize_stats,
    sanitize_contexts_by_modalities,
)
from astrbot.core.provider.provider import Provider
from astrbot.core.utils.config_normalization import to_non_negative_int, to_ratio


def _is_claude_provider(provider: Provider) -> bool:
    """Check whether the provider uses the Anthropic Claude API.

    Detection is based on the registered provider type name,
    not runtime feature probing (PRV-02).
    """
    return provider.provider_config.get("type") == "anthropic_chat_completion"


def _count_active_tools(tool_set: ToolSet | None) -> int:
    """Count active tools only.

    Auto mode should make its threshold decision based on the tools that are
    actually visible to the model, not disabled tools left in the registry.
    """
    if tool_set is None:
        return 0
    return sum(1 for tool in tool_set.tools if tool.active)


@dataclass(slots=True)
class _HandleFunctionToolsResult:
    kind: T.Literal["message_chain", "tool_call_result_blocks", "cached_image"]
    message_chain: MessageChain | None = None
    tool_call_result_blocks: list[ToolCallMessageSegment] | None = None
    cached_image: T.Any = None

    @classmethod
    def from_message_chain(cls, chain: MessageChain) -> "_HandleFunctionToolsResult":
        return cls(kind="message_chain", message_chain=chain)

    @classmethod
    def from_tool_call_result_blocks(
        cls,
        blocks: list[ToolCallMessageSegment],
    ) -> "_HandleFunctionToolsResult":
        return cls(kind="tool_call_result_blocks", tool_call_result_blocks=blocks)

    @classmethod
    def from_cached_image(cls, image: T.Any) -> "_HandleFunctionToolsResult":
        return cls(kind="cached_image", cached_image=image)


@dataclass(slots=True)
class FollowUpTicket:
    seq: int
    text: str
    consumed: bool = False
    resolved: asyncio.Event = field(default_factory=asyncio.Event)


@dataclass(slots=True, frozen=True)
class PostToolCompactionConfig:
    enabled: bool = False
    soft_ratio: float = 0.3
    hard_ratio: float = 0.7
    min_delta_tokens: int = 0
    min_delta_turns: int = 0
    debounce_seconds: int = 0


class PostToolCompactionController:
    def __init__(self, config: PostToolCompactionConfig) -> None:
        self.config = config
        self._baseline_tokens = 0
        self._baseline_messages = 0
        self._last_check_at = 0.0

    def refresh_baseline(
        self,
        *,
        messages: list[Message],
        token_counter: TokenCounter,
        trusted_token_usage: int = 0,
    ) -> None:
        try:
            self._baseline_tokens = token_counter.count_tokens(
                messages,
                trusted_token_usage,
            )
        except Exception:
            self._baseline_tokens = 0
        self._baseline_messages = len(messages)

    def should_compact(
        self,
        *,
        messages: list[Message],
        token_counter: TokenCounter,
        max_context_tokens: int,
    ) -> bool:
        if not self.config.enabled:
            return False

        now = time.monotonic()
        if (
            self.config.debounce_seconds > 0
            and self._last_check_at > 0
            and (now - self._last_check_at) < self.config.debounce_seconds
        ):
            return False
        self._last_check_at = now

        if max_context_tokens <= 0:
            # No explicit token budget configured: preserve legacy behavior.
            return True

        try:
            current_tokens = token_counter.count_tokens(messages)
        except Exception:
            return False

        current_messages = len(messages)
        current_ratio = current_tokens / max(1, max_context_tokens)

        if current_ratio >= self.config.hard_ratio:
            return True
        if current_ratio < self.config.soft_ratio:
            return False

        delta_tokens = max(0, current_tokens - self._baseline_tokens)
        delta_messages = max(0, current_messages - self._baseline_messages)
        if (
            delta_tokens < self.config.min_delta_tokens
            and delta_messages < self.config.min_delta_turns
        ):
            return False
        return True


class ToolLoopAgentRunner(BaseAgentRunner[TContext]):
    TOOL_RESULT_MAX_ESTIMATED_TOKENS = 27_500
    TOOL_RESULT_PREVIEW_MAX_ESTIMATED_TOKENS = 7000
    REQUEST_WARN_ESTIMATED_INPUT_TOKENS = 16_000
    REQUEST_WARN_IMAGE_COUNT = 1
    EMPTY_OUTPUT_RETRY_ATTEMPTS = 3
    EMPTY_OUTPUT_RETRY_WAIT_MIN_S = 1
    EMPTY_OUTPUT_RETRY_WAIT_MAX_S = 4
    USER_INTERRUPTION_MESSAGE = (
        "[SYSTEM: User actively interrupted the response generation. "
        "Partial output before interruption is preserved.]"
    )
    FOLLOW_UP_NOTICE_TEMPLATE = (
        "\n\n[SYSTEM NOTICE] User sent follow-up messages while tool execution "
        "was in progress. Prioritize these follow-up instructions in your next "
        "actions. In your very next action, briefly acknowledge to the user "
        "that their follow-up message(s) were received before continuing.\n"
        "{follow_up_lines}"
    )
    MAX_STEPS_REACHED_PROMPT = (
        "Maximum tool call limit reached. "
        "Stop calling tools, and based on the information you have gathered, "
        "summarize your task and findings, and reply to the user directly."
    )
    SKILLS_LIKE_REQUERY_INSTRUCTION_TEMPLATE = (
        "You have decided to call tool(s): {tool_names}. Now call the tool(s) "
        "with required arguments using the tool schema, and follow the existing "
        "tool-use rules."
    )
    SKILLS_LIKE_REQUERY_REPAIR_INSTRUCTION = (
        "This is the second-stage tool execution step. "
        "You must do exactly one of the following: "
        "1. Call one of the selected tools using the provided tool schema. "
        "2. If calling a tool is no longer possible or appropriate, reply to the user "
        "with a brief explanation of why. "
        "Do not return an empty response. "
        "Do not ignore the selected tools without explanation."
    )
    REPEATED_TOOL_NOTICE_L1_THRESHOLD = 3
    REPEATED_TOOL_NOTICE_L2_THRESHOLD = 4
    REPEATED_TOOL_NOTICE_L3_THRESHOLD = 5
    REPEATED_TOOL_NOTICE_EXEMPT_TOOL_NAMES = frozenset({"astrbot_execute_shell"})
    REPEATED_TOOL_NOTICE_L1_TEMPLATE = (
        "\n\n[SYSTEM NOTICE] By the way, you have executed the same tool "
        "`{tool_name}` {streak} times consecutively. Double-check whether another "
        "tool, different arguments, or a summary would move the task forward better."
    )
    REPEATED_TOOL_NOTICE_L2_TEMPLATE = (
        "\n\n[SYSTEM NOTICE] Important: you have executed the same tool "
        "`{tool_name}` {streak} times consecutively. Unless this repetition is "
        "clearly necessary, stop repeating the same action and either switch "
        "tools, refine parameters, or summarize what is still missing."
    )
    REPEATED_TOOL_NOTICE_L3_TEMPLATE = (
        "\n\n[SYSTEM NOTICE] Important: you have executed the same tool "
        "`{tool_name}` {streak} times consecutively. Repetition is now very "
        "high. Continue only if each call is clearly producing new information. "
        "Otherwise, change strategy, adjust arguments, or explain the limitation "
        "to the user."
    )
    TOOL_RESULT_OVERFLOW_NOTICE_TEMPLATE = (
        "Truncated tool output preview shown above. "
        "The tool output was too large to include directly and was written to "
        "`{overflow_path}`. Use {read_tool_hint} to inspect it. "
        "Use a narrower window when reading large files."
    )

    def _get_persona_custom_error_message(self) -> str | None:
        """Read persona-level custom error message from event extras when available."""
        event = getattr(self.run_context.context, "event", None)
        return extract_persona_custom_error_message_from_event(event)

    @staticmethod
    def _count_image_parts(messages: list[Message]) -> int:
        count = 0
        for message in messages:
            if isinstance(message.content, list):
                count += sum(
                    1 for part in message.content if isinstance(part, ImageURLPart)
                )
        return count

    def _log_request_cost_preflight(self) -> None:
        estimated_input_tokens = EstimateTokenCounter().count_tokens(
            self.run_context.messages
        )
        image_count = self._count_image_parts(self.run_context.messages)
        logger.debug(
            "LLM request preflight. provider=%s, model=%s, estimated_input_tokens=%s, image_count=%s",
            self.provider.provider_config.get("id", ""),
            self.provider.get_model(),
            estimated_input_tokens,
            image_count,
        )
        if estimated_input_tokens >= self.REQUEST_WARN_ESTIMATED_INPUT_TOKENS:
            logger.warning(
                "LLM request has high estimated input tokens. provider=%s, model=%s, estimated_input_tokens=%s",
                self.provider.provider_config.get("id", ""),
                self.provider.get_model(),
                estimated_input_tokens,
            )
        if image_count > self.REQUEST_WARN_IMAGE_COUNT:
            logger.warning(
                "LLM request contains multiple images. provider=%s, model=%s, image_count=%s",
                self.provider.provider_config.get("id", ""),
                self.provider.get_model(),
                image_count,
            )

    async def _complete_with_assistant_response(self, llm_resp: LLMResponse) -> None:
        """Finalize the current step as a plain assistant response with no tool calls."""
        self.final_llm_resp = llm_resp
        self._transition_state(AgentState.DONE)
        self.stats.end_time = time.time()

        parts = []
        if llm_resp.reasoning_content or llm_resp.reasoning_signature:
            parts.append(
                ThinkPart(
                    think=llm_resp.reasoning_content or "",
                    encrypted=llm_resp.reasoning_signature,
                ),
            )
        if llm_resp.completion_text:
            parts.append(TextPart(text=llm_resp.completion_text))
        if len(parts) == 0:
            logger.warning("LLM returned empty assistant message with no tool calls.")
        self.run_context.messages.append(Message(role="assistant", content=parts))

        try:
            await self.agent_hooks.on_agent_done(self.run_context, llm_resp)
        except Exception as e:
            logger.error(f"Error in on_agent_done hook: {e}", exc_info=True)
        self._resolve_unconsumed_follow_ups()

    @override
    async def reset(
        self,
        provider: Provider,
        request: ProviderRequest,
        run_context: ContextWrapper[TContext],
        tool_executor: BaseFunctionToolExecutor[TContext],
        agent_hooks: BaseAgentRunHooks[TContext],
        streaming: bool = False,
        # enforce max turns, will discard older turns when exceeded BEFORE compression
        # -1 means no limit
        enforce_max_turns: int = -1,
        # llm compressor
        llm_compress_instruction: str | None = None,
        llm_compress_keep_recent: int = 0,
        llm_compress_provider: Provider | None = None,
        # llm_compress_use_compact_api:
        #   some provider has its on compact logic, such as OpenAI Responses API,
        #   when this is True, the agent will try to use the provider's compact API if available,
        #   and fall back to compressor if not.
        llm_compress_use_compact_api: bool = True,
        # truncate by turns compressor
        truncate_turns: int = 1,
        # context token counting mode
        token_counter_mode: str = "estimate",
        # run context compression immediately after tool execution
        compact_context_after_tool_call: bool = False,
        # post-tool-call compaction policy
        compact_context_soft_ratio: float = 0.3,
        compact_context_hard_ratio: float = 0.7,
        compact_context_min_delta_tokens: int = 0,
        compact_context_min_delta_turns: int = 0,
        compact_context_debounce_seconds: int = 0,
        # customize
        custom_token_counter: T.Any = None,
        custom_compressor: T.Any = None,
        tool_schema_mode: str | None = "full",
        fallback_providers: list[Provider] | None = None,
        provider_config: dict | None = None,
        tool_result_overflow_dir: str | None = None,
        read_tool: FunctionTool | None = None,
        **kwargs: T.Any,
    ) -> None:
        self.req = request
        self.streaming = streaming
        self.enforce_max_turns = enforce_max_turns
        self.llm_compress_instruction = llm_compress_instruction
        self.llm_compress_keep_recent = llm_compress_keep_recent
        self.llm_compress_provider = llm_compress_provider
        self.llm_compress_use_compact_api = llm_compress_use_compact_api
        self.truncate_turns = truncate_turns
        self.token_counter_mode = token_counter_mode
        post_tool_soft_ratio = to_ratio(compact_context_soft_ratio, 0.3)
        self.post_tool_compaction = PostToolCompactionConfig(
            enabled=bool(compact_context_after_tool_call),
            soft_ratio=post_tool_soft_ratio,
            hard_ratio=max(
                post_tool_soft_ratio, to_ratio(compact_context_hard_ratio, 0.7)
            ),
            min_delta_tokens=to_non_negative_int(compact_context_min_delta_tokens),
            min_delta_turns=to_non_negative_int(compact_context_min_delta_turns),
            debounce_seconds=to_non_negative_int(compact_context_debounce_seconds),
        )
        self.post_tool_compaction_controller = PostToolCompactionController(
            self.post_tool_compaction
        )
        self.custom_token_counter = custom_token_counter
        self.custom_compressor = custom_compressor
        self.tool_result_overflow_dir = tool_result_overflow_dir
        self.read_tool = read_tool
        self._tool_result_token_counter = EstimateTokenCounter()
        # we will do compress when:
        # 1. before requesting LLM
        # 2. optionally after tool execution, controlled by config
        self.context_config = ContextConfig(
            # <=0 will never do compress
            max_context_tokens=provider.provider_config.get("max_context_tokens", 4096),
            # enforce max turns before compression
            enforce_max_turns=self.enforce_max_turns if self.enforce_max_turns != -1 else 15,
            truncate_turns=self.truncate_turns,
            llm_compress_instruction=self.llm_compress_instruction,
            llm_compress_keep_recent=self.llm_compress_keep_recent,
            llm_compress_provider=self.llm_compress_provider,
            token_counter_mode=self.token_counter_mode,
            token_counter_model=provider.get_model(),
            custom_token_counter=self.custom_token_counter,
            custom_compressor=self.custom_compressor,
        )
        self.context_manager = ContextManager(self.context_config)

        self.provider = provider
        self.fallback_providers: list[Provider] = []
        seen_provider_ids: set[str] = {str(provider.provider_config.get("id", ""))}
        for fallback_provider in fallback_providers or []:
            fallback_id = str(fallback_provider.provider_config.get("id", ""))
            if fallback_provider is provider:
                continue
            if fallback_id and fallback_id in seen_provider_ids:
                continue
            self.fallback_providers.append(fallback_provider)
            if fallback_id:
                seen_provider_ids.add(fallback_id)
        self.final_llm_resp = None
        self._state = AgentState.IDLE
        self.tool_executor = tool_executor
        self.agent_hooks = agent_hooks
        self.run_context = run_context
        self._aborted = False
        self._abort_signal = asyncio.Event()
        self._pending_follow_ups: list[FollowUpTicket] = []
        self._follow_up_seq = 0
        self._last_tool_call_key: tuple[str, str] | None = None
        self._same_tool_streak = 0

        # These are used for tool schema mode handling
        # Supported modes:
        # - "full": use full tool schema for LLM calls, default.
        # - "skills_like": use light tool schema for LLM calls, and re-query with param-only schema when needed.
        #   Light tool schema does not include tool parameters.
        #   This can reduce token usage when tools have large descriptions.
        # - "tool_search" / "auto": activates tool search with provider-appropriate strategy.
        # See #4681
        self.tool_schema_mode = tool_schema_mode
        self._tool_schema_param_set = None
        self._skill_like_raw_tool_set = None
        self._tool_search_catalog: ToolCatalog | None = None
        self._tool_search_index: ToolSearchIndex | None = None
        self._tool_search_discovery_state: DiscoveryState | None = None
        self._tool_search_max_results = 5

        effective_mode = tool_schema_mode
        self._tool_search_strategy: ToolSearchStrategy | None = None

        if effective_mode in ("tool_search", "auto"):
            tool_search_config: dict = kwargs.get("tool_search_config") or {}
            try:
                if effective_mode == "auto":
                    threshold = tool_search_config.get("threshold", 25)
                    tool_count = _count_active_tools(request.func_tool)
                    if tool_count <= threshold:
                        effective_mode = "full"

                if effective_mode != "full" and request.func_tool:
                    catalog = ToolCatalog.from_tool_set(
                        request.func_tool, tool_search_config
                    )
                    if not catalog.deferred_tools:
                        logger.info(
                            "tool_search: no deferred tools after partitioning; using 'full' mode."
                        )
                        effective_mode = "full"
                    else:
                        index = ToolSearchIndex(tools=catalog.deferred_tools)
                        self._tool_search_catalog = catalog
                        self._tool_search_index = index
                        self._tool_search_discovery_state = DiscoveryState()
                        self._tool_search_max_results = tool_search_config.get(
                            "max_results", 5
                        )
                        self._refresh_tool_search_strategy(provider)
                        effective_mode = "tool_search"
                else:
                    if effective_mode != "full":
                        effective_mode = "full"
            except Exception:
                logger.warning(
                    "tool_search initialization failed; falling back to 'full' mode.",
                    exc_info=True,
                )
                effective_mode = "full"
                self._tool_search_catalog = None
                self._tool_search_index = None
                self._tool_search_discovery_state = None
                self._tool_search_strategy = None

        self.tool_schema_mode = effective_mode

        if effective_mode == "skills_like":
            tool_set = self.req.func_tool
            if not tool_set:
                return
            self._skill_like_raw_tool_set = tool_set
            light_set = tool_set.get_light_tool_set()
            self._tool_schema_param_set = tool_set.get_param_only_tool_set()
            # MODIFY the req.func_tool to use light tool schemas
            self.req.func_tool = light_set

        # append existing messages in the run context
        messages = bind_checkpoint_messages(request.contexts or [])
        if (
            request.prompt is not None
            or request.image_urls
            or request.audio_urls
            or request.extra_user_content_parts
        ):
            m = await self._assemble_request_context_for_provider(request)
            messages.append(Message.model_validate(m))
        if request.system_prompt:
            messages.insert(
                0,
                Message(role="system", content=request.system_prompt),
            )
        self.run_context.messages = messages
        self._refresh_tool_compaction_baseline(
            trusted_token_usage=request.conversation.token_usage
            if request.conversation
            else 0
        )

        # Append tool_search system prompt after mode resolution (SYS-01, SYS-02)
        if (
            self.tool_schema_mode == "tool_search"
            and self._tool_search_strategy is not None
        ):
            if (
                self.run_context.messages
                and self.run_context.messages[0].role == "system"
            ):
                current_content = self.run_context.messages[0].content
                if isinstance(current_content, str):
                    from astrbot.core.astr_main_agent_resources import (
                        TOOL_CALL_PROMPT_TOOL_SEARCH_MODE,
                    )

                    self.run_context.messages[0].content = (
                        current_content + f"\n{TOOL_CALL_PROMPT_TOOL_SEARCH_MODE}\n"
                    )

        self.stats = AgentStats()
        self.stats.start_time = time.time()

    @staticmethod
    def _tool_call_streak_key(
        tool_name: str,
        tool_args: dict[str, T.Any],
    ) -> tuple[str, str]:
        try:
            args_fingerprint = json.dumps(
                tool_args,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )
        except Exception:
            args_fingerprint = repr(tool_args)
        return tool_name, args_fingerprint

    def _read_tool_hint(self) -> str:
        if self.read_tool is not None:
            return f"`{self.read_tool.name}`"
        return "the available file-read tool"

    async def _assemble_request_context_for_provider(
        self,
        request: ProviderRequest,
    ) -> dict[str, T.Any]:
        modalities = self.provider.provider_config.get("modalities", None)
        if not isinstance(modalities, list):
            return await request.assemble_context()

        supports_image = "image" in modalities
        supports_audio = "audio" in modalities
        if supports_image and supports_audio:
            return await request.assemble_context()

        adjusted_request = replace(
            request,
            image_urls=request.image_urls if supports_image else [],
            audio_urls=request.audio_urls if supports_audio else [],
        )

    def _should_run_post_tool_compaction(self) -> bool:
        if not hasattr(self, "post_tool_compaction_controller"):
            return False
        return self.post_tool_compaction_controller.should_compact(
            messages=self.run_context.messages,
            token_counter=self.context_manager.token_counter,
            max_context_tokens=int(self.context_config.max_context_tokens or 0),
        )

    async def _iter_llm_responses(
        self,
        *,
        include_model: bool = True,
    ) -> T.AsyncGenerator[LLMResponse, None]:
        """Yields chunks *and* a final LLMResponse."""
        contexts = self._sanitize_contexts_for_provider(self.run_context.messages)
        func_tool = self._func_tool_for_provider()
        model = self.req.model if include_model else None
        if self.streaming:
            stream = self.provider.text_chat_stream(
                contexts=contexts,
                func_tool=func_tool,
                session_id=self.req.session_id,
                extra_user_content_parts=self.req.extra_user_content_parts,
                abort_signal=self._abort_signal,
                model=model,
            )
            async for resp in stream:
                yield resp
        else:
            yield await self.provider.text_chat(
                contexts=contexts,
                func_tool=func_tool,
                session_id=self.req.session_id,
                extra_user_content_parts=self.req.extra_user_content_parts,
                abort_signal=self._abort_signal,
                model=model,
            )

    def _refresh_tool_search_strategy(self, provider: Provider) -> None:
        """Rebuild tool_search strategy for the current provider family.

        The strategy owns provider-specific serialization behavior. Fallback may
        switch from a generic provider to Anthropic (or the reverse), so we
        rebuild the strategy while reusing the same catalog/index/discovery
        state to preserve discovered tools across turns.
        """
        if (
            self._tool_search_catalog is None
            or self._tool_search_index is None
            or self._tool_search_discovery_state is None
        ):
            self._tool_search_strategy = None
            return

        if _is_claude_provider(provider):
            strategy: ToolSearchStrategy = ClaudeToolSearchStrategy(
                self._tool_search_catalog,
                self._tool_search_index,
                self._tool_search_max_results,
                discovery_state=self._tool_search_discovery_state,
            )
        else:
            strategy = GenericToolSearchStrategy(
                self._tool_search_catalog,
                self._tool_search_index,
                self._tool_search_max_results,
                discovery_state=self._tool_search_discovery_state,
            )

        self._tool_search_strategy = strategy
        self.req.func_tool = strategy.build_tool_set()

    async def _iter_llm_responses_with_fallback(
        self,
    ) -> T.AsyncGenerator[LLMResponse, None]:
        """Wrap _iter_llm_responses with provider fallback handling."""
        candidates = [self.provider, *self.fallback_providers]
        total_candidates = len(candidates)
        last_exception: Exception | None = None
        last_err_response: LLMResponse | None = None

        for idx, candidate in enumerate(candidates):
            candidate_id = candidate.provider_config.get("id", "<unknown>")
            is_last_candidate = idx == total_candidates - 1
            if idx > 0:
                logger.warning(
                    "Switched from %s to fallback chat provider: %s",
                    self.provider.provider_config.get("id", "<unknown>"),
                    candidate_id,
                )
            self.provider = candidate
            if (
                self.tool_schema_mode == "tool_search"
                and self._tool_search_strategy is not None
            ):
                self._refresh_tool_search_strategy(candidate)
            has_stream_output = False
            try:
                retrying = AsyncRetrying(
                    retry=retry_if_exception_type(EmptyModelOutputError),
                    stop=stop_after_attempt(self.EMPTY_OUTPUT_RETRY_ATTEMPTS),
                    wait=wait_exponential(
                        multiplier=1,
                        min=self.EMPTY_OUTPUT_RETRY_WAIT_MIN_S,
                        max=self.EMPTY_OUTPUT_RETRY_WAIT_MAX_S,
                    ),
                    reraise=True,
                )

                async for attempt in retrying:
                    has_stream_output = False
                    with attempt:
                        try:
                            async for resp in self._iter_llm_responses(
                                include_model=idx == 0,
                            ):
                                if resp.is_chunk:
                                    has_stream_output = True
                                    yield resp
                                    continue

                                if (
                                    resp.role == "err"
                                    and not has_stream_output
                                    and (not is_last_candidate)
                                ):
                                    last_err_response = resp
                                    logger.warning(
                                        "Chat Model %s returns error response, trying fallback to next provider.",
                                        candidate_id,
                                    )
                                    break

                                yield resp
                                return

                            if has_stream_output:
                                return
                        except EmptyModelOutputError:
                            if has_stream_output:
                                logger.warning(
                                    "Chat Model %s returned empty output after streaming started; skipping empty-output retry.",
                                    candidate_id,
                                )
                            else:
                                logger.warning(
                                    "Chat Model %s returned empty output on attempt %s/%s.",
                                    candidate_id,
                                    attempt.retry_state.attempt_number,
                                    self.EMPTY_OUTPUT_RETRY_ATTEMPTS,
                                )
                            raise
            except Exception as exc:  # noqa: BLE001
                last_exception = exc
                logger.warning(
                    "Chat Model %s request error: %s",
                    candidate_id,
                    exc,
                    exc_info=True,
                )
                continue

        if last_err_response:
            yield last_err_response
            return
        if last_exception:
            yield LLMResponse(
                role="err",
                completion_text=(
                    "All chat models failed: "
                    f"{type(last_exception).__name__}: {last_exception}"
                ),
            )
            return
        yield LLMResponse(
            role="err",
            completion_text="All available chat models are unavailable.",
        )

    def _sanitize_contexts_for_provider(
        self,
        contexts: list[Message] | list[dict[str, T.Any]],
    ) -> list[Message] | list[dict[str, T.Any]]:
        if not self._should_fix_modalities_for_provider():
            return contexts
        sanitized_contexts, stats = sanitize_contexts_by_modalities(
            contexts,
            self.provider.provider_config.get("modalities", None),
        )
        log_context_sanitize_stats(stats)
        return sanitized_contexts

    def _should_fix_modalities_for_provider(self) -> bool:
        modalities = self.provider.provider_config.get("modalities", None)
        return isinstance(modalities, list)

    def _func_tool_for_provider(self) -> ToolSet | None:
        if not self.req.func_tool:
            return None
        modalities = self.provider.provider_config.get("modalities", None)
        if isinstance(modalities, list) and "tool_use" not in modalities:
            logger.debug(
                "Provider %s does not support tool_use, clearing tools for request.",
                self.provider,
            )
            return None
        return self.req.func_tool

    def _simple_print_message_role(self, tag: str = ""):
        roles = []
        for message in self.run_context.messages:
            roles.append(message.role)
        logger.debug(f"{tag} RunCtx.messages -> [{len(roles)}] {','.join(roles)}")

    def follow_up(
        self,
        *,
        message_text: str,
    ) -> FollowUpTicket | None:
        """Queue a follow-up message for the next tool result."""
        if self.done() or self._is_stop_requested():
            return None
        text = (message_text or "").strip()
        if not text:
            return None
        ticket = FollowUpTicket(seq=self._follow_up_seq, text=text)
        self._follow_up_seq += 1
        self._pending_follow_ups.append(ticket)
        return ticket

    def _resolve_unconsumed_follow_ups(self) -> None:
        if not self._pending_follow_ups:
            return
        follow_ups = self._pending_follow_ups
        self._pending_follow_ups = []
        for ticket in follow_ups:
            ticket.resolved.set()

    def _consume_follow_up_notice(self) -> str:
        if not self._pending_follow_ups:
            return ""
        follow_ups = self._pending_follow_ups
        self._pending_follow_ups = []
        for ticket in follow_ups:
            ticket.consumed = True
            ticket.resolved.set()
        follow_up_lines = "\n".join(
            f"{idx}. {ticket.text}" for idx, ticket in enumerate(follow_ups, start=1)
        )
        return self.FOLLOW_UP_NOTICE_TEMPLATE.format(
            follow_up_lines=follow_up_lines,
        )

    def _merge_follow_up_notice(self, content: str) -> str:
        notice = self._consume_follow_up_notice()
        if not notice:
            return content
        return f"{content}{notice}"

    def _fingerprint_tool_args(self, tool_args: T.Any) -> str:
        try:
            payload = json.dumps(
                tool_args,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )
        except (TypeError, ValueError):
            payload = str(tool_args)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _track_tool_call_streak(self, tool_name: str, tool_args: T.Any) -> int:
        tool_key = (tool_name, self._fingerprint_tool_args(tool_args))
        if tool_key == self._last_tool_call_key:
            self._same_tool_streak += 1
        else:
            self._last_tool_call_key = tool_key
            self._same_tool_streak = 1
        return self._same_tool_streak

    def _build_repeated_tool_call_guidance(self, tool_name: str, streak: int) -> str:
        if tool_name in self.REPEATED_TOOL_NOTICE_EXEMPT_TOOL_NAMES:
            return ""

        if streak < self.REPEATED_TOOL_NOTICE_L1_THRESHOLD:
            return ""

        if streak >= self.REPEATED_TOOL_NOTICE_L3_THRESHOLD:
            return self.REPEATED_TOOL_NOTICE_L3_TEMPLATE.format(
                tool_name=tool_name,
                streak=streak,
            )

        if streak >= self.REPEATED_TOOL_NOTICE_L2_THRESHOLD:
            return self.REPEATED_TOOL_NOTICE_L2_TEMPLATE.format(
                tool_name=tool_name,
                streak=streak,
            )

        return self.REPEATED_TOOL_NOTICE_L1_TEMPLATE.format(
            tool_name=tool_name,
            streak=streak,
        )

    @override
    async def step(self):
        """Process a single step of the agent.
        This method should return the result of the step.
        """
        if not self.req:
            raise ValueError("Request is not set. Please call reset() first.")

        if self._state == AgentState.IDLE:
            try:
                await self.agent_hooks.on_agent_begin(self.run_context)
            except Exception as e:
                logger.error(f"Error in on_agent_begin hook: {e}", exc_info=True)

        # 开始处理，转换到运行状态
        self._transition_state(AgentState.RUNNING)
        llm_resp_result = None
        got_complete_response = False

        # do truncate and compress
        token_usage = self.req.conversation.token_usage if self.req.conversation else 0
        self._simple_print_message_role("[BefCompact]")
        event = getattr(self.run_context.context, "event", None)
        self.run_context.messages = await self.context_manager.process(
            self.run_context.messages,
            trusted_token_usage=token_usage,
        )
        self._refresh_tool_compaction_baseline(trusted_token_usage=token_usage)
        self._simple_print_message_role("[AftCompact]")
        self._log_request_cost_preflight()

        # Per-turn tool set reassembly for tool_search mode
        if (
            self._tool_search_strategy is not None
            and self.tool_schema_mode == "tool_search"
        ):
            self.req.func_tool = self._tool_search_strategy.build_tool_set()

        async for llm_response in self._iter_llm_responses_with_fallback():
            if llm_response.is_chunk:
                # update ttft
                if self.stats.time_to_first_token == 0:
                    self.stats.time_to_first_token = time.time() - self.stats.start_time

                # Handle usage from providers like MiniMax that send usage in chunk responses
                if llm_response.usage:
                    self.stats.token_usage += llm_response.usage

                if llm_response.result_chain:
                    yield AgentResponse(
                        type="streaming_delta",
                        data=AgentResponseData(chain=llm_response.result_chain),
                    )
                elif llm_response.completion_text:
                    yield AgentResponse(
                        type="streaming_delta",
                        data=AgentResponseData(
                            chain=MessageChain().message(llm_response.completion_text),
                        ),
                    )
                elif llm_response.reasoning_content:
                    yield AgentResponse(
                        type="streaming_delta",
                        data=AgentResponseData(
                            chain=MessageChain(type="reasoning").message(
                                llm_response.reasoning_content,
                            ),
                        ),
                    )
                if self._is_stop_requested():
                    llm_resp_result = LLMResponse(
                        role="assistant",
                        completion_text=self.USER_INTERRUPTION_MESSAGE,
                        reasoning_content=llm_response.reasoning_content,
                        reasoning_signature=llm_response.reasoning_signature,
                    )
                    break
                continue
            llm_resp_result = llm_response
            got_complete_response = True

            if not llm_response.is_chunk and llm_response.usage:
                # only count the token usage of the final response for computation purpose
                self.stats.token_usage += llm_response.usage
                if self.req.conversation:
                    self.req.conversation.token_usage = llm_response.usage.total
            break  # got final response

        if not llm_resp_result:
            if self._is_stop_requested():
                llm_resp_result = LLMResponse(role="assistant", completion_text="")
            else:
                return

        if self._is_stop_requested() and not got_complete_response:
            yield await self._finalize_aborted_step(llm_resp_result)
            return

        if self._is_stop_requested() and got_complete_response:
            logger.info(
                "Agent was requested to stop, but LLM already returned a "
                "complete response. Proceeding with normal response delivery."
            )

        # 处理 LLM 响应
        llm_resp = llm_resp_result

        if llm_resp.role == "err":
            # 如果 LLM 响应错误，转换到错误状态
            self.final_llm_resp = llm_resp
            self.stats.end_time = time.time()
            self._transition_state(AgentState.ERROR)
            self._resolve_unconsumed_follow_ups()
            custom_error_message = self._get_persona_custom_error_message()
            error_text = custom_error_message or (
                f"LLM 响应错误: {llm_resp.completion_text or '未知错误'}"
            )
            yield AgentResponse(
                type="err",
                data=AgentResponseData(
                    chain=MessageChain().message(error_text),
                ),
            )
            return

        has_tool_calls = bool(llm_resp.tools_call_name)
        if not has_tool_calls:
            await self._complete_with_assistant_response(llm_resp)

        # 返回 LLM 结果
        if llm_resp.reasoning_content:
            yield AgentResponse(
                type="llm_result",
                data=AgentResponseData(
                    chain=MessageChain(type="reasoning").message(
                        llm_resp.reasoning_content,
                    ),
                ),
            )
        if not has_tool_calls:
            if llm_resp.result_chain:
                yield AgentResponse(
                    type="llm_result",
                    data=AgentResponseData(chain=llm_resp.result_chain),
                )
            elif llm_resp.completion_text:
                yield AgentResponse(
                    type="llm_result",
                    data=AgentResponseData(
                        chain=MessageChain().message(llm_resp.completion_text),
                    ),
                )

        # 如果有工具调用，还需处理工具调用
        if llm_resp.tools_call_name:
            if self.tool_schema_mode == "skills_like":
                requery_resp, _ = await self._resolve_tool_exec(llm_resp)
                if not requery_resp.tools_call_name:
                    llm_resp = requery_resp
                    logger.warning(
                        "skills_like tool re-query returned no tool calls; fallback to assistant response.",
                    )
                    if llm_resp.result_chain:
                        yield AgentResponse(
                            type="llm_result",
                            data=AgentResponseData(chain=llm_resp.result_chain),
                        )
                    elif llm_resp.completion_text:
                        yield AgentResponse(
                            type="llm_result",
                            data=AgentResponseData(
                                chain=MessageChain().message(llm_resp.completion_text),
                            ),
                        )
                    await self._complete_with_assistant_response(llm_resp)
                    return
                else:
                    llm_resp.tools_call_name = requery_resp.tools_call_name
                    llm_resp.tools_call_args = requery_resp.tools_call_args
                    llm_resp.tools_call_ids = requery_resp.tools_call_ids

            tool_call_result_blocks = []
            cached_images = []  # Collect cached images for LLM visibility
            try:
                async for result in self._handle_function_tools(self.req, llm_resp):
                    if result.kind == "tool_call_result_blocks":
                        if result.tool_call_result_blocks is not None:
                            tool_call_result_blocks = result.tool_call_result_blocks
                    elif result.kind == "cached_image":
                        if result.cached_image is not None:
                            # Collect cached image info
                            cached_images.append(result.cached_image)
                    elif result.kind == "message_chain":
                        chain = result.message_chain
                        if chain is None or chain.type is None:
                            # should not happen
                            continue
                        if chain.type == "tool_direct_result":
                            ar_type = "tool_call_result"
                        else:
                            ar_type = chain.type
                        yield AgentResponse(
                            type=ar_type,
                            data=AgentResponseData(chain=chain),
                        )
            except _ToolExecutionInterrupted:
                yield await self._finalize_aborted_step(llm_resp)
                return

            # 将结果添加到上下文中
            parts = []
            if llm_resp.reasoning_content or llm_resp.reasoning_signature:
                parts.append(
                    ThinkPart(
                        think=llm_resp.reasoning_content or "",
                        encrypted=llm_resp.reasoning_signature,
                    ),
                )
            if llm_resp.completion_text:
                parts.append(TextPart(text=llm_resp.completion_text))
            if len(parts) == 0:
                parts = None
            tool_calls_result = ToolCallsResult(
                tool_calls_info=AssistantMessageSegment(
                    tool_calls=llm_resp.to_openai_to_calls_model(),
                    content=parts,
                ),
                tool_calls_result=tool_call_result_blocks,
            )
            # record the assistant message with tool calls
            self.run_context.messages.extend(
                tool_calls_result.to_openai_messages_model(),
            )

            # If there are cached images and the model supports image input,
            # append a user message with images so LLM can see them
            if cached_images:
                modalities = self.provider.provider_config.get("modalities", [])
                supports_image = "image" in modalities
                if supports_image:
                    # Build user message with images for LLM to review
                    image_parts = []
                    for cached_img in cached_images:
                        img_data = tool_image_cache.get_image_base64_by_path(
                            cached_img.file_path,
                            cached_img.mime_type,
                        )
                        if img_data:
                            base64_data, mime_type = img_data
                            image_parts.append(
                                TextPart(
                                    text=f"[Image from tool '{cached_img.tool_name}', path='{cached_img.file_path}']",
                                ),
                            )
                            image_parts.append(
                                ImageURLPart(
                                    image_url=ImageURLPart.ImageURL(
                                        url=f"data:{mime_type};base64,{base64_data}",
                                        id=cached_img.file_path,
                                    ),
                                ),
                            )
                    if image_parts:
                        self.run_context.messages.append(
                            Message(role="user", content=image_parts),
                        )
                        logger.debug(
                            f"Appended {len(cached_images)} cached image(s) to context for LLM review",
                        )

            self.req.append_tool_calls_result(tool_calls_result)

            if self._should_run_post_tool_compaction():
                self.run_context.messages = await self.context_manager.process(
                    self.run_context.messages,
                    force_compaction=True,
                )
                self._refresh_tool_compaction_baseline()

    async def step_until_done(
        self,
        max_step: int,
    ) -> T.AsyncGenerator[AgentResponse, None]:
        """Process steps until the agent is done."""
        step_count = 0
        # TODO:将max_step由30改为一个较小的值
        max_step = min(max_step, 3)
        while not self.done() and step_count < max_step:
            step_count += 1
            async for resp in self.step():
                yield resp

        #  如果循环结束了但是 agent 还没有完成，说明是达到了 max_step
        if not self.done():
            logger.warning(
                f"Agent reached max steps ({max_step}), forcing a final response.",
            )
            # 拔掉所有工具
            if self.req:
                self.req.func_tool = None
            # 注入提示词
            self.run_context.messages.append(
                Message(
                    role="user",
                    content=self.MAX_STEPS_REACHED_PROMPT,
                ),
            )
            # 再执行最后一步
            async for resp in self.step():
                yield resp

    async def _handle_function_tools(
        self,
        req: ProviderRequest,
        llm_response: LLMResponse,
    ) -> T.AsyncGenerator[_HandleFunctionToolsResult, None]:
        """处理函数工具调用。"""
        tool_call_result_blocks: list[ToolCallMessageSegment] = []
        last_func_tool_name = "unknown"
        last_func_tool_id = "unknown"
        logger.info(f"Agent 使用工具: {llm_response.tools_call_name}")

        def _append_tool_call_result(tool_call_id: str, content: str) -> None:
            tool_call_result_blocks.append(
                ToolCallMessageSegment(
                    role="tool",
                    tool_call_id=tool_call_id,
                    content=self._merge_follow_up_notice(content),
                ),
            )

        # 执行函数调用
        for func_tool_name, func_tool_args, func_tool_id in zip(
            llm_response.tools_call_name,
            llm_response.tools_call_args,
            llm_response.tools_call_ids,
            strict=False,
        ):
            tool_result_blocks_start = len(tool_call_result_blocks)
            tool_call_streak = self._track_tool_call_streak(
                func_tool_name, func_tool_args
            )
            yield _HandleFunctionToolsResult.from_message_chain(
                MessageChain(
                    type="tool_call",
                    chain=[
                        Json(
                            data={
                                "id": func_tool_id,
                                "name": func_tool_name,
                                "args": func_tool_args,
                                "ts": time.time(),
                            },
                        ),
                    ],
                ),
            )
            try:
                if not req.func_tool:
                    return

                if (
                    self.tool_schema_mode == "skills_like"
                    and self._skill_like_raw_tool_set
                ):
                    # in 'skills_like' mode, raw.func_tool is light schema, does not have handler
                    # so we need to get the tool from the raw tool set
                    func_tool = self._skill_like_raw_tool_set.get_tool(func_tool_name)
                    available_tools = self._skill_like_raw_tool_set.names()
                else:
                    func_tool = req.func_tool.get_tool(func_tool_name)
                    available_tools = req.func_tool.names()

                #  Some API may return None for tools with no parameters
                if func_tool_args is None:
                    func_tool_args = {}
                logger.info(f"使用工具：{func_tool_name}，参数：{func_tool_args}")

                if not func_tool:
                    logger.warning(f"未找到指定的工具: {func_tool_name}，将跳过。")
                    _append_tool_call_result(
                        func_tool_id,
                        f"error: Tool {func_tool_name} not found. Available tools are: {', '.join(available_tools)}",
                    )
                    continue

                valid_params = {}  # 参数过滤：只传递函数实际需要的参数

                # 获取实际的 handler 函数
                if func_tool.handler:
                    logger.debug(
                        f"工具 {func_tool_name} 期望的参数: {func_tool.parameters}",
                    )
                    if func_tool.parameters and func_tool.parameters.get("properties"):
                        expected_params = set(func_tool.parameters["properties"].keys())

                        valid_params = {
                            k: v
                            for k, v in func_tool_args.items()
                            if k in expected_params
                        }

                    # 记录被忽略的参数
                    ignored_params = set(func_tool_args.keys()) - set(
                        valid_params.keys(),
                    )
                    if ignored_params:
                        logger.warning(
                            f"工具 {func_tool_name} 忽略非期望参数: {ignored_params}",
                        )
                else:
                    # 如果没有 handler（如 MCP 工具），使用所有参数
                    valid_params = func_tool_args

                approval_cfg = self.run_context.tool_call_approval
                if approval_cfg.get("enable", False):
                    event = getattr(self.run_context.context, "event", None)
                    if event is None:
                        tool_call_result_blocks.append(
                            ToolCallMessageSegment(
                                role="tool",
                                tool_call_id=func_tool_id,
                                content=(
                                    f"error: tool call approval is enabled, but event context is unavailable for `{func_tool_name}`."
                                ),
                            ),
                        )
                        continue
                    approval_result = await request_tool_call_approval(
                        config=approval_cfg,
                        ctx=ToolCallApprovalContext(
                            event=event,
                            tool_name=func_tool_name,
                            tool_args=valid_params,
                            tool_call_id=func_tool_id,
                        ),
                    )
                    if not approval_result.approved:
                        tool_call_result_blocks.append(
                            ToolCallMessageSegment(
                                role="tool",
                                tool_call_id=func_tool_id,
                                content=approval_result.to_tool_result_text(
                                    func_tool_name
                                ),
                            ),
                        )
                        continue

                try:
                    await self.agent_hooks.on_tool_start(
                        self.run_context,
                        func_tool,
                        valid_params,
                    )
                except Exception as e:
                    logger.error(f"Error in on_tool_start hook: {e}", exc_info=True)

                executor = self.tool_executor.execute(
                    tool=func_tool,
                    run_context=self.run_context,
                    **valid_params,  # 只传递有效的参数
                )

                _final_resp: CallToolResult | None = None
                tool_result_parts: list[str] = []
                async for resp in self._iter_tool_executor_results(executor):  # type: ignore
                    if isinstance(resp, CallToolResult):
                        res = resp
                        _final_resp = resp
                        if not res.content:
                            tool_result_parts.append("The tool returned no content.")
                            continue

                        result_parts: list[str] = []
                        for index, content_item in enumerate(res.content):
                            if isinstance(content_item, TextContent):
                                result_parts.append(content_item.text)
                            elif isinstance(content_item, ImageContent):
                                # Cache the image instead of sending directly
                                cached_img = tool_image_cache.save_image(
                                    base64_data=content_item.data,
                                    tool_call_id=func_tool_id,
                                    tool_name=func_tool_name,
                                    index=index,
                                    mime_type=content_item.mimeType or "image/png",
                                )
                                result_parts.append(
                                    f"Image returned and cached at path='{cached_img.file_path}'. "
                                    f"Review the image below. Use send_message_to_user to send it to the user if satisfied, "
                                    f"with type='image' and path='{cached_img.file_path}'.",
                                )
                                # Yield image info for LLM visibility (will be handled in step())
                                yield _HandleFunctionToolsResult.from_cached_image(
                                    cached_img,
                                )
                            elif isinstance(content_item, EmbeddedResource):
                                resource = content_item.resource
                                if isinstance(resource, TextResourceContents):
                                    result_parts.append(resource.text)
                                elif (
                                    isinstance(resource, BlobResourceContents)
                                    and resource.mimeType
                                    and resource.mimeType.startswith("image/")
                                ):
                                    # Cache the image instead of sending directly
                                    cached_img = tool_image_cache.save_image(
                                        base64_data=resource.blob,
                                        tool_call_id=func_tool_id,
                                        tool_name=func_tool_name,
                                        index=index,
                                        mime_type=resource.mimeType,
                                    )
                                    result_parts.append(
                                        f"Image returned and cached at path='{cached_img.file_path}'. "
                                        f"Review the image below. Use send_message_to_user to send it to the user if satisfied, "
                                        f"with type='image' and path='{cached_img.file_path}'.",
                                    )
                                    # Yield image info for LLM visibility
                                    yield _HandleFunctionToolsResult.from_cached_image(
                                        cached_img,
                                    )
                                else:
                                    result_parts.append(
                                        "The tool has returned a data type that is not supported.",
                                    )
                        if result_parts:
                            tool_result_parts.append("\n\n".join(result_parts))

                    elif resp is None:
                        # Tool 直接请求发送消息给用户
                        # 这里我们将直接结束 Agent Loop
                        # 发送消息逻辑在 ToolExecutor 中处理了
                        logger.warning(
                            f"{func_tool_name} 没有返回值，或者已将结果直接发送给用户。",
                        )
                        self._transition_state(AgentState.DONE)
                        self.stats.end_time = time.time()
                        tool_result_parts.append(
                            "The tool has no return value, or has sent the result directly to the user."
                        )
                    else:
                        # 不应该出现其他类型
                        logger.warning(
                            f"Tool 返回了不支持的类型: {type(resp)}。",
                        )
                        tool_result_parts.append(
                            "*The tool has returned an unsupported type. Please tell the user to check the definition and implementation of this tool.*"
                        )

                if tool_result_parts:
                    inline_result = await self._materialize_large_tool_result(
                        tool_call_id=func_tool_id,
                        content="\n\n".join(tool_result_parts),
                    )
                    _append_tool_call_result(
                        func_tool_id,
                        inline_result
                        + self._build_repeated_tool_call_guidance(
                            func_tool_name, tool_call_streak
                        ),
                    )

                try:
                    await self.agent_hooks.on_tool_end(
                        self.run_context,
                        func_tool,
                        func_tool_args,
                        _final_resp,
                    )
                except Exception as e:
                    logger.error(f"Error in on_tool_end hook: {e}", exc_info=True)
            except Exception as e:
                if isinstance(e, _ToolExecutionInterrupted):
                    raise
                logger.warning(traceback.format_exc())
                _append_tool_call_result(
                    func_tool_id,
                    f"error: {e!s}"
                    + self._build_repeated_tool_call_guidance(
                        func_tool_name,
                        tool_call_streak,
                    ),
                )

        # yield the last tool call result
        if tool_call_result_blocks:
            last_tcr_content = str(tool_call_result_blocks[-1].content)
            yield _HandleFunctionToolsResult.from_message_chain(
                MessageChain(
                    type="tool_call_result",
                    chain=[
                        Json(
                            data={
                                "id": last_func_tool_id,
                                "ts": time.time(),
                                "result": last_tcr_content,
                            },
                        ),
                    ],
                ),
            )
            logger.info(f"Tool `{last_func_tool_name}` Result: {last_tcr_content}")

        # 处理函数调用响应
        if tool_call_result_blocks:
            yield _HandleFunctionToolsResult.from_tool_call_result_blocks(
                tool_call_result_blocks,
            )

    def _build_tool_requery_context(
        self,
        tool_names: list[str],
        extra_instruction: str | None = None,
    ) -> list[dict[str, T.Any]]:
        """Build contexts for re-querying LLM with param-only tool schemas."""
        contexts: list[dict[str, T.Any]] = []
        for msg in self.run_context.messages:
            if hasattr(msg, "model_dump"):
                contexts.append(msg.model_dump())
            elif isinstance(msg, dict):
                contexts.append(copy.deepcopy(msg))
        instruction = self.SKILLS_LIKE_REQUERY_INSTRUCTION_TEMPLATE.format(
            tool_names=", ".join(tool_names),
        )
        if extra_instruction:
            instruction = f"{instruction}\n{extra_instruction}"
        if contexts and contexts[0].get("role") == "system":
            content = contexts[0].get("content") or ""
            contexts[0]["content"] = f"{content}\n{instruction}"
        else:
            contexts.insert(0, {"role": "system", "content": instruction})
        return contexts

    @staticmethod
    def _has_meaningful_assistant_reply(llm_resp: LLMResponse) -> bool:
        text = (llm_resp.completion_text or "").strip()
        return bool(text)

    def _build_tool_subset(self, tool_set: ToolSet, tool_names: list[str]) -> ToolSet:
        """Build a subset of tools from the given tool set based on tool names."""
        subset = ToolSet()
        for name in tool_names:
            tool = tool_set.get_tool(name)
            if tool:
                subset.add_tool(tool)
        return subset

    async def _resolve_tool_exec(
        self,
        llm_resp: LLMResponse,
    ) -> tuple[LLMResponse, ToolSet | None]:
        """Used in 'skills_like' tool schema mode to re-query LLM with param-only tool schemas."""
        tool_names = llm_resp.tools_call_name
        if not tool_names:
            return llm_resp, self.req.func_tool
        full_tool_set = self.req.func_tool
        if not isinstance(full_tool_set, ToolSet):
            return llm_resp, self.req.func_tool

        subset = self._build_tool_subset(full_tool_set, tool_names)
        if not subset.tools:
            return llm_resp, full_tool_set

        if isinstance(self._tool_schema_param_set, ToolSet):
            param_subset = self._build_tool_subset(
                self._tool_schema_param_set,
                tool_names,
            )
            if param_subset.tools and tool_names:
                contexts = self._build_tool_requery_context(tool_names)
                requery_resp = await self.provider.text_chat(
                    contexts=self._sanitize_contexts_for_provider(contexts),
                    func_tool=param_subset,
                    model=self.req.model,
                    session_id=self.req.session_id,
                    extra_user_content_parts=self.req.extra_user_content_parts,
                    tool_choice="required",
                    abort_signal=self._abort_signal,
                )
                if (
                    requery_resp
                    and requery_resp.tools_call_name
                    and len(requery_resp.tools_call_name)
                    == len(requery_resp.tools_call_ids)
                    == len(requery_resp.tools_call_args)
                    > 0
                ):
                    llm_resp = requery_resp
                else:
                    logger.warning(
                        "LLM returned invalid or no tool calls during 'skills_like' parameter re-query. "
                        "Falling back to original light-schema response to avoid empty tool_calls error."
                    )

                # If the re-query still returns no tool calls, and also does not have a meaningful assistant reply,
                # we consider it as a failure of the LLM to follow the tool-use instruction,
                # and we will retry once with a stronger instruction that explicitly requires the LLM to either call the tool or give an explanation.
                if (
                    not llm_resp.tools_call_name
                    and not self._has_meaningful_assistant_reply(llm_resp)
                ):
                    logger.warning(
                        "skills_like tool re-query returned no tool calls and no explanation; retrying with stronger instruction.",
                    )
                    repair_contexts = self._build_tool_requery_context(
                        tool_names,
                        extra_instruction=self.SKILLS_LIKE_REQUERY_REPAIR_INSTRUCTION,
                    )
                    repair_resp = await self.provider.text_chat(
                        contexts=self._sanitize_contexts_for_provider(repair_contexts),
                        func_tool=param_subset,
                        model=self.req.model,
                        session_id=self.req.session_id,
                        extra_user_content_parts=self.req.extra_user_content_parts,
                        tool_choice="required",
                        abort_signal=self._abort_signal,
                    )
                    if repair_resp:
                        llm_resp = repair_resp

        return llm_resp, subset

    def done(self) -> bool:
        """检查 Agent 是否已完成工作"""
        return self._state in (AgentState.DONE, AgentState.ERROR)

    def request_stop(self) -> None:
        self._abort_signal.set()

    def _is_stop_requested(self) -> bool:
        return self._abort_signal.is_set()

    def was_aborted(self) -> bool:
        return self._aborted

    def get_final_llm_resp(self) -> LLMResponse | None:
        return self.final_llm_resp

    async def _finalize_aborted_step(
        self,
        llm_resp: LLMResponse | None = None,
    ) -> AgentResponse:
        logger.info("Agent execution was requested to stop by user.")
        if llm_resp is None:
            llm_resp = LLMResponse(role="assistant", completion_text="")
        if llm_resp.role != "assistant":
            llm_resp = LLMResponse(
                role="assistant",
                completion_text=self.USER_INTERRUPTION_MESSAGE,
            )
        self.final_llm_resp = llm_resp
        self._aborted = True
        self._transition_state(AgentState.DONE)
        self.stats.end_time = time.time()

        try:
            await self.agent_hooks.on_agent_done(self.run_context, llm_resp)
        except Exception as e:
            logger.error(f"Error in on_agent_done hook: {e}", exc_info=True)

        parts = []
        if llm_resp.reasoning_content or llm_resp.reasoning_signature:
            parts.append(
                ThinkPart(
                    think=llm_resp.reasoning_content or "",
                    encrypted=llm_resp.reasoning_signature,
                ),
            )
        if llm_resp.completion_text:
            parts.append(TextPart(text=llm_resp.completion_text))
        if parts:
            self.run_context.messages.append(Message(role="assistant", content=parts))

        self._resolve_unconsumed_follow_ups()
        return AgentResponse(
            type="aborted",
            data=AgentResponseData(chain=MessageChain(type="aborted")),
        )

    async def _close_executor(self, executor: T.Any) -> None:
        close_executor = getattr(executor, "aclose", None)
        if close_executor is None:
            return
        with suppress(asyncio.CancelledError, RuntimeError, StopAsyncIteration):
            await close_executor()

    async def _anext_coro(
        self,
        ait: AsyncIterator[ToolExecutorResultT],
    ) -> ToolExecutorResultT:
        return await anext(ait)

    async def _iter_tool_executor_results(
        self,
        executor: AsyncIterator[ToolExecutorResultT],
    ) -> T.AsyncGenerator[ToolExecutorResultT, None]:
        while True:
            if self._is_stop_requested():
                await self._close_executor(executor)
                raise _ToolExecutionInterrupted(
                    "Tool execution interrupted before reading the next tool result.",
                )

            next_result_task = asyncio.create_task(self._anext_coro(executor))
            abort_task = asyncio.create_task(self._abort_signal.wait())
            try:
                done, _ = await asyncio.wait(
                    {next_result_task, abort_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if abort_task in done:
                    if not next_result_task.done():
                        next_result_task.cancel()
                        with suppress(asyncio.CancelledError, StopAsyncIteration):
                            await next_result_task

                    await self._close_executor(executor)

                    raise _ToolExecutionInterrupted(
                        "Tool execution interrupted by a stop request.",
                    )

                try:
                    yield next_result_task.result()
                except StopAsyncIteration:
                    return
            finally:
                if not abort_task.done():
                    abort_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await abort_task
