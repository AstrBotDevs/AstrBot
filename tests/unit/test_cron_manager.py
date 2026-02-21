"""Tests for CronJobManager."""

import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from astrbot.core.cron.manager import CronJobManager
from astrbot.core.db.po import CronJob


@pytest.fixture
def mock_db():
    """Create a mock database."""
    db = MagicMock()
    db.create_cron_job = AsyncMock()
    db.get_cron_job = AsyncMock()
    db.update_cron_job = AsyncMock()
    db.delete_cron_job = AsyncMock()
    db.list_cron_jobs = AsyncMock(return_value=[])
    return db


@pytest.fixture
def mock_context():
    """Create a mock Context."""
    ctx = MagicMock()
    ctx.get_config = MagicMock(return_value={"admins_id": []})
    ctx.conversation_manager = MagicMock()
    return ctx


@pytest.fixture
def cron_manager(mock_db):
    """Create a CronJobManager instance."""
    return CronJobManager(mock_db)


@pytest.fixture
def sample_cron_job():
    """Create a sample CronJob."""
    return CronJob(
        job_id="test-job-id",
        name="Test Job",
        job_type="basic",
        cron_expression="0 9 * * *",
        timezone="UTC",
        payload={"key": "value"},
        description="A test job",
        enabled=True,
        persistent=True,
        run_once=False,
        status="pending",
    )


class TestCronJobManagerInit:
    """Tests for CronJobManager initialization."""

    def test_init(self, mock_db):
        """Test CronJobManager initialization."""
        manager = CronJobManager(mock_db)

        assert manager.db == mock_db
        assert manager._basic_handlers == {}
        assert manager._started is False


class TestCronJobManagerStart:
    """Tests for CronJobManager.start method."""

    @pytest.mark.asyncio
    async def test_start(self, cron_manager, mock_db, mock_context):
        """Test starting the cron manager."""
        mock_db.list_cron_jobs.return_value = []

        await cron_manager.start(mock_context)

        assert cron_manager._started is True
        assert cron_manager.ctx == mock_context

    @pytest.mark.asyncio
    async def test_start_idempotent(self, cron_manager, mock_db, mock_context):
        """Test that start is idempotent."""
        mock_db.list_cron_jobs.return_value = []

        await cron_manager.start(mock_context)
        await cron_manager.start(mock_context)

        # Should only sync once
        assert mock_db.list_cron_jobs.call_count == 1


class TestCronJobManagerShutdown:
    """Tests for CronJobManager.shutdown method."""

    @pytest.mark.asyncio
    async def test_shutdown(self, cron_manager, mock_db, mock_context):
        """Test shutting down the cron manager."""
        mock_db.list_cron_jobs.return_value = []
        await cron_manager.start(mock_context)

        await cron_manager.shutdown()

        assert cron_manager._started is False

    @pytest.mark.asyncio
    async def test_shutdown_when_not_started(self, cron_manager):
        """Test shutdown when not started."""
        # Should not raise
        await cron_manager.shutdown()


class TestAddBasicJob:
    """Tests for add_basic_job method."""

    @pytest.mark.asyncio
    async def test_add_basic_job(self, cron_manager, mock_db, sample_cron_job):
        """Test adding a basic cron job."""
        mock_db.create_cron_job.return_value = sample_cron_job

        handler = MagicMock()

        result = await cron_manager.add_basic_job(
            name="Test Job",
            cron_expression="0 9 * * *",
            handler=handler,
            description="A test job",
            enabled=True,
        )

        assert result == sample_cron_job
        assert sample_cron_job.job_id in cron_manager._basic_handlers
        mock_db.create_cron_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_basic_job_disabled(self, cron_manager, mock_db, sample_cron_job):
        """Test adding a disabled basic cron job."""
        sample_cron_job.enabled = False
        mock_db.create_cron_job.return_value = sample_cron_job

        handler = MagicMock()

        result = await cron_manager.add_basic_job(
            name="Test Job",
            cron_expression="0 9 * * *",
            handler=handler,
            enabled=False,
        )

        assert result == sample_cron_job
        assert sample_cron_job.job_id in cron_manager._basic_handlers

    @pytest.mark.asyncio
    async def test_add_basic_job_with_timezone(self, cron_manager, mock_db, sample_cron_job):
        """Test adding a basic job with timezone."""
        mock_db.create_cron_job.return_value = sample_cron_job

        handler = MagicMock()

        await cron_manager.add_basic_job(
            name="Test Job",
            cron_expression="0 9 * * *",
            handler=handler,
            timezone="Asia/Shanghai",
        )

        mock_db.create_cron_job.assert_called_once()
        call_kwargs = mock_db.create_cron_job.call_args.kwargs
        assert call_kwargs["timezone"] == "Asia/Shanghai"


