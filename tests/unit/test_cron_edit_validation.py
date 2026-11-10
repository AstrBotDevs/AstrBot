"""Verify cron edits preserve durable jobs and their live schedules."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from astrbot.core.cron.manager import CronJobManager, CronJobSchedulingError
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.dashboard.services.cron_service import CronService, CronServiceError


def scheduled_job(manager, job_id):
    """Find the live scheduler entry for a logical task ID.

    Args:
        manager: Cron manager under test.
        job_id: Logical task ID passed to the callback.

    Returns:
        The matching scheduler entry, or None.
    """
    return next(
        (job for job in manager.scheduler.get_jobs() if job.args == (job_id,)), None
    )


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
async def test_invalid_dashboard_edit_preserves_job_and_schedule(
    cron_store, expression
):
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
    scheduled = scheduled_job(manager, job.job_id)
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
    assert scheduled_job(manager, job.job_id) is scheduled
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
    restored = scheduled_job(manager, job.job_id)
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
    scheduled = scheduled_job(manager, job.job_id)
    with pytest.raises(CronJobSchedulingError):
        await manager.update_job(job.job_id, payload={"run_at": "not-a-date"})

    assert (await db.get_cron_job(job.job_id)).payload == job.payload
    assert scheduled_job(manager, job.job_id) is scheduled
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
    assert scheduled_job(manager, job.job_id) is None


@pytest.mark.asyncio
async def test_valid_edit_and_disable_remain_supported(cron_store):
    """Valid edits take effect, and broken legacy jobs can still be disabled."""
    db, manager = cron_store
    job = await manager.add_active_job(
        name="Reminder", cron_expression="0 9 * * *", payload={}, timezone="UTC"
    )
    updated = await manager.update_job(job.job_id, cron_expression="0 10 * * 0")
    assert updated.cron_expression == "0 10 * * 0"
    scheduled = scheduled_job(manager, job.job_id)
    assert scheduled.next_run_time.hour == 10
    assert scheduled.next_run_time.weekday() == 6

    # A pre-existing malformed row must not prevent the user from disabling it.
    await db.update_cron_job(job.job_id, cron_expression="invalid")
    disabled = await manager.update_job(job.job_id, enabled=False)
    assert disabled.enabled is False
    assert scheduled_job(manager, job.job_id) is None


@pytest.mark.parametrize(
    "edit", ["reschedule", "recurring", "disable", "rename", "invalid", "none"]
)
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
    scheduled = scheduled_job(manager, job.job_id)
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
                "rename": {"name": "Renamed reminder"},
            }[edit]
            await service.update_job(job.job_id, payload)
        saved = await db.get_cron_job(job.job_id)
        new_schedule = scheduled_job(manager, job.job_id)
        if edit == "rename":
            assert saved.name == "Renamed reminder"
            assert new_schedule is None
        release.set()
        await asyncio.wait_for(run, 2)

        stored = await db.get_cron_job(job.job_id)
        if edit in ("none", "invalid", "rename"):
            assert stored is None
            assert scheduled_job(manager, job.job_id) is None
        else:
            assert stored is not None
            assert stored.payload == saved.payload
            assert stored.run_once == saved.run_once
            assert stored.enabled == saved.enabled
            assert scheduled_job(manager, job.job_id) is new_schedule
            if edit == "disable":
                assert stored.status == "dispatched"
                assert stored.next_run_time is None
            else:
                assert new_schedule is not None
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
    scheduled = scheduled_job(manager, job.job_id)
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


@pytest.mark.asyncio
async def test_slow_edit_does_not_block_other_job(cron_store, monkeypatch):
    """An edit waiting for storage must leave unrelated callbacks free to run.

    Args:
        cron_store: Real database and paused scheduler.
        monkeypatch: Fixture that restores the database method.
    """
    db, manager = cron_store
    edited = await manager.add_active_job(
        name="Edited", cron_expression="0 9 * * *", payload={}
    )
    other = await manager.add_active_job(
        name="Other", cron_expression="0 10 * * *", payload={}
    )
    blocked = asyncio.Event()
    release = asyncio.Event()
    original_update = db.update_cron_job

    async def slow_update(job_id, **kwargs):
        if job_id == edited.job_id and kwargs.get("name") == "Renamed":
            blocked.set()
            await release.wait()
        return await original_update(job_id, **kwargs)

    monkeypatch.setattr(db, "update_cron_job", slow_update)
    agent = AsyncMock()
    monkeypatch.setattr(manager, "_run_active_agent_job", agent)
    update = asyncio.create_task(manager.update_job(edited.job_id, name="Renamed"))
    try:
        await asyncio.wait_for(blocked.wait(), 2)
        scheduled = scheduled_job(manager, other.job_id)
        await asyncio.wait_for(scheduled.func(*scheduled.args, **scheduled.kwargs), 2)
        assert agent.await_args.args[0].job_id == other.job_id
    finally:
        release.set()
        await asyncio.wait_for(update, 2)


@pytest.mark.asyncio
async def test_failed_schedule_install_preserves_job(cron_store, monkeypatch):
    """Failed replacement installation preserves the definition and live schedule.

    Args:
        cron_store: Real database and paused scheduler.
        monkeypatch: Restores the scheduler method.
    """
    db, manager = cron_store
    job = await manager.add_active_job(
        name="Original",
        cron_expression=None,
        payload={"note": "Original"},
        run_once=True,
        run_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
    )
    scheduled = scheduled_job(manager, job.job_id)

    def reject(*args, **kwargs):
        raise RuntimeError("Scheduler installation failed")

    monkeypatch.setattr(manager.scheduler, "add_job", reject)
    service = CronService(SimpleNamespace(cron_manager=manager))
    edit = {
        "name": "Replacement",
        "cron_expression": "0 10 * * *",
        "run_once": False,
    }
    with pytest.raises(CronServiceError, match="Scheduler installation failed"):
        await service.update_job(job.job_id, edit)

    stored = await db.get_cron_job(job.job_id)
    assert scheduled_job(manager, job.job_id) is scheduled
    assert stored.name == job.name
    assert stored.payload == job.payload
    assert stored.cron_expression == job.cron_expression
    assert stored.run_once == job.run_once
    agent = AsyncMock()
    monkeypatch.setattr(manager, "_run_active_agent_job", agent)
    await scheduled.func(*scheduled.args, **scheduled.kwargs)
    assert agent.await_args.args[0].name == "Original"


@pytest.mark.asyncio
async def test_concurrent_dashboard_edits_preserve_both_changes(
    cron_store, monkeypatch
):
    """Independent payload edits merge with the latest durable definition.

    Args:
        cron_store: Real database and paused scheduler.
        monkeypatch: Restores the manager method.
    """
    db, manager = cron_store
    job = await manager.add_active_job(
        name="Reminder",
        cron_expression="0 9 * * *",
        payload={"note": "Old", "session": "test:FriendMessage:old"},
    )
    service = CronService(SimpleNamespace(cron_manager=manager))
    original_update = manager.update_job
    first_ready = asyncio.Event()
    release_first = asyncio.Event()

    async def overlap(job_id, **kwargs):
        if not first_ready.is_set():
            first_ready.set()
            await release_first.wait()
        return await original_update(job_id, **kwargs)

    monkeypatch.setattr(manager, "update_job", overlap)
    first = asyncio.create_task(service.update_job(job.job_id, {"note": "New"}))
    try:
        await asyncio.wait_for(first_ready.wait(), 2)
        await asyncio.wait_for(
            service.update_job(job.job_id, {"session": "test:FriendMessage:new"}), 2
        )
    finally:
        release_first.set()
        await asyncio.wait_for(first, 2)
    stored = await db.get_cron_job(job.job_id)
    assert stored.payload["note"] == "New"
    assert stored.payload["session"] == "test:FriendMessage:new"
