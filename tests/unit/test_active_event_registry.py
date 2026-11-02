import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

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
        self.stopped = False

    def get_extra(self, key: str) -> object:
        return self.extras.get(key)

    def stop_event(self) -> None:
        self.stopped = True

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


@pytest.mark.asyncio
@pytest.mark.parametrize("fails", [False, True])
async def test_background_completion_releases_registry(fails: bool) -> None:
    registry = ActiveEventRegistry()
    event = StubEvent("session")

    async def run() -> None:
        if fails:
            raise RuntimeError("tool failed")

    task = asyncio.create_task(run())
    registry.register_background_task(event, task)
    await asyncio.gather(task, return_exceptions=True)
    assert registry.request_agent_stop_all("session") == 0
    assert not registry._background_tasks
    assert not registry._background_cancel_requested


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_method", ["stop_all", "request_agent_stop_all"])
async def test_background_stop_isolates_owners_and_prevents_late_tasks(stop_method):
    registry = ActiveEventRegistry()
    event, excluded, other = (
        StubEvent("session"),
        StubEvent("session"),
        StubEvent("other"),
    )
    owners = (event, event, excluded, other)
    tasks = [asyncio.create_task(asyncio.Event().wait()) for _ in owners]
    registry.register(event)
    for owner, task in zip(owners, tasks):
        registry.register_background_task(owner, task)
    registry.unregister(event)
    try:
        assert getattr(registry, stop_method)("session", exclude=excluded) == 1
        await asyncio.gather(*tasks[:2], return_exceptions=True)
        assert all(task.cancelled() for task in tasks[:2])
        assert all(not task.done() for task in tasks[2:])
        assert event.stopped == (stop_method == "stop_all")
        assert not excluded.stopped and not other.stopped

        wakeup = StubEvent("session")
        signal = registry.get_background_stop_signal(event)
        wakeup.set_extra("_background_stop_signal", signal)
        assert registry.get_background_stop_signal(wakeup) is signal
        late_task = asyncio.create_task(asyncio.sleep(0))
        tasks.append(late_task)
        registry.register_background_task(wakeup, late_task)
        await asyncio.gather(late_task, return_exceptions=True)
        assert late_task.cancelled()

        fresh = StubEvent("session")
        fresh_task = asyncio.create_task(asyncio.Event().wait())
        tasks.append(fresh_task)
        registry.register_background_task(fresh, fresh_task)
        assert not registry.get_background_stop_signal(fresh).is_set()
        assert not fresh_task.done()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    assert not registry._background_tasks


@pytest.mark.asyncio
async def test_repeated_stop_preserves_background_cleanup() -> None:
    registry = ActiveEventRegistry()
    event = StubEvent("session")
    started, cleaning, release, cleaned = (asyncio.Event() for _ in range(4))

    async def run() -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaning.set()
            await release.wait()
            cleaned.set()

    task = asyncio.create_task(run())
    registry.register_background_task(event, task)
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        assert registry.request_agent_stop_all("session") == 1
        await asyncio.wait_for(cleaning.wait(), timeout=1)
        assert registry.request_agent_stop_all("session") == 1
    finally:
        release.set()
        await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), timeout=1)
    assert task.cancelled() and cleaned.is_set()
    assert not registry._background_cancel_requested
