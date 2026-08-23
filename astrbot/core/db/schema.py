"""Create the main SQLite schema from registered SQLModel tables."""

from sqlalchemy import inspect as sa_inspect
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

    Args:
        engine: Async SQLAlchemy engine bound to the main database file.
    """
    import_all_models()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
        await _ensure_command_id_columns(conn)
    async with engine.connect() as conn:
        for pragma in _SQLITE_RUNTIME_PRAGMAS:
            await conn.execute(text(pragma))
        await conn.commit()


def _table_has_column(sync_conn, table_name: str, column_name: str) -> bool:
    inspector = sa_inspect(sync_conn)
    if table_name not in inspector.get_table_names():
        return True
    return any(
        column["name"] == column_name for column in inspector.get_columns(table_name)
    )


async def _ensure_command_id_columns(conn) -> None:
    """Add command_id to existing command tables created before the column existed."""
    has_config_column = await conn.run_sync(
        lambda sync_conn: _table_has_column(sync_conn, "command_configs", "command_id"),
    )
    if not has_config_column:
        await conn.execute(
            text("ALTER TABLE command_configs ADD COLUMN command_id VARCHAR(512)"),
        )
        await conn.execute(
            text(
                "UPDATE command_configs SET command_id = "
                "plugin_name || ':' || replace(original_command, ' ', '.') "
                "WHERE command_id IS NULL OR command_id = ''"
            ),
        )
        await conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uix_command_configs_command_id "
                "ON command_configs (command_id)"
            ),
        )

    has_conflict_column = await conn.run_sync(
        lambda sync_conn: _table_has_column(
            sync_conn,
            "command_conflicts",
            "command_id",
        ),
    )
    if not has_conflict_column:
        await conn.execute(
            text("ALTER TABLE command_conflicts ADD COLUMN command_id VARCHAR(512)"),
        )
        await conn.execute(
            text(
                "UPDATE command_conflicts SET command_id = "
                "plugin_name || ':' || replace(conflict_key, ' ', '.') "
                "WHERE command_id IS NULL OR command_id = ''"
            ),
        )
