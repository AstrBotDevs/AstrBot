"""Verify rejected cron edits preserve durable jobs and their live schedules."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from astrbot.core.cron.manager import CronJobManager, CronJobSchedulingError
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.dashboard.services.cron_service import CronService, CronServiceError


@pytest_asyncio.fixture
async def cron_store(tmp_path):
    """Provide a real SQLite store and scheduler without external agent calls."""
    db = SQLiteDatabase(str(tmp_path / "cron.db"))
    await db.initialize()
    manager = CronJobManager(db)
    await manager.start(SimpleNamespace())
    manager.scheduler.pause()
    try:
        yield db, manager
    finally:
        await manager.shutdown()
        await db.engine.dispose()


@pytest.mark.parametrize("expression", ["not a cron", "60 9 * * *", "0 9 * * 8"])
@pytest.mark.asyncio
async def test_invalid_dashboard_edit_preserves_job_and_schedule(cron_store, expression):
    """A rejected edit must not stop a previously working reminder.

    Args:
        cron_store: Real database and paused scheduler.
        expression: Invalid field count, minute, or crontab weekday.
    """
    db, manager = cron_store
    job = await manager.add_active_job(
        name="Daily reminder",
        cron_expression="0 9 * * 1",
        timezone="UTC",
        payload={"note": "Send the report", "session": "test:FriendMessage:user"},
    )
    scheduled = manager.scheduler.get_job(job.job_id)
    next_run = scheduled.next_run_time
    service = CronService(SimpleNamespace(cron_manager=manager))

    with pytest.raises(CronServiceError):
        await service.update_job(
            job.job_id, {"name": "Rejected name", "cron_expression": expression}
        )

    stored = await db.get_cron_job(job.job_id)
    assert stored.name == job.name
    assert stored.cron_expression == job.cron_expression
    assert stored.payload == job.payload
    assert manager.scheduler.get_job(job.job_id) is scheduled
    assert scheduled.next_run_time == next_run

    # The original scheduled callback still dispatches the original payload.
    manager._run_active_agent_job = AsyncMock()
    await scheduled.func(*scheduled.args)
    executed = manager._run_active_agent_job.await_args.args[0]
    assert executed.name == job.name
    assert executed.payload == job.payload

    # Reload from SQLite, as on restart; the failed edit must not poison startup.
    await manager.shutdown()
    await manager.start(SimpleNamespace())
    manager.scheduler.pause()
    restored = manager.scheduler.get_job(job.job_id)
    assert restored is not None
    assert str(restored.trigger) == str(scheduled.trigger)


@pytest.mark.asyncio
async def test_invalid_one_shot_edit_preserves_original_deadline(cron_store):
    """Reject malformed one-shot timestamps before mutating the saved task."""
    db, manager = cron_store
    deadline = datetime(2099, 1, 1, 9, tzinfo=timezone.utc)
    job = await manager.add_active_job(
        name="One-shot reminder",
        cron_expression=None,
        payload={"note": "Send the report"},
        run_once=True,
        run_at=deadline,
    )
    scheduled = manager.scheduler.get_job(job.job_id)
    with pytest.raises(CronJobSchedulingError):
        await manager.update_job(job.job_id, payload={"run_at": "not-a-date"})

    assert (await db.get_cron_job(job.job_id)).payload == job.payload
    assert manager.scheduler.get_job(job.job_id) is scheduled
    assert scheduled.next_run_time == deadline


@pytest.mark.asyncio
async def test_invalid_enable_keeps_legacy_job_disabled(cron_store):
    """An invalid saved task must remain disabled when activation fails."""
    db, manager = cron_store
    job = await db.create_cron_job(
        name="Legacy invalid task",
        job_type="active_agent",
        cron_expression="invalid",
        enabled=False,
    )
    with pytest.raises(CronJobSchedulingError):
        await manager.update_job(job.job_id, enabled=True)

    assert (await db.get_cron_job(job.job_id)).enabled is False
    assert manager.scheduler.get_job(job.job_id) is None


@pytest.mark.asyncio
async def test_valid_edit_and_disable_remain_supported(cron_store):
    """Valid edits take effect, and broken legacy jobs can still be disabled."""
    db, manager = cron_store
    job = await manager.add_active_job(
        name="Reminder", cron_expression="0 9 * * *", payload={}, timezone="UTC"
    )
    updated = await manager.update_job(job.job_id, cron_expression="0 10 * * 0")
    assert updated.cron_expression == "0 10 * * 0"
    scheduled = manager.scheduler.get_job(job.job_id)
    assert scheduled.next_run_time.hour == 10
    assert scheduled.next_run_time.weekday() == 6

    # A pre-existing malformed row must not prevent the user from disabling it.
    await db.update_cron_job(job.job_id, cron_expression="invalid")
    disabled = await manager.update_job(job.job_id, enabled=False)
    assert disabled.enabled is False
    assert manager.scheduler.get_job(job.job_id) is None
