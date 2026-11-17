"""Prepare built-in tool messages under the owning turn's delivery policy."""

from astrbot.core.agent.events import OutputReady
from astrbot.core.agent_output_content import content_from_chain
from astrbot.core.astr_agent_runtime.context import AstrAgentContext
from astrbot.core.message.message_event_result import MessageChain


def prepare_tool_output(
    agent_context: AstrAgentContext,
    message: MessageChain,
    *,
    target_umo: str | None = None,
) -> bool:
    """Publish prepared content and determine whether the tool may send it.

    Args:
        agent_context: Execution context carrying the turn's delivery policy.
        message: Authorized, prepared message with locally resolved media.
        target_umo: Destination override; defaults to the current conversation.

    Returns:
        Whether the tool should perform its existing platform send.

    Raises:
        RuntimeError: Caller-owned output has no active receiving turn.
        ValueError: Message content cannot be converted to portable output.
    """
    output_turn = agent_context._output_turn
    if output_turn is not None and output_turn.done:
        output_turn = None
    if output_turn is not None:
        output_turn.emit(
            OutputReady(
                target_umo=target_umo or agent_context.event.unified_msg_origin,
                source="tool",
                content=content_from_chain(message),
            )
        )
    elif not agent_context.send_to_user:
        raise RuntimeError("caller-owned delivery requires an active output turn.")
    return agent_context.send_to_user
