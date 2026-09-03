from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import PlatformMessageHistory
from astrbot.core.message.components import ComponentType
from astrbot.core.message.message_event_result import MessageChain


class PlatformMessageHistoryManager:
    def __init__(self, db_helper: BaseDatabase) -> None:
        self.db = db_helper

    async def insert(
        self,
        platform_id: str,
        user_id: str,
        content: dict,
        sender_id: str | None = None,
        sender_name: str | None = None,
        llm_checkpoint_id: str | None = None,
        max_messages: int | None = None,
    ) -> PlatformMessageHistory:
        """Insert a new platform message history record."""
        return await self.db.insert_platform_message_history(
            platform_id=platform_id,
            user_id=user_id,
            content=content,
            sender_id=sender_id,
            sender_name=sender_name,
            llm_checkpoint_id=llm_checkpoint_id,
            max_messages=max_messages,
        )

    async def insert_message_chain(
        self,
        platform_id: str,
        user_id: str,
        message_chain: MessageChain,
        role: str,
        sender_id: str | None = None,
        sender_name: str | None = None,
        max_messages: int | None = None,
    ) -> PlatformMessageHistory | None:
        """Store a platform-neutral, path-free representation of a message chain.

        Args:
            platform_id: Platform instance ID.
            user_id: Unified message origin for the group.
            message_chain: Message components to persist.
            role: Message role, normally ``user`` or ``bot``.
            sender_id: Sender ID reported by the platform.
            sender_name: Sender display name reported by the platform.
            max_messages: Maximum retained rows for this platform and user scope.

        Returns:
            The inserted history record, or ``None`` for an empty message chain.
        """
        parts: list[dict] = []
        for component in message_chain.chain:
            raw_component_type = component.type
            component_type_name = (
                raw_component_type.value
                if isinstance(raw_component_type, ComponentType)
                else str(raw_component_type)
            )
            if component.type == ComponentType.Plain:
                text = str(getattr(component, "text", ""))
                if text:
                    parts.append({"type": "plain", "text": text})
            elif component.type in {
                ComponentType.Image,
                ComponentType.Record,
                ComponentType.Video,
                ComponentType.File,
            }:
                parts.append({"type": "plain", "text": f"[{component_type_name}]"})
            elif component.type == ComponentType.At:
                parts.append(
                    {
                        "type": "at",
                        "user_id": str(getattr(component, "qq", "")),
                        "name": str(getattr(component, "name", "") or ""),
                    }
                )
            elif component.type == ComponentType.Reply:
                parts.append(
                    {
                        "type": "reply",
                        "message_id": str(getattr(component, "id", "")),
                        "sender_name": str(
                            getattr(component, "sender_nickname", "") or ""
                        ),
                        "text": str(getattr(component, "message_str", "") or ""),
                    }
                )
            else:
                parts.append({"type": "plain", "text": f"[{component_type_name}]"})

        if not parts:
            return None
        return await self.insert(
            platform_id=platform_id,
            user_id=user_id,
            content={"type": role, "message": parts},
            sender_id=sender_id,
            sender_name=sender_name,
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
            llm_checkpoint_id=llm_checkpoint_id,
        )

    async def delete_by_id(self, message_id: int) -> None:
        """Delete a platform message history record by ID."""
        await self.db.delete_platform_message_history_by_id(message_id)
