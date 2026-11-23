"""Handler dispatch honors priority, activation, filtering, and removal."""

import pytest

from astrbot.core.star import star_handler
from astrbot.core.star.star import StarMetadata
from astrbot.core.star.star_handler import (
    EventType,
    StarHandlerMetadata,
    StarHandlerRegistry,
)


@pytest.fixture
def registry(monkeypatch):
    registry = StarHandlerRegistry()
    plugins = {}
    monkeypatch.setattr(star_handler, "star_map", plugins)

    def add(
        name,
        *,
        priority=0,
        activated=True,
        enabled=True,
        reserved=False,
        event_type=EventType.AdapterMessageEvent,
    ):
        async def handler(event):
            return name

        module = f"data.plugins.{name}.main"
        metadata = StarHandlerMetadata(
            event_type,
            f"{module}_handler",
            "handler",
            module,
            handler,
            [],
            extras_configs={"priority": priority},
            enabled=enabled,
        )
        plugins[module] = StarMetadata(
            name=name, module_path=module, activated=activated, reserved=reserved
        )
        registry.append(metadata)
        return metadata

    return registry, add


def test_dispatch_order_and_lookup_share_the_same_metadata(registry):
    handlers, add = registry
    low, first, second = (
        add("low", priority=-1),
        add("first", priority=5),
        add("second", priority=5),
    )
    assert handlers.get_handlers_by_event_type(EventType.AdapterMessageEvent) == [
        first,
        second,
        low,
    ]
    assert handlers.get_handler_by_full_name(first.handler_full_name) is first
    assert handlers.get_handlers_by_module_name(second.handler_module_path) == [second]


def test_activation_and_enabled_filters_are_independent(registry):
    handlers, add = registry
    active = add("active")
    inactive = add("inactive", activated=False)
    add("disabled", enabled=False)
    add("other_event", event_type=EventType.OnAgentDoneEvent)
    assert handlers.get_handlers_by_event_type(EventType.AdapterMessageEvent) == [
        active
    ]
    assert handlers.get_handlers_by_event_type(
        EventType.AdapterMessageEvent, only_activated=False
    ) == [active, inactive]


def test_plugin_allowlist_preserves_reserved_handlers(registry):
    handlers, add = registry
    permitted, reserved, other = (
        add("permitted"),
        add("reserved", reserved=True),
        add("other"),
    )
    assert handlers.get_handlers_by_event_type(
        EventType.AdapterMessageEvent, plugins_name=["permitted"]
    ) == [permitted, reserved]
    assert handlers.get_handlers_by_event_type(
        EventType.AdapterMessageEvent, plugins_name=[]
    ) == [reserved]
    assert handlers.get_handlers_by_event_type(
        EventType.AdapterMessageEvent, plugins_name=["*"]
    ) == [permitted, reserved, other]


@pytest.mark.parametrize(
    "event_type",
    [
        EventType.OnAstrBotLoadedEvent,
        EventType.OnPlatformLoadedEvent,
        EventType.OnPluginLoadedEvent,
        EventType.OnPluginUnloadedEvent,
    ],
)
def test_lifecycle_notifications_are_not_session_allowlisted(registry, event_type):
    handlers, add = registry
    handler = add("lifecycle", event_type=event_type)
    assert handlers.get_handlers_by_event_type(event_type, plugins_name=[]) == [handler]


def test_remove_and_clear_update_both_dispatch_and_lookup(registry):
    handlers, add = registry
    first, second = add("first"), add("second")
    handlers.remove(first)
    assert handlers.get_handler_by_full_name(first.handler_full_name) is None
    assert list(handlers) == [second]
    handlers.clear()
    assert len(handlers) == 0
    assert handlers.get_handler_by_full_name(second.handler_full_name) is None
