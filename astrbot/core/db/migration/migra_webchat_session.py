"""
WebChat 会话数据迁移脚本。

此迁移从现有的 platform_message_history 记录中创建 PlatformSession 记录。

变更内容：
- 创建 platform_sessions 表
- 添加 platform_id 字段（默认值：'webchat'）
- 添加 display_name 字段
- Session_id 格式：{platform_id}_{uuid}
"""

# 导入 SQLAlchemy 的聚合函数和查询构建函数
from sqlalchemy import func, select
# 导入 SQLModel 的列选择函数，用于在查询中引用模型列
from sqlmodel import col

# 导入全局日志记录器和共享偏好设置实例
from astrbot.api import logger, sp
# 导入数据库基础操作类
from astrbot.core.db import BaseDatabase
# 导入数据库持久化对象（PO）模型
from astrbot.core.db.po import ConversationV2, PlatformMessageHistory, PlatformSession


async def migrate_webchat_session(db_helper: BaseDatabase) -> None:
    """
    从 platform_message_history 表创建 PlatformSession 记录。

    此迁移提取 platform_message_history 中所有 platform_id='webchat' 的
    唯一 user_id，并为每个用户创建对应的 PlatformSession 记录。
    同时从 Conversations 表中获取对话标题作为会话的显示名称。

    迁移过程：
        1. 检查是否已完成迁移（通过偏好设置标记）
        2. 查询所有 WebChat 用户的聊天历史记录
        3. 检查已存在的会话，避免重复创建
        4. 从 Conversations 表获取对话标题
        5. 批量创建 PlatformSession 记录
        6. 标记迁移完成

    Args:
        db_helper: 数据库操作助手实例，用于数据库访问和偏好设置管理
    """
    # 检查迁移是否已经完成
    # 从偏好设置中读取迁移完成标记
    migration_done = await db_helper.get_preference(
        "global", "global", "migration_done_webchat_session_1"
    )
    # 如果已经完成迁移，直接返回
    if migration_done:
        return

    # 记录迁移开始日志
    logger.info("开始执行数据库迁移（WebChat 会话迁移）...")

    try:
        # 获取数据库会话上下文管理器
        async with db_helper.get_db() as session:
            # 构建查询：从 platform_message_history 中提取 WebChat 用户数据
            query = (
                select(
                    # 选择 user_id 字段（作为会话标识）
                    col(PlatformMessageHistory.user_id),
                    # 选择 sender_name 字段（发送者名称）
                    col(PlatformMessageHistory.sender_name),
                    # 使用聚合函数获取最早的创建时间
                    func.min(PlatformMessageHistory.created_at).label("earliest"),
                    # 使用聚合函数获取最晚的更新时间
                    func.max(PlatformMessageHistory.updated_at).label("latest"),
                )
                # 过滤条件：只查询 WebChat 平台的消息
                .where(col(PlatformMessageHistory.platform_id) == "webchat")
                # 过滤条件：排除机器人自己发送的消息
                .where(col(PlatformMessageHistory.sender_id) != "bot")
                # 按 user_id 分组，获取每个用户的聚合数据
                .group_by(col(PlatformMessageHistory.user_id))
            )

            # 执行查询并获取结果
            result = await session.execute(query)
            # 获取所有查询结果行
            webchat_users = result.all()

            # 如果没有找到需要迁移的用户数据
            if not webchat_users:
                logger.info("没有找到需要迁移的 WebChat 数据")
                # 直接标记迁移完成并返回
                await sp.put_async(
                    "global", "global", "migration_done_webchat_session_1", True
                )
                return

            # 记录找到的待迁移会话数量
            logger.info(f"找到 {len(webchat_users)} 个 WebChat 会话需要迁移")

            # 查询已存在的 PlatformSession，避免重复创建
            existing_query = select(col(PlatformSession.session_id))
            existing_result = await session.execute(existing_query)
            # 将已存在的 session_id 转换为集合，方便快速查找
            existing_session_ids = {row[0] for row in existing_result.fetchall()}

            # 查询 Conversations 表中的 title，用于设置 display_name
            # 构建 Conversations 的 user_id 列表
            # 格式: webchat:FriendMessage:webchat!astrbot!{user_id}
            user_ids_to_query = [
                f"webchat:FriendMessage:webchat!astrbot!{user_id}"
                for user_id, _, _, _ in webchat_users
            ]
            # 构建查询：获取 Conversations 的标题信息
            conv_query = select(
                col(ConversationV2.user_id),   # 对话的用户 ID
                col(ConversationV2.title)       # 对话的标题
            ).where(
                # 筛选出属于这些 WebChat 用户的对话
                col(ConversationV2.user_id).in_(user_ids_to_query)
            )
            # 执行对话查询
            conv_result = await session.execute(conv_query)
            # 创建 user_id -> title 的映射字典
            # 从 Conversations 的复合 user_id 中提取原始 user_id 作为键
            title_map = {
                user_id.replace("webchat:FriendMessage:webchat!astrbot!", ""): title
                for user_id, title in conv_result.fetchall()
            }

            # 准备批量创建的 PlatformSession 记录列表
            sessions_to_add = []
            # 记录跳过的会话数量（已存在的会话）
            skipped_count = 0

            # 遍历每个 WebChat 用户，创建对应的 PlatformSession
            for user_id, sender_name, created_at, updated_at in webchat_users:
                # user_id 直接作为 session_id 使用
                session_id = user_id

                # 设置创建者名称，如果 sender_name 为空则使用 "guest"
                creator = sender_name if sender_name else "guest"

                # 检查该会话是否已经存在
                if session_id in existing_session_ids:
                    logger.debug(f"会话 {session_id} 已存在，跳过")
                    skipped_count += 1  # 增加跳过计数
                    continue  # 跳过已存在的会话

                # 从 Conversations 表的映射中获取 display_name
                display_name = title_map.get(user_id)

                # 创建新的 PlatformSession 对象，保留原始的时间戳信息
                new_session = PlatformSession(
                    session_id=session_id,      # 会话唯一标识
                    platform_id="webchat",       # 平台标识
                    creator=creator,             # 创建者名称
                    is_group=0,                  # 非群组会话（0 表示私聊）
                    created_at=created_at,       # 原始创建时间
                    updated_at=updated_at,       # 原始更新时间
                    display_name=display_name,   # 显示名称（从对话标题获取）
                )
                # 添加到待插入列表
                sessions_to_add.append(new_session)

            # 批量插入新创建的会话记录
            if sessions_to_add:
                # 使用 add_all 批量添加所有新会话
                session.add_all(sessions_to_add)
                # 提交事务，将所有更改写入数据库
                await session.commit()

                # 记录迁移完成统计信息
                logger.info(
                    f"WebChat 会话迁移完成！成功迁移: {len(sessions_to_add)}, 跳过: {skipped_count}",
                )
            else:
                # 没有新会话需要创建
                logger.info("没有新会话需要迁移")

        # 迁移成功完成，在偏好设置中标记完成状态
        await sp.put_async("global", "global", "migration_done_webchat_session_1", True)

    except Exception as e:
        # 捕获迁移过程中的任何异常
        # exc_info=True 会记录完整的异常堆栈信息
        logger.error(f"迁移过程中发生错误: {e}", exc_info=True)
        # 重新抛出异常，让上层调用者处理
        raise