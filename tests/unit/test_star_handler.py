"""Tests for StarHandlerRegistry and StarHandlerMetadata."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from astrbot.core.star.star_handler import (
    EventType,
    StarHandlerMetadata,
    StarHandlerRegistry,
)


@pytest.fixture
def registry():
    """Create a fresh StarHandlerRegistry."""
    return StarHandlerRegistry()


@pytest.fixture
def mock_handler():
    """Create a mock handler for testing."""

    def make_handler(
        event_type: EventType,
        full_name: str,
        module_path: str = "test_module",
        enabled: bool = True,
        priority: int = 0,
        extras_configs: dict | None = None,
    ) -> StarHandlerMetadata:
        handler = MagicMock(spec=StarHandlerMetadata)
        handler.event_type = event_type
        handler.handler_full_name = full_name
        handler.handler_name = full_name.split("_")[-1]
        handler.handler_module_path = module_path
        handler.enabled = enabled
        configs = extras_configs or {}
        if priority != 0:
            configs["priority"] = priority
        handler.extras_configs = configs
        return handler

    return make_handler


class TestStarHandlerRegistryAppend:
    """Tests for StarHandlerRegistry.append()."""

    def test_append_adds_to_map(self, registry, mock_handler):
        """Append adds handler to star_handlers_map."""
        handler = mock_handler(EventType.AdapterMessageEvent, "test_handler")
        registry.append(handler)
        assert registry.star_handlers_map["test_handler"] is handler

    def test_append_adds_to_list(self, registry, mock_handler):
        """Append adds handler to _handlers list."""
        handler = mock_handler(EventType.AdapterMessageEvent, "test_handler")
        registry.append(handler)
        assert handler in registry._handlers

    def test_append_sets_default_priority(self, registry, mock_handler):
        """Append sets default priority=0 if not specified."""
        handler = mock_handler(EventType.AdapterMessageEvent, "test_handler")
        registry.append(handler)
        assert handler.extras_configs["priority"] == 0

    def test_append_preserves_existing_priority(self, registry, mock_handler):
        """Append preserves explicitly set priority."""
        handler = mock_handler(
            EventType.AdapterMessageEvent,
            "test_handler",
            priority=5,
        )
        registry.append(handler)
        assert handler.extras_configs["priority"] == 5

    def test_append_sorts_by_priority_descending(self, registry, mock_handler):
        """Append keeps handlers sorted by priority (highest first)."""
        h1 = mock_handler(EventType.AdapterMessageEvent, "low_priority", priority=1)
        h5 = mock_handler(EventType.AdapterMessageEvent, "high_priority", priority=5)
        h3 = mock_handler(EventType.AdapterMessageEvent, "mid_priority", priority=3)
        registry.append(h1)
        registry.append(h5)
        registry.append(h3)
        # Should be sorted: high(5), mid(3), low(1)
        priorities = [h.extras_configs["priority"] for h in registry._handlers]
        assert priorities == [5, 3, 1]


class TestStarHandlerRegistryGetByEventType:
    """Tests for StarHandlerRegistry.get_handlers_by_event_type()."""

    def test_returns_handlers_matching_event_type(self, registry, mock_handler):
        """Returns only handlers matching the specified event type."""
        adapter_handler = mock_handler(EventType.AdapterMessageEvent, "adapter_h")
        llm_handler = mock_handler(EventType.OnLLMRequestEvent, "llm_h")
        registry.append(adapter_handler)
        registry.append(llm_handler)
        with patch("astrbot.core.star.star_handler.star_map") as mock_map:
            mock_map.get.return_value = MagicMock(activated=True, reserved=False)
            result = registry.get_handlers_by_event_type(EventType.AdapterMessageEvent)
        assert adapter_handler in result
        assert llm_handler not in result

    def test_excludes_disabled_handlers(self, registry, mock_handler):
        """Disabled handlers are excluded."""
        enabled_h = mock_handler(EventType.AdapterMessageEvent, "enabled", enabled=True)
        disabled_h = mock_handler(
            EventType.AdapterMessageEvent, "disabled", enabled=False
        )
        registry.append(enabled_h)
        registry.append(disabled_h)
        with patch("astrbot.core.star.star_handler.star_map") as mock_map:
            mock_map.get.return_value = MagicMock(activated=True, reserved=False)
            result = registry.get_handlers_by_event_type(
                EventType.AdapterMessageEvent, only_activated=True
            )
        assert enabled_h in result
        assert disabled_h not in result

    def test_only_activated_false_bypasses_star_map_check(self, registry, mock_handler):
        """only_activated=False bypasses star_map activation check but still checks handler.enabled."""
        enabled_h = mock_handler(EventType.AdapterMessageEvent, "enabled", enabled=True)
        disabled_h = mock_handler(
            EventType.AdapterMessageEvent, "disabled", enabled=False
        )
        registry.append(enabled_h)
        registry.append(disabled_h)
        result = registry.get_handlers_by_event_type(
            EventType.AdapterMessageEvent, only_activated=False
        )
        assert enabled_h in result
        # handler.enabled is still checked even with only_activated=False
        assert disabled_h not in result

    def test_plugin_not_activated_excluded(self, registry, mock_handler):
        """Handlers from deactivated plugins are excluded."""
        handler = mock_handler(
            EventType.AdapterMessageEvent, "plugin_h", module_path="mod"
        )
        registry.append(handler)
        with patch("astrbot.core.star.star_handler.star_map") as mock_map:
            mock_map.get.return_value = MagicMock(activated=False)
            result = registry.get_handlers_by_event_type(
                EventType.AdapterMessageEvent, only_activated=True
            )
        assert handler not in result

    def test_plugin_not_in_star_map_excluded(self, registry, mock_handler):
        """Handlers whose plugin is not in star_map are excluded."""
        handler = mock_handler(
            EventType.AdapterMessageEvent, "orphan_h", module_path="orphan"
        )
        registry.append(handler)
        with patch("astrbot.core.star.star_handler.star_map") as mock_map:
            mock_map.get.return_value = None
            result = registry.get_handlers_by_event_type(
                EventType.AdapterMessageEvent, only_activated=True
            )
        assert handler not in result

    def test_plugins_name_whitelist(self, registry, mock_handler):
        """plugins_name filters to specific plugin names."""
        handler1 = mock_handler(
            EventType.AdapterMessageEvent, "h1", module_path="plugin_a"
        )
        handler2 = mock_handler(
            EventType.AdapterMessageEvent, "h2", module_path="plugin_b"
        )
        registry.append(handler1)
        registry.append(handler2)

        def mock_get(path):
            m = MagicMock(activated=True, reserved=False)
            m.name = path  # set name as actual string attribute
            return m

        with patch("astrbot.core.star.star_handler.star_map") as mock_map:
            mock_map.get.side_effect = mock_get
            result = registry.get_handlers_by_event_type(
                EventType.AdapterMessageEvent,
                plugins_name=["plugin_a"],
            )
        assert handler1 in result
        assert handler2 not in result

    def test_plugins_name_wildcard_all(self, registry, mock_handler):
        """plugins_name=['*'] includes all handlers (bypasses whitelist but not activation check)."""
        h1 = mock_handler(EventType.AdapterMessageEvent, "h1", module_path="p1")
        h2 = mock_handler(EventType.AdapterMessageEvent, "h2", module_path="p2")
        registry.append(h1)
        registry.append(h2)
        with patch("astrbot.core.star.star_handler.star_map") as mock_map:
            mock_map.get.return_value = MagicMock(activated=True, reserved=False)
            result = registry.get_handlers_by_event_type(
                EventType.AdapterMessageEvent, plugins_name=["*"]
            )
        assert len(result) == 2

    def test_event_type_allowed_even_when_not_in_plugin_list(
        self, registry, mock_handler
    ):
        """Certain event types bypass the plugins_name filter."""
        handler = mock_handler(
            EventType.OnAstrBotLoadedEvent, "loaded_h", module_path="mod"
        )
        registry.append(handler)
        with patch("astrbot.core.star.star_handler.star_map") as mock_map:
            mock_map.get.return_value = MagicMock(
                name="mod", activated=True, reserved=False
            )
            # Should include even though plugin not in plugins_name list
            result = registry.get_handlers_by_event_type(
                EventType.OnAstrBotLoadedEvent, plugins_name=["other"]
            )
        assert handler in result

    def test_reserved_plugin_bypasses_whitelist(self, registry, mock_handler):
        """Reserved plugins bypass the plugins_name whitelist."""
        handler = mock_handler(
            EventType.AdapterMessageEvent, "reserved_h", module_path="core_mod"
        )
        registry.append(handler)
        with patch("astrbot.core.star.star_handler.star_map") as mock_map:
            mock_map.get.return_value = MagicMock(
                name="core", activated=True, reserved=True
            )
            result = registry.get_handlers_by_event_type(
                EventType.AdapterMessageEvent, plugins_name=["other"]
            )
        assert handler in result


class TestStarHandlerRegistryGetByFullName:
    """Tests for get_handler_by_full_name()."""

    def test_returns_handler_by_name(self, registry, mock_handler):
        """Returns the handler with the given full name."""
        h1 = mock_handler(EventType.AdapterMessageEvent, "handler_one")
        h2 = mock_handler(EventType.AdapterMessageEvent, "handler_two")
        registry.append(h1)
        registry.append(h2)
        result = registry.get_handler_by_full_name("handler_one")
        assert result is h1

    def test_returns_none_for_missing_name(self, registry):
        """Returns None for a name not in the registry."""
        result = registry.get_handler_by_full_name("nonexistent")
        assert result is None


class TestStarHandlerRegistryGetByModuleName:
    """Tests for get_handlers_by_module_name()."""

    def test_returns_handlers_for_module(self, registry, mock_handler):
        """Returns all handlers from a specific module."""
        h1 = mock_handler(EventType.AdapterMessageEvent, "m1_h1", module_path="mod_a")
        h2 = mock_handler(EventType.OnLLMRequestEvent, "m1_h2", module_path="mod_a")
        h3 = mock_handler(EventType.AdapterMessageEvent, "m2_h1", module_path="mod_b")
        registry.append(h1)
        registry.append(h2)
        registry.append(h3)
        result = registry.get_handlers_by_module_name("mod_a")
        assert h1 in result
        assert h2 in result
        assert h3 not in result

    def test_returns_empty_for_unknown_module(self, registry):
        """Returns empty list for a module with no handlers."""
        result = registry.get_handlers_by_module_name("unknown_module")
        assert result == []


class TestStarHandlerRegistryClear:
    """Tests for StarHandlerRegistry.clear()."""

    def test_clear_removes_all_handlers(self, registry, mock_handler):
        """clear() empties both maps and lists."""
        registry.append(mock_handler(EventType.AdapterMessageEvent, "h1"))
        registry.append(mock_handler(EventType.OnLLMRequestEvent, "h2"))
        registry.clear()
        assert len(registry.star_handlers_map) == 0
        assert len(registry._handlers) == 0


class TestStarHandlerRegistryRemove:
    """Tests for StarHandlerRegistry.remove()."""

    def test_remove_existing_handler(self, registry, mock_handler):
        """remove() removes the specified handler."""
        h1 = mock_handler(EventType.AdapterMessageEvent, "h1")
        h2 = mock_handler(EventType.AdapterMessageEvent, "h2")
        registry.append(h1)
        registry.append(h2)
        registry.remove(h1)
        assert "h1" not in registry.star_handlers_map
        assert h1 not in registry._handlers
        assert "h2" in registry.star_handlers_map

    def test_remove_nonexistent_no_error(self, registry, mock_handler):
        """remove() of non-existent handler does not raise."""
        handler = mock_handler(EventType.AdapterMessageEvent, "h1")
        registry.remove(handler)  # Should not raise


class TestStarHandlerRegistryIteration:
    """Tests for __iter__ and __len__."""

    def test_iter_yields_handlers(self, registry, mock_handler):
        """__iter__ yields all handlers in priority order."""
        h1 = mock_handler(EventType.AdapterMessageEvent, "h1")
        h2 = mock_handler(EventType.AdapterMessageEvent, "h2")
        registry.append(h1)
        registry.append(h2)
        result = list(registry)
        assert h1 in result
        assert h2 in result

    def test_len_returns_count(self, registry, mock_handler):
        """__len__ returns number of handlers."""
        assert len(registry) == 0
        registry.append(mock_handler(EventType.AdapterMessageEvent, "h1"))
        assert len(registry) == 1
        registry.append(mock_handler(EventType.AdapterMessageEvent, "h2"))
        assert len(registry) == 2


class TestStarHandlerMetadataPriority:
    """Tests for StarHandlerMetadata.__lt__()."""

    def test_lt_lower_priority(self):
        """Handler with lower priority is 'less than' higher priority."""
        h_low = StarHandlerMetadata(
            event_type=EventType.AdapterMessageEvent,
            handler_full_name="low",
            handler_name="low",
            handler_module_path="m",
            handler=MagicMock(),
            event_filters=[],
            extras_configs={"priority": 1},
        )
        h_high = StarHandlerMetadata(
            event_type=EventType.AdapterMessageEvent,
            handler_full_name="high",
            handler_name="high",
            handler_module_path="m",
            handler=MagicMock(),
            event_filters=[],
            extras_configs={"priority": 5},
        )
        assert (h_low < h_high) is True
        assert (h_high < h_low) is False

    def test_lt_default_priority(self):
        """Handler with default priority (0) is less than non-zero."""
        h_default = StarHandlerMetadata(
            event_type=EventType.AdapterMessageEvent,
            handler_full_name="default",
            handler_name="default",
            handler_module_path="m",
            handler=MagicMock(),
            event_filters=[],
        )
        h_nonzero = StarHandlerMetadata(
            event_type=EventType.AdapterMessageEvent,
            handler_full_name="nonzero",
            handler_name="nonzero",
            handler_module_path="m",
            handler=MagicMock(),
            event_filters=[],
            extras_configs={"priority": 10},
        )
        assert (h_default < h_nonzero) is True

    def test_lt_same_priority(self):
        """Handlers with same priority return False for both comparisons."""
        h1 = StarHandlerMetadata(
            event_type=EventType.AdapterMessageEvent,
            handler_full_name="h1",
            handler_name="h1",
            handler_module_path="m",
            handler=MagicMock(),
            event_filters=[],
            extras_configs={"priority": 5},
        )
        h2 = StarHandlerMetadata(
            event_type=EventType.AdapterMessageEvent,
            handler_full_name="h2",
            handler_name="h2",
            handler_module_path="m",
            handler=MagicMock(),
            event_filters=[],
            extras_configs={"priority": 5},
        )
        assert (h1 < h2) is False
        assert (h2 < h1) is False
