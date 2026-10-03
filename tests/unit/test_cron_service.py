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
