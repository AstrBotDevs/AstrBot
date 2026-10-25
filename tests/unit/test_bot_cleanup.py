"""Adapter cleanup must respect selections and exact ownership boundaries."""

import asyncio
import sqlite3
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlmodel import select, text

from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.cron.manager import CronJobManager
from astrbot.core.db.po import (
    ConversationV2,
    CronJob,
    PlatformMessageHistory,
    PlatformStat,
    ProviderStat,
    UmoAlias,
    UmoSender,
)
from astrbot.core.umop_config_router import UmopConfigRouter
from astrbot.core.utils.shared_preferences import SharedPreferences
from astrbot.dashboard.services import bot_cleanup_service, config_service
from astrbot.dashboard.services.bot_cleanup_service import delete_bot_data


@pytest.mark.asyncio
async def test_older_database_code_rejects_newer_conversation_schema(temp_db):
    """Reject a downgrade before creating an empty legacy conversation table.

    Args:
        temp_db: Isolated database that has not been initialized yet.
    """
    with sqlite3.connect(temp_db.db_path) as connection:
        connection.execute(
            "CREATE TABLE conversations_v3 (id INTEGER PRIMARY KEY, umo TEXT)"
        )
        connection.executemany(
            "INSERT INTO conversations_v3 (umo) VALUES (?)",
            [("onebotv11:GroupMessage:1",), ("Telegram:FriendMessage:2",)],
        )
    with pytest.raises(RuntimeError, match="newer conversations_v3 schema"):
        await temp_db.initialize()
    with sqlite3.connect(temp_db.db_path) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM conversations_v3").fetchone()[0]
            == 2
        )
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='conversations'"
            ).fetchone()
            is None
        )


@pytest.mark.asyncio
async def test_cleanup_rejects_newer_schema_before_any_data_mutation(
    temp_db, monkeypatch
):
    """Detect a schema change even after an older process initialized its DB.

    Args:
        temp_db: Isolated legacy database.
        monkeypatch: Pytest patch manager.
    """
    async with temp_db.get_db() as session:
        await session.execute(
            text("CREATE TABLE conversations_v3 (id INTEGER PRIMARY KEY, umo TEXT)")
        )
        await session.execute(
            text(
                "INSERT INTO conversations_v3 (umo) VALUES ('Telegram:FriendMessage:2')"
            )
        )
        await session.commit()
    preferences = SimpleNamespace(flush=AsyncMock())
    monkeypatch.setattr(bot_cleanup_service, "sp", preferences)
    with pytest.raises(ValueError, match="conversations_v3"):
        await delete_bot_data(
            SimpleNamespace(db=temp_db),
            "onebotv11",
            {"conversations", "preferences", "cron_jobs"},
        )
    preferences.flush.assert_not_awaited()
    async with temp_db.get_db() as session:
        assert (
            await session.execute(text("SELECT COUNT(*) FROM conversations_v3"))
        ).scalar_one() == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target",
    [
        "custom_rules",
        "preferences",
        "routing",
        "cron_jobs",
        "conversations",
        "message_history",
        "traces",
        "stats",
        "all",
    ],
)
async def test_cleanup_is_selective_and_matches_exact_platform(
    temp_db, monkeypatch, target
):
    """Keep case variants, wildcard-like IDs, shared resources and other bots."""
    preferences = SharedPreferences(temp_db)
    monkeypatch.setattr(bot_cleanup_service, "sp", preferences)
    trace_store = SimpleNamespace(
        clear_history=lambda **kwargs: trace_calls.append(kwargs)
    )
    trace_calls = []
    monkeypatch.setattr(bot_cleanup_service, "get_trace_store", lambda *_: trace_store)
    bot_id = "bot_%"
    ids = [bot_id, "BOT_%", "bot_ab", "bot_%-other"]
    core = SimpleNamespace(
        db=temp_db,
        cron_manager=CronJobManager(temp_db),
        conversation_manager=ConversationManager(temp_db),
        umop_config_router=UmopConfigRouter(preferences),
        astrbot_config={},
    )
    try:
        records = []
        groups = {"shared": {"name": "Shared", "umos": []}}
        routes = {"::": "shared", "bot*::": "shared"}
        for platform in ids:
            umo = f"{platform}:GroupMessage:room:with:colons"
            core.conversation_manager.session_conversations[umo] = platform
            groups["shared"]["umos"].append(umo)
            routes[f"{platform}::"] = "shared"
            records.extend(
                [
                    ConversationV2(
                        conversation_id=platform,
                        platform_id=platform,
                        user_id=umo,
                        content=[{"role": "user", "content": "Keep me"}],
                    ),
                    PlatformMessageHistory(
                        platform_id=platform, user_id="room", content={}
                    ),
                    UmoAlias(umo=umo, creator_sender_id="sender", user_alias="Room"),
                    UmoSender(umo=umo, sender_id="sender", sender_name="Alice"),
                    PlatformStat(
                        platform_id=platform,
                        platform_type="test",
                        timestamp=datetime(2026, 1, 1),
                    ),
                    ProviderStat(umo=umo, provider_id="shared"),
                    CronJob(
                        job_id=platform,
                        name="Reminder",
                        job_type="active_agent",
                        payload={"session": umo},
                        enabled=False,
                    ),
                ]
            )
            await preferences.session_put(
                umo, "session_service_config", {"llm_enabled": False}
            )
            await preferences.session_put(
                umo, "provider_perf_chat_completion", "shared"
            )
            await preferences.session_put(umo, "session_variables", {"name": platform})
            await preferences.session_put(umo, "sel_conv_id", platform)
            await preferences.put_async("global", umo, "dingtalk_staffid", "staff")
            await preferences.put_async(
                "lark", f"{platform}:app", "private_chat:user", "chat"
            )
        async with temp_db.get_db() as session:
            async with session.begin():
                session.add_all(records)
        await preferences.put_async("unknown", "unknown", "session_groups", groups)
        await core.umop_config_router.update_routing_data(routes)
        targets = (
            {target}
            if target != "all"
            else {
                "custom_rules",
                "preferences",
                "routing",
                "cron_jobs",
                "conversations",
                "message_history",
                "traces",
                "stats",
            }
        )

        await delete_bot_data(core, bot_id, targets)

        async with temp_db.get_db() as session:
            for model, category, field in [
                (ConversationV2, "conversations", "platform_id"),
                (PlatformMessageHistory, "message_history", "platform_id"),
                (UmoAlias, "message_history", "umo"),
                (UmoSender, "message_history", "umo"),
                (PlatformStat, "shared_platform_totals", "platform_id"),
                (ProviderStat, "stats", "umo"),
                (CronJob, "cron_jobs", "job_id"),
            ]:
                rows = (await session.execute(select(model))).scalars().all()
                owners = {getattr(row, field).partition(":")[0] for row in rows}
                assert owners == set(ids) - ({bot_id} if category in targets else set())
        for platform in ids:
            umo = groups["shared"]["umos"][ids.index(platform)]
            selected = platform == bot_id
            rules_removed = selected and "custom_rules" in targets
            prefs_removed = selected and "preferences" in targets
            assert await preferences.session_get(umo, "session_service_config") == (
                None if rules_removed else {"llm_enabled": False}
            )
            assert await preferences.session_get(umo, "session_variables") == (
                None if prefs_removed else {"name": platform}
            )
            assert await preferences.get_async("global", umo, "dingtalk_staffid") == (
                None if prefs_removed else "staff"
            )
            assert await preferences.get_async(
                "lark", f"{platform}:app", "private_chat:user"
            ) == (None if prefs_removed else "chat")
            pointer_removed = selected and bool(
                targets & {"preferences", "conversations"}
            )
            assert (await preferences.session_get(umo, "sel_conv_id")) == (
                None if pointer_removed else platform
            )
            assert (
                umo in core.conversation_manager.session_conversations
            ) is not pointer_removed
        saved_groups = await preferences.get_async(
            "unknown", "unknown", "session_groups"
        )
        assert "shared" in saved_groups
        assert len(saved_groups["shared"]["umos"]) == (
            3 if "preferences" in targets else 4
        )
        expected_routes = {
            pattern: profile
            for pattern, profile in routes.items()
            if "routing" not in targets or pattern.partition(":")[0] != bot_id
        }
        assert core.umop_config_router.umop_to_conf_id == expected_routes
        assert (
            await preferences.global_get("umop_config_routing", {}) == expected_routes
        )
        assert trace_calls == ([{"platform_id": bot_id}] if "traces" in targets else [])
    finally:
        await preferences.close()


