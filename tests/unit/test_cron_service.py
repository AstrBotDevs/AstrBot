from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.dashboard.services.cron_service import CronService


@pytest.mark.parametrize(
    (
        "include_timezone",
        "payload_timezone",
        "config_timezone",
        "session",
        "expected_timezone",
        "should_read_config",
    ),
    [
        (
            True,
            "America/New_York",
            "Asia/Shanghai",
            "test:private:session",
            "America/New_York",
            False,
        ),
        (
            True,
            "",
            "Asia/Shanghai",
            "test:private:session",
            "Asia/Shanghai",
            True,
        ),
        (
            False,
            None,
            "Asia/Shanghai",
            "test:private:session",
            "Asia/Shanghai",
            True,
        ),
        (False, None, "UTC", "", "UTC", True),
        (False, None, "", "", None, True),
    ],
)
@pytest.mark.asyncio
async def test_create_job_resolves_default_timezone(
    include_timezone: bool,
    payload_timezone: str | None,
    config_timezone: str,
    session: str,
    expected_timezone: str | None,
    should_read_config: bool,
) -> None:
    """Verify that new cron jobs inherit the configured timezone by default.

    Args:
        include_timezone: Whether the request includes the timezone field.
        payload_timezone: Timezone value supplied by the request.
        config_timezone: Timezone returned by the applicable AstrBot config.
        session: Target session supplied by the request.
        expected_timezone: Timezone expected by the cron manager.
        should_read_config: Whether configuration lookup should occur.
    """
    job = SimpleNamespace(
        job_id="job-1",
        name="test-job",
        payload={"note": "test"},
        run_once=False,
    )
    cron_manager = SimpleNamespace(
        add_active_job=AsyncMock(return_value=job),
    )
    config_manager = SimpleNamespace(
        get_conf=MagicMock(return_value={"timezone": config_timezone}),
    )
    service = CronService(
        SimpleNamespace(
            cron_manager=cron_manager,
            astrbot_config_mgr=config_manager,
        )
    )
    payload = {
        "name": "test-job",
        "note": "test",
        "cron_expression": "0 9 * * *",
        "session": session,
    }
    if include_timezone:
        payload["timezone"] = payload_timezone

    await service.create_job(payload)

    call_kwargs = cron_manager.add_active_job.await_args.kwargs
    assert call_kwargs["timezone"] == expected_timezone
    if should_read_config:
        config_manager.get_conf.assert_called_once_with(session or None)
    else:
        config_manager.get_conf.assert_not_called()


def _make_service(cron_manager: SimpleNamespace) -> CronService:
    """Build a CronService around the given mocked cron manager."""
    return CronService(
        SimpleNamespace(
            cron_manager=cron_manager,
            astrbot_config_mgr=SimpleNamespace(
                get_conf=MagicMock(return_value={}),
            ),
        )
    )


def _active_job(payload: dict) -> SimpleNamespace:
    """Build a persisted active_agent job stand-in for update tests."""
    return SimpleNamespace(
        job_id="job-1",
        name="test-job",
        job_type="active_agent",
        cron_expression="0 9 * * *",
        payload=dict(payload),
        run_once=False,
        enabled=True,
    )


@pytest.mark.asyncio
async def test_create_job_with_multiple_delivery_sessions() -> None:
    """Multiple delivery sessions are normalized and stored in the payload."""
    job = SimpleNamespace(
        job_id="job-1",
        name="test-job",
        payload={"note": "test"},
        run_once=False,
    )
    cron_manager = SimpleNamespace(add_active_job=AsyncMock(return_value=job))
    service = _make_service(cron_manager)

    await service.create_job(
        {
            "name": "test-job",
            "note": "test",
            "cron_expression": "0 9 * * *",
            "sessions": [
                "test:group:1",
                " test:group:2 ",
                "test:group:1",
                "test:group:3",
            ],
        }
    )

    call_kwargs = cron_manager.add_active_job.await_args.kwargs
    assert call_kwargs["payload"]["sessions"] == [
        "test:group:1",
        "test:group:2",
        "test:group:3",
    ]
    assert call_kwargs["payload"]["session"] == "test:group:1"