class TestAddActiveJob:
    """Tests for add_active_job method."""

    @pytest.mark.asyncio
    async def test_add_active_job(self, cron_manager, mock_db, sample_cron_job):
        """Test adding an active agent cron job."""
        sample_cron_job.job_type = "active_agent"
        mock_db.create_cron_job.return_value = sample_cron_job

        result = await cron_manager.add_active_job(
            name="Test Active Job",
            cron_expression="0 9 * * *",
            payload={"session": "test:group:123"},
        )

        assert result == sample_cron_job
        mock_db.create_cron_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_active_job_run_once(self, cron_manager, mock_db, sample_cron_job):
        """Test adding a run-once active job."""
        sample_cron_job.job_type = "active_agent"
        sample_cron_job.run_once = True
        mock_db.create_cron_job.return_value = sample_cron_job

        run_at = datetime(2025, 12, 31, 12, 0, 0, tzinfo=timezone.utc)

        result = await cron_manager.add_active_job(
            name="Test Run Once Job",
            cron_expression=None,
            payload={"session": "test:group:123"},
            run_once=True,
            run_at=run_at,
        )

        assert result == sample_cron_job
        call_kwargs = mock_db.create_cron_job.call_args.kwargs
        assert "run_at" in call_kwargs["payload"] or call_kwargs["run_once"] is True


class TestUpdateJob:
    """Tests for update_job method."""

    @pytest.mark.asyncio
    async def test_update_job(self, cron_manager, mock_db, sample_cron_job):
        """Test updating a cron job."""
        updated_job = CronJob(
            job_id="test-job-id",
            name="Updated Job",
            job_type="basic",
            cron_expression="0 10 * * *",
            enabled=False,  # Disabled to avoid scheduling
        )
        mock_db.update_cron_job.return_value = updated_job

        result = await cron_manager.update_job("test-job-id", name="Updated Job")

        assert result == updated_job
        mock_db.update_cron_job.assert_called()

    @pytest.mark.asyncio
    async def test_update_job_not_found(self, cron_manager, mock_db):
        """Test updating a non-existent job."""
        mock_db.update_cron_job.return_value = None

        result = await cron_manager.update_job("non-existent", name="Updated")

        assert result is None


class TestDeleteJob:
    """Tests for delete_job method."""

    @pytest.mark.asyncio
    async def test_delete_job(self, cron_manager, mock_db):
        """Test deleting a cron job."""
        cron_manager._basic_handlers["test-job-id"] = MagicMock()

        await cron_manager.delete_job("test-job-id")

        mock_db.delete_cron_job.assert_called_once_with("test-job-id")
        assert "test-job-id" not in cron_manager._basic_handlers


class TestListJobs:
    """Tests for list_jobs method."""

    @pytest.mark.asyncio
    async def test_list_all_jobs(self, cron_manager, mock_db, sample_cron_job):
        """Test listing all jobs."""
        mock_db.list_cron_jobs.return_value = [sample_cron_job]

        result = await cron_manager.list_jobs()

        assert len(result) == 1
        mock_db.list_cron_jobs.assert_called_once_with(None)

    @pytest.mark.asyncio
    async def test_list_jobs_by_type(self, cron_manager, mock_db, sample_cron_job):
        """Test listing jobs by type."""
        mock_db.list_cron_jobs.return_value = [sample_cron_job]

        result = await cron_manager.list_jobs(job_type="basic")

        mock_db.list_cron_jobs.assert_called_once_with("basic")


