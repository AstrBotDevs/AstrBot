"""Migration script to add token_usage column to conversations table.

This migration adds the token_usage field to track token consumption for each conversation.

Changes:
- Adds token_usage column to conversations table (default: 0)
"""
from astrbot.core.lang import t

from sqlalchemy import text

from astrbot.api import logger, sp
from astrbot.core.db import BaseDatabase


async def migrate_token_usage(db_helper: BaseDatabase) -> None:
    """Add token_usage column to conversations table.

    This migration adds a new column to track token consumption in conversations.
    """
    # 检查是否已经完成迁移
    migration_done = await db_helper.get_preference(
        "global", "global", "migration_done_token_usage_1"
    )
    if migration_done:
        return

    logger.info(t("msg-c3e53a4f"))

    # 这里只适配了 SQLite。因为截止至这一版本，AstrBot 仅支持 SQLite。

    try:
        async with db_helper.get_db() as session:
            # 检查列是否已存在
            result = await session.execute(text("PRAGMA table_info(conversations)"))
            columns = result.fetchall()
            column_names = [col[1] for col in columns]

            if "token_usage" in column_names:
                logger.info(t("msg-ccbd0a41"))
                await sp.put_async(
                    "global", "global", "migration_done_token_usage_1", True
                )
                return

            # 添加 token_usage 列
            await session.execute(
                text(
                    "ALTER TABLE conversations ADD COLUMN token_usage INTEGER NOT NULL DEFAULT 0"
                )
            )
            await session.commit()

            logger.info(t("msg-39f60232"))

        # 标记迁移完成
        await sp.put_async("global", "global", "migration_done_token_usage_1", True)
        logger.info(t("msg-4f9d3876"))

    except Exception as e:
        logger.error(t("msg-91571aaf", e=e), exc_info=True)
        raise
