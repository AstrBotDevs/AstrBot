"""Regression coverage for fixed-duration schedules and legacy Cron records."""

import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
import pytest
import pytest_asyncio
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from astrbot.core.cron.manager import CronJobManager
from astrbot.core.db.po import CronJob
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.dashboard.api import cron
from astrbot.dashboard.responses import ApiError
from astrbot.dashboard.services.cron_service import CronService, CronServiceError


@pytest_asyncio.fixture
async def interval_store(tmp_path):
    """Provide the production service, SQLite store, and a paused scheduler.

    Args:
        tmp_path: Directory for an isolated database.

    Yields:
        Database, scheduler, and dashboard service.
    """
    db = SQLiteDatabase(str(tmp_path / "cron.db"))
    await db.initialize()
    manager = CronJobManager(db)
    await manager.start(SimpleNamespace())
    manager.scheduler.pause()
    service = CronService(
        SimpleNamespace(
            cron_manager=manager,
            astrbot_config_mgr=SimpleNamespace(get_conf=lambda _: {"timezone": "UTC"}),
        )
    )
    try:
        yield db, manager, service
    finally:
        await asyncio.sleep(0)
        await manager.shutdown()
        await db.engine.dispose()


@pytest.mark.parametrize("seconds", [40 * 60, 60 * 60, 24 * 3600, 31 * 86400])
@pytest.mark.parametrize(
    "anchor",
    [
        datetime(2026, 3, 7, 14, tzinfo=timezone.utc),
        datetime(2026, 10, 31, 13, tzinfo=timezone.utc),
    ],
)
def test_interval_fire_times_and_restart_phase(seconds, anchor):
    """Fixed intervals survive calendar boundaries, DST, and missed periods.

    Args:
        seconds: Elapsed duration requested by the user.
        anchor: UTC origin immediately before a DST transition.
    """
    manager = CronJobManager(MagicMock())
    job = CronJob(
        name="Reminder",
        job_type="active_agent",
        timezone="America/New_York",
        interval_seconds=seconds,
        interval_anchor_at=anchor,
    )
    trigger = manager._build_trigger(job)
    assert isinstance(trigger, IntervalTrigger)
    first = trigger.get_next_fire_time(None, anchor)
    assert first == anchor + timedelta(seconds=seconds)
    previous = first
    for _ in range(5):
        following = trigger.get_next_fire_time(previous, previous)
        assert (following - previous).total_seconds() == seconds
        previous = following

    # A fresh trigger must skip downtime, using the persisted phase rather
    # than starting another full interval at the time of restart.
    restarted = manager._build_trigger(job)
    now = anchor + timedelta(seconds=seconds * 10 + 1)
    assert restarted.get_next_fire_time(None, now) == anchor + timedelta(
        seconds=seconds * 11
    )
    if seconds == 86400:
        local_first = first.astimezone(ZoneInfo("America/New_York"))
        assert local_first.hour != anchor.astimezone(ZoneInfo("America/New_York")).hour


@pytest.mark.asyncio
async def test_interval_creation_without_system_timezone_data(
    interval_store, monkeypatch
):
    """UTC anchoring also works on hosts without an IANA timezone database.

    Args:
        interval_store: Real database, scheduler, and service.
        monkeypatch: Fixture used to simulate missing system timezone data.
    """
    _, manager, service = interval_store
    monkeypatch.setattr(
        "astrbot.core.cron.manager.ZoneInfo",
        MagicMock(side_effect=ZoneInfoNotFoundError("No timezone data")),
    )
    created = await service.create_job({"interval_seconds": 3600})
    anchor = datetime.fromisoformat(created["interval_anchor_at"])
    assert manager.get_next_run_time(created["job_id"]) == anchor + timedelta(hours=1)


