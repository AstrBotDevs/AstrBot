"""Verify rejected cron edits preserve durable jobs and their live schedules."""

import asyncio
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
    scheduled = manager._get_scheduled_job(job.job_id)
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
    assert manager._get_scheduled_job(job.job_id) is scheduled
    assert scheduled.next_run_time == next_run

    # The original scheduled callback still dispatches the original payload.
    manager._run_active_agent_job = AsyncMock()
    await scheduled.func(*scheduled.args, **scheduled.kwargs)
    executed = manager._run_active_agent_job.await_args.args[0]
    assert executed.name == job.name
    assert executed.payload == job.payload

    # Reload from SQLite, as on restart; the failed edit must not poison startup.
    await manager.shutdown()
    await manager.start(SimpleNamespace())
    manager.scheduler.pause()
    restored = manager._get_scheduled_job(job.job_id)
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
    scheduled = manager._get_scheduled_job(job.job_id)
    with pytest.raises(CronJobSchedulingError):
        await manager.update_job(job.job_id, payload={"run_at": "not-a-date"})

    assert (await db.get_cron_job(job.job_id)).payload == job.payload
    assert manager._get_scheduled_job(job.job_id) is scheduled
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
    assert manager._get_scheduled_job(job.job_id) is None


@pytest.mark.asyncio
async def test_valid_edit_and_disable_remain_supported(cron_store):
    """Valid edits take effect, and broken legacy jobs can still be disabled."""
    db, manager = cron_store
    job = await manager.add_active_job(
        name="Reminder", cron_expression="0 9 * * *", payload={}, timezone="UTC"
    )
    updated = await manager.update_job(job.job_id, cron_expression="0 10 * * 0")
    assert updated.cron_expression == "0 10 * * 0"
    scheduled = manager._get_scheduled_job(job.job_id)
    assert scheduled.next_run_time.hour == 10
    assert scheduled.next_run_time.weekday() == 6

    # A pre-existing malformed row must not prevent the user from disabling it.
    await db.update_cron_job(job.job_id, cron_expression="invalid")
    disabled = await manager.update_job(job.job_id, enabled=False)
    assert disabled.enabled is False
    assert manager._get_scheduled_job(job.job_id) is None


@pytest.mark.parametrize("edit", ["reschedule", "recurring", "disable", "invalid", "none"])
@pytest.mark.asyncio
async def test_running_one_shot_edit_preserves_saved_job(cron_store, edit):
    """Only an unchanged one-shot definition may delete itself after execution.

    Args:
        cron_store: Real database and paused scheduler.
        edit: Edit applied while the scheduled callback is executing.
    """
    db, manager = cron_store
    job = await manager.add_active_job(
        name="Running reminder",
        cron_expression=None,
        payload={"note": "Original reminder"},
        run_once=True,
        run_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
    )
    started = asyncio.Event()
    release = asyncio.Event()

    async def run_agent(*args, **kwargs):
        started.set()
        await release.wait()

    manager._run_active_agent_job = run_agent
    scheduled = manager._get_scheduled_job(job.job_id)
    # APScheduler removes a date job when submitting its only execution.
    manager.scheduler.remove_job(scheduled.id)
    run = asyncio.create_task(scheduled.func(*scheduled.args, **scheduled.kwargs))
    try:
        await asyncio.wait_for(started.wait(), 2)
        service = CronService(SimpleNamespace(cron_manager=manager))
        if edit == "invalid":
            with pytest.raises(CronServiceError):
                await service.update_job(job.job_id, {"run_at": "invalid"})
        elif edit != "none":
            payload = {
                "reschedule": {"run_at": "2099-02-01T00:00:00+00:00"},
                "recurring": {"run_once": False, "cron_expression": "0 9 * * *"},
                "disable": {"enabled": False},
            }[edit]
            await service.update_job(job.job_id, payload)
        saved = await db.get_cron_job(job.job_id)
        new_schedule = manager._get_scheduled_job(job.job_id)
        release.set()
        await asyncio.wait_for(run, 2)

        stored = await db.get_cron_job(job.job_id)
        if edit in ("none", "invalid"):
            assert stored is None
            assert manager._get_scheduled_job(job.job_id) is None
        else:
            assert stored is not None
            assert stored.payload == saved.payload
            assert stored.run_once == saved.run_once
            assert stored.enabled == saved.enabled
            assert manager._get_scheduled_job(job.job_id) is new_schedule
            if new_schedule is not None:
                manager._run_active_agent_job = AsyncMock()
                await new_schedule.func(*new_schedule.args, **new_schedule.kwargs)
                manager._run_active_agent_job.assert_awaited_once()
                assert (await db.get_cron_job(job.job_id) is None) == stored.run_once
    finally:
        release.set()
        if not run.done():
            run.cancel()
        await asyncio.gather(run, return_exceptions=True)


@pytest.mark.asyncio
async def test_one_shot_finishing_during_edit_keeps_new_schedule(cron_store):
    """An edit awaiting its DB write must serialize with automatic deletion.

    Args:
        cron_store: Real database and paused scheduler.
    """
    db, manager = cron_store
    job = await manager.add_active_job(
        name="Original",
        cron_expression=None,
        payload={},
        run_once=True,
        run_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
    )
    started = asyncio.Event()
    release = asyncio.Event()
    agent_returning = asyncio.Event()
    original_update = db.update_cron_job

    async def run_agent(*args, **kwargs):
        started.set()
        await release.wait()
        agent_returning.set()

    async def delayed_update(job_id, **kwargs):
        if kwargs.get("name") == "Edited":
            release.set()
            await asyncio.wait_for(agent_returning.wait(), 2)
        return await original_update(job_id, **kwargs)

    manager._run_active_agent_job = run_agent
    db.update_cron_job = delayed_update
    scheduled = manager._get_scheduled_job(job.job_id)
    manager.scheduler.remove_job(scheduled.id)
    run = asyncio.create_task(scheduled.func(*scheduled.args, **scheduled.kwargs))
    try:
        await asyncio.wait_for(started.wait(), 2)
        service = CronService(SimpleNamespace(cron_manager=manager))
        await asyncio.wait_for(
            service.update_job(
                job.job_id,
                {"name": "Edited", "run_at": "2099-02-01T00:00:00+00:00"},
            ),
            3,
        )
        await asyncio.wait_for(run, 2)
        stored = await db.get_cron_job(job.job_id)
        assert stored is not None
        assert stored.name == "Edited"
        assert manager.get_next_run_time(job.job_id) == datetime(
            2099, 2, 1, tzinfo=timezone.utc
        )
    finally:
        release.set()
        if not run.done():
            run.cancel()
        await asyncio.gather(run, return_exceptions=True)
