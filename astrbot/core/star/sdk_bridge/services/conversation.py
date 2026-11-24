from __future__ import annotations

import hashlib
import json
import re
from typing import TYPE_CHECKING, Any

from astrbot_sdk.conversations import Conversation, ConversationRevision
from astrbot_sdk.errors import CapabilityDenied, Conflict, InvalidRequest, NotFound
from astrbot_sdk.events import UMO

from astrbot.core.db.conversation import ConversationConflictError
from astrbot.core.db.po import ConversationRevision as CoreRevision
from astrbot.core.platform.message_session import MessageSession

from ..convert import _resolve_part_source, to_umo_string
from .assets import AssetStore

if TYPE_CHECKING:
    from astrbot.core.conversation_mgr import ConversationManager
    from astrbot.core.db.po import Conversation as ConversationPO
    from astrbot.core.star.context import Context


def to_sdk_conversation(conv: ConversationPO) -> Conversation:
    """Copy the fields in the public Core conversation snapshot.

    Args:
        conv: Core's detached conversation object.

    Returns:
        The same field values in the SDK's protocol DTO.
    """
    return Conversation(
        platform_id=conv.platform_id,
        user_id=conv.user_id,
        cid=conv.cid,
        history=conv.history,
        title=conv.title,
        persona_id=conv.persona_id,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        token_usage=conv.token_usage,
        revision=(
            ConversationRevision(conv.revision.head_seq, conv.revision.leaf_event_id)
            if conv.revision is not None
            else None
        ),
    )


class ConversationServiceBase:
    """Shared boundaries for conversation capability calls."""

    def __init__(self, context: Context) -> None:
        self._context = context

    @property
    def _manager(self) -> ConversationManager:
        return self._context.conversation_manager

    @staticmethod
    def _umo(payload: dict[str, Any]) -> str:
        """Validate a Core session address or convert the Runner's ambient UMO.

        Args:
            payload: Operation arguments including the session address.

        Returns:
            The Core session address.

        Raises:
            InvalidRequest: The session address is missing or invalid.
        """
        value = payload.get("unified_msg_origin")
        if isinstance(value, UMO):
            value = to_umo_string(value)
        if isinstance(value, str):
            try:
                session = MessageSession.from_str(value)
                if session.platform_id and session.session_id:
                    return value
            except ValueError:
                pass
        raise InvalidRequest(
            "conversation operation requires a valid unified_msg_origin"
        )

    @staticmethod
    def _cid(value: Any) -> str:
        """Validate the requested conversation ID.

        Args:
            value: Argument supplied by the Runner.

        Returns:
            A nonempty conversation ID.

        Raises:
            InvalidRequest: The ID is not a nonempty string.
        """
        if not isinstance(value, str) or not value:
            raise InvalidRequest("conversation ID must be a non-empty string")
        return value


class ConversationReadService(ConversationServiceBase):
    """Expose Core's session-scoped reads to the Runner."""

    capability_id = "conversation.read"

    def __init__(self, context: Context, *, allow_create: bool = False) -> None:
        super().__init__(context)
        self._allow_create = allow_create

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        """Dispatch Core-shaped conversation queries.

        Args:
            operation: Requested read method.
            payload: Runner-supplied method arguments.

        Returns:
            The selected ID, a conversation, or a list of conversations.

        Raises:
            CapabilityDenied: The plugin tried to create without a write grant.
            InvalidRequest: The arguments are invalid.
            NotFound: The requested operation is unknown.
        """
        umo = self._umo(payload)
        if operation == "get_curr_conversation_id":
            return await self._manager.get_curr_conversation_id(umo)
        if operation == "get_conversation":
            cid = self._cid(payload.get("conversation_id"))
            create = payload.get("create_if_not_exists", False)
            if not isinstance(create, bool):
                raise InvalidRequest("create_if_not_exists must be a boolean")
            conv = await self._manager.get_conversation(umo, cid)
            if conv is None and create:
                if not self._allow_create:
                    raise CapabilityDenied(
                        "creating a conversation requires conversation.write"
                    )
                conv = await self._manager.get_conversation(
                    umo, cid, create_if_not_exists=True
                )
            return (
                to_sdk_conversation(conv)
                if conv is not None and conv.user_id == umo
                else None
            )
        if operation == "get_conversations":
            convs = await self._manager.get_conversations(
                umo, platform_id=payload.get("platform_id")
            )
            return [to_sdk_conversation(conv) for conv in convs]
        raise NotFound(f"unknown conversation operation: {operation}")


