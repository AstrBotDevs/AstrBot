import asyncio
import copy
import inspect
import json
import time
import traceback
import typing as T
import uuid
from contextlib import suppress
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import cast, override

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
from astrbot.core.agent.tool import (
    FunctionTool,
    ToolSet,
    get_parallel_blocked_reason,
    get_tool_id,
)
from astrbot.core.agent.tool_image_cache import ToolImageCache
from astrbot.core.exceptions import EmptyModelOutputError, ProviderResponseError
from astrbot.core.message.components import Json
from astrbot.core.message.message_event_result import (
    MessageChain,
)
from astrbot.core.persona_error_reply import (
    extract_persona_custom_error_message_from_event,
)
from astrbot.core.utils.error_redaction import safe_error

from ..chat_model import ChatModel
from ..context.compressor import ContextCompressor
from ..context.config import ContextConfig
from ..context.manager import ContextManager
from ..context.modalities import (
    log_context_sanitize_stats,
    sanitize_contexts_by_modalities,
)
from ..context.token_counter import EstimateTokenCounter, TokenCounter
from ..hooks import BaseAgentRunHooks
from ..llm_types import LLMResponse, ProviderRequest, ToolCallsResult
from ..message import (
    AssistantMessageSegment,
    Message,
    ToolCallMessageSegment,
    bind_checkpoint_messages,
)
from ..response import AgentResponseData, AgentResponseType, AgentStats
from ..run_context import ContextWrapper, TContext
from ..tool_executor import BaseFunctionToolExecutor
from ..tool_history_compactor import compact_consumed_tool_history
from .base import AgentResponse, AgentState, BaseAgentRunner


@dataclass(slots=True)
class _HandleFunctionToolsResult:
    kind: T.Literal["message_chain", "tool_call_result_blocks", "cached_image"]
    message_chain: MessageChain | None = None
    tool_call_result_blocks: list[ToolCallMessageSegment] | None = None
    cached_image: T.Any = None

    @classmethod
    def from_message_chain(cls, chain: MessageChain) -> _HandleFunctionToolsResult:
        return cls(kind="message_chain", message_chain=chain)

    @classmethod
    def from_tool_call_result_blocks(
        cls, blocks: list[ToolCallMessageSegment]
    ) -> _HandleFunctionToolsResult:
        return cls(kind="tool_call_result_blocks", tool_call_result_blocks=blocks)

    @classmethod
    def from_cached_image(cls, image: T.Any) -> _HandleFunctionToolsResult:
        return cls(kind="cached_image", cached_image=image)


@dataclass(slots=True)
class FollowUpTicket:
    seq: int
    text: str
    consumed: bool = False
    resolved: asyncio.Event = field(default_factory=asyncio.Event)


class AgentStopRequested(Exception):
    """Raised when a user asks an active Agent run to stop."""


@dataclass(slots=True)
class _ParallelToolOutcome:
    """Ordered, provider-neutral outcome of one concurrently executed call."""

    tool_name: str
    tool_call_id: str
    tool_call_streak: int
    content: str
    cached_images: list[T.Any] = field(default_factory=list)
    final_response: CallToolResult | None = None


ToolExecutorResultT = T.TypeVar("ToolExecutorResultT")


