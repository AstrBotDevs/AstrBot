from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import PlatformMessageHistory


class PlatformMessageHistoryManager:
    def __init__(self, db_helper: BaseDatabase):
        self.db = db_helper

    async def insert(
        self,
        platform_id: str,
        user_id: str,
        content: list[dict],  # TODO: parse from message chain
        sender_id: str = None,
        sender_name: str = None,
    ):
        """Insert a new platform message history record."""
        await self.db.insert_platform_message_history(
            platform_id=platform_id,
            user_id=user_id,
            content=content,
            sender_id=sender_id,
            sender_name=sender_name,
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

    async def delete(self, platform_id: str, user_id: str, offset_sec: int = 86400):
        """Delete platform message history records older than the specified offset."""
        await self.db.delete_platform_message_offset(
            platform_id=platform_id, user_id=user_id, offset_sec=offset_sec
        )
