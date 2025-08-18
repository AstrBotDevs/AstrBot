import asyncio
import typing as T
import threading
from datetime import datetime, timedelta
from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import (
    ConversationV2,
    PlatformStat,
    PlatformMessageHistory,
    Attachment,
    Persona,
    Preference,
    Stats as DeprecatedStats,
    Platform as DeprecatedPlatformStat,
    SQLModel,
)

from sqlalchemy import select, update, delete, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

NOT_GIVEN = T.TypeVar("NOT_GIVEN")


class SQLiteDatabase(BaseDatabase):
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.DATABASE_URL = f"sqlite+aiosqlite:///{db_path}"
        self.inited = False
        super().__init__()

    async def initialize(self) -> None:
        """Initialize the database by creating tables if they do not exist."""
        async with self.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
            await conn.commit()

    # ====
    # Platform Statistics
    # ====

    async def insert_platform_stats(
        self,
        platform_id: str,
        platform_type: str,
        count: int = 1,
        timestamp: datetime = None,
    ) -> None:
        """Insert a new platform statistic record."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                if timestamp is None:
                    timestamp = datetime.now().replace(
                        minute=0, second=0, microsecond=0
                    )
                current_hour = timestamp
                await session.execute(
                    text("""
                    INSERT INTO platform_stats (timestamp, platform_id, platform_type, count)
                    VALUES (:timestamp, :platform_id, :platform_type, :count)
                    ON CONFLICT(timestamp, platform_id, platform_type) DO UPDATE SET
                        count = platform_stats.count + EXCLUDED.count
                    """),
                    {
                        "timestamp": current_hour,
                        "platform_id": platform_id,
                        "platform_type": platform_type,
                        "count": count,
                    },
                )

    async def count_platform_stats(self) -> int:
        """Count the number of platform statistics records."""
        async with self.get_db() as session:
            session: AsyncSession
            result = await session.execute(
                select(func.count(PlatformStat.platform_id)).select_from(PlatformStat)
            )
            count = result.scalar_one_or_none()
            return count if count is not None else 0

    async def get_platform_stats(self, offset_sec: int = 86400) -> T.List[PlatformStat]:
        """Get platform statistics within the specified offset in seconds and group by platform_id."""
        async with self.get_db() as session:
            session: AsyncSession
            now = datetime.now()
            start_time = now - timedelta(seconds=offset_sec)
            result = await session.execute(
                text("""
                SELECT * FROM platform_stats
                WHERE timestamp >= :start_time
                ORDER BY timestamp DESC
                GROUP BY platform_id
                """),
                {"start_time": start_time},
            )
            return result.scalars().all()

    # ====
    # Conversation Management
    # ====

    async def get_conversations(self, user_id=None, platform_id=None):
        async with self.get_db() as session:
            session: AsyncSession
            query = select(ConversationV2)

            if user_id:
                query = query.where(ConversationV2.user_id == user_id)
            if platform_id:
                query = query.where(ConversationV2.platform_id == platform_id)
            # order by
            query = query.order_by(ConversationV2.created_at.desc())
            result = await session.execute(query)

            return result.scalars().all()

    async def get_conversation_by_id(self, cid):
        async with self.get_db() as session:
            session: AsyncSession
            query = select(ConversationV2).where(ConversationV2.conversation_id == cid)
            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def get_all_conversations(self, page=1, page_size=20):
        async with self.get_db() as session:
            session: AsyncSession
            offset = (page - 1) * page_size
            result = await session.execute(
                select(ConversationV2)
                .order_by(ConversationV2.created_at.desc())
                .offset(offset)
                .limit(page_size)
            )
            return result.scalars().all()

    async def get_filtered_conversations(
        self,
        page=1,
        page_size=20,
        platform_ids=None,
        search_query="",
        **kwargs,
    ):
        async with self.get_db() as session:
            session: AsyncSession
            # Build the base query with filters
            base_query = select(ConversationV2)

            if platform_ids:
                base_query = base_query.where(
                    ConversationV2.platform_id.in_(platform_ids)
                )
            if search_query:
                base_query = base_query.where(
                    ConversationV2.title.ilike(f"%{search_query}%")
                )

            # Get total count matching the filters
            count_query = select(func.count()).select_from(base_query.subquery())
            total_count = await session.execute(count_query)
            total = total_count.scalar_one()

            # Get paginated results
            offset = (page - 1) * page_size
            result_query = (
                base_query.order_by(ConversationV2.created_at.desc())
                .offset(offset)
                .limit(page_size)
            )
            result = await session.execute(result_query)
            conversations = result.scalars().all()

            return conversations, total

    async def create_conversation(
        self,
        user_id,
        platform_id,
        content=None,
        title=None,
        persona_id=None,
        cid=None,
        created_at=None,
        updated_at=None,
    ):
        kwargs = {}
        if cid:
            kwargs["conversation_id"] = cid
        if created_at:
            kwargs["created_at"] = created_at
        if updated_at:
            kwargs["updated_at"] = updated_at
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                new_conversation = ConversationV2(
                    user_id=user_id,
                    content=content or [],
                    platform_id=platform_id,
                    title=title,
                    persona_id=persona_id,
                    **kwargs,
                )
                session.add(new_conversation)
                return new_conversation

    async def update_conversation(self, cid, title=None, persona_id=None, content=None):
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                query = update(ConversationV2).where(
                    ConversationV2.conversation_id == cid
                )
                values = {}
                if title is not None:
                    values["title"] = title
                if persona_id is not None:
                    values["persona_id"] = persona_id
                if content is not None:
                    values["content"] = content
                if not values:
                    return
                query = query.values(**values)
                await session.execute(query)
        return await self.get_conversation_by_id(cid)

    async def delete_conversation(self, cid):
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    delete(ConversationV2).where(ConversationV2.conversation_id == cid)
                )

    async def insert_platform_message_history(
        self,
        platform_id,
        user_id,
        content,
        sender_id=None,
        sender_name=None,
    ):
        """Insert a new platform message history record."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                new_history = PlatformMessageHistory(
                    platform_id=platform_id,
                    user_id=user_id,
                    content=content,
                    sender_id=sender_id,
                    sender_name=sender_name,
                )
                session.add(new_history)
                return new_history

    async def delete_platform_message_offset(
        self, platform_id, user_id, offset_sec=86400
    ):
        """Delete platform message history records older than the specified offset."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                now = datetime.now()
                cutoff_time = now - timedelta(seconds=offset_sec)
                await session.execute(
                    delete(PlatformMessageHistory).where(
                        PlatformMessageHistory.platform_id == platform_id,
                        PlatformMessageHistory.user_id == user_id,
                        PlatformMessageHistory.created_at < cutoff_time,
                    )
                )

    async def get_platform_message_history(
        self, platform_id, user_id, page=1, page_size=20
    ):
        """Get platform message history records."""
        async with self.get_db() as session:
            session: AsyncSession
            offset = (page - 1) * page_size
            query = (
                select(PlatformMessageHistory)
                .where(
                    PlatformMessageHistory.platform_id == platform_id,
                    PlatformMessageHistory.user_id == user_id,
                )
                .order_by(PlatformMessageHistory.created_at.desc())
            )
            result = await session.execute(query.offset(offset).limit(page_size))
            return result.scalars().all()

    async def insert_attachment(self, path, type, mime_type):
        """Insert a new attachment record."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                new_attachment = Attachment(
                    path=path,
                    type=type,
                    mime_type=mime_type,
                )
                session.add(new_attachment)
                return new_attachment

    async def get_attachment_by_id(self, attachment_id):
        """Get an attachment by its ID."""
        async with self.get_db() as session:
            session: AsyncSession
            query = select(Attachment).where(Attachment.id == attachment_id)
            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def insert_persona(
        self, persona_id, system_prompt, begin_dialogs=None, tools=None
    ):
        """Insert a new persona record."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                new_persona = Persona(
                    persona_id=persona_id,
                    system_prompt=system_prompt,
                    begin_dialogs=begin_dialogs or [],
                    tools=tools,
                )
                session.add(new_persona)
                return new_persona

    async def get_persona_by_id(self, persona_id):
        """Get a persona by its ID."""
        async with self.get_db() as session:
            session: AsyncSession
            query = select(Persona).where(Persona.persona_id == persona_id)
            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def get_personas(self):
        """Get all personas for a specific bot."""
        async with self.get_db() as session:
            session: AsyncSession
            query = select(Persona)
            result = await session.execute(query)
            return result.scalars().all()

    async def update_persona(
        self, persona_id, system_prompt=None, begin_dialogs=None, tools=NOT_GIVEN
    ):
        """Update a persona's system prompt or begin dialogs."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                query = update(Persona).where(Persona.persona_id == persona_id)
                values = {}
                if system_prompt is not None:
                    values["system_prompt"] = system_prompt
                if begin_dialogs is not None:
                    values["begin_dialogs"] = begin_dialogs
                if tools is not NOT_GIVEN:
                    values["tools"] = tools
                if not values:
                    return
                query = query.values(**values)
                await session.execute(query)
        return await self.get_persona_by_id(persona_id)

    async def delete_persona(self, persona_id):
        """Delete a persona by its ID."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    delete(Persona).where(Persona.persona_id == persona_id)
                )

    async def insert_preference_or_update(self, scope, scope_id, key, value):
        """Insert a new preference record or update if it exists."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                query = select(Preference).where(
                    Preference.scope == scope,
                    Preference.scope_id == scope_id,
                    Preference.key == key,
                )
                result = await session.execute(query)
                existing_preference = result.scalar_one_or_none()
                if existing_preference:
                    existing_preference.value = value
                else:
                    new_preference = Preference(
                        scope=scope, scope_id=scope_id, key=key, value=value
                    )
                    session.add(new_preference)
                return existing_preference or new_preference

    async def get_preference(self, scope, scope_id, key):
        """Get a preference by key."""
        async with self.get_db() as session:
            session: AsyncSession
            query = select(Preference).where(
                Preference.scope == scope,
                Preference.scope_id == scope_id,
                Preference.key == key,
            )
            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def get_preferences(self, scope, scope_id=None, key=None):
        """Get all preferences for a specific scope ID or key."""
        async with self.get_db() as session:
            session: AsyncSession
            query = select(Preference).where(Preference.scope == scope)
            if scope_id is not None:
                query = query.where(Preference.scope_id == scope_id)
            if key is not None:
                query = query.where(Preference.key == key)
            result = await session.execute(query)
            return result.scalars().all()

    async def remove_preference(self, scope, scope_id, key):
        """Remove a preference by scope ID and key."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    delete(Preference).where(
                        Preference.scope == scope,
                        Preference.scope_id == scope_id,
                        Preference.key == key,
                    )
                )
            await session.commit()

    async def clear_preferences(self, scope, scope_id):
        """Clear all preferences for a specific scope ID."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    delete(Preference).where(
                        Preference.scope == scope, Preference.scope_id == scope_id
                    )
                )
            await session.commit()

    # ====
    # Deprecated Methods
    # ====

    def get_base_stats(self, offset_sec=86400):
        """Get base statistics within the specified offset in seconds."""

        async def _inner():
            async with self.get_db() as session:
                session: AsyncSession
                now = datetime.now()
                start_time = now - timedelta(seconds=offset_sec)
                result = await session.execute(
                    select(PlatformStat).where(PlatformStat.timestamp >= start_time)
                )
                all_datas = result.scalars().all()
                deprecated_stats = DeprecatedStats()
                for data in all_datas:
                    deprecated_stats.platform.append(
                        DeprecatedPlatformStat(
                            name=data.platform_id,
                            count=data.count,
                            timestamp=data.timestamp.timestamp(),
                        )
                    )
                return deprecated_stats

        result = None

        def runner():
            nonlocal result
            result = asyncio.run(_inner())

        t = threading.Thread(target=runner)
        t.start()
        t.join()
        return result

    def get_total_message_count(self):
        """Get the total message count from platform statistics."""

        async def _inner():
            async with self.get_db() as session:
                session: AsyncSession
                result = await session.execute(
                    select(func.sum(PlatformStat.count)).select_from(PlatformStat)
                )
                total_count = result.scalar_one_or_none()
                return total_count if total_count is not None else 0

        result = None

        def runner():
            nonlocal result
            result = asyncio.run(_inner())

        t = threading.Thread(target=runner)
        t.start()
        t.join()
        return result

    def get_grouped_base_stats(self, offset_sec=86400):
        # group by platform_id
        async def _inner():
            async with self.get_db() as session:
                session: AsyncSession
                now = datetime.now()
                start_time = now - timedelta(seconds=offset_sec)
                result = await session.execute(
                    select(PlatformStat.platform_id, func.sum(PlatformStat.count))
                    .where(PlatformStat.timestamp >= start_time)
                    .group_by(PlatformStat.platform_id)
                )
                grouped_stats = result.all()
                deprecated_stats = DeprecatedStats()
                for platform_id, count in grouped_stats:
                    deprecated_stats.platform.append(
                        DeprecatedPlatformStat(
                            name=platform_id,
                            count=count,
                            timestamp=start_time.timestamp(),
                        )
                    )
                return deprecated_stats

        result = None

        def runner():
            nonlocal result
            result = asyncio.run(_inner())

        t = threading.Thread(target=runner)
        t.start()
        t.join()
        return result