@pytest.mark.asyncio
async def test_interval_persistence_edits_and_restart(interval_store):
    """Metadata and enable/disable edits keep the phase; duration edits reset it.

    Args:
        interval_store: Real database, scheduler, and service.
    """
    db, manager, service = interval_store
    created = await service.create_job({"name": "Reminder", "interval_seconds": 2400})
    job_id = created["job_id"]
    anchor = datetime.fromisoformat(created["interval_anchor_at"])
    assert anchor.utcoffset() == timedelta(0)
    assert manager.get_next_run_time(job_id) == anchor + timedelta(seconds=2400)
    stored = await db.get_cron_job(job_id)
    assert stored.interval_anchor_at.replace(tzinfo=timezone.utc) == anchor
    assert stored.cron_expression is None

    for patch in (
        {"name": "Renamed"},
        {"note": "Edited note"},
        {"session": "test:FriendMessage:other"},
        {"timezone": "Asia/Shanghai"},
        {"enabled": False},
        {"enabled": True},
        {"interval_seconds": 2400},
    ):
        result = await service.update_job(job_id, patch)
        assert result["interval_anchor_at"] == created["interval_anchor_at"]
    assert manager.get_next_run_time(job_id) == anchor + timedelta(seconds=2400)

    await manager.shutdown()
    await manager.start(SimpleNamespace())
    manager.scheduler.pause()
    assert manager.get_next_run_time(job_id) == anchor + timedelta(seconds=2400)

    changed = await service.update_job(job_id, {"interval_seconds": 3600})
    new_anchor = datetime.fromisoformat(changed["interval_anchor_at"])
    assert new_anchor > anchor
    assert manager.get_next_run_time(job_id) == new_anchor + timedelta(hours=1)

    changed = await service.update_job(
        job_id,
        {
            "interval_seconds": None,
            "cron_expression": "0 9 * * *",
        },
    )
    assert changed["interval_anchor_at"] is None
    assert isinstance(manager.scheduler.get_job(job_id).trigger, CronTrigger)


@pytest.mark.parametrize("invalid", [0, -60, True, 60.0, 90.5, "60", 61, 2**31, 10**30])
@pytest.mark.asyncio
async def test_invalid_interval_never_changes_database_or_scheduler(
    interval_store, invalid
):
    """Reject invalid durations even when a job is created disabled.

    Args:
        interval_store: Real database, scheduler, and service.
        invalid: Duration with an invalid type, resolution, or range.
    """
    db, manager, service = interval_store
    with pytest.raises(CronServiceError):
        await service.create_job({"interval_seconds": invalid, "enabled": False})
    assert await db.list_cron_jobs() == []

    created = await service.create_job({"interval_seconds": 2400})
    job_id = created["job_id"]
    scheduled = manager.scheduler.get_job(job_id)
    with pytest.raises(CronServiceError):
        await service.update_job(
            job_id, {"interval_seconds": invalid, "name": "Rejected"}
        )
    stored = await db.get_cron_job(job_id)
    assert stored.interval_seconds == 2400
    assert stored.name == created["name"]
    assert manager.scheduler.get_job(job_id) is scheduled


@pytest.mark.parametrize(
    "conflict",
    [
        {"cron_expression": "*/40 * * * *"},
        {"run_once": True, "run_at": "2030-01-01T00:00:00+00:00"},
        {"run_at": "2030-01-01T00:00:00+00:00"},
    ],
)
@pytest.mark.asyncio
async def test_interval_rejects_conflicting_schedules(interval_store, conflict):
    """Mixed schedule types cannot silently select one trigger.

    Args:
        interval_store: Real database, scheduler, and service.
        conflict: An incompatible Cron or one-shot schedule.
    """
    db, _, service = interval_store
    with pytest.raises(CronServiceError):
        await service.create_job({"interval_seconds": 2400, **conflict})
    assert await db.list_cron_jobs() == []
    created = await service.create_job({"interval_seconds": 2400})
    with pytest.raises(CronServiceError):
        await service.update_job(created["job_id"], conflict)
    assert (await db.get_cron_job(created["job_id"])).interval_seconds == 2400


