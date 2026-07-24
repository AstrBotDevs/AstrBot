import asyncio
import copy
import json
import sys
import time
import traceback
import typing as T
import uuid
from contextlib import suppress
from dataclasses import dataclass, field, replace
from pathlib import Path

import jsonschema
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
from astrbot.core.agent.message import ImageURLPart, TextPart, ThinkPart
from astrbot.core.agent.tool import FunctionTool, ToolSet
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

from ..context.compressor import ContextCompressor
from ..context.config import ContextConfig
from ..context.manager import ContextManager
from ..context.token_counter import EstimateTokenCounter, TokenCounter
from ..evidence_store import get_agent_evidence_store
from ..execution_policy import (
    AGENT_TOOL_AUTHORIZATION_EXTRA_KEY,
    get_agent_execution_policy,
)
from ..hooks import BaseAgentRunHooks
from ..message import (
    AssistantMessageSegment,
    Message,
    ToolCallMessageSegment,
    bind_checkpoint_messages,
)
from ..model_gateway import ModelGateway
from ..response import AgentResponseData, AgentStats
from ..run_context import ContextWrapper, TContext
from ..tool import ToolOutcome
from ..tool_executor import BaseFunctionToolExecutor
from ..tool_gateway import ToolGateway
from .base import AgentResponse, AgentState, BaseAgentRunner, RunTerminalStatus

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


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
        cls, blocks: list[ToolCallMessageSegment]
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


class _ToolExecutionInterrupted(Exception):
    """Raised when a running tool call is interrupted by a stop request."""


ToolExecutorResultT = T.TypeVar("ToolExecutorResultT")


