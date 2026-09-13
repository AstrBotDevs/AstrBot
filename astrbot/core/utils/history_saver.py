import json

from astrbot import logger
from astrbot.core.agent.conversation_events import ConversationEventWriter
from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import ProviderRequest


async def persist_agent_history(
    conversation_manager: ConversationManager,
    *,
    event: AstrMessageEvent,
    req: ProviderRequest,
    summary_note: str,
    conversation_events: ConversationEventWriter | None = None,
) -> None:
    """Persist an autonomous task summary at its host's history-save boundary.

    Args:
        conversation_manager: Legacy conversation API used without a bound writer.
        event: Event identifying the conversation owner.
        req: Request with the original conversation history.
        summary_note: Task result added to future context.
        conversation_events: Explicit host collector for the running turn.
    """
    if not req or not req.conversation:
        return

    history = []
    try:
        history = json.loads(req.conversation.history or "[]")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to parse conversation history: %s", exc)
    history.append({"role": "user", "content": "Output your last task result below."})
    history.append({"role": "assistant", "content": summary_note})
    if conversation_events is not None:
        await conversation_events.save_history(history)
        return
    await conversation_manager.update_conversation(
        event.unified_msg_origin,
        req.conversation.cid,
        history=history,
    )
