"""Tests for Platform base class."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.platform.platform import Platform, PlatformError, PlatformStatus
from astrbot.core.platform.platform_metadata import PlatformMetadata


class ConcretePlatform(Platform):
    """Concrete implementation of Platform for testing purposes."""

    def __init__(self, config: dict, event_queue: asyncio.Queue) -> None:
        super().__init__(config, event_queue)
        self._meta = PlatformMetadata(
            name="test_platform",
            description="Test platform for unit testing",
            id="test_platform_id",
        )

    def run(self):
        """Return a coroutine for running the platform."""
        return self._run_impl()

    async def _run_impl(self):
        """Implementation of run method."""
        await asyncio.Future()  # Never completes

    def meta(self) -> PlatformMetadata:
        """Return platform metadata."""
        return self._meta


@pytest.fixture
def event_queue():
    """Create an event queue for testing."""
    return asyncio.Queue()


@pytest.fixture
def platform_config():
    """Create a platform configuration for testing."""
    return {
        "id": "test_platform_id",
        "type": "test_platform",
        "enable": True,
    }


@pytest.fixture
def platform(event_queue, platform_config):
    """Create a concrete platform instance for testing."""
    return ConcretePlatform(platform_config, event_queue)


class TestPlatformInit:
    """Tests for Platform initialization."""

    def test_init_basic(self, event_queue, platform_config):
        """Test basic Platform initialization."""
        platform = ConcretePlatform(platform_config, event_queue)

        assert platform.config == platform_config
        assert platform._event_queue == event_queue
        assert platform.client_self_id is not None
        assert len(platform.client_self_id) == 32  # uuid.hex length

    def test_init_status_pending(self, platform):
        """Test that initial status is PENDING."""
        assert platform.status == PlatformStatus.PENDING

    def test_init_empty_errors(self, platform):
        """Test that initial errors list is empty."""
        assert platform.errors == []
        assert platform.last_error is None

    def test_init_started_at_none(self, platform):
        """Test that started_at is None initially."""
        assert platform._started_at is None


class TestPlatformStatus:
    """Tests for Platform status property."""

    def test_status_getter(self, platform):
        """Test status getter returns current status."""
        assert platform.status == PlatformStatus.PENDING

    def test_status_setter_to_running(self, platform):
        """Test setting status to RUNNING sets started_at."""
        platform.status = PlatformStatus.RUNNING

        assert platform.status == PlatformStatus.RUNNING
        assert platform._started_at is not None
        assert isinstance(platform._started_at, datetime)

    def test_status_setter_running_only_sets_started_at_once(self, platform):
        """Test that started_at is only set once when status becomes RUNNING."""
        first_time = datetime(2020, 1, 1)
        platform._started_at = first_time

        platform.status = PlatformStatus.RUNNING

        assert platform._started_at == first_time

    def test_status_setter_to_error(self, platform):
        """Test setting status to ERROR."""
        platform.status = PlatformStatus.ERROR
        assert platform.status == PlatformStatus.ERROR

    def test_status_setter_to_stopped(self, platform):
        """Test setting status to STOPPED."""
        platform.status = PlatformStatus.STOPPED
        assert platform.status == PlatformStatus.STOPPED


class TestPlatformErrors:
    """Tests for Platform error handling."""

    def test_errors_property_returns_list(self, platform):
        """Test errors property returns the errors list."""
        assert platform.errors == []

    def test_last_error_returns_none_when_empty(self, platform):
        """Test last_error returns None when no errors."""
        assert platform.last_error is None

    def test_record_error_adds_to_list(self, platform):
        """Test record_error adds error to the list."""
        platform.record_error("Test error message")

        assert len(platform.errors) == 1
        assert platform.errors[0].message == "Test error message"
        assert platform.errors[0].traceback is None

    def test_record_error_with_traceback(self, platform):
        """Test record_error with traceback."""
        platform.record_error("Error with traceback", "Line 1\nLine 2")

        assert platform.errors[0].traceback == "Line 1\nLine 2"

    def test_record_error_sets_status_to_error(self, platform):
        """Test record_error sets status to ERROR."""
        platform.record_error("Test error")
        assert platform.status == PlatformStatus.ERROR

    def test_last_error_returns_most_recent(self, platform):
        """Test last_error returns the most recent error."""
        platform.record_error("First error")
        platform.record_error("Second error")

        assert platform.last_error.message == "Second error"

    def test_clear_errors_removes_all_errors(self, platform):
        """Test clear_errors removes all errors."""
        platform.record_error("Error 1")
        platform.record_error("Error 2")
        platform.clear_errors()

        assert platform.errors == []
        assert platform.last_error is None

    def test_clear_errors_resets_status_from_error_to_running(self, platform):
        """Test clear_errors resets status from ERROR to RUNNING."""
        platform.record_error("Error")
        assert platform.status == PlatformStatus.ERROR

        platform.clear_errors()
        assert platform.status == PlatformStatus.RUNNING

    def test_clear_errors_does_not_change_status_if_not_error(self, platform):
        """Test clear_errors doesn't change status if not ERROR."""
        platform.status = PlatformStatus.STOPPED
        platform.clear_errors()

        assert platform.status == PlatformStatus.STOPPED


