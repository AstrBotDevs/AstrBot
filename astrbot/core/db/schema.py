"""Create the main SQLite schema from registered SQLModel tables."""

from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import SQLModel, text

from astrbot.core.db.po.registry import import_all_models

_SQLITE_RUNTIME_PRAGMAS = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA busy_timeout=30000",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA cache_size=20000",
    "PRAGMA temp_store=MEMORY",
    "PRAGMA mmap_size=134217728",
    "PRAGMA optimize",
)


async def initialize_sqlite_schema(engine: AsyncEngine) -> None:
    """Register table models, create missing tables, and apply SQLite PRAGMAs.

    Startup does not inspect or patch an existing file. Upgrading to this
    schema means deleting ``data/data_v4.db*`` and starting with an empty
    database.

    Args:
        engine: Async SQLAlchemy engine bound to the main database file.
    """
    import_all_models()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    async with engine.connect() as conn:
        for pragma in _SQLITE_RUNTIME_PRAGMAS:
            await conn.execute(text(pragma))
        await conn.commit()
