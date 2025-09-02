import json
import datetime
from .. import BaseDatabase
from .sqlite_v3 import SQLiteDatabase as SQLiteV3DatabaseV3
from .shared_preferences_v3 import sp as sp_v3
from astrbot.core.config.default import DB_PATH
from astrbot.api import logger, sp
from astrbot.core.config import AstrBotConfig
from astrbot.core.platform.astr_message_event import MessageSesion
from sqlalchemy.ext.asyncio import AsyncSession
from astrbot.core.db.po import ConversationV2, PlatformMessageHistory
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
            for idx, conversation in enumerate(conversations):
                if total_cnt > 0 and (idx + 1) % max(1, total_cnt // 10) == 0:
                    progress = int((idx + 1) / total_cnt * 100)
                    if progress % 10 == 0:
                        logger.info(f"进度: {progress}% ({idx + 1}/{total_cnt})")
                try:
                    conv = db_helper_v3.get_conversation_by_user_id(
                        user_id=conversation.get("user_id", "unknown"),
                        cid=conversation.get("cid", "unknown"),
                    )
                    if not conv:
                        logger.info(
                            f"未找到该条旧会话对应的具体数据: {conversation}, 跳过。"
                        )
                    if ":" not in conv.user_id:
                        continue
                    session = MessageSesion.from_str(session_str=conv.user_id)
                    platform_id = get_platform_id(
                        platform_id_map, session.platform_name
                    )
                    session.platform_id = platform_id  # 更新平台名称为新的 ID
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
                except Exception as e:
                    logger.error(
                        f"迁移旧会话 {conversation.get('cid', 'unknown')} 失败: {e}",
                        exc_info=True,
                    )
    logger.info(f"成功迁移 {total_cnt} 条旧的会话数据到新表。")


async def migration_platform_table(
    db_helper: BaseDatabase, platform_id_map: dict[str, dict[str, str]]
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
        logger.info("没有找到旧平台数据，跳过迁移。")
        return

    first_time_stamp = platform_stats_v3[0].timestamp
    end_time_stamp = platform_stats_v3[-1].timestamp
    start_time = first_time_stamp - (first_time_stamp % 3600)  # 向下取整到小时
    end_time = end_time_stamp + (3600 - (end_time_stamp % 3600))  # 向上取整到小时

    idx = 0

    async with db_helper.get_db() as dbsession:
        dbsession: AsyncSession
        async with dbsession.begin():
            total_buckets = (end_time - start_time) // 3600
            for bucket_idx, bucket_end in enumerate(range(start_time, end_time, 3600)):
                if bucket_idx % 500 == 0:
                    progress = int((bucket_idx + 1) / total_buckets * 100)
                    logger.info(f"进度: {progress}% ({bucket_idx + 1}/{total_buckets})")
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
    logger.info(f"成功迁移 {len(platform_stats_v3)} 条旧的平台数据到新表。")


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
            for idx, conversation in enumerate(conversations):
                if total_cnt > 0 and (idx + 1) % max(1, total_cnt // 10) == 0:
                    progress = int((idx + 1) / total_cnt * 100)
                    if progress % 10 == 0:
                        logger.info(f"进度: {progress}% ({idx + 1}/{total_cnt})")
                try:
                    conv = db_helper_v3.get_conversation_by_user_id(
                        user_id=conversation.get("user_id", "unknown"),
                        cid=conversation.get("cid", "unknown"),
                    )
                    if not conv:
                        logger.info(
                            f"未找到该条旧会话对应的具体数据: {conversation}, 跳过。"
                        )
                    if ":" in conv.user_id:
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

                except Exception:
                    logger.error(
                        f"迁移旧 WebChat 会话 {conversation.get('cid', 'unknown')} 失败",
                        exc_info=True,
                    )

    logger.info(f"成功迁移 {total_cnt} 条旧的 WebChat 会话数据到新表。")


async def migration_persona_data(
    db_helper: BaseDatabase, astrbot_config: AstrBotConfig
):
    """
    迁移 Persona 数据到新的表中。
    旧的 Persona 数据存储在 preference 中，新的 Persona 数据存储在 persona 表中。
    """
    v3_persona_config: list[dict] = astrbot_config.get("persona", [])
    total_personas = len(v3_persona_config)
    logger.info(f"迁移 {total_personas} 个 Persona 配置到新表中...")

    for idx, persona in enumerate(v3_persona_config):
        if total_personas > 0 and (idx + 1) % max(1, total_personas // 10) == 0:
            progress = int((idx + 1) / total_personas * 100)
            if progress % 10 == 0:
                logger.info(f"进度: {progress}% ({idx + 1}/{total_personas})")
        try:
            begin_dialogs = persona.get("begin_dialogs", [])
            mood_imitation_dialogs = persona.get("mood_imitation_dialogs", [])
            mood_prompt = ""
            user_turn = True
            for mood_dialog in mood_imitation_dialogs:
                if user_turn:
                    mood_prompt += f"A: {mood_dialog}\n"
                else:
                    mood_prompt += f"B: {mood_dialog}\n"
                user_turn = not user_turn
            system_prompt = persona.get("prompt", "")
            if mood_prompt:
                system_prompt += f"Here are few shots of dialogs, you need to imitate the tone of 'B' in the following dialogs to respond:\n {mood_prompt}"
            persona_new = await db_helper.insert_persona(
                persona_id=persona["name"],
                system_prompt=system_prompt,
                begin_dialogs=begin_dialogs,
            )
            logger.info(
                f"迁移 Persona {persona['name']}({persona_new.system_prompt[:30]}...) 到新表成功。"
            )
        except Exception as e:
            logger.error(f"解析 Persona 配置失败：{e}")


async def migration_preferences(
    db_helper: BaseDatabase, platform_id_map: dict[str, dict[str, str]]
):
    # 1. global scope migration
    keys = [
        "inactivated_llm_tools",
        "inactivated_plugins",
        "curr_provider",
        "curr_provider_tts",
        "curr_provider_stt",
        "alter_cmd",
    ]
    for key in keys:
        value = sp_v3.get(key)
        if value is not None:
            await sp.put_async("global", "global", key, value)
            logger.info(f"迁移全局偏好设置 {key} 成功，值: {value}")

    # 2. umo scope migration
    session_conversation = sp_v3.get("session_conversation", default={})
    for umo, conversation_id in session_conversation.items():
        if not umo or not conversation_id:
            continue
        try:
            session = MessageSesion.from_str(session_str=umo)
            platform_id = get_platform_id(platform_id_map, session.platform_name)
            session.platform_id = platform_id
            await sp.put_async("umo", str(session), "sel_conv_id", conversation_id)
            logger.info(f"迁移会话 {umo} 的对话数据到新表成功，平台 ID: {platform_id}")
        except Exception as e:
            logger.error(f"迁移会话 {umo} 的对话数据失败: {e}", exc_info=True)

    session_service_config = sp_v3.get("session_service_config", default={})
    for umo, config in session_service_config.items():
        if not umo or not config:
            continue
        try:
            session = MessageSesion.from_str(session_str=umo)
            platform_id = get_platform_id(platform_id_map, session.platform_name)
            session.platform_id = platform_id

            await sp.put_async("umo", str(session), "session_service_config", config)

            logger.info(f"迁移会话 {umo} 的服务配置到新表成功，平台 ID: {platform_id}")
        except Exception as e:
            logger.error(f"迁移会话 {umo} 的服务配置失败: {e}", exc_info=True)

    session_variables = sp_v3.get("session_variables", default={})
    for umo, variables in session_variables.items():
        if not umo or not variables:
            continue
        try:
            session = MessageSesion.from_str(session_str=umo)
            platform_id = get_platform_id(platform_id_map, session.platform_name)
            session.platform_id = platform_id
            await sp.put_async("umo", str(session), "session_variables", variables)
        except Exception as e:
            logger.error(f"迁移会话 {umo} 的变量失败: {e}", exc_info=True)

    session_provider_perf = sp_v3.get("session_provider_perf", default={})
    for umo, perf in session_provider_perf.items():
        if not umo or not perf:
            continue
        try:
            session = MessageSesion.from_str(session_str=umo)
            platform_id = get_platform_id(platform_id_map, session.platform_name)
            session.platform_id = platform_id

            for provider_type, provider_id in perf.items():
                await sp.put_async(
                    "umo", str(session), f"provider_perf_{provider_type}", provider_id
                )
            logger.info(
                f"迁移会话 {umo} 的提供商偏好到新表成功，平台 ID: {platform_id}"
            )
        except Exception as e:
            logger.error(f"迁移会话 {umo} 的提供商偏好失败: {e}", exc_info=True)