class TestPlatformError:
    """Tests for PlatformError dataclass."""

    def test_platform_error_creation(self):
        """Test creating a PlatformError."""
        error = PlatformError(message="Test error")

        assert error.message == "Test error"
        assert error.timestamp is not None
        assert isinstance(error.timestamp, datetime)
        assert error.traceback is None

    def test_platform_error_with_traceback(self):
        """Test creating a PlatformError with traceback."""
        error = PlatformError(message="Error", traceback="Stack trace here")

        assert error.traceback == "Stack trace here"


class TestUnifiedWebhook:
    """Tests for unified_webhook method."""

    def test_unified_webhook_false_by_default(self, platform):
        """Test unified_webhook returns False by default."""
        assert platform.unified_webhook() is False

    def test_unified_webhook_true_when_configured(self, event_queue):
        """Test unified_webhook returns True when properly configured."""
        config = {
            "unified_webhook_mode": True,
            "webhook_uuid": "test-uuid-123",
        }
        platform = ConcretePlatform(config, event_queue)

        assert platform.unified_webhook() is True

    def test_unified_webhook_false_when_missing_uuid(self, event_queue):
        """Test unified_webhook returns False when webhook_uuid is missing."""
        config = {"unified_webhook_mode": True}
        platform = ConcretePlatform(config, event_queue)

        assert platform.unified_webhook() is False

    def test_unified_webhook_false_when_mode_disabled(self, event_queue):
        """Test unified_webhook returns False when mode is disabled."""
        config = {
            "unified_webhook_mode": False,
            "webhook_uuid": "test-uuid-123",
        }
        platform = ConcretePlatform(config, event_queue)

        assert platform.unified_webhook() is False


class TestGetStats:
    """Tests for get_stats method."""

    def test_get_stats_basic(self, platform):
        """Test get_stats returns basic statistics."""
        stats = platform.get_stats()

        assert stats["id"] == "test_platform_id"
        assert stats["type"] == "test_platform"
        assert stats["status"] == PlatformStatus.PENDING.value
        assert stats["error_count"] == 0
        assert stats["last_error"] is None
        assert stats["unified_webhook"] is False

    def test_get_stats_with_running_status(self, platform):
        """Test get_stats with RUNNING status includes started_at."""
        platform.status = PlatformStatus.RUNNING
        stats = platform.get_stats()

        assert stats["status"] == PlatformStatus.RUNNING.value
        assert stats["started_at"] is not None

    def test_get_stats_with_errors(self, platform):
        """Test get_stats includes error information."""
        platform.record_error("Test error", "Traceback info")
        stats = platform.get_stats()

        assert stats["error_count"] == 1
        assert stats["last_error"] is not None
        assert stats["last_error"]["message"] == "Test error"
        assert stats["last_error"]["traceback"] == "Traceback info"

    def test_get_stats_meta_info(self, platform):
        """Test get_stats includes metadata information."""
        stats = platform.get_stats()

        assert "meta" in stats
        assert stats["meta"]["name"] == "test_platform"
        assert stats["meta"]["id"] == "test_platform_id"


class TestWebhookCallback:
    """Tests for webhook_callback method."""

    @pytest.mark.asyncio
    async def test_webhook_callback_raises_not_implemented(self, platform):
        """Test webhook_callback raises NotImplementedError by default."""
        mock_request = MagicMock()

        with pytest.raises(NotImplementedError) as exc_info:
            await platform.webhook_callback(mock_request)

        assert "未实现统一 Webhook 模式" in str(exc_info.value)


class TestCommitEvent:
    """Tests for commit_event method."""

    def test_commit_event_puts_in_queue(self, platform, event_queue):
        """Test commit_event puts event in the queue."""
        mock_event = MagicMock()
        platform.commit_event(mock_event)

        assert event_queue.qsize() == 1
        assert event_queue.get_nowait() == mock_event


class TestTerminate:
    """Tests for terminate method."""

    @pytest.mark.asyncio
    async def test_terminate_default_implementation(self, platform):
        """Test terminate method has default empty implementation."""
        # Should not raise any exception
        await platform.terminate()


class TestGetClient:
    """Tests for get_client method."""

    def test_get_client_default_returns_none(self, platform):
        """Test get_client returns None by default."""
        result = platform.get_client()
        assert result is None


class TestSendBySession:
    """Tests for send_by_session method."""

    @pytest.mark.asyncio
    async def test_send_by_session_default_implementation(self, platform):
        """Test send_by_session default implementation."""
        mock_session = MagicMock()
        mock_message_chain = MagicMock()

        with patch(
            "astrbot.core.platform.platform.Metric.upload", new_callable=AsyncMock
        ) as mock_upload:
            await platform.send_by_session(mock_session, mock_message_chain)
            mock_upload.assert_awaited_once_with(
                msg_event_tick=1, adapter_name="test_platform"
            )


class TestPlatformStatusEnum:
    """Tests for PlatformStatus enum."""

    def test_platform_status_values(self):
        """Test PlatformStatus enum values."""
        assert PlatformStatus.PENDING.value == "pending"
        assert PlatformStatus.RUNNING.value == "running"
        assert PlatformStatus.ERROR.value == "error"
        assert PlatformStatus.STOPPED.value == "stopped"
