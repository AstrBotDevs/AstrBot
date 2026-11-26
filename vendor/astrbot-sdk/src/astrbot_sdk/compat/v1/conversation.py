"""Legacy ConversationManager facade over the conversation capability."""

from __future__ import annotations

import json
from typing import Any

from ...conversations import ConversationPatch, Message
from ...events import UMO, MessageType
from .po import Conversation
from .provider import contexts_to_messages


def umo_from_str(unified_msg_origin: str) -> UMO:
    """Parse one legacy unified_msg_origin string into an SDK UMO."""
    platform_id, message_type, session_id = unified_msg_origin.split(":", 2)
    sdk_type = {
        "FriendMessage": MessageType.PRIVATE,
        "private": MessageType.PRIVATE,
        "GroupMessage": MessageType.GROUP,
        "group": MessageType.GROUP,
    }.get(message_type, MessageType.OTHER)
    return UMO(platform_id, sdk_type, session_id)


def _part_to_openai(part: Any) -> dict:
    from ...conversations import AudioPart, ImagePart, TextPart

    if isinstance(part, TextPart):
        return {"type": "text", "text": part.text}
    if isinstance(part, ImagePart):
        return {"type": "image_url", "image_url": {"url": part.source}}
    if isinstance(part, AudioPart):
        return {"type": "audio_url", "audio_url": part.source}
    return {"type": "text", "text": str(part)}


def message_to_openai(message: Message) -> dict:
    """Convert one SDK Message into the OpenAI dict plugins expect."""
    result: dict[str, Any] = {"role": message.role}
    if message.content is None:
        result["content"] = None
    elif isinstance(message.content, str):
        result["content"] = message.content
    else:
        result["content"] = [_part_to_openai(part) for part in message.content]
    if message.tool_calls:
        result["tool_calls"] = list(message.tool_calls)
    if message.tool_call_id:
        result["tool_call_id"] = message.tool_call_id
    return result


def to_legacy_conversation(conv: Any) -> Conversation:
    """Convert one SDK Conversation DTO into the legacy PO shape."""
    history = json.dumps(
        [message_to_openai(message) for message in conv.messages],
        ensure_ascii=False,
    )
    return Conversation(
        cid=conv.id,
        history=history,
        persona_id=conv.persona_id,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        title=conv.title,
    )


class ConversationManager:
    """Legacy conversation_manager facade bound to one plugin context."""

    def __init__(self, ctx: Any) -> None:
        self._ctx = ctx
        self._last_umo: UMO | None = None

    def _track(self, umo: UMO) -> UMO:
        self._last_umo = umo
        return umo

    async def get_curr_conversation_id(
        self,
        unified_msg_origin: str,
    ) -> str | None:
        umo = self._track(umo_from_str(unified_msg_origin))
        conv = await self._ctx.conversations.current(umo)
        return conv.id if conv is not None else None

    async def get_conversation(
        self,
        unified_msg_origin: str,
        conversation_id: str,
        create_if_not_exists: bool = False,
    ) -> Conversation | None:
        umo = self._track(umo_from_str(unified_msg_origin))
        conv = await self._ctx.conversations.get(umo, conversation_id)
        if conv is None and create_if_not_exists:
            conv = await self._ctx.conversations.create(umo)
        return to_legacy_conversation(conv) if conv is not None else None

    async def get_conversations(
        self,
        unified_msg_origin: str | None = None,
        platform_id: str | None = None,
    ) -> list[Conversation]:
        if unified_msg_origin is None:
            if self._last_umo is None:
                return []
            umo = self._last_umo
        else:
            umo = self._track(umo_from_str(unified_msg_origin))
        items: list[Conversation] = []
        cursor = None
        while True:
            page = await self._ctx.conversations.list(umo, cursor=cursor, limit=50)
            items.extend(to_legacy_conversation(conv) for conv in page.items)
            if page.next_cursor is None:
                return items
            cursor = page.next_cursor

    async def new_conversation(
        self,
        unified_msg_origin: str,
        platform_id: str | None = None,
        content: list[dict] | None = None,
        title: str | None = None,
        persona_id: str | None = None,
    ) -> str:
        umo = self._track(umo_from_str(unified_msg_origin))
        conv = await self._ctx.conversations.create(
            umo,
            title=title,
            persona_id=persona_id,
            messages=tuple(contexts_to_messages(content)),
        )
        return conv.id

    async def switch_conversation(
        self,
        unified_msg_origin: str,
        conversation_id: str,
    ) -> None:
        umo = self._track(umo_from_str(unified_msg_origin))
        await self._ctx.conversations.set_current(umo, conversation_id)

    async def delete_conversation(
        self,
        unified_msg_origin: str,
        conversation_id: str,
    ) -> None:
        umo = self._track(umo_from_str(unified_msg_origin))
        await self._ctx.conversations.delete(umo, conversation_id)

    async def delete_conversations_by_user_id(
        self,
        unified_msg_origin: str,
    ) -> None:
        umo = umo_from_str(unified_msg_origin)
        for conv in await self.get_conversations(unified_msg_origin):
            await self._ctx.conversations.delete(umo, conv.cid)

    async def update_conversation(
        self,
        unified_msg_origin: str,
        conversation_id: str | None = None,
        history: list[dict] | None = None,
        title: str | None = None,
        persona_id: str | None = None,
        token_usage: int | None = None,
    ) -> None:
        umo = self._track(umo_from_str(unified_msg_origin))
        if not conversation_id:
            conversation_id = await self.get_curr_conversation_id(
                unified_msg_origin,
            )
        if not conversation_id:
            return
        patch = ConversationPatch(
            title=title,
            persona_id=persona_id,
            messages=(
                tuple(contexts_to_messages(history)) if history is not None else None
            ),
        )
        await self._ctx.conversations.update(umo, conversation_id, patch)

    async def add_message_pair(
        self,
        cid: str,
        user_message: Any,
        assistant_message: Any,
    ) -> None:
        """Append a user/assistant message pair to one conversation.

        The legacy signature carries no UMO; the facade reuses the UMO of
        the most recent conversation call.
        """
        if self._last_umo is None:
            raise ValueError(
                "add_message_pair needs a prior conversation call to bind "
                "the session UMO"
            )
        pair = []
        for message in (user_message, assistant_message):
            if hasattr(message, "model_dump"):
                message = message.model_dump()
            pair.extend(contexts_to_messages([message]))
        await self._ctx.conversations.append(self._last_umo, cid, tuple(pair))
