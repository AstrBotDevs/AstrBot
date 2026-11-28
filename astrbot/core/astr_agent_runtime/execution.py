"""Drive the native loop without rendering or sending platform messages."""

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import aclosing
from typing import TYPE_CHECKING

from astrbot.core.agent.events import (
    ContextUsage,
    ExecutionMetrics,
    RequestFinished,
    RequestStarted,
    RuntimeErrorInfo,
    RuntimeTokenUsage,
    TurnUsage,
    UsageUpdated,
)
from astrbot.core.agent.output import PlainOutput
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runtime import AgentTurn, TurnResult, TurnStatus
from astrbot.core.agent_output_content import content_from_chain
from astrbot.core.astr_agent_runtime.history import ConversationHistoryObserver
from astrbot.core.astr_agent_runtime.runner import AgentRunner, _watch_agent_stop_signal

if TYPE_CHECKING:
    from astrbot.core.agent.conversation_events import ConversationEventWriter
    from astrbot.core.astr_agent_runtime.context import AstrAgentContext
    from astrbot.core.astr_agent_runtime.main_agent.config import MainAgentBuildConfig
    from astrbot.core.provider.entities import ProviderRequest
    from astrbot.core.provider.provider import Provider
    from astrbot.core.star.context import Context


SANDBOX_TOOL_RESULT_OVERFLOW_PREFIX = ".astrbot_tool_overflow_"


def create_sandbox_tool_result_overflow_writer(
    context: "Context",
    umo: str,
) -> Callable[[str, str], Awaitable[str]]:
    """Create an async writer that spills oversized tool results into a sandbox.

    Args:
        context: Host service context used to resolve the session sandbox booter.
        umo: Unified message origin identifying the sandbox session.

    Returns:
        Async callback accepting ``(file_name, content)`` and returning a
        sandbox path readable by ``astrbot_file_read_tool``.
    """
    from astrbot.core.astr_agent_runtime.computer import computer_client
    from astrbot.core.astr_agent_runtime.computer.booters.local import LocalBooter

    async def _write_to_sandbox(file_name: str, content: str) -> str:
        booter = await computer_client.get_booter(context, umo)
        if isinstance(booter, LocalBooter):
            raise RuntimeError(
                "Active computer-use runtime switched to local; refusing to "
                "write sandbox tool overflow file to host working directory."
            )
        # Write flat hidden files in the sandbox workspace root because sandbox
        # filesystem APIs (such as Bay/Shipyard) are jailed to the workspace
        # root and may not create parent directories automatically.
        target_path = f"{SANDBOX_TOOL_RESULT_OVERFLOW_PREFIX}{file_name}"
        result = await booter.fs.write_file(
            path=target_path,
            content=content,
            mode="w",
            encoding="utf-8",
        )
        if not isinstance(result, dict) or not result.get("success", False):
            error_detail = ""
            if isinstance(result, dict):
                error_detail = str(
                    result.get("error")
                    or result.get("stderr")
                    or result.get("message")
                    or ""
                ).strip()
            raise RuntimeError(error_detail or "unknown sandbox filesystem write error")
        written_path = result.get("path")
        if isinstance(written_path, str) and written_path.strip():
            return written_path.strip()
        return target_path

    return _write_to_sandbox


async def create_native_runner(
    context: "Context",
    provider: "Provider",
    request: "ProviderRequest",
    config: "MainAgentBuildConfig",
    agent_context: "AstrAgentContext",
    *,
    fallback_providers: list["Provider"] | None = None,
    writer: "ConversationEventWriter | None" = None,
) -> AgentRunner:
    """Initialize the native loop identically for main and delegated requests.

    Args:
        context: Host provider and tool services.
        provider: Selected model for this request.
        request: Prepared prompt, history and authorized tools.
        config: Effective execution settings for this session.
        agent_context: Current permissions, event and session identity.
        fallback_providers: Already-selected image-compatible fallbacks, if any.
        writer: Host-owned writer for this conversation, when bound.

    Returns:
        A runner ready for the shared native execution lifecycle.
    """
    from astrbot.core.astr_agent_runtime.hooks import MainAgentHooks
    from astrbot.core.astr_agent_runtime.main_agent import providers
    from astrbot.core.astr_agent_runtime.tool_executor import FunctionToolExecutor
    from astrbot.core.utils.astrbot_path import get_astrbot_system_tmp_path
    from astrbot.core.utils.llm_metadata import LLM_METADATAS

    max_context_tokens = provider.provider_config.get("max_context_tokens", 0)
    if max_context_tokens <= 0:
        model_info = LLM_METADATAS.get(provider.get_model())
        max_context_tokens = (
            model_info["limit"]["context"]
            if model_info
            else config.fallback_max_context_tokens
        )
    runner = AgentRunner()
    candidate_read_tool = (
        request.func_tool.get_tool("astrbot_file_read_tool")
        if request.func_tool
        else None
    )
    read_tool = (
        candidate_read_tool
        if candidate_read_tool is not None and candidate_read_tool.active
        else None
    )
    use_sandbox_overflow = (
        read_tool is not None and config.computer_use_runtime == "sandbox"
    )
    overflow_dir = (
        get_astrbot_system_tmp_path()
        if read_tool is not None and not use_sandbox_overflow
        else None
    )
    overflow_writer = (
        create_sandbox_tool_result_overflow_writer(
            context, agent_context.event.unified_msg_origin
        )
        if use_sandbox_overflow
        else None
    )
    compression_provider = await providers.resolve_compression_provider(config, context)
    if (
        config.context_limit_reached_strategy == "llm_compress"
        and compression_provider is None
    ):
        compression_provider = provider
    context_observer = ConversationHistoryObserver(writer, request) if writer else None
    await runner.reset(
        provider=provider,
        request=request,
        run_context=ContextWrapper(
            context=agent_context, tool_call_timeout=config.tool_call_timeout
        ),
        tool_executor=FunctionToolExecutor(),
        agent_hooks=MainAgentHooks(request, context_observer=context_observer),
        conversation_event_sink=writer.consume if writer else None,
        streaming=config.streaming_response,
        max_context_tokens=max_context_tokens,
        llm_compress_instruction=config.llm_compress_instruction,
        llm_compress_keep_recent_ratio=config.llm_compress_keep_recent_ratio,
        llm_compress_provider=compression_provider,
        truncate_turns=config.dequeue_context_length,
        enforce_max_turns=config.max_context_length,
        tool_schema_mode=config.tool_schema_mode,
        fallback_providers=fallback_providers
        if fallback_providers is not None
        else providers.resolve_fallback_providers(
            provider, context, config.fallback_provider_ids
        ),
        request_max_retries=config.request_max_retries,
        tool_result_overflow_dir=overflow_dir,
        tool_result_overflow_writer=overflow_writer,
        read_tool=read_tool,
    )
    if context_observer is not None:
        context_observer.runtime_context = runner.run_context
    return runner


