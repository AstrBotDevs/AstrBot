"""Tests for EventBus."""

import asyncio
from contextlib import suppress
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
    config_mgr.get_conf_info = MagicMock(
        return_value={"id": "test-conf-id", "name": "Test Config"}
    )
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
        processed = asyncio.Event()

        async def execute_and_signal(event):  # noqa: ARG001
            processed.set()

        mock_pipeline_scheduler.execute.side_effect = execute_and_signal

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
        try:
            await asyncio.wait_for(processed.wait(), timeout=1.0)
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        # Verify scheduler was called
        mock_pipeline_scheduler.execute.assert_called_once_with(mock_event)
        mock_config_manager.get_conf_info.assert_called_once_with(
            "test-platform:group:123"
        )

    @pytest.mark.asyncio
    async def test_dispatch_handles_missing_scheduler(
        self,
        event_bus,
        event_queue,
        mock_config_manager,
        mock_pipeline_scheduler,
    ):
        """Test that dispatch handles missing scheduler gracefully."""
        logged = asyncio.Event()

        def error_and_signal(*args, **kwargs):  # noqa: ARG001
            logged.set()

        # Configure to return a config ID that has no scheduler
        mock_config_manager.get_conf_info.return_value = {
            "id": "missing-scheduler",
            "name": "Missing Config",
        }

        mock_event = MagicMock()
        mock_event.unified_msg_origin = "test-platform:group:123"
        mock_event.get_platform_id.return_value = "test-platform"
        mock_event.get_platform_name.return_value = "Test Platform"
        mock_event.get_sender_name.return_value = None
        mock_event.get_sender_id.return_value = "user123"
        mock_event.get_message_outline.return_value = "Hello"

        await event_queue.put(mock_event)

        with patch("astrbot.core.event_bus.logger") as mock_logger:
            mock_logger.error.side_effect = error_and_signal
            task = asyncio.create_task(event_bus.dispatch())
            try:
                await asyncio.wait_for(logged.wait(), timeout=1.0)
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

            mock_logger.error.assert_called_once()
            assert "missing-scheduler" in mock_logger.error.call_args[0][0]

        mock_pipeline_scheduler.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_multiple_events(
        self, event_bus, event_queue, mock_pipeline_scheduler, mock_config_manager
    ):
        """Test that dispatch processes multiple events."""
        processed_all = asyncio.Event()
        processed_count = 0

        async def execute_and_count(event):  # noqa: ARG001
            nonlocal processed_count
            processed_count += 1
            if processed_count == 3:
                processed_all.set()

        mock_pipeline_scheduler.execute.side_effect = execute_and_count

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
        try:
            await asyncio.wait_for(processed_all.wait(), timeout=1.0)
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        assert mock_pipeline_scheduler.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_dispatch_handles_incomplete_conf_info(
        self,
        event_bus,
        mock_config_manager,
        mock_pipeline_scheduler,
    ):
        """Test that dispatch ignores incomplete conf_info defensively."""
        mock_config_manager.get_conf_info.return_value = {
            "name": "Missing ID",
        }

        mock_event = MagicMock()
        mock_event.unified_msg_origin = "test-platform:group:123"
        mock_event.get_platform_id.return_value = "test-platform"
        mock_event.get_platform_name.return_value = "Test Platform"
        mock_event.get_sender_name.return_value = "TestUser"
        mock_event.get_sender_id.return_value = "user123"
        mock_event.get_message_outline.return_value = "Hello"

        event_bus.event_queue.get = AsyncMock(
            side_effect=[mock_event, asyncio.CancelledError()]
        )

        with (
            patch("astrbot.core.event_bus.logger") as mock_logger,
            patch.object(event_bus, "_print_event") as mock_print_event,
        ):
            with suppress(asyncio.CancelledError):
                await event_bus.dispatch()

            mock_logger.error.assert_called_once()
            assert "Incomplete conf_info" in mock_logger.error.call_args[0][0]

        mock_print_event.assert_not_called()
        mock_pipeline_scheduler.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_falls_back_to_conf_id_when_name_missing(
        self,
        event_bus,
        event_queue,
        mock_config_manager,
        mock_pipeline_scheduler,
    ):
        """Test that missing conf name does not block dispatch."""
        processed = asyncio.Event()
        mock_config_manager.get_conf_info.return_value = {
            "id": "test-conf-id",
        }

        async def execute_and_signal(event):  # noqa: ARG001
            processed.set()

        mock_pipeline_scheduler.execute.side_effect = execute_and_signal

        mock_event = MagicMock()
        mock_event.unified_msg_origin = "test-platform:group:123"
        mock_event.get_platform_id.return_value = "test-platform"
        mock_event.get_platform_name.return_value = "Test Platform"
        mock_event.get_sender_name.return_value = "TestUser"
        mock_event.get_sender_id.return_value = "user123"
        mock_event.get_message_outline.return_value = "Hello"

        await event_queue.put(mock_event)

        with patch.object(event_bus, "_print_event") as mock_print_event:
            task = asyncio.create_task(event_bus.dispatch())
            try:
                await asyncio.wait_for(processed.wait(), timeout=1.0)
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

        mock_print_event.assert_called_once_with(mock_event, "test-conf-id")
        mock_pipeline_scheduler.execute.assert_called_once_with(mock_event)


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


