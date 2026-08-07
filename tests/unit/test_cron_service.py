from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.dashboard.services.cron_service import CronService


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "payload_timezone",
        "config_timezone",
        "session",
        "expected_timezone",
        "should_read_config",
    ),
    [
        (
            "America/New_York",
            "Asia/Shanghai",
            "test:private:session",
            "America/New_York",
            False,
        ),
        ("", "Asia/Shanghai", "test:private:session", "Asia/Shanghai", True),
        (None, "UTC", "", "UTC", True),
        (None, "", "", None, True),
    ],
)
async def test_create_job_resolves_default_timezone(
    payload_timezone: str | None,
    config_timezone: str,
    session: str,
    expected_timezone: str | None,
    should_read_config: bool,
) -> None:
    job = SimpleNamespace(
        job_id="job-1",
        name="test-job",
        payload={"note": "test"},
        run_once=False,
    )
    cron_manager = SimpleNamespace(add_active_job=AsyncMock(return_value=job))
    config_manager = SimpleNamespace(
        get_conf=MagicMock(return_value={"timezone": config_timezone}),
    )
    service = CronService(cron_manager, config_manager)

    payload = {
        "name": "test-job",
        "note": "test",
        "cron_expression": "0 9 * * *",
        "session": session,
        "timezone": payload_timezone,
    }

    await service.create_job(payload)

    assert cron_manager.add_active_job.await_args.kwargs["timezone"] == (
        expected_timezone
    )
    if should_read_config:
        config_manager.get_conf.assert_called_once_with(session or None)
    else:
        config_manager.get_conf.assert_not_called()
