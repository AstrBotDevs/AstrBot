from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.dashboard.services.cron_service import CronService, CronServiceError


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


@pytest.mark.asyncio
async def test_dashboard_cron_delivery_sessions_round_trip() -> None:
    """Preserve ordered targets on create, then honor single-target API edits."""
    first = "lark:GroupMessage:first"
    second = "lark:GroupMessage:second"
    job = SimpleNamespace(
        job_id="job",
        job_type="active_agent",
        run_once=False,
        cron_expression="0 9 * * *",
        description="Report",
    )

    async def apply_payload(*args, payload, **kwargs):
        job.payload = payload
        return job

    manager = SimpleNamespace(
        add_active_job=AsyncMock(side_effect=apply_payload),
        update_job=AsyncMock(side_effect=apply_payload),
        db=SimpleNamespace(get_cron_job=AsyncMock(return_value=job)),
    )
    get_conf = MagicMock(return_value={"timezone": "Asia/Shanghai"})
    service = CronService(
        SimpleNamespace(
            cron_manager=manager, astrbot_config_mgr=SimpleNamespace(get_conf=get_conf)
        )
    )
    data = await service.create_job(
        {"cron_expression": "0 9 * * *", "sessions": [first, second, first]}
    )
    assert data["sessions"] == [first, second]
    assert job.payload["session"] == first
    get_conf.assert_called_once_with(first)

    data = await service.update_job("job", {"note": "Updated report"})
    assert data["sessions"] == [first, second]
    data = await service.update_job("job", {"session": second})
    assert data["sessions"] == [second]
    assert job.payload["session"] == second
    assert "sessions" not in job.payload
    data = await service.update_job("job", {"sessions": []})
    assert data["sessions"] == []

    with pytest.raises(CronServiceError, match="Invalid delivery session"):
        await service.update_job("job", {"sessions": [first, "invalid"]})
    assert manager.update_job.await_count == 3
