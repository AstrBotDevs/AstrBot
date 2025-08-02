import json
import datetime
from .. import BaseDatabase
from .sqlite_v3 import SQLiteDatabase as SQLiteV3DatabaseV3
from astrbot.core.config.default import DB_PATH
from astrbot.api import logger
from astrbot.core.platform.astr_message_event import MessageSesion
from sqlalchemy.ext.asyncio import AsyncSession
from astrbot.core.db.po import (
    ConversationV2,
    PlatformMessageHistory,
)
from sqlalchemy import text

"""
1. 迁移旧的 webchat_conversation 表到新的 conversation 表。
2. 迁移旧的 platform 到新的 platform_stats 表。
"""


def get_platform_id(
    platform_id_map: dict[str, dict[str, str]], old_platform_name: str
) -> str:
    return platform_id_map.get(
        old_platform_name,
        {"platform_id": old_platform_name, "platform_type": old_platform_name},
    ).get("platform_id", old_platform_name)


def get_platform_type(
    platform_id_map: dict[str, dict[str, str]], old_platform_name: str
) -> str:
    return platform_id_map.get(
        old_platform_name,
        {"platform_id": old_platform_name, "platform_type": old_platform_name},
    ).get("platform_type", old_platform_name)


async def migration_conversation_table(
    db_helper: BaseDatabase, platform_id_map: dict[str, dict[str, str]]
):
    db_helper_v3 = SQLiteV3DatabaseV3(
        db_path=DB_PATH.replace("data_v4.db", "data_v3.db")
    )
    conversations, total_cnt = db_helper_v3.get_all_conversations(
        page=1, page_size=10000000
    )
    logger.info(f"迁移 {total_cnt} 条旧的会话数据到新的表中...")

    async with db_helper.get_db() as dbsession:
        dbsession: AsyncSession
        async with dbsession.begin():
            for conversation in conversations:
                try:
                    conv = db_helper_v3.get_conversation_by_user_id(
                        user_id=conversation.get("user_id", "unknown"),
                        cid=conversation.get("cid", "unknown"),
                    )
                    if not conv:
                        logger.warning(
                            f"未找到该条旧会话对应的具体数据: {conversation}, 跳过。"
                        )
                    if ":" not in conv.user_id:
                        logger.warning(
                            f"跳过 user_id 为 {conv.user_id} 的会话，它可能是 WebChat 的消息历史记录。"
                        )
                        continue
                    session = MessageSesion.from_str(session_str=conv.user_id)
                    platform_id = get_platform_id(
                        platform_id_map, session.platform_name
                    )
                    session.platform_name = platform_id  # 更新平台名称为新的 ID
                    conv_v2 = ConversationV2(
                        user_id=str(session),
                        content=json.loads(conv.history) if conv.history else [],
                        platform_id=platform_id,
                        title=conv.title,
                        persona_id=conv.persona_id,
                        conversation_id=conv.cid,
                        created_at=datetime.datetime.fromtimestamp(conv.created_at),
                        updated_at=datetime.datetime.fromtimestamp(conv.updated_at),
                    )
                    dbsession.add(conv_v2)
                    if conv_v2:
                        logger.info(f"迁移旧会话 {conv.cid} 到新表成功。")
                except Exception as e:
                    logger.error(
                        f"迁移旧会话 {conversation.get('cid', 'unknown')} 失败: {e}",
                        exc_info=True,
                    )


