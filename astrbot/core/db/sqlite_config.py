"""Connection performance policy shared by the main and knowledge-base stores."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def apply_sqlite_performance_pragmas(connection: AsyncConnection) -> None:
    """Apply common tuning without opening or committing a transaction."""
    for pragma in (
        "PRAGMA synchronous=NORMAL",
        "PRAGMA cache_size=20000",
        "PRAGMA temp_store=MEMORY",
        "PRAGMA mmap_size=134217728",
        "PRAGMA optimize",
    ):
        await connection.execute(text(pragma))
