"""Verify cron recovery across WSL clock pauses and process restarts."""

import asyncio
import os
import signal
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_MISSED

from astrbot.core.cron.manager import CronJobManager
from astrbot.core.db.sqlite import SQLiteDatabase


@pytest_asyncio.fixture
async def cron_store(tmp_path):
    """Provide an isolated SQLite store without sending external messages."""
    db = SQLiteDatabase(str(tmp_path / "cron.db"))
    await db.initialize()
    manager = CronJobManager(db)
    manager._run_active_agent_job = AsyncMock()
    try:
        yield db, manager
    finally:
        await manager.shutdown()
        await db.engine.dispose()


def test_long_wait_does_not_poll_system_time():
    """Normal operation waits for the next deadline without extra checks."""
    scheduler = CronJobManager(MagicMock()).scheduler
    scheduler._eventloop = MagicMock()
    scheduler._start_timer(20 * 60 * 60)

    assert scheduler._eventloop.call_later.call_args.args[0] == 20 * 60 * 60
    scheduler._start_timer(None)
    scheduler._eventloop.call_later.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.skipif(not hasattr(signal, "SIGCONT"), reason="Requires POSIX signals")
async def test_resume_signal_executes_overdue_one_shot_once(cron_store, monkeypatch):
    """Host notifications recover an overdue job without polling or duplicates."""
    monkeypatch.setenv("ASTRBOT_CRON_RESUME_SIGNAL", "1")
    db, manager = cron_store
    await manager.start(SimpleNamespace())
    deadline = datetime.now(timezone.utc) + timedelta(hours=2)
    job = await manager.add_active_job(
        name="Resume reminder",
        cron_expression=None,
        payload={"note": "Send a reminder"},
        run_once=True,
        run_at=deadline,
    )
    # Let initial scheduler wakeups finish before simulating suspended loop time.
    await asyncio.sleep(0.05)
    assert manager._resume_loop is asyncio.get_running_loop()
    finished = asyncio.Event()
    manager.scheduler.add_listener(lambda event: finished.set(), EVENT_JOB_EXECUTED)
    resumed_at = deadline + timedelta(hours=1)

    class ResumedDateTime(datetime):
        """Model advancing system time without changing asyncio loop time."""

        @classmethod
        def now(cls, tz=None):
            """Return the simulated time after resume.

            Args:
                tz: Requested timezone, or None for a naive local datetime.
            """
            if tz is None:
                return resumed_at.replace(tzinfo=None)
            return resumed_at.astimezone(tz)

    with (
        patch("apscheduler.schedulers.base.datetime", ResumedDateTime),
        patch("apscheduler.executors.base.datetime", ResumedDateTime),
    ):
        os.kill(os.getpid(), signal.SIGCONT)
        await asyncio.wait_for(finished.wait(), timeout=3)
        os.kill(os.getpid(), signal.SIGCONT)
        await asyncio.sleep(0.05)

    assert manager._run_active_agent_job.await_count == 1
    assert await db.get_cron_job(job.job_id) is None
    await manager.shutdown()
    assert manager._resume_loop is None
    assert signal.getsignal(signal.SIGCONT) == signal.SIG_DFL


@pytest.mark.asyncio
async def test_resume_signal_is_opt_in(cron_store, monkeypatch):
    """Other deployments must not install process-wide signal handlers."""
    monkeypatch.delenv("ASTRBOT_CRON_RESUME_SIGNAL", raising=False)
    _, manager = cron_store

    await manager.start(SimpleNamespace())

    assert manager._resume_loop is None


@pytest.mark.parametrize("overdue", [timedelta(hours=4), timedelta(days=3)])
@pytest.mark.asyncio
async def test_restart_coalesces_missed_runs_and_does_not_replay(cron_store, overdue):
    """Restart recovers one recent run and persists the following deadline."""
    db, manager = cron_store
    now = datetime.now(timezone.utc)
    saved_next = (now - overdue).replace(second=0, microsecond=0)
    job = await db.create_cron_job(
        name="Persisted reminder",
        job_type="active_agent",
        cron_expression="* * * * *",
        timezone="Asia/Shanghai",
        payload={"note": "Send a reminder"},
        persistent=True,
    )
    await db.update_cron_job(
        job.job_id,
        next_run_time=saved_next,
        last_run_at=saved_next - timedelta(days=1),
        status="completed",
    )
    finished = asyncio.Event()
    manager.scheduler.add_listener(lambda event: finished.set(), EVENT_JOB_EXECUTED)

    await manager.start(SimpleNamespace())
    await asyncio.wait_for(finished.wait(), timeout=3)
    saved = await db.get_cron_job(job.job_id)

    assert manager._run_active_agent_job.await_count == 1
    assert saved.status == "completed"
    assert saved.last_run_at.replace(tzinfo=timezone.utc) >= now
    assert saved.next_run_time.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc)

    await manager.shutdown()
    await manager.start(SimpleNamespace())
    manager.scheduler.pause()
    assert manager.scheduler.get_job(job.job_id).next_run_time > datetime.now(
        timezone.utc
    )
    assert manager._run_active_agent_job.await_count == 1


@pytest.mark.asyncio
async def test_already_executed_deadline_is_not_recovered(cron_store):
    """A stale saved deadline must not repeat a run recorded as executed."""
    db, manager = cron_store
    now = datetime.now(timezone.utc)
    job = await db.create_cron_job(
        name="Already delivered",
        job_type="active_agent",
        cron_expression="* * * * *",
        payload={},
        persistent=True,
    )
    await db.update_cron_job(
        job.job_id,
        next_run_time=now - timedelta(minutes=5),
        last_run_at=now,
    )

    await manager.start(SimpleNamespace())
    manager.scheduler.pause()

    assert manager.scheduler.get_job(job.job_id).next_run_time > now
    manager._run_active_agent_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_expired_one_shot_is_not_delivered(cron_store):
    """A one-shot older than the recovery window must not be sent."""
    db, manager = cron_store
    deadline = datetime.now(timezone.utc) - timedelta(days=2)
    await db.create_cron_job(
        name="Expired reminder",
        job_type="active_agent",
        cron_expression=None,
        payload={"run_at": deadline.isoformat()},
        persistent=True,
        run_once=True,
    )
    missed = asyncio.Event()
    manager.scheduler.add_listener(lambda event: missed.set(), EVENT_JOB_MISSED)

    await manager.start(SimpleNamespace())
    await asyncio.wait_for(missed.wait(), timeout=3)

    manager._run_active_agent_job.assert_not_awaited()
