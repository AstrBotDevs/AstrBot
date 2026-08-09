from astrbot.core.db.po import PlatformMessageHistory
from astrbot.core.db.protocols import MessageHistoryStore
from astrbot.core.message.components import (
    At,
    AtAll,
    BaseMessageComponent,
    File,
    Image,
    Plain,
    Record,
    Reply,
    Video,
)
from astrbot.core.message.message_event_result import MessageChain

_ROLES = {"user", "assistant", "system"}
_MAX_PERSISTED_TEXT = 4096


class PlatformMessageHistoryManager:
    def __init__(self, db_helper: MessageHistoryStore) -> None:
        self.db = db_helper

    async def insert(
        self,
        platform_id: str,
        user_id: str,
        content: dict,  # TODO: parse from message chain
        sender_id: str | None = None,
        sender_name: str | None = None,
        role: str = "user",
        is_group: bool = False,
        llm_checkpoint_id: str | None = None,
        max_messages: int | None = None,
    ) -> PlatformMessageHistory:
        """Insert a new platform message history record."""
        role = _normalize_role(role)
        return await self.db.insert_platform_message_history(
            platform_id=platform_id,
            user_id=user_id,
            content=content,
            sender_id=sender_id,
            sender_name=sender_name,
            role=role,
            is_group=is_group,
            llm_checkpoint_id=llm_checkpoint_id,
            max_messages=max_messages,
        )

    async def insert_message_chain(
        self,
        *,
        platform_id: str,
        user_id: str,
        message_chain: MessageChain,
        role: str,
        is_group: bool,
        sender_id: str | None = None,
        sender_name: str | None = None,
        max_messages: int | None = None,
    ) -> PlatformMessageHistory | None:
        """Persist a sanitized, platform-neutral message chain."""
        parts = [_serialize_component(component) for component in message_chain.chain]
        parts = [part for part in parts if part is not None]
        if not parts:
            return None
        return await self.insert(
            platform_id=platform_id,
            user_id=user_id,
            content={"message": parts},
            role=role,
            is_group=is_group,
            sender_id=_bounded(sender_id, 256),
            sender_name=_bounded(sender_name, 256),
            max_messages=max_messages,
        )

    async def get(
        self,
        platform_id: str,
        user_id: str,
        page: int = 1,
        page_size: int = 200,
    ) -> list[PlatformMessageHistory]:
        """Get platform message history for a specific user."""
        history = await self.db.get_platform_message_history(
            platform_id=platform_id,
            user_id=user_id,
            page=page,
            page_size=page_size,
        )
        history.reverse()
        return history

    async def get_group(
        self,
        platform_id: str,
        group_id: str,
        *,
        limit: int = 50,
        before_id: int | None = None,
    ) -> list[PlatformMessageHistory]:
        """Query only explicitly marked history for one group."""
        history = await self.db.get_group_message_history(
            platform_id,
            group_id,
            limit=limit,
            before_id=before_id,
        )
        history.reverse()
        return history

    async def delete(
        self, platform_id: str, user_id: str, offset_sec: int = 86400
    ) -> None:
        """Delete platform message history records older than the specified offset."""
        await self.db.delete_platform_message_offset(
            platform_id=platform_id,
            user_id=user_id,
            offset_sec=offset_sec,
        )

    async def update(
        self,
        message_id: int,
        content: dict | None = None,
        llm_checkpoint_id: str | None = None,
    ) -> None:
        """Update a platform message history record."""
        await self.db.update_platform_message_history(
            message_id=message_id,
            content=content,
            role=None,
            llm_checkpoint_id=llm_checkpoint_id,
        )

    async def delete_by_id(self, message_id: int) -> None:
        """Delete a platform message history record by ID."""
        await self.db.delete_platform_message_history_by_id(message_id)


def _normalize_role(role: str) -> str:
    normalized = str(role or "user").strip().lower()
    if normalized == "bot":
        normalized = "assistant"
    return normalized if normalized in _ROLES else "system"


def _bounded(value: object, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:limit] or None


def _serialize_component(component: BaseMessageComponent) -> dict | None:
    """Serialize message content without paths, URLs, or raw provider metadata."""
    if isinstance(component, Plain):
        text = _bounded(component.text, _MAX_PERSISTED_TEXT)
        return {"type": "plain", "text": text} if text else None
    if isinstance(component, (Image, Record, Video, File)):
        return {"type": component.type.lower(), "text": f"[{component.type}]"}
    if isinstance(component, At):
        return {
            "type": "at",
            "name": _bounded(getattr(component, "name", None), 256) or "user",
        }
    if isinstance(component, AtAll):
        return {"type": "at_all"}
    if isinstance(component, Reply):
        return {
            "type": "reply",
            "sender_name": _bounded(getattr(component, "sender_nickname", None), 256),
            "text": _bounded(getattr(component, "message_str", None), 512),
        }
    return {"type": str(component.type).lower(), "text": "[Unsupported]"}
