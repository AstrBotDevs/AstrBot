from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from astrbot_sdk.conversations import (
    Conversation,
    ConversationEvent,
    ConversationPage,
    ConversationPatch,
    ConversationRevision,
    Message,
)
from astrbot_sdk.errors import Conflict, InvalidRequest, NotFound
from astrbot_sdk.events import UMO

from astrbot.core.db.conversation import ConversationConflictError
from astrbot.core.db.po import ConversationRevision as CoreRevision

from ..convert import to_core_content, to_core_context_message, to_umo_string
from .assets import AssetStore

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
        revision=(
            ConversationRevision(conv.revision.head_seq, conv.revision.leaf_event_id)
            if conv.revision is not None
            else None
        ),
        created_at=(
            datetime.fromtimestamp(conv.created_at, UTC) if conv.created_at else None
        ),
        updated_at=(
            datetime.fromtimestamp(conv.updated_at, UTC) if conv.updated_at else None
        ),
    )


class ConversationServiceBase:
    """Shared helpers for the conversation capability services."""

    def __init__(
        self, context: Context, plugin_id: str = "", store: AssetStore | None = None
    ) -> None:
        """Initialize the service.

        Args:
            context: AstrBot star context with the conversation manager.
            plugin_id: Namespaces the calling plugin's custom events.
            store: Resolves attachment references from the calling plugin.
        """
        self._context = context
        self._event_namespace = hashlib.sha256(plugin_id.encode()).hexdigest()
        self._resolve_asset = store.resolve if store is not None else None

    @property
    def _manager(self) -> ConversationManager:
        return self._context.conversation_manager

    @staticmethod
    def _umo(payload: dict[str, Any]) -> str:
        umo = payload.get("umo")
        if not isinstance(umo, UMO):
            raise InvalidRequest("conversation operation requires umo")
        return to_umo_string(umo)

    @staticmethod
    def _cid(payload: dict[str, Any]) -> str:
        cid = payload.get("conversation_id")
        if not isinstance(cid, str) or not cid:
            raise InvalidRequest("conversation_id must be a non-empty string")
        return cid

    async def _owned(self, umo: str, cid: str) -> ConversationPO | None:
        """Read a conversation only in the specified session.

        Args:
            umo: Requested session.
            cid: Conversation identifier.

        Returns:
            A conversation owned by this session, or None.
        """
        conv = await self._manager.get_conversation(umo, cid)
        return conv if conv is not None and conv.user_id == umo else None

    def _event_kind(self, payload: dict[str, Any]) -> str:
        """Validate and namespace one plugin event type.

        Args:
            payload: Operation payload containing an event_type.

        Returns:
            Plugin-specific event type without the storage prefix.

        Raises:
            InvalidRequest: The event name is malformed or too long.
        """
        name = payload.get("event_type")
        if not isinstance(name, str) or not re.fullmatch(
            r"[a-zA-Z0-9_.-]{1,128}", name
        ):
            raise InvalidRequest("invalid plugin event_type")
        return f"{self._event_namespace}.{name}"

    def _history(self, messages: Any) -> list[dict[str, Any]]:
        """Encode typed SDK messages for the conversation event store.

        Args:
            messages: Sequence of SDK messages.

        Returns:
            JSON-compatible Core messages.

        Raises:
            InvalidRequest: A message is not a typed SDK message.
        """
        if not all(isinstance(message, Message) for message in messages):
            raise InvalidRequest("conversation history expects SDK Message values")
        return [
            to_core_context_message(message, resolve_asset=self._resolve_asset)
            for message in messages
        ]


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
            conv = await self._owned(umo, cid)
            return {
                "conversation": (
                    to_sdk_conversation(conv) if conv is not None else None
                ),
            }
        if operation == "get":
            conv = await self._owned(
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
        if operation == "list_plugin_events":
            cid = self._cid(payload)
            if await self._owned(self._umo(payload), cid) is None:
                raise NotFound("conversation not found")
            kind = self._event_kind(payload)
            after_seq, limit = payload.get("after_seq", 0), payload.get("limit", 100)
            if (
                type(after_seq) is not int
                or after_seq < 0
                or type(limit) is not int
                or not 1 <= limit <= 1000
            ):
                raise InvalidRequest("invalid event page cursor or limit")
            events = await self._manager.db.conversation_store.events(
                cid, after_seq=after_seq, event_type=f"plugin.{kind}", limit=limit
            )
            return [
                ConversationEvent(
                    item.event_id,
                    item.seq,
                    payload["event_type"],
                    item.payload or {},
                    item.created_at,
                )
                for item in events
            ]
        raise NotFound(f"unknown conversation operation: {operation}")


class ConversationWriteService(ConversationServiceBase):
    """Write operations for the conversation.write capability."""

    capability_id = "conversation.write"

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        """Serve create/set_current/update/append/delete operations."""
        umo = self._umo(payload)
        if operation == "fork":
            source = payload.get("source_event_id")
            if not isinstance(source, str) or not source:
                raise InvalidRequest("fork requires a source_event_id")
            try:
                return await self._manager.fork_conversation(umo, source)
            except ValueError as exc:
                raise InvalidRequest(str(exc)) from exc
        if operation == "create":
            cid = await self._manager.new_conversation(
                umo,
                content=self._history(payload.get("messages", [])),
                title=payload.get("title"),
                persona_id=payload.get("persona_id"),
            )
            conv = await self._owned(umo, cid)
            return {"conversation": to_sdk_conversation(conv)}
        if operation not in {
            "set_current",
            "update",
            "append",
            "append_message",
            "append_plugin_event",
            "delete",
        }:
            raise NotFound(f"unknown conversation operation: {operation}")
        cid = self._cid(payload)
        if await self._owned(umo, cid) is None:
            raise NotFound(f"conversation not found: {cid}")
        try:
            if operation == "set_current":
                await self._manager.switch_conversation(umo, cid)
                return {}
            if operation == "update":
                patch = payload.get("patch")
                revision = payload.get("expected_revision")
                if not isinstance(patch, ConversationPatch):
                    raise InvalidRequest("update requires a ConversationPatch")
                if revision is not None and not isinstance(
                    revision, ConversationRevision
                ):
                    raise InvalidRequest(
                        "expected_revision must be a ConversationRevision"
                    )
                await self._manager.update_conversation(
                    umo,
                    cid,
                    title=patch.title,
                    persona_id=patch.persona_id,
                    history=self._history(patch.messages)
                    if patch.messages is not None
                    else None,
                    **(
                        {
                            "expected_revision": CoreRevision(
                                revision.head_seq, revision.leaf_event_id
                            )
                        }
                        if revision is not None
                        else {}
                    ),
                )
                conv = await self._owned(umo, cid)
                if conv is None:
                    raise NotFound(f"conversation not found: {cid}")
                return {"conversation": to_sdk_conversation(conv)}
            if operation == "append":
                await self._manager.db.conversation_store.append(
                    cid,
                    [
                        {"type": "message.appended", "payload": {"message": message}}
                        for message in self._history(payload.get("messages", []))
                    ],
                )
                return {}
            if operation == "append_message":
                content = to_core_content(
                    payload.get("content"), resolve_asset=self._resolve_asset
                )
                return await self._manager.append_message(
                    content, cid=cid, message_id=payload.get("message_id")
                )
            if operation == "append_plugin_event":
                return await self._manager.append_plugin_event(
                    self._event_kind(payload),
                    payload.get("data"),
                    cid=cid,
                    event_id=payload.get("event_id"),
                )
            await self._manager.delete_conversation(umo, cid)
            return {}
        except ConversationConflictError as exc:
            raise Conflict(str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise InvalidRequest(str(exc)) from exc
