from types import SimpleNamespace

import pytest

from astrbot.core.pipeline import context_utils
from astrbot.core.star.star_handler import EventType


@pytest.mark.asyncio
async def test_after_message_sent_runs_all_cleanup_hooks_when_event_stopped(
    monkeypatch,
) -> None:
    calls: list[str] = []

    async def release_route(event) -> None:
        calls.append("route")

    async def release_chat_lock(event) -> None:
        calls.append("chat")

    handlers = [
        SimpleNamespace(
            handler=release_route,
            handler_module_path="route_plugin",
            handler_name="release_route",
        ),
        SimpleNamespace(
            handler=release_chat_lock,
            handler_module_path="chat_plugin",
            handler_name="release_chat_lock",
        ),
    ]
    monkeypatch.setattr(
        context_utils.star_handlers_registry,
        "get_handlers_by_event_type",
        lambda *args, **kwargs: handlers,
    )
    monkeypatch.setitem(
        context_utils.star_map, "route_plugin", SimpleNamespace(name="route")
    )
    monkeypatch.setitem(
        context_utils.star_map, "chat_plugin", SimpleNamespace(name="chat")
    )
    event = SimpleNamespace(plugins_name=None, is_stopped=lambda: True)

    stopped = await context_utils.call_event_hook(
        event, EventType.OnAfterMessageSentEvent
    )

    assert stopped is True
    assert calls == ["route", "chat"]


@pytest.mark.asyncio
async def test_normal_hook_still_short_circuits_when_event_stopped(monkeypatch) -> None:
    calls: list[str] = []

    async def first(event) -> None:
        calls.append("first")

    async def second(event) -> None:
        calls.append("second")

    handlers = [
        SimpleNamespace(
            handler=first,
            handler_module_path="first_plugin",
            handler_name="first",
        ),
        SimpleNamespace(
            handler=second,
            handler_module_path="second_plugin",
            handler_name="second",
        ),
    ]
    monkeypatch.setattr(
        context_utils.star_handlers_registry,
        "get_handlers_by_event_type",
        lambda *args, **kwargs: handlers,
    )
    monkeypatch.setitem(
        context_utils.star_map, "first_plugin", SimpleNamespace(name="first")
    )
    monkeypatch.setitem(
        context_utils.star_map, "second_plugin", SimpleNamespace(name="second")
    )
    event = SimpleNamespace(plugins_name=None, is_stopped=lambda: True)

    stopped = await context_utils.call_event_hook(event, EventType.OnLLMResponseEvent)

    assert stopped is True
    assert calls == ["first"]
