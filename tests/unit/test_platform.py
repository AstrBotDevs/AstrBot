"""Tests for astrbot.core.platform.platform — Platform ABC."""

import asyncio
from asyncio import Queue
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.platform.platform import Platform, PlatformError, PlatformStatus
from astrbot.core.platform.platform_metadata import PlatformMetadata


# ---------------------------------------------------------------------------
# Concrete subclass so we can test non-abstract behaviour of Platform.
# ---------------------------------------------------------------------------
class ConcretePlatform(Platform):
    """Minimal concrete Platform used in every test that needs an instance."""

    async def run(self) -> None:
        pass

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="test_adapter",
            description="A test adapter",
            id="test_adapter_id",
            adapter_display_name="Test Adapter",
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def config() -> dict:
    return {
        "key": "value",
        "unified_webhook_mode": False,
    }


@pytest.fixture
def event_queue() -> Queue:
    return Queue()


@pytest.fixture
def platform(config: dict, event_queue: Queue) -> ConcretePlatform:
    return ConcretePlatform(config, event_queue)


# ===================================================================
# Construction
# ===================================================================

class TestConstruction:
    """Platform.__init__ stores constructor arguments and sets defaults."""

    def test_stores_config_and_queue(self, config: dict, event_queue: Queue):
        p = ConcretePlatform(config, event_queue)
        assert p.config is config
        assert p._event_queue is event_queue

    def test_default_status_is_pending(self, platform: ConcretePlatform):
        assert platform.status == PlatformStatus.PENDING

    def test_client_self_id_is_random_hex(self, platform: ConcretePlatform):
        assert isinstance(platform.client_self_id, str)
        assert len(platform.client_self_id) == 32  # uuid4 hex

    def test_errors_list_starts_empty(self, platform: ConcretePlatform):
        assert platform.errors == []

    def test_started_at_is_none_until_running(self, platform: ConcretePlatform):
        assert platform._started_at is None


# ===================================================================
# Status property
# ===================================================================

class TestStatus:
    """Platform.status getter/setter and side-effects."""

    def test_setter_changes_status(self, platform: ConcretePlatform):
        platform.status = PlatformStatus.RUNNING
        assert platform.status == PlatformStatus.RUNNING

    def test_setting_running_records_started_at(self, platform: ConcretePlatform):
        platform.status = PlatformStatus.RUNNING
        assert platform._started_at is not None
        assert isinstance(platform._started_at, datetime)

    def test_setting_running_twice_does_not_overwrite_started_at(
        self, platform: ConcretePlatform
    ):
        platform.status = PlatformStatus.RUNNING
        t1 = platform._started_at
        platform.status = PlatformStatus.ERROR
        platform.status = PlatformStatus.RUNNING
        assert platform._started_at == t1


# ===================================================================
# Error paths
# ===================================================================

class TestErrors:
    """record_error, last_error, clear_errors."""

    def test_record_error_appends_to_list(self, platform: ConcretePlatform):
        platform.record_error("something went wrong", "traceback line 1")
        assert len(platform.errors) == 1
        assert platform.errors[0].message == "something went wrong"
        assert platform.errors[0].traceback == "traceback line 1"

    def test_record_error_sets_status_to_error(self, platform: ConcretePlatform):
        platform.record_error("fail")
        assert platform.status == PlatformStatus.ERROR

    def test_last_error_none_when_empty(self, platform: ConcretePlatform):
        assert platform.last_error is None

    def test_last_error_returns_most_recent(self, platform: ConcretePlatform):
        platform.record_error("first")
        platform.record_error("second")
        assert platform.last_error.message == "second"

    def test_clear_errors_empties_list(self, platform: ConcretePlatform):
        platform.record_error("first")
        platform.clear_errors()
        assert platform.errors == []

    def test_clear_errors_resets_status_from_error(self, platform: ConcretePlatform):
        platform.record_error("first")
        platform.clear_errors()
        assert platform.status == PlatformStatus.RUNNING

    def test_clear_errors_is_noop_when_no_error(self, platform: ConcretePlatform):
        platform.clear_errors()
        assert platform.errors == []
        assert platform.status == PlatformStatus.PENDING


# ===================================================================
# unified_webhook
# ===================================================================

class TestUnifiedWebhook:
    """Platform.unified_webhook() logic."""

    def test_disabled_by_default(self, platform: ConcretePlatform):
        assert platform.unified_webhook() is False

    def test_enabled_when_both_config_present(
        self, config: dict, event_queue: Queue
    ):
        config["unified_webhook_mode"] = True
        config["webhook_uuid"] = "abc123"
        p = ConcretePlatform(config, event_queue)
        assert p.unified_webhook() is True

    def test_disabled_without_uuid(self, config: dict, event_queue: Queue):
        config["unified_webhook_mode"] = True
        # no webhook_uuid set
        p = ConcretePlatform(config, event_queue)
        assert p.unified_webhook() is False

    def test_disabled_when_mode_off(self, config: dict, event_queue: Queue):
        config["unified_webhook_mode"] = False
        config["webhook_uuid"] = "abc123"
        p = ConcretePlatform(config, event_queue)
        assert p.unified_webhook() is False


