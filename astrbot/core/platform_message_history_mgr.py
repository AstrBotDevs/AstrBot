from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import PlatformMessageHistory


class PlatformMessageHistoryManager:
    def __init__(self, db_helper: BaseDatabase) -> None:
        self.db = db_helper

    async def insert(
        self,
        platform_id: str,
        user_id: str,
        content: dict,  # TODO: parse from message chain
        sender_id: str | None = None,
        sender_name: str | None = None,
        llm_checkpoint_id: str | None = None,
    ) -> PlatformMessageHistory:
        """Insert a new platform message history record."""
        return await self.db.insert_platform_message_history(
            platform_id=platform_id,
            user_id=user_id,
            content=content,
            sender_id=sender_id,
            sender_name=sender_name,
            llm_checkpoint_id=llm_checkpoint_id,
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
