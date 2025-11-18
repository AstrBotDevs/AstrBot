"""Migration script from version 4.6 to 4.7.

This migration creates PlatformSession from existing platform_message_history records.

Changes:
- Creates platform_sessions table
- Adds platform_id field (default: 'webchat')
- Adds display_name field
- Session_id format: {platform_id}_{uuid}
"""

from sqlalchemy import func, select
from sqlmodel import col

from astrbot.api import logger, sp
from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import PlatformMessageHistory


async def migrate_46_to_47(db_helper: BaseDatabase):
    """Create PlatformSession records from platform_message_history.

    This migration extracts all unique user_ids from platform_message_history
    where platform_id='webchat' and creates corresponding PlatformSession records.
    """
    # 检查是否已经完成迁移
    migration_done = await db_helper.get_preference(
        "global", "global", "migration_done_v47"
    )
    if migration_done:
        return

    logger.info("开始执行数据库迁移（4.6 -> 4.7）...")

    try:
        async with db_helper.get_db() as session:
            # 从 platform_message_history 创建 PlatformSession
            query = (
                select(
                    col(PlatformMessageHistory.user_id),
                    col(PlatformMessageHistory.sender_name),
                    func.min(PlatformMessageHistory.created_at).label("earliest"),
                    func.max(PlatformMessageHistory.updated_at).label("latest"),
                )
                .where(col(PlatformMessageHistory.platform_id) == "webchat")
                .where(col(PlatformMessageHistory.sender_id) == "astrbot")
                .group_by(col(PlatformMessageHistory.user_id))
            )

            result = await session.execute(query)
            webchat_users = result.all()

            if not webchat_users:
                logger.info("没有找到需要迁移的 WebChat 数据")
                await sp.put_async("global", "global", "migration_done_v47", True)
                return

            logger.info(f"找到 {len(webchat_users)} 个 WebChat 会话需要迁移")

            # 为每个 user_id 创建 PlatformSession 记录
            migrated_count = 0
            skipped_count = 0

            for user_id, sender_name, created_at, updated_at in webchat_users:
                # user_id 就是 webchat_conv_id (session_id)
                session_id = user_id

                # sender_name 通常是 username，但可能为 None
                creator = sender_name if sender_name else "guest"

                # 检查是否已经存在该会话
                existing_session = await db_helper.get_platform_session_by_id(
                    session_id
                )
                if existing_session:
                    logger.debug(f"会话 {session_id} 已存在，跳过")
                    skipped_count += 1
                    continue

                # 创建新的 PlatformSession
                try:
                    await db_helper.create_platform_session(
                        creator=creator,
                        session_id=session_id,
                        platform_id="webchat",
                        is_group=0,
                    )

                    migrated_count += 1

                    if migrated_count % 100 == 0:
                        logger.info(f"已迁移 {migrated_count} 个会话...")

                except Exception as e:
                    logger.error(f"迁移会话 {session_id} 失败: {e}")
                    continue

            logger.info(
                f"WebChat 会话迁移完成！成功迁移: {migrated_count}, 跳过: {skipped_count}",
            )

        # 标记迁移完成
        await sp.put_async("global", "global", "migration_done_v47", True)

    except Exception as e:
        logger.error(f"迁移过程中发生错误: {e}", exc_info=True)
        raise
