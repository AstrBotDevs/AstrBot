from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.dashboard.services.cron_service import CronService


@pytest.mark.parametrize(
    (
        "timezone_fields",
        "config_timezone",
        "session",
        "expected_timezone",
    ),
    [
        (
            {"timezone": "America/New_York"},
            "Asia/Shanghai",
            "test:private:session",
            "America/New_York",
        ),
        (
            {"timezone": ""},
            "Etc/GMT-2",
            "test:FriendMessage:user",
            "Etc/GMT-2",
        ),
        (
            {},
            "Etc/GMT-2",
            "test:FriendMessage:user",
            "Etc/GMT-2",
        ),
        ({}, "UTC", "", "UTC"),
        ({}, "", "", None),
    ],
)
@pytest.mark.asyncio
async def test_create_job_resolves_default_timezone(
    timezone_fields: dict[str, str],
    config_timezone: str,
    session: str,
    expected_timezone: str | None,
) -> None:
    """Verify that new cron jobs inherit the configured timezone by default.

    Args:
        timezone_fields: Explicit, empty, or omitted timezone request field.
        config_timezone: System timezone, independent of the session config.
        session: Target session supplied by the request.
        expected_timezone: Timezone expected by the cron manager.
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
        get_conf=lambda umo: {
            "timezone": config_timezone if umo is None else "Asia/Shanghai"
        },
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
        **timezone_fields,
    }

    await service.create_job(payload)

    call_kwargs = cron_manager.add_active_job.await_args.kwargs
    assert call_kwargs["timezone"] == expected_timezone