async def migration_platform_table(
    db_helper: BaseDatabase, platform_id_map: dict[str, str]
):
    db_helper_v3 = SQLiteV3DatabaseV3(
        db_path=DB_PATH.replace("data_v4.db", "data_v3.db")
    )
    secs_from_2023_4_10_to_now = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.datetime(2023, 4, 10, tzinfo=datetime.timezone.utc)
    ).total_seconds()
    offset_sec = int(secs_from_2023_4_10_to_now)
    logger.info(f"迁移旧平台数据，offset_sec: {offset_sec} 秒。")
    stats = db_helper_v3.get_base_stats(offset_sec=offset_sec)
    logger.info(f"迁移 {len(stats.platform)} 条旧的平台数据到新的表中...")
    platform_stats_v3 = stats.platform

    if not platform_stats_v3:
        logger.warning("没有找到旧平台数据，跳过迁移。")
        return

    first_time_stamp = platform_stats_v3[0].timestamp
    end_time_stamp = platform_stats_v3[-1].timestamp
    start_time = first_time_stamp - (first_time_stamp % 3600)  # 向下取整到小时
    end_time = end_time_stamp + (3600 - (end_time_stamp % 3600))  # 向上取整到小时

    idx = 0

    async with db_helper.get_db() as dbsession:
        dbsession: AsyncSession
        async with dbsession.begin():
            for bucket_end in range(start_time, end_time, 3600):
                cnt = 0
                while (
                    idx < len(platform_stats_v3)
                    and platform_stats_v3[idx].timestamp < bucket_end
                ):
                    cnt += platform_stats_v3[idx].count
                    idx += 1
                if cnt == 0:
                    continue
                platform_id = get_platform_id(
                    platform_id_map, platform_stats_v3[idx].name
                )
                platform_type = get_platform_type(
                    platform_id_map, platform_stats_v3[idx].name
                )
                logger.info(
                    f"迁移平台统计数据: {platform_id}, {platform_type}, 时间戳: {bucket_end}, 计数: {cnt}"
                )
                try:
                    await dbsession.execute(
                        text("""
                        INSERT INTO platform_stats (timestamp, platform_id, platform_type, count)
                        VALUES (:timestamp, :platform_id, :platform_type, :count)
                        ON CONFLICT(timestamp, platform_id, platform_type) DO UPDATE SET
                            count = platform_stats.count + EXCLUDED.count
                        """),
                        {
                            "timestamp": datetime.datetime.fromtimestamp(
                                bucket_end, tz=datetime.timezone.utc
                            ),
                            "platform_id": platform_id,
                            "platform_type": platform_type,
                            "count": cnt,
                        },
                    )
                except Exception:
                    logger.error(
                        f"迁移平台统计数据失败: {platform_id}, {platform_type}, 时间戳: {bucket_end}",
                        exc_info=True,
                    )


async def migration_webchat_data(
    db_helper: BaseDatabase, platform_id_map: dict[str, dict[str, str]]
):
    """迁移 WebChat 的历史记录到新的 PlatformMessageHistory 表中"""
    db_helper_v3 = SQLiteV3DatabaseV3(
        db_path=DB_PATH.replace("data_v4.db", "data_v3.db")
    )
    conversations, total_cnt = db_helper_v3.get_all_conversations(
        page=1, page_size=10000000
    )
    logger.info(f"迁移 {total_cnt} 条旧的 WebChat 会话数据到新的表中...")

    async with db_helper.get_db() as dbsession:
        dbsession: AsyncSession
        async with dbsession.begin():
            for conversation in conversations:
                try:
                    conv = db_helper_v3.get_conversation_by_user_id(
                        user_id=conversation.get("user_id", "unknown"),
                        cid=conversation.get("cid", "unknown"),
                    )
                    if not conv:
                        logger.warning(
                            f"未找到该条旧会话对应的具体数据: {conversation}, 跳过。"
                        )
                    if ":" in conv.user_id:
                        logger.warning(
                            f"跳过 user_id 为 {conv.user_id} 的会话，它不是 WebChat 的消息历史记录。"
                        )
                        continue
                    platform_id = "webchat"
                    history = json.loads(conv.history) if conv.history else []
                    for msg in history:
                        type_ = msg.get("type")  # user type, "bot" or "user"
                        new_history = PlatformMessageHistory(
                            platform_id=platform_id,
                            user_id=conv.cid,  # we use conv.cid as user_id for webchat
                            content=msg,
                            sender_id=type_,
                            sender_name=type_,
                        )
                        dbsession.add(new_history)

                    logger.info(f"迁移旧 WebChat 会话 {conv.cid} 到新表成功。")
                except Exception:
                    logger.error(
                        f"迁移旧 WebChat 会话 {conversation.get('cid', 'unknown')} 失败",
                        exc_info=True,
                    )
