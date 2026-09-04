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
async def test_create_privileged_job_requires_totp_when_enabled(monkeypatch) -> None:
    """Require a valid TOTP code before creating a privileged cron job."""
    cron_manager = SimpleNamespace(add_active_job=AsyncMock())
    config_manager = SimpleNamespace(
        get_conf=MagicMock(
            return_value={
                "dashboard": {
                    "totp": {
                        "enable": True,
                        "secret": "JBSWY3DPEHPK3PXP",
                        "recovery_code_hash": "configured",
                    }
                }
            }
        )
    )
    verify = AsyncMock(return_value=False)
    monkeypatch.setattr(
        "astrbot.dashboard.services.cron_service.verify_configured_2fa_code",
        verify,
    )
    service = CronService(
        SimpleNamespace(cron_manager=cron_manager, astrbot_config_mgr=config_manager)
    )

    with pytest.raises(CronServiceError) as exc_info:
        await service.create_job(
            {
                "name": "privileged",
                "note": "test",
                "cron_expression": "0 9 * * *",
            },
            allow_privileged_execution=True,
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.data == {"totp_required": True}
    verify.assert_not_awaited()
    cron_manager.add_active_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_privileged_job_accepts_totp_when_enabled(monkeypatch) -> None:
    """Pass the one-time TOTP code through before creating a privileged job."""
    job = SimpleNamespace(job_id="job-1", name="privileged", payload={}, run_once=False)
    cron_manager = SimpleNamespace(add_active_job=AsyncMock(return_value=job))
    config_manager = SimpleNamespace(
        get_conf=MagicMock(
            return_value={
                "dashboard": {
                    "totp": {
                        "enable": True,
                        "secret": "JBSWY3DPEHPK3PXP",
                        "recovery_code_hash": "configured",
                    }
                }
            }
        )
    )
    verify = AsyncMock(return_value=object())
    monkeypatch.setattr(
        "astrbot.dashboard.services.cron_service.verify_configured_2fa_code",
        verify,
    )
    service = CronService(
        SimpleNamespace(cron_manager=cron_manager, astrbot_config_mgr=config_manager)
    )

    await service.create_job(
        {
            "name": "privileged",
            "note": "test",
            "cron_expression": "0 9 * * *",
        },
        allow_privileged_execution=True,
        two_factor_code="123456",
    )

    verify.assert_awaited_once_with(
        config_manager.get_conf.return_value,
        "123456",
        allow_recovery=False,
    )
    assert cron_manager.add_active_job.await_args.kwargs[
        "allow_privileged_execution"
    ] is True


@pytest.mark.asyncio
async def test_update_only_requires_totp_when_enabling_privileged_job(monkeypatch) -> None:
    """Avoid consuming a TOTP code when a job remains privileged or is disabled."""
    job = SimpleNamespace(
        job_id="job-1",
        name="job",
        job_type="active_agent",
        payload={"note": "test"},
        run_once=False,
        cron_expression="0 9 * * *",
        allow_privileged_execution=True,
    )
    cron_manager = SimpleNamespace(
        db=SimpleNamespace(get_cron_job=AsyncMock(return_value=job)),
        update_job=AsyncMock(return_value=job),
    )
    config_manager = SimpleNamespace(get_conf=MagicMock(return_value={}))
    verify = AsyncMock(return_value=False)
    monkeypatch.setattr(
        "astrbot.dashboard.services.cron_service.verify_configured_2fa_code",
        verify,
    )
    service = CronService(
        SimpleNamespace(cron_manager=cron_manager, astrbot_config_mgr=config_manager)
    )

    await service.update_job(
        "job-1",
        {"enabled": False},
        allow_privileged_execution=True,
    )

    verify.assert_not_awaited()
