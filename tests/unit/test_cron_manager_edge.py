"""Supplementary edge-case tests for CronJobManager.

Covers validation branches, interval-based jobs, run-once auto-cleanup,
and failure paths not covered by the main test suite.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.cron.manager import CronJobManager, CronJobSchedulingError
from astrbot.core.db.po import CronJob


# ---- Fixtures (self-contained) ----


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.create_cron_job = AsyncMock()
    db.get_cron_job = AsyncMock()
    db.update_cron_job = AsyncMock()
    db.delete_cron_job = AsyncMock()
    db.list_cron_jobs = AsyncMock(return_value=[])
    return db


@pytest.fixture
def mock_context():
    ctx = MagicMock()
    ctx.get_config = MagicMock(return_value={"admins_id": []})
    ctx.conversation_manager = MagicMock()
    return ctx


@pytest.fixture
def cron_manager(mock_db):
    return CronJobManager(mock_db)


# ---- add_basic_job validation edge cases ----


class TestAddBasicJobEdgeCases:
    """Validation and interval-based variants for add_basic_job."""

    @pytest.mark.asyncio
    async def test_add_basic_job_with_interval_seconds(self, cron_manager, mock_db):
        """interval_seconds can be used instead of cron_expression."""
        cron_manager._started = True
        job = CronJob(job_id="interval-job", name="Interval", job_type="basic")
        mock_db.create_cron_job.return_value = job

        handler = MagicMock()
        result = await cron_manager.add_basic_job(
            name="Interval",
            interval_seconds=300,
            handler=handler,
            description="Every 5 min",
        )

        assert result == job
        mock_db.create_cron_job.assert_called_once()
        # interval should be packed into the payload
        call_payload = mock_db.create_cron_job.call_args.kwargs["payload"]
        assert "interval_seconds" in call_payload
        assert call_payload["interval_seconds"] == 300

    @pytest.mark.asyncio
    async def test_add_basic_job_both_cron_and_interval_raises(self, cron_manager, mock_db):
        """Providing both cron_expression and interval_seconds raises ValueError."""
        handler = MagicMock()
        with pytest.raises(ValueError, match="must have exactly one value"):
            await cron_manager.add_basic_job(
                name="Bad",
                cron_expression="0 9 * * *",
                interval_seconds=300,
                handler=handler,
            )

    @pytest.mark.asyncio
    async def test_add_basic_job_neither_cron_nor_interval_raises(self, cron_manager, mock_db):
        """Providing neither cron_expression nor interval_seconds raises ValueError."""
        handler = MagicMock()
        with pytest.raises(ValueError, match="must have exactly one value"):
            await cron_manager.add_basic_job(
                name="Bad",
                handler=handler,
            )

    @pytest.mark.asyncio
    async def test_add_basic_job_payload_passed_through(self, cron_manager, mock_db):
        """User-supplied payload is forwarded to create_cron_job."""
        cron_manager._started = True
        job = CronJob(job_id="payload-job", name="Payload", job_type="basic")
        mock_db.create_cron_job.return_value = job

        handler = MagicMock()
        user_payload = {"custom_key": "custom_value"}
        await cron_manager.add_basic_job(
            name="Payload",
            cron_expression="0 9 * * *",
            handler=handler,
            payload=user_payload,
        )

        call_payload = mock_db.create_cron_job.call_args.kwargs["payload"]
        assert call_payload["custom_key"] == "custom_value"

    @pytest.mark.asyncio
    async def test_add_basic_job_non_persistent_not_scheduled(self, cron_manager, mock_db):
        """A disabled non-persistent job is stored but not scheduled."""
        job = CronJob(
            job_id="np-job", name="NonPersist", job_type="basic", enabled=False
        )
        mock_db.create_cron_job.return_value = job

        handler = MagicMock()
        with patch.object(cron_manager, "_schedule_job") as mock_schedule:
            result = await cron_manager.add_basic_job(
                name="NonPersist",
                cron_expression="0 9 * * *",
                handler=handler,
                persistent=False,
                enabled=False,
            )

        assert result == job
        mock_schedule.assert_not_called()


# ---- _run_job full lifecycle edge cases ----


class TestRunJobEdgeCases:
    """Full lifecycle for _run_job covering status transitions and cleanup."""

    @pytest.mark.asyncio
    async def test_run_job_basic_completed(self, cron_manager, mock_db):
        """A basic job transitions to 'completed' after successful run."""
        job = CronJob(
            job_id="basic-done",
            name="Done",
            job_type="basic",
            enabled=True,
            cron_expression="0 9 * * *",
        )
        mock_db.get_cron_job.return_value = job

        handler = MagicMock(return_value=None)
        cron_manager._basic_handlers["basic-done"] = handler

        await cron_manager._run_job("basic-done")

        # Status should be updated twice: running -> completed
        update_calls = [
            c for c in mock_db.update_cron_job.call_args_list
        ]
        # At minimum one call with status="running" and one with status="completed"
        running_calls = [
            c for c in update_calls
            if c.kwargs.get("status") == "running"
        ]
        completed_calls = [
            c for c in update_calls
            if c.kwargs.get("status") == "completed"
        ]
        assert len(running_calls) >= 1, "Expected a 'running' status update"
        assert len(completed_calls) >= 1, "Expected a 'completed' status update"
        handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_job_basic_failed(self, cron_manager, mock_db):
        """A basic job transitions to 'failed' and records the error."""
        mock_db.get_cron_job.return_value = CronJob(
            job_id="basic-fail",
            name="Fail",
            job_type="basic",
            enabled=True,
            cron_expression="0 9 * * *",
        )
        # Remove the handler so _run_basic_job raises RuntimeError
        if "basic-fail" in cron_manager._basic_handlers:
            del cron_manager._basic_handlers["basic-fail"]

        await cron_manager._run_job("basic-fail")

        # final update should have status="failed" and last_error set
        last_call = mock_db.update_cron_job.call_args_list[-1]
        assert last_call.kwargs["status"] == "failed"
        assert last_call.kwargs["last_error"] is not None

    @pytest.mark.asyncio
    async def test_run_job_run_once_deletes_after_completion(self, cron_manager, mock_db):
        """A run_once job is deleted after it completes successfully."""
        job = CronJob(
            job_id="once-job",
            name="Once",
            job_type="basic",
            enabled=True,
            run_once=True,
            cron_expression="0 9 * * *",
        )
        mock_db.get_cron_job.return_value = job

        handler = MagicMock(return_value=None)
        cron_manager._basic_handlers["once-job"] = handler

        with patch.object(cron_manager, "delete_job") as mock_delete:
            await cron_manager._run_job("once-job")

        mock_delete.assert_awaited_once_with("once-job")

    @pytest.mark.asyncio
    async def test_run_job_active_agent_raises_on_missing_session(self, cron_manager, mock_db):
        """run_job on an active_agent job without session payload raises."""
        job = CronJob(
            job_id="aa-no-session",
            name="NoSession",
            job_type="active_agent",
            enabled=True,
            cron_expression="0 9 * * *",
            payload={},  # No "session" key
        )
        mock_db.get_cron_job.return_value = job

        await cron_manager._run_job("aa-no-session")

        # Should not crash the manager; error is caught and logged,
        # status should be "failed"
        last_call = mock_db.update_cron_job.call_args_list[-1]
        assert last_call.kwargs["status"] == "failed"
        assert "missing session" in (last_call.kwargs.get("last_error") or "").lower()


# ---- update_job and sync_from_db ----


class TestUpdateAndSyncEdgeCases:
    """Edge cases for update_job and sync_from_db."""

    @pytest.mark.asyncio
    async def test_update_job_reschedules_when_enabled(self, cron_manager, mock_db):
        """update_job re-schedules a job that was previously disabled."""
        job_id = "re-enable-job"
        updated_job = CronJob(
            job_id=job_id,
            name="ReEnabled",
            job_type="basic",
            cron_expression="0 9 * * *",
            enabled=True,  # Now enabled
        )
        mock_db.update_cron_job.return_value = updated_job

        with patch.object(cron_manager, "_schedule_job") as mock_schedule:
            result = await cron_manager.update_job(job_id, enabled=True)

        assert result == updated_job
        mock_schedule.assert_called_once_with(updated_job)

    @pytest.mark.asyncio
    async def test_update_job_removes_scheduled_when_disabled(self, cron_manager, mock_db):
        """update_job removes the job from the scheduler when disabled."""
        job_id = "disable-job"
        updated_job = CronJob(
            job_id=job_id,
            name="Disabled",
            job_type="basic",
            cron_expression="0 9 * * *",
            enabled=False,  # Now disabled, should not schedule
        )
        mock_db.update_cron_job.return_value = updated_job

        with patch.object(cron_manager, "_remove_scheduled") as mock_remove:
            with patch.object(cron_manager, "_schedule_job") as mock_schedule:
                result = await cron_manager.update_job(job_id, enabled=False)

        assert result == updated_job
        mock_remove.assert_called_once_with(job_id)
        mock_schedule.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_from_db_schedules_basic_with_handler(self, cron_manager, mock_db):
        """sync_from_db schedules basic jobs when their handler is registered."""
        job = CronJob(
            job_id="sync-basic",
            name="SyncBasic",
            job_type="basic",
            cron_expression="0 9 * * *",
            enabled=True,
            persistent=True,
        )
        mock_db.list_cron_jobs.return_value = [job]
        cron_manager._basic_handlers["sync-basic"] = MagicMock()

        with patch.object(cron_manager, "_schedule_job") as mock_schedule:
            await cron_manager.sync_from_db()

        mock_schedule.assert_called_once_with(job)

    @pytest.mark.asyncio
    async def test_sync_from_db_skips_basic_without_handler(self, cron_manager, mock_db):
        """sync_from_db skips basic jobs that have no registered handler."""
        job = CronJob(
            job_id="orphan-basic",
            name="Orphan",
            job_type="basic",
            cron_expression="0 9 * * *",
            enabled=True,
            persistent=True,
        )
        mock_db.list_cron_jobs.return_value = [job]

        with patch.object(cron_manager, "_schedule_job") as mock_schedule:
            await cron_manager.sync_from_db()

        mock_schedule.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_from_db_schedules_active_agent_without_handler(self, cron_manager, mock_db):
        """Active-agent jobs are scheduled regardless of handler registration."""
        job = CronJob(
            job_id="sync-active",
            name="SyncActive",
            job_type="active_agent",
            cron_expression="0 9 * * *",
            enabled=True,
            persistent=True,
        )
        mock_db.list_cron_jobs.return_value = [job]

        with patch.object(cron_manager, "_schedule_job") as mock_schedule:
            await cron_manager.sync_from_db()

        mock_schedule.assert_called_once_with(job)


# ---- _schedule_job trigger variants ----


class TestScheduleJobTriggers:
    """Trigger type selection in _schedule_job."""

    @pytest.mark.asyncio
    async def test_schedule_interval_trigger(self, cron_manager, mock_context):
        """_schedule_job creates an IntervalTrigger when payload has interval_seconds."""
        job = CronJob(
            job_id="interval-trigger",
            name="Interval",
            job_type="basic",
            cron_expression="0 9 * * *",
            enabled=True,
            payload={"interval_seconds": 600},
        )
        mock_db = cron_manager.db
        mock_db.list_cron_jobs = AsyncMock(return_value=[])
        mock_db.update_cron_job = AsyncMock()
        await cron_manager.start(mock_context)

        cron_manager._schedule_job(job)

        aps_job = cron_manager.scheduler.get_job("interval-trigger")
        assert aps_job is not None
        # The trigger should be an IntervalTrigger
        from apscheduler.triggers.interval import IntervalTrigger

        assert isinstance(aps_job.trigger, IntervalTrigger)
        assert aps_job.trigger.interval.total_seconds() == 600

    @pytest.mark.asyncio
    async def test_schedule_invalid_cron_raises_scheduling_error(self, cron_manager, mock_context):
        """An invalid cron expression raises CronJobSchedulingError."""
        job = CronJob(
            job_id="bad-cron",
            name="BadCron",
            job_type="basic",
            cron_expression="not-a-valid-cron",
            enabled=True,
        )
        mock_db = cron_manager.db
        mock_db.list_cron_jobs = AsyncMock(return_value=[])
        mock_db.update_cron_job = AsyncMock()
        await cron_manager.start(mock_context)

        with pytest.raises(CronJobSchedulingError):
            cron_manager._schedule_job(job)

    @pytest.mark.asyncio
    async def test_schedule_run_once_without_run_at_raises(self, cron_manager, mock_context):
        """A run_once job without run_at in payload or expression raises CronJobSchedulingError."""
        job = CronJob(
            job_id="no-run-at",
            name="NoRunAt",
            job_type="active_agent",
            cron_expression=None,
            enabled=True,
            run_once=True,
            payload={},
        )
        mock_db = cron_manager.db
        mock_db.list_cron_jobs = AsyncMock(return_value=[])
        mock_db.update_cron_job = AsyncMock()
        await cron_manager.start(mock_context)

        with pytest.raises(CronJobSchedulingError):
            cron_manager._schedule_job(job)

    @pytest.mark.asyncio
    async def test_schedule_auto_starts_when_not_started(self, cron_manager):
        """_schedule_job auto-starts the scheduler if _started is False."""
        assert cron_manager._started is False

        job = CronJob(
            job_id="auto-start",
            name="AutoStart",
            job_type="basic",
            cron_expression="0 9 * * *",
            enabled=True,
        )
        cron_manager.db.list_cron_jobs = AsyncMock(return_value=[])
        cron_manager.db.update_cron_job = AsyncMock()

        cron_manager._schedule_job(job)

        assert cron_manager._started is True
        assert cron_manager.scheduler.get_job("auto-start") is not None
