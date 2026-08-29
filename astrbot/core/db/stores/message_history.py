from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, delete, desc, select, update

from astrbot.core.db.po import PlatformMessageHistory
from astrbot.core.db.stores.mixin import DatabaseStoreMixin, store_session


class MessageHistoryStoreMixin(DatabaseStoreMixin):
    async def insert_platform_message_history(
        self,
        platform_id: str,
        user_id: str,
        content: dict,
        sender_id: str | None = None,
        sender_name: str | None = None,
        role: str = "user",
        is_group: bool = False,
        llm_checkpoint_id: str | None = None,
        max_messages: int | None = None,
    ) -> PlatformMessageHistory:
        """Insert a new platform message history record."""
        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                new_history = PlatformMessageHistory(
                    platform_id=platform_id,
                    user_id=user_id,
                    content=content,
                    sender_id=sender_id,
                    sender_name=sender_name,
                    role=role,
                    is_group=is_group,
                    llm_checkpoint_id=llm_checkpoint_id,
                )
                session.add(new_history)
                await session.flush()
                if max_messages is not None:
                    keep_count = max(1, int(max_messages))
                    keep_ids = (
                        select(PlatformMessageHistory.id)
                        .where(
                            col(PlatformMessageHistory.platform_id) == platform_id,
                            col(PlatformMessageHistory.user_id) == user_id,
                            col(PlatformMessageHistory.is_group) == is_group,
                        )
                        .order_by(desc(PlatformMessageHistory.id))
                        .limit(keep_count)
                    )
                    await session.execute(
                        delete(PlatformMessageHistory).where(
                            col(PlatformMessageHistory.platform_id) == platform_id,
                            col(PlatformMessageHistory.user_id) == user_id,
                            col(PlatformMessageHistory.is_group) == is_group,
                            col(PlatformMessageHistory.id).not_in(keep_ids),
                        )
                    )
                return new_history

    async def update_platform_message_history(
        self,
        message_id: int,
        content: dict | None = None,
        role: str | None = None,
        llm_checkpoint_id: str | None = None,
    ) -> None:
        """Update a platform message history record."""
        values = {}
        if content is not None:
            values["content"] = content
        if role is not None:
            values["role"] = role
        if llm_checkpoint_id is not None:
            values["llm_checkpoint_id"] = llm_checkpoint_id
        if not values:
            return

        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    update(PlatformMessageHistory)
                    .where(col(PlatformMessageHistory.id) == message_id)
                    .values(**values)
                )

    async def delete_platform_message_history_by_id(self, message_id: int) -> None:
        """Delete a platform message history record by ID."""
        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    delete(PlatformMessageHistory).where(
                        col(PlatformMessageHistory.id) == message_id
                    )
                )

    async def delete_platform_message_offset(
        self,
        platform_id: str,
        user_id: str,
        offset_sec: int = 86400,
    ) -> None:
        """Delete platform message history records newer than the specified offset."""
        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                now = datetime.now()
                cutoff_time = now - timedelta(seconds=offset_sec)
                await session.execute(
                    delete(PlatformMessageHistory).where(
                        col(PlatformMessageHistory.platform_id) == platform_id,
                        col(PlatformMessageHistory.user_id) == user_id,
                        col(PlatformMessageHistory.created_at) >= cutoff_time,
                    ),
                )

    async def get_platform_message_history(
        self,
        platform_id: str,
        user_id: str,
        page: int = 1,
        page_size: int = 20,
        *,
        is_group: bool | None = None,
        before_id: int | None = None,
    ) -> list[PlatformMessageHistory]:
        """Get platform message history records."""
        async with store_session(self) as session:
            session: AsyncSession
            offset = (page - 1) * page_size
            query = (
                select(PlatformMessageHistory)
                .where(
                    PlatformMessageHistory.platform_id == platform_id,
                    PlatformMessageHistory.user_id == user_id,
                )
                .order_by(
                    desc(PlatformMessageHistory.created_at),
                    desc(PlatformMessageHistory.id),
                )
            )
            if is_group is not None:
                query = query.where(PlatformMessageHistory.is_group == is_group)
            if before_id is not None:
                query = query.where(col(PlatformMessageHistory.id) < before_id)
            result = await session.execute(query.offset(offset).limit(page_size))
            return list(result.scalars().all())

    async def get_group_message_history(
        self,
        platform_id: str,
        group_id: str,
        *,
        limit: int = 50,
        before_id: int | None = None,
    ) -> list[PlatformMessageHistory]:
        """Return only explicitly marked rows for one group scope."""
        return await self.get_platform_message_history(
            platform_id,
            group_id,
            page=1,
            page_size=max(1, min(int(limit), 500)),
            is_group=True,
            before_id=before_id,
        )

    async def get_platform_message_history_by_id(
        self, message_id: int
    ) -> PlatformMessageHistory | None:
        """Get a platform message history record by its ID."""
        async with store_session(self) as session:
            session: AsyncSession
            query = select(PlatformMessageHistory).where(
                PlatformMessageHistory.id == message_id
            )
            result = await session.execute(query)
            return result.scalar_one_or_none()
