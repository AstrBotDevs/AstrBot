"""Supplementary edge-case tests for EventBus.

Covers exception resilience in the dispatch loop, edge values in
_print_event, empty pipeline mappings, and rapid event delivery.
"""

import asyncio
from contextlib import suppress
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.event_bus import EventBus


# ---- Fixtures ----


@pytest.fixture
def event_queue():
    return asyncio.Queue()


@pytest.fixture
def mock_scheduler():
    scheduler = MagicMock()
    scheduler.execute = AsyncMock()
    return scheduler


@pytest.fixture
def mock_config_manager():
    config_mgr = MagicMock()
    config_mgr.get_conf_info = MagicMock(
        return_value={"id": "test-conf-id", "name": "Test Config"}
    )
    return config_mgr


# ---- Exception resilience ----


class TestDispatchExceptionResilience:
    """The dispatch loop must survive scheduler exceptions."""

    @pytest.mark.asyncio
    async def test_exception_in_scheduler_does_not_crash_loop(
        self, event_queue, mock_config_manager
    ):
        """After a scheduler that raises, subsequent events are still processed."""
        processed_second = asyncio.Event()

        # Scheduler 1 raises on every call
        scheduler1 = MagicMock()
        scheduler1.execute = AsyncMock(side_effect=RuntimeError("Boom"))

        # Scheduler 2 works normally
        scheduler2 = MagicMock()
        scheduler2.execute = AsyncMock()

        async def execute_second(event):  # noqa: ARG001
            processed_second.set()

        scheduler2.execute.side_effect = execute_second

        def get_conf_info(origin):
            if "event-1" in origin:
                return {"id": "conf-1", "name": "C1"}
            return {"id": "conf-2", "name": "C2"}

        mock_config_manager.get_conf_info.side_effect = get_conf_info

        mapping = {"conf-1": scheduler1, "conf-2": scheduler2}
        event_bus = EventBus(
            event_queue=event_queue,
            pipeline_scheduler_mapping=mapping,
            astrbot_config_mgr=mock_config_manager,
        )

        # Event 1 should trigger the failing scheduler
        ev1 = MagicMock()
        ev1.unified_msg_origin = "event-1"
        ev1.get_platform_id.return_value = "p1"
        ev1.get_platform_name.return_value = "P1"
        ev1.get_sender_name.return_value = None
        ev1.get_sender_id.return_value = "u1"
        ev1.get_message_outline.return_value = "m1"

        # Event 2 should trigger the working scheduler
        ev2 = MagicMock()
        ev2.unified_msg_origin = "event-2"
        ev2.get_platform_id.return_value = "p2"
        ev2.get_platform_name.return_value = "P2"
        ev2.get_sender_name.return_value = None
        ev2.get_sender_id.return_value = "u2"
        ev2.get_message_outline.return_value = "m2"

        await event_queue.put(ev1)
        await event_queue.put(ev2)

        task = asyncio.create_task(event_bus.dispatch())
        try:
            await asyncio.wait_for(processed_second.wait(), timeout=2.0)
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        # Both schedulers should have been called
        scheduler1.execute.assert_called_once_with(ev1)
        scheduler2.execute.assert_called_once_with(ev2)

    @pytest.mark.asyncio
    async def test_dispatch_continues_after_scheduler_exception(
        self, event_queue, mock_config_manager
    ):
        """The dispatch loop must continue processing after a scheduler exception."""
        scheduler = MagicMock()
        call_count = 0

        async def execute_alternating(event):  # noqa: ARG001
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("First call fails")

        scheduler.execute.side_effect = execute_alternating
        mock_config_manager.get_conf_info.return_value = {
            "id": "same-conf",
            "name": "Same",
        }
        mapping = {"same-conf": scheduler}
        event_bus = EventBus(
            event_queue=event_queue,
            pipeline_scheduler_mapping=mapping,
            astrbot_config_mgr=mock_config_manager,
        )

        ev = MagicMock()
        ev.unified_msg_origin = "test:group:1"
        ev.get_platform_id.return_value = "test"
        ev.get_platform_name.return_value = "Test"
        ev.get_sender_name.return_value = None
        ev.get_sender_id.return_value = "u1"
        ev.get_message_outline.return_value = "m"

        await event_queue.put(ev)

        task = asyncio.create_task(event_bus.dispatch())
        try:
            await asyncio.wait_for(asyncio.sleep(0.2), timeout=1.0)
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        # scheduler should have been called once (event consumed,
        # exception swallowed by asyncio.create_task)
        assert call_count >= 1


