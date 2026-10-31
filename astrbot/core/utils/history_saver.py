import json

from astrbot import logger
from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.utils.session_lock import session_lock_manager

PROACTIVE_CONVERSATION_ID_KEY = "_proactive_conversation_id"
PROACTIVE_SAVED_TEXTS_KEY = "_proactive_saved_texts"


async def persist_agent_message(
    conversation_manager: ConversationManager,
    *,
    event: AstrMessageEvent,
    conversation_id: str,
    text: str,
) -> None:
    """Record a confirmed delivery while the caller holds the session lock.

    The caller runs this operation in a shielded task so cancellation cannot
    interrupt a delivered message's read-modify-write operation.

    Args:
        conversation_manager: Service used to read and update conversation history.
        event: Proactive event tracking successfully recorded messages.
        conversation_id: Conversation bound when the proactive run started.
        text: Plain text confirmed sent to the current session.
    """
    conversation = await conversation_manager.get_conversation(
        event.unified_msg_origin, conversation_id
    )
    # Do not recreate a deleted conversation or write to the newly selected one.
    if conversation is None:
        return
    history = json.loads(conversation.history or "[]")
    history.append({"role": "assistant", "content": text})
    await conversation_manager.update_conversation(
        event.unified_msg_origin, conversation_id, history=history
    )
    saved_texts = event.get_extra(PROACTIVE_SAVED_TEXTS_KEY, [])
    saved_texts.append(text)
    event.set_extra(PROACTIVE_SAVED_TEXTS_KEY, saved_texts)


async def persist_agent_history(
    conversation_manager: ConversationManager,
    *,
    event: AstrMessageEvent,
    req: ProviderRequest,
    summary_note: str,
) -> None:
    """Append a proactive task summary without overwriting intervening replies.

    Args:
        conversation_manager: Service used to read and update conversation history.
        event: Proactive event identifying the session to lock.
        req: Task request bound to its original conversation.
        summary_note: Task metadata and any final result not already recorded.
    """
    if not req or not req.conversation:
        return

    async with session_lock_manager.acquire_lock(event.unified_msg_origin):
        conversation = await conversation_manager.get_conversation(
            event.unified_msg_origin, req.conversation.cid
        )
        if conversation is None:
            return
        try:
            history = json.loads(conversation.history or "[]")
        except (TypeError, ValueError) as exc:
            logger.warning("Failed to parse conversation history: %s", exc)
            return
        history.append(
            {"role": "user", "content": "Output your last task result below."}
        )
        history.append({"role": "assistant", "content": summary_note})
        await conversation_manager.update_conversation(
            event.unified_msg_origin,
            conversation.cid,
            history=history,
        )
