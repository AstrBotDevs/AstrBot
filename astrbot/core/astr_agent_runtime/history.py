"""Native history commits and execution statistics; never called by Pipeline."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from astrbot.core import db_helper, logger
from astrbot.core.agent.message import (
    Message,
    dump_messages,
)
from astrbot.core.agent.response import AgentStats
from astrbot.core.astr_agent_runtime.runner import AgentRunner
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import LLMResponse, ProviderRequest

if TYPE_CHECKING:
    from astrbot.core.agent.conversation_events import ConversationEventWriter


class ConversationHistoryObserver:
    """Adapt mutable host context to staged events at plugin boundaries."""

    def __init__(
        self, writer: ConversationEventWriter, request: ProviderRequest | None = None
    ):
        """Bind one execution's persistence and its legacy request context.

        Args:
            writer: Revision-bound event writer owned by the host.
            request: Request used before a native runtime context is available.
        """
        self.writer = writer
        self.request = request
        self.runtime_context = None

    def __call__(self, origin: str) -> None:
        """Stage context changes without exposing host objects to persistence.

        Args:
            origin: Attribution for changes observed at this boundary.
        """
        if self.writer.closed:
            return
        if self.runtime_context is not None:
            messages = self.runtime_context.messages
            history = dump_messages(
                messages[1:] if messages and messages[0].role == "system" else messages,
                include_temporary=True,
            )
        elif self.request is not None and self.request.conversation is not None:
            history = self.request.contexts
        else:
            return
        self.writer.stage_history(history, origin=origin)


async def save_agent_history(
    *,
    req: ProviderRequest,
    llm_response: LLMResponse | None,
    all_messages: list[Message],
    runner_stats: AgentStats | None,
    commit: Callable[[list[dict], int | None], Awaitable[None]],
    user_aborted: bool = False,
    writer: ConversationEventWriter | None = None,
) -> bool:
    """Commit native history after a settled or user-aborted execution.

    Args:
        req: Prepared native request with its bound conversation.
        llm_response: Final native response, when one exists.
        all_messages: Runner-owned messages, inspected only inside the runtime.
        runner_stats: Execution statistics used for token accounting.
        commit: Storage writer for this session's canonical history.
        user_aborted: Whether partial output belongs to an explicit cancellation.
        writer: Revision-bound writer for event-backed history.

    Returns:
        Whether history was successfully committed.
    """
    if not req or not req.conversation:
        return False

    messages_to_save: list[Message] = []
    skipped_initial_system = False
    for message in all_messages:
        if message.role == "system" and not skipped_initial_system:
            skipped_initial_system = True
            continue
        if (
            writer is None
            and message.role in ["assistant", "user"]
            and message._no_save
        ):
            continue
        messages_to_save.append(message)

    message_to_save = dump_messages(
        messages_to_save, include_temporary=writer is not None
    )
    if not user_aborted and (llm_response is None or llm_response.role != "assistant"):
        if writer is not None and writer.turn_id:
            await writer.save_history(message_to_save)
            return True
        if llm_response is None and req.tool_calls_result:
            token_usage = req.conversation.token_usage
            await commit(message_to_save, token_usage)
            return True
        return False

    if llm_response and llm_response.role != "assistant":
        if not user_aborted:
            return False
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
        return False

    token_usage = None
    if runner_stats:
        token_usage = llm_response.usage.total if llm_response.usage else None

    if writer is None:
        await commit(message_to_save, token_usage)
    else:
        await writer.save_history(message_to_save, token_usage=token_usage)
    return True


async def record_agent_stats(
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