class TestSyncFromDb:
    """Tests for sync_from_db method."""

    @pytest.mark.asyncio
    async def test_sync_from_db_empty(self, cron_manager, mock_db):
        """Test syncing from empty database."""
        mock_db.list_cron_jobs.return_value = []

        await cron_manager.sync_from_db()

        mock_db.list_cron_jobs.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_from_db_skips_disabled(self, cron_manager, mock_db, sample_cron_job):
        """Test that sync skips disabled jobs."""
        sample_cron_job.enabled = False
        mock_db.list_cron_jobs.return_value = [sample_cron_job]

        await cron_manager.sync_from_db()

        # Job should not be scheduled (no error raised)

    @pytest.mark.asyncio
    async def test_sync_from_db_skips_non_persistent(self, cron_manager, mock_db, sample_cron_job):
        """Test that sync skips non-persistent jobs."""
        sample_cron_job.persistent = False
        mock_db.list_cron_jobs.return_value = [sample_cron_job]

        await cron_manager.sync_from_db()

    @pytest.mark.asyncio
    async def test_sync_from_db_basic_without_handler(
        self, cron_manager, mock_db, sample_cron_job
    ):
        """Test that sync warns for basic jobs without handlers."""
        mock_db.list_cron_jobs.return_value = [sample_cron_job]

        with patch("astrbot.core.cron.manager.logger") as mock_logger:
            await cron_manager.sync_from_db()

        mock_logger.warning.assert_called()


class TestRemoveScheduled:
    """Tests for _remove_scheduled method."""

    @pytest.mark.asyncio
    async def test_remove_scheduled_existing(self, cron_manager, mock_context):
        """Test removing a scheduled job."""
        # Start the scheduler first
        job = CronJob(
            job_id="test-job-id",
            name="Test",
            job_type="active_agent",
            cron_expression="0 9 * * *",
            enabled=True,
            persistent=True,
        )
        mock_db = cron_manager.db
        mock_db.list_cron_jobs = AsyncMock(return_value=[job])
        await cron_manager.start(mock_context)

        # Then remove it
        cron_manager._remove_scheduled("test-job-id")

        # Should not raise

    def test_remove_scheduled_nonexistent(self, cron_manager):
        """Test removing a non-existent job."""
        # Should not raise
        cron_manager._remove_scheduled("non-existent")


