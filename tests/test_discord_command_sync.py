import asyncio
from unittest.mock import MagicMock, Mock

import pytest

from tests.fixtures.mocks.discord import (
    MockDiscordBuilder,
    mock_discord_modules,  # noqa: F401
)


class DiscordSyncError(Exception):
    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


def _build_adapter(monkeypatch: pytest.MonkeyPatch):
    from astrbot.core.platform.sources.discord import discord_platform_adapter
    from astrbot.core.platform.sources.discord.discord_platform_adapter import (
        DiscordPlatformAdapter,
    )

    monkeypatch.setattr(discord_platform_adapter, "star_handlers_registry", [])
    monkeypatch.setattr(
        discord_platform_adapter.discord,
        "HTTPException",
        DiscordSyncError,
        raising=False,
    )

    adapter = DiscordPlatformAdapter(
        {"discord_command_register": True},
        {},
        asyncio.Queue(),
    )
    adapter.client = MockDiscordBuilder.create_client()
    return adapter


@pytest.mark.asyncio
async def test_discord_command_sync_ignores_daily_quota(monkeypatch):
    from astrbot.core.platform.sources.discord import discord_platform_adapter

    adapter = _build_adapter(monkeypatch)
    warning = Mock()
    monkeypatch.setattr(discord_platform_adapter.logger, "warning", warning)
    adapter.client.sync_commands.side_effect = DiscordSyncError(
        "Max number of daily application command creates reached",
        code=30034,
    )

    await adapter._collect_and_register_commands()

    adapter.client.sync_commands.assert_awaited_once()
    warning.assert_called_once()
    assert "30034" in warning.call_args.args[0]


class _FakeSlashCommand:
    """Minimal stand-in for `discord.SlashCommand` that keeps the command name."""

    def __init__(self, **kwargs) -> None:
        self.name = kwargs["name"]
        self.description = kwargs.get("description", "")


def _build_command_adapter(monkeypatch: pytest.MonkeyPatch):
    """Build an adapter whose `discord` reference is a self-contained stub.

    Other Discord test modules import the adapter while the real `discord`
    package is loaded, so the module-level `discord` reference of the adapter
    may point at the installed package instead of the mock. Detaching it keeps
    the command registration path independent of the installed package.
    """
    from astrbot.core.platform.sources.discord import discord_platform_adapter

    adapter = _build_adapter(monkeypatch)
    stub = MagicMock()
    stub.Option = MagicMock()
    stub.SlashCommandOptionType = MagicMock()
    stub.SlashCommandOptionType.string = 3
    stub.SlashCommand = _FakeSlashCommand
    stub.HTTPException = DiscordSyncError
    monkeypatch.setattr(discord_platform_adapter, "discord", stub)
    return adapter


def _make_command_handler(module_path: str, command_name: str):
    """Build a `StarHandlerMetadata` exposing a single slash command."""
    from astrbot.core.star.filter.command import CommandFilter
    from astrbot.core.star.star_handler import EventType, StarHandlerMetadata

    async def _handler(self, event):
        return None

    handler_md = StarHandlerMetadata(
        event_type=EventType.AdapterMessageEvent,
        handler_full_name=f"{module_path}_{command_name}",
        handler_name=command_name,
        handler_module_path=module_path,
        handler=_handler,
        event_filters=[],
    )
    handler_md.event_filters.append(
        CommandFilter(command_name, handler_md=handler_md),
    )
    return handler_md


@pytest.mark.asyncio
async def test_discord_command_sync_skips_handler_from_plugin_submodule(
    monkeypatch,
):
    """A handler defined in a plugin submodule must not abort the whole sync.

    `star_map` is keyed by the plugin's main module, so a handler registered
    from a submodule (e.g. a mixin class in `plugin/foo.py`) has a
    `handler_module_path` that is absent from `star_map`. Looking that key up
    directly raised `KeyError`, which aborted the collection loop before
    `sync_commands()` was reached, so *no* plugin's slash commands were
    registered.
    """
    from astrbot.core.platform.sources.discord import discord_platform_adapter
    from astrbot.core.star.star import StarMetadata

    adapter = _build_command_adapter(monkeypatch)

    plugin_meta = StarMetadata(name="example_plugin")
    plugin_meta.activated = True
    monkeypatch.setattr(
        discord_platform_adapter,
        "star_map",
        {"data.plugins.example_plugin.main": plugin_meta},
    )
    monkeypatch.setattr(
        discord_platform_adapter,
        "star_handlers_registry",
        [
            # Registered from a submodule of the plugin: not a `star_map` key.
            _make_command_handler("data.plugins.example_plugin.mixin", "sub_cmd"),
            # Registered from the plugin's main module.
            _make_command_handler("data.plugins.example_plugin.main", "cmd"),
        ],
    )

    await adapter._collect_and_register_commands()

    adapter.client.sync_commands.assert_awaited_once()
    registered = [
        call.args[0].name
        for call in adapter.client.add_application_command.call_args_list
    ]
    assert registered == ["cmd"]


@pytest.mark.asyncio
async def test_discord_command_sync_skips_deactivated_plugin(monkeypatch):
    """Commands of a deactivated plugin are not registered."""
    from astrbot.core.platform.sources.discord import discord_platform_adapter
    from astrbot.core.star.star import StarMetadata

    adapter = _build_command_adapter(monkeypatch)

    plugin_meta = StarMetadata(name="example_plugin")
    plugin_meta.activated = False
    monkeypatch.setattr(
        discord_platform_adapter,
        "star_map",
        {"data.plugins.example_plugin.main": plugin_meta},
    )
    monkeypatch.setattr(
        discord_platform_adapter,
        "star_handlers_registry",
        [_make_command_handler("data.plugins.example_plugin.main", "cmd")],
    )

    await adapter._collect_and_register_commands()

    adapter.client.sync_commands.assert_awaited_once()
    adapter.client.add_application_command.assert_not_called()