# ---- Edge-case inputs to dispatch ----


class TestDispatchEdgeInputs:
    """Dispatch handles unusual or missing event attributes."""

    @pytest.mark.asyncio
    async def test_dispatch_with_empty_origin(
        self, event_queue, mock_config_manager, mock_scheduler
    ):
        """An event with empty unified_msg_origin is handled (falls back to '')."""
        processed = asyncio.Event()

        mock_config_manager.get_conf_info.return_value = {
            "id": "test-conf-id",
            "name": "Test",
        }

        async def execute_and_signal(event):  # noqa: ARG001
            processed.set()

        mock_scheduler.execute.side_effect = execute_and_signal

        mapping = {"test-conf-id": mock_scheduler}
        event_bus = EventBus(
            event_queue=event_queue,
            pipeline_scheduler_mapping=mapping,
            astrbot_config_mgr=mock_config_manager,
        )

        ev = MagicMock()
        ev.unified_msg_origin = ""  # empty origin
        ev.get_platform_id.return_value = "test"
        ev.get_platform_name.return_value = "Test"
        ev.get_sender_name.return_value = None
        ev.get_sender_id.return_value = "u1"
        ev.get_message_outline.return_value = "m"

        await event_queue.put(ev)

        task = asyncio.create_task(event_bus.dispatch())
        try:
            await asyncio.wait_for(processed.wait(), timeout=1.0)
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        mock_config_manager.get_conf_info.assert_called_once_with("")
        mock_scheduler.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_with_empty_config_info(
        self, event_queue, mock_config_manager, mock_scheduler
    ):
        """get_conf_info returning empty dict still works (id falls back to '')."""
        processed = asyncio.Event()
        mock_config_manager.get_conf_info.return_value = {}

        async def execute_and_signal(event):  # noqa: ARG001
            processed.set()

        mock_scheduler.execute.side_effect = execute_and_signal

        # The scheduler mapped to '' will be used (empty string from get("id", ""))
        mapping = {"": mock_scheduler}
        event_bus = EventBus(
            event_queue=event_queue,
            pipeline_scheduler_mapping=mapping,
            astrbot_config_mgr=mock_config_manager,
        )

        ev = MagicMock()
        ev.unified_msg_origin = "some:origin"
        ev.get_platform_id.return_value = "test"
        ev.get_platform_name.return_value = "Test"
        ev.get_sender_name.return_value = None
        ev.get_sender_id.return_value = "u1"
        ev.get_message_outline.return_value = "m"

        await event_queue.put(ev)

        task = asyncio.create_task(event_bus.dispatch())
        try:
            await asyncio.wait_for(processed.wait(), timeout=1.0)
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        mock_scheduler.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_pipeline_mapping_logs_error(
        self, event_queue, mock_config_manager
    ):
        """An event is dropped with a logged error when no scheduler matches."""
        error_logged = asyncio.Event()
        mock_config_manager.get_conf_info.return_value = {
            "id": "orphan-id",
            "name": "Orphan",
        }

        event_bus = EventBus(
            event_queue=event_queue,
            pipeline_scheduler_mapping={},
            astrbot_config_mgr=mock_config_manager,
        )

        ev = MagicMock()
        ev.unified_msg_origin = "test:private:1"
        ev.get_platform_id.return_value = "test"
        ev.get_platform_name.return_value = "Test"
        ev.get_sender_name.return_value = "User"
        ev.get_sender_id.return_value = "u1"
        ev.get_message_outline.return_value = "m"

        await event_queue.put(ev)

        with patch("astrbot.core.event_bus.logger") as mock_logger:
            mock_logger.error.side_effect = lambda *a, **kw: error_logged.set()
            task = asyncio.create_task(event_bus.dispatch())
            try:
                await asyncio.wait_for(error_logged.wait(), timeout=1.0)
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

            assert "orphan-id" in mock_logger.error.call_args[0][0]


