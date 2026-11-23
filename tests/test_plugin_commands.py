"""Plugin commands delegate once and enforce demo and missing-manager guards."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.builtin_stars.builtin_commands.commands import plugin as plugin_module


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("command", "method"),
    [("plugin_on", "turn_on_plugin"), ("plugin_off", "turn_off_plugin")],
)
@pytest.mark.parametrize("demo", [False, True])
async def test_plugin_toggle_honors_demo_mode(
    monkeypatch, command, method, demo
) -> None:
    manager = SimpleNamespace(turn_on_plugin=AsyncMock(), turn_off_plugin=AsyncMock())
    event = SimpleNamespace(set_result=Mock())
    monkeypatch.setattr(plugin_module, "DEMO_MODE", demo)
    await getattr(
        plugin_module.PluginCommands(SimpleNamespace(_star_manager=manager)), command
    )(event, "weather")
    if demo:
        manager.turn_on_plugin.assert_not_awaited()
        manager.turn_off_plugin.assert_not_awaited()
    else:
        getattr(manager, method).assert_awaited_once_with("weather")
        other = "turn_off_plugin" if method == "turn_on_plugin" else "turn_on_plugin"
        getattr(manager, other).assert_not_awaited()
    assert event.set_result.call_args.args[0].chain[0].text


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["plugin_on", "plugin_off"])
async def test_missing_plugin_manager_returns_a_result(
    monkeypatch, command: str
) -> None:
    monkeypatch.setattr(plugin_module, "DEMO_MODE", False)
    event = SimpleNamespace(set_result=Mock())
    await getattr(
        plugin_module.PluginCommands(SimpleNamespace(_star_manager=None)), command
    )(event, "weather")
    assert event.set_result.call_count == 1
    assert event.set_result.call_args.args[0].chain[0].text


@pytest.mark.asyncio
async def test_plugin_listing_reports_activation_without_mutating_metadata() -> None:
    plugins = [
        SimpleNamespace(name="enabled", author="author", desc="first", activated=True),
        SimpleNamespace(
            name="disabled", author="author", desc="second", activated=False
        ),
    ]
    event = SimpleNamespace(set_result=Mock())
    context = SimpleNamespace(get_all_stars=lambda: plugins)
    await plugin_module.PluginCommands(context).plugin_ls(event)
    text = event.set_result.call_args.args[0].chain[0].text
    assert "enabled" in text and "disabled" in text
    assert text.index("enabled") < text.index("disabled")
    assert [plugin.activated for plugin in plugins] == [True, False]
