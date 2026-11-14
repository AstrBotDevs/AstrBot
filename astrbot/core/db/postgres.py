"""PostgreSQL backend using the shared relational operations."""

import asyncio

from sqlalchemy.engine import make_url
from sqlmodel import SQLModel

from astrbot.core.db.migration.migra_conversation_events import migrate_conversations
from astrbot.core.db.relational import RelationalDatabase


class PostgreSQLDatabase(RelationalDatabase):
    """Store application data in PostgreSQL with conversation-scoped row locks."""

    def __init__(self, url: str) -> None:
        """Configure asynchronous and legacy synchronous psycopg connections.

        Args:
            url: PostgreSQL connection URL; psycopg is the supported driver.

        Raises:
            ValueError: The URL specifies a different database or driver.
        """
        parsed = make_url(url)
        if parsed.drivername not in {"postgresql", "postgresql+psycopg"}:
            raise ValueError("Expected a postgresql or postgresql+psycopg URL")
        self.DATABASE_URL = parsed.set(drivername="postgresql+psycopg")
        self.inited = False
        self._initialize_lock = asyncio.Lock()
        super().__init__()

    async def initialize(self) -> None:
        """Create the current schema once before accepting application traffic."""
        async with self._initialize_lock:
            if self.inited:
                return
            async with self.engine.begin() as connection:
                await connection.run_sync(
                    lambda conn: SQLModel.metadata.create_all(
                        conn,
                        tables=[
                            table
                            for name, table in SQLModel.metadata.tables.items()
                            if name != "conversations"
                        ],
                    )
                )
            await migrate_conversations(self.conversation_store)
            self.inited = True