@pytest.mark.asyncio
async def test_create_job_backfills_sessions_from_single_session() -> None:
    """A lone session value is promoted to a one-entry sessions list."""
    job = SimpleNamespace(
        job_id="job-1",
        name="test-job",
        payload={"note": "test"},
        run_once=False,
    )
    cron_manager = SimpleNamespace(add_active_job=AsyncMock(return_value=job))
    service = _make_service(cron_manager)

    await service.create_job(
        {
            "name": "test-job",
            "note": "test",
            "cron_expression": "0 9 * * *",
            "session": "test:private:1",
        }
    )

    call_kwargs = cron_manager.add_active_job.await_args.kwargs
    assert call_kwargs["payload"]["sessions"] == ["test:private:1"]
    assert call_kwargs["payload"]["session"] == "test:private:1"


@pytest.mark.asyncio
async def test_create_job_caps_delivery_sessions() -> None:
    """Delivery sessions are capped to keep one schedule bounded."""
    job = SimpleNamespace(
        job_id="job-1",
        name="test-job",
        payload={"note": "test"},
        run_once=False,
    )
    cron_manager = SimpleNamespace(add_active_job=AsyncMock(return_value=job))
    service = _make_service(cron_manager)

    await service.create_job(
        {
            "name": "test-job",
            "note": "test",
            "cron_expression": "0 9 * * *",
            "sessions": [f"test:group:{i}" for i in range(30)],
        }
    )

    call_kwargs = cron_manager.add_active_job.await_args.kwargs
    assert len(call_kwargs["payload"]["sessions"]) == 20


@pytest.mark.asyncio
async def test_update_job_replaces_delivery_sessions() -> None:
    """Updating sessions rewrites both the list and the primary session."""
    job = _active_job({"session": "test:group:1", "note": "old"})
    updated = _active_job(
        {"session": "test:group:2", "sessions": ["test:group:2", "test:group:3"]}
    )
    cron_manager = SimpleNamespace(
        db=SimpleNamespace(get_cron_job=AsyncMock(return_value=job)),
        update_job=AsyncMock(return_value=updated),
    )
    service = _make_service(cron_manager)

    await service.update_job("job-1", {"sessions": ["test:group:2", "test:group:3"]})

    call_kwargs = cron_manager.update_job.await_args.kwargs
    assert call_kwargs["payload"]["sessions"] == ["test:group:2", "test:group:3"]
    assert call_kwargs["payload"]["session"] == "test:group:2"


@pytest.mark.asyncio
async def test_update_job_clears_delivery_sessions() -> None:
    """An empty sessions list removes the delivery target entirely."""
    job = _active_job(
        {"session": "test:group:1", "sessions": ["test:group:1"], "note": "old"}
    )
    updated = _active_job({"note": "old"})
    cron_manager = SimpleNamespace(
        db=SimpleNamespace(get_cron_job=AsyncMock(return_value=job)),
        update_job=AsyncMock(return_value=updated),
    )
    service = _make_service(cron_manager)

    await service.update_job("job-1", {"sessions": []})

    call_kwargs = cron_manager.update_job.await_args.kwargs
    assert "sessions" not in call_kwargs["payload"]
    assert "session" not in call_kwargs["payload"]


@pytest.mark.parametrize(
    ("payload", "expected_sessions"),
    [
        (
            {"sessions": ["test:group:1", "test:group:2"]},
            ["test:group:1", "test:group:2"],
        ),
        ({"session": "test:group:1"}, ["test:group:1"]),
        ({}, []),
    ],
    ids=["sessions-list", "legacy-session", "none"],
)
def test_serialize_job_exposes_delivery_sessions(
    payload: dict, expected_sessions: list[str]
) -> None:
    """Serialization always exposes a sessions list, legacy or new."""
    job = SimpleNamespace(
        job_id="job-1",
        name="test-job",
        job_type="active_agent",
        payload=payload,
        run_once=False,
    )

    data = CronService.serialize_job(job)

    assert data["sessions"] == expected_sessions
