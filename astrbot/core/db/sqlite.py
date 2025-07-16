from datetime import datetime, timedelta
import typing as T
from astrbot.core.db.po import (
    ConversationV2,
    PlatformStat,
    Base,
)
from sqlalchemy import select, update, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


class SQLiteDatabase:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

        DATABASE_URL = f"sqlite+aiosqlite:///{db_path}"
        self.engine = create_async_engine(
            DATABASE_URL,
            echo=True,
            future=True,
        )
        self.AsyncSessionLocal = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        self.inited = False

    async def init_db(self) -> None:
        """Initialize the database by creating tables if they do not exist."""
        async with self.engine.begin() as conn:
            await conn.execute("PRAGMA foreign_keys = ON;")
            await conn.run_sync(Base.metadata.create_all)
            await conn.commit()

    async def get_db(self) -> T.AsyncGenerator[AsyncSession, None]:
        """Get a database session."""
        if not self.inited:
            await self.init_db()
            self.inited = True
        async with self.AsyncSessionLocal() as session:
            yield session

    # ====
    # Platform Statistics
    # ====

    async def insert_platform_stats(
        self, bot_id: str, platform_id: int, platform_type: str, count: int = 1
    ) -> None:
        """Insert a new platform statistic record."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                current_hour = datetime.now().replace(minute=0, second=0, microsecond=0)
                await session.execute(
                    """
                    INSERT INTO platform_stats (timestamp, bot_id, platform_id, platform_type, count)
                    VALUES (:timestamp, :bot_id, :platform_id, :platform_type, :count)
                    ON CONFLICT(date, bot_id, platform_id, platform_type) DO UPDATE SET
                        count = platform_stats.count + EXCLUDED.count
                    """,
                    {
                        "timestamp": current_hour,
                        "bot_id": bot_id,
                        "platform_id": platform_id,
                        "platform_type": platform_type,
                        "count": count,
                    },
                )
            await session.commit()

    async def count_platform_stats(self, bot_id: str) -> int:
        """Count the number of platform statistics records."""
        async with self.get_db() as session:
            session: AsyncSession
            result = await session.execute(
                """
                SELECT COUNT(*) FROM platform_stats
                WHERE bot_id = :bot_id
                """,
                {
                    "bot_id": bot_id,
                },
            )
            count = result.scalar_one_or_none()
            return count if count is not None else 0

    async def get_platform_stats(
        self, bot_id: str, offset_sec: int = 86400
    ) -> T.List[PlatformStat]:
        """Get platform statistics within the specified offset in seconds and group by platform_id."""
        async with self.get_db() as session:
            session: AsyncSession
            now = datetime.now()
            start_time = now - timedelta(seconds=offset_sec)
            result = await session.execute(
                """
                SELECT * FROM platform_stats
                WHERE timestamp >= :start_time AND bot_id = :bot_id
                ORDER BY timestamp DESC
                GROUP BY platform_id, bot_id
                """,
                {"start_time": start_time, "bot_id": bot_id},
            )
            return result.scalars().all()

    # ====
    # Conversation Management
    # ====

    async def get_conversations(
        self, bot_id: str, user_id: str
    ) -> T.List[ConversationV2]:
        """Get all conversations for a specific bot and user."""
        async with self.get_db() as session:
            session: AsyncSession
            result = await session.execute(
                """
                SELECT * FROM conversations
                WHERE bot_id = :bot_id AND user_id = :user_id
                ORDER BY created_at DESC
                """,
                {"bot_id": bot_id, "user_id": user_id},
            )
            return result.scalars().all()

    async def get_conversation_by_id(
        self,
        conversation_id: int,
        bot_id: str = "",
    ) -> T.Optional[ConversationV2]:
        """Get a specific conversation by its ID."""
        async with self.get_db() as session:
            session: AsyncSession
            query = select(ConversationV2).where(
                ConversationV2.conversation_id == conversation_id
            )
            if bot_id:
                query = query.where(ConversationV2.bot_id == bot_id)
            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def get_all_conversations(
        self, page: int = 1, page_size: int = 20
    ) -> T.List[ConversationV2]:
        """Get all conversations with pagination."""
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
        page: int = 1,
        page_size: int = 20,
        platform_ids: list[str] | None = None,
        bot_id: str = "",
        search_query: str = "",
        **kwargs: T.Any,
    ) -> T.List[ConversationV2]:
        """Get conversations filtered by platform IDs and search query."""
        async with self.get_db() as session:
            session: AsyncSession
            offset = (page - 1) * page_size
            query = select(ConversationV2).order_by(ConversationV2.created_at.desc())

            if platform_ids:
                query = query.where(ConversationV2.platform_id.in_(platform_ids))
            if bot_id:
                query = query.where(ConversationV2.bot_id == bot_id)
            if search_query:
                query = query.where(ConversationV2.title.ilike(f"%{search_query}%"))

            result = await session.execute(query.offset(offset).limit(page_size))
            return result.scalars().all()

    async def creare_conversation(
        self,
        bot_id: str,
        user_id: str,
        title: str = None,
        persona_id: int = None,
    ) -> ConversationV2:
        """Create a new conversation."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                new_conversation = ConversationV2(
                    bot_id=bot_id,
                    user_id=user_id,
                    title=title,
                    persona_id=persona_id,
                )
                session.add(new_conversation)
                await session.commit()
                return new_conversation

    async def update_conversation(
        self,
        conversation_id: int,
        title: str = None,
        persona_id: int = None,
    ) -> T.Optional[ConversationV2]:
        """Update an existing conversation."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                query = update(ConversationV2).where(
                    ConversationV2.conversation_id == conversation_id
                )
                if title is not None:
                    query = query.values(title=title)
                if persona_id is not None:
                    query = query.values(persona_id=persona_id)
                await session.execute(query)
                await session.commit()
                return await self.get_conversation_by_id(conversation_id)

    async def delete_conversation(self, conversation_id: int) -> None:
        """Delete a conversation by its ID."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    delete(ConversationV2).where(
                        ConversationV2.conversation_id == conversation_id
                    )
                )
                await session.commit()