class TestEventSubscription:
    """Tests for event subscription functionality."""

    @pytest.mark.asyncio
    async def test_subscriber_registration(self, event_queue, mock_config_manager):
        """Test registering a subscriber (scheduler) to the event bus."""
        # Create multiple schedulers as subscribers
        scheduler1 = MagicMock()
        scheduler1.execute = AsyncMock()
        scheduler2 = MagicMock()
        scheduler2.execute = AsyncMock()

        # Create EventBus with multiple subscribers
        pipeline_mapping = {
            "conf-id-1": scheduler1,
            "conf-id-2": scheduler2,
        }
        event_bus = EventBus(
            event_queue=event_queue,
            pipeline_scheduler_mapping=pipeline_mapping,
            astrbot_config_mgr=mock_config_manager,
        )

        # Verify both subscribers are registered
        assert "conf-id-1" in event_bus.pipeline_scheduler_mapping
        assert "conf-id-2" in event_bus.pipeline_scheduler_mapping
        assert event_bus.pipeline_scheduler_mapping["conf-id-1"] == scheduler1
        assert event_bus.pipeline_scheduler_mapping["conf-id-2"] == scheduler2

    @pytest.mark.asyncio
    async def test_multiple_subscribers_receive_events(
        self, event_queue, mock_config_manager
    ):
        """Test that events are dispatched to the correct subscriber based on config."""
        processed = asyncio.Event()
        call_tracker = {"scheduler1": False, "scheduler2": False}
        mock_config_manager.get_conf_info.return_value = {
            "id": "conf-id-1",
            "name": "Test Config",
        }

        scheduler1 = MagicMock()
        scheduler1.execute = AsyncMock()

        async def execute_scheduler1(event):  # noqa: ARG001
            call_tracker["scheduler1"] = True
            processed.set()

        scheduler1.execute.side_effect = execute_scheduler1

        scheduler2 = MagicMock()
        scheduler2.execute = AsyncMock()

        async def execute_scheduler2(event):  # noqa: ARG001
            call_tracker["scheduler2"] = True

        scheduler2.execute.side_effect = execute_scheduler2

        pipeline_mapping = {
            "conf-id-1": scheduler1,
            "conf-id-2": scheduler2,
        }
        event_bus = EventBus(
            event_queue=event_queue,
            pipeline_scheduler_mapping=pipeline_mapping,
            astrbot_config_mgr=mock_config_manager,
        )

        mock_event = MagicMock()
        mock_event.unified_msg_origin = "platform:group:123"
        mock_event.get_platform_id.return_value = "platform"
        mock_event.get_platform_name.return_value = "Platform"
        mock_event.get_sender_name.return_value = "User"
        mock_event.get_sender_id.return_value = "user1"
        mock_event.get_message_outline.return_value = "Test"

        await event_queue.put(mock_event)

        task = asyncio.create_task(event_bus.dispatch())
        try:
            await asyncio.wait_for(processed.wait(), timeout=1.0)
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        # Only scheduler1 should have been called (based on mock_config_manager default)
        assert call_tracker["scheduler1"] is True
        assert call_tracker["scheduler2"] is False

    @pytest.mark.asyncio
    async def test_unsubscribe_by_removing_scheduler(
        self, event_queue, mock_config_manager
    ):
        """Test that removing a scheduler effectively unsubscribes it."""
        scheduler = MagicMock()
        scheduler.execute = AsyncMock()

        pipeline_mapping = {"conf-id": scheduler}
        event_bus = EventBus(
            event_queue=event_queue,
            pipeline_scheduler_mapping=pipeline_mapping,
            astrbot_config_mgr=mock_config_manager,
        )

        # Verify scheduler is registered
        assert "conf-id" in event_bus.pipeline_scheduler_mapping

        # Remove the scheduler (unsubscribe)
        del event_bus.pipeline_scheduler_mapping["conf-id"]

        # Verify scheduler is no longer registered
        assert "conf-id" not in event_bus.pipeline_scheduler_mapping

    @pytest.mark.asyncio
    async def test_subscriber_exception_handling(
        self, event_queue, mock_config_manager
    ):
        """Test that exceptions in subscriber execution don't crash the event bus."""
        exception_raised = asyncio.Event()
        second_event_processed = asyncio.Event()
        mock_config_manager.get_conf_info.return_value = {
            "id": "conf-id-1",
            "name": "Test Config",
        }

        scheduler1 = MagicMock()
        scheduler1.execute = AsyncMock()

        async def execute_with_exception(event):  # noqa: ARG001
            exception_raised.set()
            raise RuntimeError("Subscriber error")

        scheduler1.execute.side_effect = execute_with_exception

        scheduler2 = MagicMock()
        scheduler2.execute = AsyncMock()

        async def execute_normal(event):  # noqa: ARG001
            second_event_processed.set()

        scheduler2.execute.side_effect = execute_normal

        pipeline_mapping = {
            "conf-id-1": scheduler1,
            "conf-id-2": scheduler2,
        }
        event_bus = EventBus(
            event_queue=event_queue,
            pipeline_scheduler_mapping=pipeline_mapping,
            astrbot_config_mgr=mock_config_manager,
        )

        # First event will cause exception
        mock_event1 = MagicMock()
        mock_event1.unified_msg_origin = "platform:group:1"
        mock_event1.get_platform_id.return_value = "platform"
        mock_event1.get_platform_name.return_value = "Platform"
        mock_event1.get_sender_name.return_value = "User"
        mock_event1.get_sender_id.return_value = "user1"
        mock_event1.get_message_outline.return_value = "Test"

        await event_queue.put(mock_event1)

        task = asyncio.create_task(event_bus.dispatch())
        try:
            await asyncio.wait_for(exception_raised.wait(), timeout=1.0)
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        # Verify the scheduler was called (exception occurred but didn't crash)
        scheduler1.execute.assert_called_once()


