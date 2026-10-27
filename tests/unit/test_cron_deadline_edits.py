"""Verify rejected cron edits preserve durable jobs and their live schedules."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from astrbot.core.cron.manager import CronJobManager, CronJobSchedulingError
from astrbot.core.db.sqlite import SQLiteDatabase


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


@pytest.mark.asyncio
async def test_note_edit_rejects_expired_effective_deadline(cron_store):
    """An omitted run_at must not let an expired one-shot edit succeed.

    Args:
        cron_store: Real SQLite store and paused scheduler.
    """
    from datetime import timedelta

    db, manager = cron_store
    old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    job = await db.create_cron_job(
        name="Expired",
        job_type="active_agent",
        cron_expression=None,
        payload={"run_at": old, "note": "old"},
        run_once=True,
    )
    with pytest.raises(CronJobSchedulingError):
        await manager.update_job(job.job_id, payload_patch={"note": "new"})
    assert (await db.get_cron_job(job.job_id)).payload["note"] == "old"


@pytest.mark.asyncio
async def test_overlapping_payload_edits_keep_latest_deadline(cron_store):
    """Interleaved updates must merge with the serialized latest DB payload.

    Args:
        cron_store: Real SQLite store and paused scheduler.
    """
    import asyncio
    from datetime import timedelta

    db, manager = cron_store
    future = datetime.now(timezone.utc) + timedelta(days=1)
    job = await manager.add_active_job(
        name="Concurrent",
        cron_expression=None,
        run_once=True,
        run_at=future,
        payload={"note": "old", "session": "test:FriendMessage:user"},
    )
    entered, release = asyncio.Event(), asyncio.Event()
    original_update = db.update_cron_job

    async def slow_update(job_id, **kwargs):
        if (
            kwargs.get("payload", {}).get("run_at")
            == (future + timedelta(days=1)).isoformat()
        ):
            entered.set()
            await release.wait()
        return await original_update(job_id, **kwargs)

    db.update_cron_job = slow_update
    deadline_edit = asyncio.create_task(
        manager.update_job(
            job.job_id,
            payload_patch={"run_at": (future + timedelta(days=1)).isoformat()},
        )
    )
    await asyncio.wait_for(entered.wait(), timeout=3)
    note_edit = asyncio.create_task(
        manager.update_job(job.job_id, payload_patch={"note": "new"})
    )
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(deadline_edit, note_edit)
    stored = await db.get_cron_job(job.job_id)
    assert stored.payload == {
        "run_at": (future + timedelta(days=1)).isoformat(),
        "note": "new",
        "session": "test:FriendMessage:user",
    }
    assert manager.scheduler.get_job(job.job_id).next_run_time == future + timedelta(
        days=1
    )


@pytest.mark.asyncio
async def test_database_delay_rejects_expired_create(cron_store, monkeypatch):
    """A DB await cannot turn an accepted deadline into a silent misfire.

    Args:
        cron_store: Real SQLite store and paused scheduler.
        monkeypatch: Restore the manager clock and delayed write after testing.
    """
    from datetime import timedelta
    from astrbot.core.cron import manager as manager_module

    db, manager = cron_store
    now = datetime.now(timezone.utc)
    clock = [now]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0].astimezone(tz)

    original_create = db.create_cron_job
    created = []

    async def slow_create(**kwargs):
        job = await original_create(**kwargs)
        created.append(job)
        clock[0] += timedelta(minutes=10)
        return job

    monkeypatch.setattr(manager_module, "datetime", Clock)
    monkeypatch.setattr(db, "create_cron_job", slow_create)
    with pytest.raises(CronJobSchedulingError):
        await manager.add_active_job(
            name="Late",
            cron_expression=None,
            run_once=True,
            run_at=now + timedelta(seconds=30),
            payload={},
        )
    assert manager.scheduler.get_job(created[0].job_id) is None


@pytest.mark.asyncio
async def test_database_delay_rejects_expired_update(cron_store, monkeypatch):
    """Keep the existing schedule when an update is too late after its DB await.

    Args:
        cron_store: Real SQLite store and paused scheduler.
        monkeypatch: Restore the manager clock and delayed write after testing.
    """
    from datetime import timedelta
    from astrbot.core.cron import manager as manager_module

    db, manager = cron_store
    now = datetime.now(timezone.utc)
    job = await manager.add_active_job(
        name="Existing",
        cron_expression=None,
        run_once=True,
        run_at=now + timedelta(days=1),
        payload={"note": "old"},
    )
    clock = [now]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0].astimezone(tz)

    original_update = db.update_cron_job

    async def slow_update(job_id, **kwargs):
        result = await original_update(job_id, **kwargs)
        if "payload" in kwargs:
            clock[0] += timedelta(minutes=10)
        return result

    monkeypatch.setattr(manager_module, "datetime", Clock)
    monkeypatch.setattr(db, "update_cron_job", slow_update)
    with pytest.raises(CronJobSchedulingError):
        await manager.update_job(
            job.job_id,
            payload_patch={"run_at": (now + timedelta(seconds=30)).isoformat()},
        )
    assert manager.scheduler.get_job(job.job_id).next_run_time == now + timedelta(
        days=1
    )
    assert (await db.get_cron_job(job.job_id)).payload == job.payload


@pytest.mark.asyncio
async def test_tool_note_edit_rejects_expired_stored_deadline(cron_store):
    """Exercise the public tool with run_at omitted, using real SQLite storage.

    Args:
        cron_store: Real SQLite store and paused scheduler.
    """
    from datetime import timedelta

    from astrbot.core.platform.message_type import MessageType
    from astrbot.core.tools.cron_tools import FutureTaskTool

    db, manager = cron_store
    old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    job = await db.create_cron_job(
        name="Expired",
        job_type="active_agent",
        cron_expression=None,
        payload={
            "run_at": old,
            "note": "old",
            "session": "test:FriendMessage:user",
            "sender_id": "user",
        },
        run_once=True,
    )
    context = SimpleNamespace(
        context=SimpleNamespace(
            context=SimpleNamespace(cron_manager=manager),
            event=SimpleNamespace(
                unified_msg_origin="test:FriendMessage:user",
                get_sender_id=lambda: "user",
                get_message_type=lambda: MessageType.FRIEND_MESSAGE,
            ),
        )
    )
    result = await FutureTaskTool().call(
        context, action="edit", job_id=job.job_id, note="new"
    )
    assert result.startswith("error:")
    assert (await db.get_cron_job(job.job_id)).payload["note"] == "old"
    assert manager.scheduler.get_job(job.job_id) is None


@pytest.mark.asyncio
async def test_tool_stale_read_cannot_restore_prior_deadline(cron_store, monkeypatch):
    """An overlapping note edit must preserve another tool edit's new deadline.

    Args:
        cron_store: Real SQLite store and paused scheduler.
        monkeypatch: Restore the DB getter after the controlled stale read.
    """
    import asyncio
    from datetime import timedelta

    from astrbot.core.platform.message_type import MessageType
    from astrbot.core.tools.cron_tools import FutureTaskTool

    db, manager = cron_store
    future = datetime.now(timezone.utc) + timedelta(days=1)
    job = await manager.add_active_job(
        name="Concurrent",
        cron_expression=None,
        run_once=True,
        run_at=future,
        payload={
            "note": "old",
            "session": "test:FriendMessage:user",
            "sender_id": "user",
        },
    )
    context = SimpleNamespace(
        context=SimpleNamespace(
            context=SimpleNamespace(cron_manager=manager),
            event=SimpleNamespace(
                unified_msg_origin="test:FriendMessage:user",
                get_sender_id=lambda: "user",
                get_message_type=lambda: MessageType.FRIEND_MESSAGE,
            ),
        )
    )
    entered, release = asyncio.Event(), asyncio.Event()
    original_get = db.get_cron_job
    first = [True]

    async def stale_read(job_id):
        snapshot = await original_get(job_id)
        if first[0]:
            first[0] = False
            entered.set()
            await release.wait()
        return snapshot

    monkeypatch.setattr(db, "get_cron_job", stale_read)
    note = asyncio.create_task(
        FutureTaskTool().call(context, action="edit", job_id=job.job_id, note="new")
    )
    await asyncio.wait_for(entered.wait(), timeout=3)
    moved = await FutureTaskTool().call(
        context,
        action="edit",
        job_id=job.job_id,
        run_at=(future + timedelta(days=1)).isoformat(),
    )
    release.set()
    assert moved.startswith("Updated")
    assert (await note).startswith("Updated")
    stored = await db.get_cron_job(job.job_id)
    assert stored.payload["run_at"] == (future + timedelta(days=1)).isoformat()
    assert stored.payload["note"] == "new"