async def execute_native_loop(
    runner: AgentRunner, turn: AgentTurn, max_steps: int
) -> TurnResult:
    """Publish native outputs while keeping loop completion inside the runtime.

    Args:
        runner: Prepared native loop, private to this runtime.
        turn: Execution handle receiving presentation events.
        max_steps: Model/tool step budget before forcing a final reply.

    Returns:
        Native outcome; the session commits history before publishing completion.
    """
    event = turn.input.event
    watcher = asyncio.create_task(_watch_agent_stop_signal(runner, event))
    seen: set[str] = set()
    active_requests: set[str] = set()
    input_tokens = output_tokens = cached_tokens = 0
    has_input = has_output = has_cached = False
    complete = True
    usage = TurnUsage()
    try:
        async with aclosing(runner.step_until_done(max_steps)) as responses:
            async for payload in responses:
                if isinstance(payload, RequestStarted):
                    active_requests.add(payload.request_id)
                    if usage.source == "unknown":
                        usage = TurnUsage(source="requests", complete=False)
                if (
                    isinstance(payload, RequestFinished)
                    and payload.request_id not in seen
                ):
                    seen.add(payload.request_id)
                    active_requests.discard(payload.request_id)
                    report = payload.usage
                    complete = (
                        complete
                        and report is not None
                        and report.input_tokens is not None
                        and report.output_tokens is not None
                    )
                    if report is not None:
                        if report.input_tokens is not None:
                            input_tokens += report.input_tokens
                            has_input = True
                        if report.output_tokens is not None:
                            output_tokens += report.output_tokens
                            has_output = True
                        if report.cached_input_tokens is not None:
                            cached_tokens += report.cached_input_tokens
                            has_cached = True
                    usage = TurnUsage(
                        source="requests",
                        complete=complete,
                        tokens=RuntimeTokenUsage(
                            input_tokens=input_tokens if has_input else None,
                            output_tokens=output_tokens if has_output else None,
                            cached_input_tokens=cached_tokens if has_cached else None,
                        ),
                        context=ContextUsage(
                            tokens=report.input_tokens if report is not None else None,
                            limit=runner.request_context_manager_config.max_context_tokens
                            if runner.request_context_manager_config.max_context_tokens
                            > 0
                            else None,
                        ),
                    )
                turn.emit(payload)
                if isinstance(payload, RequestFinished):
                    turn.emit(UsageUpdated(usage=usage, metrics=ExecutionMetrics()))
    finally:
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)
        if active_requests:
            usage = usage.model_copy(update={"complete": False})
        metrics = ExecutionMetrics(
            duration_ms=max(0, runner.stats.end_time - runner.stats.start_time) * 1000,
            first_token_ms=runner.stats.time_to_first_token * 1000
            if runner.stats.time_to_first_token
            else None,
            steps=runner._step_budget_used,
        )
        turn.emit(UsageUpdated(usage=usage, metrics=metrics))

    response = runner.get_final_llm_resp()
    cancelled = runner.was_aborted()
    error = response is not None and response.role == "err"
    content = content_from_chain(response.result_chain) if response else ()
    if not content and response is not None and response.completion_text:
        content = (PlainOutput(text=response.completion_text),)
    return TurnResult(
        status=TurnStatus.CANCELLED
        if cancelled
        else TurnStatus.FAILED
        if error
        else TurnStatus.COMPLETED,
        content=content if not error else (),
        error=RuntimeErrorInfo(code="provider_error", message=response.completion_text)
        if error and response is not None
        else None,
        reason=runner.run_context.run_end_reason or "completed",
        usage=usage,
        metrics=metrics,
    )