class TestEventFiltering:
    """Tests for event filtering functionality."""

    @pytest.mark.asyncio
    async def test_filter_by_event_origin(self, event_queue):
        """Test filtering events by their unified_msg_origin."""
        scheduler1 = MagicMock()
        scheduler1.execute = AsyncMock()
        scheduler2 = MagicMock()
        scheduler2.execute = AsyncMock()

        config_mgr = MagicMock()

        # Route different origins to different schedulers
        def get_conf_info(origin):
            if origin.startswith("telegram"):
                return {"id": "telegram-conf", "name": "Telegram Config"}
            elif origin.startswith("discord"):
                return {"id": "discord-conf", "name": "Discord Config"}
            return {"id": "default-conf", "name": "Default Config"}

        config_mgr.get_conf_info = MagicMock(side_effect=get_conf_info)

        pipeline_mapping = {
            "telegram-conf": scheduler1,
            "discord-conf": scheduler2,
        }
        event_bus = EventBus(
            event_queue=event_queue,
            pipeline_scheduler_mapping=pipeline_mapping,
            astrbot_config_mgr=config_mgr,
        )

        processed = asyncio.Event()
        scheduler1.execute.side_effect = lambda e: processed.set()  # noqa: ARG001

        # Create Telegram event
        mock_event = MagicMock()
        mock_event.unified_msg_origin = "telegram:private:123"
        mock_event.get_platform_id.return_value = "telegram"
        mock_event.get_platform_name.return_value = "Telegram"
        mock_event.get_sender_name.return_value = "TGUser"
        mock_event.get_sender_id.return_value = "tg123"
        mock_event.get_message_outline.return_value = "TG Message"

        await event_queue.put(mock_event)

        task = asyncio.create_task(event_bus.dispatch())
        try:
            await asyncio.wait_for(processed.wait(), timeout=1.0)
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        # Only telegram scheduler should be called
        scheduler1.execute.assert_called_once()
        scheduler2.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_filter_by_message_content_type(
        self, event_queue, mock_config_manager
    ):
        """Test filtering based on message content (e.g., group vs private)."""
        processed = asyncio.Event()
        scheduler = MagicMock()
        scheduler.execute = AsyncMock()

        async def execute_and_signal(event):  # noqa: ARG001
            processed.set()

        scheduler.execute.side_effect = execute_and_signal

        pipeline_mapping = {"test-conf-id": scheduler}
        event_bus = EventBus(
            event_queue=event_queue,
            pipeline_scheduler_mapping=pipeline_mapping,
            astrbot_config_mgr=mock_config_manager,
        )

        # Create event with group message origin
        mock_event = MagicMock()
        mock_event.unified_msg_origin = "platform:group:456"
        mock_event.get_platform_id.return_value = "platform"
        mock_event.get_platform_name.return_value = "Platform"
        mock_event.get_sender_name.return_value = "GroupUser"
        mock_event.get_sender_id.return_value = "user456"
        mock_event.get_message_outline.return_value = "Group message"

        await event_queue.put(mock_event)

        task = asyncio.create_task(event_bus.dispatch())
        try:
            await asyncio.wait_for(processed.wait(), timeout=1.0)
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        # Verify config was queried with correct origin
        mock_config_manager.get_conf_info.assert_called_once_with("platform:group:456")
        scheduler.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_combined_filter_conditions(self, event_queue):
        """Test filtering with combined conditions (platform + message type)."""
        scheduler_telegram_group = MagicMock()
        scheduler_telegram_group.execute = AsyncMock()
        scheduler_telegram_private = MagicMock()
        scheduler_telegram_private.execute = AsyncMock()
        scheduler_discord = MagicMock()
        scheduler_discord.execute = AsyncMock()

        config_mgr = MagicMock()

        def get_conf_info(origin):
            # Combined filtering based on platform and message type
            if origin.startswith("telegram:group"):
                return {"id": "tg-group-conf", "name": "Telegram Group"}
            elif origin.startswith("telegram:private"):
                return {"id": "tg-private-conf", "name": "Telegram Private"}
            elif origin.startswith("discord"):
                return {"id": "discord-conf", "name": "Discord"}
            return {"id": "unknown", "name": "Unknown"}

        config_mgr.get_conf_info = MagicMock(side_effect=get_conf_info)

        pipeline_mapping = {
            "tg-group-conf": scheduler_telegram_group,
            "tg-private-conf": scheduler_telegram_private,
            "discord-conf": scheduler_discord,
        }
        event_bus = EventBus(
            event_queue=event_queue,
            pipeline_scheduler_mapping=pipeline_mapping,
            astrbot_config_mgr=config_mgr,
        )

        processed = asyncio.Event()
        scheduler_telegram_group.execute.side_effect = lambda e: processed.set()  # noqa: ARG001

        # Create Telegram group event
        mock_event = MagicMock()
        mock_event.unified_msg_origin = "telegram:group:789"
        mock_event.get_platform_id.return_value = "telegram"
        mock_event.get_platform_name.return_value = "Telegram"
        mock_event.get_sender_name.return_value = "GroupUser"
        mock_event.get_sender_id.return_value = "user789"
        mock_event.get_message_outline.return_value = "Group msg"

        await event_queue.put(mock_event)

        task = asyncio.create_task(event_bus.dispatch())
        try:
            await asyncio.wait_for(processed.wait(), timeout=1.0)
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        # Only telegram group scheduler should be called
        scheduler_telegram_group.execute.assert_called_once()
        scheduler_telegram_private.execute.assert_not_called()
        scheduler_discord.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_matching_filter_ignores_event(self, event_queue):
        """Test that events with no matching filter are ignored."""
        error_logged = asyncio.Event()

        scheduler = MagicMock()
        scheduler.execute = AsyncMock()

        config_mgr = MagicMock()
        # Return a config ID that doesn't exist in pipeline_mapping
        config_mgr.get_conf_info.return_value = {
            "id": "nonexistent-conf",
            "name": "Nonexistent",
        }

        pipeline_mapping = {"existing-conf": scheduler}
        event_bus = EventBus(
            event_queue=event_queue,
            pipeline_scheduler_mapping=pipeline_mapping,
            astrbot_config_mgr=config_mgr,
        )

        mock_event = MagicMock()
        mock_event.unified_msg_origin = "unknown:platform:123"
        mock_event.get_platform_id.return_value = "unknown"
        mock_event.get_platform_name.return_value = "Unknown"
        mock_event.get_sender_name.return_value = "User"
        mock_event.get_sender_id.return_value = "user123"
        mock_event.get_message_outline.return_value = "Test"

        await event_queue.put(mock_event)

        with patch("astrbot.core.event_bus.logger") as mock_logger:
            mock_logger.error.side_effect = lambda *args, **kwargs: error_logged.set()  # noqa: ARG001
            task = asyncio.create_task(event_bus.dispatch())
            try:
                await asyncio.wait_for(error_logged.wait(), timeout=1.0)
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

            # Verify error was logged
            mock_logger.error.assert_called_once()
            assert "nonexistent-conf" in mock_logger.error.call_args[0][0]

        # Scheduler should not have been called
        scheduler.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_pipeline_mapping_filters_all(self, event_queue):
        """Test that empty pipeline mapping filters out all events."""
        error_logged = asyncio.Event()

        config_mgr = MagicMock()
        config_mgr.get_conf_info.return_value = {
            "id": "some-conf",
            "name": "Some Config",
        }

        pipeline_mapping = {}  # Empty mapping
        event_bus = EventBus(
            event_queue=event_queue,
            pipeline_scheduler_mapping=pipeline_mapping,
            astrbot_config_mgr=config_mgr,
        )

        mock_event = MagicMock()
        mock_event.unified_msg_origin = "platform:group:123"
        mock_event.get_platform_id.return_value = "platform"
        mock_event.get_platform_name.return_value = "Platform"
        mock_event.get_sender_name.return_value = "User"
        mock_event.get_sender_id.return_value = "user123"
        mock_event.get_message_outline.return_value = "Test"

        await event_queue.put(mock_event)

        with patch("astrbot.core.event_bus.logger") as mock_logger:
            mock_logger.error.side_effect = lambda *args, **kwargs: error_logged.set()  # noqa: ARG001
            task = asyncio.create_task(event_bus.dispatch())
            try:
                await asyncio.wait_for(error_logged.wait(), timeout=1.0)
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

            # Verify error was logged for missing scheduler
            mock_logger.error.assert_called_once()
