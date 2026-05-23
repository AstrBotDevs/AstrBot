from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import col

from astrbot.core import logger

from .entities import BaseMemoryModel, MemoryChunk


class MemoryDatabase:
    def __init__(self, db_path: str = "data/astr_memory/memory.db") -> None:
        """Initialize memory database

        Args:
            db_path: Database file path, default is data/astr_memory/memory.db

        """
        self.db_path = db_path
        self.DATABASE_URL = f"sqlite+aiosqlite:///{db_path}"
        self.inited = False

        # Ensure directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # Create async engine
        self.engine = create_async_engine(
            self.DATABASE_URL,
            echo=False,
            pool_pre_ping=True,
            pool_recycle=3600,
        )

        # Create session factory
        self.async_session = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @asynccontextmanager
    async def get_db(self):
        """Get database session

        Usage:
            async with mem_db.get_db() as session:
                # Perform database operations
                result = await session.execute(stmt)
        """
        async with self.async_session() as session:
            yield session

    async def initialize(self) -> None:
        """Initialize database, create tables and configure SQLite parameters"""
        async with self.engine.begin() as conn:
            # Create all memory related tables
            await conn.run_sync(BaseMemoryModel.metadata.create_all)

            # Configure SQLite performance optimization parameters
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA synchronous=NORMAL"))
            await conn.execute(text("PRAGMA cache_size=20000"))
            await conn.execute(text("PRAGMA temp_store=MEMORY"))
            await conn.execute(text("PRAGMA mmap_size=134217728"))
            await conn.execute(text("PRAGMA optimize"))
            await conn.commit()

        await self._create_indexes()
        self.inited = True
        logger.info(f"Memory database initialized: {self.db_path}")

    async def _create_indexes(self) -> None:
        """Create indexes for memory_chunks table"""
        async with self.get_db() as session:
            async with session.begin():
                # Create memory chunks table indexes
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_mem_mem_id "
                        "ON memory_chunks(mem_id)",
                    ),
                )
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_mem_owner_id "
                        "ON memory_chunks(owner_id)",
                    ),
                )
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_mem_owner_active "
                        "ON memory_chunks(owner_id, is_active)",
                    ),
                )
                await session.commit()

    async def close(self) -> None:
        """Close database connection"""
        await self.engine.dispose()
        logger.info(f"Memory database closed: {self.db_path}")

    async def insert_memory(self, memory: MemoryChunk) -> MemoryChunk:
        """Insert a new memory chunk"""
        async with self.get_db() as session:
            session.add(memory)
            await session.commit()
            await session.refresh(memory)
            return memory

    async def get_memory_by_id(self, mem_id: str) -> MemoryChunk | None:
        """Get memory chunk by mem_id"""
        async with self.get_db() as session:
            stmt = select(MemoryChunk).where(col(MemoryChunk.mem_id) == mem_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def update_memory(self, memory: MemoryChunk) -> MemoryChunk:
        """Update an existing memory chunk"""
        async with self.get_db() as session:
            session.add(memory)
            await session.commit()
            await session.refresh(memory)
            return memory

    async def get_active_memories(self, owner_id: str) -> list[MemoryChunk]:
        """Get all active memories for a user"""
        async with self.get_db() as session:
            stmt = select(MemoryChunk).where(
                col(MemoryChunk.owner_id) == owner_id,
                col(MemoryChunk.is_active) == True,  # noqa: E712
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def update_retrieval_stats(
        self,
        mem_ids: list[str],
        current_time: datetime | None = None,
    ) -> None:
        """Update retrieval statistics for multiple memories"""
        if not mem_ids:
            return

        if current_time is None:
            current_time = datetime.now(timezone.utc)

        async with self.get_db() as session:
            async with session.begin():
                stmt = (
                    update(MemoryChunk)
                    .where(col(MemoryChunk.mem_id).in_(mem_ids))
                    .values(
                        retrieval_count=MemoryChunk.retrieval_count + 1,
                        last_retrieval_at=current_time,
                    )
                )
                await session.execute(stmt)
                await session.commit()

    async def deactivate_memory(self, mem_id: str) -> bool:
        """Deactivate a memory chunk"""
        async with self.get_db() as session:
            async with session.begin():
                stmt = (
                    update(MemoryChunk)
                    .where(col(MemoryChunk.mem_id) == mem_id)
                    .values(is_active=False)
                )
                result = await session.execute(stmt)
                await session.commit()
                return result.rowcount > 0 if result.rowcount else False  # type: ignore