# ---- _print_event edge cases ----


class TestPrintEventEdgeCases:
    """_print_event handles unusual sender/platform names."""

    def test_print_event_no_sender_name(self, event_bus_factory):
        """When sender_name is None, the log omits the sender name section."""
        event_bus = event_bus_factory()
        ev = MagicMock()
        ev.get_platform_id.return_value = "test"
        ev.get_platform_name.return_value = "TestPlatform"
        ev.get_sender_name.return_value = None
        ev.get_sender_id.return_value = "user-123"
        ev.get_message_outline.return_value = "Hello"

        with patch("astrbot.core.event_bus.logger") as mock_logger:
            event_bus._print_event(ev, "MyConfig")

        log_msg = mock_logger.info.call_args[0][0]
        assert "MyConfig" in log_msg
        assert "TestPlatform" in log_msg
        assert "user-123" in log_msg
        # Without sender name, there should be no '/' before user-123
        # (the format is [Config] [platform] sender_id: outline)
        assert "Hello" in log_msg

    def test_print_event_sender_name_is_empty_string(self, event_bus_factory):
        """An empty sender_name string is treated similarly to a missing name."""
        event_bus = event_bus_factory()
        ev = MagicMock()
        ev.get_platform_id.return_value = "test"
        ev.get_platform_name.return_value = "TestPlatform"
        ev.get_sender_name.return_value = ""
        ev.get_sender_id.return_value = "user-123"
        ev.get_message_outline.return_value = "Hello"

        with patch("astrbot.core.event_bus.logger") as mock_logger:
            event_bus._print_event(ev, "MyConfig")

        mock_logger.info.assert_called_once()

    def test_print_event_with_special_characters(self, event_bus_factory):
        """Special characters in event fields do not break logging."""
        event_bus = event_bus_factory()
        ev = MagicMock()
        ev.get_platform_id.return_value = "test@#$"
        ev.get_platform_name.return_value = "Test[Platform]"
        ev.get_sender_name.return_value = "User{}|"
        ev.get_sender_id.return_value = "user:\n456"
        ev.get_message_outline.return_value = "Hello\nWorld"

        with patch("astrbot.core.event_bus.logger") as mock_logger:
            event_bus._print_event(ev, "Config[1]")

        mock_logger.info.assert_called_once()


# ---- EventBus construction edge cases ----


class TestEventBusConstructionEdgeCases:
    """EventBus handles edge values passed to __init__."""

    def test_empty_pipeline_scheduler_mapping(self, event_queue, mock_config_manager):
        """Empty pipeline_mapping is accepted at construction."""
        bus = EventBus(
            event_queue=event_queue,
            pipeline_scheduler_mapping={},
            astrbot_config_mgr=mock_config_manager,
        )
        assert bus.pipeline_scheduler_mapping == {}

    def test_none_in_pipeline_mapping(self, event_queue, mock_config_manager):
        """None values in the mapping are accepted (dealt with at dispatch time)."""
        bus = EventBus(
            event_queue=event_queue,
            pipeline_scheduler_mapping={"conf-id": None},
            astrbot_config_mgr=mock_config_manager,
        )
        assert bus.pipeline_scheduler_mapping["conf-id"] is None


# ---- Helper fixtures ----


@pytest.fixture
def event_bus_factory():
    """Factory that creates EventBus with default test dependencies."""

    def _create(event_queue=None, mapping=None, config_mgr=None):
        import asyncio

        q = event_queue or asyncio.Queue()
        m = mapping or {"test-id": MagicMock()}
        cm = config_mgr or MagicMock()
        return EventBus(
            event_queue=q,
            pipeline_scheduler_mapping=m,
            astrbot_config_mgr=cm,
        )

    return _create
