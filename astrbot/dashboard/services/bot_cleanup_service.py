"""Selective cleanup of data owned by one platform adapter instance."""

import asyncio

from sqlmodel import col, delete, func, select, text

from astrbot.core import sp
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db.po import (
    ConversationV2,
    PlatformMessageHistory,
    Preference,
    ProviderStat,
    UmoAlias,
    UmoSender,
)
from astrbot.core.utils.trace_store import get_trace_store
from astrbot.dashboard.schemas import BotCleanupTarget
from astrbot.dashboard.services.session_management_service import (
    AVAILABLE_SESSION_RULE_KEYS,
)


async def delete_bot_data(
    core: AstrBotCoreLifecycle, bot_id: str, targets: set[BotCleanupTarget]
) -> None:
    """Remove selected data without deleting shared resources or other adapters.

    Preference mutations go through their writer to keep the cache coherent.
    History tables are deleted in one transaction, while traces use their own
    writer queue. The caller stops incoming and active messages before cleanup.

    Args:
        core: Running core and its data managers.
        bot_id: Exact adapter instance ID, matched case-sensitively.
        targets: Explicitly selected cleanup categories.

    Raises:
        Exception: A storage or scheduler operation fails; the caller retains
            the adapter configuration so cleanup can be retried.
    """
    prefix = f"{bot_id}:"
    # An already-running process may have opened a database migrated by another
    # checkout. Refuse cleanup before changing any preferences or task records.
    async with core.db.get_db() as session:
        if (
            await session.execute(
                text(
                    "SELECT 1 FROM sqlite_master "
                    "WHERE type = 'table' AND name = 'conversations_v3'"
                )
            )
        ).first():
            raise ValueError(
                "Cannot clean up a database using conversations_v3 with this "
                "AstrBot version. Use the version that owns this schema."
            )
    await sp.flush()

    if "cron_jobs" in targets:
        for job in await core.db.list_cron_jobs():
            session = (job.payload or {}).get("session")
            if isinstance(session, str) and session.partition(":")[0] == bot_id:
                if core.cron_manager:
                    await core.cron_manager.delete_job(job.job_id)
                else:
                    await core.db.delete_cron_job(job.job_id)

    if targets & {"custom_rules", "preferences", "conversations"}:
        async with core.db.get_db() as session:
            preferences = (
                (
                    await session.execute(
                        select(Preference).where(
                            Preference.scope == "umo",
                            func.substr(Preference.scope_id, 1, len(prefix)) == prefix,
                        )
                    )
                )
                .scalars()
                .all()
            )
        for preference in preferences:
            is_rule = preference.key in AVAILABLE_SESSION_RULE_KEYS
            if (
                (is_rule and "custom_rules" in targets)
                or (not is_rule and "preferences" in targets)
                or (preference.key == "sel_conv_id" and "conversations" in targets)
            ):
                await sp.remove_async("umo", preference.scope_id, preference.key)

    if "preferences" in targets:
        groups = await sp.get_async("unknown", "unknown", "session_groups", {})
        for group in groups.values():
            group["umos"] = [
                umo for umo in group.get("umos", []) if umo.partition(":")[0] != bot_id
            ]
        await sp.put_async("unknown", "unknown", "session_groups", groups)

        # Built-in adapters also keep delivery mappings outside the UMO scope.
        async with core.db.get_db() as session:
            mappings = (
                (
                    await session.execute(
                        select(Preference).where(
                            func.substr(Preference.scope_id, 1, len(prefix)) == prefix,
                            col(Preference.scope).in_(["global", "lark"]),
                        )
                    )
                )
                .scalars()
                .all()
            )
        for preference in mappings:
            if preference.scope == "lark" or preference.key == "dingtalk_staffid":
                await sp.remove_async(
                    preference.scope, preference.scope_id, preference.key
                )

    if targets & {"preferences", "conversations"}:
        manager = core.conversation_manager
        for umo in list(manager.session_conversations):
            if umo.partition(":")[0] == bot_id:
                manager.session_conversations.pop(umo, None)

    if "routing" in targets:
        router = core.umop_config_router
        await router.update_routing_data(
            {
                pattern: config_id
                for pattern, config_id in router.umop_to_conf_id.items()
                if pattern.partition(":")[0] != bot_id
            }
        )

    async with core.db.get_db() as session:
        async with session.begin():
            if "conversations" in targets:
                await session.execute(
                    delete(ConversationV2).where(ConversationV2.platform_id == bot_id)
                )
            if "message_history" in targets:
                await session.execute(
                    delete(PlatformMessageHistory).where(
                        PlatformMessageHistory.platform_id == bot_id
                    )
                )
                for model in (UmoAlias, UmoSender):
                    await session.execute(
                        delete(model).where(
                            func.substr(model.umo, 1, len(prefix)) == prefix
                        )
                    )
            if "stats" in targets:
                # PlatformStat aggregates adapter types, so it is shared by bots.
                await session.execute(
                    delete(ProviderStat).where(
                        func.substr(ProviderStat.umo, 1, len(prefix)) == prefix
                    )
                )

    if "traces" in targets:
        await asyncio.to_thread(
            get_trace_store(core.astrbot_config).clear_history, platform_id=bot_id
        )