class ToolLoopAgentRunner(BaseAgentRunner[TContext]):
    TOOL_RESULT_MAX_ESTIMATED_TOKENS = 27_500
    TOOL_RESULT_PREVIEW_MAX_ESTIMATED_TOKENS = 7000
    # Empty model output is not a transient condition worth holding a QQ
    # conversation hostage for several seconds. One bounded attempt keeps the
    # fallback provider path responsive.
    EMPTY_OUTPUT_RETRY_ATTEMPTS = 2
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

    async def _complete_with_assistant_response(self, llm_resp: LLMResponse) -> None:
        """Finalize the current step as a plain assistant response with no tool calls."""
        self.final_llm_resp = llm_resp
        self._transition_state(AgentState.DONE)
        self.stats.end_time = time.time()
        self._finish_agent_trace("success")

        parts = []
        if llm_resp.reasoning_content is not None or llm_resp.reasoning_signature:
            parts.append(
                ThinkPart(
                    think=llm_resp.reasoning_content or "",
                    encrypted=llm_resp.reasoning_signature,
                )
            )
        if llm_resp.completion_text:
            parts.append(TextPart(text=llm_resp.completion_text))
        if len(parts) == 0:
            event = getattr(self.run_context.context, "event", None)
            terminal_sent = bool(
                event is not None
                and hasattr(event, "get_extra")
                and event.get_extra("agent_control_terminal_sent", False)
            )
            if terminal_sent:
                logger.info(
                    "LLM returned no text after a verified terminal tool delivery."
                )
            else:
                llm_resp.completion_text = "回复模型没有返回可用内容，请稍后再试。"
                parts.append(TextPart(text=llm_resp.completion_text))
                logger.warning(
                    "LLM returned empty assistant message; using degraded reply."
                )
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
        llm_compress_keep_recent_ratio: float = 0.15,
        llm_compress_provider: Provider | None = None,
        # truncate by turns compressor
        truncate_turns: int = 1,
        # customize
        custom_token_counter: TokenCounter | None = None,
        custom_compressor: ContextCompressor | None = None,
        tool_schema_mode: str | None = "full",
        fallback_providers: list[Provider] | None = None,
        request_max_retries: int | None = None,
        tool_result_overflow_dir: str | None = None,
        read_tool: FunctionTool | None = None,
        **kwargs: T.Any,
    ) -> None:
        self.req = request
        self.streaming = streaming
        self.enforce_max_turns = enforce_max_turns
        self.llm_compress_instruction = llm_compress_instruction
        self.llm_compress_keep_recent_ratio = llm_compress_keep_recent_ratio
        self.llm_compress_provider = llm_compress_provider
        self.truncate_turns = truncate_turns
        self.custom_token_counter = custom_token_counter
        self.custom_compressor = custom_compressor
        self.request_max_retries = request_max_retries
        self.tool_result_overflow_dir = tool_result_overflow_dir
        self.read_tool = read_tool
        self._tool_result_token_counter = EstimateTokenCounter()
        self.request_context_manager_config = ContextConfig(
            # <=0 disables token-based guarding.
            max_context_tokens=provider.provider_config.get("max_context_tokens", 0),
            # Enforce max turns before token-based guarding.
            enforce_max_turns=self.enforce_max_turns,
            truncate_turns=self.truncate_turns,
            llm_compress_instruction=self.llm_compress_instruction,
            llm_compress_keep_recent_ratio=self.llm_compress_keep_recent_ratio,
            llm_compress_provider=self.llm_compress_provider,
            custom_token_counter=self.custom_token_counter,
            custom_compressor=self.custom_compressor,
        )
        self.request_context_manager = ContextManager(
            self.request_context_manager_config
        )

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
        self._last_tool_name: str | None = None
        self._same_tool_streak = 0
        self._last_tool_signature: str | None = None
        self._same_tool_signature_streak = 0
        self._force_final_after_tool_guard = False
        self._tool_guard_triggered = False
        self._tool_arg_repairs: dict[str, int] = {}
        self._required_tool_corrections = 0
        self.terminal_status: RunTerminalStatus | None = None
        self._run_started_monotonic = time.monotonic()
        self._run_deadline_monotonic = self._run_started_monotonic + 90.0

        # These two are used for tool schema mode handling
        # We now have two modes:
        # - "full": use full tool schema for LLM calls, default.
        # - "skills_like": use light tool schema for LLM calls, and re-query with param-only schema when needed.
        #   Light tool schema does not include tool parameters.
        #   This can reduce token usage when tools have large descriptions.
        # See #4681
        self.tool_schema_mode = tool_schema_mode
        self._tool_schema_param_set = None
        self._skill_like_raw_tool_set = None
        if tool_schema_mode == "skills_like":
            tool_set = self.req.func_tool
            if not tool_set:
                return
            self._skill_like_raw_tool_set = tool_set
            light_set = tool_set.get_light_tool_set()
            self._tool_schema_param_set = tool_set.get_param_only_tool_set()
            # MODIFIE the req.func_tool to use light tool schemas
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

        self.stats = AgentStats()
        self.stats.start_time = time.time()

        event = getattr(run_context.context, "event", None)
        trace_id = ""
        if event is not None and hasattr(event, "get_extra"):
            trace_id = str(event.get_extra("agent_trace_id") or "")
        if not trace_id:
            trace_id = f"trace-{uuid.uuid4().hex}"
            if event is not None and hasattr(event, "set_extra"):
                event.set_extra("agent_trace_id", trace_id)
        self.trace_id = trace_id
        policy = (
            get_agent_execution_policy(event)
            if event is not None and hasattr(event, "get_extra")
            else None
        )
        self._evidence_store = get_agent_evidence_store()
        self._evidence_store.start_run(
            trace_id=trace_id,
            session_id=str(getattr(event, "unified_msg_origin", "unknown")),
            principal_id=str(getattr(event, "get_sender_id", lambda: "unknown")()),
            goal=str(request.prompt or "")[:4000],
            route=str(getattr(policy, "route", "standard") if policy else "standard"),
        )
        self._evidence_store.update_phase(
            trace_id,
            "RECEIVED",
            deadline_at=time.time() + 90.0,
        )
        if event is not None and hasattr(event, "set_extra"):
            event.set_extra("agent_trace_started", True)

    def _finish_agent_trace(self, final_status: str) -> None:
        """Close the current trace after a terminal Agent response.

        Args:
            final_status: Sanitized completion status for the audit record.
        """

        store = getattr(self, "_evidence_store", None)
        trace_id = getattr(self, "trace_id", "")
        self.terminal_status = RunTerminalStatus(
            {
                "success": "COMPLETED",
                "direct_sent": "COMPLETED",
                "aborted": "CANCELLED",
                "expired": "EXPIRED",
                "llm_error": "FAILED",
                "error": "FAILED",
            }.get(str(final_status), "FAILED")
        )
        if store is not None and trace_id:
            final_response = getattr(self, "final_llm_resp", None)
            store.finish_run(
                trace_id,
                final_status,
                final_response=(
                    getattr(final_response, "completion_text", "")
                    if final_response is not None
                    else None
                ),
            )

    def _mark_run_phase(
        self, phase: str, *, step: int | None = None, reason: str = ""
    ) -> None:
        """Persist a lifecycle phase without exposing model reasoning."""

        store = getattr(self, "_evidence_store", None)
        trace_id = getattr(self, "trace_id", "")
        if store is not None and trace_id:
            store.update_phase(trace_id, phase, step=step, reason=reason)
            store.save_checkpoint(
                trace_id,
                {"phase": phase, "step": step, "reason": reason[:300]},
            )

    def _read_tool_hint(self) -> str:
        if self.read_tool is not None:
            return f"`{self.read_tool.name}`"
        return "the available file-read tool"

    async def _assemble_request_context_for_provider(
        self,
        request: ProviderRequest,
    ) -> dict[str, T.Any]:
        modalities = self.provider.provider_config.get("modalities", None)
        if not modalities:  # Unconfigured (None or empty list) defaults to support all modalities for backward compatibility
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
        context = await adjusted_request.assemble_context()
        content = context.get("content")
        if isinstance(content, str):
            content_blocks: list[dict[str, T.Any]] = [{"type": "text", "text": content}]
        elif isinstance(content, list):
            content_blocks = content
        else:
            content_blocks = []

        if not supports_image:
            for _ in request.image_urls:
                content_blocks.append({"type": "text", "text": "[Image]"})
        if not supports_audio:
            for _ in request.audio_urls:
                content_blocks.append({"type": "text", "text": "[Audio]"})

        return {"role": "user", "content": content_blocks}

    async def _write_tool_result_overflow_file(
        self,
        *,
        tool_call_id: str,
        content: str,
    ) -> str:
        if self.tool_result_overflow_dir is None:
            raise ValueError("tool_result_overflow_dir is not configured")

        overflow_dir = Path(self.tool_result_overflow_dir).resolve(strict=False)
        safe_tool_call_id = (
            "".join(
                ch if ch.isalnum() or ch in {"-", "_", "."} else "_"
                for ch in tool_call_id
            ).strip("._")
            or "tool_call"
        )
        file_name = f"{safe_tool_call_id}_{uuid.uuid4().hex[:8]}.txt"
        overflow_path = overflow_dir / file_name

        def _run() -> str:
            overflow_dir.mkdir(parents=True, exist_ok=True)
            overflow_path.write_text(content, encoding="utf-8")
            return str(overflow_path)

        return await asyncio.to_thread(_run)

    async def _materialize_large_tool_result(
        self,
        *,
        tool_call_id: str,
        content: str,
    ) -> str:
        if self.tool_result_overflow_dir is None or self.read_tool is None:
            return content

        estimated_tokens = self._tool_result_token_counter.count_tokens(
            [Message(role="tool", content=content, tool_call_id=tool_call_id)]
        )
        if estimated_tokens <= self.TOOL_RESULT_MAX_ESTIMATED_TOKENS:
            return content

        preview = self._truncate_tool_result_preview(content, tool_call_id=tool_call_id)
        try:
            overflow_path = await self._write_tool_result_overflow_file(
                tool_call_id=tool_call_id,
                content=content,
            )
        except Exception as exc:
            logger.warning(
                "Failed to spill oversized tool result for %s: %s",
                tool_call_id,
                exc,
                exc_info=True,
            )
            error_notice = (
                "Tool output exceeded the inline result limit "
                f"({estimated_tokens} estimated tokens > "
                f"{self.TOOL_RESULT_MAX_ESTIMATED_TOKENS}) and could not be written "
                f"to `{self.tool_result_overflow_dir}`: {exc}"
            )
            if not preview:
                return error_notice
            return f"{preview}\n\n{error_notice}"

        notice = self.TOOL_RESULT_OVERFLOW_NOTICE_TEMPLATE.format(
            overflow_path=overflow_path,
            read_tool_hint=self._read_tool_hint(),
        )
        if not preview:
            return notice
        return f"{preview}\n\n{notice}"

    def _truncate_tool_result_preview(
        self,
        content: str,
        *,
        tool_call_id: str,
    ) -> str:
        preview = content
        while preview:
            estimated_tokens = self._tool_result_token_counter.count_tokens(
                [Message(role="tool", content=preview, tool_call_id=tool_call_id)]
            )
            if estimated_tokens <= self.TOOL_RESULT_PREVIEW_MAX_ESTIMATED_TOKENS:
                return preview
            next_len = len(preview) // 2
            if next_len <= 0:
                break
            preview = preview[:next_len]
        return preview

    async def _iter_llm_responses(
        self, *, include_model: bool = True
    ) -> T.AsyncGenerator[LLMResponse, None]:
        """Yields chunks *and* a final LLMResponse."""
        payload = {
            "contexts": self._sanitize_contexts_for_provider(self.run_context.messages),
            "func_tool": self._func_tool_for_provider(),
            "session_id": self.req.session_id,
            "extra_user_content_parts": self.req.extra_user_content_parts,  # list[ContentPart]
            "abort_signal": self._abort_signal,
            "request_max_retries": self.request_max_retries,
        }
        if include_model:
            # For primary provider we keep explicit model selection if provided.
            payload["model"] = self.req.model
        timeout = max(
            1.0, min(float(getattr(self.req, "model_timeout_seconds", 75.0)), 90.0)
        )
        if self.streaming:
            async with asyncio.timeout(timeout):
                stream = self.provider.text_chat_stream(**payload)
                async for resp in stream:  # type: ignore
                    yield resp
        else:
            outcome = await ModelGateway.complete(
                lambda: self.provider.text_chat(**payload),
                timeout=timeout,
                provider_id=str(self.provider.provider_config.get("id", "")),
            )
            if outcome.status != "success" or outcome.response is None:
                yield LLMResponse(
                    role="err",
                    completion_text=(
                        f"{outcome.error_code or 'MODEL_EMPTY_OUTPUT'}: "
                        f"{outcome.diagnostics or 'model returned no usable output'}"
                    ),
                )
            else:
                yield outcome.response

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
            event = getattr(self.run_context.context, "event", None)
            execution_policy = (
                get_agent_execution_policy(event)
                if event is not None and hasattr(event, "get_extra")
                else None
            )
            modalities = candidate.provider_config.get("modalities")
            if (
                bool(getattr(execution_policy, "tool_required", False))
                and self.req.func_tool
                and isinstance(modalities, list)
                and modalities
                and "tool_use" not in modalities
            ):
                logger.warning(
                    "Skipping provider %s because the required tool route is "
                    "not supported by its declared modalities.",
                    candidate_id,
                )
                continue
            if idx > 0:
                logger.warning(
                    "Switched from %s to fallback chat provider: %s",
                    self.provider.provider_config.get("id", "<unknown>"),
                    candidate_id,
                )
            self.provider = candidate
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
                                include_model=idx == 0
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
                                    # Preserve failures from providers that are
                                    # skipped by a successful fallback.  The
                                    # final response alone cannot identify that
                                    # Gemini failed, so without this audit trail
                                    # the same broken provider is retried for
                                    # every subsequent message.
                                    if (
                                        event is not None
                                        and hasattr(event, "get_extra")
                                        and hasattr(event, "set_extra")
                                    ):
                                        failures = event.get_extra(
                                            "agent_provider_failures", []
                                        )
                                        if not isinstance(failures, list):
                                            failures = []
                                        failures.append(
                                            {
                                                "provider_id": str(candidate_id),
                                                "detail": str(
                                                    resp.completion_text or ""
                                                )[:500],
                                            }
                                        )
                                        event.set_extra(
                                            "agent_provider_failures", failures[-8:]
                                        )
                                    last_err_response = resp
                                    logger.warning(
                                        "Chat Model %s returns error response (%s), "
                                        "trying fallback to next provider.",
                                        candidate_id,
                                        str(resp.completion_text or "")[:500],
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
        modalities = self.provider.provider_config.get("modalities", None)
        if not modalities:
            # Unconfigured (None or empty list) defaults to support all
            # modalities, but no-tool history compaction below still applies.
            sanitized_contexts = contexts
        else:
            sanitized_contexts, stats = sanitize_contexts_by_modalities(
                contexts,
                self.provider.provider_config.get("modalities", None),
            )
            log_context_sanitize_stats(stats)
        if self.req.func_tool:
            return sanitized_contexts

        # Fast conversational turns do not declare tools.  Do not replay old
        # tool-call protocol messages into a no-tool request: providers may
        # reject a function response whose declaration is not present in the
        # current request, and Gemini is especially strict about empty thought
        # parts.  Keep the visible assistant text and user context only.
        compact_contexts: list[Message | dict[str, T.Any]] = []
        for message in sanitized_contexts:
            if isinstance(message, Message):
                if message.role == "tool":
                    continue
                if message.role == "assistant" and message.tool_calls:
                    if isinstance(message.content, list):
                        visible_text = "".join(
                            part.text
                            for part in message.content
                            if isinstance(part, TextPart) and part.text
                        )
                    else:
                        visible_text = str(message.content or "")
                    if not visible_text.strip():
                        continue
                    compact_contexts.append(
                        message.model_copy(
                            update={"content": visible_text, "tool_calls": None}
                        )
                    )
                    continue
                if message.role == "assistant" and isinstance(message.content, list):
                    visible_text = "".join(
                        part.text
                        for part in message.content
                        if isinstance(part, TextPart) and part.text
                    )
                    if not visible_text.strip():
                        continue
                    compact_contexts.append(
                        message.model_copy(update={"content": visible_text})
                    )
                    continue
                compact_contexts.append(message)
                continue

            if not isinstance(message, dict):
                compact_contexts.append(message)
                continue
            role = message.get("role")
            if role == "tool":
                continue
            if role == "assistant" and message.get("tool_calls"):
                content = message.get("content")
                if isinstance(content, list):
                    visible_text = "".join(
                        str(part.get("text") or "")
                        for part in content
                        if isinstance(part, dict) and part.get("type") == "text"
                    )
                else:
                    visible_text = str(content or "")
                if not visible_text.strip():
                    continue
                compact_message = dict(message)
                compact_message["content"] = visible_text
                compact_message.pop("tool_calls", None)
                compact_contexts.append(compact_message)
                continue
            if role == "assistant" and isinstance(message.get("content"), list):
                visible_text = "".join(
                    str(part.get("text") or "")
                    for part in message["content"]
                    if isinstance(part, dict) and part.get("type") == "text"
                )
                if not visible_text.strip():
                    continue
                compact_message = dict(message)
                compact_message["content"] = visible_text
                compact_contexts.append(compact_message)
                continue
            compact_contexts.append(message)
        return compact_contexts

    def _func_tool_for_provider(self) -> ToolSet | None:
        if not self.req.func_tool:
            return None
        modalities = self.provider.provider_config.get("modalities", None)
        if isinstance(modalities, list) and modalities and "tool_use" not in modalities:
            logger.debug(
                "Provider %s does not support tool_use, clearing tools for request.",
                self.provider,
            )
            return None
        return self.req.func_tool

    def _simple_print_message_role(self, tag: str, messages: list):
        roles = [m.role for m in messages]
        n = len(roles)
        if n > 10:
            summary = ",".join(roles[:4]) + ",...," + ",".join(roles[-4:])
        else:
            summary = ",".join(roles)
        logger.debug(f"{tag} messages -> [{n}] {summary}")

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

    def _track_tool_call_streak(self, tool_name: str) -> int:
        if tool_name == self._last_tool_name:
            self._same_tool_streak += 1
        else:
            self._last_tool_name = tool_name
            self._same_tool_streak = 1
        return self._same_tool_streak

    def _build_repeated_tool_call_guidance(self, tool_name: str, streak: int) -> str:
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

        if self._force_final_after_tool_guard:
            # A repeated tool call is a scheduler/executor concern, not a
            # prompt-level suggestion. Remove tools for the next provider
            # request so an uncooperative model cannot repeat the call.
            self.req.func_tool = None
            self.run_context.messages.append(
                Message(
                    role="user",
                    content=self.MAX_STEPS_REACHED_PROMPT,
                )
            )
            self._force_final_after_tool_guard = False

        if time.monotonic() >= getattr(self, "_run_deadline_monotonic", float("inf")):
            self.final_llm_resp = LLMResponse(
                role="err", completion_text="AI 任务已超过时间限制，请稍后重试。"
            )
            self.stats.end_time = time.time()
            self._transition_state(AgentState.ERROR)
            self._finish_agent_trace("expired")
            yield AgentResponse(
                type="err",
                data=AgentResponseData(
                    chain=MessageChain().message(self.final_llm_resp.completion_text)
                ),
            )
            return

        if self._state == AgentState.IDLE:
            try:
                await self.agent_hooks.on_agent_begin(self.run_context)
            except Exception as e:
                logger.error(f"Error in on_agent_begin hook: {e}", exc_info=True)

        # 开始处理，转换到运行状态
        self._transition_state(AgentState.RUNNING)
        self._mark_run_phase("RUNNING_MODEL")
        llm_resp_result = None

        # Process request-time context before sending it to the provider.
        token_usage = self.req.conversation.token_usage if self.req.conversation else 0
        self._simple_print_message_role("[BefCompact]", self.run_context.messages)
        self.run_context.messages = await self.request_context_manager.process(
            self.run_context.messages, trusted_token_usage=token_usage
        )
        self._simple_print_message_role("[AftCompact]", self.run_context.messages)

        async for llm_response in self._iter_llm_responses_with_fallback():
            if llm_response.is_chunk:
                if self.stats.time_to_first_token == 0:
                    self.stats.time_to_first_token = time.time() - self.stats.start_time

                if llm_response.reasoning_content:
                    yield AgentResponse(
                        type="streaming_delta",
                        data=AgentResponseData(
                            chain=MessageChain(type="reasoning").message(
                                llm_response.reasoning_content,
                            ),
                        ),
                    )
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
                llm_resp_result = LLMResponse(
                    role="err",
                    completion_text="模型没有返回有效结果，请稍后重试。",
                )

        if self._is_stop_requested():
            yield await self._finalize_aborted_step(llm_resp_result)
            return

        # 处理 LLM 响应
        llm_resp = llm_resp_result

        if self._tool_guard_triggered and llm_resp.tools_call_name:
            # Some providers ignore an empty tool schema and keep emitting the
            # same call. Convert that response into a normal final response so
            # the guard cannot be bypassed by an uncooperative model.
            logger.warning(
                "Suppressing tool calls after the repeated-call guard triggered."
            )
            llm_resp.tools_call_name = []
            llm_resp.tools_call_args = []
            llm_resp.tools_call_ids = []
            if not str(llm_resp.completion_text or "").strip():
                llm_resp.completion_text = (
                    "同一个工具和参数已经执行两次，我已停止重复调用，避免任务陷入循环。"
                )
            self._tool_guard_triggered = False

        if llm_resp.role == "err":
            # 如果 LLM 响应错误，转换到错误状态
            self.final_llm_resp = llm_resp
            self.stats.end_time = time.time()
            self._transition_state(AgentState.ERROR)
            self._finish_agent_trace("llm_error")
            self._resolve_unconsumed_follow_ups()
            event = getattr(self.run_context.context, "event", None)
            provider_failures = (
                event.get_extra("agent_provider_failures", [])
                if event is not None and hasattr(event, "get_extra")
                else []
            )
            tool_satisfied = bool(
                event is not None
                and hasattr(event, "get_extra")
                and event.get_extra("agent_control_tool_satisfied", False)
            )
            # Persona-level text is intentionally bypassed for provider
            # outages; otherwise a network failure looks like a normal reply.
            if tool_satisfied:
                error_text = "工具已经执行完成，但回复模型暂时不可用；我先不编造结果。"
            elif isinstance(provider_failures, list) and provider_failures:
                error_text = (
                    "回复模型通道暂时不可用，刚才这条没有生成有效结果。请稍后再试。"
                )
            else:
                custom_error_message = self._get_persona_custom_error_message()
                error_text = custom_error_message or (
                    f"LLM 响应错误: {llm_resp.completion_text or '未知错误'}"
                )
            if event is not None and hasattr(event, "set_extra"):
                event.set_extra("agent_model_failure_message", error_text)
            yield AgentResponse(
                type="err",
                data=AgentResponseData(
                    chain=MessageChain().message(error_text),
                ),
            )
            return

        if not llm_resp.tools_call_name:
            event = getattr(self.run_context.context, "event", None)
            execution_policy = (
                get_agent_execution_policy(event)
                if event is not None and hasattr(event, "get_extra")
                else None
            )
            # Some OpenAI-compatible providers occasionally emit their native
            # DSML tool markup as plain text instead of a structured tool call.
            # Never expose that protocol payload to QQ users. Keep any natural
            # language prefix, then let the required-tool correction below ask
            # for a real registered call when the route requires one.
            completion_text = str(llm_resp.completion_text or "")
            leaked_markers = (
                "<｜｜DSML｜｜",
                "<|DSML|>",
                "<tool_calls>",
                "<function=",
            )
            marker_positions = [
                completion_text.find(marker)
                for marker in leaked_markers
                if completion_text.find(marker) >= 0
            ]
            if marker_positions:
                llm_resp.completion_text = completion_text[
                    : min(marker_positions)
                ].rstrip()
                logger.warning(
                    "Provider emitted unstructured tool markup; stripped it before response."
                )
            tool_required = bool(execution_policy and execution_policy.tool_required)
            tool_satisfied = bool(
                event.get_extra("agent_control_tool_satisfied", False)
                if event is not None and hasattr(event, "get_extra")
                else False
            )
            terminal_failure = (
                event.get_extra("agent_control_terminal_tool_failure")
                if event is not None and hasattr(event, "get_extra")
                else None
            )
            # A non-retryable tool failure is terminal for this request. Do not
            # let the model turn an error into a fabricated success message.
            terminal_failure_finalized = False
            if (
                tool_required
                and not tool_satisfied
                and isinstance(terminal_failure, dict)
                and not bool(terminal_failure.get("retryable"))
            ):
                failed_tool = str(terminal_failure.get("tool_name") or "工具")
                failure_code = str(terminal_failure.get("error_code") or "tool_failed")
                failure_reason = {
                    "tool_timeout": "执行超时",
                    "tool_cancelled": "执行被取消",
                    "tool_empty": "没有返回可用结果",
                }.get(failure_code, "执行失败")
                llm_resp.completion_text = (
                    f"这次请求需要调用 {failed_tool}，但{failure_reason}，所以没有完成。"
                    "我不会把未成功的结果说成已经完成，请稍后重试。"
                )
                terminal_failure_finalized = True
            if tool_required and not tool_satisfied and not terminal_failure_finalized:
                if self._required_tool_corrections == 0:
                    self._required_tool_corrections = 1
                    allowed_tools = execution_policy.allowed_tools
                    selected_tool = execution_policy.selected_tool
                    selected_instruction = (
                        f"Preferred tool selected by the semantic planner: {selected_tool}. "
                        "Use it unless its schema cannot be satisfied; then use one listed fallback. "
                        if selected_tool
                        else ""
                    )
                    if llm_resp.completion_text:
                        self.run_context.messages.append(
                            Message(
                                role="assistant",
                                content=llm_resp.completion_text,
                            )
                        )
                    self.run_context.messages.append(
                        Message(
                            role="user",
                            content=(
                                "[SYSTEM NOTICE] This request requires a registered tool, "
                                "but no successful tool result has been observed. Call exactly "
                                "one best matching allowed tool now. Do not send progress text. "
                                f"{selected_instruction}"
                                f"Allowed tools: {', '.join(allowed_tools)}"
                            ),
                        )
                    )
                    logger.warning(
                        "Required tool was not satisfied; issuing one internal correction."
                    )
                    return
                llm_resp.completion_text = (
                    "这次请求需要调用工具，但工具没有成功返回结果。我不能假装已经查到，"
                    "请稍后再试，或补充更明确的查询条件。"
                )
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
            self._mark_run_phase("RUNNING_TOOL")
            if self.tool_schema_mode == "skills_like":
                requery_resp, _ = await self._resolve_tool_exec(llm_resp)
                if not requery_resp.tools_call_name:
                    llm_resp = requery_resp
                    logger.warning(
                        "skills_like tool re-query returned no tool calls; fallback to assistant response."
                    )
                    if llm_resp.reasoning_content:
                        yield AgentResponse(
                            type="llm_result",
                            data=AgentResponseData(
                                chain=MessageChain(type="reasoning").message(
                                    llm_resp.reasoning_content,
                                ),
                            ),
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
            if llm_resp.reasoning_content is not None or llm_resp.reasoning_signature:
                parts.append(
                    ThinkPart(
                        think=llm_resp.reasoning_content or "",
                        encrypted=llm_resp.reasoning_signature,
                    )
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
                tool_calls_result.to_openai_messages_model()
            )

            # If there are cached images and the model supports image input,
            # append a user message with images so LLM can see them
            if cached_images:
                modalities = self.provider.provider_config.get("modalities", [])
                supports_image = (
                    not modalities or "image" in modalities
                )  # Empty list is treated as unconfigured for backward compatibility
                if supports_image:
                    # Build user message with images for LLM to review
                    image_parts = []
                    for cached_img in cached_images:
                        img_data = tool_image_cache.get_image_base64_by_path(
                            cached_img.file_path, cached_img.mime_type
                        )
                        if img_data:
                            base64_data, mime_type = img_data
                            image_parts.append(
                                TextPart(
                                    text=f"[Image from tool '{cached_img.tool_name}', path='{cached_img.file_path}']"
                                )
                            )
                            image_parts.append(
                                ImageURLPart(
                                    image_url=ImageURLPart.ImageURL(
                                        url=f"data:{mime_type};base64,{base64_data}",
                                        id=cached_img.file_path,
                                    )
                                )
                            )
                    if image_parts:
                        self.run_context.messages.append(
                            Message(role="user", content=image_parts)
                        )
                        logger.debug(
                            f"Appended {len(cached_images)} cached image(s) to context for LLM review"
                        )

            self.req.append_tool_calls_result(tool_calls_result)

    async def step_until_done(
        self, max_step: int
    ) -> T.AsyncGenerator[AgentResponse, None]:
        """Process steps until the agent is done."""
        step_count = 0
        while not self.done() and step_count < max_step:
            step_count += 1
            async for resp in self.step():
                yield resp

        #  如果循环结束了但是 agent 还没有完成，说明是达到了 max_step
        if not self.done():
            logger.warning(
                f"Agent reached max steps ({max_step}), forcing a final response."
            )
            # 拔掉所有工具
            if self.req:
                self.req.func_tool = None
            # 注入提示词
            self.run_context.messages.append(
                Message(
                    role="user",
                    content=self.MAX_STEPS_REACHED_PROMPT,
                )
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
        ):
            tool_result_blocks_start = len(tool_call_result_blocks)
            tool_call_streak = self._track_tool_call_streak(func_tool_name)
            try:
                tool_signature = json.dumps(
                    func_tool_args or {},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                )
            except Exception:
                tool_signature = repr(func_tool_args)
            tool_signature = f"{func_tool_name}:{tool_signature}"
            if tool_signature == self._last_tool_signature:
                self._same_tool_signature_streak += 1
            else:
                self._last_tool_signature = tool_signature
                self._same_tool_signature_streak = 1
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
                            }
                        )
                    ],
                )
            )
            try:
                if self._same_tool_signature_streak > 2:
                    logger.warning(
                        "Blocking repeated tool call %s after two identical attempts.",
                        func_tool_name,
                    )
                    event = getattr(self.run_context.context, "event", None)
                    if event is not None and hasattr(event, "set_extra"):
                        event.set_extra("agent_control_tool_satisfied", False)
                        event.set_extra(
                            "agent_control_terminal_tool_failure",
                            {
                                "tool_name": func_tool_name,
                                "status": "failed",
                                "error_code": "tool_repeated",
                                "diagnostics": "The same tool and arguments were already executed twice.",
                                "retryable": False,
                            },
                        )
                    _append_tool_call_result(
                        func_tool_id,
                        "error: The same tool with identical arguments was already executed twice. "
                        "Do not call it again; summarize the available result or explain the limitation.",
                    )
                    self._force_final_after_tool_guard = True
                    self._tool_guard_triggered = True
                    continue
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

                schema = func_tool.parameters or {
                    "type": "object",
                    "properties": {},
                }
                validation_errors = sorted(
                    jsonschema.Draft202012Validator(schema).iter_errors(valid_params),
                    key=lambda error: list(error.path),
                )
                if validation_errors:
                    repair_count = self._tool_arg_repairs.get(func_tool_name, 0) + 1
                    self._tool_arg_repairs[func_tool_name] = repair_count
                    error_text = "; ".join(
                        error.message for error in validation_errors[:3]
                    )
                    if repair_count == 1:
                        guidance = (
                            "Correct the arguments once using only the tool schema and "
                            "the user's request, then call the same tool again."
                        )
                    else:
                        guidance = (
                            "Do not call this tool again in this turn. Ask the user for "
                            "the missing information or explain that the request is incomplete."
                        )
                    _append_tool_call_result(
                        func_tool_id,
                        f"error: Tool arguments failed schema validation: {error_text}. {guidance}",
                    )
                    continue

                try:
                    event = getattr(self.run_context.context, "event", None)
                    if event is not None and hasattr(event, "set_extra"):
                        event.set_extra(AGENT_TOOL_AUTHORIZATION_EXTRA_KEY, None)
                    await self.agent_hooks.on_tool_start(
                        self.run_context,
                        func_tool,
                        valid_params,
                    )
                except Exception as e:
                    logger.error(f"Error in on_tool_start hook: {e}", exc_info=True)

                authorization = (
                    event.get_extra(AGENT_TOOL_AUTHORIZATION_EXTRA_KEY)
                    if event is not None and hasattr(event, "get_extra")
                    else None
                )
                execution_policy = (
                    get_agent_execution_policy(event)
                    if event is not None and hasattr(event, "get_extra")
                    else None
                )
                authorization_matches = (
                    isinstance(authorization, dict)
                    and authorization.get("tool_name") == func_tool_name
                )
                if execution_policy and not (
                    authorization_matches and authorization.get("allowed") is True
                ):
                    denial_message = (
                        authorization.get("message") if authorization_matches else None
                    )
                    _append_tool_call_result(
                        func_tool_id,
                        str(
                            denial_message
                            or f"error: Tool {func_tool_name} was denied by policy."
                        ),
                    )
                    continue

                executor = ToolGateway.invoke(
                    self.tool_executor.execute,
                    func_tool,
                    self.run_context,
                    **valid_params,
                )

                _final_resp: CallToolResult | None = None
                terminal_direct_sent = False
                async for resp in self._iter_tool_executor_results(executor):  # type: ignore
                    if isinstance(resp, ToolOutcome):
                        res = resp.result or CallToolResult(
                            content=[
                                TextContent(
                                    type="text",
                                    text="The tool returned no usable result.",
                                )
                            ],
                            isError=True,
                        )
                        _final_resp = res
                        if resp.status == "direct_sent":
                            logger.info(
                                "Tool `%s` sent a verified direct result.",
                                func_tool_name,
                            )
                            _append_tool_call_result(
                                func_tool_id,
                                "The tool sent its result directly to the user.",
                            )
                            if resp.terminal:
                                self._transition_state(AgentState.DONE)
                                self.stats.end_time = time.time()
                                self._finish_agent_trace("direct_sent")
                                terminal_direct_sent = True
                                break
                            continue
                        event = getattr(self.run_context.context, "event", None)
                        if event is not None and hasattr(event, "set_extra"):
                            if resp.status in {
                                "empty",
                                "failed",
                                "timeout",
                                "cancelled",
                            }:
                                event.set_extra("agent_control_tool_satisfied", False)
                                event.set_extra(
                                    "agent_control_terminal_tool_failure",
                                    {
                                        "tool_name": func_tool_name,
                                        "status": resp.status,
                                        "error_code": resp.error_code,
                                        "diagnostics": resp.diagnostics,
                                        "retryable": bool(resp.retryable),
                                    },
                                )
                            elif resp.status in {"success", "direct_sent"}:
                                # ToolGateway has already normalized the result,
                                # recorded evidence, and evaluated the completion
                                # contract before the generator closes. Persist
                                # the successful observation on the event so a
                                # required-tool route does not re-enter the
                                # correction loop after a real tool call.
                                event.set_extra("agent_control_tool_satisfied", True)
                                event.set_extra(
                                    "agent_control_terminal_tool_failure", None
                                )
                        if resp.status in {"empty", "failed", "timeout", "cancelled"}:
                            logger.warning(
                                "Tool `%s` outcome=%s code=%s diagnostics=%s",
                                func_tool_name,
                                resp.status,
                                resp.error_code or "unknown",
                                resp.diagnostics or "none",
                            )
                    elif isinstance(resp, CallToolResult):
                        res = resp
                        _final_resp = resp
                    else:
                        res = None

                    if res is not None:
                        if not res.content:
                            if res.structuredContent:
                                structured = json.dumps(
                                    res.structuredContent,
                                    ensure_ascii=False,
                                    default=str,
                                )
                                _append_tool_call_result(
                                    func_tool_id,
                                    ("error: " if res.isError else "") + structured,
                                )
                                continue
                            _append_tool_call_result(
                                func_tool_id,
                                "error: The tool returned no content. Use an approved fallback or explain the failure.",
                            )
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
                                    f"with type='image' and path='{cached_img.file_path}'."
                                )
                                # Yield image info for LLM visibility (will be handled in step())
                                yield _HandleFunctionToolsResult.from_cached_image(
                                    cached_img
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
                                        f"with type='image' and path='{cached_img.file_path}'."
                                    )
                                    # Yield image info for LLM visibility
                                    yield _HandleFunctionToolsResult.from_cached_image(
                                        cached_img
                                    )
                                else:
                                    result_parts.append(
                                        "The tool has returned a data type that is not supported."
                                    )
                        if result_parts:
                            inline_result = "\n\n".join(result_parts)
                            if res.isError:
                                inline_result = f"error: {inline_result}"
                            inline_result = await self._materialize_large_tool_result(
                                tool_call_id=func_tool_id,
                                content=inline_result,
                            )
                            _append_tool_call_result(
                                func_tool_id,
                                inline_result
                                + self._build_repeated_tool_call_guidance(
                                    func_tool_name, tool_call_streak
                                ),
                            )

                    elif resp is None:
                        logger.warning(
                            f"{func_tool_name} 没有返回值，且无法确认已向用户发送结果。"
                        )
                        _append_tool_call_result(
                            func_tool_id,
                            "error: The tool returned nothing and no direct send was verified. "
                            "Use an approved fallback or explain the failure."
                            + self._build_repeated_tool_call_guidance(
                                func_tool_name, tool_call_streak
                            ),
                        )
                    else:
                        # 不应该出现其他类型
                        logger.warning(
                            f"Tool 返回了不支持的类型: {type(resp)}。",
                        )
                        _append_tool_call_result(
                            func_tool_id,
                            "*The tool has returned an unsupported type. Please tell the user to check the definition and implementation of this tool.*"
                            + self._build_repeated_tool_call_guidance(
                                func_tool_name, tool_call_streak
                            ),
                        )

                event = getattr(self.run_context.context, "event", None)
                if (
                    event is not None
                    and hasattr(event, "set_extra")
                    and _final_resp is not None
                    and bool(getattr(_final_resp, "isError", False))
                ):
                    existing_failure = (
                        event.get_extra("agent_control_terminal_tool_failure")
                        if hasattr(event, "get_extra")
                        else None
                    )
                    event.set_extra("agent_control_tool_satisfied", False)
                    event.set_extra(
                        "agent_control_terminal_tool_failure",
                        {
                            "tool_name": func_tool_name,
                            "status": "failed",
                            "error_code": "tool_failed",
                            "diagnostics": "The tool returned an error result.",
                            "retryable": bool(
                                existing_failure.get("retryable")
                                if isinstance(existing_failure, dict)
                                else False
                            ),
                        },
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
                if terminal_direct_sent:
                    return
            except Exception as e:
                if isinstance(e, _ToolExecutionInterrupted):
                    raise
                logger.warning(traceback.format_exc())
                _append_tool_call_result(
                    func_tool_id,
                    f"error: {e!s}"
                    + self._build_repeated_tool_call_guidance(
                        func_tool_name, tool_call_streak
                    ),
                )

            if len(tool_call_result_blocks) > tool_result_blocks_start:
                tool_result_content = str(tool_call_result_blocks[-1].content)
                yield _HandleFunctionToolsResult.from_message_chain(
                    MessageChain(
                        type="tool_call_result",
                        chain=[
                            Json(
                                data={
                                    "id": func_tool_id,
                                    "ts": time.time(),
                                    "result": tool_result_content,
                                }
                            )
                        ],
                    )
                )
                logger.info(f"Tool `{func_tool_name}` Result: {tool_result_content}")

        # 处理函数调用响应
        if tool_call_result_blocks:
            yield _HandleFunctionToolsResult.from_tool_call_result_blocks(
                tool_call_result_blocks
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
                contexts.append(msg.model_dump())  # type: ignore[call-arg]
            elif isinstance(msg, dict):
                contexts.append(copy.deepcopy(msg))
        instruction = self.SKILLS_LIKE_REQUERY_INSTRUCTION_TEMPLATE.format(
            tool_names=", ".join(tool_names)
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
                self._tool_schema_param_set, tool_names
            )
            if param_subset.tools and tool_names:
                contexts = self._build_tool_requery_context(tool_names)
                requery_resp = await self.provider.text_chat(
                    contexts=self._sanitize_contexts_for_provider(contexts),
                    func_tool=param_subset,
                    model=self.req.model,
                    session_id=self.req.session_id,
                    extra_user_content_parts=self.req.extra_user_content_parts,
                    # tool_choice="required",
                    abort_signal=self._abort_signal,
                    request_max_retries=self.request_max_retries,
                )
                if requery_resp:
                    llm_resp = requery_resp

                # If the re-query still returns no tool calls, and also does not have a meaningful assistant reply,
                # we consider it as a failure of the LLM to follow the tool-use instruction,
                # and we will retry once with a stronger instruction that explicitly requires the LLM to either call the tool or give an explanation.
                if (
                    not llm_resp.tools_call_name
                    and not self._has_meaningful_assistant_reply(llm_resp)
                ):
                    logger.warning(
                        "skills_like tool re-query returned no tool calls and no explanation; retrying with stronger instruction."
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
                        # tool_choice="required",
                        abort_signal=self._abort_signal,
                        request_max_retries=self.request_max_retries,
                    )
                    if repair_resp:
                        llm_resp = repair_resp

        return llm_resp, subset

    def done(self) -> bool:
        """检查 Agent 是否已完成工作"""
        return self._state in (AgentState.DONE, AgentState.ERROR)

    def request_stop(self) -> None:
        self._abort_signal.set()

    def force_terminal(self, status: str, message: str) -> None:
        """Force a terminal state when an outer watchdog owns cancellation."""

        if self.done():
            return
        self.final_llm_resp = LLMResponse(role="err", completion_text=message)
        self.stats.end_time = time.time()
        self._transition_state(AgentState.ERROR)
        self._finish_agent_trace(status)

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
        self._finish_agent_trace("aborted")

        parts = []
        if llm_resp.reasoning_content is not None or llm_resp.reasoning_signature:
            parts.append(
                ThinkPart(
                    think=llm_resp.reasoning_content or "",
                    encrypted=llm_resp.reasoning_signature,
                )
            )
        if llm_resp.completion_text:
            parts.append(TextPart(text=llm_resp.completion_text))
        if parts:
            self.run_context.messages.append(Message(role="assistant", content=parts))

        try:
            await self.agent_hooks.on_agent_done(self.run_context, llm_resp)
        except Exception as e:
            logger.error(f"Error in on_agent_done hook: {e}", exc_info=True)

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

    async def _iter_tool_executor_results(
        self,
        executor: T.AsyncGenerator[ToolExecutorResultT, None],
    ) -> T.AsyncGenerator[ToolExecutorResultT, None]:
        async def _next_executor_result() -> ToolExecutorResultT:
            return await anext(executor)

        while True:
            if self._is_stop_requested():
                await self._close_executor(executor)
                raise _ToolExecutionInterrupted(
                    "Tool execution interrupted before reading the next tool result."
                )

            next_result_task = asyncio.create_task(_next_executor_result())
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
                        "Tool execution interrupted by a stop request."
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