# ===================================================================
# get_stats
# ===================================================================

class TestGetStats:
    """Platform.get_stats() structure and content."""

    def test_stats_contains_expected_keys(self, platform: ConcretePlatform):
        stats = platform.get_stats()
        expected_keys = {
            "id", "type", "display_name", "status", "started_at",
            "error_count", "last_error", "unified_webhook", "meta",
        }
        assert expected_keys.issubset(stats.keys())

    def test_stats_values_without_errors(self, platform: ConcretePlatform):
        stats = platform.get_stats()
        assert stats["id"] == "test_adapter_id"
        assert stats["type"] == "test_adapter"
        assert stats["display_name"] == "Test Adapter"
        assert stats["status"] == PlatformStatus.PENDING.value
        assert stats["started_at"] is None
        assert stats["error_count"] == 0
        assert stats["last_error"] is None
        assert stats["unified_webhook"] is False
        assert stats["meta"]["id"] == "test_adapter_id"
        assert stats["meta"]["name"] == "test_adapter"

    def test_stats_reflects_recorded_errors(self, platform: ConcretePlatform):
        platform.record_error("err1", "tb1")
        platform.record_error("err2", "tb2")
        stats = platform.get_stats()
        assert stats["error_count"] == 2
        assert stats["last_error"]["message"] == "err2"
        assert stats["last_error"]["traceback"] == "tb2"


# ===================================================================
# Instance methods
# ===================================================================

class TestMethods:
    """terminate, get_client, commit_event, webhook_callback, send_by_session."""

    @pytest.mark.asyncio
    async def test_terminate_sets_stopped(self, platform: ConcretePlatform):
        await platform.terminate()
        assert platform.status == PlatformStatus.STOPPED

    def test_get_client_returns_none(self, platform: ConcretePlatform):
        assert platform.get_client() is None

    @pytest.mark.asyncio
    async def test_commit_event_puts_into_queue(
        self, platform: ConcretePlatform, event_queue: Queue
    ):
        mock_event = MagicMock()
        platform.commit_event(mock_event)
        assert event_queue.qsize() == 1
        assert await event_queue.get() is mock_event

    @pytest.mark.asyncio
    async def test_webhook_callback_raises_not_implemented(
        self, platform: ConcretePlatform
    ):
        with pytest.raises(NotImplementedError) as exc:
            await platform.webhook_callback(None)
        assert "未实现统一 Webhook 模式" in str(exc.value)

    @pytest.mark.asyncio
    async def test_send_by_session_calls_metric_upload(
        self, platform: ConcretePlatform
    ):
        mock_session = MagicMock()
        mock_chain = MagicMock()
        with patch(
            "astrbot.core.platform.platform.Metric.upload",
            new_callable=AsyncMock,
        ) as mock_upload:
            await platform.send_by_session(mock_session, mock_chain)
            mock_upload.assert_called_once_with(
                msg_event_tick=1, adapter_name="test_adapter"
            )


# ===================================================================
# Abstract-method detection (cannot instantiate ABC directly)
# ===================================================================

class TestAbstractDetection:
    """Verify the ABC enforces that run() and meta() are implemented."""

    def test_cannot_instantiate_platform_directly(self):
        with pytest.raises(TypeError):
            Platform({"k": "v"}, Queue())  # type: ignore[abstract]

    def test_missing_run_raises_type_error(self):
        class MissingRun(Platform):
            def meta(self) -> PlatformMetadata:
                return PlatformMetadata(name="x", description="x", id="x")

        with pytest.raises(TypeError):
            MissingRun({}, Queue())  # type: ignore[abstract]

    def test_missing_meta_raises_type_error(self):
        class MissingMeta(Platform):
            async def run(self) -> None:
                pass

        with pytest.raises(TypeError):
            MissingMeta({}, Queue())  # type: ignore[abstract]


# ===================================================================
# PlatformError dataclass
# ===================================================================

class TestPlatformErrorDataclass:
    """PlatformError construction and defaults."""

    def test_required_message(self):
        err = PlatformError(message="oops")
        assert err.message == "oops"
        assert err.traceback is None
        assert isinstance(err.timestamp, datetime)

    def test_with_traceback(self):
        err = PlatformError(message="oops", traceback="tb content")
        assert err.traceback == "tb content"

    def test_default_timestamp_is_nowish(self):
        before = datetime.now()
        err = PlatformError(message="oops")
        after = datetime.now()
        assert before <= err.timestamp <= after