class ToolLoopAgentRunner(BaseAgentRunner[TContext]):
    TOOL_RESULT_MAX_ESTIMATED_TOKENS = 27_500
    TOOL_RESULT_PREVIEW_MAX_ESTIMATED_TOKENS = 7000
    EMPTY_OUTPUT_RETRY_ATTEMPTS = 3
    EMPTY_OUTPUT_RETRY_WAIT_MIN_S = 1
    EMPTY_OUTPUT_RETRY_WAIT_MAX_S = 4
    STOP_HISTORY_USER_TEXT = "Stop output."
    STOP_HISTORY_ASSISTANT_TEXT = "Output stopped."
    STOP_CLEANUP_GRACE_SECONDS = 0.25
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
    MALFORMED_TOOL_NAME_PLACEHOLDER = "__malformed_tool_name__"
    REPEATED_TOOL_NOTICE_L1_TEMPLATE = (
        "\n\n[SYSTEM NOTICE] By the way, you have executed the same tool "
        "`{tool_name}` with the same arguments {streak} times consecutively. "
        "Double-check whether another tool, different arguments, or a summary would "
        "move the task forward better."
    )
    REPEATED_TOOL_NOTICE_L2_TEMPLATE = (
        "\n\n[SYSTEM NOTICE] Important: you have executed the same tool "
        "`{tool_name}` with the same arguments {streak} times consecutively. "
        "Unless this repetition is clearly necessary, stop repeating the same action "
        "and either switch tools, refine parameters, or summarize what is still "
        "missing."
    )
    REPEATED_TOOL_NOTICE_L3_TEMPLATE = (
        "\n\n[SYSTEM NOTICE] Important: you have executed the same tool "
        "`{tool_name}` with the same arguments {streak} times consecutively. "
        "Repetition is now very high. Continue only if each call is clearly producing "
        "new information. Otherwise, change strategy, adjust arguments, or explain "
        "the limitation to the user."
    )
    TOOL_RESULT_OVERFLOW_NOTICE_TEMPLATE = (
        "Truncated tool output preview shown above. "
        "The tool output was too large to include directly and was written to "
        "`{overflow_path}`. Use {read_tool_hint} to inspect it. "
        "Use a narrower window when reading large files."
    )

    def __init__(self, tool_image_cache: ToolImageCache) -> None:
        """Create a runner with its runtime-owned tool image cache."""
        self.tool_image_cache = tool_image_cache
        # reset() replaces these sets for every run.  Initializing them here keeps
        # the runner safe for focused internal consumers that exercise tool
        # execution before a full agent reset.
        self._inflight_operations: set[asyncio.Future[T.Any]] = set()
        self._stop_cleanup_tasks: set[asyncio.Future[T.Any]] = set()

    def _get_persona_custom_error_message(self) -> str | None:
        """Read persona-level custom error message from event extras when available."""
        event = getattr(self.run_context.context, "event", None)
        return extract_persona_custom_error_message_from_event(event)

    async def _complete_with_assistant_response(self, llm_resp: LLMResponse) -> None:
        """Finalize the current step as a plain assistant response with no tool calls."""
        self.final_llm_resp = llm_resp
        self._transition_state(AgentState.DONE)
        self.stats.end_time = time.time()

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
            logger.warning("LLM returned empty assistant message with no tool calls.")
        self.run_context.messages.append(
            Message(
                role="assistant",
                content=parts,
                provider_state=llm_resp.provider_state,
            )
        )

        await self._notify_agent_done(llm_resp)
        self._resolve_unconsumed_follow_ups()

    async def _notify_agent_done(self, llm_resp: LLMResponse) -> None:
        """Run the terminal hook once for either completion or user stop."""
        if self._agent_done_notified:
            return
        self._agent_done_notified = True
        try:
            await self.agent_hooks.on_agent_done(self.run_context, llm_resp)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("Error in on_agent_done hook: %s", exc, exc_info=True)

    @override
    async def reset(
        self,
        provider: ChatModel,
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
        llm_compress_provider: ChatModel | None = None,
        # truncate by turns compressor
        truncate_turns: int = 1,
        # customize
        custom_token_counter: TokenCounter | None = None,
        custom_compressor: ContextCompressor | None = None,
        tool_schema_mode: str | None = "full",
        fallback_providers: list[ChatModel] | None = None,
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
        self.fallback_providers: list[ChatModel] = []
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
        self._last_tool_args: dict[str, T.Any] | None = None
        self._same_tool_streak = 0
        self._inflight_operations: set[asyncio.Future[T.Any]] = set()
        self._stop_cleanup_tasks: set[asyncio.Future[T.Any]] = set()
        self._agent_done_notified = False

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
            if tool_set:
                self._skill_like_raw_tool_set = tool_set
                light_set = tool_set.get_light_tool_set()
                self._tool_schema_param_set = tool_set.get_param_only_tool_set()
                # MODIFIE the req.func_tool to use light tool schemas
                self.req.func_tool = light_set

        # append existing messages in the run context
        contexts = request.contexts or []
        if request.tool_history_mode == "compact_consumed":
            contexts = compact_consumed_tool_history(
                contexts,
                request.tool_history_placeholder
                or "[Stale tool result omitted, call the tool again if needed]",
            )
        messages = bind_checkpoint_messages(contexts)
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

    def _track_inflight_operation(self, task: asyncio.Future[T.Any]) -> None:
        self._inflight_operations.add(task)
        task.add_done_callback(self._inflight_operations.discard)

    def _detach_stop_cleanup(self, task: asyncio.Future[T.Any]) -> None:
        """Keep a cancellation-resistant operation owned until it finishes."""
        self._stop_cleanup_tasks.add(task)

        def _consume_result(completed: asyncio.Future[T.Any]) -> None:
            self._stop_cleanup_tasks.discard(completed)
            try:
                completed.result()
            except asyncio.CancelledError:
                pass
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Agent stop cleanup task failed: %s", safe_error("", exc)
                )

        task.add_done_callback(_consume_result)

    async def _cancel_operation_with_grace(
        self,
        task: asyncio.Future[T.Any],
    ) -> None:
        if not task.done():
            task.cancel()
        try:
            await asyncio.wait_for(
                asyncio.shield(task),
                timeout=self.STOP_CLEANUP_GRACE_SECONDS,
            )
        except TimeoutError:
            self._detach_stop_cleanup(task)
        except asyncio.CancelledError, StopAsyncIteration:
            pass
        except Exception:  # The caller handles the original operation result.
            pass

    async def _close_after_operation(
        self,
        operation: asyncio.Future[T.Any],
        close: T.Callable[[], T.Awaitable[None]],
    ) -> None:
        """Close a generator once a cancellation-resistant anext finishes."""
        try:
            await asyncio.shield(operation)
        except asyncio.CancelledError, StopAsyncIteration, Exception:
            pass
        await close()

    async def _await_stop_interruptibly(
        self,
        awaitable: T.Awaitable[T.Any],
        *,
        close_after_stop: T.Callable[[], T.Awaitable[None]] | None = None,
    ) -> T.Any:
        """Await one provider/compressor operation while honoring a stop request."""
        if self._is_stop_requested():
            raise AgentStopRequested("Agent stop requested before operation start.")

        operation_task = asyncio.ensure_future(awaitable)
        self._track_inflight_operation(operation_task)
        stop_task = asyncio.create_task(self._abort_signal.wait())
        try:
            done, _ = await asyncio.wait(
                {operation_task, stop_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if stop_task in done or self._is_stop_requested():
                await self._cancel_operation_with_grace(operation_task)
                if close_after_stop is not None and not operation_task.done():
                    cleanup_task = asyncio.create_task(
                        self._close_after_operation(
                            operation_task,
                            close_after_stop,
                        )
                    )
                    self._detach_stop_cleanup(cleanup_task)
                raise AgentStopRequested("Agent stop requested during operation.")
            return operation_task.result()
        except asyncio.CancelledError:
            await self._cancel_operation_with_grace(operation_task)
            raise
        finally:
            if not stop_task.done():
                stop_task.cancel()
                with suppress(asyncio.CancelledError):
                    await stop_task

    async def _close_async_generator(self, generator: T.Any) -> None:
        close = getattr(generator, "aclose", None)
        if not callable(close):
            return
        close_task = asyncio.create_task(
            cast(T.Coroutine[T.Any, T.Any, T.Any], close())
        )
        try:
            await asyncio.wait_for(
                asyncio.shield(close_task),
                timeout=self.STOP_CLEANUP_GRACE_SECONDS,
            )
        except TimeoutError:
            self._detach_stop_cleanup(close_task)
        except RuntimeError, StopAsyncIteration:
            pass

    def _read_tool_hint(self) -> str:
        if self.read_tool is not None:
            return f"`{self.read_tool.name}`"
        return "the available file-read tool"

    async def _assemble_request_context_for_provider(
        self,
        request: ProviderRequest,
    ) -> dict[str, T.Any]:
        modalities = self.provider.provider_config.get("modalities", None)
        if modalities is None or not isinstance(modalities, list):
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
    ) -> T.AsyncGenerator[LLMResponse]:
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
        if self.streaming:
            stream = self.provider.text_chat_stream(**payload)
            try:
                while True:
                    try:
                        response = await self._await_stop_interruptibly(
                            anext(stream),
                            close_after_stop=lambda: self._close_async_generator(
                                stream
                            ),
                        )
                    except StopAsyncIteration:
                        return
                    yield response
            finally:
                await self._close_async_generator(stream)
        else:
            yield await self._await_stop_interruptibly(
                self.provider.text_chat(**payload)
            )

    async def _iter_llm_responses_with_fallback(
        self,
    ) -> T.AsyncGenerator[LLMResponse]:
        """Wrap _iter_llm_responses with provider fallback handling."""
        if not self.run_context.messages:
            logger.warning(
                "Skipping LLM request because no messages remain after agent/request "
                "hooks and context processing."
            )
            yield LLMResponse(
                role="err",
                completion_text="No messages remain for the LLM request.",
            )
            return

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
            has_visible_stream_output = False
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
                    with attempt:
                        try:
                            async for resp in self._iter_llm_responses(
                                include_model=idx == 0
                            ):
                                if resp.is_chunk:
                                    has_visible_stream_output = (
                                        has_visible_stream_output
                                        or bool(
                                            resp.completion_text
                                            or resp.reasoning_content
                                            or resp.result_chain
                                        )
                                    )
                                    yield resp
                                    continue

                                if (
                                    resp.role == "err"
                                    and not has_visible_stream_output
                                    and (not is_last_candidate)
                                ):
                                    last_err_response = resp
                                    logger.warning(
                                        "Chat Model %s returns error response, trying fallback to next provider.",
                                        candidate_id,
                                    )
                                    break

                                self._sanitize_malformed_tool_calls(resp)
                                yield resp
                                return

                            if has_visible_stream_output:
                                yield LLMResponse(
                                    role="err",
                                    completion_text=(
                                        "The model stream ended without a final response."
                                    ),
                                )
                                return
                        except EmptyModelOutputError:
                            if has_visible_stream_output:
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
            except AgentStopRequested:
                raise
            except asyncio.CancelledError:
                raise
            except ProviderResponseError as exc:
                last_exception = exc
                logger.warning(
                    "Chat Model %s returned a terminal provider response: %s",
                    candidate_id,
                    exc,
                )
                break
            except Exception as exc:  # noqa: BLE001
                if has_visible_stream_output:
                    logger.warning(
                        "Chat Model %s stream failed after visible output: %s",
                        candidate_id,
                        exc,
                        exc_info=True,
                    )
                    yield LLMResponse(
                        role="err",
                        completion_text=(
                            "The model stream was interrupted after partial output."
                        ),
                    )
                    return
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
        if (
            not modalities
        ):  # Unconfigured (None or empty list) defaults to support all modalities
            return contexts
        sanitized_contexts, stats = sanitize_contexts_by_modalities(
            contexts,
            self.provider.provider_config.get("modalities", None),
        )
        log_context_sanitize_stats(stats)
        return sanitized_contexts

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

    def _track_tool_call_streak(
        self,
        tool_name: str,
        tool_args: dict[str, T.Any] | None,
    ) -> int:
        """Track consecutive tool calls with the same name and arguments."""
        normalized_args = {} if tool_args is None else tool_args
        if (
            tool_name == self._last_tool_name
            and normalized_args == self._last_tool_args
        ):
            self._same_tool_streak += 1
        else:
            self._last_tool_name = tool_name
            self._last_tool_args = copy.deepcopy(normalized_args)
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

    def _sanitize_malformed_tool_calls(
        self,
        llm_resp: LLMResponse,
    ) -> None:
        """Normalize malformed tool call names.

        Args:
            llm_resp: The LLM response whose tool call lists should be sanitized.
        """
        llm_resp.tools_call_name = [
            self.MALFORMED_TOOL_NAME_PLACEHOLDER
            if tool_name is None or tool_name.strip() == ""
            else tool_name
            for tool_name in llm_resp.tools_call_name
        ]

    async def _prepare_step_request(self) -> None:
        """Run begin hooks and compact the request context for one step."""
        if self._is_stop_requested():
            raise AgentStopRequested("Agent stop requested before context preparation.")
        if self._state == AgentState.IDLE:
            try:
                await self.agent_hooks.on_agent_begin(self.run_context)
            except Exception as exc:  # noqa: BLE001
                logger.error("Error in on_agent_begin hook: %s", exc, exc_info=True)

        self._transition_state(AgentState.RUNNING)
        token_usage = self.req.conversation.token_usage if self.req.conversation else 0
        self._simple_print_message_role("[BefCompact]", self.run_context.messages)
        self.run_context.messages = await self._await_stop_interruptibly(
            self.request_context_manager.process(
                self.run_context.messages,
                trusted_token_usage=token_usage,
            )
        )
        self._simple_print_message_role("[AftCompact]", self.run_context.messages)

    def _streaming_response_events(self, response: LLMResponse) -> list[AgentResponse]:
        """Translate a provider stream chunk into agent output events."""
        events: list[AgentResponse] = []
        if response.reasoning_content:
            events.append(
                AgentResponse(
                    type="streaming_delta",
                    data=AgentResponseData(
                        chain=MessageChain(type="reasoning").message(
                            response.reasoning_content,
                        ),
                    ),
                )
            )
        if response.result_chain:
            events.append(
                AgentResponse(
                    type="streaming_delta",
                    data=AgentResponseData(chain=response.result_chain),
                )
            )
        elif response.completion_text:
            events.append(
                AgentResponse(
                    type="streaming_delta",
                    data=AgentResponseData(
                        chain=MessageChain().message(response.completion_text),
                    ),
                )
            )
        return events

    def _record_final_response_usage(self, response: LLMResponse) -> None:
        """Update cumulative and current request usage from a final response."""
        self.stats.current_context_tokens = 0
        if response.usage:
            self.stats.token_usage += response.usage
            self.stats.current_context_tokens = response.usage.input
            if self.req.conversation:
                self.req.conversation.token_usage = response.usage.total

    def _final_response_events(self, response: LLMResponse) -> list[AgentResponse]:
        """Build source, reasoning, and final-content events for one response."""
        events: list[AgentResponse] = []
        if response.citations or response.sources:
            events.append(
                AgentResponse(
                    type="llm_sources",
                    data=AgentResponseData(
                        chain=MessageChain(
                            type="llm_sources",
                            chain=[
                                Json(
                                    data={
                                        "citations": [
                                            citation.__dict__
                                            for citation in response.citations
                                        ],
                                        "sources": [
                                            source.__dict__
                                            for source in response.sources
                                        ],
                                    }
                                )
                            ],
                        )
                    ),
                )
            )
        if response.reasoning_content:
            events.append(
                AgentResponse(
                    type="llm_result",
                    data=AgentResponseData(
                        chain=MessageChain(type="reasoning").message(
                            response.reasoning_content,
                        ),
                    ),
                )
            )
        if response.result_chain:
            events.append(
                AgentResponse(
                    type="llm_result",
                    data=AgentResponseData(chain=response.result_chain),
                )
            )
        elif response.completion_text:
            events.append(
                AgentResponse(
                    type="llm_result",
                    data=AgentResponseData(
                        chain=MessageChain().message(response.completion_text),
                    ),
                )
            )
        return events

    def _append_tool_results_to_context(
        self,
        response: LLMResponse,
        result_blocks: list[ToolCallMessageSegment],
        cached_images: list[T.Any],
    ) -> None:
        """Record tool calls and their results for the next provider round."""
        parts = []
        if response.reasoning_content is not None or response.reasoning_signature:
            parts.append(
                ThinkPart(
                    think=response.reasoning_content or "",
                    encrypted=response.reasoning_signature,
                )
            )
        if response.completion_text:
            parts.append(TextPart(text=response.completion_text))
        tool_calls_result = ToolCallsResult(
            tool_calls_info=AssistantMessageSegment(
                tool_calls=response.to_function_tool_calls_model(),
                content=parts or None,
                provider_state=response.provider_state,
            ),
            tool_calls_result=result_blocks,
        )
        self.run_context.messages.extend(tool_calls_result.to_message_models())
        self._append_cached_tool_images(cached_images)
        self.req.append_tool_calls_result(tool_calls_result)

    def _append_cached_tool_images(self, cached_images: list[T.Any]) -> None:
        if not cached_images:
            return
        modalities = self.provider.provider_config.get("modalities", [])
        if not isinstance(modalities, list) or "image" not in modalities:
            return
        image_parts = []
        for cached_image in cached_images:
            image_data = self.tool_image_cache.get_image_base64_by_path(
                cached_image.file_path,
                cached_image.mime_type,
            )
            if image_data is None:
                continue
            base64_data, mime_type = image_data
            image_parts.append(
                TextPart(
                    text=(
                        f"[Image from tool '{cached_image.tool_name}', "
                        f"path='{cached_image.file_path}']"
                    )
                )
            )
            image_parts.append(
                ImageURLPart(
                    image_url=ImageURLPart.ImageURL(
                        url=f"data:{mime_type};base64,{base64_data}",
                        id=cached_image.file_path,
                    )
                )
            )
        if image_parts:
            self.run_context.messages.append(Message(role="user", content=image_parts))
            logger.debug(
                "Appended %d cached image(s) to context for LLM review",
                len(cached_images),
            )

    async def _resolve_skills_like_tool_call(
        self,
        response: LLMResponse,
    ) -> tuple[LLMResponse, bool]:
        """Resolve the second provider pass required by skills-like tools."""
        if self.tool_schema_mode != "skills_like":
            return response, True
        requery_response, _ = await self._resolve_tool_exec(response)
        if not requery_response.tools_call_name:
            return requery_response, False
        response.tools_call_name = requery_response.tools_call_name
        response.tools_call_args = requery_response.tools_call_args
        response.tools_call_ids = requery_response.tools_call_ids
        return response, True

    @override
    async def step(self):
        """Process a single step of the agent.
        This method should return the result of the step.
        """
        if not self.req:
            raise ValueError("Request is not set. Please call reset() first.")

        if self._is_stop_requested():
            yield await self._finalize_aborted_step()
            return

        llm_resp_result = None
        try:
            await self._prepare_step_request()
        except AgentStopRequested:
            yield await self._finalize_aborted_step()
            return

        try:
            async for llm_response in self._iter_llm_responses_with_fallback():
                if llm_response.is_chunk:
                    if self.stats.time_to_first_token == 0:
                        self.stats.time_to_first_token = (
                            time.time() - self.stats.start_time
                        )

                    for response_event in self._streaming_response_events(llm_response):
                        yield response_event
                    if self._is_stop_requested():
                        break
                    continue
                llm_resp_result = llm_response

                self._record_final_response_usage(llm_response)
                # Agent statistics are serialized immediately below. Record the
                # completed model-call boundary first so intermediate tool-loop
                # updates and the final update carry a meaningful duration.
                self.stats.end_time = time.time()
                yield AgentResponse(
                    type="agent_stats",
                    data=AgentResponseData(
                        chain=MessageChain(
                            type="agent_stats",
                            chain=[Json(data=self.stats.to_dict())],
                        )
                    ),
                )
                break  # got final response
        except AgentStopRequested:
            yield await self._finalize_aborted_step()
            return

        if not llm_resp_result:
            if self._is_stop_requested():
                llm_resp_result = LLMResponse(role="assistant", completion_text="")
            else:
                return

        if self._is_stop_requested():
            yield await self._finalize_aborted_step(llm_resp_result)
            return

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

        if not llm_resp.tools_call_name:
            await self._complete_with_assistant_response(llm_resp)

        for response_event in self._final_response_events(llm_resp):
            yield response_event
        # 如果有工具调用，还需处理工具调用
        if llm_resp.tools_call_name:
            try:
                (
                    resolved_response,
                    should_execute_tools,
                ) = await self._resolve_skills_like_tool_call(llm_resp)
            except AgentStopRequested:
                yield await self._finalize_aborted_step()
                return
            if not should_execute_tools:
                logger.warning(
                    "skills_like tool re-query returned no tool calls; fallback to assistant response."
                )
                for response_event in self._final_response_events(resolved_response):
                    yield response_event
                await self._complete_with_assistant_response(resolved_response)
                return
            llm_resp = resolved_response

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
                        ar_type: AgentResponseType = (
                            "tool_call_result"
                            if chain.type == "tool_direct_result"
                            else cast(AgentResponseType, chain.type)
                        )
                        yield AgentResponse(
                            type=ar_type,
                            data=AgentResponseData(chain=chain),
                        )
            except AgentStopRequested:
                yield await self._finalize_aborted_step(llm_resp)
                return

            self._append_tool_results_to_context(
                llm_resp,
                tool_call_result_blocks,
                cached_images,
            )

    @override
    async def step_until_done(
        self, max_step: int = 30
    ) -> T.AsyncGenerator[AgentResponse]:
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

    def _resolve_function_tool(
        self,
        req: ProviderRequest,
        tool_name: str,
        tool_args: dict[str, T.Any] | None,
    ) -> tuple[FunctionTool | None, dict[str, T.Any], list[str]]:
        """Resolve a tool and discard arguments outside its declared schema."""
        tool_args = tool_args or {}
        if self.tool_schema_mode == "skills_like" and self._skill_like_raw_tool_set:
            tool_set = self._skill_like_raw_tool_set
        else:
            tool_set = req.func_tool
        if not tool_set:
            return None, tool_args, []

        function_tool = tool_set.get_tool(tool_name)
        available_tools = tool_set.names()
        if not function_tool or not function_tool.handler:
            return function_tool, tool_args, available_tools

        properties = (function_tool.parameters or {}).get("properties", {})
        valid_params = {
            key: value for key, value in tool_args.items() if key in properties
        }
        ignored_params = set(tool_args) - set(valid_params)
        if ignored_params:
            logger.warning("工具 %s 忽略非期望参数: %s", tool_name, ignored_params)
        return function_tool, valid_params, available_tools

    async def _normalize_call_tool_result(
        self,
        result: CallToolResult,
        *,
        tool_call_id: str,
        tool_name: str,
    ) -> tuple[str, list[T.Any]]:
        """Turn MCP result content into text and cached image records."""
        result_parts: list[str] = []
        cached_images: list[T.Any] = []
        structured_content = getattr(result, "structured_content", None)
        if structured_content is None:
            structured_content = getattr(result, "structuredContent", None)
        if structured_content is not None:
            try:
                result_parts.append(
                    "Structured result:\n"
                    + json.dumps(structured_content, ensure_ascii=False, default=str)
                )
            except TypeError, ValueError:
                result_parts.append("The tool returned structured content.")
        for index, content_item in enumerate(result.content or []):
            image_data = None
            mime_type = "image/png"
            if isinstance(content_item, TextContent):
                result_parts.append(content_item.text)
                continue
            if isinstance(content_item, ImageContent):
                image_data = content_item.data
                mime_type = (
                    getattr(content_item, "mime_type", None)
                    or getattr(content_item, "mimeType", None)
                    or mime_type
                )
            elif isinstance(content_item, EmbeddedResource):
                resource = content_item.resource
                if isinstance(resource, TextResourceContents):
                    result_parts.append(resource.text)
                    continue
                if isinstance(resource, BlobResourceContents) and (
                    getattr(resource, "mime_type", None)
                    or getattr(resource, "mimeType", None)
                    or ""
                ).startswith("image/"):
                    image_data = resource.blob
                    mime_type = (
                        getattr(resource, "mime_type", None)
                        or getattr(resource, "mimeType", None)
                        or mime_type
                    )
                else:
                    result_parts.append(
                        "The tool has returned a data type that is not supported."
                    )
                    continue
            elif getattr(content_item, "type", None) == "audio":
                result_parts.append(
                    "The tool returned audio content, which is not available in the "
                    "agent text context."
                )
                continue
            elif getattr(content_item, "type", None) == "resource_link":
                uri = getattr(content_item, "uri", None)
                result_parts.append(
                    f"The tool returned resource link: {uri}."
                    if uri
                    else "The tool returned a resource link."
                )
                continue
            else:
                result_parts.append(
                    "The tool has returned a data type that is not supported."
                )
                continue

            cached_image = self.tool_image_cache.save_image(
                base64_data=image_data,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                index=index,
                mime_type=mime_type,
            )
            cached_images.append(cached_image)
            result_parts.append(
                f"Image returned and cached at path='{cached_image.file_path}'. "
                "Review the image below. Use send_message_to_user to send it to the user if satisfied, "
                f"with type='image' and path='{cached_image.file_path}'."
            )
        return "\n\n".join(result_parts), cached_images

    async def _authorize_tool(self, tool: FunctionTool) -> str | None:
        """Run an optional tool-owned authorization check."""
        authorize = getattr(tool, "authorize", None)
        if not callable(authorize):
            return None
        result = authorize(self.run_context)
        if inspect.isawaitable(result):
            result = await result
        return result if isinstance(result, str) else None

    async def _parallel_tool_settings(self) -> tuple[bool, set[str], int, int]:
        """Read the runtime parallel-tool policy from shared preferences."""
        execution_context = getattr(self.run_context.context, "context", None)
        preferences = getattr(execution_context, "preferences", None)
        if preferences is None:
            return False, set(), 8, 1
        try:
            raw = await preferences.global_get("tool_parallel_execution", {})
        except Exception as exc:  # pragma: no cover - defensive runtime fallback
            logger.warning("读取工具并行策略失败: %s", safe_error("", exc))
            return False, set(), 8, 1
        if not isinstance(raw, dict):
            return False, set(), 8, 1
        allowed_raw = raw.get("allowed_tool_ids", [])
        allowed = (
            {
                value.strip()
                for value in allowed_raw
                if isinstance(value, str) and value.strip()
            }
            if isinstance(allowed_raw, list)
            else set()
        )
        try:
            max_calls = max(1, min(8, int(raw.get("max_calls", 8))))
        except TypeError, ValueError:
            max_calls = 8
        try:
            mcp_max_calls = max(1, min(8, int(raw.get("mcp_max_concurrency", 1))))
        except TypeError, ValueError:
            mcp_max_calls = 1
        return bool(raw.get("enabled", False)), allowed, max_calls, mcp_max_calls

    @staticmethod
    def _parallel_blocked_reason(tool: FunctionTool) -> str | None:
        """Return a stable explanation when a tool cannot run concurrently."""
        if not getattr(tool, "active", True):
            return "Tool is inactive."
        return get_parallel_blocked_reason(tool)

    async def _can_parallelize_function_tools(
        self,
        req: ProviderRequest,
        llm_response: LLMResponse,
    ) -> bool:
        """Return whether this complete model batch can safely run in parallel."""
        enabled, allowed_ids, max_calls, _ = await self._parallel_tool_settings()
        names = llm_response.tools_call_name
        if (
            not enabled
            or len(names) < 2
            or len(names) > max_calls
            or len(llm_response.tools_call_args) != len(names)
            or len(llm_response.tools_call_ids) != len(names)
            or not req.func_tool
        ):
            return False

        for name, args in zip(
            llm_response.tools_call_name,
            llm_response.tools_call_args,
            strict=True,
        ):
            tool, _, _ = self._resolve_function_tool(req, name, args)
            if tool is None:
                return False
            blocked_reason = self._parallel_blocked_reason(tool)
            if blocked_reason is not None or get_tool_id(tool) not in allowed_ids:
                return False
        return True

    async def _execute_parallel_tool_call(
        self,
        req: ProviderRequest,
        tool_name: str,
        tool_args: dict[str, T.Any] | None,
        tool_call_id: str,
        tool_call_streak: int,
        mcp_max_concurrency: int,
    ) -> _ParallelToolOutcome:
        """Execute one already-approved call for the parallel TaskGroup."""
        if self._is_stop_requested():
            raise AgentStopRequested("Agent stop requested before parallel tool start.")
        func_tool, valid_params, available_tools = self._resolve_function_tool(
            req,
            tool_name,
            tool_args,
        )
        guidance = self._build_repeated_tool_call_guidance(tool_name, tool_call_streak)
        if func_tool is None:
            return _ParallelToolOutcome(
                tool_name,
                tool_call_id,
                tool_call_streak,
                f"error: Tool {tool_name} not found. Available tools are: "
                f"{', '.join(available_tools)}{guidance}",
            )

        authorization_error = await self._authorize_tool(func_tool)
        if authorization_error is not None:
            return _ParallelToolOutcome(
                tool_name,
                tool_call_id,
                tool_call_streak,
                authorization_error + guidance,
            )

        final_response: CallToolResult | None = None
        result_parts: list[str] = []
        cached_images: list[T.Any] = []
        hook_started = False
        try:
            try:
                await self.agent_hooks.on_tool_start(
                    self.run_context,
                    func_tool,
                    valid_params,
                )
                hook_started = True
            except Exception as exc:
                logger.error("Error in on_tool_start hook: %s", safe_error("", exc))

            authorization_error = await self._authorize_tool(func_tool)
            if authorization_error is not None:
                return _ParallelToolOutcome(
                    tool_name,
                    tool_call_id,
                    tool_call_streak,
                    authorization_error + guidance,
                )

            if self._is_stop_requested():
                raise AgentStopRequested(
                    "Agent stop requested before parallel tool execution."
                )

            mcp_client = getattr(func_tool, "mcp_client", None)
            configure_parallel_limit = getattr(
                mcp_client, "configure_parallel_limit", None
            )
            if callable(configure_parallel_limit):
                configure_parallel_limit(mcp_max_concurrency)

            executor = self.tool_executor.execute(
                tool=func_tool,
                run_context=self.run_context,
                **valid_params,
            )
            async for resp in self._iter_tool_executor_results(executor):  # type: ignore
                if isinstance(resp, CallToolResult):
                    final_response = resp
                    if (
                        not resp.content
                        and getattr(resp, "structured_content", None) is None
                        and getattr(resp, "structuredContent", None) is None
                    ):
                        result_parts.append(
                            "error: The tool reported an execution error."
                            if bool(
                                getattr(resp, "is_error", False)
                                or getattr(resp, "isError", False)
                            )
                            else "The tool returned no content."
                        )
                        continue
                    inline_result, images = await self._normalize_call_tool_result(
                        resp,
                        tool_call_id=tool_call_id,
                        tool_name=tool_name,
                    )
                    cached_images.extend(images)
                    if inline_result:
                        if bool(
                            getattr(resp, "is_error", False)
                            or getattr(resp, "isError", False)
                        ):
                            inline_result = f"error: {inline_result}"
                        result_parts.append(inline_result)
                elif resp is None:
                    result_parts.append(
                        "error: Direct-send tools are not supported in a parallel batch."
                    )
                else:
                    result_parts.append(
                        "*The tool has returned an unsupported type. Please check "
                        "the tool definition and implementation.*"
                    )
        except AgentStopRequested:
            raise
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "Parallel tool %s failed: %s",
                tool_name,
                safe_error("", exc),
                exc_info=True,
            )
            result_parts.append(f"error: {safe_error('', exc)}")
        finally:
            if hook_started:
                try:
                    await self.agent_hooks.on_tool_end(
                        self.run_context,
                        func_tool,
                        valid_params,
                        final_response,
                    )
                except Exception as exc:
                    logger.error("Error in on_tool_end hook: %s", safe_error("", exc))

        content = "\n\n".join(part for part in result_parts if part)
        if not content:
            content = "The tool returned no content."
        content = await self._materialize_large_tool_result(
            tool_call_id=tool_call_id,
            content=content,
        )
        return _ParallelToolOutcome(
            tool_name,
            tool_call_id,
            tool_call_streak,
            content + guidance,
            cached_images,
            final_response,
        )

    async def _handle_parallel_function_tools(
        self,
        req: ProviderRequest,
        llm_response: LLMResponse,
    ) -> T.AsyncGenerator[_HandleFunctionToolsResult]:
        """Execute an approved model batch concurrently and write it back ordered."""
        if self._is_stop_requested():
            raise AgentStopRequested("Agent stop requested before parallel tools.")
        calls = list(
            zip(
                llm_response.tools_call_name,
                llm_response.tools_call_args,
                llm_response.tools_call_ids,
                strict=True,
            )
        )
        for tool_name, tool_args, tool_call_id in calls:
            if self._is_stop_requested():
                raise AgentStopRequested(
                    "Agent stop requested before emitting a tool call."
                )
            yield _HandleFunctionToolsResult.from_message_chain(
                MessageChain(
                    type="tool_call",
                    chain=[
                        Json(
                            data={
                                "id": tool_call_id,
                                "name": tool_name,
                                "args": tool_args,
                                "ts": time.time(),
                            }
                        )
                    ],
                )
            )

        outcomes: list[_ParallelToolOutcome | None] = [None] * len(calls)
        interrupted = asyncio.Event()
        _, _, _, mcp_max_concurrency = await self._parallel_tool_settings()
        call_streaks = [
            self._track_tool_call_streak(tool_name, tool_args)
            for tool_name, tool_args, _ in calls
        ]

        async def _run_one(index: int, call: tuple[str, dict[str, T.Any], str]) -> None:
            try:
                outcomes[index] = await self._execute_parallel_tool_call(
                    req,
                    call[0],
                    call[1],
                    call[2],
                    call_streaks[index],
                    mcp_max_concurrency,
                )
            except AgentStopRequested:
                interrupted.set()

        async with asyncio.TaskGroup() as task_group:
            for index, call in enumerate(calls):
                if self._is_stop_requested():
                    raise AgentStopRequested(
                        "Agent stop requested before scheduling a tool call."
                    )
                task_group.create_task(
                    _run_one(index, call),
                    name=f"parallel-tool:{call[0]}:{call[2]}",
                )

        if interrupted.is_set():
            raise AgentStopRequested("Parallel tool execution interrupted.")

        result_blocks: list[ToolCallMessageSegment] = []
        for outcome in outcomes:
            if outcome is None:
                continue
            for cached_image in outcome.cached_images:
                yield _HandleFunctionToolsResult.from_cached_image(cached_image)
            block = ToolCallMessageSegment(
                role="tool",
                tool_call_id=outcome.tool_call_id,
                content=self._merge_follow_up_notice(outcome.content),
            )
            result_blocks.append(block)
            yield _HandleFunctionToolsResult.from_message_chain(
                MessageChain(
                    type="tool_call_result",
                    chain=[
                        Json(
                            data={
                                "id": outcome.tool_call_id,
                                "ts": time.time(),
                                "result": str(block.content),
                            }
                        )
                    ],
                )
            )
            logger.info("Tool `%s` Result: %s", outcome.tool_name, outcome.content)

        if result_blocks:
            yield _HandleFunctionToolsResult.from_tool_call_result_blocks(result_blocks)

    async def _handle_function_tools(
        self,
        req: ProviderRequest,
        llm_response: LLMResponse,
    ) -> T.AsyncGenerator[_HandleFunctionToolsResult]:
        """处理函数工具调用。"""
        if self._is_stop_requested():
            raise AgentStopRequested("Agent stop requested before tool execution.")
        if await self._can_parallelize_function_tools(req, llm_response):
            async for result in self._handle_parallel_function_tools(req, llm_response):
                yield result
            return

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
            if self._is_stop_requested():
                raise AgentStopRequested(
                    "Agent stop requested before emitting a tool call."
                )
            tool_result_blocks_start = len(tool_call_result_blocks)
            tool_call_streak = self._track_tool_call_streak(
                func_tool_name,
                func_tool_args,
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
                            }
                        )
                    ],
                )
            )
            try:
                if not req.func_tool:
                    return

                func_tool, valid_params, available_tools = self._resolve_function_tool(
                    req,
                    func_tool_name,
                    func_tool_args,
                )
                func_tool_args = func_tool_args or {}
                logger.info(f"使用工具：{func_tool_name}，参数：{func_tool_args}")

                if not func_tool:
                    logger.warning(f"未找到指定的工具: {func_tool_name}，将跳过。")
                    _append_tool_call_result(
                        func_tool_id,
                        f"error: Tool {func_tool_name} not found. Available tools are: {', '.join(available_tools)}",
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

                if self._is_stop_requested():
                    raise AgentStopRequested(
                        "Agent stop requested before tool execution."
                    )

                executor = self.tool_executor.execute(
                    tool=func_tool,
                    run_context=self.run_context,
                    **valid_params,  # 只传递有效的参数
                )

                _final_resp: CallToolResult | None = None
                async for resp in self._iter_tool_executor_results(executor):  # type: ignore
                    if isinstance(resp, CallToolResult):
                        res = resp
                        _final_resp = resp
                        if (
                            not res.content
                            and getattr(res, "structured_content", None) is None
                            and getattr(res, "structuredContent", None) is None
                        ):
                            _append_tool_call_result(
                                func_tool_id,
                                "error: The tool reported an execution error."
                                if bool(
                                    getattr(res, "is_error", False)
                                    or getattr(res, "isError", False)
                                )
                                else "The tool returned no content.",
                            )
                            continue

                        (
                            inline_result,
                            cached_images,
                        ) = await self._normalize_call_tool_result(
                            res,
                            tool_call_id=func_tool_id,
                            tool_name=func_tool_name,
                        )
                        for cached_image in cached_images:
                            yield _HandleFunctionToolsResult.from_cached_image(
                                cached_image
                            )
                        if inline_result:
                            if bool(
                                getattr(res, "is_error", False)
                                or getattr(res, "isError", False)
                            ):
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
                        # Tool 直接请求发送消息给用户
                        # 这里我们将直接结束 Agent Loop
                        # 发送消息逻辑在 ToolExecutor 中处理了
                        logger.warning(
                            f"{func_tool_name} 没有返回值，或者已将结果直接发送给用户。"
                        )
                        self._transition_state(AgentState.DONE)
                        self.stats.end_time = time.time()
                        _append_tool_call_result(
                            func_tool_id,
                            "The tool has no return value, or has sent the result directly to the user."
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
                if isinstance(e, AgentStopRequested):
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
        if self._is_stop_requested():
            raise AgentStopRequested(
                "Agent stop requested before skills-like re-query."
            )
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
                requery_resp = await self._await_stop_interruptibly(
                    self.provider.text_chat(
                        contexts=self._sanitize_contexts_for_provider(contexts),
                        func_tool=param_subset,
                        model=self.req.model,
                        session_id=self.req.session_id,
                        extra_user_content_parts=self.req.extra_user_content_parts,
                        # tool_choice="required",
                        abort_signal=self._abort_signal,
                        request_max_retries=self.request_max_retries,
                    )
                )
                if requery_resp:
                    llm_resp = requery_resp
                    self._sanitize_malformed_tool_calls(llm_resp)

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
                    repair_resp = await self._await_stop_interruptibly(
                        self.provider.text_chat(
                            contexts=self._sanitize_contexts_for_provider(
                                repair_contexts
                            ),
                            func_tool=param_subset,
                            model=self.req.model,
                            session_id=self.req.session_id,
                            extra_user_content_parts=self.req.extra_user_content_parts,
                            # tool_choice="required",
                            abort_signal=self._abort_signal,
                            request_max_retries=self.request_max_retries,
                        )
                    )
                    if repair_resp:
                        llm_resp = repair_resp
                        self._sanitize_malformed_tool_calls(llm_resp)

        return llm_resp, subset

    def done(self) -> bool:
        """检查 Agent 是否已完成工作"""
        return self._state in (AgentState.DONE, AgentState.ERROR)

    def request_stop(self) -> None:
        self._abort_signal.set()
        for operation in tuple(self._inflight_operations):
            if not operation.done():
                operation.cancel()

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
        if self._aborted:
            return AgentResponse(
                type="aborted",
                data=AgentResponseData(chain=MessageChain(type="aborted")),
            )
        llm_resp = LLMResponse(
            role="assistant",
            completion_text=self.STOP_HISTORY_ASSISTANT_TEXT,
        )
        self.final_llm_resp = llm_resp
        self._aborted = True
        self._transition_state(AgentState.DONE)
        self.stats.end_time = time.time()

        await self._notify_agent_done(llm_resp)

        self._resolve_unconsumed_follow_ups()
        return AgentResponse(
            type="aborted",
            data=AgentResponseData(chain=MessageChain(type="aborted")),
        )

    async def _close_executor(self, executor: T.Any) -> None:
        close_executor = getattr(executor, "aclose", None)
        if close_executor is None:
            return
        await self._close_async_generator(executor)

    async def _iter_tool_executor_results(
        self,
        executor: T.AsyncGenerator[ToolExecutorResultT],
    ) -> T.AsyncGenerator[ToolExecutorResultT]:
        async def _next_executor_result() -> ToolExecutorResultT:
            return await anext(executor)

        while True:
            if self._is_stop_requested():
                await self._close_executor(executor)
                raise AgentStopRequested(
                    "Tool execution interrupted before reading the next tool result."
                )

            try:
                yield await self._await_stop_interruptibly(
                    _next_executor_result(),
                    close_after_stop=lambda: self._close_executor(executor),
                )
            except StopAsyncIteration:
                return
            except AgentStopRequested:
                await self._close_executor(executor)
                raise