@pytest.mark.parametrize("prefix", ["/api/v1/cron", "/api/cron"])
@pytest.mark.asyncio
async def test_http_interval_round_trip_and_schedule_switches(interval_store, prefix):
    """Both API families preserve explicit nulls when switching schedule types.

    Args:
        interval_store: Real database, scheduler, and service.
        prefix: Versioned or legacy dashboard API path.
    """
    _, _, service = interval_store
    app = FastAPI()
    app.state.services = SimpleNamespace(cron=service)
    app.include_router(cron.router, prefix="/api/v1")
    app.include_router(cron.legacy_router)
    app.dependency_overrides[cron.require_system_scope] = lambda: None
    app.dependency_overrides[cron.require_dashboard_user] = lambda: "tester"
    app.add_exception_handler(
        ApiError,
        lambda _, exc: JSONResponse(
            {"message": exc.message},
            status_code=exc.status_code,
        ),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        for invalid in (True, 60.0, "60", 61, 0, 2**31):
            response = await client.post(
                f"{prefix}/jobs", json={"interval_seconds": invalid}
            )
            assert response.status_code == 422
        response = await client.post(f"{prefix}/jobs", json={"interval_seconds": 2400})
        assert response.status_code == 200
        created = response.json()["data"]
        url = f"{prefix}/jobs/{created['job_id']}"
        response = await client.patch(url, json={"name": "Renamed"})
        assert (
            response.json()["data"]["interval_anchor_at"]
            == created["interval_anchor_at"]
        )
        response = await client.patch(
            url,
            json={
                "interval_seconds": None,
                "run_once": True,
                "run_at": "2030-01-01T00:00:00+00:00",
            },
        )
        assert response.status_code == 200
        assert response.json()["data"]["interval_seconds"] is None
        response = await client.patch(
            url,
            json={
                "run_once": False,
                "run_at": "",
                "interval_seconds": 86400,
            },
        )
        assert response.status_code == 200
        assert response.json()["data"]["interval_seconds"] == 86400
        response = await client.patch(
            url,
            json={
                "interval_seconds": None,
                "cron_expression": "*/40 * * * *",
            },
        )
        assert response.status_code == 200
        assert response.json()["data"]["interval_anchor_at"] is None
        response = await client.patch(
            url,
            json={
                "cron_expression": "",
                "interval_seconds": 2400,
            },
        )
        assert response.status_code == 200
        listed = (await client.get(f"{prefix}/jobs")).json()["data"]
        assert listed[0]["interval_seconds"] == 2400


@pytest.mark.asyncio
async def test_legacy_database_migration_preserves_cron(tmp_path):
    """Add nullable fields idempotently without guessing historical intervals.

    Args:
        tmp_path: Directory for a database using the previous schema.
    """
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE cron_jobs (
                id INTEGER PRIMARY KEY, job_id VARCHAR(64) NOT NULL UNIQUE,
                name VARCHAR(255) NOT NULL, description TEXT,
                job_type VARCHAR(32) NOT NULL, cron_expression VARCHAR(255),
                timezone VARCHAR(64), payload JSON, enabled BOOLEAN,
                persistent BOOLEAN, run_once BOOLEAN, status VARCHAR(32),
                last_run_at DATETIME, next_run_time DATETIME, last_error TEXT,
                created_at DATETIME, updated_at DATETIME
            );
            INSERT INTO cron_jobs VALUES (
                1, 'legacy', 'Reminder', NULL, 'active_agent', '*/40 * * * *',
                'UTC', '{}', 1, 1, 0, 'scheduled', NULL, NULL, NULL,
                '2026-10-01 00:00:00', '2026-10-01 00:00:00'
            );
        """)
    db = SQLiteDatabase(str(path))
    try:
        await db.initialize()
        await db.initialize()
        job = await db.get_cron_job("legacy")
        assert job.cron_expression == "*/40 * * * *"
        assert job.interval_seconds is None
        assert job.interval_anchor_at is None
        trigger = CronJobManager(db)._build_trigger(job)
        assert isinstance(trigger, CronTrigger)
        first = trigger.get_next_fire_time(
            None, datetime(2026, 10, 3, tzinfo=timezone.utc)
        )
        second = trigger.get_next_fire_time(first, first)
        third = trigger.get_next_fire_time(second, second)
        assert (second - first).total_seconds() == 2400
        assert (third - second).total_seconds() == 1200
    finally:
        await db.engine.dispose()
