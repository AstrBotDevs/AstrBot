"""Drive the native loop without rendering or sending platform messages."""

import asyncio
from contextlib import aclosing
from typing import TYPE_CHECKING

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runtime import AgentTurn, TurnResult, TurnStatus
from astrbot.core.astr_agent_runtime.runner import AgentRunner, _watch_agent_stop_signal

if TYPE_CHECKING:
    from astrbot.core.astr_agent_runtime.context import AstrAgentContext
    from astrbot.core.astr_agent_runtime.main_agent.config import MainAgentBuildConfig
    from astrbot.core.provider.entities import ProviderRequest
    from astrbot.core.provider.provider import Provider
    from astrbot.core.star.context import Context


async def create_native_runner(
    context: "Context",
    provider: "Provider",
    request: "ProviderRequest",
    config: "MainAgentBuildConfig",
    agent_context: "AstrAgentContext",
    *,
    fallback_providers: list["Provider"] | None = None,
) -> AgentRunner:
    """Initialize the native loop identically for main and delegated requests.

    Args:
        context: Host provider and tool services.
        provider: Selected model for this request.
        request: Prepared prompt, history and authorized tools.
        config: Effective execution settings for this session.
        agent_context: Current permissions, event and session identity.
        fallback_providers: Already-selected image-compatible fallbacks, if any.

    Returns:
        A runner ready for the shared native execution lifecycle.
    """
    from astrbot.core.astr_agent_runtime.hooks import MAIN_AGENT_HOOKS
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
    read_tool = (
        request.func_tool.get_tool("astrbot_file_read_tool")
        if request.func_tool
        else None
    )
    compression_provider = await providers.resolve_compression_provider(config, context)
    if (
        config.context_limit_reached_strategy == "llm_compress"
        and compression_provider is None
    ):
        compression_provider = provider
    await runner.reset(
        provider=provider,
        request=request,
        run_context=ContextWrapper(
            context=agent_context, tool_call_timeout=config.tool_call_timeout
        ),
        tool_executor=FunctionToolExecutor(),
        agent_hooks=MAIN_AGENT_HOOKS,
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
        tool_result_overflow_dir=get_astrbot_system_tmp_path() if read_tool else None,
        read_tool=read_tool,
    )
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
    try:
        async with aclosing(runner.step_until_done(max_steps)) as responses:
            async for response in responses:
                turn.emit(response.type, response.data)
    finally:
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)
    turn.emit("step_completed", {"steps": runner._step_budget_used})
    response = runner.get_final_llm_resp()
    cancelled = runner.was_aborted()
    error = response is not None and response.role == "err"
    return TurnResult(
        status=TurnStatus.CANCELLED
        if cancelled
        else TurnStatus.FAILED
        if error
        else TurnStatus.COMPLETED,
        text=response.completion_text if response else "",
        chain=response.result_chain if response else None,
        error=response.completion_text if error and response is not None else None,
        reason=runner.run_context.run_end_reason or "completed",
        usage=runner.stats.to_dict(),
    )
