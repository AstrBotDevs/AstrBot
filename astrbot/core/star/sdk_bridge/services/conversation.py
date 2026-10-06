from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from astrbot_sdk.conversations import (
    Conversation,
    ConversationPage,
    ConversationPatch,
    Message,
)
from astrbot_sdk.errors import InvalidRequest, NotFound

from ..convert import to_core_chain, to_umo_string

if TYPE_CHECKING:
    from astrbot.core.conversation_mgr import ConversationManager
    from astrbot.core.db.po import Conversation as ConversationPO
    from astrbot.core.star.context import Context


def _content_to_text(content: Any) -> str:
    """Flatten one OpenAI-style message content into plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(part.get("text", ""))
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    return str(content)


def to_sdk_conversation(conv: ConversationPO) -> Conversation:
    """Convert a core conversation PO into the SDK DTO.

    Args:
        conv: Core conversation with the JSON-string history field.

    Returns:
        Immutable SDK conversation with structured messages.
    """
    try:
        history = json.loads(conv.history) if conv.history else []
    except json.JSONDecodeError:
        history = []
    messages = tuple(
        Message(
            role=str(item.get("role", "")),
            content=(
                _content_to_text(item["content"])
                if item.get("content") is not None
                else None
            ),
            tool_calls=(
                tuple(item["tool_calls"])
                if item.get("tool_calls") is not None
                else None
            ),
            tool_call_id=(
                str(item["tool_call_id"])
                if item.get("tool_call_id") is not None
                else None
            ),
        )
        for item in history
        if isinstance(item, dict)
    )
    return Conversation(
        id=str(conv.cid),
        title=conv.title or None,
        persona_id=conv.persona_id or None,
        messages=messages,
        created_at=(
            datetime.fromtimestamp(conv.created_at, UTC) if conv.created_at else None
        ),
        updated_at=(
            datetime.fromtimestamp(conv.updated_at, UTC) if conv.updated_at else None
        ),
    )


def _to_history(messages: Any) -> list[dict[str, Any]]:
    """Convert SDK messages into the core history format.

    Mirrors the core serializer: tool_calls and tool_call_id are only present
    when set.
    """
    history = []
    for message in messages:
        item: dict[str, Any] = {"role": message.role, "content": message.content}
        if message.tool_calls is not None:
            item["tool_calls"] = [dict(call) for call in message.tool_calls]
        if message.tool_call_id is not None:
            item["tool_call_id"] = message.tool_call_id
        history.append(item)
    return history


class ConversationServiceBase:
    """Shared helpers for the conversation capability services."""

    def __init__(self, context: Context) -> None:
        """Initialize the service.

        Args:
            context: AstrBot star context with the conversation manager.
        """
        self._context = context

    @property
    def _manager(self) -> ConversationManager:
        return self._context.conversation_manager

    @staticmethod
    def _umo(payload: dict[str, Any]) -> str:
        umo = payload.get("umo")
        if umo is None:
            raise InvalidRequest("conversation operation requires umo")
        return to_umo_string(umo)

    @staticmethod
    def _cid(payload: dict[str, Any]) -> str:
        cid = payload.get("conversation_id")
        if not isinstance(cid, str) or not cid:
            raise InvalidRequest("conversation_id must be a non-empty string")
        return cid


class ConversationReadService(ConversationServiceBase):
    """Read operations for the conversation.read capability."""

    capability_id = "conversation.read"

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        """Serve current/get/list operations."""
        if operation == "current":
            umo = self._umo(payload)
            cid = await self._manager.get_curr_conversation_id(umo)
            if cid is None:
                return {"conversation": None}
            conv = await self._manager.get_conversation(umo, cid)
            return {
                "conversation": (
                    to_sdk_conversation(conv) if conv is not None else None
                ),
            }
        if operation == "get":
            conv = await self._manager.get_conversation(
                self._umo(payload),
                self._cid(payload),
            )
            return {
                "conversation": (
                    to_sdk_conversation(conv) if conv is not None else None
                ),
            }
        if operation == "list":
            umo = self._umo(payload)
            cursor = payload.get("cursor")
            limit = payload.get("limit", 50)
            offset = int(cursor) if isinstance(cursor, str) and cursor else 0
            limit = max(1, min(int(limit), 200))
            convs = await self._manager.get_conversations(umo)
            page_items = convs[offset : offset + limit]
            next_offset = offset + limit
            return {
                "page": ConversationPage(
                    items=tuple(to_sdk_conversation(conv) for conv in page_items),
                    next_cursor=(
                        str(next_offset) if next_offset < len(convs) else None
                    ),
                ),
            }
        raise NotFound(f"unknown conversation operation: {operation}")


class ConversationWriteService(ConversationServiceBase):
    """Write operations for the conversation.write capability."""

    capability_id = "conversation.write"

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        """Serve create/set_current/update/append/delete operations."""
        if operation == "create":
            umo = self._umo(payload)
            cid = await self._manager.new_conversation(
                umo,
                content=_to_history(payload.get("messages", [])),
                title=payload.get("title"),
                persona_id=payload.get("persona_id"),
            )
            conv = await self._manager.get_conversation(umo, cid)
            return {"conversation": to_sdk_conversation(conv)}
        if operation == "set_current":
            await self._manager.switch_conversation(
                self._umo(payload),
                self._cid(payload),
            )
            return {}
        if operation == "update":
            umo = self._umo(payload)
            cid = self._cid(payload)
            patch = payload.get("patch")
            if not isinstance(patch, ConversationPatch):
                raise InvalidRequest("update requires a ConversationPatch")
            await self._manager.update_conversation(
                umo,
                cid,
                title=patch.title,
                persona_id=patch.persona_id,
                history=(
                    _to_history(list(patch.messages))
                    if patch.messages is not None
                    else None
                ),
            )
            conv = await self._manager.get_conversation(umo, cid)
            if conv is None:
                raise NotFound(f"conversation not found: {cid}")
            return {"conversation": to_sdk_conversation(conv)}
        if operation == "append":
            umo = self._umo(payload)
            cid = self._cid(payload)
            conv = await self._manager.get_conversation(umo, cid)
            if conv is None:
                raise NotFound(f"conversation not found: {cid}")
            try:
                history = json.loads(conv.history) if conv.history else []
            except json.JSONDecodeError:
                history = []
            history.extend(_to_history(payload.get("messages", [])))
            await self._manager.update_conversation(umo, cid, history=history)
            return {}
        if operation == "delete":
            await self._manager.delete_conversation(
                self._umo(payload),
                self._cid(payload),
            )
            return {}
        raise NotFound(f"unknown conversation operation: {operation}")


def _serialize_history(record: Any) -> dict[str, Any]:
    """Serialize one PlatformMessageHistory row to a JSON-safe dict."""
    created_at = getattr(record, "created_at", None)
    updated_at = getattr(record, "updated_at", None)
    return {
        "id": record.id,
        "platform_id": record.platform_id,
        "user_id": record.user_id,
        "sender_id": record.sender_id,
        "sender_name": record.sender_name,
        "content": record.content,
        "llm_checkpoint_id": record.llm_checkpoint_id,
        "created_at": created_at.isoformat() if created_at else None,
        "updated_at": updated_at.isoformat() if updated_at else None,
    }


class MessageHistoryService:
    """Platform message history access for isolated legacy plugins.

    Mirrors ``context.message_history_manager``; only granted to legacy
    plugins so their transcript bookkeeping keeps working.
    """

    capability_id = "message.history"

    def __init__(self, context: Context) -> None:
        """Initialize the service.

        Args:
            context: AstrBot star context with the history manager.
        """
        self._context = context

    @property
    def _manager(self) -> Any:
        return self._context.message_history_manager

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        """Serve one message.history operation."""
        if operation == "insert":
            record = await self._manager.insert(
                platform_id=self._required(payload, "platform_id"),
                user_id=self._required(payload, "user_id"),
                content=payload.get("content") or {},
                sender_id=payload.get("sender_id"),
                sender_name=payload.get("sender_name"),
                llm_checkpoint_id=payload.get("llm_checkpoint_id"),
                max_messages=payload.get("max_messages"),
            )
            return {"record": _serialize_history(record)}
        if operation == "insert_message_chain":
            chain = payload.get("message_chain")
            if chain is None:
                raise InvalidRequest("insert_message_chain requires message_chain")
            from astrbot.core.message.message_event_result import (
                MessageChain as CoreChain,
            )

            core_chain = CoreChain(chain=to_core_chain(chain))
            record = await self._manager.insert_message_chain(
                platform_id=self._required(payload, "platform_id"),
                user_id=self._required(payload, "user_id"),
                message_chain=core_chain,
                role=str(payload.get("role") or "user"),
                sender_id=payload.get("sender_id"),
                sender_name=payload.get("sender_name"),
                max_messages=payload.get("max_messages"),
            )
            return {"record": _serialize_history(record) if record else None}
        if operation == "get":
            records = await self._manager.get(
                platform_id=self._required(payload, "platform_id"),
                user_id=self._required(payload, "user_id"),
                page=int(payload.get("page") or 1),
                page_size=int(payload.get("page_size") or 200),
            )
            return {"records": [_serialize_history(record) for record in records]}
        if operation == "count":
            return {
                "count": await self._manager.count(
                    platform_id=self._required(payload, "platform_id"),
                    user_id=self._required(payload, "user_id"),
                ),
            }
        if operation == "delete":
            await self._manager.delete(
                platform_id=self._required(payload, "platform_id"),
                user_id=self._required(payload, "user_id"),
                offset_sec=int(payload.get("offset_sec") or 86400),
            )
            return {}
        if operation == "update":
            await self._manager.update(
                int(self._required(payload, "message_id")),
                content=payload.get("content"),
                llm_checkpoint_id=payload.get("llm_checkpoint_id"),
            )
            return {}
        if operation == "delete_by_id":
            await self._manager.delete_by_id(int(self._required(payload, "message_id")))
            return {}
        raise NotFound(f"unknown message.history operation: {operation}")

    @staticmethod
    def _required(payload: dict[str, Any], key: str) -> Any:
        value = payload.get(key)
        if value is None or value == "":
            raise InvalidRequest(f"message.history operation requires {key}")
        return value
