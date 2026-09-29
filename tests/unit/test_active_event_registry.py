from types import SimpleNamespace
from unittest.mock import Mock

from astrbot.core.pipeline.process_stage.follow_up import (
    register_active_runner,
    unregister_active_runner,
)
from astrbot.core.utils.active_event_registry import (
    ActiveEventRegistry,
    active_event_registry,
)


class StubEvent:
    """Minimal event implementation used by ActiveEventRegistry tests."""

    def __init__(self, umo: str) -> None:
        self.unified_msg_origin = umo
        self.extras: dict[str, object] = {}

    def set_extra(self, key: str, value: object) -> None:
        """Store an event extra.

        Args:
            key: Extra field name.
            value: Extra field value.
        """
        self.extras[key] = value


def test_request_agent_stop_invokes_registered_callback() -> None:
    """Agent stop requests immediately invoke the active execution callback."""
    registry = ActiveEventRegistry()
    event = StubEvent("webchat:FriendMessage:webchat!alice!session")
    callback = Mock()
    registry.register(event)
    registry.register_agent_stop_callback(event, callback)

    stopped_count = registry.request_agent_stop_all(event.unified_msg_origin)

    assert stopped_count == 1
    assert event.extras["agent_stop_requested"] is True
    callback.assert_called_once_with()


def test_unregister_removes_agent_stop_callback() -> None:
    """Unregistered events cannot retain stale Agent cancellation callbacks."""
    registry = ActiveEventRegistry()
    event = StubEvent("webchat:FriendMessage:webchat!alice!session")
    callback = Mock()
    registry.register(event)
    registry.register_agent_stop_callback(event, callback)

    registry.unregister(event)
    stopped_count = registry.request_agent_stop_all(event.unified_msg_origin)

    assert stopped_count == 0
    callback.assert_not_called()


def test_active_runner_wires_immediate_stop_callback() -> None:
    """Active Runner registration connects registry stop to Runner cancellation."""
    event = StubEvent("webchat:FriendMessage:webchat!alice!runner-session")
    runner = SimpleNamespace(
        run_context=SimpleNamespace(context=SimpleNamespace(event=event)),
        request_stop=Mock(),
    )
    active_event_registry.register(event)
    register_active_runner(event.unified_msg_origin, runner)

    try:
        stopped_count = active_event_registry.request_agent_stop_all(
            event.unified_msg_origin
        )

        assert stopped_count == 1
        runner.request_stop.assert_called_once_with()
    finally:
        unregister_active_runner(event.unified_msg_origin, runner)
        active_event_registry.unregister(event)
