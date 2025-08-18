import os
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.core.db import BaseDatabase
from astrbot.core.config import AstrBotConfig
from astrbot.api import logger, sp
from .migra_3_to_4 import (
    migration_conversation_table,
    migration_platform_table,
    migration_webchat_data,
    migration_persona_data,
    migration_preferences,
)


async def check_migration_needed_v4(db_helper: BaseDatabase) -> bool:
    """
    检查是否需要进行数据库迁移
    如果存在 data_v3.db 并且 preference 中没有 migration_done_v4，则需要进行迁移。
    """
    data_v3_exists = os.path.exists(get_astrbot_data_path())
    if not data_v3_exists:
        return False
    migration_done = await db_helper.get_preference(
        "global", "global", "migration_done_v4"
    )
    if migration_done:
        return False
    return True


async def do_migration_v4(
    db_helper: BaseDatabase,
    platform_id_map: dict[str, dict[str, str]],
    astrbot_config: AstrBotConfig,
):
    """
    执行数据库迁移
    迁移旧的 webchat_conversation 表到新的 conversation 表。
    迁移旧的 platform 到新的 platform_stats 表。
    """
    if not await check_migration_needed_v4(db_helper):
        return

    logger.info("开始执行数据库迁移...")

    # 执行会话表迁移
    await migration_conversation_table(db_helper, platform_id_map)

    # 执行人格数据迁移
    await migration_persona_data(db_helper, astrbot_config)

    # 执行 WebChat 数据迁移
    await migration_webchat_data(db_helper, platform_id_map)

    # 执行偏好设置迁移
    await migration_preferences(db_helper,platform_id_map)

    # 执行平台统计表迁移
    await migration_platform_table(db_helper, platform_id_map)

    # 标记迁移完成
    await sp.put_async("global", "global", "migration_done_v4", True)

    logger.info("数据库迁移完成。")