@pytest.mark.asyncio
async def test_delete_bot_keeps_config_on_cleanup_failure(monkeypatch):
    """Report cleanup failure without losing the adapter needed for a retry."""
    bot = {"id": "bot", "enable": True}
    bus = SimpleNamespace(stopped_platforms={"bot"}, stop_platform=AsyncMock())
    core = SimpleNamespace(
        astrbot_config={"platform": [bot]},
        event_bus=bus,
        platform_manager=SimpleNamespace(
            terminate_platform=AsyncMock(), load_platform=AsyncMock()
        ),
    )
    cleanup = AsyncMock(side_effect=RuntimeError("storage unavailable"))
    monkeypatch.setattr(config_service, "delete_bot_data", cleanup)
    save = Mock()
    monkeypatch.setattr(config_service, "save_config", save)
    service = config_service.BotConfigService(core)
    with pytest.raises(ValueError, match="Invalid"):
        await service.delete_bot("bot", cleanup=["unknown"])
    core.platform_manager.terminate_platform.assert_not_awaited()
    with pytest.raises(RuntimeError, match="storage unavailable"):
        await service.delete_bot("bot", cleanup=["traces"])
    assert core.astrbot_config["platform"] == [bot]
    assert not bus.stopped_platforms
    save.assert_not_called()
    core.platform_manager.load_platform.assert_awaited_once_with(bot)

    cleanup.side_effect = None
    await service.delete_bot("bot")
    assert core.astrbot_config["platform"] == []
    assert cleanup.await_count == 1
    save.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("run_once", [False, True])
async def test_delete_scheduled_job_drains_active_run(temp_db, run_once):
    """Finish cancellation cleanup before deleting a job, including one-shots."""
    manager = CronJobManager(temp_db)
    started = asyncio.Event()
    finished = asyncio.Event()

    async def run(**_payload):
        try:
            started.set()
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            finished.set()

    job = await temp_db.create_cron_job(
        name="test",
        job_type="basic",
        cron_expression=None,
        payload={"session": "bot:FriendMessage:1"},
        run_once=run_once,
    )
    manager._basic_handlers[job.job_id] = run
    task = asyncio.create_task(manager._run_job(job.job_id))
    await asyncio.wait_for(started.wait(), 2)
    await asyncio.wait_for(manager.delete_job(job.job_id), 2)
    assert task.cancelled()
    assert finished.is_set()
    assert await temp_db.get_cron_job(job.job_id) is None
    assert manager._running_tasks == {}
