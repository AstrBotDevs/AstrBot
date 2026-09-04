"""Tests for the privileged cron Dashboard API boundary."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.dashboard.api.cron import _create_job, _update_job
from astrbot.dashboard.responses import ApiError
from astrbot.dashboard.schemas import CronJobRequest


@pytest.mark.asyncio
async def test_create_privileged_cron_forwards_dashboard_totp_header() -> None:
    """Forward a Dashboard TOTP header only after the session boundary check."""
    service = SimpleNamespace(create_job=AsyncMock(return_value={"job_id": "job-1"}))
    payload = CronJobRequest(allow_privileged_execution=True)

    response = await _create_job(
        payload,
        service,
        dashboard_username="admin-1",
        two_factor_code="123456",
    )

    assert response["status"] == "ok"
    assert service.create_job.await_args.kwargs == {
        "allow_privileged_execution": True,
        "created_by": "admin-1",
        "two_factor_code": "123456",
    }


@pytest.mark.asyncio
async def test_create_privileged_cron_rejects_non_dashboard_caller() -> None:
    """Keep API-key callers from enabling privileged cron execution."""
    service = SimpleNamespace(create_job=AsyncMock())

    with pytest.raises(ApiError) as exc_info:
        await _create_job(
            CronJobRequest(allow_privileged_execution=True),
            service,
        )

    assert exc_info.value.status_code == 403
    service.create_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_preserves_absent_privileged_field() -> None:
    """Do not turn an unrelated cron update into a privilege transition."""
    service = SimpleNamespace(update_job=AsyncMock(return_value={"job_id": "job-1"}))

    await _update_job(
        "job-1",
        CronJobRequest(enabled=False),
        service,
        dashboard_username="admin-1",
        two_factor_code="123456",
    )

    assert service.update_job.await_args.kwargs == {
        "allow_privileged_execution": None,
        "two_factor_code": "123456",
    }
