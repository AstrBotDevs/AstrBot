"""Submit a programmatic main-agent input through the normal event queue."""

import asyncio

from astrbot.core.platform.agent_wakeup_event import AgentWakeupEvent, WakeupSource
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.star.context import Context


async def wake_main_agent(
    ctx: Context,
    *,
    umo: str,
    user_prompt: str,
    source: WakeupSource,
    source_id: str | None = None,
    role: str = "member",
    stop_signal: asyncio.Event | None = None,
) -> None:
    """Queue a triggered user turn without waiting for agent execution.

    Args:
        ctx: Session configuration and agent services.
        umo: UMO whose current conversation supplies the existing context.
        user_prompt: Trigger instructions and data, exclusively for this user turn.
        source: Trigger mechanism, independent of the target session's platform.
        source_id: Cron job ID, background task ID, or invoking plugin ID.
        role: Initiating caller's resolved permission role.
        stop_signal: Optional cancellation signal shared with a background task.

    Raises:
        ValueError: If the source or target session is invalid,
            or the target platform adapter is unavailable.
    """
    if stop_signal is not None and stop_signal.is_set():
        return
    session = MessageSession.from_str(umo)
    platform = ctx.get_platform_inst(session.platform_id)
    if platform is None:
        raise ValueError(
            f"Platform adapter {session.platform_id!r} not found for wakeup UMO {umo!r}."
        )
    event = AgentWakeupEvent(
        context=ctx,
        session=session,
        platform_meta=platform.meta(),
        prompt=user_prompt,
        source=source,
        source_id=source_id,
        role=role,
    )
    if stop_signal is not None:
        event.set_extra("_background_stop_signal", stop_signal)
    await ctx.get_event_queue().put(event)
