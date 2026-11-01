import json

from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import LLMResponse, ProviderRequest


async def persist_agent_history(
    conversation_manager: ConversationManager,
    *,
    event: AstrMessageEvent,
    req: ProviderRequest,
    response: LLMResponse | None,
) -> None:
    """Append the real wakeup turn without rewriting any stored history entries.

    Args:
        conversation_manager: Service owning the current conversation.
        event: Event identifying the session.
        req: Request with its original conversation snapshot and current user turn.
        response: Final assistant response, if the agent produced one.

    Raises:
        ValueError: If stored history cannot be parsed as a message list.
    """
    if not req or not req.conversation:
        return

    history = json.loads(req.conversation.history or "[]")
    if not isinstance(history, list):
        raise ValueError("Conversation history must be a message list.")
    history.append({"role": "user", "content": req.prompt})
    if response and response.role == "assistant":
        history.append({"role": "assistant", "content": response.completion_text})
    await conversation_manager.update_conversation(
        event.unified_msg_origin,
        req.conversation.cid,
        history=history,
    )
