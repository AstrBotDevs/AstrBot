"""Verify cron timezone resolution across configuration, storage, and scheduling."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.cron.manager import CronJobManager
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.star.context import Context
from astrbot.core.tools.cron_tools import FutureTaskTool
from astrbot.core.umop_config_router import UmopConfigRouter
from astrbot.dashboard.services.cron_service import CronService


@pytest.mark.parametrize("entrypoint", ["tool", "dashboard", "explicit_timezone"])
@pytest.mark.parametrize("run_once", [False, True])
@pytest.mark.asyncio
async def test_cron_uses_system_timezone_with_a_bound_profile(
    tmp_path, entrypoint, run_once
):
    """A hidden profile timezone must not override the system scheduling timezone.

    Args:
        tmp_path: Isolated directory for the real SQLite database.
        entrypoint: Creation path, optionally supplying an explicit job timezone.
        run_once: Whether to schedule a naive one-shot timestamp or a daily cron.
    """
    db = SQLiteDatabase(str(tmp_path / "cron.db"))
    await db.initialize()
    manager = CronJobManager(db)
    umo = "test:FriendMessage:user"
    router = UmopConfigRouter(MagicMock())
    router.umop_to_conf_id = {umo: "profile"}
    config_manager = AstrBotConfigManager(
        default_config={"timezone": "Etc/GMT-2"},
        ucr=router,
        sp=MagicMock(),
    )
    config_manager.abconf_data = {
        "profile": {"name": "Chat profile", "path": "profile.json"}
    }
    config_manager.confs["profile"] = {"timezone": "Asia/Shanghai"}
    context = Context(
        event_queue=asyncio.Queue(),
        config=config_manager.default_conf,
        db=db,
        provider_manager=None,
        platform_manager=None,
        conversation_manager=None,
        message_history_manager=None,
        persona_manager=None,
        astrbot_config_mgr=config_manager,
        knowledge_base_manager=None,
        cron_manager=manager,
    )
    assert context.get_config(umo)["timezone"] == "Asia/Shanghai"
    await manager.start(context)
    manager.scheduler.pause()
    try:
        payload = {
            "name": "Morning reminder",
            "note": "Send the daily report",
            "run_once": run_once,
            "run_at": "2099-01-02T08:00:00" if run_once else None,
            "cron_expression": None if run_once else "0 8 * * *",
        }
        if entrypoint == "tool":
            wrapper = SimpleNamespace(
                context=SimpleNamespace(
                    context=context,
                    event=SimpleNamespace(
                        unified_msg_origin=umo, get_sender_id=lambda: "user"
                    ),
                )
            )
            result = await FutureTaskTool().call(wrapper, action="create", **payload)
            assert result.startswith("Scheduled future task"), result
        else:
            payload["session"] = umo
            if entrypoint == "explicit_timezone":
                payload["timezone"] = "UTC"
            await CronService(context).create_job(payload)

        job = (await db.list_cron_jobs())[0]
        expected_zone = "UTC" if entrypoint == "explicit_timezone" else "Etc/GMT-2"
        assert job.timezone == expected_zone
        expected_time = datetime(2099, 1, 2, 8, tzinfo=ZoneInfo(expected_zone))
        now = datetime(2099, 1, 2, tzinfo=timezone.utc)
        scheduled = manager.scheduler.get_job(job.job_id)
        assert scheduled.trigger.get_next_fire_time(None, now) == expected_time

        # Restoring the durable row must preserve the same execution instant.
        await manager.shutdown()
        await manager.start(context)
        manager.scheduler.pause()
        restored = manager.scheduler.get_job(job.job_id)
        assert restored.trigger.get_next_fire_time(None, now) == expected_time
    finally:
        await manager.shutdown()
        await db.engine.dispose()