class TestScheduleJob:
    """Tests for _schedule_job method."""

    @pytest.mark.asyncio
    async def test_schedule_job_basic(self, cron_manager, sample_cron_job, mock_context):
        """Test scheduling a basic job."""
        mock_db = cron_manager.db
        mock_db.list_cron_jobs = AsyncMock(return_value=[])
        mock_db.update_cron_job = AsyncMock()
        await cron_manager.start(mock_context)
        cron_manager._schedule_job(sample_cron_job)

        # Verify job was added to scheduler
        assert cron_manager.scheduler.get_job("test-job-id") is not None

    @pytest.mark.asyncio
    async def test_schedule_job_with_timezone(self, cron_manager, sample_cron_job, mock_context):
        """Test scheduling a job with timezone."""
        sample_cron_job.timezone = "America/New_York"
        mock_db = cron_manager.db
        mock_db.list_cron_jobs = AsyncMock(return_value=[])
        mock_db.update_cron_job = AsyncMock()
        await cron_manager.start(mock_context)
        cron_manager._schedule_job(sample_cron_job)

        assert cron_manager.scheduler.get_job("test-job-id") is not None

    @pytest.mark.asyncio
    async def test_schedule_job_invalid_timezone(self, cron_manager, sample_cron_job, mock_context):
        """Test scheduling a job with invalid timezone."""
        sample_cron_job.timezone = "Invalid/Timezone"
        mock_db = cron_manager.db
        mock_db.list_cron_jobs = AsyncMock(return_value=[])
        mock_db.update_cron_job = AsyncMock()

        with patch("astrbot.core.cron.manager.logger") as mock_logger:
            await cron_manager.start(mock_context)
            cron_manager._schedule_job(sample_cron_job)

        # Should still schedule with system timezone
        assert cron_manager.scheduler.get_job("test-job-id") is not None
        mock_logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_schedule_job_run_once(self, cron_manager, mock_context):
        """Test scheduling a run-once job."""
        job = CronJob(
            job_id="run-once-job",
            name="Run Once",
            job_type="active_agent",
            cron_expression=None,
            enabled=True,
            run_once=True,
            payload={"run_at": "2025-12-31T12:00:00+00:00"},
        )
        mock_db = cron_manager.db
        mock_db.list_cron_jobs = AsyncMock(return_value=[])
        mock_db.update_cron_job = AsyncMock()
        await cron_manager.start(mock_context)
        cron_manager._schedule_job(job)

        assert cron_manager.scheduler.get_job("run-once-job") is not None


class TestRunJob:
    """Tests for _run_job method."""

    @pytest.mark.asyncio
    async def test_run_job_disabled(self, cron_manager, mock_db, sample_cron_job):
        """Test running a disabled job."""
        sample_cron_job.enabled = False
        mock_db.get_cron_job.return_value = sample_cron_job

        await cron_manager._run_job("test-job-id")

        # Should not update status
        mock_db.update_cron_job.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_job_not_found(self, cron_manager, mock_db):
        """Test running a non-existent job."""
        mock_db.get_cron_job.return_value = None

        await cron_manager._run_job("non-existent")

        # Should not update status
        mock_db.update_cron_job.assert_not_called()


class TestRunBasicJob:
    """Tests for _run_basic_job method."""

    @pytest.mark.asyncio
    async def test_run_basic_job_sync_handler(self, cron_manager, sample_cron_job):
        """Test running a basic job with sync handler."""
        handler = MagicMock(return_value=None)
        cron_manager._basic_handlers["test-job-id"] = handler
        sample_cron_job.payload = {"arg1": "value1"}

        await cron_manager._run_basic_job(sample_cron_job)

        handler.assert_called_once_with(arg1="value1")

    @pytest.mark.asyncio
    async def test_run_basic_job_async_handler(self, cron_manager, sample_cron_job):
        """Test running a basic job with async handler."""
        async_handler = AsyncMock()
        cron_manager._basic_handlers["test-job-id"] = async_handler
        sample_cron_job.payload = {}

        await cron_manager._run_basic_job(sample_cron_job)

        async_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_basic_job_no_handler(self, cron_manager, sample_cron_job):
        """Test running a basic job without handler."""
        sample_cron_job.job_id = "no-handler-job"

        with pytest.raises(RuntimeError, match="handler not found"):
            await cron_manager._run_basic_job(sample_cron_job)


class TestGetNextRunTime:
    """Tests for _get_next_run_time method."""

    @pytest.mark.asyncio
    async def test_get_next_run_time_existing_job(self, cron_manager, sample_cron_job, mock_context):
        """Test getting next run time for existing job."""
        mock_db = cron_manager.db
        mock_db.list_cron_jobs = AsyncMock(return_value=[])
        mock_db.update_cron_job = AsyncMock()
        await cron_manager.start(mock_context)
        cron_manager._schedule_job(sample_cron_job)

        next_run = cron_manager._get_next_run_time("test-job-id")

        assert next_run is not None

    def test_get_next_run_time_nonexistent(self, cron_manager):
        """Test getting next run time for non-existent job."""
        next_run = cron_manager._get_next_run_time("non-existent")

        assert next_run is None
