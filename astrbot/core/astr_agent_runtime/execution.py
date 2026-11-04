"""Drive the native loop without rendering or sending platform messages."""

import asyncio
from contextlib import aclosing

from astrbot.core.agent.runtime import AgentTurn, TurnResult, TurnStatus
from astrbot.core.astr_agent_runtime.runner import AgentRunner, _watch_agent_stop_signal


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
