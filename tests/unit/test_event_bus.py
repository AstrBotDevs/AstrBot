"""Tests for EventBus."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from astrbot.core.event_bus import EventBus


@pytest.fixture
def event_queue():
    """Create an event queue."""
    return asyncio.Queue()


@pytest.fixture
def mock_pipeline_scheduler():
    """Create a mock pipeline scheduler."""
    scheduler = MagicMock()
    scheduler.execute = AsyncMock()
    return scheduler


@pytest.fixture
def mock_config_manager():
    """Create a mock config manager."""
    config_mgr = MagicMock()
    config_mgr.get_conf_info = MagicMock(return_value={"id": "test-conf-id", "name": "Test Config"})
    return config_mgr


@pytest.fixture
def event_bus(event_queue, mock_pipeline_scheduler, mock_config_manager):
    """Create an EventBus instance."""
    return EventBus(
        event_queue=event_queue,
        pipeline_scheduler_mapping={"test-conf-id": mock_pipeline_scheduler},
        astrbot_config_mgr=mock_config_manager,
    )


class TestEventBusInit:
    """Tests for EventBus initialization."""

    def test_init(self, event_queue, mock_pipeline_scheduler, mock_config_manager):
        """Test EventBus initialization."""
        bus = EventBus(
            event_queue=event_queue,
            pipeline_scheduler_mapping={"test": mock_pipeline_scheduler},
            astrbot_config_mgr=mock_config_manager,
        )

        assert bus.event_queue == event_queue
        assert bus.pipeline_scheduler_mapping == {"test": mock_pipeline_scheduler}
        assert bus.astrbot_config_mgr == mock_config_manager


class TestEventBusDispatch:
    """Tests for EventBus dispatch method."""

    @pytest.mark.asyncio
    async def test_dispatch_processes_event(
        self, event_bus, event_queue, mock_pipeline_scheduler, mock_config_manager
    ):
        """Test that dispatch processes an event from the queue."""
        # Create a mock event
        mock_event = MagicMock()
        mock_event.unified_msg_origin = "test-platform:group:123"
        mock_event.get_platform_id.return_value = "test-platform"
        mock_event.get_platform_name.return_value = "Test Platform"
        mock_event.get_sender_name.return_value = "TestUser"
        mock_event.get_sender_id.return_value = "user123"
        mock_event.get_message_outline.return_value = "Hello"

        # Put event in queue
        await event_queue.put(mock_event)

        # Start dispatch in background and cancel after processing
        task = asyncio.create_task(event_bus.dispatch())

        # Wait for the event to be processed
        await asyncio.sleep(0.1)

        # Cancel the dispatch loop
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Verify scheduler was called
        mock_pipeline_scheduler.execute.assert_called_once_with(mock_event)
        mock_config_manager.get_conf_info.assert_called_once_with("test-platform:group:123")

    @pytest.mark.asyncio
    async def test_dispatch_handles_missing_scheduler(
        self, event_bus, event_queue, mock_config_manager
    ):
        """Test that dispatch handles missing scheduler gracefully."""
        # Configure to return a config ID that has no scheduler
        mock_config_manager.get_conf_info.return_value = {
            "id": "missing-scheduler",
            "name": "Missing Config"
        }

        mock_event = MagicMock()
        mock_event.unified_msg_origin = "test-platform:group:123"
        mock_event.get_platform_id.return_value = "test-platform"
        mock_event.get_platform_name.return_value = "Test Platform"
        mock_event.get_sender_name.return_value = None
        mock_event.get_sender_id.return_value = "user123"
        mock_event.get_message_outline.return_value = "Hello"

        await event_queue.put(mock_event)

        task = asyncio.create_task(event_bus.dispatch())
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_dispatch_multiple_events(
        self, event_bus, event_queue, mock_pipeline_scheduler, mock_config_manager
    ):
        """Test that dispatch processes multiple events."""
        events = []
        for i in range(3):
            mock_event = MagicMock()
            mock_event.unified_msg_origin = f"test-platform:group:{i}"
            mock_event.get_platform_id.return_value = "test-platform"
            mock_event.get_platform_name.return_value = "Test Platform"
            mock_event.get_sender_name.return_value = f"User{i}"
            mock_event.get_sender_id.return_value = f"user{i}"
            mock_event.get_message_outline.return_value = f"Message {i}"
            events.append(mock_event)
            await event_queue.put(mock_event)

        task = asyncio.create_task(event_bus.dispatch())
        await asyncio.sleep(0.2)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert mock_pipeline_scheduler.execute.call_count == 3


class TestPrintEvent:
    """Tests for _print_event method."""

    def test_print_event_with_sender_name(self, event_bus):
        """Test printing event with sender name."""
        mock_event = MagicMock()
        mock_event.get_platform_id.return_value = "test-platform"
        mock_event.get_platform_name.return_value = "Test Platform"
        mock_event.get_sender_name.return_value = "TestUser"
        mock_event.get_sender_id.return_value = "user123"
        mock_event.get_message_outline.return_value = "Hello"

        with patch("astrbot.core.event_bus.logger") as mock_logger:
            event_bus._print_event(mock_event, "TestConfig")

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        assert "TestConfig" in call_args
        assert "TestUser" in call_args
        assert "user123" in call_args
        assert "Hello" in call_args

    def test_print_event_without_sender_name(self, event_bus):
        """Test printing event without sender name."""
        mock_event = MagicMock()
        mock_event.get_platform_id.return_value = "test-platform"
        mock_event.get_platform_name.return_value = "Test Platform"
        mock_event.get_sender_name.return_value = None
        mock_event.get_sender_id.return_value = "user123"
        mock_event.get_message_outline.return_value = "Hello"

        with patch("astrbot.core.event_bus.logger") as mock_logger:
            event_bus._print_event(mock_event, "TestConfig")

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        assert "TestConfig" in call_args
        assert "user123" in call_args
        assert "Hello" in call_args
        # Should not have sender name separator
        assert "/" not in call_args
