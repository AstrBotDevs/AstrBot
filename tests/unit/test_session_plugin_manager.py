"""Tests for SessionPluginManager session-level plugin disable rules."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.pipeline.context_utils import call_event_hook
from astrbot.core.star.session_plugin_manager import SessionPluginManager
from astrbot.core.star.star_handler import EventType

UMO = "test-platform:GroupMessage:12345"


def make_event() -> MagicMock:
    """Create a mock message event bound to a fixed session."""
    event = MagicMock()
    event.unified_msg_origin = UMO
    event._extras = {}
    event.get_extra.side_effect = lambda key=None, default=None: event._extras.get(
        key,
        default,
    )
    event.set_extra.side_effect = lambda key, value: event._extras.__setitem__(
        key,
        value,
    )
    event.plugins_name = None
    event.is_stopped.return_value = False
    return event


def make_handler(name: str, plugin_module: str) -> tuple[MagicMock, list[str]]:
    """Create a mock event handler metadata belonging to a plugin module.

    handler.handler is a real coroutine function so that
    inspect.iscoroutinefunction() accepts it inside call_event_hook.
    Returns the handler and a call log list shared by the coroutine.
    """
    handler = MagicMock()
    handler.handler_name = name
    handler.handler_module_path = plugin_module
    log: list[str] = []

    async def _invoke(event, *args, **kwargs):
        log.append(name)

    handler.handler = _invoke
    return handler, log


@pytest.mark.asyncio
async def test_get_disabled_plugins_reads_and_caches(monkeypatch):
    """Disabled plugin list is read from preferences and cached on the event."""
    event = make_event()
    mock_sp = MagicMock()
    mock_sp.get_async = AsyncMock(
        return_value={UMO: {"disabled_plugins": ["astrbot_meme_plugin"]}}
    )
    monkeypatch.setattr(
        "astrbot.core.star.session_plugin_manager.sp",
        mock_sp,
    )

    first = await SessionPluginManager.get_disabled_plugins(event)
    second = await SessionPluginManager.get_disabled_plugins(event)

    assert first == {"astrbot_meme_plugin"}
    assert second == {"astrbot_meme_plugin"}
    mock_sp.get_async.assert_awaited_once()

    assert event._extras["session_disabled_plugins"] == {"astrbot_meme_plugin"}


@pytest.mark.asyncio
async def test_get_disabled_plugins_returns_empty_when_no_config(monkeypatch):
    """No session config means no disabled plugins."""
    event = make_event()
    mock_sp = MagicMock()
    mock_sp.get_async = AsyncMock(return_value={})
    monkeypatch.setattr(
        "astrbot.core.star.session_plugin_manager.sp",
        mock_sp,
    )

    assert await SessionPluginManager.get_disabled_plugins(event) == set()


@pytest.mark.asyncio
async def test_filter_handlers_by_session_skips_disabled_plugin(monkeypatch):
    """Handlers of plugins disabled in the session are filtered out."""
    event = make_event()
    handler, _ = make_handler("on_llm_request", "astrbot_meme_plugin")
    mock_sp = MagicMock()
    mock_sp.get_async = AsyncMock(
        return_value={UMO: {"disabled_plugins": ["astrbot_meme_plugin"]}}
    )
    monkeypatch.setattr(
        "astrbot.core.star.session_plugin_manager.sp",
        mock_sp,
    )
    mock_plugin = MagicMock()
    mock_plugin.name = "astrbot_meme_plugin"
    mock_plugin.reserved = False
    monkeypatch.setattr(
        "astrbot.core.star.star.star_map",
        {"astrbot_meme_plugin": mock_plugin},
    )

    filtered = await SessionPluginManager.filter_handlers_by_session(event, [handler])

    assert filtered == []


@pytest.mark.asyncio
async def test_call_event_hook_skips_disabled_plugin_hook(monkeypatch):
    """call_event_hook does not invoke hooks of session-disabled plugins."""
    event = make_event()
    disabled_handler, disabled_log = make_handler(
        "on_llm_request",
        "astrbot_meme_plugin",
    )
    enabled_handler, enabled_log = make_handler(
        "on_llm_request",
        "astrbot_other_plugin",
    )

    mock_registry = MagicMock()
    mock_registry.get_handlers_by_event_type.return_value = [
        disabled_handler,
        enabled_handler,
    ]
    monkeypatch.setattr(
        "astrbot.core.pipeline.context_utils.star_handlers_registry",
        mock_registry,
    )

    mock_plugin_disabled = MagicMock()
    mock_plugin_disabled.name = "astrbot_meme_plugin"
    mock_plugin_disabled.reserved = False
    mock_plugin_enabled = MagicMock()
    mock_plugin_enabled.name = "astrbot_other_plugin"
    mock_plugin_enabled.reserved = False
    monkeypatch.setattr(
        "astrbot.core.star.star.star_map",
        {
            "astrbot_meme_plugin": mock_plugin_disabled,
            "astrbot_other_plugin": mock_plugin_enabled,
        },
    )
    monkeypatch.setattr(
        "astrbot.core.pipeline.context_utils.star_map",
        {
            "astrbot_meme_plugin": mock_plugin_disabled,
            "astrbot_other_plugin": mock_plugin_enabled,
        },
    )

    mock_sp = MagicMock()
    mock_sp.get_async = AsyncMock(
        return_value={UMO: {"disabled_plugins": ["astrbot_meme_plugin"]}}
    )
    monkeypatch.setattr(
        "astrbot.core.star.session_plugin_manager.sp",
        mock_sp,
    )

    await call_event_hook(event, EventType.OnLLMRequestEvent, None)

    assert disabled_log == []
    assert enabled_log == ["on_llm_request"]
