"""Native history commits and execution statistics; never called by Pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING

from astrbot.core import db_helper, logger
from astrbot.core.agent.message import (
    CheckpointData,
    CheckpointMessageSegment,
    Message,
    dump_messages_with_checkpoints,
)
from astrbot.core.agent.response import AgentStats
from astrbot.core.astr_agent_runtime.runner import AgentRunner
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import LLMResponse, ProviderRequest

if TYPE_CHECKING:
    from astrbot.core.star.context import Context


async def save_main_history(
    context: Context,
    event: AstrMessageEvent,
    req: ProviderRequest,
    llm_response: LLMResponse | None,
    all_messages: list[Message],
    runner_stats: AgentStats | None,
    user_aborted: bool = False,
) -> None:
    """Commit native history after a settled or user-aborted execution.

    Args:
        context: Application conversation storage services.
        event: Input owning this execution and checkpoint identity.
        req: Prepared native request with its bound conversation.
        llm_response: Final native response, when one exists.
        all_messages: Runner-owned messages, inspected only inside the runtime.
        runner_stats: Execution statistics used for token accounting.
        user_aborted: Whether partial output belongs to an explicit cancellation.
    """
    if not req or not req.conversation:
        return

    messages_to_save: list[Message] = []
    skipped_initial_system = False
    for message in all_messages:
        if message.role == "system" and not skipped_initial_system:
            skipped_initial_system = True
            continue
        if message.role in ["assistant", "user"] and message._no_save:
            continue
        messages_to_save.append(message)

    checkpoint_id = event.get_extra("llm_checkpoint_id")
    has_checkpoint = isinstance(checkpoint_id, str) and bool(checkpoint_id)
    message_to_save = dump_messages_with_checkpoints(messages_to_save)
    if not user_aborted and (llm_response is None or llm_response.role != "assistant"):
        if has_checkpoint:
            message_to_save.append(
                CheckpointMessageSegment(
                    content=CheckpointData(id=checkpoint_id),
                ).model_dump()
            )
        if has_checkpoint or (llm_response is None and req.tool_calls_result):
            token_usage = None if has_checkpoint else req.conversation.token_usage
            await context.conversation_manager.update_conversation(
                event.unified_msg_origin,
                req.conversation.cid,
                history=message_to_save,
                token_usage=token_usage,
            )
        return

    if llm_response and llm_response.role != "assistant":
        if not user_aborted:
            return
        llm_response = LLMResponse(
            role="assistant",
            completion_text=llm_response.completion_text or "",
        )
    elif llm_response is None:
        llm_response = LLMResponse(role="assistant", completion_text="")

    if (
        not llm_response.completion_text
        and not req.tool_calls_result
        and not user_aborted
    ):
        logger.debug("The LLM response is empty; not saving a record.")
        return

    if isinstance(checkpoint_id, str) and checkpoint_id:
        message_to_save.append(
            CheckpointMessageSegment(
                content=CheckpointData(id=checkpoint_id),
            ).model_dump()
        )

    token_usage = None
    if runner_stats:
        token_usage = llm_response.usage.total if llm_response.usage else None

    await context.conversation_manager.update_conversation(
        event.unified_msg_origin,
        req.conversation.cid,
        history=message_to_save,
        token_usage=token_usage,
    )


async def record_main_stats(
    event: AstrMessageEvent,
    req: ProviderRequest | None,
    agent_runner: AgentRunner | None,
    final_resp: LLMResponse | None,
) -> None:
    """Persist internal agent stats without affecting the user response flow."""
    if agent_runner is None:
        return

    provider = agent_runner.provider
    stats = agent_runner.stats
    if provider is None or stats is None:
        return

    try:
        provider_config = getattr(provider, "provider_config", {}) or {}
        conversation_id = (
            req.conversation.cid
            if req is not None and req.conversation is not None
            else None
        )

        if agent_runner.was_aborted():
            status = "aborted"
        elif final_resp is not None and final_resp.role == "err":
            status = "error"
        else:
            status = "completed"

        await db_helper.insert_provider_stat(
            umo=event.unified_msg_origin,
            conversation_id=conversation_id,
            provider_id=provider_config.get("id", "") or provider.meta().id,
            provider_model=provider.get_model(),
            status=status,
            stats=stats.to_dict(),
            agent_type="internal",
        )
    except Exception as e:
        logger.warning("Persist provider stats failed: %s", e, exc_info=True)