class ConversationWriteService(ConversationServiceBase):
    """Forward SDK writes to Core's public conversation methods."""

    capability_id = "conversation.write"

    def __init__(
        self, context: Context, plugin_id: str = "", store: AssetStore | None = None
    ) -> None:
        super().__init__(context)
        self._event_namespace = hashlib.sha256(plugin_id.encode()).hexdigest()
        self._resolve_asset = store.resolve if store is not None else None

    def _content(
        self, content: Any, existing_media: set[tuple[str, str]] | None = None
    ) -> Any:
        """Validate portable Core-style message content.

        Args:
            content: Text or serialized content parts from the Runner.
            existing_media: References already stored in the conversation being updated.

        Returns:
            Content with plugin-owned assets resolved for Core.

        Raises:
            InvalidRequest: Parts are invalid or reference unsupported media.
        """
        if content is None or isinstance(content, str):
            return content
        if not isinstance(content, list) or not all(
            isinstance(part, dict) for part in content
        ):
            raise InvalidRequest("content must be text or a list of content objects")
        parts = []
        for part in content:
            kind = part.get("type")
            if kind not in ("image_url", "audio_url"):
                parts.append(part)
                continue
            reference = part.get(kind)
            if not isinstance(reference, dict):
                raise InvalidRequest(f"{kind} must contain a URL or AssetRef")
            source = reference.get("url")
            media_type = "image" if kind == "image_url" else "audio"
            if not isinstance(source, str) or not (
                source.startswith(f"data:{media_type}/")
                or (existing_media is not None and (kind, source) in existing_media)
            ):
                source = _resolve_part_source(source, self._resolve_asset)
            parts.append({**part, kind: {**reference, "url": source}})
        return parts

    def _history(
        self, history: Any, *, previous_history: str | None = None
    ) -> list[dict] | None:
        """Normalize a Core-style list of message dictionaries.

        Args:
            history: Requested conversation history.
            previous_history: Core's prior history when updating the same conversation.

        Returns:
            Message dictionaries with portable media resolved, or None.

        Raises:
            InvalidRequest: History is not a list of message objects.
        """
        if history is None:
            return None
        if not isinstance(history, list) or not all(
            isinstance(msg, dict) for msg in history
        ):
            raise InvalidRequest(
                "conversation history must be a list of message objects"
            )
        existing_media = set()
        if previous_history:
            for message in json.loads(previous_history):
                parts = message.get("content") if isinstance(message, dict) else None
                if not isinstance(parts, list):
                    continue
                for part in parts:
                    kind = part.get("type") if isinstance(part, dict) else None
                    if kind not in ("image_url", "audio_url"):
                        continue
                    reference = part.get(kind)
                    url = reference.get("url") if isinstance(reference, dict) else None
                    if isinstance(url, str):
                        existing_media.add((kind, url))
        return [
            {**msg, "content": self._content(msg["content"], existing_media)}
            if "content" in msg
            else msg
            for msg in history
        ]

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        """Dispatch a Core-shaped write within the conversation capability.

        Args:
            operation: Requested write method.
            payload: Runner-supplied method arguments.

        Returns:
            The committed ID for creation and event appends, or None.

        Raises:
            Conflict: The supplied write revision is stale.
            InvalidRequest: The input is invalid.
            NotFound: The conversation or operation is inaccessible.
        """
        try:
            if operation in {
                "add_message_pair",
                "append_message",
                "append_plugin_event",
            }:
                cid = self._cid(payload.get("cid"))
                ambient = payload.get("unified_msg_origin")
                umo = self._umo(payload) if ambient is not None else None
                conv = await self._manager.get_conversation(umo or "", cid)
                if conv is None or (umo is not None and conv.user_id != umo):
                    raise NotFound(f"conversation not found: {cid}")
                if operation == "add_message_pair":
                    pair = self._history(
                        [payload.get("user_message"), payload.get("assistant_message")]
                    )
                    await self._manager.add_message_pair(cid, *pair)
                    return None
                if operation == "append_message":
                    return await self._manager.append_message(
                        self._content(payload.get("content")),
                        cid=cid,
                        message_id=payload.get("message_id"),
                    )
                name = payload.get("event_type")
                if not isinstance(name, str) or not re.fullmatch(
                    r"[a-zA-Z0-9_.-]{1,128}", name
                ):
                    raise InvalidRequest("invalid plugin event_type")
                return await self._manager.append_plugin_event(
                    f"{self._event_namespace}.{name}",
                    payload.get("data"),
                    cid=cid,
                    event_id=payload.get("event_id"),
                )

            umo = self._umo(payload)
            if operation == "new_conversation":
                return await self._manager.new_conversation(
                    umo,
                    platform_id=payload.get("platform_id"),
                    content=self._history(payload.get("content")),
                    title=payload.get("title"),
                    persona_id=payload.get("persona_id"),
                )
            if operation == "fork_conversation":
                source = payload.get("source_event_id")
                if not isinstance(source, str) or not source:
                    raise InvalidRequest("fork_conversation requires a source_event_id")
                return await self._manager.fork_conversation(umo, source)
            if operation not in {
                "switch_conversation",
                "update_conversation",
                "delete_conversation",
            }:
                raise NotFound(f"unknown conversation operation: {operation}")

            cid = payload.get("conversation_id")
            if operation != "switch_conversation" and not cid:
                cid = await self._manager.get_curr_conversation_id(umo)
            previous_history = None
            if cid is not None or operation == "switch_conversation":
                cid = self._cid(cid)
                conv = await self._manager.get_conversation(umo, cid)
                if conv is None or conv.user_id != umo:
                    raise NotFound(f"conversation not found: {cid}")
                previous_history = conv.history
            if operation == "switch_conversation":
                await self._manager.switch_conversation(umo, cid)
            elif operation == "update_conversation":
                revision = payload.get("expected_revision")
                if revision is not None and not isinstance(
                    revision, ConversationRevision
                ):
                    raise InvalidRequest(
                        "expected_revision must be a ConversationRevision"
                    )
                await self._manager.update_conversation(
                    umo,
                    cid,
                    history=self._history(
                        payload.get("history"), previous_history=previous_history
                    ),
                    title=payload.get("title"),
                    persona_id=payload.get("persona_id"),
                    token_usage=payload.get("token_usage"),
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
            elif cid is not None:
                await self._manager.delete_conversation(umo, cid)
            return None
        except ConversationConflictError as exc:
            raise Conflict(str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise InvalidRequest(str(exc)) from exc
