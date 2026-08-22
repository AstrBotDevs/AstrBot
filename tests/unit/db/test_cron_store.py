from datetime import UTC, datetime, timedelta

import pytest

from astrbot.core.db.sqlite import SQLiteDatabase


@pytest.mark.asyncio
async def test_cron_job_update_distinguishes_not_set_from_explicit_none(
    temp_db: SQLiteDatabase,
):
    scheduled_time = datetime.now(UTC) + timedelta(hours=1)
    job = await temp_db.create_cron_job(
        name="Morning sync",
        job_type="sync",
        cron_expression="0 8 * * *",
        timezone="Asia/Shanghai",
        payload={"scope": "all"},
        description="daily",
        enabled=True,
        persistent=True,
        run_once=False,
        status="scheduled",
        job_id="job-1",
    )

    updated = await temp_db.update_cron_job(
        job.job_id,
        cron_expression=None,
        payload={"scope": "one"},
        enabled=False,
        next_run_time=scheduled_time,
        last_error=None,
    )

    assert updated is not None
    assert updated.job_id == "job-1"
    assert updated.name == "Morning sync"
    assert updated.cron_expression is None
    assert updated.timezone == "Asia/Shanghai"
    assert updated.payload == {"scope": "one"}
    assert updated.enabled is False
    assert updated.next_run_time == scheduled_time.replace(tzinfo=None)
    assert updated.last_error is None

    untouched = await temp_db.update_cron_job("missing-job", status="failed")
    assert untouched is None

    filtered = await temp_db.list_cron_jobs(job_type="sync")
    assert [item.job_id for item in filtered] == ["job-1"]
