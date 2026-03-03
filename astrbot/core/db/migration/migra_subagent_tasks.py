"""Migration script for subagent background task table."""

from sqlalchemy import text

from astrbot.api import logger, sp
from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import SQLModel


async def migrate_subagent_tasks(db_helper: BaseDatabase) -> None:
    table_marker = "migration_done_subagent_tasks_1"
    index_marker = "migration_done_subagent_tasks_index_2"
    table_migration_done = await db_helper.get_preference(
        "global", "global", table_marker
    )
    index_migration_done = await db_helper.get_preference(
        "global", "global", index_marker
    )
    if table_migration_done and index_migration_done:
        return

    logger.info("Start migration for subagent_tasks table...")
    try:
        async with db_helper.engine.begin() as conn:
            if not table_migration_done:
                await conn.run_sync(SQLModel.metadata.create_all)
                result = await conn.execute(
                    text(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='subagent_tasks'"
                    )
                )
                if not result.fetchone():
                    raise RuntimeError("subagent_tasks table was not created")

            if not index_migration_done:
                await conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_subagent_tasks_status_next_run_created "
                        "ON subagent_tasks(status, next_run_at, created_at)"
                    )
                )

        if not table_migration_done:
            await sp.put_async("global", "global", table_marker, True)
        if not index_migration_done:
            await sp.put_async("global", "global", index_marker, True)
        logger.info("subagent_tasks migration completed.")
    except Exception as exc:
        logger.error("Migration for subagent_tasks failed: %s", exc, exc_info=True)
        raise
