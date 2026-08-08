from astrbot.core.utils.active_event_registry import ActiveEventRegistry


class _Event:
    def __init__(self, umo: str) -> None:
        self.unified_msg_origin = umo
        self.extras: dict[str, object] = {}
        self.stopped = False

    def set_extra(self, key: str, value: object) -> None:
        self.extras[key] = value

    def stop_event(self) -> None:
        self.stopped = True


def test_request_agent_stop_invokes_all_callbacks_despite_one_failure():
    registry = ActiveEventRegistry()
    first = _Event("webchat:session")
    second = _Event("webchat:session")
    called: list[str] = []

    def broken_callback() -> None:
        called.append("broken")
        raise RuntimeError("callback failure")

    registry.register(first)
    registry.register(second)
    registry.register_agent_stop_callback(first, broken_callback)
    registry.register_agent_stop_callback(second, lambda: called.append("second"))

    assert registry.request_agent_stop_all("webchat:session") == 2
    assert first.extras["agent_stop_requested"] is True
    assert second.extras["agent_stop_requested"] is True
    assert set(called) == {"broken", "second"}


def test_unregister_agent_stop_callback_and_event_release_runner_controls():
    registry = ActiveEventRegistry()
    event = _Event("webchat:session")
    called: list[str] = []

    def callback() -> None:
        called.append("stop")

    registry.register(event)
    registry.register_agent_stop_callback(event, callback)

    registry.unregister_agent_stop_callback(event, callback)
    registry.request_agent_stop_all("webchat:session")
    assert called == []

    registry.register_agent_stop_callback(event, callback)
    registry.unregister(event)
    assert registry.request_agent_stop_all("webchat:session") == 0
    assert called == []
